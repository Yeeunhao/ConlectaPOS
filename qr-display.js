const qrState = {
  activeQr: null,
  settings: {},
  preview: null,
  displayEvent: null,
  cashierNotice: null,
  version: {},
  merchantId: "",
  accountId: "",
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
let displayEventTimer = null;
let orphanAckTimer = null;
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
  if (cashierNoticeMatches(event)) return "Menunggu kasir klik OK pada notifikasi payment success.";
  if (displayEventAgeMs(event) < CASHIER_NOTICE_GRACE_MS) return "Mengecek notifikasi payment success di cashier...";
  return "Cek cashier: notif Payment Success tidak terdeteksi. Jika notif tidak ada, display dibersihkan otomatis.";
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
    const raw = localStorage.getItem(settingsStorageKey());
    if (raw) return JSON.parse(raw);
    const legacy = localStorage.getItem(deviceStorageKey("conlecta_settings"));
    return legacy ? JSON.parse(legacy) : {};
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
  if (event.requires_ack) return false;
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
  if (event.requires_ack) return;
  const delay = Math.max(0, Number(event.expires_ts || 0) * 1000 - Date.now());
  displayEventTimer = setTimeout(() => {
    if (displayEventExpired(qrState.displayEvent)) {
      qrState.displayEvent = null;
      localStorage.removeItem(deviceStorageKey("conlecta_display_event"));
      renderDisplay();
    }
  }, delay + 80);
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
  $("#display-version-label").textContent = version.label || "Conlecta Version";
}

function applyBrand() {
  const settings = qrState.settings || {};
  const shop = settings.shop_name || "Conlecta";
  const address = [settings.shop_address, settings.shop_postcode].filter(Boolean).join(" | ") || "Point of Sale";
  const logo = settings.brand_logo_url || "/assets/ConlectaPosLogo.png";
  document.body.dataset.theme = settings.active_theme || "deep_space";
  $$(".js-display-logo").forEach((img) => {
    if (img.dataset.brandSrc !== logo) {
      img.dataset.brandSrc = logo;
      img.src = logo;
    }
  });
  $("#display-shop").textContent = shop;
  $("#display-bottom-shop").textContent = shop;
  $("#display-bottom-address").textContent = address;
  $("#display-hero-title").textContent = "";
  const marquee = settings.marquee_msgs?.length
    ? settings.marquee_msgs.join("  -  ")
    : "CONLECTA POS - QRIS tersedia - Pembayaran aman dan cepat";
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
  const file = decodeURIComponent(String(src || "").split("/").pop() || "");
  const base = file.replace(/\.[a-z0-9]+$/i, "").replace(/^\d+[_-]/, "");
  const key = base.toLowerCase().replace(/[\s()]+/g, "_").replace(/[-]+/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "");
  const known = {
    gsingapay: "SingaPay",
    mybca: "BCA",
    ovo: "OVO",
    qris: "QRIS",
    egopay: "GoPay",
    images_1: "BRI",
    images: "Mandiri",
    "shopee_pay_logo_png_seeklogo_406839": "ShopeePay",
  };
  return known[key] || base.replace(/[_-]+/g, " ").replace(/\b\w/g, (ch) => ch.toUpperCase()) || "Payment";
}

function linePriceHtml(item) {
  const qty = Number(item.qty || 0);
  const unit = Number(item.unit_price || item.amount || item.price || 0);
  const gross = Number(item.gross || unit * qty);
  const subtotal = Number(item.subtotal || 0);
  const discount = Number(item.line_discount || Math.max(0, gross - subtotal));
  if (discount && gross) {
    return `<span class="price-strike">${formatRp(gross)}</span> ${item.free ? "FREE" : formatRp(subtotal)}`;
  }
  return formatRp(subtotal || unit * qty);
}

function applyVideoPlaylist() {
  const video = $("#display-video");
  const playlist = qrState.settings?.video_playlist_urls || [];
  if (video && playlist.length && video.getAttribute("src") !== playlist[0]) {
    video.src = playlist[0];
    video.load();
    video.play?.().catch(() => null);
  }
}

function renderPaymentLogos() {
  $("#display-payment-logos").innerHTML = paymentLogoPaths().map((src) => `
    <div class="payment-logo-cell">
      <span class="payment-logo-img"><img src="${escapeAttr(src)}" alt=""></span>
      <strong>${escapeHtml(paymentLogoLabel(src))}</strong>
    </div>
  `).join("");
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
  const preview = qrState.preview || {};
  const view = active || event || preview;
  const hasActiveQr = hasQrPayload(active);
  const hasEvent = Boolean(event);
  const items = hasEvent ? [] : (view.items || []);
  const stageQr = $("#display-stage-qr");
  const stageEvent = $("#display-stage-event");
  const video = $("#display-video");
  const paymentArea = $(".display-payment-area");
  const eventPanel = $("#display-event-panel");

  if (hasEvent) {
    stageQr.hidden = true;
    stageEvent.hidden = false;
    video.hidden = true;
    paymentArea.hidden = true;
    eventPanel.hidden = false;
    const isDismissed = event.type === "dismissed";
    const isCashSuccess = !isDismissed && String(event.payment_method || "").toLowerCase() === "cash";
    const kicker = isDismissed ? "QRIS Dismissed" : "Payment Success";
    const eventMessage = isDismissed
      ? "Payment request closed."
      : (isCashSuccess ? `Kembalian ${formatRp(event.change || 0)}` : (event.message || ""));
    const validation = cashierValidationMessage(event);
    $("#display-stage-event-kicker").textContent = kicker;
    $("#display-stage-event-title").textContent = event.title || kicker;
    $("#display-stage-event-message").textContent = validation || eventMessage;
    $("#display-stage-event-total").textContent = formatRp(event.amount);
    $("#display-event-kicker").textContent = kicker;
    $("#display-event-title").textContent = event.title || kicker;
    $("#display-event-message").textContent = validation || eventMessage;
    $("#display-event-total").textContent = formatRp(event.amount);
  } else if (hasActiveQr) {
    $("#display-stage-qr-img").src = qrImageSrc(active, 420);
    $("#display-stage-total").textContent = formatRp(active.amount);
    stageQr.hidden = false;
    stageEvent.hidden = true;
    video.hidden = true;
    paymentArea.hidden = true;
    eventPanel.hidden = true;
  } else {
    $("#display-stage-qr-img").removeAttribute("src");
    stageQr.hidden = true;
    stageEvent.hidden = true;
    video.hidden = false;
    paymentArea.hidden = false;
    eventPanel.hidden = true;
    video.play?.().catch(() => null);
  }

  if (!items.length) {
    $("#display-status").textContent = "";
    $("#display-total").textContent = event ? formatRp(event.amount) : "Rp 0";
    $("#display-items").innerHTML = `<div class="empty-state">Waiting for order</div>`;
    $("#display-payment-logos").hidden = hasEvent;
    $("#display-hint").textContent = cashierValidationMessage(event);
    return;
  }

  $("#display-status").textContent = "";
  $("#display-total").textContent = formatRp(view.amount);
  $("#display-items").innerHTML = items.map((item) => `
    <div class="display-item">
      <span>${escapeHtml(item.item_name || item.name || "")}${item.free ? " [FREE]" : ""}</span>
      <span>x${escapeHtml(item.qty || 0)}</span>
      <span class="line-price">${linePriceHtml(item)}</span>
    </div>
  `).join("") || `<div class="empty-state">No line items</div>`;

  $("#display-payment-logos").hidden = hasActiveQr || hasEvent;
  $("#display-hint").textContent = "";
}

function applyDisplayPayload(data = {}) {
  const previousMid = sessionMerchantId();
  const previousAid = sessionAccountId();
  if (data.merchant_id || data.account_id) {
    rememberDisplaySession(data.merchant_id, data.account_id);
  } else if (data.settings?.merchant_id) {
    rememberDisplaySession(data.settings.merchant_id, data.account_id || previousAid);
  }
  const incomingSettings = data.settings || {};
  if (incomingSettings.merchant_id) {
    const nextAid = String(data.account_id || sessionAccountId() || "").trim();
    if (previousMid && previousMid !== String(incomingSettings.merchant_id).trim()) {
      localStorage.removeItem(deviceStorageKey("conlecta_active_qr"));
      localStorage.removeItem(deviceStorageKey("conlecta_display_event"));
      localStorage.removeItem(deviceStorageKey("conlecta_display_preview"));
      qrState.activeQr = null;
      qrState.displayEvent = null;
      qrState.preview = null;
    }
    if (previousAid && nextAid && previousAid !== nextAid) {
      qrState.settings = {};
    }
    qrState.settings = incomingSettings;
    localStorage.setItem(settingsStorageKey(), JSON.stringify(incomingSettings));
  }
  if (Object.prototype.hasOwnProperty.call(data, "display_event")) {
    qrState.displayEvent = data.display_event;
  }
  if (Object.prototype.hasOwnProperty.call(data, "cashier_notice")) {
    qrState.cashierNotice = data.cashier_notice || null;
  }
  if (Object.prototype.hasOwnProperty.call(data, "active_qr")) {
    qrState.activeQr = sanitizeActiveQr(data.active_qr);
  }
  if (data.preview) qrState.preview = data.preview;
  if (data.version) qrState.version = data.version;
  if (terminalDisplayEvent(qrState.displayEvent)) rememberClosedQr(qrState.displayEvent);
  renderDisplay();
}

async function refreshFromServer() {
  if (displayClosed) return;
  try {
    const data = await api("/api/display-state");
    applyDisplayPayload({
      ...data,
      preview: readLocalPreview(),
    });
  } catch {
    qrState.settings = readLocalSettings();
    qrState.displayEvent = readLocalDisplayEvent();
    qrState.cashierNotice = readLocalCashierNotice();
    if (terminalDisplayEvent(qrState.displayEvent)) rememberClosedQr(qrState.displayEvent);
    qrState.activeQr = readLocalQr();
    qrState.version = readLocalVersion();
    qrState.preview = readLocalPreview();
    renderDisplay();
  }
}

function startSplash() {
  const splash = $("#display-splash");
  setTimeout(() => splash.classList.add("hide"), 1700);
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
    });
  }
});

window.addEventListener("storage", (event) => {
  if (event.key === "conlecta_close_qr_display_at") {
    shutdownDisplay();
    return;
  }
  if (
    event.key === deviceStorageKey("conlecta_active_qr")
    || event.key === deviceStorageKey("conlecta_settings")
    || event.key === settingsStorageKey()
    || event.key === deviceStorageKey("conlecta_display_preview")
    || event.key === deviceStorageKey("conlecta_display_event")
    || event.key === CASHIER_NOTICE_STORAGE_KEY
    || event.key === "conlecta_version"
    || event.key === CLOSED_QR_STORAGE_KEY
  ) {
    qrState.settings = readLocalSettings();
    qrState.displayEvent = readLocalDisplayEvent();
    qrState.cashierNotice = readLocalCashierNotice();
    if (terminalDisplayEvent(qrState.displayEvent)) rememberClosedQr(qrState.displayEvent);
    qrState.activeQr = readLocalQr();
    qrState.version = readLocalVersion();
    qrState.preview = readLocalPreview();
    renderDisplay();
  }
});

function shutdownDisplay() {
  if (displayClosed) return;
  displayClosed = true;
  clearTimeout(displayEventTimer);
  clearTimeout(orphanAckTimer);
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

renderPaymentLogos();
updateClock();
clockTimer = setInterval(updateClock, 1000);
startSplash();
refreshFromServer();
refreshTimer = setInterval(refreshFromServer, 5000);
