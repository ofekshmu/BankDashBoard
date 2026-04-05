"""
Downloader package
==================
Automated bank-file download pipeline.

Sub-modules:
    DownloadManager     — main orchestrator (entry point for AppManager)
    CredentialManager   — secure credential storage via Windows Credential Manager
    BaseSiteDownloader  — abstract base class + DownloadTarget dataclass
    sites/              — one concrete downloader class per banking site
"""
