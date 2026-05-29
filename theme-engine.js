/* ============================================================
   Conlecta Theme Engine
   ------------------------------------------------------------
   - Canvas-driven animated background (crystals, pearls, sparkles)
   - Theme switcher UI (floating dropdown)
   - Syncs with document.body.dataset.theme + localStorage
   - Listens for tp:themechange and external theme updates
   - Performance-optimized: FPS throttling, reduced-motion support,
     visibility-based pause, adaptive particle reduction
   ============================================================ */
(function (global) {
  "use strict";

  const STORAGE_KEY = "conlecta:theme";
  let storageKey = STORAGE_KEY;
  const PERF_MODE_KEY = "conlecta:perfMode";
  const DEFAULT_THEME = "crystal_bloom";
  const TARGET_FRAME_MS = 1000 / 30;
  const FPS_SAMPLE_INTERVAL = 1000;
  const FPS_LOW_THRESHOLD = 20;

  const THEMES = [
    { id: "crystal_bloom",  label: "Crystal Bloom" },
    { id: "pearl_mist",     label: "Pearl Mist" },
    { id: "aurora_glass",   label: "Aurora Glass" },
    { id: "midnight_velvet",label: "Midnight Velvet" },
    { id: "deep_space",     label: "Deep Space" },
    { id: "warm_terminal",  label: "Warm Terminal" },
    { id: "midnight_teal",  label: "Midnight Teal" },
  ];

  /* ------------------------------------------------------------
     Palette per theme used by canvas drawing
     ------------------------------------------------------------ */
  const PALETTES = {
    crystal_bloom: {
      sky: ["#0a0820", "#18113f", "#281a55", "#3a2270"],
      iris: ["#c4b5fd", "#bff5ff", "#ffd5e8", "#fff6d8"],
      pearl: "#fff6f1",
      sparkle: "#f7eaff",
      aurora: ["rgba(177,150,255,0.18)", "rgba(155,231,255,0.15)", "rgba(255,213,232,0.16)"],
      mode: "screen",
      light: false,
    },
    pearl_mist: {
      sky: ["#f6f1ff", "#ebe4ff", "#e0d4ff", "#ffd5e6"],
      iris: ["#7c5cff", "#5cb8d8", "#d8527a", "#d8a25c"],
      pearl: "#ffffff",
      sparkle: "#ffffff",
      aurora: ["rgba(124,92,255,0.18)", "rgba(92,184,216,0.18)", "rgba(216,82,122,0.16)"],
      mode: "multiply",
      light: true,
    },
    aurora_glass: {
      sky: ["#04111a", "#06262e", "#0a3a3f", "#0d4d4f"],
      iris: ["#6ee7d2", "#9fe8b2", "#fef9c3", "#a5f3fc"],
      pearl: "#e8fff5",
      sparkle: "#d9f99d",
      aurora: ["rgba(110,231,210,0.16)", "rgba(159,232,178,0.14)", "rgba(250,204,21,0.12)"],
      mode: "screen",
      light: false,
    },
    midnight_velvet: {
      sky: ["#100416", "#270a30", "#401048", "#5a1564"],
      iris: ["#ff8ad0", "#d6a7ff", "#ffd086", "#d8f7ff"],
      pearl: "#fff0f7",
      sparkle: "#ffd5ee",
      aurora: ["rgba(255,138,208,0.18)", "rgba(214,167,255,0.16)", "rgba(255,208,134,0.14)"],
      mode: "screen",
      light: false,
    },
    deep_space: {
      sky: ["#060816", "#0d1128", "#1a1a3e", "#080b20"],
      iris: ["#9b7cff", "#67e8f9", "#e7c36f", "#f4a9cd"],
      pearl: "#f5f1ff",
      sparkle: "#c4b5fd",
      aurora: ["rgba(155,124,255,0.16)", "rgba(103,232,249,0.12)", "rgba(231,195,111,0.1)"],
      mode: "screen",
      light: false,
    },
    warm_terminal: {
      sky: ["#120e08", "#201307", "#2a1a08", "#3a210b"],
      iris: ["#ff8a3d", "#fbbf24", "#f59e0b", "#facc15"],
      pearl: "#fff1d6",
      sparkle: "#ffd086",
      aurora: ["rgba(255,138,61,0.18)", "rgba(251,191,36,0.14)", "rgba(245,158,11,0.12)"],
      mode: "screen",
      light: false,
    },
    midnight_teal: {
      sky: ["#041415", "#062024", "#0a2a2d", "#0d3639"],
      iris: ["#2dd4bf", "#99f6e4", "#fbbf24", "#facc15"],
      pearl: "#e8fff8",
      sparkle: "#99f6e4",
      aurora: ["rgba(45,212,191,0.16)", "rgba(153,246,228,0.14)", "rgba(251,191,36,0.1)"],
      mode: "screen",
      light: false,
    },
  };

  function getPalette(themeId) {
    return PALETTES[themeId] || PALETTES[DEFAULT_THEME];
  }

  function isValidTheme(id) {
    return !!PALETTES[id];
  }

  /* ------------------------------------------------------------
     Random / utility
     ------------------------------------------------------------ */
  const rand = (a, b) => a + Math.random() * (b - a);
  const irand = (a, b) => Math.floor(rand(a, b + 1));
  const pick = (arr) => arr[irand(0, arr.length - 1)];

  /* ============================================================
     CANVAS ANIMATION
     ============================================================ */
  let canvas = null;
  let ctx = null;
  let dpr = 1;
  let width = 0;
  let height = 0;
  let rafId = null;
  let lastTs = 0;
  let lastFrameTs = 0;
  let visible = true;
  let currentPalette = getPalette(DEFAULT_THEME);
  let performanceMode = false;
  let reducedMotion = false;
  let particleReductionFactor = 1;

  let fpsFrameCount = 0;
  let fpsLastSample = 0;
  let currentFps = 60;
  let fpsDropCount = 0;

  let crystals = [];
  let pearls = [];
  let sparkles = [];
  let shootingStars = [];
  let auroraT = 0;
  let lastAppliedTheme = null;

  function ensureCanvas() {
    if (canvas) return canvas;
    canvas = document.createElement("canvas");
    canvas.className = "tp-canvas";
    canvas.setAttribute("aria-hidden", "true");
    canvas.style.willChange = "transform";
    document.body.appendChild(canvas);
    ctx = canvas.getContext("2d");
    return canvas;
  }

  function resize() {
    if (!canvas) return;
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    canvas.style.width = width + "px";
    canvas.style.height = height + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    seedScene();
  }

  function currentThemeId() {
    return document.body.dataset.theme || DEFAULT_THEME;
  }

  const THEME_SCENE_PROFILES = {
    crystal_bloom: { density: 1.5, motion: 0.72, auroraSpeed: 0.00035, shooting: 0.0013, pearls: 1.45, sparkles: 1.35, crystals: 1.3 },
    pearl_mist: { density: 1.2, motion: 0.48, auroraSpeed: 0.00022, shooting: 0.00035, pearls: 2, sparkles: 1.7, crystals: 0.35 },
    aurora_glass: { density: 1.4, motion: 0.92, auroraSpeed: 0.0011, shooting: 0.00055, pearls: 0.45, sparkles: 1.65, crystals: 0.55 },
    midnight_velvet: { density: 1.35, motion: 0.62, auroraSpeed: 0.00048, shooting: 0.001, pearls: 1.15, sparkles: 1.45, crystals: 0.85 },
    deep_space: { density: 1.15, motion: 0.38, auroraSpeed: 0.00018, shooting: 0.0022, pearls: 0.25, sparkles: 2.4, crystals: 0.2 },
    warm_terminal: { density: 1.05, motion: 0.58, auroraSpeed: 0.00042, shooting: 0.00028, pearls: 0.35, sparkles: 2, crystals: 0.15 },
    midnight_teal: { density: 1.3, motion: 0.8, auroraSpeed: 0.00058, shooting: 0.00075, pearls: 0.7, sparkles: 1.75, crystals: 0.4 },
  };

  function themeSceneProfile() {
    const base = THEME_SCENE_PROFILES[currentThemeId()] || THEME_SCENE_PROFILES.crystal_bloom;
    const authBoost = isAuthVisible() ? 1.18 : 1;
    const displayBoost = document.body.classList.contains("qr-display-body") ? 1.12 : 1;
    return {
      density: base.density * authBoost * displayBoost,
      motion: base.motion,
      auroraSpeed: base.auroraSpeed,
      shooting: base.shooting,
      pearls: base.pearls * authBoost,
      sparkles: base.sparkles * displayBoost,
      crystals: base.crystals * displayBoost,
    };
  }

  function sceneDensityBoost() {
    return themeSceneProfile().density;
  }

  function motionScale() {
    return themeSceneProfile().motion;
  }

  function isAuthVisible() {
    const auth = document.getElementById("auth-screen");
    return Boolean(auth && !auth.classList.contains("hidden") && !document.body.classList.contains("qr-display-body"));
  }

  function seedScene() {
    const profile = themeSceneProfile();
    const boost = profile.density;
    const baseCount = Math.min(window.innerWidth, 1600) / 1600;
    const reduction = (performanceMode ? 0.45 : 0.55) * particleReductionFactor;
    const cCount = Math.round((6 + baseCount * 5) * reduction * boost * profile.crystals);
    const pCount = Math.round((2 + baseCount * 2) * reduction * boost * profile.pearls);
    const sCount = Math.round((16 + baseCount * 32) * reduction * boost * profile.sparkles);

    crystals = [];
    for (let i = 0; i < cCount; i++) crystals.push(spawnCrystal(true));

    pearls = [];
    for (let i = 0; i < pCount; i++) pearls.push(spawnPearlStrand());

    sparkles = [];
    for (let i = 0; i < sCount; i++) sparkles.push(spawnSparkle(true));

    shootingStars = [];
  }

  function spawnCrystal(initialPlacement) {
    return {
      x: rand(0, width),
      y: initialPlacement ? rand(0, height) : height + rand(20, 100),
      size: rand(14, 38),
      rot: rand(0, Math.PI * 2),
      rotSpeed: rand(-0.0008, 0.0008),
      drift: rand(-0.08, 0.08),
      rise: rand(0.05, 0.18),
      hue: irand(0, 3),
      alpha: rand(0.18, 0.55),
      twinkleT: rand(0, Math.PI * 2),
      twinkleSpeed: rand(0.001, 0.003),
    };
  }

  function spawnPearlStrand() {
    const baseX = rand(0.05, 0.95) * width;
    const beadCount = irand(6, 14);
    const beads = [];
    for (let i = 0; i < beadCount; i++) {
      beads.push({
        offset: i * rand(8, 14),
        size: rand(2.5, 4.5),
      });
    }
    return {
      anchorX: baseX,
      anchorY: rand(-40, height * 0.18),
      length: beadCount * 14,
      sway: rand(0.4, 1.4),
      phase: rand(0, Math.PI * 2),
      speed: rand(0.0006, 0.0014),
      beads,
      alpha: rand(0.25, 0.55),
    };
  }

  function spawnSparkle(initialPlacement) {
    return {
      x: rand(0, width),
      y: initialPlacement ? rand(0, height) : height + rand(10, 60),
      size: rand(0.6, 2.2),
      rise: rand(0.06, 0.3),
      drift: rand(-0.05, 0.05),
      t: rand(0, Math.PI * 2),
      tSpeed: rand(0.002, 0.006),
      alpha: rand(0.2, 0.9),
    };
  }

  function spawnShootingStar() {
    const fromLeft = Math.random() > 0.5;
    return {
      x: fromLeft ? -40 : width + 40,
      y: rand(0, height * 0.55),
      vx: fromLeft ? rand(0.6, 1.0) : -rand(0.6, 1.0),
      vy: rand(0.18, 0.35),
      life: 0,
      maxLife: rand(900, 1500),
      length: rand(80, 160),
    };
  }

  function drawBackground() {
    const p = currentPalette;
    const profile = themeSceneProfile();
    ctx.globalCompositeOperation = "source-over";

    const grad1 = ctx.createRadialGradient(width * 0.2, height * 0.2, 10, width * 0.5, height * 0.5, Math.max(width, height));
    grad1.addColorStop(0, p.aurora[0]);
    grad1.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = grad1;
    ctx.fillRect(0, 0, width, height);

    const grad2 = ctx.createRadialGradient(width * 0.85, height * 0.15, 10, width * 0.85, height * 0.15, Math.max(width, height) * 0.8);
    grad2.addColorStop(0, p.aurora[1]);
    grad2.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = grad2;
    ctx.fillRect(0, 0, width, height);

    const grad3 = ctx.createRadialGradient(width * 0.55, height * 1.05, 10, width * 0.55, height * 1.05, Math.max(width, height) * 0.9);
    grad3.addColorStop(0, p.aurora[2]);
    grad3.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = grad3;
    ctx.fillRect(0, 0, width, height);

    const auroraSpeed = profile.auroraSpeed;
    const sweepX = (Math.sin(auroraT * auroraSpeed) * 0.4 + 0.5) * width;
    const sweep = ctx.createLinearGradient(sweepX - 200, 0, sweepX + 200, height);
    sweep.addColorStop(0, "rgba(0,0,0,0)");
    sweep.addColorStop(0.5, p.aurora[0]);
    sweep.addColorStop(1, "rgba(0,0,0,0)");
    ctx.globalCompositeOperation = p.light ? "multiply" : "screen";
    ctx.fillStyle = sweep;
    ctx.fillRect(0, 0, width, height);

    if (currentThemeId() === "aurora_glass") {
      const bandY = (Math.sin(auroraT * 0.00075 + 1.2) * 0.22 + 0.42) * height;
      const band = ctx.createLinearGradient(0, bandY - 120, 0, bandY + 120);
      band.addColorStop(0, "rgba(0,0,0,0)");
      band.addColorStop(0.5, p.aurora[1]);
      band.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = band;
      ctx.fillRect(0, 0, width, height);
    } else if (currentThemeId() === "midnight_velvet") {
      const bloom = ctx.createRadialGradient(width * 0.5, height * 0.42, 20, width * 0.5, height * 0.42, Math.max(width, height) * 0.55);
      bloom.addColorStop(0, p.aurora[0]);
      bloom.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = bloom;
      ctx.fillRect(0, 0, width, height);
    } else if (currentThemeId() === "warm_terminal") {
      const scanY = (auroraT * 0.035) % (height + 240) - 120;
      const scan = ctx.createLinearGradient(0, scanY, 0, scanY + 90);
      scan.addColorStop(0, "rgba(0,0,0,0)");
      scan.addColorStop(0.5, p.aurora[1]);
      scan.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = scan;
      ctx.fillRect(0, 0, width, height);
    } else if (currentThemeId() === "deep_space") {
      const nebula = ctx.createRadialGradient(width * 0.68, height * 0.28, 10, width * 0.68, height * 0.28, Math.max(width, height) * 0.45);
      nebula.addColorStop(0, p.aurora[2]);
      nebula.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = nebula;
      ctx.fillRect(0, 0, width, height);
    }

    ctx.globalCompositeOperation = "source-over";
  }

  function drawCrystal(c) {
    const p = currentPalette;
    const color = p.iris[c.hue % p.iris.length];
    const tw = 0.5 + Math.sin(c.twinkleT) * 0.5;
    ctx.save();
    ctx.translate(c.x, c.y);
    ctx.rotate(c.rot);
    ctx.globalAlpha = c.alpha * (0.55 + tw * 0.45);

    const s = c.size;

    if (performanceMode) {
      ctx.fillStyle = color;
      ctx.shadowBlur = 10;
      ctx.shadowColor = color;
      ctx.beginPath();
      ctx.arc(0, 0, s * 0.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
      return;
    }

    const grad = ctx.createLinearGradient(-s * 0.5, -s, s * 0.5, s);
    grad.addColorStop(0, p.iris[(c.hue) % p.iris.length]);
    grad.addColorStop(0.5, p.iris[(c.hue + 1) % p.iris.length]);
    grad.addColorStop(1, p.iris[(c.hue + 2) % p.iris.length]);
    ctx.fillStyle = grad;
    ctx.strokeStyle = color;
    ctx.lineWidth = 0.6;

    ctx.beginPath();
    ctx.moveTo(0, -s);
    ctx.lineTo(s * 0.55, -s * 0.25);
    ctx.lineTo(s * 0.4, s * 0.7);
    ctx.lineTo(0, s);
    ctx.lineTo(-s * 0.4, s * 0.7);
    ctx.lineTo(-s * 0.55, -s * 0.25);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();

    ctx.strokeStyle = "rgba(255,255,255,0.45)";
    ctx.lineWidth = 0.4;
    ctx.beginPath();
    ctx.moveTo(0, -s);
    ctx.lineTo(0, s);
    ctx.moveTo(-s * 0.55, -s * 0.25);
    ctx.lineTo(s * 0.55, -s * 0.25);
    ctx.moveTo(0, -s);
    ctx.lineTo(s * 0.4, s * 0.7);
    ctx.moveTo(0, -s);
    ctx.lineTo(-s * 0.4, s * 0.7);
    ctx.stroke();

    ctx.shadowBlur = 18;
    ctx.shadowColor = color;
    ctx.fillStyle = "rgba(255,255,255,0.05)";
    ctx.fillRect(-s, -s, s * 2, s * 2);

    ctx.restore();
  }

  function drawPearl(strand) {
    const p = currentPalette;
    ctx.save();
    ctx.globalAlpha = strand.alpha;
    ctx.strokeStyle = p.pearl;
    ctx.lineWidth = 0.6;

    const sway = Math.sin(strand.phase) * 14 * strand.sway;
    let prevX = strand.anchorX;
    let prevY = strand.anchorY;

    ctx.beginPath();
    ctx.moveTo(prevX, prevY);

    strand.beads.forEach((bead, i) => {
      const ratio = (i + 1) / strand.beads.length;
      const x = strand.anchorX + sway * ratio;
      const y = strand.anchorY + bead.offset * 1.6;
      ctx.lineTo(x, y);
      prevX = x;
      prevY = y;
    });
    ctx.stroke();

    // Pearls
    strand.beads.forEach((bead, i) => {
      const ratio = (i + 1) / strand.beads.length;
      const x = strand.anchorX + sway * ratio;
      const y = strand.anchorY + bead.offset * 1.6;
      const r = bead.size;

      const g = ctx.createRadialGradient(x - r * 0.4, y - r * 0.4, 0.1, x, y, r);
      g.addColorStop(0, "rgba(255,255,255,0.95)");
      g.addColorStop(0.6, p.pearl);
      g.addColorStop(1, "rgba(255,255,255,0.1)");
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fill();
    });

    ctx.restore();
  }

  function drawSparkle(s) {
    const p = currentPalette;
    const a = s.alpha * (0.5 + Math.sin(s.t) * 0.5);
    ctx.save();
    ctx.globalAlpha = a;
    ctx.fillStyle = p.sparkle;
    ctx.shadowBlur = 8;
    ctx.shadowColor = p.sparkle;
    ctx.beginPath();
    ctx.arc(s.x, s.y, s.size, 0, Math.PI * 2);
    ctx.fill();

    // Cross flare for larger sparkles
    if (s.size > 1.4) {
      ctx.strokeStyle = p.sparkle;
      ctx.lineWidth = 0.4;
      ctx.beginPath();
      ctx.moveTo(s.x - s.size * 3, s.y);
      ctx.lineTo(s.x + s.size * 3, s.y);
      ctx.moveTo(s.x, s.y - s.size * 3);
      ctx.lineTo(s.x, s.y + s.size * 3);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawShootingStar(s) {
    const p = currentPalette;
    const a = Math.min(1, s.life / 240) * Math.max(0, 1 - (s.life / s.maxLife));
    ctx.save();
    ctx.globalAlpha = a;
    const grad = ctx.createLinearGradient(s.x, s.y, s.x - s.vx * s.length, s.y - s.vy * s.length);
    grad.addColorStop(0, p.sparkle);
    grad.addColorStop(1, "rgba(255,255,255,0)");
    ctx.strokeStyle = grad;
    ctx.lineWidth = 1.2;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(s.x, s.y);
    ctx.lineTo(s.x - s.vx * s.length, s.y - s.vy * s.length);
    ctx.stroke();
    ctx.restore();
  }

  function measureFps(ts) {
    fpsFrameCount++;
    if (ts - fpsLastSample >= FPS_SAMPLE_INTERVAL) {
      currentFps = Math.round((fpsFrameCount * 1000) / (ts - fpsLastSample));
      fpsFrameCount = 0;
      fpsLastSample = ts;
      if (currentFps < FPS_LOW_THRESHOLD) {
        fpsDropCount++;
        if (fpsDropCount >= 3 && particleReductionFactor > 0.4) {
          particleReductionFactor = Math.max(0.4, particleReductionFactor - 0.15);
          seedScene();
        }
      } else {
        fpsDropCount = Math.max(0, fpsDropCount - 1);
      }
    }
  }

  function frame(ts) {
    if (!ctx || !visible) return;

    const elapsed = ts - lastFrameTs;
    if (elapsed < TARGET_FRAME_MS) {
      rafId = requestAnimationFrame(frame);
      return;
    }
    lastFrameTs = ts;

    const dt = lastTs ? Math.min(60, ts - lastTs) : 16;
    lastTs = ts;
    auroraT += dt;

    measureFps(ts);

    ctx.clearRect(0, 0, width, height);
    drawBackground();

    const dtScale = motionScale();
    pearls.forEach((strand) => {
      strand.phase += strand.speed * dt * dtScale;
      drawPearl(strand);
    });

    sparkles.forEach((s) => {
      s.y -= s.rise * dt * 0.06 * dtScale;
      s.x += s.drift * dt * 0.06 * dtScale;
      s.t += s.tSpeed * dt;
      if (s.y < -10 || s.x < -10 || s.x > width + 10) {
        Object.assign(s, spawnSparkle(false));
      }
      drawSparkle(s);
    });

    crystals.forEach((c) => {
      c.y -= c.rise * dt * 0.06 * dtScale;
      c.x += c.drift * dt * 0.06 * dtScale;
      c.rot += c.rotSpeed * dt * dtScale;
      c.twinkleT += c.twinkleSpeed * dt * dtScale;
      if (c.y < -60) {
        Object.assign(c, spawnCrystal(false));
      }
      drawCrystal(c);
    });

    if (Math.random() < themeSceneProfile().shooting) {
      shootingStars.push(spawnShootingStar());
    }
    shootingStars.forEach((s) => {
      s.life += dt;
      s.x += s.vx * dt;
      s.y += s.vy * dt;
      drawShootingStar(s);
    });
    shootingStars = shootingStars.filter((s) => s.life < s.maxLife);

    rafId = requestAnimationFrame(frame);
  }

  function start() {
    if (!ctx) return;
    if (rafId) return;
    lastTs = 0;
    rafId = requestAnimationFrame(frame);
  }

  function stop() {
    if (rafId) cancelAnimationFrame(rafId);
    rafId = null;
  }

  /* ============================================================
     THEME APPLICATION
     ============================================================ */
  function setStorageKey(key) {
    storageKey = String(key || STORAGE_KEY).trim() || STORAGE_KEY;
  }

  function getStorageKey() {
    return storageKey;
  }

  function readStoredTheme() {
    try { return localStorage.getItem(storageKey) || null; } catch (e) { return null; }
  }

  function writeStoredTheme(id) {
    try { localStorage.setItem(storageKey, id); } catch (e) { /* ignore */ }
  }

  function applyTheme(id, opts) {
    const themeId = isValidTheme(id) ? id : DEFAULT_THEME;
    document.body.dataset.theme = themeId;
    lastAppliedTheme = themeId;
    currentPalette = getPalette(themeId);
    if (!opts || opts.persist !== false) writeStoredTheme(themeId);
    syncSwitcher(themeId);
    if (canvas) {
      seedScene();
    }
    document.dispatchEvent(new CustomEvent("tp:themechange", { detail: { theme: themeId } }));
  }

  /* ============================================================
     THEME SWITCHER UI
     ============================================================ */
  let switcherEl = null;
  let switcherSelect = null;

  function buildSwitcher() {
    if (switcherEl) return switcherEl;
    switcherEl = document.createElement("div");
    switcherEl.className = "tp-theme-switcher";
    switcherEl.setAttribute("role", "group");
    switcherEl.setAttribute("aria-label", "Theme selector");
    switcherEl.innerHTML = `
      <span class="tp-theme-orb" aria-hidden="true"></span>
      <label for="tp-theme-select">Theme</label>
      <select id="tp-theme-select" aria-label="Choose theme"></select>
    `;
    document.body.appendChild(switcherEl);
    switcherSelect = switcherEl.querySelector("select");
    THEMES.forEach((t) => {
      const opt = document.createElement("option");
      opt.value = t.id;
      opt.textContent = t.label;
      switcherSelect.appendChild(opt);
    });
    switcherSelect.addEventListener("change", () => applyTheme(switcherSelect.value));
    return switcherEl;
  }

  function syncSwitcher(id) {
    if (switcherSelect && switcherSelect.value !== id) {
      switcherSelect.value = id;
    }
    // Keep the Settings page dropdown in sync as well, for live preview UX.
    const settingsSelect = document.getElementById("set-active-theme");
    if (settingsSelect && settingsSelect.value !== id) {
      settingsSelect.value = id;
    }
  }

  /* ============================================================
     OBSERVER: watch body[data-theme] changes done by other code
     (settings page change, applyBrand, etc.) so we re-sync the
     canvas palette / switcher.
     ============================================================ */
  function observeBody() {
    if (!("MutationObserver" in global)) return;
    const obs = new MutationObserver(() => {
      const id = document.body.dataset.theme || DEFAULT_THEME;
      if (id !== lastAppliedTheme) {
        applyTheme(id, { persist: false });
      }
    });
    obs.observe(document.body, { attributes: true, attributeFilter: ["data-theme"] });
  }

  function currentTheme() {
    return document.body.dataset.theme || DEFAULT_THEME;
  }

  /* ============================================================
     INIT
     ============================================================ */
  function boot() {
    if (document.body.classList.contains("qr-display-body")) {
      try {
        const did = localStorage.getItem("conlecta_device_id") || "";
        if (did) setStorageKey(`conlecta:display:theme:${did}`);
      } catch (e) { /* ignore */ }
      document.body.classList.add("tp-display-canvas");
    }
    reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reducedMotion) {
      const stored = readStoredTheme();
      const existing = document.body.dataset.theme;
      const authVisible = isAuthVisible();
      const preferExisting = document.body.classList.contains("qr-display-body");
      const initial = authVisible
        ? DEFAULT_THEME
        : preferExisting
          ? (isValidTheme(existing) ? existing : (isValidTheme(stored) ? stored : DEFAULT_THEME))
          : (isValidTheme(stored) ? stored : (isValidTheme(existing) ? existing : DEFAULT_THEME));
      document.body.dataset.theme = initial;
      lastAppliedTheme = initial;
      currentPalette = getPalette(initial);
      observeBody();
      return;
    }

    try {
      const storedPerf = localStorage.getItem(PERF_MODE_KEY);
      performanceMode = storedPerf === null ? true : storedPerf === "true";
      if (storedPerf === null) {
        try { localStorage.setItem(PERF_MODE_KEY, "true"); } catch (e) { /* ignore */ }
      }
    } catch (e) {
      performanceMode = true;
    }
    document.body.classList.toggle("conlecta-lite", performanceMode);

    ensureCanvas();
    resize();
    document.body.classList.add("conlecta-canvas-bg");
    const staticScene = document.querySelector(".bg-scene");
    if (staticScene) staticScene.classList.add("is-reduced");

    const stored = readStoredTheme();
    const existing = document.body.dataset.theme;
    const authVisible = isAuthVisible();
    const preferExisting = document.body.classList.contains("qr-display-body");
    const initial = authVisible
      ? DEFAULT_THEME
      : preferExisting
        ? (isValidTheme(existing) ? existing : (isValidTheme(stored) ? stored : DEFAULT_THEME))
        : (isValidTheme(stored) ? stored : (isValidTheme(existing) ? existing : DEFAULT_THEME));
    applyTheme(initial, { persist: false });

    start();
    observeBody();

    window.addEventListener("resize", resize);
    document.addEventListener("visibilitychange", () => {
      visible = !document.hidden;
      if (visible) {
        lastTs = 0;
        lastFrameTs = 0;
        fpsFrameCount = 0;
        fpsLastSample = 0;
        start();
      } else {
        stop();
      }
    });

    window.matchMedia("(prefers-reduced-motion: reduce)").addEventListener("change", (e) => {
      reducedMotion = e.matches;
      if (reducedMotion) {
        stop();
        if (canvas) {
          canvas.remove();
          canvas = null;
          ctx = null;
        }
      } else {
        ensureCanvas();
        resize();
        start();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }

  /* ============================================================
     PUBLIC API
     ============================================================ */
  function setPerformanceMode(enabled) {
    performanceMode = !!enabled;
    try { localStorage.setItem(PERF_MODE_KEY, performanceMode ? "true" : "false"); } catch (e) { /* ignore */ }
    document.body.classList.toggle("conlecta-lite", performanceMode);
    if (canvas) seedScene();
  }

  function getPerformanceMode() {
    return performanceMode;
  }

  global.ConlectaTheme = {
    THEMES: THEMES.slice(),
    apply: applyTheme,
    current: currentTheme,
    isValid: isValidTheme,
    setStorageKey,
    getStorageKey,
    setPerformanceMode,
    getPerformanceMode,
  };
})(window);
