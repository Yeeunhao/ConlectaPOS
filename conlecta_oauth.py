"""Shared Google OAuth token paths and loaders for Conlecta (repo / VPS local files)."""

import os
import logging

log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _path_from_env(env_key, default_name):
    custom = str(os.environ.get(env_key) or "").strip()
    if custom:
        return custom if os.path.isabs(custom) else os.path.join(BASE_DIR, custom)
    return os.path.join(BASE_DIR, default_name)


OAUTH_CREDS_FILE = _path_from_env("CONLECTA_OAUTH_CREDS_FILE", "oauth_credentials.json")
OAUTH_TOKEN_FILE = _path_from_env("CONLECTA_OAUTH_TOKEN_FILE", "oauth_token.json")
GMAIL_TOKEN_FILE = _path_from_env("CONLECTA_GMAIL_TOKEN_FILE", "token.json")
CLIENT_SECRET_FILE = _path_from_env("CONLECTA_CLIENT_SECRET_FILE", "client_secret.json")

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


def token_file_candidates():
    paths = []
    seen = set()
    for path in (GMAIL_TOKEN_FILE, OAUTH_TOKEN_FILE):
        abspath = os.path.normcase(os.path.abspath(path))
        if abspath in seen:
            continue
        seen.add(abspath)
        paths.append(path)
    return paths


def credentials_file_candidates():
    paths = []
    seen = set()
    for path in (OAUTH_CREDS_FILE, CLIENT_SECRET_FILE):
        abspath = os.path.normcase(os.path.abspath(path))
        if abspath in seen:
            continue
        seen.add(abspath)
        if os.path.isfile(path):
            paths.append(path)
    return paths


def load_google_credentials(scopes):
    """Load and refresh OAuth credentials from repo-local token files."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except Exception as exc:
        log.warning("Google auth import failed: %s", exc)
        return None, None

    for path in token_file_candidates():
        if not os.path.isfile(path):
            log.debug("Google token file missing: %s", path)
            continue
        try:
            creds = Credentials.from_authorized_user_file(path, scopes)
            if not creds:
                continue
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(path, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
                log.info("Google token refreshed: %s", path)
            if creds.valid:
                log.info("Google credentials loaded from %s", path)
                return creds, path
        except Exception as exc:
            log.warning("Google token skipped %s: %s", path, exc)
    return None, None
