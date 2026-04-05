"""
Downloader.sites package
========================
Contains one concrete BaseSiteDownloader subclass per banking site.

Available downloaders:
    IsraCardDownloader   — israelcard.co.il  (Isra-Card, Isra-Card-2026)
    AmexDownloader       — americanexpress.co.il  (American-Express)
    CalDownloader        — cal-online.co.il  (Cal)
    LeumiMaxDownloader   — max.co.il  (Leumi-Max)
    BeinLeumiDownloader  — bankleumi.co.il  (BeinLeumi-Bank, BeinLeumi-Bank-Date-Range)

All methods that interact with a browser are currently stubs (raise
NotImplementedError).  Implement them by capturing selectors from a live
session using `playwright codegen <site_url>`.
"""
