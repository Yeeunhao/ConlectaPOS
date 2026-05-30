# =========================================================
# TokenGenerator.py
#
# Google OAuth for Conlecta (VPS-friendly):
#   python3 TokenGenerator.py                    refresh/sync .env + token.json
#   python3 TokenGenerator.py --generate         new login (client_secret.json + browser)
#   python3 TokenGenerator.py --generate --manual   headless VPS paste-code flow
#   python3 gmail_token_generator.py             same as --generate (legacy name)
# =========================================================

import argparse
import json
import os
import sys
import webbrowser

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from conlecta_oauth import (
    CLIENT_SECRET_FILE,
    COMBINED_SCOPES,
    ENV_FILE,
    GMAIL_TOKEN_ENV_KEY,
    GMAIL_TOKEN_FILE,
    OAUTH_CLIENT_ID_ENV,
    OAUTH_CLIENT_SECRET_ENV,
    OAUTH_CREDS_ENV_KEY,
    OAUTH_CREDS_FILE,
    OAUTH_TOKEN_ENV_KEY,
    OAUTH_TOKEN_FILE,
    ensure_env_loaded,
    find_existing_token_data,
    diagnose_oauth_files,
    load_client_config,
    refresh_and_persist_tokens,
    resolve_client_secrets_path,
    write_token_env,
)

SCOPES = COMBINED_SCOPES


def _client_config_help():
    print("OAuth client config (VM only — never commit to git):")
    print(f"  1) {CLIENT_SECRET_FILE} on the VPS (recommended, same as gmail_token_generator.py)")
    print(f"  2) {OAUTH_CREDS_FILE}")
    print(f"  3) {OAUTH_CREDS_ENV_KEY} in {ENV_FILE}")
    print(f"  4) {OAUTH_CLIENT_ID_ENV} + {OAUTH_CLIENT_SECRET_ENV} in {ENV_FILE}")
    print("  5) client_id/client_secret inside existing token.json / .env token JSON")
    print()


def _resolve_client_config():
    cfg = load_client_config()
    if cfg.get("client_id") and cfg.get("client_secret"):
        return cfg
    return {}


def _flow_client_config(client_config):
    return {
        "installed": {
            "client_id": client_config["client_id"],
            "client_secret": client_config["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": client_config.get("token_uri") or "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }


def _load_oauth_client_block(secret_path=""):
    if secret_path and os.path.isfile(secret_path):
        try:
            with open(secret_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("installed") or data.get("web") or {}
        except Exception:
            return {}
    return {}


def _resolve_redirect_uri(secret_path=""):
    block = _load_oauth_client_block(secret_path)
    uris = [str(u).strip() for u in (block.get("redirect_uris") or []) if str(u).strip()]
    if uris:
        return uris[0]
    return "http://localhost"


def _is_headless_environment():
    if str(os.environ.get("CONLECTA_OAUTH_FORCE_MANUAL") or "").strip() == "1":
        return True
    if sys.platform in ("win32", "darwin"):
        return False
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        return False
    return True


def _create_flow(client_config):
    secret_path = resolve_client_secrets_path()
    source = str(client_config.get("source") or "")
    if not secret_path and source and os.path.isfile(source):
        secret_path = source
    if secret_path and os.path.isfile(secret_path):
        flow = InstalledAppFlow.from_client_secrets_file(secret_path, SCOPES)
    else:
        flow = InstalledAppFlow.from_client_config(_flow_client_config(client_config), SCOPES)
    redirect_uri = _resolve_redirect_uri(secret_path)
    flow.redirect_uri = redirect_uri
    return flow, redirect_uri


def _parse_authorization_response(raw):
    text = str(raw or "").strip()
    if not text:
        return ""
    if "code=" in text:
        code = text.split("code=", 1)[1]
        return code.split("&", 1)[0].strip()
    return text


def _run_manual_oauth(flow, redirect_uri):
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    print("\nOpen this URL in a browser on ANY device (laptop/phone):\n")
    print(auth_url)
    print(f"\nRedirect URI: {redirect_uri}")
    print("\nAfter you approve access:")
    print("- Browser may show 'This site can't be reached' — that is OK.")
    print("- Copy the FULL address bar URL (http://localhost/?code=...)")
    print("- Or copy only the code= value and paste below.\n")
    raw = input("Redirect URL or authorization code: ").strip()
    code = _parse_authorization_response(raw)
    if not code:
        raise ValueError("No authorization code received.")
    flow.fetch_token(code=code)
    return flow.credentials


def _run_oauth_flow(client_config, manual=False):
    flow, redirect_uri = _create_flow(client_config)
    use_manual = manual or _is_headless_environment()

    if use_manual:
        if not manual and _is_headless_environment():
            print("[INFO] VPS/headless server detected — using manual OAuth (paste code).\n")
        return _run_manual_oauth(flow, redirect_uri)

    try:
        return flow.run_local_server(
            port=0,
            open_browser=True,
            access_type="offline",
            prompt="consent",
        )
    except (webbrowser.Error, OSError) as exc:
        print(f"[INFO] Browser unavailable ({exc}) — switching to manual OAuth.\n")
        flow, redirect_uri = _create_flow(client_config)
        return _run_manual_oauth(flow, redirect_uri)


def _save_tokens(creds):
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or SCOPES),
        "universe_domain": getattr(creds, "universe_domain", "googleapis.com"),
        "account": "",
    }
    if getattr(creds, "expiry", None):
        expiry = creds.expiry
        if expiry.tzinfo is None:
            token_data["expiry"] = expiry.isoformat() + "Z"
        else:
            token_data["expiry"] = expiry.astimezone().isoformat().replace("+00:00", "Z")

    for path in (GMAIL_TOKEN_FILE, OAUTH_TOKEN_FILE):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(token_data, f, indent=4)
        print(f"Saved {path}")

    try:
        write_token_env(token_data)
        print(f"Saved OAuth tokens to {ENV_FILE} ({GMAIL_TOKEN_ENV_KEY}, {OAUTH_TOKEN_ENV_KEY})")
    except Exception as exc:
        print(f"[WARNING] Failed to write OAuth tokens to .env: {exc}")


def _remove_old_tokens():
    for path in (GMAIL_TOKEN_FILE, OAUTH_TOKEN_FILE):
        if not os.path.exists(path):
            continue
        try:
            os.remove(path)
            print(f"[INFO] Old {path} deleted")
        except Exception as exc:
            print(f"[WARNING] Failed delete old token {path}: {exc}")


def _print_token_sources():
    ensure_env_loaded()
    _, env_source = find_existing_token_data()
    file_hits = [path for path in (GMAIL_TOKEN_FILE, OAUTH_TOKEN_FILE) if os.path.isfile(path)]
    secret_path = resolve_client_secrets_path()
    print("Token sources checked (priority: .env env vars, then files):")
    print(f"  - {GMAIL_TOKEN_ENV_KEY} / {OAUTH_TOKEN_ENV_KEY} in {ENV_FILE}")
    for path in (GMAIL_TOKEN_FILE, OAUTH_TOKEN_FILE):
        mark = "found" if path in file_hits else "missing"
        print(f"  - {path}: {mark}")
    if secret_path:
        print(f"  - OAuth client file: {secret_path}")
    elif os.path.isfile(CLIENT_SECRET_FILE):
        print(f"  - {CLIENT_SECRET_FILE}: present but invalid JSON")
    if env_source:
        print(f"\nActive token source: {env_source}")
    elif file_hits:
        print(f"\nActive token source: {file_hits[0]}")
    else:
        print("\nNo token found yet.")
    print()


def _print_diagnostics():
    warnings = diagnose_oauth_files()
    if not warnings:
        return
    print("[WARN] OAuth setup issues detected:")
    for line in warnings:
        print(f"  - {line}")
    print(f"  Use valid {CLIENT_SECRET_FILE} on the VM, or client id/secret in .env.")
    print()


def run_refresh(force=False):
    _print_diagnostics()
    _print_token_sources()
    creds, err = refresh_and_persist_tokens(force=force)
    if err:
        print(f"ERROR: {err}\n")
        _client_config_help()
        secret_path = resolve_client_secrets_path()
        if secret_path:
            print("First-time setup on this VM:")
            print("  python3 TokenGenerator.py --generate")
            print("  (VPS auto-switches to paste-code mode; no local browser needed)")
        return 1

    print("\n=========================================")
    print("TOKEN REFRESH OK")
    print("=========================================")
    print("Refresh token:", "YES (long-lived — keeps Gmail working)" if creds.refresh_token else "NO")
    if getattr(creds, "expiry", None):
        print("Access token expiry:", creds.expiry, "(short-lived, auto-renewed)")
    print(f"\nSynced to {GMAIL_TOKEN_FILE}, {OAUTH_TOKEN_FILE}, and {ENV_FILE}")
    print("While Conlecta runs, access tokens auto-refresh when near expiry.")
    print("Re-run --generate only if refresh_token is revoked (invalid_grant).")
    return 0


def run_generate(manual=False, replace=False):
    _print_diagnostics()

    secret_path = resolve_client_secrets_path()
    client_config = _resolve_client_config()
    if not client_config:
        print(f"ERROR: OAuth client config not found (need valid {CLIENT_SECRET_FILE}).\n")
        _client_config_help()
        return 1

    source = secret_path or client_config.get("source") or "configured client"
    print(f"Using OAuth client from: {source}\n")

    if replace:
        _remove_old_tokens()

    print("[INFO] Starting Google OAuth Login...\n")
    try:
        creds = _run_oauth_flow(client_config, manual=manual)
    except Exception as exc:
        print(f"\nERROR: OAuth login failed: {exc}")
        if not replace:
            print("Existing token.json / .env tokens were NOT deleted.")
        return 1

    try:
        if creds.expired and creds.refresh_token:
            print("[INFO] Refreshing token...")
            creds.refresh(Request())
    except Exception as exc:
        print(f"[WARNING] Refresh failed: {exc}")

    if not creds.refresh_token:
        print("\n=========================================")
        print("WARNING: NO REFRESH TOKEN RECEIVED")
        print("=========================================")
        print("Possible causes:")
        print("- OAuth app still in Testing mode")
        print("- Old Google permission cached")
        print("\nFix:")
        print("1. Open https://myaccount.google.com/permissions")
        print("2. Remove app access")
        print("3. Run this script again")
        print("=========================================\n")
        return 1

    _save_tokens(creds)

    print("\n=========================================")
    print("SUCCESS!")
    print("token.json created (+ oauth_token.json + .env sync)")
    print("=========================================")
    print("Refresh Token Exists:", "YES" if creds.refresh_token else "NO")
    print("\nIMPORTANT:")
    print("- Keep token.json / .env private (VM only)")
    print("- Publish OAuth app to Production (Testing tokens expire ~7 days)")
    print("- Conlecta auto-refreshes access tokens while the server runs")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate or refresh Google OAuth tokens for Conlecta")
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Run Google OAuth login (needs client_secret.json on VM, opens browser unless --manual)",
    )
    parser.add_argument(
        "--manual",
        action="store_true",
        help="With --generate: headless VPS — print URL and paste authorization code",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="With --generate: delete old token.json before login (legacy gmail_token_generator behavior)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force refresh even if access token still valid",
    )
    args = parser.parse_args(argv)

    ensure_env_loaded()

    print("=========================================")
    print(" GOOGLE TOKEN GENERATOR")
    print("=========================================\n")
    print("Scopes:")
    for scope in SCOPES:
        print(f"  - {scope}")
    print()

    if args.generate:
        return run_generate(manual=args.manual, replace=args.replace)

    print("Mode: refresh/sync (use --generate for new OAuth login)\n")
    return run_refresh(force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
