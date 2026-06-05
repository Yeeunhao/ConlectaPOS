const qrState = {
  activeQr: null,
  settings: {},
  preview: null,
  displayEvent: null,
  cashierNotice: null,
  version: {},
  merchantId: "",
  accountId: "",
  language: "en",
};

const qrChannel = "BroadcastChannel" in window ? new BroadcastChannel("conlecta-qr") : null;
const DEVICE_ID_KEY = "conlecta_device_id";
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));
const CLOSED_QR_STORAGE_KEY = "conlecta_closed_qr_ids";
const CASHIER_NOTICE_STORAGE_KEY = "conlecta_cashier_payment_notice";
const CLOSED_QR_LIMIT = 300;
const ACTIVE_QR_TTL_MS = 30 * 60 * 1000;
const CASHIER_NOTICE_STALE_MS = 8000;
const CASHIER_NOTICE_GRACE_MS = 3000;
const ORPHAN_SUCCESS_CLEAR_MS = 12000;
const CASH_CHANGE_OVERLAY_MS = 6000;
const DISPLAY_EVENT_TTL_MS = 6000;
const QR_RENDER_SIZE = 512;
const DEFAULT_BRAND_LOGO = "/assets/ConlectaPosLogo.png";
const DISPLAY_LANGUAGE_STORAGE_KEY = "conlecta_ui_language";
const DISPLAY_LANGUAGES = {
  en: "English",
  id: "Indonesia",
  zh: "中文",
};
const DISPLAY_HTML_LANG = {
  en: "en",
  id: "id",
  zh: "zh-Hans",
};
const DISPLAY_I18N = {
  "Payment Display": { en: "Payment Display", id: "Tampilan Pembayaran", zh: "支付显示" },
  "Processing": { en: "Processing", id: "Memproses", zh: "处理中" },
  "Secure Conlecta access": { en: "Secure Conlecta access", id: "Akses Conlecta aman", zh: "安全访问 Conlecta" },
  "Checking user session...": { en: "Checking user session...", id: "Mengecek session user...", zh: "正在检查用户会话..." },
  "Please wait...": { en: "Please wait...", id: "Mohon tunggu...", zh: "请稍候..." },
  "Point of Sale": { en: "Point of Sale", id: "Point of Sale", zh: "销售终端" },
  "Payment": { en: "Payment", id: "Pembayaran", zh: "支付" },
  "Payment Update": { en: "Payment Update", id: "Update Pembayaran", zh: "支付更新" },
  "Payment Success": { en: "Payment Success", id: "Pembayaran Berhasil", zh: "支付成功" },
  "Payment completed.": { en: "Payment completed.", id: "Pembayaran selesai.", zh: "支付已完成。" },
  "QRIS Canceled": { en: "QRIS Canceled", id: "QRIS Dibatalkan", zh: "QRIS 已取消" },
  "QR Request Closed": { en: "QR Request Closed", id: "Permintaan QR Ditutup", zh: "二维码请求已关闭" },
  "The cashier closed QRIS. Please wait for a new QR.": { en: "The cashier closed QRIS. Please wait for a new QR.", id: "Kasir menutup QRIS. Silakan tunggu QR baru.", zh: "收银员已关闭 QRIS。请等待新的二维码。" },
  "Cash Payment": { en: "Cash Payment", id: "Pembayaran Tunai", zh: "现金支付" },
  "QRIS Success": { en: "QRIS Success", id: "QRIS Berhasil", zh: "QRIS 成功" },
  "Payment Successful": { en: "Payment Successful", id: "Pembayaran Sukses", zh: "支付成功" },
  "Cash payment summary": { en: "Total {total} - Paid {cash}", id: "Total {total} - Bayar {cash}", zh: "总计 {total} - 已付 {cash}" },
  "QRIS payment received": { en: "Payment {amount} received.", id: "Pembayaran {amount} diterima.", zh: "已收到付款 {amount}。" },
  "Change": { en: "Change", id: "Kembalian", zh: "找零" },
  "Item": { en: "Item", id: "Item", zh: "商品" },
  "Qty": { en: "Qty", id: "Qty", zh: "数量" },
  "Price": { en: "Price", id: "Harga", zh: "价格" },
  "Total Payment": { en: "Total Payment", id: "Total Pembayaran", zh: "支付总额" },
  "Cash Received": { en: "Cash Received", id: "Uang Diterima", zh: "收到现金" },
  "Total": { en: "Total", id: "Total", zh: "总计" },
  "Waiting for order": { en: "Waiting for order", id: "Menunggu order", zh: "等待订单" },
  "No line items": { en: "No line items", id: "Belum ada item", zh: "暂无商品" },
  "Waiting for cash payment confirmation...": { en: "Waiting for cash payment confirmation...", id: "Menunggu konfirmasi pembayaran tunai...", zh: "正在等待现金支付确认..." },
  "Waiting for cashier payment success confirmation.": { en: "Waiting for cashier payment success confirmation.", id: "Menunggu kasir klik OK pada notifikasi payment success.", zh: "等待收银员确认支付成功通知。" },
  "Checking cashier payment success notification...": { en: "Checking cashier payment success notification...", id: "Mengecek notifikasi payment success di cashier...", zh: "正在检查收银员端的支付成功通知..." },
  "Cashier payment success notification was not detected. Display will clear automatically if no notification appears.": { en: "Cashier payment success notification was not detected. Display will clear automatically if no notification appears.", id: "Cek cashier: notif Payment Success tidak terdeteksi. Jika notif tidak ada, display dibersihkan otomatis.", zh: "未检测到收银员端的支付成功通知。如没有通知，显示将自动清除。" },
  "CONLECTA POS - QRIS available - Secure and fast payment": { en: "CONLECTA POS - QRIS available - Secure and fast payment", id: "CONLECTA POS - QRIS tersedia - Pembayaran aman dan cepat", zh: "CONLECTA POS - 支持 QRIS - 安全快捷支付" },
  "Conlecta Version": { en: "Conlecta Version", id: "Versi Conlecta", zh: "Conlecta 版本" },
  "Online": { en: "ONLINE", id: "ONLINE", zh: "在线" },
  "Free": { en: "FREE", id: "GRATIS", zh: "免费" },
  "QRIS payment code": { en: "QRIS payment code", id: "Kode pembayaran QRIS", zh: "QRIS 支付码" },
};
let displayI18nAliasMap = null;

function displayBrandLogoUrl(settings = qrState.settings) {
  return String(settings?.brand_logo_url || "").trim() || DEFAULT_BRAND_LOGO;
}

function applyDisplayLogo(img, settings = qrState.settings) {
  if (!img) return;
  const url = displayBrandLogoUrl(settings);
  const mid = String(settings?.merchant_id || "");
  if (img.dataset.brandMerchant !== mid) {
    img.dataset.brandMerchant = mid;
    delete img.dataset.brandSrc;
  }
  img.onerror = () => {
    if (img.dataset.brandSrc !== DEFAULT_BRAND_LOGO) {
      img.dataset.brandSrc = DEFAULT_BRAND_LOGO;
      img.src = DEFAULT_BRAND_LOGO;
    } else {
      img.onerror = null;
    }
  };
  if (img.dataset.brandSrc === url && img.complete && img.naturalWidth > 0) return;
  img.dataset.brandSrc = url;
  img.src = url;
}
let displayEventTimer = null;
let orphanAckTimer = null;
let cashChangeTimer = null;
let refreshTimer = null;
let clockTimer = null;
let displayClosed = false;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value);
}

function normalizeDisplayI18nText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function buildDisplayI18nAliasMap() {
  const map = new Map();
  Object.entries(DISPLAY_I18N).forEach(([key, values]) => {
    map.set(normalizeDisplayI18nText(key), key);
    Object.values(values || {}).forEach((value) => {
      const normalized = normalizeDisplayI18nText(value);
      if (normalized) map.set(normalized, key);
    });
  });
  return map;
}

function displayI18nKeyFor(value) {
  if (!displayI18nAliasMap) displayI18nAliasMap = buildDisplayI18nAliasMap();
  return displayI18nAliasMap.get(normalizeDisplayI18nText(value)) || "";
}

function displayText(value, params = {}) {
  const key = DISPLAY_I18N[value] ? value : displayI18nKeyFor(value);
  let text = (key && (DISPLAY_I18N[key]?.[qrState.language] || DISPLAY_I18N[key]?.en)) || String(value || "");
  Object.entries(params || {}).forEach(([param, replacement]) => {
    text = text.replaceAll(`{${param}}`, String(replacement ?? ""));
  });
  return text;
}

function readDisplayLanguagePreference() {
  try {
    const stored = localStorage.getItem(DISPLAY_LANGUAGE_STORAGE_KEY);
    if (Object.prototype.hasOwnProperty.call(DISPLAY_LANGUAGES, stored)) return stored;
  } catch {
    // Keep the QR display usable if localStorage is blocked.
  }
  return "en";
}

function shouldSkipDisplayTranslationElement(el) {
  if (!el) return true;
  return Boolean(el.closest([
    "script",
    "style",
    "textarea",
    "select",
    "option",
    "code",
    "pre",
    "img",
    "video",
    "#display-shop",
    "#display-bottom-shop",
    "#display-bottom-address",
    "#display-marquee",
    ".payment-logo-cell",
    "#display-items .display-item span:first-child",
    "[data-i18n-skip]",
  ].join(",")));
}

function translateDisplayTextNode(node) {
  if (!node?.nodeValue || shouldSkipDisplayTranslationElement(node.parentElement)) return;
  const raw = node.nodeValue;
  const leading = raw.match(/^\s*/)?.[0] || "";
  const trailing = raw.match(/\s*$/)?.[0] || "";
  const trimmed = normalizeDisplayI18nText(raw);
  if (!trimmed) return;
  const key = displayI18nKeyFor(trimmed);
  if (key) node.nodeValue = `${leading}${displayText(key)}${trailing}`;
}

function translateDisplayAttributes(root) {
  const elements = [];
  if (root?.nodeType === Node.ELEMENT_NODE) elements.push(root);
  elements.push(...(root?.querySelectorAll?.("[placeholder], [title], [aria-label], [alt]") || []));
  elements.forEach((el) => {
    if (shouldSkipDisplayTranslationElement(el)) return;
    ["placeholder", "title", "aria-label", "alt"].forEach((attr) => {
      const value = el.getAttribute?.(attr);
      const key = displayI18nKeyFor(value);
      if (key) el.setAttribute(attr, displayText(key));
    });
  });
}

function applyDisplayLanguage(root = document.body) {
  if (!root) return;
  document.documentElement.lang = DISPLAY_HTML_LANG[qrState.language] || "en";
  const walkerRoot = root.nodeType === Node.DOCUMENT_NODE ? root.body : root;
  if (walkerRoot?.nodeType === Node.TEXT_NODE) {
    translateDisplayTextNode(walkerRoot);
  } else if (walkerRoot) {
    const walker = document.createTreeWalker(walkerRoot, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      translateDisplayTextNode(node);
      node = walker.nextNode();
    }
    translateDisplayAttributes(walkerRoot);
  }
}

function bootstrapDisplayLanguage() {
  qrState.language = readDisplayLanguagePreference();
  applyDisplayLanguage(document.body);
}

function formatRp(value) {
  return "Rp " + Number(value || 0).toLocaleString("id-ID", { maximumFractionDigits: 0 });
}

function qrIdentityKeys(source) {
  const keys = [];
  const qrId = String(source?.id || source?.qr_id || "").trim();
  const txnId = String(source?.txn_id || source?.transaction_id || "").trim();
  if (qrId) keys.push(`qr:${qrId}`);
  if (txnId) keys.push(`txn:${txnId}`);
  return keys;
}

function readClosedQrMap() {
  try {
    const raw = localStorage.getItem(CLOSED_QR_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function writeClosedQrMap(map) {
  try {
    const entries = Object.entries(map)
      .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0))
      .slice(0, CLOSED_QR_LIMIT);
    localStorage.setItem(CLOSED_QR_STORAGE_KEY, JSON.stringify(Object.fromEntries(entries)));
  } catch {
    // Ignore storage failures; the current display state is still sanitized.
  }
}

function rememberClosedQr(source) {
  const keys = qrIdentityKeys(source);
  if (!keys.length) return;
  const map = readClosedQrMap();
  const now = Date.now();
  keys.forEach((key) => { map[key] = now; });
  writeClosedQrMap(map);
  localStorage.removeItem("conlecta_active_qr");
}

function isClosedQr(source) {
  const status = String(source?.status || source?.type || "").trim().toLowerCase();
  if (["paid", "success", "succeeded", "settled", "completed", "dismissed", "dismiss", "cancelled", "canceled"].includes(status)) {
    return true;
  }
  const createdTs = Number(source?.created_ts || 0) * 1000;
  if (createdTs && Date.now() - createdTs > ACTIVE_QR_TTL_MS) return true;
  const map = readClosedQrMap();
  return qrIdentityKeys(source).some((key) => Boolean(map[key]));
}

function sanitizeActiveQr(active) {
  if (!active) return null;
  if (isClosedQr(active)) {
    localStorage.removeItem("conlecta_active_qr");
    return null;
  }
  return active;
}

function terminalDisplayEvent(event) {
  return ["success", "dismissed"].includes(String(event?.type || "").trim().toLowerCase());
}

function displayEventAgeMs(event) {
  const created = Number(event?.created_ts || 0) * 1000;
  return created ? Date.now() - created : 0;
}

function noticeTimestampMs(notice) {
  const raw = Number(notice?.updated_ts || 0);
  if (!raw) return 0;
  return raw > 100000000000 ? raw : raw * 1000;
}

function cashierNoticeFresh(notice) {
  const ts = noticeTimestampMs(notice);
  return Boolean(notice?.visible && ts && Date.now() - ts <= CASHIER_NOTICE_STALE_MS);
}

function cashierNoticeMatches(event, notice = qrState.cashierNotice || readLocalCashierNotice()) {
  if (!event || !cashierNoticeFresh(notice)) return false;
  const eventTxn = String(event.txn_id || event.transaction_id || "").trim();
  const eventQr = String(event.qr_id || event.id || "").trim();
  const noticeTxn = String(notice.txn_id || notice.transaction_id || "").trim();
  const noticeQr = String(notice.qr_id || notice.id || "").trim();
  return Boolean((eventTxn && eventTxn === noticeTxn) || (eventQr && eventQr === noticeQr));
}

function successNeedsCashierAck(event) {
  return Boolean(event?.requires_ack && String(event.type || "").toLowerCase() === "success");
}

function cashierValidationMessage(event) {
  if (!successNeedsCashierAck(event)) return "";
  if (cashierNoticeMatches(event)) return displayText("Waiting for cashier payment success confirmation.");
  if (displayEventAgeMs(event) < CASHIER_NOTICE_GRACE_MS) return displayText("Checking cashier payment success notification...");
  return displayText("Cashier payment success notification was not detected. Display will clear automatically if no notification appears.");
}

async function acknowledgeDisplayEvent(event, reason = "qr_display_orphan") {
  if (!event) return;
  try {
    const result = await api("/api/display-event/ack", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        txn_id: event.txn_id || "",
        qr_id: event.qr_id || event.id || "",
        merchant_id: event.merchant_id || qrState.settings?.merchant_id || "",
        reason,
      }),
    });
    qrState.displayEvent = result.display_event || null;
  } catch {
    qrState.displayEvent = null;
  }
  localStorage.removeItem("conlecta_display_event");
  renderDisplay();
}

function scheduleOrphanSuccessClear(event) {
  clearTimeout(orphanAckTimer);
  orphanAckTimer = null;
  if (!successNeedsCashierAck(event) || cashierNoticeMatches(event)) return;
  const delay = Math.max(0, ORPHAN_SUCCESS_CLEAR_MS - displayEventAgeMs(event));
  orphanAckTimer = setTimeout(() => {
    if (qrState.displayEvent === event && !cashierNoticeMatches(event)) {
      acknowledgeDisplayEvent(event);
    }
  }, delay + 80);
}

async function api(path, options = {}) {
  const init = {
    cache: "no-store",
    headers: {
      "X-Conlecta-Device-Id": getDeviceId(),
      ...(options.headers || {}),
    },
    ...options,
  };
  const res = await fetch(path, init);
  const data = await res.json();
  if (!res.ok || data.ok === false) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function getDeviceId() {
  let id = localStorage.getItem(DEVICE_ID_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(DEVICE_ID_KEY, id);
  }
  return id;
}

function deviceStorageKey(name) {
  return `${name}:${getDeviceId()}`;
}

function settingsStorageKey() {
  const aid = sessionAccountId();
  if (aid) return `${"conlecta_settings"}:${getDeviceId()}:${aid}`;
  return deviceStorageKey("conlecta_settings");
}

function sessionMerchantId() {
  return String(
    qrState.merchantId
    || localStorage.getItem(deviceStorageKey("conlecta_display_merchant"))
    || qrState.settings?.merchant_id
    || "",
  ).trim();
}

function sessionAccountId() {
  return String(
    qrState.accountId
    || localStorage.getItem(deviceStorageKey("conlecta_display_account"))
    || "",
  ).trim();
}

function localMatchesSession(settings = {}) {
  const sessionMid = sessionMerchantId();
  const sessionAid = sessionAccountId();
  const localMid = String(settings.merchant_id || "").trim();
  if (sessionMid && localMid && sessionMid !== localMid) return false;
  if (sessionAid) {
    const cachedAid = String(
      localStorage.getItem(deviceStorageKey("conlecta_display_account")) || "",
    ).trim();
    if (cachedAid && cachedAid !== sessionAid) return false;
  }
  if (!sessionMid) return true;
  if (!localMid) return false;
  return sessionMid === localMid;
}

function readRawLocalSettings() {
  try {
    const did = getDeviceId();
    const lockedAid = String(displaySession.accountId || "").trim();
    if (lockedAid) {
      const scoped = localStorage.getItem(`conlecta_settings:${did}:${lockedAid}`);
      if (scoped) return JSON.parse(scoped);
      return {};
    }
    const raw = localStorage.getItem(settingsStorageKey());
    if (raw) return JSON.parse(raw);
    if (!sessionAccountId()) {
      const legacy = localStorage.getItem(deviceStorageKey("conlecta_settings"));
      return legacy ? JSON.parse(legacy) : {};
    }
    return {};
  } catch {
    return {};
  }
}

function rememberDisplaySession(merchantId = "", accountId = "") {
  qrState.merchantId = String(merchantId || "").trim();
  qrState.accountId = String(accountId || "").trim();
  if (qrState.merchantId) {
    localStorage.setItem(deviceStorageKey("conlecta_display_merchant"), qrState.merchantId);
  }
  if (qrState.accountId) {
    localStorage.setItem(deviceStorageKey("conlecta_display_account"), qrState.accountId);
  }
}

function clearDisplayLocalCache() {
  localStorage.removeItem(deviceStorageKey("conlecta_active_qr"));
  localStorage.removeItem(deviceStorageKey("conlecta_settings"));
  localStorage.removeItem(settingsStorageKey());
  localStorage.removeItem(deviceStorageKey("conlecta_display_preview"));
  localStorage.removeItem(deviceStorageKey("conlecta_display_event"));
  localStorage.removeItem(deviceStorageKey("conlecta_display_merchant"));
  localStorage.removeItem(deviceStorageKey("conlecta_display_account"));
  qrState.activeQr = null;
  qrState.settings = {};
  qrState.preview = null;
  qrState.displayEvent = null;
  qrState.cashierNotice = null;
}

function readLocalQr() {
  if (!localMatchesSession(readRawLocalSettings())) return null;
  try {
    const raw = localStorage.getItem(deviceStorageKey("conlecta_active_qr"));
    return raw ? sanitizeActiveQr(JSON.parse(raw)) : null;
  } catch {
    return null;
  }
}

function readLocalSettings() {
  const settings = readRawLocalSettings();
  return localMatchesSession(settings) ? settings : {};
}

function readLocalPreview() {
  try {
    const raw = localStorage.getItem(deviceStorageKey("conlecta_display_preview"));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function readLocalDisplayEvent() {
  try {
    const raw = localStorage.getItem(deviceStorageKey("conlecta_display_event"));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function readLocalCashierNotice() {
  try {
    const raw = localStorage.getItem(CASHIER_NOTICE_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function readLocalVersion() {
  try {
    const raw = localStorage.getItem("conlecta_version");
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function displayEventExpired(event) {
  if (!event) return true;
  return Date.now() > Number(event.expires_ts || 0) * 1000;
}

function currentDisplayEvent() {
  if (displayEventExpired(qrState.displayEvent)) {
    qrState.displayEvent = null;
    localStorage.removeItem(deviceStorageKey("conlecta_display_event"));
  } else if (terminalDisplayEvent(qrState.displayEvent)) {
    rememberClosedQr(qrState.displayEvent);
    qrState.activeQr = sanitizeActiveQr(qrState.activeQr);
  }
  return qrState.displayEvent;
}

function scheduleDisplayEventExpiry(event) {
  clearTimeout(displayEventTimer);
  displayEventTimer = null;
  if (!event) return;
  const delay = Math.max(0, Number(event.expires_ts || 0) * 1000 - Date.now(), DISPLAY_EVENT_TTL_MS - displayEventAgeMs(event));
  displayEventTimer = setTimeout(() => {
    if (displayEventExpired(qrState.displayEvent)) {
      qrState.displayEvent = null;
      localStorage.removeItem(deviceStorageKey("conlecta_display_event"));
      renderDisplay();
    }
  }, delay + 80);
}

function displayEventCopy(event) {
  const type = String(event?.type || "").trim().toLowerCase();
  const isDismissed = type === "dismissed";
  const isCashSuccess = type === "success" && isCashPayment(event);
  const isQrisSuccess = type === "success" && !isCashPayment(event);
  if (isDismissed) {
    return {
      kicker: displayText("QRIS Canceled"),
      title: displayText("QR Request Closed"),
      message: event.message || displayText("The cashier closed QRIS. Please wait for a new QR."),
      tone: "dismiss",
    };
  }
  if (isCashSuccess) {
    return {
      kicker: displayText("Cash Payment"),
      title: displayText("Payment Success"),
      message: event.message || displayText("Cash payment summary", {
        total: formatRp(event.amount),
        cash: formatRp(event.cash_received || event.amount),
      }),
      tone: "cash-success",
    };
  }
  if (isQrisSuccess) {
    return {
      kicker: displayText("QRIS Success"),
      title: displayText("Payment Successful"),
      message: event.message || displayText("QRIS payment received", { amount: formatRp(event.amount) }),
      tone: "qris-success",
    };
  }
  return {
    kicker: event.title || displayText("Payment"),
    title: event.title || displayText("Payment Update"),
    message: event.message || "",
    tone: "info",
  };
}

function applyDisplayNotificationState(event) {
  const copy = event ? displayEventCopy(event) : null;
  document.body.classList.toggle("display-notify-active", Boolean(event));
  document.body.classList.toggle("display-notify-success", copy?.tone === "qris-success" || copy?.tone === "cash-success");
  document.body.classList.toggle("display-notify-dismiss", copy?.tone === "dismiss");
  document.body.classList.toggle("display-notify-cash", copy?.tone === "cash-success");
  if (copy?.tone) {
    document.body.dataset.notifyTone = copy.tone;
  } else {
    delete document.body.dataset.notifyTone;
  }
}

function updateClock() {
  const now = new Date();
  $("#display-clock").textContent = now.toLocaleString("id-ID", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function renderVersion() {
  const version = qrState.version || {};
  $("#display-version-label").textContent = version.label || displayText("Conlecta Version");
}

const DISPLAY_DEFAULT_THEME = "crystal_bloom";

let displayRenderTimer = null;
let lastAppliedTheme = "";
let lastBrandSignature = "";
const displaySession = {
  merchantId: "",
  accountId: "",
  theme: "",
  locked: false,
};

function lockDisplaySession(merchantId = "", accountId = "", theme = "", { force = false } = {}) {
  const mid = String(merchantId || "").trim();
  const aid = String(accountId || "").trim();
  const nextTheme = String(theme || "").trim();
  const accountChanged = Boolean(
    displaySession.locked
    && aid
    && displaySession.accountId
    && aid !== displaySession.accountId,
  );
  if (accountChanged || force) {
    displaySession.merchantId = mid || displaySession.merchantId;
    displaySession.accountId = aid || displaySession.accountId;
    displaySession.theme = nextTheme || displaySession.theme;
    displaySession.locked = Boolean(displaySession.merchantId || displaySession.accountId);
    return;
  }
  if (mid) displaySession.merchantId = mid;
  if (aid) displaySession.accountId = aid;
  if (nextTheme) displaySession.theme = nextTheme;
  displaySession.locked = Boolean(displaySession.merchantId || displaySession.accountId);
}

function bootstrapDisplaySession() {
  const mid = localStorage.getItem(deviceStorageKey("conlecta_display_merchant")) || "";
  const aid = localStorage.getItem(deviceStorageKey("conlecta_display_account")) || "";
  const settings = readLocalSettings();
  lockDisplaySession(mid || settings.merchant_id || "", aid, settings.active_theme || "");
}

function displaySettingsSignature(settings = {}) {
  return [
    settings.merchant_id || "",
    settings.active_theme || "",
    settings.brand_logo_url || "",
    JSON.stringify(settings.qris_frame || null),
  ].join("|");
}

function scheduleRenderDisplay() {
  clearTimeout(displayRenderTimer);
  displayRenderTimer = setTimeout(() => {
    displayRenderTimer = null;
    renderDisplay();
  }, 60);
}

function serverPayloadMatchesDisplaySession(data = {}) {
  if (!displaySession.locked) return true;
  const mid = String(data.merchant_id || data.settings?.merchant_id || "").trim();
  const aid = String(data.account_id || "").trim();
  if (displaySession.merchantId && mid && mid !== displaySession.merchantId) return false;
  if (displaySession.accountId && aid && aid !== displaySession.accountId) return false;
  return true;
}

function storageEventMatchesDisplaySession(key) {
  if (!key) return false;
  const did = getDeviceId();
  const aid = displaySession.accountId || sessionAccountId();
  const allowed = new Set([
    deviceStorageKey("conlecta_active_qr"),
    deviceStorageKey("conlecta_display_preview"),
    deviceStorageKey("conlecta_display_event"),
    deviceStorageKey("conlecta_display_merchant"),
    deviceStorageKey("conlecta_display_account"),
    CASHIER_NOTICE_STORAGE_KEY,
    CLOSED_QR_STORAGE_KEY,
    "conlecta_version",
  ]);
  if (allowed.has(key)) return true;
  if (key === deviceStorageKey("conlecta_settings")) {
    return !displaySession.accountId && !sessionAccountId();
  }
  if (aid && key === `conlecta_settings:${did}:${aid}`) return true;
  if (!displaySession.accountId && key.startsWith(`conlecta_settings:${did}:`)) return false;
  return false;
}

function reloadDisplayFromLocalStorage() {
  const settings = readLocalSettings();
  if (displaySession.theme) settings.active_theme = displaySession.theme;
  qrState.settings = settings;
  qrState.displayEvent = readLocalDisplayEvent();
  qrState.cashierNotice = readLocalCashierNotice();
  if (terminalDisplayEvent(qrState.displayEvent)) rememberClosedQr(qrState.displayEvent);
  qrState.activeQr = readLocalQr();
  qrState.version = readLocalVersion();
  qrState.preview = readLocalPreview();
}

function applyDisplayTheme(themeId) {
  const theme = themeId && window.ConlectaTheme?.isValid?.(themeId)
    ? themeId
    : DISPLAY_DEFAULT_THEME;
  if (theme === lastAppliedTheme) return theme;
  lastAppliedTheme = theme;
  displaySession.theme = theme;
  if (window.ConlectaTheme?.apply) {
    window.ConlectaTheme.apply(theme, { persist: false });
  } else {
    document.body.dataset.theme = theme;
  }
  return theme;
}

function bootstrapDisplayTheme(settings = readLocalSettings()) {
  applyDisplayTheme(settings?.active_theme);
}

function applyBrand() {
  const settings = qrState.settings || {};
  const theme = applyDisplayTheme(displaySession.theme || settings.active_theme);
  const signature = displaySettingsSignature({ ...settings, active_theme: theme });
  const shop = settings.shop_name || "Conlecta";
  const address = [settings.shop_address, settings.shop_postcode].filter(Boolean).join(" | ") || displayText("Point of Sale");
  if (signature !== lastBrandSignature) {
    lastBrandSignature = signature;
    applyDisplayQrisFrame(settings);
    $$(".js-display-logo").forEach((img) => applyDisplayLogo(img, settings));
  }
  $("#display-shop").textContent = shop;
  $("#display-bottom-shop").textContent = shop;
  $("#display-bottom-address").textContent = address;
  $("#display-hero-title").textContent = "";
  const marquee = settings.marquee_msgs?.length
    ? settings.marquee_msgs.join("  -  ")
    : displayText("CONLECTA POS - QRIS available - Secure and fast payment");
  $("#display-marquee").textContent = marquee;
  applyVideoPlaylist();
}

function paymentLogoPaths() {
  return qrState.settings?.payment_image_urls?.length ? qrState.settings.payment_image_urls : [
    "/assets/Icon/Gsingapay.jpeg",
    "/assets/Icon/MyBca.jpg",
    "/assets/Icon/OVO.jpg",
    "/assets/Icon/Qris.png",
    "/assets/Icon/eGopay.png",
    "/assets/Icon/images (1).png",
    "/assets/Icon/images.jpg",
    "/assets/Icon/shopee-pay-logo-png_seeklogo-406839.png",
  ];
}

function paymentLogoLabel(src) {
  const clean = String(src || "").split("?")[0];
  const file = decodeURIComponent(clean.split("/").pop() || "");
  const base = file.replace(/\.[a-z0-9]+$/i, "").replace(/^\d+[_-]/, "");
  const key = base.toLowerCase().replace(/[\s()]+/g, "_").replace(/[-]+/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "");
  const known = {
    gsingapay: "SingaPay",
    singapay: "SingaPay",
    mybca: "BCA",
    ovo: "OVO",
    qris: "QRIS",
    egopay: "GoPay",
    images_1: "BRI",
    images: "Mandiri",
    shopee_pay_logo_png_seeklogo_406839: "ShopeePay",
  };
  return known[key] || base.replace(/[_-]+/g, " ").replace(/\b\w/g, (ch) => ch.toUpperCase()) || displayText("Payment");
}

function linePriceHtml(item) {
  const qty = Number(item.qty || 0);
  const unit = Number(item.unit_price || item.amount || item.price || 0);
  const gross = Number(item.gross || unit * qty);
  const subtotal = Number(item.subtotal || 0);
  const tip = Number(item.tip_fixed || 0);
  const discount = Number(item.line_discount || Math.max(0, gross - Math.max(0, subtotal - tip)));
  if (discount && gross) {
    return `<span class="price-strike">${formatRp(gross)}</span> ${item.free ? displayText("Free") : formatRp(subtotal)}`;
  }
  return formatRp(subtotal || unit * qty);
}

function groupedDisplayItems(items = []) {
  const rows = [];
  const groups = new Map();
  items.forEach((item) => {
    if (item.line_type === "package" && item.package_items) {
      rows.push({
        type: "package",
        package_id: item.package_id || item.id,
        package_name: item.package_name || item.name,
        qty: item.qty || 1,
        subtotal: item.subtotal || 0,
        children: item.package_items || [],
        free: item.free,
      });
      return;
    }
    const packageId = String(item.package_id || "").trim();
    if (!packageId) {
      rows.push({ type: "item", item });
      return;
    }
    const key = String(item.package_line_id || packageId);
    let group = groups.get(key);
    if (!group) {
      group = {
        type: "package",
        package_id: packageId,
        package_name: item.package_name || "Package",
        qty: Number(item.package_qty || 1) || 1,
        subtotal: Number(item.package_total || 0),
        children: [],
        free: item.free,
      };
      groups.set(key, group);
      rows.push(group);
    }
    group.children.push(item);
    if (!group.subtotal) group.subtotal += Number(item.subtotal || 0);
  });
  return rows;
}

function displayItemsHtml(items = []) {
  return groupedDisplayItems(items).map((row) => {
    if (row.type === "package") {
      const total = row.subtotal || row.children.reduce((sum, child) => sum + Number(child.subtotal || 0), 0);
      return `
        <div class="display-item display-package-item">
          <span>${escapeHtml(row.package_name)}${row.free ? ` [${escapeHtml(displayText("Free"))}]` : ""}</span>
          <span>x${escapeHtml(row.qty || 1)}</span>
          <span class="line-price">${formatRp(total)}</span>
          <div class="display-package-lines">
            ${row.children.map((child) => `
              <div>
                <span>${escapeHtml(child.item_name || child.name || "")}</span>
                <span>${linePriceHtml(child)}</span>
              </div>
            `).join("")}
          </div>
        </div>
      `;
    }
    const item = row.item || {};
    return `
      <div class="display-item">
        <span>${escapeHtml(item.item_name || item.name || "")}${item.free ? ` [${escapeHtml(displayText("Free"))}]` : ""}</span>
        <span>x${escapeHtml(item.qty || 0)}</span>
        <span class="line-price">${linePriceHtml(item)}</span>
      </div>
    `;
  }).join("") || `<div class="empty-state">${escapeHtml(displayText("No line items"))}</div>`;
}

let videoPlaylistIndex = 0;
let videoPlaylistSignature = "";

function setupVideoPlaylistPlayer() {
  const video = $("#display-video");
  if (!video || video.dataset.playlistBound === "1") return;
  video.dataset.playlistBound = "1";
  video.addEventListener("ended", () => {
    const playlist = qrState.settings?.video_playlist_urls || [];
    if (!playlist.length) return;
    if (playlist.length <= 1) return;
    videoPlaylistIndex = (videoPlaylistIndex + 1) % playlist.length;
    applyVideoPlaylist(videoPlaylistIndex, { fromEnded: true });
  });
}

function applyVideoPlaylist(forceIndex = null, options = {}) {
  const video = $("#display-video");
  const playlist = qrState.settings?.video_playlist_urls || [];
  if (!video || !playlist.length) return;

  video.loop = playlist.length <= 1;

  const signature = playlist.join("|");
  if (forceIndex === null && signature === videoPlaylistSignature && video.currentSrc && !options.forceRestart) {
    return;
  }

  if (signature !== videoPlaylistSignature) {
    videoPlaylistSignature = signature;
    if (forceIndex === null) videoPlaylistIndex = 0;
  }

  if (forceIndex !== null) {
    videoPlaylistIndex = ((forceIndex % playlist.length) + playlist.length) % playlist.length;
  }

  const nextSrc = playlist[videoPlaylistIndex];
  const currentSrc = video.currentSrc || video.getAttribute("src") || "";
  const sameSrc = currentSrc.endsWith(nextSrc) || currentSrc.includes(encodeURI(nextSrc.split("/").pop() || ""));
  const restartSame = sameSrc && (options.forceRestart || options.fromEnded);
  if (restartSame) {
    video.currentTime = 0;
  } else if (!sameSrc) {
    video.src = nextSrc;
    video.load();
  }
  video.play?.().catch(() => null);
}

function videoMediaBasename(value) {
  const text = String(value || "").split("?")[0];
  try {
    return decodeURIComponent(text.split("/").pop() || "").toLowerCase();
  } catch {
    return text.split("/").pop()?.toLowerCase() || "";
  }
}

function videoMediaKeysMatch(a, b) {
  const left = String(a || "").split("?")[0].toLowerCase();
  const right = String(b || "").split("?")[0].toLowerCase();
  if (!left || !right) return false;
  if (left === right) return true;
  const leftBase = videoMediaBasename(left);
  const rightBase = videoMediaBasename(right);
  return Boolean(leftBase && rightBase && leftBase === rightBase);
}

function playVideoImmediately(urlOrPath) {
  const raw = String(urlOrPath || "").trim();
  if (!raw) return;
  setupVideoPlaylistPlayer();
  const playlist = qrState.settings?.video_playlist_urls || [];
  const idx = playlist.findIndex((entry) => videoMediaKeysMatch(entry, raw));
  if (idx >= 0) {
    applyVideoPlaylist(idx, { forceRestart: true });
    return;
  }

  const video = $("#display-video");
  if (!video) return;
  let src = raw;
  if (!/^https?:\/\//i.test(src) && !src.startsWith("/")) {
    const match = playlist.find((entry) => videoMediaKeysMatch(entry, raw));
    if (match) src = match;
  }
  video.loop = playlist.length <= 1;
  const currentSrc = video.currentSrc || video.getAttribute("src") || "";
  const sameSrc = videoMediaKeysMatch(currentSrc, src);
  if (sameSrc) {
    video.currentTime = 0;
  } else {
    video.src = src;
    video.load();
  }
  video.play?.().catch(() => null);
}

let lastPaymentLogoSignature = "";

function renderPaymentLogos() {
  const paths = paymentLogoPaths();
  const sig = paths.join("|");
  if (sig === lastPaymentLogoSignature) return;
  lastPaymentLogoSignature = sig;
  $("#display-payment-logos").innerHTML = paths.map((src) => `
    <div class="payment-logo-cell">
      <span class="payment-logo-img"><img src="${escapeAttr(src)}" alt=""></span>
      <strong>${escapeHtml(paymentLogoLabel(src))}</strong>
    </div>
  `).join("");
}

function isCashPayment(source) {
  return String(source?.payment_method || "").trim().toLowerCase() === "cash";
}

function previewCashInfo(preview) {
  const cash = Number(preview?.cash_received || 0);
  const amount = Number(preview?.amount || 0);
  const change = Math.max(0, Number(preview?.change ?? (cash - amount)));
  const active = cash > 0 || isCashPayment(preview);
  return { active, cash, amount, change };
}

function qrImageSrcKey(active) {
  if (!active) return "";
  const id = String(active.id || active.txn_id || "").trim();
  const hasImage = Boolean(String(active.qr_image || "").trim());
  return `${id}:${hasImage ? "img" : "data"}`;
}

function applyDisplayQrisFrame(settings = qrState.settings) {
  const layout = window.ConlectaQrisFrame?.layoutFromSettings?.(settings)
    || window.ConlectaQrisFrame?.normalizeLayout?.();
  window.ConlectaQrisFrame?.applyQrisFrame?.($("#display-stage-qr"), layout);
  return layout;
}

function preloadQrisFrame(settings = qrState.settings) {
  applyDisplayQrisFrame(settings);
}

function updateStageQrImage(active) {
  const img = $("#display-stage-qr-img");
  if (!img || !active) return;
  const src = qrImageSrc(active, QR_RENDER_SIZE);
  if (!src) return;
  const srcKey = qrImageSrcKey(active);
  if (img.dataset.qrSrcKey === srcKey && img.complete && img.naturalWidth > 0) return;
  applyDisplayQrisFrame(qrState.settings);
  img.dataset.qrSrcKey = srcKey;
  img.dataset.qrSrc = src;
  img.src = src;
}

function scheduleCashChangeClear(event) {
  clearTimeout(cashChangeTimer);
  cashChangeTimer = null;
  if (!event || event.type !== "success" || !isCashPayment(event)) return;
  const delay = Math.max(0, CASH_CHANGE_OVERLAY_MS - displayEventAgeMs(event));
  cashChangeTimer = setTimeout(() => {
    if (qrState.displayEvent !== event) return;
    qrState.displayEvent = null;
    localStorage.removeItem(deviceStorageKey("conlecta_display_event"));
    renderDisplay();
  }, delay + 80);
}

function renderCashLive(preview) {
  const panel = $("#display-cash-live");
  const changeRow = $("#display-cash-change-row");
  if (!panel) return;
  const cashInfo = previewCashInfo(preview);
  if (!cashInfo.active || cashInfo.cash <= 0) {
    panel.hidden = true;
    if (changeRow) changeRow.hidden = true;
    return;
  }
  panel.hidden = false;
  $("#display-cash-received").textContent = formatRp(cashInfo.cash);
  if (changeRow) {
    const showChange = cashInfo.amount > 0 && cashInfo.cash >= cashInfo.amount;
    changeRow.hidden = !showChange;
    if (showChange) $("#display-cash-change").textContent = formatRp(cashInfo.change);
  }
}

function qrImageSrc(active, size = 420) {
  if (!active) return "";
  const image = String(active.qr_image || "").trim();
  if (image) return image;
  const data = String(active.qr_data || "").trim();
  if (!data) return "";
  return `https://api.qrserver.com/v1/create-qr-code/?size=${size}x${size}&data=${encodeURIComponent(data)}`;
}

function hasQrPayload(active) {
  return Boolean(active && (String(active.qr_image || "").trim() || String(active.qr_data || "").trim()));
}

function renderDisplay() {
  if (displayClosed) return;
  applyBrand();
  renderVersion();
  renderPaymentLogos();
  const event = currentDisplayEvent();
  qrState.activeQr = sanitizeActiveQr(qrState.activeQr);
  const active = qrState.activeQr;
  scheduleDisplayEventExpiry(event);
  scheduleOrphanSuccessClear(event);
  scheduleCashChangeClear(event);
  const preview = qrState.preview || {};
  const view = active || event || preview;
  const hasActiveQr = hasQrPayload(active);
  const hasEvent = Boolean(event);
  const items = hasEvent ? [] : (view.items || []);
  const stageQr = $("#display-stage-qr");
  const stageEvent = $("#display-stage-event");
  const stageEventCard = $(".stage-event-card");
  const video = $("#display-video");
  const paymentArea = $(".display-payment-area");
  const eventPanel = $("#display-event-panel");
  const cashLive = previewCashInfo(hasEvent || hasActiveQr ? {} : preview);

  if (hasEvent) {
    const copy = displayEventCopy(event);
    const isDismissed = copy.tone === "dismiss";
    const isCashSuccess = copy.tone === "cash-success";
    stageQr.hidden = true;
    stageEvent.hidden = false;
    video.hidden = true;
    paymentArea.hidden = true;
    eventPanel.hidden = false;
    if (stageEventCard) {
      stageEventCard.classList.toggle("is-cash-change", isCashSuccess);
      stageEventCard.classList.toggle("is-qris-success", copy.tone === "qris-success");
      stageEventCard.classList.toggle("is-dismissed", isDismissed);
      stageEventCard.dataset.notifyTone = copy.tone;
    }
    if (eventPanel) eventPanel.dataset.notifyTone = copy.tone;
    applyDisplayNotificationState(event);
    if (isCashSuccess) {
      $("#display-stage-event-kicker").textContent = copy.kicker;
      $("#display-stage-event-title").textContent = displayText("Change");
      $("#display-stage-event-message").textContent = copy.message;
      $("#display-stage-event-total").textContent = formatRp(event.change || 0);
      $("#display-event-kicker").textContent = copy.kicker;
      $("#display-event-title").textContent = displayText("Change");
      $("#display-event-message").textContent = copy.message;
      $("#display-event-total").textContent = formatRp(event.change || 0);
    } else {
      $("#display-stage-event-kicker").textContent = copy.kicker;
      $("#display-stage-event-title").textContent = copy.title;
      $("#display-stage-event-message").textContent = copy.message;
      $("#display-stage-event-total").textContent = formatRp(event.amount);
      $("#display-event-kicker").textContent = copy.kicker;
      $("#display-event-title").textContent = copy.title;
      $("#display-event-message").textContent = copy.message;
      $("#display-event-total").textContent = formatRp(event.amount);
    }
    renderCashLive({});
  } else if (hasActiveQr) {
    applyDisplayNotificationState(null);
    if (stageEventCard) {
      stageEventCard.classList.remove("is-cash-change", "is-qris-success", "is-dismissed");
      delete stageEventCard.dataset.notifyTone;
    }
    if (eventPanel) delete eventPanel.dataset.notifyTone;
    updateStageQrImage(active);
    stageQr.hidden = false;
    stageEvent.hidden = true;
    video.hidden = true;
    paymentArea.hidden = true;
    eventPanel.hidden = true;
    renderCashLive({});
  } else {
    applyDisplayNotificationState(null);
    if (stageEventCard) {
      stageEventCard.classList.remove("is-cash-change", "is-qris-success", "is-dismissed");
      delete stageEventCard.dataset.notifyTone;
    }
    if (eventPanel) delete eventPanel.dataset.notifyTone;
    const qrImg = $("#display-stage-qr-img");
    if (qrImg) {
      qrImg.removeAttribute("src");
      delete qrImg.dataset.qrSrc;
      delete qrImg.dataset.qrSrcKey;
    }
    stageQr.hidden = true;
    stageEvent.hidden = true;
    video.hidden = false;
    paymentArea.hidden = false;
    eventPanel.hidden = true;
    if (stageEventCard) stageEventCard.classList.remove("is-cash-change");
    video.play?.().catch(() => null);
    renderCashLive(preview);
  }

  if (!items.length) {
    $("#display-status").textContent = "";
    $("#display-total").textContent = event ? formatRp(event.amount) : formatRp(preview.amount || 0);
    $("#display-items").innerHTML = `<div class="empty-state">${escapeHtml(displayText("Waiting for order"))}</div>`;
    $("#display-payment-logos").hidden = hasEvent || hasActiveQr;
    $("#display-hint").textContent = cashLive.active && cashLive.cash > 0 && !hasEvent && !hasActiveQr
      ? displayText("Waiting for cash payment confirmation...")
      : cashierValidationMessage(event);
    return;
  }

  $("#display-status").textContent = "";
  $("#display-total").textContent = formatRp(view.amount);
  $("#display-items").innerHTML = displayItemsHtml(items);

  $("#display-payment-logos").hidden = hasActiveQr || hasEvent;
  $("#display-hint").textContent = cashLive.active && cashLive.cash > 0 && !hasEvent && !hasActiveQr
    ? displayText("Waiting for cash payment confirmation...")
    : "";
}

function applyDisplayPayload(data = {}, options = {}) {
  const fromCashier = options.fromCashier === true;
  if (!fromCashier && displaySession.locked && !serverPayloadMatchesDisplaySession(data)) {
    return;
  }

  const previousMid = sessionMerchantId();
  const previousAid = sessionAccountId();
  const nextMid = String(data.merchant_id || data.settings?.merchant_id || "").trim();
  const nextAid = String(data.account_id || previousAid || "").trim();

  if (nextMid || nextAid) {
    rememberDisplaySession(nextMid || previousMid, nextAid || previousAid);
  }

  const incomingSettings = { ...(data.settings || {}) };
  if (incomingSettings.merchant_id) {
    const accountChanged = Boolean(previousAid && nextAid && previousAid !== nextAid);
    const merchantChanged = Boolean(previousMid && nextMid && previousMid !== nextMid);

    if (merchantChanged) {
      localStorage.removeItem(deviceStorageKey("conlecta_active_qr"));
      localStorage.removeItem(deviceStorageKey("conlecta_display_event"));
      localStorage.removeItem(deviceStorageKey("conlecta_display_preview"));
      qrState.activeQr = null;
      qrState.displayEvent = null;
      qrState.preview = null;
      lockDisplaySession(nextMid, nextAid, incomingSettings.active_theme || "", { force: true });
      lastAppliedTheme = "";
      lastBrandSignature = "";
    } else if (accountChanged) {
      qrState.settings = {};
      lockDisplaySession(nextMid, nextAid, incomingSettings.active_theme || "", { force: true });
      lastAppliedTheme = "";
      lastBrandSignature = "";
    } else {
      lockDisplaySession(
        nextMid,
        nextAid,
        fromCashier ? (incomingSettings.active_theme || "") : (displaySession.theme || incomingSettings.active_theme || ""),
      );
    }

    if (fromCashier && incomingSettings.active_theme) {
      displaySession.theme = incomingSettings.active_theme;
      lastAppliedTheme = "";
    } else if (displaySession.theme) {
      incomingSettings.active_theme = displaySession.theme;
    }

    qrState.settings = incomingSettings;
    if (fromCashier || accountChanged || merchantChanged) {
      localStorage.setItem(settingsStorageKey(), JSON.stringify(incomingSettings));
    }
  }
  if (Object.prototype.hasOwnProperty.call(data, "display_event")) {
    qrState.displayEvent = data.display_event;
  }
  if (Object.prototype.hasOwnProperty.call(data, "cashier_notice")) {
    qrState.cashierNotice = data.cashier_notice || null;
  }
  if (Object.prototype.hasOwnProperty.call(data, "active_qr")) {
    const next = sanitizeActiveQr(data.active_qr);
    if (next || !hasQrPayload(qrState.activeQr) || fromCashier) {
      qrState.activeQr = next;
    }
  }
  if (data.preview) qrState.preview = data.preview;
  if (data.version) qrState.version = data.version;
  if (data.videoPlayNow) playVideoImmediately(data.videoPlayNow);
  if (terminalDisplayEvent(qrState.displayEvent)) rememberClosedQr(qrState.displayEvent);
  scheduleRenderDisplay();
}

async function refreshFromServer() {
  if (displayClosed) return;
  try {
    const data = await api("/api/display-state");
    if (!serverPayloadMatchesDisplaySession(data)) return;
    const serverSettings = { ...(data.settings || {}) };
    if (displaySession.theme) serverSettings.active_theme = displaySession.theme;
    applyDisplayPayload({
      ...data,
      settings: serverSettings,
      preview: readLocalPreview(),
    });
  } catch {
    reloadDisplayFromLocalStorage();
    scheduleRenderDisplay();
  }
}

function startSplash() {
  const splash = $("#display-splash");
  const fill = $("#display-splash-progress-fill");
  const percent = $("#display-splash-percent");
  const steps = $("#display-splash-steps");
  let value = 0;
  const bootLines = [
    { label: displayText("Checking user session..."), status: "active" },
  ];
  const paintSteps = (lines) => {
    if (!steps) return;
    steps.innerHTML = lines.map((line) => {
      const icon = line.status === "done"
        ? "✓"
        : line.status === "active"
          ? '<span class="spinner">⟳</span>'
          : "·";
      return `<div class="loading-line ${line.status}"><span>${icon}</span><span>${escapeHtml(line.label)}</span></div>`;
    }).join("");
  };
  paintSteps(bootLines);
  const timer = setInterval(() => {
    value = Math.min(100, value + Math.random() * 14 + 6);
    if (fill) fill.style.width = `${Math.round(value)}%`;
    if (percent) percent.textContent = `${Math.round(value)}%`;
    if (value >= 35 && value < 70) {
      paintSteps([
        { label: displayText("Checking user session..."), status: "done" },
        { label: displayText("Please wait..."), status: "active" },
      ]);
    }
    if (value >= 100) {
      clearInterval(timer);
      paintSteps([
        { label: displayText("Checking user session..."), status: "done" },
        { label: displayText("Please wait..."), status: "done" },
      ]);
      splash?.classList.add("hide");
    }
  }, 120);
  const video = $("#display-video");
  video?.play?.().catch(() => null);
}

qrChannel?.addEventListener("message", (event) => {
  if (event.data?.type === "close-display") {
    shutdownDisplay();
    return;
  }
  if (event.data?.type === "display-state") {
    applyDisplayPayload({
      settings: event.data.settings,
      preview: event.data.preview,
      display_event: event.data.displayEvent,
      cashier_notice: event.data.cashierNotice,
      active_qr: event.data.activeQr,
      version: event.data.version,
      merchant_id: event.data.settings?.merchant_id,
      account_id: event.data.account_id,
      videoPlayNow: event.data.videoPlayNow,
    }, { fromCashier: true });
  }
});

window.addEventListener("storage", (event) => {
  if (event.key === "conlecta_close_qr_display_at") {
    shutdownDisplay();
    return;
  }
  if (event.key === DISPLAY_LANGUAGE_STORAGE_KEY) {
    qrState.language = readDisplayLanguagePreference();
    lastPaymentLogoSignature = "";
    lastBrandSignature = "";
    applyDisplayLanguage(document.body);
    scheduleRenderDisplay();
    return;
  }
  if (!storageEventMatchesDisplaySession(event.key)) return;
  reloadDisplayFromLocalStorage();
  scheduleRenderDisplay();
});

function shutdownDisplay() {
  if (displayClosed) return;
  displayClosed = true;
  clearTimeout(displayEventTimer);
  clearTimeout(orphanAckTimer);
  clearTimeout(cashChangeTimer);
  clearInterval(refreshTimer);
  clearInterval(clockTimer);
  localStorage.removeItem(deviceStorageKey("conlecta_active_qr"));
  localStorage.removeItem(deviceStorageKey("conlecta_display_event"));
  localStorage.removeItem(deviceStorageKey("conlecta_display_preview"));
  qrState.activeQr = null;
  qrState.displayEvent = null;
  qrState.cashierNotice = null;
  qrState.preview = null;
  try {
    window.close();
  } catch {
    // Some browsers only allow script-opened tabs to close themselves.
  }
  document.body.innerHTML = "";
}

bootstrapDisplayLanguage();
bootstrapDisplaySession();
setupVideoPlaylistPlayer();
qrState.settings = readLocalSettings();
if (displaySession.theme) {
  applyDisplayTheme(displaySession.theme);
} else {
  bootstrapDisplayTheme();
}
renderPaymentLogos();
if (Object.keys(qrState.settings || {}).length) {
  preloadQrisFrame();
}
updateClock();
clockTimer = setInterval(updateClock, 1000);
startSplash();
refreshFromServer();
refreshTimer = setInterval(refreshFromServer, 5000);
