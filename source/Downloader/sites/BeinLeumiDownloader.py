"""
BeinLeumiDownloader.py — Automated Downloader for Bank Leumi (BeinLeumi)
=========================================================================

Purpose:
    Implements the browser automation steps for logging in to the Bank Leumi
    (בנק לאומי) online banking portal and downloading the Excel bank-statement
    file for a given date range.

Supported Formats:
    - BeinLeumi-Bank            (standard headers, sort by serial number)
    - BeinLeumi-Bank-Date-Range (flipped table, associated with BeinLeumi-Bank)

Portal URL:
    https://hb2.bankleumi.co.il  (or the current active online-banking URL)

2FA:
    Bank Leumi uses SMS OTP.  The base class login() handles the pause.

Implementation Status:
    ** STUB — browser interaction methods not yet implemented. **
    To implement: fill in the four abstract methods using Playwright selectors
    captured via `playwright codegen https://hb2.bankleumi.co.il`.

Notes on BeinLeumi Export:
    - Bank statements cover a date range, not a billing cycle.
    - Two file formats are produced per export (BeinLeumi-Bank and
      BeinLeumi-Bank-Date-Range) — each is a different view of the same data.
    - The serial number in the filename is used for deduplication and sorting.
    - For the target month, download the statement from the 1st to the last
      day of that month.
"""

from __future__ import annotations

import logging
from typing import Optional

from Downloader.BaseSiteDownloader import BaseSiteDownloader, DownloadTarget

logger = logging.getLogger("downloader_logger")


class BeinLeumiDownloader(BaseSiteDownloader):
    """
    Downloads bank statement Excel files from the Bank Leumi online portal.

    Because BeinLeumi exports two associated files per period
    (BeinLeumi-Bank and BeinLeumi-Bank-Date-Range), trigger_download() may
    return the primary file path while also saving the companion file to
    self.download_dir.  Both are moved to INPUT_FOLDER by DownloadManager.

    Class Constants (fill in after live selector capture):
        LOGIN_URL              — Leumi online banking login URL
        USERNAME_SELECTOR      — Account number / ID input selector
        PASSWORD_SELECTOR      — Password input selector
        SUBMIT_SELECTOR        — Login submit button selector
        OTP_URL_PATTERN        — URL fragment for OTP page
        POST_LOGIN_URL_PATTERN — URL fragment on the post-login dashboard
        EXPORT_NAV_SELECTOR    — Navigation to the account activity / export section
        DATE_FROM_SELECTOR     — "From date" input selector
        DATE_TO_SELECTOR       — "To date" input selector
        DOWNLOAD_BTN_SELECTOR  — Export to Excel button selector
    """

    # -----------------------------------------------------------------------
    # Site constants — fill in after live selector capture
    # -----------------------------------------------------------------------

    LOGIN_URL: str = "https://hb2.bankleumi.co.il"

    USERNAME_SELECTOR: str = ""  # TODO
    PASSWORD_SELECTOR: str = ""  # TODO
    SUBMIT_SELECTOR: str = ""    # TODO
    OTP_URL_PATTERN: str = ""    # TODO
    POST_LOGIN_URL_PATTERN: str = "bankleumi.co.il"  # TODO: verify
    EXPORT_NAV_SELECTOR: str = ""     # TODO
    DATE_FROM_SELECTOR: str = ""      # TODO
    DATE_TO_SELECTOR: str = ""        # TODO
    DOWNLOAD_BTN_SELECTOR: str = ""   # TODO

    # -----------------------------------------------------------------------
    # Abstract method implementations
    # -----------------------------------------------------------------------

    def navigate_to_login(self) -> None:
        """
        Navigate to the Bank Leumi online banking login page.

        Steps:
            1. self._page.goto(self.LOGIN_URL)
            2. Wait for the username / account field to appear.
        """
        logger.debug(f"[BeinLeumi] Navigating to login page: {self.LOGIN_URL}")
        # TODO: self._page.goto(self.LOGIN_URL)
        # TODO: self._page.wait_for_selector(self.USERNAME_SELECTOR)
        raise NotImplementedError(
            "BeinLeumiDownloader.navigate_to_login() is not yet implemented. "
            "Run `playwright codegen https://hb2.bankleumi.co.il` to capture selectors."
        )

    def fill_credentials(self) -> None:
        """
        Enter the account number / ID and password, then submit the login form.

        Uses self._username and self._password.  Neither is logged.
        """
        logger.debug("[BeinLeumi] Filling credentials")
        # TODO: self._page.fill(self.USERNAME_SELECTOR, self._username)
        # TODO: self._page.fill(self.PASSWORD_SELECTOR, self._password)
        # TODO: self._page.click(self.SUBMIT_SELECTOR)
        raise NotImplementedError("BeinLeumiDownloader.fill_credentials() is not yet implemented.")

    def navigate_to_export(self, target: DownloadTarget) -> None:
        """
        Navigate to the account activity export section for the given period.

        Args:
            target: Billing period to export.  For bank statements this maps
                    to the first and last day of target.month/year.
                    If target.is_discovery is True, use the last 30 days.

        Steps:
            1. Click the account activity / transactions navigation item.
            2. Set the date range:
               - From: 01/<target.month>/<target.year>
               - To:   last day of <target.month>/<target.year>
            3. Wait for the transaction list to load.
        """
        if target.is_discovery:
            logger.debug("[BeinLeumi] Discovery mode — last 30 days")
        else:
            import calendar
            last_day = calendar.monthrange(target.year, target.month)[1]
            logger.debug(
                f"[BeinLeumi] Navigating to export: "
                f"01/{target.month:02d}/{target.year} – {last_day:02d}/{target.month:02d}/{target.year}"
            )
        # TODO: Implement after selector capture
        raise NotImplementedError("BeinLeumiDownloader.navigate_to_export() is not yet implemented.")

    def trigger_download(self, target: DownloadTarget) -> Optional[str]:
        """
        Click the Excel export button and save the bank statement file.

        Args:
            target: The period being exported.

        Returns:
            Absolute path to the primary downloaded .xls / .xlsx file, or None
            if no transactions exist for the given period.

        Notes:
            Bank Leumi may produce two files per export.  If both files are
            downloaded, save both to self.download_dir.  Return the primary
            file path; the companion will be picked up by the input-folder scan.

        Implementation example:
            with self._page.expect_download() as dl_info:
                self._page.click(self.DOWNLOAD_BTN_SELECTOR)
            download = dl_info.value
            dest = os.path.join(self.download_dir, download.suggested_filename)
            download.save_as(dest)
            return dest
        """
        logger.debug(f"[BeinLeumi] Triggering download for {target}")
        # TODO: Implement after selector capture
        raise NotImplementedError("BeinLeumiDownloader.trigger_download() is not yet implemented.")
