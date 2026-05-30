"""Shared Google OAuth token paths and loaders for Conlecta (repo / VPS local files)."""

import json
import os
import logging
import shutil
import threading
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
ENV_FILE = _path_from_env("CONLECTA_ENV_FILE", ".env")
GMAIL_TOKEN_ENV_KEY = "CONLECTA_GMAIL_TOKEN_JSON"
OAUTH_TOKEN_ENV_KEY = "CONLECTA_OAUTH_TOKEN_JSON"
OAUTH_CREDS_ENV_KEY = "CONLECTA_OAUTH_CREDS_JSON"
OAUTH_CLIENT_ID_ENV = "CONLECTA_OAUTH_CLIENT_ID"
OAUTH_CLIENT_SECRET_ENV = "CONLECTA_OAUTH_CLIENT_SECRET"

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]
COMBINED_SCOPES = list(dict.fromkeys(GMAIL_SCOPES + SHEETS_SCOPES))

REFRESH_SKEW_SECONDS = int(os.environ.get("CONLECTA_OAUTH_REFRESH_SKEW_SECONDS") or 900)
REFRESH_LOOP_SECONDS = int(os.environ.get("CONLECTA_OAUTH_REFRESH_LOOP_SECONDS") or 600)

_ENV_LOADED = False


def ensure_env_loaded():
    """Load .env into os.environ (VPS deploy uses env vars instead of token/oauth files)."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        _ENV_LOADED = True
        return
    if os.path.isfile(ENV_FILE):
        load_dotenv(ENV_FILE)
    _ENV_LOADED = True


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


def _client_config_from_block(block, source=""):
    block = block or {}
    client_id = str(block.get("client_id") or "").strip()
    client_secret = str(block.get("client_secret") or "").strip()
    if not client_id or not client_secret:
        return {}
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "token_uri": str(block.get("token_uri") or "https://oauth2.googleapis.com/token").strip(),
        "source": source,
    }


def _load_client_config_from_env():
    ensure_env_loaded()
    raw = str(os.environ.get(OAUTH_CREDS_ENV_KEY) or "").strip()
    if raw:
        try:
            data = json.loads(raw)
            block = data.get("installed") or data.get("web") or data
            cfg = _client_config_from_block(block, f"env:{OAUTH_CREDS_ENV_KEY}")
            if cfg:
                return cfg
        except Exception as exc:
            log.warning("Google client config env %s is not valid JSON: %s", OAUTH_CREDS_ENV_KEY, exc)
    client_id = str(os.environ.get(OAUTH_CLIENT_ID_ENV) or "").strip()
    client_secret = str(os.environ.get(OAUTH_CLIENT_SECRET_ENV) or "").strip()
    if client_id and client_secret:
        return {
            "client_id": client_id,
            "client_secret": client_secret,
            "token_uri": "https://oauth2.googleapis.com/token",
            "source": f"env:{OAUTH_CLIENT_ID_ENV}",
        }
    return {}


def _load_client_config_from_tokens():
    for env_key in (OAUTH_TOKEN_ENV_KEY, GMAIL_TOKEN_ENV_KEY):
        cfg = _client_config_from_block(_read_token_json_from_env(env_key), f"env:{env_key}")
        if cfg:
            return cfg
    for path in token_file_candidates():
        cfg = _client_config_from_block(_read_token_json(path), path)
        if cfg:
            return cfg
    return {}


def _load_installed_client_config():
    ensure_env_loaded()
    for path in credentials_file_candidates():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            block = data.get("installed") or data.get("web") or {}
            cfg = _client_config_from_block(block, path)
            if cfg:
                return cfg
        except Exception as exc:
            log.warning("Google client config unreadable %s: %s", path, exc)
    cfg = _load_client_config_from_env()
    if cfg:
        return cfg
    return _load_client_config_from_tokens()


def load_client_config():
    """OAuth client id/secret from local json file, .env, or existing token payload."""
    return dict(_load_installed_client_config() or {})


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


def _token_env_key_for_path(path):
    target_abs = os.path.normcase(os.path.abspath(path))
    if target_abs == os.path.normcase(os.path.abspath(GMAIL_TOKEN_FILE)):
        return GMAIL_TOKEN_ENV_KEY
    if target_abs == os.path.normcase(os.path.abspath(OAUTH_TOKEN_FILE)):
        return OAUTH_TOKEN_ENV_KEY
    return ""


def _read_token_json_from_env(env_key):
    raw = str(os.environ.get(env_key) or "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception as exc:
        log.warning("Google token env %s is not valid JSON: %s", env_key, exc)
        return {}


def _upsert_env_file(path, updates):
    lines = []
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        except Exception:
            lines = []
    written = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            new_lines.append(line)
            continue
        key, _, _ = line.partition("=")
        key = key.strip()
        if key in updates:
            new_lines.append(f"{key}={json.dumps(updates[key], ensure_ascii=False)}")
            written.add(key)
        else:
            new_lines.append(line)
    for key, value in updates.items():
        if key not in written:
            new_lines.append(f"{key}={json.dumps(value, ensure_ascii=False)}")
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines).rstrip() + "\n")


def write_token_env(token_data, env_file=None):
    """Persist OAuth token JSON to .env for VPS deploy/clone without copying token files."""
    payload = json.dumps(token_data, ensure_ascii=False)
    updates = {
        GMAIL_TOKEN_ENV_KEY: token_data,
        OAUTH_TOKEN_ENV_KEY: token_data,
    }
    target = env_file or ENV_FILE
    _upsert_env_file(target, updates)
    os.environ[GMAIL_TOKEN_ENV_KEY] = payload
    os.environ[OAUTH_TOKEN_ENV_KEY] = payload
    log.info("Google OAuth tokens written to env file %s", target)


def sync_token_env_from_credentials(creds, path):
    env_key = _token_env_key_for_path(path)
    if not env_key or not creds:
        return
    try:
        data = json.loads(creds.to_json())
    except Exception:
        data = _read_token_json(path)
        if not data:
            return
    _upsert_env_file(ENV_FILE, {env_key: data})
    os.environ[env_key] = json.dumps(data, ensure_ascii=False)


def _persist_credentials(creds, path):
    token_data = json.loads(creds.to_json())
    with open(path, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    try:
        write_token_env(token_data)
    except Exception as exc:
        log.warning("Google token env sync failed for %s: %s", path, exc)


def _scopes_for_token_path(path):
    target_abs = os.path.normcase(os.path.abspath(path))
    gmail_abs = os.path.normcase(os.path.abspath(GMAIL_TOKEN_FILE))
    oauth_abs = os.path.normcase(os.path.abspath(OAUTH_TOKEN_FILE))
    if target_abs == gmail_abs:
        return GMAIL_SCOPES
    if target_abs == oauth_abs:
        return SHEETS_SCOPES
    return COMBINED_SCOPES


def _mirror_token_files(creds, source_path):
    if not creds or not getattr(creds, "valid", False):
        return
    source_abs = os.path.normcase(os.path.abspath(source_path))
    payload = creds.to_json()
    for path in token_file_candidates():
        target_abs = os.path.normcase(os.path.abspath(path))
        if target_abs == source_abs:
            continue
        if not _credentials_has_scopes(creds, _scopes_for_token_path(path), source_path):
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


def find_existing_token_data():
    """Return (token_dict, source_label) from .env first, then token files."""
    ensure_env_loaded()
    for env_key in (OAUTH_TOKEN_ENV_KEY, GMAIL_TOKEN_ENV_KEY):
        data = _read_token_json_from_env(env_key)
        if data.get("refresh_token") or data.get("token"):
            return data, f"env:{env_key}"
    for path in token_file_candidates():
        data = _read_token_json(path)
        if data.get("refresh_token") or data.get("token"):
            return data, path
    return {}, ""


def refresh_and_persist_tokens(force=False):
    """
    Load OAuth token from .env or token.json, refresh, write token files + .env.
    Does not require oauth_credentials.json when token already contains client_id/secret.
    """
    ensure_env_loaded()
    token_data, source = find_existing_token_data()
    if not token_data:
        return None, (
            "No OAuth token found. Set CONLECTA_GMAIL_TOKEN_JSON in .env "
            f"or create {GMAIL_TOKEN_FILE} on the server."
        )
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except Exception as exc:
        return None, f"Google auth libraries unavailable: {exc}"

    creds = Credentials.from_authorized_user_info(token_data)
    creds = _repair_credentials(creds, GMAIL_TOKEN_FILE)
    if not getattr(creds, "refresh_token", None):
        return None, f"Token from {source} has no refresh_token. Run TokenGenerator.py --generate --manual."

    if force or _needs_refresh(creds, GMAIL_TOKEN_FILE):
        try:
            creds.refresh(Request())
        except Exception as exc:
            if _is_invalid_grant(exc):
                return None, (
                    f"Refresh token revoked/expired ({source}). "
                    "Revoke app access at https://myaccount.google.com/permissions "
                    "then run TokenGenerator.py --generate --manual."
                )
            return None, f"Token refresh failed ({source}): {exc}"

    for path in token_file_candidates():
        _persist_credentials(creds, path)
    try:
        write_token_env(json.loads(creds.to_json()))
    except Exception as exc:
        log.warning("Google token env write failed: %s", exc)
    return creds, None


def _load_credentials_from_path(path, required_scopes):
    ensure_env_loaded()
    env_key = _token_env_key_for_path(path)
    if env_key:
        env_data = _read_token_json_from_env(env_key)
        if env_data:
            try:
                from google.oauth2.credentials import Credentials
                creds = Credentials.from_authorized_user_info(env_data)
                creds = _repair_credentials(creds, path)
                if _credentials_has_scopes(creds, required_scopes, path):
                    creds, refresh_error = _refresh_credentials(creds, path)
                    if refresh_error and _is_invalid_grant(refresh_error):
                        return None, refresh_error
                    if creds and creds.valid:
                        log.info("Google credentials loaded from env %s", env_key)
                        return creds, None
            except Exception as exc:
                log.warning("Google token env load failed (%s): %s", env_key, exc)

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
    """Gmail OTP/receipt always use token.json (CONLECTA_GMAIL_TOKEN_FILE)."""
    return _load_credentials_from_path(GMAIL_TOKEN_FILE, GMAIL_SCOPES)


def load_sheets_credentials():
    """Sheets sync uses oauth_token.json (CONLECTA_OAUTH_TOKEN_FILE)."""
    return _load_credentials_from_path(OAUTH_TOKEN_FILE, SHEETS_SCOPES)


def load_google_credentials(scopes):
    """Backward-compatible loader with scope validation."""
    return load_credentials_for_scopes(scopes)


def warm_up_google_tokens():
    """Proactively refresh token files (call on server startup)."""
    ensure_env_loaded()
    results = {}
    refreshed, refresh_err = refresh_and_persist_tokens(force=False)
    if refreshed:
        results["combined"] = {
            "ok": True,
            "path": "env+files",
            "error": "",
            "expiry": str(getattr(refreshed, "expiry", "") or ""),
            "has_refresh_token": bool(getattr(refreshed, "refresh_token", None)),
        }
        log.info(
            "Google token warm-up OK (combined, expiry=%s, refresh_token=%s)",
            getattr(refreshed, "expiry", ""),
            "yes" if getattr(refreshed, "refresh_token", None) else "no",
        )
    elif refresh_err:
        results["combined"] = {"ok": False, "path": "env+files", "error": refresh_err}
        log.warning("Google token warm-up failed (combined): %s", refresh_err)

    for label, loader, path in (
        ("gmail", load_gmail_credentials, GMAIL_TOKEN_FILE),
        ("sheets", load_sheets_credentials, OAUTH_TOKEN_FILE),
    ):
        creds, err = loader()
        results[label] = {
            "ok": bool(creds and creds.valid),
            "path": path,
            "error": err if not creds else "",
            "has_refresh_token": bool(getattr(creds, "refresh_token", None)) if creds else False,
        }
        if creds and creds.valid:
            log.info("Google token warm-up OK (%s)", label)
        elif err and not refreshed:
            log.warning("Google token warm-up failed (%s): %s", label, err)
        elif not creds and not refreshed:
            log.warning("Google token warm-up failed (%s): no valid token", label)
    return results


_REFRESH_LOOP_STARTED = False


def start_google_token_refresh_loop():
    """
    Background loop: when access token nears expiry, use refresh_token and
    write the new access token back to .env + token.json automatically.
    """
    global _REFRESH_LOOP_STARTED
    if _REFRESH_LOOP_STARTED:
        return
    _REFRESH_LOOP_STARTED = True

    def _loop():
        while True:
            time.sleep(REFRESH_LOOP_SECONDS)
            try:
                ensure_env_loaded()
                creds, err = refresh_and_persist_tokens(force=False)
                if creds:
                    log.info(
                        "Google OAuth auto-refresh OK (expiry=%s)",
                        getattr(creds, "expiry", ""),
                    )
                elif err:
                    log.warning("Google OAuth auto-refresh skipped: %s", err)
            except Exception as exc:
                log.warning("Google OAuth auto-refresh failed: %s", exc)

    threading.Thread(target=_loop, daemon=True, name="oauth-refresh-loop").start()
    log.info(
        "Google OAuth auto-refresh loop started (every %ss, renew ~%ss before expiry)",
        REFRESH_LOOP_SECONDS,
        REFRESH_SKEW_SECONDS,
    )


def google_token_status():
    """Non-destructive status for logs / health checks."""
    ensure_env_loaded()
    status = {
        "files": [],
        "env": {},
        "ready": {"gmail": False, "sheets": False},
        "auto_refresh_loop_seconds": REFRESH_LOOP_SECONDS,
        "refresh_skew_seconds": REFRESH_SKEW_SECONDS,
    }
    for env_key in (GMAIL_TOKEN_ENV_KEY, OAUTH_TOKEN_ENV_KEY):
        data = _read_token_json_from_env(env_key)
        status["env"][env_key] = {
            "present": bool(data),
            "has_refresh_token": bool(data.get("refresh_token")),
            "expiry": data.get("expiry") or "",
        }
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
