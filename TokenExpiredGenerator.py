# Force token.json to look expired so auto-refresh can be tested.

import json
from datetime import datetime, timedelta, timezone

from conlecta_oauth import GMAIL_TOKEN_FILE, OAUTH_TOKEN_FILE, token_file_candidates


def force_expire(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    expired_time = (
        datetime.now(timezone.utc) - timedelta(days=1)
    ).isoformat().replace("+00:00", "Z")
    data["expiry"] = expired_time
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    print(f"Forced expired: {path}")
    print(f"New expiry: {expired_time}")


def main():
    print("====================================")
    print(" FORCE EXPIRE GOOGLE TOKEN")
    print("====================================\n")
    paths = [path for path in token_file_candidates() if __import__("os").path.isfile(path)]
    if not paths:
        print(f"No token files found. Expected {GMAIL_TOKEN_FILE} or {OAUTH_TOKEN_FILE}.")
        return
    for path in paths:
        force_expire(path)
    print("\nNow run the app; Google library should auto-refresh the token.")


if __name__ == "__main__":
    main()
