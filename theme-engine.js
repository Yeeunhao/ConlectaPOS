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
    { id: "ocean_azure",    label: "Ocean Azure" },
    { id: "obsidian_glass", label: "Obsidian Glass" },
    { id: "bubblegum_pop",  label: "Bubblegum Pop" },
    { id: "forest_emerald", label: "Forest Emerald" },
    { id: "cobalt_night",   label: "Cobalt Night" },
    { id: "sunset_amber",   label: "Sunset Amber" },
    { id: "neon_tokyo",     label: "Neon Tokyo" },
    { id: "sakura_drift",   label: "Sakura Drift" },
    { id: "arctic_frost",   label: "Arctic Frost" },
    { id: "copper_dusk",    label: "Copper Dusk" },
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
    ocean_azure: {
      sky: ["#010a14", "#031428", "#062447", "#08305c"],
      iris: ["#38bdf8", "#0ea5e9", "#bae6fd", "#e0f2fe"],
      pearl: "#f0f9ff",
      sparkle: "#7dd3fc",
      aurora: ["rgba(56,189,248,0.22)", "rgba(14,165,233,0.18)", "rgba(186,230,253,0.16)"],
      mode: "screen",
      light: false,
    },
    obsidian_glass: {
      sky: ["#000000", "#050508", "#0a0a0f", "#121218"],
      iris: ["#e2e8f0", "#94a3b8", "#64748b", "#f8fafc"],
      pearl: "#f8fafc",
      sparkle: "#cbd5e1",
      aurora: ["rgba(148,163,184,0.14)", "rgba(226,232,240,0.1)", "rgba(100,116,139,0.08)"],
      mode: "screen",
      light: false,
    },
    bubblegum_pop: {
      sky: ["#10040c", "#220818", "#401030", "#52143e"],
      iris: ["#ff4da6", "#ff85c0", "#ffc2dc", "#ffe4ef"],
      pearl: "#fff0f7",
      sparkle: "#ff85c0",
      aurora: ["rgba(255,77,166,0.22)", "rgba(255,133,192,0.18)", "rgba(255,194,220,0.14)"],
      mode: "screen",
      light: false,
    },
    forest_emerald: {
      sky: ["#020a06", "#061810", "#0c341c", "#104224"],
      iris: ["#22c55e", "#86efac", "#dcfce7", "#fde047"],
      pearl: "#ecfdf5",
      sparkle: "#bbf7d0",
      aurora: ["rgba(34,197,94,0.18)", "rgba(134,239,172,0.16)", "rgba(253,224,71,0.1)"],
      mode: "screen",
      light: false,
    },
    cobalt_night: {
      sky: ["#00040c", "#030d24", "#071842", "#091f52"],
      iris: ["#3b82f6", "#6366f1", "#93c5fd", "#dbeafe"],
      pearl: "#eff6ff",
      sparkle: "#93c5fd",
      aurora: ["rgba(59,130,246,0.2)", "rgba(99,102,241,0.16)", "rgba(147,197,253,0.14)"],
      mode: "screen",
      light: false,
    },
    sunset_amber: {
      sky: ["#120804", "#241006", "#3a1808", "#4a1e0a"],
      iris: ["#fb923c", "#fbbf24", "#fde68a", "#fff7ed"],
      pearl: "#fff7ed",
      sparkle: "#fdba74",
      aurora: ["rgba(251,146,60,0.22)", "rgba(251,191,36,0.18)", "rgba(253,224,71,0.12)"],
      mode: "screen",
      light: false,
    },
    neon_tokyo: {
      sky: ["#070014", "#120028", "#1f0044", "#2a005a"],
      iris: ["#ff2bd6", "#00f5ff", "#bf5fff", "#ffe066"],
      pearl: "#ffe8ff",
      sparkle: "#00f5ff",
      aurora: ["rgba(255,43,214,0.2)", "rgba(0,245,255,0.18)", "rgba(191,95,255,0.14)"],
      mode: "screen",
      light: false,
    },
    sakura_drift: {
      sky: ["#140810", "#28101c", "#401828", "#521e34"],
      iris: ["#fda4af", "#fb7185", "#fecdd3", "#fff1f2"],
      pearl: "#fff1f2",
      sparkle: "#fda4af",
      aurora: ["rgba(253,164,175,0.2)", "rgba(251,113,133,0.16)", "rgba(254,205,211,0.14)"],
      mode: "screen",
      light: false,
    },
    arctic_frost: {
      sky: ["#071018", "#0c1a28", "#123048", "#184060"],
      iris: ["#dbeafe", "#93c5fd", "#e0f2fe", "#ffffff"],
      pearl: "#f8fafc",
      sparkle: "#e0f2fe",
      aurora: ["rgba(224,242,254,0.18)", "rgba(147,197,253,0.14)", "rgba(255,255,255,0.1)"],
      mode: "screen",
      light: false,
    },
    copper_dusk: {
      sky: ["#100806", "#201008", "#341808", "#442010"],
      iris: ["#d97706", "#f59e0b", "#fcd34d", "#fef3c7"],
      pearl: "#fffbeb",
      sparkle: "#fbbf24",
      aurora: ["rgba(217,119,6,0.2)", "rgba(245,158,11,0.16)", "rgba(252,211,77,0.12)"],
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

  const LEGACY_THEME_MAP = {
    lilac_glass: "ocean_azure",
    mint_prism: "forest_emerald",
    rose_quartz: "bubblegum_pop",
  };

  function normalizeThemeId(id) {
    const key = String(id || "").trim();
    return LEGACY_THEME_MAP[key] || key;
  }

  function getPalette(themeId) {
    return PALETTES[normalizeThemeId(themeId)] || PALETTES[DEFAULT_THEME];
  }

  function isValidTheme(id) {
    return !!PALETTES[normalizeThemeId(id)];
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
    lilac_glass: { density: 1.65, motion: 0.82, auroraSpeed: 0.00055, shooting: 0.0012, pearls: 1.55, sparkles: 1.75, crystals: 1.1 },
    mint_prism: { density: 1.6, motion: 1.0, auroraSpeed: 0.0012, shooting: 0.0007, pearls: 0.55, sparkles: 1.9, crystals: 0.65 },
    rose_quartz: { density: 1.55, motion: 0.72, auroraSpeed: 0.00052, shooting: 0.0011, pearls: 1.35, sparkles: 1.65, crystals: 0.95 },
    ocean_azure: { density: 1.62, motion: 0.84, auroraSpeed: 0.0005, shooting: 0.001, pearls: 1.4, sparkles: 1.8, crystals: 0.9 },
    obsidian_glass: { density: 1.45, motion: 0.62, auroraSpeed: 0.00038, shooting: 0.0014, pearls: 0.8, sparkles: 2.1, crystals: 0.5 },
    bubblegum_pop: { density: 1.58, motion: 0.78, auroraSpeed: 0.00048, shooting: 0.0009, pearls: 1.2, sparkles: 1.85, crystals: 0.75 },
    forest_emerald: { density: 1.52, motion: 0.86, auroraSpeed: 0.00056, shooting: 0.0008, pearls: 0.65, sparkles: 1.7, crystals: 0.55 },
    cobalt_night: { density: 1.5, motion: 0.8, auroraSpeed: 0.00046, shooting: 0.0011, pearls: 0.9, sparkles: 1.95, crystals: 0.6, sceneMode: "classic" },
    sunset_amber: { density: 1.35, motion: 0.66, auroraSpeed: 0.00034, shooting: 0.00035, pearls: 0.25, sparkles: 2.4, crystals: 0.15, sceneMode: "ember" },
    neon_tokyo: { density: 1.55, motion: 1.05, auroraSpeed: 0.00072, shooting: 0.00055, pearls: 0.15, sparkles: 2.8, crystals: 0.1, sceneMode: "rain" },
    sakura_drift: { density: 1.48, motion: 0.74, auroraSpeed: 0.00038, shooting: 0.00025, pearls: 0.2, sparkles: 2.2, crystals: 0.12, sceneMode: "petal" },
    arctic_frost: { density: 1.42, motion: 0.58, auroraSpeed: 0.00028, shooting: 0.00018, pearls: 0.35, sparkles: 2.5, crystals: 0.08, sceneMode: "snow" },
    copper_dusk: { density: 1.28, motion: 0.52, auroraSpeed: 0.00062, shooting: 0.00022, pearls: 0.55, sparkles: 1.6, crystals: 0.18, sceneMode: "wave" },
    deep_space: { density: 1.15, motion: 0.38, auroraSpeed: 0.00018, shooting: 0.0022, pearls: 0.25, sparkles: 2.4, crystals: 0.2, sceneMode: "classic" },
    warm_terminal: { density: 1.05, motion: 0.58, auroraSpeed: 0.00042, shooting: 0.00028, pearls: 0.35, sparkles: 2, crystals: 0.15 },
    midnight_teal: { density: 1.3, motion: 0.8, auroraSpeed: 0.00058, shooting: 0.00075, pearls: 0.7, sparkles: 1.75, crystals: 0.4 },
  };

  function themeSceneProfile() {
    const base = THEME_SCENE_PROFILES[normalizeThemeId(currentThemeId())] || THEME_SCENE_PROFILES.crystal_bloom;
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
      sceneMode: base.sceneMode || "classic",
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
    } else if (currentThemeId() === "copper_dusk" || currentThemeId() === "sunset_amber") {
      const bandY = (Math.sin(auroraT * 0.00055 + 0.8) * 0.18 + 0.58) * height;
      const band = ctx.createLinearGradient(0, bandY - 140, 0, bandY + 140);
      band.addColorStop(0, "rgba(0,0,0,0)");
      band.addColorStop(0.5, p.aurora[1]);
      band.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = band;
      ctx.fillRect(0, 0, width, height);
    } else if (currentThemeId() === "neon_tokyo") {
      const pulseX = (Math.sin(auroraT * 0.0009) * 0.35 + 0.5) * width;
      const pulse = ctx.createRadialGradient(pulseX, height * 0.2, 10, pulseX, height * 0.2, Math.max(width, height) * 0.35);
      pulse.addColorStop(0, p.aurora[0]);
      pulse.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = pulse;
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

  function isFallingSceneMode(mode) {
    return mode === "rain" || mode === "petal" || mode === "snow";
  }

  function updateSparkle(s, dt, dtScale, mode) {
    const fall = isFallingSceneMode(mode);
    const speed = fall ? 0.12 : 0.06;
    if (fall) {
      s.y += s.rise * dt * speed * dtScale;
      s.x += (s.drift + Math.sin(s.t) * 0.04) * dt * speed * dtScale;
      if (s.y > height + 12) {
        s.y = -rand(8, 40);
        s.x = rand(0, width);
      }
    } else {
      s.y -= s.rise * dt * speed * dtScale;
      s.x += s.drift * dt * speed * dtScale;
      if (s.y < -12) {
        s.y = height + rand(8, 40);
        s.x = rand(0, width);
      }
    }
    s.t += s.tSpeed * dt;
    if (s.x < -12) s.x = width + rand(8, 24);
    else if (s.x > width + 12) s.x = -rand(8, 24);
  }

  function drawSparkleClassic(s, p, a) {
    ctx.fillStyle = p.sparkle;
    ctx.shadowBlur = 8;
    ctx.shadowColor = p.sparkle;
    ctx.beginPath();
    ctx.arc(s.x, s.y, s.size, 0, Math.PI * 2);
    ctx.fill();
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
  }

  function drawSparkle(s) {
    const p = currentPalette;
    const mode = themeSceneProfile().sceneMode || "classic";
    const a = s.alpha * (0.5 + Math.sin(s.t) * 0.5);
    ctx.save();
    ctx.globalAlpha = a;

    if (mode === "rain") {
      const len = 8 + s.size * 10;
      const grad = ctx.createLinearGradient(s.x, s.y, s.x, s.y + len);
      grad.addColorStop(0, "rgba(255,255,255,0)");
      grad.addColorStop(0.2, p.sparkle);
      grad.addColorStop(1, "rgba(255,255,255,0)");
      ctx.strokeStyle = grad;
      ctx.lineWidth = 0.8 + s.size * 0.25;
      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(s.x + s.drift * 18, s.y + len);
      ctx.stroke();
    } else if (mode === "petal") {
      ctx.translate(s.x, s.y);
      ctx.rotate(s.t + s.drift * 4);
      ctx.fillStyle = p.iris[irand(0, p.iris.length - 1)];
      ctx.beginPath();
      ctx.ellipse(0, 0, s.size * 2.4, s.size * 1.1, 0, 0, Math.PI * 2);
      ctx.fill();
    } else if (mode === "snow") {
      const r = s.size * 1.8;
      ctx.strokeStyle = p.sparkle;
      ctx.lineWidth = 0.5;
      for (let i = 0; i < 6; i += 1) {
        const angle = (Math.PI / 3) * i;
        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(s.x + Math.cos(angle) * r, s.y + Math.sin(angle) * r);
        ctx.stroke();
      }
    } else if (mode === "ember") {
      const r = s.size * 2.2;
      const g = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, r);
      g.addColorStop(0, "rgba(255,255,255,0.95)");
      g.addColorStop(0.35, p.sparkle);
      g.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(s.x, s.y, r, 0, Math.PI * 2);
      ctx.fill();
    } else if (mode === "wave") {
      const r = s.size * 3.2;
      const g = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, r);
      g.addColorStop(0, p.aurora[0]);
      g.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(s.x, s.y, r, 0, Math.PI * 2);
      ctx.fill();
    } else {
      drawSparkleClassic(s, p, a);
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
    const sceneMode = themeSceneProfile().sceneMode || "classic";
    pearls.forEach((strand) => {
      if (sceneMode === "rain" || sceneMode === "snow") return;
      strand.phase += strand.speed * dt * dtScale;
      drawPearl(strand);
    });

    sparkles.forEach((s) => {
      updateSparkle(s, dt, dtScale, sceneMode);
      drawSparkle(s);
    });

    crystals.forEach((c) => {
      if (sceneMode === "rain" || sceneMode === "petal" || sceneMode === "wave") return;
      c.y -= c.rise * dt * 0.06 * dtScale;
      c.x += c.drift * dt * 0.06 * dtScale;
      c.rot += c.rotSpeed * dt * dtScale;
      c.twinkleT += c.twinkleSpeed * dt * dtScale;
      if (c.y < -80) {
        c.y = height + rand(20, 120);
        c.x = rand(0, width);
      } else if (c.x < -80) {
        c.x = width + rand(20, 60);
      } else if (c.x > width + 80) {
        c.x = -rand(20, 60);
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

  let hiddenAt = 0;

  function advanceSceneBy(ms) {
    if (!ms || ms <= 0) return;
    const scale = motionScale();
    const sceneMode = themeSceneProfile().sceneMode || "classic";
    auroraT += ms;
    pearls.forEach((strand) => {
      strand.phase += strand.speed * ms;
    });
    sparkles.forEach((s) => {
      updateSparkle(s, ms, scale, sceneMode);
    });
    crystals.forEach((c) => {
      c.twinkleT += c.twinkleSpeed * ms * scale;
      c.y -= c.rise * ms * 0.06 * scale;
      c.x += c.drift * ms * 0.06 * scale;
      if (c.y < -80) c.y = height + rand(20, 120);
      if (c.x < -80) c.x = width + rand(20, 60);
      if (c.x > width + 80) c.x = -rand(20, 60);
    });
    shootingStars.forEach((s) => {
      s.life += ms;
      s.x += s.vx * ms;
      s.y += s.vy * ms;
    });
    shootingStars = shootingStars.filter((s) => s.life < s.maxLife);
  }

  function resumeAnimationClock() {
    const now = performance.now();
    if (hiddenAt > 0) {
      advanceSceneBy(now - hiddenAt);
      hiddenAt = 0;
    }
    lastTs = now;
    lastFrameTs = now - TARGET_FRAME_MS;
  }

  function start() {
    if (!ctx) return;
    if (rafId) return;
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
    const normalized = normalizeThemeId(id);
    const themeId = isValidTheme(normalized) ? normalized : DEFAULT_THEME;
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
        resumeAnimationClock();
        start();
      } else {
        hiddenAt = performance.now();
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
