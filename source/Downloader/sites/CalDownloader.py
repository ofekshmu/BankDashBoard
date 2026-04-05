"""
CalDownloader.py — Automated Downloader for Cal (Leumi-Cal) Credit Card
========================================================================

Purpose:
    Implements the browser automation steps for logging in to the Cal
    (Leumi-Cal / כאל) online portal and downloading the Excel transaction
    file for a given billing month.

Supported Formats:
    - Cal  (identified by headers; cell currency detection enabled)

Portal URL:
    https://www.cal-online.co.il

2FA:
    Cal uses SMS OTP.  The base class login() handles the interactive pause.

Implementation Status:
    ** STUB — browser interaction methods not yet implemented. **
    To implement: fill in the four abstract methods using Playwright selectors
    captured via `playwright codegen https://www.cal-online.co.il`.

Notes on Cal-specific Export:
    - Cal's export page typically shows a date range picker.
    - The charge month (timestamp) is embedded inside each Excel cell — this
      is handled by the existing Cal format parser (Cell currency = True,
      TimeStamp Location = inner cell).  No special handling is needed here
      beyond downloading the correct month's file.
"""

from __future__ import annotations

import logging
from typing import Optional

from Downloader.BaseSiteDownloader import BaseSiteDownloader, DownloadTarget

logger = logging.getLogger("downloader_logger")


class CalDownloader(BaseSiteDownloader):
    """
    Downloads transaction Excel files from the Cal (Leumi-Cal) portal.

    Class Constants (fill in after live selector capture):
        LOGIN_URL              — Cal login page URL
        USERNAME_SELECTOR      — National ID input field selector
        PASSWORD_SELECTOR      — Password input field selector
        SUBMIT_SELECTOR        — Login submit button selector
        OTP_URL_PATTERN        — URL fragment for OTP verification page
        POST_LOGIN_URL_PATTERN — URL fragment on the post-login dashboard
        EXPORT_NAV_SELECTOR    — Link/button to the transactions export section
        MONTH_SELECTOR         — Billing-month selector
        DOWNLOAD_BTN_SELECTOR  — Excel export / download button
    """

    # -----------------------------------------------------------------------
    # Site constants — fill in after live selector capture
    # -----------------------------------------------------------------------

    LOGIN_URL: str = "https://www.cal-online.co.il/col-gui/accounts/logon.aspx"

    USERNAME_SELECTOR: str = ""  # TODO
    PASSWORD_SELECTOR: str = ""  # TODO
    SUBMIT_SELECTOR: str = ""    # TODO
    OTP_URL_PATTERN: str = ""    # TODO
    POST_LOGIN_URL_PATTERN: str = "cal-online.co.il"  # TODO: verify
    EXPORT_NAV_SELECTOR: str = ""   # TODO
    MONTH_SELECTOR: str = ""        # TODO
    DOWNLOAD_BTN_SELECTOR: str = "" # TODO

    # -----------------------------------------------------------------------
    # Abstract method implementations
    # -----------------------------------------------------------------------

    def navigate_to_login(self) -> None:
        """
        Navigate to the Cal login page and wait for the form to be ready.

        Steps:
            1. self._page.goto(self.LOGIN_URL)
            2. Wait for the username input to appear.
        """
        logger.debug(f"[Cal] Navigating to login page: {self.LOGIN_URL}")
        # TODO: self._page.goto(self.LOGIN_URL)
        # TODO: self._page.wait_for_selector(self.USERNAME_SELECTOR)
        raise NotImplementedError(
            "CalDownloader.navigate_to_login() is not yet implemented. "
            "Run `playwright codegen https://www.cal-online.co.il` to capture selectors."
        )

    def fill_credentials(self) -> None:
        """
        Fill the national ID and password fields and submit the login form.

        Uses self._username and self._password.  Neither is logged.
        """
        logger.debug("[Cal] Filling credentials")
        # TODO: self._page.fill(self.USERNAME_SELECTOR, self._username)
        # TODO: self._page.fill(self.PASSWORD_SELECTOR, self._password)
        # TODO: self._page.click(self.SUBMIT_SELECTOR)
        raise NotImplementedError("CalDownloader.fill_credentials() is not yet implemented.")

    def navigate_to_export(self, target: DownloadTarget) -> None:
        """
        Navigate to the export page for the given billing period.

        Args:
            target: Billing period to export.  If target.is_discovery is True,
                    use the default (most recent) billing period.

        Steps:
            1. Click the transactions navigation item.
            2. Select the target month using the billing-month picker.
               (Cal uses a month/year dropdown or date range.)
            3. Wait for the transaction list to load.
        """
        if target.is_discovery:
            logger.debug("[Cal] Discovery mode — default export page")
        else:
            logger.debug(f"[Cal] Navigating to export: {target.month:02d}/{target.year}")
        # TODO: Implement after selector capture
        raise NotImplementedError("CalDownloader.navigate_to_export() is not yet implemented.")

    def trigger_download(self, target: DownloadTarget) -> Optional[str]:
        """
        Click the Excel download button and return the saved file path.

        Args:
            target: The billing period being downloaded.

        Returns:
            Absolute path to the downloaded file, or None if unavailable.

        Implementation example:
            with self._page.expect_download() as dl_info:
                self._page.click(self.DOWNLOAD_BTN_SELECTOR)
            download = dl_info.value
            dest = os.path.join(self.download_dir, download.suggested_filename)
            download.save_as(dest)
            return dest
        """
        logger.debug(f"[Cal] Triggering download for {target}")
        # TODO: Implement after selector capture
        raise NotImplementedError("CalDownloader.trigger_download() is not yet implemented.")
