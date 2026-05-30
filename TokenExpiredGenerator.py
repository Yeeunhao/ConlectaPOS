# Force token.json to look expired so auto-refresh can be tested.

import json
import os
from datetime import datetime, timedelta, timezone

from conlecta_oauth import (
    ENV_FILE,
    GMAIL_TOKEN_ENV_KEY,
    GMAIL_TOKEN_FILE,
    OAUTH_TOKEN_ENV_KEY,
    OAUTH_TOKEN_FILE,
    ensure_env_loaded,
    find_existing_token_data,
    token_file_candidates,
    write_token_env,
)


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


def force_expire_env(source_label):
    data, _ = find_existing_token_data()
    if not data:
        return False
    expired_time = (
        datetime.now(timezone.utc) - timedelta(days=1)
    ).isoformat().replace("+00:00", "Z")
    data["expiry"] = expired_time
    write_token_env(data)
    print(f"Forced expired: {source_label} -> synced to {ENV_FILE}")
    print(f"New expiry: {expired_time}")
    return True


def main():
    ensure_env_loaded()
    print("====================================")
    print(" FORCE EXPIRE GOOGLE TOKEN")
    print("====================================\n")
    paths = [path for path in token_file_candidates() if os.path.isfile(path)]
    token_data, env_source = find_existing_token_data()
    if not paths and not token_data:
        print(f"No tokens found in {ENV_FILE} ({GMAIL_TOKEN_ENV_KEY}) or token files.")
        print(f"Expected {GMAIL_TOKEN_FILE} or {OAUTH_TOKEN_FILE} on the VPS.")
        return
    if env_source.startswith("env:"):
        force_expire_env(env_source)
    for path in paths:
        force_expire(path)
    print("\nNow run: python TokenGenerator.py")
    print("Or start the app; Google library should auto-refresh the token.")


if __name__ == "__main__":
    main()
