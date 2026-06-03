import argparse
import ast
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATABASE_ENV = BASE_DIR / "database.env"


def _parse_env_value(raw):
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        try:
            return str(ast.literal_eval(value))
        except Exception:
            return value[1:-1]
    return value


def load_database_env(path=DATABASE_ENV):
    loaded = {}
    if not path.is_file():
        return loaded
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, raw_value = text.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = _parse_env_value(raw_value)
        os.environ.setdefault(key, value)
        loaded[key] = value
    return loaded


def print_database_status():
    try:
        import conlecta_db
    except Exception as exc:
        print(f"[db] Could not import conlecta_db: {exc}")
        return

    configured = conlecta_db.is_configured()
    cfg = conlecta_db._env_config()
    if cfg.get("conninfo"):
        target = "DATABASE_URL"
    else:
        target = f"{cfg.get('user') or '-'}@{cfg.get('host') or '-'}:{cfg.get('port') or '-'} / {cfg.get('dbname') or '-'}"

    print(f"[db] Configured from database.env/env: {'yes' if configured else 'no'}")
    print(f"[db] Target: {target}")
    if not configured:
        return

    try:
        ok = conlecta_db.ping()
    except Exception:
        ok = False
    print(f"[db] Connection test: {'ok' if ok else 'failed'}")


def main():
    parser = argparse.ArgumentParser(description="Run Conlecta Web locally.")
    parser.add_argument("--host", default=os.environ.get("CONLECTA_WEB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("CONLECTA_WEB_PORT", "8765")))
    parser.add_argument("--skip-db-ping", action="store_true", help="Start without testing the database connection.")
    parser.add_argument("--warm-oauth", action="store_true", help="Also warm Google OAuth tokens on startup.")
    args = parser.parse_args()

    loaded = load_database_env()
    if not args.warm_oauth:
        os.environ.setdefault("CONLECTA_SKIP_OAUTH_WARMUP", "1")
    print(f"[env] Loaded database.env: {'yes' if loaded else 'no'}")
    print(f"[oauth] Warm-up: {'enabled' if args.warm_oauth else 'skipped for local run'}")
    if not args.skip_db_ping:
        print_database_status()

    import conlecta_web

    print(f"[web] Opening local server at http://{args.host}:{args.port}")
    conlecta_web.run(args.host, args.port)


if __name__ == "__main__":
    main()
