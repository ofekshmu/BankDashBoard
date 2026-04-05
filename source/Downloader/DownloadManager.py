"""
DownloadManager.py — Orchestrator for Automated Bank File Downloads
====================================================================

Purpose:
    Central coordinator that:
      1. Determines which files are missing from the database for each enabled site.
      2. Optionally prompts the user before downloading from each site
         ("ask_before_download" setting).
      3. Launches a Playwright browser session for each site that has missing
         files, instantiates the appropriate site downloader, and runs the
         download loop.
      4. Moves downloaded files from a temporary staging area to INPUT_FOLDER.
      5. Updates last_download timestamps in personal_config.json.
      6. Writes a full download log to Outputs/download_log.log.

Usage (from AppManager):
    from Downloader.DownloadManager import DownloadManager
    DownloadManager.run()

Usage (manage settings):
    DownloadManager.manage_sites()

Missing File Detection Logic:
    For each site, DownloadManager queries the File table in the SQLite database
    to find all (Format, Card_Number) pairs that belong to the site.  It then
    computes which charge-months are absent between the earliest known month
    and today.  If a site has no files at all (first time), a single
    "discovery" DownloadTarget (with month/year/card_number=None) is returned
    so the site downloader can download whatever the site's default view shows.

Skip Mid-Process:
    A threading.Event is used as the skip flag.  A background daemon thread
    reads stdin; if the user types 'skip' + Enter during an active download
    session, the event is set and the download loop checks it between targets.
    The flag is reset before each site's session begins.

Dependencies:
    - playwright.sync_api
    - pandas  (for date arithmetic on the file table DataFrame)
    - Downloader.CredentialManager
    - Downloader.BaseSiteDownloader  (DownloadTarget)
    - Configurations.DownloadConfig  (DOWNLOAD_SITES)
    - database  (DataBase)
    - Constants  (Paths)
"""

from __future__ import annotations

import importlib
import json
import logging
import logging.handlers
import os
import shutil
import threading
from datetime import datetime, date
from typing import Optional

import pandas as pd
from playwright.sync_api import sync_playwright

from Configurations.DownloadConfig import DOWNLOAD_SITES
from Downloader.BaseSiteDownloader import BaseSiteDownloader, DownloadTarget
from Downloader.CredentialManager import CredentialManager


# ---------------------------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------------------------
# A rotating file handler writes DEBUG+ to download_log.log.
# A stream handler writes WARNING+ to the console so normal terminal output
# is not cluttered with debug lines.

def _setup_logger() -> logging.Logger:
    """
    Create and configure the shared 'downloader_logger'.

    Returns the logger.  If the logger already has handlers it is returned as-is
    to avoid duplicating handlers across multiple DownloadManager.run() calls.
    """
    _log = logging.getLogger("downloader_logger")
    if _log.handlers:
        return _log  # Already configured

    _log.setLevel(logging.DEBUG)

    # Determine log file path relative to project root
    _here = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.dirname(os.path.dirname(_here))  # source/../
    _log_path = os.path.join(_project_root, "Outputs", "download_log.log")
    os.makedirs(os.path.dirname(_log_path), exist_ok=True)

    # Rotating file handler — DEBUG+
    fh = logging.handlers.RotatingFileHandler(
        _log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    # Stream (console) handler — WARNING+
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    _log.addHandler(fh)
    _log.addHandler(ch)
    return _log


logger = _setup_logger()


# ---------------------------------------------------------------------------
# DownloadManager
# ---------------------------------------------------------------------------

class DownloadManager:
    """
    Orchestrates the complete automated download pipeline for all enabled sites.

    All public entry points are class methods so AppManager can call them
    without instantiating the class.

    Class Methods:
        run()           — main download flow: detect missing files → download → move
        manage_sites()  — interactive sub-menu for enabling/disabling sites and
                          updating credentials
    """

    # -----------------------------------------------------------------------
    # Public entry points
    # -----------------------------------------------------------------------

    @classmethod
    def run(cls) -> None:
        """
        Main download flow.  Called from AppManager's menu option.

        Steps:
            1. Load download settings from personal_config.json.
            2. For each enabled site, compute missing DownloadTargets.
            3. If ask_before_download is True, prompt before each site.
            4. Launch Playwright, run the site downloader, move files.
            5. Persist last_download timestamps.

        Side effects:
            - Files downloaded to INPUT_FOLDER.
            - personal_config.json updated with last_download dates.
            - download_log.log updated.
        """
        logger.info("=" * 70)
        logger.info("DownloadManager.run() — session started")

        settings = cls._load_settings()
        ask_before = settings.get("ask_before_download", True)
        enabled_sites = [name for name, cfg in DOWNLOAD_SITES.items() if cfg["enabled"]]

        if not enabled_sites:
            print("No download sites are enabled.  Use 'Manage download sites' to enable them.")
            logger.info("No enabled sites — session ended early")
            return

        # Collect targets per site
        site_targets: dict[str, list[DownloadTarget]] = {}
        for site_name in enabled_sites:
            targets = cls._get_missing_targets(site_name)
            site_targets[site_name] = targets
            if targets:
                logger.info(f"[{site_name}] {len(targets)} missing target(s): "
                            + ", ".join(str(t) for t in targets))
            else:
                logger.info(f"[{site_name}] No missing files detected")

        # Filter to sites that actually have something to download
        sites_to_download = {s: t for s, t in site_targets.items() if t}
        if not sites_to_download:
            print("\nAll files are up to date.  Nothing to download.")
            logger.info("All sites up to date — session complete")
            return

        print(f"\nFiles to download:")
        for site_name, targets in sites_to_download.items():
            print(f"  {site_name}: {len(targets)} file(s)  "
                  + " | ".join(str(t) for t in targets))

        # Main download loop
        total_downloaded = 0
        for site_name, targets in sites_to_download.items():

            # ask_before_download gate
            if ask_before:
                ans = input(
                    f"\nDownload {len(targets)} file(s) from {site_name}? "
                    f"[Y / n / skip] (default Y): "
                ).strip().lower()
                if ans in ("n", "no", "skip", "s"):
                    logger.info(f"[{site_name}] Skipped by user (ask_before_download)")
                    print(f"  Skipped {site_name}.")
                    continue

            # Ensure credentials are available, using site-appropriate prompts
            cred_type = DOWNLOAD_SITES[site_name].get("credential_type", "bank")
            if not CredentialManager.has(site_name):
                CredentialManager.prompt_and_store(site_name, cred_type)

            credentials = CredentialManager.get(site_name)

            # Skip flag — set by background input thread when user types 'skip'
            skip_event = threading.Event()
            cls._start_skip_listener(skip_event)

            # Resolve downloader class
            downloader_cls = cls._load_downloader_class(site_name)
            if downloader_cls is None:
                continue

            logger.info(f"[{site_name}] Launching Playwright browser")
            downloaded_paths: list[str] = []

            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=False)
                    context = browser.new_context(accept_downloads=True)
                    page = context.new_page()

                    uses_otp = DOWNLOAD_SITES[site_name].get("uses_otp", True)
                    downloader: BaseSiteDownloader = downloader_cls(
                        site_name=site_name,
                        download_dir=cls._get_input_folder(),
                        credentials=credentials,
                        page=page,
                        skip_callback=skip_event.is_set,
                        uses_otp=uses_otp,
                    )

                    downloaded_paths = downloader.download(targets)
                    browser.close()

            except Exception as exc:
                logger.exception(f"[{site_name}] Unhandled error during download session: {exc}")
                print(f"  ERROR during {site_name} download: {exc}")
                continue
            finally:
                skip_event.set()  # Unblock the skip-listener thread so it can exit

            # Move files to INPUT_FOLDER (they may already be there if download_dir == INPUT_FOLDER)
            moved = cls._move_to_input_folder(downloaded_paths)
            total_downloaded += len(moved)

            # Persist last_download timestamp
            if moved:
                cls._update_last_download(site_name, settings)

            print(f"  [{site_name}] Done — {len(moved)} file(s) ready in input folder.")
            logger.info(f"[{site_name}] Session complete — {len(moved)} file(s) moved to INPUT_FOLDER")

        print(f"\nDownload session finished.  Total files ready: {total_downloaded}")
        logger.info(f"DownloadManager.run() complete — {total_downloaded} file(s) total")

    @classmethod
    def manage_sites(cls) -> None:
        """
        Interactive sub-menu for managing download site configuration.

        Options presented to the user:
            1. Enable / disable a site
            2. Update credentials for a site
            3. View last download dates
            4. Toggle 'ask before download'
            5. Back

        Side effects:
            - May update DownloadConfig.DOWNLOAD_SITES["enabled"] at runtime.
              (Persistent changes require editing DownloadConfig.py manually,
               which is by design — code is the source of truth for site config.)
            - Credentials are stored / deleted via CredentialManager.
            - ask_before_download flag is persisted in personal_config.json.
        """
        while True:
            settings = cls._load_settings()
            ask_before = settings.get("ask_before_download", True)

            print("\n--- Manage Download Sites ---")
            options = [
                "Enable / disable a site",
                "Update credentials for a site",
                "View last download dates and overdue status",
                f"Toggle 'ask before download'  (currently: {'ON' if ask_before else 'OFF'})",
                "Back",
            ]
            for i, opt in enumerate(options, start=1):
                print(f"  {i}. {opt}")

            choice = input("\nChoose an option: ").strip()
            if not choice.isdigit() or int(choice) not in range(1, len(options) + 1):
                print("Invalid choice.")
                continue

            choice = int(choice)

            if choice == 1:
                cls._toggle_site_enabled()
            elif choice == 2:
                cls._update_site_credentials()
            elif choice == 3:
                cls._show_last_download_dates(settings)
            elif choice == 4:
                settings["ask_before_download"] = not ask_before
                cls._save_settings(settings)
                state = "ON" if settings["ask_before_download"] else "OFF"
                print(f"  'ask before download' is now {state}.")
                logger.info(f"ask_before_download toggled to {settings['ask_before_download']}")
            elif choice == 5:
                break

    # -----------------------------------------------------------------------
    # Missing file detection
    # -----------------------------------------------------------------------

    @classmethod
    def _get_missing_targets(cls, site_name: str) -> list[DownloadTarget]:
        """
        Query the database to find which billing months are missing for *site_name*.

        For each (Format, Card_Number) pair that belongs to the site, the method
        finds all months between the earliest recorded month and today.
        Any month not present in the database is returned as a DownloadTarget.

        If no files exist for the site (first download), returns a single
        discovery DownloadTarget (month=None, card_number=None) so the
        site downloader can fetch whatever the default export view shows.

        Args:
            site_name: Key in DOWNLOAD_SITES.

        Returns:
            Sorted list of DownloadTarget objects (oldest missing month first).
        """
        # Import DataBase here to avoid circular imports at module level
        from database import DataBase

        site_config = DOWNLOAD_SITES[site_name]
        format_names: list[str] = site_config["format_names"]

        try:
            file_table: pd.DataFrame = DataBase().get_file_table()
        except Exception as exc:
            logger.exception(f"[{site_name}] Failed to query database: {exc}")
            return []

        # Filter to rows belonging to this site's formats
        site_files = file_table[file_table["Format"].isin(format_names)].copy()

        if site_files.empty:
            # No files ever downloaded for this site — use discovery target
            logger.info(
                f"[{site_name}] No existing files in database — returning discovery target"
            )
            return [DownloadTarget(format_name=format_names[0])]

        # Parse the Date column to datetime
        site_files["Date"] = pd.to_datetime(site_files["Date"], errors="coerce")
        site_files = site_files.dropna(subset=["Date"])

        today = datetime.today()
        targets: list[DownloadTarget] = []

        # Iterate over every (Format, Card_Number) combination found in the DB
        for (fmt, card), group in site_files.groupby(["Format", "Card_Number"]):
            existing: set[tuple[int, int]] = set()
            for dt in group["Date"]:
                existing.add((dt.year, dt.month))

            if not existing:
                continue

            # Generate the full range from the earliest month to today
            min_year, min_month = min(existing)
            y, m = min_year, min_month
            while (y, m) <= (today.year, today.month):
                if (y, m) not in existing:
                    # This month is missing — queue a download target
                    targets.append(DownloadTarget(
                        format_name=fmt,
                        card_number=str(card),
                        month=m,
                        year=y,
                    ))
                # Advance by one month
                m += 1
                if m > 12:
                    m = 1
                    y += 1

        targets.sort(key=lambda t: (t.year or 0, t.month or 0))
        return targets

    # -----------------------------------------------------------------------
    # Settings persistence
    # -----------------------------------------------------------------------

    @classmethod
    def _load_settings(cls) -> dict:
        """
        Load the download_settings section from personal_config.json.

        Returns:
            The download_settings dict.  If the section does not yet exist,
            returns a default structure with ask_before_download=True and
            empty site sub-dicts.

        Side effects:
            If the section was missing it is written back to the file with
            default values so future loads have a valid structure.
        """
        from Constants import Paths
        config_path = Paths.PERSONAL_CONFIG

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            logger.warning(f"Could not read personal_config.json: {exc}")
            config = {}

        if "download_settings" not in config:
            # First-time initialisation
            config["download_settings"] = cls._default_settings()
            cls._write_config(config, config_path)
            logger.info("Initialised download_settings in personal_config.json")

        return config["download_settings"]

    @classmethod
    def _save_settings(cls, settings: dict) -> None:
        """
        Persist updated download_settings back to personal_config.json.

        Args:
            settings: The complete download_settings dict to save.

        Side effects:
            Reads the current personal_config.json, replaces the
            download_settings key, and writes the file back.
        """
        from Constants import Paths
        config_path = Paths.PERSONAL_CONFIG

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            config = {}

        config["download_settings"] = settings
        cls._write_config(config, config_path)

    @classmethod
    def _update_last_download(cls, site_name: str, settings: dict) -> None:
        """
        Update the last_download date for *site_name* to today's date and
        persist to personal_config.json.

        Args:
            site_name: Key in DOWNLOAD_SITES.
            settings:  The current download_settings dict (mutated in place).
        """
        today_str = date.today().isoformat()
        if "sites" not in settings:
            settings["sites"] = {}
        if site_name not in settings["sites"]:
            settings["sites"][site_name] = {}
        settings["sites"][site_name]["last_download"] = today_str
        cls._save_settings(settings)
        logger.info(f"[{site_name}] Updated last_download to {today_str}")

    @staticmethod
    def _default_settings() -> dict:
        """Return the default download_settings structure."""
        return {
            "ask_before_download": True,
            "sites": {
                name: {"last_download": None, "interval_months": cfg["download_interval_months"]}
                for name, cfg in DOWNLOAD_SITES.items()
            },
        }

    @staticmethod
    def _write_config(config: dict, path: str) -> None:
        """Write the full config dict back to *path* as formatted JSON."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    # -----------------------------------------------------------------------
    # Helper: skip listener
    # -----------------------------------------------------------------------

    @staticmethod
    def _start_skip_listener(skip_event: threading.Event) -> None:
        """
        Start a daemon thread that reads stdin and sets *skip_event* if the
        user types 'skip' (case-insensitive) followed by Enter.

        The thread is a daemon so it does not prevent process exit.
        The thread exits naturally once skip_event is set or the main thread
        sets it (DownloadManager.run() sets it in the finally block).

        Args:
            skip_event: threading.Event shared with the download loop.
        """
        def _listen() -> None:
            print("  (type 'skip' + Enter at any time to skip remaining downloads for this site)")
            while not skip_event.is_set():
                try:
                    line = input()
                except EOFError:
                    break
                if line.strip().lower() == "skip":
                    skip_event.set()
                    break

        t = threading.Thread(target=_listen, daemon=True)
        t.start()

    # -----------------------------------------------------------------------
    # Helper: load downloader class dynamically
    # -----------------------------------------------------------------------

    @staticmethod
    def _load_downloader_class(site_name: str) -> Optional[type]:
        """
        Dynamically import and return the downloader class for *site_name*.

        The class name is taken from DOWNLOAD_SITES[site_name]["downloader_class"].
        The module is expected to live at Downloader.sites.<ClassName>.

        Args:
            site_name: Key in DOWNLOAD_SITES.

        Returns:
            The downloader class, or None if import fails.
        """
        class_name = DOWNLOAD_SITES[site_name]["downloader_class"]
        module_path = f"Downloader.sites.{class_name}"
        try:
            module = importlib.import_module(module_path)
            cls_obj = getattr(module, class_name)
            return cls_obj
        except (ImportError, AttributeError) as exc:
            logger.error(
                f"[{site_name}] Could not load downloader class '{class_name}' "
                f"from '{module_path}': {exc}"
            )
            print(f"  ERROR: Downloader for '{site_name}' not found ({exc}).  Skipping.")
            return None

    # -----------------------------------------------------------------------
    # Helper: file moving
    # -----------------------------------------------------------------------

    @staticmethod
    def _get_input_folder() -> str:
        """Return the absolute path to INPUT_FOLDER."""
        from Constants import Paths
        here = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(here))
        return os.path.join(project_root, Paths.INPUT_FOLDER)

    @staticmethod
    def _move_to_input_folder(file_paths: list[str]) -> list[str]:
        """
        Move downloaded files to INPUT_FOLDER if they are not already there.

        Args:
            file_paths: List of absolute paths to downloaded files.

        Returns:
            List of final destination paths.

        Side effects:
            Files are moved on disk.  Logs each move operation.
        """
        from Constants import Paths
        here = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(here))
        dest_folder = os.path.join(project_root, Paths.INPUT_FOLDER)
        os.makedirs(dest_folder, exist_ok=True)

        moved: list[str] = []
        for src in file_paths:
            if not os.path.exists(src):
                logger.warning(f"File not found after download: {src}")
                continue
            dest = os.path.join(dest_folder, os.path.basename(src))
            if os.path.abspath(src) != os.path.abspath(dest):
                shutil.move(src, dest)
                logger.info(f"Moved '{os.path.basename(src)}' → {dest}")
            moved.append(dest)
        return moved

    # -----------------------------------------------------------------------
    # Helper: manage_sites sub-actions
    # -----------------------------------------------------------------------

    @staticmethod
    def _toggle_site_enabled() -> None:
        """
        Interactively toggle the enabled/disabled state of a site.

        Note: This changes the in-memory DOWNLOAD_SITES dict for the current
        process run.  To make the change permanent, the user must edit
        DownloadConfig.py.  A reminder is printed after the toggle.
        """
        print("\n  Sites (current enabled status):")
        site_list = list(DOWNLOAD_SITES.keys())
        for i, name in enumerate(site_list, start=1):
            state = "ON " if DOWNLOAD_SITES[name]["enabled"] else "OFF"
            print(f"    {i}. [{state}] {name}")

        choice = input("  Choose site number (or 0 to cancel): ").strip()
        if not choice.isdigit() or int(choice) == 0:
            return

        idx = int(choice) - 1
        if idx < 0 or idx >= len(site_list):
            print("  Invalid choice.")
            return

        site_name = site_list[idx]
        DOWNLOAD_SITES[site_name]["enabled"] = not DOWNLOAD_SITES[site_name]["enabled"]
        new_state = "enabled" if DOWNLOAD_SITES[site_name]["enabled"] else "disabled"
        print(f"  '{site_name}' is now {new_state} for this session.")
        print(f"  To make this permanent, edit 'source/Configurations/DownloadConfig.py'.")
        logger.info(f"[{site_name}] Toggled to {new_state} via manage_sites")

    @staticmethod
    def _update_site_credentials() -> None:
        """Prompt the user to update credentials for a chosen site."""
        site_list = list(DOWNLOAD_SITES.keys())
        print("\n  Choose a site to update credentials:")
        for i, name in enumerate(site_list, start=1):
            has = "✓" if CredentialManager.has(name) else "✗"
            print(f"    {i}. [{has}] {name}")

        choice = input("  Site number (or 0 to cancel): ").strip()
        if not choice.isdigit() or int(choice) == 0:
            return

        idx = int(choice) - 1
        if idx < 0 or idx >= len(site_list):
            print("  Invalid choice.")
            return

        site_name = site_list[idx]
        cred_type = DOWNLOAD_SITES[site_name].get("credential_type", "bank")
        CredentialManager.update(site_name, cred_type)

    @staticmethod
    def _show_last_download_dates(settings: dict) -> None:
        """Print a table of last_download dates and overdue status per site."""
        today = date.today()
        print(f"\n  {'Site':<20} {'Last Download':<16} {'Interval':<10} Status")
        print("  " + "-" * 60)

        site_settings: dict = settings.get("sites", {})
        for site_name, site_cfg in DOWNLOAD_SITES.items():
            interval = site_cfg["download_interval_months"]
            saved = site_settings.get(site_name, {})
            last_str = saved.get("last_download", None)

            if last_str:
                last = date.fromisoformat(last_str)
                months_since = (today.year - last.year) * 12 + (today.month - last.month)
                overdue = months_since >= interval
                status = "OVERDUE" if overdue else "OK"
            else:
                last_str = "never"
                status = "NEVER DOWNLOADED"

            enabled_tag = "" if site_cfg["enabled"] else "  [disabled]"
            print(f"  {site_name:<20} {last_str:<16} {interval} month(s)   {status}{enabled_tag}")
        print()
