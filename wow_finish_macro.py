"""
WoW character-creation "Finish" spam macro (Windows only).

Loop:
  * If the population-imbalance popup ("Okay" button) is visible -> click Okay.
  * Else if the red "Finish" button (bottom right) is enabled -> click Finish.
  * Else (neither visible for longer than GRACE_SECONDS) -> pause PAUSE_SECONDS.

Detection is pixel-colour based. Positions are expressed in a 2000x1125 reference
frame and scaled by the game's client-area height, so any 16:9 / 21:9 resolution
works as long as the in-game UI scale matches the reference screenshots.

Hotkeys (global, polled):  F8 = pause / resume,  F10 = quit.

Usage:
  python wow_finish_macro.py            # run the macro
  python wow_finish_macro.py --debug    # one screenshot of the game, annotated, saved to debug.png
  python wow_finish_macro.py --test a.png b.png   # run detection on image files
"""

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# DPI awareness MUST be set before any capture / window-geometry call, otherwise
# capture coordinates and click coordinates live in different spaces at >100% scaling.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor DPI aware
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import numpy as np
from PIL import Image, ImageDraw, ImageGrab

# --------------------------------------------------------------------------- settings
PAUSE_SECONDS = 10.0        # pause when neither button is visible
GRACE_SECONDS = 1.5         # "neither visible" must last this long before pausing
                            # (right after a Finish click the button greys out before the popup arrives)
AFTER_FINISH_CLICK = 0.5    # wait after clicking Finish
AFTER_OKAY_CLICK = 0.4      # wait after clicking Okay
POLL_INTERVAL = 0.15        # idle loop interval
START_DELAY = 3.0           # time to alt-tab into WoW after starting
ONLY_WHEN_WOW_FOCUSED = True  # never click while another window is in front

VK_F7, VK_F8, VK_F10 = 0x76, 0x77, 0x79

# .env next to this script: line 1 = Telegram bot token, line 2 = chat id
# (plain values or KEY=value lines both work).
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

# --------------------------------------------------------------------------- geometry
REF_H = 1125.0  # reference client height the offsets below were measured on (2000x1125)

# Regions: (anchor, (x0, y0, x1, y1)) in reference pixels relative to the anchor.
#   "br" = bottom-right corner of the client area, "c" = centre of the client area.
REGIONS = {
    "finish":     ("br", (-255, -70, -60, -40)),    # red Finish button body
    "okay":       ("c",  (-95, 22.5, 95, 43.5)),     # red Okay button body
    "popup_left": ("c",  (-295, 22.5, -120, 49.5)),  # popup backdrop, left of Okay
    "popup_top":  ("c",  (-295, -54.5, 295, -44.5)), # popup backdrop, above the message
    "popup_text": ("c",  (-240, -44.5, 240, 2.5)),   # yellow message text band
    # Login screen (shown after "You have been disconnected from the server"):
    # stacked red Menu / Create Account / Quit buttons in the bottom-right corner.
    "login_menu":   ("br", (-195, -147, -40, -136)),
    "login_create": ("br", (-195, -111, -40, -98)),
}
CLICK_POINTS = {
    "finish": ("br", (-157, -56)),
    "okay":   ("c",  (-1, 32.5)),
}


def _to_px(anchor, x, y, w, h):
    s = h / REF_H
    if anchor == "br":
        return w + x * s, h + y * s
    return w / 2 + x * s, h / 2 + y * s


def region_box(name, w, h):
    anchor, (x0, y0, x1, y1) = REGIONS[name]
    ax0, ay0 = _to_px(anchor, x0, y0, w, h)
    ax1, ay1 = _to_px(anchor, x1, y1, w, h)
    return int(round(ax0)), int(round(ay0)), int(round(ax1)), int(round(ay1))


def click_point(name, w, h):
    anchor, (x, y) = CLICK_POINTS[name]
    px, py = _to_px(anchor, x, y, w, h)
    return int(round(px)), int(round(py))


# --------------------------------------------------------------------------- detection
def _pixels(img, box):
    x0, y0, x1, y1 = box
    return img[max(y0, 0):y1, max(x0, 0):x1].reshape(-1, 3).astype(np.int32)


def red_ratio(p):
    r, g, b = p[:, 0], p[:, 1], p[:, 2]
    return float(((r >= 70) & (g < 45) & (b < 40) & (r > 2.5 * np.maximum(g, b))).mean())


def dark_ratio(p):
    return float((p.max(axis=1) < 75).mean())


def yellow_ratio(p):
    r, g, b = p[:, 0], p[:, 1], p[:, 2]
    return float(((r > 170) & (g > 130) & (b < 100) & (r - b > 100)).mean())


def analyze(img):
    """img: HxWx3 uint8 RGB array of the game client area. Returns dict with scores + decisions."""
    h, w = img.shape[:2]
    px = {name: _pixels(img, region_box(name, w, h)) for name in REGIONS}
    s = {
        "finish_red": red_ratio(px["finish"]),
        "okay_red": red_ratio(px["okay"]),
        "popup_left_dark": dark_ratio(px["popup_left"]),
        "popup_top_dark": dark_ratio(px["popup_top"]),
        "popup_text_yellow": yellow_ratio(px["popup_text"]),
        "login_menu_red": red_ratio(px["login_menu"]),
        "login_create_red": red_ratio(px["login_create"]),
    }
    # Login screen = we were disconnected. Checked first: its Quit button sits
    # where Finish is, so Finish/Okay must never be clicked on this screen.
    s["disconnected"] = s["login_menu_red"] > 0.35 and s["login_create_red"] > 0.35
    backdrop = s["popup_left_dark"] > 0.6 and s["popup_top_dark"] > 0.6
    text = s["popup_text_yellow"] > 0.01
    s["okay"] = s["okay_red"] > 0.5 and (backdrop or (text and max(s["popup_left_dark"], s["popup_top_dark"]) > 0.4))
    s["finish"] = s["finish_red"] > 0.5
    if s["disconnected"]:
        s["okay"] = s["finish"] = False
    return s


# --------------------------------------------------------------------------- win32
user32 = ctypes.windll.user32
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004


def find_wow_window():
    hwnd = user32.FindWindowW("GxWindowClass", None)  # WoW's window class
    if not hwnd:
        hwnd = user32.FindWindowW(None, "World of Warcraft")
    return hwnd or None


def client_rect(hwnd):
    """Screen rect (left, top, right, bottom) of the game's client area, or the primary screen."""
    if hwnd:
        rc = wt.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(rc))
        pt = wt.POINT(0, 0)
        user32.ClientToScreen(hwnd, ctypes.byref(pt))
        if rc.right > 0 and rc.bottom > 0:
            return pt.x, pt.y, pt.x + rc.right, pt.y + rc.bottom
    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def grab(rect):
    return np.asarray(ImageGrab.grab(bbox=rect, all_screens=True).convert("RGB"))


def click(x, y):
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.04)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.04)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


class Hotkeys:
    def __init__(self):
        self._down = {VK_F7: False, VK_F8: False, VK_F10: False}

    def pressed(self, vk):
        down = bool(user32.GetAsyncKeyState(vk) & 0x8000)
        edge = down and not self._down[vk]
        self._down[vk] = down
        return edge


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


# --------------------------------------------------------------------------- telegram
def load_telegram_env(path=ENV_PATH):
    """Return (token, chat_id) from .env, or (None, None) if missing/incomplete."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            lines = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
    except OSError:
        return None, None

    def value(line):
        if "=" in line:
            line = line.split("=", 1)[1]
        return line.strip().strip("'\"")

    if len(lines) < 2:
        return None, None
    return value(lines[0]) or None, value(lines[1]) or None


class Telegram:
    def __init__(self, path=ENV_PATH):
        self.token, self.chat_id = load_telegram_env(path)

    @property
    def enabled(self):
        return bool(self.token and self.chat_id)

    def _send(self, text):
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": self.chat_id, "text": text,
            "parse_mode": "HTML", "disable_web_page_preview": "true",
        }).encode()
        try:
            with urllib.request.urlopen(url, data=data, timeout=10) as r:
                ok = json.load(r).get("ok", False)
            log("Telegram: message sent." if ok else "Telegram: API returned ok=false.")
            return ok
        except urllib.error.HTTPError as e:
            # Never log the URL: it contains the bot token.
            try:
                desc = json.load(e).get("description", "")
            except Exception:
                desc = ""
            log(f"Telegram error: HTTP {e.code} {desc}")
        except Exception as e:
            log(f"Telegram error: {type(e).__name__}")
        return False

    def send(self, text, wait=False):
        """Send in a background thread; wait=True blocks (max ~12 s) until done."""
        if not self.enabled:
            log("Telegram: .env missing or incomplete - message skipped.")
            return
        t = threading.Thread(target=self._send, args=(text,), daemon=True)
        t.start()
        if wait:
            t.join(12)


def fmt_duration(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h} sa {m} dk {s} sn" if h else f"{m} dk {s} sn"


def test_message():
    return (
        "🧪 <b>WoW Telegram bildirim test</b>\n"
        "✅ Bildirimler çalışıyor.\n"
        f"🕒 {time.strftime('%d.%m.%Y %H:%M:%S')}"
    )


def created_message(elapsed, finish_clicks, okay_clicks):
    return (
        "🎉 <b>WoW karakter oluşturuldu!</b>\n"
        "━━━━━━━━━━━━━━━\n"
        f"⏱ Süre: {fmt_duration(elapsed)}\n"
        f"🖱 Finish tıklama: {finish_clicks}\n"
        f"✅ Okay tıklama: {okay_clicks}\n"
        f"🕒 {time.strftime('%d.%m.%Y %H:%M:%S')}\n"
        "━━━━━━━━━━━━━━━\n"
        f"ℹ️ Finish/Okay {PAUSE_SECONDS:.0f} sn boyunca görünmedi, makro durdu."
    )


def disconnected_message(elapsed, finish_clicks, okay_clicks):
    return (
        "🚨 <b>WoW: Sunucu bağlantısı koptu!</b>\n"
        "━━━━━━━━━━━━━━━\n"
        "🔌 Hesaptan çıkış yapıldı (disconnected).\n"
        "🛠 <b>İşlem gerekli:</b> tekrar giriş yap ve makroyu yeniden başlat.\n"
        "━━━━━━━━━━━━━━━\n"
        f"⏱ Çalışma süresi: {fmt_duration(elapsed)}\n"
        f"🖱 Finish tıklama: {finish_clicks}\n"
        f"✅ Okay tıklama: {okay_clicks}\n"
        f"🕒 {time.strftime('%d.%m.%Y %H:%M:%S')}\n"
        "🛑 Makro durduruldu."
    )


# --------------------------------------------------------------------------- modes
def run():
    keys = Hotkeys()
    tg = Telegram()
    paused = False
    state = {"quit": False}

    def wait(seconds):
        """Sleep while still reacting to hotkeys. Returns False if the user quit."""
        nonlocal paused
        end = time.time() + seconds
        while time.time() < end or paused:
            if keys.pressed(VK_F10):
                state["quit"] = True
                return False
            if keys.pressed(VK_F7):
                log("F7: sending Telegram test message...")
                tg.send(test_message())
            if keys.pressed(VK_F8):
                paused = not paused
                log("PAUSED (F8 to resume)" if paused else "RESUMED")
                if not paused:
                    return True
            time.sleep(0.03)
        return True

    log("Telegram: " + ("enabled (.env loaded)" if tg.enabled else "DISABLED (.env missing or incomplete)"))
    log(f"Starting in {START_DELAY:.0f}s - switch to WoW. F7 = Telegram test, F8 = pause/resume, F10 = quit.")
    if not wait(START_DELAY):
        return

    started = time.time()
    last_seen = time.time()
    finish_clicks = okay_clicks = 0
    focus_warned = False
    paused_once = False  # True after a full PAUSE_SECONDS wait with neither button visible

    while not state["quit"]:
        hwnd = find_wow_window()
        if ONLY_WHEN_WOW_FOCUSED and hwnd and user32.GetForegroundWindow() != hwnd:
            if not focus_warned:
                log("WoW is not the active window - waiting (no clicks).")
                focus_warned = True
            last_seen = time.time()
            if not wait(0.5):
                break
            continue
        focus_warned = False

        rect = client_rect(hwnd)
        w, h = rect[2] - rect[0], rect[3] - rect[1]
        s = analyze(grab(rect))
        if s["okay"] or s["finish"]:
            paused_once = False

        if s["disconnected"]:
            log("Disconnected from the server (login screen) - stopping.")
            tg.send(disconnected_message(time.time() - started, finish_clicks, okay_clicks), wait=True)
            break
        elif s["okay"]:
            x, y = click_point("okay", w, h)
            click(rect[0] + x, rect[1] + y)
            okay_clicks += 1
            log(f"Okay clicked   (#{okay_clicks})")
            last_seen = time.time()
            wait(AFTER_OKAY_CLICK)
        elif s["finish"]:
            x, y = click_point("finish", w, h)
            click(rect[0] + x, rect[1] + y)
            finish_clicks += 1
            if finish_clicks % 10 == 1:
                log(f"Finish clicked (#{finish_clicks})")
            last_seen = time.time()
            wait(AFTER_FINISH_CLICK)
        elif paused_once:
            # Still nothing after the full pause -> the character was most likely created.
            log("Still no Finish/Okay after the pause - character created? Stopping.")
            tg.send(created_message(time.time() - started, finish_clicks, okay_clicks), wait=True)
            break
        elif time.time() - last_seen >= GRACE_SECONDS:
            log(f"Neither Finish nor Okay found - pausing {PAUSE_SECONDS:.0f}s.")
            if not wait(PAUSE_SECONDS):
                break
            paused_once = True
            last_seen = time.time()
        else:
            wait(POLL_INTERVAL)

    log(f"Stopped. Finish clicks: {finish_clicks}, Okay clicks: {okay_clicks}")


def annotate(img, s, out_path):
    h, w = img.shape[:2]
    pil = Image.fromarray(img)
    d = ImageDraw.Draw(pil)
    for name in REGIONS:
        d.rectangle(region_box(name, w, h), outline=(0, 255, 0), width=2)
    for name in CLICK_POINTS:
        x, y = click_point(name, w, h)
        d.ellipse((x - 6, y - 6, x + 6, y + 6), outline=(255, 0, 255), width=3)
    d.text((10, 10), " | ".join(f"{k}={v:.2f}" if isinstance(v, float) else f"{k}={v}" for k, v in s.items()),
           fill=(255, 255, 0))
    pil.save(out_path)


def fmt(s):
    return (f"finish={s['finish']!s:5} okay={s['okay']!s:5} disconnected={s['disconnected']!s:5} | "
            + " ".join(f"{k}={v:.2f}" for k, v in s.items() if isinstance(v, float)))


def debug():
    hwnd = find_wow_window()
    rect = client_rect(hwnd)
    log(f"WoW window: {'found' if hwnd else 'NOT found (using primary screen)'}; client rect {rect}")
    img = grab(rect)
    s = analyze(img)
    print(fmt(s))
    if img.max() < 10:
        print("WARNING: captured image is black - switch WoW to Windowed (Fullscreen) mode.")
    annotate(img, s, "debug.png")
    log("Annotated screenshot saved to debug.png")


def test(paths):
    for p in paths:
        img = np.asarray(Image.open(p).convert("RGB"))
        print(f"{p}: {fmt(analyze(img))}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--debug", action="store_true", help="annotate one live screenshot to debug.png and exit")
    ap.add_argument("--test", nargs="+", metavar="IMAGE", help="run detection on image files and exit")
    a = ap.parse_args()
    if sys.platform != "win32":
        sys.exit("Windows only.")
    if a.test:
        test(a.test)
    elif a.debug:
        debug()
    else:
        try:
            run()
        except KeyboardInterrupt:
            log("Stopped (Ctrl+C).")
