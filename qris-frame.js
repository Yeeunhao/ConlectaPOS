(function (global) {
  "use strict";

  const FALLBACK_FRAME_SRC = "/assets/qris-frame/SingapayConlectaQrisFrame.png";

  const DEFAULT_LAYOUT = {
    frame_src: FALLBACK_FRAME_SRC,
    source_width: 1086,
    source_height: 1448,
    crop: { x: 0, y: 0, w: 1, h: 1 },
    qr: { x: 0.18, y: 0.28, w: 0.64, h: 0.32 },
  };

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function normalizeBox(raw, fallback) {
    const base = { ...(fallback || {}) };
    const next = { ...(raw || {}) };
    return {
      x: clamp(Number(next.x ?? base.x ?? 0), 0, 1),
      y: clamp(Number(next.y ?? base.y ?? 0), 0, 1),
      w: clamp(Number(next.w ?? base.w ?? 1), 0.05, 1),
      h: clamp(Number(next.h ?? base.h ?? 1), 0.05, 1),
    };
  }

  function normalizeLayout(raw) {
    const input = raw || {};
    const crop = normalizeBox(input.crop, DEFAULT_LAYOUT.crop);
    if (crop.x + crop.w > 1) crop.w = 1 - crop.x;
    if (crop.y + crop.h > 1) crop.h = 1 - crop.y;
    const qr = normalizeBox(input.qr, DEFAULT_LAYOUT.qr);
    if (qr.x + qr.w > 1) qr.w = 1 - qr.x;
    if (qr.y + qr.h > 1) qr.h = 1 - qr.y;
    return {
      frame_src: String(input.frame_src || input.frame_url || DEFAULT_LAYOUT.frame_src).split("?")[0],
      frame_url: String(input.frame_url || input.frame_src || DEFAULT_LAYOUT.frame_src),
      source_width: Math.max(1, Number(input.source_width || DEFAULT_LAYOUT.source_width)),
      source_height: Math.max(1, Number(input.source_height || DEFAULT_LAYOUT.source_height)),
      crop,
      qr,
    };
  }

  function layoutFromSettings(settings) {
    if (!settings?.qris_frame) return normalizeLayout(DEFAULT_LAYOUT);
    return normalizeLayout(settings.qris_frame);
  }

  function frameUrl(layout) {
    const next = normalizeLayout(layout);
    return next.frame_url || next.frame_src || FALLBACK_FRAME_SRC;
  }

  function viewportAspectRatio(layout) {
    const next = normalizeLayout(layout);
    const crop = next.crop;
    const width = Math.max(1, next.source_width * crop.w);
    const height = Math.max(1, next.source_height * crop.h);
    return `${width} / ${height}`;
  }

  function cropImageStyles(layout) {
    const next = normalizeLayout(layout);
    const crop = next.crop;
    const w = Math.max(0.05, crop.w);
    const h = Math.max(0.05, crop.h);
    return {
      width: `${100 / w}%`,
      height: `${100 / h}%`,
      left: `${(-crop.x / w) * 100}%`,
      top: `${(-crop.y / h) * 100}%`,
    };
  }

  function qrSlotStyles(layout) {
    const next = normalizeLayout(layout);
    const qr = next.qr;
    return {
      left: `${qr.x * 100}%`,
      top: `${qr.y * 100}%`,
      width: `${qr.w * 100}%`,
      height: `${qr.h * 100}%`,
      right: "auto",
      bottom: "auto",
    };
  }

  function applyQrisFrame(root, layout) {
    if (!root) return normalizeLayout(layout);
    const next = normalizeLayout(layout);
    const wrap = root.classList?.contains("qris-frame-wrap") ? root : root.querySelector(".qris-frame-wrap");
    if (!wrap) return next;

    const sig = JSON.stringify({
      frame_src: next.frame_src,
      crop: next.crop,
      qr: next.qr,
      sw: next.source_width,
      sh: next.source_height,
    });
    if (wrap.dataset.qrisLayoutSig === sig) return next;
    wrap.dataset.qrisLayoutSig = sig;

    wrap.style.aspectRatio = viewportAspectRatio(next);

    const viewport = wrap.querySelector(".qris-frame-viewport") || wrap;
    const bg = wrap.querySelector(".qris-frame-bg");
    const slot = wrap.querySelector(".qris-frame-slot");
    const url = frameUrl(next);

    if (bg) {
      if (bg.dataset.frameSrc !== url) {
        bg.dataset.frameSrc = url;
        bg.src = url;
      }
      Object.assign(bg.style, {
        position: "absolute",
        display: "block",
        objectFit: "fill",
        maxWidth: "none",
        ...cropImageStyles(next),
      });
    }

    if (slot) {
      Object.assign(slot.style, qrSlotStyles(next));
    }

    if (viewport !== wrap) {
      viewport.style.position = "absolute";
      viewport.style.inset = "0";
      viewport.style.overflow = "hidden";
      viewport.style.zIndex = "1";
    }

    return next;
  }

  global.ConlectaQrisFrame = {
    DEFAULT_LAYOUT,
    FALLBACK_FRAME_SRC,
    normalizeLayout,
    layoutFromSettings,
    frameUrl,
    viewportAspectRatio,
    cropImageStyles,
    qrSlotStyles,
    applyQrisFrame,
  };
})(window);
