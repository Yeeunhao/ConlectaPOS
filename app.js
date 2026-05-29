const state = {
  settings: {},
  auth: null,
  pendingLogin: null,
  products: [],
  vendors: [],
  history: [],
  assets: { videos: [], payment_icons: [] },
  emailTemplates: {},
  vendorInvoiceRows: [],
  vendorInvoiceTotals: {},
  stockTab: "items",
  activeQr: null,
  session: { sales: 0, revenue: 0 },
  cart: {},
  filter: "all",
  selectedStockName: "",
  selectedStockIndex: -1,
  stockImageB64: "",
  currentTxn: "",
  historySearch: "",
  historyQr: "",
  historyCustomer: "",
  historyMethod: "",
  historyCashier: "",
  historyFrom: "",
  historyTo: "",
  analyticsFrom: "",
  analyticsTo: "",
  analyticsMethod: "",
  analyticsMetric: "profit",
  analyticsLimit: 8,
  logLevel: "",
  logAdminPassword: "",
  accountAdminPassword: "",
  accountFormUnlocked: false,
  logs: [],
  currentDetail: null,
  qrCompleting: false,
  sessionTimedOut: false,
  displayEvent: null,
  activePaymentModalTxn: "",
  paymentModalAck: {},
  pendingPaymentClear: false,
  version: {},
  systemAdmin: null,
  selectedSystemMerchantId: "",
  systemMerchantDraft: false,
  systemMerchantLogoDataUrl: "",
  systemMerchantLogoFilename: "",
  systemAdminTab: "merchants",
  systemTxnMerchantId: "",
  systemTransactions: [],
  systemTxnProducts: [],
  selectedSystemTxnId: "",
};

const qrChannel = "BroadcastChannel" in window ? new BroadcastChannel("conlecta-qr") : null;
const CONLECTA_IDENTITY_LOGO = "/assets/ConlectaPosLogo.png";
const OTP_TTL_MS = 60_000;
const SESSION_TIMEOUT_MS = 30 * 60 * 1000;
const SESSION_HEARTBEAT_MS = 60 * 1000;
const PAYMENT_NOTICE_MS = 5000;
const PAYMENT_ACK_STORAGE_KEY = "conlecta_ack_payment_modals";
const CASHIER_NOTICE_STORAGE_KEY = "conlecta_cashier_payment_notice";
const CASHIER_NOTICE_HEARTBEAT_MS = 2500;
const PAYMENT_ACK_LIMIT = 250;
const CLOSED_QR_STORAGE_KEY = "conlecta_closed_qr_ids";
const CLOSED_QR_LIMIT = 300;
const ACTIVE_QR_TTL_MS = 30 * 60 * 1000;
const QRIS_FEE_RATE = 0.007;
const ROUTE_PAGE_MAP = {
  "/cashier": "cashier",
  "/stock": "stock",
  "/analytics": "analytics",
  "/history": "history",
  "/settings": "settings",
  "/log": "log",
  "/system-admin": "system-admin",
};
const PAGE_ROUTE_MAP = Object.fromEntries(Object.entries(ROUTE_PAGE_MAP).map(([route, page]) => [page, route]));
const AUTH_ROUTES = new Set(["/login", "/otp", "/pin", "/pin-register"]);
let toastTimer = null;
let displayEventTimer = null;
let qrPollTimer = null;
let qrDisplayWindow = null;
let otpTimer = null;
let sessionTimer = null;
let heartbeatTimer = null;
let dailySessionTimer = null;
let dismissCooldownTimer = null;
let otpVerifying = false;
let pinVerifying = false;
let pinRegistering = false;
let pinRegisterStep = 1;
let lastActivityTs = Date.now();
let lastActivitySyncTs = 0;
let activityHeartbeatPending = false;
let dismissQrLockedUntil = 0;
let qrDismissInFlight = false;
let loadingDepth = 0;
let displayPublishQueued = false;
let hasBootstrapped = false;
let authEpoch = 0;
let cashierNoticeTimer = null;
let cashierNoticeRecord = null;
const DEVICE_ID_KEY = "conlecta_device_id";
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

function accountScopedStorageKey(name, accountId = "") {
  const aid = String(accountId || state.auth?.id || "").trim();
  if (aid) return `${name}:${getDeviceId()}:${aid}`;
  return deviceStorageKey(name);
}

function clearDisplayLocalCache() {
  localStorage.removeItem(deviceStorageKey("conlecta_active_qr"));
  localStorage.removeItem(deviceStorageKey("conlecta_settings"));
  localStorage.removeItem(deviceStorageKey("conlecta_display_preview"));
  localStorage.removeItem(deviceStorageKey("conlecta_display_event"));
  localStorage.removeItem(deviceStorageKey("conlecta_display_merchant"));
  localStorage.removeItem(deviceStorageKey("conlecta_display_account"));
}
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

function formatRp(value) {
  return "Rp " + Number(value || 0).toLocaleString("id-ID", { maximumFractionDigits: 0 });
}

function formatSignedRp(value) {
  const amount = Number(value || 0);
  if (!amount) return formatRp(0);
  return `${amount < 0 ? "-" : ""}${formatRp(Math.abs(amount))}`;
}

function formatPlainNumber(value) {
  const n = Number(value || 0);
  return n ? n.toLocaleString("en-US", { maximumFractionDigits: 0 }) : "";
}

function parseMoney(value) {
  const digits = String(value || "").replace(/[^\d-]/g, "");
  return Number.parseInt(digits || "0", 10) || 0;
}

function displayPaymentMethod(record) {
  const method = String(record?.payment_method || "").trim().toLowerCase();
  if (method === "cash" || method === "tunai") return "Cash";
  if (method === "qris" || method === "qr" || method === "qr payment") return "QRIS";
  if (parseMoney(record?.cash_received) > 0 || parseMoney(record?.change) > 0) return "Cash";
  if (!String(record?.qr_id || "").trim()) return "Cash";
  return "QRIS";
}

function recordPaymentFee(record) {
  const stored = Number(record?.payment_fee || 0);
  if (stored) return stored;
  return displayPaymentMethod(record) === "Cash" ? 0 : Math.round(Number(record?.amount || 0) * QRIS_FEE_RATE);
}

function productCapital(product) {
  return Number(product?.capital || product?.modal || product?.harga_beli || product?.harga_modal || product?.cost || product?.buy_price || 0) || 0;
}

function paymentModalTxnId(record) {
  return String(record?.txn_id || record?.transaction_id || record?.qr_id || "").trim();
}

function readPaymentAckMap() {
  try {
    const raw = localStorage.getItem(PAYMENT_ACK_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function writePaymentAckMap(map) {
  try {
    const entries = Object.entries(map)
      .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0))
      .slice(0, PAYMENT_ACK_LIMIT);
    localStorage.setItem(PAYMENT_ACK_STORAGE_KEY, JSON.stringify(Object.fromEntries(entries)));
  } catch {
    // Browser storage can be unavailable in private modes; the modal still works for the current open state.
  }
}

function paymentModalAcknowledged(txnId) {
  return Boolean(txnId && (state.paymentModalAck[txnId] || readPaymentAckMap()[txnId]));
}

function markPaymentModalAcknowledged(txnId) {
  if (!txnId) return;
  state.paymentModalAck[txnId] = Date.now();
  const map = readPaymentAckMap();
  map[txnId] = Date.now();
  writePaymentAckMap(map);
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
    // Ignore storage failures; active in-memory state is still cleared.
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

function forgetClosedQr(source) {
  const keys = qrIdentityKeys(source);
  if (!keys.length) return;
  const map = readClosedQrMap();
  keys.forEach((key) => { delete map[key]; });
  writeClosedQrMap(map);
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
    localStorage.removeItem(deviceStorageKey("conlecta_active_qr"));
    return null;
  }
  return active;
}

function terminalDisplayEvent(event) {
  return ["success", "dismissed"].includes(String(event?.type || "").trim().toLowerCase());
}

function formatPct(value) {
  const n = Number(value || 0);
  return `${n.toLocaleString("id-ID", { maximumFractionDigits: 1 })}%`;
}

function displayEventExpired(event) {
  if (!event) return true;
  if (event.requires_ack) return false;
  return Date.now() > Number(event.expires_ts || 0) * 1000;
}

function setDisplayEvent(event) {
  clearTimeout(displayEventTimer);
  displayEventTimer = null;
  state.displayEvent = event && !displayEventExpired(event) ? event : null;
  if (terminalDisplayEvent(state.displayEvent)) rememberClosedQr(state.displayEvent);
  state.activeQr = sanitizeActiveQr(state.activeQr);
  if (state.displayEvent) {
    if (state.displayEvent.requires_ack) return;
    const delay = Math.max(0, Number(state.displayEvent.expires_ts || 0) * 1000 - Date.now());
    displayEventTimer = setTimeout(() => {
      if (displayEventExpired(state.displayEvent)) {
        state.displayEvent = null;
        publishDisplayState();
      }
    }, delay + 80);
  }
}

function cashierNoticePayload(record, visible = true) {
  const data = record || {};
  return {
    visible,
    merchant_id: state.auth?.merchant_id || state.settings?.merchant_id || "",
    device_id: getDeviceId(),
    txn_id: String(data.txn_id || data.transaction_id || state.activePaymentModalTxn || "").trim(),
    qr_id: String(data.qr_id || data.id || "").trim(),
    amount: Number(data.amount || 0),
    payment_method: displayPaymentMethod(data),
    updated_ts: Date.now(),
  };
}

function writeCashierNotice(record) {
  try {
    localStorage.setItem(CASHIER_NOTICE_STORAGE_KEY, JSON.stringify(cashierNoticePayload(record, true)));
  } catch {
    // Local storage is only a cross-tab hint; server heartbeat remains the source.
  }
}

function clearCashierNoticeLocal() {
  try {
    localStorage.removeItem(CASHIER_NOTICE_STORAGE_KEY);
  } catch {
    // Ignore storage failures.
  }
}

function syncCashierNotice(record, visible = true, useBeacon = false) {
  const payload = cashierNoticePayload(record, visible);
  if (useBeacon && navigator.sendBeacon) {
    navigator.sendBeacon(
      "/api/display-event/notice",
      new Blob([JSON.stringify(payload)], { type: "application/json" }),
    );
    return;
  }
  api("/api/display-event/notice", {
    method: "POST",
    body: payload,
    loading: false,
  }).catch(() => null);
}

function startCashierNoticeHeartbeat(record) {
  stopCashierNoticeHeartbeat("", { notify: false });
  cashierNoticeRecord = { ...(record || {}) };
  writeCashierNotice(cashierNoticeRecord);
  syncCashierNotice(cashierNoticeRecord, true);
  cashierNoticeTimer = setInterval(() => {
    writeCashierNotice(cashierNoticeRecord);
    syncCashierNotice(cashierNoticeRecord, true);
  }, CASHIER_NOTICE_HEARTBEAT_MS);
}

function stopCashierNoticeHeartbeat(txnId = "", { notify = true, useBeacon = false } = {}) {
  clearInterval(cashierNoticeTimer);
  cashierNoticeTimer = null;
  const record = cashierNoticeRecord || { txn_id: txnId };
  cashierNoticeRecord = null;
  clearCashierNoticeLocal();
  if (notify) syncCashierNotice(record, false, useBeacon);
}

function imageSrc(item) {
  const img = item?.image_b64 || item?.image || "";
  if (!img) return "";
  if (img.startsWith("data:")) return img;
  return "data:image/png;base64," + img;
}

function productInitial(name) {
  return String(name || "?").trim().slice(0, 1).toUpperCase() || "?";
}

function clampNumber(value, min, max) {
  return Math.max(min, Math.min(max, Number(value || 0)));
}

function cartRaw(name) {
  const raw = state.cart[name];
  if (!raw) return { qty: 0, free: false, disc_pct: 0, disc_fixed: 0 };
  if (typeof raw === "number") return { qty: raw, free: false, disc_pct: 0, disc_fixed: 0 };
  return {
    qty: Number(raw.qty || 0),
    free: Boolean(raw.free),
    disc_pct: clampNumber(raw.disc_pct, 0, 100),
    disc_fixed: Math.max(0, Number(raw.disc_fixed || 0)),
  };
}

function setCartRaw(name, patch) {
  const current = cartRaw(name);
  const next = { ...current, ...patch };
  if (Number(next.qty || 0) <= 0) delete state.cart[name];
  else state.cart[name] = next;
}

function lineDiscount(gross, pct, fixed, free) {
  if (free) return gross;
  const pctDiscount = Math.round(gross * clampNumber(pct, 0, 100) / 100);
  return Math.min(gross, pctDiscount + Math.max(0, Number(fixed || 0)));
}

function isSystemAdmin() {
  return state.auth?.role === "system_admin";
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

async function api(path, options = {}) {
  const loadingMessage = options.loading === false
    ? ""
    : options.loading || ((options.method || "GET").toUpperCase() !== "GET" ? "Memproses..." : "");

  const cleanOptions = { ...options };
  delete cleanOptions.loading;

  const init = {
    headers: {
      "Content-Type": "application/json",
      "X-Conlecta-Device-Id": getDeviceId(),
},
    ...cleanOptions,
  };

  if (init.body && typeof init.body !== "string") {
    init.body = JSON.stringify(init.body);
  }

  if (loadingMessage) showLoading(loadingMessage);

  try {
    const res = await fetch(path, init);
    const type = res.headers.get("content-type") || "";
    const payload = type.includes("application/json") ? await res.json() : await res.text();

    if (!res.ok || payload.ok === false) {
      throw new Error(payload.error || payload.message || `HTTP ${res.status}`);
    }

    return payload;
  } finally {
    if (loadingMessage) hideLoading();
  }
}
function showToast(message, type = "success", duration = 3200) {
  const toast = $("#toast");
  if (!toast) return;
  toast.textContent = message;
  toast.className = "toast show " + type;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), duration);
}

function showLoading(message = "Mohon tunggu...") {
  loadingDepth += 1;
  const overlay = $("#loading-overlay");
  if (!overlay) return;
  $("#loading-message").textContent = message;
  overlay.hidden = false;
  requestAnimationFrame(() => overlay.classList.add("show"));
}

function hideLoading() {
  loadingDepth = Math.max(0, loadingDepth - 1);
  if (loadingDepth > 0) return;
  const overlay = $("#loading-overlay");
  if (!overlay) return;
  overlay.classList.remove("show");
  setTimeout(() => {
    if (loadingDepth === 0) overlay.hidden = true;
  }, 180);
}

async function withLoading(message, task) {
  showLoading(message);
  try {
    return await task();
  } finally {
    hideLoading();
  }
}

function filenameFromDisposition(disposition, fallback) {
  const raw = String(disposition || "");
  const utfMatch = raw.match(/filename\*=UTF-8''([^;]+)/i);
  if (utfMatch) return decodeURIComponent(utfMatch[1].trim().replaceAll('"', ""));
  const match = raw.match(/filename="?([^";]+)"?/i);
  return match ? match[1].trim() : fallback;
}

async function downloadFile(path, {
  method = "GET",
  body = null,
  filename = "download.pdf",
  message = "Menyiapkan PDF...",
} = {}) {
  showLoading(message);
  try {
    const init = {
      method,
      headers: {
        "X-Conlecta-Device-Id": getDeviceId(),
      },
    };
    if (body !== null) {
      init.headers["Content-Type"] = "application/json";
      init.body = typeof body === "string" ? body : JSON.stringify(body);
    }
    const response = await fetch(path, init);
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.error || err.message || `HTTP ${response.status}`);
    }
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filenameFromDisposition(response.headers.get("content-disposition"), filename);
    link.style.display = "none";
    document.body.appendChild(link);
    link.click();
    await new Promise((resolve) => setTimeout(resolve, 250));
    link.remove();
    URL.revokeObjectURL(objectUrl);
  } finally {
    hideLoading();
  }
}

function downloadTextFile(filename, text, type = "text/plain;charset=utf-8") {
  const blob = new Blob([text], { type });
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  setTimeout(() => {
    link.remove();
    URL.revokeObjectURL(objectUrl);
  }, 250);
}

function updateClock() {
  const now = new Date();
  $("#clock").textContent = now.toLocaleString("id-ID", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

const DEFAULT_THEME = "crystal_bloom";

function accountThemeStorageKey() {
  const accountId = String(state.auth?.id || "").trim();
  const deviceId = getDeviceId();
  if (accountId && deviceId) return `conlecta:theme:${deviceId}:${accountId}`;
  return "conlecta:theme";
}

function syncThemeStorageContext() {
  const key = accountThemeStorageKey();
  if (window.ConlectaTheme?.setStorageKey) {
    window.ConlectaTheme.setStorageKey(key);
  }
  return key;
}

function deviceThemeId() {
  const current = window.ConlectaTheme?.current?.();
  if (current && window.ConlectaTheme?.isValid?.(current)) return current;
  const bodyTheme = document.body.dataset.theme;
  if (bodyTheme && window.ConlectaTheme?.isValid?.(bodyTheme)) return bodyTheme;
  return DEFAULT_THEME;
}

function applyDeviceTheme(themeId, { persist = true } = {}) {
  const next = themeId && window.ConlectaTheme?.isValid?.(themeId) ? themeId : deviceThemeId();
  if (window.ConlectaTheme?.apply) {
    window.ConlectaTheme.apply(next, persist ? undefined : { persist: false });
  } else {
    document.body.dataset.theme = next;
  }
  return next;
}

function bootstrapDeviceTheme() {
  if (!window.ConlectaTheme) return;
  syncThemeStorageContext();
  const storageKey = accountThemeStorageKey();
  let stored = null;
  try {
    stored = localStorage.getItem(storageKey);
  } catch {
    // Private browsing can block storage; fall back to the current body theme.
  }
  if (stored && window.ConlectaTheme.isValid(stored)) {
    applyDeviceTheme(stored, { persist: false });
    return;
  }
  const merchantDefault = state.settings?.active_theme;
  if (merchantDefault && window.ConlectaTheme.isValid(merchantDefault)) {
    applyDeviceTheme(merchantDefault);
    return;
  }
  applyDeviceTheme(DEFAULT_THEME);
}

function applyBrand() {
  const s = state.settings || {};
  const name = s.shop_name || "Conlecta";
  const logo = s.brand_logo_url || "/assets/ConlectaPosLogo.png";
  $$(".js-brand-name").forEach((el) => { el.textContent = name; });
  $$(".js-brand-logo").forEach((el) => { el.src = logo; });
  $$(".conlecta-identity-logo").forEach((el) => { el.src = CONLECTA_IDENTITY_LOGO; });
  const preview = $("#brand-preview");
  if (preview) preview.src = logo;
}

function routePath() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  return path === "/" ? "/" : path;
}

function routeForPage(name) {
  return PAGE_ROUTE_MAP[name] || "/cashier";
}

function setRoute(path, replace = false) {
  if (!path || routePath() === path) return;
  const method = replace ? "replaceState" : "pushState";
  window.history[method]({ path }, "", path);
}

function defaultAuthedPage() {
  return isSystemAdmin() ? "system-admin" : "cashier";
}

function applyRouteAfterBootstrap() {
  const path = routePath();
  if (!state.auth) {
    const routeStep = path === "/otp" ? "otp" : (path === "/pin" ? "pin" : (path === "/pin-register" ? "pin-register" : "login"));
    const step = routeStep !== "login" && state.pendingLogin?.account_id ? routeStep : "login";
    showLoginStep(step, { updateRoute: false });
    const targetRoute = step === "otp" ? "/otp" : (step === "pin" ? "/pin" : (step === "pin-register" ? "/pin-register" : "/login"));
    if (path !== targetRoute) setRoute(targetRoute, true);
    return;
  }
  const requestedPage = ROUTE_PAGE_MAP[path];
  const page = requestedPage && !(path === "/system-admin" && !isSystemAdmin())
    ? requestedPage
    : defaultAuthedPage();
  showPage(page, { updateRoute: false });
  const targetRoute = routeForPage(page);
  if (path === "/" || AUTH_ROUTES.has(path) || path !== targetRoute) {
    setRoute(targetRoute, true);
  }
}

function renderAuth() {
  const locked = !state.auth;
  const systemMode = isSystemAdmin();
  $("#auth-screen").classList.toggle("hidden", !locked);
  $("#app").classList.toggle("is-locked", locked);
  $("#app").classList.toggle("system-admin-mode", systemMode);
  $(".brand").dataset.page = systemMode ? "system-admin" : "cashier";
  $("#user-pill").textContent = state.auth
    ? `${systemMode ? "Admin" : "Kasir"}: ${state.auth.name || state.auth.username || "Cashier"}`
    : "Kasir: -";
  $("#cashier-name").textContent = `Kasir: ${state.auth?.name || "Cashier"}`;
  if (locked) {
    stopSessionTimer();
    stopHeartbeat();
  } else {
    scheduleSessionTimer();
    startHeartbeat();
  }
  if (systemMode) {
    const activePage = $(".page.active")?.id || "";
    if (activePage !== "page-system-admin") showPage("system-admin", { sync: false, updateRoute: false });
  } else if (!locked && $(".page.active")?.id === "page-system-admin") {
    showPage("cashier", { sync: false, updateRoute: false });
  }
}

function showLoginStep(step, { updateRoute = true } = {}) {
  $("#login-form").classList.toggle("active", step === "login");
  $("#otp-form").classList.toggle("active", step === "otp");
  $("#pin-form")?.classList.toggle("active", step === "pin");
  $("#pin-register-form")?.classList.toggle("active", step === "pin-register");
  if (step === "pin-register") setPinRegisterStep(1);
  if (step === "login") stopOtpTimer();
  if (!state.auth && updateRoute) {
    const route = step === "otp" ? "/otp" : (step === "pin" ? "/pin" : (step === "pin-register" ? "/pin-register" : "/login"));
    setRoute(route);
  }
}

function resetAuthForms({ clearCredentials = false, updateRoute = true } = {}) {
  state.pendingLogin = null;
  stopOtpTimer();
  clearOtpCode(false);
  clearPinCode(false);
  clearPinRegisterCode(false);
  $("#login-status").textContent = "";
  $("#otp-status").textContent = "";
  $("#pin-status").textContent = "";
  $("#pin-register-status").textContent = "";
  $("#otp-target").textContent = "OTP sent to your email.";
  $("#pin-target").textContent = "Masukkan 6 digit PIN.";
  $("#pin-register-target").textContent = "Buat PIN 6 angka untuk login berikutnya.";
  $("#otp-countdown").textContent = "OTP berlaku 60 detik.";
  const resend = $("#otp-resend");
  if (resend) {
    resend.disabled = true;
    resend.textContent = "Resend OTP";
  }
  if (clearCredentials) {
    $("#login-id").value = "";
    $("#login-password").value = "";
    $("#login-password").type = "password";
    const mask = $("[data-action='toggle-login-password']");
    if (mask) {
      mask.setAttribute("aria-pressed", "false");
      mask.setAttribute("aria-label", "Show password");
    }
  }
  showLoginStep("login", { updateRoute });
}

function otpInputs() {
  return $$(".otp-digit");
}

function setOtpCode(value = "") {
  const clean = String(value || "").replace(/\D/g, "").slice(0, 6);
  const hidden = $("#otp-code");
  if (hidden) hidden.value = clean;
  otpInputs().forEach((input, index) => {
    input.value = clean[index] || "";
  });
  return clean;
}

function getOtpCode() {
  const inputs = otpInputs();
  const code = inputs.length
    ? inputs.map((input) => input.value).join("")
    : ($("#otp-code")?.value || "");
  return String(code || "").replace(/\D/g, "").slice(0, 6);
}

function syncOtpCodeFromInputs() {
  const code = getOtpCode();
  const hidden = $("#otp-code");
  if (hidden) hidden.value = code;
  return code;
}

function focusOtpInput(index = 0) {
  const inputs = otpInputs();
  if (inputs.length) {
    inputs[Math.max(0, Math.min(index, inputs.length - 1))].focus();
  } else {
    $("#otp-code")?.focus();
  }
}

function markOtpError() {
  const row = $(".otp-row");
  if (!row) return;
  row.classList.remove("is-error");
  void row.offsetWidth;
  row.classList.add("is-error");
  setTimeout(() => row.classList.remove("is-error"), 300);
}

function clearOtpCode(focus = false) {
  setOtpCode("");
  $(".otp-row")?.classList.remove("is-error");
  if (focus) focusOtpInput();
}

function maybeAutoSubmitOtp() {
  if (getOtpCode().length === 6 && state.pendingLogin?.account_id) {
    otpSubmit().catch((err) => {
      $("#otp-status").textContent = err.message;
    });
  }
}

function bindOtpInputs() {
  const inputs = otpInputs();
  inputs.forEach((input, index) => {
    input.addEventListener("input", () => {
      const digits = input.value.replace(/\D/g, "");
      input.value = "";
      digits.split("").forEach((digit, offset) => {
        if (inputs[index + offset]) inputs[index + offset].value = digit;
      });
      const code = syncOtpCodeFromInputs();
      if (code.length === inputs.length) {
        maybeAutoSubmitOtp();
      } else if (digits && index < inputs.length - 1) {
        focusOtpInput(Math.min(index + digits.length, inputs.length - 1));
      }
    });

    input.addEventListener("keydown", (event) => {
      if (event.key === "Backspace" && !input.value && index > 0) {
        event.preventDefault();
        inputs[index - 1].value = "";
        syncOtpCodeFromInputs();
        focusOtpInput(index - 1);
      } else if (event.key === "ArrowLeft" && index > 0) {
        event.preventDefault();
        focusOtpInput(index - 1);
      } else if (event.key === "ArrowRight" && index < inputs.length - 1) {
        event.preventDefault();
        focusOtpInput(index + 1);
      }
    });

    input.addEventListener("paste", (event) => {
      event.preventDefault();
      const pasted = (event.clipboardData || window.clipboardData)
        .getData("text")
        .replace(/\D/g, "")
        .slice(0, inputs.length);
      setOtpCode(pasted);
      if (pasted.length === inputs.length) {
        focusOtpInput(inputs.length - 1);
        maybeAutoSubmitOtp();
      } else {
        focusOtpInput(pasted.length);
      }
    });
  });
}

function pinInputs() {
  return $$(".pin-digit");
}

function pinNewInputs() {
  return $$(".pin-new-digit");
}

function pinConfirmInputs() {
  return $$(".pin-confirm-digit");
}

function setDigitCode(inputs, hiddenSelector, value = "") {
  const clean = String(value || "").replace(/\D/g, "").slice(0, 6);
  const hidden = $(hiddenSelector);
  if (hidden) hidden.value = clean;
  inputs.forEach((input, index) => {
    input.value = clean[index] || "";
  });
  return clean;
}

function getDigitCode(inputs, hiddenSelector) {
  const code = inputs.length
    ? inputs.map((input) => input.value).join("")
    : ($(hiddenSelector)?.value || "");
  return String(code || "").replace(/\D/g, "").slice(0, 6);
}

function focusDigitInput(inputs, index = 0) {
  if (!inputs.length) return;
  inputs[Math.max(0, Math.min(index, inputs.length - 1))].focus();
}

function markDigitError(inputs) {
  const row = inputs[0]?.closest?.(".otp-row");
  if (!row) return;
  row.classList.remove("is-error");
  void row.offsetWidth;
  row.classList.add("is-error");
  setTimeout(() => row.classList.remove("is-error"), 300);
}

function setPinCode(value = "") {
  return setDigitCode(pinInputs(), "#pin-code", value);
}

function getPinCode() {
  return getDigitCode(pinInputs(), "#pin-code");
}

function clearPinCode(focus = false) {
  setPinCode("");
  $(".pin-row")?.classList.remove("is-error");
  if (focus) focusDigitInput(pinInputs());
}

function setPinRegisterCode(value = "", confirm = "") {
  setDigitCode(pinNewInputs(), "#pin-new-code", value);
  setDigitCode(pinConfirmInputs(), "#pin-confirm-code", confirm);
}

function getPinRegisterCode() {
  return getDigitCode(pinNewInputs(), "#pin-new-code");
}

function getPinConfirmCode() {
  return getDigitCode(pinConfirmInputs(), "#pin-confirm-code");
}

function clearPinRegisterCode(focus = false) {
  setPinRegisterCode("", "");
  setPinRegisterStep(1);
  $$(".pin-row").forEach((row) => row.classList.remove("is-error"));
  if (focus) focusDigitInput(pinNewInputs());
}

function setPinRegisterStep(step) {
  pinRegisterStep = step === 2 ? 2 : 1;
  $("#pin-register-step1")?.classList.toggle("hidden", pinRegisterStep !== 1);
  $("#pin-register-step2")?.classList.toggle("hidden", pinRegisterStep !== 2);
  const indicator = $("#pin-step-indicator");
  if (indicator) indicator.textContent = `Langkah ${pinRegisterStep} dari 2`;
  $("#pin-register-status").textContent = "";
  if (pinRegisterStep === 1) {
    focusDigitInput(pinNewInputs());
  } else {
    focusDigitInput(pinConfirmInputs());
  }
}

function pinRegisterContinue() {
  const pin = getPinRegisterCode();
  if (pin.length !== 6) {
    markDigitError(pinNewInputs());
    $("#pin-register-status").textContent = "Masukkan PIN 6 angka.";
    focusDigitInput(pinNewInputs());
    return;
  }
  setPinRegisterStep(2);
}

function pinRegisterBack() {
  setDigitCode(pinConfirmInputs(), "#pin-confirm-code", "");
  setPinRegisterStep(1);
}

function maybeAutoAdvancePinRegister() {
  if (pinRegisterStep !== 1) return;
  if (getPinRegisterCode().length === 6) {
    pinRegisterContinue();
  }
}

function maybeAutoSubmitPin() {
  if (getPinCode().length === 6 && state.pendingLogin?.account_id) {
    pinSubmit().catch((err) => {
      $("#pin-status").textContent = err.message;
    });
  }
}

function maybeAutoRegisterPin() {
  if (pinRegisterStep !== 2) return;
  const pin = getPinRegisterCode();
  const confirm = getPinConfirmCode();
  if (pin.length !== 6 || confirm.length !== 6 || !state.pendingLogin?.account_id) return;
  if (pin !== confirm) {
    markDigitError(pinConfirmInputs());
    $("#pin-register-status").textContent = "Konfirmasi PIN tidak sama.";
    setDigitCode(pinConfirmInputs(), "#pin-confirm-code", "");
    focusDigitInput(pinConfirmInputs());
    return;
  }
  registerPinSubmit().catch((err) => {
    $("#pin-register-status").textContent = err.message;
  });
}

function bindDigitInputs(inputs, hiddenSelector, autoSubmit) {
  inputs.forEach((input, index) => {
    input.addEventListener("input", () => {
      const digits = input.value.replace(/\D/g, "");
      input.value = "";
      digits.split("").forEach((digit, offset) => {
        if (inputs[index + offset]) inputs[index + offset].value = digit;
      });
      const code = getDigitCode(inputs, hiddenSelector);
      const hidden = $(hiddenSelector);
      if (hidden) hidden.value = code;
      if (code.length === inputs.length) {
        autoSubmit?.();
      } else if (digits && index < inputs.length - 1) {
        focusDigitInput(inputs, Math.min(index + digits.length, inputs.length - 1));
      }
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Backspace" && !input.value && index > 0) {
        event.preventDefault();
        inputs[index - 1].value = "";
        const code = getDigitCode(inputs, hiddenSelector);
        const hidden = $(hiddenSelector);
        if (hidden) hidden.value = code;
        focusDigitInput(inputs, index - 1);
      } else if (event.key === "ArrowLeft" && index > 0) {
        event.preventDefault();
        focusDigitInput(inputs, index - 1);
      } else if (event.key === "ArrowRight" && index < inputs.length - 1) {
        event.preventDefault();
        focusDigitInput(inputs, index + 1);
      }
    });
    input.addEventListener("paste", (event) => {
      event.preventDefault();
      const pasted = (event.clipboardData || window.clipboardData)
        .getData("text")
        .replace(/\D/g, "")
        .slice(0, inputs.length);
      setDigitCode(inputs, hiddenSelector, pasted);
      if (pasted.length === inputs.length) {
        focusDigitInput(inputs, inputs.length - 1);
        autoSubmit?.();
      } else {
        focusDigitInput(inputs, pasted.length);
      }
    });
  });
}

function bindPinInputs() {
  bindDigitInputs(pinInputs(), "#pin-code", maybeAutoSubmitPin);
  bindDigitInputs(pinNewInputs(), "#pin-new-code", maybeAutoAdvancePinRegister);
  bindDigitInputs(pinConfirmInputs(), "#pin-confirm-code", maybeAutoRegisterPin);
}

function applyPendingLogin(pending) {
  state.pendingLogin = {
    ...pending,
    expiresAtMs: Date.now() + Math.max(0, Number(pending?.expires_in ?? 600)) * 1000,
  };
}

function applyPendingOtp(pending) {
  const now = Date.now();
  const expiresIn = Number(pending?.expires_in ?? 60);
  const cooldown = Number(pending?.resend_cooldown ?? 60);
  state.pendingLogin = {
    ...pending,
    expiresAtMs: now + Math.max(0, expiresIn) * 1000,
    canResendAtMs: now + Math.max(0, cooldown) * 1000,
    resendRemaining: Number(pending?.resend_remaining ?? 0),
  };
  renderOtpCountdown();
  stopOtpTimer();
  otpTimer = setInterval(renderOtpCountdown, 1000);
}

function stopOtpTimer() {
  if (otpTimer) clearInterval(otpTimer);
  otpTimer = null;
}

function renderOtpCountdown() {
  const pending = state.pendingLogin || {};
  const now = Date.now();
  const expiresLeft = Math.max(0, Math.ceil(((pending.expiresAtMs || now) - now) / 1000));
  const resendLeft = Math.max(0, Math.ceil(((pending.canResendAtMs || now) - now) / 1000));
  const resendRemaining = Number(pending.resendRemaining || 0);
  const resend = $("#otp-resend");
  if (expiresLeft > 0) {
    $("#otp-countdown").textContent = `OTP berlaku ${expiresLeft} detik.`;
  } else if (resendRemaining > 0) {
    $("#otp-countdown").textContent = resendLeft > 0
      ? `OTP expired. Resend tersedia dalam ${resendLeft} detik.`
      : "OTP expired. Resend OTP tersedia.";
  } else {
    $("#otp-countdown").textContent = "OTP expired. Silakan login ulang.";
  }
  if (resend) {
    resend.disabled = resendRemaining <= 0 || resendLeft > 0;
    resend.textContent = resendRemaining <= 0
      ? "Resend sudah dipakai"
      : (resendLeft > 0 ? `Resend OTP (${resendLeft}s)` : "Resend OTP");
  }
}

function authActivityMs(auth = state.auth) {
  const value = auth?.last_activity_ts || auth?.login_ts || auth?.last_seen_ts;
  if (!value) return 0;
  if (typeof value === "number") return value > 100000000000 ? value : value * 1000;
  const text = String(value).trim();
  const numeric = Number(text);
  if (Number.isFinite(numeric) && numeric > 0) {
    return numeric > 100000000000 ? numeric : numeric * 1000;
  }
  const parsed = Date.parse(text);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function scheduleSessionTimer() {
  if (!state.auth) return;
  clearTimeout(sessionTimer);
  const remaining = SESSION_TIMEOUT_MS - (Date.now() - lastActivityTs);
  sessionTimer = setTimeout(handleSessionTimeout, Math.max(0, remaining));
}

function resetSessionTimer(ts = Date.now()) {
  if (!state.auth) return;
  lastActivityTs = ts;
  scheduleSessionTimer();
}

function stopSessionTimer() {
  clearTimeout(sessionTimer);
  sessionTimer = null;
}

function stopHeartbeat() {
  if (heartbeatTimer) clearInterval(heartbeatTimer);
  heartbeatTimer = null;
}

function heartbeatPayload() {
  return {
    active_qr: Boolean(state.activeQr),
    cart_count: cartEntries().length,
    page: $(".page.active")?.id || "",
    last_activity_ts: Math.floor(lastActivityTs / 1000),
    device_id: getDeviceId(),
  };
}

function startHeartbeat() {
  if (!state.auth || heartbeatTimer) return;
  heartbeatTimer = setInterval(() => {
    sendSessionHeartbeat().catch(() => null);
  }, SESSION_HEARTBEAT_MS);
}

function applyLoggedOutState(message = "") {
  authEpoch += 1;
  stopCashierNoticeHeartbeat(state.activePaymentModalTxn, { notify: true });
  requestQrDisplayClose();
  state.auth = null;
  state.pendingLogin = null;
  state.systemAdmin = null;
  state.selectedSystemMerchantId = "";
  state.systemMerchantDraft = false;
  state.systemMerchantLogoDataUrl = "";
  state.systemMerchantLogoFilename = "";
  state.activeQr = null;
  state.displayEvent = null;
  state.pendingPaymentClear = false;
  state.cart = {};
  state.currentTxn = "";
  stopQrPolling();
  stopOtpTimer();
  stopSessionTimer();
  stopHeartbeat();
  closeModal(true);
  resetAuthForms({ clearCredentials: true });
  setRoute("/login", true);
  renderAuth();
  renderCart();
  updateTotals();
  publishDisplayState();
  if (message) showToast(message, "error");
}

async function sendSessionHeartbeat(useBeacon = false) {
  if (!state.auth) return;
  const body = JSON.stringify(heartbeatPayload());
  if (useBeacon && navigator.sendBeacon) {
    navigator.sendBeacon("/api/auth/heartbeat", new Blob([body], { type: "application/json" }));
    return;
  }
  const result = await api("/api/auth/heartbeat", {
    method: "POST",
    body,
    loading: false,
  });
  if (Object.prototype.hasOwnProperty.call(result, "auth") && !result.auth) {
    applyLoggedOutState("Session expired. Silakan login ulang.");
  } else if (result.auth) {
    state.auth = result.auth;
    const activityMs = authActivityMs(result.auth);
    if (activityMs) {
      lastActivityTs = activityMs;
      scheduleSessionTimer();
    }
  }
}

async function handleSessionTimeout() {
  if (!state.auth || Date.now() - lastActivityTs < SESSION_TIMEOUT_MS - 1000) {
    scheduleSessionTimer();
    return;
  }
  state.sessionTimedOut = true;
  applyLoggedOutState("Session timeout. Silakan login ulang.");
  try {
    await api("/api/auth/logout", { method: "POST", body: {}, loading: false });
  } catch {
    // UI already locks locally if network/logout update fails.
  }
}

function queueActivityHeartbeat() {
  if (!state.auth || activityHeartbeatPending) return;
  if (Date.now() - lastActivitySyncTs < 15000) return;
  activityHeartbeatPending = true;
  lastActivitySyncTs = Date.now();
  sendSessionHeartbeat()
    .catch(() => null)
    .finally(() => {
      activityHeartbeatPending = false;
    });
}

function noteActivity() {
  if (!state.auth) return;
  const now = Date.now();
  if (now - lastActivityTs >= SESSION_TIMEOUT_MS) {
    handleSessionTimeout();
    return;
  }
  if (now - lastActivityTs < 1000) return;
  resetSessionTimer(now);
  queueActivityHeartbeat();
}

async function loginSubmit(event) {
  event.preventDefault();
  $("#login-status").textContent = "Memverifikasi password...";
  $("#otp-status").textContent = "";
  $("#pin-status").textContent = "";
  $("#pin-register-status").textContent = "";
  const result = await api("/api/auth/login", {
    method: "POST",
    body: {
      login: $("#login-id").value.trim(),
      password: $("#login-password").value,
    },
  });
  const pending = result.pending || {};
  if (pending.mode === "otp") {
    applyPendingOtp(pending);
    $("#otp-target").textContent = `OTP dikirim ke ${pending.email || "email akun"}.`;
    $("#login-status").textContent = "";
    clearOtpCode(false);
    showLoginStep("otp");
    focusOtpInput();
    return;
  }
  applyPendingLogin(pending);
  $("#login-status").textContent = "";
  if (pending.mode === "register_pin") {
    $("#pin-register-target").textContent = `Register PIN untuk ${pending.account_name || pending.username || "akun ini"}.`;
    clearPinRegisterCode(false);
    showLoginStep("pin-register");
    focusDigitInput(pinNewInputs());
  } else {
    $("#pin-target").textContent = `Masukkan PIN untuk ${pending.account_name || pending.username || "akun ini"}.`;
    clearPinCode(false);
    showLoginStep("pin");
    focusDigitInput(pinInputs());
  }
}

async function finishAuthLogin(result) {
  authEpoch += 1;
  clearDisplayLocalCache();
  state.auth = result.auth;
  lastActivityTs = authActivityMs(result.auth) || Date.now();
  lastActivitySyncTs = 0;
  state.pendingLogin = null;
  state.systemAdmin = result.system_admin || null;
  stopOtpTimer();
  if (result.settings) state.settings = result.settings;
  resetAuthForms({ clearCredentials: true, updateRoute: false });
  renderAuth();
  applyBrand();
  await withLoading(isSystemAdmin() ? "Memuat dashboard admin..." : "Memuat data kasir...", reloadBootstrap);
  applyRouteAfterBootstrap();
  showToast("Login berhasil");
}

async function otpSubmit(event) {
  event?.preventDefault();
  if (otpVerifying) return;
  if (!state.pendingLogin?.account_id) {
    showLoginStep("login");
    return;
  }
  const otp = getOtpCode();
  if (otp.length !== 6) {
    $("#otp-status").textContent = "Masukkan 6 digit OTP.";
    focusOtpInput();
    return;
  }
  $("#otp-status").textContent = "Memverifikasi OTP...";
  otpVerifying = true;
  let result;
  try {
    result = await api("/api/auth/verify", {
      method: "POST",
      body: {
        account_id: state.pendingLogin.account_id,
        otp,
      },
    });
  } catch (err) {
    markOtpError();
    clearOtpCode(true);
    $("#otp-status").textContent = err.message || "OTP salah. Kode dibersihkan.";
    showToast("OTP salah. Silakan coba lagi.", "error");
    return;
  } finally {
    otpVerifying = false;
  }
  if (result.pending) {
    applyPendingLogin(result.pending);
    clearPinRegisterCode(false);
    $("#pin-register-target").textContent = "Buat PIN baru setelah OTP berhasil.";
    showLoginStep("pin-register");
    focusDigitInput(pinNewInputs());
    return;
  }
  await finishAuthLogin(result);
}

async function pinSubmit(event) {
  event?.preventDefault();
  if (pinVerifying) return;
  if (!state.pendingLogin?.account_id) {
    showLoginStep("login");
    return;
  }
  const pin = getPinCode();
  if (pin.length !== 6) {
    $("#pin-status").textContent = "PIN wajib 6 angka.";
    focusDigitInput(pinInputs());
    return;
  }
  pinVerifying = true;
  $("#pin-status").textContent = "Memverifikasi PIN...";
  try {
    const result = await api("/api/auth/verify-pin", {
      method: "POST",
      body: { account_id: state.pendingLogin.account_id, pin },
    });
    await finishAuthLogin(result);
  } catch (err) {
    markDigitError(pinInputs());
    clearPinCode(true);
    $("#pin-status").textContent = err.message || "PIN salah.";
    showToast("PIN salah. Silakan coba lagi.", "error");
  } finally {
    pinVerifying = false;
  }
}

async function registerPinSubmit(event) {
  event?.preventDefault();
  if (pinRegistering) return;
  if (!state.pendingLogin?.account_id) {
    showLoginStep("login");
    return;
  }
  if (pinRegisterStep === 1) {
    pinRegisterContinue();
    return;
  }
  const pin = getPinRegisterCode();
  const confirm = getPinConfirmCode();
  if (pin.length !== 6) {
    setPinRegisterStep(1);
    $("#pin-register-status").textContent = "Masukkan PIN 6 angka.";
    return;
  }
  if (confirm.length !== 6) {
    $("#pin-register-status").textContent = "Konfirmasi PIN 6 angka.";
    focusDigitInput(pinConfirmInputs());
    return;
  }
  if (pin !== confirm) {
    markDigitError(pinConfirmInputs());
    $("#pin-register-status").textContent = "Konfirmasi PIN tidak sama.";
    return;
  }
  pinRegistering = true;
  $("#pin-register-status").textContent = "Menyimpan PIN...";
  try {
    const result = await api("/api/auth/register-pin", {
      method: "POST",
      body: { account_id: state.pendingLogin.account_id, pin, confirm_pin: confirm },
    });
    await finishAuthLogin(result);
  } catch (err) {
    markDigitError(pinNewInputs());
    markDigitError(pinConfirmInputs());
    clearPinRegisterCode(true);
    $("#pin-register-status").textContent = err.message || "Register PIN gagal.";
    throw err;
  } finally {
    pinRegistering = false;
  }
}

async function forgotPin() {
  if (!state.pendingLogin?.account_id) {
    showLoginStep("login");
    return;
  }
  $("#pin-status").textContent = "Mengirim OTP reset PIN...";
  const result = await api("/api/auth/forgot-pin", {
    method: "POST",
    body: { account_id: state.pendingLogin.account_id },
  });
  applyPendingOtp(result.pending);
  $("#otp-target").textContent = `OTP reset PIN dikirim ke ${result.pending?.email || "email akun"}.`;
  $("#pin-status").textContent = "";
  clearOtpCode(false);
  showLoginStep("otp");
  focusOtpInput();
}

async function resendOtp() {
  if (!state.pendingLogin?.account_id) {
    showLoginStep("login");
    return;
  }
  $("#otp-status").textContent = "Mengirim ulang OTP...";
  try {
    const result = await api("/api/auth/resend-otp", {
      method: "POST",
      body: { account_id: state.pendingLogin.account_id },
    });
    applyPendingOtp(result.pending);
    clearOtpCode(false);
    $("#otp-status").textContent = result.message || "OTP baru dikirim.";
    focusOtpInput();
  } catch (err) {
    renderOtpCountdown();
    $("#otp-status").textContent = err.message || "Resend OTP gagal.";
    throw err;
  }
}

function toggleLoginPassword() {
  const input = $("#login-password");
  const button = $("[data-action='toggle-login-password']");
  if (!input || !button) return;
  const show = input.type === "password";
  input.type = show ? "text" : "password";
  button.setAttribute("aria-pressed", show ? "true" : "false");
  button.setAttribute("aria-label", show ? "Hide password" : "Show password");
  input.focus();
}

function showLogoutModal() {
  $("#payment-modal").hidden = true;
  $("#detail-modal").hidden = true;
  $("#qr-modal").hidden = true;
  $("#dismiss-modal").hidden = true;
  $("#logout-modal").hidden = false;
  $("#modal-backdrop").hidden = false;
}

async function logout() {
  authEpoch += 1;
  requestQrDisplayClose();
  clearDisplayLocalCache();
  await withLoading("Menutup sesi...", async () => {
    await api("/api/auth/logout", { method: "POST", body: {} });
  });
  state.auth = null;
  state.pendingLogin = null;
  state.systemAdmin = null;
  state.selectedSystemMerchantId = "";
  state.systemMerchantDraft = false;
  state.systemMerchantLogoDataUrl = "";
  state.systemMerchantLogoFilename = "";
  state.activeQr = null;
  state.displayEvent = null;
  state.pendingPaymentClear = false;
  state.logAdminPassword = "";
  state.cart = {};
  state.currentTxn = "";
  stopQrPolling();
  stopOtpTimer();
  stopSessionTimer();
  stopHeartbeat();
  closeModal();
  resetAuthForms({ clearCredentials: true });
  if ($("#log-admin-password")) $("#log-admin-password").value = "";
  setRoute("/login", true);
  renderAuth();
  renderCart();
  updateTotals();
  publishDisplayState();
}

function showPage(name, { sync = true, updateRoute = true } = {}) {
  if (!name) return;
  if (isSystemAdmin() && name !== "system-admin") name = "system-admin";
  $$(".page").forEach((page) => page.classList.toggle("active", page.id === `page-${name}`));
  $$(".nav-btn[data-page]").forEach((btn) => btn.classList.toggle("active", btn.dataset.page === name));
  if (state.auth && updateRoute) setRoute(routeForPage(name));
  if (name === "system-admin") renderSystemAdmin();
  if (name === "stock") renderStock();
  if (name === "analytics") renderAnalytics();
  if (name === "history") renderHistory();
  if (name === "settings") renderSettings();
  if (name === "log") renderLogs();
  if (sync && state.auth) {
    syncMenuData(name).catch((err) => showToast(err.message, "error"));
  }
}

function cartEntries() {
  return Object.entries(state.cart)
    .map(([name]) => {
      const product = state.products.find((item) => item.name === name);
      const raw = cartRaw(name);
      const qty = raw.qty;
      if (!product || qty <= 0) return null;
      const unit = Number(product.price || 0);
      const gross = unit * qty;
      const discount = lineDiscount(gross, raw.disc_pct, raw.disc_fixed, raw.free);
      const subtotal = Math.max(0, gross - discount);
      const isFree = raw.free || (gross > 0 && subtotal <= 0 && discount >= gross);
      return {
        name,
        item_name: name,
        qty,
        price: isFree ? 0 : unit,
        amount: isFree ? 0 : unit,
        unit_price: unit,
        capital: productCapital(product),
        cost: productCapital(product),
        stock: Number(product.stock || 0),
        image_b64: product.image_b64 || "",
        gross,
        line_discount: discount,
        disc_pct: raw.disc_pct,
        disc_fixed: raw.disc_fixed,
        subtotal,
        profit: subtotal - (productCapital(product) * qty),
        free: isFree,
      };
    })
    .filter(Boolean);
}

function cartTotal() {
  return cartEntries().reduce((sum, item) => sum + item.subtotal, 0);
}

function cartQtyTotal() {
  return cartEntries().reduce((sum, item) => sum + item.qty, 0);
}

function reconcileCartWithStock() {
  if (state.activeQr) return;
  const byName = new Map((state.products || []).map((item) => [item.name, Number(item.stock || 0)]));
  Object.keys(state.cart).forEach((name) => {
    if (!byName.has(name)) {
      delete state.cart[name];
      return;
    }
    const raw = cartRaw(name);
    const qty = Math.max(0, Math.min(raw.qty, byName.get(name)));
    if (qty <= 0) delete state.cart[name];
    else state.cart[name] = { ...raw, qty };
  });
}

function setCartQty(name, qty) {
  if (state.activeQr) {
    showToast("Dismiss QR dulu sebelum ubah cart", "error");
    return;
  }
  const product = state.products.find((item) => item.name === name);
  if (!product) return;
  const next = Math.max(0, Math.min(Number(product.stock || 0), Number(qty || 0)));
  setCartRaw(name, { qty: next });
  renderCatalog();
  renderCart();
  updateTotals();
}

function changeCartQty(name, delta) {
  const product = state.products.find((item) => item.name === name);
  if (!product) return;
  const cur = cartRaw(name).qty;
  if (delta > 0 && cur >= Number(product.stock || 0)) {
    showToast("Stock tidak cukup", "error");
    return;
  }
  setCartQty(name, cur + delta);
}

function toggleFreeItem(name, checked) {
  if (state.activeQr) {
    showToast("Dismiss QR dulu sebelum ubah cart", "error");
    return;
  }
  if (!cartRaw(name).qty) setCartQty(name, 1);
  setCartRaw(name, { free: checked });
  renderCatalog();
  renderCart();
  updateTotals();
}

function setLineDiscount(name, field, value) {
  if (state.activeQr) {
    showToast("Dismiss QR dulu sebelum ubah diskon", "error");
    return;
  }
  const activeInput = document.activeElement;
  const restoreFocus = activeInput?.matches?.("[data-discount-field]")
    ? {
      name: activeInput.dataset.name,
      field: activeInput.dataset.discountField,
      pos: activeInput.selectionStart,
    }
    : null;
  const product = state.products.find((item) => item.name === name);
  const raw = cartRaw(name);
  const qty = raw.qty || 1;
  const gross = Number(product?.price || 0) * qty;
  const next = {};
  if (field === "disc_pct") {
    const pct = clampNumber(value, 0, 100);
    next.disc_pct = pct;
    if (pct > 0) next.disc_fixed = 0;
    if (pct >= 100) next.free = true;
    else next.free = false;
  } else {
    const fixed = Math.min(Math.max(0, Number(value || 0)), gross || Number.MAX_SAFE_INTEGER);
    next.disc_fixed = fixed;
    if (fixed > 0) next.disc_pct = 0;
    if (gross && fixed >= gross) next.free = true;
    else next.free = false;
  }
  setCartRaw(name, next);
  renderCatalog();
  renderCart();
  if (restoreFocus) {
    requestAnimationFrame(() => {
      const input = $$("[data-discount-field]").find((el) => el.dataset.name === restoreFocus.name && el.dataset.discountField === restoreFocus.field);
      if (!input || input.disabled) return;
      input.focus();
      const pos = Math.min(Number(restoreFocus.pos || 0), input.value.length);
      input.setSelectionRange?.(pos, pos);
    });
  }
  updateTotals();
}

function cartPricingHtml(item) {
  const gross = Number(item.gross || 0);
  if (item.line_discount && gross) {
    const label = item.free ? "FREE" : formatRp(item.subtotal);
    return `<span class="price-strike">${formatRp(gross)}</span> <strong>${label}</strong>`;
  }
  return `${item.qty} x ${formatRp(item.unit_price)} = ${formatRp(item.subtotal)}`;
}

function renderCatalog() {
  const grid = $("#product-grid");
  const search = ($("#search-input").value || "").trim().toLowerCase();
  let products = state.products.filter((item) => item.name.toLowerCase().includes(search));
  if (state.filter === "low") products = products.filter((item) => Number(item.stock || 0) <= 5);
  if (state.filter === "cart") products = products.filter((item) => cartRaw(item.name).qty > 0);

  if (!products.length) {
    grid.innerHTML = `<div class="empty-state">No products found</div>`;
    return;
  }

  grid.innerHTML = products.map((item) => {
    const raw = cartRaw(item.name);
    const qty = raw.qty;
    const src = imageSrc(item);
    const stock = Number(item.stock || 0);
    const stockClass = stock <= 0 ? "out" : stock <= 5 ? "low" : "";
    return `
      <article class="product-card ${qty ? "in-cart" : ""}">
        <div class="product-media">
          ${src ? `<img src="${escapeAttr(src)}" alt="">` : `<div class="product-fallback">${escapeHtml(productInitial(item.name))}</div>`}
        </div>
        <div>
          <div class="product-name">${escapeHtml(item.name)}</div>
          <div class="product-price">${formatRp(item.price)}</div>
          <div class="product-stock ${stockClass}">Stok: ${stock}</div>
        </div>
        <div class="qty-control">
          <button type="button" data-action="cart-dec" data-name="${escapeAttr(item.name)}">-</button>
          <span class="qty-count">${qty}</span>
          <button type="button" data-action="cart-inc" data-name="${escapeAttr(item.name)}">+</button>
        </div>
        <label class="free-toggle">
          <input type="checkbox" data-action="toggle-free" data-name="${escapeAttr(item.name)}" ${raw.free ? "checked" : ""}>
          <span>FREE</span>
        </label>
      </article>
    `;
  }).join("");
}

function renderCart() {
  const list = $("#cart-list");
  const entries = cartEntries();
  if (!entries.length) {
    list.innerHTML = `<div class="empty-state">Keranjang kosong - pilih produk di katalog</div>`;
    return;
  }
  list.innerHTML = entries.map((item) => `
    <article class="cart-item">
      <div class="cart-item-head">
        <div class="cart-item-main">
          <strong class="cart-item-name">${escapeHtml(item.name)}${item.free ? ' <span class="cart-free-badge">FREE</span>' : ""}</strong>
          <div class="cart-item-line">${cartPricingHtml(item)}</div>
        </div>
        <div class="cart-controls">
          <button class="mini-btn" type="button" data-action="cart-dec" data-name="${escapeAttr(item.name)}" aria-label="Kurangi">-</button>
          <span>${item.qty}</span>
          <button class="mini-btn add" type="button" data-action="cart-inc" data-name="${escapeAttr(item.name)}" aria-label="Tambah">+</button>
        </div>
      </div>
      <div class="cart-item-adjust">
        <label class="cart-disc-chip">
          <span>Disc %</span>
          <input type="text" inputmode="numeric" placeholder="0" value="${item.disc_pct || ""}" data-discount-field="disc_pct" data-name="${escapeAttr(item.name)}" ${item.disc_fixed ? "disabled" : ""}>
        </label>
        <label class="cart-disc-chip">
          <span>Disc Rp</span>
          <input type="text" inputmode="numeric" placeholder="0" value="${item.disc_fixed ? formatPlainNumber(item.disc_fixed) : ""}" data-discount-field="disc_fixed" data-name="${escapeAttr(item.name)}" ${item.disc_pct ? "disabled" : ""}>
        </label>
        <label class="cart-free-chip">
          <input type="checkbox" data-action="toggle-free" data-name="${escapeAttr(item.name)}" ${item.free ? "checked" : ""}>
          <span>Free</span>
        </label>
      </div>
    </article>
  `).join("");
}

function updateTotals() {
  const total = cartTotal();
  const cash = parseMoney($("#cash-received").value);
  const itemTypes = cartEntries().length;
  const itemQty = cartQtyTotal();
  const balance = cash - total;
  const hasCash = cash > 0;
  const ready = total > 0 && hasCash && balance >= 0;
  const topBalance = hasCash ? balance : -total;
  const topIsChange = hasCash && balance >= 0 && total > 0;
  const topIsDue = total > 0 && !topIsChange;

  $("#checkout-total").textContent = formatRp(total);
  $("#top-total-label").textContent = topIsChange ? "Change" : "Total Due";
  $("#top-total").textContent = formatSignedRp(topBalance);
  $("#top-total").classList.toggle("change", topIsChange);
  $("#top-total").classList.toggle("due", topIsDue);
  $("#top-count").textContent = `${itemTypes} jenis - ${itemQty} pcs`;
  $("#cash-hint").textContent = !itemQty ? "Add items first" : hasCash ? (ready ? "Ready" : "Below total") : "Blank = QRIS";
  $("#balance-label").textContent = hasCash ? (balance >= 0 ? "Change" : "Total Due") : "Total Due";
  $("#balance-value").textContent = formatSignedRp(hasCash ? balance : -total);
  $("#balance-row").classList.toggle("ready", balance >= 0 && total > 0);

  const payButton = $("#pay-button");
  if (state.activeQr) {
    payButton.textContent = "QRIS payment active";
    payButton.disabled = true;
  } else if (hasCash) {
    payButton.textContent = "Pay with Cash";
    payButton.disabled = !ready;
  } else {
    payButton.textContent = "Generate QRIS payment";
    payButton.disabled = total <= 0;
  }
  updateQrActions();
  queueDisplayPublish();
}

function qrImageSrc(active, size = 320) {
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

function updateQrActions() {
  const hasQr = Boolean(state.activeQr?.id && hasQrPayload(state.activeQr));
  const dismissLocked = qrDismissInFlight || Date.now() < dismissQrLockedUntil;
  const actions = $("#qr-actions");
  if (actions) actions.hidden = !hasQr;
  $$("[data-action='check-payment']").forEach((btn) => {
    btn.disabled = !hasQr;
    btn.title = hasQr ? "" : "Tidak ada QR aktif";
  });
  $$("[data-action='dismiss-qr']").forEach((btn) => {
    btn.disabled = !hasQr || dismissLocked;
    btn.title = !hasQr ? "Tidak ada QR aktif" : (dismissLocked ? "Tunggu 3 detik sebelum dismiss lagi" : "");
  });
}

function startDismissCooldown() {
  dismissQrLockedUntil = Date.now() + 3000;
  clearTimeout(dismissCooldownTimer);
  updateQrActions();
  dismissCooldownTimer = setTimeout(() => {
    dismissQrLockedUntil = 0;
    updateQrActions();
  }, 3000);
}

function resetCustomerFields() {
  const nameEl = $("#customer-name");
  const emailEl = $("#customer-email");
  if (nameEl) nameEl.value = "";
  if (emailEl) emailEl.value = "";
  queueDisplayPublish();
}

function clearCart({ force = false } = {}) {
  if (state.activeQr && !force) {
    showToast("Dismiss QR dulu sebelum clear cart", "error");
    return;
  }
  state.cart = {};
  $("#cash-received").value = "";
  resetCustomerFields();
  state.currentTxn = "";
  $("#txn-label").textContent = "TXN -";
  renderCatalog();
  renderCart();
  updateTotals();
}

function getCustomerSnapshot() {
  return {
    customer_name: $("#customer-name").value.trim(),
    customer_email: $("#customer-email").value.trim(),
    cashier_name: state.auth?.name || "Cashier",
  };
}

function checkoutPayload(method) {
  const total = cartTotal();
  const entries = cartEntries();
  const gross = entries.reduce((sum, item) => sum + Number(item.gross || 0), 0);
  const lineDiscountTotal = entries.reduce((sum, item) => sum + Number(item.line_discount || 0), 0);
  const cash = parseMoney($("#cash-received").value);
  const change = Math.max(0, cash - total);

  return {
    ...getCustomerSnapshot(),
    txn_id: state.currentTxn || "",
    amount: total,
    gross,
    line_discount: lineDiscountTotal,
    discount: lineDiscountTotal ? `line:${lineDiscountTotal}` : "0",
    cash_received: method === "Cash" ? cash : 0,
    change: method === "Cash" ? change : 0,
    payment_method: method,
    items: entries,
  };
}
async function payCash() {
  if (!cartEntries().length) {
    showToast("Keranjang kosong", "error");
    return;
  }
  const total = cartTotal();
  const cash = parseMoney($("#cash-received").value);
  if (cash < total) {
    showToast("Cash received masih kurang", "error");
    return;
  }
  const result = await api("/api/checkout/cash", { method: "POST", body: checkoutPayload("Cash") });
  const record = result.record || {};
  resetCustomerFields();
  state.pendingPaymentClear = true;
  applyServerData(result, { preserveCart: true });
  setDisplayEvent(result.display_event || null);
  publishDisplayState();
  showPaymentModal(record);
  showToast("Payment success", "success", PAYMENT_NOTICE_MS);
}

function compactActiveQr(active) {
  if (!active) return null;
  const next = { ...active };
  if (next.qr_data && next.qr_image) delete next.qr_image;
  return next;
}

function safeSetLocalStorage(key, value) {
  try {
    localStorage.setItem(key, value);
    return true;
  } catch (err) {
    if (err?.name === "QuotaExceededError" || /quota/i.test(String(err?.message || ""))) {
      console.warn("localStorage quota exceeded for", key);
      return false;
    }
    console.warn("localStorage set failed for", key, err);
    return false;
  }
}

function compactDisplayItem(item) {
  return {
    name: item.name,
    item_name: item.item_name || item.name,
    qty: item.qty,
    price: item.price,
    amount: item.amount,
    unit_price: item.unit_price,
    gross: item.gross,
    line_discount: item.line_discount,
    disc_pct: item.disc_pct,
    disc_fixed: item.disc_fixed,
    subtotal: item.subtotal,
    free: item.free,
  };
}

function compactDisplayPreview(preview) {
  return {
    items: (preview.items || []).map(compactDisplayItem),
    amount: preview.amount,
    payment_method: preview.payment_method,
    cash_received: preview.cash_received,
    change: preview.change,
    customer_name: preview.customer_name,
    cashier_name: preview.cashier_name,
  };
}
function displaySnapshot() {
  const cash = parseMoney($("#cash-received")?.value || "");
  const total = cartTotal();
  return compactDisplayPreview({
    items: cartEntries(),
    amount: total,
    payment_method: cash > 0 ? "Cash" : "QRIS",
    cash_received: cash,
    change: Math.max(0, cash - total),
    customer_name: $("#customer-name")?.value?.trim?.() || "",
    cashier_name: state.auth?.name || "Cashier",
  });
}

function publishDisplayState() {
  if (displayEventExpired(state.displayEvent)) state.displayEvent = null;
  state.activeQr = sanitizeActiveQr(state.activeQr);
  const preview = displaySnapshot();
  const payload = {
    activeQr: state.activeQr,
    settings: state.settings,
    preview,
    displayEvent: state.displayEvent,
    cashierNotice: cashierNoticeRecord ? cashierNoticePayload(cashierNoticeRecord, true) : null,
    version: state.version,
    account_id: state.auth?.id || "",
  };

  const merchantId = state.settings?.merchant_id || state.auth?.merchant_id || "";
  if (merchantId) safeSetLocalStorage(deviceStorageKey("conlecta_display_merchant"), merchantId);
  if (state.auth?.id) safeSetLocalStorage(deviceStorageKey("conlecta_display_account"), state.auth.id);

  if (state.activeQr) safeSetLocalStorage(deviceStorageKey("conlecta_active_qr"), JSON.stringify(compactActiveQr(state.activeQr)));
  else localStorage.removeItem(deviceStorageKey("conlecta_active_qr"));

  if (state.displayEvent) safeSetLocalStorage(deviceStorageKey("conlecta_display_event"), JSON.stringify(state.displayEvent));
  else localStorage.removeItem(deviceStorageKey("conlecta_display_event"));

  safeSetLocalStorage("conlecta_version", JSON.stringify(state.version || {}));
  safeSetLocalStorage(accountScopedStorageKey("conlecta_settings"), JSON.stringify(state.settings || {}));
  safeSetLocalStorage(deviceStorageKey("conlecta_display_preview"), JSON.stringify(preview));

  qrChannel?.postMessage({ type: "display-state", ...payload });
}

function queueDisplayPublish() {
  if (displayPublishQueued) return;
  displayPublishQueued = true;
  requestAnimationFrame(() => {
    displayPublishQueued = false;
    publishDisplayState();
  });
}

async function generateQR() {
  if (!cartEntries().length) {
    showToast("Keranjang kosong", "error");
    return;
  }

  const payload = checkoutPayload("QRIS");

  const result = await api("/api/qr/generate", {
    method: "POST",
    body: payload
  });

  console.log("QR GENERATE RESULT:", result);

  forgetClosedQr(result.active_qr);
  state.activeQr = sanitizeActiveQr(result.active_qr);

  if (!state.activeQr) {
    showToast("QRIS gagal ditampilkan", "error");
    return;
  }

  setDisplayEvent(null);
  state.currentTxn = state.activeQr.txn_id;
  $("#txn-label").textContent = state.currentTxn;

  updateQrActions();
  publishDisplayState();
  startQrPolling();
  renderCatalog();
  renderCart();
  updateTotals();
  showQrModal(state.activeQr);

  showToast(state.activeQr.message || "QRIS generated");
}

function isPaidStatus(status) {
  return ["PAID", "SUCCESS", "SUCCEEDED", "SETTLED", "COMPLETED"].includes(String(status || "").toUpperCase());
}

async function checkPayment(manual = true) {
  if (!state.activeQr) {
    if (manual) showToast("Tidak ada QR aktif", "error");
    return;
  }
  const result = await api(`/api/qr/status?id=${encodeURIComponent(state.activeQr.id)}`);
  const nextActive = result.active_qr || state.activeQr;
  if (isPaidStatus(result.status)) {
    state.activeQr = nextActive;
    await completeQrisPayment();
    return;
  }
  state.activeQr = sanitizeActiveQr(nextActive);
  if (!state.activeQr) {
    stopQrPolling();
    updateQrActions();
    publishDisplayState();
    return;
  }
  publishDisplayState();
  updateQrModal();
  if (manual) {
    showToast(`Status: ${result.status || "PENDING"}`);
  }
}

async function completeQrisPayment() {
  if (!state.activeQr || state.qrCompleting) return;
  state.qrCompleting = true;
  try {
    const active = state.activeQr;
    rememberClosedQr(active);
    const gross = (active.items || []).reduce((sum, item) => sum + Number(item.gross || 0), 0) || active.amount;
    const lineDiscount = (active.items || []).reduce((sum, item) => sum + Number(item.line_discount || 0), 0);
    const payload = {
      txn_id: active.txn_id,
      qr_id: active.id,
      amount: active.amount,
      gross,
      line_discount: lineDiscount,
      discount: lineDiscount ? `line:${lineDiscount}` : "0",
      customer_name: active.customer_name,
      customer_email: active.customer_email,
      cashier_name: active.cashier_name,
      payment_method: "QRIS",
      items: active.items || [],
    };
    const result = await api("/api/checkout/qris-success", { method: "POST", body: payload });
    const record = result.record || payload;
    resetCustomerFields();
    state.pendingPaymentClear = true;
    applyServerData(result, { preserveCart: true });
    state.activeQr = null;
    setDisplayEvent(result.display_event || null);
    updateQrActions();
    stopQrPolling();
    publishDisplayState();
    showPaymentModal(record);
    showToast("Payment success", "success", PAYMENT_NOTICE_MS);
  } finally {
    state.qrCompleting = false;
  }
}

async function dismissQR() {
  if (qrDismissInFlight || Date.now() < dismissQrLockedUntil) {
    showToast("Tunggu 3 detik sebelum dismiss lagi.", "error");
    return;
  }
  if (!state.activeQr) {
    updateQrActions();
    showToast("Tidak ada QR aktif untuk dismiss.", "error");
    return;
  }
  qrDismissInFlight = true;
  startDismissCooldown();
  try {
    const result = await api("/api/qr/dismiss", { method: "POST", body: {} });
    rememberClosedQr(state.activeQr);
    state.activeQr = null;
    stopQrPolling();
    closeModal(true);
    clearCart({ force: true });
    setDisplayEvent(result.display_event || null);
    localStorage.removeItem(deviceStorageKey("conlecta_active_qr"));
    publishDisplayState();
    showToast("QR dismissed", "error", PAYMENT_NOTICE_MS);
  } finally {
    qrDismissInFlight = false;
    updateQrActions();
  }
}

function startQrPolling() {
  stopQrPolling();
  if (!state.activeQr) return;
  qrPollTimer = setInterval(() => checkPayment(false).catch(() => null), 5000);
}

function stopQrPolling() {
  if (qrPollTimer) clearInterval(qrPollTimer);
  qrPollTimer = null;
}

function msUntilNextSessionReset() {
  const now = new Date();
  const reset = new Date(now);
  reset.setHours(23, 59, 0, 0);
  if (now >= reset) reset.setDate(reset.getDate() + 1);
  return Math.max(1000, reset.getTime() - now.getTime());
}

function scheduleDailySessionReset() {
  if (dailySessionTimer) clearTimeout(dailySessionTimer);
  dailySessionTimer = setTimeout(() => {
    reloadBootstrap()
      .then(() => showToast("Cashier session reset untuk hari baru."))
      .catch(() => null)
      .finally(scheduleDailySessionReset);
  }, msUntilNextSessionReset());
}

function openQrDisplay() {
  publishDisplayState();
  const win = window.open("/qr-display.html", `conlecta_qr_display_${getDeviceId()}`);
  if (win) {
    qrDisplayWindow = win;
    win.focus();
  }
  else showToast("Browser blocked the QR Display tab", "error");
}

function requestQrDisplayClose() {
  try {
    qrChannel?.postMessage({ type: "close-display" });
    localStorage.setItem("conlecta_close_qr_display_at", String(Date.now()));
    localStorage.removeItem(deviceStorageKey("conlecta_active_qr"));
    localStorage.removeItem(deviceStorageKey("conlecta_display_event"));
    localStorage.removeItem(deviceStorageKey("conlecta_display_preview"));
    qrDisplayWindow?.close?.();
  } catch {
    // Closing a browser tab can be blocked; QR Display also listens for the close signal.
  } finally {
    qrDisplayWindow = null;
  }
}

function showPaymentModal(record) {
  const txnId = paymentModalTxnId(record);
  if (paymentModalAcknowledged(txnId)) return;
  if (!$("#payment-modal").hidden && txnId && state.activePaymentModalTxn === txnId) return;
  const method = displayPaymentMethod(record);
  const change = parseMoney(record.change);
  const changeAlert = $("#modal-cash-change-alert");
  state.activePaymentModalTxn = txnId;
  $("#detail-modal").hidden = true;
  $("#qr-modal").hidden = true;
  $("#dismiss-modal").hidden = true;
  $("#logout-modal").hidden = true;
  $("#payment-modal").hidden = false;
  $("#payment-title").textContent = "Payment Success";
  $("#payment-subtitle").textContent = method === "Cash" ? `Kembalian ${formatRp(change)}` : "QRIS Paid";
  $("#modal-txn").textContent = record.txn_id || "-";
  $("#modal-customer").textContent = record.customer_name || record.customer || "-";
  $("#modal-email").textContent = record.customer_email || "-";
  $("#modal-amount").textContent = formatRp(record.amount);
  $("#modal-cash").textContent = method === "Cash" ? formatRp(record.cash_received) : "-";
  $("#modal-change").textContent = method === "Cash" ? formatRp(change) : "-";
  if (changeAlert) {
    changeAlert.hidden = method !== "Cash";
    $("#modal-cash-change").textContent = formatRp(change);
  }
  $("#modal-backdrop").hidden = false;
  startCashierNoticeHeartbeat(record);
}

function showDismissModal(event) {
  const data = event || {};
  $("#payment-modal").hidden = true;
  $("#detail-modal").hidden = true;
  $("#qr-modal").hidden = true;
  $("#logout-modal").hidden = true;
  $("#dismiss-modal").hidden = false;
  $("#dismiss-subtitle").textContent = data.message || "Payment request closed.";
  $("#dismiss-txn").textContent = data.txn_id || "-";
  $("#dismiss-qr-id").textContent = data.qr_id || data.id || "-";
  $("#dismiss-total").textContent = formatRp(data.amount);
  $("#modal-backdrop").hidden = false;
}

function showQrModal(active = state.activeQr) {
  const src = qrImageSrc(active, 320);
  if (!src) return;
  $("#payment-modal").hidden = true;
  $("#detail-modal").hidden = true;
  $("#dismiss-modal").hidden = true;
  $("#logout-modal").hidden = true;
  $("#qr-modal").hidden = false;
  $("#qr-modal-img").src = src;
  $("#qr-modal-txn").textContent = active.txn_id || "-";
  $("#qr-modal-id").textContent = active.id || "-";
  $("#qr-modal-total").textContent = formatRp(active.amount);
  $("#qr-modal-status").textContent = active.status ? `Status: ${active.status}` : "Menunggu pembayaran";
  $("#modal-backdrop").hidden = false;
  updateQrActions();
}

function updateQrModal() {
  if ($("#qr-modal").hidden || !state.activeQr) return;
  showQrModal(state.activeQr);
}

function acknowledgeDisplayEvent(txnId) {
  api("/api/display-event/ack", {
    method: "POST",
    body: { txn_id: txnId || "" },
    loading: false,
  })
    .then((result) => {
      if (Object.prototype.hasOwnProperty.call(result, "display_event")) {
        setDisplayEvent(result.display_event || null);
        publishDisplayState();
      }
    })
    .catch((err) => showToast(err.message, "error"));
}

function closeModal(force = false) {
  if (!force && !$("#qr-modal").hidden && state.activeQr) return;
  const paymentWasOpen = !$("#payment-modal").hidden;
  const paymentTxn = state.activePaymentModalTxn || $("#modal-txn").textContent;
  if (paymentWasOpen) {
    markPaymentModalAcknowledged(paymentTxn);
    stopCashierNoticeHeartbeat(paymentTxn);
    setDisplayEvent(null);
    acknowledgeDisplayEvent(paymentTxn);
    if (state.pendingPaymentClear) {
      state.pendingPaymentClear = false;
      clearCart({ force: true });
    } else {
      publishDisplayState();
    }
  }
  state.activePaymentModalTxn = "";
  $("#modal-backdrop").hidden = true;
  $("#payment-modal").hidden = true;
  $("#detail-modal").hidden = true;
  $("#qr-modal").hidden = true;
  $("#dismiss-modal").hidden = true;
  $("#logout-modal").hidden = true;
}

function applyServerData(result, { preserveCart = false } = {}) {
  if (result.products) state.products = result.products;
  if (result.history) state.history = result.history;
  if (result.session) state.session = result.session;
  if (Object.prototype.hasOwnProperty.call(result, "display_event")) setDisplayEvent(result.display_event);
  if (!preserveCart) reconcileCartWithStock();
  renderCatalog();
  renderCart();
  renderHistory();
  updateSession();
  updateTotals();
}

function updateSession() {
  $("#session-sales").textContent = state.session?.sales || 0;
  $("#session-revenue").textContent = formatRp(state.session?.revenue || 0);
}

function selectedStockIndex() {
  const idx = Number(state.selectedStockIndex);
  if (Number.isInteger(idx) && idx >= 0 && idx < state.products.length) return idx;
  if (state.selectedStockName) {
    return state.products.findIndex((item) => item.name === state.selectedStockName);
  }
  return -1;
}

function selectedStockItem() {
  const idx = selectedStockIndex();
  return idx >= 0 ? state.products[idx] : null;
}

function renderStock() {
  renderVendorOptions();
  renderVendors();
  const selectedIndex = selectedStockIndex();
  state.selectedStockIndex = selectedIndex;
  const selectedItem = selectedStockItem();
  state.selectedStockName = selectedItem?.name || "";
  if (selectedItem && $("#stock-vendor")) $("#stock-vendor").value = selectedItem.vendor_id || "";
  $("#stock-count").textContent = `${state.products.length} items`;
  const vendorMap = Object.fromEntries((state.vendors || []).map((v) => [String(v.id), v.name]));
  $("#stock-list").innerHTML = state.products.map((item, index) => {
    const stock = Number(item.stock || 0);
    const cls = stock <= 0 ? "out" : stock <= 5 ? "low" : "";
    const src = imageSrc(item);
    const vendorName = vendorMap[String(item.vendor_id || "")] || "No Vendor";
    const capital = productCapital(item);
    const unitProfit = Number(item.price || 0) - capital;
    return `
      <article class="stock-item ${selectedIndex === index ? "selected" : ""}" data-action="select-stock" data-index="${index}" data-name="${escapeAttr(item.name)}">
        <div class="stock-thumb">${src ? `<img src="${escapeAttr(src)}" alt="">` : escapeHtml(productInitial(item.name))}</div>
        <div>
          <strong>${escapeHtml(item.name)}</strong>
          <div class="stock-price">${formatRp(item.price)}</div>
          <div class="muted">Modal ${formatRp(capital)} | Margin ${formatRp(unitProfit)}</div>
          <div class="muted">${escapeHtml(vendorName)}</div>
        </div>
        <div class="stock-badge ${cls}">${stock}</div>
      </article>
    `;
  }).join("");
}

function renderVendorOptions() {
  const currentStockVendor = $("#stock-vendor")?.value || "";
  const currentInvoiceVendor = $("#invoice-vendor")?.value || "";
  const options = [`<option value="">(No Vendor)</option>`].concat(
    (state.vendors || []).map((v) => `<option value="${escapeAttr(v.id)}">${escapeHtml(v.name)}</option>`),
  ).join("");
  const stockVendor = $("#stock-vendor");
  const invoiceVendor = $("#invoice-vendor");
  if (stockVendor) {
    stockVendor.innerHTML = options;
    stockVendor.value = currentStockVendor;
  }
  if (invoiceVendor) {
    invoiceVendor.innerHTML = `<option value="">(All)</option>${(state.vendors || []).map((v) => `<option value="${escapeAttr(v.id)}">${escapeHtml(v.name)}</option>`).join("")}`;
    invoiceVendor.value = currentInvoiceVendor;
  }
}

function renderVendors() {
  const list = $("#vendor-list");
  if (!list) return;
  if (!state.vendors?.length) {
    list.innerHTML = `<div class="empty-state">Belum ada vendor</div>`;
    return;
  }
  list.innerHTML = state.vendors.map((vendor) => `
    <article class="stock-item">
      <div class="stock-thumb">${escapeHtml(productInitial(vendor.name))}</div>
      <div>
        <strong>${escapeHtml(vendor.name)}</strong>
      </div>
      <button class="btn danger-soft" type="button" data-action="delete-vendor" data-id="${escapeAttr(vendor.id)}">Delete</button>
    </article>
  `).join("");
}

function selectStock(identifier) {
  const numericIndex = Number(identifier);
  const index = Number.isInteger(numericIndex) && numericIndex >= 0 && numericIndex < state.products.length
    ? numericIndex
    : state.products.findIndex((p) => p.name === identifier);
  const item = index >= 0 ? state.products[index] : null;
  if (!item) return;
  state.selectedStockIndex = index;
  state.selectedStockName = item.name;
  state.stockImageB64 = item.image_b64 || "";
  $("#stock-name").value = item.name;
  $("#stock-price").value = formatPlainNumber(item.price);
  $("#stock-capital").value = formatPlainNumber(productCapital(item));
  $("#stock-qty").value = item.stock || 0;
  $("#stock-vendor").value = item.vendor_id || "";
  renderImagePreview();
  renderStock();
}

function renderImagePreview() {
  const preview = $("#stock-image-preview");
  const img = state.stockImageB64 ? imageSrc({ image_b64: state.stockImageB64 }) : "";
  preview.innerHTML = img ? `<img src="${escapeAttr(img)}" alt="">` : "Choose image";
}

function resetStockForm() {
  state.selectedStockName = "";
  state.selectedStockIndex = -1;
  state.stockImageB64 = "";
  $("#stock-form").reset();
  if ($("#stock-image")) $("#stock-image").value = "";
  renderImagePreview();
}

async function saveStockForm(event) {
  event.preventDefault();
  const name = $("#stock-name").value.trim();
  if (!name) {
    showToast("Nama item tidak boleh kosong", "error");
    return;
  }
  const item = {
    name,
    price: parseMoney($("#stock-price").value),
    capital: parseMoney($("#stock-capital").value),
    stock: parseMoney($("#stock-qty").value),
    vendor_id: $("#stock-vendor").value || "",
    image_b64: state.stockImageB64 || "",
  };
  let index = selectedStockIndex();
  if (index < 0) index = state.products.findIndex((p) => p.name === state.selectedStockName || p.name === name);
  if (index >= 0) state.products[index] = item;
  else state.products.push(item);
  const result = await api("/api/stock/save", { method: "POST", body: { products: state.products } });
  state.products = result.products || state.products;
  resetStockForm();
  renderStock();
  renderCatalog();
  showToast("Stock saved");
}

async function deleteSelectedStock() {
  const index = selectedStockIndex();
  if (index < 0) {
    showToast("Pilih item dulu", "error");
    return;
  }
  const removed = state.products[index];
  state.products.splice(index, 1);
  delete state.cart[removed.name];
  const result = await api("/api/stock/save", { method: "POST", body: { products: state.products } });
  state.products = result.products || state.products;
  resetStockForm();
  renderStock();
  renderCatalog();
  renderCart();
  updateTotals();
  showToast("Item deleted");
}

async function setStockTab(tab, { loading = true } = {}) {
  const nextTab = ["items", "vendors", "invoice"].includes(tab) ? tab : "items";
  state.stockTab = nextTab;
  $$(".stock-tabs .seg").forEach((btn) => btn.classList.toggle("active", btn.dataset.stockTab === nextTab));
  $$(".stock-section").forEach((section) => section.classList.toggle("active", section.id === `stock-section-${nextTab}`));
  if (!state.auth || isSystemAdmin()) return;
  await refreshActiveStockTab({ loading });
}

async function addVendor() {
  const name = $("#vendor-name").value.trim();
  if (!name) {
    showToast("Vendor name kosong", "error");
    return;
  }
  const result = await api("/api/vendor/save", { method: "POST", body: { name } });
  state.vendors = result.vendors || state.vendors;
  $("#vendor-name").value = "";
  renderStock();
  showToast("Vendor saved");
}

async function deleteVendor(vendorId) {
  const result = await api("/api/vendor/delete", { method: "POST", body: { vendor_id: vendorId } });
  state.vendors = result.vendors || [];
  state.products = state.products.map((item) => String(item.vendor_id || "") === String(vendorId) ? { ...item, vendor_id: "" } : item);
  renderStock();
  showToast("Vendor deleted");
}

async function buildVendorInvoice() {
  await refreshVendorInvoiceContext({ loading: true });
  const params = new URLSearchParams({
    vendor_id: $("#invoice-vendor").value || "",
    from: $("#invoice-from").value || "",
    to: $("#invoice-to").value || "",
  });
  const result = await api(`/api/vendor-invoice?${params.toString()}`, { loading: "Memuat vendor invoice..." });
  state.vendorInvoiceRows = result.rows || [];
  state.vendorInvoiceTotals = result.totals || {};
  renderVendorInvoice();
}

function renderVendorInvoice() {
  const totals = state.vendorInvoiceTotals || {};
  $("#vendor-invoice-stats").innerHTML = [
    ["Lines", state.vendorInvoiceRows.length || 0],
    ["Qty", totals.qty || 0],
    ["Vendor Cost", formatRp(totals.cost || 0)],
    ["Gross", formatRp(totals.gross || 0)],
    ["Discount", formatRp(totals.discount || 0)],
    ["Subtotal", formatRp(totals.subtotal || 0)],
    ["Profit", formatRp(totals.profit || 0)],
  ].map(([label, value]) => `<div class="stat-card"><span>${label}</span><strong>${value}</strong></div>`).join("");
  const body = $("#vendor-invoice-body");
  if (!state.vendorInvoiceRows.length) {
    body.innerHTML = `<tr><td colspan="12" class="muted">Build table untuk melihat invoice vendor</td></tr>`;
    return;
  }
  body.innerHTML = state.vendorInvoiceRows.map((row) => `
    <tr>
      <td class="mono">${escapeHtml(row.txn || "-")}</td>
      <td>${escapeHtml(row.date || "-")}</td>
      <td>${escapeHtml(row.method || "-")}</td>
      <td>${escapeHtml(row.vendor_name || "-")}</td>
      <td>${escapeHtml(row.item || "-")}</td>
      <td>${escapeHtml(row.qty || 0)}</td>
      <td class="amount">${formatRp(row.capital || 0)}</td>
      <td class="amount">${formatRp(row.cost || 0)}</td>
      <td class="amount">${formatRp(row.gross)}</td>
      <td class="amount">${row.discount ? formatRp(row.discount) : "-"}</td>
      <td class="amount">${formatRp(row.subtotal)}</td>
      <td class="amount">${formatRp(row.profit || 0)}</td>
    </tr>
  `).join("");
}

async function exportVendorPdf() {
  const params = new URLSearchParams({
    vendor_id: $("#invoice-vendor").value || "",
    from: $("#invoice-from").value || "",
    to: $("#invoice-to").value || "",
  });
  await downloadFile(`/api/vendor-invoice.pdf?${params.toString()}`, {
    filename: "vendor-invoice.pdf",
    message: "Menyiapkan vendor invoice...",
  });
  showToast("Vendor invoice downloaded");
}

function parseHistoryDate(value) {
  const text = String(value || "").split(" - ").pop().trim();
  if (!text) return null;
  if (/^\d{2}-\d{2}-\d{4}/.test(text)) {
    const [date, time = "00:00"] = text.split(" ");
    const [day, month, year] = date.split("-").map(Number);
    const [hour = 0, minute = 0] = time.split(":").map(Number);
    return new Date(year, month - 1, day, hour, minute);
  }
  const dt = new Date(text);
  return Number.isNaN(dt.getTime()) ? null : dt;
}

function parseDiscountMeta(raw) {
  const meta = { pct: 0, cart: 0, line: 0, gross: 0 };
  const text = String(raw || "").trim();
  if (!text || text === "0" || text === "-") return meta;
  if (/^\d+%$/.test(text)) {
    meta.pct = clampNumber(parseMoney(text), 0, 100);
    return meta;
  }
  if (/^\d+$/.test(text)) {
    meta.pct = clampNumber(parseMoney(text), 0, 100);
    return meta;
  }
  text.split("|").forEach((part) => {
    const [rawKey, rawValue] = part.split(":");
    if (!rawKey || rawValue === undefined) return;
    const key = rawKey.trim().toLowerCase();
    const value = parseMoney(rawValue);
    if (["pct", "percent", "percentage"].includes(key)) meta.pct = clampNumber(value, 0, 100);
    else if (["cart", "cart_amt", "gross_discount", "gross_disc"].includes(key)) meta.cart = value;
    else if (["line", "line_discount", "item", "fixed"].includes(key)) meta.line = value;
    else if (key === "gross") meta.gross = value;
  });
  return meta;
}

function historyDiscountBreakdown(record) {
  const amount = Number(record.amount || 0);
  const meta = parseDiscountMeta(record.discount);
  const line = Number(record.line_discount || record.line_discount_total || 0) || meta.line;
  const pct = Number(record.cart_discount_pct || 0) || meta.pct;
  let cart = Number(record.cart_discount_amt || 0) || meta.cart;
  let gross = Number(record.gross || record.gross_subtotal || 0) || meta.gross;
  if (!gross) {
    gross = pct && pct < 100
      ? Math.round(amount / (1 - pct / 100)) + line
      : amount + line + cart;
  }
  const afterLine = Math.max(0, gross - line);
  if (pct && !cart) cart = Math.round(afterLine * pct / 100);
  return {
    amount,
    gross,
    line,
    pct,
    cart,
    total: line + cart,
  };
}

function filteredHistory() {
  const search = state.historySearch.trim().toLowerCase();
  const qr = state.historyQr.trim().toLowerCase();
  const customer = state.historyCustomer.trim().toLowerCase();
  const method = state.historyMethod;
  const cashier = state.historyCashier;
  const from = state.historyFrom ? new Date(state.historyFrom) : null;
  const to = state.historyTo ? new Date(state.historyTo) : null;
  return (state.history || []).filter((record) => {
    const recordMethod = displayPaymentMethod(record);
    const matchesMethod = !method || recordMethod === method;
    const matchesTxn = !search || String(record.txn_id || "").toLowerCase().includes(search);
    const matchesQr = !qr || String(record.qr_id || "").toLowerCase().includes(qr);
    const matchesCustomer = !customer || `${record.customer_name || ""} ${record.customer || ""} ${record.customer_email || ""}`.toLowerCase().includes(customer);
    const matchesCashier = !cashier || String(record.cashier_name || "") === cashier;
    const dt = parseHistoryDate(record.updated_at_display || record.updated_at);
    const matchesFrom = !from || (dt && dt >= from);
    const matchesTo = !to || (dt && dt <= to);
    return matchesMethod && matchesTxn && matchesQr && matchesCustomer && matchesCashier && matchesFrom && matchesTo;
  }).sort((a, b) => {
    const da = parseHistoryDate(a.updated_at_display || a.updated_at);
    const db = parseHistoryDate(b.updated_at_display || b.updated_at);
    return (da ? da.getTime() : 0) - (db ? db.getTime() : 0);
  });
}

function discountText(record) {
  const breakdown = historyDiscountBreakdown(record);
  if (breakdown.total) return formatRp(breakdown.total);
  const raw = String(record.discount || "").trim();
  if (raw && raw !== "0" && !/^\d+%?$/.test(raw)) return raw;
  return "-";
}

function analyticsFilteredHistory() {
  const from = state.analyticsFrom ? new Date(state.analyticsFrom) : null;
  const to = state.analyticsTo ? new Date(state.analyticsTo) : null;
  const method = state.analyticsMethod;
  return (state.history || []).filter((record) => {
    const dt = parseHistoryDate(record.updated_at_display || record.updated_at);
    const matchesFrom = !from || (dt && dt >= from);
    const matchesTo = !to || (dt && dt <= to);
    const matchesMethod = !method || displayPaymentMethod(record) === method;
    return matchesFrom && matchesTo && matchesMethod;
  });
}

function syncAnalyticsFiltersFromInputs() {
  state.analyticsFrom = $("#analytics-from")?.value || "";
  state.analyticsTo = $("#analytics-to")?.value || "";
  state.analyticsMethod = $("#analytics-method")?.value || "";
  state.analyticsMetric = $("#analytics-metric")?.value || "profit";
  state.analyticsLimit = Number($("#analytics-limit")?.value || 8) || 8;
}

function analyticsItemCosts(record, productMap = new Map()) {
  const items = record.items || [];
  const totalFee = recordPaymentFee(record);
  const subtotalTotal = items.reduce((sum, item) => sum + Number(item.subtotal || 0), 0);
  let remainingFee = totalFee;
  return items.map((item, index) => {
    const name = String(item.item_name || item.name || "").trim();
    const qty = Number(item.qty || 0);
    const subtotal = Number(item.subtotal || 0);
    const gross = Number(item.gross || subtotal || 0);
    const currentProduct = productMap.get(name);
    const capital = Number(item.capital || item.cost || productCapital(currentProduct) || 0);
    const storedFee = Number(item.payment_fee || 0);
    const qrisCost = storedFee || (totalFee && subtotalTotal
      ? (index === items.length - 1 ? remainingFee : Math.round(totalFee * subtotal / subtotalTotal))
      : 0);
    if (!storedFee) remainingFee -= qrisCost;
    const storedTotalCost = Number(item.total_cost || 0);
    const vendorCost = (capital * qty) || Math.max(0, storedTotalCost - qrisCost);
    const totalCost = vendorCost + qrisCost;
    return {
      item,
      name,
      qty,
      subtotal,
      gross,
      vendorCost,
      qrisCost,
      totalCost,
      profit: subtotal - totalCost,
    };
  });
}

function analyticsRows(records = analyticsFilteredHistory()) {
  const productMap = new Map((state.products || []).map((product) => [String(product.name || ""), product]));
  const rows = new Map();
  records.forEach((record) => {
    analyticsItemCosts(record, productMap).forEach((costLine) => {
      const name = costLine.name;
      if (!name) return;
      const row = rows.get(name) || {
        name,
        qty: 0,
        revenue: 0,
        gross: 0,
        vendorCost: 0,
        qrisCost: 0,
        cost: 0,
        profit: 0,
        transactions: new Set(),
      };
      row.qty += costLine.qty;
      row.revenue += costLine.subtotal;
      row.gross += costLine.gross;
      row.vendorCost += costLine.vendorCost;
      row.qrisCost += costLine.qrisCost;
      row.cost += costLine.totalCost;
      row.profit += costLine.profit;
      row.transactions.add(record.txn_id || record.qr_id || `${name}-${row.qty}`);
      rows.set(name, row);
    });
  });
  return Array.from(rows.values()).map((row) => ({
    ...row,
    transactions: row.transactions.size,
    margin: row.revenue ? (row.profit / row.revenue) * 100 : 0,
  }));
}

function metricValue(row, metric = state.analyticsMetric) {
  if (metric === "qty") return row.qty;
  if (metric === "revenue") return row.revenue;
  if (metric === "vendor_cost") return row.vendorCost;
  if (metric === "qris_cost") return row.qrisCost;
  if (metric === "cost") return row.cost;
  if (metric === "margin") return row.margin;
  return row.profit;
}

function metricLabel(metric = state.analyticsMetric) {
  return {
    profit: "Profit",
    revenue: "Revenue",
    vendor_cost: "Vendor Cost",
    qris_cost: "QRIS Cost",
    cost: "Total Cost",
    qty: "Qty Sold",
    margin: "Margin %",
  }[metric] || "Profit";
}

function metricDisplay(value, metric = state.analyticsMetric) {
  if (metric === "qty") return Number(value || 0).toLocaleString("id-ID");
  if (metric === "margin") return formatPct(value);
  return formatRp(value);
}

function dailyAnalytics(records) {
  const days = new Map();
  const productMap = new Map((state.products || []).map((product) => [String(product.name || ""), product]));
  records.forEach((record) => {
    const dt = parseHistoryDate(record.updated_at_display || record.updated_at);
    const key = dt ? dt.toLocaleDateString("sv-SE") : "Unknown";
    const row = days.get(key) || { date: key, revenue: 0, vendorCost: 0, qrisCost: 0, cost: 0, profit: 0 };
    row.revenue += Number(record.amount || 0);
    analyticsItemCosts(record, productMap).forEach((costLine) => {
      row.vendorCost += costLine.vendorCost;
      row.qrisCost += costLine.qrisCost;
      row.cost += costLine.totalCost;
      row.profit += costLine.profit;
    });
    days.set(key, row);
  });
  return Array.from(days.values()).sort((a, b) => a.date.localeCompare(b.date));
}

function trendSvg(points) {
  if (!points.length) return `<div class="empty-state">No trend data</div>`;
  const width = 720;
  const height = 220;
  const pad = 26;
  const max = Math.max(...points.map((p) => Math.max(p.revenue, p.profit)), 1);
  const x = (index) => pad + (points.length === 1 ? (width - pad * 2) / 2 : index * ((width - pad * 2) / (points.length - 1)));
  const y = (value) => height - pad - (Number(value || 0) / max) * (height - pad * 2);
  const revenue = points.map((p, index) => `${x(index)},${y(p.revenue)}`).join(" ");
  const profit = points.map((p, index) => `${x(index)},${y(p.profit)}`).join(" ");
  return `
    <svg class="analytics-trend-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Revenue and profit trend">
      <defs>
        <linearGradient id="trendRevenue" x1="0" x2="1"><stop stop-color="#67e8f9"/><stop offset="1" stop-color="#34d399"/></linearGradient>
        <linearGradient id="trendProfit" x1="0" x2="1"><stop stop-color="#facc15"/><stop offset="1" stop-color="#fb7185"/></linearGradient>
      </defs>
      <line x1="${pad}" y1="${height - pad}" x2="${width - pad}" y2="${height - pad}" class="trend-axis"></line>
      <polyline points="${revenue}" class="trend-line revenue"></polyline>
      <polyline points="${profit}" class="trend-line profit"></polyline>
      ${points.map((p, index) => `<circle cx="${x(index)}" cy="${y(p.revenue)}" r="4" class="trend-dot revenue"></circle>`).join("")}
      ${points.map((p, index) => `<circle cx="${x(index)}" cy="${y(p.profit)}" r="4" class="trend-dot profit"></circle>`).join("")}
    </svg>
  `;
}

function analyticsSummary(records, rows) {
  const totalRevenue = records.reduce((sum, record) => sum + Number(record.amount || 0), 0);
  const totalVendorCost = rows.reduce((sum, row) => sum + row.vendorCost, 0);
  const totalQrisCost = rows.reduce((sum, row) => sum + row.qrisCost, 0);
  const totalCost = totalVendorCost + totalQrisCost;
  const totalProfit = totalRevenue - totalCost;
  const totalQty = rows.reduce((sum, row) => sum + row.qty, 0);
  const cash = records.filter((record) => displayPaymentMethod(record) === "Cash").length;
  const qris = records.length - cash;
  return {
    totalRevenue,
    totalVendorCost,
    totalQrisCost,
    totalCost,
    totalProfit,
    totalQty,
    cash,
    qris,
    transactions: records.length,
    margin: totalRevenue ? (totalProfit / totalRevenue) * 100 : 0,
  };
}

function renderAnalytics() {
  if (!$("#analytics-stats")) return;
  const records = analyticsFilteredHistory();
  const rows = analyticsRows(records);
  const metric = state.analyticsMetric;
  const sorted = [...rows].sort((a, b) => metricValue(b, metric) - metricValue(a, metric));
  const limit = Math.max(3, Number(state.analyticsLimit || 8));
  const top = sorted.slice(0, limit);
  const summary = analyticsSummary(records, rows);
  const maxMetric = Math.max(...top.map((row) => Math.abs(metricValue(row, metric))), 1);

  $("#analytics-stats").innerHTML = [
    ["Revenue", formatRp(summary.totalRevenue)],
    ["Vendor Cost", formatRp(summary.totalVendorCost)],
    ["QRIS Cost", formatRp(summary.totalQrisCost)],
    ["Total Cost", formatRp(summary.totalCost)],
    ["Profit", formatRp(summary.totalProfit)],
    ["Margin", formatPct(summary.margin)],
    ["Units", summary.totalQty.toLocaleString("id-ID")],
    ["Transactions", summary.transactions],
  ].map(([label, value]) => `<div class="stat-card"><span>${label}</span><strong>${value}</strong></div>`).join("");

  $("#analytics-bars-title").textContent = `Top Products by ${metricLabel(metric)}`;
  $("#analytics-bars").innerHTML = top.length ? top.map((row, index) => {
    const value = metricValue(row, metric);
    const width = Math.max(4, Math.min(100, Math.abs(value) / maxMetric * 100));
    return `
      <div class="analytics-bar-row">
        <div class="analytics-rank">${index + 1}</div>
        <div class="analytics-bar-main">
          <div class="analytics-bar-head">
            <strong>${escapeHtml(row.name)}</strong>
            <span>${metricDisplay(value, metric)}</span>
          </div>
          <div class="analytics-bar-track"><i style="width:${width}%"></i></div>
          <div class="analytics-bar-meta">
            <span>${row.qty} pcs</span>
            <span>${formatRp(row.revenue)} revenue</span>
            <span>${formatRp(row.vendorCost)} vendor</span>
            <span>${formatRp(row.qrisCost)} QRIS</span>
            <span>${formatRp(row.profit)} profit</span>
            <span>${formatPct(row.margin)} margin</span>
          </div>
        </div>
      </div>
    `;
  }).join("") : `<div class="empty-state">No sales data for this filter</div>`;

  const cashPct = records.length ? Math.round(summary.cash / records.length * 100) : 0;
  $("#analytics-method-donut").style.background = `conic-gradient(var(--green) 0 ${cashPct}%, var(--cyan) ${cashPct}% 100%)`;
  $("#analytics-method-text").innerHTML = `<strong>${cashPct}%</strong><span>Cash</span><small>${summary.cash} cash / ${summary.qris} QRIS</small>`;
  $("#analytics-trend").innerHTML = trendSvg(dailyAnalytics(records));
  $("#analytics-table-body").innerHTML = sorted.length ? sorted.map((row) => `
    <tr>
      <td>${escapeHtml(row.name)}</td>
      <td class="amount">${row.qty}</td>
      <td class="amount">${formatRp(row.revenue)}</td>
      <td class="amount">${formatRp(row.vendorCost)}</td>
      <td class="amount">${formatRp(row.qrisCost)}</td>
      <td class="amount">${formatRp(row.cost)}</td>
      <td class="amount">${formatRp(row.profit)}</td>
      <td class="amount">${formatPct(row.margin)}</td>
      <td class="amount">${row.transactions}</td>
    </tr>
  `).join("") : `<tr><td colspan="9" class="muted">No analytics rows</td></tr>`;
}

function csvCell(value) {
  const text = String(value ?? "");
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function rawNumber(value, decimals = 2) {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return "0";
  return Number.isInteger(number) ? String(number) : number.toFixed(decimals);
}

function exportAnalyticsData() {
  syncAnalyticsFiltersFromInputs();
  const records = analyticsFilteredHistory();
  const rows = analyticsRows(records);
  const metric = state.analyticsMetric;
  const sorted = [...rows].sort((a, b) => metricValue(b, metric) - metricValue(a, metric));
  const summary = analyticsSummary(records, rows);
  const csvRows = [
    ["summary_metric", "value"],
    ["revenue", rawNumber(summary.totalRevenue, 0)],
    ["vendor_modal_cost", rawNumber(summary.totalVendorCost, 0)],
    ["qris_cost", rawNumber(summary.totalQrisCost, 0)],
    ["total_cost", rawNumber(summary.totalCost, 0)],
    ["profit", rawNumber(summary.totalProfit, 0)],
    ["margin_pct", rawNumber(summary.margin)],
    ["units", rawNumber(summary.totalQty, 0)],
    ["transactions", rawNumber(summary.transactions, 0)],
    ["cash_transactions", rawNumber(summary.cash, 0)],
    ["qris_transactions", rawNumber(summary.qris, 0)],
    [],
    ["item", "qty", "revenue", "vendor_modal_cost", "qris_cost", "total_cost", "profit", "margin_pct", "transactions"],
    ...sorted.map((row) => [
      row.name,
      rawNumber(row.qty, 0),
      rawNumber(row.revenue, 0),
      rawNumber(row.vendorCost, 0),
      rawNumber(row.qrisCost, 0),
      rawNumber(row.cost, 0),
      rawNumber(row.profit, 0),
      rawNumber(row.margin),
      rawNumber(row.transactions, 0),
    ]),
  ];
  const csv = csvRows.map((row) => row.map(csvCell).join(",")).join("\r\n");
  const stamp = new Date().toLocaleString("sv-SE").replace(/[-: ]/g, "").slice(0, 12);
  downloadTextFile(`analytics-data-${stamp}.csv`, csv, "text/csv;charset=utf-8");
  renderAnalytics();
  showToast("Analytics data exported");
}

function renderHistory() {
  const rows = filteredHistory();
  renderHistoryStats(rows);
  renderHistoryCashiers();
  const body = $("#history-body");
  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="11" class="muted">No transactions found</td></tr>`;
    return;
  }
  body.innerHTML = rows.map((record) => `
    ${(() => {
      const method = displayPaymentMethod(record);
      const isCash = method === "Cash";
      return `
    <tr>
      <td class="mono">${escapeHtml(record.txn_id || "-")}</td>
      <td class="mono">${escapeHtml(record.qr_id || "-")}</td>
      <td>${escapeHtml(method)}</td>
      <td>${escapeHtml(record.customer_name || record.customer || "-")}</td>
      <td class="amount">${formatRp(record.amount)}</td>
      <td class="amount">${escapeHtml(discountText(record))}</td>
      <td class="amount">${isCash ? formatRp(record.cash_received) : "-"}</td>
      <td class="amount">${isCash ? formatRp(record.change) : "-"}</td>
      <td>${escapeHtml(record.cashier_name || "-")}</td>
      <td>${escapeHtml(record.updated_at_display || record.updated_at || "-")}</td>
      <td><button class="btn ghost" type="button" data-action="open-detail" data-txn="${escapeAttr(record.txn_id)}">View</button></td>
    </tr>
      `;
    })()}
  `).join("");
}

function renderHistoryCashiers() {
  const select = $("#history-cashier");
  if (!select) return;
  const current = select.value || state.historyCashier || "";
  const names = Array.from(new Set((state.history || []).map((record) => record.cashier_name).filter(Boolean))).sort();
  select.innerHTML = `<option value="">All</option>${names.map((name) => `<option value="${escapeAttr(name)}">${escapeHtml(name)}</option>`).join("")}`;
  select.value = current;
}

function renderHistoryStats(records = filteredHistory()) {
  const all = records;
  const gross = all.reduce((sum, record) => sum + historyDiscountBreakdown(record).gross, 0);
  const discount = all.reduce((sum, record) => sum + historyDiscountBreakdown(record).total, 0);
  const paidGross = all.reduce((sum, record) => sum + Number(record.amount || 0), 0);
  const cash = all.filter((record) => displayPaymentMethod(record) === "Cash").length;
  const qris = all.filter((record) => displayPaymentMethod(record) !== "Cash").length;
  const fee = all.reduce((sum, record) => sum + recordPaymentFee(record), 0);
  const net = paidGross - fee;
  const stats = [
    ["Transactions", all.length],
    ["Gross Revenue", formatRp(gross)],
    ["Discount", formatRp(discount)],
    ["QRIS Fee", formatRp(fee)],
    ["Net", formatRp(net)],
    ["Cash", cash],
    ["QRIS", qris],
  ];
  $("#history-stats").innerHTML = stats.map(([label, value]) => `
    <div class="stat-card"><span>${label}</span><strong>${value}</strong></div>
  `).join("");
}

function openDetail(txnId) {
  const record = state.history.find((item) => item.txn_id === txnId);
  if (!record) return;
  state.currentDetail = record;
  $("#payment-modal").hidden = true;
  $("#qr-modal").hidden = true;
  $("#dismiss-modal").hidden = true;
  $("#logout-modal").hidden = true;
  $("#detail-modal").hidden = false;
  $("#detail-title").textContent = record.txn_id || "Transaction";
  const method = displayPaymentMethod(record);
  const isCash = method === "Cash";
  $("#detail-summary").innerHTML = `
    <div><dt>Method</dt><dd>${escapeHtml(method)}</dd></div>
    <div><dt>Customer</dt><dd>${escapeHtml(record.customer_name || record.customer || "-")}</dd></div>
    <div><dt>Email</dt><dd>${escapeHtml(record.customer_email || "-")}</dd></div>
    <div><dt>Amount</dt><dd>${formatRp(record.amount)}</dd></div>
    ${isCash ? `<div><dt>Cash Received</dt><dd>${formatRp(record.cash_received)}</dd></div><div><dt>Change</dt><dd>${formatRp(record.change)}</dd></div>` : ""}
  `;
  $("#detail-items").innerHTML = (record.items || []).map((item) => {
    const gross = Number(item.gross || (item.unit_price || item.amount || item.price || 0) * (item.qty || 0));
    const subtotal = Number(item.subtotal || 0);
    const discount = Number(item.line_discount || Math.max(0, gross - subtotal));
    const price = discount && gross
      ? `<span class="price-strike">${formatRp(gross)}</span> ${item.free ? "FREE" : formatRp(subtotal)}`
      : `${item.qty} x ${formatRp(item.amount || item.price || item.unit_price || 0)}`;
    return `
      <div class="detail-item">
        <strong>${escapeHtml(item.item_name || item.name || "")}${item.free ? " [FREE]" : ""}</strong>
        <span>${price}</span>
        <span class="amount">${formatRp(subtotal)}</span>
      </div>
    `;
  }).join("");
  $("#modal-backdrop").hidden = false;
}

async function downloadPdf(kind) {
  if (!state.currentDetail?.txn_id) return;
  const path = kind === "merchant" ? "/api/merchant.pdf" : "/api/receipt.pdf";
  const label = kind === "merchant" ? "merchant invoice" : "receipt";
  await downloadFile(`${path}?txn_id=${encodeURIComponent(state.currentDetail.txn_id)}`, {
    filename: `${kind}-${state.currentDetail.txn_id}.pdf`,
    message: `Menyiapkan ${label}...`,
  });
  showToast(`${label} downloaded`);
}

async function exportHistoryPdf() {
  const rows = filteredHistory();
  await downloadFile("/api/history/export.pdf", {
    method: "POST",
    body: { txn_ids: rows.map((record) => record.txn_id).filter(Boolean) },
    filename: "invoice-history.pdf",
    message: "Menyiapkan history invoice...",
  });
  showToast("History invoice downloaded");
}

function renderSettings() {
  const s = state.settings || {};
  $("#set-shop-name").value = s.shop_name || "";
  $("#set-shop-address").value = s.shop_address || "";
  $("#set-shop-postcode").value = s.shop_postcode || "";
  $("#set-customer-prefix").value = s.default_customer_prefix || "Conlecta Customer";
  if ($("#set-admin-password")) $("#set-admin-password").value = "";
  if ($("#account-merchant-name")) $("#account-merchant-name").textContent = s.merchant_name || s.shop_name || "Conlecta";
  if ($("#account-merchant-id")) $("#account-merchant-id").textContent = s.merchant_id || "conlecta";
  $("#set-active-theme").value = deviceThemeId() || s.active_theme || DEFAULT_THEME;
  const marquee = s.marquee_msgs || [];
  $$(".marquee-input").forEach((input, index) => { input.value = marquee[index] || ""; });
  applyBrand();
  renderPaymentPreview();
  renderVideoAssets();
  renderEmailTemplate();
  renderAccountGate();
}

function collectSettings() {
  return {
    shop_name: $("#set-shop-name").value.trim(),
    shop_address: $("#set-shop-address").value.trim(),
    shop_postcode: $("#set-shop-postcode").value.trim(),
    default_customer_prefix: $("#set-customer-prefix").value.trim(),
    active_theme: $("#set-active-theme").value,
    admin_password: $("#set-admin-password")?.value || "",
    marquee_msgs: $$(".marquee-input").map((input) => input.value.trim()).filter(Boolean),
    payment_image_paths: state.settings.payment_image_paths || [],
    payment_image_path: state.settings.payment_image_path || "",
    video_playlist: state.settings.video_playlist || [],
  };
}

function renderPaymentPreview() {
  const preview = $("#payment-image-preview");
  if (!preview) return;
  const urls = state.settings.payment_image_urls || [];
  preview.innerHTML = urls.length
    ? urls.map((url) => `<span><img src="${escapeAttr(url)}" alt=""></span>`).join("")
    : `<em>No payment images</em>`;
}

function renderVideoAssets() {
  const list = $("#video-asset-list");
  if (!list) return;
  const selected = new Set((state.settings.video_playlist_urls || state.settings.video_playlist || []).map(String));
  const videos = state.assets?.videos || [];
  if (!videos.length) {
    list.innerHTML = `<div class="empty-state">Belum ada video standby</div>`;
    return;
  }
  list.innerHTML = videos.map((video) => {
    const active = selected.has(video.url) || selected.has(video.path);
    return `
      <div class="asset-row">
        <span>${escapeHtml(video.name)}</span>
        <small>${escapeHtml(video.size_mb || 0)} MB</small>
        <button class="btn ghost" type="button" data-action="toggle-video" data-url="${escapeAttr(video.url)}">${active ? "Added" : "Add"}</button>
        <button class="btn danger-soft" type="button" data-action="remove-video" data-url="${escapeAttr(video.url)}" data-path="${escapeAttr(video.path || "")}">Remove</button>
      </div>
    `;
  }).join("");
}

function toggleVideo(url) {
  const list = new Set((state.settings.video_playlist || state.settings.video_playlist_urls || []).map(String));
  if (list.has(url)) list.delete(url);
  else list.add(url);
  state.settings.video_playlist = Array.from(list);
  state.settings.video_playlist_urls = Array.from(list);
  renderVideoAssets();
  publishDisplayState();
}

async function uploadPaymentImages(files) {
  const selected = Array.from(files || []);
  if (!selected.length) return;
  const encoded = await Promise.all(selected.map((file) => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve({ filename: file.name, data_url: String(reader.result || "") });
    reader.onerror = reject;
    reader.readAsDataURL(file);
  })));
  const result = await api("/api/payment-images", { method: "POST", body: { files: encoded } });
  state.settings = result.settings;
  renderPaymentPreview();
  publishDisplayState();
  showToast("Payment images updated");
}

async function uploadVideo(file) {
  if (!file) return;
  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
  const result = await api("/api/video-upload", { method: "POST", body: { filename: file.name, data_url: dataUrl } });
  state.assets = result.assets || state.assets;
  if (result.settings) state.settings = result.settings;
  else {
    const playlist = new Set(state.settings.video_playlist || []);
    if (result.video?.path) playlist.add(result.video.path);
    else if (result.video?.url) playlist.add(result.video.url);
    state.settings.video_playlist = Array.from(playlist);
  }
  renderVideoAssets();
  publishDisplayState();
  showToast("Video uploaded");
}

async function removeVideo(target) {
  const result = await api("/api/video/remove", {
    method: "POST",
    body: {
      url: target.dataset.url || "",
      path: target.dataset.path || "",
    },
  });
  state.settings = result.settings || state.settings;
  state.assets = result.assets || state.assets;
  renderVideoAssets();
  publishDisplayState();
  showToast("Video removed");
}

function renderEmailTemplate() {
  const key = $("#email-template-key")?.value || "otp";
  const tpl = state.emailTemplates?.[key] || {};
  if (!$("#email-subject")) return;
  $("#email-subject").value = tpl.subject || "";
  $("#email-primary-color").value = tpl.primary_color || "";
  $("#email-primary-text").value = tpl.primary_text_color || "";
  $("#email-bg-color").value = tpl.bg_color || "";
  $("#email-secondary-color").value = tpl.secondary_color || "";
  $("#email-logo-path").value = tpl.logo_path || "";
  $("#email-logo-align").value = tpl.logo_align || "center";
  $("#email-html-override").value = tpl.html_override || "";
}

async function loadEmailTemplates() {
  const result = await api("/api/email-templates");
  state.emailTemplates = result.templates || {};
  renderEmailTemplate();
}

async function saveEmailTemplate() {
  const key = $("#email-template-key").value;
  const template = {
    subject: $("#email-subject").value,
    primary_color: $("#email-primary-color").value,
    primary_text_color: $("#email-primary-text").value,
    bg_color: $("#email-bg-color").value,
    secondary_color: $("#email-secondary-color").value,
    logo_path: $("#email-logo-path").value,
    logo_align: $("#email-logo-align").value,
    html_override: $("#email-html-override").value,
  };
  $("#email-template-status").textContent = "Saving template...";
  const result = await api("/api/email-template", { method: "POST", body: { key, template } });
  state.emailTemplates = result.templates || state.emailTemplates;
  $("#email-template-status").textContent = "Template saved.";
  showToast("Email template saved");
}

async function saveSettings() {
  const settings = collectSettings();
  const result = await api("/api/settings", {
    method: "POST",
    body: { settings, admin_password: settings.admin_password },
  });
  state.settings = result.settings;
  if ($("#set-admin-password")) $("#set-admin-password").value = "";
  applyBrand();
  publishDisplayState();
  showToast("Settings saved");
}

function setSettingsTab(tab) {
  $$(".tab").forEach((btn) => btn.classList.toggle("active", btn.dataset.settingsTab === tab));
  $$(".settings-section").forEach((section) => section.classList.toggle("active", section.id === `settings-${tab}`));
}

async function uploadBrandLogo(file) {
  if (!file) return;
  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
  const result = await api("/api/brand-logo", {
    method: "POST",
    body: { filename: file.name, data_url: dataUrl, admin_password: $("#set-admin-password")?.value || "" },
  });
  state.settings = result.settings;
  if ($("#set-admin-password")) $("#set-admin-password").value = "";
  applyBrand();
  publishDisplayState();
  showToast("Logo updated");
}

async function checkQrisEnv() {
  $("#qris-env-status").textContent = "Checking...";
  const result = await api("/api/qris/env");
  $("#qris-env-status").textContent = `${result.environment}: ${result.detail}`;
}

async function unlockAccountForm() {
  const adminPassword = $("#reg-admin-password").value;
  $("#register-status").textContent = "Memverifikasi admin...";
  await withLoading("Memverifikasi admin...", async () => {
    await api("/api/admin/verify", { method: "POST", body: { admin_password: adminPassword } });
  });
  state.accountAdminPassword = adminPassword;
  state.accountFormUnlocked = true;
  renderAccountGate();
  $("#register-status").textContent = "Form account baru sudah terbuka.";
}

function renderAccountGate() {
  const unlocked = Boolean(state.accountFormUnlocked);
  const adminInput = $("#reg-admin-password");
  const unlockButton = $("#account-gate [data-action='unlock-account-form']");
  $("#account-create-form").classList.toggle("hidden", !unlocked);
  $("#account-gate").classList.toggle("is-unlocked", unlocked);
  if (adminInput) adminInput.disabled = unlocked;
  if (unlockButton) {
    unlockButton.disabled = unlocked;
    unlockButton.textContent = unlocked ? "Unlocked" : "Unlock Form";
  }
}

async function registerAccount() {
  const password = $("#reg-password").value;
  const confirm = $("#reg-confirm").value;
  if (password !== confirm) {
    $("#register-status").textContent = "Password confirmation tidak sama.";
    return;
  }
  $("#register-status").textContent = "Menyimpan account...";
  const result = await api("/api/account/register", {
    method: "POST",
    body: {
      admin_password: state.accountAdminPassword || $("#reg-admin-password").value,
      name: $("#reg-name").value.trim(),
      email: $("#reg-email").value.trim(),
      password,
    },
  });
  $("#register-status").textContent = result.message || "Account berhasil dibuat.";
  $("#reg-name").value = "";
  $("#reg-email").value = "";
  $("#reg-password").value = "";
  $("#reg-confirm").value = "";
  $("#reg-admin-password").value = "";
  state.accountAdminPassword = "";
  state.accountFormUnlocked = false;
  renderAccountGate();
}

function renderLogs() {
  const search = ($("#log-search")?.value || "").trim().toLowerCase();
  const lines = (state.logs || []).filter((line) => {
    const matchesLevel = !state.logLevel || line.includes(`[${state.logLevel}]`) || line.includes(state.logLevel);
    const matchesSearch = !search || line.toLowerCase().includes(search);
    return matchesLevel && matchesSearch;
  });
  $("#log-viewer").textContent = lines.join("\n");
}

function systemMerchants() {
  return state.systemAdmin?.merchants || [];
}

function systemAccounts() {
  return state.systemAdmin?.accounts || [];
}

function systemAccountConflict(name, email, excludeId = "") {
  const wantedName = String(name || "").trim().toLowerCase();
  const wantedEmail = String(email || "").trim().toLowerCase();
  const exclude = String(excludeId || "");
  return systemAccounts().find((account) => {
    if (exclude && String(account.id || "") === exclude) return false;
    const existingNames = [
      String(account.name || "").trim().toLowerCase(),
      String(account.username || "").trim().toLowerCase(),
    ];
    return (wantedEmail && wantedEmail === String(account.email || "").trim().toLowerCase())
      || (wantedName && existingNames.includes(wantedName));
  });
}

function selectedSystemMerchant() {
  if (state.systemMerchantDraft) {
    return { id: "", merchant_id: "", name: "", logo_url: CONLECTA_IDENTITY_LOGO };
  }
  const merchants = systemMerchants();
  if (!state.selectedSystemMerchantId && merchants.length) {
    state.selectedSystemMerchantId = merchants[0].id || merchants[0].merchant_id || "";
  }
  return merchants.find((merchant) => String(merchant.id || merchant.merchant_id) === String(state.selectedSystemMerchantId))
    || merchants[0]
    || { id: "conlecta", name: "Conlecta", logo_url: CONLECTA_IDENTITY_LOGO };
}

function merchantLogoSrc(merchant) {
  return merchant?.logo_url || merchant?.brand_logo_url || merchant?.logo_data_url || CONLECTA_IDENTITY_LOGO;
}

function merchantOptions(selectedId) {
  return systemMerchants().map((merchant) => {
    const id = merchant.id || merchant.merchant_id || "";
    return `<option value="${escapeAttr(id)}" ${String(id) === String(selectedId) ? "selected" : ""}>${escapeHtml(merchant.name || id)}</option>`;
  }).join("");
}

function setSystemAdminTab(tab) {
  state.systemAdminTab = tab === "transactions" ? "transactions" : "merchants";
  $$(".system-admin-section").forEach((section) => {
    section.classList.toggle("active", section.id === `system-admin-${state.systemAdminTab}`);
  });
  $$(".system-admin-tabs .seg").forEach((button) => {
    button.classList.toggle("active", button.dataset.systemTab === state.systemAdminTab);
  });
  renderSystemAdmin();
}

function systemTxnMerchantOptions(selectedId) {
  const selected = selectedId || state.systemTxnMerchantId || selectedSystemMerchant()?.id || "";
  return systemMerchants().map((merchant) => {
    const id = merchant.id || merchant.merchant_id || "";
    return `<option value="${escapeAttr(id)}" ${String(id) === String(selected) ? "selected" : ""}>${escapeHtml(merchant.name || id)}</option>`;
  }).join("");
}

function systemTxnSearchText(record) {
  return [
    record.txn_id,
    record.qr_id,
    record.customer_name,
    record.customer,
    record.cashier_name,
    record.payment_method,
  ].map((value) => String(value || "").toLowerCase()).join(" ");
}

function filteredSystemTransactions() {
  const search = ($("#system-txn-search")?.value || "").trim().toLowerCase();
  return (state.systemTransactions || []).filter((record) => !search || systemTxnSearchText(record).includes(search));
}

function selectedSystemTransaction() {
  return (state.systemTransactions || []).find((record) => String(record.txn_id || "") === String(state.selectedSystemTxnId || ""));
}

function renderSystemTransactionList() {
  const list = $("#system-txn-list");
  if (!list) return;
  const rows = filteredSystemTransactions();
  if (!state.systemTxnMerchantId) {
    list.innerHTML = `<div class="empty-state">Pilih merchant dulu</div>`;
    return;
  }
  if (!rows.length) {
    list.innerHTML = `<div class="empty-state">Tidak ada transaksi</div>`;
    return;
  }
  list.innerHTML = rows.map((record) => `
    <button class="system-txn-card ${String(record.txn_id) === String(state.selectedSystemTxnId) ? "selected" : ""}" type="button" data-action="select-system-transaction" data-txn="${escapeAttr(record.txn_id || "")}">
      <span>
        <strong>${escapeHtml(record.txn_id || "-")}</strong>
        <small>${escapeHtml(record.customer_name || record.customer || "Customer")} - ${escapeHtml(record.payment_method || "-")}</small>
      </span>
      <b>${formatRp(record.amount || 0)}</b>
    </button>
  `).join("");
}

function systemTxnProductOptions(selectedName = "") {
  const names = Array.from(new Set((state.systemTxnProducts || []).map((item) => item.name).filter(Boolean))).sort();
  if (selectedName && !names.includes(selectedName)) names.unshift(selectedName);
  return names.map((name) => `<option value="${escapeAttr(name)}" ${name === selectedName ? "selected" : ""}>${escapeHtml(name)}</option>`).join("");
}

function systemTxnItemTemplate(item = {}, index = 0) {
  const name = item.item_name || item.name || "";
  return `
    <div class="system-txn-item" data-system-txn-item="${index}">
      <label class="field"><span>Item</span><select class="system-txn-input" data-txn-item-field="item_name">${systemTxnProductOptions(name)}</select></label>
      <label class="field"><span>Qty</span><input class="system-txn-input" data-txn-item-field="qty" type="number" min="1" step="1" value="${escapeAttr(item.qty || 1)}"></label>
      <label class="field"><span>Price</span><input class="system-txn-input money-field" data-txn-item-field="amount" inputmode="numeric" value="${escapeAttr(formatPlainNumber(item.amount || item.price || item.unit_price || 0))}"></label>
      <label class="field"><span>Capital</span><input class="system-txn-input money-field" data-txn-item-field="capital" inputmode="numeric" value="${escapeAttr(formatPlainNumber(item.capital || item.cost || 0))}"></label>
      <label class="field"><span>Disc %</span><input class="system-txn-input" data-txn-item-field="disc_pct" type="number" min="0" max="100" step="1" value="${escapeAttr(item.disc_pct || 0)}"></label>
      <label class="field"><span>Disc Rp</span><input class="system-txn-input money-field" data-txn-item-field="disc_fixed" inputmode="numeric" value="${escapeAttr(formatPlainNumber(item.disc_fixed || 0))}"></label>
      <label class="check-row inline-check"><input class="system-txn-input" data-txn-item-field="free" type="checkbox" ${item.free ? "checked" : ""}><span>Free</span></label>
      <button class="btn danger-soft" type="button" data-action="remove-system-txn-item">Remove</button>
    </div>
  `;
}

function renderSystemTransactionEditor() {
  const editor = $("#system-txn-editor");
  if (!editor) return;
  const record = selectedSystemTransaction();
  if (!record) {
    editor.innerHTML = `<div class="empty-state">Pilih transaksi untuk diedit.</div>`;
    return;
  }
  editor.innerHTML = `
    <div class="system-txn-form" data-system-txn-editor="${escapeAttr(record.txn_id || "")}">
      <div class="system-txn-summary">
        <div><span>Transaction</span><strong>${escapeHtml(record.txn_id || "-")}</strong></div>
        <div><span>Total</span><strong id="system-txn-total">${formatRp(record.amount || 0)}</strong></div>
      </div>
      <div class="system-txn-fields">
        <label class="field"><span>QR ID</span><input id="system-txn-qr" value="${escapeAttr(record.qr_id || "")}"></label>
        <label class="field"><span>Customer</span><input id="system-txn-customer" value="${escapeAttr(record.customer_name || record.customer || "")}"></label>
        <label class="field"><span>Email</span><input id="system-txn-email" type="email" value="${escapeAttr(record.customer_email || "")}"></label>
        <label class="field"><span>Cashier</span><input id="system-txn-cashier" value="${escapeAttr(record.cashier_name || "")}"></label>
        <label class="field"><span>Method</span><select id="system-txn-method">
          <option value="Cash" ${record.payment_method === "Cash" ? "selected" : ""}>Cash</option>
          <option value="QRIS" ${record.payment_method !== "Cash" ? "selected" : ""}>QRIS</option>
        </select></label>
        <label class="field"><span>Cash Received</span><input id="system-txn-cash-received" class="money-field" inputmode="numeric" value="${escapeAttr(formatPlainNumber(record.cash_received || 0))}"></label>
      </div>
      <div class="system-txn-items-head">
        <strong>Items</strong>
        <button class="btn ghost" type="button" data-action="add-system-txn-item">Add Item</button>
      </div>
      <div class="system-txn-items" id="system-txn-items">
        ${(record.items || []).map(systemTxnItemTemplate).join("")}
      </div>
      <div class="button-row">
        <button class="btn primary" type="button" data-action="save-system-transaction">Save Transaction</button>
      </div>
    </div>
  `;
  updateSystemTxnComputed();
}

function renderSystemAdminTransactions() {
  const merchantSelect = $("#system-txn-merchant");
  if (!merchantSelect) return;
  if (!state.systemTxnMerchantId) {
    state.systemTxnMerchantId = state.selectedSystemMerchantId || selectedSystemMerchant()?.id || "";
  }
  merchantSelect.innerHTML = systemTxnMerchantOptions(state.systemTxnMerchantId);
  merchantSelect.value = state.systemTxnMerchantId || merchantSelect.value || "";
  renderSystemTransactionList();
  renderSystemTransactionEditor();
}

function renderSystemAdmin() {
  const list = $("#system-merchant-list");
  if (!list) return;
  $$(".system-admin-section").forEach((section) => {
    section.classList.toggle("active", section.id === `system-admin-${state.systemAdminTab}`);
  });
  $$(".system-admin-tabs .seg").forEach((button) => {
    button.classList.toggle("active", button.dataset.systemTab === state.systemAdminTab);
  });
  if (!isSystemAdmin()) {
    list.innerHTML = `<div class="empty-state">System admin access required</div>`;
    return;
  }
  const merchants = systemMerchants();
  if (!state.systemMerchantDraft && !state.selectedSystemMerchantId && merchants.length) {
    state.selectedSystemMerchantId = merchants[0].id || merchants[0].merchant_id || "";
  }
  const selected = selectedSystemMerchant();
  list.innerHTML = merchants.length ? merchants.map((merchant) => {
    const id = merchant.id || merchant.merchant_id || "";
    return `
      <button class="system-merchant-card ${!state.systemMerchantDraft && String(id) === String(state.selectedSystemMerchantId) ? "selected" : ""}" type="button" data-action="select-system-merchant" data-id="${escapeAttr(id)}">
        <img src="${escapeAttr(merchantLogoSrc(merchant))}" alt="">
        <span>
          <strong>${escapeHtml(merchant.name || id)}</strong>
          <small>${escapeHtml(id)}</small>
        </span>
      </button>
    `;
  }).join("") : `<div class="empty-state">No merchant yet</div>`;

  $("#system-merchant-title").textContent = selected?.name || "New Merchant";
  $("#system-merchant-id").value = selected?.id || selected?.merchant_id || "";
  $("#system-merchant-name").value = selected?.name || "";
  $("#system-merchant-logo-preview").src = state.systemMerchantLogoDataUrl || merchantLogoSrc(selected);

  const selectedId = $("#system-merchant-id").value || state.selectedSystemMerchantId;
  const accounts = systemAccounts().filter((account) => String(account.merchant_id || "") === String(selectedId));
  $("#system-account-list").innerHTML = accounts.length ? accounts.map((account) => `
    <div class="system-account-row" data-system-account-id="${escapeAttr(account.id)}">
      <label class="field"><span>Name</span><input data-account-field="name" value="${escapeAttr(account.name || "")}"></label>
      <label class="field"><span>Email</span><input data-account-field="email" type="email" value="${escapeAttr(account.email || "")}"></label>
      <label class="field"><span>New Password</span><input data-account-field="password" type="password" placeholder="Keep current"></label>
      <label class="field"><span>Merchant</span><select data-account-field="merchant_id">${merchantOptions(account.merchant_id)}</select></label>
      <label class="check-row inline-check"><input data-account-field="admin_account" type="checkbox" ${account.admin_account ? "checked" : ""}><span>Merchant Admin</span></label>
      <button class="btn ghost" type="button" data-action="save-system-account">Save</button>
    </div>
  `).join("") : `<div class="empty-state">No account for this merchant</div>`;

  const version = state.systemAdmin?.version || state.version || {};
  $("#system-version-number").value = version.version || "";
  $("#system-version-title").value = version.title || "";
  $("#system-version-change").value = version.change || "";
  renderSystemAdminTransactions();
}

async function saveSystemMerchant() {
  const merchantId = $("#system-merchant-id").value.trim();
  const merchantName = $("#system-merchant-name").value.trim();
  if (!merchantId || !merchantName) {
    showToast("Merchant ID dan name wajib diisi", "error");
    return;
  }
  const result = await api("/api/system-admin/merchant/save", {
    method: "POST",
    body: {
      merchant_id: merchantId,
      merchant_name: merchantName,
      logo_data_url: state.systemMerchantLogoDataUrl,
      logo_filename: state.systemMerchantLogoFilename,
    },
  });
  state.systemAdmin = result.system_admin || state.systemAdmin;
  state.selectedSystemMerchantId = result.merchant?.id || merchantId;
  state.systemMerchantDraft = false;
  state.systemMerchantLogoDataUrl = "";
  state.systemMerchantLogoFilename = "";
  renderSystemAdmin();
  showToast("Merchant saved");
}

async function createSystemAccount() {
  const merchant = selectedSystemMerchant();
  const body = {
    merchant_id: $("#system-merchant-id").value.trim() || merchant.id || merchant.merchant_id,
    name: $("#system-account-name").value.trim(),
    email: $("#system-account-email").value.trim(),
    password: $("#system-account-password").value,
    admin_account: $("#system-account-admin").checked,
  };
  if (!body.name || !body.email || !body.password) {
    showToast("Name, email, dan password wajib diisi", "error");
    return;
  }
  if (systemAccountConflict(body.name, body.email)) {
    showToast("Username/account name atau email sudah dipakai", "error");
    return;
  }
  const result = await api("/api/system-admin/account/create", { method: "POST", body });
  state.systemAdmin = result.system_admin || state.systemAdmin;
  $("#system-account-name").value = "";
  $("#system-account-email").value = "";
  $("#system-account-password").value = "";
  $("#system-account-admin").checked = false;
  renderSystemAdmin();
  showToast(result.message || "Account created");
}

async function saveSystemAccount(target) {
  const row = target.closest("[data-system-account-id]");
  if (!row) return;
  const value = (field) => row.querySelector(`[data-account-field="${field}"]`);
  const nextName = value("name").value.trim();
  const nextEmail = value("email").value.trim();
  if (systemAccountConflict(nextName, nextEmail, row.dataset.systemAccountId)) {
    showToast("Username/account name atau email sudah dipakai", "error");
    return;
  }
  const result = await api("/api/system-admin/account/update", {
    method: "POST",
    body: {
      account_id: row.dataset.systemAccountId,
      name: nextName,
      email: nextEmail,
      password: value("password").value,
      merchant_id: value("merchant_id").value,
      admin_account: value("admin_account").checked,
    },
  });
  state.systemAdmin = result.system_admin || state.systemAdmin;
  renderSystemAdmin();
  showToast(result.message || "Account updated");
}

async function saveSystemVersion() {
  const result = await api("/api/system-admin/version/save", {
    method: "POST",
    body: {
      version: $("#system-version-number").value.trim(),
      title: $("#system-version-title").value.trim(),
      change: $("#system-version-change").value.trim(),
    },
  });
  state.systemAdmin = result.system_admin || state.systemAdmin;
  state.version = result.version || state.version;
  publishDisplayState();
  renderSystemAdmin();
  showToast("Version saved");
}

async function loadSystemTransactions() {
  const merchantId = $("#system-txn-merchant")?.value || state.systemTxnMerchantId || selectedSystemMerchant()?.id || "";
  if (!merchantId) {
    showToast("Pilih merchant dulu", "error");
    return;
  }
  state.systemTxnMerchantId = merchantId;
  const result = await api(`/api/system-admin/transactions?merchant_id=${encodeURIComponent(merchantId)}`, {
    loading: "Memuat transaksi merchant...",
  });
  state.systemTransactions = result.transactions || [];
  state.systemTxnProducts = result.products || [];
  state.selectedSystemTxnId = state.systemTransactions[0]?.txn_id || "";
  renderSystemAdminTransactions();
}

function selectSystemTransaction(txnId) {
  state.selectedSystemTxnId = txnId || "";
  renderSystemTransactionList();
  renderSystemTransactionEditor();
}

function addSystemTxnItem() {
  const product = state.systemTxnProducts[0] || {};
  const container = $("#system-txn-items");
  if (!container) return;
  const index = $$(".system-txn-item", container).length;
  container.insertAdjacentHTML("beforeend", systemTxnItemTemplate({
    item_name: product.name || "",
    qty: 1,
    amount: product.price || 0,
    capital: product.capital || 0,
  }, index));
  updateSystemTxnComputed();
}

function collectSystemTxnItems() {
  return $$(".system-txn-item").map((row) => {
    const value = (field) => row.querySelector(`[data-txn-item-field="${field}"]`);
    const itemName = value("item_name")?.value || "";
    const product = (state.systemTxnProducts || []).find((item) => item.name === itemName) || {};
    return {
      item_name: itemName,
      name: itemName,
      qty: parseMoney(value("qty")?.value || 0),
      amount: parseMoney(value("amount")?.value || product.price || 0),
      price: parseMoney(value("amount")?.value || product.price || 0),
      unit_price: parseMoney(value("amount")?.value || product.price || 0),
      capital: parseMoney(value("capital")?.value || product.capital || 0),
      disc_pct: parseMoney(value("disc_pct")?.value || 0),
      disc_fixed: parseMoney(value("disc_fixed")?.value || 0),
      free: Boolean(value("free")?.checked),
    };
  }).filter((item) => item.item_name && item.qty > 0);
}

function computeSystemTxnTotal(items = collectSystemTxnItems()) {
  return items.reduce((sum, item) => {
    const gross = parseMoney(item.amount) * parseMoney(item.qty);
    const discount = item.free ? gross : Math.min(gross, Math.round(gross * parseMoney(item.disc_pct) / 100) + parseMoney(item.disc_fixed));
    return sum + Math.max(0, gross - discount);
  }, 0);
}

function updateSystemTxnComputed() {
  const total = computeSystemTxnTotal();
  const target = $("#system-txn-total");
  if (target) target.textContent = formatRp(total);
}

function hydrateSystemTxnProduct(row) {
  const name = row.querySelector('[data-txn-item-field="item_name"]')?.value || "";
  const product = (state.systemTxnProducts || []).find((item) => item.name === name);
  if (!product) return;
  const price = row.querySelector('[data-txn-item-field="amount"]');
  const capital = row.querySelector('[data-txn-item-field="capital"]');
  if (price) price.value = formatPlainNumber(product.price || 0);
  if (capital) capital.value = formatPlainNumber(product.capital || 0);
}

async function saveSystemTransaction() {
  const record = selectedSystemTransaction();
  if (!record) {
    showToast("Pilih transaksi dulu", "error");
    return;
  }
  const items = collectSystemTxnItems();
  if (!items.length) {
    showToast("Minimal satu item transaksi", "error");
    return;
  }
  const result = await api("/api/system-admin/transaction/update", {
    method: "POST",
    loading: "Menyimpan perubahan transaksi...",
    body: {
      merchant_id: state.systemTxnMerchantId,
      txn_id: record.txn_id,
      qr_id: $("#system-txn-qr")?.value || "",
      customer_name: $("#system-txn-customer")?.value || "",
      customer_email: $("#system-txn-email")?.value || "",
      cashier_name: $("#system-txn-cashier")?.value || "",
      payment_method: $("#system-txn-method")?.value || "QRIS",
      cash_received: parseMoney($("#system-txn-cash-received")?.value || 0),
      items,
    },
  });
  state.systemTransactions = result.transactions || state.systemTransactions;
  state.systemTxnProducts = result.products || state.systemTxnProducts;
  state.selectedSystemTxnId = result.record?.txn_id || record.txn_id;
  if (state.systemTxnMerchantId === state.auth?.merchant_id) {
    state.history = result.transactions || state.history;
    state.products = result.products || state.products;
    renderStock();
    renderHistory();
  }
  renderSystemAdminTransactions();
  showToast("Transaction updated");
}

function exportLogs() {
  const blob = new Blob([$("#log-viewer").textContent || ""], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "conlecta_web_log.txt";
  a.click();
  URL.revokeObjectURL(url);
}

async function refreshStockData({ loading = false } = {}) {
  const [stockResult, vendorResult] = await Promise.all([
    api("/api/stock", { loading: loading ? "Loading item from Database..." : false }),
    api("/api/vendors", { loading: false }),
  ]);
  const nextProducts = Array.isArray(stockResult.products) ? stockResult.products : [];
  if (nextProducts.length || !state.products.length) {
    state.products = nextProducts;
  } else {
    showToast("Stock database kosong atau gagal dimuat, katalog lokal dipertahankan.", "error");
  }
  state.vendors = vendorResult.vendors || [];
  reconcileCartWithStock();
  renderStock();
  renderCatalog();
  renderCart();
  updateTotals();
  publishDisplayState();
}

async function refreshVendorData({ loading = false } = {}) {
  const result = await api("/api/vendors", { loading: loading ? "Memuat vendor dari database..." : false });
  state.vendors = result.vendors || [];
  renderVendorOptions();
  renderVendors();
}

async function refreshHistoryData({ loading = false } = {}) {
  const result = await api("/api/history", { loading: loading ? "Memuat history terbaru..." : false });
  state.history = result.history || [];
  renderHistory();
}

async function refreshVendorInvoiceContext({ loading = false } = {}) {
  const loadContext = async () => {
    await Promise.all([
      refreshStockData({ loading: false }),
      refreshVendorData({ loading: false }),
      refreshHistoryData({ loading: false }),
    ]);
    renderVendorOptions();
    renderVendorInvoice();
  };
  if (loading) return withLoading("Loading Vendor Data from Database...", loadContext);
  return loadContext();
}

async function refreshActiveStockTab({ loading = true } = {}) {
  if (state.stockTab === "vendors") {
    await refreshVendorData({ loading });
  } else if (state.stockTab === "invoice") {
    await refreshVendorInvoiceContext({ loading });
  } else {
    await refreshStockData({ loading });
  }
}

async function syncMenuData(name) {
  if (!state.auth || isSystemAdmin()) return;
  if (name === "cashier") {
    await refreshStockData({ loading: false });
  } else if (name === "stock") {
    await refreshActiveStockTab({ loading: true });
  } else if (name === "analytics") {
    await Promise.all([
      refreshStockData({ loading: false }),
      refreshHistoryData({ loading: false }),
    ]);
    renderAnalytics();
  } else if (name === "history") {
    await refreshHistoryData({ loading: false });
  } else if (name === "settings") {
    const result = await api("/api/assets", { loading: false });
    state.assets = result.assets || state.assets;
    if (result.settings) state.settings = result.settings;
    renderSettings();
    publishDisplayState();
  }
}

async function reloadBootstrap() {
  const epoch = authEpoch;
  const result = await api("/api/bootstrap");
  if (epoch !== authEpoch) return;
  state.settings = result.settings || {};
  if (Object.prototype.hasOwnProperty.call(result, "auth")) state.auth = result.auth || null;
  if (state.auth) {
    lastActivityTs = authActivityMs(state.auth) || lastActivityTs || Date.now();
  }
  const bootProducts = Array.isArray(result.products) ? result.products : [];
  if (bootProducts.length || !state.products.length) state.products = bootProducts;
  state.vendors = result.vendors || [];
  state.activeQr = sanitizeActiveQr(result.active_qr || null);
  reconcileCartWithStock();
  state.history = result.history || [];
  state.assets = result.assets || { videos: [], payment_icons: [] };
  state.version = result.version || state.version || {};
  state.systemAdmin = result.system_admin || state.systemAdmin || null;
  if (!Object.keys(state.emailTemplates || {}).length) {
    loadEmailTemplates().catch(() => null);
  }
  setDisplayEvent(result.display_event || null);
  state.session = result.session || { sales: 0, revenue: 0 };
  state.logs = result.logs || [];
  applyBrand();
  bootstrapDeviceTheme();
  renderAuth();
  if (!hasBootstrapped) applyRouteAfterBootstrap();
  hasBootstrapped = true;
  publishDisplayState();
  renderCatalog();
  renderCart();
  renderStock();
  renderAnalytics();
  renderHistory();
  renderVendorInvoice();
  renderSettings();
  renderLogs();
  renderSystemAdmin();
  updateSession();
  updateTotals();
  if (state.activeQr) {
    state.currentTxn = state.activeQr.txn_id || "";
    $("#txn-label").textContent = state.currentTxn || "TXN -";
    startQrPolling();
  } else {
    state.currentTxn = "";
    $("#txn-label").textContent = "TXN -";
    stopQrPolling();
  }
  updateQrActions();
  scheduleDailySessionReset();
}

async function handleAction(action, target) {
  const publicActions = new Set(["back-login", "resend-otp", "toggle-login-password", "forgot-pin"]);
  if (!state.auth && !publicActions.has(action)) return;
  try {
    if (action === "sync-data") {
      await withLoading("Sinkronisasi data...", reloadBootstrap);
      showToast("Data synced");
    } else if (action === "open-qr-display") {
      openQrDisplay();
    } else if (action === "logout") {
      showLogoutModal();
    } else if (action === "confirm-logout") {
      await logout();
    } else if (action === "back-login") {
      resetAuthForms({ clearCredentials: false });
    } else if (action === "resend-otp") {
      await resendOtp();
    } else if (action === "forgot-pin") {
      await forgotPin();
    } else if (action === "toggle-login-password") {
      toggleLoginPassword();
    } else if (action === "cart-inc") {
      changeCartQty(target.dataset.name, 1);
    } else if (action === "cart-dec") {
      changeCartQty(target.dataset.name, -1);
    } else if (action === "clear-cart") {
      clearCart();
    } else if (action === "primary-pay") {
      parseMoney($("#cash-received").value) > 0 ? await payCash() : await generateQR();
    } else if (action === "check-payment") {
      await checkPayment(true);
    } else if (action === "dismiss-qr") {
      await dismissQR();
    } else if (action === "select-stock") {
      selectStock(target.dataset.index ?? target.dataset.name);
    } else if (action === "toggle-free") {
      toggleFreeItem(target.dataset.name, target.checked);
    } else if (action === "delete-stock") {
      await deleteSelectedStock();
    } else if (action === "reload-stock") {
      await refreshActiveStockTab({ loading: true });
      showToast("Data refreshed");
    } else if (action === "add-vendor") {
      await addVendor();
    } else if (action === "delete-vendor") {
      await deleteVendor(target.dataset.id);
    } else if (action === "build-vendor-invoice") {
      await buildVendorInvoice();
    } else if (action === "export-vendor-pdf") {
      await exportVendorPdf();
    } else if (action === "apply-analytics-filter") {
      syncAnalyticsFiltersFromInputs();
      renderAnalytics();
    } else if (action === "export-analytics-data") {
      exportAnalyticsData();
    } else if (action === "reset-analytics-filter") {
      state.analyticsFrom = "";
      state.analyticsTo = "";
      state.analyticsMethod = "";
      state.analyticsMetric = "profit";
      state.analyticsLimit = 8;
      $("#analytics-from").value = "";
      $("#analytics-to").value = "";
      $("#analytics-method").value = "";
      $("#analytics-metric").value = "profit";
      $("#analytics-limit").value = "8";
      renderAnalytics();
    } else if (action === "reload-history") {
      await refreshHistoryData({ loading: true });
      showToast("History reloaded");
    } else if (action === "apply-history-filter") {
      state.historySearch = $("#history-search").value;
      state.historyQr = $("#history-qr").value;
      state.historyCustomer = $("#history-customer").value;
      state.historyMethod = $("#history-method").value;
      state.historyCashier = $("#history-cashier").value;
      state.historyFrom = $("#history-from").value;
      state.historyTo = $("#history-to").value;
      renderHistory();
    } else if (action === "reset-history-filter") {
      state.historySearch = "";
      state.historyQr = "";
      state.historyCustomer = "";
      state.historyMethod = "";
      state.historyCashier = "";
      state.historyFrom = "";
      state.historyTo = "";
      $("#history-search").value = "";
      $("#history-qr").value = "";
      $("#history-customer").value = "";
      $("#history-method").value = "";
      $("#history-cashier").value = "";
      $("#history-from").value = "";
      $("#history-to").value = "";
      renderHistory();
    } else if (action === "export-history-pdf") {
      await exportHistoryPdf();
    } else if (action === "open-detail") {
      openDetail(target.dataset.txn);
    } else if (action === "download-receipt") {
      await downloadPdf("receipt");
    } else if (action === "close-modal") {
      closeModal();
    } else if (action === "new-system-merchant") {
      state.selectedSystemMerchantId = "";
      state.systemMerchantDraft = true;
      state.systemMerchantLogoDataUrl = "";
      state.systemMerchantLogoFilename = "";
      renderSystemAdmin();
      $("#system-merchant-id")?.focus();
    } else if (action === "select-system-merchant") {
      state.selectedSystemMerchantId = target.dataset.id || "";
      state.systemMerchantDraft = false;
      state.systemMerchantLogoDataUrl = "";
      state.systemMerchantLogoFilename = "";
      renderSystemAdmin();
    } else if (action === "pick-system-merchant-logo") {
      $("#system-merchant-logo-file").click();
    } else if (action === "save-system-merchant") {
      await saveSystemMerchant();
    } else if (action === "create-system-account") {
      await createSystemAccount();
    } else if (action === "save-system-account") {
      await saveSystemAccount(target);
    } else if (action === "save-system-version") {
      await saveSystemVersion();
    } else if (action === "load-system-transactions") {
      await loadSystemTransactions();
    } else if (action === "select-system-transaction") {
      selectSystemTransaction(target.dataset.txn);
    } else if (action === "add-system-txn-item") {
      addSystemTxnItem();
    } else if (action === "remove-system-txn-item") {
      target.closest(".system-txn-item")?.remove();
      updateSystemTxnComputed();
    } else if (action === "save-system-transaction") {
      await saveSystemTransaction();
    } else if (action === "save-settings") {
      await saveSettings();
    } else if (action === "check-qris-env") {
      await checkQrisEnv();
    } else if (action === "unlock-account-form") {
      await unlockAccountForm();
    } else if (action === "register-account") {
      await registerAccount();
    } else if (action === "pick-brand-logo") {
      $("#brand-logo-file").click();
    } else if (action === "pick-payment-images") {
      $("#payment-image-files").click();
    } else if (action === "use-sample-payment-images") {
      const result = await api("/api/settings", {
        method: "POST",
        body: {
          settings: {
            ...collectSettings(),
            payment_image_paths: [],
            payment_image_path: "",
          },
        },
      });
      state.settings = result.settings;
      renderPaymentPreview();
      publishDisplayState();
    } else if (action === "clear-payment-images") {
      const result = await api("/api/settings", {
        method: "POST",
        body: {
          settings: {
            ...collectSettings(),
            payment_image_paths: [],
            payment_image_path: "",
          },
        },
      });
      state.settings = result.settings;
      renderPaymentPreview();
      publishDisplayState();
    } else if (action === "pick-video-upload") {
      $("#video-upload-file").click();
    } else if (action === "scan-assets") {
      const result = await api("/api/assets");
      state.assets = result.assets || state.assets;
      if (result.settings) state.settings = result.settings;
      renderVideoAssets();
      showToast("Assets scanned");
    } else if (action === "toggle-video") {
      toggleVideo(target.dataset.url);
    } else if (action === "remove-video") {
      await removeVideo(target);
    } else if (action === "load-email-template") {
      await loadEmailTemplates();
    } else if (action === "save-email-template") {
      await saveEmailTemplate();
    } else if (action === "unlock-log") {
      state.logAdminPassword = $("#log-admin-password").value;
      const result = await api("/api/logs/read", { method: "POST", body: { admin_password: state.logAdminPassword } });
      state.logs = result.logs || [];
      renderLogs();
      $("#log-admin-password").value = "";
      showToast("Log unlocked");
    } else if (action === "refresh-log") {
      if (!state.logAdminPassword) {
        showToast("Unlock log dulu dengan password account.", "error");
        return;
      }
      const result = await api("/api/logs/read", { method: "POST", body: { admin_password: state.logAdminPassword } });
      state.logs = result.logs || [];
      renderLogs();
    } else if (action === "export-log") {
      exportLogs();
    } else if (action === "clear-log") {
      if (!state.logAdminPassword) {
        showToast("Unlock log dulu dengan password account.", "error");
        return;
      }
      const result = await api("/api/logs/clear", { method: "POST", body: { admin_password: state.logAdminPassword } });
      state.logs = result.logs || [];
      renderLogs();
      showToast("Session log cleared");
    }
  } catch (err) {
    showToast(err.message, "error");
    const status = target?.closest?.(".settings-section")?.querySelector?.(".auth-status");
    if (status) status.textContent = err.message;
  }
}

function buildAmbientParticles() {
  const container = $("#particles-container");
  if (!container || container.dataset.ready === "true") return;
  const palette = ["var(--purple)", "var(--cyan)", "var(--gold)"];
  for (let i = 0; i < 64; i += 1) {
    const particle = document.createElement("div");
    particle.className = "particle ambient-particle";
    particle.style.left = `${Math.random() * 100}%`;
    particle.style.top = `${Math.random() * 100}%`;
    particle.style.color = palette[Math.floor(Math.random() * palette.length)];
    particle.style.background = "currentColor";
    particle.style.animationDuration = `${Math.random() * 8 + 5}s`;
    particle.style.animationDelay = `${Math.random() * 10}s`;
    particle.style.opacity = "0";
    container.appendChild(particle);
  }
  container.dataset.ready = "true";
}

function bindEvents() {
  $("#login-form").addEventListener("submit", (event) => loginSubmit(event).catch((err) => {
    $("#login-status").textContent = err.message;
  }));
  $("#otp-form").addEventListener("submit", (event) => otpSubmit(event).catch((err) => {
    $("#otp-status").textContent = err.message;
  }));
  $("#pin-form")?.addEventListener("submit", (event) => pinSubmit(event).catch((err) => {
    $("#pin-status").textContent = err.message;
  }));
  $("#pin-register-form")?.addEventListener("submit", (event) => registerPinSubmit(event).catch((err) => {
    $("#pin-register-status").textContent = err.message;
  }));
  $("#pin-register-continue")?.addEventListener("click", pinRegisterContinue);
  $("#pin-register-back")?.addEventListener("click", pinRegisterBack);
  bindOtpInputs();
  bindPinInputs();

  document.addEventListener("click", (event) => {
    const pageBtn = event.target.closest("[data-page]");
    if (pageBtn) {
      showPage(pageBtn.dataset.page);
      return;
    }
    const actionBtn = event.target.closest("[data-action]");
    if (actionBtn) {
      handleAction(actionBtn.dataset.action, actionBtn);
      return;
    }
    const filterBtn = event.target.closest("[data-filter]");
    if (filterBtn) {
      state.filter = filterBtn.dataset.filter;
      $$(".seg[data-filter]").forEach((btn) => btn.classList.toggle("active", btn === filterBtn));
      renderCatalog();
      return;
    }
    const settingsTab = event.target.closest("[data-settings-tab]");
    if (settingsTab) {
      setSettingsTab(settingsTab.dataset.settingsTab);
      return;
    }
    const systemTab = event.target.closest("[data-system-tab]");
    if (systemTab) {
      setSystemAdminTab(systemTab.dataset.systemTab);
      return;
    }
    const stockTab = event.target.closest("[data-stock-tab]");
    if (stockTab) {
      setStockTab(stockTab.dataset.stockTab).catch((err) => showToast(err.message, "error"));
      return;
    }
    const logBtn = event.target.closest("[data-log-level]");
    if (logBtn) {
      state.logLevel = logBtn.dataset.logLevel;
      $$(".seg[data-log-level]").forEach((btn) => btn.classList.toggle("active", btn === logBtn));
      renderLogs();
    }
  });

  $("#search-input").addEventListener("input", renderCatalog);
  $("#cash-received").addEventListener("input", (event) => {
    const amount = parseMoney(event.target.value);
    event.target.value = formatPlainNumber(amount);
    updateTotals();
  });
  $("#customer-name").addEventListener("input", queueDisplayPublish);
  $("#customer-email").addEventListener("input", queueDisplayPublish);
  $("#stock-price").addEventListener("input", (event) => {
    event.target.value = formatPlainNumber(parseMoney(event.target.value));
  });
  $("#stock-capital").addEventListener("input", (event) => {
    event.target.value = formatPlainNumber(parseMoney(event.target.value));
  });
  $("#stock-form").addEventListener("submit", saveStockForm);
  $("#stock-image").addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      state.stockImageB64 = result.includes(",") ? result.split(",")[1] : result;
      renderImagePreview();
    };
    reader.readAsDataURL(file);
  });
  document.addEventListener("input", (event) => {
    const discountInput = event.target.closest("[data-discount-field]");
    if (discountInput) {
      const field = discountInput.dataset.discountField;
      const value = parseMoney(discountInput.value);
      if (field === "disc_fixed") discountInput.value = value ? formatPlainNumber(value) : "";
      setLineDiscount(discountInput.dataset.name, field, value);
    }
    if (event.target.closest("#system-txn-search")) {
      renderSystemTransactionList();
    }
    const txnInput = event.target.closest(".system-txn-input, #system-txn-cash-received");
    if (txnInput) {
      if (txnInput.classList.contains("money-field")) {
        txnInput.value = formatPlainNumber(parseMoney(txnInput.value));
      }
      updateSystemTxnComputed();
    }
  });
  document.addEventListener("change", (event) => {
    if (event.target.closest("[data-discount-field]")) renderCart();
    if (event.target.closest("#system-txn-merchant")) {
      state.systemTxnMerchantId = event.target.value;
      state.systemTransactions = [];
      state.systemTxnProducts = [];
      state.selectedSystemTxnId = "";
      renderSystemAdminTransactions();
    }
    if (event.target.id === "set-active-theme") {
      syncThemeStorageContext();
      const next = event.target.value;
      if (window.ConlectaTheme && window.ConlectaTheme.isValid(next)) {
        window.ConlectaTheme.apply(next);
      } else {
        document.body.dataset.theme = next;
      }
    }
    const itemName = event.target.closest('[data-txn-item-field="item_name"]');
    if (itemName) {
      hydrateSystemTxnProduct(itemName.closest(".system-txn-item"));
      updateSystemTxnComputed();
    }
  });
  $("#brand-logo-file").addEventListener("change", (event) => {
    uploadBrandLogo(event.target.files?.[0]).catch((err) => showToast(err.message, "error"));
    event.target.value = "";
  });
  $("#system-merchant-logo-file")?.addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      state.systemMerchantLogoDataUrl = await readFileAsDataUrl(file);
      state.systemMerchantLogoFilename = file.name;
      renderSystemAdmin();
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      event.target.value = "";
    }
  });
  $("#payment-image-files").addEventListener("change", (event) => {
    uploadPaymentImages(event.target.files).catch((err) => showToast(err.message, "error"));
    event.target.value = "";
  });
  $("#video-upload-file").addEventListener("change", (event) => {
    uploadVideo(event.target.files?.[0]).catch((err) => showToast(err.message, "error"));
    event.target.value = "";
  });
  $("#email-template-key").addEventListener("change", renderEmailTemplate);
  $("#log-search").addEventListener("input", renderLogs);

  ["pointerdown", "keydown", "input", "touchstart"].forEach((eventName) => {
    document.addEventListener(eventName, noteActivity, { passive: true });
  });
  document.addEventListener("visibilitychange", () => {
    if (!state.auth) return;
    if (document.visibilityState === "visible") {
      reloadBootstrap().catch(() => null);
    } else {
      sendSessionHeartbeat(true);
    }
  });
  window.addEventListener("popstate", () => {
    if (state.auth) {
      const page = ROUTE_PAGE_MAP[routePath()] || defaultAuthedPage();
      showPage(page, { updateRoute: false });
    } else {
      const path = routePath();
      const routeStep = path === "/otp" ? "otp" : (path === "/pin" ? "pin" : (path === "/pin-register" ? "pin-register" : "login"));
      const step = routeStep !== "login" && state.pendingLogin?.account_id ? routeStep : "login";
      showLoginStep(step, { updateRoute: false });
    }
  });
  window.addEventListener("pagehide", () => {
    sendSessionHeartbeat(true);
    if (!$("#payment-modal")?.hidden) {
      stopCashierNoticeHeartbeat(state.activePaymentModalTxn, { notify: true, useBeacon: true });
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "F2") {
      event.preventDefault();
      showPage("cashier");
      $("#search-input").focus();
    }
    if (event.key === "F5") {
      event.preventDefault();
      handleAction("primary-pay", $("#pay-button"));
    }
    if (event.key === "Escape") {
      event.preventDefault();
      if (!$("#qr-modal").hidden && state.activeQr) dismissQR();
      else if (!$("#payment-modal").hidden) $("#payment-modal .ok-btn")?.focus();
      else if (!$("#modal-backdrop").hidden) closeModal();
      else if (state.activeQr) dismissQR();
    }
  });
}

async function init() {
  buildAmbientParticles();
  bindEvents();
  updateClock();
  setInterval(updateClock, 1000);
  await withLoading("Mengecek session user...", reloadBootstrap);
}

init().catch((err) => showToast(err.message, "error"));
