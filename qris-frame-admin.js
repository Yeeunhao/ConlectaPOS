(function () {
  "use strict";

  const QR = window.ConlectaQrisFrame;
  if (!QR) return;

  function cloneLayout(layout) {
    return QR.normalizeLayout(JSON.parse(JSON.stringify(layout || QR.DEFAULT_LAYOUT)));
  }

  function editorState() {
    if (!window.state.qrisFrameDraft) window.state.qrisFrameDraft = cloneLayout(QR.DEFAULT_LAYOUT);
    if (!window.state.qrisFrameAdmin) {
      window.state.qrisFrameAdmin = { frames: [], config: { default: cloneLayout(), merchants: {} }, merchants: [] };
    }
    if (!window.state.qrisFrameEditorStep) window.state.qrisFrameEditorStep = "crop";
    if (!window.state.qrisFrameScope) window.state.qrisFrameScope = "default";
    if (!window.state.qrisFrameMerchantIds) window.state.qrisFrameMerchantIds = [];
    return window.state;
  }

  function applyBoxStyle(el, box) {
    if (!el || !box) return;
    el.style.left = `${box.x * 100}%`;
    el.style.top = `${box.y * 100}%`;
    el.style.width = `${box.w * 100}%`;
    el.style.height = `${box.h * 100}%`;
  }

  function bindDragBox(boxEl, getBox, setBox, minSize = 0.05) {
    if (!boxEl || boxEl.dataset.dragBound === "1") return;
    boxEl.dataset.dragBound = "1";
    let mode = "move";
    let start = null;

    const onMove = (event) => {
      if (!start) return;
      const bounds = start.bounds;
      const dx = (event.clientX - start.x) / bounds.width;
      const dy = (event.clientY - start.y) / bounds.height;
      let next = { ...start.box };
      if (mode === "move") {
        next.x = Math.max(0, Math.min(1 - next.w, start.box.x + dx));
        next.y = Math.max(0, Math.min(1 - next.h, start.box.y + dy));
      } else {
        if (mode.includes("e")) next.w = Math.max(minSize, Math.min(1 - start.box.x, start.box.w + dx));
        if (mode.includes("s")) next.h = Math.max(minSize, Math.min(1 - start.box.y, start.box.h + dy));
        if (mode.includes("w")) {
          const right = start.box.x + start.box.w;
          next.x = Math.max(0, Math.min(right - minSize, start.box.x + dx));
          next.w = Math.max(minSize, right - next.x);
        }
        if (mode.includes("n")) {
          const bottom = start.box.y + start.box.h;
          next.y = Math.max(0, Math.min(bottom - minSize, start.box.y + dy));
          next.h = Math.max(minSize, bottom - next.y);
        }
      }
      setBox(next);
      applyBoxStyle(boxEl, next);
    };

    const onUp = () => {
      start = null;
      window.removeEventListener("pointermove", onMove);
    };

    const begin = (event, nextMode) => {
      event.preventDefault();
      mode = nextMode;
      start = {
        x: event.clientX,
        y: event.clientY,
        box: { ...getBox() },
        bounds: boxEl.parentElement.getBoundingClientRect(),
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp, { once: true });
    };

    boxEl.addEventListener("pointerdown", (event) => {
      if (event.target.closest("[data-handle]")) return;
      begin(event, "move");
    });
    boxEl.querySelectorAll("[data-handle]").forEach((handle) => {
      handle.addEventListener("pointerdown", (event) => {
        event.stopPropagation();
        begin(event, handle.dataset.handle || "se");
      });
    });
  }

  function renderCropStage(draft, stage) {
    stage.innerHTML = `
      <div class="qris-frame-crop-stage">
        <img class="qris-frame-crop-image" src="${escapeAttr(draft.frame_url || draft.frame_src)}" alt="">
        <div class="qris-frame-crop-box" data-qris-crop-box></div>
      </div>
    `;
    const img = stage.querySelector(".qris-frame-crop-image");
    const box = stage.querySelector("[data-qris-crop-box]");
    box.innerHTML = `<span data-handle="nw"></span><span data-handle="ne"></span><span data-handle="sw"></span><span data-handle="se"></span>`;
    applyBoxStyle(box, draft.crop);
    img.addEventListener("load", () => {
      window.state.qrisFrameDraft.source_width = img.naturalWidth || draft.source_width;
      window.state.qrisFrameDraft.source_height = img.naturalHeight || draft.source_height;
    }, { once: true });
    bindDragBox(box, () => window.state.qrisFrameDraft.crop, (next) => {
      window.state.qrisFrameDraft.crop = next;
    });
  }

  function renderLayoutStage(draft, stage) {
    stage.innerHTML = `
      <div class="qris-frame-layout-stage">
        <div class="qris-frame-wrap qris-frame-editor-preview">
          <div class="qris-frame-viewport">
            <img class="qris-frame-bg" src="${escapeAttr(draft.frame_url || draft.frame_src)}" alt="">
          </div>
          <div class="qris-frame-slot">
            <div class="qris-frame-qr-guide">QR area</div>
          </div>
          <div class="qris-frame-qr-overlay" data-qris-qr-box>QR<span data-handle="nw"></span><span data-handle="ne"></span><span data-handle="sw"></span><span data-handle="se"></span></div>
        </div>
      </div>
    `;
    const wrap = stage.querySelector(".qris-frame-wrap");
    const overlay = stage.querySelector("[data-qris-qr-box]");
    QR.applyQrisFrame(wrap, draft);
    applyBoxStyle(overlay, draft.qr);
    bindDragBox(overlay, () => window.state.qrisFrameDraft.qr, (next) => {
      window.state.qrisFrameDraft.qr = next;
      QR.applyQrisFrame(wrap, window.state.qrisFrameDraft);
    });
  }

  function renderEditorStage() {
    const st = editorState();
    const stage = document.querySelector("#qris-frame-editor-stage");
    if (!stage) return;
    const draft = cloneLayout(st.qrisFrameDraft);
    if (st.qrisFrameEditorStep === "layout") renderLayoutStage(draft, stage);
    else renderCropStage(draft, stage);
  }

  function renderGallery() {
    const st = editorState();
    const gallery = document.querySelector("#qris-frame-gallery");
    if (!gallery) return;
    const draft = st.qrisFrameDraft;
    gallery.innerHTML = (st.qrisFrameAdmin.frames || []).map((frame) => `
      <button type="button" class="qris-frame-thumb ${draft.frame_src === frame.src ? "selected" : ""}" data-action="pick-qris-frame" data-src="${escapeAttr(frame.src)}" data-url="${escapeAttr(frame.url || frame.src)}">
        <img src="${escapeAttr(frame.url || frame.src)}" alt="${escapeAttr(frame.name)}">
        <span>${escapeHtml(frame.name)}</span>
      </button>
    `).join("") || `<div class="empty-state">No PNG frames in assets/qris-frame</div>`;
  }

  function renderMerchantPicks() {
    const st = editorState();
    const host = document.querySelector("#qris-frame-merchant-picks");
    if (!host) return;
    host.hidden = st.qrisFrameScope !== "merchants";
    host.innerHTML = (st.qrisFrameAdmin.merchants || []).map((merchant) => {
      const id = merchant.id || merchant.merchant_id || "";
      const checked = st.qrisFrameMerchantIds.includes(id) ? "checked" : "";
      return `
        <label class="check-row inline-check">
          <input type="checkbox" data-qris-merchant-id="${escapeAttr(id)}" ${checked}>
          <span>${escapeHtml(merchant.name || id)} <small>(${escapeHtml(id)})</small></span>
        </label>
      `;
    }).join("") || `<div class="empty-state">No merchants yet</div>`;
  }

  window.renderSystemQrisFrame = function renderSystemQrisFrame() {
    editorState();
    renderGallery();
    renderEditorStage();
    renderMerchantPicks();
    document.querySelectorAll("[data-qris-step]").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.qrisStep === window.state.qrisFrameEditorStep);
    });
    document.querySelectorAll("[name=qris-frame-scope]").forEach((input) => {
      input.checked = input.value === window.state.qrisFrameScope;
    });
  };

  window.loadQrisFrameAdmin = async function loadQrisFrameAdmin() {
    const result = await window.api("/api/system-admin/qris-frame");
    window.state.qrisFrameAdmin = {
      frames: result.frames || [],
      config: result.config || { default: cloneLayout(), merchants: {} },
      merchants: result.merchants || [],
    };
    window.state.qrisFrameDraft = cloneLayout(result.config?.default || QR.DEFAULT_LAYOUT);
    window.renderSystemQrisFrame();
  };

  window.saveQrisFrameConfig = async function saveQrisFrameConfig() {
    const st = editorState();
    const layout = cloneLayout(st.qrisFrameDraft);
    const scope = st.qrisFrameScope === "merchants" ? "merchants" : "default";
    const merchantIds = scope === "merchants" ? [...st.qrisFrameMerchantIds] : [];
    if (scope === "merchants" && !merchantIds.length) {
      window.showToast("Pilih minimal satu merchant", "error");
      return;
    }
    const result = await window.api("/api/system-admin/qris-frame/save", {
      method: "POST",
      body: { scope, merchant_ids: merchantIds, layout },
    });
    window.state.qrisFrameAdmin.config = result.config || window.state.qrisFrameAdmin.config;
    window.showToast(scope === "default" ? "Default QR Frame saved" : "QR Frame saved for selected merchants", "success");
    window.renderSystemQrisFrame();
  };

  window.pickQrisFrameAsset = function pickQrisFrameAsset(src, url) {
    const st = editorState();
    st.qrisFrameDraft.frame_src = src;
    st.qrisFrameDraft.frame_url = url || src;
    st.qrisFrameDraft.crop = { x: 0, y: 0, w: 1, h: 1 };
    window.renderSystemQrisFrame();
  };

  document.addEventListener("click", (event) => {
    const pick = event.target.closest("[data-action='pick-qris-frame']");
    if (pick) {
      window.pickQrisFrameAsset(pick.dataset.src, pick.dataset.url);
      return;
    }
    const step = event.target.closest("[data-qris-step]");
    if (step) {
      window.state.qrisFrameEditorStep = step.dataset.qrisStep === "layout" ? "layout" : "crop";
      window.renderSystemQrisFrame();
      return;
    }
    if (event.target.closest("[data-action='save-qris-frame']")) {
      window.saveQrisFrameConfig().catch((err) => window.showToast(err.message, "error"));
    }
  });

  document.addEventListener("change", (event) => {
    if (event.target.matches("[name=qris-frame-scope]")) {
      window.state.qrisFrameScope = event.target.value === "merchants" ? "merchants" : "default";
      renderMerchantPicks();
    }
    if (event.target.matches("[data-qris-merchant-id]")) {
      const id = event.target.dataset.qrisMerchantId;
      const list = new Set(window.state.qrisFrameMerchantIds || []);
      if (event.target.checked) list.add(id);
      else list.delete(id);
      window.state.qrisFrameMerchantIds = Array.from(list);
    }
  });
})();
