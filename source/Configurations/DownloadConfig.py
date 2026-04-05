"""
DownloadConfig.py — Download Site Registry
==========================================

Purpose:
    Central registry that maps each banking site to:
      - The Playwright-based downloader class that handles it
      - The existing format names (from Formats.FORMATS) produced by that site
      - Whether the site is currently enabled for automated downloading
      - The expected download interval in months

Usage:
    Import DOWNLOAD_SITES to iterate over configured sites.
    Call validate_download_config() on startup to catch misconfiguration early.

Dependencies:
    - Configurations.Formats  (to validate format_names exist)

Notes:
    - Adding a new banking site: add an entry to DOWNLOAD_SITES and create a
      corresponding downloader class under source/Downloader/sites/.
    - Removing a site: set "enabled": False rather than deleting the entry,
      so historical last_download data in personal_config.json is preserved.
    - format_names must exactly match keys in Formats.FORMATS.
    - download_interval_months is informational only; the actual "missing" logic
      in DownloadManager computes gaps from the database, not from this value.
      This field is used to warn the user when a download is overdue.
"""

# ---------------------------------------------------------------------------
# Site Registry
# ---------------------------------------------------------------------------

DOWNLOAD_SITES: dict[str, dict] = {

    "IsraCard": {
        # Format names this site produces (must exist in Formats.FORMATS)
        "format_names": ["Isra-Card", "Isra-Card-2026"],

        # Downloader class name inside source/Downloader/sites/
        "downloader_class": "IsraCardDownloader",

        # Set to False to exclude this site from all automated downloads
        "enabled": True,

        # Expected gap between downloads (months). Used only for overdue warnings.
        "download_interval_months": 1,
    },

    "AmericanExpress": {
        "format_names": ["American-Express"],
        "downloader_class": "AmexDownloader",
        "enabled": True,
        "download_interval_months": 1,
    },

    "Cal": {
        "format_names": ["Cal"],
        "downloader_class": "CalDownloader",
        "enabled": True,
        "download_interval_months": 1,
    },

    "LeumiMax": {
        "format_names": ["Leumi-Max"],
        "downloader_class": "LeumiMaxDownloader",
        "enabled": True,
        "download_interval_months": 1,
    },

    "BeinLeumi": {
        # BeinLeumi-Bank-Date-Range is a companion file; both come from the same site.
        "format_names": ["BeinLeumi-Bank", "BeinLeumi-Bank-Date-Range"],
        "downloader_class": "BeinLeumiDownloader",
        "enabled": True,
        "download_interval_months": 1,
    },
}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_download_config() -> None:
    """
    Validate that every format_name declared in DOWNLOAD_SITES exists as a key
    in Formats.FORMATS.  Called once on AppManager startup.

    Raises:
        ValueError: If any declared format_name is not found in Formats.FORMATS,
                    with a message listing all broken references.
    """
    # Import here to avoid circular imports at module load time
    from Configurations.Formats import Formats

    known_formats: set[str] = set(Formats.FORMATS.keys())
    errors: list[str] = []

    for site_name, config in DOWNLOAD_SITES.items():
        for fmt in config["format_names"]:
            if fmt not in known_formats:
                errors.append(
                    f"  Site '{site_name}': format_name '{fmt}' not found in Formats.FORMATS"
                )

    if errors:
        raise ValueError(
            "DownloadConfig validation failed — the following format names are unknown:\n"
            + "\n".join(errors)
        )
