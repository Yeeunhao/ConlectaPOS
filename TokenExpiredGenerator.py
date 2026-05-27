# force_expire_token.py
#
# PURPOSE:
# Force token.json to look expired
# so you can test auto refresh
#
# RUN:
# python force_expire_token.py

import json
from datetime import datetime, timedelta, timezone

TOKEN_FILE = "token.json"

def main():

    print("====================================")
    print(" FORCE EXPIRE GOOGLE TOKEN")
    print("====================================\n")

    # ---------------------------------
    # Load token
    # ---------------------------------
    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # ---------------------------------
    # Force expired time
    # ---------------------------------
    expired_time = (
        datetime.now(timezone.utc) - timedelta(days=1)
    ).isoformat().replace("+00:00", "Z")

    data["expiry"] = expired_time

    # ---------------------------------
    # Save back
    # ---------------------------------
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    print("SUCCESS!")
    print("Token forced expired.")
    print("\nNew expiry:")
    print(expired_time)

    print("\nNow run your Gmail script.")
    print("Google library should auto refresh token.")

if __name__ == "__main__":
    main()