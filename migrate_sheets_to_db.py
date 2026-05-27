import json
import os
import sys

os.environ.setdefault("CONLECTA_ALLOW_SHEETS", "1")

import conlecta_db as db
import conlecta_web as web


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_local_state():
    path = getattr(web, "WEB_STATE_FILE", os.path.join(BASE_DIR, "web_state.json"))
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        print(f"local_state_read_failed: {exc}")
        return {}


def sheet_rows(title, headers):
    ws = web._get_ws(title, headers)
    if ws is None:
        return []
    try:
        return ws.get_all_values()
    except Exception as exc:
        print(f"sheet_read_failed {title}: {exc}")
        return []


def migrate_merchants():
    count = 0
    rows = sheet_rows(web.SHEET_MERCHANTS, web.MERCHANT_HEADER)
    seen = set()
    for row in rows[1:]:
        mid = web.normalize_merchant_id(row[0] if len(row) > 0 else "")
        if not mid:
            continue
        name = str(row[1]).strip() if len(row) > 1 and str(row[1]).strip() else web.DEFAULT_MERCHANT_NAME
        logo_path = str(row[2]).strip() if len(row) > 2 else ""
        db.upsert_merchant(mid, name, logo_path)
        seen.add(mid)
        count += 1
    if web.DEFAULT_MERCHANT_ID not in seen:
        db.upsert_merchant(web.DEFAULT_MERCHANT_ID, web.DEFAULT_MERCHANT_NAME, web.BRAND_DEFAULT_LOGO)
        count += 1
    return count


def migrate_settings():
    path = web.SETTINGS_FILE
    if not os.path.isfile(path):
        return 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        print(f"settings_read_failed: {exc}")
        return 0

    count = 0
    default_keys = set(web.DEFAULT_SETTINGS)
    legacy = {k: v for k, v in data.items() if k in default_keys and v is not None}
    if legacy:
        settings = dict(web.DEFAULT_SETTINGS)
        settings.update(web._strip_legacy_settings(legacy))
        settings["merchant_id"] = web.DEFAULT_MERCHANT_ID
        db.save_settings(settings, web.DEFAULT_MERCHANT_ID)
        count += 1

    tenant_settings = data.get("merchant_settings", {}) if isinstance(data.get("merchant_settings"), dict) else {}
    for mid, values in tenant_settings.items():
        if not isinstance(values, dict):
            continue
        merchant_id = web.normalize_merchant_id(mid)
        settings = dict(web.DEFAULT_SETTINGS)
        settings.update(web._strip_legacy_settings(values))
        settings["merchant_id"] = merchant_id
        db.save_settings(settings, merchant_id)
        count += 1
    return count


def migrate_accounts():
    rows = sheet_rows(web.SHEET_ACCOUNTS, web.ACCOUNT_HEADER)
    count = 0
    for idx, row in enumerate(rows[1:], start=2):
        acc = web._parse_account_row(row, idx)
        if not acc:
            continue
        db.upsert_account(acc)
        count += 1
    return count


def migrate_vendors():
    rows = sheet_rows(web.SHEET_VENDORS, web.VENDOR_HEADER)
    count = 0
    for row in rows[1:]:
        legacy_id = str(row[0]).strip() if len(row) > 0 else ""
        name = str(row[1]).strip() if len(row) > 1 else ""
        mid = web.normalize_merchant_id(row[2] if len(row) > 2 else web.DEFAULT_MERCHANT_ID)
        if not legacy_id or not name:
            continue
        db.save_vendor(name, mid, legacy_vendor_id=legacy_id)
        count += 1
    return count


def migrate_stock():
    rows = sheet_rows(web.SHEET_STOCK, web.STOCK_HEADERS)
    products = web.parse_stock_rows(rows) if len(rows) > 1 else []
    by_merchant = {}
    for item in products:
        mid = web.normalize_merchant_id(item.get("merchant_id"))
        name = str(item.get("name") or "").strip().casefold()
        if name:
            by_merchant.setdefault(mid, {})[name] = dict(item, merchant_id=mid)

    state = load_local_state()
    local_buckets = {}
    if state.get("products"):
        local_buckets[web.DEFAULT_MERCHANT_ID] = state.get("products") or []
    tenant_data = state.get("tenant_data") if isinstance(state.get("tenant_data"), dict) else {}
    for mid, bucket in tenant_data.items():
        if isinstance(bucket, dict) and bucket.get("products"):
            local_buckets[web.normalize_merchant_id(mid)] = bucket.get("products") or []

    for mid, items in local_buckets.items():
        merchant_id = web.normalize_merchant_id(mid)
        for item in items:
            name = str((item or {}).get("name") or (item or {}).get("item_name") or "").strip()
            if not name:
                continue
            clean = dict(item)
            clean["name"] = name
            clean["merchant_id"] = merchant_id
            by_merchant.setdefault(merchant_id, {})[name.casefold()] = clean

    count = 0
    for mid, items_by_name in by_merchant.items():
        items = list(items_by_name.values())
        db.save_stock(items, mid)
        count += len(items)
    return count


def load_all_sheet_history():
    txn_rows = sheet_rows(web.SHEET_TXN, web.TXN_HEADER)
    item_rows = sheet_rows(web.SHEET_TXN_ITEMS, web.ITEMS_HEADER)
    if len(txn_rows) <= 1:
        return []

    item_headers = {name.strip(): idx for idx, name in enumerate(item_rows[0])} if item_rows else {}
    items_by_txn = {}
    items_by_qr = {}
    for row in item_rows[1:]:
        row_mid = web.normalize_merchant_id(web._cell(row, item_headers, "Merchant ID", 14, web.DEFAULT_MERCHANT_ID))
        tid = str(web._cell(row, item_headers, "Transaction ID", 1)).strip()
        qid = str(web._cell(row, item_headers, "QR ID", 2)).strip()
        item_change = web._cell_int(row, item_headers, "Change", 12)
        item_cash_received = web._cell_int(row, item_headers, "Cash Received", 13)
        item_capital = web._cell_int(row, item_headers, "Capital")
        item_qty = web._cell_int(row, item_headers, "Qty", 4)
        item_subtotal = web._cell_int(row, item_headers, "Subtotal", 6)
        item_payment_fee = web._cell_int(row, item_headers, "Payment Fee")
        item_total_cost = web._cell_int(row, item_headers, "Total Cost") or ((item_capital * item_qty) + item_payment_fee)
        item = {
            "item_name": web._cell(row, item_headers, "Item Name", 3),
            "name": web._cell(row, item_headers, "Item Name", 3),
            "qty": item_qty,
            "amount": web._cell_int(row, item_headers, "Amount", 5),
            "price": web._cell_int(row, item_headers, "Amount", 5),
            "unit_price": web._cell_int(row, item_headers, "Amount", 5),
            "subtotal": item_subtotal,
            "capital": item_capital,
            "cost": item_capital,
            "payment_fee": item_payment_fee,
            "total_cost": item_total_cost,
            "profit": web._cell_int(row, item_headers, "Profit") or (item_subtotal - item_total_cost if item_total_cost else 0),
            "free": str(web._cell(row, item_headers, "Free", 7)).strip().lower() == "yes",
            "disc_pct": web._cell_int(row, item_headers, "Disc %", 8),
            "disc_fixed": web._cell_int(row, item_headers, "Disc Rp", 9),
            "line_discount": web._cell_int(row, item_headers, "Line Discount", 10),
            "payment_method": web.derive_payment_method(
                web._cell(row, item_headers, "Payment Method", 11),
                item_cash_received,
                item_change,
                qid,
            ),
            "change": item_change,
            "cash_received": item_cash_received,
            "merchant_id": row_mid,
        }
        if tid:
            items_by_txn.setdefault(tid, []).append(item)
        if qid:
            items_by_qr.setdefault(qid, []).append(item)

    txn_headers = {name.strip(): idx for idx, name in enumerate(txn_rows[0])}
    records = []
    for row in txn_rows[1:]:
        row_mid = web.normalize_merchant_id(web._cell(row, txn_headers, "Merchant ID", 14, web.DEFAULT_MERCHANT_ID))
        tid = str(web._cell(row, txn_headers, "Transaction ID", 1)).strip()
        qid = str(web._cell(row, txn_headers, "QR ID", 2)).strip()
        if not tid and not qid:
            continue
        amount = web._cell_int(row, txn_headers, "Amount", 3)
        cash_received = web._cell_int(row, txn_headers, "Cash Received", 12)
        change = web._cell_int(row, txn_headers, "Change", 13)
        payment_fee = web._cell_int(row, txn_headers, "Payment Fee")
        method = web.derive_payment_method(
            web._cell(row, txn_headers, "Payment Method", 11),
            cash_received,
            change,
            qid,
        )
        if not payment_fee and method == web.PAYMENT_METHOD_QRIS:
            payment_fee = web.calc_qris_fee(amount)
        customer = web._cell(row, txn_headers, "Customer Note", 5)
        record_items = items_by_txn.get(tid) or items_by_qr.get(qid) or []
        if payment_fee and record_items and not sum(web._int_money(item.get("payment_fee")) for item in record_items):
            web.apply_payment_fee_to_items(record_items, method, amount)
        records.append({
            "txn_id": tid,
            "qr_id": qid,
            "amount": amount,
            "updated_at": web._cell(row, txn_headers, "Updated At", 4),
            "updated_at_display": web._cell(row, txn_headers, "Updated At", 4),
            "customer_name": customer,
            "customer": customer,
            "customer_email": "",
            "discount": web._cell(row, txn_headers, "Discount", 6),
            "cashier_name": web._cell(row, txn_headers, "Cashier Name", 7),
            "gross": web._cell_int(row, txn_headers, "Gross", 8) or amount,
            "line_discount": web._cell_int(row, txn_headers, "Line Discount", 9),
            "cart_discount_amt": web._cell_int(row, txn_headers, "Cart Disc Amt", 10),
            "payment_method": method,
            "cash_received": cash_received,
            "change": change,
            "payment_fee": payment_fee,
            "net_amount": web._cell_int(row, txn_headers, "Net Amount") or (amount - payment_fee),
            "merchant_id": row_mid,
            "items": record_items,
        })
    return records


def migrate_history():
    count = 0
    for record in load_all_sheet_history():
        db.save_history(record, record.get("merchant_id"))
        count += 1
    return count


def _transaction_owner_map():
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT transaction_id, merchant_id FROM transactions")
            return {str(txn_id): web.normalize_merchant_id(mid) for txn_id, mid in cur.fetchall() if txn_id}


def _collision_safe_txn_id(txn_id, merchant_id, owners):
    owner = owners.get(txn_id)
    if not owner or owner == merchant_id:
        return txn_id, False
    base = f"{txn_id}-{merchant_id}"[:100]
    candidate = base
    counter = 2
    while owners.get(candidate) and owners.get(candidate) != merchant_id:
        suffix = f"-{counter}"
        candidate = f"{base[:100 - len(suffix)]}{suffix}"
        counter += 1
    return candidate, True


def migrate_local_history():
    state = load_local_state()
    tenant_data = state.get("tenant_data") if isinstance(state.get("tenant_data"), dict) else {}
    local_buckets = {}
    if state.get("history"):
        local_buckets[web.DEFAULT_MERCHANT_ID] = state.get("history") or []
    for mid, bucket in tenant_data.items():
        if isinstance(bucket, dict) and bucket.get("history"):
            local_buckets[web.normalize_merchant_id(mid)] = bucket.get("history") or []

    count = 0
    owners = _transaction_owner_map()
    for mid, records in local_buckets.items():
        merchant_id = web.normalize_merchant_id(mid)
        existing_ids = {str(record.get("txn_id") or "") for record in db.load_history(merchant_id)}
        for record in records:
            txn_id = str((record or {}).get("txn_id") or (record or {}).get("transaction_id") or "").strip()
            if not txn_id or txn_id in existing_ids:
                continue
            clean = dict(record)
            clean["merchant_id"] = web.normalize_merchant_id(clean.get("merchant_id") or merchant_id)
            safe_txn_id, collided = _collision_safe_txn_id(txn_id, clean["merchant_id"], owners)
            if safe_txn_id in existing_ids:
                continue
            if collided:
                print(f"local_txn_id_collision {txn_id} owner={owners.get(txn_id)} migrated_as={safe_txn_id}")
            clean["txn_id"] = safe_txn_id
            db.save_history(clean, clean["merchant_id"])
            existing_ids.add(safe_txn_id)
            owners[safe_txn_id] = clean["merchant_id"]
            count += 1
    return count


def migrate_email_templates():
    templates = web.load_email_templates()
    for key, tpl in templates.items():
        db.save_email_template(key, tpl)
    return len(templates)


def migrate_version():
    db.save_version(web.load_version_info())
    return 1


def migrate_password_config():
    rows = sheet_rows(web.SHEET_PASSWORDS, web.PASSWORDS_HEADER)
    if len(rows) <= 1:
        return 0
    headers = {name.strip(): idx for idx, name in enumerate(rows[0])}
    count = 0
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM password_config")
            for row in rows[1:]:
                fn = str(web._cell(row, headers, "Password Function", 1)).strip()
                value = str(web._cell(row, headers, "Password", 2)).strip()
                if not fn:
                    continue
                cur.execute(
                    "INSERT INTO password_config (password_function, password_value) VALUES (%s,%s)",
                    (fn, value),
                )
                count += 1
        conn.commit()
    return count


def main():
    if "--dry-run" in sys.argv:
        print("dry_run_not_supported: this migration is idempotent and writes to PostgreSQL")
        return 2
    db.ensure_schema()
    summary = {
        "merchants": migrate_merchants(),
        "settings": migrate_settings(),
        "accounts": migrate_accounts(),
        "vendors": migrate_vendors(),
        "stock_items": migrate_stock(),
        "transactions": migrate_history(),
        "local_transactions": migrate_local_history(),
        "email_templates": migrate_email_templates(),
        "version_changes": migrate_version(),
        "password_config": migrate_password_config(),
    }
    for key, value in summary.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
