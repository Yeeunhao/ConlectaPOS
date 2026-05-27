import base64
import os
import time
from datetime import datetime
from decimal import Decimal

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
except Exception:  # pragma: no cover - app can still fall back to Sheets
    psycopg = None
    dict_row = None
    Jsonb = None

try:
    from dotenv import dotenv_values
except Exception:  # pragma: no cover
    dotenv_values = None


ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.env")
DEFAULT_MERCHANT_ID = "conlecta"
DEFAULT_MERCHANT_NAME = "Conlecta"


def _env_config():
    data = {}
    if dotenv_values and os.path.isfile(ENV_FILE):
        data.update({k: v for k, v in dotenv_values(ENV_FILE).items() if v is not None})
    data.update({k: v for k, v in os.environ.items() if k.startswith("DB_") or k == "DATABASE_URL"})
    if data.get("DATABASE_URL"):
        return {"conninfo": data["DATABASE_URL"]}
    return {
        "host": data.get("DB_HOST"),
        "port": int(data.get("DB_PORT") or 5432),
        "dbname": data.get("DB_NAME") or data.get("DB_DATABASE"),
        "user": data.get("DB_USER") or data.get("DB_USERNAME"),
        "password": data.get("DB_PASSWORD"),
        "sslmode": data.get("DB_SSLMODE") or "prefer",
        "connect_timeout": int(data.get("DB_CONNECT_TIMEOUT") or 10),
    }


def is_configured():
    cfg = _env_config()
    return bool(psycopg and (cfg.get("conninfo") or (cfg.get("host") and cfg.get("dbname") and cfg.get("user"))))


def connect(row_factory=None):
    if not is_configured():
        raise RuntimeError("Database belum dikonfigurasi.")
    cfg = _env_config()
    kwargs = {}
    if row_factory is not None:
        kwargs["row_factory"] = row_factory
    if cfg.get("conninfo"):
        return psycopg.connect(cfg["conninfo"], **kwargs)
    return psycopg.connect(**cfg, **kwargs)


def ping():
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("select 1")
                return cur.fetchone()[0] == 1
    except Exception:
        return False


def normalize_merchant_id(value):
    text = str(value or "").strip().lower()
    if not text:
        return DEFAULT_MERCHANT_ID
    safe = "".join(ch if ch.isalnum() else "_" for ch in text)
    safe = "_".join(part for part in safe.split("_") if part)
    return safe or DEFAULT_MERCHANT_ID


def _int_money(value, default=0):
    if value in ("", None):
        return default
    try:
        return int(round(float(str(value).replace(",", "").strip())))
    except Exception:
        return default


def _bool_flag(value):
    return str(value or "").strip().lower() in {"1", "yes", "true", "admin", "owner", "y"}


def _ts(value=None):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value))
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromtimestamp(float(text))
    except Exception:
        pass
    try:
        return datetime.fromisoformat(text)
    except Exception:
        pass
    legacy_text = text.split(" - ", 1)[-1].strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y",
    ):
        try:
            return datetime.strptime(legacy_text[:19], fmt)
        except Exception:
            pass
    return None


def _iso(value):
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return str(value or "")


def _money(value):
    if isinstance(value, Decimal):
        return int(round(float(value)))
    return _int_money(value)


def _read_blob(path):
    text = str(path or "").strip()
    if not text or not os.path.isfile(text):
        return None, ""
    with open(text, "rb") as f:
        return f.read(), os.path.basename(text)


def _decode_data_blob(value):
    text = str(value or "").strip()
    if not text:
        return None
    if "," in text and text.lower().startswith("data:"):
        text = text.split(",", 1)[1]
    try:
        return base64.b64decode(text)
    except Exception:
        return None


def _encode_blob(value):
    if not value:
        return ""
    return base64.b64encode(bytes(value)).decode("ascii")


def _blob_data_url(value, filename=""):
    encoded = _encode_blob(value)
    if not encoded:
        return ""
    ext = os.path.splitext(str(filename or ""))[1].lower().lstrip(".")
    if ext == "jpg":
        ext = "jpeg"
    if ext not in {"png", "jpeg", "webp", "bmp", "gif", "ico"}:
        ext = "png"
    mime = "image/x-icon" if ext == "ico" else f"image/{ext}"
    return f"data:{mime};base64,{encoded}"


def ensure_schema():
    statements = [
        """
        CREATE TABLE IF NOT EXISTS merchants (
            merchant_id VARCHAR(100) PRIMARY KEY,
            merchant_name VARCHAR(255) NOT NULL,
            logo_data BYTEA,
            logo_filename VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS vendors (
            vendor_id BIGSERIAL PRIMARY KEY,
            vendor_name VARCHAR(255) NOT NULL,
            merchant_id VARCHAR(100) NOT NULL REFERENCES merchants(merchant_id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS password_config (
            password_id BIGSERIAL PRIMARY KEY,
            password_function VARCHAR(100) NOT NULL,
            password_value TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS conlecta_account (
            account_id VARCHAR(100) PRIMARY KEY,
            account_name VARCHAR(255),
            email VARCHAR(255),
            password VARCHAR(255),
            otp VARCHAR(20),
            username VARCHAR(255),
            session_status VARCHAR(50),
            device_id VARCHAR(255),
            last_ip VARCHAR(100),
            merchant_id VARCHAR(100) REFERENCES merchants(merchant_id) ON DELETE SET NULL,
            admin_account BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS email_templates (
            template_key VARCHAR(100) PRIMARY KEY,
            subject VARCHAR(500),
            html_override TEXT,
            primary_color VARCHAR(20),
            primary_text_color VARCHAR(20),
            bg_color VARCHAR(20),
            secondary_color VARCHAR(20),
            logo_data BYTEA,
            logo_filename VARCHAR(255),
            logo_align VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS stock_items (
            item_id BIGSERIAL PRIMARY KEY,
            item_name VARCHAR(255) NOT NULL,
            price NUMERIC(18,2) NOT NULL DEFAULT 0,
            capital NUMERIC(18,2) DEFAULT 0,
            stock_qty INTEGER DEFAULT 0,
            vendor_id BIGINT REFERENCES vendors(vendor_id) ON DELETE SET NULL,
            image_data BYTEA,
            image_filename VARCHAR(255),
            merchant_id VARCHAR(100) REFERENCES merchants(merchant_id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id VARCHAR(100) PRIMARY KEY,
            qr_id VARCHAR(100),
            amount NUMERIC(18,2) DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            customer VARCHAR(255),
            discount_percent NUMERIC(10,2) DEFAULT 0,
            cashier VARCHAR(255),
            customer_note TEXT,
            cashier_name VARCHAR(255),
            gross_amount NUMERIC(18,2) DEFAULT 0,
            line_discount NUMERIC(18,2) DEFAULT 0,
            cart_disc_amount NUMERIC(18,2) DEFAULT 0,
            payment_method VARCHAR(100),
            cash_received NUMERIC(18,2) DEFAULT 0,
            change_amount NUMERIC(18,2) DEFAULT 0,
            merchant_id VARCHAR(100) REFERENCES merchants(merchant_id) ON DELETE SET NULL,
            payment_fee NUMERIC(18,2) DEFAULT 0,
            net_amount NUMERIC(18,2) DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS transaction_items (
            item_line_id BIGSERIAL PRIMARY KEY,
            transaction_id VARCHAR(100) NOT NULL REFERENCES transactions(transaction_id) ON DELETE CASCADE,
            qr_id VARCHAR(100),
            item_name VARCHAR(255),
            qty INTEGER DEFAULT 0,
            unit_price NUMERIC(18,2) DEFAULT 0,
            subtotal NUMERIC(18,2) DEFAULT 0,
            free_flag BOOLEAN DEFAULT FALSE,
            disc_percent NUMERIC(10,2) DEFAULT 0,
            disc_amount NUMERIC(18,2) DEFAULT 0,
            line_discount NUMERIC(18,2) DEFAULT 0,
            payment_method VARCHAR(100),
            change_amount NUMERIC(18,2) DEFAULT 0,
            cash_received NUMERIC(18,2) DEFAULT 0,
            merchant_id VARCHAR(100) REFERENCES merchants(merchant_id) ON DELETE SET NULL,
            capital NUMERIC(18,2) DEFAULT 0,
            profit NUMERIC(18,2) DEFAULT 0,
            payment_fee NUMERIC(18,2) DEFAULT 0,
            total_cost NUMERIC(18,2) DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS version_changes (
            version_no VARCHAR(50) PRIMARY KEY,
            title VARCHAR(255),
            change_log TEXT,
            active_flag BOOLEAN DEFAULT TRUE,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS referral_codes (
            referral_code VARCHAR(50) PRIMARY KEY,
            sales_name VARCHAR(255),
            active_flag BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS merchant_registration (
            registration_id BIGSERIAL PRIMARY KEY,
            merchant_id VARCHAR(100) REFERENCES merchants(merchant_id) ON DELETE SET NULL,
            business_name VARCHAR(255),
            business_desc TEXT,
            referral_code VARCHAR(50) REFERENCES referral_codes(referral_code) ON DELETE SET NULL,
            status VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS merchant_settings (
            merchant_id VARCHAR(100) PRIMARY KEY REFERENCES merchants(merchant_id) ON DELETE CASCADE,
            settings_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "ALTER TABLE conlecta_account ADD COLUMN IF NOT EXISTS last_activity_ts TIMESTAMP",
        "ALTER TABLE conlecta_account ADD COLUMN IF NOT EXISTS pin VARCHAR(20)",
        "ALTER TABLE vendors ADD COLUMN IF NOT EXISTS legacy_vendor_id VARCHAR(100)",
        "ALTER TABLE stock_items ADD COLUMN IF NOT EXISTS legacy_item_no INTEGER",
        "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS customer_email VARCHAR(255)",
        "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS discount_raw TEXT",
        "ALTER TABLE transaction_items ADD COLUMN IF NOT EXISTS gross_amount NUMERIC(18,2) DEFAULT 0",
        "ALTER TABLE transaction_items ADD COLUMN IF NOT EXISTS source_line_no INTEGER",
        "CREATE INDEX IF NOT EXISTS idx_vendors_merchant ON vendors(merchant_id)",
        "CREATE INDEX IF NOT EXISTS idx_vendors_legacy ON vendors(merchant_id, legacy_vendor_id)",
        "CREATE INDEX IF NOT EXISTS idx_stock_items_merchant ON stock_items(merchant_id)",
        "CREATE INDEX IF NOT EXISTS idx_transactions_merchant_updated ON transactions(merchant_id, updated_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_transaction_items_txn ON transaction_items(transaction_id)",
    ]
    with connect() as conn:
        with conn.cursor() as cur:
            for sql in statements:
                cur.execute(sql)
        conn.commit()


def ensure_merchant(merchant_id=None, name=None, logo_path=None):
    mid = normalize_merchant_id(merchant_id)
    provided_name = str(name or "").strip()
    if not provided_name and not logo_path:
        with connect(row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT merchant_id, merchant_name, logo_data, logo_filename FROM merchants WHERE merchant_id=%s", (mid,))
                row = cur.fetchone()
                if row:
                    return {
                        "id": row["merchant_id"],
                        "name": row["merchant_name"] or DEFAULT_MERCHANT_NAME,
                        "logo_path": "",
                        "logo_filename": row.get("logo_filename") or "",
                        "logo_data_url": _blob_data_url(row.get("logo_data"), row.get("logo_filename")),
                    }
    merchant_name = provided_name or (DEFAULT_MERCHANT_NAME if mid == DEFAULT_MERCHANT_ID else mid)
    logo_data, logo_filename = _read_blob(logo_path)
    with connect(row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO merchants (merchant_id, merchant_name, logo_data, logo_filename, updated_at)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (merchant_id) DO UPDATE SET
                    merchant_name = EXCLUDED.merchant_name,
                    logo_data = COALESCE(EXCLUDED.logo_data, merchants.logo_data),
                    logo_filename = COALESCE(EXCLUDED.logo_filename, merchants.logo_filename),
                    updated_at = CURRENT_TIMESTAMP
                RETURNING merchant_id, merchant_name, logo_filename
                """,
                (mid, merchant_name, logo_data, logo_filename),
            )
            row = cur.fetchone()
        conn.commit()
    return {
        "id": row["merchant_id"],
        "name": row["merchant_name"],
        "logo_path": logo_path or "",
        "logo_filename": row.get("logo_filename") or "",
    }


def load_merchants():
    ensure_merchant(DEFAULT_MERCHANT_ID, DEFAULT_MERCHANT_NAME)
    with connect(row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT merchant_id, merchant_name, logo_data, logo_filename FROM merchants ORDER BY merchant_name")
            rows = cur.fetchall()
    return {
        row["merchant_id"]: {
            "id": row["merchant_id"],
            "name": row["merchant_name"] or DEFAULT_MERCHANT_NAME,
            "logo_path": "",
            "logo_filename": row.get("logo_filename") or "",
            "logo_data_url": _blob_data_url(row.get("logo_data"), row.get("logo_filename")),
        }
        for row in rows
    }


def upsert_merchant(merchant_id, name="", logo_path=""):
    return ensure_merchant(merchant_id, name, logo_path)


def load_settings(default_settings, merchant_id=None):
    mid = normalize_merchant_id(merchant_id)
    ensure_merchant(mid)
    merged = dict(default_settings or {})
    with connect(row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT settings_json FROM merchant_settings WHERE merchant_id=%s", (mid,))
            row = cur.fetchone()
    if row and isinstance(row["settings_json"], dict):
        merged.update({k: v for k, v in row["settings_json"].items() if v is not None})
    merged["merchant_id"] = mid
    return merged


def save_settings(settings, merchant_id=None):
    mid = normalize_merchant_id(merchant_id or (settings or {}).get("merchant_id"))
    ensure_merchant(mid, (settings or {}).get("shop_name"), (settings or {}).get("brand_logo_path"))
    clean = dict(settings or {})
    clean.pop("merchant_id", None)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO merchant_settings (merchant_id, settings_json, updated_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (merchant_id) DO UPDATE SET
                    settings_json = EXCLUDED.settings_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (mid, Jsonb(clean)),
            )
        conn.commit()
    out = dict(clean)
    out["merchant_id"] = mid
    return out


def _account_from_row(row):
    if not row:
        return None
    return {
        "row_index": row["account_id"],
        "id": row["account_id"],
        "name": row.get("account_name") or "",
        "username": row.get("username") or row.get("account_name") or "",
        "email": row.get("email") or "",
        "password": row.get("password") or "",
        "otp": row.get("otp") or "",
        "session": row.get("session_status") or "",
        "device_id": row.get("device_id") or "",
        "last_ip": row.get("last_ip") or "",
        "merchant_id": normalize_merchant_id(row.get("merchant_id")),
        "admin_account": bool(row.get("admin_account")),
        "last_activity_ts": _iso(row.get("last_activity_ts")),
        "pin": row.get("pin") or "",
    }


def find_account_by_id(account_id):
    with connect(row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM conlecta_account WHERE account_id=%s", (str(account_id or "").strip(),))
            return _account_from_row(cur.fetchone())


def find_account_by_email(email):
    wanted = str(email or "").strip().lower()
    with connect(row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM conlecta_account WHERE lower(email)=%s LIMIT 1", (wanted,))
            return _account_from_row(cur.fetchone())


def find_account_by_login(login_id):
    login = str(login_id or "").strip().lower()
    if not login:
        return None
    with connect(row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM conlecta_account
                WHERE lower(email)=%s OR lower(username)=%s OR lower(account_name)=%s
                LIMIT 1
                """,
                (login, login, login),
            )
            return _account_from_row(cur.fetchone())


def load_all_accounts():
    with connect(row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM conlecta_account ORDER BY account_name")
            return [_account_from_row(row) for row in cur.fetchall()]


def accounts_for_merchant(merchant_id=None):
    mid = normalize_merchant_id(merchant_id)
    with connect(row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM conlecta_account WHERE merchant_id=%s ORDER BY account_name", (mid,))
            return [_account_from_row(row) for row in cur.fetchall()]


def account_conflict_message(account_name, email, exclude_account_id=""):
    username = str(account_name or "").strip().lower()
    wanted_email = str(email or "").strip().lower()
    exclude = str(exclude_account_id or "").strip()
    with connect(row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT account_id, account_name, username, email FROM conlecta_account
                WHERE (%s = '' OR account_id <> %s)
                  AND (lower(email)=%s OR lower(username)=%s OR lower(account_name)=%s)
                LIMIT 1
                """,
                (exclude, exclude, wanted_email, username, username),
            )
            row = cur.fetchone()
    if not row:
        return ""
    if wanted_email and wanted_email == str(row.get("email") or "").strip().lower():
        return "Email sudah terdaftar."
    return "Username / account name sudah terdaftar."


def create_account(account_id, account_name, email, password, merchant_id=None, admin_account=False):
    mid = normalize_merchant_id(merchant_id)
    ensure_merchant(mid)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conlecta_account (
                    account_id, account_name, email, password, otp, username,
                    session_status, device_id, last_ip, merchant_id, admin_account, pin, updated_at
                ) VALUES (%s,%s,%s,%s,'',%s,%s,'','',%s,%s,'',CURRENT_TIMESTAMP)
                """,
                (account_id, account_name, email, password, account_name, "logged_out", mid, bool(admin_account)),
            )
            if admin_account:
                cur.execute(
                    "UPDATE conlecta_account SET admin_account=FALSE, updated_at=CURRENT_TIMESTAMP WHERE merchant_id=%s AND account_id<>%s",
                    (mid, account_id),
                )
        conn.commit()


def upsert_account(acc):
    if not acc:
        return
    account_id = str(acc.get("id") or acc.get("account_id") or "").strip()
    if not account_id:
        return
    mid = normalize_merchant_id(acc.get("merchant_id"))
    ensure_merchant(mid)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conlecta_account (
                    account_id, account_name, email, password, otp, username,
                    session_status, device_id, last_ip, merchant_id, admin_account,
                    last_activity_ts, pin, updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                ON CONFLICT (account_id) DO UPDATE SET
                    account_name=EXCLUDED.account_name,
                    email=EXCLUDED.email,
                    password=EXCLUDED.password,
                    otp=EXCLUDED.otp,
                    username=EXCLUDED.username,
                    session_status=EXCLUDED.session_status,
                    device_id=EXCLUDED.device_id,
                    last_ip=EXCLUDED.last_ip,
                    merchant_id=EXCLUDED.merchant_id,
                    admin_account=EXCLUDED.admin_account,
                    last_activity_ts=EXCLUDED.last_activity_ts,
                    pin=COALESCE(NULLIF(EXCLUDED.pin, ''), conlecta_account.pin),
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    account_id,
                    str(acc.get("name") or acc.get("account_name") or "").strip(),
                    str(acc.get("email") or "").strip(),
                    str(acc.get("password") or "").strip(),
                    str(acc.get("otp") or "").strip(),
                    str(acc.get("username") or acc.get("name") or "").strip(),
                    str(acc.get("session") or acc.get("session_status") or "logged_out").strip(),
                    str(acc.get("device_id") or "").strip(),
                    str(acc.get("last_ip") or "").strip(),
                    mid,
                    bool(acc.get("admin_account")),
                    _ts(acc.get("last_activity_ts")),
                    str(acc.get("pin") or "").strip(),
                ),
            )
        conn.commit()


def update_account(account_id, account_name=None, email=None, password=None, merchant_id=None, admin_account=None):
    acc = find_account_by_id(account_id)
    if not acc:
        return False
    mid = normalize_merchant_id(merchant_id if merchant_id is not None else acc.get("merchant_id"))
    ensure_merchant(mid)
    name = str(account_name if account_name is not None else acc.get("name", "")).strip()
    mail = str(email if email is not None else acc.get("email", "")).strip()
    pwd = str(password if password is not None and str(password).strip() else acc.get("password", "")).strip()
    admin = bool(acc.get("admin_account") if admin_account is None else admin_account)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE conlecta_account SET
                    account_name=%s, email=%s, password=%s, username=%s,
                    merchant_id=%s, admin_account=%s, updated_at=CURRENT_TIMESTAMP
                WHERE account_id=%s
                """,
                (name, mail, pwd, acc.get("username") or name, mid, admin, account_id),
            )
            if admin:
                cur.execute(
                    "UPDATE conlecta_account SET admin_account=FALSE, updated_at=CURRENT_TIMESTAMP WHERE merchant_id=%s AND account_id<>%s",
                    (mid, account_id),
                )
        conn.commit()
    return True


def set_account_otp(account_id, otp_value):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conlecta_account SET otp=%s, updated_at=CURRENT_TIMESTAMP WHERE account_id=%s",
                (str(otp_value or ""), str(account_id or "")),
            )
        conn.commit()


def set_account_session(account_id, session_value, device_id=None, ip_address=None, last_activity_ts=None):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE conlecta_account SET
                    session_status=%s,
                    device_id=COALESCE(%s, device_id),
                    last_ip=COALESCE(%s, last_ip),
                    last_activity_ts=COALESCE(%s, last_activity_ts),
                    updated_at=CURRENT_TIMESTAMP
                WHERE account_id=%s
                """,
                (session_value, device_id, ip_address, _ts(last_activity_ts), str(account_id or "")),
            )
        conn.commit()


def set_account_last_activity(account_id, last_activity_ts=None):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conlecta_account SET last_activity_ts=%s, updated_at=CURRENT_TIMESTAMP WHERE account_id=%s",
                (_ts(last_activity_ts) or datetime.now(), str(account_id or "")),
            )
        conn.commit()


def set_account_pin(account_id, pin_value=""):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conlecta_account SET pin=%s, updated_at=CURRENT_TIMESTAMP WHERE account_id=%s",
                (str(pin_value or "").strip(), str(account_id or "")),
            )
        conn.commit()


def clear_other_merchant_admins(merchant_id, keep_account_id=""):
    mid = normalize_merchant_id(merchant_id)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conlecta_account SET admin_account=FALSE, updated_at=CURRENT_TIMESTAMP WHERE merchant_id=%s AND account_id<>%s",
                (mid, str(keep_account_id or "")),
            )
        conn.commit()


def load_vendors(merchant_id=None):
    mid = normalize_merchant_id(merchant_id)
    ensure_merchant(mid)
    with connect(row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT vendor_id, vendor_name, legacy_vendor_id, merchant_id FROM vendors WHERE merchant_id=%s ORDER BY vendor_name",
                (mid,),
            )
            return [
                {
                    "id": str(row["vendor_id"]),
                    "name": row["vendor_name"],
                    "merchant_id": row["merchant_id"],
                    "legacy_id": row.get("legacy_vendor_id") or "",
                }
                for row in cur.fetchall()
            ]


def save_vendor(name, merchant_id=None, legacy_vendor_id=None):
    mid = normalize_merchant_id(merchant_id)
    ensure_merchant(mid)
    vendor_name = str(name or "").strip()
    with connect(row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT vendor_id, vendor_name, merchant_id FROM vendors WHERE merchant_id=%s AND lower(vendor_name)=lower(%s) LIMIT 1",
                (mid, vendor_name),
            )
            row = cur.fetchone()
            if row:
                if legacy_vendor_id:
                    cur.execute("UPDATE vendors SET legacy_vendor_id=%s, updated_at=CURRENT_TIMESTAMP WHERE vendor_id=%s", (str(legacy_vendor_id), row["vendor_id"]))
                    conn.commit()
                return {"id": str(row["vendor_id"]), "name": row["vendor_name"], "merchant_id": row["merchant_id"]}
            cur.execute(
                "INSERT INTO vendors (vendor_name, merchant_id, legacy_vendor_id) VALUES (%s,%s,%s) RETURNING vendor_id, vendor_name, merchant_id",
                (vendor_name, mid, str(legacy_vendor_id or "") or None),
            )
            row = cur.fetchone()
        conn.commit()
    return {"id": str(row["vendor_id"]), "name": row["vendor_name"], "merchant_id": row["merchant_id"]}


def delete_vendor(vendor_id, merchant_id=None):
    mid = normalize_merchant_id(merchant_id)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM vendors WHERE vendor_id=%s AND merchant_id=%s", (int(vendor_id), mid))
            deleted = cur.rowcount > 0
        conn.commit()
    return deleted


def _vendor_id_for_input(cur, merchant_id, vendor_id):
    text = str(vendor_id or "").strip()
    if not text:
        return None
    cur.execute(
        "SELECT vendor_id FROM vendors WHERE merchant_id=%s AND (vendor_id::text=%s OR legacy_vendor_id=%s) LIMIT 1",
        (merchant_id, text, text),
    )
    row = cur.fetchone()
    return row["vendor_id"] if row else None


def load_stock(merchant_id=None):
    mid = normalize_merchant_id(merchant_id)
    ensure_merchant(mid)
    with connect(row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT item_id, item_name, price, capital, stock_qty, vendor_id, image_data, merchant_id
                FROM stock_items
                WHERE merchant_id=%s
                ORDER BY item_name
                """,
                (mid,),
            )
            rows = cur.fetchall()
    return [
        {
            "name": row["item_name"],
            "price": _money(row["price"]),
            "capital": _money(row["capital"]),
            "stock": int(row["stock_qty"] or 0),
            "vendor_id": str(row["vendor_id"] or ""),
            "image_b64": _encode_blob(row.get("image_data")),
            "merchant_id": row["merchant_id"],
        }
        for row in rows
    ]


def save_stock(products, merchant_id=None):
    mid = normalize_merchant_id(merchant_id)
    ensure_merchant(mid)
    clean = []
    with connect(row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM stock_items WHERE merchant_id=%s", (mid,))
            for idx, item in enumerate(products or [], start=1):
                name = str(item.get("name") or item.get("item_name") or "").strip()
                if not name:
                    continue
                vendor_db_id = _vendor_id_for_input(cur, mid, item.get("vendor_id"))
                image_blob = _decode_data_blob(item.get("image_b64") or item.get("image"))
                cur.execute(
                    """
                    INSERT INTO stock_items (
                        item_name, price, capital, stock_qty, vendor_id, image_data,
                        image_filename, merchant_id, legacy_item_no, updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                    """,
                    (
                        name,
                        _int_money(item.get("price")),
                        _int_money(item.get("capital") or item.get("cost") or item.get("buy_price")),
                        _int_money(item.get("stock")),
                        vendor_db_id,
                        image_blob,
                        f"{name}.png" if image_blob else None,
                        mid,
                        idx,
                    ),
                )
                clean.append({
                    "name": name,
                    "price": _int_money(item.get("price")),
                    "capital": _int_money(item.get("capital") or item.get("cost") or item.get("buy_price")),
                    "stock": _int_money(item.get("stock")),
                    "vendor_id": str(vendor_db_id or ""),
                    "image_b64": item.get("image_b64", "") or "",
                    "merchant_id": mid,
                })
        conn.commit()
    return clean


def sync_stock_delta(products, changed_names, merchant_id=None):
    names = {str(name or "").strip().casefold() for name in (changed_names or []) if str(name or "").strip()}
    if not names:
        return
    mid = normalize_merchant_id(merchant_id)
    current = [item for item in (products or []) if str(item.get("name") or "").strip().casefold() in names]
    if not current:
        return
    with connect(row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            for item in current:
                name = str(item.get("name") or "").strip()
                vendor_db_id = _vendor_id_for_input(cur, mid, item.get("vendor_id"))
                image_blob = _decode_data_blob(item.get("image_b64") or item.get("image"))
                cur.execute("DELETE FROM stock_items WHERE merchant_id=%s AND lower(item_name)=lower(%s)", (mid, name))
                cur.execute(
                    """
                    INSERT INTO stock_items (item_name, price, capital, stock_qty, vendor_id, image_data, image_filename, merchant_id, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                    """,
                    (
                        name,
                        _int_money(item.get("price")),
                        _int_money(item.get("capital") or item.get("cost") or item.get("buy_price")),
                        _int_money(item.get("stock")),
                        vendor_db_id,
                        image_blob,
                        f"{name}.png" if image_blob else None,
                        mid,
                    ),
                )
        conn.commit()


def save_history(record, merchant_id=None):
    mid = normalize_merchant_id(merchant_id or record.get("merchant_id"))
    ensure_merchant(mid)
    txn_id = str(record.get("txn_id") or record.get("transaction_id") or "").strip()
    if not txn_id:
        return
    amount = _int_money(record.get("amount"))
    payment_fee = _int_money(record.get("payment_fee"))
    updated_at = _ts(record.get("updated_at")) or _ts(record.get("updated_at_display")) or datetime.now()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO transactions (
                    transaction_id, qr_id, amount, updated_at, customer, customer_note, customer_email,
                    discount_raw, cashier_name, gross_amount, line_discount, cart_disc_amount,
                    payment_method, cash_received, change_amount, merchant_id, payment_fee, net_amount
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (transaction_id) DO UPDATE SET
                    qr_id=EXCLUDED.qr_id,
                    amount=EXCLUDED.amount,
                    updated_at=EXCLUDED.updated_at,
                    customer=EXCLUDED.customer,
                    customer_note=EXCLUDED.customer_note,
                    customer_email=EXCLUDED.customer_email,
                    discount_raw=EXCLUDED.discount_raw,
                    cashier_name=EXCLUDED.cashier_name,
                    gross_amount=EXCLUDED.gross_amount,
                    line_discount=EXCLUDED.line_discount,
                    cart_disc_amount=EXCLUDED.cart_disc_amount,
                    payment_method=EXCLUDED.payment_method,
                    cash_received=EXCLUDED.cash_received,
                    change_amount=EXCLUDED.change_amount,
                    merchant_id=EXCLUDED.merchant_id,
                    payment_fee=EXCLUDED.payment_fee,
                    net_amount=EXCLUDED.net_amount
                """,
                (
                    txn_id,
                    str(record.get("qr_id") or ""),
                    amount,
                    updated_at,
                    str(record.get("customer_name") or record.get("customer") or ""),
                    str(record.get("customer_note") or record.get("customer_name") or record.get("customer") or ""),
                    str(record.get("customer_email") or ""),
                    str(record.get("discount") or "0"),
                    str(record.get("cashier_name") or ""),
                    _int_money(record.get("gross"), amount),
                    _int_money(record.get("line_discount")),
                    _int_money(record.get("cart_discount_amt")),
                    str(record.get("payment_method") or ""),
                    _int_money(record.get("cash_received")),
                    _int_money(record.get("change")),
                    mid,
                    payment_fee,
                    _int_money(record.get("net_amount"), amount - payment_fee),
                ),
            )
            cur.execute("DELETE FROM transaction_items WHERE transaction_id=%s", (txn_id,))
            for line_no, item in enumerate(record.get("items", []) or [], start=1):
                qty = _int_money(item.get("qty"))
                unit = _int_money(item.get("amount") or item.get("price") or item.get("unit_price"))
                subtotal = _int_money(item.get("subtotal"), unit * qty)
                capital = _int_money(item.get("capital") or item.get("cost"))
                payment_fee_line = _int_money(item.get("payment_fee"))
                total_cost = _int_money(item.get("total_cost"), (capital * qty) + payment_fee_line)
                cur.execute(
                    """
                    INSERT INTO transaction_items (
                        transaction_id, qr_id, item_name, qty, unit_price, subtotal, free_flag,
                        disc_percent, disc_amount, line_discount, payment_method, change_amount,
                        cash_received, merchant_id, capital, profit, payment_fee, total_cost,
                        gross_amount, source_line_no
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        txn_id,
                        str(record.get("qr_id") or ""),
                        str(item.get("item_name") or item.get("name") or ""),
                        qty,
                        unit,
                        subtotal,
                        bool(item.get("free")),
                        _int_money(item.get("disc_pct")),
                        _int_money(item.get("disc_fixed")),
                        _int_money(item.get("line_discount")),
                        str(record.get("payment_method") or item.get("payment_method") or ""),
                        _int_money(record.get("change") or item.get("change")),
                        _int_money(record.get("cash_received") or item.get("cash_received")),
                        mid,
                        capital,
                        _int_money(item.get("profit"), subtotal - total_cost),
                        payment_fee_line,
                        total_cost,
                        _int_money(item.get("gross"), unit * qty),
                        line_no,
                    ),
                )
        conn.commit()


def load_history(merchant_id=None):
    mid = normalize_merchant_id(merchant_id)
    with connect(row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM transactions WHERE merchant_id=%s ORDER BY updated_at DESC, created_at DESC",
                (mid,),
            )
            txns = cur.fetchall()
            ids = [row["transaction_id"] for row in txns]
            items_by_txn = {tid: [] for tid in ids}
            if ids:
                cur.execute(
                    "SELECT * FROM transaction_items WHERE transaction_id = ANY(%s) ORDER BY transaction_id, source_line_no, item_line_id",
                    (ids,),
                )
                for row in cur.fetchall():
                    item = {
                        "item_name": row.get("item_name") or "",
                        "name": row.get("item_name") or "",
                        "qty": int(row.get("qty") or 0),
                        "amount": _money(row.get("unit_price")),
                        "price": _money(row.get("unit_price")),
                        "unit_price": _money(row.get("unit_price")),
                        "subtotal": _money(row.get("subtotal")),
                        "gross": _money(row.get("gross_amount")),
                        "capital": _money(row.get("capital")),
                        "cost": _money(row.get("capital")),
                        "payment_fee": _money(row.get("payment_fee")),
                        "total_cost": _money(row.get("total_cost")),
                        "profit": _money(row.get("profit")),
                        "free": bool(row.get("free_flag")),
                        "disc_pct": _money(row.get("disc_percent")),
                        "disc_fixed": _money(row.get("disc_amount")),
                        "line_discount": _money(row.get("line_discount")),
                        "payment_method": row.get("payment_method") or "",
                        "change": _money(row.get("change_amount")),
                        "cash_received": _money(row.get("cash_received")),
                    }
                    items_by_txn.setdefault(row["transaction_id"], []).append(item)
    result = []
    for row in txns:
        updated = _iso(row.get("updated_at"))
        result.append({
            "txn_id": row["transaction_id"],
            "qr_id": row.get("qr_id") or "",
            "amount": _money(row.get("amount")),
            "updated_at": updated,
            "updated_at_display": updated,
            "customer_name": row.get("customer") or row.get("customer_note") or "",
            "customer": row.get("customer") or row.get("customer_note") or "",
            "customer_email": row.get("customer_email") or "",
            "discount": row.get("discount_raw") or "0",
            "cashier_name": row.get("cashier_name") or row.get("cashier") or "",
            "gross": _money(row.get("gross_amount")) or _money(row.get("amount")),
            "line_discount": _money(row.get("line_discount")),
            "cart_discount_amt": _money(row.get("cart_disc_amount")),
            "payment_method": row.get("payment_method") or "",
            "cash_received": _money(row.get("cash_received")),
            "change": _money(row.get("change_amount")),
            "payment_fee": _money(row.get("payment_fee")),
            "net_amount": _money(row.get("net_amount")),
            "merchant_id": row.get("merchant_id") or mid,
            "items": items_by_txn.get(row["transaction_id"], []),
        })
    return result


def load_version(default_info):
    info = dict(default_info or {})
    with connect(row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM version_changes ORDER BY active_flag DESC, updated_at DESC LIMIT 1")
            row = cur.fetchone()
    if row:
        info.update({
            "version": row.get("version_no") or info.get("version", ""),
            "title": row.get("title") or info.get("title", ""),
            "change": row.get("change_log") or info.get("change", ""),
            "active": "yes" if row.get("active_flag") else "",
            "updated_at": _iso(row.get("updated_at")),
        })
    title = str(info.get("title") or "Conlecta Version").strip()
    version = str(info.get("version") or "").strip()
    info["label"] = f"{title} {version}".strip()
    return info


def save_version(data):
    version = str(data.get("version") or "1.0.0").strip()
    title = str(data.get("title") or "Conlecta Version").strip()
    change = str(data.get("change") or "").strip()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE version_changes SET active_flag=FALSE")
            cur.execute(
                """
                INSERT INTO version_changes (version_no, title, change_log, active_flag, updated_at)
                VALUES (%s,%s,%s,TRUE,CURRENT_TIMESTAMP)
                ON CONFLICT (version_no) DO UPDATE SET
                    title=EXCLUDED.title,
                    change_log=EXCLUDED.change_log,
                    active_flag=TRUE,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (version, title, change),
            )
        conn.commit()
    return load_version({"version": version, "title": title, "change": change, "active": "yes"})


def load_email_templates(default_templates):
    templates = {k: dict(v) for k, v in (default_templates or {}).items()}
    with connect(row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM email_templates")
            rows = cur.fetchall()
    for row in rows:
        key = str(row.get("template_key") or "").lower()
        if key not in templates:
            continue
        templates[key].update({
            "subject": row.get("subject") or templates[key].get("subject", ""),
            "html_override": row.get("html_override") or "",
            "primary_color": row.get("primary_color") or templates[key].get("primary_color", ""),
            "primary_text_color": row.get("primary_text_color") or templates[key].get("primary_text_color", ""),
            "bg_color": row.get("bg_color") or templates[key].get("bg_color", ""),
            "secondary_color": row.get("secondary_color") or templates[key].get("secondary_color", ""),
            "logo_path": templates[key].get("logo_path", ""),
            "logo_align": row.get("logo_align") or templates[key].get("logo_align", "center"),
        })
    return templates


def save_email_template(key, data):
    key = str(key or "").strip().lower()
    logo_data, logo_filename = _read_blob(data.get("logo_path"))
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO email_templates (
                    template_key, subject, html_override, primary_color, primary_text_color,
                    bg_color, secondary_color, logo_data, logo_filename, logo_align, updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                ON CONFLICT (template_key) DO UPDATE SET
                    subject=EXCLUDED.subject,
                    html_override=EXCLUDED.html_override,
                    primary_color=EXCLUDED.primary_color,
                    primary_text_color=EXCLUDED.primary_text_color,
                    bg_color=EXCLUDED.bg_color,
                    secondary_color=EXCLUDED.secondary_color,
                    logo_data=COALESCE(EXCLUDED.logo_data, email_templates.logo_data),
                    logo_filename=COALESCE(EXCLUDED.logo_filename, email_templates.logo_filename),
                    logo_align=EXCLUDED.logo_align,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    key,
                    str(data.get("subject", "") or ""),
                    str(data.get("html_override", "") or ""),
                    str(data.get("primary_color", "") or ""),
                    str(data.get("primary_text_color", "") or ""),
                    str(data.get("bg_color", "") or ""),
                    str(data.get("secondary_color", "") or ""),
                    logo_data,
                    logo_filename,
                    str(data.get("logo_align", "center") or "center"),
                ),
            )
        conn.commit()
