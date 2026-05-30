(function (global) {
  "use strict";

  const PRESETS = {
    brand: {
      aspect: 1,
      label: "Square brand logo",
      outputWidth: 512,
      outputHeight: 512,
    },
    catalog: {
      aspect: 190 / 92,
      label: "Catalog product image",
      outputWidth: 380,
      outputHeight: 184,
    },
    payment: {
      aspect: 16 / 9,
      label: "Display payment image",
      outputWidth: 640,
      outputHeight: 360,
    },
  };

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function fitCropBox(box, aspect) {
    const next = { ...box };
    if (next.w / next.h > aspect) {
      next.w = next.h * aspect;
    } else {
      next.h = next.w / aspect;
    }
    next.x = clamp(next.x, 0, 1 - next.w);
    next.y = clamp(next.y, 0, 1 - next.h);
    return next;
  }

  function initialCropBox(aspect) {
    const maxW = 0.92;
    let w = maxW;
    let h = w / aspect;
    if (h > 0.92) {
      h = 0.92;
      w = h * aspect;
    }
    return fitCropBox({
      x: (1 - w) / 2,
      y: (1 - h) / 2,
      w,
      h,
    }, aspect);
  }

  function applyBoxStyle(el, box) {
    if (!el || !box) return;
    el.style.left = `${box.x * 100}%`;
    el.style.top = `${box.y * 100}%`;
    el.style.width = `${box.w * 100}%`;
    el.style.height = `${box.h * 100}%`;
  }

  function bindFixedAspectCropBox(boxEl, getBox, setBox, aspect) {
    const minSize = 0.08;
    let mode = "move";
    let start = null;

    const onMove = (event) => {
      if (!start) return;
      const bounds = start.bounds;
      const dx = (event.clientX - start.x) / bounds.width;
      const dy = (event.clientY - start.y) / bounds.height;
      let next = { ...start.box };

      if (mode === "move") {
        next.x = clamp(start.box.x + dx, 0, 1 - next.w);
        next.y = clamp(start.box.y + dy, 0, 1 - next.h);
      } else {
        let anchorX = start.box.x;
        let anchorY = start.box.y;
        let oppositeX = start.box.x + start.box.w;
        let oppositeY = start.box.y + start.box.h;

        if (mode.includes("w")) anchorX = clamp(start.box.x + dx, 0, oppositeX - minSize);
        if (mode.includes("e")) oppositeX = clamp(start.box.x + start.box.w + dx, anchorX + minSize, 1);
        if (mode.includes("n")) anchorY = clamp(start.box.y + dy, 0, oppositeY - minSize);
        if (mode.includes("s")) oppositeY = clamp(start.box.y + start.box.h + dy, anchorY + minSize, 1);

        let w = oppositeX - anchorX;
        let h = w / aspect;
        if (h > oppositeY - anchorY) {
          h = oppositeY - anchorY;
          w = h * aspect;
        }
        if (mode.includes("w")) anchorX = oppositeX - w;
        if (mode.includes("n")) anchorY = oppositeY - h;
        if (anchorX < 0) {
          anchorX = 0;
          w = oppositeX - anchorX;
          h = w / aspect;
        }
        if (anchorY < 0) {
          anchorY = 0;
          h = oppositeY - anchorY;
          w = h * aspect;
        }
        if (anchorX + w > 1) {
          w = 1 - anchorX;
          h = w / aspect;
        }
        if (anchorY + h > 1) {
          h = 1 - anchorY;
          w = h * aspect;
        }
        next = fitCropBox({ x: anchorX, y: anchorY, w, h }, aspect);
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

  function cropToDataUrl(img, box, outW, outH) {
    const canvas = document.createElement("canvas");
    canvas.width = outW;
    canvas.height = outH;
    const ctx = canvas.getContext("2d");
    const sx = img.naturalWidth * box.x;
    const sy = img.naturalHeight * box.y;
    const sw = img.naturalWidth * box.w;
    const sh = img.naturalHeight * box.h;
    ctx.drawImage(img, sx, sy, sw, sh, 0, 0, outW, outH);
    return canvas.toDataURL("image/jpeg", 0.92);
  }

  function readFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  function open(options = {}) {
    const presetKey = options.preset || "brand";
    const preset = PRESETS[presetKey] || PRESETS.brand;
    const file = options.file;
    const title = options.title || preset.label;

    if (!file) {
      return Promise.reject(new Error("No image selected."));
    }

    return readFileAsDataUrl(file).then((src) => new Promise((resolve, reject) => {
      const overlay = document.createElement("div");
      overlay.className = "image-crop-overlay";
      overlay.innerHTML = `
        <div class="image-crop-modal panel" role="dialog" aria-modal="true" aria-label="${title}">
          <div class="panel-head">
            <div>
              <p class="eyebrow">Crop Image</p>
              <h2>${title}</h2>
            </div>
            <button class="btn ghost" type="button" data-crop-action="cancel">Cancel</button>
          </div>
          <p class="muted image-crop-note">Drag to move. Corner handles resize while keeping a fixed ${presetKey === "brand" ? "square" : "catalog"} ratio.</p>
          <div class="image-crop-stage">
            <img class="image-crop-image" src="" alt="">
            <div class="image-crop-box">
              <span data-handle="nw"></span><span data-handle="ne"></span>
              <span data-handle="sw"></span><span data-handle="se"></span>
            </div>
          </div>
          <div class="button-row">
            <button class="btn primary" type="button" data-crop-action="apply">Use Cropped Image</button>
          </div>
        </div>
      `;

      const cropBox = { ...initialCropBox(preset.aspect) };
      const img = overlay.querySelector(".image-crop-image");
      const boxEl = overlay.querySelector(".image-crop-box");
      img.src = src;

      const cleanup = () => overlay.remove();

      const finish = (result) => {
        cleanup();
        resolve(result);
      };

      const fail = (err) => {
        cleanup();
        reject(err);
      };

      img.addEventListener("load", () => {
        bindFixedAspectCropBox(
          boxEl,
          () => cropBox,
          (next) => Object.assign(cropBox, next),
          preset.aspect,
        );
        applyBoxStyle(boxEl, cropBox);
      }, { once: true });

      img.addEventListener("error", () => fail(new Error("Could not load image.")), { once: true });

      overlay.addEventListener("click", (event) => {
        const action = event.target.closest("[data-crop-action]");
        if (!action) return;
        if (action.dataset.cropAction === "cancel") {
          fail(new Error("Crop cancelled."));
          return;
        }
        if (action.dataset.cropAction === "apply") {
          if (!img.naturalWidth) {
            fail(new Error("Image not ready yet."));
            return;
          }
          const dataUrl = cropToDataUrl(img, cropBox, preset.outputWidth, preset.outputHeight);
          finish({
            dataUrl,
            filename: file.name || "image.jpg",
            preset: presetKey,
          });
        }
      });

      document.body.appendChild(overlay);
      applyBoxStyle(boxEl, cropBox);
    }));
  }

  global.ConlectaImageCrop = {
    PRESETS,
    open,
  };
})(window);
