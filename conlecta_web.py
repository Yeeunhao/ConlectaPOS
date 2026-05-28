import base64
import glob
import html
import io
import json
import logging
import mimetypes
import os
try:
    from dotenv import load_dotenv

    BASE_ENV_DIR = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(BASE_ENV_DIR, ".env"))
    load_dotenv(os.path.join(BASE_ENV_DIR, "database.env"))
except Exception:
    pass
import random
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.text import MIMEText
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

try:
    import qrcode
except Exception:
    qrcode = None

try:
    import requests
except Exception:
    requests = None

try:
    import conlecta_db
except Exception:
    conlecta_db = None

try:
    import gspread
    GSHEETS_AVAILABLE = True
except Exception:
    gspread = None
    GSHEETS_AVAILABLE = False


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = BASE_DIR
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

SETTINGS_FILE = os.path.join(BASE_DIR, "pos_settings.json")
WEB_STATE_FILE = os.path.join(BASE_DIR, "web_state.json")
OAUTH_CREDS_FILE = os.path.join(BASE_DIR, "oauth_credentials.json")
OAUTH_TOKEN_FILE = os.path.join(BASE_DIR, "oauth_token.json")
GMAIL_TOKEN_FILE = os.path.join(BASE_DIR, "token.json")

SPREADSHEET_ID = "1wVrAETyYaK4Nj-qfZofT6Ki9eToeiVpmaKY3qu1bzlQ"
SHEET_STOCK = "Stock Conlecta"
SHEET_TXN = "Transactions"
SHEET_TXN_ITEMS = "Transaction Items"
SHEET_ACCOUNTS = "Conlecta Account"
SHEET_MERCHANTS = "Merchants"
SHEET_VERSION_CHANGES = "Version Changes"
SHEET_PASSWORDS = "Passwords"
SHEET_EMAIL_TEMPLATES = "Email_Templates"
SHEET_VENDORS = "Vendors"

DEFAULT_MERCHANT_ID = "conlecta"
DEFAULT_MERCHANT_NAME = "Conlecta"
SYSTEM_ADMIN_NAME = "Junhao"
SYSTEM_ADMIN_EMAIL = "joshuandiantonio@gmail.com"
SYSTEM_LOG_ADMIN_EMAIL = "antoniojos121@gmail.com"
PDF_GENERATED_REMARK = "This document was generated automatically by Conlecta POS. Please keep it for your records."

STOCK_HEADERS = ["No", "Item Name", "Price", "Capital", "Stock", "Vendor ID", "Image_Base64", "Merchant ID"]
TXN_HEADER = [
    "No", "Transaction ID", "QR ID", "Amount", "Updated At",
    "Customer Note", "Discount", "Cashier Name", "Gross",
    "Line Discount", "Cart Disc Amt", "Payment Method",
    "Cash Received", "Change", "Payment Fee", "Net Amount", "Merchant ID",
]
ITEMS_HEADER = [
    "No", "Transaction ID", "QR ID", "Item Name", "Qty", "Amount",
    "Subtotal", "Capital", "Profit", "Payment Fee", "Total Cost", "Free", "Disc %", "Disc Rp", "Line Discount",
    "Payment Method", "Change", "Cash Received", "Merchant ID",
]
ACCOUNT_HEADER = [
    "Account ID", "Account Name", "Email", "Password", "OTP",
    "Username", "Session", "Device ID", "Last IP", "Merchant ID",
    "Admin Account", "Last Activity Timestamp", "PIN",
]
PASSWORDS_HEADER = ["Passwords ID", "Password Function", "Password"]
EMAIL_TEMPLATE_HEADER = [
    "Key", "Subject", "HTML Override", "Primary Color", "Primary Text Color",
    "BG Color", "Secondary Color", "Logo Path", "Logo Align",
]
VENDOR_HEADER = ["Vendor ID", "Vendor Name", "Merchant ID"]
MERCHANT_HEADER = ["Merchant ID", "Merchant Name", "Logo Path"]
VERSION_HEADER = ["Version", "Title", "Change", "Active", "Updated At"]

DEFAULT_VERSION_INFO = {
    "version": "1.0.0",
    "title": "Conlecta Version",
    "change": "Initial web POS version",
    "active": "yes",
    "updated_at": "",
    "label": "Conlecta Version 1.0.0",
}

COL_OTP = 5
COL_SESSION = 7
COL_DEVICE_ID = 8
COL_LAST_IP = 9
COL_LAST_ACTIVITY = 12
SESSION_ACTIVE = "active"
SESSION_LOGGED_OUT = "logged_out"
SESSION_IDLE_SECONDS = 30 * 60

PAYMENT_METHOD_QRIS = "QRIS"
PAYMENT_METHOD_CASH = "Cash"
QRIS_FEE_RATE = 0.007
PAID_QRIS_STATUSES = {"success", "paid", "completed", "settled", "succeeded"}
OTP_TTL_SECONDS = 60
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_RESENDS = 1
DISPLAY_EVENT_TTL_SECONDS = 5
DISPLAY_SUCCESS_MAX_HOLD_SECONDS = 24 * 60 * 60
CASHIER_NOTICE_STALE_SECONDS = 8
CLOSED_QR_TTL_SECONDS = 24 * 60 * 60
ACTIVE_QR_TTL_SECONDS = 30 * 60
PENDING_AUTH_TTL_SECONDS = 10 * 60

VPS_QRIS_BASE_URL = os.environ.get(
    "CONLECTA_QRIS_VPS_URL",
    "http://34.128.90.163:8000",
).rstrip("/")
VPS_QRIS_GENERATE_URL = f"{VPS_QRIS_BASE_URL}/qris/generate"
VPS_QRIS_STATUS_URL = f"{VPS_QRIS_BASE_URL}/qris/status"
VPS_QRIS_SHOW_URL = f"{VPS_QRIS_BASE_URL}/qris/show"

BRAND_DEFAULT_LOGO = os.path.join(ASSETS_DIR, "ConlectaPosLogo.png")
BRAND_EMAIL_LOGO = os.path.join(ASSETS_DIR, "Email", "ConlectaIcon.png")
VIDEO_FOLDER = os.path.join(ASSETS_DIR, "videos")
PAYMENT_UPLOAD_FOLDER = os.path.join(ASSETS_DIR, "Payment")
SPLASH_VIDEO = os.path.join(VIDEO_FOLDER, "Splash.mp4")

DEFAULT_EMAIL_TEMPLATES = {
    "otp": {
        "subject": "Conlecta POS - OTP untuk {account_name}",
        "html_override": "",
        "primary_color": "#22d3c5",
        "primary_text_color": "#ffffff",
        "bg_color": "#0f172a",
        "secondary_color": "#7c3aed",
        "logo_path": BRAND_DEFAULT_LOGO,
        "logo_align": "center",
    },
    "receipt": {
        "subject": "{shop_name} - Payment Receipt on {timestamp}",
        "html_override": "",
        "primary_color": "#00C896",
        "primary_text_color": "#ffffff",
        "bg_color": "#0D1117",
        "secondary_color": "#0094FF",
        "logo_path": BRAND_EMAIL_LOGO,
        "logo_align": "center",
    },
}

DEFAULT_SETTINGS = {
    "shop_name": DEFAULT_MERCHANT_NAME,
    "shop_address": "Store ADDRESS",
    "shop_postcode": "Store postal code",
    "marquee_msgs": [
        "CONLECTA POS - Scan QR untuk membayar",
        "QRIS tersedia - Semua bank & e-wallet",
        "Pembayaran aman & cepat",
        "Powered by SingaPay QRIS",
    ],
    "video_playlist": [],
    "saved_cashier_account_id": "",
    "remember_cashier": False,
    "active_theme": "crystal_bloom",
    "default_customer_prefix": "Conlecta Customer",
    "brand_logo_path": "",
    "payment_image_path": "",
    "payment_image_paths": [],
}
LEGACY_QRIS_SETTING_KEYS = {
    "partner_id", "client_id", "client_secret", "base_url", "token_url",
    "token_body", "qr_generate_path", "qr_show_path", "qr_body",
}

SAMPLE_PRODUCTS = [
    {"name": "Es Teh Solo", "price": 10000, "stock": 74, "vendor_id": "", "image_b64": ""},
    {"name": "Es Mambo", "price": 10000, "stock": 1, "vendor_id": "", "image_b64": ""},
    {"name": "Ciki", "price": 10000, "stock": 10, "vendor_id": "", "image_b64": ""},
    {"name": "ciki 2", "price": 10000, "stock": 10, "vendor_id": "", "image_b64": ""},
    {"name": "test", "price": 10000, "stock": 100, "vendor_id": "", "image_b64": ""},
    {"name": "Odading", "price": 10000, "stock": 10, "vendor_id": "", "image_b64": ""},
]

STATE_LOCK = threading.RLock()
_gspread_client = None
_spreadsheet_handle = None
_stock_cache = None
_stock_cache_ts = 0.0
_ACCOUNT_LOOKUP_UNAVAILABLE = object()
_DB_SCHEMA_READY = False
_DB_SCHEMA_ERROR_TS = 0.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, "conlecta_web.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("ConlectaWeb")


def _db_configured():
    return conlecta_db is not None and conlecta_db.is_configured()


def _db_mandatory():
    if not _db_configured() or os.environ.get("CONLECTA_ALLOW_SHEETS") == "1":
        return False
    return _db_ready()


def _db_unavailable_message(area="data"):
    return f"Database PostgreSQL tidak tersedia untuk {area}."


def _db_ready():
    global _DB_SCHEMA_READY, _DB_SCHEMA_ERROR_TS
    if not _db_configured():
        return False
    if _DB_SCHEMA_READY:
        return True
    now = time.time()
    if _DB_SCHEMA_ERROR_TS and now - _DB_SCHEMA_ERROR_TS < 30:
        return False
    try:
        conlecta_db.ensure_schema()
        _DB_SCHEMA_READY = True
        _DB_SCHEMA_ERROR_TS = 0.0
        return True
    except Exception as exc:
        _DB_SCHEMA_ERROR_TS = now
        log.warning(
            "database unavailable: %s (host=%s port=%s - check Cloud SQL authorized networks / VPN)",
            exc,
            (conlecta_db._env_config().get("host") if conlecta_db else "-"),
            (conlecta_db._env_config().get("port") if conlecta_db else "-"),
        )
        return False


def _int_money(value, default=0):
    try:
        if value is None:
            return default
        text = str(value).replace("Rp", "").replace(",", "").replace(".", "").strip()
        return int(float(text or default))
    except Exception:
        return default


def format_rupiah(value):
    try:
        return f"Rp {int(value):,}".replace(",", ".")
    except Exception:
        return f"Rp {value}"


def format_datetime(value=None):
    if not value:
        dt = datetime.now()
    elif isinstance(value, datetime):
        dt = value
    else:
        text = str(value).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except Exception:
            return str(value)
    return dt.strftime("%A - %d-%m-%Y %H:%M")


def generate_txn_id():
    return f"TXN-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"


def generate_account_id():
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"ACC-{ts}-{uuid.uuid4().hex[:8].upper()}"


def calc_qris_fee(amount):
    return round(_int_money(amount) * QRIS_FEE_RATE)


def normalize_payment_method(method):
    text = str(method or "").strip().lower()
    if text in {"cash", "tunai"}:
        return PAYMENT_METHOD_CASH
    return PAYMENT_METHOD_QRIS


def derive_payment_method(method=None, cash_received=0, change=0, qr_id=None):
    text = str(method or "").strip().lower()
    if text in {"cash", "tunai"}:
        return PAYMENT_METHOD_CASH
    if text in {"qris", "qr", "qr payment"}:
        return PAYMENT_METHOD_QRIS
    if _int_money(cash_received) > 0 or _int_money(change) > 0:
        return PAYMENT_METHOD_CASH
    if qr_id is not None and not str(qr_id or "").strip():
        return PAYMENT_METHOD_CASH
    return PAYMENT_METHOD_QRIS


def _strip_legacy_settings(data):
    clean = dict(data or {})
    for key in LEGACY_QRIS_SETTING_KEYS:
        clean.pop(key, None)
    return clean


def normalize_merchant_id(value):
    text = str(value or "").strip().lower()
    if not text:
        return DEFAULT_MERCHANT_ID
    safe = "".join(ch if ch.isalnum() else "_" for ch in text)
    safe = "_".join(part for part in safe.split("_") if part)
    return safe or DEFAULT_MERCHANT_ID


def _is_admin_flag(value):
    return str(value or "").strip().lower() in {"1", "yes", "true", "admin", "owner", "y"}


def _session_business_day(now=None):
    now = now or datetime.now()
    day = now.date()
    if now.hour == 23 and now.minute >= 59:
        day = day + timedelta(days=1)
    return day.isoformat()


def _next_session_reset_at(now=None):
    now = now or datetime.now()
    reset = now.replace(hour=23, minute=59, second=0, microsecond=0)
    if now >= reset:
        reset = reset + timedelta(days=1)
    return reset.isoformat(timespec="minutes")


def _state_tenant_bucket(state, merchant_id=None):
    mid = normalize_merchant_id(merchant_id)
    session_day = _session_business_day()
    tenants = state.setdefault("tenant_data", {})
    if mid not in tenants:
        legacy = mid == DEFAULT_MERCHANT_ID
        tenants[mid] = {
            "products": list(state.get("products") or SAMPLE_PRODUCTS) if legacy else [],
            "history": list(state.get("history") or []) if legacy else [],
            "active_qr": state.get("active_qr") if legacy else None,
            "display_event": state.get("display_event") if legacy else None,
            "closed_qr_ids": dict(state.get("closed_qr_ids") or {}) if legacy else {},
            "session": dict(state.get("session") or {"sales": 0, "revenue": 0}) if legacy else {"sales": 0, "revenue": 0},
            "session_day": str(state.get("session_day") or session_day) if legacy else session_day,
            "session_reset_at": str(state.get("session_reset_at") or _next_session_reset_at()),
            "customer_counter": _int_money(state.get("customer_counter")) if legacy else 0,
        }
    bucket = tenants[mid]
    bucket.setdefault("products", [])
    bucket.setdefault("history", [])
    bucket.setdefault("active_qr", None)
    bucket.setdefault("display_event", None)
    bucket.setdefault("closed_qr_ids", {})
    bucket.setdefault("session", {"sales": 0, "revenue": 0})
    bucket.setdefault("session_day", session_day)
    bucket.setdefault("session_reset_at", _next_session_reset_at())
    bucket.setdefault("customer_counter", 0)
    return bucket


def _ensure_daily_session(state, merchant_id=None):
    mid = normalize_merchant_id(merchant_id)
    bucket = _state_tenant_bucket(state, mid)
    session_day = _session_business_day()
    if str(bucket.get("session_day") or "") != session_day:
        bucket["session"] = {"sales": 0, "revenue": 0}
        bucket["session_day"] = session_day
        bucket["session_reset_at"] = _next_session_reset_at()
        log.info("Daily cashier session reset for merchant=%s day=%s", mid, session_day)
    else:
        bucket["session_reset_at"] = _next_session_reset_at()
    _sync_legacy_state_for_default(state, mid)
    return bucket


def _sync_legacy_state_for_default(state, merchant_id=None):
    mid = normalize_merchant_id(merchant_id)
    if mid != DEFAULT_MERCHANT_ID:
        return
    bucket = _state_tenant_bucket(state, mid)
    state["products"] = bucket.get("products", [])
    state["history"] = bucket.get("history", [])
    state["active_qr"] = bucket.get("active_qr")
    state["display_event"] = bucket.get("display_event")
    state["closed_qr_ids"] = bucket.get("closed_qr_ids", {})
    state["session"] = bucket.get("session", {"sales": 0, "revenue": 0})
    state["session_day"] = bucket.get("session_day", _session_business_day())
    state["session_reset_at"] = bucket.get("session_reset_at", _next_session_reset_at())
    state["customer_counter"] = bucket.get("customer_counter", 0)


def current_merchant_id():
    try:
        state = load_state()
        auth = state.get("auth") or {}
        if auth.get("merchant_id"):
            return normalize_merchant_id(auth.get("merchant_id"))
        if auth.get("id"):
            acc = _find_account_by_id(auth.get("id"))
            if acc:
                return normalize_merchant_id(acc.get("merchant_id"))
        return DEFAULT_MERCHANT_ID
    except Exception:
        return DEFAULT_MERCHANT_ID


def load_settings(merchant_id=None):
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    if _db_ready():
        try:
            merged = conlecta_db.load_settings(DEFAULT_SETTINGS, mid)
            for key, value in DEFAULT_SETTINGS.items():
                if isinstance(value, str) and not str(merged.get(key, "")).strip():
                    merged[key] = value
            merged["merchant_id"] = mid
            return merged
        except Exception as exc:
            log.warning("load_settings db failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("settings")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("settings"))
    data = {}
    if os.path.isfile(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            log.warning("load_settings: %s", exc)
    merged = dict(DEFAULT_SETTINGS)
    tenant_settings = data.get("merchant_settings", {}) if isinstance(data.get("merchant_settings"), dict) else {}
    legacy_settings = {k: v for k, v in data.items() if k in DEFAULT_SETTINGS and v is not None}
    if mid == DEFAULT_MERCHANT_ID:
        merged.update(_strip_legacy_settings(legacy_settings))
    if mid in tenant_settings and isinstance(tenant_settings[mid], dict):
        merged.update(_strip_legacy_settings({k: v for k, v in tenant_settings[mid].items() if v is not None}))
    for key, value in DEFAULT_SETTINGS.items():
        if isinstance(value, str) and not str(merged.get(key, "")).strip():
            merged[key] = value
    merged["merchant_id"] = mid
    return merged


def _write_settings_for_merchant(settings, merchant_id=None):
    mid = normalize_merchant_id(merchant_id or settings.get("merchant_id") or current_merchant_id())
    if _db_ready():
        try:
            saved = conlecta_db.save_settings(settings, mid)
            return settings_payload(saved, merchant_id=mid)
        except Exception as exc:
            log.warning("write_settings db failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("settings")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("settings"))
    stored = {}
    if os.path.isfile(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                stored = json.load(f)
        except Exception:
            stored = {}
    tenant_settings = stored.get("merchant_settings")
    if not isinstance(tenant_settings, dict):
        tenant_settings = {}
    clean = {k: v for k, v in settings.items() if k in DEFAULT_SETTINGS}
    tenant_settings[mid] = clean
    stored["merchant_settings"] = tenant_settings
    if mid == DEFAULT_MERCHANT_ID:
        stored.update(clean)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(stored, f, ensure_ascii=False, indent=2)
    return settings_payload(settings, merchant_id=mid)


def save_settings(data, merchant_id=None):
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    current = load_settings(mid)
    allowed = set(DEFAULT_SETTINGS)
    for key, value in _strip_legacy_settings(data).items():
        if key in allowed:
            current[key] = value
    log.info("Settings saved from web UI")
    sync_merchant_from_settings(current, mid)
    return _write_settings_for_merchant(current, mid)


def default_state():
    return {
        "products": list(SAMPLE_PRODUCTS),
        "history": [],
        "active_qr": None,
        "display_event": None,
        "session": {"sales": 0, "revenue": 0},
        "session_day": _session_business_day(),
        "session_reset_at": _next_session_reset_at(),
        "customer_counter": 0,
        "auth": None,
        "pending_otps": {},
        "pending_auth": {},
    }


def load_state():
    with STATE_LOCK:
        state = default_state()
        if os.path.isfile(WEB_STATE_FILE):
            try:
                with open(WEB_STATE_FILE, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                if isinstance(stored, dict):
                    state.update(stored)
            except Exception as exc:
                log.warning("load_state: %s", exc)
        return state


def save_state(state):
    with STATE_LOCK:
        state = dict(state or {})
        with open(WEB_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)


def get_gspread_client():
    global _gspread_client
    if _gspread_client:
        return _gspread_client
    if not GSHEETS_AVAILABLE or not os.path.isfile(OAUTH_CREDS_FILE):
        return None
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except Exception as exc:
        log.warning("Google auth import failed: %s", exc)
        return None

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
    ]
    creds = None
    if os.path.isfile(OAUTH_TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(OAUTH_TOKEN_FILE, scopes)
        except Exception as exc:
            log.warning("Could not load Google token: %s", exc)
    if creds and not creds.valid and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(OAUTH_TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
            log.info("Google token refreshed")
        except Exception as exc:
            log.warning("Google token refresh failed: %s", exc)
            creds = None
    if not creds or not creds.valid:
        return None
    try:
        _gspread_client = gspread.authorize(creds)
        return _gspread_client
    except Exception as exc:
        log.warning("gspread authorize failed: %s", exc)
        return None


def get_spreadsheet():
    global _spreadsheet_handle
    if _db_mandatory():
        return None
    if _spreadsheet_handle is not None:
        return _spreadsheet_handle
    client = get_gspread_client()
    if not client:
        return None
    try:
        _spreadsheet_handle = client.open_by_key(SPREADSHEET_ID)
        return _spreadsheet_handle
    except Exception as exc:
        log.warning("open spreadsheet failed: %s", exc)
        _spreadsheet_handle = None
        return None


def ensure_ws(spreadsheet, title, headers):
    try:
        ws = spreadsheet.worksheet(title)
    except Exception as exc:
        try:
            for candidate in spreadsheet.worksheets():
                if candidate.title == title:
                    ws = candidate
                    break
            else:
                ws = None
        except Exception:
            ws = None
        if ws is None:
            try:
                ws = spreadsheet.add_worksheet(title=title, rows=2000, cols=max(8, len(headers) + 2))
                ws.update([headers], "A1")
                return ws
            except Exception as add_exc:
                log.warning("ensure worksheet failed for %s: lookup=%s add=%s", title, exc, add_exc)
                return None
    try:
        current = ws.row_values(1)
        if not current:
            ws.update([headers], "A1")
        else:
            extended = list(current)
            changed = False
            for header in headers:
                if header not in extended:
                    extended.append(header)
                    changed = True
            if changed:
                ws.update([extended], "A1")
    except Exception as exc:
        log.warning("ensure headers failed for %s: %s", title, exc)
    return ws


def _get_ws(title, headers):
    spreadsheet = get_spreadsheet()
    if spreadsheet is None:
        return None
    try:
        return ensure_ws(spreadsheet, title, headers)
    except Exception as exc:
        log.warning("get worksheet failed for %s: %s", title, exc)
        return None


def load_merchants():
    if _db_ready():
        try:
            merchants = conlecta_db.load_merchants()
            if DEFAULT_MERCHANT_ID not in merchants:
                merchants[DEFAULT_MERCHANT_ID] = {
                    "id": DEFAULT_MERCHANT_ID,
                    "name": DEFAULT_MERCHANT_NAME,
                    "logo_path": BRAND_DEFAULT_LOGO,
                }
            return merchants
        except Exception as exc:
            log.warning("load_merchants db failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("merchant"))
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("merchant"))
    ws = _get_ws(SHEET_MERCHANTS, MERCHANT_HEADER)
    merchants = {}
    if ws is not None:
        try:
            for row in ws.get_all_values()[1:]:
                mid = normalize_merchant_id(row[0] if len(row) > 0 else "")
                if not mid:
                    continue
                merchants[mid] = {
                    "id": mid,
                    "name": str(row[1]).strip() if len(row) > 1 and str(row[1]).strip() else DEFAULT_MERCHANT_NAME,
                    "logo_path": str(row[2]).strip() if len(row) > 2 else "",
                }
        except Exception as exc:
            log.warning("load_merchants failed: %s", exc)
    if DEFAULT_MERCHANT_ID not in merchants:
        merchants[DEFAULT_MERCHANT_ID] = {
            "id": DEFAULT_MERCHANT_ID,
            "name": DEFAULT_MERCHANT_NAME,
            "logo_path": BRAND_DEFAULT_LOGO,
        }
    return merchants


def upsert_merchant(merchant_id, name="", logo_path=""):
    mid = normalize_merchant_id(merchant_id)
    name = str(name or "").strip() or DEFAULT_MERCHANT_NAME
    logo_path = str(logo_path or "").strip()
    if _db_ready():
        try:
            return conlecta_db.upsert_merchant(mid, name, logo_path)
        except Exception as exc:
            log.warning("upsert_merchant db failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("merchant")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("merchant"))
    ws = _get_ws(SHEET_MERCHANTS, MERCHANT_HEADER)
    if ws is None:
        return {"id": mid, "name": name, "logo_path": logo_path}
    rows = ws.get_all_values()
    row_out = [mid, name, logo_path]
    try:
        for row_index, row in enumerate(rows[1:], start=2):
            if row and normalize_merchant_id(row[0]) == mid:
                ws.update([row_out], f"A{row_index}")
                return {"id": mid, "name": name, "logo_path": logo_path}
        ws.append_row(row_out, value_input_option="USER_ENTERED")
    except Exception as exc:
        log.warning("upsert_merchant failed: %s", exc)
    return {"id": mid, "name": name, "logo_path": logo_path}


def merchant_payload(merchant_id=None):
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    return load_merchants().get(mid) or {
        "id": mid,
        "name": DEFAULT_MERCHANT_NAME,
        "logo_path": BRAND_DEFAULT_LOGO,
    }


def sync_merchant_from_settings(settings, merchant_id=None):
    mid = normalize_merchant_id(merchant_id or settings.get("merchant_id") or current_merchant_id())
    name = settings.get("shop_name") or DEFAULT_MERCHANT_NAME
    logo_path = settings.get("brand_logo_path") or BRAND_DEFAULT_LOGO
    return upsert_merchant(mid, name, logo_path)


def _save_merchant_logo_data(merchant_id, data_url, filename="merchant_logo.png"):
    mid = normalize_merchant_id(merchant_id)
    raw = str(data_url or "")
    if not raw:
        return ""
    if "," in raw:
        raw = raw.split(",", 1)[1]
    ext = os.path.splitext(str(filename or ""))[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".ico"):
        ext = ".png"
    dst_dir = os.path.join(ASSETS_DIR, "Brand")
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, f"{mid}_brand_logo{ext}")
    with open(dst, "wb") as f:
        f.write(base64.b64decode(raw))
    return dst


def save_system_merchant(data):
    require_system_admin()
    mid = normalize_merchant_id(data.get("merchant_id"))
    name = str(data.get("merchant_name") or data.get("name") or "").strip() or DEFAULT_MERCHANT_NAME
    logo_path = str(data.get("logo_path") or "").strip()
    if data.get("logo_data_url"):
        logo_path = _save_merchant_logo_data(mid, data.get("logo_data_url"), data.get("logo_filename"))
    merchant = upsert_merchant(mid, name, logo_path)
    settings = load_settings(mid)
    settings["shop_name"] = name
    if logo_path:
        settings["brand_logo_path"] = logo_path
    _write_settings_for_merchant(settings, mid)
    return merchant_payload(mid)


def load_version_info():
    info = dict(DEFAULT_VERSION_INFO)
    if _db_ready():
        try:
            return conlecta_db.load_version(info)
        except Exception as exc:
            log.warning("load_version db failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("version"))
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("version"))
    ws = _get_ws(SHEET_VERSION_CHANGES, VERSION_HEADER)
    if ws is None:
        return info
    try:
        rows = ws.get_all_values()
        if len(rows) <= 1:
            ws.append_row([
                info["version"], info["title"], info["change"],
                info["active"], info["updated_at"],
            ], value_input_option="USER_ENTERED")
            rows = ws.get_all_values()
        selected = None
        fallback = None
        for row in rows[1:]:
            if not any(str(cell).strip() for cell in row):
                continue
            parsed = {
                "version": str(row[0]).strip() if len(row) > 0 else "",
                "title": str(row[1]).strip() if len(row) > 1 else "",
                "change": str(row[2]).strip() if len(row) > 2 else "",
                "active": str(row[3]).strip() if len(row) > 3 else "",
                "updated_at": str(row[4]).strip() if len(row) > 4 else "",
            }
            fallback = parsed
            if _is_admin_flag(parsed.get("active")):
                selected = parsed
        picked = selected or fallback
        if picked:
            info.update({k: v for k, v in picked.items() if v})
        version = str(info.get("version") or "").strip()
        title = str(info.get("title") or "Conlecta Version").strip()
        info["label"] = f"{title} {version}".strip()
        return info
    except Exception as exc:
        log.warning("load_version_info failed: %s", exc)
        return info


def save_version_info(data):
    require_system_admin()
    version = str(data.get("version") or DEFAULT_VERSION_INFO["version"]).strip()
    title = str(data.get("title") or "Conlecta Version").strip()
    change = str(data.get("change") or "").strip()
    updated_at = str(data.get("updated_at") or datetime.now().isoformat(timespec="seconds")).strip()
    if _db_ready():
        try:
            return conlecta_db.save_version({
                "version": version,
                "title": title,
                "change": change,
                "updated_at": updated_at,
            })
        except Exception as exc:
            log.warning("save_version db failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("version")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("version"))
    ws = _get_ws(SHEET_VERSION_CHANGES, VERSION_HEADER)
    if ws is None:
        return {
            "version": version,
            "title": title,
            "change": change,
            "active": "yes",
            "updated_at": updated_at,
            "label": f"{title} {version}".strip(),
        }
    row_out = [version, title, change, "yes", updated_at]
    rows = ws.get_all_values()
    target_row = None
    for row_index, row in enumerate(rows[1:], start=2):
        if len(row) > 3 and _is_admin_flag(row[3]):
            target_row = row_index
            break
    if target_row:
        ws.update([row_out], f"A{target_row}")
    else:
        ws.append_row(row_out, value_input_option="USER_ENTERED")
    return load_version_info()


def system_admin_payload():
    require_system_admin()
    merchants = []
    for merchant in load_merchants().values():
        row = dict(merchant)
        row["logo_url"] = (
            public_asset_url(row.get("logo_path"))
            or row.get("logo_data_url")
            or public_asset_url(BRAND_DEFAULT_LOGO, fallback_logo=True)
        )
        merchants.append(row)
    accounts = load_all_accounts()
    return {
        "merchants": merchants,
        "accounts": accounts,
        "version": load_version_info(),
    }


def _display_event_expired(event):
    if not event:
        return True
    if event.get("requires_ack"):
        return False
    try:
        return time.time() > float(event.get("expires_ts") or 0)
    except Exception:
        return True


def _display_event_payload(kind, source=None):
    source = dict(source or {})
    created = time.time()
    amount = _int_money(source.get("amount"))
    kind = str(kind or "").strip().lower() or "info"
    payment_method = derive_payment_method(
        source.get("payment_method"),
        source.get("cash_received"),
        source.get("change"),
        source.get("qr_id") or source.get("id"),
    )
    cash_received = _int_money(source.get("cash_received"))
    change = max(0, _int_money(source.get("change")))
    if kind == "success":
        title = "Payment Success"
        if payment_method == PAYMENT_METHOD_CASH:
            message = f"Cash payment completed. Change: {change}"
        else:
            message = f"{payment_method} payment completed."
    elif kind == "dismissed":
        title = "QR Dismissed"
        message = "QRIS payment was dismissed by cashier."
    else:
        title = "Display Update"
        message = ""
    requires_ack = kind == "success"
    return {
        "type": kind,
        "title": title,
        "message": message,
        "txn_id": str(source.get("txn_id") or ""),
        "qr_id": str(source.get("qr_id") or source.get("id") or ""),
        "amount": amount,
        "payment_method": payment_method,
        "cash_received": cash_received,
        "change": change,
        "customer_name": str(source.get("customer_name") or source.get("customer") or ""),
        "cashier_name": str(source.get("cashier_name") or ""),
        "items": [],
        "created_ts": created,
        "expires_ts": created + (DISPLAY_SUCCESS_MAX_HOLD_SECONDS if requires_ack else DISPLAY_EVENT_TTL_SECONDS),
        "requires_ack": requires_ack,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _qr_identity_keys(source=None):
    source = source or {}
    keys = []
    qr_id = str(source.get("qr_id") or source.get("id") or "").strip()
    txn_id = str(source.get("txn_id") or source.get("transaction_id") or "").strip()
    if qr_id:
        keys.append(f"qr:{qr_id}")
    if txn_id:
        keys.append(f"txn:{txn_id}")
    return keys


def _float_value(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _prune_closed_qrs(bucket):
    closed = bucket.get("closed_qr_ids")
    if not isinstance(closed, dict):
        closed = {}
        bucket["closed_qr_ids"] = closed
    now = time.time()
    stale = [
        key for key, ts in closed.items()
        if now - _float_value(ts) > CLOSED_QR_TTL_SECONDS
    ]
    for key in stale:
        closed.pop(key, None)
    if len(closed) > 300:
        keep = dict(sorted(closed.items(), key=lambda item: _float_value(item[1]), reverse=True)[:300])
        closed.clear()
        closed.update(keep)
    return closed


def _mark_closed_qr(bucket, source=None):
    keys = _qr_identity_keys(source)
    if not keys:
        return
    closed = _prune_closed_qrs(bucket)
    now = time.time()
    for key in keys:
        closed[key] = now


def _forget_closed_qr(bucket, source=None):
    closed = _prune_closed_qrs(bucket)
    for key in _qr_identity_keys(source):
        closed.pop(key, None)


def _is_closed_qr(bucket, source=None):
    if not source:
        return False
    status = str(source.get("status") or source.get("type") or "").strip().lower()
    if status in {"paid", "success", "succeeded", "settled", "completed", "dismissed", "dismiss", "cancelled", "canceled"}:
        return True
    created_ts = _float_value(source.get("created_ts"))
    if created_ts and time.time() - created_ts > ACTIVE_QR_TTL_SECONDS:
        return True
    closed = _prune_closed_qrs(bucket)
    return any(key in closed for key in _qr_identity_keys(source))


def current_active_qr(state, merchant_id=None):
    mid = normalize_merchant_id(merchant_id)
    bucket = _state_tenant_bucket(state, mid)
    active = bucket.get("active_qr")
    if active and _is_closed_qr(bucket, active):
        _mark_closed_qr(bucket, active)
        bucket["active_qr"] = None
        _sync_legacy_state_for_default(state, mid)
        return None
    return active


def set_display_event(state, merchant_id, kind, source=None):
    mid = normalize_merchant_id(merchant_id)
    bucket = _state_tenant_bucket(state, mid)
    event = _display_event_payload(kind, source)
    event["merchant_id"] = mid
    bucket["display_event"] = event
    if event.get("type") in {"success", "dismissed"}:
        _mark_closed_qr(bucket, event)
        if bucket.get("active_qr") and _is_closed_qr(bucket, bucket.get("active_qr")):
            bucket["active_qr"] = None
    _sync_legacy_state_for_default(state, mid)
    return event


def clear_display_event(state, merchant_id=None, txn_id=None):
    mid = normalize_merchant_id(merchant_id)
    bucket = _state_tenant_bucket(state, mid)
    event = bucket.get("display_event")
    wanted_txn = str(txn_id or "").strip()
    if event and wanted_txn:
        event_txn = str(event.get("txn_id") or event.get("qr_id") or "").strip()
        if event_txn and event_txn != wanted_txn:
            return event
    bucket["display_event"] = None
    _sync_legacy_state_for_default(state, mid)
    return None


def current_display_event(state, merchant_id=None):
    mid = normalize_merchant_id(merchant_id)
    bucket = _state_tenant_bucket(state, mid)
    event = bucket.get("display_event")
    if event and _display_event_expired(event):
        bucket["display_event"] = None
        _sync_legacy_state_for_default(state, mid)
        return None
    return event


def _notice_matches_event(notice=None, event=None):
    notice = notice or {}
    event = event or {}
    notice_txn = str(notice.get("txn_id") or "").strip()
    notice_qr = str(notice.get("qr_id") or notice.get("id") or "").strip()
    event_txn = str(event.get("txn_id") or "").strip()
    event_qr = str(event.get("qr_id") or event.get("id") or "").strip()
    return bool((notice_txn and notice_txn == event_txn) or (notice_qr and notice_qr == event_qr))


def current_cashier_payment_notice(state, merchant_id=None):
    mid = normalize_merchant_id(merchant_id)
    bucket = _state_tenant_bucket(state, mid)
    notice = bucket.get("cashier_payment_notice")
    if not isinstance(notice, dict) or not notice.get("visible"):
        bucket["cashier_payment_notice"] = None
        return None
    if time.time() - _float_value(notice.get("updated_ts")) > CASHIER_NOTICE_STALE_SECONDS:
        bucket["cashier_payment_notice"] = None
        _sync_legacy_state_for_default(state, mid)
        return None
    return notice


def update_cashier_payment_notice(state, merchant_id=None, data=None):
    mid = normalize_merchant_id(merchant_id)
    bucket = _state_tenant_bucket(state, mid)
    data = dict(data or {})
    visible = bool(data.get("visible"))
    txn_id = str(data.get("txn_id") or "").strip()
    qr_id = str(data.get("qr_id") or data.get("id") or "").strip()
    if not visible:
        existing = bucket.get("cashier_payment_notice")
        incoming = {"txn_id": txn_id, "qr_id": qr_id}
        if not isinstance(existing, dict) or not txn_id and not qr_id or _notice_matches_event(incoming, existing):
            bucket["cashier_payment_notice"] = None
        _sync_legacy_state_for_default(state, mid)
        return None
    notice = {
        "visible": True,
        "txn_id": txn_id,
        "qr_id": qr_id,
        "amount": _int_money(data.get("amount")),
        "payment_method": str(data.get("payment_method") or ""),
        "updated_ts": time.time(),
    }
    bucket["cashier_payment_notice"] = notice
    _sync_legacy_state_for_default(state, mid)
    return notice


def display_state_merchant_id(state):
    auth = state.get("auth") or {}
    if auth.get("merchant_id"):
        return normalize_merchant_id(auth.get("merchant_id"))
    tenants = state.get("tenant_data") if isinstance(state.get("tenant_data"), dict) else {}
    for mid, bucket in tenants.items():
        if not isinstance(bucket, dict):
            continue
        if bucket.get("active_qr"):
            return normalize_merchant_id(mid)
        event = bucket.get("display_event")
        if event and not _display_event_expired(event):
            return normalize_merchant_id(mid)
    return DEFAULT_MERCHANT_ID


def _get_local_ip_address():
    return ""


def _get_login_device_id(account_id=""):
    raw = "|".join([
        str(account_id or "").strip().lower(),
        os.environ.get("COMPUTERNAME", "").strip().lower(),
        os.environ.get("USERNAME", os.environ.get("USER", "")).strip().lower(),
        str(uuid.getnode()),
        sys.platform,
    ])
    import hashlib
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32].upper()


def _parse_account_row(row, row_index):
    if len(row) < 4:
        return None
    name = row[1].strip()
    username = row[5].strip() if len(row) > 5 and row[5].strip() else name
    return {
        "row_index": row_index,
        "id": row[0].strip(),
        "name": name,
        "username": username,
        "email": row[2].strip(),
        "password": row[3].strip(),
        "otp": row[4].strip() if len(row) > 4 else "",
        "session": row[6].strip() if len(row) > 6 else "",
        "device_id": row[7].strip() if len(row) > 7 else "",
        "last_ip": row[8].strip() if len(row) > 8 else "",
        "merchant_id": normalize_merchant_id(row[9] if len(row) > 9 else DEFAULT_MERCHANT_ID),
        "admin_account": _is_admin_flag(row[10] if len(row) > 10 else ""),
        "last_activity_ts": row[11].strip() if len(row) > 11 else "",
        "pin": row[12].strip() if len(row) > 12 else "",
    }


def _is_system_admin_account(acc):
    if not acc:
        return False
    return str(acc.get("email") or "").strip().lower() == SYSTEM_ADMIN_EMAIL


def current_auth():
    try:
        return load_state().get("auth") or {}
    except Exception:
        return {}


def current_auth_is_system_admin():
    return bool((current_auth() or {}).get("role") == "system_admin")


def require_system_admin():
    if not current_auth_is_system_admin():
        raise PermissionError("System admin access required.")


def _auth_timestamp(value):
    if value in ("", None):
        return 0.0
    if isinstance(value, (int, float)):
        ts = float(value)
        return ts / 1000 if ts > 100000000000 else ts
    text = str(value).strip()
    try:
        ts = float(text)
        return ts / 1000 if ts > 100000000000 else ts
    except Exception:
        pass
    try:
        return datetime.fromisoformat(text).timestamp()
    except Exception:
        return 0.0


def _activity_sheet_value(ts=None):
    try:
        ts = float(ts if ts is not None else time.time())
    except Exception:
        ts = time.time()
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def _auth_last_activity_ts(auth=None, acc=None):
    acc_ts = _auth_timestamp((acc or {}).get("last_activity_ts"))
    if acc_ts:
        return acc_ts
    auth = auth or {}
    return (
        _auth_timestamp(auth.get("last_activity_ts"))
        or _auth_timestamp(auth.get("login_ts"))
    )


def _client_activity_ts(value):
    now = time.time()
    ts = _auth_timestamp(value)
    if not ts:
        return 0.0
    if ts > now + 60:
        return now
    return ts


def _active_qr_for_auth(state, auth):
    if not auth:
        return None
    mid = normalize_merchant_id(auth.get("merchant_id"))
    active = current_active_qr(state, mid)
    if not active:
        return None
    if normalize_merchant_id(active.get("merchant_id") or mid) != mid:
        return None
    return active


def _logout_auth_from_state(state, auth=None, reason=""):
    auth = auth or (state.get("auth") or {})
    account_id = str(auth.get("id") or "").strip()
    if account_id:
        try:
            acc = _find_account_by_id(account_id)
            if acc:
                _set_account_session(acc["row_index"], SESSION_LOGGED_OUT)
        except Exception as exc:
            log.warning("session logout update failed for %s: %s", account_id, exc)
    state["auth"] = None
    if reason:
        log.info("Web auth cleared: account=%s reason=%s", account_id or "-", reason)


def _clear_local_auth_from_state(state, auth=None, reason=""):
    auth = auth or (state.get("auth") or {})
    account_id = str(auth.get("id") or "").strip()
    state["auth"] = None
    if reason:
        log.info("Web auth cleared locally: account=%s reason=%s", account_id or "-", reason)


def _auth_session_expired(state, auth, acc=None, activity_ts=None):
    if not auth:
        return False
    now = time.time()
    last_activity = _auth_last_activity_ts(auth, acc)
    if not last_activity:
        last_activity = _client_activity_ts(activity_ts)
    if last_activity and now - last_activity > SESSION_IDLE_SECONDS:
        return True
    if str(auth.get("session_day") or "") and str(auth.get("session_day")) != _session_business_day():
        return True
    return False


def validate_stored_auth(state, refresh_seen=False, activity_ts=None):
    auth = state.get("auth") or {}
    if not auth:
        return None
    account_id = str(auth.get("id") or "").strip()
    acc = _find_account_by_id(account_id, unavailable_sentinel=True) if account_id else None
    if acc is _ACCOUNT_LOOKUP_UNAVAILABLE:
        log.warning("Auth validation deferred because account database is unavailable: account=%s", account_id or "-")
        return auth
    if not acc:
        _clear_local_auth_from_state(state, auth, "account_missing")
        return None
    if str(acc.get("session") or "").strip().lower() != SESSION_ACTIVE:
        _clear_local_auth_from_state(state, auth, "db_session_inactive")
        return None
    device_id = str(acc.get("device_id") or "").strip()
    current_device_id = _get_login_device_id(acc.get("id"))
    if device_id and device_id != current_device_id:
        _clear_local_auth_from_state(state, auth, "device_mismatch")
        return None
    if _auth_session_expired(state, auth, acc, activity_ts if refresh_seen else None):
        _logout_auth_from_state(state, auth, "idle_or_daily_timeout")
        return None
    auth["name"] = auth.get("name") or acc.get("name", "")
    auth["username"] = auth.get("username") or acc.get("username", "")
    auth["email"] = auth.get("email") or acc.get("email", "")
    auth["merchant_id"] = normalize_merchant_id(auth.get("merchant_id") or acc.get("merchant_id"))
    auth["admin_account"] = bool(acc.get("admin_account"))
    account_activity = _auth_timestamp(acc.get("last_activity_ts"))
    if account_activity:
        auth["last_activity_ts"] = account_activity
    if refresh_seen:
        now = time.time()
        auth["last_seen_ts"] = now
        incoming_activity = _client_activity_ts(activity_ts)
        if incoming_activity:
            previous_activity = _auth_last_activity_ts(auth, acc)
            if incoming_activity > previous_activity + 0.5:
                auth["last_activity_ts"] = incoming_activity
                try:
                    _set_account_last_activity(acc["row_index"], incoming_activity)
                except Exception as exc:
                    log.warning("last activity update failed for %s: %s", account_id, exc)
        auth["session_day"] = auth.get("session_day") or _session_business_day()
    return auth


def _find_account_by_login(login_id):
    login = str(login_id or "").strip().lower()
    if not login:
        return None
    if _db_ready():
        try:
            return conlecta_db.find_account_by_login(login)
        except Exception as exc:
            log.warning("account login db lookup failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("account")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("account"))
    ws = _get_ws(SHEET_ACCOUNTS, ACCOUNT_HEADER)
    if ws is None:
        return None
    for i, row in enumerate(ws.get_all_values()[1:], start=2):
        acc = _parse_account_row(row, i)
        if not acc:
            continue
        if login in (acc["email"].lower(), acc["username"].lower(), acc["name"].lower()):
            return acc
    return None


def _find_account_by_email(email):
    wanted = str(email or "").strip().lower()
    if not wanted:
        return None
    if _db_ready():
        try:
            return conlecta_db.find_account_by_email(wanted)
        except Exception as exc:
            log.warning("account email db lookup failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("account")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("account"))
    ws = _get_ws(SHEET_ACCOUNTS, ACCOUNT_HEADER)
    if ws is None:
        return None
    for i, row in enumerate(ws.get_all_values()[1:], start=2):
        acc = _parse_account_row(row, i)
        if acc and acc["email"].lower() == wanted:
            return acc
    return None


def _find_account_by_id(account_id, unavailable_sentinel=False):
    aid = str(account_id or "").strip()
    if not aid:
        return None
    if _db_ready():
        try:
            return conlecta_db.find_account_by_id(aid)
        except Exception as exc:
            log.warning("account id db lookup failed for %s: %s", aid, exc)
            if _db_mandatory():
                if unavailable_sentinel:
                    return _ACCOUNT_LOOKUP_UNAVAILABLE
                raise RuntimeError(_db_unavailable_message("account")) from exc
            return _ACCOUNT_LOOKUP_UNAVAILABLE if unavailable_sentinel else None
    if _db_mandatory():
        if unavailable_sentinel:
            return _ACCOUNT_LOOKUP_UNAVAILABLE
        raise RuntimeError(_db_unavailable_message("account"))
    ws = _get_ws(SHEET_ACCOUNTS, ACCOUNT_HEADER)
    if ws is None:
        return _ACCOUNT_LOOKUP_UNAVAILABLE if unavailable_sentinel else None
    try:
        rows = ws.get_all_values()[1:]
    except Exception as exc:
        log.warning("account lookup failed for %s: %s", aid, exc)
        return _ACCOUNT_LOOKUP_UNAVAILABLE if unavailable_sentinel else None
    for i, row in enumerate(rows, start=2):
        acc = _parse_account_row(row, i)
        if acc and acc["id"] == aid:
            return acc
    return None


def _account_conflict_message(account_name, email, exclude_account_id=""):
    username = str(account_name or "").strip().lower()
    wanted_email = str(email or "").strip().lower()
    exclude = str(exclude_account_id or "").strip()
    if _db_ready():
        try:
            return conlecta_db.account_conflict_message(account_name, email, exclude)
        except Exception as exc:
            log.warning("account conflict db check failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("account")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("account"))
    ws = _get_ws(SHEET_ACCOUNTS, ACCOUNT_HEADER)
    if ws is None:
        return ""
    for row in ws.get_all_values()[1:]:
        acc = _parse_account_row(row, 0)
        if not acc or (exclude and acc.get("id") == exclude):
            continue
        if wanted_email and wanted_email == str(acc.get("email") or "").strip().lower():
            return "Email sudah terdaftar."
        existing_names = {
            str(acc.get("name") or "").strip().lower(),
            str(acc.get("username") or "").strip().lower(),
        }
        if username and username in existing_names:
            return "Username / account name sudah terdaftar."
    return ""


def load_all_accounts():
    if _db_ready():
        try:
            accounts = []
            for acc in conlecta_db.load_all_accounts():
                if acc:
                    public = {k: v for k, v in acc.items() if k not in {"password", "pin", "otp"}}
                    public["has_pin"] = bool(acc.get("pin"))
                    public["is_system_admin"] = _is_system_admin_account(acc)
                    accounts.append(public)
            return accounts
        except Exception as exc:
            log.warning("load_all_accounts db failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("account")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("account"))
    ws = _get_ws(SHEET_ACCOUNTS, ACCOUNT_HEADER)
    if ws is None:
        return []
    accounts = []
    try:
        for i, row in enumerate(ws.get_all_values()[1:], start=2):
            acc = _parse_account_row(row, i)
            if acc:
                public = {k: v for k, v in acc.items() if k not in {"password", "pin", "otp"}}
                public["has_pin"] = bool(acc.get("pin"))
                public["is_system_admin"] = _is_system_admin_account(acc)
                accounts.append(public)
    except Exception as exc:
        log.warning("load_all_accounts failed: %s", exc)
    return accounts


def _set_account_otp(row_index, otp_value):
    if _db_ready():
        try:
            conlecta_db.set_account_otp(row_index, otp_value)
            return
        except Exception as exc:
            log.warning("set account otp db failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("account")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("account"))
    ws = _get_ws(SHEET_ACCOUNTS, ACCOUNT_HEADER)
    if ws is not None:
        ws.update_cell(row_index, COL_OTP, otp_value)


def _set_account_session(row_index, session_value, device_id=None, ip_address=None, last_activity_ts=None):
    if _db_ready():
        try:
            conlecta_db.set_account_session(row_index, session_value, device_id, ip_address, last_activity_ts)
            return
        except Exception as exc:
            log.warning("set account session db failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("account")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("account"))
    ws = _get_ws(SHEET_ACCOUNTS, ACCOUNT_HEADER)
    if ws is None:
        return
    ws.update_cell(row_index, COL_SESSION, session_value)
    if device_id is not None:
        ws.update_cell(row_index, COL_DEVICE_ID, device_id)
    if ip_address is not None:
        ws.update_cell(row_index, COL_LAST_IP, ip_address)
    if last_activity_ts is not None:
        ws.update_cell(row_index, COL_LAST_ACTIVITY, _activity_sheet_value(last_activity_ts))


def _set_account_last_activity(row_index, last_activity_ts=None):
    if _db_ready():
        try:
            conlecta_db.set_account_last_activity(row_index, last_activity_ts)
            return
        except Exception as exc:
            log.warning("set account activity db failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("account")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("account"))
    ws = _get_ws(SHEET_ACCOUNTS, ACCOUNT_HEADER)
    if ws is not None:
        ws.update_cell(row_index, COL_LAST_ACTIVITY, _activity_sheet_value(last_activity_ts))


def _set_account_pin(row_index, pin_value=""):
    pin = str(pin_value or "").strip()
    if _db_ready():
        try:
            conlecta_db.set_account_pin(row_index, pin)
            return
        except Exception as exc:
            log.warning("set account pin db failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("account")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("account"))
    ws = _get_ws(SHEET_ACCOUNTS, ACCOUNT_HEADER)
    if ws is not None:
        ws.update_cell(row_index, len(ACCOUNT_HEADER), pin)


def _accounts_for_merchant(merchant_id=None):
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    if _db_ready():
        try:
            return [acc for acc in conlecta_db.accounts_for_merchant(mid) if acc]
        except Exception as exc:
            log.warning("accounts_for_merchant db failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("account")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("account"))
    ws = _get_ws(SHEET_ACCOUNTS, ACCOUNT_HEADER)
    if ws is None:
        return []
    accounts = []
    for i, row in enumerate(ws.get_all_values()[1:], start=2):
        acc = _parse_account_row(row, i)
        if acc and normalize_merchant_id(acc.get("merchant_id")) == mid:
            accounts.append(acc)
    return accounts


def _merchant_admin_account(merchant_id=None):
    accounts = _accounts_for_merchant(merchant_id)
    flagged = [acc for acc in accounts if acc.get("admin_account")]
    return flagged[0] if flagged else (accounts[0] if accounts else None)


def _clear_other_merchant_admins(ws, merchant_id, keep_account_id=""):
    mid = normalize_merchant_id(merchant_id)
    if _db_ready():
        try:
            conlecta_db.clear_other_merchant_admins(mid, keep_account_id)
            return
        except Exception as exc:
            log.warning("clear merchant admin flags db failed for %s: %s", mid, exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("account")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("account"))
    keep = str(keep_account_id or "")
    try:
        for row_index, row in enumerate(ws.get_all_values()[1:], start=2):
            acc = _parse_account_row(row, row_index)
            if not acc:
                continue
            if acc["id"] == keep:
                continue
            if normalize_merchant_id(acc.get("merchant_id")) == mid and acc.get("admin_account"):
                ws.update_cell(row_index, 11, "")
    except Exception as exc:
        log.warning("clear merchant admin flags failed for %s: %s", mid, exc)


def verify_admin_password(password, merchant_id=None):
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    admin = _merchant_admin_account(mid)
    if not admin:
        return False, f"Admin merchant {mid} belum tersedia di database account."
    if str(password or "").strip() != str(admin.get("password") or "").strip():
        return False, "Password admin salah."
    return True, "OK"


def verify_system_log_password(password):
    auth = current_auth()
    account_id = str(auth.get("id") or "").strip()
    if not account_id:
        return False, "Login ulang sebelum membuka log."
    account = _find_account_by_id(account_id)
    if not account:
        return False, "Account login tidak ditemukan."
    if str(password or "").strip() != str(account.get("password") or "").strip():
        return False, "Password account salah."
    return True, "OK"


def create_account_record(account_name, email, password, merchant_id=None, admin_account=False):
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    account_name = str(account_name or "").strip()
    email = str(email or "").strip()
    password = str(password or "").strip()
    if not account_name or not email or not password:
        return False, "Account name, email, dan password wajib diisi."
    if "@" not in email or "." not in email.split("@")[-1]:
        return False, "Format email belum valid."
    if len(password) < 6:
        return False, "Password minimal 6 karakter."
    conflict = _account_conflict_message(account_name, email)
    if conflict:
        return False, conflict
    account_id = generate_account_id()
    if _db_ready():
        try:
            conlecta_db.create_account(account_id, account_name, email, password, mid, admin_account)
            log.info("Account registered in db from web: %s merchant=%s name=%s", account_id, mid, account_name)
            return True, f"Account berhasil dibuat: {account_id}"
        except Exception as exc:
            log.warning("create account db failed: %s", exc)
            if _db_mandatory():
                return False, "Database account tidak tersedia."
    if _db_mandatory():
        return False, "Database account tidak tersedia."
    ws = _get_ws(SHEET_ACCOUNTS, ACCOUNT_HEADER)
    if ws is None:
        return False, "Database account tidak tersedia."
    ws.append_row([
        account_id, account_name, email, password,
        "", account_name, SESSION_LOGGED_OUT, "", "", mid, "yes" if admin_account else "", "",
    ], value_input_option="USER_ENTERED")
    if admin_account:
        _clear_other_merchant_admins(ws, mid, account_id)
    log.info("Account registered from web: %s merchant=%s name=%s", account_id, mid, account_name)
    return True, f"Account berhasil dibuat: {account_id}"


def update_account_record(account_id, account_name=None, email=None, password=None, merchant_id=None, admin_account=None):
    acc = _find_account_by_id(account_id)
    if not acc:
        return False, "Account tidak ditemukan."
    admin_flag = acc.get("admin_account") if admin_account is None else bool(admin_account)
    row = [
        acc["id"],
        str(account_name if account_name is not None else acc["name"]).strip(),
        str(email if email is not None else acc["email"]).strip(),
        str(password if password is not None and str(password).strip() else acc["password"]).strip(),
        acc.get("otp", ""),
        acc.get("username", ""),
        acc.get("session", SESSION_LOGGED_OUT),
        acc.get("device_id", ""),
        acc.get("last_ip", ""),
        normalize_merchant_id(merchant_id if merchant_id is not None else acc.get("merchant_id")),
        "yes" if admin_flag else "",
        acc.get("last_activity_ts", ""),
        acc.get("pin", ""),
    ]
    if not row[1] or not row[2] or not row[3]:
        return False, "Account name, email, dan password wajib diisi."
    if "@" not in row[2] or "." not in row[2].split("@")[-1]:
        return False, "Format email belum valid."
    if password is not None and str(password).strip() and len(str(password).strip()) < 6:
        return False, "Password minimal 6 karakter."
    conflict = _account_conflict_message(row[1], row[2], exclude_account_id=row[0])
    if conflict:
        return False, conflict
    if _db_ready():
        try:
            conlecta_db.update_account(row[0], row[1], row[2], row[3], row[9], admin_flag)
            log.info("System admin updated account in db: %s merchant=%s admin=%s", row[0], row[9], row[10])
            return True, "Account updated."
        except Exception as exc:
            log.warning("update account db failed: %s", exc)
            return False, "Database account tidak tersedia."
    if _db_mandatory():
        return False, "Database account tidak tersedia."
    ws = _get_ws(SHEET_ACCOUNTS, ACCOUNT_HEADER)
    if ws is None:
        return False, "Database account tidak tersedia."
    ws.update([row], f"A{acc['row_index']}")
    if admin_flag:
        _clear_other_merchant_admins(ws, row[9], row[0])
    log.info("System admin updated account: %s merchant=%s admin=%s", row[0], row[9], row[10])
    return True, "Account updated."


def load_email_templates():
    templates = {key: dict(value) for key, value in DEFAULT_EMAIL_TEMPLATES.items()}
    if _db_ready():
        try:
            return conlecta_db.load_email_templates(templates)
        except Exception as exc:
            log.warning("load email templates db failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("template email")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("template email"))
    ws = _get_ws(SHEET_EMAIL_TEMPLATES, EMAIL_TEMPLATE_HEADER)
    if ws is None:
        return templates
    try:
        rows = ws.get_all_values()
        if len(rows) < 2:
            return templates
        headers = [str(h).strip().lower() for h in rows[0]]

        def idx(name):
            for pos, header in enumerate(headers):
                if name in header:
                    return pos
            return -1

        col = {
            "key": idx("key"),
            "subject": idx("subject"),
            "html_override": idx("html override"),
            "primary_color": idx("primary color"),
            "primary_text_color": idx("primary text color"),
            "bg_color": idx("bg color"),
            "secondary_color": idx("secondary color"),
            "logo_path": idx("logo path"),
            "logo_align": idx("logo align"),
        }

        def cell(row, key):
            pos = col.get(key, -1)
            return str(row[pos]).strip() if pos >= 0 and pos < len(row) else ""

        for row in rows[1:]:
            key = cell(row, "key").lower()
            if key not in templates:
                continue
            templates[key]["subject"] = cell(row, "subject") or templates[key]["subject"]
            templates[key]["html_override"] = cell(row, "html_override")
            for field in (
                "primary_color", "primary_text_color", "bg_color",
                "secondary_color", "logo_path", "logo_align",
            ):
                value = cell(row, field)
                if value:
                    templates[key][field] = value
    except Exception as exc:
        log.warning("load_email_templates failed: %s", exc)
    return templates


def save_email_template(key, data):
    key = str(key or "").strip().lower()
    if key not in DEFAULT_EMAIL_TEMPLATES:
        raise ValueError("Template key tidak valid.")
    if _db_ready():
        try:
            conlecta_db.save_email_template(key, data)
            return [
                key,
                str(data.get("subject", "") or ""),
                str(data.get("html_override", "") or ""),
                str(data.get("primary_color", "") or ""),
                str(data.get("primary_text_color", "") or ""),
                str(data.get("bg_color", "") or ""),
                str(data.get("secondary_color", "") or ""),
                str(data.get("logo_path", "") or ""),
                str(data.get("logo_align", "center") or "center"),
            ]
        except Exception as exc:
            log.warning("save email template db failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("template email")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("template email"))
    ws = _get_ws(SHEET_EMAIL_TEMPLATES, EMAIL_TEMPLATE_HEADER)
    if ws is None:
        raise RuntimeError("Database template email tidak tersedia.")
    row_out = [
        key,
        str(data.get("subject", "") or ""),
        str(data.get("html_override", "") or ""),
        str(data.get("primary_color", "") or ""),
        str(data.get("primary_text_color", "") or ""),
        str(data.get("bg_color", "") or ""),
        str(data.get("secondary_color", "") or ""),
        str(data.get("logo_path", "") or ""),
        str(data.get("logo_align", "center") or "center"),
    ]
    rows = ws.get_all_values()
    for row_index, row in enumerate(rows[1:], start=2):
        if row and str(row[0]).strip().lower() == key:
            ws.update([row_out], f"A{row_index}")
            return row_out
    ws.append_row(row_out, value_input_option="USER_ENTERED")
    return row_out


def _load_gmail_credentials():
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except Exception:
        return None
    scopes = ["https://www.googleapis.com/auth/gmail.send"]
    for path in (GMAIL_TOKEN_FILE, OAUTH_TOKEN_FILE):
        if not os.path.isfile(path):
            continue
        try:
            creds = Credentials.from_authorized_user_file(path, scopes)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(path, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
            if creds and creds.valid:
                return creds
        except Exception as exc:
            log.warning("Gmail token skipped %s: %s", path, exc)
    return None


def _fill_email_placeholders(text, values, escape_html=False):
    out = str(text or "")
    for key, value in values.items():
        replacement = str(value or "")
        if escape_html:
            replacement = html.escape(replacement)
        out = out.replace("{" + key + "}", replacement)
    return out


def _template_color(tpl, key, fallback):
    value = str((tpl or {}).get(key) or fallback or "").strip()
    return value or fallback


def _template_logo_path(tpl):
    logo_path = str((tpl or {}).get("logo_path") or BRAND_DEFAULT_LOGO or "").strip()
    if logo_path and logo_path.startswith("/assets/"):
        logo_path = os.path.join(BASE_DIR, logo_path.lstrip("/").replace("/", os.sep))
    if logo_path and not os.path.isabs(logo_path):
        logo_path = os.path.join(BASE_DIR, logo_path)
    return logo_path if logo_path and os.path.isfile(logo_path) else ""


def _otp_display_name(account_name="", username=""):
    name = str(account_name or "").strip()
    if not name or name.startswith("@"):
        name = str(username or "").strip()
    name = name.lstrip("@").strip()
    return name or "User"


def _build_otp_html(otp_code, name, tpl, logo_path=""):
    primary = _template_color(tpl, "primary_color", "#22d3c5")
    secondary = _template_color(tpl, "secondary_color", "#7c3aed")
    bg = _template_color(tpl, "bg_color", "#0f172a")
    safe_name = html.escape(str(name or "User"))
    safe_otp = html.escape(str(otp_code or ""))
    logo_html = (
        '<img src="cid:otp_logo" width="122" height="122" '
        'style="display:block;width:122px;height:122px;object-fit:cover;border-radius:14px;'
        'margin:0 auto 28px;border:1px solid rgba(255,255,255,.16);" alt="Conlecta POS">'
        if logo_path else ""
    )
    return f"""<!doctype html>
<html>
<body style="margin:0;padding:0;background:{bg};font-family:Segoe UI,Arial,sans-serif;color:#e5edf7;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{bg};padding:42px 18px;">
    <tr>
      <td align="center">
        <table role="presentation" width="662" cellpadding="0" cellspacing="0" style="width:100%;max-width:662px;border-collapse:separate;border-spacing:0;background:#1a2433;border:1px solid #2b3950;border-radius:20px;overflow:hidden;">
          <tr>
            <td style="height:5px;background:linear-gradient(90deg,{primary},#3b82f6,{secondary});font-size:0;line-height:0;">&nbsp;</td>
          </tr>
          <tr>
            <td align="center" style="padding:47px 40px 38px;">
              {logo_html}
              <h1 style="margin:0 0 17px;color:#f6f8fb;font-size:29px;line-height:1.2;font-weight:800;text-align:center;">Verifikasi Login</h1>
              <p style="margin:0;color:#94a3b8;font-size:17px;line-height:1.55;text-align:center;">
                Halo <strong style="color:#f6f8fb;">{safe_name}</strong>
              </p>
              <p style="margin:2px 0 30px;color:#94a3b8;font-size:17px;line-height:1.55;text-align:center;">
                Gunakan kode OTP berikut untuk masuk ke Conlecta POS.
              </p>
              <div style="border:1px solid {primary};border-radius:14px;background:#0b111a;padding:29px 20px 34px;text-align:center;">
                <div style="color:#64748b;font-size:12px;letter-spacing:6px;font-weight:800;margin-bottom:22px;">KODE OTP &bull; BERLAKU 60 DETIK</div>
                <div style="color:{primary};font-size:44px;letter-spacing:14px;font-weight:900;line-height:1;font-family:Segoe UI,Arial,sans-serif;">{safe_otp}</div>
              </div>
              <p style="margin:36px 0 4px;color:#64748b;font-size:14px;line-height:1.55;text-align:center;">Jangan bagikan kode ini kepada siapapun.</p>
              <p style="margin:0;color:#64748b;font-size:14px;line-height:1.55;text-align:center;">Jika Anda tidak meminta kode ini, abaikan email ini.</p>
            </td>
          </tr>
          <tr>
            <td align="center" style="border-top:1px solid #2b3950;padding:26px 20px;color:#475569;font-size:13px;">&copy; Conlecta POS &middot; Secure login</td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _send_otp_email(to_email, otp_code, account_name, username=""):
    creds = _load_gmail_credentials()
    if creds is None:
        raise RuntimeError("Gmail token tidak tersedia untuk kirim OTP.")
    try:
        from googleapiclient.discovery import build
    except Exception as exc:
        raise RuntimeError(f"googleapiclient unavailable: {exc}")

    name = _otp_display_name(account_name, username)
    uname = str(username or "").strip().lstrip("@")
    username_label = ""
    tpl = load_email_templates().get("otp", {})
    values = {
        "account_name": name,
        "name": name,
        "username": uname,
        "username_label": username_label,
        "email": to_email,
        "otp": otp_code,
        "otp_code": otp_code,
    }
    subject = f"Conlecta POS - OTP untuk {name}"
    logo_path = _template_logo_path(tpl)
    html_body = _build_otp_html(otp_code, name, tpl, logo_path)

    msg = MIMEMultipart("related")
    msg["to"] = to_email
    msg["from"] = "Conlecta Indonesia <conlecta.indonesia@gmail.com>"
    msg["subject"] = subject
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(f"Halo {name}, kode OTP login Conlecta POS Anda: {otp_code}\n\nBerlaku 60 detik.", "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)
    if logo_path:
        try:
            with open(logo_path, "rb") as f:
                img = MIMEImage(f.read())
            img.add_header("Content-ID", "<otp_logo>")
            img.add_header("Content-Disposition", "inline", filename=os.path.basename(logo_path))
            msg.attach(img)
        except Exception as exc:
            log.debug("OTP logo skipped %s: %s", logo_path, exc)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    service = build("gmail", "v1", credentials=creds)
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    log.info("OTP sent from web to %s", to_email)


def _pending_otp_payload(acc, meta):
    now = time.time()
    expires_in = max(0, int(float(meta.get("expires_ts", now)) - now))
    resend_cooldown = max(0, int(float(meta.get("can_resend_at", now)) - now))
    resend_count = _int_money(meta.get("resend_count"))
    return {
        "account_id": acc["id"],
        "account_name": acc["name"],
        "username": acc["username"],
        "email": acc["email"],
        "mode": "otp",
        "purpose": str(meta.get("purpose") or "login"),
        "expires_in": expires_in,
        "resend_cooldown": resend_cooldown,
        "resend_remaining": max(0, OTP_MAX_RESENDS - resend_count),
    }


def _store_pending_otp(acc, otp_code, resend_count=0, purpose="login"):
    now = time.time()
    state = load_state()
    pending = state.get("pending_otps") or {}
    meta = {
        "code": otp_code,
        "purpose": str(purpose or "login"),
        "created_ts": now,
        "expires_ts": now + OTP_TTL_SECONDS,
        "last_sent_ts": now,
        "can_resend_at": now + OTP_RESEND_COOLDOWN_SECONDS,
        "resend_count": resend_count,
    }
    pending[acc["id"]] = meta
    state["pending_otps"] = pending
    save_state(state)
    _set_account_otp(acc["row_index"], otp_code)
    return _pending_otp_payload(acc, meta)


def _pending_auth_payload(acc, mode, meta=None):
    meta = meta or {}
    now = time.time()
    return {
        "account_id": acc["id"],
        "account_name": acc["name"],
        "username": acc["username"],
        "email": acc["email"],
        "mode": mode,
        "expires_in": max(0, int(float(meta.get("expires_ts", now + PENDING_AUTH_TTL_SECONDS)) - now)),
        "has_pin": bool(acc.get("pin")),
    }


def _store_pending_auth(acc, mode):
    now = time.time()
    state = load_state()
    pending = state.get("pending_auth") or {}
    meta = {
        "account_id": acc["id"],
        "mode": mode,
        "created_ts": now,
        "expires_ts": now + PENDING_AUTH_TTL_SECONDS,
    }
    pending[acc["id"]] = meta
    state["pending_auth"] = pending
    save_state(state)
    return _pending_auth_payload(acc, mode, meta)


def _get_pending_auth(account_id, mode=None):
    acc = _find_account_by_id(account_id)
    if not acc:
        raise RuntimeError("Akun tidak ditemukan.")
    state = load_state()
    pending = state.get("pending_auth") or {}
    meta = pending.get(acc["id"])
    if not meta:
        raise RuntimeError("Session login sudah tidak aktif. Login ulang.")
    if time.time() > float(meta.get("expires_ts") or 0):
        pending.pop(acc["id"], None)
        state["pending_auth"] = pending
        save_state(state)
        raise RuntimeError("Session login expired. Login ulang.")
    if mode and str(meta.get("mode") or "") != mode:
        raise RuntimeError("Flow login tidak sesuai. Login ulang.")
    return acc, meta


def _clear_pending_auth(account_id):
    state = load_state()
    pending = state.get("pending_auth") or {}
    pending.pop(str(account_id or ""), None)
    state["pending_auth"] = pending
    save_state(state)


def _clear_pending_otp(account_id, row_index=None):
    state = load_state()
    pending = state.get("pending_otps") or {}
    pending.pop(str(account_id or ""), None)
    state["pending_otps"] = pending
    save_state(state)
    if row_index:
        _set_account_otp(row_index, "")


def _complete_login(acc):
    _clear_pending_auth(acc["id"])
    _clear_pending_otp(acc["id"], acc.get("row_index"))
    device_id = _get_login_device_id(acc["id"])
    now_ts = time.time()
    _set_account_session(acc["row_index"], SESSION_ACTIVE, device_id, _get_local_ip_address(), now_ts)
    merchant_id = normalize_merchant_id(acc.get("merchant_id"))
    is_system_admin = _is_system_admin_account(acc)
    if not is_system_admin:
        settings = load_settings(merchant_id)
        settings["saved_cashier_account_id"] = acc["id"]
        settings["account_id"] = acc["id"]
        save_settings(settings, merchant_id)
    merchant = merchant_payload(merchant_id)
    auth = {
        "id": acc["id"],
        "name": acc["name"],
        "username": acc["username"],
        "email": acc["email"],
        "role": "system_admin" if is_system_admin else "cashier",
        "merchant_id": merchant_id,
        "merchant_name": merchant.get("name") or DEFAULT_MERCHANT_NAME,
        "admin_account": bool(acc.get("admin_account")),
        "login_ts": datetime.now().isoformat(timespec="seconds"),
        "log_start_ts": now_ts,
        "last_activity_ts": now_ts,
        "last_seen_ts": now_ts,
        "session_day": _session_business_day(),
    }
    state = load_state()
    state["auth"] = auth
    save_state(state)
    log.info("Web login complete: account=%s merchant=%s", acc["id"], merchant_id)
    return auth


def begin_login(login_id, password):
    acc = _find_account_by_login(login_id)
    if not acc:
        raise RuntimeError("Email/username tidak ditemukan.")
    if acc["password"] != str(password or ""):
        raise RuntimeError("Password salah.")
    mode = "pin" if str(acc.get("pin") or "").strip() else "register_pin"
    return _store_pending_auth(acc, mode)


def begin_forgot_pin(account_id):
    acc, _meta = _get_pending_auth(account_id, "pin")
    otp_code = str(random.randint(100000, 999999))
    _send_otp_email(acc["email"], otp_code, acc["name"], acc["username"])
    return _store_pending_otp(acc, otp_code, resend_count=0, purpose="forgot_pin")


def resend_login_otp(account_id):
    acc = _find_account_by_id(account_id)
    if not acc:
        raise RuntimeError("Akun tidak ditemukan.")
    state = load_state()
    pending = state.get("pending_otps") or {}
    meta = pending.get(acc["id"])
    if not meta:
        raise RuntimeError("OTP sudah tidak aktif. Login ulang.")
    now = time.time()
    resend_count = _int_money(meta.get("resend_count"))
    if resend_count >= OTP_MAX_RESENDS:
        raise RuntimeError("Resend OTP sudah dipakai.")
    cooldown = float(meta.get("can_resend_at", now)) - now
    if cooldown > 0:
        raise RuntimeError(f"Tunggu {max(1, int(cooldown))} detik sebelum resend OTP.")
    otp_code = str(random.randint(100000, 999999))
    _send_otp_email(acc["email"], otp_code, acc["name"], acc["username"])
    return _store_pending_otp(acc, otp_code, resend_count=resend_count + 1, purpose=meta.get("purpose") or "login")


def verify_login_pin(account_id, pin_value):
    acc, _meta = _get_pending_auth(account_id, "pin")
    pin = str(pin_value or "").strip()
    if not pin.isdigit() or len(pin) != 6:
        raise RuntimeError("PIN wajib 6 angka.")
    if pin != str(acc.get("pin") or "").strip():
        raise RuntimeError("PIN salah.")
    return _complete_login(acc)


def register_login_pin(account_id, pin_value, confirm_pin):
    acc, _meta = _get_pending_auth(account_id, "register_pin")
    pin = str(pin_value or "").strip()
    confirm = str(confirm_pin or "").strip()
    if not pin.isdigit() or len(pin) != 6:
        raise RuntimeError("PIN wajib 6 angka.")
    if pin != confirm:
        raise RuntimeError("Konfirmasi PIN tidak sama.")
    _set_account_pin(acc["row_index"], pin)
    acc["pin"] = pin
    return _complete_login(acc)


def verify_login_otp(account_id, otp):
    acc = _find_account_by_id(account_id)
    if not acc:
        raise RuntimeError("Akun tidak ditemukan.")
    state = load_state()
    pending = state.get("pending_otps") or {}
    meta = pending.get(acc["id"])
    now = time.time()
    if not meta:
        _set_account_otp(acc["row_index"], "")
        raise RuntimeError("OTP sudah tidak aktif. Login ulang.")
    if now > float(meta.get("expires_ts", 0)):
        _set_account_otp(acc["row_index"], "")
        raise RuntimeError("OTP sudah expired. Silakan resend OTP.")
    expected = str(meta.get("code") or acc.get("otp") or "")
    if not expected or expected != str(otp or "").strip():
        raise RuntimeError("Kode OTP salah atau kadaluarsa.")
    purpose = str(meta.get("purpose") or "login")
    _clear_pending_otp(acc["id"], acc["row_index"])
    if purpose == "forgot_pin":
        _set_account_pin(acc["row_index"], "")
        acc["pin"] = ""
        return {"pending": _store_pending_auth(acc, "register_pin")}
    return {"auth": _complete_login(acc)}


def logout_current_account():
    state = load_state()
    _logout_auth_from_state(state, reason="logout")
    save_state(state)


def exit_current_account_locally():
    state = load_state()
    state["auth"] = None
    save_state(state)


def parse_stock_rows(rows):
    products = []
    headers = _header_map([str(h).strip() for h in (rows[0] if rows else STOCK_HEADERS)])
    for row in rows[1:]:
        name = str(_cell(row, headers, "Item Name", 1)).strip()
        if not name:
            continue
        products.append({
            "name": name,
            "price": _int_money(_cell(row, headers, "Price", 2)),
            "capital": _int_money(_cell_any(row, headers, (
                "Capital", "Modal", "Harga Beli", "Harga Beli / Modal",
                "Harga Modal", "Cost", "Buy Price",
            ), None, 0)),
            "stock": _int_money(_cell(row, headers, "Stock", 3)),
            "vendor_id": str(_cell(row, headers, "Vendor ID", 4)).strip(),
            "image_b64": str(_cell(row, headers, "Image_Base64", 5)).strip(),
            "merchant_id": normalize_merchant_id(_cell(row, headers, "Merchant ID", None, DEFAULT_MERCHANT_ID)),
        })
    return products


def stock_row_values(idx, item, fallback_merchant_id=None):
    return [
        idx,
        str(item.get("name", "") or "").strip(),
        _int_money(item.get("price")),
        _int_money(item.get("capital") or item.get("cost") or item.get("buy_price")),
        _int_money(item.get("stock")),
        str(item.get("vendor_id", "") or ""),
        str(item.get("image_b64", "") or ""),
        normalize_merchant_id(item.get("merchant_id") or fallback_merchant_id or DEFAULT_MERCHANT_ID),
    ]


def ensure_stock_sheet_headers(ws):
    rows = ws.get_all_values()
    current = [str(h).strip() for h in (rows[0] if rows else [])]
    if not current:
        ws.update([STOCK_HEADERS], "A1")
        return list(STOCK_HEADERS)
    if current == STOCK_HEADERS:
        return current

    parsed = parse_stock_rows(rows)
    if len(rows) > 1 and not parsed:
        log.warning("Stock sheet schema migration skipped because existing rows could not be parsed.")
        return _sheet_headers(ws, STOCK_HEADERS)

    migrated = [STOCK_HEADERS]
    for idx, item in enumerate(parsed, start=1):
        migrated.append(stock_row_values(idx, item, item.get("merchant_id")))
    ws.clear()
    ws.update(migrated, "A1", value_input_option="USER_ENTERED")
    return list(STOCK_HEADERS)


def load_stock(force=False, merchant_id=None):
    global _stock_cache, _stock_cache_ts
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    now = time.time()
    if not force and isinstance(_stock_cache, dict) and mid in _stock_cache and (now - _stock_cache_ts) < 20:
        return _stock_cache[mid]
    state = load_state()
    bucket = _state_tenant_bucket(state, mid)
    if _db_ready():
        try:
            products = conlecta_db.load_stock(mid)
            if not isinstance(_stock_cache, dict):
                _stock_cache = {}
            _stock_cache[mid] = products
            _stock_cache_ts = now
            bucket["products"] = products
            _sync_legacy_state_for_default(state, mid)
            save_state(state)
            return products
        except Exception as exc:
            log.warning("load_stock db failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("stock")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("stock"))
    spreadsheet = get_spreadsheet()
    if spreadsheet:
        try:
            ws = ensure_ws(spreadsheet, SHEET_STOCK, STOCK_HEADERS)
            if not ws:
                raise RuntimeError("Stock worksheet tidak tersedia.")
            ensure_stock_sheet_headers(ws)
            rows = ws.get_all_values()
            parsed = parse_stock_rows(rows) if len(rows) > 1 else []
            filtered = [item for item in parsed if normalize_merchant_id(item.get("merchant_id")) == mid]
            if not filtered and (bucket.get("products") or []):
                log.warning("load_stock returned empty for merchant=%s; preserving local products to avoid accidental catalog wipe.", mid)
                return bucket.get("products") or []
            if not isinstance(_stock_cache, dict):
                _stock_cache = {}
            _stock_cache[mid] = filtered
            _stock_cache_ts = now
            bucket["products"] = filtered
            _sync_legacy_state_for_default(state, mid)
            save_state(state)
            return filtered
        except Exception as exc:
            log.warning("load_stock data sync failed: %s", exc)
    products = bucket.get("products") or (list(SAMPLE_PRODUCTS) if mid == DEFAULT_MERCHANT_ID else [])
    if not isinstance(_stock_cache, dict):
        _stock_cache = {}
    _stock_cache[mid] = products
    _stock_cache_ts = now
    return products


def save_stock(products, merchant_id=None):
    global _stock_cache, _stock_cache_ts
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    clean = []
    for item in products or []:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        clean.append({
            "name": name,
            "price": _int_money(item.get("price")),
            "capital": _int_money(item.get("capital") or item.get("cost") or item.get("buy_price")),
            "stock": _int_money(item.get("stock")),
            "vendor_id": str(item.get("vendor_id", "") or ""),
            "image_b64": str(item.get("image_b64", "") or ""),
            "merchant_id": mid,
        })
    if _db_ready():
        try:
            clean = conlecta_db.save_stock(clean, mid)
            state = load_state()
            bucket = _state_tenant_bucket(state, mid)
            bucket["products"] = clean
            _sync_legacy_state_for_default(state, mid)
            save_state(state)
            if not isinstance(_stock_cache, dict):
                _stock_cache = {}
            _stock_cache[mid] = clean
            _stock_cache_ts = time.time()
            return clean
        except Exception as exc:
            log.warning("save_stock db failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("stock")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("stock"))
    spreadsheet = get_spreadsheet()
    if spreadsheet:
        try:
            ws = ensure_ws(spreadsheet, SHEET_STOCK, STOCK_HEADERS)
            if not ws:
                raise RuntimeError("Stock worksheet tidak tersedia.")
            ensure_stock_sheet_headers(ws)
            existing = parse_stock_rows(ws.get_all_values())
            existing_current = [item for item in existing if normalize_merchant_id(item.get("merchant_id")) == mid]
            if not clean and existing_current:
                log.warning("save_stock blocked empty overwrite for merchant=%s; preserving existing sheet stock.", mid)
                return existing_current
            others = [item for item in existing if normalize_merchant_id(item.get("merchant_id")) != mid]
            rows = [STOCK_HEADERS]
            for idx, item in enumerate(others + clean, start=1):
                rows.append(stock_row_values(idx, item, mid))
            ws.clear()
            ws.update(rows, "A1", value_input_option="USER_ENTERED")
        except Exception as exc:
            log.warning("save_stock data sync failed: %s", exc)
    state = load_state()
    bucket = _state_tenant_bucket(state, mid)
    if not clean and (bucket.get("products") or []):
        log.warning("save_stock blocked empty local overwrite for merchant=%s; preserving current stock.", mid)
        return bucket.get("products") or []
    bucket["products"] = clean
    _sync_legacy_state_for_default(state, mid)
    save_state(state)
    if not isinstance(_stock_cache, dict):
        _stock_cache = {}
    _stock_cache[mid] = clean
    _stock_cache_ts = time.time()
    return clean


def sync_stock_delta_to_sheets(products, changed_names, merchant_id=None):
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    names = {str(name or "").strip().lower() for name in (changed_names or []) if str(name or "").strip()}
    if not names:
        return
    if _db_ready():
        try:
            conlecta_db.sync_stock_delta(products, changed_names, mid)
            return
        except Exception as exc:
            log.warning("stock delta db sync failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("stock")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("stock"))
    spreadsheet = get_spreadsheet()
    if not spreadsheet:
        return
    try:
        ws = ensure_ws(spreadsheet, SHEET_STOCK, STOCK_HEADERS)
        if not ws:
            return
        headers = _sheet_headers(ws, STOCK_HEADERS)
        header_map = _header_map(headers)
        rows = ws.get_all_values()
        existing_by_name = {}
        for row_index, row in enumerate(rows[1:], start=2):
            row_mid = normalize_merchant_id(_cell(row, header_map, "Merchant ID", 6, DEFAULT_MERCHANT_ID))
            if row_mid != mid:
                continue
            name = str(_cell(row, header_map, "Item Name", 1)).strip()
            if name:
                existing_by_name[name.lower()] = (row_index, row)

        append_rows = []
        next_no = len(rows)
        for item in products or []:
            name = str(item.get("name", "")).strip()
            if not name or name.lower() not in names:
                continue
            existing = existing_by_name.get(name.lower())
            values = {
                "No": _cell(existing[1], header_map, "No", 0, next_no) if existing else next_no,
                "Item Name": name,
                "Price": _int_money(item.get("price")),
                "Capital": _int_money(item.get("capital") or item.get("cost") or item.get("buy_price")),
                "Stock": _int_money(item.get("stock")),
                "Vendor ID": str(item.get("vendor_id", "") or ""),
                "Image_Base64": str(item.get("image_b64", "") or ""),
                "Merchant ID": mid,
            }
            if existing:
                ws.update([_row_from_mapping(headers, values)], f"A{existing[0]}", value_input_option="USER_ENTERED")
            else:
                append_rows.append(_row_from_mapping(headers, values))
                next_no += 1
        if append_rows:
            ws.append_rows(append_rows, value_input_option="USER_ENTERED")
    except Exception as exc:
        log.warning("stock delta sync failed: %s", exc)


def load_vendors(force=False, merchant_id=None):
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    if _db_ready():
        try:
            return conlecta_db.load_vendors(mid)
        except Exception as exc:
            log.warning("load_vendors db failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("vendor")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("vendor"))
    ws = _get_ws(SHEET_VENDORS, VENDOR_HEADER)
    if ws is None:
        return []
    try:
        result = []
        for row in ws.get_all_values()[1:]:
            if len(row) >= 2 and str(row[0]).strip():
                row_mid = normalize_merchant_id(row[2] if len(row) > 2 else DEFAULT_MERCHANT_ID)
                if row_mid == mid:
                    result.append({"id": str(row[0]).strip(), "name": str(row[1]).strip(), "merchant_id": row_mid})
        return result
    except Exception as exc:
        log.warning("load_vendors failed: %s", exc)
        return []


def save_vendor(name, merchant_id=None):
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    name = str(name or "").strip()
    if not name:
        raise ValueError("Vendor name kosong.")
    if _db_ready():
        try:
            vendor = conlecta_db.save_vendor(name, mid)
            log.info("Vendor saved in db from web: %s merchant=%s %s", vendor.get("id"), mid, name)
            return vendor
        except Exception as exc:
            log.warning("save_vendor db failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("vendor")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("vendor"))
    ws = _get_ws(SHEET_VENDORS, VENDOR_HEADER)
    if ws is None:
        raise RuntimeError("Database vendor tidak tersedia.")
    rows = ws.get_all_values()
    for row in rows[1:]:
        row_mid = normalize_merchant_id(row[2] if len(row) > 2 else DEFAULT_MERCHANT_ID)
        if row_mid == mid and len(row) >= 2 and str(row[1]).strip().lower() == name.lower():
            return {"id": str(row[0]).strip(), "name": str(row[1]).strip(), "merchant_id": row_mid}
    next_id = str(len(rows))
    ws.append_row([next_id, name, mid], value_input_option="USER_ENTERED")
    log.info("Vendor saved from web: %s merchant=%s %s", next_id, mid, name)
    return {"id": next_id, "name": name, "merchant_id": mid}


def delete_vendor(vendor_id, merchant_id=None):
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    vendor_id = str(vendor_id or "").strip()
    if not vendor_id:
        raise ValueError("Vendor ID kosong.")
    if _db_ready():
        try:
            deleted = conlecta_db.delete_vendor(vendor_id, mid)
            if deleted:
                log.info("Vendor deleted from db: %s", vendor_id)
            return deleted
        except Exception as exc:
            log.warning("delete_vendor db failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("vendor")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("vendor"))
    ws = _get_ws(SHEET_VENDORS, VENDOR_HEADER)
    if ws is None:
        raise RuntimeError("Database vendor tidak tersedia.")
    rows = ws.get_all_values()
    for idx in range(len(rows), 1, -1):
        row = rows[idx - 1]
        row_mid = normalize_merchant_id(row[2] if len(row) > 2 else DEFAULT_MERCHANT_ID)
        if row and str(row[0]).strip() == vendor_id and row_mid == mid:
            ws.delete_rows(idx)
            log.info("Vendor deleted from web: %s", vendor_id)
            return True
    return False


def make_qr_data_uri(data):
    if not qrcode:
        return ""
    img = qrcode.make(str(data or "CONLECTA"))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _json_response_or_raw(response):
    try:
        return response.json()
    except Exception:
        return {"status": response.status_code, "raw": response.text}


def _extract_qris_payload(data):
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        return data["data"]
    return data if isinstance(data, dict) else {}


def _qris_status_text(qris):
    if not isinstance(qris, dict):
        return ""
    for key in ("status", "payment_status", "transaction_status", "state"):
        value = qris.get(key)
        if value is not None:
            return str(value)
    return ""


def generate_qris(payload):
    if not requests:
        raise RuntimeError("requests package is unavailable")
    amount = _int_money(payload.get("amount"))
    if amount <= 0:
        raise ValueError("Amount must be greater than 0")
    expired_min = _int_money(payload.get("expired_min"), 30) or 30
    expired_at = (datetime.now() + timedelta(minutes=expired_min)).strftime("%Y-%m-%d %H:%M:%S")
    txn_id = str(payload.get("txn_id") or generate_txn_id())
    body = {
        "amount": amount,
        "expired_at": expired_at,
        "merchant_reff_no": txn_id,
    }
    log.info("Generate QRIS via VPS: POST %s amount=%s", VPS_QRIS_GENERATE_URL, amount)
    response = requests.post(VPS_QRIS_GENERATE_URL, json=body, timeout=30)
    data = _json_response_or_raw(response)
    if not response.ok:
        raise RuntimeError(str(data)[:400])
    qris = _extract_qris_payload(data)
    if not qris:
        raise RuntimeError(str(data)[:400])
    qris_id = str(qris.get("id") or qris.get("qris_id") or txn_id)
    qr_data = str(qris.get("qr_data") or qris.get("qrData") or qris_id)
    return {
        "mode": "vps",
        "id": qris_id,
        "txn_id": txn_id,
        "qr_data": qr_data,
        "qr_image": make_qr_data_uri(qr_data),
        "status": str(qris.get("status") or "PENDING"),
        "message": "QRIS generated via VPS",
        "raw": qris,
    }


def fetch_qris_status(qris_id, timeout=12):
    if not requests:
        raise RuntimeError("requests package is unavailable")
    qris_id = str(qris_id or "").strip()
    if not qris_id:
        return {"status": "NONE", "active_qr": None}
    show_url = f"{VPS_QRIS_SHOW_URL}/{quote(qris_id, safe='')}"
    log.debug("POLL via VPS: GET %s", show_url)
    response = requests.get(show_url, timeout=timeout)
    data = _json_response_or_raw(response)
    if not response.ok:
        raise RuntimeError(str(data)[:400])
    return data


def qris_proxy_environment(timeout=5):
    if not requests:
        return "Unknown", "requests package unavailable"
    for path in ("/env", "/qris/env", "/qris/config", "/config", "/", "/openapi.json"):
        try:
            response = requests.get(f"{VPS_QRIS_BASE_URL}{path}", timeout=timeout)
            if not response.ok:
                continue
            try:
                payload = response.json()
            except Exception:
                payload = response.text
            text = json.dumps(payload, ensure_ascii=False).lower() if isinstance(payload, dict) else str(payload).lower()
            env = ""
            if isinstance(payload, dict):
                raw = str(payload.get("environment") or payload.get("env") or "").lower()
                if raw == "sandbox":
                    env = "Sandbox"
                elif raw in ("production", "prod"):
                    env = "Production"
            if not env:
                if "sandbox" in text:
                    env = "Sandbox"
                elif "production" in text or "payment-b2b.singapay.id" in text or "payment.singapay.id" in text:
                    env = "Production"
            if env:
                hidden = isinstance(payload, dict) and payload.get("base_url_type") == "hidden"
                detail = f"Detected from VPS metadata ({path})"
                if hidden:
                    detail += "; SingaPay base_url hidden."
                else:
                    detail += "."
                return env, detail
        except Exception as exc:
            log.debug("QRIS env check %s: %s", path, exc)
    return "Unknown", "VPS belum expose /env atau environment belum terbaca."


def normalize_items(items, payment_method, cash_received=0, change=0):
    clean = []
    for item in items or []:
        name = str(item.get("name") or item.get("item_name") or "").strip()
        qty = _int_money(item.get("qty"))
        unit_price = _int_money(item.get("unit_price") or item.get("price") or item.get("amount"))
        price = _int_money(item.get("amount") or unit_price)
        capital = _int_money(item.get("capital") or item.get("cost") or item.get("buy_price"))
        free = bool(item.get("free"))
        if not name or qty <= 0:
            continue
        gross = _int_money(item.get("gross")) or unit_price * qty
        disc_pct = max(0, min(100, _int_money(item.get("disc_pct"))))
        disc_fixed = max(0, _int_money(item.get("disc_fixed")))
        computed_pct_discount = round(gross * disc_pct / 100) if disc_pct else 0
        computed_discount = min(gross, computed_pct_discount + disc_fixed)
        line_discount = _int_money(item.get("line_discount")) or computed_discount
        line_discount = max(0, min(gross, line_discount))
        if free:
            line_discount = gross
            subtotal = 0
            price = 0
        else:
            subtotal = _int_money(item.get("subtotal"))
            if subtotal <= 0 and gross:
                subtotal = max(0, gross - line_discount)
            if gross and subtotal <= 0 and line_discount >= gross:
                free = True
                price = 0
        clean.append({
            "item_name": name,
            "name": name,
            "qty": qty,
            "amount": price,
            "price": price,
            "unit_price": unit_price,
            "capital": capital,
            "cost": capital,
            "gross": gross,
            "subtotal": subtotal,
            "payment_fee": _int_money(item.get("payment_fee")),
            "total_cost": _int_money(item.get("total_cost")) or (capital * qty),
            "profit": subtotal - ((capital * qty) + _int_money(item.get("payment_fee"))),
            "free": free,
            "disc_pct": disc_pct,
            "disc_fixed": disc_fixed,
            "line_discount": line_discount,
            "payment_method": payment_method,
            "cash_received": cash_received,
            "change": change,
        })
    return clean


def apply_payment_fee_to_items(items, payment_method, amount):
    fee_total = calc_qris_fee(amount) if payment_method == PAYMENT_METHOD_QRIS else 0
    subtotal_total = sum(_int_money(item.get("subtotal")) for item in items)
    remaining_fee = fee_total
    for index, item in enumerate(items):
        subtotal = _int_money(item.get("subtotal"))
        capital_cost = _int_money(item.get("capital") or item.get("cost")) * _int_money(item.get("qty"))
        if fee_total and subtotal_total:
            payment_fee = remaining_fee if index == len(items) - 1 else round(fee_total * subtotal / subtotal_total)
            remaining_fee -= payment_fee
        else:
            payment_fee = 0
        item["payment_fee"] = payment_fee
        item["total_cost"] = capital_cost + payment_fee
        item["profit"] = subtotal - item["total_cost"]
    return fee_total


def _stock_name_key(name):
    return str(name or "").strip().casefold()


def _stock_lookup(products):
    lookup = {}
    for product in products or []:
        key = _stock_name_key(product.get("name"))
        if key:
            lookup[key] = product
    return lookup


def load_and_validate_stock_for_items(items, merchant_id=None):
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    if _db_mandatory() and not _db_ready():
        raise RuntimeError("Database stock tidak tersedia. Transaksi dibatalkan agar stok tetap akurat.")
    products = list(load_stock(force=True, merchant_id=mid))
    lookup = _stock_lookup(products)
    requested = {}
    display_names = {}
    for item in items or []:
        name = str(item.get("item_name") or item.get("name") or "").strip()
        qty = _int_money(item.get("qty"))
        key = _stock_name_key(name)
        if not key or qty <= 0:
            continue
        requested[key] = requested.get(key, 0) + qty
        display_names.setdefault(key, name)

    errors = []
    for key, qty in requested.items():
        product = lookup.get(key)
        name = display_names.get(key) or key
        if not product:
            errors.append(f"{name} tidak ada di database stock.")
            continue
        available = _int_money(product.get("stock"))
        if qty > available:
            errors.append(f"Stock {name} tidak cukup (tersedia {available}, diminta {qty}).")
    if errors:
        raise ValueError(" ".join(errors))
    return products, lookup


def next_customer_name(state):
    mid = current_merchant_id()
    bucket = _state_tenant_bucket(state, mid)
    bucket["customer_counter"] = _int_money(bucket.get("customer_counter")) + 1
    _sync_legacy_state_for_default(state, mid)
    prefix = str(load_settings(mid).get("default_customer_prefix") or "Conlecta Customer")
    return f"{prefix} {bucket['customer_counter']}"


def _sheet_headers(ws, required_headers):
    current = [str(h).strip() for h in (ws.row_values(1) or [])]
    if not current:
        current = list(required_headers)
        ws.update([current], "A1")
        return current
    changed = False
    for header in required_headers:
        if header not in current:
            current.append(header)
            changed = True
    if changed:
        ws.update([current], "A1")
    return current


def _header_map(headers):
    return {str(name).strip(): idx for idx, name in enumerate(headers)}


def _row_from_mapping(headers, values):
    return [values.get(str(header).strip(), "") for header in headers]


def _sheet_row_matches(row, headers, txn_id, merchant_id):
    row_txn = str(_cell(row, headers, "Transaction ID", 1)).strip()
    if not row_txn or row_txn != str(txn_id):
        return False
    row_mid = normalize_merchant_id(_cell(row, headers, "Merchant ID", None, merchant_id))
    return row_mid == normalize_merchant_id(merchant_id)


def save_history_to_sheets(record):
    if _db_ready():
        try:
            conlecta_db.save_history(record, record.get("merchant_id") or current_merchant_id())
            return
        except Exception as exc:
            log.warning("save_history db sync failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("history")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("history"))
    spreadsheet = get_spreadsheet()
    if not spreadsheet:
        return
    try:
        txn_ws = ensure_ws(spreadsheet, SHEET_TXN, TXN_HEADER)
        items_ws = ensure_ws(spreadsheet, SHEET_TXN_ITEMS, ITEMS_HEADER)
        if not txn_ws or not items_ws:
            return

        merchant_id = normalize_merchant_id(record.get("merchant_id") or current_merchant_id())
        txn_id = str(record.get("txn_id") or "").strip()
        if not txn_id:
            return
        cash_received = _int_money(record.get("cash_received"))
        change = _int_money(record.get("change"))
        payment_method = derive_payment_method(record.get("payment_method"), cash_received, change, record.get("qr_id"))

        txn_headers = _sheet_headers(txn_ws, TXN_HEADER)
        txn_header_map = _header_map(txn_headers)
        txn_rows = txn_ws.get_all_values()
        txn_row_index = None
        existing_txn_row = []
        for idx, row in enumerate(txn_rows[1:], start=2):
            if _sheet_row_matches(row, txn_header_map, txn_id, merchant_id):
                txn_row_index = idx
                existing_txn_row = row
                break

        txn_values = {
            "No": _cell(existing_txn_row, txn_header_map, "No", 0, "") if existing_txn_row else len(txn_rows),
            "Transaction ID": txn_id,
            "QR ID": record.get("qr_id", ""),
            "Amount": record.get("amount", 0),
            "Updated At": record.get("updated_at_display", record.get("updated_at", "")),
            "Customer Note": record.get("customer_name", record.get("customer", "")),
            "Discount": record.get("discount", "0"),
            "Cashier Name": record.get("cashier_name", ""),
            "Gross": record.get("gross", record.get("amount", 0)),
            "Line Discount": record.get("line_discount", 0),
            "Cart Disc Amt": record.get("cart_discount_amt", 0),
            "Payment Method": payment_method,
            "Cash Received": cash_received,
            "Change": change,
            "Payment Fee": record.get("payment_fee", 0),
            "Net Amount": record.get("net_amount", _int_money(record.get("amount")) - _int_money(record.get("payment_fee"))),
            "Merchant ID": merchant_id,
        }
        txn_row = _row_from_mapping(txn_headers, txn_values)
        if txn_row_index:
            txn_ws.update([txn_row], f"A{txn_row_index}", value_input_option="USER_ENTERED")
        else:
            txn_ws.append_row(txn_row, value_input_option="USER_ENTERED")

        item_headers = _sheet_headers(items_ws, ITEMS_HEADER)
        item_header_map = _header_map(item_headers)
        item_rows = items_ws.get_all_values()
        existing_item_rows = []
        for idx, row in enumerate(item_rows[1:], start=2):
            if _sheet_row_matches(row, item_header_map, txn_id, merchant_id):
                existing_item_rows.append((idx, row))

        expected_rows = []
        next_no_item = len(item_rows)
        for item in record.get("items", []) or []:
            item_name = item.get("item_name") or item.get("name") or ""
            expected_rows.append({
                "No": next_no_item,
                "Transaction ID": txn_id,
                "QR ID": record.get("qr_id", ""),
                "Item Name": item_name,
                "Qty": item.get("qty", 0),
                "Amount": item.get("amount", item.get("price", item.get("unit_price", 0))),
                "Subtotal": item.get("subtotal", 0),
                "Capital": item.get("capital", item.get("cost", 0)),
                "Profit": item.get("profit", _int_money(item.get("subtotal")) - (_int_money(item.get("capital", item.get("cost", 0))) * _int_money(item.get("qty")))),
                "Payment Fee": item.get("payment_fee", 0),
                "Total Cost": item.get("total_cost", (_int_money(item.get("capital", item.get("cost", 0))) * _int_money(item.get("qty"))) + _int_money(item.get("payment_fee"))),
                "Free": "Yes" if item.get("free") else "No",
                "Disc %": item.get("disc_pct", 0),
                "Disc Rp": item.get("disc_fixed", 0),
                "Line Discount": item.get("line_discount", 0),
                "Payment Method": payment_method,
                "Change": change,
                "Cash Received": cash_received,
                "Merchant ID": merchant_id,
            })
            next_no_item += 1

        append_rows = []
        for idx, values in enumerate(expected_rows):
            if idx < len(existing_item_rows):
                row_index, old_row = existing_item_rows[idx]
                values["No"] = _cell(old_row, item_header_map, "No", 0, values["No"])
                items_ws.update([_row_from_mapping(item_headers, values)], f"A{row_index}", value_input_option="USER_ENTERED")
            else:
                append_rows.append(_row_from_mapping(item_headers, values))
        if append_rows:
            items_ws.append_rows(append_rows, value_input_option="USER_ENTERED")

        for row_index, _old_row in reversed(existing_item_rows[len(expected_rows):]):
            try:
                items_ws.delete_rows(row_index)
            except Exception:
                items_ws.update([["" for _ in item_headers]], f"A{row_index}", value_input_option="USER_ENTERED")
    except Exception as exc:
        log.warning("save_history data sync failed: %s", exc)


def _cell(row, headers, name, fallback=None, default=""):
    idx = headers.get(name)
    if idx is None:
        wanted = str(name or "").strip().casefold()
        for header, pos in (headers or {}).items():
            if str(header or "").strip().casefold() == wanted:
                idx = pos
                break
    if idx is None:
        idx = fallback
    if idx is None or idx >= len(row):
        return default
    return row[idx]


def _cell_any(row, headers, names, fallback=None, default=""):
    for name in names or []:
        value = _cell(row, headers, name, None, None)
        if value not in (None, ""):
            return value
    return _cell(row, headers, (names or [""])[0], fallback, default)


def _cell_int(row, headers, name, fallback=None):
    return _int_money(_cell(row, headers, name, fallback, ""))


def load_history_from_sheets():
    mid = current_merchant_id()
    if _db_ready():
        try:
            return conlecta_db.load_history(mid)
        except Exception as exc:
            log.warning("load_history db sync failed: %s", exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("history")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("history"))
    spreadsheet = get_spreadsheet()
    if not spreadsheet:
        return []
    try:
        txn_ws = ensure_ws(spreadsheet, SHEET_TXN, TXN_HEADER)
        items_ws = ensure_ws(spreadsheet, SHEET_TXN_ITEMS, ITEMS_HEADER)
        txn_rows = txn_ws.get_all_values()
        item_rows = items_ws.get_all_values()
        if len(txn_rows) <= 1:
            return []
        item_headers = {name.strip(): idx for idx, name in enumerate(item_rows[0])} if item_rows else {}
        items_by_txn = {}
        items_by_qr = {}
        for row in item_rows[1:]:
            row_mid = normalize_merchant_id(_cell(row, item_headers, "Merchant ID", 14, DEFAULT_MERCHANT_ID))
            if row_mid != mid:
                continue
            tid = str(_cell(row, item_headers, "Transaction ID", 1)).strip()
            qid = str(_cell(row, item_headers, "QR ID", 2)).strip()
            item_change = _cell_int(row, item_headers, "Change", 12)
            item_cash_received = _cell_int(row, item_headers, "Cash Received", 13)
            item_capital = _cell_int(row, item_headers, "Capital")
            item_qty = _cell_int(row, item_headers, "Qty", 4)
            item_subtotal = _cell_int(row, item_headers, "Subtotal", 6)
            item_payment_fee = _cell_int(row, item_headers, "Payment Fee")
            item_total_cost = _cell_int(row, item_headers, "Total Cost") or ((item_capital * item_qty) + item_payment_fee)
            item = {
                "item_name": _cell(row, item_headers, "Item Name", 3),
                "name": _cell(row, item_headers, "Item Name", 3),
                "qty": item_qty,
                "amount": _cell_int(row, item_headers, "Amount", 5),
                "price": _cell_int(row, item_headers, "Amount", 5),
                "subtotal": item_subtotal,
                "capital": item_capital,
                "cost": item_capital,
                "payment_fee": item_payment_fee,
                "total_cost": item_total_cost,
                "profit": _cell_int(row, item_headers, "Profit") or (item_subtotal - item_total_cost if item_total_cost else 0),
                "free": str(_cell(row, item_headers, "Free", 7)).strip().lower() == "yes",
                "disc_pct": _cell_int(row, item_headers, "Disc %", 8),
                "disc_fixed": _cell_int(row, item_headers, "Disc Rp", 9),
                "line_discount": _cell_int(row, item_headers, "Line Discount", 10),
                "payment_method": derive_payment_method(
                    _cell(row, item_headers, "Payment Method", 11),
                    item_cash_received,
                    item_change,
                    qid,
                ),
                "change": item_change,
                "cash_received": item_cash_received,
            }
            if tid:
                items_by_txn.setdefault(tid, []).append(item)
            if qid:
                items_by_qr.setdefault(qid, []).append(item)
        txn_headers = {name.strip(): idx for idx, name in enumerate(txn_rows[0])}
        result = []
        for row in txn_rows[1:]:
            row_mid = normalize_merchant_id(_cell(row, txn_headers, "Merchant ID", 14, DEFAULT_MERCHANT_ID))
            if row_mid != mid:
                continue
            tid = str(_cell(row, txn_headers, "Transaction ID", 1)).strip()
            qid = str(_cell(row, txn_headers, "QR ID", 2)).strip()
            if not tid and not qid:
                continue
            amount = _cell_int(row, txn_headers, "Amount", 3)
            cash_received = _cell_int(row, txn_headers, "Cash Received", 12)
            change = _cell_int(row, txn_headers, "Change", 13)
            payment_fee = _cell_int(row, txn_headers, "Payment Fee")
            method = derive_payment_method(
                _cell(row, txn_headers, "Payment Method", 11),
                cash_received,
                change,
                qid,
            )
            if not payment_fee and method == PAYMENT_METHOD_QRIS:
                payment_fee = calc_qris_fee(amount)
            customer = _cell(row, txn_headers, "Customer Note", 5)
            record_items = items_by_txn.get(tid) or items_by_qr.get(qid) or []
            if payment_fee and record_items and not sum(_int_money(item.get("payment_fee")) for item in record_items):
                apply_payment_fee_to_items(record_items, method, amount)
            record = {
                "txn_id": tid,
                "qr_id": qid,
                "amount": amount,
                "updated_at": _cell(row, txn_headers, "Updated At", 4),
                "updated_at_display": _cell(row, txn_headers, "Updated At", 4),
                "customer_name": customer,
                "customer": customer,
                "customer_email": "",
                "discount": _cell(row, txn_headers, "Discount", 6),
                "cashier_name": _cell(row, txn_headers, "Cashier Name", 7),
                "gross": _cell_int(row, txn_headers, "Gross", 8) or amount,
                "line_discount": _cell_int(row, txn_headers, "Line Discount", 9),
                "cart_discount_amt": _cell_int(row, txn_headers, "Cart Disc Amt", 10),
                "payment_method": method,
                "cash_received": cash_received,
                "change": change,
                "payment_fee": payment_fee,
                "net_amount": _cell_int(row, txn_headers, "Net Amount") or (amount - payment_fee),
                "merchant_id": row_mid,
                "items": record_items,
            }
            result.append(record)
        result.reverse()
        return result
    except Exception as exc:
        log.warning("load_history data sync failed: %s", exc)
        return []


def send_receipt_email(record, email):
    try:
        from conlecta_email import send_receipt_email as _send
    except Exception as exc:
        log.warning("Email module unavailable: %s", exc)
        return

    def ok(msg):
        log.info("Receipt email sent to %s: %s", email, msg)

    def fail(msg):
        log.warning("Receipt email failed to %s: %s", email, msg)

    try:
        rec = dict(record)
        mid = normalize_merchant_id(rec.get("merchant_id") or current_merchant_id())
        settings = settings_payload(merchant_id=mid)
        merchant = merchant_payload(mid)
        rec["merchant_id"] = mid
        rec["shop_name"] = (
            rec.get("shop_name")
            or settings.get("shop_name")
            or merchant.get("name")
            or DEFAULT_MERCHANT_NAME
        )
        rec["brand_logo_path"] = (
            rec.get("brand_logo_path")
            or settings.get("brand_logo_path")
            or merchant.get("logo_path")
            or BRAND_DEFAULT_LOGO
        )
        rec["brand_logo_url"] = rec.get("brand_logo_url") or settings.get("brand_logo_url", "")
        rec["updated_at_display"] = rec.get("updated_at_display") or format_datetime(rec.get("updated_at"))
        rec["updated_at"] = rec["updated_at_display"]
        rec["email_template"] = load_email_templates().get("receipt", {})
        _send(rec, email, on_success=ok, on_error=fail)
    except Exception as exc:
        log.warning("send_receipt_email call failed: %s", exc)


def save_transaction(payload, payment_method):
    global _stock_cache, _stock_cache_ts
    payment_method = normalize_payment_method(payment_method)
    state = load_state()
    mid = current_merchant_id()
    bucket = _ensure_daily_session(state, mid)
    amount = _int_money(payload.get("amount"))
    cash_received = _int_money(payload.get("cash_received"))
    change = max(0, _int_money(payload.get("change")))
    items = normalize_items(payload.get("items", []), payment_method, cash_received, change)
    if not items:
        raise ValueError("No cart items")
    gross_total = sum(_int_money(item.get("gross")) for item in items)
    line_discount_total = sum(_int_money(item.get("line_discount")) for item in items)
    if amount <= 0:
        amount = sum(item["subtotal"] for item in items)
    payment_fee = calc_qris_fee(amount) if payment_method == PAYMENT_METHOD_QRIS else 0
    customer_name = str(payload.get("customer_name") or "").strip() or next_customer_name(state)
    customer_email = str(payload.get("customer_email") or "").strip()
    auth = state.get("auth") or {}
    txn_id = str(payload.get("txn_id") or generate_txn_id())
    qr_id = str(payload.get("qr_id") or "")
    updated_at = datetime.now().isoformat(timespec="seconds")
    record = {
        "txn_id": txn_id,
        "qr_id": qr_id,
        "merchant_id": mid,
        "amount": amount,
        "updated_at": updated_at,
        "updated_at_display": format_datetime(updated_at),
        "customer_name": customer_name,
        "customer": customer_name,
        "customer_email": customer_email,
        "discount": str(payload.get("discount", "0") or "0"),
        "cashier_name": str(payload.get("cashier_name") or auth.get("name") or "Cashier"),
        "gross": _int_money(payload.get("gross"), gross_total or amount),
        "line_discount": _int_money(payload.get("line_discount"), line_discount_total),
        "cart_discount_amt": _int_money(payload.get("cart_discount_amt")),
        "payment_method": payment_method,
        "cash_received": cash_received,
        "change": change,
        "payment_fee": payment_fee,
        "net_amount": amount - payment_fee,
        "items": items,
    }

    history = list(bucket.get("history") or [])
    existing = next((h for h in history if str(h.get("txn_id") or "") == txn_id), None)
    if not existing:
        db_existing = next((h for h in load_history_from_sheets() if str(h.get("txn_id") or "") == txn_id), None)
        if db_existing:
            existing = db_existing
    if existing:
        existing["payment_method"] = derive_payment_method(
            existing.get("payment_method"),
            existing.get("cash_received"),
            existing.get("change"),
            existing.get("qr_id"),
        )
        if not any(str(h.get("txn_id") or "") == txn_id for h in history):
            history.insert(0, existing)
            bucket["history"] = history[:1000]
        if payment_method == PAYMENT_METHOD_QRIS:
            active = bucket.get("active_qr") or {}
            _mark_closed_qr(bucket, existing)
            if not active or str(active.get("txn_id") or "") == txn_id:
                bucket["active_qr"] = None
        _sync_legacy_state_for_default(state, mid)
        save_state(state)
        save_history_to_sheets(existing)
        log.info("%s payment retry ignored: txn=%s already saved", payment_method, txn_id)
        return existing
    products, product_lookup = load_and_validate_stock_for_items(items, merchant_id=mid)
    for item in items:
        product = product_lookup.get(_stock_name_key(item.get("item_name")))
        if product:
            capital = _int_money(product.get("capital") or product.get("cost") or product.get("buy_price"))
            item["capital"] = capital
            item["cost"] = capital
    payment_fee = apply_payment_fee_to_items(items, payment_method, amount)
    record["payment_fee"] = payment_fee
    record["net_amount"] = amount - payment_fee
    history.insert(0, record)
    bucket["history"] = history[:1000]
    session = bucket.setdefault("session", {"sales": 0, "revenue": 0})
    session["sales"] = _int_money(session.get("sales")) + 1
    session["revenue"] = _int_money(session.get("revenue")) + amount
    if payment_method == PAYMENT_METHOD_QRIS:
        bucket["active_qr"] = None
    set_display_event(state, mid, "success", record)

    changed_stock_names = set()
    for item in items:
        product = product_lookup.get(_stock_name_key(item.get("item_name")))
        if product:
            product["stock"] = _int_money(product.get("stock")) - _int_money(item.get("qty"))
            changed_stock_names.add(product.get("name"))
    bucket["products"] = products
    if not isinstance(_stock_cache, dict):
        _stock_cache = {}
    _stock_cache[mid] = products
    _stock_cache_ts = time.time()
    _sync_legacy_state_for_default(state, mid)
    save_state(state)
    sync_stock_delta_to_sheets(products, changed_stock_names, merchant_id=mid)
    save_history_to_sheets(record)
    if customer_email:
        threading.Thread(target=lambda: send_receipt_email(record, customer_email), daemon=True).start()
    log.info("%s payment success: txn=%s amount=%s", payment_method, txn_id, amount)
    return record


def load_history():
    mid = current_merchant_id()
    state = load_state()
    bucket = _state_tenant_bucket(state, mid)
    if _db_mandatory():
        history = load_history_from_sheets()
        bucket["history"] = history[:1000]
        _sync_legacy_state_for_default(state, mid)
        save_state(state)
        return history
    local_history = list(bucket.get("history") or [])
    db_history = load_history_from_sheets()
    if not db_history:
        return local_history
    seen = {str(record.get("txn_id") or record.get("qr_id")) for record in db_history}
    merged = list(db_history)
    for record in local_history:
        key = str(record.get("txn_id") or record.get("qr_id"))
        if key and key not in seen:
            merged.insert(0, record)
            seen.add(key)
    bucket["history"] = merged[:1000]
    _sync_legacy_state_for_default(state, mid)
    save_state(state)
    return merged


def load_history_for_merchant(merchant_id=None):
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    if _db_ready():
        try:
            return conlecta_db.load_history(mid)
        except Exception as exc:
            log.warning("admin load_history db failed for %s: %s", mid, exc)
            if _db_mandatory():
                raise RuntimeError(_db_unavailable_message("history")) from exc
    if _db_mandatory():
        raise RuntimeError(_db_unavailable_message("history"))
    state = load_state()
    bucket = _state_tenant_bucket(state, mid)
    return list(bucket.get("history") or [])


def admin_transactions_payload(merchant_id=None):
    require_system_admin()
    mid = normalize_merchant_id(merchant_id)
    records = load_history_for_merchant(mid)
    products = load_stock(force=True, merchant_id=mid)
    return {
        "merchant_id": mid,
        "transactions": records[:300],
        "products": products,
    }


def _aggregate_item_qty(items):
    out = {}
    labels = {}
    for item in items or []:
        name = str(item.get("item_name") or item.get("name") or "").strip()
        key = _stock_name_key(name)
        qty = _int_money(item.get("qty"))
        if not key or qty <= 0:
            continue
        out[key] = out.get(key, 0) + qty
        labels.setdefault(key, name)
    return out, labels


def update_system_transaction(data):
    global _stock_cache, _stock_cache_ts
    require_system_admin()
    mid = normalize_merchant_id(data.get("merchant_id"))
    txn_id = str(data.get("txn_id") or data.get("transaction_id") or "").strip()
    if not txn_id:
        raise ValueError("Transaction ID wajib dipilih.")
    history = load_history_for_merchant(mid)
    existing = next((record for record in history if str(record.get("txn_id") or "") == txn_id), None)
    if not existing:
        raise ValueError("Transaksi tidak ditemukan untuk merchant ini.")

    payment_method = normalize_payment_method(data.get("payment_method") or existing.get("payment_method"))
    raw_items = data.get("items") or []
    items = normalize_items(raw_items, payment_method)
    if not items:
        raise ValueError("Minimal satu item transaksi wajib ada.")

    products = list(load_stock(force=True, merchant_id=mid))
    lookup = _stock_lookup(products)
    old_counts, old_labels = _aggregate_item_qty(existing.get("items") or [])
    new_counts, new_labels = _aggregate_item_qty(items)
    changed_names = set()

    for key, qty in old_counts.items():
        product = lookup.get(key)
        if product:
            product["stock"] = _int_money(product.get("stock")) + qty
            changed_names.add(product.get("name") or old_labels.get(key))

    errors = []
    for key, qty in new_counts.items():
        product = lookup.get(key)
        name = new_labels.get(key) or key
        if not product:
            errors.append(f"{name} tidak ada di stock merchant.")
            continue
        available = _int_money(product.get("stock"))
        if qty > available:
            errors.append(f"Stock {name} tidak cukup setelah return item lama (tersedia {available}, diminta {qty}).")
    if errors:
        raise ValueError(" ".join(errors))

    for item in items:
        key = _stock_name_key(item.get("item_name"))
        product = lookup.get(key)
        if product:
            capital = _int_money(product.get("capital") or product.get("cost") or product.get("buy_price"))
            item["capital"] = capital
            item["cost"] = capital
            product["stock"] = _int_money(product.get("stock")) - _int_money(item.get("qty"))
            changed_names.add(product.get("name") or item.get("item_name"))

    amount = sum(_int_money(item.get("subtotal")) for item in items)
    gross_total = sum(_int_money(item.get("gross")) for item in items)
    line_discount_total = sum(_int_money(item.get("line_discount")) for item in items)
    cash_received = _int_money(data.get("cash_received") if data.get("cash_received") not in (None, "") else existing.get("cash_received"))
    change = max(0, cash_received - amount) if payment_method == PAYMENT_METHOD_CASH else 0
    payment_fee = apply_payment_fee_to_items(items, payment_method, amount)
    updated_at = datetime.now().isoformat(timespec="seconds")
    record = dict(existing)
    record.update({
        "txn_id": txn_id,
        "qr_id": str(data.get("qr_id") if data.get("qr_id") is not None else existing.get("qr_id") or ""),
        "merchant_id": mid,
        "amount": amount,
        "updated_at": updated_at,
        "updated_at_display": format_datetime(updated_at),
        "customer_name": str(data.get("customer_name") if data.get("customer_name") is not None else existing.get("customer_name") or "").strip(),
        "customer": str(data.get("customer_name") if data.get("customer_name") is not None else existing.get("customer") or "").strip(),
        "customer_email": str(data.get("customer_email") if data.get("customer_email") is not None else existing.get("customer_email") or "").strip(),
        "discount": str(data.get("discount") if data.get("discount") is not None else existing.get("discount") or "0"),
        "cashier_name": str(data.get("cashier_name") if data.get("cashier_name") is not None else existing.get("cashier_name") or "").strip(),
        "gross": gross_total or amount,
        "line_discount": line_discount_total,
        "cart_discount_amt": _int_money(data.get("cart_discount_amt")),
        "payment_method": payment_method,
        "cash_received": cash_received if payment_method == PAYMENT_METHOD_CASH else 0,
        "change": change,
        "payment_fee": payment_fee,
        "net_amount": amount - payment_fee,
        "items": items,
    })

    if not isinstance(_stock_cache, dict):
        _stock_cache = {}
    _stock_cache[mid] = products
    _stock_cache_ts = time.time()
    sync_stock_delta_to_sheets(products, changed_names, merchant_id=mid)
    save_history_to_sheets(record)

    state = load_state()
    bucket = _state_tenant_bucket(state, mid)
    local_history = list(bucket.get("history") or [])
    replaced = False
    for index, existing_local in enumerate(local_history):
        if str(existing_local.get("txn_id") or "") == txn_id:
            local_history[index] = record
            replaced = True
            break
    if not replaced:
        local_history.insert(0, record)
    bucket["history"] = local_history[:1000]
    bucket["products"] = products
    session = bucket.setdefault("session", {"sales": 0, "revenue": 0})
    session["revenue"] = max(0, _int_money(session.get("revenue")) + amount - _int_money(existing.get("amount")))
    _sync_legacy_state_for_default(state, mid)
    save_state(state)
    log.info("System admin updated transaction: merchant=%s txn=%s amount=%s", mid, txn_id, amount)
    return {
        "record": record,
        "transactions": load_history_for_merchant(mid)[:300],
        "products": products,
    }


def parse_history_datetime(value):
    text = str(value or "").strip()
    if not text:
        return None
    text = text.split(" - ", 1)[-1].strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y",
    ):
        try:
            return datetime.strptime(text[:19], fmt)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _parse_discount_meta(raw):
    out = {"cart_discount_pct": 0, "cart_discount_amt": 0, "line_discount": 0, "gross": 0}
    text = str(raw or "").strip()
    if not text or text in ("0", "-", "—"):
        return out
    if text.endswith("%") and text[:-1].strip().isdigit():
        out["cart_discount_pct"] = max(0, min(100, _int_money(text[:-1])))
        return out
    if text.isdigit():
        out["cart_discount_pct"] = max(0, min(100, _int_money(text)))
        return out
    for part in text.replace(";", "|").split("|"):
        part = part.strip()
        if not part:
            continue
        if part.endswith("%") and part[:-1].strip().isdigit():
            out["cart_discount_pct"] = max(0, min(100, _int_money(part[:-1])))
            continue
        if ":" not in part:
            continue
        key, value = [x.strip().lower() for x in part.split(":", 1)]
        amount = max(0, _int_money(value))
        if key in ("pct", "percent", "percentage", "cart_pct"):
            out["cart_discount_pct"] = max(0, min(100, amount))
        elif key in ("line", "line_discount", "item", "fixed"):
            out["line_discount"] = amount
        elif key in ("cart", "cart_amt", "gross_discount", "gross_disc"):
            out["cart_discount_amt"] = amount
        elif key == "gross":
            out["gross"] = amount
    return out


def discount_breakdown(record):
    amount = _int_money(record.get("amount"))
    meta = _parse_discount_meta(record.get("discount", "0"))
    gross = _int_money(record.get("gross")) or _int_money(record.get("gross_subtotal")) or meta["gross"] or amount
    line_discount = _int_money(record.get("line_discount")) or _int_money(record.get("line_discount_total")) or meta["line_discount"]
    cart_pct = _int_money(record.get("cart_discount_pct")) or meta["cart_discount_pct"]
    cart_amt = _int_money(record.get("cart_discount_amt")) or meta["cart_discount_amt"]
    if not gross:
        if cart_pct and amount and cart_pct < 100:
            gross = int(round(amount / (1 - cart_pct / 100))) + line_discount
        else:
            gross = amount + line_discount + cart_amt
    after_line = max(0, gross - line_discount)
    if cart_pct and not cart_amt:
        cart_amt = round(after_line * cart_pct / 100)
    if not amount:
        amount = max(0, after_line - cart_amt)
    return {
        "amount": amount,
        "gross": gross,
        "line_discount": line_discount,
        "cart_discount_pct": cart_pct,
        "cart_discount_amt": cart_amt,
        "total_discount": line_discount + cart_amt,
    }


def item_discount_breakdown(item):
    qty = _int_money(item.get("qty"))
    subtotal = _int_money(item.get("subtotal"))
    gross = _int_money(item.get("gross")) or _int_money(item.get("unit_price") or item.get("amount")) * qty
    line_discount = _int_money(item.get("line_discount")) or max(0, gross - subtotal)
    if item.get("free"):
        line_discount = gross
        subtotal = 0
    return {
        "qty": qty,
        "gross": gross,
        "line_discount": line_discount,
        "after_line": max(0, subtotal),
    }


def items_with_cart_discount(record):
    rows = []
    cart_amt = discount_breakdown(record)["cart_discount_amt"]
    for item in record.get("items", []) or []:
        bd = item_discount_breakdown(item)
        rows.append({"item": item, **bd, "cart_discount": 0})
    eligible = [i for i, row in enumerate(rows) if row["after_line"] > 0]
    base_total = sum(rows[i]["after_line"] for i in eligible)
    if cart_amt and base_total:
        remaining = cart_amt
        for pos, idx in enumerate(eligible):
            share = remaining if pos == len(eligible) - 1 else round(cart_amt * rows[idx]["after_line"] / base_total)
            share = max(0, min(share, rows[idx]["after_line"], remaining))
            rows[idx]["cart_discount"] = share
            remaining -= share
    for row in rows:
        row["discount"] = row["line_discount"] + row["cart_discount"]
        row["subtotal"] = max(0, row["after_line"] - row["cart_discount"])
    return rows


def vendor_invoice_payload(vendor_id="", vendor_name="", date_from="", date_to=""):
    history = load_history()
    products = load_stock(force=True)
    vendors = load_vendors(force=True)
    vendor_map = {str(v["id"]): v["name"] for v in vendors}
    product_by_name = {str(item.get("name") or ""): item for item in products}
    item_vendor = {name: str(item.get("vendor_id", "")) for name, item in product_by_name.items()}
    selected_id = str(vendor_id or "").strip()
    selected_name = str(vendor_name or "").strip()
    dt_from = parse_history_datetime(date_from)
    dt_to = parse_history_datetime(date_to)
    if dt_to and dt_to.hour == 0 and dt_to.minute == 0:
        dt_to = dt_to.replace(hour=23, minute=59, second=59)

    rows = []
    totals = {"qty": 0, "gross": 0, "discount": 0, "subtotal": 0, "capital": 0, "cost": 0, "profit": 0}
    for rec in history:
        rec_dt = parse_history_datetime(rec.get("updated_at_display") or rec.get("updated_at"))
        if dt_from and (not rec_dt or rec_dt < dt_from):
            continue
        if dt_to and (not rec_dt or rec_dt > dt_to):
            continue
        for row_bd in items_with_cart_discount(rec):
            item = row_bd["item"]
            item_name = str(item.get("item_name") or item.get("name") or "")
            product = product_by_name.get(item_name, {})
            vid = item_vendor.get(item_name, "")
            vname = vendor_map.get(vid, "(Unknown)" if vid else "(No Vendor)")
            if selected_id and vid != selected_id:
                continue
            if selected_name and selected_name != "(All)" and vname != selected_name:
                continue
            capital = _int_money(
                item.get("capital")
                or item.get("cost")
                or product.get("capital")
                or product.get("modal")
                or product.get("harga_beli")
                or product.get("buy_price")
            )
            vendor_cost = capital * row_bd["qty"]
            profit = row_bd["subtotal"] - vendor_cost
            row = {
                "txn": rec.get("txn_id", "-"),
                "date": rec.get("updated_at_display") or rec.get("updated_at", "-"),
                "method": derive_payment_method(rec.get("payment_method"), rec.get("cash_received"), rec.get("change"), rec.get("qr_id")),
                "vendor_id": vid,
                "vendor_name": vname,
                "item": item_name,
                "qty": row_bd["qty"],
                "capital": capital,
                "cost": vendor_cost,
                "gross": row_bd["gross"],
                "discount": row_bd["discount"],
                "subtotal": row_bd["subtotal"],
                "profit": profit,
            }
            rows.append(row)
            totals["qty"] += row["qty"]
            totals["capital"] += capital
            totals["cost"] += row["cost"]
            totals["gross"] += row["gross"]
            totals["discount"] += row["discount"]
            totals["subtotal"] += row["subtotal"]
            totals["profit"] += row["profit"]
    return {
        "rows": rows,
        "totals": totals,
        "vendors": vendors,
        "selected_vendor": selected_name or (vendor_map.get(selected_id, "(All)") if selected_id else "(All)"),
    }


def active_qr_status(qr_id=None):
    mid = current_merchant_id()
    state = load_state()
    bucket = _state_tenant_bucket(state, mid)
    active = current_active_qr(state, mid)
    if not active:
        save_state(state)
        return {"status": "NONE", "active_qr": None}
    if normalize_merchant_id(active.get("merchant_id")) != mid:
        return {"status": "NONE", "active_qr": None}
    if qr_id and str(active.get("id")) != str(qr_id):
        return {"status": "NOT_FOUND", "active_qr": active}
    try:
        data = fetch_qris_status(active.get("id"))
        qris = _extract_qris_payload(data)
        status = _qris_status_text(qris) or active.get("status") or "PENDING"
        active["status"] = status.upper()
        active["raw_status"] = qris
        if str(status or "").strip().lower() in PAID_QRIS_STATUSES:
            _mark_closed_qr(bucket, active)
            bucket["active_qr"] = None
        else:
            bucket["active_qr"] = active
        _sync_legacy_state_for_default(state, mid)
        save_state(state)
    except Exception as exc:
        active["last_error"] = str(exc)
    return {"status": str(active.get("status") or "PENDING").upper(), "active_qr": active}


def _pdf_escape(value):
    return str(value if value is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _pdf_logo(settings, Image, size=46):
    path = settings.get("brand_logo_path") or BRAND_DEFAULT_LOGO
    if not path or not os.path.isfile(path):
        path = BRAND_DEFAULT_LOGO if os.path.isfile(BRAND_DEFAULT_LOGO) else BRAND_EMAIL_LOGO
    if path and os.path.isfile(path):
        try:
            return Image(path, width=size, height=size)
        except Exception:
            return ""
    return ""


def _pdf_short_date(value=None):
    text = format_datetime(value)
    return text if text else datetime.now().strftime("%A - %d-%m-%Y %H:%M")


def _pdf_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 6.5)
    canvas.setFillColorRGB(0.42, 0.44, 0.50)
    canvas.drawString(doc.leftMargin, 18, PDF_GENERATED_REMARK)
    canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 18, f"Page {doc.page}")
    canvas.setStrokeColorRGB(0.88, 0.89, 0.92)
    canvas.setLineWidth(0.4)
    canvas.line(doc.leftMargin, 30, doc.pagesize[0] - doc.rightMargin, 30)
    canvas.restoreState()


def _pdf_build(doc, story):
    doc.build(story, onFirstPage=_pdf_footer, onLaterPages=_pdf_footer)


def make_pdf(record, merchant=False):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
        from reportlab.platypus import HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        from reportlab.graphics.shapes import Drawing, Rect, String
    except Exception as exc:
        raise RuntimeError(f"ReportLab unavailable: {exc}")

    settings = load_settings(record.get("merchant_id") or current_merchant_id())
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=56, leftMargin=56, topMargin=48, bottomMargin=40)
    W = doc.width
    styles = getSampleStyleSheet()

    ink = colors.HexColor("#1a1a2e")
    muted = colors.HexColor("#6c727f")
    accent = colors.HexColor("#6366f1")
    teal = colors.HexColor("#0d9488")
    emerald = colors.HexColor("#059669")
    amber = colors.HexColor("#d97706")
    soft_line = colors.HexColor("#e2e5ea")
    badge_bg = colors.HexColor("#f0fdf4")
    badge_txt = colors.HexColor("#166534")
    header_bg = colors.HexColor("#f8f9fc")

    s_title = ParagraphStyle("PdfTitle2", parent=styles["Title"], fontSize=28, leading=32, textColor=accent, fontName="Helvetica-Bold", alignment=TA_RIGHT)
    s_brand = ParagraphStyle("PdfBrand2", parent=styles["BodyText"], fontSize=11, leading=16, textColor=ink)
    s_label = ParagraphStyle("PdfLabel2", parent=styles["BodyText"], fontSize=7, leading=9, textColor=muted, fontName="Helvetica-Bold", spaceBefore=0, spaceAfter=0)
    s_body = ParagraphStyle("PdfBody2", parent=styles["BodyText"], fontSize=9, leading=13, textColor=ink)
    s_bold = ParagraphStyle("PdfBold2", parent=s_body, fontName="Helvetica-Bold")
    s_right = ParagraphStyle("PdfRight2", parent=s_body, alignment=TA_RIGHT)
    s_right_bold = ParagraphStyle("PdfRightB2", parent=s_right, fontName="Helvetica-Bold")
    s_total = ParagraphStyle("PdfTotal2", parent=styles["BodyText"], fontSize=20, leading=24, textColor=emerald, fontName="Helvetica-Bold", alignment=TA_RIGHT)
    s_small = ParagraphStyle("PdfSmall2", parent=styles["BodyText"], fontSize=7, leading=10, textColor=muted)
    s_center = ParagraphStyle("PdfCenter2", parent=s_body, alignment=TA_CENTER)

    shop = _pdf_escape(settings.get("shop_name") or "Conlecta")
    address = _pdf_escape(settings.get("shop_address") or "")
    doc_title = "INVOICE" if merchant else "RECEIPT"
    method = derive_payment_method(record.get("payment_method"), record.get("cash_received"), record.get("change"), record.get("qr_id"))
    amount = _int_money(record.get("amount"))
    breakdown = discount_breakdown(record)
    gross = breakdown["gross"] or amount
    line_discount = breakdown["line_discount"]
    cart_discount = breakdown["cart_discount_amt"]
    fee = 0 if method == PAYMENT_METHOD_CASH else calc_qris_fee(amount)
    paid_at = record.get("updated_at_display") or record.get("updated_at")

    accent_bar = Drawing(W, 4)
    accent_bar.add(Rect(0, 0, W, 4, fillColor=accent, strokeColor=None))

    logo = _pdf_logo(settings, Image, 48)
    addr_html = f"<br/><font color='#6c727f' size='8'>{address}</font>" if address else ""
    header = Table([[
        logo if logo else "",
        Paragraph(f"<b>{shop}</b>{addr_html}", s_brand),
        Paragraph(doc_title, s_title),
    ]], colWidths=[58, W - 228, 170])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))

    txn_id = _pdf_escape(record.get("txn_id", "-"))
    receipt_no = _pdf_escape(record.get("qr_id") or record.get("receipt_no") or "-")
    info_data = [
        [Paragraph("TRANSACTION ID", s_label), Paragraph("NO. DOKUMEN", s_label), Paragraph("TANGGAL", s_label), Paragraph("STATUS", s_label)],
        [
            Paragraph(f"<b>{txn_id}</b>", s_body),
            Paragraph(f"<b>{receipt_no}</b>", s_body),
            Paragraph(f"<b>{_pdf_escape(_pdf_short_date(paid_at))}</b>", s_body),
            Paragraph("<font color='#059669'><b>&#x2713; Lunas</b></font>", s_body),
        ],
    ]
    info_table = Table(info_data, colWidths=[W * 0.28, W * 0.28, W * 0.28, W * 0.16])
    info_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, -1), header_bg),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 10),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
    ]))

    customer = record.get("customer_name") or record.get("customer") or "-"
    cashier = record.get("cashier_name") or "-"
    detail_left = [["METODE PEMBAYARAN", method]]
    if not merchant:
        detail_left.append(["PELANGGAN", customer])
    detail_left.append(["KASIR", cashier])
    if method == PAYMENT_METHOD_CASH:
        detail_left.extend([
            ["UANG DITERIMA", format_rupiah(record.get("cash_received", 0))],
            ["KEMBALIAN", format_rupiah(record.get("change", 0))],
        ])
    else:
        detail_left.append(["QR ID", record.get("qr_id") or "-"])

    detail_rows = [[
        Paragraph(f"<font color='#6c727f' size='7'>{_pdf_escape(label)}</font>", s_body),
        Paragraph(f"<b>{_pdf_escape(value)}</b>", s_body),
    ] for label, value in detail_left]
    detail_table = Table(detail_rows, colWidths=[120, W - 120])
    detail_table.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, soft_line),
    ]))

    total_display = gross if merchant else amount
    total_box = Table([[
        Paragraph("TOTAL" if not merchant else "TOTAL KOTOR", ParagraphStyle("t2", parent=s_body, fontSize=10, textColor=muted)),
        Paragraph(format_rupiah(total_display), s_total),
    ]], colWidths=[W * 0.4, W * 0.6])
    total_box.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("BACKGROUND", (0, 0), (-1, -1), badge_bg),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
    ]))

    col_num = 28
    col_name = W - 208
    col_qty = 45
    col_price = 68
    col_sub = 68
    item_header = [
        Paragraph("#", ParagraphStyle("ih", parent=s_label, textColor=colors.white)),
        Paragraph("PRODUK", ParagraphStyle("ih2", parent=s_label, textColor=colors.white)),
        Paragraph("QTY", ParagraphStyle("ih3", parent=s_label, textColor=colors.white, alignment=TA_CENTER)),
        Paragraph("HARGA", ParagraphStyle("ih4", parent=s_label, textColor=colors.white, alignment=TA_RIGHT)),
        Paragraph("SUBTOTAL", ParagraphStyle("ih5", parent=s_label, textColor=colors.white, alignment=TA_RIGHT)),
    ]
    item_data = [item_header]
    for idx, item in enumerate(record.get("items", []) or [], start=1):
        qty = _int_money(item.get("qty"))
        name = _pdf_escape(item.get("item_name") or item.get("name") or "")
        unit_price = _int_money(item.get("unit_price") or item.get("amount") or 0)
        item_gross = _int_money(item.get("gross")) or (unit_price * qty)
        item_subtotal = _int_money(item.get("subtotal"))
        item_disc = _int_money(item.get("line_discount")) or max(0, item_gross - item_subtotal)
        if item.get("free"):
            name += " <font color='#d97706'>[FREE]</font>"
        price_display = format_rupiah(unit_price) if unit_price else format_rupiah(item_subtotal)
        if item_disc and item_gross:
            price_display = f"<strike><font color='#9ca3af'>{format_rupiah(unit_price)}</font></strike>"
        item_data.append([
            Paragraph(str(idx), s_center),
            Paragraph(f"<b>{name}</b>", s_body),
            Paragraph(str(qty), s_center),
            Paragraph(price_display, s_right),
            Paragraph(f"<b>{format_rupiah(item_subtotal)}</b>", s_right_bold),
        ])
    if len(item_data) == 1:
        item_data.append(["-", Paragraph("Tidak ada item", s_body), "", "", Paragraph(format_rupiah(0), s_right)])
    item_table = Table(item_data, colWidths=[col_num, col_name, col_qty, col_price, col_sub], repeatRows=1)
    stripe_white = colors.white
    stripe_alt = colors.HexColor("#f8f9fc")
    item_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e1b4b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [stripe_white, stripe_alt]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, soft_line),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 0), (2, -1), "CENTER"),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 9),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))

    summary_rows = []
    sub_label = "Subtotal (gross)" if gross != amount or line_discount or cart_discount else "Subtotal"
    summary_rows.append([Paragraph(sub_label, s_body), Paragraph(format_rupiah(gross), s_right)])
    if line_discount:
        summary_rows.append([Paragraph("<font color='#d97706'>Potongan item</font>", s_body), Paragraph(f"<font color='#d97706'>- {format_rupiah(line_discount)}</font>", s_right)])
    if cart_discount:
        summary_rows.append([Paragraph("<font color='#d97706'>Potongan transaksi</font>", s_body), Paragraph(f"<font color='#d97706'>- {format_rupiah(cart_discount)}</font>", s_right)])
    if merchant:
        summary_rows.append([Paragraph("<font color='#d97706'>Biaya Pembayaran</font>", s_body), Paragraph(f"<font color='#d97706'>- {format_rupiah(fee)}</font>", s_right)])
        summary_rows.append([Paragraph("<font color='#059669'><b>Total Bersih (Net)</b></font>", s_bold), Paragraph(f"<font color='#059669'><b>{format_rupiah(amount - fee)}</b></font>", s_right_bold)])
    else:
        summary_rows.append([Paragraph("<font color='#059669'><b>Total Dibayar</b></font>", s_bold), Paragraph(f"<font color='#059669'><b>{format_rupiah(amount)}</b></font>", s_right_bold)])
    summary = Table(summary_rows, colWidths=[W - 140, 140])
    summary.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, soft_line),
        ("LINEBELOW", (0, -1), (-1, -1), 1.5, accent),
    ]))

    story = [accent_bar, Spacer(1, 16), header, Spacer(1, 14)]
    story.extend([info_table, Spacer(1, 8), total_box, Spacer(1, 14), detail_table, Spacer(1, 14)])
    story.extend([
        Paragraph("<b>Daftar Pesanan</b>", ParagraphStyle("sec2", parent=styles["Heading3"], fontSize=11, textColor=ink)),
        Spacer(1, 6), item_table, Spacer(1, 8), summary,
    ])

    if not merchant:
        note = Table([[
            Paragraph(
                "<font color='#92400e'><b>CATATAN</b></font><br/>"
                "<font color='#78716c'>Receipt ini merupakan bukti transaksi resmi. Simpan sebagai bukti pembayaran Anda.</font>",
                ParagraphStyle("note2", parent=s_small, leading=12),
            ),
        ]], colWidths=[W])
        note.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffbeb")),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("ROUNDEDCORNERS", [4, 4, 4, 4]),
        ]))
        story.extend([Spacer(1, 16), note])

    footer_brand = Table([[
        logo if logo else "",
        Paragraph(f"<b>{shop}</b><br/><font color='#6c727f' size='7'>Powered by Conlecta POS</font>", s_body),
    ]], colWidths=[44, W - 44])
    footer_brand.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.extend([
        Spacer(1, 20),
        HRFlowable(width="100%", thickness=0.5, color=soft_line),
        Spacer(1, 10),
        footer_brand,
        Spacer(1, 6),
        Paragraph(_pdf_escape(PDF_GENERATED_REMARK), s_small),
    ])

    _pdf_build(doc, story)
    buffer.seek(0)
    return buffer.getvalue()


def make_history_export_pdf(records, title="Invoice History"):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.enums import TA_RIGHT, TA_CENTER
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, Image
        from reportlab.graphics.shapes import Drawing, Rect
    except Exception as exc:
        raise RuntimeError(f"ReportLab unavailable: {exc}")

    settings = load_settings(current_merchant_id())
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    W = doc.width
    styles = getSampleStyleSheet()

    ink = colors.HexColor("#1a1a2e")
    muted = colors.HexColor("#6c727f")
    accent = colors.HexColor("#6366f1")
    emerald = colors.HexColor("#059669")
    amber = colors.HexColor("#d97706")
    soft_line = colors.HexColor("#e2e5ea")
    card_bg = colors.HexColor("#f8f9fc")

    s_title = ParagraphStyle("HT2", parent=styles["Title"], textColor=accent, fontSize=22, alignment=0, fontName="Helvetica-Bold")
    s_small = ParagraphStyle("HS2", parent=styles["BodyText"], fontSize=7.5, textColor=muted)
    s_cell = ParagraphStyle("HC2", parent=styles["BodyText"], fontSize=7.5, leading=10, textColor=ink)
    s_cell_r = ParagraphStyle("HCR2", parent=s_cell, alignment=TA_RIGHT)
    s_cell_c = ParagraphStyle("HCC2", parent=s_cell, alignment=TA_CENTER)
    s_head = ParagraphStyle("HH2", parent=s_small, textColor=colors.white, fontName="Helvetica-Bold")
    s_head_r = ParagraphStyle("HHR2", parent=s_head, alignment=TA_RIGHT)

    records = sorted(records, key=lambda r: parse_history_datetime(r.get("updated_at_display") or r.get("updated_at")) or datetime.min)
    gross = sum(discount_breakdown(r)["gross"] for r in records)
    total_discount = sum(discount_breakdown(r)["total_discount"] for r in records)
    paid_gross = sum(_int_money(r.get("amount")) for r in records)
    qris_fee = sum(
        0 if derive_payment_method(r.get("payment_method"), r.get("cash_received"), r.get("change"), r.get("qr_id")) == PAYMENT_METHOD_CASH else calc_qris_fee(r.get("amount"))
        for r in records
    )

    accent_bar = Drawing(W, 4)
    accent_bar.add(Rect(0, 0, W, 4, fillColor=accent, strokeColor=None))

    shop = _pdf_escape(settings.get("shop_name") or "Conlecta")
    logo = _pdf_logo(settings, Image, 36)
    header_left = [[logo if logo else "", Paragraph(f"<b>{shop}</b>", s_cell)]]
    header_brand = Table(header_left, colWidths=[42, 180])
    header_brand.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))

    header = Table([[
        header_brand,
        Paragraph(f"<b>{_pdf_escape(title)}</b><br/><font color='#6c727f' size='7'>Generated: {datetime.now().strftime('%d %B %Y %H:%M')}</font>", ParagraphStyle("hr2", parent=s_cell, alignment=TA_RIGHT, fontSize=14)),
    ]], colWidths=[W * 0.45, W * 0.55])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))

    kpi_style = ParagraphStyle("kpi2", parent=s_small, fontSize=7, leading=10)
    kpi_val = ParagraphStyle("kpiv2", parent=s_cell, fontSize=10, fontName="Helvetica-Bold", leading=14)
    kpi_data = [[
        Paragraph(f"TRANSAKSI<br/><br/><font size='10'><b>{len(records)}</b></font>", kpi_style),
        Paragraph(f"GROSS<br/><br/><font size='10'><b>{format_rupiah(gross)}</b></font>", kpi_style),
        Paragraph(f"DISKON<br/><br/><font color='#d97706' size='10'><b>{format_rupiah(total_discount)}</b></font>", kpi_style),
        Paragraph(f"BIAYA<br/><br/><font color='#d97706' size='10'><b>{format_rupiah(qris_fee)}</b></font>", kpi_style),
        Paragraph(f"<font color='#059669'>NET REVENUE<br/><br/><font size='10'><b>{format_rupiah(paid_gross - qris_fee)}</b></font></font>", kpi_style),
    ]]
    kpi_table = Table(kpi_data, colWidths=[W / 5] * 5)
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), card_bg),
        ("PADDING", (0, 0), (-1, -1), 12),
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, soft_line),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, soft_line),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))

    story = [accent_bar, Spacer(1, 12), header, Spacer(1, 14), kpi_table, Spacer(1, 14)]

    col_widths = [100, 120, 120, 58, 100, 72, 72]
    remaining = W - sum(col_widths)
    if remaining > 0:
        col_widths[1] += remaining * 0.4
        col_widths[2] += remaining * 0.3
        col_widths[4] += remaining * 0.3

    rows = [[Paragraph(x, s_head if i < 5 else s_head_r) for i, x in enumerate(["TXN ID", "TANGGAL", "PELANGGAN", "METODE", "KASIR", "DISKON", "JUMLAH"])]]
    for rec in records:
        rec_discount = discount_breakdown(rec)["total_discount"]
        meth = derive_payment_method(rec.get("payment_method"), rec.get("cash_received"), rec.get("change"), rec.get("qr_id"))
        meth_color = "#059669" if meth == PAYMENT_METHOD_CASH else "#6366f1"
        rows.append([
            Paragraph(_pdf_escape(rec.get("txn_id", "")), s_cell),
            Paragraph(_pdf_escape(rec.get("updated_at_display") or rec.get("updated_at", "")), s_cell),
            Paragraph(_pdf_escape(rec.get("customer_name") or rec.get("customer") or ""), s_cell),
            Paragraph(f"<font color='{meth_color}'><b>{_pdf_escape(meth)}</b></font>", s_cell_c),
            Paragraph(_pdf_escape(rec.get("cashier_name", "")), s_cell),
            Paragraph(f"<font color='#d97706'>{format_rupiah(rec_discount)}</font>" if rec_discount else "-", s_cell_r),
            Paragraph(f"<b>{format_rupiah(rec.get('amount', 0))}</b>", s_cell_r),
        ])
    rows.append([
        "", "", "", "", Paragraph("<b>TOTAL</b>", s_cell),
        Paragraph(f"<b>{format_rupiah(total_discount)}</b>", s_cell_r),
        Paragraph(f"<font color='#059669'><b>{format_rupiah(paid_gross)}</b></font>", s_cell_r),
    ])
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e1b4b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, card_bg]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.2, soft_line),
        ("ALIGN", (-2, 1), (-1, -1), "RIGHT"),
        ("PADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 9),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, ink),
        ("ROUNDEDCORNERS", [4, 4, 0, 0]),
    ]))
    story.extend([table, Spacer(1, 10), Paragraph(_pdf_escape(PDF_GENERATED_REMARK), s_small)])
    _pdf_build(doc, story)
    buffer.seek(0)
    return buffer.getvalue()


def make_vendor_invoice_pdf(payload):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.enums import TA_RIGHT, TA_CENTER
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, Image
        from reportlab.graphics.shapes import Drawing, Rect
    except Exception as exc:
        raise RuntimeError(f"ReportLab unavailable: {exc}")

    rows_data = payload.get("rows", [])
    totals = payload.get("totals", {})
    vendor = payload.get("selected_vendor", "(All)")
    settings = load_settings(current_merchant_id())
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=48, bottomMargin=40)
    W = doc.width
    styles = getSampleStyleSheet()

    ink = colors.HexColor("#1a1a2e")
    muted = colors.HexColor("#6c727f")
    accent = colors.HexColor("#6366f1")
    emerald = colors.HexColor("#059669")
    amber = colors.HexColor("#d97706")
    soft_line = colors.HexColor("#e2e5ea")
    card_bg = colors.HexColor("#f8f9fc")

    s_title = ParagraphStyle("VT2", parent=styles["Title"], textColor=accent, fontSize=20, alignment=0, fontName="Helvetica-Bold")
    s_right = ParagraphStyle("VR2", parent=styles["BodyText"], fontSize=8, leading=11, textColor=ink, alignment=TA_RIGHT)
    s_small = ParagraphStyle("VS2", parent=styles["BodyText"], fontSize=7.5, leading=10, textColor=muted)
    s_cell = ParagraphStyle("VC2", parent=styles["BodyText"], fontSize=7.5, leading=10, textColor=ink)
    s_cell_r = ParagraphStyle("VCR2", parent=s_cell, alignment=TA_RIGHT)
    s_cell_c = ParagraphStyle("VCC2", parent=s_cell, alignment=TA_CENTER)
    s_head = ParagraphStyle("VH2", parent=s_small, textColor=colors.white, fontName="Helvetica-Bold")
    s_head_r = ParagraphStyle("VHR2", parent=s_head, alignment=TA_RIGHT)
    s_head_c = ParagraphStyle("VHC2", parent=s_head, alignment=TA_CENTER)

    accent_bar = Drawing(W, 4)
    accent_bar.add(Rect(0, 0, W, 4, fillColor=accent, strokeColor=None))

    shop = _pdf_escape(settings.get("shop_name") or "Conlecta")
    logo = _pdf_logo(settings, Image, 40)
    brand_cell = Table([[logo if logo else "", Paragraph(f"<b>{shop}</b>", s_cell)]], colWidths=[46, 160])
    brand_cell.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))

    header = Table([[
        brand_cell,
        Paragraph(f"<b>VENDOR INVOICE</b><br/><font color='#6c727f' size='7'>{_pdf_escape(vendor)}</font><br/><font color='#6c727f' size='7'>Generated: {datetime.now().strftime('%d %B %Y %H:%M')}</font>", ParagraphStyle("vhr2", parent=s_cell, alignment=TA_RIGHT, fontSize=13)),
    ]], colWidths=[W * 0.5, W * 0.5])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))

    total_cost = totals.get("cost", totals.get("subtotal", 0))
    total_sales = totals.get("subtotal", 0)
    total_profit = totals.get("profit", total_sales - total_cost if total_sales else 0)
    kpi_data = [[
        Paragraph(f"TRANSAKSI<br/><br/><font size='10'><b>{len(rows_data)}</b></font>", s_small),
        Paragraph(f"TOTAL QTY<br/><br/><font size='10'><b>{totals.get('qty', 0)}</b></font>", s_small),
        Paragraph(f"MODAL VENDOR<br/><br/><font color='#d97706' size='10'><b>{format_rupiah(total_cost)}</b></font>", s_small),
        Paragraph(f"<font color='#059669'>PROFIT<br/><br/><font size='10'><b>{format_rupiah(total_profit)}</b></font></font>", s_small),
    ]]
    kpi_table = Table(kpi_data, colWidths=[W / 4] * 4)
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), card_bg),
        ("PADDING", (0, 0), (-1, -1), 12),
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, soft_line),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, soft_line),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))

    col_widths = [68, 70, 100, 30, 52, 52, 52, 52]
    remaining = W - sum(col_widths)
    if remaining > 0:
        col_widths[2] += remaining

    table_rows = [[
        Paragraph("TXN ID", s_head),
        Paragraph("TANGGAL", s_head),
        Paragraph("ITEM", s_head),
        Paragraph("QTY", s_head_c),
        Paragraph("MODAL", s_head_r),
        Paragraph("COST", s_head_r),
        Paragraph("SALES", s_head_r),
        Paragraph("PROFIT", s_head_r),
    ]]
    for row in rows_data:
        profit = row.get("profit", 0)
        profit_color = "#059669" if profit >= 0 else "#dc2626"
        table_rows.append([
            Paragraph(_pdf_escape(row.get("txn", "")), s_cell),
            Paragraph(_pdf_escape(row.get("date", "")), s_cell),
            Paragraph(f"<b>{_pdf_escape(row.get('item', ''))}</b>", s_cell),
            Paragraph(str(row.get("qty", 0)), s_cell_c),
            Paragraph(format_rupiah(row.get("capital", 0)), s_cell_r),
            Paragraph(format_rupiah(row.get("cost", 0)), s_cell_r),
            Paragraph(format_rupiah(row.get("subtotal", 0)), s_cell_r),
            Paragraph(f"<font color='{profit_color}'><b>{format_rupiah(profit)}</b></font>", s_cell_r),
        ])
    if len(table_rows) == 1:
        table_rows.append(["-", "-", Paragraph("Tidak ada transaksi", s_cell), "0", format_rupiah(0), format_rupiah(0), format_rupiah(0), format_rupiah(0)])

    table = Table(table_rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e1b4b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, card_bg]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.2, soft_line),
        ("ALIGN", (3, 1), (3, -1), "CENTER"),
        ("ALIGN", (4, 1), (-1, -1), "RIGHT"),
        ("PADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 9),
        ("ROUNDEDCORNERS", [4, 4, 0, 0]),
    ]))
    story = [accent_bar, Spacer(1, 12), header, Spacer(1, 14), kpi_table, Spacer(1, 16), table, Spacer(1, 10), Paragraph(_pdf_escape(PDF_GENERATED_REMARK), s_small)]
    _pdf_build(doc, story)
    buffer.seek(0)
    return buffer.getvalue()


def find_record(txn_id):
    for record in load_history():
        if str(record.get("txn_id")) == str(txn_id):
            return record
    return None


def _log_line_timestamp(line):
    text = str(line or "")
    stamp = text[:23]
    for fmt in ("%Y-%m-%d %H:%M:%S,%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(stamp[:23 if "%f" in fmt else 19], fmt).timestamp()
        except Exception:
            pass
    return 0.0


def _auth_log_start_ts(auth=None):
    auth = auth or current_auth()
    return _auth_timestamp(auth.get("log_start_ts")) or _auth_timestamp(auth.get("login_ts"))


def load_logs(limit=220, auth=None):
    auth = auth or current_auth()
    start_ts = _auth_log_start_ts(auth)
    paths = [
        os.path.join(LOGS_DIR, "conlecta_web.log"),
        os.path.join(LOGS_DIR, "conlecta_system.log"),
    ]
    lines = []
    for path in paths:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines.extend(f.readlines()[-limit:])
        except Exception:
            pass
    scoped = []
    for line in lines:
        if start_ts:
            line_ts = _log_line_timestamp(line)
            if line_ts and line_ts < start_ts:
                continue
        scoped.append(line.rstrip("\n"))
    return scoped[-limit:]


def clear_current_log_window():
    state = load_state()
    auth = state.get("auth") or {}
    if not auth:
        return
    auth["log_start_ts"] = time.time()
    state["auth"] = auth
    save_state(state)
    log.info("Session log window cleared for account=%s", auth.get("id") or "-")


def public_asset_url(path, fallback_logo=False):
    if str(path or "").strip().startswith("data:"):
        return str(path or "").strip()
    if path and os.path.isfile(path):
        full = os.path.abspath(path)
        assets_abs = os.path.abspath(ASSETS_DIR)
        full_cmp = os.path.normcase(full)
        assets_cmp = os.path.normcase(assets_abs)
        try:
            common = os.path.commonpath([full_cmp, assets_cmp])
        except Exception:
            common = ""
        if common == assets_cmp:
            rel = os.path.relpath(full, BASE_DIR).replace(os.sep, "/")
            return "/" + rel
    if fallback_logo and os.path.isfile(BRAND_DEFAULT_LOGO):
        return "/assets/ConlectaPosLogo.png"
    if fallback_logo and os.path.isfile(BRAND_EMAIL_LOGO):
        return "/assets/Email/ConlectaIcon.png"
    return ""


def default_payment_icon_paths():
    candidates = [
        "Gsingapay.jpeg",
        "MyBca.jpg",
        "OVO.jpg",
        "Qris.png",
        "eGopay.png",
        "images (1).png",
        "images.jpg",
        "shopee-pay-logo-png_seeklogo-406839.png",
    ]
    return [os.path.join(ASSETS_DIR, "Icon", name) for name in candidates if os.path.isfile(os.path.join(ASSETS_DIR, "Icon", name))]


def configured_payment_image_paths(settings=None):
    settings = settings or load_settings()
    paths = [str(path or "").strip() for path in settings.get("payment_image_paths", []) if str(path or "").strip()]
    single = str(settings.get("payment_image_path", "") or "").strip()
    if single and single not in paths:
        paths.append(single)
    paths = [path for path in paths if os.path.isfile(path)]
    return paths or default_payment_icon_paths()


def video_playlist_urls(settings=None):
    settings = settings or load_settings()
    urls = []
    for value in settings.get("video_playlist", []) or []:
        text = str(value or "").strip()
        if not text:
            continue
        if text.startswith("/assets/"):
            path = safe_path(BASE_DIR, text)
        else:
            path = text
        url = public_asset_url(path)
        if url:
            urls.append(url)
    if not urls and os.path.isfile(SPLASH_VIDEO):
        urls.append("/assets/videos/Splash.mp4")
    return urls


def scan_asset_payload():
    video_files = []
    for path in sorted(glob.glob(os.path.join(VIDEO_FOLDER, "*.mp4"))):
        video_files.append({
            "name": os.path.basename(path),
            "url": public_asset_url(path),
            "path": path,
            "size_mb": round(os.path.getsize(path) / (1024 * 1024), 1),
        })
    return {
        "videos": video_files,
        "payment_icons": [{"name": os.path.basename(path), "url": public_asset_url(path), "path": path} for path in default_payment_icon_paths()],
    }


def _decode_data_file(data_url):
    raw = str(data_url or "")
    if "," in raw:
        raw = raw.split(",", 1)[1]
    return base64.b64decode(raw)


def save_payment_images(data):
    mid = current_merchant_id()
    files = data.get("files") or []
    if not files:
        raise ValueError("Pilih minimal satu gambar payment.")
    dst_dir = os.path.join(PAYMENT_UPLOAD_FOLDER, mid)
    os.makedirs(dst_dir, exist_ok=True)
    saved = []
    for index, file_data in enumerate(files, start=1):
        filename = str(file_data.get("filename") or f"payment_{index}.png")
        base = os.path.splitext(os.path.basename(filename))[0]
        safe_base = "".join(ch if ch.isalnum() else "_" for ch in base).strip("_").lower() or f"payment_{index}"
        ext = os.path.splitext(filename)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
            ext = ".png"
        dst = os.path.join(dst_dir, f"{index:02d}_{safe_base}{ext}")
        with open(dst, "wb") as f:
            f.write(_decode_data_file(file_data.get("data_url")))
        saved.append(dst)
    settings = load_settings(mid)
    settings["payment_image_paths"] = saved
    settings["payment_image_path"] = saved[0] if saved else ""
    return _write_settings_for_merchant(settings, mid)


def save_video_upload(data):
    filename = os.path.basename(str(data.get("filename") or "video.mp4"))
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".mp4", ".mov", ".mkv", ".avi", ".webm"):
        ext = ".mp4"
    safe_name = f"web_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
    os.makedirs(VIDEO_FOLDER, exist_ok=True)
    dst = os.path.join(VIDEO_FOLDER, safe_name)
    with open(dst, "wb") as f:
        f.write(_decode_data_file(data.get("data_url")))
    return {"name": os.path.basename(dst), "url": public_asset_url(dst), "path": dst}


def _video_path_from_value(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("/assets/"):
        path = safe_path(BASE_DIR, text)
    else:
        path = text
    if not path:
        return ""
    full = os.path.abspath(path)
    video_root = os.path.abspath(VIDEO_FOLDER)
    try:
        common = os.path.commonpath([os.path.normcase(full), os.path.normcase(video_root)])
    except Exception:
        return ""
    if common != os.path.normcase(video_root):
        return ""
    return full


def remove_video_asset(data):
    mid = current_merchant_id()
    target = _video_path_from_value(data.get("path") or data.get("url"))
    if not target:
        raise ValueError("Video tidak valid.")
    target_url = public_asset_url(target)
    settings = load_settings(mid)
    playlist = []
    for value in settings.get("video_playlist", []) or []:
        value_path = _video_path_from_value(value)
        value_url = public_asset_url(value_path) if value_path else str(value or "")
        if os.path.normcase(value_path or "") == os.path.normcase(target):
            continue
        if target_url and value_url == target_url:
            continue
        playlist.append(value)
    settings["video_playlist"] = playlist
    if os.path.isfile(target):
        os.remove(target)
    saved = _write_settings_for_merchant(settings, mid)
    log.info("Video removed from web settings: merchant=%s file=%s", mid, os.path.basename(target))
    return {"settings": saved, "assets": scan_asset_payload()}


def settings_payload(settings=None, merchant_id=None):
    mid = normalize_merchant_id(merchant_id or (settings or {}).get("merchant_id") or current_merchant_id())
    settings = dict(settings or load_settings(mid))
    merchant = merchant_payload(mid)
    if merchant.get("name") and (not settings.get("shop_name") or (mid != DEFAULT_MERCHANT_ID and settings.get("shop_name") == DEFAULT_MERCHANT_NAME)):
        settings["shop_name"] = merchant["name"]
    if not settings.get("brand_logo_path") and merchant.get("logo_path"):
        settings["brand_logo_path"] = merchant["logo_path"]
    settings["merchant_id"] = mid
    settings["merchant_name"] = merchant.get("name") or settings.get("shop_name") or DEFAULT_MERCHANT_NAME
    settings["brand_logo_url"] = (
        public_asset_url(settings.get("brand_logo_path"))
        or merchant.get("logo_data_url")
        or public_asset_url(BRAND_DEFAULT_LOGO, fallback_logo=True)
    )
    settings["payment_image_urls"] = [public_asset_url(path) for path in configured_payment_image_paths(settings)]
    settings["payment_image_urls"] = [url for url in settings["payment_image_urls"] if url]
    settings["video_playlist_urls"] = video_playlist_urls(settings)
    settings["qris_vps_env_var"] = "CONLECTA_QRIS_VPS_URL"
    return settings


def display_settings_payload(merchant_id=None):
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    settings = dict(load_settings(mid))
    merchant = merchant_payload(mid)
    settings["merchant_id"] = mid
    settings["merchant_name"] = settings.get("shop_name") or merchant.get("name") or DEFAULT_MERCHANT_NAME
    settings["brand_logo_url"] = (
        public_asset_url(settings.get("brand_logo_path"))
        or merchant.get("logo_data_url")
        or public_asset_url(BRAND_DEFAULT_LOGO, fallback_logo=True)
    )
    settings["payment_image_urls"] = [public_asset_url(path) for path in configured_payment_image_paths(settings)]
    settings["payment_image_urls"] = [url for url in settings["payment_image_urls"] if url]
    settings["video_playlist_urls"] = video_playlist_urls(settings)
    settings["qris_vps_env_var"] = "CONLECTA_QRIS_VPS_URL"
    return settings


def save_brand_logo(data):
    mid = current_merchant_id()
    data_url = str(data.get("data_url") or "")
    filename = str(data.get("filename") or "brand_logo.png")
    if "," in data_url:
        meta, b64 = data_url.split(",", 1)
    else:
        meta, b64 = "", data_url
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".ico"):
        ext = ".png"
    blob = base64.b64decode(b64)
    dst_dir = os.path.join(ASSETS_DIR, "Brand")
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, f"{mid}_brand_logo{ext}")
    with open(dst, "wb") as f:
        f.write(blob)
    settings = load_settings(mid)
    settings["brand_logo_path"] = dst
    sync_merchant_from_settings(settings, mid)
    log.info("Brand logo uploaded from web: %s", dst)
    return _write_settings_for_merchant(settings, mid)


def safe_path(root, request_path):
    rel = unquote(request_path).lstrip("/").replace("/", os.sep)
    full = os.path.abspath(os.path.join(root, rel))
    root_abs = os.path.abspath(root)
    if full != root_abs and not full.startswith(root_abs + os.sep):
        return None
    return full


class ConlectaWebHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
    super().end_headers()

    server_version = "ConlectaWeb/2.0"

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def log_message(self, fmt, *args):
        log.debug("%s - %s", self.address_string(), fmt % args)

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def send_json(self, data, status=200):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def send_bytes(self, data, content_type, filename=None):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, exc, status=400):
        log.warning("API error: %s", exc)
        self.send_json({"ok": False, "error": str(exc)}, status)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        app_path = path.rstrip("/") or "/"
        try:
            if path.startswith("/api/"):
                return self.handle_api_get(path, parse_qs(parsed.query))
            if app_path in ("", "/", "/login", "/otp", "/pin", "/pin-register", "/cashier", "/stock", "/analytics", "/history", "/settings", "/log", "/system-admin"):
                return self.serve_file(os.path.join(WEB_DIR, "index.html"))
            if app_path in ("/qr-display", "/qr-display.html"):
                return self.serve_file(os.path.join(WEB_DIR, "qr-display.html"))
            if path.startswith("/assets/"):
                return self.serve_file(safe_path(BASE_DIR, path))
            if path in ("/styles.css", "/app.js", "/qr-display.js", "/theme-pack.css", "/theme-engine.js"):
                return self.serve_file(os.path.join(WEB_DIR, path.lstrip("/")))
            return self.send_error(404, "Not found")
        except Exception as exc:
            return self.send_error_json(exc, 500)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            if not parsed.path.startswith("/api/"):
                return self.send_error(404, "Not found")
            return self.handle_api_post(parsed.path, self.read_json())
        except Exception as exc:
            return self.send_error_json(exc, 500)

    def serve_file(self, path):
        if not path or not os.path.isfile(path):
            return self.send_error(404, "File not found")
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def handle_api_get(self, path, query):
        if path == "/api/display-state":
            state = load_state()
            mid = display_state_merchant_id(state)
            bucket = _state_tenant_bucket(state, mid)
            display_event = current_display_event(state, mid)
            cashier_notice = current_cashier_payment_notice(state, mid)
            active_qr = current_active_qr(state, mid)
            save_state(state)
            return self.send_json({
                "ok": True,
                "settings": display_settings_payload(mid),
                "active_qr": active_qr,
                "display_event": display_event,
                "cashier_notice": cashier_notice,
                "version": load_version_info(),
            })
        if path == "/api/bootstrap":
            state = load_state()
            auth = validate_stored_auth(state)
            mid = normalize_merchant_id((auth or {}).get("merchant_id") or DEFAULT_MERCHANT_ID)
            if auth:
                acc = _find_account_by_id(auth.get("id")) if auth.get("id") else None
                if acc:
                    auth["role"] = "system_admin" if _is_system_admin_account(acc) else (auth.get("role") or "cashier")
                    auth["email"] = auth.get("email") or acc.get("email", "")
                    auth["merchant_id"] = normalize_merchant_id(auth.get("merchant_id") or acc.get("merchant_id"))
                    auth["admin_account"] = bool(acc.get("admin_account"))
                elif not auth.get("role"):
                    auth["role"] = "cashier"
                if not auth.get("merchant_id"):
                    auth["merchant_id"] = mid
                if not auth.get("merchant_name"):
                    auth["merchant_name"] = merchant_payload(mid).get("name") or DEFAULT_MERCHANT_NAME
                auth["last_seen_ts"] = time.time()
                auth["last_activity_ts"] = _auth_last_activity_ts(auth, acc)
                auth["session_day"] = auth.get("session_day") or _session_business_day()
                mid = normalize_merchant_id(auth.get("merchant_id") or mid)
            if (state.get("auth") or {}).get("role") == "system_admin":
                save_state(state)
                return self.send_json({
                    "ok": True,
                    "auth": state.get("auth"),
                    "settings": settings_payload(merchant_id=DEFAULT_MERCHANT_ID),
                    "products": [],
                    "vendors": [],
                    "history": [],
                    "active_qr": None,
                    "display_event": None,
                    "session": {"sales": 0, "revenue": 0},
                    "session_day": _session_business_day(),
                    "session_reset_at": _next_session_reset_at(),
                    "version": load_version_info(),
                    "system_admin": system_admin_payload(),
                    "logs": [],
                    "assets": scan_asset_payload(),
                })
            bucket = _ensure_daily_session(state, mid)
            display_event = current_display_event(state, mid)
            active_qr = current_active_qr(state, mid)
            products = load_stock(merchant_id=mid)
            bucket["products"] = products
            _sync_legacy_state_for_default(state, mid)
            save_state(state)
            return self.send_json({
                "ok": True,
                "auth": state.get("auth"),
                "settings": settings_payload(merchant_id=mid),
                "products": products,
                "vendors": load_vendors(merchant_id=mid),
                "history": load_history(),
                "active_qr": active_qr,
                "display_event": display_event,
                "session": bucket.get("session", {"sales": 0, "revenue": 0}),
                "session_day": bucket.get("session_day"),
                "session_reset_at": bucket.get("session_reset_at"),
                "version": load_version_info(),
                "logs": [],
                "assets": scan_asset_payload(),
            })
        if path == "/api/stock":
            return self.send_json({"ok": True, "products": load_stock(force=True)})
        if path == "/api/vendors":
            return self.send_json({"ok": True, "vendors": load_vendors()})
        if path == "/api/assets":
            return self.send_json({"ok": True, "assets": scan_asset_payload(), "settings": settings_payload()})
        if path == "/api/email-templates":
            return self.send_json({"ok": True, "templates": load_email_templates()})
        if path == "/api/history":
            return self.send_json({"ok": True, "history": load_history()})
        if path == "/api/system-admin/transactions":
            try:
                payload = admin_transactions_payload((query.get("merchant_id") or [""])[0])
            except PermissionError as exc:
                return self.send_error_json(exc, 403)
            except Exception as exc:
                return self.send_error_json(exc, 400)
            return self.send_json({"ok": True, **payload})
        if path == "/api/logs":
            password = (query.get("admin_password") or [""])[0]
            ok, msg = verify_system_log_password(password)
            if not ok:
                return self.send_error_json(msg, 403)
            return self.send_json({"ok": True, "logs": load_logs(260)})
        if path == "/api/qris/env":
            env_name, detail = qris_proxy_environment()
            return self.send_json({"ok": True, "environment": env_name, "detail": detail})
        if path == "/api/vendor-invoice":
            payload = vendor_invoice_payload(
                vendor_id=(query.get("vendor_id") or [""])[0],
                vendor_name=(query.get("vendor_name") or [""])[0],
                date_from=(query.get("from") or [""])[0],
                date_to=(query.get("to") or [""])[0],
            )
            return self.send_json({"ok": True, **payload})
        if path == "/api/vendor-invoice.pdf":
            payload = vendor_invoice_payload(
                vendor_id=(query.get("vendor_id") or [""])[0],
                vendor_name=(query.get("vendor_name") or [""])[0],
                date_from=(query.get("from") or [""])[0],
                date_to=(query.get("to") or [""])[0],
            )
            name = str(payload.get("selected_vendor", "all")).replace(" ", "_")
            return self.send_bytes(make_vendor_invoice_pdf(payload), "application/pdf", f"vendor-invoice-{name}.pdf")
        if path == "/api/qr/status":
            qr_id = (query.get("id") or [""])[0]
            return self.send_json({"ok": True, **active_qr_status(qr_id)})
        if path == "/api/receipt.pdf":
            txn_id = (query.get("txn_id") or [""])[0]
            record = find_record(txn_id)
            if not record:
                return self.send_error_json("Transaction not found", 404)
            return self.send_bytes(make_pdf(record, merchant=False), "application/pdf", f"receipt-{txn_id}.pdf")
        if path == "/api/merchant.pdf":
            txn_id = (query.get("txn_id") or [""])[0]
            record = find_record(txn_id)
            if not record:
                return self.send_error_json("Transaction not found", 404)
            return self.send_bytes(make_pdf(record, merchant=True), "application/pdf", f"merchant-{txn_id}.pdf")
        return self.send_error_json("Unknown API route", 404)

    def handle_api_post(self, path, data):
        if path == "/api/auth/login":
            try:
                pending = begin_login(data.get("login"), data.get("password"))
            except Exception as exc:
                return self.send_error_json(exc, 400)
            message = "Masukkan PIN." if pending.get("mode") == "pin" else "Register PIN baru."
            return self.send_json({"ok": True, "pending": pending, "message": message})
        if path == "/api/auth/forgot-pin":
            try:
                pending = begin_forgot_pin(data.get("account_id"))
            except Exception as exc:
                return self.send_error_json(exc, 400)
            return self.send_json({"ok": True, "pending": pending, "message": "OTP reset PIN dikirim ke email."})
        if path == "/api/auth/resend-otp":
            try:
                pending = resend_login_otp(data.get("account_id"))
            except Exception as exc:
                return self.send_error_json(exc, 400)
            return self.send_json({"ok": True, "pending": pending, "message": "OTP baru dikirim."})
        if path == "/api/auth/verify":
            try:
                verified = verify_login_otp(data.get("account_id"), data.get("otp"))
            except Exception as exc:
                return self.send_error_json(exc, 400)
            if verified.get("pending"):
                return self.send_json({"ok": True, "pending": verified["pending"], "message": "OTP benar. Register PIN baru."})
            auth = verified.get("auth") or {}
            body = {"ok": True, "auth": auth, "settings": settings_payload(merchant_id=auth.get("merchant_id"))}
            if auth.get("role") == "system_admin":
                body["system_admin"] = system_admin_payload()
            return self.send_json(body)
        if path == "/api/auth/verify-pin":
            try:
                auth = verify_login_pin(data.get("account_id"), data.get("pin"))
            except Exception as exc:
                return self.send_error_json(exc, 400)
            body = {"ok": True, "auth": auth, "settings": settings_payload(merchant_id=auth.get("merchant_id"))}
            if auth.get("role") == "system_admin":
                body["system_admin"] = system_admin_payload()
            return self.send_json(body)
        if path == "/api/auth/register-pin":
            try:
                auth = register_login_pin(data.get("account_id"), data.get("pin"), data.get("confirm_pin"))
            except Exception as exc:
                return self.send_error_json(exc, 400)
            body = {"ok": True, "auth": auth, "settings": settings_payload(merchant_id=auth.get("merchant_id"))}
            if auth.get("role") == "system_admin":
                body["system_admin"] = system_admin_payload()
            return self.send_json(body)
        if path == "/api/auth/logout":
            logout_current_account()
            return self.send_json({"ok": True})
        if path == "/api/auth/heartbeat":
            state = load_state()
            auth = validate_stored_auth(state, refresh_seen=True, activity_ts=data.get("last_activity_ts"))
            save_state(state)
            return self.send_json({"ok": True, "auth": auth})
        if path == "/api/auth/local-exit":
            exit_current_account_locally()
            return self.send_json({"ok": True})
        if path == "/api/admin/verify":
            ok, msg = verify_admin_password(data.get("admin_password"), current_merchant_id())
            if not ok:
                return self.send_error_json(msg, 403)
            return self.send_json({"ok": True})
        if path == "/api/account/register":
            mid = current_merchant_id()
            ok, msg = verify_admin_password(data.get("admin_password"), mid)
            if not ok:
                return self.send_error_json(msg, 403)
            ok, msg = create_account_record(data.get("name"), data.get("email"), data.get("password"), mid)
            if not ok:
                return self.send_error_json(msg, 400)
            return self.send_json({"ok": True, "message": msg, "merchant_id": mid})
        if path == "/api/system-admin/merchant/save":
            try:
                merchant = save_system_merchant(data)
            except PermissionError as exc:
                return self.send_error_json(exc, 403)
            return self.send_json({"ok": True, "merchant": merchant, "system_admin": system_admin_payload()})
        if path == "/api/system-admin/account/create":
            try:
                require_system_admin()
            except PermissionError as exc:
                return self.send_error_json(exc, 403)
            ok, msg = create_account_record(
                data.get("name"), data.get("email"), data.get("password"),
                data.get("merchant_id"), bool(data.get("admin_account")),
            )
            if not ok:
                return self.send_error_json(msg, 400)
            return self.send_json({"ok": True, "message": msg, "system_admin": system_admin_payload()})
        if path == "/api/system-admin/account/update":
            try:
                require_system_admin()
            except PermissionError as exc:
                return self.send_error_json(exc, 403)
            ok, msg = update_account_record(
                data.get("account_id"), data.get("name"), data.get("email"),
                data.get("password"), data.get("merchant_id"), bool(data.get("admin_account")),
            )
            if not ok:
                return self.send_error_json(msg, 400)
            return self.send_json({"ok": True, "message": msg, "system_admin": system_admin_payload()})
        if path == "/api/system-admin/version/save":
            try:
                version = save_version_info(data)
            except PermissionError as exc:
                return self.send_error_json(exc, 403)
            return self.send_json({"ok": True, "version": version, "system_admin": system_admin_payload()})
        if path == "/api/system-admin/transaction/update":
            try:
                updated = update_system_transaction(data)
            except PermissionError as exc:
                return self.send_error_json(exc, 403)
            except Exception as exc:
                return self.send_error_json(exc, 400)
            return self.send_json({"ok": True, **updated})
        if path == "/api/vendor/save":
            vendor = save_vendor(data.get("name"))
            return self.send_json({"ok": True, "vendor": vendor, "vendors": load_vendors()})
        if path == "/api/vendor/delete":
            delete_vendor(data.get("vendor_id"))
            return self.send_json({"ok": True, "vendors": load_vendors()})
        if path == "/api/settings":
            mid = current_merchant_id()
            incoming = dict(data.get("settings", data) or {})
            current = load_settings(mid)
            identity_changed = (
                str(incoming.get("shop_name", current.get("shop_name", ""))).strip() != str(current.get("shop_name", "")).strip()
            )
            if identity_changed:
                ok, msg = verify_admin_password(data.get("admin_password") or incoming.get("admin_password"), mid)
                if not ok:
                    return self.send_error_json(msg, 403)
            incoming.pop("admin_password", None)
            return self.send_json({"ok": True, "settings": save_settings(incoming, mid)})
        if path == "/api/brand-logo":
            mid = current_merchant_id()
            ok, msg = verify_admin_password(data.get("admin_password"), mid)
            if not ok:
                return self.send_error_json(msg, 403)
            return self.send_json({"ok": True, "settings": save_brand_logo(data)})
        if path == "/api/payment-images":
            return self.send_json({"ok": True, "settings": save_payment_images(data)})
        if path == "/api/video-upload":
            saved = save_video_upload(data)
            return self.send_json({"ok": True, "video": saved, "assets": scan_asset_payload()})
        if path == "/api/video/remove":
            try:
                removed = remove_video_asset(data)
            except Exception as exc:
                return self.send_error_json(exc, 400)
            return self.send_json({"ok": True, **removed})
        if path == "/api/email-template":
            saved = save_email_template(data.get("key"), data.get("template", {}))
            return self.send_json({"ok": True, "saved": saved, "templates": load_email_templates()})
        if path == "/api/stock/save":
            products = save_stock(data.get("products", []), current_merchant_id())
            return self.send_json({"ok": True, "products": products})
        if path == "/api/checkout/cash":
            try:
                record = save_transaction(data, PAYMENT_METHOD_CASH)
            except Exception as exc:
                return self.send_error_json(exc, 400)
            mid = current_merchant_id()
            state = load_state()
            bucket = _ensure_daily_session(state, mid)
            display_event = current_display_event(state, mid)
            save_state(state)
            return self.send_json({
                "ok": True, "record": record,
                "products": bucket.get("products", []),
                "history": bucket.get("history", []),
                "session": bucket.get("session"),
                "display_event": display_event,
            })
        if path == "/api/checkout/qris-success":
            try:
                record = save_transaction(data, PAYMENT_METHOD_QRIS)
            except Exception as exc:
                return self.send_error_json(exc, 400)
            mid = current_merchant_id()
            state = load_state()
            bucket = _ensure_daily_session(state, mid)
            display_event = current_display_event(state, mid)
            save_state(state)
            return self.send_json({
                "ok": True, "record": record,
                "products": bucket.get("products", []),
                "history": bucket.get("history", []),
                "session": bucket.get("session"),
                "display_event": display_event,
            })
        if path == "/api/qr/generate":
            mid = current_merchant_id()
            items = normalize_items(data.get("items", []), PAYMENT_METHOD_QRIS)
            if not items:
                return self.send_error_json("Keranjang kosong.", 400)
            try:
                load_and_validate_stock_for_items(items, merchant_id=mid)
            except Exception as exc:
                return self.send_error_json(exc, 400)
            qris = generate_qris(data)
            active = dict(qris)
            active.update({
                "merchant_id": mid,
                "created_ts": time.time(),
                "amount": _int_money(data.get("amount")),
                "txn_id": str(data.get("txn_id") or qris.get("txn_id") or generate_txn_id()),
                "items": items,
                "customer_name": str(data.get("customer_name", "") or ""),
                "customer_email": str(data.get("customer_email", "") or ""),
                "cashier_name": str(data.get("cashier_name", "") or (load_state().get("auth") or {}).get("name") or "Cashier"),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            })
            state = load_state()
            bucket = _ensure_daily_session(state, mid)
            _forget_closed_qr(bucket, active)
            bucket["active_qr"] = active
            bucket["display_event"] = None
            _sync_legacy_state_for_default(state, mid)
            save_state(state)
            return self.send_json({"ok": True, "active_qr": active})
        if path == "/api/qr/dismiss":
            mid = current_merchant_id()
            state = load_state()
            bucket = _ensure_daily_session(state, mid)
            active = current_active_qr(state, mid)
            if not active:
                return self.send_error_json("Tidak ada QR aktif untuk dismiss.", 400)
            display_event = set_display_event(state, mid, "dismissed", active)
            bucket["active_qr"] = None
            _sync_legacy_state_for_default(state, mid)
            save_state(state)
            return self.send_json({"ok": True, "display_event": display_event})
        if path == "/api/display-event/ack":
            state = load_state()
            mid = normalize_merchant_id(data.get("merchant_id") or display_state_merchant_id(state))
            display_event = clear_display_event(state, mid, data.get("txn_id"))
            save_state(state)
            return self.send_json({"ok": True, "display_event": display_event})
        if path == "/api/display-event/notice":
            state = load_state()
            mid = normalize_merchant_id(data.get("merchant_id") or current_merchant_id())
            notice = update_cashier_payment_notice(state, mid, data)
            save_state(state)
            return self.send_json({"ok": True, "cashier_notice": notice})
        if path == "/api/history/export.pdf":
            txn_ids = {str(txn_id) for txn_id in data.get("txn_ids", []) if str(txn_id)}
            records = [record for record in load_history() if not txn_ids or str(record.get("txn_id")) in txn_ids]
            return self.send_bytes(make_history_export_pdf(records), "application/pdf", "invoice-history.pdf")
        if path == "/api/logs/read":
            ok, msg = verify_system_log_password(data.get("admin_password"))
            if not ok:
                return self.send_error_json(msg, 403)
            return self.send_json({"ok": True, "logs": load_logs(260)})
        if path == "/api/logs/clear":
            ok, msg = verify_system_log_password(data.get("admin_password"))
            if not ok:
                return self.send_error_json(msg, 403)
            clear_current_log_window()
            return self.send_json({"ok": True, "logs": []})
        return self.send_error_json("Unknown API route", 404)


def run(host="127.0.0.1", port=8765):
    server = ThreadingHTTPServer((host, port), ConlectaWebHandler)
    log.info("Conlecta web app running at http://%s:%s", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    host = os.environ.get("CONLECTA_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("CONLECTA_WEB_PORT", "8765"))
    run(host, port)
