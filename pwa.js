(function () {
  let installPrompt = null;

  function isStandalone() {
    return window.matchMedia("(display-mode: standalone)").matches
      || window.matchMedia("(display-mode: fullscreen)").matches
      || window.navigator.standalone === true;
  }

  function isMobilePlatform() {
    const ua = navigator.userAgent || "";
    if (/Android/i.test(ua)) return true;
    if (/iPhone|iPod/i.test(ua)) return true;
    if (/iPad/i.test(ua)) return true;
    if (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1) return true;
    return false;
  }

  function isIos() {
    const ua = navigator.userAgent || "";
    return /iPhone|iPad|iPod/i.test(ua)
      || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  }

  function isQrDisplayPage() {
    return /qr-display/i.test(window.location.pathname);
  }

  function isCashierPage() {
    return !isQrDisplayPage();
  }

  function canUseQrDisplay() {
    return !isMobilePlatform();
  }

  function canUseServiceWorker() {
    return "serviceWorker" in navigator;
  }

  async function registerServiceWorker() {
    if (!canUseServiceWorker()) return false;
    try {
      await navigator.serviceWorker.register("/service-worker.js", { scope: "/" });
      return true;
    } catch {
      return false;
    }
  }

  function bindInstallPrompt() {
    window.addEventListener("beforeinstallprompt", (event) => {
      if (!isCashierPage()) return;
      event.preventDefault();
      installPrompt = event;
      document.dispatchEvent(new CustomEvent("conlecta:pwa-ready"));
    });

    window.addEventListener("appinstalled", () => {
      installPrompt = null;
      document.dispatchEvent(new CustomEvent("conlecta:pwa-installed"));
    });
  }

  function installAvailable() {
    return Boolean(installPrompt);
  }

  function installStatusText() {
    if (isStandalone()) {
      return "Installed. QR Display opens in a separate window on desktop or Mac.";
    }
    if (installAvailable()) return "Ready to install on this device.";
    if (isIos()) return "Safari: tap Share, then Add to Home Screen.";
    return "Chrome or Edge: use Install in the address bar or browser menu.";
  }

  async function promptInstall() {
    if (installPrompt) {
      await installPrompt.prompt();
      const choice = await installPrompt.userChoice;
      installPrompt = null;
      return { ok: choice.outcome === "accepted", outcome: choice.outcome };
    }
    if (isIos() && !isStandalone()) {
      return { ok: false, reason: "ios-manual" };
    }
    return { ok: false, reason: "unavailable" };
  }

  function openQrDisplayWindow(deviceId) {
    if (!canUseQrDisplay()) return null;
    const query = new URLSearchParams();
    if (deviceId) query.set("device", deviceId);
    const url = `${window.location.origin}/qr-display.html${query.toString() ? `?${query}` : ""}`;
    const windowName = `conlecta_qr_display_${deviceId || "default"}`;
    return window.open(url, windowName, "noopener,noreferrer");
  }

  function applyMobileQrRules(root) {
    if (canUseQrDisplay()) return;
    const scope = root || document;
    scope.body?.classList?.add("mobile-no-qr-display");
    scope.querySelectorAll('[data-action="open-qr-display"]').forEach((el) => {
      el.hidden = true;
      el.disabled = true;
    });
    scope.querySelectorAll(".qr-display-only").forEach((el) => {
      el.hidden = true;
    });
  }

  function mobileQrBlockMessage() {
    return "QR Display is not available on Android or iOS. Use Conlecta on desktop or Mac for cashier + customer screen setup.";
  }

  async function init() {
    bindInstallPrompt();
    await registerServiceWorker();
    applyMobileQrRules(document);
    document.dispatchEvent(new CustomEvent("conlecta:pwa-ready"));
  }

  window.ConlectaPwa = {
    init,
    isStandalone,
    isMobilePlatform,
    isIos,
    isQrDisplayPage,
    isCashierPage,
    canUseQrDisplay,
    canUseServiceWorker,
    installAvailable,
    installStatusText,
    promptInstall,
    openQrDisplayWindow,
    applyMobileQrRules,
    mobileQrBlockMessage,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => { init().catch(() => null); });
  } else {
    init().catch(() => null);
  }
}());
