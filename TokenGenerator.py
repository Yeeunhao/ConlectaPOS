# =========================================================
# TokenGenerator.py
#
# Generate Google OAuth token.json + oauth_token.json
# Auto refresh capable. Use --manual on headless VPS.
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
    GMAIL_SCOPES,
    GMAIL_TOKEN_FILE,
    OAUTH_CREDS_FILE,
    OAUTH_TOKEN_FILE,
    SHEETS_SCOPES,
    credentials_file_candidates,
)

SCOPES = COMBINED_SCOPES


def _resolve_client_secret():
    candidates = credentials_file_candidates()
    if candidates:
        return candidates[0]
    return CLIENT_SECRET_FILE or OAUTH_CREDS_FILE


def _run_oauth_flow(client_secret, manual=False):
    flow = InstalledAppFlow.from_client_secrets_file(client_secret, SCOPES)
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


def main():
    parser = argparse.ArgumentParser(description="Generate Google OAuth tokens for Conlecta")
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Headless mode: print URL and paste authorization code (for VPS)",
    )
    args = parser.parse_args()

    print("=========================================")
    print(" GOOGLE TOKEN GENERATOR")
    print("=========================================\n")
    print("Scopes:")
    for scope in SCOPES:
        print(f"  - {scope}")
    print()

    client_secret = _resolve_client_secret()
    if not os.path.exists(client_secret):
        print(f"ERROR: OAuth client file not found.")
        print(f"Expected one of: {OAUTH_CREDS_FILE}, {CLIENT_SECRET_FILE}")
        return 1

    print(f"Using client secrets: {client_secret}\n")

    for path in (GMAIL_TOKEN_FILE, OAUTH_TOKEN_FILE):
        if os.path.exists(path):
            try:
                os.remove(path)
                print(f"[INFO] Old {path} deleted")
            except Exception as exc:
                print(f"[WARNING] Failed delete old token {path}: {exc}")

    print("\n[INFO] Starting Google OAuth Login...\n")
    creds = _run_oauth_flow(client_secret, manual=args.manual)

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
        print("3. Run this script again with --manual on VPS")
        print("=========================================\n")
        return 1

    _save_tokens(creds)

    print("\n=========================================")
    print("SUCCESS!")
    print("=========================================\n")
    print("Refresh Token Exists:", "YES" if creds.refresh_token else "NO")
    print("\nIMPORTANT:")
    print("- Keep token.json private")
    print("- Publish OAuth app to Production (Testing tokens expire ~7 days)")
    print("- Server auto-refreshes access tokens ~15 min before expiry")
    print("- If you see invalid_grant, revoke app access and run this again")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
