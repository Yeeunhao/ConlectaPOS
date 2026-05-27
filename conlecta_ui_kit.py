"""
conlecta_ui_kit.py
==================
Design system untuk Conlecta POS — dark glassmorphism / void-crystal aesthetic.
Port dari HTML reference ke Tkinter native.

Features:
  - Animated mesh background (Canvas dengan radial gradient + particle drift)
  - Crystal float animation
  - Toast notification system
  - Premium glassmorphism cards & buttons
  - Font loading (Cinzel / JetBrains Mono / Outfit via bundled TTF)
  - Shimmer border topbar
  - Semua widget helper yang kompatibel dengan existing code
"""

import tkinter as tk
from tkinter import ttk, font as tkfont
import threading
import time
import math
import random
import os
import sys
from typing import Optional, Callable

# =========================================================
# PATHS
# =========================================================
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

FONTS_DIR = os.path.join(BASE_DIR, "assets", "fonts")

# =========================================================
# COLOR SYSTEM — Void Crystal palette (dari HTML)
# =========================================================
C = {
    # Backgrounds
    "bg":         "#080B1A",
    "bg2":        "#0D1128",
    "bg3":        "#111830",
    "surface":    "#141C35",
    "surface2":   "#1A2340",
    "surface3":   "#1F2A4A",
    "glass":      "#FFFFFF0A",      # rgba(255,255,255,0.04)
    "glass2":     "#FFFFFF11",

    # Accents
    "purple":     "#9B7CFF",
    "purple2":    "#C4B5FD",
    "purple_dk":  "#5B3FBF",
    "cyan":       "#67E8F9",
    "cyan2":      "#A5F3FC",
    "gold":       "#E7C36F",
    "gold2":      "#FDE68A",
    "pink":       "#F472B6",
    "green":      "#34D399",
    "red":        "#F87171",

    # Text
    "text":       "#F5F1FF",
    "text2":      "#B8B0D8",
    "text3":      "#7870A0",

    # Borders
    "border":     "#A08CFF2E",      # glass border purple ~18% alpha
    "border2":    "#6EF2FF26",      # glass border cyan  ~15% alpha
    "border_px":  "#4A3D80",        # solid for Tk (no alpha support native)
    "border2_px": "#2A5A60",

    # Legacy aliases agar existing code tidak crash
    "C_BG":         "#080B1A",
    "C_SURFACE":    "#141C35",
    "C_SURFACE2":   "#1A2340",
    "C_SURFACE3":   "#1F2A4A",
    "C_TEAL":       "#67E8F9",
    "C_TEAL_DK":    "#38B2AC",
    "C_TEAL_LT":    "#A5F3FC",
    "C_LAVENDER":   "#9B7CFF",
    "C_LAVENDER_DK":"#5B3FBF",
    "C_PINK_SOFT":  "#F472B6",
    "C_GOLD":       "#E7C36F",
    "C_GOLD_DK":    "#B8912E",
    "C_TEXT":       "#F5F1FF",
    "C_TEXT2":      "#B8B0D8",
    "C_TEXT3":      "#A5F3FC",
    "C_TEXT_DIM":   "#7870A0",
    "C_WHITE":      "#FFFFFF",
    "C_BLACK":      "#060816",
    "C_RED":        "#F87171",
    "C_RED_DK":     "#DC2626",
    "C_GREEN":      "#34D399",
    "C_GREEN_DK":   "#059669",
    "C_GREEN_LT":   "#6EE7B7",
    "C_BORDER":     "#4A3D80",
    "C_BORDER2":    "#2A5A60",
    "C_AMBER":      "#E7C36F",
    "C_BTN_BLUE":   "#60A5FA",
    "C_BTN_PURPLE": "#9B7CFF",
}

# Shorthand - semua C_* yang dipakai existing code
C_BG         = C["bg"]
C_BG_TOP     = C["bg2"]
C_SURFACE    = C["surface"]
C_SURFACE2   = C["surface2"]
C_SURFACE3   = C["surface3"]
C_GLASS_LITE = "#E8E4FF"
C_BORDER     = C["border_px"]
C_BORDER2    = C["border2_px"]
C_TEAL       = C["cyan"]
C_TEAL_DK    = "#38B2AC"
C_TEAL_LT    = C["cyan2"]
C_LAVENDER   = C["purple"]
C_LAVENDER_DK = C["purple_dk"]
C_PINK_SOFT  = C["pink"]
C_GOLD       = C["gold"]
C_GOLD_DK    = "#B8912E"
C_TEXT       = C["text"]
C_TEXT2      = C["text2"]
C_TEXT3      = C["cyan2"]
C_TEXT_DIM   = C["text3"]
C_WHITE      = "#FFFFFF"
C_BLACK      = "#060816"
C_QR_BG      = "#04070F"
C_RED        = C["red"]
C_RED_DK     = "#DC2626"
C_RED_LT     = "#FCA5A5"
C_AMBER      = C["gold"]
C_SUCCESS    = C["green"]
C_GREEN      = C["green"]
C_GREEN_DK   = "#059669"
C_GREEN_LT   = "#6EE7B7"
C_GREEN_XLT  = "#A7F3D0"
C_GREEN_GLOW = "#34D39940"
C_NAV_STOCK  = "#059669"
C_NAV_HIST   = "#5B3FBF"
C_NAV_SET    = "#1F2A4A"
C_NAV_LOG    = "#2A1A4A"
C_NAV_EXIT   = "#DC2626"
C_BTN_BLUE   = "#60A5FA"
C_BTN_PURPLE = C["purple"]
C_NEON       = C["cyan"]
C_NEON_DK    = "#38B2AC"
C_NEON_LT    = C["cyan2"]
C_PINK       = C["purple"]
C_PINK_LT    = C["purple2"]
C_PINK_DK    = C["purple_dk"]
C_STICKER    = "#E8E4FF"
C_PURPLE2    = "#C4B5FD"

# =========================================================
# FONT SYSTEM
# =========================================================
# Nama font yang akan dipakai (fallback ke system jika TTF tidak ada)
_FONT_DISPLAY_NAME = "Cinzel"
_FONT_UI_NAME      = "Outfit"
_FONT_MONO_NAME    = "JetBrains Mono"

_fonts_loaded = False

def load_custom_fonts():
    """
    Load bundled TTF fonts dari assets/fonts/.
    Tkinter tidak punya native font loading — kita pakai tkinter.font
    dengan PhotoImage trick atau tk.font.families() check.
    
    Untuk Windows: font harus sudah di-install atau kita gunakan
    win32api (jika tersedia) untuk temporary load.
    Fallback: Segoe UI / Consolas.
    """
    global _fonts_loaded, _FONT_DISPLAY_NAME, _FONT_UI_NAME, _FONT_MONO_NAME
    if _fonts_loaded:
        return

    available = tkfont.families()

    # Check apakah font sudah tersedia (sudah di-install)
    if "Cinzel" not in available:
        # Coba load sementara via Windows GDI jika ada fontnya
        cinzel_path = os.path.join(FONTS_DIR, "Cinzel-Bold.ttf")
        if os.path.isfile(cinzel_path) and os.name == "nt":
            try:
                import ctypes
                FR_PRIVATE = 0x10
                ctypes.windll.gdi32.AddFontResourceExW(cinzel_path, FR_PRIVATE, 0)
            except Exception:
                pass

    if "JetBrains Mono" not in available:
        jb_path = os.path.join(FONTS_DIR, "JetBrainsMono-Regular.ttf")
        if os.path.isfile(jb_path) and os.name == "nt":
            try:
                import ctypes
                ctypes.windll.gdi32.AddFontResourceExW(jb_path, 0x10, 0)
            except Exception:
                pass

    if "Outfit" not in available:
        outfit_path = os.path.join(FONTS_DIR, "Outfit-Regular.ttf")
        if os.path.isfile(outfit_path) and os.name == "nt":
            try:
                import ctypes
                ctypes.windll.gdi32.AddFontResourceExW(outfit_path, 0x10, 0)
            except Exception:
                pass

    # Re-check setelah load attempt
    available = tkfont.families()
    if "Cinzel" not in available:
        _FONT_DISPLAY_NAME = "Georgia"
    if "Outfit" not in available:
        _FONT_UI_NAME = "Segoe UI"
    if "JetBrains Mono" not in available:
        _FONT_MONO_NAME = "Consolas"

    _fonts_loaded = True

# =========================================================
# FONT TUPLES
# =========================================================
def _F(name, size, weight="normal"):
    return (name, size, weight)

def get_fonts():
    """Return font tuples — call setelah load_custom_fonts()"""
    d  = _FONT_DISPLAY_NAME
    u  = _FONT_UI_NAME
    m  = _FONT_MONO_NAME
    return {
        "display":    _F(d, 28, "bold"),
        "title":      _F(u, 14, "bold"),
        "ui":         _F(u, 11),
        "ui_sm":      _F(u, 9),
        "ui_xs":      _F(u, 8),
        "mono":       _F(m, 10),
        "mono_sm":    _F(m, 9),
        "mono_lg":    _F(m, 13, "bold"),
        "logo":       _F(d, 16, "bold"),
    }

# Legacy font tuples (kompatibel existing code)
FONT_DISPLAY = ("Georgia", 26, "bold")
FONT_TITLE   = ("Segoe UI", 14, "bold")
FONT_UI      = ("Segoe UI", 11)
FONT_UI_SM   = ("Segoe UI", 9)
FONT_UI_XS   = ("Segoe UI", 8)
FONT_MONO    = ("Consolas", 10)
FONT_MONO_SM = ("Consolas", 9)

def _update_legacy_fonts():
    global FONT_DISPLAY, FONT_TITLE, FONT_UI, FONT_UI_SM, FONT_UI_XS, FONT_MONO, FONT_MONO_SM
    FONT_DISPLAY = (_FONT_DISPLAY_NAME, 26, "bold")
    FONT_TITLE   = (_FONT_UI_NAME, 14, "bold")
    FONT_UI      = (_FONT_UI_NAME, 11)
    FONT_UI_SM   = (_FONT_UI_NAME, 9)
    FONT_UI_XS   = (_FONT_UI_NAME, 8)
    FONT_MONO    = (_FONT_MONO_NAME, 10)
    FONT_MONO_SM = (_FONT_MONO_NAME, 9)

# =========================================================
# TTK STYLES — void crystal dark theme
# =========================================================
def apply_ttk_styles(style: ttk.Style):
    style.theme_use("clam")

    # Treeview
    style.configure("Dark.Treeview",
                    background=C_SURFACE2, foreground=C_TEXT,
                    fieldbackground=C_SURFACE2, rowheight=38,
                    font=FONT_UI, bordercolor=C_BORDER, relief="flat")
    style.configure("Dark.Treeview.Heading",
                    background=C_SURFACE, foreground=C_TEAL_LT,
                    font=(_FONT_UI_NAME, 10, "bold"), relief="flat",
                    borderwidth=0)
    style.map("Dark.Treeview",
              background=[("selected", C_LAVENDER_DK)],
              foreground=[("selected", C_WHITE)])

    # Scrollbars
    style.configure("Dark.Vertical.TScrollbar",
                    troughcolor=C_SURFACE, background=C_LAVENDER,
                    arrowcolor=C_TEXT, bordercolor=C_BORDER,
                    lightcolor=C_SURFACE2, darkcolor=C_SURFACE)
    style.configure("Dark.Horizontal.TScrollbar",
                    troughcolor=C_SURFACE, background=C_TEAL_DK,
                    arrowcolor=C_TEXT, bordercolor=C_BORDER)

    # Combobox
    style.configure("Glass.TCombobox",
                    fieldbackground=C_GLASS_LITE, background=C_SURFACE2,
                    foreground=C_BLACK, selectbackground=C_LAVENDER_DK,
                    selectforeground=C_WHITE, bordercolor=C_BORDER,
                    arrowcolor=C_LAVENDER)

    # Spinbox
    style.configure("TSpinbox",
                    fieldbackground=C_GLASS_LITE, foreground=C_BLACK,
                    background=C_SURFACE2, bordercolor=C_BORDER,
                    arrowcolor=C_LAVENDER)

    # Progressbar
    style.configure("Crystal.Horizontal.TProgressbar",
                    troughcolor=C_SURFACE, background=C_LAVENDER,
                    bordercolor=C_BORDER, lightcolor=C_PURPLE2 if "C_PURPLE2" in dir() else C_LAVENDER,
                    darkcolor=C_LAVENDER_DK)

# =========================================================
# ANIMATED CANVAS BACKGROUND
# =========================================================
class VoidCrystalBackground:
    """
    Animated background: radial gradient mesh + drifting particles + crystal shards.
    Renders onto a tk.Canvas yang di-place di bawah semua widget.
    """

    PARTICLE_COUNT = 22
    CRYSTAL_COUNT  = 6

    def __init__(self, parent: tk.Widget, width: int = 1400, height: int = 900):
        self.parent = parent
        self.w      = width
        self.h      = height
        self._running = False
        self._canvas  = None
        self._particles = []
        self._crystals  = []
        self._frame_id  = None
        self._bg_photo  = None

    def attach(self) -> tk.Canvas:
        """Buat canvas, render gradient bg, start animasi, return canvas."""
        self._canvas = tk.Canvas(
            self.parent, width=self.w, height=self.h,
            bg=C_BG, highlightthickness=0, bd=0
        )
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._canvas.lower()

        self._draw_gradient_bg()
        self._init_particles()
        self._init_crystals()
        self._running = True
        self._animate()
        return self._canvas

    def detach(self):
        self._running = False
        if self._frame_id:
            try:
                self.parent.after_cancel(self._frame_id)
            except Exception:
                pass
        if self._canvas:
            try:
                self._canvas.destroy()
            except Exception:
                pass

    # ── Static gradient background ──
    def _draw_gradient_bg(self):
        c = self._canvas
        w, h = self.w, self.h

        # Base dark gradient via multiple overlapping rectangles (no PIL needed for basic version)
        # Outer dark
        c.create_rectangle(0, 0, w, h, fill="#080B1A", outline="")

        # Radial-ish blobs using ovals with stipple / transparency workaround
        # Tkinter tidak support alpha di shapes → kita gunakan layered ovals dgn stipple
        blobs = [
            # (cx%, cy%, rx%, ry%, color, stipple)
            (0.20, 0.30, 0.55, 0.50, "#6438DC", "gray25"),
            (0.80, 0.20, 0.45, 0.55, "#67E8F9", "gray12"),
            (0.60, 0.80, 0.65, 0.40, "#9B7CFF", "gray12"),
        ]
        for cx_r, cy_r, rx_r, ry_r, col, stip in blobs:
            cx = int(cx_r * w); cy = int(cy_r * h)
            rx = int(rx_r * w // 2); ry = int(ry_r * h // 2)
            c.create_oval(cx-rx, cy-ry, cx+rx, cy+ry,
                          fill=col, outline="", stipple=stip)

        # Grid scanlines subtle
        for y in range(0, h, 40):
            c.create_line(0, y, w, y, fill="#FFFFFF04", width=1)

    # ── Particles ──
    def _init_particles(self):
        c = self._canvas
        for _ in range(self.PARTICLE_COUNT):
            x = random.uniform(0, self.w)
            y = random.uniform(0, self.h)
            size = random.choice([1, 1, 1, 2, 2])
            speed = random.uniform(0.3, 1.2)
            drift = random.uniform(-0.4, 0.4)
            color = random.choice([C_TEAL_LT, C_LAVENDER, C_WHITE, C_TEAL])
            delay = random.uniform(0, 120)  # frames sebelum mulai fade in
            oid = c.create_oval(x, y, x+size, y+size,
                                fill=color, outline="", state="hidden")
            self._particles.append({
                "id": oid, "x": x, "y": y,
                "vx": drift, "vy": -speed,
                "size": size, "delay": delay,
                "life": 0, "max_life": random.uniform(80, 180),
                "color": color,
            })

    # ── Crystals (floating diamond shapes) ──
    def _init_crystals(self):
        c = self._canvas
        for _ in range(self.CRYSTAL_COUNT):
            x = random.uniform(50, self.w - 50)
            y = random.uniform(self.h * 0.2, self.h * 0.85)
            sz = random.randint(8, 20)
            color = random.choice([C_LAVENDER, C_TEAL_LT, "#C4B5FD"])
            angle = random.uniform(0, 360)
            speed_y = random.uniform(0.15, 0.5)
            delay = random.uniform(0, 200)
            pts = self._diamond_pts(x, y, sz, angle)
            oid = c.create_polygon(*pts, fill="", outline=color, width=1,
                                   state="hidden")
            self._crystals.append({
                "id": oid, "x": x, "y": y, "sz": sz,
                "angle": angle, "speed_y": speed_y,
                "delay": delay, "life": 0,
                "max_life": random.uniform(120, 300),
                "color": color,
            })

    @staticmethod
    def _diamond_pts(cx, cy, sz, angle_deg):
        """4-point diamond dengan rotasi."""
        pts = []
        for a in [0, 90, 180, 270]:
            rad = math.radians(a + angle_deg)
            scale = sz if a in (0, 180) else sz * 0.55
            pts.extend([cx + math.cos(rad)*scale, cy + math.sin(rad)*scale])
        return pts

    # ── Animation loop ──
    def _animate(self):
        if not self._running:
            return
        c = self._canvas
        if not c.winfo_exists():
            return

        # Update particles
        for p in self._particles:
            if p["delay"] > 0:
                p["delay"] -= 1
                continue
            p["life"] += 1
            p["x"] += p["vx"]
            p["y"] += p["vy"]

            # Lifecycle: fade in → steady → fade out
            life_ratio = p["life"] / p["max_life"]
            if life_ratio < 0.1:
                alpha_factor = life_ratio / 0.1
            elif life_ratio > 0.9:
                alpha_factor = (1 - life_ratio) / 0.1
            else:
                alpha_factor = 1.0

            if life_ratio >= 1.0 or p["y"] < -10:
                # Reset particle
                p["x"] = random.uniform(0, self.w)
                p["y"] = self.h + 5
                p["vx"] = random.uniform(-0.4, 0.4)
                p["vy"] = -random.uniform(0.3, 1.2)
                p["life"] = 0
                p["max_life"] = random.uniform(80, 180)
                p["delay"] = random.uniform(0, 30)
                c.itemconfig(p["id"], state="hidden")
                continue

            if alpha_factor > 0.2:
                c.coords(p["id"],
                         p["x"], p["y"],
                         p["x"] + p["size"], p["y"] + p["size"])
                c.itemconfig(p["id"], state="normal")
            else:
                c.itemconfig(p["id"], state="hidden")

        # Update crystals
        for cr in self._crystals:
            if cr["delay"] > 0:
                cr["delay"] -= 1
                continue
            cr["life"] += 1
            cr["y"] -= cr["speed_y"]
            cr["angle"] += 0.3

            life_ratio = cr["life"] / cr["max_life"]
            if life_ratio < 0.2:
                alpha_factor = life_ratio / 0.2
            elif life_ratio > 0.8:
                alpha_factor = (1 - life_ratio) / 0.2
            else:
                alpha_factor = 1.0

            if life_ratio >= 1.0 or cr["y"] < -30:
                cr["x"] = random.uniform(50, self.w - 50)
                cr["y"] = self.h + random.uniform(10, 60)
                cr["speed_y"] = random.uniform(0.15, 0.5)
                cr["life"] = 0
                cr["max_life"] = random.uniform(120, 300)
                cr["delay"] = random.uniform(0, 100)
                c.itemconfig(cr["id"], state="hidden")
                continue

            if alpha_factor > 0.15:
                pts = self._diamond_pts(cr["x"], cr["y"], cr["sz"], cr["angle"])
                c.coords(cr["id"], *pts)
                c.itemconfig(cr["id"], state="normal")
            else:
                c.itemconfig(cr["id"], state="hidden")

        # 30fps
        self._frame_id = c.after(33, self._animate)


# =========================================================
# SHIMMER BORDER (topbar bottom)
# =========================================================
class ShimmerBorder(tk.Canvas):
    """1px Canvas yang animasi gradient purple→cyan→purple."""

    def __init__(self, parent, **kw):
        h = kw.pop("height", 2)
        super().__init__(parent, height=h, bg=C_SURFACE,
                         highlightthickness=0, bd=0, **kw)
        self._phase  = 0.0
        self._line   = None
        self._active = False
        self.bind("<Map>", lambda e: self._start())
        self.bind("<Unmap>", lambda e: self._stop())

    def _start(self):
        if not self._active:
            self._active = True
            self._shimmer()

    def _stop(self):
        self._active = False

    def _shimmer(self):
        if not self._active:
            return
        if not self.winfo_exists():
            return
        w = self.winfo_width()
        if w < 10:
            self.after(200, self._shimmer)
            return

        self._phase = (self._phase + 0.025) % (2 * math.pi)
        # Build gradient line via many short segments
        self.delete("shimmer")
        segments = max(40, w // 8)
        for i in range(segments):
            x0 = int(i * w / segments)
            x1 = int((i + 1) * w / segments)
            t  = i / segments
            # wave: purple at 0/1, cyan at 0.5, shifted by phase
            phase_t = (t + self._phase / (2 * math.pi)) % 1.0
            if phase_t < 0.5:
                ratio = phase_t * 2
                r = int(0x9B + (0x67 - 0x9B) * ratio)
                g = int(0x7C + (0xE8 - 0x7C) * ratio)
                b = int(0xFF + (0xF9 - 0xFF) * ratio)
            else:
                ratio = (phase_t - 0.5) * 2
                r = int(0x67 + (0x9B - 0x67) * ratio)
                g = int(0xE8 + (0x7C - 0xE8) * ratio)
                b = int(0xF9 + (0xFF - 0xF9) * ratio)
            color = f"#{r:02X}{g:02X}{b:02X}"
            h = self.winfo_height()
            self.create_line(x0, h//2, x1, h//2,
                             fill=color, width=h, tags="shimmer")

        self.after(30, self._shimmer)


# =========================================================
# TOAST NOTIFICATION
# =========================================================
class ToastManager:
    """
    Global toast system — pojok kanan bawah, auto-dismiss.
    Usage:
        toast = ToastManager(root)
        toast.show("Berhasil!", "success")   # success | error | warning | info
    """
    _COLORS = {
        "success": (C_GREEN,      "#065F46"),
        "error":   (C_RED,        "#7F1D1D"),
        "warning": (C_GOLD,       "#78350F"),
        "info":    (C_TEAL_LT,    "#0C4A6E"),
    }
    _ICONS = {
        "success": "✓",
        "error":   "✕",
        "warning": "⚠",
        "info":    "ℹ",
    }

    def __init__(self, root: tk.Tk):
        self.root   = root
        self._queue = []
        self._showing = False
        self._win   = None

    def show(self, message: str, kind: str = "success", duration: int = 3000):
        self._queue.append((message, kind, duration))
        if not self._showing:
            self._next()

    def _next(self):
        if not self._queue:
            self._showing = False
            return
        self._showing = True
        msg, kind, dur = self._queue.pop(0)
        self._display(msg, kind, dur)

    def _display(self, msg: str, kind: str, dur: int):
        fg, bg = self._COLORS.get(kind, self._COLORS["info"])
        icon   = self._ICONS.get(kind, "ℹ")

        if self._win and self._win.winfo_exists():
            try:
                self._win.destroy()
            except Exception:
                pass

        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=bg)

        # Position: bottom-right
        self.root.update_idletasks()
        rw = self.root.winfo_width()
        rh = self.root.winfo_height()
        rx = self.root.winfo_rootx()
        ry = self.root.winfo_rooty()

        tw, th = 340, 56
        x = rx + rw - tw - 20
        y = ry + rh - th - 20
        win.geometry(f"{tw}x{th}+{x}+{y}")

        # Shimmer border top
        border_top = tk.Frame(win, bg=fg, height=2)
        border_top.pack(fill="x")

        inner = tk.Frame(win, bg=bg, padx=14, pady=10)
        inner.pack(fill="both", expand=True)

        tk.Label(inner, text=icon, bg=bg, fg=fg,
                 font=("Consolas", 16, "bold")).pack(side="left", padx=(0, 10))
        tk.Label(inner, text=msg, bg=bg, fg=fg,
                 font=("Segoe UI", 10), wraplength=260,
                 justify="left", anchor="w").pack(side="left", fill="x", expand=True)

        self._win = win
        # Slide in via alpha
        win.attributes("-alpha", 0.0)
        self._fade_in(win, 0.0, dur)

    def _fade_in(self, win, alpha, dur):
        if not win.winfo_exists():
            return
        alpha = min(1.0, alpha + 0.12)
        win.attributes("-alpha", alpha)
        if alpha < 1.0:
            win.after(20, lambda: self._fade_in(win, alpha, dur))
        else:
            win.after(dur, lambda: self._fade_out(win))

    def _fade_out(self, win):
        if not win.winfo_exists():
            self._showing = False
            self.root.after(100, self._next)
            return
        try:
            alpha = win.attributes("-alpha")
        except Exception:
            self._showing = False
            self.root.after(100, self._next)
            return
        alpha = max(0.0, alpha - 0.08)
        win.attributes("-alpha", alpha)
        if alpha > 0:
            win.after(20, lambda: self._fade_out(win))
        else:
            try:
                win.destroy()
            except Exception:
                pass
            self._showing = False
            self.root.after(80, self._next)


# =========================================================
# GLASSMORPHISM WIDGETS
# =========================================================

def glass_card(parent, inner_bg=C_SURFACE, border_color=None, border_w=1,
               padx=1, pady=1):
    """
    Card dengan border tipis — kompatibel dengan existing glass_card() call.
    Returns (outer, inner).
    """
    bc = border_color or C_BORDER
    outer = tk.Frame(parent, bg=bc, padx=border_w, pady=border_w)
    inner = tk.Frame(outer, bg=inner_bg)
    inner.pack(fill="both", expand=True)
    return outer, inner

# Alias
brutal_card = glass_card


def accent_strip(parent, h: int = 3) -> tk.Frame:
    """Purple→cyan→pink gradient strip."""
    fr = tk.Frame(parent, bg=C_BG, height=h)
    tk.Frame(fr, bg=C_LAVENDER, height=max(1, h)).place(
        relx=0, rely=0, relwidth=0.40, relheight=1)
    tk.Frame(fr, bg=C_TEAL, height=max(1, h)).place(
        relx=0.35, rely=0, relwidth=0.35, relheight=1)
    tk.Frame(fr, bg=C_PINK_SOFT, height=max(1, h)).place(
        relx=0.65, rely=0, relwidth=0.35, relheight=1)
    return fr


def section_heading(parent, text, bg=C_BG, fg=C_TEAL_LT, sub=None):
    fr = tk.Frame(parent, bg=bg)
    tk.Label(fr, text=text, bg=bg, fg=fg, font=FONT_TITLE).pack(side="left")
    if sub:
        tk.Label(fr, text=sub, bg=bg, fg=C_TEXT_DIM,
                 font=FONT_UI_SM).pack(side="left", padx=(10, 0))
    return fr


def page_header(parent, title, subtitle=None, on_back=None):
    bar = tk.Frame(parent, bg=C_SURFACE, height=56)
    bar.pack(fill="x")
    bar.pack_propagate(False)
    accent_strip(bar, h=3).pack(fill="x", side="top")
    row = tk.Frame(bar, bg=C_SURFACE)
    row.pack(fill="both", expand=True, padx=12, pady=6)
    if on_back:
        styled_btn(row, "← Back", bg=C_SURFACE2, fg=C_TEXT2,
                   font_size=10, pady=6, padx=12,
                   command=on_back).pack(side="left", padx=(0, 10))
    tk.Label(row, text=title, bg=C_SURFACE, fg=C_TEXT,
             font=FONT_TITLE).pack(side="left")
    if subtitle:
        tk.Label(row, text=subtitle, bg=C_SURFACE, fg=C_TEXT_DIM,
                 font=FONT_UI_SM).pack(side="left", padx=(12, 0))
    return bar


# =========================================================
# BUTTONS
# =========================================================
BTN_H = 8

# Mapping style → (bg, hover_bg, fg)
_BUTTON_STYLES = {
    "primary":   (C_LAVENDER,    "#7C5CE0",   C_WHITE),
    "secondary": (C_SURFACE2,    C_SURFACE3,  C_TEXT2),
    "accent":    (C_TEAL_DK,     "#2A8F89",   C_WHITE),
    "danger":    (C_RED_DK,      "#B91C1C",   C_WHITE),
    "purple":    (C_BTN_PURPLE,  "#7C5CE0",   C_WHITE),
    "ghost":     (C_SURFACE3,    C_SURFACE2,  C_TEXT2),
    "gold":      (C_GOLD,        "#B8912E",   C_BLACK),
    "success":   (C_GREEN,       C_GREEN_DK,  C_BLACK),
}

_BTN_IMG_CACHE: dict = {}


def _darken(hex_color: str) -> str:
    mapping = {
        C_TEAL: C_TEAL_DK, C_TEAL_DK: "#2A8F89",
        C_LAVENDER: C_LAVENDER_DK, C_LAVENDER_DK: "#4A2FA0",
        C_RED: C_RED_DK, C_RED_DK: "#B91C1C",
        C_GOLD: C_GOLD_DK, C_GOLD_DK: "#956D1A",
        C_GREEN: C_GREEN_DK, C_GREEN_DK: "#047857",
        C_SURFACE: C_BG, C_SURFACE2: C_SURFACE, C_SURFACE3: C_SURFACE2,
        C_BTN_BLUE: "#3B82F6", C_BTN_PURPLE: C_LAVENDER_DK,
        C_NAV_STOCK: "#047857", C_NAV_HIST: C_LAVENDER_DK,
        C_NAV_EXIT: "#B91C1C",
    }
    return mapping.get(hex_color, hex_color)


def _btn_fg_for(bg: str, fg=None) -> str:
    if fg is not None:
        return fg
    light_bgs = {C_TEAL, C_TEAL_LT, C_GOLD, C_GREEN, C_GLASS_LITE, C_STICKER, C_WHITE}
    return C_BLACK if bg in light_bgs else C_TEXT


def styled_btn(parent, text, bg, fg=None, font_size=11, bold=True,
               width=None, height=None, command=None,
               padx=16, pady=BTN_H, hover_bg=None, border=0) -> tk.Button:
    weight = "bold" if bold else "normal"
    fg     = _btn_fg_for(bg, fg)
    hov    = hover_bg or _darken(bg)
    kw = dict(
        text=text, bg=bg, fg=fg,
        font=(FONT_UI[0], font_size, weight),
        relief="flat", cursor="hand2",
        activebackground=hov, activeforeground=fg,
        bd=border, highlightthickness=1,
        highlightbackground=C_BORDER, highlightcolor=C_LAVENDER,
        padx=padx, pady=pady,
    )
    if width:  kw["width"]  = width
    if height: kw["height"] = height
    if command: kw["command"] = command
    btn = tk.Button(parent, **kw)

    def _on(e):  btn.config(bg=hov)
    def _off(e): btn.config(bg=bg)
    btn.bind("<Enter>", _on)
    btn.bind("<Leave>", _off)
    return btn


def modern_btn(parent, text, command=None, style="primary",
               width=0, height=42, font_size=11, full_width=False):
    """
    Rounded gradient-style button via compound label trick.
    Compatible dengan existing modern_btn() calls.
    """
    bg, hov, fg = _BUTTON_STYLES.get(style, _BUTTON_STYLES["primary"])
    weight = "bold" if style in ("primary", "accent", "danger", "purple", "gold", "success") else "normal"
    font   = (FONT_UI[0], font_size, weight)

    try:
        parent_bg = parent["bg"]
    except Exception:
        parent_bg = C_BG

    holder = tk.Frame(parent, bg=parent_bg, cursor="hand2")

    inner_btn = tk.Button(
        holder, text=text, bg=bg, fg=fg,
        font=font, relief="flat", bd=0, cursor="hand2",
        activebackground=hov, activeforeground=fg,
        highlightthickness=1,
        highlightbackground=C_BORDER,
        highlightcolor=C_LAVENDER,
        padx=14, pady=max(4, (height - 24) // 2),
    )
    inner_btn.pack(fill="x" if full_width else "none",
                   expand=full_width)

    if full_width:
        holder.pack(fill="x")

    def _enter(_e): inner_btn.config(bg=hov)
    def _leave(_e): inner_btn.config(bg=bg)
    inner_btn.bind("<Enter>", _enter)
    inner_btn.bind("<Leave>", _leave)
    holder.bind("<Enter>", _enter)
    holder.bind("<Leave>", _leave)

    holder._command = command
    holder._inner   = inner_btn

    def _click(_e):
        if holder._command:
            holder._command()

    def _mb_config(**kw):
        if "command" in kw:
            holder._command = kw["command"]
            inner_btn.config(command=kw["command"])

    holder.config = _mb_config
    inner_btn.config(command=lambda: holder._command() if holder._command else None)

    for wdg in (holder, inner_btn):
        wdg.bind("<Button-1>", _click)

    if width:
        inner_btn.config(width=width)

    return holder


# =========================================================
# ENTRY & FORM WIDGETS
# =========================================================
def _entry_dark(parent, textvariable=None, width=10,
                readonly=False, show=None) -> tk.Entry:
    kw = dict(
        bg="#E8E4FF", fg="#0D0B1F",
        insertbackground=C_LAVENDER,
        relief="flat", bd=0,
        highlightthickness=1,
        highlightbackground=C_BORDER,
        highlightcolor=C_LAVENDER,
        font=FONT_UI, width=width,
    )
    if textvariable: kw["textvariable"] = textvariable
    if show:         kw["show"]         = show
    e = tk.Entry(parent, **kw)
    if readonly:
        e.config(state="readonly", bg=C_SURFACE3, fg=C_TEXT2,
                 highlightbackground=C_SURFACE3)
    return e


# =========================================================
# SCROLLABLE HELPERS
# =========================================================
def _bind_mousewheel(canvas: tk.Canvas):
    def _scroll(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    def _bind(_e=None):   canvas.bind_all("<MouseWheel>", _scroll)
    def _unbind(_e=None): canvas.unbind_all("<MouseWheel>")
    canvas.bind("<Enter>", _bind)
    canvas.bind("<Leave>", _unbind)


def _scrollable_tree(parent, columns, headings, col_cfg=None, height=16):
    outer, inner = glass_card(parent, inner_bg=C_SURFACE2)
    outer.pack(fill="both", expand=True)
    tree_fr = tk.Frame(inner, bg=C_SURFACE2)
    tree_fr.pack(fill="both", expand=True, padx=4, pady=4)
    tree_fr.rowconfigure(0, weight=1)
    tree_fr.columnconfigure(0, weight=1)

    vsb = ttk.Scrollbar(tree_fr, orient="vertical",   style="Dark.Vertical.TScrollbar")
    hsb = ttk.Scrollbar(tree_fr, orient="horizontal", style="Dark.Horizontal.TScrollbar")
    tree = ttk.Treeview(
        tree_fr, columns=columns, show="headings",
        yscrollcommand=vsb.set, xscrollcommand=hsb.set,
        style="Dark.Treeview", height=height
    )
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.config(command=tree.yview)
    hsb.config(command=tree.xview)

    for col in columns:
        tree.heading(col, text=headings.get(col, col))
        if col_cfg and col in col_cfg:
            tree.column(col, **col_cfg[col])
    return tree, outer


# =========================================================
# NAV BUTTON WITH ACTIVE STATE
# =========================================================
class NavButton:
    """Glassmorphism nav button dengan active/inactive state."""

    def __init__(self, parent, text: str, icon: str = "",
                 command: Optional[Callable] = None, active: bool = False):
        self.active  = active
        self.command = command
        self._bg_active  = C_SURFACE2
        self._bg_normal  = C_SURFACE3
        self._fg_active  = C_LAVENDER
        self._fg_normal  = C_TEXT2

        self.frame = tk.Frame(parent, bg=self._bg_normal,
                              highlightthickness=1,
                              highlightbackground=C_BORDER,
                              cursor="hand2")
        self.lbl = tk.Label(
            self.frame,
            text=f"{icon}  {text}" if icon else text,
            bg=self._bg_normal, fg=self._fg_normal,
            font=(FONT_UI[0], 11), padx=14, pady=8,
            cursor="hand2",
        )
        self.lbl.pack()

        for w in (self.frame, self.lbl):
            w.bind("<Button-1>", self._click)
            w.bind("<Enter>",    self._hover)
            w.bind("<Leave>",    self._unhover)

        if active:
            self._set_active(True)

    def _click(self, _e):
        if self.command:
            self.command()

    def _hover(self, _e):
        if not self.active:
            self.frame.config(highlightbackground=C_LAVENDER)
            self.lbl.config(fg=C_TEXT)

    def _unhover(self, _e):
        if not self.active:
            self.frame.config(highlightbackground=C_BORDER)
            self.lbl.config(fg=self._fg_normal)

    def _set_active(self, is_active: bool):
        self.active = is_active
        if is_active:
            self.frame.config(bg=self._bg_active, highlightbackground=C_LAVENDER)
            self.lbl.config(bg=self._bg_active, fg=self._fg_active,
                            font=(FONT_UI[0], 11, "bold"))
        else:
            self.frame.config(bg=self._bg_normal, highlightbackground=C_BORDER)
            self.lbl.config(bg=self._bg_normal, fg=self._fg_normal,
                            font=(FONT_UI[0], 11))

    def set_active(self, val: bool):
        self._set_active(val)

    def pack(self, **kw):
        self.frame.pack(**kw)

    def grid(self, **kw):
        self.frame.grid(**kw)


# =========================================================
# STAT CARD
# =========================================================
def stat_card(parent, title: str, value: str,
              color=None, width: int = 140) -> dict:
    """Compact glassmorphism stat card. Returns dict dengan 'frame' dan 'val_lbl'."""
    color = color or C_TEAL_LT
    outer, inner = glass_card(parent, inner_bg=C_SURFACE2)
    inner.config(padx=12, pady=10, width=width)
    inner.pack_propagate(False)
    tk.Label(inner, text=title, bg=C_SURFACE2, fg=C_TEXT_DIM,
             font=FONT_UI_XS).pack(anchor="w")
    val_lbl = tk.Label(inner, text=value, bg=C_SURFACE2, fg=color,
                       font=FONT_TITLE)
    val_lbl.pack(anchor="w", pady=(2, 0))
    return {"frame": outer, "val_lbl": val_lbl}


# =========================================================
# LOADING OVERLAY (existing-compatible)
# =========================================================
def show_loading(parent, message: str = "Memuat data...") -> tk.Toplevel:
    overlay = tk.Toplevel(parent)
    overlay.overrideredirect(True)
    overlay.configure(bg=C_BG)
    overlay.attributes("-alpha", 0.93)
    overlay.grab_set()
    parent.update_idletasks()
    pw = parent.winfo_width()
    ph = parent.winfo_height()
    px = parent.winfo_rootx()
    py = parent.winfo_rooty()
    ow, oh = 380, 140
    overlay.geometry(f"{ow}x{oh}+{px+(pw-ow)//2}+{py+(ph-oh)//2}")

    accent_strip(overlay, h=4).pack(fill="x")
    inner = tk.Frame(overlay, bg=C_BG, padx=30, pady=20)
    inner.pack(fill="both", expand=True)

    spinners = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
    spin_lbl = tk.Label(inner, text=spinners[0], bg=C_BG, fg=C_LAVENDER,
                        font=(_FONT_DISPLAY_NAME, 22))
    spin_lbl.pack()
    tk.Label(inner, text=message, bg=C_BG, fg=C_TEXT, font=FONT_UI).pack(pady=(8, 0))
    tk.Label(inner, text="Mohon tunggu...", bg=C_BG, fg=C_TEXT_DIM,
             font=FONT_UI_SM).pack()
    accent_strip(overlay, h=4).pack(fill="x", side="bottom")

    _idx = [0]
    def _animate():
        if overlay.winfo_exists():
            _idx[0] = (_idx[0]+1) % len(spinners)
            spin_lbl.config(text=spinners[_idx[0]])
            overlay.after(80, _animate)
    _animate()
    overlay.update()
    return overlay


def hide_loading(overlay) -> None:
    try:
        if overlay and overlay.winfo_exists():
            overlay.grab_release()
            overlay.destroy()
    except Exception:
        pass


# =========================================================
# LOGO HELPERS
# =========================================================
def _make_app_icon(root_win):
    """Set window icon dari app.ico jika ada."""
    from PIL import Image, ImageTk
    ico_path = os.path.join(BASE_DIR, "app.ico")
    try:
        if os.path.isfile(ico_path):
            img   = Image.open(ico_path)
            photo = ImageTk.PhotoImage(img)
            root_win.iconphoto(True, photo)
            root_win._icon_ref = photo
    except Exception:
        pass


def _logo_label(parent, bg, size=32) -> tk.Label:
    from PIL import Image, ImageTk
    ico_path = os.path.join(BASE_DIR, "app.ico")
    try:
        img   = Image.open(ico_path).resize((size, size))
        photo = ImageTk.PhotoImage(img)
        lbl   = tk.Label(parent, image=photo, bg=bg, cursor="hand2")
        lbl.image = photo
        return lbl
    except Exception:
        return tk.Label(parent, text="◆", bg=bg,
                        fg=C_LAVENDER,
                        font=(_FONT_DISPLAY_NAME, max(10, size // 3)))


# =========================================================
# BRAND / CONLECTA WORDMARK
# =========================================================
def conlecta_wordmark(parent, bg=C_SURFACE, compact=False) -> tk.Frame:
    """Logo + wordmark block untuk topbar atau panel."""
    fr = tk.Frame(parent, bg=bg)

    # Icon box (purple gradient faked via colored label)
    icon_sz = 28 if compact else 36
    icon_box = tk.Label(
        fr, text="C",
        bg=C_LAVENDER_DK, fg=C_WHITE,
        font=(_FONT_DISPLAY_NAME, icon_sz // 2 + 2, "bold"),
        width=2, relief="flat",
        highlightthickness=2,
        highlightbackground=C_LAVENDER,
    )
    icon_box.pack(side="left", padx=(0, 8))

    txt_fr = tk.Frame(fr, bg=bg)
    txt_fr.pack(side="left")
    size_title = 12 if compact else 15
    tk.Label(txt_fr, text="CONLECTA", bg=bg, fg=C_TEXT,
             font=(_FONT_DISPLAY_NAME, size_title, "bold"),
             letter_spacing=2 if hasattr(tk.Label, "letter_spacing") else 0
             ).pack(anchor="w")
    if not compact:
        tk.Label(txt_fr, text="POINT OF SALE", bg=bg, fg=C_TEXT3,
                 font=(FONT_UI_XS[0], 7), letter_spacing=3
                 ).pack(anchor="w")
    return fr


# =========================================================
# BACKGROUND HELPER (existing compat)
# =========================================================
_BG_PHOTO = None

def apply_mesh_background(widget, width=1400, height=900):
    """
    Existing code calls this — kita pasang VoidCrystalBackground.
    Return canvas (bisa di-ignore, existing code cuma cek None).
    """
    bg_obj = VoidCrystalBackground(widget, width, height)
    canvas = bg_obj.attach()
    widget._void_bg = bg_obj   # keep reference
    return canvas


# =========================================================
# MISC HELPERS (existing compat)
# =========================================================
def format_rupiah(value) -> str:
    try:
        return f"Rp {int(value):,.0f}".replace(",", ".")
    except Exception:
        return f"Rp {value}"


def format_datetime(datetime_str: str) -> str:
    from datetime import datetime as _dt
    try:
        dt = _dt.fromisoformat(datetime_str)
        return dt.strftime(f"{dt.strftime('%A')} - %d-%m-%Y %H:%M")
    except Exception:
        return datetime_str


def calc_qris_fee(amount: int) -> int:
    return round(amount * 0.007)


def calc_net_amount(amount: int) -> int:
    return amount - calc_qris_fee(amount)
