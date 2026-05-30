"""Shared Google OAuth token paths and loaders for Conlecta (repo / VPS local files)."""

import json
import os
import logging
import shutil
import time
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class GoogleTokenError(RuntimeError):
    """OAuth token missing, expired without refresh, or revoked (invalid_grant)."""


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

REFRESH_SKEW_SECONDS = int(os.environ.get("CONLECTA_OAUTH_REFRESH_SKEW_SECONDS") or 900)


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


def _read_token_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _read_token_scopes(path):
    data = _read_token_json(path)
    scopes = data.get("scopes") or []
    return {str(scope).strip() for scope in scopes if str(scope).strip()}


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


def _parse_expiry(value):
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _credentials_expiry(creds, token_path=""):
    expiry = _parse_expiry(getattr(creds, "expiry", None))
    if expiry:
        return expiry
    if token_path:
        return _parse_expiry(_read_token_json(token_path).get("expiry"))
    return None


def _needs_refresh(creds, token_path="", skew_seconds=None):
    if not creds or not getattr(creds, "refresh_token", None):
        return False
    skew = REFRESH_SKEW_SECONDS if skew_seconds is None else max(0, int(skew_seconds))
    if not getattr(creds, "valid", False):
        return True
    if getattr(creds, "expired", False):
        return True
    expiry = _credentials_expiry(creds, token_path)
    if not expiry:
        return False
    return expiry <= datetime.now(timezone.utc) + timedelta(seconds=skew)


def _is_invalid_grant(exc):
    text = str(exc or "").lower()
    return "invalid_grant" in text or "token has been expired or revoked" in text


def _load_installed_client_config():
    for path in credentials_file_candidates():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            block = data.get("installed") or data.get("web") or {}
            client_id = str(block.get("client_id") or "").strip()
            client_secret = str(block.get("client_secret") or "").strip()
            if client_id and client_secret:
                return {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "token_uri": str(block.get("token_uri") or "https://oauth2.googleapis.com/token").strip(),
                }
        except Exception as exc:
            log.warning("Google client config unreadable %s: %s", path, exc)
    return {}


def _repair_credentials(creds, token_path):
    if not creds:
        return creds
    from google.oauth2.credentials import Credentials

    data = _read_token_json(token_path)
    client_id = str(getattr(creds, "client_id", None) or data.get("client_id") or "").strip()
    client_secret = str(getattr(creds, "client_secret", None) or data.get("client_secret") or "").strip()
    token_uri = str(getattr(creds, "token_uri", None) or data.get("token_uri") or "https://oauth2.googleapis.com/token").strip()
    if not client_id or not client_secret:
        installed = _load_installed_client_config()
        client_id = client_id or installed.get("client_id", "")
        client_secret = client_secret or installed.get("client_secret", "")
        token_uri = token_uri or installed.get("token_uri", "https://oauth2.googleapis.com/token")

    refresh_token = getattr(creds, "refresh_token", None) or data.get("refresh_token")
    token = getattr(creds, "token", None) or data.get("token")
    scopes = list(getattr(creds, "scopes", None) or data.get("scopes") or [])
    expiry = _credentials_expiry(creds, token_path)

    info = {
        "token": token,
        "refresh_token": refresh_token,
        "token_uri": token_uri,
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": scopes,
    }
    if expiry is not None:
        info["expiry"] = expiry.isoformat().replace("+00:00", "Z")
    try:
        return Credentials.from_authorized_user_info(info)
    except Exception as exc:
        log.warning("Google token repair skipped for %s: %s", token_path, exc)
        return creds


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


def _quarantine_token(path, reason="invalid_grant"):
    if not path or not os.path.isfile(path):
        return ""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = f"{path}.{reason}.{stamp}.bak"
    try:
        shutil.move(path, backup)
        log.warning("Google token quarantined: %s -> %s", path, backup)
        return backup
    except Exception as exc:
        log.warning("Google token quarantine failed %s: %s", path, exc)
        return ""


def _refresh_credentials(creds, path):
    try:
        from google.auth.transport.requests import Request
    except Exception as exc:
        log.warning("Google auth refresh import failed: %s", exc)
        return creds, None

    creds = _repair_credentials(creds, path)
    if not creds or not getattr(creds, "refresh_token", None):
        return creds, None
    if not _needs_refresh(creds, path):
        return creds, None

    try:
        creds.refresh(Request())
        _persist_credentials(creds, path)
        _mirror_token_files(creds, path)
        log.info("Google token refreshed: %s (expiry=%s)", path, getattr(creds, "expiry", ""))
        return creds, None
    except Exception as exc:
        if _is_invalid_grant(exc):
            backup = _quarantine_token(path)
            msg = (
                f"Google refresh token revoked/expired for {path}. "
                "Re-run TokenGenerator.py on the VPS "
                "(python TokenGenerator.py --manual) after revoking old access at "
                "https://myaccount.google.com/permissions"
            )
            if backup:
                msg += f" Backup: {backup}"
            log.error(msg)
            return None, msg
        log.warning("Google token refresh failed %s: %s", path, exc)
        return creds, str(exc)


def _load_credentials_from_path(path, required_scopes):
    if not os.path.isfile(path):
        log.debug("Google token file missing: %s", path)
        return None, None
    try:
        from google.oauth2.credentials import Credentials
    except Exception as exc:
        log.warning("Google auth import failed: %s", exc)
        return None, None
    try:
        creds = Credentials.from_authorized_user_file(path)
    except Exception as exc:
        log.warning("Google token skipped %s: %s", path, exc)
        return None, None
    if not creds:
        return None, None

    creds = _repair_credentials(creds, path)
    if not _credentials_has_scopes(creds, required_scopes, path):
        log.info(
            "Google token %s lacks required scopes %s (has %s)",
            path,
            required_scopes,
            sorted(_read_token_scopes(path) or getattr(creds, "scopes", []) or []),
        )
        return None, None

    creds, refresh_error = _refresh_credentials(creds, path)
    if refresh_error and _is_invalid_grant(refresh_error):
        return None, refresh_error
    if creds and creds.valid:
        log.info("Google credentials loaded from %s", path)
        return creds, None
    return None, refresh_error or "Google token invalid or expired"


def load_credentials_for_scopes(required_scopes):
    """Load OAuth credentials that include all required scopes (oauth_token preferred)."""
    last_error = None
    for path in token_file_candidates():
        creds, err = _load_credentials_from_path(path, required_scopes)
        if creds:
            return creds, path
        if err:
            last_error = err
    return None, last_error


def load_gmail_credentials():
    return load_credentials_for_scopes(GMAIL_SCOPES)


def load_sheets_credentials():
    return load_credentials_for_scopes(SHEETS_SCOPES)


def load_google_credentials(scopes):
    """Backward-compatible loader with scope validation."""
    return load_credentials_for_scopes(scopes)


def warm_up_google_tokens():
    """Proactively refresh token files (call on server startup)."""
    results = {}
    for label, scopes in (
        ("gmail", GMAIL_SCOPES),
        ("sheets", SHEETS_SCOPES),
        ("combined", COMBINED_SCOPES),
    ):
        creds, err = load_credentials_for_scopes(scopes)
        results[label] = {
            "ok": bool(creds and creds.valid),
            "path": err if isinstance(err, str) and err else "",
            "error": err if not creds else "",
        }
        if creds and creds.valid:
            log.info("Google token warm-up OK (%s)", label)
        elif err:
            log.warning("Google token warm-up failed (%s): %s", label, err)
        else:
            log.warning("Google token warm-up failed (%s): no valid token", label)
    return results


def google_token_status():
    """Non-destructive status for logs / health checks."""
    status = {"files": [], "ready": {"gmail": False, "sheets": False}}
    for path in token_file_candidates():
        entry = {
            "path": path,
            "exists": os.path.isfile(path),
            "scopes": sorted(_read_token_scopes(path)) if os.path.isfile(path) else [],
        }
        if entry["exists"]:
            data = _read_token_json(path)
            entry["expiry"] = data.get("expiry") or ""
            entry["has_refresh_token"] = bool(data.get("refresh_token"))
        status["files"].append(entry)
    creds, _ = load_gmail_credentials()
    status["ready"]["gmail"] = bool(creds and creds.valid)
    creds, _ = load_sheets_credentials()
    status["ready"]["sheets"] = bool(creds and creds.valid)
    return status
