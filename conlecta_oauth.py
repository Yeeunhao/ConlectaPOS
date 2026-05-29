"""Shared Google OAuth token paths and loaders for Conlecta (repo / VPS local files)."""

import json
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
COMBINED_SCOPES = list(dict.fromkeys(GMAIL_SCOPES + SHEETS_SCOPES))


def token_file_candidates():
    paths = []
    seen = set()
    for path in (OAUTH_TOKEN_FILE, GMAIL_TOKEN_FILE):
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


def _read_token_scopes(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        scopes = data.get("scopes") or []
        return {str(scope).strip() for scope in scopes if str(scope).strip()}
    except Exception:
        return set()


def _credentials_has_scopes(creds, required_scopes, token_path=""):
    if not creds:
        return False
    required = {str(scope).strip() for scope in (required_scopes or []) if str(scope).strip()}
    if not required:
        return True
    granted = {str(scope).strip() for scope in (getattr(creds, "scopes", None) or []) if str(scope).strip()}
    if not granted and token_path:
        granted = _read_token_scopes(token_path)
    if not granted:
        return False
    return required.issubset(granted)


def _persist_credentials(creds, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(creds.to_json())


def _mirror_token_files(creds, source_path):
    if not creds or not getattr(creds, "valid", False):
        return
    source_abs = os.path.normcase(os.path.abspath(source_path))
    payload = creds.to_json()
    for path in token_file_candidates():
        target_abs = os.path.normcase(os.path.abspath(path))
        if target_abs == source_abs:
            continue
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(payload)
            log.info("Google token mirrored to %s", path)
        except Exception as exc:
            log.warning("Google token mirror failed %s: %s", path, exc)


def _refresh_credentials(creds, path):
    try:
        from google.auth.transport.requests import Request
    except Exception as exc:
        log.warning("Google auth refresh import failed: %s", exc)
        return creds
    if not creds or not creds.expired or not creds.refresh_token:
        return creds
    try:
        creds.refresh(Request())
        _persist_credentials(creds, path)
        _mirror_token_files(creds, path)
        log.info("Google token refreshed: %s", path)
    except Exception as exc:
        log.warning("Google token refresh failed %s: %s", path, exc)
    return creds


def _load_credentials_from_path(path, required_scopes):
    if not os.path.isfile(path):
        log.debug("Google token file missing: %s", path)
        return None
    try:
        from google.oauth2.credentials import Credentials
    except Exception as exc:
        log.warning("Google auth import failed: %s", exc)
        return None
    try:
        creds = Credentials.from_authorized_user_file(path, required_scopes)
    except Exception as exc:
        log.warning("Google token skipped %s: %s", path, exc)
        return None
    if not creds:
        return None
    if not _credentials_has_scopes(creds, required_scopes, path):
        log.info("Google token %s lacks required scopes %s", path, required_scopes)
        return None
    creds = _refresh_credentials(creds, path)
    if creds and creds.valid:
        log.info("Google credentials loaded from %s", path)
        return creds
    return None


def load_credentials_for_scopes(required_scopes):
    """Load OAuth credentials that include all required scopes (oauth_token preferred)."""
    for path in token_file_candidates():
        creds = _load_credentials_from_path(path, required_scopes)
        if creds:
            return creds, path
    return None, None


def load_gmail_credentials():
    return load_credentials_for_scopes(GMAIL_SCOPES)


def load_sheets_credentials():
    return load_credentials_for_scopes(SHEETS_SCOPES)


def load_google_credentials(scopes):
    """Backward-compatible loader with scope validation."""
    return load_credentials_for_scopes(scopes)
