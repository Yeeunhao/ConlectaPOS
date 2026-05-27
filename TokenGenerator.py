# =========================================================
# gmail_token_generator.py
#
# Generate Google OAuth token.json
# Auto refresh capable
# =========================================================

import os
import json
from datetime import timezone

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# =========================================================
# SCOPES
# =========================================================
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

# =========================================================
# MAIN
# =========================================================
def main():

    print("=========================================")
    print(" GOOGLE TOKEN GENERATOR")
    print("=========================================\n")

    # -----------------------------------------------------
    # Check client secret
    # -----------------------------------------------------
    if not os.path.exists("client_secret.json"):
        print("ERROR: client_secret.json not found")
        return

    # -----------------------------------------------------
    # Delete old token
    # -----------------------------------------------------
    if os.path.exists("token.json"):
        try:
            os.remove("token.json")
            print("[INFO] Old token.json deleted")
        except Exception as e:
            print(f"[WARNING] Failed delete old token: {e}")

    print("\n[INFO] Starting Google OAuth Login...\n")

    # -----------------------------------------------------
    # OAuth Flow
    # -----------------------------------------------------
    flow = InstalledAppFlow.from_client_secrets_file(
        "client_secret.json",
        SCOPES
    )

    # Force refresh token generation
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true"
    )

    print("If browser not auto open, open this URL manually:\n")
    print(auth_url)
    print("\nWaiting for login...\n")

    creds = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent"
    )

    # -----------------------------------------------------
    # Auto refresh if expired
    # -----------------------------------------------------
    try:
        if creds.expired and creds.refresh_token:
            print("[INFO] Refreshing token...")
            creds.refresh(Request())
    except Exception as e:
        print(f"[WARNING] Refresh failed: {e}")

    # -----------------------------------------------------
    # Validate refresh token
    # -----------------------------------------------------
    if not creds.refresh_token:
        print("\n=========================================")
        print("WARNING: NO REFRESH TOKEN RECEIVED")
        print("=========================================")
        print("Possible causes:")
        print("- OAuth app still testing")
        print("- Existing Google permission cached")
        print("- Need revoke old access")
        print("\nFix:")
        print("1. Open:")
        print("https://myaccount.google.com/permissions")
        print("2. Remove app access")
        print("3. Run script again")
        print("=========================================\n")

    # -----------------------------------------------------
    # Build token data
    # -----------------------------------------------------
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes),
        "universe_domain": getattr(
            creds,
            "universe_domain",
            "googleapis.com"
        ),
        "account": ""
    }

    # -----------------------------------------------------
    # Save token
    # -----------------------------------------------------
    with open("token.json", "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=4)

    # -----------------------------------------------------
    # Success
    # -----------------------------------------------------
    print("\n=========================================")
    print("SUCCESS!")
    print("token.json created")
    print("=========================================\n")

    print("Refresh Token Exists:",
          "YES" if creds.refresh_token else "NO")

    print("\nIMPORTANT:")
    print("- Keep token.json private")
    print("- Do not regenerate too often")
    print("- Publish OAuth app to Production")
    print("- Refresh token can die if revoked")

# =========================================================
# RUN
# =========================================================
if __name__ == "__main__":
    main()