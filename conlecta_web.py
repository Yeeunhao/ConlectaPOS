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
import secrets
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
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
from conlecta_oauth import (
    GMAIL_SCOPES,
    GMAIL_TOKEN_FILE,
    OAUTH_CREDS_FILE,
    OAUTH_TOKEN_FILE,
    SHEETS_SCOPES,
    credentials_file_candidates,
    load_gmail_credentials,
    load_google_credentials,
    load_sheets_credentials,
    token_file_candidates,
    warm_up_google_tokens,
    start_google_token_refresh_loop,
)

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
SYSTEM_ADMIN_EMAIL = "joshuandiantoio@gmail.com"
SYSTEM_LOG_ADMIN_EMAIL = "antoniojos121@gmail.com"
DEFAULT_SYSTEM_ADMIN_EMAILS = {
    "joshuandiantoio@gmail.com",
    "joshuandiantonio@gmail.com",
}


def _system_admin_emails():
    raw = str(os.environ.get("CONLECTA_SYSTEM_ADMIN_EMAILS") or "").strip()
    emails = set(DEFAULT_SYSTEM_ADMIN_EMAILS)
    legacy = str(os.environ.get("CONLECTA_SYSTEM_ADMIN_EMAIL") or SYSTEM_ADMIN_EMAIL).strip().lower()
    if legacy:
        emails.add(legacy)
    if raw:
        emails = {part.strip().lower() for part in raw.split(",") if part.strip()}
    return emails
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
COL_ADMIN_ACCOUNT = 11
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
DISPLAY_EVENT_TTL_SECONDS = 6
DISPLAY_CASH_CHANGE_SECONDS = 6
DISPLAY_SUCCESS_MAX_HOLD_SECONDS = 6
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
QRIS_FRAME_FOLDER = os.path.join(ASSETS_DIR, "qris-frame")
QRIS_FRAME_BUILTIN = "/assets/qris-frame/SingapayConlectaQrisFrame.png"
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
    "admin_allow_stock_crud": True,
    "admin_allow_analytics": True,
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
    if not _db_configured():
        return False
    return os.environ.get("CONLECTA_ALLOW_SHEETS") != "1"


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
def is_system_admin_auth(auth):
    email = str((auth or {}).get("email") or "").strip().lower()
    return email in _system_admin_emails() or (auth or {}).get("role") == "system_admin"

def request_system_admin(self, state=None):
    state = state or load_state()
    auth = self.request_auth(state, required=True)

    if not is_system_admin_auth(auth):
        raise PermissionError("System admin access required.")

    return auth


def format_rupiah(value):
    try:
        return f"Rp {int(value):,}".replace(",", ".")
    except Exception:
        return f"Rp {value}"


def _app_timezone():
    name = str(os.environ.get("CONLECTA_TIMEZONE") or "Asia/Jakarta").strip()
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Asia/Jakarta")


def app_now():
    return datetime.now(_app_timezone())


def format_datetime(value=None):
    tz = _app_timezone()
    if not value:
        dt = app_now()
    elif isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        else:
            dt = dt.astimezone(tz)
    else:
        text = str(value).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz)
            else:
                dt = dt.astimezone(tz)
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


def _normalize_admin_account(value, default=False):
    if conlecta_db:
        return conlecta_db.normalize_admin_account(value, default=default)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"", "0", "false", "no", "n", "off"}:
        return False
    return _is_admin_flag(value)


def _coerce_admin_account(value, default=None):
    if value is None and default is None:
        return None
    if value is None:
        return _normalize_admin_account(default, default=False)
    return _normalize_admin_account(value, default=False)


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


DEVICE_SETTING_KEYS = frozenset({
    "payment_image_paths",
    "payment_image_path",
    "video_playlist",
    "active_theme",
})


def _device_settings_root(state):
    root = state.setdefault("device_settings", {})
    if not isinstance(root, dict):
        root = {}
        state["device_settings"] = root
    return root


def get_device_settings(state, device_id, account_id=None):
    if not device_id:
        return {}
    bucket = _device_settings_root(state).get(device_id)
    current = dict(bucket) if isinstance(bucket, dict) else {}
    aid = str(account_id or "").strip()
    if aid:
        themes = current.get("themes_by_account")
        if isinstance(themes, dict) and themes.get(aid):
            current["active_theme"] = themes[aid]
        current["video_playlist"] = _resolve_account_video_playlist(current, aid)
        current["video_disable_default_splash"] = _resolve_account_disable_default_splash(current, aid)
    return current


def _resolve_account_disable_default_splash(device_settings, account_id=""):
    device_settings = dict(device_settings or {})
    aid = str(account_id or "").strip()
    by_account = device_settings.get("video_disable_default_splash_by_account")
    if isinstance(by_account, dict):
        by_account = {str(key).strip(): bool(value) for key, value in by_account.items() if str(key).strip()}
        if aid and aid in by_account:
            return bool(by_account.get(aid))
    legacy = bool(device_settings.get("video_disable_default_splash"))
    legacy_aid = str(device_settings.get("account_id") or "").strip()
    if legacy and (not aid or not legacy_aid or legacy_aid == aid):
        return legacy
    return False


def _store_account_disable_default_splash(current, account_id, disabled):
    current = dict(current or {})
    aid = str(account_id or "").strip()
    disabled = bool(disabled)
    if aid:
        by_account = current.get("video_disable_default_splash_by_account")
        if not isinstance(by_account, dict):
            by_account = {}
        by_account = {str(key).strip(): bool(value) for key, value in by_account.items() if str(key).strip()}
        by_account[aid] = disabled
        current["video_disable_default_splash_by_account"] = by_account
        if str(current.get("account_id") or "") == aid:
            current["video_disable_default_splash"] = disabled
    else:
        current["video_disable_default_splash"] = disabled
    return current


def _resolve_account_video_playlist(device_settings, account_id=""):
    device_settings = dict(device_settings or {})
    aid = str(account_id or "").strip()
    by_account = device_settings.get("video_playlists_by_account")
    if isinstance(by_account, dict) and aid and aid in by_account:
        return list(by_account.get(aid) or [])
    legacy = list(device_settings.get("video_playlist") or [])
    legacy_aid = str(device_settings.get("account_id") or "").strip()
    if legacy and (not aid or not legacy_aid or legacy_aid == aid):
        return legacy
    return []


def _store_account_video_playlist(current, account_id, playlist):
    current = dict(current or {})
    aid = str(account_id or "").strip()
    playlist = list(playlist or [])
    if aid:
        by_account = current.get("video_playlists_by_account")
        if not isinstance(by_account, dict):
            by_account = {}
        by_account[aid] = playlist
        current["video_playlists_by_account"] = by_account
        if str(current.get("account_id") or "") == aid:
            current.pop("video_playlist", None)
    else:
        current["video_playlist"] = playlist
    return current


def set_device_settings(state, device_id, patch, merchant_id=None, account_id=None):
    if not device_id:
        return {}
    clean = {k: v for k, v in dict(patch or {}).items() if k in DEVICE_SETTING_KEYS}
    aid = str(account_id or "").strip()
    theme_value = None
    if aid and "active_theme" in clean:
        theme_value = str(clean.pop("active_theme") or "").strip()
    if not clean and theme_value is None and merchant_id is None and account_id is None:
        return get_device_settings(state, device_id, account_id=aid or None)
    root = _device_settings_root(state)
    current = dict(root.get(device_id) or {})
    if theme_value:
        themes = current.get("themes_by_account")
        if not isinstance(themes, dict):
            themes = {}
        themes[aid] = theme_value
        current["themes_by_account"] = themes
        current.pop("active_theme", None)
    current.update(clean)
    if merchant_id is not None:
        current["merchant_id"] = normalize_merchant_id(merchant_id)
    if account_id is not None:
        current["account_id"] = str(account_id or "")
    current["updated_ts"] = time.time()
    root[device_id] = current
    return get_device_settings(state, device_id, account_id=aid or None)


def merge_settings_with_device(merchant_settings, device_settings):
    merged = dict(merchant_settings or {})
    device = dict(device_settings or {})
    payment_paths = [str(path or "").strip() for path in device.get("payment_image_paths", []) if str(path or "").strip()]
    if payment_paths:
        merged["payment_image_paths"] = payment_paths
        merged["payment_image_path"] = str(device.get("payment_image_path") or payment_paths[0]).strip() or payment_paths[0]
    elif str(device.get("payment_image_path") or "").strip():
        merged["payment_image_path"] = str(device.get("payment_image_path") or "").strip()
        merged["payment_image_paths"] = [merged["payment_image_path"]]
    if "video_playlist" in device:
        merged["video_playlist"] = list(device.get("video_playlist") or [])
    if "video_disable_default_splash" in device:
        merged["video_disable_default_splash"] = bool(device.get("video_disable_default_splash"))
    if str(device.get("active_theme") or "").strip():
        merged["active_theme"] = str(device.get("active_theme") or "").strip()
    return merged


def _is_default_splash_value(value):
    text = str(value or "").strip().lower()
    if text.endswith("/splash.mp4") or text.endswith("\\splash.mp4"):
        return True
    if text.endswith("/assets/videos/splash.mp4"):
        return True
    path = _video_path_from_value(value)
    if path and os.path.isfile(path):
        try:
            return os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(SPLASH_VIDEO))
        except Exception:
            return False
    return False


def _account_has_uploaded_video(device_id, account_id):
    assets = scan_asset_payload(device_id, account_id).get("videos") or []
    return any(not _is_default_splash_value(item.get("path") or item.get("url")) for item in assets)


def _validate_disable_default_splash(device_id, account_id, disabled):
    if not disabled:
        return
    if not _account_has_uploaded_video(device_id, account_id):
        raise ValueError("Upload at least one video before disabling the default sample video.")


def _validate_user_playlist_not_empty(playlist, disable_default):
    if not disable_default:
        return
    user_entries = [entry for entry in (playlist or []) if not _is_default_splash_value(entry)]
    if not user_entries:
        raise ValueError(
            "Cannot remove the last uploaded video while default sample video is disabled. "
            "Upload another video first or re-enable the sample video."
        )


def _validate_user_video_removal(device_id, account_id, target_path, disable_default):
    if not disable_default:
        return
    if _is_default_splash_value(target_path):
        return
    target_norm = os.path.normcase(os.path.abspath(target_path))
    remaining = []
    for item in scan_asset_payload(device_id, account_id).get("videos") or []:
        if _is_default_splash_value(item.get("path") or item.get("url")):
            continue
        item_path = str(item.get("path") or "").strip()
        if not item_path:
            continue
        try:
            item_norm = os.path.normcase(os.path.abspath(item_path))
        except Exception:
            continue
        if item_norm != target_norm:
            remaining.append(item)
    if not remaining:
        raise ValueError(
            "Cannot remove the last uploaded video while default sample video is disabled. "
            "Upload another video first or re-enable the sample video."
        )


def save_account_disable_default_splash(state, device_id, account_id, disabled, merchant_id=None):
    if not device_id:
        raise ValueError("Device ID tidak valid untuk video settings.")
    _validate_disable_default_splash(device_id, account_id, disabled)
    root = _device_settings_root(state)
    current = dict(root.get(device_id) or {})
    aid = str(account_id or "").strip()
    current = _store_account_disable_default_splash(current, aid, disabled)
    if merchant_id is not None:
        current["merchant_id"] = normalize_merchant_id(merchant_id)
    if aid:
        current["account_id"] = aid
    if disabled:
        playlist = [
            entry for entry in (_resolve_account_video_playlist(current, aid) or [])
            if not _is_default_splash_value(entry)
        ]
        current = _store_account_video_playlist(current, aid, playlist)
    else:
        playlist = list(_resolve_account_video_playlist(current, aid) or [])
        if not any(_is_default_splash_value(entry) for entry in playlist) and os.path.isfile(SPLASH_VIDEO):
            playlist.append(SPLASH_VIDEO)
            current = _store_account_video_playlist(current, aid, playlist)
    current["updated_ts"] = time.time()
    root[device_id] = current
    save_state(state)
    return get_device_settings(state, device_id, account_id=aid or None)


def normalize_video_playlist(entries):
    paths = []
    seen = set()
    for value in entries or []:
        path = _video_path_from_value(value)
        if not path:
            continue
        key = os.path.normcase(os.path.abspath(path))
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
    return paths


def save_device_video_playlist(state, device_id, entries, merchant_id=None, account_id=None):
    if not device_id:
        raise ValueError("Device ID tidak valid untuk video playlist.")
    root = _device_settings_root(state)
    current = dict(root.get(device_id) or {})
    aid = str(account_id or "").strip()
    disable_default = _resolve_account_disable_default_splash(current, aid)
    playlist = normalize_video_playlist(entries)
    if disable_default:
        playlist = [entry for entry in playlist if not _is_default_splash_value(entry)]
    _validate_user_playlist_not_empty(playlist, disable_default)
    current = _store_account_video_playlist(current, aid, playlist)
    if merchant_id is not None:
        current["merchant_id"] = normalize_merchant_id(merchant_id)
    if aid:
        current["account_id"] = aid
    current["updated_ts"] = time.time()
    root[device_id] = current
    save_state(state)
    return playlist


def _default_qris_frame_layout():
    return {
        "frame_src": QRIS_FRAME_BUILTIN,
        "source_width": 1086,
        "source_height": 1448,
        "crop": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
        "qr": {"x": 0.18, "y": 0.28, "w": 0.64, "h": 0.32},
    }


def _clamp_qris_ratio(value, minimum=0.0, maximum=1.0):
    try:
        return max(minimum, min(maximum, float(value)))
    except Exception:
        return minimum


def _normalize_qris_box(raw, fallback):
    base = dict(fallback or {})
    data = dict(raw or {})
    box = {
        "x": _clamp_qris_ratio(data.get("x", base.get("x", 0))),
        "y": _clamp_qris_ratio(data.get("y", base.get("y", 0))),
        "w": _clamp_qris_ratio(data.get("w", base.get("w", 1)), 0.05, 1.0),
        "h": _clamp_qris_ratio(data.get("h", base.get("h", 1)), 0.05, 1.0),
    }
    if box["x"] + box["w"] > 1.0:
        box["w"] = max(0.05, 1.0 - box["x"])
    if box["y"] + box["h"] > 1.0:
        box["h"] = max(0.05, 1.0 - box["y"])
    return box


def normalize_qris_frame_layout(raw=None):
    default = _default_qris_frame_layout()
    data = dict(raw or {})
    crop = _normalize_qris_box(data.get("crop"), default["crop"])
    qr = _normalize_qris_box(data.get("qr"), default["qr"])
    frame_src = str(data.get("frame_src") or data.get("frame_url") or default["frame_src"]).strip()
    if frame_src.startswith("/assets/qris-frame/"):
        pass
    elif frame_src and not frame_src.startswith("/"):
        frame_src = f"/assets/qris-frame/{os.path.basename(frame_src)}"
    if not frame_src:
        frame_src = default["frame_src"]
    return {
        "frame_src": frame_src.split("?")[0],
        "source_width": max(1, int(data.get("source_width") or default["source_width"])),
        "source_height": max(1, int(data.get("source_height") or default["source_height"])),
        "crop": crop,
        "qr": qr,
    }


def load_qris_frame_store(state=None):
    state = state or load_state()
    store = state.get("qris_frame_config")
    if not isinstance(store, dict):
        store = {}
    default_layout = normalize_qris_frame_layout(store.get("default") or _default_qris_frame_layout())
    merchants = {}
    for mid, layout in (store.get("merchants") or {}).items():
        key = normalize_merchant_id(mid)
        if not key:
            continue
        merchants[key] = normalize_qris_frame_layout(layout)
    return {"default": default_layout, "merchants": merchants}


def save_qris_frame_store(state, store):
    state["qris_frame_config"] = {
        "default": normalize_qris_frame_layout((store or {}).get("default")),
        "merchants": {
            normalize_merchant_id(mid): normalize_qris_frame_layout(layout)
            for mid, layout in ((store or {}).get("merchants") or {}).items()
            if normalize_merchant_id(mid)
        },
    }
    save_state(state)
    return state["qris_frame_config"]


def qris_frame_public_payload(layout):
    normalized = normalize_qris_frame_layout(layout)
    path = safe_path(BASE_DIR, normalized["frame_src"])
    url = public_asset_url(path) if path and os.path.isfile(path) else normalized["frame_src"]
    return {
        **normalized,
        "frame_url": url or normalized["frame_src"],
    }


def resolve_qris_frame_config(merchant_id=None, state=None):
    store = load_qris_frame_store(state)
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    layout = store.get("merchants", {}).get(mid) or store.get("default") or _default_qris_frame_layout()
    return qris_frame_public_payload(layout)


def list_qris_frame_assets():
    items = []
    if not os.path.isdir(QRIS_FRAME_FOLDER):
        return items
    for path in sorted(glob.glob(os.path.join(QRIS_FRAME_FOLDER, "*.png"))):
        rel = "/" + os.path.relpath(path, BASE_DIR).replace("\\", "/")
        items.append({
            "name": os.path.basename(path),
            "src": rel,
            "url": public_asset_url(path) or rel,
        })
    return items


def qris_frame_admin_payload(auth=None):
    require_system_admin(auth)
    state = load_state()
    store = load_qris_frame_store(state)
    return {
        "frames": list_qris_frame_assets(),
        "config": {
            "default": qris_frame_public_payload(store.get("default")),
            "merchants": {
                mid: qris_frame_public_payload(layout)
                for mid, layout in (store.get("merchants") or {}).items()
            },
        },
        "merchants": list(load_merchants().values()),
    }


def save_qris_frame_admin_config(data, auth=None):
    require_system_admin(auth)
    state = load_state()
    store = load_qris_frame_store(state)
    layout = normalize_qris_frame_layout(data.get("layout") or data)
    scope = str(data.get("scope") or "default").strip().lower()
    merchant_ids = [
        normalize_merchant_id(value)
        for value in (data.get("merchant_ids") or data.get("merchants") or [])
        if normalize_merchant_id(value)
    ]
    if scope == "merchants":
        if not merchant_ids:
            raise ValueError("Pilih minimal satu merchant untuk QR Frame khusus.")
        for mid in merchant_ids:
            store["merchants"][mid] = layout
    else:
        store["default"] = layout
    save_qris_frame_store(state, store)
    return qris_frame_admin_payload(auth)


def _active_qr_store(state, merchant_id):
    bucket = _state_tenant_bucket(state, merchant_id)
    store = bucket.setdefault("active_qrs_by_device", {})
    if not isinstance(store, dict):
        store = {}
        bucket["active_qrs_by_device"] = store
    return store


def _display_event_store(state, merchant_id):
    bucket = _state_tenant_bucket(state, merchant_id)
    store = bucket.setdefault("display_events_by_device", {})
    if not isinstance(store, dict):
        store = {}
        bucket["display_events_by_device"] = store
    return store


def _clear_device_session_state(state, merchant_id, device_id):
    if not device_id:
        return
    mid = normalize_merchant_id(merchant_id)
    _active_qr_store(state, mid).pop(device_id, None)
    _display_event_store(state, mid).pop(device_id, None)
    bucket = _state_tenant_bucket(state, mid)
    legacy = bucket.get("active_qr") or {}
    if str(legacy.get("device_id") or "") == str(device_id):
        bucket["active_qr"] = None
    legacy_event = bucket.get("display_event") or {}
    if str(legacy_event.get("device_id") or "") == str(device_id):
        bucket["display_event"] = None
    _sync_legacy_state_for_default(state, mid)


def set_active_qr_for_session(state, merchant_id, device_id, account_id, active):
    mid = normalize_merchant_id(merchant_id)
    if not device_id:
        bucket = _state_tenant_bucket(state, mid)
        bucket["active_qr"] = active
        _sync_legacy_state_for_default(state, mid)
        return active
    store = _active_qr_store(state, mid)
    if not active:
        store.pop(device_id, None)
    else:
        payload = dict(active)
        payload["device_id"] = device_id
        payload["account_id"] = str(account_id or "")
        store[device_id] = payload
    bucket = _state_tenant_bucket(state, mid)
    legacy = bucket.get("active_qr") or {}
    if not legacy.get("device_id") or str(legacy.get("device_id")) == str(device_id):
        bucket["active_qr"] = None
    _sync_legacy_state_for_default(state, mid)
    return active


def get_active_qr_for_session(state, merchant_id=None, device_id=None, account_id=None, require_account=True):
    mid = normalize_merchant_id(merchant_id)
    bucket = _state_tenant_bucket(state, mid)
    active = None
    if device_id:
        active = (_active_qr_store(state, mid).get(device_id) or None)
    if not active:
        legacy = bucket.get("active_qr")
        if legacy:
            legacy_device = str(legacy.get("device_id") or "")
            legacy_account = str(legacy.get("account_id") or "")
            if device_id and legacy_device and legacy_device != str(device_id):
                legacy = None
            elif require_account and account_id and legacy_account and legacy_account != str(account_id):
                legacy = None
        active = legacy
    if active and require_account and account_id:
        stored_account = str(active.get("account_id") or "")
        if stored_account and stored_account != str(account_id):
            return None
    if active and _is_closed_qr(bucket, active):
        _mark_closed_qr(bucket, active)
        if device_id:
            _active_qr_store(state, mid).pop(device_id, None)
        if bucket.get("active_qr") and _qr_identity_keys(bucket.get("active_qr")) == _qr_identity_keys(active):
            bucket["active_qr"] = None
        _sync_legacy_state_for_default(state, mid)
        return None
    return active


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


def current_merchant_id(state=None, device_id=None):
    try:
        state = state if state is not None else load_state()
        auth = current_auth(state, device_id)
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
    allowed = set(DEFAULT_SETTINGS) - DEVICE_SETTING_KEYS
    for key, value in _strip_legacy_settings(data).items():
        if key in allowed:
            current[key] = value
    log.info("Settings saved from web UI merchant=%s", mid)
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
    if not GSHEETS_AVAILABLE or not credentials_file_candidates():
        return None
    creds, _path = load_sheets_credentials()
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
    _cleanup_old_brand_logos(mid, dst)
    with open(dst, "wb") as f:
        f.write(base64.b64decode(raw))
    return dst


def save_system_merchant(data, auth=None):
    require_system_admin(auth)
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
    row = dict(merchant_payload(mid))
    row["logo_url"] = (
        merchant_brand_logo_url(load_settings(mid), mid)
        or public_asset_url(BRAND_DEFAULT_LOGO, fallback_logo=True)
    )
    return row


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


def save_version_info(data, auth=None):
    require_system_admin(auth)
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


def system_admin_payload(auth=None):
    require_system_admin(auth)
    merchants = []
    for merchant in load_merchants().values():
        row = dict(merchant)
        mid = normalize_merchant_id(row.get("id") or row.get("merchant_id"))
        row["logo_url"] = merchant_brand_logo_url(load_settings(mid), mid)
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
    requires_ack = False
    hold_seconds = DISPLAY_CASH_CHANGE_SECONDS if kind == "success" and payment_method == PAYMENT_METHOD_CASH else DISPLAY_EVENT_TTL_SECONDS
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
        "expires_ts": created + hold_seconds,
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


def current_active_qr(state, merchant_id=None, device_id=None, account_id=None, require_account=True):
    return get_active_qr_for_session(
        state,
        merchant_id,
        device_id=device_id,
        account_id=account_id,
        require_account=require_account,
    )


def set_display_event(state, merchant_id, kind, source=None, device_id=None):
    mid = normalize_merchant_id(merchant_id)
    bucket = _state_tenant_bucket(state, mid)
    event = _display_event_payload(kind, source)
    event["merchant_id"] = mid
    if device_id:
        event["device_id"] = device_id
        _display_event_store(state, mid)[device_id] = event
        if bucket.get("display_event") and str((bucket.get("display_event") or {}).get("device_id") or "") in ("", str(device_id)):
            bucket["display_event"] = None
    else:
        bucket["display_event"] = event
    if event.get("type") in {"success", "dismissed"}:
        _mark_closed_qr(bucket, event)
        if device_id:
            _active_qr_store(state, mid).pop(device_id, None)
        elif bucket.get("active_qr") and _is_closed_qr(bucket, bucket.get("active_qr")):
            bucket["active_qr"] = None
    _sync_legacy_state_for_default(state, mid)
    return event


def clear_display_event(state, merchant_id=None, txn_id=None, device_id=None):
    mid = normalize_merchant_id(merchant_id)
    bucket = _state_tenant_bucket(state, mid)
    if device_id:
        store = _display_event_store(state, mid)
        event = store.get(device_id)
        wanted_txn = str(txn_id or "").strip()
        if event and wanted_txn:
            event_txn = str(event.get("txn_id") or event.get("qr_id") or "").strip()
            if event_txn and event_txn != wanted_txn:
                return event
        store.pop(device_id, None)
        _sync_legacy_state_for_default(state, mid)
        return None
    event = bucket.get("display_event")
    wanted_txn = str(txn_id or "").strip()
    if event and wanted_txn:
        event_txn = str(event.get("txn_id") or event.get("qr_id") or "").strip()
        if event_txn and event_txn != wanted_txn:
            return event
    bucket["display_event"] = None
    _sync_legacy_state_for_default(state, mid)
    return None


def current_display_event(state, merchant_id=None, device_id=None):
    mid = normalize_merchant_id(merchant_id)
    bucket = _state_tenant_bucket(state, mid)
    event = (_display_event_store(state, mid).get(device_id) if device_id else bucket.get("display_event"))
    if event and _display_event_expired(event):
        if device_id:
            _display_event_store(state, mid).pop(device_id, None)
        else:
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


def display_state_merchant_id(state, device_id=None):
    did = str(device_id or "").strip()
    if did:
        auth = (state.get("auth_by_device") or {}).get(did) or {}
        if auth.get("merchant_id"):
            return normalize_merchant_id(auth.get("merchant_id"))
    auth = state.get("auth") or {}
    if auth.get("merchant_id"):
        return normalize_merchant_id(auth.get("merchant_id"))
    tenants = state.get("tenant_data") if isinstance(state.get("tenant_data"), dict) else {}
    if did:
        for mid, bucket in tenants.items():
            if not isinstance(bucket, dict):
                continue
            store = bucket.get("active_qrs_by_device") or {}
            if store.get(did):
                return normalize_merchant_id(mid)
            event = (bucket.get("display_events_by_device") or {}).get(did)
            if event and not _display_event_expired(event):
                return normalize_merchant_id(mid)
        return DEFAULT_MERCHANT_ID
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
        "admin_account": _normalize_admin_account(row[10] if len(row) > 10 else ""),
        "last_activity_ts": row[11].strip() if len(row) > 11 else "",
        "pin": row[12].strip() if len(row) > 12 else "",
    }


def _is_system_admin_account(acc):
    if not acc:
        return False
    return str(acc.get("email") or "").strip().lower() in _system_admin_emails()


def current_auth(state=None, device_id=None):
    try:
        state = state if state is not None else load_state()
    except Exception:
        return {}
    auth = dict(state.get("auth") or {})
    if auth.get("id"):
        return auth
    did = str(device_id or auth.get("device_id") or "").strip()
    if did:
        stored = (state.get("auth_by_device") or {}).get(did)
        if stored:
            return dict(stored)
    return auth


def current_auth_is_system_admin(auth=None):
    return is_system_admin_auth(auth if auth is not None else current_auth())


def require_system_admin(auth=None):
    if not is_system_admin_auth(auth):
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


def _active_qr_for_auth(state, auth, device_id=None):
    if not auth:
        return None
    mid = normalize_merchant_id(auth.get("merchant_id"))
    did = str(device_id or auth.get("device_id") or "").strip()
    return get_active_qr_for_session(state, mid, did, auth.get("id"), require_account=True)


def _account_device_sessions(state):
    return state.setdefault("account_device_sessions", {})


def _register_account_device_session(state, account_id, device_id, ts=None):
    aid = str(account_id or "").strip()
    did = str(device_id or "").strip()
    if not aid or not did:
        return
    now = float(ts if ts is not None else time.time())
    bucket = _account_device_sessions(state).setdefault(aid, {})
    entry = bucket.get(did) or {}
    entry["login_ts"] = entry.get("login_ts") or now
    entry["last_activity_ts"] = now
    bucket[did] = entry


def _remove_account_device_session(state, account_id, device_id):
    aid = str(account_id or "").strip()
    did = str(device_id or "").strip()
    if not aid or not did:
        return False
    bucket = _account_device_sessions(state).get(aid) or {}
    if did not in bucket:
        return False
    del bucket[did]
    if not bucket:
        _account_device_sessions(state).pop(aid, None)
    return True


def _device_session_is_active(state, account_id, device_id):
    aid = str(account_id or "").strip()
    did = str(device_id or "").strip()
    if not aid or not did:
        return False
    return did in (_account_device_sessions(state).get(aid) or {})


def _logout_auth_from_state(state, auth=None, reason="", device_id=None):
    auth = auth or (state.get("auth") or {})
    account_id = str(auth.get("id") or "").strip()
    did = str(device_id or auth.get("device_id") or "").strip()
    if account_id and did:
        _remove_account_device_session(state, account_id, did)
    if account_id and not (_account_device_sessions(state).get(account_id) or {}):
        try:
            acc = _find_account_by_id(account_id)
            if acc:
                _set_account_session(acc["row_index"], SESSION_LOGGED_OUT)
        except Exception as exc:
            log.warning("session logout update failed for %s: %s", account_id, exc)
    state["auth"] = None
    if reason:
        log.info(
            "Web auth cleared: account=%s device=%s reason=%s",
            account_id or "-",
            did or "-",
            reason,
        )


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
    client_device_id = str(auth.get("device_id") or "").strip()
    if client_device_id:
        if not _device_session_is_active(state, account_id, client_device_id):
            if str(acc.get("session") or "").strip().lower() == SESSION_ACTIVE:
                _register_account_device_session(state, account_id, client_device_id)
            else:
                _clear_local_auth_from_state(state, auth, "device_session_inactive")
                return None
    elif str(acc.get("session") or "").strip().lower() != SESSION_ACTIVE:
        _clear_local_auth_from_state(state, auth, "db_session_inactive")
        return None
    if _auth_session_expired(state, auth, acc, activity_ts if refresh_seen else None):
        _logout_auth_from_state(state, auth, "idle_or_daily_timeout", device_id=client_device_id)
        return None
    auth["name"] = auth.get("name") or acc.get("name", "")
    auth["username"] = auth.get("username") or acc.get("username", "")
    auth["email"] = auth.get("email") or acc.get("email", "")
    auth["merchant_id"] = normalize_merchant_id(auth.get("merchant_id") or acc.get("merchant_id"))
    auth["admin_account"] = _normalize_admin_account(acc.get("admin_account"))
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
        if client_device_id:
            _register_account_device_session(
                state,
                account_id,
                client_device_id,
                auth.get("last_activity_ts") or now,
            )
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
    flagged = [acc for acc in accounts if _normalize_admin_account(acc.get("admin_account"))]
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
            if normalize_merchant_id(acc.get("merchant_id")) == mid and _normalize_admin_account(acc.get("admin_account")):
                ws.update_cell(row_index, 11, "")
    except Exception as exc:
        log.warning("clear merchant admin flags failed for %s: %s", mid, exc)


def verify_admin_password(password, mid):
    mid = normalize_merchant_id(mid or current_merchant_id())
    admin = _merchant_admin_account(mid)
    if not admin:
        return False, f"Admin merchant {mid} belum tersedia di database account."
    if str(password or "").strip() != str(admin.get("password") or "").strip():
        return False, "Password admin salah."
    return True, "OK"


def verify_system_log_password(password, auth=None):
    auth = auth or current_auth()
    account_id = str(auth.get("id") or "").strip()
    if not account_id:
        return False, "Login ulang sebelum membuka log."
    account = _find_account_by_id(account_id)
    if not account:
        return False, "Account login tidak ditemukan."
    if str(password or "").strip() != str(account.get("password") or "").strip():
        return False, "Password account salah."
    return True, "OK"


def _log_line_matches_session(line, auth=None, device_id=""):
    auth = auth or {}
    start_ts = _auth_log_start_ts(auth)
    line_ts = _log_line_timestamp(line)
    if start_ts and line_ts and line_ts < start_ts:
        return False
    account_id = str(auth.get("id") or "").strip()
    if account_id:
        match = re.search(r"account=([^\s,]+)", line)
        if match and match.group(1) not in {account_id, "-"}:
            return False
    device_id = str(device_id or auth.get("device_id") or "").strip()
    if device_id:
        match = re.search(r"device=([^\s,]+)", line)
        if match and match.group(1) not in {device_id, "-"}:
            return False
    return True


def create_account_record(account_name, email, password, merchant_id=None, admin_account=False):
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    admin_account = _normalize_admin_account(admin_account)
    account_name = str(account_name or "").strip()
    email = str(email or "").strip()
    password = str(password or "").strip()
    if not account_name or not email:
        return False, "Account name dan email wajib diisi."
    if "@" not in email or "." not in email.split("@")[-1]:
        return False, "Format email belum valid."
    if not password:
        password = secrets.token_urlsafe(16)
    elif len(password) < 6:
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
    log.info("Account registered from web: %s merchant=%s name=%s", account_id, mid, account_name)
    return True, f"Account berhasil dibuat: {account_id}"


def update_account_record(account_id, account_name=None, email=None, password=None, merchant_id=None, admin_account=None):
    acc = _find_account_by_id(account_id)
    if not acc:
        return False, "Account tidak ditemukan."
    admin_flag = acc.get("admin_account") if admin_account is None else _normalize_admin_account(admin_account)
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
    log.info("System admin updated account: %s merchant=%s admin=%s", row[0], row[9], row[10])
    return True, "Account updated."


def merchant_admin_accounts_payload(merchant_id=None):
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    accounts = _accounts_for_merchant(mid)
    return [
        {
            "id": acc.get("id"),
            "name": acc.get("name", ""),
            "email": acc.get("email", ""),
            "username": acc.get("username", ""),
            "admin_account": _normalize_admin_account(acc.get("admin_account")),
            "merchant_id": mid,
        }
        for acc in accounts
    ]


def save_merchant_admin_settings(data, merchant_id=None):
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    settings = load_settings(mid)
    if "admin_allow_stock_crud" in data:
        settings["admin_allow_stock_crud"] = bool(data.get("admin_allow_stock_crud"))
    if "admin_allow_analytics" in data:
        settings["admin_allow_analytics"] = bool(data.get("admin_allow_analytics"))
    merchant_name = str(data.get("merchant_name") or data.get("shop_name") or "").strip()
    if merchant_name:
        settings["shop_name"] = merchant_name
    if "shop_address" in data:
        settings["shop_address"] = str(data.get("shop_address") or "").strip()
    if "shop_postcode" in data:
        settings["shop_postcode"] = str(data.get("shop_postcode") or "").strip()
    logo_path = str(settings.get("brand_logo_path") or "").strip()
    if data.get("logo_data_url"):
        logo_path = _save_merchant_logo_data(mid, data.get("logo_data_url"), data.get("logo_filename"))
        settings["brand_logo_path"] = logo_path
    if merchant_name or logo_path:
        upsert_merchant(mid, merchant_name or settings.get("shop_name") or DEFAULT_MERCHANT_NAME, logo_path)
    saved = save_settings(settings, mid)
    log.info(
        "Merchant admin settings saved: merchant=%s name=%s stock_crud=%s analytics=%s",
        mid,
        saved.get("shop_name"),
        saved.get("admin_allow_stock_crud"),
        saved.get("admin_allow_analytics"),
    )
    return saved


def merchant_admin_update_account(account_id, data, merchant_id=None):
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    acc = _find_account_by_id(account_id)
    if not acc:
        return False, "Account tidak ditemukan."
    if normalize_merchant_id(acc.get("merchant_id")) != mid:
        return False, "Account bukan milik merchant ini."
    admin_flag = acc.get("admin_account") if "admin_account" not in data else data.get("admin_account")
    return update_account_record(
        account_id,
        account_name=data.get("name"),
        email=data.get("email"),
        password=data.get("password"),
        merchant_id=mid,
        admin_account=admin_flag,
    )


def toggle_merchant_account_admin(account_id, admin_account, merchant_id=None):
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    acc = _find_account_by_id(account_id)
    if not acc:
        return False, "Account tidak ditemukan."
    if normalize_merchant_id(acc.get("merchant_id")) != mid:
        return False, "Account bukan milik merchant ini."
    admin_flag = _normalize_admin_account(admin_account)
    if _db_ready():
        try:
            if not conlecta_db.set_account_admin_flag(account_id, admin_flag):
                return False, "Account tidak ditemukan."
            log.info("Merchant admin flag updated: account=%s merchant=%s admin=%s", account_id, mid, admin_flag)
            return True, "Admin role updated."
        except Exception as exc:
            log.warning("toggle merchant admin db failed: %s", exc)
            if _db_mandatory():
                return False, "Database account tidak tersedia."
    if _db_mandatory():
        return False, "Database account tidak tersedia."
    ws = _get_ws(SHEET_ACCOUNTS, ACCOUNT_HEADER)
    if ws is None:
        return False, "Database account tidak tersedia."
    ws.update_cell(acc["row_index"], COL_ADMIN_ACCOUNT, "yes" if admin_flag else "")
    log.info("Merchant admin flag updated: account=%s merchant=%s admin=%s", account_id, mid, admin_flag)
    return True, "Admin role updated."


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
    creds, _path = load_gmail_credentials()
    return creds


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


def _complete_login(acc, state=None, client_device_id=None):
    state = state or load_state()
    _clear_pending_auth(acc["id"])
    _clear_pending_otp(acc["id"], acc.get("row_index"))
    device_id = str(client_device_id or "").strip() or _get_login_device_id(acc["id"])
    now_ts = time.time()
    _register_account_device_session(state, acc["id"], device_id, now_ts)
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
        "admin_account": _normalize_admin_account(acc.get("admin_account")),
        "login_ts": datetime.now().isoformat(timespec="seconds"),
        "log_start_ts": now_ts,
        "last_activity_ts": now_ts,
        "last_seen_ts": now_ts,
        "session_day": _session_business_day(),
        "device_id": device_id,
    }
    log.info(
        "Web login complete: account=%s merchant=%s device=%s",
        acc["id"],
        merchant_id,
        device_id,
    )
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


def verify_login_pin(account_id, pin_value, state=None, client_device_id=None):
    acc, _meta = _get_pending_auth(account_id, "pin")
    pin = str(pin_value or "").strip()
    if not pin.isdigit() or len(pin) != 6:
        raise RuntimeError("PIN wajib 6 angka.")
    if pin != str(acc.get("pin") or "").strip():
        raise RuntimeError("PIN salah.")
    return _complete_login(acc, state=state, client_device_id=client_device_id)


def register_login_pin(account_id, pin_value, confirm_pin, state=None, client_device_id=None):
    acc, _meta = _get_pending_auth(account_id, "register_pin")
    pin = str(pin_value or "").strip()
    confirm = str(confirm_pin or "").strip()
    if not pin.isdigit() or len(pin) != 6:
        raise RuntimeError("PIN wajib 6 angka.")
    if pin != confirm:
        raise RuntimeError("Konfirmasi PIN tidak sama.")
    _set_account_pin(acc["row_index"], pin)
    acc["pin"] = pin
    return _complete_login(acc, state=state, client_device_id=client_device_id)


def verify_login_otp(account_id, otp, state=None, client_device_id=None):
    acc = _find_account_by_id(account_id)
    if not acc:
        raise RuntimeError("Akun tidak ditemukan.")
    state = state or load_state()
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
    return {"auth": _complete_login(acc, state=state, client_device_id=client_device_id)}


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


def is_merchant_admin_auth(auth):
    return _normalize_admin_account((auth or {}).get("admin_account"))


def admin_allow_stock_crud(settings=None, merchant_id=None):
    settings = settings if settings is not None else load_settings(merchant_id)
    return bool(settings.get("admin_allow_stock_crud", True))


def admin_allow_analytics(settings=None, merchant_id=None):
    settings = settings if settings is not None else load_settings(merchant_id)
    return bool(settings.get("admin_allow_analytics", True))


def can_merchant_crud_stock(auth, merchant_id=None):
    if not is_merchant_admin_auth(auth):
        return False
    mid = normalize_merchant_id(merchant_id or (auth or {}).get("merchant_id"))
    return admin_allow_stock_crud(merchant_id=mid)


def can_merchant_view_analytics(auth, merchant_id=None):
    if not is_merchant_admin_auth(auth):
        return False
    mid = normalize_merchant_id(merchant_id or (auth or {}).get("merchant_id"))
    return admin_allow_analytics(merchant_id=mid)


def save_vendor(name, merchant_id=None, registered_by_account_id=None):
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    name = str(name or "").strip()
    if not name:
        raise ValueError("Vendor name kosong.")
    if _db_ready():
        try:
            vendor = conlecta_db.save_vendor(name, mid, registered_by_account_id=registered_by_account_id)
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
    text = str(data or "").strip()
    if not text:
        return ""
    if qrcode:
        try:
            img = qrcode.make(text)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception:
            log.warning("qrcode image generation failed; using remote QR fallback", exc_info=True)
    return f"https://api.qrserver.com/v1/create-qr-code/?size=512x512&data={quote(text)}"


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
        tip_fixed = max(0, _int_money(item.get("tip_fixed")))
        computed_pct_discount = round(gross * disc_pct / 100) if disc_pct else 0
        computed_discount = min(gross, computed_pct_discount + disc_fixed)
        line_discount = _int_money(item.get("line_discount")) or computed_discount
        line_discount = max(0, min(gross, line_discount))
        if free:
            line_discount = gross
            subtotal = tip_fixed
            price = 0
        else:
            subtotal = _int_money(item.get("subtotal"))
            base = max(0, gross - line_discount)
            if subtotal <= 0 and gross:
                subtotal = base + tip_fixed
            elif tip_fixed <= 0 and subtotal > base:
                tip_fixed = max(0, subtotal - base)
            else:
                subtotal = base + tip_fixed
            if gross and subtotal <= 0 and line_discount >= gross and not tip_fixed:
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
            "tip_fixed": tip_fixed,
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


def next_customer_name(state=None, merchant_id=None):
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    if state is None:
        state = load_state()
    bucket = _ensure_daily_session(state, mid)

    seq = int(bucket.get("customer_seq", 0)) + 1
    bucket["customer_seq"] = seq
    save_state(state)

    prefix = str(load_settings(mid).get("default_customer_prefix") or "Conlecta Customer").strip() or "Conlecta Customer"
    return f"{prefix} {seq:03d}"


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
        log.warning(
            "Email module unavailable: %s (on VPS run: pip install -r requirements.txt)",
            exc,
        )
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


def save_transaction(payload, payment_method, merchant_id=None, auth=None, device_id=None):
    global _stock_cache, _stock_cache_ts
    payment_method = normalize_payment_method(payment_method)
    state = load_state()
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    auth = auth or {}
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
    customer_name = str(payload.get("customer_name") or "").strip() or next_customer_name(state, merchant_id=mid)
    customer_email = str(payload.get("customer_email") or "").strip()
    auth = auth or {}
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
            _mark_closed_qr(bucket, existing)
            set_active_qr_for_session(state, mid, device_id, auth.get("id") if auth else None, None)
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
        set_active_qr_for_session(state, mid, device_id, auth.get("id") if auth else None, None)
    set_display_event(state, mid, "success", record, device_id=device_id)

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
    log.info("%s payment success: txn=%s amount=%s account=%s device=%s", payment_method, txn_id, amount, (auth or {}).get("id") or "-", device_id or "-")
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


def admin_transactions_payload(merchant_id=None, auth=None):
    require_system_admin(auth)
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


def update_system_transaction(data, auth=None):
    global _stock_cache, _stock_cache_ts
    require_system_admin(auth)
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
    gross = _int_money(item.get("gross")) or _int_money(item.get("unit_price") or item.get("amount")) * qty
    tip_fixed = max(0, _int_money(item.get("tip_fixed")))
    line_discount = _int_money(item.get("line_discount"))
    subtotal = _int_money(item.get("subtotal"))
    if item.get("free"):
        if not line_discount:
            line_discount = gross
        base = 0
    else:
        if not line_discount and gross:
            line_discount = max(0, gross - max(0, subtotal - tip_fixed))
        base = max(0, gross - line_discount)
    if not subtotal:
        subtotal = base + tip_fixed
    elif tip_fixed <= 0 and subtotal > base:
        tip_fixed = max(0, subtotal - base)
    after_line = subtotal
    return {
        "qty": qty,
        "gross": gross,
        "line_discount": line_discount,
        "tip_fixed": tip_fixed,
        "after_line": after_line,
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


def vendor_invoice_payload(vendor_id="", vendor_name="", date_from="", date_to="", merchant_id=None):
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    history = load_history_for_merchant(mid)
    products = load_stock(force=True, merchant_id=mid)
    vendors = load_vendors(force=True, merchant_id=mid)
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
        if normalize_merchant_id(rec.get("merchant_id") or mid) != mid:
            continue
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
            tip_fixed = max(0, _int_money(item.get("tip_fixed")))
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
                "tip_fixed": tip_fixed,
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
        "merchant_id": mid,
        "selected_vendor": selected_name or (vendor_map.get(selected_id, "(All)") if selected_id else "(All)"),
    }


def active_qr_status(qr_id=None, merchant_id=None, device_id=None, account_id=None):
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    state = load_state()
    bucket = _state_tenant_bucket(state, mid)
    active = get_active_qr_for_session(state, mid, device_id, account_id, require_account=bool(account_id))
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
            set_active_qr_for_session(state, mid, device_id, account_id, None)
        else:
            set_active_qr_for_session(state, mid, device_id or active.get("device_id"), account_id or active.get("account_id"), active)
        _sync_legacy_state_for_default(state, mid)
        save_state(state)
    except Exception as exc:
        active["last_error"] = str(exc)
    return {"status": str(active.get("status") or "PENDING").upper(), "active_qr": active}


def _pdf_escape(value):
    return str(value if value is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _normalize_asset_path(path):
    path = str(path or "").strip()
    if not path:
        return ""
    if path.startswith("/assets/"):
        path = os.path.join(BASE_DIR, path.lstrip("/").replace("/", os.sep))
    elif not os.path.isabs(path):
        path = os.path.join(BASE_DIR, path)
    return path if os.path.isfile(path) else ""


def merchant_brand_logo_file(settings=None, merchant_id=None):
    """Resolve uploaded merchant logo path from settings / merchant record."""
    mid = normalize_merchant_id(merchant_id or (settings or {}).get("merchant_id") or current_merchant_id())
    settings = dict(settings or load_settings(mid))
    merchant = merchant_payload(mid)
    default_base = os.path.basename(BRAND_DEFAULT_LOGO or "").lower()
    for raw in (settings.get("brand_logo_path"), merchant.get("logo_path")):
        path = _normalize_asset_path(raw)
        if not path:
            continue
        if default_base and os.path.basename(path).lower() == default_base:
            continue
        return path
    return _normalize_asset_path(BRAND_DEFAULT_LOGO)


def merchant_brand_logo_url(settings=None, merchant_id=None):
    """Public URL for merchant logo uploaded via settings (API-served, not guessed paths)."""
    mid = normalize_merchant_id(merchant_id or (settings or {}).get("merchant_id") or current_merchant_id())
    settings = dict(settings or load_settings(mid))
    path = merchant_brand_logo_file(settings, mid)
    default_path = _normalize_asset_path(BRAND_DEFAULT_LOGO)
    if path and (not default_path or os.path.normcase(path) != os.path.normcase(default_path)):
        try:
            version = int(os.path.getmtime(path))
        except Exception:
            version = int(time.time())
        return f"/api/brand-image?merchant_id={quote(mid)}&v={version}"
    return public_asset_url(BRAND_DEFAULT_LOGO, fallback_logo=True) or "/assets/ConlectaPosLogo.png"


def _resolve_brand_logo_path(settings=None, merchant_id=None):
    mid = normalize_merchant_id(merchant_id or (settings or {}).get("merchant_id") or current_merchant_id())
    settings = dict(settings or load_settings(mid))
    merchant = merchant_payload(mid)
    default_base = os.path.basename(BRAND_DEFAULT_LOGO or "").lower()

    for raw in (settings.get("brand_logo_path"), merchant.get("logo_path")):
        path = _normalize_asset_path(raw)
        if path and os.path.basename(path).lower() != default_base:
            return path

    brand_dir = os.path.join(ASSETS_DIR, "Brand")
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
        guess = os.path.join(brand_dir, f"{mid}_brand_logo{ext}")
        if os.path.isfile(guess):
            return guess

    for raw in (settings.get("brand_logo_path"), merchant.get("logo_path")):
        path = _normalize_asset_path(raw)
        if path:
            return path
    return _normalize_asset_path(BRAND_DEFAULT_LOGO) or _normalize_asset_path(BRAND_EMAIL_LOGO)


def _pdf_logo(settings, Image, size=46, merchant_id=None):
    path = _resolve_brand_logo_path(settings, merchant_id)
    if path and os.path.isfile(path):
        try:
            return Image(path, width=size, height=size)
        except Exception:
            return ""
    return ""


def _pdf_now_display():
    return app_now().strftime("%d %B %Y %H:%M")


def _pdf_short_date(value=None):
    text = format_datetime(value)
    return text if text else app_now().strftime("%A - %d-%m-%Y %H:%M")


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

    mid = normalize_merchant_id(record.get("merchant_id") or current_merchant_id())
    settings = load_settings(mid)
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

    logo = _pdf_logo(settings, Image, 48, mid)
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
        tip_fixed = max(0, _int_money(item.get("tip_fixed")))
        item_disc = _int_money(item.get("line_discount"))
        if not item_disc and item_gross:
            item_disc = max(0, item_gross - max(0, item_subtotal - tip_fixed))
        if item.get("free"):
            name += " <font color='#d97706'>[FREE]</font>"
        price_display = format_rupiah(unit_price) if unit_price else format_rupiah(item_subtotal)
        if item_disc and item_gross and not item.get("free"):
            price_display = f"<strike><font color='#9ca3af'>{format_rupiah(unit_price)}</font></strike>"
        if merchant and tip_fixed:
            price_display += f"<br/><font color='#059669' size='7'>+ tip {format_rupiah(tip_fixed)}</font>"
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


def make_history_export_pdf(records, title="Invoice History", merchant_id=None):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.enums import TA_RIGHT, TA_CENTER
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, Image
        from reportlab.graphics.shapes import Drawing, Rect
    except Exception as exc:
        raise RuntimeError(f"ReportLab unavailable: {exc}")

    mid = normalize_merchant_id(merchant_id or (records[0].get("merchant_id") if records else None) or current_merchant_id())
    settings = load_settings(mid)
    merchant = merchant_payload(mid)
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

    shop = _pdf_escape(settings.get("shop_name") or merchant.get("name") or "Conlecta")
    logo = _pdf_logo(settings, Image, 36, mid)
    header_left = [[logo if logo else "", Paragraph(f"<b>{shop}</b><br/><font color='#6c727f' size='7'>{_pdf_escape(mid)}</font>", s_cell)]]
    header_brand = Table(header_left, colWidths=[42, 180])
    header_brand.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))

    header = Table([[
        header_brand,
        Paragraph(f"<b>{_pdf_escape(title)}</b><br/><font color='#6c727f' size='7'>Generated: {_pdf_now_display()}</font>", ParagraphStyle("hr2", parent=s_cell, alignment=TA_RIGHT, fontSize=14)),
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
    mid = normalize_merchant_id(payload.get("merchant_id") or current_merchant_id())
    settings = load_settings(mid)
    merchant = merchant_payload(mid)
    shop = _pdf_escape(settings.get("shop_name") or merchant.get("name") or "Conlecta")
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

    logo = _pdf_logo(settings, Image, 40, mid)
    brand_cell = Table([[logo if logo else "", Paragraph(f"<b>{shop}</b><br/><font color='#6c727f' size='7'>{_pdf_escape(mid)}</font>", s_cell)]], colWidths=[46, 160])
    brand_cell.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))

    header = Table([[
        brand_cell,
        Paragraph(f"<b>VENDOR INVOICE</b><br/><font color='#6c727f' size='7'>{_pdf_escape(vendor)}</font><br/><font color='#6c727f' size='7'>Generated: {_pdf_now_display()}</font>", ParagraphStyle("vhr2", parent=s_cell, alignment=TA_RIGHT, fontSize=13)),
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
        tip_fixed = max(0, _int_money(row.get("tip_fixed")))
        base_sales = max(0, _int_money(row.get("subtotal")) - tip_fixed)
        sales_display = format_rupiah(base_sales)
        if tip_fixed:
            sales_display += f"<br/><font color='#059669' size='7'>+ tip {format_rupiah(tip_fixed)}</font>"
        table_rows.append([
            Paragraph(_pdf_escape(row.get("txn", "")), s_cell),
            Paragraph(_pdf_escape(row.get("date", "")), s_cell),
            Paragraph(f"<b>{_pdf_escape(row.get('item', ''))}</b>", s_cell),
            Paragraph(str(row.get("qty", 0)), s_cell_c),
            Paragraph(format_rupiah(row.get("capital", 0)), s_cell_r),
            Paragraph(format_rupiah(row.get("cost", 0)), s_cell_r),
            Paragraph(sales_display, s_cell_r),
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


def load_logs(limit=220, auth=None, device_id=""):
    auth = auth or current_auth()
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
        if not _log_line_matches_session(line, auth, device_id):
            continue
        scoped.append(line.rstrip("\n"))
    return scoped[-limit:]


def clear_current_log_window(auth=None, device_id="", state=None):
    state = state or load_state()
    auth = dict(auth or current_auth())
    if not auth.get("id"):
        return
    auth["log_start_ts"] = time.time()
    device_id = str(device_id or auth.get("device_id") or "").strip()
    if device_id:
        auth["device_id"] = device_id
        state.setdefault("auth_by_device", {})[device_id] = auth
    else:
        state["auth"] = auth
    save_state(state)
    log.info("Session log window cleared for account=%s device=%s", auth.get("id") or "-", device_id or "-")


def _cleanup_old_brand_logos(merchant_id, keep_path):
    mid = normalize_merchant_id(merchant_id)
    brand_dir = os.path.join(ASSETS_DIR, "Brand")
    keep_abs = os.path.normcase(os.path.abspath(str(keep_path or "")))
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".ico"):
        guess = os.path.join(brand_dir, f"{mid}_brand_logo{ext}")
        if not os.path.isfile(guess):
            continue
        if keep_abs and os.path.normcase(os.path.abspath(guess)) == keep_abs:
            continue
        try:
            os.remove(guess)
            log.info("Removed old brand logo: %s", guess)
        except Exception as exc:
            log.warning("Failed to remove old brand logo %s: %s", guess, exc)


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
            url = "/" + rel
            try:
                return f"{url}?v={int(os.path.getmtime(full))}"
            except Exception:
                return url
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
    if not urls and not bool(settings.get("video_disable_default_splash")) and os.path.isfile(SPLASH_VIDEO):
        urls.append("/assets/videos/Splash.mp4")
    return urls


def scan_asset_payload(device_id=None, account_id=None):
    video_files = []
    patterns = [os.path.join(VIDEO_FOLDER, "*.mp4")]
    device_key = str(device_id or "").strip()
    account_key = str(account_id or "").strip()
    if device_key and account_key:
        account_dir = os.path.join(VIDEO_FOLDER, device_key, account_key)
        legacy_dir = os.path.join(VIDEO_FOLDER, device_key)
        patterns = []
        if os.path.isdir(account_dir):
            patterns.extend([
                os.path.join(account_dir, "*.mp4"),
                os.path.join(account_dir, "*.mov"),
                os.path.join(account_dir, "*.mkv"),
                os.path.join(account_dir, "*.avi"),
                os.path.join(account_dir, "*.webm"),
            ])
        if os.path.isdir(legacy_dir):
            patterns.append(os.path.join(legacy_dir, f"{device_key}_*.mp4"))
            patterns.append(os.path.join(legacy_dir, "*.mp4"))
    elif device_key:
        device_dir = os.path.join(VIDEO_FOLDER, device_key)
        if os.path.isdir(device_dir):
            patterns = [os.path.join(device_dir, "*.mp4")]
            for sub in glob.glob(os.path.join(device_dir, "*")):
                if os.path.isdir(sub):
                    patterns.extend([
                        os.path.join(sub, "*.mp4"),
                        os.path.join(sub, "*.mov"),
                        os.path.join(sub, "*.mkv"),
                        os.path.join(sub, "*.avi"),
                        os.path.join(sub, "*.webm"),
                    ])
    else:
        for device_dir in glob.glob(os.path.join(VIDEO_FOLDER, "*")):
            if os.path.isdir(device_dir):
                patterns.append(os.path.join(device_dir, "*.mp4"))
                for sub in glob.glob(os.path.join(device_dir, "*")):
                    if os.path.isdir(sub):
                        patterns.append(os.path.join(sub, "*.mp4"))
    seen = set()
    for pattern in patterns:
        for path in sorted(glob.glob(pattern)):
            norm = os.path.normcase(os.path.abspath(path))
            if norm in seen:
                continue
            seen.add(norm)
            video_files.append({
                "name": os.path.basename(path),
                "url": public_asset_url(path),
                "path": path,
                "size_mb": round(os.path.getsize(path) / (1024 * 1024), 1),
                "device_id": device_key or "",
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


def save_payment_images(data, merchant_id=None, device_id=None, state=None):
    state = state or load_state()
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    files = data.get("files") or []
    if not files:
        raise ValueError("Pilih minimal satu gambar payment.")
    if not device_id:
        raise ValueError("Device ID tidak valid untuk custom payment image.")
    dst_dir = os.path.join(PAYMENT_UPLOAD_FOLDER, mid, device_id)
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
    device_settings = set_device_settings(
        state,
        device_id,
        {
            "payment_image_paths": saved,
            "payment_image_path": saved[0] if saved else "",
        },
        merchant_id=mid,
    )
    save_state(state)
    merged = merge_settings_with_device(load_settings(mid), device_settings)
    log.info("Payment images saved for merchant=%s device=%s count=%s", mid, device_id, len(saved))
    return settings_payload(merged, mid)


def save_video_upload(data, device_id=None, account_id=None, state=None):
    state = state or load_state()
    if not device_id:
        raise ValueError("Device ID tidak valid untuk upload video.")
    account_key = str(account_id or "").strip() or "_legacy"
    filename = os.path.basename(str(data.get("filename") or "video.mp4"))
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".mp4", ".mov", ".mkv", ".avi", ".webm"):
        ext = ".mp4"
    safe_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
    device_dir = os.path.join(VIDEO_FOLDER, device_id, account_key)
    os.makedirs(device_dir, exist_ok=True)
    dst = os.path.join(device_dir, safe_name)
    with open(dst, "wb") as f:
        f.write(_decode_data_file(data.get("data_url")))
    return {
        "name": os.path.basename(dst),
        "url": public_asset_url(dst),
        "path": dst,
        "device_id": device_id,
        "account_id": account_key,
    }


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


def _video_belongs_to_device(path, device_id="", account_id=""):
    if not path or not device_id:
        return False
    full = os.path.abspath(path)
    device_root = os.path.abspath(os.path.join(VIDEO_FOLDER, device_id))
    try:
        common = os.path.commonpath([os.path.normcase(full), os.path.normcase(device_root)])
    except Exception:
        return False
    if common != os.path.normcase(device_root):
        return False
    aid = str(account_id or "").strip()
    if aid:
        account_root = os.path.abspath(os.path.join(device_root, aid))
        try:
            account_common = os.path.commonpath([os.path.normcase(full), os.path.normcase(account_root)])
            if account_common == os.path.normcase(account_root):
                return True
        except Exception:
            pass
    return f"/{device_id}/" in str(path).replace("\\", "/") or os.path.basename(path).startswith(f"{device_id}_")


def remove_video_asset(data, merchant_id=None, device_id=None, account_id=None, state=None):
    state = state or load_state()
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    if not device_id:
        raise ValueError("Device ID tidak valid untuk hapus video.")
    target = _video_path_from_value(data.get("path") or data.get("url"))
    if not target:
        raise ValueError("Video tidak valid.")
    if not _video_belongs_to_device(target, device_id, account_id):
        raise ValueError("Video ini bukan milik account/device saat ini.")
    target_url = public_asset_url(target)
    device_settings = get_device_settings(state, device_id, account_id)
    disable_default = _resolve_account_disable_default_splash(device_settings, account_id)
    _validate_user_video_removal(device_id, account_id, target, disable_default)
    playlist = []
    for value in device_settings.get("video_playlist", []) or []:
        value_path = _video_path_from_value(value)
        value_url = public_asset_url(value_path) if value_path else str(value or "")
        if os.path.normcase(value_path or "") == os.path.normcase(target):
            continue
        if target_url and value_url == target_url:
            continue
        playlist.append(value)
    _validate_user_playlist_not_empty(playlist, disable_default)
    save_device_video_playlist(state, device_id, playlist, merchant_id=mid, account_id=account_id)
    if os.path.isfile(target):
        os.remove(target)
    merged = merge_settings_with_device(load_settings(mid), get_device_settings(state, device_id, account_id))
    log.info(
        "Video removed from device settings: merchant=%s device=%s account=%s file=%s",
        mid,
        device_id,
        account_id or "-",
        os.path.basename(target),
    )
    return {
        "settings": settings_payload(merged, mid, get_device_settings(state, device_id, account_id), account_id=account_id),
        "assets": scan_asset_payload(device_id, account_id),
    }


def settings_payload(settings=None, merchant_id=None, device_settings=None, account_id=None):
    mid = normalize_merchant_id(merchant_id or (settings or {}).get("merchant_id") or current_merchant_id())
    settings = merge_settings_with_device(dict(settings or load_settings(mid)), device_settings or {})
    merchant = merchant_payload(mid)
    if merchant.get("name") and (not settings.get("shop_name") or (mid != DEFAULT_MERCHANT_ID and settings.get("shop_name") == DEFAULT_MERCHANT_NAME)):
        settings["shop_name"] = merchant["name"]
    if not settings.get("brand_logo_path") and merchant.get("logo_path"):
        settings["brand_logo_path"] = merchant["logo_path"]
    settings["merchant_id"] = mid
    settings["merchant_name"] = merchant.get("name") or settings.get("shop_name") or DEFAULT_MERCHANT_NAME
    settings["brand_logo_url"] = merchant_brand_logo_url(settings, mid)
    settings["payment_image_urls"] = [public_asset_url(path) for path in configured_payment_image_paths(settings)]
    settings["payment_image_urls"] = [url for url in settings["payment_image_urls"] if url]
    if device_settings is not None:
        aid = str(account_id or device_settings.get("account_id") or "").strip()
        if aid:
            settings["video_disable_default_splash"] = _resolve_account_disable_default_splash(device_settings, aid)
        elif "video_disable_default_splash" in device_settings:
            settings["video_disable_default_splash"] = bool(device_settings.get("video_disable_default_splash"))
    settings["video_playlist_urls"] = video_playlist_urls(settings)
    settings["qris_frame"] = resolve_qris_frame_config(mid, load_state())
    settings["qris_vps_env_var"] = "CONLECTA_QRIS_VPS_URL"
    return settings


def display_settings_payload(merchant_id=None, device_settings=None):
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
    settings = merge_settings_with_device(dict(load_settings(mid)), device_settings or {})
    merchant = merchant_payload(mid)
    if not settings.get("brand_logo_path") and merchant.get("logo_path"):
        settings["brand_logo_path"] = merchant["logo_path"]
    settings["merchant_id"] = mid
    settings["merchant_name"] = settings.get("shop_name") or merchant.get("name") or DEFAULT_MERCHANT_NAME
    settings["brand_logo_url"] = merchant_brand_logo_url(settings, mid)
    settings["payment_image_urls"] = [public_asset_url(path) for path in configured_payment_image_paths(settings)]
    settings["payment_image_urls"] = [url for url in settings["payment_image_urls"] if url]
    settings["video_playlist_urls"] = video_playlist_urls(settings)
    settings["qris_frame"] = resolve_qris_frame_config(mid, load_state())
    settings["qris_vps_env_var"] = "CONLECTA_QRIS_VPS_URL"
    return settings


def save_brand_logo(data, merchant_id=None):
    mid = normalize_merchant_id(merchant_id or current_merchant_id())
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
    _cleanup_old_brand_logos(mid, dst)
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
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Conlecta-Device-Id")
        super().end_headers()

    server_version = "ConlectaWeb/2.0"

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()
    
    def request_auth(self, state=None, required=True):
        state = state or load_state()
        auth = self.get_device_auth(state)

        if auth:
            state["auth"] = auth
            auth = validate_stored_auth(state)
            state["auth"] = None

        if required and not auth:
            raise PermissionError("Session login tidak valid. Silakan login ulang.")

        return auth

    def request_merchant_id(self, state=None):
        auth = self.request_auth(state, required=True)
        return normalize_merchant_id(auth.get("merchant_id")), auth

    def request_merchant_admin(self, state=None):
        auth = self.request_auth(state, required=True)
        if not is_merchant_admin_auth(auth):
            raise PermissionError("Akses merchant admin diperlukan.")
        return auth

    def request_merchant_stock_admin(self, state=None):
        auth = self.request_merchant_admin(state)
        mid = normalize_merchant_id(auth.get("merchant_id"))
        if not admin_allow_stock_crud(merchant_id=mid):
            raise PermissionError("CRUD stock belum diaktifkan untuk merchant ini.")
        return auth

    def log_message(self, fmt, *args):
        log.debug("%s - %s", self.address_string(), fmt % args)
    
    def device_id(self, payload=None):
        did = self.headers.get("X-Conlecta-Device-Id", "").strip()
        if not did and isinstance(payload, dict):
            did = str(payload.get("device_id") or "").strip()
        return did

    def get_device_auth(self, state, payload=None):
        did = self.device_id(payload)
        if not did:
            return None
        return (state.get("auth_by_device") or {}).get(did)
    
    def set_device_auth(self, state, auth, payload=None):
        did = self.device_id(payload)
        if not did:
            return
        auth = dict(auth or {})
        auth["device_id"] = did
        prev = (state.get("auth_by_device") or {}).get(did) or {}
        prev_id = str(prev.get("id") or "")
        new_id = str(auth.get("id") or "")
        auth_by_device = state.setdefault("auth_by_device", {})
        auth_by_device[did] = auth
        state["auth"] = None
        if new_id and prev_id and prev_id != new_id:
            _clear_device_session_state(state, auth.get("merchant_id"), did)


    def request_system_admin(self, state=None):
        auth = self.request_auth(state, required=True)
        if not is_system_admin_auth(auth):
            raise PermissionError("System admin access required.")
        return auth

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
            if app_path == "/qr-display.html":
                self.send_response(308)
                self.send_header("Location", "/qr-display")
                self.end_headers()
                return
            if app_path == "/qr-display":
                return self.serve_file(os.path.join(WEB_DIR, "qr-display.html"))
            if path.startswith("/assets/"):
                return self.serve_file(safe_path(BASE_DIR, path))
            if path in ("/styles.css", "/app.js", "/qr-display.js", "/qris-frame.js", "/qris-frame-admin.js", "/image-crop.js", "/theme-pack.css", "/theme-engine.js"):
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

    def _api_path(self, path):
        return (path or "").rstrip("/") or "/"

    def handle_api_get(self, path, query):
        path = self._api_path(path)
        if path == "/api/brand-image":
            mid = normalize_merchant_id((query.get("merchant_id") or [""])[0])
            if not mid:
                return self.send_error(400, "merchant_id required")
            logo_path = merchant_brand_logo_file(load_settings(mid), mid)
            if not logo_path:
                logo_path = _normalize_asset_path(BRAND_DEFAULT_LOGO)
            if not logo_path:
                return self.send_error(404, "Logo not found")
            return self.serve_file(logo_path)
        if path == "/api/display-state":
            state = load_state()
            did = self.device_id()
            auth = self.get_device_auth(state)
            if auth:
                state["auth"] = auth
                auth = validate_stored_auth(state)
                state["auth"] = None
            mid = normalize_merchant_id(
                (auth or {}).get("merchant_id") or display_state_merchant_id(state, device_id=did or None)
            )
            account_id = str((auth or {}).get("id") or "").strip()
            bucket = _state_tenant_bucket(state, mid)
            display_event = current_display_event(state, mid, device_id=did or None)
            cashier_notice = current_cashier_payment_notice(state, mid)
            active_qr = get_active_qr_for_session(
                state,
                mid,
                did or None,
                account_id or None,
                require_account=bool(account_id),
            )
            save_state(state)
            return self.send_json({
                "ok": True,
                "merchant_id": mid,
                "account_id": account_id,
                "settings": display_settings_payload(mid, get_device_settings(state, did, account_id) if did else {}),
                "active_qr": active_qr,
                "display_event": display_event,
                "cashier_notice": cashier_notice,
                "version": load_version_info(),
            })
        if path == "/api/bootstrap":
            state = load_state()
            auth = self.get_device_auth(state)
            if auth:
                state["auth"] = auth
                auth = validate_stored_auth(state)
                state["auth"] = None
            mid = normalize_merchant_id((auth or {}).get("merchant_id") or DEFAULT_MERCHANT_ID)
            if auth:
                acc = _find_account_by_id(auth.get("id")) if auth.get("id") else None
                if acc:
                    auth["role"] = "system_admin" if _is_system_admin_account(acc) else (auth.get("role") or "cashier")
                    auth["email"] = auth.get("email") or acc.get("email", "")
                    auth["merchant_id"] = normalize_merchant_id(auth.get("merchant_id") or acc.get("merchant_id"))
                    auth["admin_account"] = _normalize_admin_account(acc.get("admin_account"))
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
            if (auth or {}).get("role") == "system_admin":
                save_state(state)
                return self.send_json({
                    "ok": True,
                    "auth": auth,
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
                    "system_admin": system_admin_payload(auth),
                    "logs": [],
                    "assets": scan_asset_payload(),
                })

            bucket = _ensure_daily_session(state, mid)
            did = self.device_id()
            device_settings = get_device_settings(state, did, (auth or {}).get("id")) if did else {}
            display_event = current_display_event(state, mid, device_id=did or None)
            active_qr = _active_qr_for_auth(state, auth, did) if auth else None

            products = load_stock(merchant_id=mid)
            history = load_history_for_merchant(mid)
            vendors = load_vendors(merchant_id=mid)

            bucket["products"] = products
            bucket["history"] = history[:1000]

            save_state(state)

            return self.send_json({
                "ok": True,
                "auth": auth,
                "settings": settings_payload(
                    merchant_id=mid,
                    device_settings=device_settings,
                    account_id=(auth or {}).get("id"),
                ),
                "products": products,
                "vendors": vendors,
                "history": history,
                "active_qr": active_qr,
                "display_event": display_event,
                "session": bucket.get("session", {"sales": 0, "revenue": 0}),
                "session_day": bucket.get("session_day"),
                "session_reset_at": bucket.get("session_reset_at"),
                "version": load_version_info(),
                "logs": [],
                "assets": scan_asset_payload(did or None, (auth or {}).get("id")),
            })
        if path == "/api/stock":
            state = load_state()
            auth = self.get_device_auth(state)
            auth = validate_stored_auth({**state, "auth": auth}) if auth else None
            mid = normalize_merchant_id((auth or {}).get("merchant_id"))
            return self.send_json({"ok": True, "products": load_stock(force=True, merchant_id=mid)})
        if path == "/api/vendors":
            state = load_state()
            auth = self.get_device_auth(state)
            auth = validate_stored_auth({**state, "auth": auth}) if auth else None
            mid = normalize_merchant_id((auth or {}).get("merchant_id"))
            return self.send_json({"ok": True, "vendors": load_vendors(merchant_id=mid)})
        if path == "/api/merchant-admin/accounts":
            state = load_state()
            try:
                mid, auth = self.request_merchant_id(state)
                self.request_merchant_admin(state)
            except PermissionError as exc:
                return self.send_error_json(exc, 403)
            settings = load_settings(mid)
            return self.send_json({
                "ok": True,
                "merchant_id": mid,
                "merchant_name": merchant_payload(mid).get("name") or settings.get("shop_name") or DEFAULT_MERCHANT_NAME,
                "admin_allow_stock_crud": admin_allow_stock_crud(settings),
                "admin_allow_analytics": admin_allow_analytics(settings),
                "accounts": merchant_admin_accounts_payload(mid),
            })
        if path == "/api/assets":
            state = load_state()
            auth = self.get_device_auth(state)
            did = self.device_id()
            mid = normalize_merchant_id((auth or {}).get("merchant_id") or current_merchant_id())
            device_settings = get_device_settings(state, did, (auth or {}).get("id")) if did else {}
            return self.send_json({
                "ok": True,
                "assets": scan_asset_payload(did or None, (auth or {}).get("id")),
                "settings": settings_payload(
                    merchant_id=mid,
                    device_settings=device_settings,
                    account_id=(auth or {}).get("id"),
                ),
            })
        if path == "/api/email-templates":
            return self.send_json({"ok": True, "templates": load_email_templates()})
        if path == "/api/history":
            state = load_state()
            auth = self.get_device_auth(state)
            auth = validate_stored_auth({**state, "auth": auth}) if auth else None
            mid = normalize_merchant_id((auth or {}).get("merchant_id"))
            return self.send_json({"ok": True, "history": load_history_for_merchant(mid)})
        if path == "/api/system-admin/transactions":
            state = load_state()
            try:
                auth = self.request_system_admin(state)
                payload = admin_transactions_payload((query.get("merchant_id") or [""])[0], auth=auth)
            except PermissionError as exc:
                return self.send_error_json(exc, 403)
            except Exception as exc:
                return self.send_error_json(exc, 400)
            return self.send_json({"ok": True, **payload})
        if path == "/api/system-admin/qris-frame":
            state = load_state()
            try:
                auth = self.request_system_admin(state)
            except PermissionError as exc:
                return self.send_error_json(exc, 403)
            return self.send_json({"ok": True, **qris_frame_admin_payload(auth)})
        if path == "/api/logs":
            state = load_state()
            auth = self.get_device_auth(state)
            password = (query.get("admin_password") or [""])[0]
            ok, msg = verify_system_log_password(password, auth=auth)
            if not ok:
                return self.send_error_json(msg, 403)
            return self.send_json({"ok": True, "logs": load_logs(260, auth=auth, device_id=self.device_id())})
        if path == "/api/qris/env":
            env_name, detail = qris_proxy_environment()
            return self.send_json({"ok": True, "environment": env_name, "detail": detail})
        if path == "/api/vendor-invoice":
            state = load_state()
            try:
                mid, _auth = self.request_merchant_id(state)
            except PermissionError as exc:
                return self.send_error_json(exc, 403)
            payload = vendor_invoice_payload(
                vendor_id=(query.get("vendor_id") or [""])[0],
                vendor_name=(query.get("vendor_name") or [""])[0],
                date_from=(query.get("from") or [""])[0],
                date_to=(query.get("to") or [""])[0],
                merchant_id=mid,
            )
            return self.send_json({"ok": True, **payload})
        if path == "/api/vendor-invoice.pdf":
            state = load_state()
            try:
                mid, _auth = self.request_merchant_id(state)
            except PermissionError as exc:
                return self.send_error_json(exc, 403)
            payload = vendor_invoice_payload(
                vendor_id=(query.get("vendor_id") or [""])[0],
                vendor_name=(query.get("vendor_name") or [""])[0],
                date_from=(query.get("from") or [""])[0],
                date_to=(query.get("to") or [""])[0],
                merchant_id=mid,
            )
            name = str(payload.get("selected_vendor", "all")).replace(" ", "_")
            return self.send_bytes(make_vendor_invoice_pdf(payload), "application/pdf", f"vendor-invoice-{name}.pdf")
        if path == "/api/qr/status":
            qr_id = (query.get("id") or [""])[0]
            state = load_state()
            auth = self.get_device_auth(state)
            if auth:
                state["auth"] = auth
                auth = validate_stored_auth(state)
                state["auth"] = None
            mid = normalize_merchant_id((auth or {}).get("merchant_id") or current_merchant_id())
            return self.send_json({
                "ok": True,
                **active_qr_status(
                    qr_id,
                    merchant_id=mid,
                    device_id=self.device_id(),
                    account_id=(auth or {}).get("id"),
                ),
            })
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
        path = self._api_path(path)
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
            state = load_state()
            try:
                verified = verify_login_otp(
                    data.get("account_id"),
                    data.get("otp"),
                    state=state,
                    client_device_id=self.device_id(data),
                )
            except Exception as exc:
                return self.send_error_json(exc, 400)
            if verified.get("pending"):
                save_state(state)
                return self.send_json({"ok": True, "pending": verified["pending"], "message": "OTP benar. Register PIN baru."})
            auth = verified.get("auth") or {}
            self.set_device_auth(state, auth, data)
            save_state(state)
            body = {"ok": True, "auth": auth, "settings": settings_payload(merchant_id=auth.get("merchant_id"))}
            if auth.get("role") == "system_admin":
                body["system_admin"] = system_admin_payload(auth)
            return self.send_json(body)
        if path == "/api/auth/verify-pin":
            state = load_state()
            try:
                auth = verify_login_pin(
                    data.get("account_id"),
                    data.get("pin"),
                    state=state,
                    client_device_id=self.device_id(data),
                )
            except Exception as exc:
                return self.send_error_json(exc, 400)
            self.set_device_auth(state, auth, data)
            save_state(state)
            body = {"ok": True, "auth": auth, "settings": settings_payload(merchant_id=auth.get("merchant_id"))}
            if auth.get("role") == "system_admin":
                body["system_admin"] = system_admin_payload(auth)
            return self.send_json(body)
        if path == "/api/auth/register-pin":
            state = load_state()
            try:
                auth = register_login_pin(
                    data.get("account_id"),
                    data.get("pin"),
                    data.get("confirm_pin"),
                    state=state,
                    client_device_id=self.device_id(data),
                )
                self.set_device_auth(state, auth, data)
                save_state(state)
            except Exception as exc:
                return self.send_error_json(exc, 400)
            body = {"ok": True, "auth": auth, "settings": settings_payload(merchant_id=auth.get("merchant_id"))}
            if auth.get("role") == "system_admin":
                body["system_admin"] = system_admin_payload(auth)
            return self.send_json(body)
        if path == "/api/auth/logout":
            state = load_state()
            did = self.device_id(data)
            auth = self.get_device_auth(state, data)
            if auth:
                _logout_auth_from_state(state, auth, reason="logout", device_id=did)
            if did and isinstance(state.get("auth_by_device"), dict):
                state["auth_by_device"].pop(did, None)
            state["auth"] = None
            save_state(state)
            return self.send_json({"ok": True})
        if path == "/api/auth/heartbeat":
            state = load_state()
            auth = self.get_device_auth(state, data)
            if auth:
                state["auth"] = auth
                auth = validate_stored_auth(state, refresh_seen=True, activity_ts=data.get("last_activity_ts"))
                state["auth"] = None
                if auth:
                    self.set_device_auth(state, auth, data)
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
            state = load_state()
            try:
                mid, auth = self.request_merchant_id(state)
                self.request_merchant_admin(state)
            except PermissionError as exc:
                return self.send_error_json(exc, 403)
            ok, msg = create_account_record(
                data.get("name"),
                data.get("email"),
                data.get("password"),
                mid,
                admin_account=data.get("admin_account"),
            )
            if not ok:
                return self.send_error_json(msg, 400)
            return self.send_json({
                "ok": True,
                "message": msg,
                "merchant_id": mid,
                "accounts": merchant_admin_accounts_payload(mid),
            })
        if path == "/api/merchant-admin/settings":
            state = load_state()
            try:
                mid, auth = self.request_merchant_id(state)
                self.request_merchant_admin(state)
            except PermissionError as exc:
                return self.send_error_json(exc, 403)
            saved = save_merchant_admin_settings(data, mid)
            return self.send_json({
                "ok": True,
                "settings": settings_payload(saved, mid),
                "merchant_id": mid,
                "merchant_name": merchant_payload(mid).get("name") or saved.get("shop_name") or DEFAULT_MERCHANT_NAME,
                "admin_allow_stock_crud": admin_allow_stock_crud(saved),
                "admin_allow_analytics": admin_allow_analytics(saved),
            })
        if path == "/api/merchant-admin/account/update":
            state = load_state()
            try:
                mid, auth = self.request_merchant_id(state)
                self.request_merchant_admin(state)
            except PermissionError as exc:
                return self.send_error_json(exc, 403)
            ok, msg = merchant_admin_update_account(data.get("account_id"), data, mid)
            if not ok:
                return self.send_error_json(msg, 400)
            return self.send_json({
                "ok": True,
                "message": msg,
                "accounts": merchant_admin_accounts_payload(mid),
            })
        if path == "/api/merchant-admin/account/toggle-admin":
            state = load_state()
            try:
                mid, auth = self.request_merchant_id(state)
                self.request_merchant_admin(state)
            except PermissionError as exc:
                return self.send_error_json(exc, 403)
            ok, msg = toggle_merchant_account_admin(
                data.get("account_id"),
                data.get("admin_account"),
                mid,
            )
            if not ok:
                return self.send_error_json(msg, 400)
            return self.send_json({
                "ok": True,
                "message": msg,
                "accounts": merchant_admin_accounts_payload(mid),
            })
        if path == "/api/system-admin/merchant/save":
            state = load_state()
            try:
                auth = self.request_system_admin(state)
                merchant = save_system_merchant(data, auth)
            except PermissionError as exc:
                return self.send_error_json(exc, 403)
            return self.send_json({"ok": True, "merchant": merchant, "system_admin": system_admin_payload(auth)})
        if path == "/api/system-admin/account/create":
            state = load_state()
            try:
                auth = self.request_system_admin(state)
            except PermissionError as exc:
                return self.send_error_json(exc, 403)
            ok, msg = create_account_record(
                data.get("name"), data.get("email"), data.get("password"),
                data.get("merchant_id"), _coerce_admin_account(data.get("admin_account"), default=False),
            )
            if not ok:
                return self.send_error_json(msg, 400)
            return self.send_json({"ok": True, "message": msg, "system_admin": system_admin_payload(auth)})
        if path == "/api/system-admin/account/update":
            state = load_state()
            try:
                auth = self.request_system_admin(state)
            except PermissionError as exc:
                return self.send_error_json(exc, 403)
            ok, msg = update_account_record(
                data.get("account_id"), data.get("name"), data.get("email"),
                data.get("password"), data.get("merchant_id"),
                _coerce_admin_account(data.get("admin_account")) if "admin_account" in data else None,
            )
            if not ok:
                return self.send_error_json(msg, 400)
            return self.send_json({"ok": True, "message": msg, "system_admin": system_admin_payload(auth)})
        if path == "/api/system-admin/version/save":
            state = load_state()
            try:
                auth = self.request_system_admin(state)
                version = save_version_info(data, auth)
            except PermissionError as exc:
                return self.send_error_json(exc, 403)
            return self.send_json({"ok": True, "version": version, "system_admin": system_admin_payload(auth)})
        if path == "/api/system-admin/transaction/update":
            state = load_state()
            try:
                auth = self.request_system_admin(state)
                updated = update_system_transaction(data, auth)
            except PermissionError as exc:
                return self.send_error_json(exc, 403)
            except Exception as exc:
                return self.send_error_json(exc, 400)
            return self.send_json({"ok": True, **updated})
        if path == "/api/system-admin/qris-frame/save":
            state = load_state()
            try:
                auth = self.request_system_admin(state)
                payload = save_qris_frame_admin_config(data, auth)
            except PermissionError as exc:
                return self.send_error_json(exc, 403)
            except Exception as exc:
                return self.send_error_json(exc, 400)
            return self.send_json({"ok": True, **payload})
        if path == "/api/vendor/save":
            state = load_state()
            try:
                mid, auth = self.request_merchant_id(state)
                self.request_merchant_stock_admin(state)
            except PermissionError as exc:
                return self.send_error_json(exc, 403)
            vendor = save_vendor(
                data.get("name"),
                merchant_id=mid,
                registered_by_account_id=auth.get("id"),
            )
            return self.send_json({"ok": True, "vendor": vendor, "vendors": load_vendors(merchant_id=mid)})
        if path == "/api/vendor/delete":
            state = load_state()
            try:
                mid, auth = self.request_merchant_id(state)
                self.request_merchant_stock_admin(state)
            except PermissionError as exc:
                return self.send_error_json(exc, 403)
            delete_vendor(data.get("vendor_id"), merchant_id=mid)
            return self.send_json({"ok": True, "vendors": load_vendors(merchant_id=mid)})
        if path == "/api/settings":
            state = load_state()
            mid, auth = self.request_merchant_id(state)
            did = self.device_id()
            incoming = dict(data.get("settings", data) or {})
            current = load_settings(mid)
            identity_changed = (
                str(incoming.get("shop_name", current.get("shop_name", ""))).strip() != str(current.get("shop_name", "")).strip()
            )
            if identity_changed and not is_merchant_admin_auth(auth):
                ok, msg = verify_admin_password(data.get("admin_password") or incoming.get("admin_password"), mid)
                if not ok:
                    return self.send_error_json(msg, 403)
            incoming.pop("admin_password", None)
            device_patch = {k: incoming.pop(k) for k in list(incoming.keys()) if k in DEVICE_SETTING_KEYS}
            if did and "video_playlist" in device_patch and not device_patch.get("video_playlist"):
                existing_playlist = get_device_settings(state, did).get("video_playlist") or []
                if existing_playlist:
                    device_patch.pop("video_playlist")
            merchant_saved = save_settings(incoming, mid)
            if did:
                set_device_settings(state, did, device_patch, merchant_id=mid, account_id=auth.get("id"))
                save_state(state)
            merged = settings_payload(merchant_saved, mid, get_device_settings(state, did, auth.get("id")) if did else {}, account_id=auth.get("id"))
            return self.send_json({"ok": True, "settings": merged})
        if path == "/api/brand-logo":
            state = load_state()
            mid, auth = self.request_merchant_id(state)

            if not is_merchant_admin_auth(auth):
                ok, msg = verify_admin_password(data.get("admin_password"), mid)
                if not ok:
                    return self.send_error_json(msg, 403)

            return self.send_json({
                "ok": True,
                "settings": save_brand_logo(data, merchant_id=mid)
            })
        if path == "/api/payment-images":
            state = load_state()
            mid, auth = self.request_merchant_id(state)
            did = self.device_id()
            if not did:
                return self.send_error_json("Device ID tidak valid.", 400)
            return self.send_json({"ok": True, "settings": save_payment_images(data, mid, did, state)})
        if path == "/api/video-upload":
            state = load_state()
            mid, auth = self.request_merchant_id(state)
            did = self.device_id()
            if not did:
                return self.send_error_json("Device ID tidak valid.", 400)
            saved = save_video_upload(data, did, auth.get("id"), state)
            device_settings = get_device_settings(state, did, auth.get("id"))
            playlist = list(device_settings.get("video_playlist") or [])
            if saved.get("path") and saved["path"] not in playlist:
                playlist.append(saved["path"])
            save_device_video_playlist(state, did, playlist, merchant_id=mid, account_id=auth.get("id"))
            merged = settings_payload(load_settings(mid), mid, get_device_settings(state, did, auth.get("id")), account_id=auth.get("id"))
            return self.send_json({
                "ok": True,
                "video": saved,
                "assets": scan_asset_payload(did, auth.get("id")),
                "settings": merged,
            })
        if path == "/api/video-playlist":
            state = load_state()
            mid, auth = self.request_merchant_id(state)
            did = self.device_id()
            if not did:
                return self.send_error_json("Device ID tidak valid.", 400)
            aid = auth.get("id")
            try:
                disable_default = None
                if "disable_default_splash" in data:
                    disable_default = bool(data.get("disable_default_splash"))
                    save_account_disable_default_splash(
                        state,
                        did,
                        aid,
                        disable_default,
                        merchant_id=mid,
                    )
                entries = data.get("playlist")
                if entries is None:
                    entries = data.get("video_playlist")
                if entries is not None:
                    playlist = save_device_video_playlist(state, did, entries, merchant_id=mid, account_id=aid)
                else:
                    device_settings = get_device_settings(state, did, aid)
                    playlist = list(device_settings.get("video_playlist") or [])
            except ValueError as exc:
                return self.send_error_json(exc, 400)
            merged = settings_payload(
                load_settings(mid),
                mid,
                get_device_settings(state, did, aid),
                account_id=aid,
            )
            return self.send_json({
                "ok": True,
                "playlist": playlist,
                "settings": merged,
                "assets": scan_asset_payload(did, aid),
            })
        if path == "/api/video/remove":
            state = load_state()
            mid, auth = self.request_merchant_id(state)
            did = self.device_id()
            if not did:
                return self.send_error_json("Device ID tidak valid.", 400)
            try:
                removed = remove_video_asset(data, mid, did, auth.get("id"), state)
            except Exception as exc:
                return self.send_error_json(exc, 400)
            return self.send_json({"ok": True, **removed})
        if path == "/api/email-template":
            saved = save_email_template(data.get("key"), data.get("template", {}))
            return self.send_json({"ok": True, "saved": saved, "templates": load_email_templates()})
        if path == "/api/stock/save":
            state = load_state()
            try:
                mid, auth = self.request_merchant_id(state)
                self.request_merchant_stock_admin(state)
            except PermissionError as exc:
                return self.send_error_json(exc, 403)

            products = save_stock(
                data.get("products", []),
                merchant_id=mid
            )

            return self.send_json({
                "ok": True,
                "products": products
            })
        if path == "/api/checkout/cash":
            state = load_state()
            mid, auth = self.request_merchant_id(state)
            did = self.device_id()

            try:
                record = save_transaction(
                    data,
                    PAYMENT_METHOD_CASH,
                    merchant_id=mid,
                    auth=auth,
                    device_id=did,
                )
            except Exception as exc:
                return self.send_error_json(exc, 400)

            bucket = _ensure_daily_session(state, mid)
            display_event = current_display_event(state, mid, device_id=did or None)
            save_state(state)

            return self.send_json({
                "ok": True,
                "record": record,
                "products": bucket.get("products", []),
                "history": bucket.get("history", []),
                "session": bucket.get("session"),
                "display_event": display_event,
            })
        if path == "/api/checkout/qris-success":
            state = load_state()
            mid, auth = self.request_merchant_id(state)
            did = self.device_id()
            try:
                record = save_transaction(data, PAYMENT_METHOD_QRIS, merchant_id=mid, auth=auth, device_id=did)
            except Exception as exc:
                return self.send_error_json(exc, 400)
            bucket = _ensure_daily_session(state, mid)
            display_event = current_display_event(state, mid, device_id=did or None)
            save_state(state)
            return self.send_json({
                "ok": True, "record": record,
                "products": bucket.get("products", []),
                "history": bucket.get("history", []),
                "session": bucket.get("session"),
                "display_event": display_event,
            }) 
        if path == "/api/qr/generate":
            state = load_state()
            auth = self.get_device_auth(state)

            if auth:
                state["auth"] = auth
                auth = validate_stored_auth(state)
                state["auth"] = None

            if not auth:
                return self.send_error_json("Session login tidak valid. Silakan login ulang.", 401)

            mid = normalize_merchant_id(auth.get("merchant_id"))
            did = self.device_id()

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
                "device_id": did,
                "account_id": str(auth.get("id") or ""),
                "created_ts": time.time(),
                "amount": _int_money(data.get("amount")),
                "txn_id": str(data.get("txn_id") or qris.get("txn_id") or generate_txn_id()),
                "items": items,
                "customer_name": str(data.get("customer_name", "") or ""),
                "customer_email": str(data.get("customer_email", "") or ""),
                "cashier_name": str(data.get("cashier_name", "") or auth.get("name") or "Cashier"),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            })

            bucket = _ensure_daily_session(state, mid)
            _forget_closed_qr(bucket, active)
            set_active_qr_for_session(state, mid, did, auth.get("id"), active)
            if did:
                _display_event_store(state, mid).pop(did, None)
            else:
                bucket["display_event"] = None

            _sync_legacy_state_for_default(state, mid)
            save_state(state)

            return self.send_json({"ok": True, "active_qr": active})
        if path == "/api/qr/dismiss":
            state = load_state()
            mid, auth = self.request_merchant_id(state)
            did = self.device_id()
            bucket = _ensure_daily_session(state, mid)
            active = get_active_qr_for_session(state, mid, did, auth.get("id"))
            if not active:
                return self.send_error_json("Tidak ada QR aktif untuk dismiss.", 400)
            display_event = set_display_event(state, mid, "dismissed", active, device_id=did or None)
            set_active_qr_for_session(state, mid, did, auth.get("id"), None)
            _sync_legacy_state_for_default(state, mid)
            save_state(state)
            return self.send_json({"ok": True, "display_event": display_event})
        if path == "/api/display-event/ack":
            state = load_state()
            mid = normalize_merchant_id(data.get("merchant_id") or display_state_merchant_id(state))
            display_event = clear_display_event(state, mid, data.get("txn_id"), device_id=self.device_id() or data.get("device_id"))
            save_state(state)
            return self.send_json({"ok": True, "display_event": display_event})
        if path == "/api/display-event/notice":
            state = load_state()
            mid = normalize_merchant_id(data.get("merchant_id") or current_merchant_id())
            notice = update_cashier_payment_notice(state, mid, data)
            save_state(state)
            return self.send_json({"ok": True, "cashier_notice": notice})
        if path == "/api/history/export.pdf":
            state = load_state()
            mid, auth = self.request_merchant_id(state)

            txn_ids = {
                str(txn_id)
                for txn_id in data.get("txn_ids", [])
                if str(txn_id)
            }

            records = [
                record for record in load_history_for_merchant(mid)
                if not txn_ids or str(record.get("txn_id")) in txn_ids
            ]

            return self.send_bytes(
                make_history_export_pdf(records, merchant_id=mid),
                "application/pdf",
                "invoice-history.pdf"
            )
        if path == "/api/logs/read":
            state = load_state()
            auth = self.get_device_auth(state)
            ok, msg = verify_system_log_password(data.get("admin_password"), auth=auth)
            if not ok:
                return self.send_error_json(msg, 403)
            return self.send_json({"ok": True, "logs": load_logs(260, auth=auth, device_id=self.device_id())})
        if path == "/api/logs/clear":
            state = load_state()
            auth = self.get_device_auth(state)
            ok, msg = verify_system_log_password(data.get("admin_password"), auth=auth)
            if not ok:
                return self.send_error_json(msg, 403)
            clear_current_log_window(auth=auth, device_id=self.device_id(), state=state)
            return self.send_json({"ok": True, "logs": []})
        return self.send_error_json("Unknown API route", 404)


def _email_deps_ready():
    try:
        import google.oauth2.credentials  # noqa: F401
        import googleapiclient.discovery  # noqa: F401
        return True
    except ImportError:
        return False


def _pdf_deps_ready():
    try:
        import reportlab  # noqa: F401
        return True
    except ImportError:
        return False


def run(host="127.0.0.1", port=8765):
    if _email_deps_ready():
        log.info("Gmail/receipt email dependencies: OK")
    else:
        log.warning(
            "Gmail/receipt email disabled on this VPS. Install with: "
            "pip install -r requirements.txt  (then restart the server)"
        )
    if _pdf_deps_ready():
        log.info("PDF export dependencies: OK")
    else:
        log.warning(
            "PDF export disabled on this VPS. Install with: "
            "pip install -r requirements.txt  (then restart the server)"
        )
    if _email_deps_ready():
        def _warm_oauth_tokens():
            try:
                warm_up_google_tokens()
                start_google_token_refresh_loop()
            except Exception as exc:
                log.warning("Google OAuth warm-up failed: %s", exc)
        threading.Thread(target=_warm_oauth_tokens, daemon=True, name="oauth-warmup").start()
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
