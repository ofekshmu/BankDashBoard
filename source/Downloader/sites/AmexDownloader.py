"""
AmexDownloader.py — Automated Downloader for American Express Israel
=====================================================================

Purpose:
    Implements the browser automation steps required to log in to the
    American Express Israel portal (americanexpress.co.il) and download
    the Excel transaction file for a given billing month and card number.

Supported Formats:
    - American-Express  (identified by cell (4,0) containing the card label)

Portal URL:
    https://www.americanexpress.co.il

2FA:
    AmEx Israel uses SMS OTP.  The base class login() handles the pause.

Implementation Status:
    ** STUB — browser interaction methods not yet implemented. **
    The class structure, constants, and docstrings are complete.
    To implement: fill in the four abstract methods using selectors captured
    from a live session via `playwright codegen https://www.americanexpress.co.il`.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from Downloader.BaseSiteDownloader import BaseSiteDownloader, DownloadTarget

logger = logging.getLogger("downloader_logger")


class AmexDownloader(BaseSiteDownloader):
    """
    Downloads transaction Excel files from the American Express Israel portal.

    Class Constants (fill in after live selector capture):
        LOGIN_URL              — URL of the login page
        USERNAME_SELECTOR      — CSS selector for the ID number input
        PASSWORD_SELECTOR      — CSS selector for the password input
        SUBMIT_SELECTOR        — CSS selector for the login submit button
        OTP_URL_PATTERN        — URL fragment for the OTP/SMS verification page
        POST_LOGIN_URL_PATTERN — URL fragment on the post-login landing page
        EXPORT_NAV_SELECTOR    — Selector to reach the transactions/export section
        MONTH_SELECTOR         — Selector for the billing month picker
        DOWNLOAD_BTN_SELECTOR  — Selector for the Excel export button
    """

    # -----------------------------------------------------------------------
    # Site constants — fill in after live selector capture
    # -----------------------------------------------------------------------

    LOGIN_URL: str = "https://www.americanexpress.co.il/LOGIN"

    USERNAME_SELECTOR: str = ""  # TODO
    PASSWORD_SELECTOR: str = ""  # TODO
    SUBMIT_SELECTOR: str = ""    # TODO
    OTP_URL_PATTERN: str = ""    # TODO
    POST_LOGIN_URL_PATTERN: str = ""  # TODO
    EXPORT_NAV_SELECTOR: str = ""  # TODO
    MONTH_SELECTOR: str = ""     # TODO
    DOWNLOAD_BTN_SELECTOR: str = ""  # TODO

    # -----------------------------------------------------------------------
    # Abstract method implementations
    # -----------------------------------------------------------------------

    def navigate_to_login(self) -> None:
        """
        Navigate to the AmEx Israel login page and wait for the form to appear.

        Steps:
            1. self._page.goto(self.LOGIN_URL)
            2. Wait for the username input to be visible.
        """
        logger.debug(f"[AmericanExpress] Navigating to login page: {self.LOGIN_URL}")
        # TODO: self._page.goto(self.LOGIN_URL)
        # TODO: self._page.wait_for_selector(self.USERNAME_SELECTOR)
        raise NotImplementedError(
            "AmexDownloader.navigate_to_login() is not yet implemented. "
            "Run `playwright codegen https://www.americanexpress.co.il` to capture selectors."
        )

    def fill_credentials(self) -> None:
        """
        Enter the national ID and password, then submit the login form.

        Uses self._username (national ID) and self._password.  Neither is logged.
        """
        logger.debug("[AmericanExpress] Filling credentials")
        # TODO: self._page.fill(self.USERNAME_SELECTOR, self._username)
        # TODO: self._page.fill(self.PASSWORD_SELECTOR, self._password)
        # TODO: self._page.click(self.SUBMIT_SELECTOR)
        raise NotImplementedError("AmexDownloader.fill_credentials() is not yet implemented.")

    def navigate_to_export(self, target: DownloadTarget) -> None:
        """
        Navigate to the transactions export page for the given billing month.

        Args:
            target: Billing period and card number to download.  If
                    target.is_discovery is True, use the site's default
                    (most recent) billing period.

        Steps:
            1. Click the export / transactions navigation item.
            2. Select the target month from the billing-month picker.
            3. If multiple cards, select target.card_number.
            4. Wait for transaction table to load.
        """
        if target.is_discovery:
            logger.debug("[AmericanExpress] Discovery mode — default export page")
        else:
            logger.debug(
                f"[AmericanExpress] Navigating to export: card={target.card_number} "
                f"{target.month:02d}/{target.year}"
            )
        # TODO: Implement after selector capture
        raise NotImplementedError("AmexDownloader.navigate_to_export() is not yet implemented.")

    def trigger_download(self, target: DownloadTarget) -> Optional[str]:
        """
        Click the Excel export button and return the path to the saved file.

        Args:
            target: Billing period being exported.

        Returns:
            Absolute path to the downloaded .xls / .xlsx file, or None if
            the period is not available.

        Implementation example (after selector capture):
            with self._page.expect_download() as dl_info:
                self._page.click(self.DOWNLOAD_BTN_SELECTOR)
            download = dl_info.value
            dest = os.path.join(self.download_dir, download.suggested_filename)
            download.save_as(dest)
            return dest
        """
        logger.debug(f"[AmericanExpress] Triggering download for {target}")
        # TODO: Implement after selector capture
        raise NotImplementedError("AmexDownloader.trigger_download() is not yet implemented.")
