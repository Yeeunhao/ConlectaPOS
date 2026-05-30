# =========================================================
# TokenGenerator.py
#
# Google OAuth for Conlecta (VPS-friendly):
#   python TokenGenerator.py              refresh/sync from .env or token.json
#   python TokenGenerator.py --generate   new OAuth login (needs client creds)
#   python TokenGenerator.py --generate --manual   headless VPS paste-code flow
# =========================================================

import argparse
import json
import os
import sys

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
    credentials_file_candidates,
    ensure_env_loaded,
    find_existing_token_data,
    diagnose_oauth_files,
    load_client_config,
    refresh_and_persist_tokens,
    write_token_env,
)

SCOPES = COMBINED_SCOPES


def _client_config_help():
    print("OAuth client config (server/.env only — never commit to git):")
    print(f"  1) {OAUTH_CREDS_FILE} or {CLIENT_SECRET_FILE} on the VPS")
    print(f"  2) {OAUTH_CREDS_ENV_KEY}={{\"installed\":{{...}}}} in {ENV_FILE}")
    print(f"  3) {OAUTH_CLIENT_ID_ENV} + {OAUTH_CLIENT_SECRET_ENV} in {ENV_FILE}")
    print("  4) client_id/client_secret already inside your token.json / .env token JSON")
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


def _run_oauth_flow(client_config, manual=False):
    flow = InstalledAppFlow.from_client_config(_flow_client_config(client_config), SCOPES)
    if manual:
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true",
        )
        print("\nOpen this URL in a browser (any machine):\n")
        print(auth_url)
        print("\nAfter approving, paste the full redirect URL or authorization code here.\n")
        raw = input("Authorization code or redirect URL: ").strip()
        if "code=" in raw:
            raw = raw.split("code=", 1)[1]
            raw = raw.split("&", 1)[0]
        flow.fetch_token(code=raw)
        return flow.credentials

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    print("If browser not auto open, open this URL manually:\n")
    print(auth_url)
    print("\nWaiting for login...\n")
    return flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
    )


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


def _print_token_sources():
    ensure_env_loaded()
    _, env_source = find_existing_token_data()
    file_hits = [path for path in (GMAIL_TOKEN_FILE, OAUTH_TOKEN_FILE) if os.path.isfile(path)]
    print("Token sources checked (priority: .env env vars, then files):")
    print(f"  - {GMAIL_TOKEN_ENV_KEY} / {OAUTH_TOKEN_ENV_KEY} in {ENV_FILE}")
    for path in (GMAIL_TOKEN_FILE, OAUTH_TOKEN_FILE):
        mark = "found" if path in file_hits else "missing"
        print(f"  - {path}: {mark}")
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
    print("  Broken oauth_credentials.json is ignored when .env has valid client id/secret or tokens.")
    print()


def run_refresh(force=False):
    _print_diagnostics()
    _print_token_sources()
    creds, err = refresh_and_persist_tokens(force=force)
    if err:
        print(f"ERROR: {err}\n")
        _client_config_help()
        print("To create a brand-new token (requires OAuth client config):")
        print("  python TokenGenerator.py --generate --manual")
        return 1

    print("\n=========================================")
    print("TOKEN REFRESH OK")
    print("=========================================")
    print("Refresh token:", "YES (long-lived — keeps Gmail working)" if creds.refresh_token else "NO")
    if getattr(creds, "expiry", None):
        print("Access token expiry:", creds.expiry, "(short-lived, auto-renewed)")
    print(f"\nSynced to {GMAIL_TOKEN_FILE}, {OAUTH_TOKEN_FILE}, and {ENV_FILE}")
    print("While Conlecta is running, access tokens auto-refresh ~every 10 min when near expiry.")
    print("You only need --generate --manual again if refresh_token is revoked (invalid_grant).")
    return 0


def run_generate(manual=False):
    _print_diagnostics()
    client_config = _resolve_client_config()
    if not client_config:
        print("ERROR: OAuth client config not found.\n")
        _client_config_help()
        print("For VPS: put client id/secret in .env (not in git), then run:")
        print("  python3 TokenGenerator.py --generate --manual")
        print("\nIf oauth_credentials.json on the server is broken/empty, delete it or fix the JSON.")
        return 1

    source = client_config.get("source") or "configured client"
    print(f"Using OAuth client from: {source}\n")

    print("\n[INFO] Starting Google OAuth Login...\n")
    try:
        creds = _run_oauth_flow(client_config, manual=manual)
    except Exception as exc:
        print(f"\nERROR: OAuth login failed: {exc}")
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
        print("Fix:")
        print("1. Open https://myaccount.google.com/permissions")
        print("2. Remove Conlecta / Google Cloud app access")
        print("3. Run this script again with --generate --manual")
        print("=========================================\n")
        return 1

    _save_tokens(creds)

    print("\n=========================================")
    print("SUCCESS!")
    print("=========================================")
    print("Refresh Token Exists:", "YES" if creds.refresh_token else "NO")
    print("\nIMPORTANT:")
    print("- Keep token.json / .env private (VM only, not in git)")
    print(f"- Clone repo on VPS, copy {ENV_FILE} with {GMAIL_TOKEN_ENV_KEY}")
    print("- Or place token.json on the VPS manually")
    print("- Server loads .env first, then token.json files")
    print("- Publish OAuth app to Production (Testing tokens expire ~7 days)")
    print("- If you see invalid_grant, revoke app access and run --generate --manual")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Generate or refresh Google OAuth tokens for Conlecta")
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Run full Google login and create new tokens (requires OAuth client config)",
    )
    parser.add_argument(
        "--manual",
        action="store_true",
        help="With --generate: headless VPS paste authorization code",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force refresh even if access token still valid",
    )
    args = parser.parse_args()

    ensure_env_loaded()

    print("=========================================")
    print(" GOOGLE TOKEN GENERATOR (refresh mode)")
    print("=========================================\n")
    print("Default: refresh/sync tokens from .env or token.json")
    print("New login: python3 TokenGenerator.py --generate --manual\n")
    print("Scopes:")
    for scope in SCOPES:
        print(f"  - {scope}")
    print()

    if args.generate:
        return run_generate(manual=args.manual)

    return run_refresh(force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
