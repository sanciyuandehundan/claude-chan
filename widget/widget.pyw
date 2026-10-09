"""Claude 酱额度挂件：贴在 Claude 桌面版窗口右下角的像素小人和气泡。

- 额度来自 ~/.claude/clawd-widget/usage.json，由同一个插件的 hooks 在每个 Code 会话里写入。
- 只跟着 Claude 窗口走：Claude 在前台时置顶，切到别的软件就退到 Claude 正上方，
  最小化时隐藏。透明像素不接鼠标。
- 左键点：换一句台词 + 跳一下 + 音效；按住拖动：挪位置；右键：菜单。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import datetime as dt
import json
import math
import os
import pathlib
import random
import sys
import time
import traceback
from collections import deque

from PIL import Image, ImageDraw, ImageFont

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# 代码在插件目录里，数据（额度、设置、日志、音效）放用户目录下，插件更新不会丢
DATA = pathlib.Path(os.environ.get("CLAWD_WIDGET_DATA") or (pathlib.Path.home() / ".claude" / "clawd-widget"))
DATA.mkdir(parents=True, exist_ok=True)

import art  # noqa: E402
import audio  # noqa: E402
import lines  # noqa: E402
import sounds  # noqa: E402

USAGE_FILE = DATA / "usage.json"
CONFIG_FILE = DATA / "config.json"
LOG_FILE = DATA / "widget.log"
FONTS = pathlib.Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"

DEFAULT_CONFIG = {"offset": [0, 0], "muted": False, "bubble": True, "scale": 2, "volume": 0.1}


def log(msg: str) -> None:
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 256_000:
            LOG_FILE.unlink()
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"{dt.datetime.now():%m-%d %H:%M:%S} {msg}\n")
    except OSError:
        pass


# ---------------------------------------------------------------- Win32

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

LRESULT = ctypes.c_ssize_t
UINT_PTR = ctypes.c_size_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
WINEVENTPROC = ctypes.WINFUNCTYPE(None, wt.HANDLE, wt.DWORD, wt.HWND, wt.LONG, wt.LONG, wt.DWORD, wt.DWORD)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.UINT), ("style", wt.UINT), ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE),
        ("hIcon", wt.HICON), ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR), ("hIconSm", wt.HICON),
    ]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


class TRACKMOUSEEVENT(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("dwFlags", wt.DWORD), ("hwndTrack", wt.HWND), ("dwHoverTime", wt.DWORD)]


def _sig(fn, res, *args):
    fn.restype = res
    fn.argtypes = args


_sig(user32.DefWindowProcW, LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
_sig(user32.RegisterClassExW, wt.ATOM, ctypes.POINTER(WNDCLASSEXW))
_sig(user32.CreateWindowExW, wt.HWND, wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
     ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID)
_sig(user32.ShowWindow, wt.BOOL, wt.HWND, ctypes.c_int)
_sig(user32.SetWindowPos, wt.BOOL, wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT)
_sig(user32.UpdateLayeredWindow, wt.BOOL, wt.HWND, wt.HDC, ctypes.POINTER(wt.POINT), ctypes.POINTER(wt.SIZE), wt.HDC,
     ctypes.POINTER(wt.POINT), wt.COLORREF, ctypes.POINTER(BLENDFUNCTION), wt.DWORD)
_sig(user32.GetDC, wt.HDC, wt.HWND)
_sig(gdi32.CreateCompatibleDC, wt.HDC, wt.HDC)
_sig(gdi32.CreateDIBSection, wt.HBITMAP, wt.HDC, ctypes.c_void_p, wt.UINT, ctypes.POINTER(ctypes.c_void_p), wt.HANDLE,
     wt.DWORD)
_sig(gdi32.SelectObject, wt.HGDIOBJ, wt.HDC, wt.HGDIOBJ)
_sig(gdi32.DeleteObject, wt.BOOL, wt.HGDIOBJ)
_sig(user32.SetTimer, UINT_PTR, wt.HWND, UINT_PTR, wt.UINT, ctypes.c_void_p)
_sig(user32.GetMessageW, wt.BOOL, ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT)
_sig(user32.TranslateMessage, wt.BOOL, ctypes.POINTER(wt.MSG))
_sig(user32.DispatchMessageW, LRESULT, ctypes.POINTER(wt.MSG))
_sig(user32.PostQuitMessage, None, ctypes.c_int)
_sig(user32.PostMessageW, wt.BOOL, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
_sig(user32.GetForegroundWindow, wt.HWND)
_sig(user32.SetForegroundWindow, wt.BOOL, wt.HWND)
_sig(user32.GetWindowThreadProcessId, wt.DWORD, wt.HWND, ctypes.POINTER(wt.DWORD))
_sig(user32.IsWindow, wt.BOOL, wt.HWND)
_sig(user32.IsWindowVisible, wt.BOOL, wt.HWND)
_sig(user32.IsIconic, wt.BOOL, wt.HWND)
_sig(user32.GetWindow, wt.HWND, wt.HWND, wt.UINT)
_sig(user32.GetWindowLongW, wt.LONG, wt.HWND, ctypes.c_int)
_sig(user32.EnumWindows, wt.BOOL, WNDENUMPROC, wt.LPARAM)
_sig(user32.GetClassNameW, ctypes.c_int, wt.HWND, wt.LPWSTR, ctypes.c_int)
_sig(user32.GetDpiForWindow, wt.UINT, wt.HWND)
_sig(user32.SetCapture, wt.HWND, wt.HWND)
_sig(user32.ReleaseCapture, wt.BOOL)
_sig(user32.GetCursorPos, wt.BOOL, ctypes.POINTER(wt.POINT))
_sig(user32.LoadCursorW, wt.HANDLE, wt.HINSTANCE, ctypes.c_void_p)
_sig(user32.SetCursor, wt.HANDLE, wt.HANDLE)
_sig(user32.TrackMouseEvent, wt.BOOL, ctypes.POINTER(TRACKMOUSEEVENT))
_sig(user32.CreatePopupMenu, wt.HMENU)
_sig(user32.AppendMenuW, wt.BOOL, wt.HMENU, wt.UINT, UINT_PTR, wt.LPCWSTR)
_sig(user32.TrackPopupMenu, ctypes.c_int, wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND,
     ctypes.c_void_p)
_sig(user32.DestroyMenu, wt.BOOL, wt.HMENU)
_sig(user32.SetWinEventHook, wt.HANDLE, wt.DWORD, wt.DWORD, wt.HMODULE, WINEVENTPROC, wt.DWORD, wt.DWORD, wt.DWORD)
_sig(user32.SetProcessDpiAwarenessContext, wt.BOOL, ctypes.c_void_p)
_sig(kernel32.GetModuleHandleW, wt.HMODULE, wt.LPCWSTR)
_sig(kernel32.CreateMutexW, wt.HANDLE, ctypes.c_void_p, wt.BOOL, wt.LPCWSTR)
_sig(kernel32.OpenProcess, wt.HANDLE, wt.DWORD, wt.BOOL, wt.DWORD)
_sig(kernel32.QueryFullProcessImageNameW, wt.BOOL, wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD))
_sig(kernel32.CloseHandle, wt.BOOL, wt.HANDLE)
_sig(dwmapi.DwmGetWindowAttribute, ctypes.c_long, wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD)

WS_POPUP = 0x80000000
WS_EX_LAYERED, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE, WS_EX_TOPMOST = 0x80000, 0x80, 0x08000000, 0x8
WM_DESTROY, WM_TIMER, WM_MOUSEMOVE = 0x0002, 0x0113, 0x0200
WM_LBUTTONDOWN, WM_LBUTTONUP, WM_RBUTTONUP = 0x0201, 0x0202, 0x0205
WM_MOUSEACTIVATE, WM_SETCURSOR, WM_MOUSELEAVE, WM_NULL = 0x0021, 0x0020, 0x02A3, 0x0000
MA_NOACTIVATE = 3
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE = 0x1, 0x2, 0x4, 0x10
HWND_TOP, HWND_TOPMOST, HWND_NOTOPMOST = 0, -1, -2
GW_HWNDPREV, GWL_EXSTYLE = 3, -20
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
ULW_ALPHA, AC_SRC_ALPHA = 2, 1
DWMWA_EXTENDED_FRAME_BOUNDS, DWMWA_CLOAKED = 9, 14
EVENT_SYSTEM_FOREGROUND, WINEVENT_OUTOFCONTEXT = 3, 0
TME_LEAVE = 2
IDC_HAND = 32649
MF_STRING, MF_CHECKED, MF_SEPARATOR = 0x0, 0x8, 0x800
TPM_RETURNCMD, TPM_RIGHTBUTTON = 0x100, 0x2


def pid_of(hwnd) -> int:
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def exe_of(pid: int) -> str:
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(520)
        n = wt.DWORD(520)
        return buf.value if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else ""
    finally:
        kernel32.CloseHandle(h)


def find_claude():
    """Claude 桌面版的主窗口（Electron，进程名 claude.exe），挑可见的最大那个。"""
    found = []

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value != "Chrome_WidgetWin_1":
            return True
        pid = pid_of(hwnd)
        if not exe_of(pid).lower().endswith("\\claude.exe"):
            return True
        r = frame_rect(hwnd)
        if r:
            found.append(((r[2] - r[0]) * (r[3] - r[1]), hwnd, pid))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    if not found:
        return None, 0
    _, hwnd, pid = max(found)
    return hwnd, pid


def frame_rect(hwnd):
    r = wt.RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)) != 0:
        return None
    return r.left, r.top, r.right, r.bottom


def is_cloaked(hwnd) -> bool:
    v = ctypes.c_int(0)
    dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(v), ctypes.sizeof(v))
    return v.value != 0


def lparam_xy(lp):
    return ctypes.c_short(lp & 0xFFFF).value, ctypes.c_short((lp >> 16) & 0xFFFF).value


def blit(dst: Image.Image, src: Image.Image, x: int, y: int) -> None:
    """alpha_composite，但允许贴到画布外面（自动裁掉）。"""
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dst.width, x + src.width), min(dst.height, y + src.height)
    if x1 <= x0 or y1 <= y0:
        return
    part = src.crop((x0 - x, y0 - y, x1 - x, y1 - y))
    dst.alpha_composite(part, (x0, y0))


# ---------------------------------------------------------------- 额度数据

def parse_time(s):
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def fmt_hms(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def fmt_dh(sec: float) -> str:
    sec = max(0, int(sec))
    if sec >= 86400:
        return f"{sec // 86400}天{sec % 86400 // 3600}时"
    if sec >= 3600:
        return f"{sec // 3600}时{sec % 3600 // 60:02d}分"
    return f"{max(1, sec // 60)}分"


def fmt_human(sec: float) -> str:
    sec = max(0, int(sec))
    if sec < 3600:
        return f"{max(1, sec // 60)} 分钟"
    return f"{sec // 3600} 小时 {sec % 3600 // 60} 分"


class Usage:
    """读 usage.json；窗口过了重置时间但还没刷新时按 0% 算。"""

    def __init__(self) -> None:
        self.mtime = 0.0
        self.data: dict | None = None
        self.checked = 0.0

    def poll(self, now: float) -> bool:
        if now - self.checked < 2:
            return False
        self.checked = now
        try:
            m = USAGE_FILE.stat().st_mtime
        except OSError:
            return False
        if m == self.mtime:
            return False
        try:
            self.data = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
            self.mtime = m
            return True
        except (OSError, ValueError):
            return False

    def windows(self):
        """[(短名, 已用%, 距重置秒数 或 None)]，5 小时在前。"""
        if not self.data:
            return []
        now = dt.datetime.now(dt.timezone.utc)
        out = []
        for w in self.data.get("windows") or []:
            label = str(w.get("label", ""))
            pct = float(w.get("percentUsed") or 0)
            reset = parse_time(w.get("resetsAt"))
            left = (reset - now).total_seconds() if reset else None
            if left is not None and left <= 0:
                pct, left = 0.0, None
            if label.startswith("5-hour"):
                name = "5h"
            elif label.endswith("all models"):
                name = "本周"
            else:
                name = label.split("· ")[-1]
            out.append((name, pct, left))
        out.sort(key=lambda t: {"5h": 0, "本周": 1}.get(t[0], 2))
        return out

    def age(self) -> float | None:
        if not self.data:
            return None
        t = parse_time(self.data.get("fetchedAt"))
        return (dt.datetime.now(dt.timezone.utc) - t).total_seconds() if t else None

    def ctx(self) -> dict:
        ws = {n: (p, left) for n, p, left in self.windows()}
        five, week = ws.get("5h"), ws.get("本周")
        return {
            "p5": round(five[0]) if five else None,
            "left5": round(100 - five[0]) if five else None,
            "reset5": fmt_human(five[1]) if five and five[1] else "一会儿",
            "pw": round(week[0]) if week else None,
            "leftw": round(100 - week[0]) if week else None,
        }


# ---------------------------------------------------------------- 绘制

CREAM = (255, 249, 241, 255)
BROWN = (92, 46, 34, 255)
INK = (74, 36, 24, 255)
RED = (226, 76, 52, 255)
SOFT = (126, 86, 70, 255)
BAR_BG = (241, 226, 214, 255)
CHIP = (217, 119, 87, 255)


class Painter:
    """按 DPI 缩放后的尺寸画气泡；字体、气泡底图按尺寸缓存。"""

    def __init__(self, s: float) -> None:
        self.s = s
        f = lambda name, px: ImageFont.truetype(str(FONTS / name), max(8, round(px * s)))  # noqa: E731
        self.f_phrase = f("msyhbd.ttc", 16)
        self.f_timer = f("segoeuib.ttf", 22)
        self.f_chip = f("msyhbd.ttc", 12)
        self.f_small = f("msyh.ttc", 12)
        self.f_smallb = f("msyhbd.ttc", 12)
        self.f_tiny = f("msyh.ttc", 11)
        self.bw = round(272 * s)
        self._shape_cache: dict = {}
        self._digit_cache: dict = {}

    def px(self, v: float) -> int:
        return round(v * self.s)

    def wrap(self, text: str, font, width: int, max_lines: int = 3) -> list[str]:
        out, cur = [], ""
        for ch in text:
            # 句末标点挂在行尾，不让它单独起一行
            if font.getlength(cur + ch) <= width or (cur and ch in "。，、！？；：…）」』”’~～.,!?"):
                cur += ch
                continue
            out.append(cur)
            cur = ch.lstrip()
            if len(out) == max_lines:
                out[-1] = out[-1][:-1] + "…"
                return out
        if cur:
            out.append(cur)
        return out

    def shape(self, w: int, h: int) -> Image.Image:
        key = (w, h)
        if key not in self._shape_cache:
            ss = 3
            im = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            bd = self.px(3.5) * ss
            d.rounded_rectangle((bd // 2, bd // 2, w * ss - bd // 2 - 1, h * ss - bd // 2 - 1),
                                radius=self.px(30) * ss, fill=CREAM, outline=BROWN, width=bd)
            self._shape_cache[key] = im.resize((w, h), Image.LANCZOS)
        return self._shape_cache[key]

    def trail(self) -> Image.Image:
        """思考气泡下面那两个小圆圈。"""
        key = "trail"
        if key not in self._shape_cache:
            ss = 3
            w, h = self.px(46), self.px(46)
            im = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            bd = self.px(3) * ss
            for cx, cy, r in ((14, 12, 10), (36, 34, 6)):
                cx, cy, r = self.px(cx) * ss, self.px(cy) * ss, self.px(r) * ss
                d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=CREAM, outline=BROWN, width=bd)
            self._shape_cache[key] = im.resize((w, h), Image.LANCZOS)
        return self._shape_cache[key]

    def digits(self, text: str, cell: int, hot: bool) -> Image.Image:
        key = (text, cell, hot)
        if key not in self._digit_cache:
            im = art.pixel_text(text, (226, 70, 56) if hot else (238, 118, 50))
            self._digit_cache[key] = im.resize((im.width * cell, im.height * cell), Image.NEAREST)
        return self._digit_cache[key]

    def bar(self, d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, pct: float) -> None:
        d.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=BAR_BG)
        fw = round(w * max(0.0, min(100.0, pct)) / 100)
        if fw > 0:
            col = (226, 76, 52, 255) if pct >= 80 else (233, 128, 74, 255)
            d.rounded_rectangle((x, y, x + max(fw, h), y + h), radius=h // 2, fill=col)

    def bubble(self, phrase: str, usage: Usage) -> Image.Image:
        s, px = self.s, self.px
        bw = self.bw
        inner = bw - px(40)
        lines_ = self.wrap(phrase, self.f_phrase, inner)
        line_h = px(23)
        ws = usage.windows()
        five = next((w for w in ws if w[0] == "5h"), None)
        rest = [w for w in ws if w[0] != "5h"]
        age = usage.age()
        stale = age is None or age > App.STALE_AFTER

        h = px(18) + line_h * len(lines_) + px(8)
        h += px(30)  # 计时行
        h += px(50)  # 大数字
        h += px(19) * len(rest)
        h += px(16) if stale else 0
        h += px(16)

        img = self.shape(bw, h).copy()
        d = ImageDraw.Draw(img)
        y = px(18)
        for ln in lines_:
            d.text((bw // 2, y), ln, font=self.f_phrase, fill=INK, anchor="mt")
            y += line_h
        y += px(8)

        # 计时行：[5h] 02:14:05
        timer = fmt_hms(five[2]) if five and five[2] else ("已回满" if five else "--:--:--")
        chip_w = px(30)
        tw = self.f_timer.getlength(timer) if five is None or five[2] else self.f_smallb.getlength(timer)
        total = chip_w + px(8) + tw
        x0 = round(bw / 2 - total / 2)
        d.rounded_rectangle((x0, y + px(3), x0 + chip_w, y + px(23)), radius=px(6), fill=CHIP)
        d.text((x0 + chip_w // 2, y + px(13)), "5h", font=self.f_chip, fill=(255, 255, 255, 255), anchor="mm")
        font = self.f_timer if five is None or five[2] else self.f_smallb
        d.text((x0 + chip_w + px(8), y + px(13)), timer, font=font, fill=RED, anchor="lm")
        y += px(30)

        # 大号像素百分比
        pct_txt = f"{round(five[1])}%" if five else "--%"
        cell = max(3, round(4 * s))
        dig = self.digits(pct_txt, cell, bool(five and five[1] >= 80))
        img.alpha_composite(dig, (bw // 2 - dig.width // 2, y))
        d.text((bw // 2 + dig.width // 2 + px(4), y + dig.height - px(8)), "已用", font=self.f_tiny, fill=SOFT,
               anchor="ls")
        y += px(50)

        # 其他窗口：本周、各模型
        for name, pct, left in rest:
            label_w, bar_w = px(44), px(78)
            reset = f"· {fmt_dh(left)}" if left else ""
            txt = f"{round(pct)}%"
            total = label_w + bar_w + px(8) + self.f_smallb.getlength(txt) + px(6) + self.f_small.getlength(reset)
            x = round(bw / 2 - total / 2)
            d.text((x + label_w - px(6), y + px(8)), name, font=self.f_small, fill=SOFT, anchor="rm")
            self.bar(d, x + label_w, y + px(4), bar_w, px(8), pct)
            x += label_w + bar_w + px(8)
            d.text((x, y + px(8)), txt, font=self.f_smallb, fill=INK, anchor="lm")
            x += round(self.f_smallb.getlength(txt)) + px(6)
            d.text((x, y + px(8)), reset, font=self.f_small, fill=SOFT, anchor="lm")
            y += px(19)
        if stale:
            note = f"数据是 {fmt_dh(age)}前的，开个 Code 会话会刷新" if age is not None else "还没拿到额度，开个 Code 会话就有了"
            d.text((bw // 2, y + px(8)), note, font=self.f_tiny,
                   fill=(160, 130, 118, 255), anchor="mm")
        return img


# ---------------------------------------------------------------- 挂件本体

def ease_out_back(t: float) -> float:
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


class Particle:
    def __init__(self, x, y, s):
        self.img_key = (random.choice(["heart", "heart", "star", "spark", "note", "dot"]),
                        random.choice(art.PARTICLE_COLORS))
        ang = random.uniform(-math.pi * 0.95, -math.pi * 0.05)
        sp = random.uniform(160, 380) * s
        self.x, self.y = x, y
        self.vx, self.vy = math.cos(ang) * sp, math.sin(ang) * sp
        self.g = 760 * s
        self.life = random.uniform(0.7, 1.1)
        self.age = 0.0

    def step(self, dt_):
        self.age += dt_
        self.vy += self.g * dt_
        self.x += self.vx * dt_
        self.y += self.vy * dt_
        return self.age < self.life


class Zlet:
    """瞌睡时从头的左上方飘出来的 z：慢慢上飘、轻轻左右摆、最后淡出。"""

    def __init__(self, x, y, s, big):
        self.x0, self.y0, self.s, self.big = x, y, s, big
        self.life = 2.8
        self.age = 0.0

    def step(self, dt_):
        self.age += dt_
        return self.age < self.life

    def pos(self):
        t = self.age / self.life
        return (self.x0 + (math.sin(t * math.pi * 2) * 4 + t * 10) * self.s, self.y0 - t * 26 * self.s)

    def alpha(self):
        t = self.age / self.life
        return max(0.0, min(1.0, (1 - t) / 0.35))


class App:
    def __init__(self) -> None:
        self.cfg = self.load_config()
        self.hwnd = None
        self.claude, self.claude_pid = None, 0
        self.last_scan = 0.0
        self.s = None
        self.layout_key = None
        self.visible = False
        self.topmost = None
        self.pos = None
        self.size = (0, 0)
        self.hdc_screen = user32.GetDC(None)
        self.hdc_mem = gdi32.CreateCompatibleDC(self.hdc_screen)
        self.hbmp = None
        self.bits = ctypes.c_void_p()
        self.sprites: dict = {}
        self.usage = Usage()
        self.picker = lines.Picker()
        self.audio = audio.Audio(log)
        now = time.monotonic()
        self.prev_t = now
        self.blink_at = now + random.uniform(2, 4)
        self.blink_until = 0.0
        self.clawd_blink_at = now + random.uniform(3, 6)
        self.clawd_blink_until = 0.0
        self.clawd_wave_at = now + random.uniform(15, 30)
        self.clawd_wave_until = 0.0
        self.face, self.face_until = "smug", 0.0
        self.jump_t = None
        self.hop_t = None
        self.shake_t = None
        self.pop_t = None
        self.particles: list[Particle] = []
        self.zlets: list[Zlet] = []
        self.z_at = 0.0
        self.clicks: deque[float] = deque(maxlen=8)
        self.phrase = ""
        self.phrase_until = 0.0
        self.idle_phrase_at = 0.0
        self.show_bubble_until = 0.0
        self.hover = False
        self.tracking = False
        self.drag = None
        self.hidden_until = 0.0
        self.last_tier = None
        self.frame_key = None
        self.z_checked = 0.0
        self.compact = False
        self.interval = 30
        self.p5 = None
        self.stale = True
        self._bubble_key = None
        self._bubble_img = None

    # ---- 配置
    def load_config(self) -> dict:
        try:
            cfg = {**DEFAULT_CONFIG, **json.loads(CONFIG_FILE.read_text(encoding="utf-8"))}
        except (OSError, ValueError):
            cfg = dict(DEFAULT_CONFIG)
        return cfg

    def save_config(self) -> None:
        try:
            CONFIG_FILE.write_text(json.dumps(self.cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as e:
            log(f"save config: {e}")

    # ---- 窗口
    def create(self) -> None:
        hinst = kernel32.GetModuleHandleW(None)
        self._wndproc = WNDPROC(self.wndproc)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = hinst
        wc.lpszClassName = "ClaudeChanWidget"
        user32.RegisterClassExW(ctypes.byref(wc))
        self.hwnd = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE, "ClaudeChanWidget", "Claude 酱", WS_POPUP,
            0, 0, 10, 10, None, None, hinst, None)
        user32.SetTimer(self.hwnd, 1, 30, None)
        self._fg_hook = WINEVENTPROC(lambda *a: self.safe(self.update_z, True))
        user32.SetWinEventHook(EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, None, self._fg_hook, 0, 0,
                               WINEVENT_OUTOFCONTEXT)

    def safe(self, fn, *a):
        try:
            return fn(*a)
        except Exception:  # noqa: BLE001 —— 回调里抛出去会直接把进程带走
            log(traceback.format_exc())

    def wndproc(self, hwnd, msg, wp, lp):
        try:
            if msg == WM_TIMER:
                self.tick()
                return 0
            if msg == WM_MOUSEACTIVATE:
                return MA_NOACTIVATE
            if msg == WM_SETCURSOR:
                user32.SetCursor(user32.LoadCursorW(None, ctypes.c_void_p(IDC_HAND)))
                return 1
            if msg == WM_LBUTTONDOWN:
                self.on_down(*lparam_xy(lp))
                return 0
            if msg == WM_MOUSEMOVE:
                self.on_move()
                return 0
            if msg == WM_LBUTTONUP:
                self.on_up(*lparam_xy(lp))
                return 0
            if msg == WM_MOUSELEAVE:
                self.hover = False
                self.tracking = False
                return 0
            if msg == WM_RBUTTONUP:
                self.on_menu()
                return 0
            if msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
        except Exception:  # noqa: BLE001
            log(traceback.format_exc())
        return user32.DefWindowProcW(hwnd, msg, wp, lp)

    # ---- 布局
    def layout(self, s: float):
        k = max(2, round(float(self.cfg.get("scale", 3)) * s))
        key = (s, k)
        if key == self.layout_key:
            return
        self.layout_key = key
        self.s, self.k = s, k
        self.painter = Painter(s)
        self.sprites.clear()
        base = art.build_sprite()
        self.sw, self.sh = base.width * k, base.height * k
        m = round(40 * s)
        self.bubble_max_h = round(270 * s)
        bw = self.painter.bw
        gap = round(6 * s)
        eye = art.EYE_LINE * k - round(6 * s)  # 气泡底边大约齐眼睛
        self.win_w = m + bw + gap + self.sw
        self.win_h = m + self.bubble_max_h - eye + self.sh
        self.sprite_x = self.win_w - self.sw
        self.sprite_y = self.win_h - self.sh
        self.bubble_x = m
        self.bubble_bottom = self.sprite_y + eye
        self.frame_key = None

    def sprite(self, face, clawd, bob=0):
        key = (face, clawd, bob)
        if key not in self.sprites:
            self.sprites[key] = art.scaled(face, clawd, self.k, bob)
        return self.sprites[key]

    def clawd_img(self, frame):
        key = ("clawd", frame)
        if key not in self.sprites:
            im, (gx, gy) = art.clawd_sticker(frame)
            self.sprites[key] = (im.resize((im.width * self.k, im.height * self.k), Image.NEAREST),
                                 (gx * self.k, gy * self.k))
        return self.sprites[key]

    # ---- 跟随 Claude 窗口
    def track(self, now: float):
        if self.claude is None or not user32.IsWindow(self.claude):
            if now - self.last_scan < 2:
                return None
            self.last_scan = now
            self.claude, self.claude_pid = find_claude()
            if self.claude is None:
                return None
        if not user32.IsWindowVisible(self.claude) or user32.IsIconic(self.claude) or is_cloaked(self.claude):
            return None
        return frame_rect(self.claude)

    def update_z(self, force=False):
        if not self.visible or self.claude is None:
            return
        fg = user32.GetForegroundWindow()
        fg_pid = pid_of(fg) if fg else 0
        front = fg_pid in (self.claude_pid, os.getpid())
        flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        if front:
            if self.topmost is not True or force:
                user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
                self.topmost = True
            return
        if self.topmost is not False or force:
            user32.SetWindowPos(self.hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
            self.topmost = False
        # 摆到 Claude 正上方：插在“Claude 上面那个窗口”的后面
        prev = user32.GetWindow(self.claude, GW_HWNDPREV)
        if prev == self.hwnd:
            return
        if prev and not (user32.GetWindowLongW(prev, GWL_EXSTYLE) & WS_EX_TOPMOST):
            user32.SetWindowPos(self.hwnd, prev, 0, 0, 0, 0, flags)
        else:
            user32.SetWindowPos(self.hwnd, HWND_TOP, 0, 0, 0, 0, flags)

    # ---- 每一帧
    def tick(self):
        now = time.monotonic()
        dt_ = min(0.1, now - self.prev_t)
        self.prev_t = now

        rect = self.track(now) if now >= self.hidden_until else None
        if rect is None:
            if self.visible:
                user32.ShowWindow(self.hwnd, SW_HIDE)
                self.visible = False
            self.set_interval(250)
            return

        s = (user32.GetDpiForWindow(self.claude) or 96) / 96
        self.layout(s)
        cw = rect[2] - rect[0]
        # 右边留白 ≈ (窗口宽 - 侧栏 - 输入框) / 2，放不下整个挂件就把气泡收起来，只在点击后弹出
        room = (cw - 320 * s - 760 * s) / 2
        self.compact = room < self.win_w - round(40 * s)
        if room < self.sw * 0.6:
            if self.visible:
                user32.ShowWindow(self.hwnd, SW_HIDE)
                self.visible = False
            self.set_interval(250)
            return

        ox, oy = self.cfg.get("offset", [0, 0])
        x = rect[2] - round(14 * s) - self.win_w + round(ox * s)
        y = rect[3] - round(4 * s) - self.win_h + round(oy * s)

        if self.usage.poll(time.time()):
            self.on_usage()
        self.animate(now, dt_)
        self.render((x, y), now)
        self.warm_audio()
        self.set_interval(30 if self.busy(now) else 120)

        if not self.visible:
            user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            self.visible = True
            self.topmost = None
            self.update_z(True)
        elif now - self.z_checked > 0.5:
            self.z_checked = now
            self.update_z()

    def on_usage(self):
        ctx = self.usage.ctx()
        p5 = self.p5 = ctx["p5"]
        tier = None if p5 is None else (3 if p5 >= 100 else 2 if p5 >= 95 else 1 if p5 >= 80 else 0)
        if self.last_tier is not None and tier is not None and tier > self.last_tier and tier >= 1:
            self.say(self.picker.warn(ctx), 12)
            self.face, self.face_until = "wow", time.monotonic() + 3
            # 没人碰挂件时耳机多半睡着：先叫醒，过一秒再响
            self.play(sounds.WARN, delay=0.0 if self.audio.is_warm() else 1.2)
        self.last_tier = tier
        self.idle_phrase_at = 0

    STALE_AFTER = 10 * 60  # 数据多久没刷新算过期（秒）

    def base_face(self):
        """按额度状态挑表情：回满 得意 / 正常 微笑 / 过半 平静 / 快用完 惊讶 / 耗尽 哭 / 数据过期 打瞌睡。"""
        p5 = self.p5
        if p5 is None or self.stale:
            return "sleepy"
        if p5 >= 100:
            return "cry"
        if p5 >= 80:
            return "strain"
        if p5 >= 50:
            return "calm"
        if p5 >= 4:
            return "smile"
        return "smug"

    def busy(self, now) -> bool:
        return bool(self.particles or self.jump_t or self.hop_t or self.shake_t or self.pop_t
                    or (self.drag and self.drag["moved"]) or self.hover or now < self.clawd_wave_until)

    def set_interval(self, ms):
        if ms != self.interval:
            self.interval = ms
            user32.SetTimer(self.hwnd, 1, ms, None)

    def animate(self, now, dt_):
        if now >= self.blink_at:
            self.blink_until = now + 0.14
            self.blink_at = now + random.uniform(2.5, 5.5)
        if now >= self.clawd_blink_at:
            self.clawd_blink_until = now + 0.16
            self.clawd_blink_at = now + random.uniform(3, 7)
        if now >= self.clawd_wave_at:
            self.clawd_wave_until = now + 0.9
            self.clawd_wave_at = now + random.uniform(18, 40)
        if now >= self.idle_phrase_at and now >= self.phrase_until:
            self.phrase = self.picker.idle(self.usage.ctx(), self.stale)
            self.idle_phrase_at = now + 600
        self.particles = [p for p in self.particles if p.step(dt_)]
        self.zlets = [z for z in self.zlets if z.step(dt_)]
        if now >= self.face_until and self.base_face() == "sleepy" and now >= self.z_at and self.visible:
            zx = self.sprite_x + art.ZZZ_SPOT[0] * self.k
            zy = self.sprite_y + art.ZZZ_SPOT[1] * self.k
            self.zlets.append(Zlet(zx, zy, self.s, big=len(self.zlets) % 2 == 1))
            self.z_at = now + 1.5
        if int(now) != getattr(self, "_p5_sec", None):  # 窗口过了重置时间要按 0% 算，所以每秒重算一次
            self._p5_sec = int(now)
            self.p5 = self.usage.ctx()["p5"]
            age = self.usage.age()
            self.stale = age is None or age > self.STALE_AFTER

    def say(self, text, secs=10.0):
        now = time.monotonic()
        self.phrase = text
        self.phrase_until = now + secs
        self.idle_phrase_at = now + secs
        self.pop_t = now
        self.show_bubble_until = now + max(secs, 7)

    def play(self, name, delay=0.0):
        if self.cfg.get("muted"):
            return
        try:
            self.audio.play(str(sounds.ASSETS / name), gain=float(self.cfg.get("volume", 0.1)), delay=delay)
        except Exception as e:  # noqa: BLE001
            log(f"sound: {e!r}")

    def warm_audio(self):
        """鼠标靠近挂件就先把输出流开起来，蓝牙耳机醒着，单击的音效才不会被吞掉。"""
        if self.cfg.get("muted") or self.pos is None:
            return
        pt = wt.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        m = round(160 * (self.s or 1))
        x, y = self.pos
        w, h = self.size
        if x - m <= pt.x <= x + w + m and y - m <= pt.y <= y + h + m:
            self.audio.wake(20)

    # ---- 鼠标
    def on_down(self, x, y):
        pt = wt.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        self.drag = {"start": (pt.x, pt.y), "offset": list(self.cfg.get("offset", [0, 0])), "moved": False,
                     "at": (x, y)}
        user32.SetCapture(self.hwnd)

    def on_move(self):
        if not self.tracking:
            tme = TRACKMOUSEEVENT(ctypes.sizeof(TRACKMOUSEEVENT), TME_LEAVE, self.hwnd, 0)
            user32.TrackMouseEvent(ctypes.byref(tme))
            self.tracking = True
        self.hover = True
        if not self.cfg.get("muted"):
            self.audio.wake(20)
        if not self.drag:
            return
        pt = wt.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        dx, dy = pt.x - self.drag["start"][0], pt.y - self.drag["start"][1]
        if not self.drag["moved"] and dx * dx + dy * dy < 36:
            return
        self.drag["moved"] = True
        s = self.s or 1
        self.cfg["offset"] = [round(self.drag["offset"][0] + dx / s), round(self.drag["offset"][1] + dy / s)]

    def on_up(self, x, y):
        user32.ReleaseCapture()
        drag, self.drag = self.drag, None
        if drag and drag["moved"]:
            self.save_config()
            return
        self.poke(x, y)

    def poke(self, x, y):
        now = time.monotonic()
        self.clicks.append(now)
        recent = [t for t in self.clicks if now - t < 2.5]
        ctx = self.usage.ctx()
        if len(recent) >= 5:
            self.clicks.clear()
            self.face, self.face_until = "pout", now + 2.4
            self.shake_t = now
            self.say(self.picker.annoyed(ctx), 6)
            self.play(sounds.ANNOYED)
            return
        self.face, self.face_until = ("happy" if random.random() < 0.25 else "wink"), now + 2.2
        self.jump_t = now
        self.hop_t = now + 0.07
        self.say(self.picker.poke(ctx, dt.datetime.now().hour), 10)
        hx = self.sprite_x + self.sw // 2
        hy = self.sprite_y + art.EYE_LINE * self.k
        cx, cy = (x, y) if x >= self.sprite_x else (hx, hy)
        for _ in range(random.randint(9, 14)):
            self.particles.append(Particle(cx, cy, self.s))
        self.play(random.choice(sounds.CLICK))

    def on_menu(self):
        menu = user32.CreatePopupMenu()
        muted = self.cfg.get("muted")
        pinned = self.cfg.get("bubble", True)
        user32.AppendMenuW(menu, MF_STRING | (MF_CHECKED if muted else 0), 1, "静音")
        user32.AppendMenuW(menu, MF_STRING | (MF_CHECKED if pinned else 0), 2, "气泡常驻")
        user32.AppendMenuW(menu, MF_STRING, 3, "隐藏 30 分钟")
        user32.AppendMenuW(menu, MF_STRING, 4, "回到右下角")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, 5, "打开挂件文件夹")
        user32.AppendMenuW(menu, MF_STRING, 9, "退出")
        pt = wt.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self.hwnd)
        cmd = user32.TrackPopupMenu(menu, TPM_RETURNCMD | TPM_RIGHTBUTTON, pt.x, pt.y, 0, self.hwnd, None)
        user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(menu)
        if cmd == 1:
            self.cfg["muted"] = not muted
        elif cmd == 2:
            self.cfg["bubble"] = not pinned
        elif cmd == 3:
            self.hidden_until = time.monotonic() + 30 * 60
        elif cmd == 4:
            self.cfg["offset"] = [0, 0]
        elif cmd == 5:
            os.startfile(DATA)
        elif cmd == 9:
            user32.PostQuitMessage(0)
        if cmd in (1, 2, 4):
            self.save_config()
        if self.claude:
            user32.SetForegroundWindow(self.claude)

    # ---- 合成一帧
    def render(self, pos, now):
        k, s = self.k, self.s
        face = self.face if now < self.face_until else self.base_face()
        if now < self.blink_until and face in art.BLINKABLE:
            face = f"{face}:blink"
        hopping = self.hop_t is not None and now - self.hop_t < 0.5
        if hopping or now < self.clawd_wave_until or (self.hover and int(now / 0.3) % 2):
            clawd = 1 if int(now / 0.15) % 2 or hopping else 0
        elif now < self.clawd_blink_until:
            clawd = 2
        else:
            clawd = 0

        jump = 0.0
        squash = False
        if self.jump_t is not None:
            t = (now - self.jump_t) / 0.42
            if t < 1:
                jump = 4 * t * (1 - t) * 26 * s
            elif t < 1.3:
                squash = True
            else:
                self.jump_t = None
        hop = 0.0
        if self.hop_t is not None:
            t = (now - self.hop_t) / 0.5
            if 0 <= t < 1:
                hop = 4 * t * (1 - t) * 20 * s
            elif t >= 1:
                self.hop_t = None
        shake = 0.0
        if self.shake_t is not None:
            t = now - self.shake_t
            if t < 0.45:
                shake = math.sin(t * 70) * 4 * s * (1 - t / 0.45)
            else:
                self.shake_t = None
        # 呼吸：头和小 Clawd 每秒上下错一格（立绘里分层画），身体不动
        bob = int(time.time()) % 2 if self.jump_t is None else 0

        bubble_on = bool(self.cfg.get("bubble", True)) and not self.compact
        bubble_on = bubble_on or now < self.show_bubble_until
        pop = 1.0
        if self.pop_t is not None:
            t = (now - self.pop_t) / 0.3
            if t < 1:
                pop = 0.82 + 0.18 * ease_out_back(t)
            else:
                self.pop_t = None

        sec = int(time.time())
        key = (pos, face, clawd, round(jump), round(hop), squash, round(shake), bob, bubble_on, round(pop, 3),
               self.phrase, sec, self.usage.mtime, len(self.particles) > 0,
               tuple(round(z.pos()[1]) for z in self.zlets))
        if key == self.frame_key and not self.particles:
            return
        self.frame_key = key

        img = Image.new("RGBA", (self.win_w, self.win_h), (0, 0, 0, 0))
        if bubble_on:
            bkey = (self.phrase, sec, self.usage.mtime, self.k)
            if bkey != self._bubble_key:
                self._bubble_key, self._bubble_img = bkey, self.painter.bubble(self.phrase, self.usage)
            b = self._bubble_img
            if b.height > self.bubble_max_h:
                b = b.crop((0, 0, b.width, self.bubble_max_h))
            bx, by = self.bubble_x, self.bubble_bottom - b.height
            if pop != 1.0:
                nw, nh = max(1, round(b.width * pop)), max(1, round(b.height * pop))
                b = b.resize((nw, nh), Image.BICUBIC)
                bx += self.painter.bw - nw
                by = self.bubble_bottom - nh
            blit(img, b, bx, by)
            tr = self.painter.trail()
            blit(img, tr, self.bubble_x + self.painter.bw - round(34 * s), self.bubble_bottom - round(6 * s))

        detached = hop > 0
        spr = self.sprite(face, None if detached else clawd, bob)
        sx = self.sprite_x + round(shake)
        sy = self.sprite_y - round(jump)
        if squash:
            nw, nh = round(spr.width * 1.06), round(spr.height * 0.94)
            spr = spr.resize((nw, nh), Image.NEAREST)
            sx -= (nw - self.sw) // 2
            sy += self.sh - nh
        blit(img, spr, sx, sy)
        if detached:
            cim, (cx, cy) = self.clawd_img(clawd)
            blit(img, cim, sx + cx, sy + cy + (1 - bob) * k - round(hop))

        for z in self.zlets:
            zim = art.particle("Z" if z.big else "z", (190, 226, 255))
            zim = zim.resize((zim.width * k, zim.height * k), Image.NEAREST)
            a = z.alpha()
            if a < 1:
                zim = zim.copy()
                zim.putalpha(zim.getchannel("A").point(lambda v: int(v * a)))
            zx, zy = z.pos()
            blit(img, zim, round(zx), round(zy))

        for p in self.particles:
            pim = art.particle(*p.img_key)
            cell = k
            pim = pim.resize((pim.width * cell, pim.height * cell), Image.NEAREST)
            fade = 1.0 if p.age < p.life - 0.3 else max(0.0, (p.life - p.age) / 0.3)
            if fade < 1:
                a = pim.getchannel("A").point(lambda v: int(v * fade))
                pim = pim.copy()
                pim.putalpha(a)
            blit(img, pim, round(p.x - pim.width / 2), round(p.y - pim.height / 2))

        self.push(img, pos)

    def push(self, img: Image.Image, pos):
        w, h = img.size
        if (w, h) != self.size or self.hbmp is None:
            if self.hbmp:
                gdi32.DeleteObject(self.hbmp)
            bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
            self.hbmp = gdi32.CreateDIBSection(self.hdc_mem, ctypes.byref(bmi), 0, ctypes.byref(self.bits), None, 0)
            gdi32.SelectObject(self.hdc_mem, self.hbmp)
            self.size = (w, h)
        data = img.tobytes("raw", "BGRa")  # UpdateLayeredWindow 要预乘过 alpha 的 BGRA
        ctypes.memmove(self.bits, data, len(data))
        blend = BLENDFUNCTION(0, 0, 255, AC_SRC_ALPHA)
        ok = user32.UpdateLayeredWindow(self.hwnd, self.hdc_screen, ctypes.byref(wt.POINT(*pos)),
                                        ctypes.byref(wt.SIZE(w, h)), self.hdc_mem, ctypes.byref(wt.POINT(0, 0)), 0,
                                        ctypes.byref(blend), ULW_ALPHA)
        if not ok:
            log(f"UpdateLayeredWindow failed: {ctypes.get_last_error()}")
        self.pos = pos

    def run(self):
        self.create()
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))


def main():
    kernel32.CreateMutexW(None, False, "Local\\ClaudeChanWidget")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS：已经开着一个了
        return
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    sounds.ensure()
    log("start")
    try:
        App().run()
    except Exception:  # noqa: BLE001
        log(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
