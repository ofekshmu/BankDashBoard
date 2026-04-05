"""
BaseSiteDownloader.py — Abstract Base Class for Banking Site Downloaders
========================================================================

Purpose:
    Defines the contract that every site-specific downloader must implement.
    Provides the shared login flow (including interactive 2FA pause) and the
    outer download loop that iterates over DownloadTargets, respecting the
    skip-callback provided by DownloadManager.

Usage:
    Subclass BaseSiteDownloader and implement the four abstract methods:
        - navigate_to_login()
        - fill_credentials()
        - navigate_to_export(target)
        - trigger_download(target)

    The concrete class should declare site-specific constants (LOGIN_URL,
    CSS selectors, etc.) as class-level attributes so the parent's generic
    login() flow can call the right subclass methods without knowing the
    site details.

Dependencies:
    - playwright.sync_api  (sync Playwright browser automation)
    - logging              (uses the shared 'downloader_logger' logger)

Key Concepts:
    DownloadTarget  — a dataclass identifying a single file to download,
                      characterised by format name, card number, month and year.
                      If card_number/month/year are None this is a "discovery"
                      download — the site should download whatever the default
                      view shows (used when the card has never been seen before).

    skip_callback   — a callable() → bool injected by DownloadManager.
                      Returns True when the user has requested to skip the
                      remaining targets for the current site.  The download
                      loop checks this between every target.

2FA / OTP Flow:
    1. fill_credentials() submits the login form.
    2. login() waits briefly for the page to stabilise.
    3. _is_on_2fa_page() is called — each subclass may override this to
       check for its own OTP indicator (URL pattern, element, etc.).
    4. If 2FA is detected the user is prompted in the terminal; execution
       blocks on input() while the user enters the OTP in the visible browser.
    5. After the user presses Enter, login() waits for navigation away from
       the 2FA page before returning.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Optional

from playwright.sync_api import Page

logger = logging.getLogger("downloader_logger")


# ---------------------------------------------------------------------------
# DownloadTarget
# ---------------------------------------------------------------------------

@dataclass
class DownloadTarget:
    """
    Identifies a single Excel file that should be downloaded from a banking site.

    Attributes:
        format_name (str): The format key from Formats.FORMATS that this file
            will be parsed as (e.g. "Isra-Card-2026").
        card_number (str | None): Last 4 digits (or other identifier) of the
            card/account.  None for a "discovery" download where the card
            number is not yet known.
        month (int | None): Charge month (1–12).  None for discovery.
        year (int | None): Charge year (e.g. 2026).  None for discovery.

    A target with month=None / year=None / card_number=None is a *discovery*
    target: the site downloader should download whatever the site's default
    export page shows (typically the most recent billing cycle) and the
    actual card number / month will be inferred from the downloaded filename.
    """
    format_name: str
    card_number: Optional[str] = None
    month: Optional[int] = None
    year: Optional[int] = None

    @property
    def is_discovery(self) -> bool:
        """True when this target has no specific period — download latest available."""
        return self.month is None or self.year is None

    def __str__(self) -> str:
        if self.is_discovery:
            return f"[{self.format_name}] discovery download"
        return f"[{self.format_name}] card={self.card_number}  {self.month:02d}/{self.year}"


# ---------------------------------------------------------------------------
# BaseSiteDownloader
# ---------------------------------------------------------------------------

class BaseSiteDownloader(ABC):
    """
    Abstract base class for all banking-site downloaders.

    Each concrete subclass handles exactly one banking site and must implement
    the four abstract methods below.  The shared login() and download() logic
    is provided here so that only site-specific details need to be written per
    subclass.

    Constructor Args:
        site_name (str): Human-readable site label used in log/print messages.
        download_dir (str): Absolute path to the folder where downloaded files
            should be saved (typically INPUT_FOLDER).
        credentials (tuple[str, str]): (username, password) retrieved from
            CredentialManager.  Never logged.
        page (Page): A Playwright Page object already attached to an open
            browser context.  Injected by DownloadManager so that a single
            browser session can be reused across multiple targets.
        skip_callback (Callable[[], bool]): Called before each target.
            Returns True when the user wants to skip the remaining targets
            for this site.

    Key Attributes:
        site_name     — label used in all log messages
        download_dir  — destination for downloaded files
        _username     — stored internally, never logged
        _password     — stored internally, never logged
        _page         — Playwright Page
        _skip         — skip_callback reference
    """

    # -----------------------------------------------------------------------
    # Subclass must set these class-level constants
    # -----------------------------------------------------------------------

    #: URL of the site's login page.  Must be overridden by every subclass.
    LOGIN_URL: str = ""

    #: CSS selector or XPath for the 2FA / OTP input or container.
    #: Override in the subclass if the site uses 2FA.  If left empty the
    #: base class will fall back to URL-pattern matching via _is_on_2fa_page().
    OTP_ELEMENT_SELECTOR: str = ""

    #: URL substring that appears on the 2FA / OTP page (used as fallback).
    OTP_URL_PATTERN: str = ""

    #: URL substring that indicates a successful post-login landing page.
    #: Used by login() to confirm that authentication succeeded.
    POST_LOGIN_URL_PATTERN: str = ""

    # -----------------------------------------------------------------------
    # Constructor
    # -----------------------------------------------------------------------

    def __init__(
        self,
        site_name: str,
        download_dir: str,
        credentials: tuple[str, str],
        page: Page,
        skip_callback: Callable[[], bool],
        uses_otp: bool = True,
    ) -> None:
        self.site_name = site_name
        self.download_dir = download_dir
        self._username, self._password = credentials
        self._page = page
        self._skip = skip_callback
        # Whether this site requires an SMS/OTP step after credential submission.
        # Card sites: True.  Bank sites: False.
        self._uses_otp = uses_otp

    # -----------------------------------------------------------------------
    # Abstract methods — implement in each subclass
    # -----------------------------------------------------------------------

    @abstractmethod
    def navigate_to_login(self) -> None:
        """
        Navigate the browser to the site's login page.

        Implementation notes:
            Use self._page.goto(self.LOGIN_URL) as the minimum.  If the site
            requires accepting cookies or dismissing a popup before the login
            form is visible, handle that here.

        Side effects:
            Browser navigates to the login page.
        """

    @abstractmethod
    def fill_credentials(self) -> None:
        """
        Locate and fill the username / password fields, then submit the form.

        Implementation notes:
            Use self._username and self._password.  Never print or log these.
            After filling, click the submit button or press Enter.

        Side effects:
            Login form submitted; page begins navigation to either the 2FA
            page or the post-login landing page.
        """

    @abstractmethod
    def navigate_to_export(self, target: DownloadTarget) -> None:
        """
        Navigate to the page where the export/download for *target* can be
        triggered.

        Args:
            target: Specifies which billing period and card to navigate to.
                    If target.is_discovery is True, navigate to the default
                    export view (most recent period).

        Side effects:
            Browser is on the export/download page for the given target.
        """

    @abstractmethod
    def trigger_download(self, target: DownloadTarget) -> Optional[str]:
        """
        Click the download/export button and wait for the file to be saved.

        Args:
            target: Used to select the correct export format or period if the
                    site shows multiple options.

        Returns:
            Absolute path to the downloaded file, or None if the download was
            not possible for this target (e.g. the billing period does not
            exist on the site).

        Side effects:
            One Excel / CSV file is saved to self.download_dir.
        """

    # -----------------------------------------------------------------------
    # Shared login flow
    # -----------------------------------------------------------------------

    def login(self) -> bool:
        """
        Execute the full login sequence: navigate → fill credentials → handle 2FA.

        The method blocks on input() if a 2FA / OTP page is detected, giving
        the user time to enter the code in the visible browser window.  After
        the user presses Enter the method waits for the browser to navigate
        away from the 2FA page before returning.

        Returns:
            True  if login succeeded (browser is on a post-login page).
            False if login failed (an error page or timeout was detected).

        Raises:
            playwright.sync_api.TimeoutError: If the page does not respond
                within the Playwright default timeout after credential entry.
        """
        logger.info(f"[{self.site_name}] Starting login — navigating to {self.LOGIN_URL}")
        self.navigate_to_login()

        logger.info(f"[{self.site_name}] Filling credentials (username: {self._username})")
        self.fill_credentials()

        # Give the page a moment to react to form submission
        try:
            self._page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            # Some sites navigate away before reaching networkidle — that is fine
            pass

        # --- 2FA / OTP handling (card sites only) ---
        if self._uses_otp and self._is_on_2fa_page():
            logger.info(f"[{self.site_name}] 2FA / OTP page detected")
            print(
                f"\n[{self.site_name}] OTP prompt detected.\n"
                f"  Please enter the OTP in the browser window, then press Enter here to continue..."
            )
            input()  # Block until user has completed OTP entry in the browser
            logger.info(f"[{self.site_name}] User confirmed OTP entry — waiting for navigation")

            # Wait for the browser to move away from the 2FA page
            try:
                self._page.wait_for_url(
                    lambda url: self.OTP_URL_PATTERN not in url,
                    timeout=60_000,
                )
            except Exception:
                # If we can't confirm navigation, proceed anyway and let
                # navigate_to_export() fail gracefully if still on OTP page
                logger.warning(
                    f"[{self.site_name}] Could not confirm navigation away from OTP page — proceeding"
                )

        # --- Confirm login success ---
        current_url = self._page.url
        if self.POST_LOGIN_URL_PATTERN and self.POST_LOGIN_URL_PATTERN not in current_url:
            logger.warning(
                f"[{self.site_name}] Login may have failed — "
                f"expected URL pattern '{self.POST_LOGIN_URL_PATTERN}', got '{current_url}'"
            )
            return False

        logger.info(f"[{self.site_name}] Login successful — current URL: {current_url}")
        return True

    # -----------------------------------------------------------------------
    # Outer download loop
    # -----------------------------------------------------------------------

    def download(self, targets: list[DownloadTarget]) -> list[str]:
        """
        Run the full download session for a list of targets.

        Sequence for each target:
            1. Check skip_callback — if True, abort remaining targets.
            2. Call navigate_to_export(target).
            3. Call trigger_download(target).
            4. Append the returned file path (if not None) to results.
            5. Prompt user to continue or skip (if ask_before_each is needed,
               this is handled at the DownloadManager level, not here).

        Args:
            targets: List of DownloadTarget objects to process in order.
                     Typically provided by DownloadManager.get_missing_targets().

        Returns:
            List of absolute paths to successfully downloaded files.

        Side effects:
            Files are saved to self.download_dir.
            Login is performed once before the first target.
        """
        downloaded: list[str] = []

        if not targets:
            logger.info(f"[{self.site_name}] No targets to download — skipping session")
            return downloaded

        logger.info(
            f"[{self.site_name}] Starting download session for {len(targets)} target(s): "
            + ", ".join(str(t) for t in targets)
        )

        # Login once per session
        login_ok = self.login()
        if not login_ok:
            logger.error(f"[{self.site_name}] Login failed — aborting download session")
            print(f"[{self.site_name}] Login failed. Skipping this site.")
            return downloaded

        for idx, target in enumerate(targets, start=1):
            # Check if the user has requested a skip mid-process
            if self._skip():
                logger.info(
                    f"[{self.site_name}] Skip requested by user after {len(downloaded)} "
                    f"download(s) — aborting remaining {len(targets) - idx + 1} target(s)"
                )
                print(f"[{self.site_name}] Skipping remaining downloads.")
                break

            logger.info(
                f"[{self.site_name}] Downloading target {idx}/{len(targets)}: {target}"
            )
            print(f"  [{self.site_name}] Downloading {target}  ({idx}/{len(targets)})")

            try:
                self.navigate_to_export(target)
                file_path = self.trigger_download(target)
            except Exception as exc:
                logger.exception(
                    f"[{self.site_name}] Error while downloading {target}: {exc}"
                )
                print(f"  [{self.site_name}] ERROR for {target}: {exc}")
                continue

            if file_path:
                downloaded.append(file_path)
                import os
                size_kb = os.path.getsize(file_path) / 1024 if os.path.exists(file_path) else 0
                logger.info(
                    f"[{self.site_name}] Downloaded '{os.path.basename(file_path)}' "
                    f"({size_kb:.1f} KB) → {file_path}"
                )
                print(f"  [{self.site_name}] Saved: {os.path.basename(file_path)}")
            else:
                logger.warning(
                    f"[{self.site_name}] trigger_download returned None for {target} "
                    f"— period may not be available on the site"
                )

        logger.info(
            f"[{self.site_name}] Session complete — "
            f"{len(downloaded)}/{len(targets)} file(s) downloaded"
        )
        return downloaded

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _is_on_2fa_page(self) -> bool:
        """
        Heuristic check: is the current page a 2FA / OTP page?

        Strategy (in order):
            1. If OTP_ELEMENT_SELECTOR is set, look for that element.
            2. If OTP_URL_PATTERN is set, check if it appears in the current URL.
            3. Default: return False (no 2FA detected).

        Subclasses may override this method to provide a more reliable check
        using site-specific selectors or URL patterns.

        Returns:
            True if the current page looks like a 2FA / OTP page.
        """
        if self.OTP_ELEMENT_SELECTOR:
            element = self._page.query_selector(self.OTP_ELEMENT_SELECTOR)
            if element:
                return True

        if self.OTP_URL_PATTERN and self.OTP_URL_PATTERN in self._page.url:
            return True

        return False
