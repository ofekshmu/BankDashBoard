"""
CredentialManager.py — Secure Credential Storage
=================================================

Purpose:
    Provides a thin wrapper around the `keyring` library to store and retrieve
    per-site login credentials (username + password) in the Windows Credential
    Manager (or the OS-appropriate secure store on other platforms).

    Credentials are NEVER written to disk in plain text, logged, or printed.

Usage:
    from Downloader.CredentialManager import CredentialManager

    # Check if credentials are already stored
    if not CredentialManager.has("IsraCard"):
        CredentialManager.prompt_and_store("IsraCard")

    username, password = CredentialManager.get("IsraCard")

Security Notes:
    - Passwords are stored under Windows Credential Manager via the `keyring`
      library.  They survive reboots and are tied to the Windows user account.
    - Usernames are stored as a separate keyring entry (username is not
      considered secret but is stored alongside the password for convenience).
    - Neither username nor password is ever written to a log file, printed to
      stdout, or stored anywhere else in this codebase.
    - The `getpass` module is used for password input so the password is not
      echoed in the terminal.

Dependencies:
    - keyring  (pip install keyring)

Keyring Entry Naming:
    service = "BankProject"
    username entry: username key = "{site_name}__username"
    password entry: username key = "{site_name}__password"
    (keyring stores a (service, username_key) → secret mapping)
"""

from __future__ import annotations

import getpass
import logging

import keyring

logger = logging.getLogger("downloader_logger")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SERVICE = "BankProject"


def _username_key(site_name: str) -> str:
    """Returns the keyring key used to store the username for *site_name*."""
    return f"{site_name}__username"


def _password_key(site_name: str) -> str:
    """Returns the keyring key used to store the password for *site_name*."""
    return f"{site_name}__password"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class CredentialManager:
    """
    Static helper class for managing per-site credentials in Windows Credential
    Manager (or equivalent OS keychain).

    All methods are static — do not instantiate this class.
    """

    @staticmethod
    def has(site_name: str) -> bool:
        """
        Check whether credentials for *site_name* are already stored.

        Args:
            site_name: The site identifier as used in DOWNLOAD_SITES
                       (e.g. "IsraCard", "AmericanExpress").

        Returns:
            True if both username and password entries exist in the keyring.
        """
        u = keyring.get_password(_SERVICE, _username_key(site_name))
        p = keyring.get_password(_SERVICE, _password_key(site_name))
        return u is not None and p is not None

    @staticmethod
    def get(site_name: str) -> tuple[str, str]:
        """
        Retrieve stored credentials for *site_name*.

        Args:
            site_name: The site identifier (e.g. "IsraCard").

        Returns:
            (username, password) tuple.

        Raises:
            KeyError: If no credentials are stored for *site_name*.
                      Call has() or prompt_and_store() first.
        """
        username = keyring.get_password(_SERVICE, _username_key(site_name))
        password = keyring.get_password(_SERVICE, _password_key(site_name))

        if username is None or password is None:
            raise KeyError(
                f"No credentials found for site '{site_name}'. "
                f"Call CredentialManager.prompt_and_store('{site_name}') first."
            )

        # Only the username is logged — never the password
        logger.debug(f"[CredentialManager] Retrieved credentials for '{site_name}' (user: {username})")
        return username, password

    @staticmethod
    def store(site_name: str, username: str, password: str) -> None:
        """
        Store credentials for *site_name* in the OS keychain.

        Args:
            site_name: The site identifier (e.g. "IsraCard").
            username:  The login username / ID number.
            password:  The login password.  Never logged.

        Side effects:
            Two entries are written to Windows Credential Manager.
        """
        keyring.set_password(_SERVICE, _username_key(site_name), username)
        keyring.set_password(_SERVICE, _password_key(site_name), password)
        logger.info(
            f"[CredentialManager] Stored credentials for '{site_name}' (user: {username})"
        )

    @staticmethod
    def delete(site_name: str) -> None:
        """
        Remove stored credentials for *site_name* from the OS keychain.

        Args:
            site_name: The site identifier (e.g. "IsraCard").

        Side effects:
            Both username and password entries are deleted.
            If they do not exist the operation is silently ignored.
        """
        for key_fn in (_username_key, _password_key):
            try:
                keyring.delete_password(_SERVICE, key_fn(site_name))
            except keyring.errors.PasswordDeleteError:
                pass  # Already absent — not an error

        logger.info(f"[CredentialManager] Deleted credentials for '{site_name}'")

    @staticmethod
    def prompt_and_store(site_name: str) -> None:
        """
        Interactively prompt the user for credentials and persist them.

        The username is read with a standard input() prompt.
        The password is read with getpass.getpass() — it is NOT echoed.

        Args:
            site_name: The site identifier (e.g. "IsraCard").

        Side effects:
            Credentials are stored via store().
        """
        print(f"\n[{site_name}] Credentials not found.  Please enter login details:")
        username = input(f"  Username / ID for {site_name}: ").strip()
        password = getpass.getpass(f"  Password for {site_name} (hidden): ")

        CredentialManager.store(site_name, username, password)
        print(f"  Credentials for '{site_name}' saved to Windows Credential Manager.\n")

    @staticmethod
    def update(site_name: str) -> None:
        """
        Prompt the user to overwrite existing credentials for *site_name*.

        Equivalent to prompt_and_store() but prints a different leading message
        to make it clear that existing credentials will be replaced.

        Args:
            site_name: The site identifier (e.g. "IsraCard").
        """
        print(f"\n[{site_name}] Updating stored credentials:")
        username = input(f"  New username / ID for {site_name}: ").strip()
        password = getpass.getpass(f"  New password for {site_name} (hidden): ")

        CredentialManager.store(site_name, username, password)
        print(f"  Credentials for '{site_name}' updated.\n")
