# =========================================================
# conlecta_email.py
#
# Gmail receipt sender
# =========================================================

import os
import html
import base64
import threading
import logging
from datetime import datetime

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

log = logging.getLogger(__name__)

from conlecta_oauth import (
    BASE_DIR as _BASE_DIR,
    GMAIL_SCOPES,
    GMAIL_TOKEN_FILE,
    OAUTH_TOKEN_FILE,
    load_google_credentials,
)

TOKEN_FILE = GMAIL_TOKEN_FILE

LOGO_PATH = os.path.join(
    _BASE_DIR,
    "assets",
    "Email",
    "ConlectaIcon.png"
)

SENDER_EMAIL = (
    "Conlecta Indonesia "
    "<conlecta.indonesia@gmail.com>"
)

# =========================================================
# SCOPES
# =========================================================
SCOPES = GMAIL_SCOPES


def _load_gmail_credentials() -> Credentials | None:
    creds, _path = load_google_credentials(GMAIL_SCOPES)
    return creds


def google_auth() -> Credentials:

    creds = _load_gmail_credentials()

    if creds:
        return creds

    raise FileNotFoundError(
        "token.json tidak ditemukan "
        "atau tidak valid untuk Gmail.\n"
        "Pastikan OAuth Gmail "
        "(scope gmail.send) "
        "sudah di-setup."
    )

# =========================================================
# FORMAT
# =========================================================
def _fmt_rp(amount):

    try:
        return f"Rp {int(amount):,}".replace(",", ".")

    except Exception:
        return f"Rp {amount}"


def _fmt_timestamp(value=None):

    text = str(value or "").strip()

    if not text:
        return datetime.now().strftime("%A - %d-%m-%Y %H:%M")

    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.strftime("%A - %d-%m-%Y %H:%M")

    except Exception:
        return text


def _receipt_timestamp(record: dict) -> str:
    return _fmt_timestamp(
        record.get("updated_at_display")
        or record.get("updated_at")
        or record.get("timestamp")
    )


def _resolve_logo_path(path):

    logo_path = str(path or "").strip()

    if logo_path.startswith("/assets/"):
        logo_path = os.path.join(
            _BASE_DIR,
            logo_path.lstrip("/").replace("/", os.sep)
        )

    if logo_path and not os.path.isabs(logo_path):
        logo_path = os.path.join(_BASE_DIR, logo_path)

    return logo_path


def _parse_discount_meta(raw):

    out = {
        "cart_discount_pct": 0,
        "line_discount": 0,
        "gross": 0
    }

    if not raw:
        return out

    s = str(raw).strip()

    if s.isdigit():

        out["cart_discount_pct"] = int(s)

        return out

    for part in s.split("|"):

        if ":" not in part:
            continue

        k, v = part.split(":", 1)

        k = k.strip().lower()

        try:
            val = int(v.strip())

        except ValueError:
            continue

        if k == "pct":
            out["cart_discount_pct"] = val

        elif k == "line":
            out["line_discount"] = val

        elif k == "gross":
            out["gross"] = val

    return out


def _receipt_subject(record: dict) -> str:
    """
    Plain subject:
    Nama Toko - Payment Receipt on Timestamp
    """

    shop = str(
        record.get("shop_name", "CONLECTA")
    ).strip() or "CONLECTA"

    ts = _receipt_timestamp(record)

    custom = record.get(
        "email_subject",
        ""
    ).strip()

    if custom:

        return (
            custom.replace("{shop_name}", shop)
            .replace("{timestamp}", ts)
            .replace(
                "{txn_id}",
                str(record.get("txn_id", ""))
            )
        )

    return f"{shop} - Payment Receipt on {ts}"

# =========================================================
# BUILD HTML RECEIPT
# =========================================================
def _build_receipt_html(record: dict) -> str:

    override = (
        record.get("html_override") or ""
    ).strip()

    if override:

        shop = str(
            record.get("shop_name", "CONLECTA")
        )

        ts = _receipt_timestamp(record)

        return (
            override.replace(
                "{shop_name}",
                html.escape(shop)
            )
            .replace(
                "{timestamp}",
                html.escape(ts)
            )
            .replace(
                "{txn_id}",
                html.escape(
                    str(record.get("txn_id", "N/A"))
                )
            )
            .replace(
                "{customer}",
                html.escape(
                    str(record.get(
                        "customer",
                        "Guest"
                    ))
                )
            )
            .replace(
                "{total}",
                _fmt_rp(record.get("amount", 0))
            )
            .replace(
                "{payment_method}",
                html.escape(str(record.get("payment_method", "QRIS")))
            )
        )

    txn_id = html.escape(
        str(record.get("txn_id", "N/A"))
    )

    amount = int(
        record.get("amount", 0) or 0
    )

    shop_name = html.escape(
        str(record.get(
            "shop_name",
            "CONLECTA"
        ))
    )

    customer = html.escape(
        str(
            record.get(
                "customer_note",
                record.get(
                    "customer",
                    ""
                )
            ) or "Guest"
        )
    )

    updated_at = html.escape(_receipt_timestamp(record))
    payment_method = html.escape(
        str(record.get("payment_method", "QRIS") or "QRIS")
    )
    cash_received = int(record.get("cash_received", 0) or 0)
    change_amount = int(record.get("change", 0) or 0)

    items = record.get("items", []) or []

    disc_meta = _parse_discount_meta(
        record.get("discount", "0")
    )

    cart_pct = int(
        record.get(
            "cart_discount_pct",
            disc_meta["cart_discount_pct"]
        ) or 0
    )

    line_disc = int(
        record.get(
            "line_discount_total",
            disc_meta["line_discount"]
        ) or 0
    )

    cart_disc_amt = int(
        record.get(
            "cart_discount_amt",
            0
        ) or 0
    )

    gross_before = int(
        record.get(
            "gross_subtotal",
            0
        ) or 0
    )

    if not gross_before:

        gross_before = sum(
            int(it.get("gross", 0) or 0)
            or int(it.get("amount", 0) or 0)
            * int(it.get("qty", 0) or 0)
            for it in items
        )

    if not gross_before:

        gross_before = (
            amount
            + line_disc
            + cart_disc_amt
        )

    if not cart_disc_amt and cart_pct:

        after_line = max(
            0,
            gross_before - line_disc
        )

        cart_disc_amt = round(
            after_line * cart_pct / 100
        )

    total_final = (
        amount
        if amount else max(
            0,
            gross_before
            - line_disc
            - cart_disc_amt
        )
    )

    # =========================================================
    # ITEM ROWS
    # =========================================================
    item_rows = ""

    for item in items:

        name = html.escape(
            str(item.get("item_name", ""))
        )

        qty = int(
            item.get("qty", 0) or 0
        )

        subtotal = int(
            item.get("subtotal", 0) or 0
        )

        is_free = item.get(
            "free",
            False
        )

        name_display = (
            f"{name} "
            f"<span style='color:#FCD34D;"
            f"font-size:11px;'>[FREE]</span>"
            if is_free else name
        )

        row_bg = "#ffffff" if (len(item_rows) // 4) % 2 == 0 else "#f8fafc"
        item_rows += f"""
        <tr style="background:{row_bg};">
            <td style="padding:10px 16px;color:#1a1a2e;font-size:14px;">
                {name_display}
            </td>
            <td align="center"
                style="padding:10px 12px;color:#64748b;font-size:14px;">
                {qty}
            </td>
            <td align="right"
                style="padding:10px 16px;color:#1a1a2e;font-size:14px;font-weight:600;">
                {_fmt_rp(subtotal)}
            </td>
        </tr>
        """

    discount_rows = ""

    if (
        gross_before > total_final
        or line_disc
        or cart_disc_amt
    ):

        discount_rows = f"""
        <tr style="border-top:1px solid #e2e5ea;background:#f8fafc;">
            <td colspan="2"
                style="padding:10px 16px;color:#64748b;font-size:14px;">
                Subtotal (gross)
            </td>
            <td align="right"
                style="padding:10px 16px;color:#64748b;font-size:14px;">
                {_fmt_rp(gross_before)}
            </td>
        </tr>
        """

        if line_disc:

            discount_rows += f"""
            <tr style="background:#f8fafc;">
                <td colspan="2"
                    style="padding:6px 16px;color:#d97706;font-size:13px;">
                    Potongan item
                </td>
                <td align="right"
                    style="padding:6px 16px;color:#d97706;font-size:13px;">
                    &minus; {_fmt_rp(line_disc)}
                </td>
            </tr>
            """

        if cart_disc_amt:

            lbl = (
                f"Diskon cart ({cart_pct}%)"
                if cart_pct else "Diskon cart"
            )

            discount_rows += f"""
            <tr style="background:#f8fafc;">
                <td colspan="2"
                    style="padding:6px 16px;color:#d97706;font-size:13px;">
                    {lbl}
                </td>
                <td align="right"
                    style="padding:6px 16px;color:#d97706;font-size:13px;">
                    &minus; {_fmt_rp(cart_disc_amt)}
                </td>
            </tr>
            """
    cash_section = ""
    if payment_method.lower() == "cash":
        cash_section = f"""
<tr>
<td style="padding:12px 20px;color:#94a3b8;font-size:14px;border-bottom:1px solid #e2e5ea;">Uang Diterima</td>
<td align="right" style="padding:12px 20px;color:#1a1a2e;font-size:14px;border-bottom:1px solid #e2e5ea;font-weight:600;">{_fmt_rp(cash_received)}</td>
</tr>
<tr>
<td style="padding:12px 20px;color:#94a3b8;font-size:14px;">Kembalian</td>
<td align="right" style="padding:12px 20px;color:#059669;font-size:14px;font-weight:600;">{_fmt_rp(change_amount)}</td>
</tr>
"""

    return f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" role="presentation">
<tr><td align="center" style="padding:32px 16px;">
<table width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.06);">

<tr><td style="height:4px;background:linear-gradient(90deg,#6366f1,#8b5cf6,#a78bfa);font-size:0;line-height:0;">&nbsp;</td></tr>

<tr><td align="center" style="padding:32px 40px 24px;">
<img src="cid:logo" width="72" height="72" style="display:block;width:72px;height:72px;object-fit:cover;border-radius:14px;border:2px solid #e2e5ea;margin-bottom:16px;" alt="{shop_name}">
<h1 style="margin:0 0 4px;font-size:22px;color:#1a1a2e;font-weight:700;">{shop_name}</h1>
<p style="margin:0;font-size:13px;color:#94a3b8;">Payment Receipt</p>
</td></tr>

<tr><td style="padding:0 40px;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0fdf4;border-radius:12px;border:1px solid #bbf7d0;">
<tr><td align="center" style="padding:20px;">
<p style="margin:0 0 4px;font-size:13px;color:#166534;font-weight:600;">Pembayaran Berhasil</p>
<p style="margin:0;font-size:28px;color:#059669;font-weight:800;letter-spacing:-0.5px;">{_fmt_rp(total_final)}</p>
</td></tr>
</table>
</td></tr>

<tr><td style="padding:24px 40px 16px;">
<p style="margin:0 0 16px;font-size:15px;color:#475569;">Halo <strong style="color:#1a1a2e;">{customer}</strong>, terima kasih atas pembayaran Anda.</p>
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;border-radius:10px;border:1px solid #e2e8f0;">
<tr>
<td style="padding:12px 20px;color:#94a3b8;font-size:14px;border-bottom:1px solid #e2e5ea;">Transaction ID</td>
<td align="right" style="padding:12px 20px;color:#6366f1;font-size:14px;font-weight:700;border-bottom:1px solid #e2e5ea;">{txn_id}</td>
</tr>
<tr>
<td style="padding:12px 20px;color:#94a3b8;font-size:14px;border-bottom:1px solid #e2e5ea;">Tanggal</td>
<td align="right" style="padding:12px 20px;color:#1a1a2e;font-size:14px;border-bottom:1px solid #e2e5ea;">{updated_at}</td>
</tr>
<tr>
<td style="padding:12px 20px;color:#94a3b8;font-size:14px;{'' if payment_method.lower() == 'cash' else ''}border-bottom:1px solid #e2e5ea;">Metode Pembayaran</td>
<td align="right" style="padding:12px 20px;color:#6366f1;font-size:14px;font-weight:600;border-bottom:1px solid #e2e5ea;">{payment_method}</td>
</tr>
{cash_section}
</table>
</td></tr>

<tr><td style="padding:8px 40px 8px;">
<h3 style="margin:0 0 12px;font-size:15px;color:#1a1a2e;font-weight:700;">Ringkasan Pesanan</h3>
<table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;">
<tr style="background:#1e1b4b;">
<td style="padding:10px 16px;color:#e0e7ff;font-size:12px;font-weight:700;">Produk</td>
<td align="center" style="padding:10px 12px;color:#e0e7ff;font-size:12px;font-weight:700;">Qty</td>
<td align="right" style="padding:10px 16px;color:#e0e7ff;font-size:12px;font-weight:700;">Subtotal</td>
</tr>
{item_rows}
{discount_rows}
<tr style="border-top:2px solid #e2e5ea;background:#f8fafc;">
<td colspan="2" style="padding:14px 16px;font-size:16px;font-weight:800;color:#1a1a2e;">Total</td>
<td align="right" style="padding:14px 16px;font-size:16px;font-weight:800;color:#059669;">{_fmt_rp(total_final)}</td>
</tr>
</table>
</td></tr>

<tr><td align="center" style="padding:28px 40px;border-top:1px solid #e2e8f0;">
<p style="margin:0;font-size:12px;color:#94a3b8;">&copy; {shop_name} &middot; Powered by Conlecta POS</p>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""


# =========================================================
# SEND EMAIL
# =========================================================

def send_receipt_email(record, customer_email, on_success=None, on_error=None, tk_root=None):

    def worker():

        try:

            creds = google_auth()
            service = build("gmail", "v1", credentials=creds)

            rec = dict(record)
            tpl = rec.get("email_template") or {}
            if tpl.get("subject"):
                rec["email_subject"] = tpl["subject"]
            if tpl.get("html_override"):
                rec["html_override"] = tpl["html_override"]

            msg = MIMEMultipart("mixed")
            msg["to"]      = customer_email
            msg["from"]    = SENDER_EMAIL
            msg["Subject"] = _receipt_subject(rec)

            related = MIMEMultipart("related")
            related.attach(MIMEText(_build_receipt_html(rec), "html", "utf-8"))

            logo_path = (
                rec.get("brand_logo_path")
                or rec.get("logo_path")
                or tpl.get("logo_path")
                or LOGO_PATH
            )
            logo_path = _resolve_logo_path(logo_path)
            if os.path.exists(logo_path):

                with open(logo_path, "rb") as f:

                    img = MIMEImage(f.read())

                    img.add_header("Content-ID", "<logo>")

                    img.add_header(
                        "Content-Disposition",
                        "inline",
                        filename=os.path.basename(logo_path)
                    )

                    related.attach(img)

            else:

                print(f"LOGO NOT FOUND: {logo_path or LOGO_PATH}")

            msg.attach(related)

            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

            service.users().messages().send(
                userId="me",
                body={"raw": raw}
            ).execute()

            print("EMAIL SENT SUCCESS")

            if on_success:
                on_success("Email sent")

        except Exception as e:
            log.error(f"send_receipt_email: {e}")
            if on_error:
                on_error(str(e))

    threading.Thread(target=worker, daemon=True).start()
