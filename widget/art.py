"""Clawd 酱的像素立绘（第四版）：表情包里那位橙发大小姐的 Q 版像素化，头顶站着戴王冠的小 Clawd。

画法参照日系像素画的习惯：
- 头发是一个整体：后发、鬓发、刘海各画一层但都不单独描边，合成之后只沿整头头发的
  外轮廓（贴着皮肤、衣服、空白的地方）描一圈红褐线，头发和头发相接处只靠颜色过渡；
- 外轮廓从头顶顺着滑到发尾，中间没有拐点：刘海和鬓发都不许鼓出头的圆，长发在头下方
  才慢慢变宽，最宽处在肩膀以下，发尾收成两三簇长短不一的尖，长度到裙摆；
- 长发上端和头顶同色，靠身体的内侧和发尖逐级变暗，只有被肩膀挡住的里层用最暗的一阶；
- 几条发丝线从发旋一路画进长发（只落在头发上），两块就连成一头；
- 两侧不镜像：右边一缕搭在肩膀和袖子前面，左边被账本挡住一部分；
- 白色衣物里面的分界用暖棕灰，贴着贴纸边的白衣再补一圈暖灰轮廓；裙摆黑底金纹的锯齿边，
  整条裙边两头往上收成弧；两只脚微微外八、右脚靠前半步；
- 头、身体、小 Clawd 分三层，呼吸时头和小 Clawd 各自上下错一格。

所有图在 104x150 的格子上画，再整数倍放大。build_sprite() 给挂件用，
直接运行本文件会把各个表情导出到 preview/。
"""
from __future__ import annotations

import math
from functools import lru_cache

from PIL import Image, ImageDraw

W, H = 104, 150
CX = 52
HEAD = (21, 15, 83, 77)  # 头的圆：除发饰和小 Clawd 外，头发都不许鼓出去

P = {
    # 头发：阴影往红偏，高光往黄偏
    "HL": (255, 242, 196),
    "H1": (255, 196, 110),
    "H2": (250, 150, 60),
    "H3": (226, 106, 46),
    "H4": (178, 66, 42),
    "H5": (138, 46, 38),
    "HO": (110, 34, 34),
    # 皮肤
    "SK": (255, 242, 232),
    "S2": (250, 212, 198),
    "S3": (228, 164, 154),
    "BL": (248, 142, 142),
    # 眼睛（琥珀色）
    "EL": (60, 22, 28),
    "E1": (132, 44, 24),
    "E2": (214, 102, 32),
    "E3": (250, 166, 56),
    "E4": (255, 222, 130),
    "WH": (255, 255, 255),
    "MO": (130, 30, 42),
    "TG": (242, 120, 120),
    # 布料：W3 是白衣内部分界线，WO 是白衣贴着外边时的轮廓
    "W0": (255, 255, 255),
    "W1": (250, 246, 242),
    "W2": (232, 222, 220),
    "W3": (178, 146, 136),
    "WO": (160, 124, 114),
    "K0": (22, 16, 28),
    "K1": (48, 38, 58),
    "K2": (90, 76, 106),
    "O1": (255, 168, 86),
    "O2": (238, 118, 50),
    "O3": (186, 72, 38),
    "G0": (255, 250, 210),
    "G1": (252, 210, 90),
    "G2": (216, 150, 48),
    "G3": (148, 90, 32),
    "B1": (126, 70, 48),
    "B2": (90, 46, 34),
    "B3": (62, 30, 26),
    "OL": (58, 24, 30),
    # 小 Clawd
    "C1": (217, 119, 87),
    "C2": (182, 92, 66),
    "C3": (240, 156, 124),
    "RD": (226, 70, 70),
    "TE": (150, 214, 255),
    "SW": (170, 220, 255),
}

WHITES = {P["W0"], P["W1"], P["W2"]}
HAIR = {P[k] for k in ("HL", "H1", "H2", "H3", "H4", "H5")}
HAIR_LIGHT = {P[k] for k in ("HL", "H1", "H2")}


def rgba(key: str) -> tuple[int, int, int, int]:
    return (*P[key], 255)


def _bez(ctrl, n=32):
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = ctrl
    out = []
    for i in range(n + 1):
        t = i / n
        m = 1 - t
        out.append((m ** 3 * x0 + 3 * m * m * t * x1 + 3 * m * t * t * x2 + t ** 3 * x3,
                    m ** 3 * y0 + 3 * m * m * t * y1 + 3 * m * t * t * y2 + t ** 3 * y3))
    return out


def _ring(img: Image.Image, color) -> Image.Image:
    """在不透明区域外面描一圈（四邻接）。"""
    src = img.load()
    out = img.copy()
    dst = out.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            if src[x, y][3] != 0:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and src[nx, ny][3] != 0:
                    dst[x, y] = color
                    break
    return out


def inner_outline(img: Image.Image, color, only=None) -> Image.Image:
    """把图层里贴着透明区域的那一圈像素染成 color（描在形状里面，不改变外形）。

    only：只染这些颜色的像素（白衣的暖灰轮廓用）。
    """
    src = img.load()
    out = img.copy()
    dst = out.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            p = src[x, y]
            if p[3] == 0 or (only is not None and p[:3] not in only):
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < w and 0 <= ny < h) or src[nx, ny][3] == 0:
                    dst[x, y] = (*color, 255)
                    break
    return out


def hair_outline(img: Image.Image) -> Image.Image:
    """整头头发的外轮廓：头发像素贴着空白、皮肤、衣服的那一圈染成 HO；头发贴头发不描。"""
    src = img.load()
    out = img.copy()
    dst = out.load()
    w, h = img.size
    ho = P["HO"]
    for y in range(h):
        for x in range(w):
            p = src[x, y]
            if p[3] == 0 or p[:3] not in HAIR:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                q = src[nx, ny] if 0 <= nx < w and 0 <= ny < h else (0, 0, 0, 0)
                if q[3] == 0 or (q[:3] not in HAIR and q[:3] != ho):
                    dst[x, y] = (*ho, 255)
                    break
    return out


class Canvas:
    def __init__(self) -> None:
        self.img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def paste(self, layer: "Canvas", dy: int = 0, only=None) -> None:
        """叠一层上来；only 给出时只落在底下是这些颜色的像素上（发丝线只画在头发上）。"""
        src = layer.img if dy == 0 else self._shifted(layer.img, dy)
        if only is None:
            self.img.alpha_composite(src)
            return
        s = src.load()
        d = self.img.load()
        for y in range(H):
            for x in range(W):
                if s[x, y][3] and d[x, y][:3] in only:
                    d[x, y] = s[x, y]

    @staticmethod
    def _shifted(img: Image.Image, dy: int) -> Image.Image:
        out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        out.alpha_composite(img.crop((0, max(0, -dy), W, H - max(0, dy))), (0, max(0, dy)))
        return out

    def replace(self, img: Image.Image) -> None:
        """换掉底图（描边这类整图操作之后用），画笔也跟着换。"""
        self.img = img
        self.d = ImageDraw.Draw(self.img)

    def clip_ellipse(self, box) -> None:
        """只保留椭圆里面的部分。"""
        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).ellipse(box, fill=255)
        empty = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        self.img = Image.composite(self.img, empty, mask)
        self.d = ImageDraw.Draw(self.img)

    def poly(self, pts, fill=None, outline=None):
        self.d.polygon([tuple(p) for p in pts], fill=rgba(fill) if fill else None,
                       outline=rgba(outline) if outline else None)

    def ell(self, box, fill=None, outline=None):
        self.d.ellipse(box, fill=rgba(fill) if fill else None, outline=rgba(outline) if outline else None)

    def rect(self, box, fill=None, outline=None):
        self.d.rectangle(box, fill=rgba(fill) if fill else None, outline=rgba(outline) if outline else None)

    def line(self, pts, color, width=1):
        self.d.line([tuple(p) for p in pts], fill=rgba(color), width=width)

    def curve(self, ctrl, color, t0=0.0, t1=1.0):
        pts = _bez(ctrl, 48)
        a, b = int(t0 * 48), int(t1 * 48)
        self.line(pts[a:b + 1], color)

    def px(self, x, y, color):
        x, y = int(round(x)), int(round(y))
        if 0 <= x < W and 0 <= y < H:
            self.img.putpixel((x, y), rgba(color))

    def get(self, x, y):
        if 0 <= x < W and 0 <= y < H:
            return self.img.getpixel((x, y))
        return (0, 0, 0, 0)

    def patch(self, x0, y0, rows, legend, flip=False):
        """贴一块字符画：legend 把字符映射到调色板，'.' 不画。"""
        for dy, row in enumerate(rows):
            if flip:
                row = row[::-1]
            for dx, ch in enumerate(row):
                if ch in legend:
                    self.px(x0 + dx, y0 + dy, legend[ch])

    def strand(self, ctrl, w0, w1=0.0, fill="H2", shade=None, side=1, shade_frac=0.45, hi=None,
               hi_span=(0.08, 0.32), taper=1.0, shift=(0, 0), cut=None, cut_span=(0.35, 1.0), prof=None):
        """一束头发：沿三次贝塞尔中线、从根部宽 w0 收到尖端 w1 的多边形。

        shade：靠 side 一侧的一条暗色带；hi：中线附近一小段高光；
        cut：沿 -side 那条边画一道分束线（只画 cut_span 那一段）；
        prof：给出时用 prof(t) 当作整束的宽度（根部细、中间粗、末端尖这种）。
        """
        pts = _bez(ctrl)
        n = len(pts) - 1
        left, right, mids, normals, widths = [], [], [], [], []
        for i, (x, y) in enumerate(pts):
            t = i / n
            xa, ya = pts[max(0, i - 1)]
            xb, yb = pts[min(n, i + 1)]
            dx, dy = xb - xa, yb - ya
            ln = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / ln, dx / ln
            w = (prof(t) if prof else (w0 * (1 - t) ** taper + w1 * t)) / 2
            x, y = x + shift[0], y + shift[1]
            left.append((x + nx * w, y + ny * w))
            right.append((x - nx * w, y - ny * w))
            mids.append((x, y))
            normals.append((nx, ny))
            widths.append(w)
        self.poly(left + right[::-1], fill)
        if shade:
            band, back = [], []
            for (x, y), (nx, ny), w in zip(mids, normals, widths):
                inner = w * (1 - 2 * shade_frac)
                band.append((x + side * nx * w, y + side * ny * w))
                back.append((x + side * nx * inner, y + side * ny * inner))
            self.poly(band + back[::-1], shade)
        if hi:
            a, b = int(hi_span[0] * n), int(hi_span[1] * n)
            seg, seg2 = [], []
            for (x, y), (nx, ny), w in list(zip(mids, normals, widths))[a:b + 1]:
                hw = max(0.6, w * 0.22)
                off = -side * w * 0.25
                seg.append((x + nx * (off + hw), y + ny * (off + hw)))
                seg2.append((x + nx * (off - hw), y + ny * (off - hw)))
            if len(seg) >= 2:
                self.poly(seg + seg2[::-1], hi)
        if cut:
            edge = left if side < 0 else right
            a, b = int(cut_span[0] * n), int(cut_span[1] * n)
            self.line(edge[a:b + 1], cut)
        return left, right


# ---------------------------------------------------------------- 脸

EYE_LEGEND = {"L": "EL", "a": "E1", "b": "E2", "c": "E3", "d": "E4", "w": "WH", "s": "S3", "t": "TE"}

# 左眼（画面左边那只），13x15，外眼角在左；右眼左右翻转。
EYES = {
    "open": [
        ".....LLLLLL..",
        "..LLLLLLLLLLL",
        "LLLLaaaaaaaLL",
        "LL.aaaaaaaaaL",
        "...awwaaaaaa.",
        "...awwwaaaba.",
        "...awwabbbba.",
        "...abbbbbbba.",
        "..wabbbcbbba.",
        "..wabbcccbba.",
        "...abcccccba.",
        "...abcdddwba.",
        "....abdddba..",
        ".....abbba...",
        "......sss....",
    ],
    "smug": [
        ".............",
        ".............",
        ".............",
        ".............",
        "LLLLLLLLLLL..",
        "LLLLLLLLLLLL.",
        "..LaaaaaaaaL.",
        "...awwaabbba.",
        "...awwabbbba.",
        "...abbbcbbba.",
        "...abbcccbba.",
        "...abcdddwba.",
        "....abdddba..",
        ".....abbba...",
        "......sss....",
    ],
    "sleepy": [  # 眼皮耷拉下来，只露下半个瞳孔
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
        ".LLLLLLLLLLL.",
        "LLLLLLLLLLLL.",
        "..LaabbbbbaL.",
        "...abbcccba..",
        "...abcdddba..",
        "....abbbba...",
        ".....sss.....",
        ".............",
        ".............",
    ],
    "blink": [
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
        "LLLLLLLLLLLL.",
        "LLLLLLLLLLL..",
        "..LLLLLLLL...",
        "...ssssss....",
        ".............",
        ".............",
        ".............",
    ],
    "happy": [
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
        "....LLLLL....",
        "..LLLLLLLLL..",
        ".LLL.....LLL.",
        "LL.........LL",
        "L...........L",
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
    ],
    "sad": [  # 闭着眼往下弯，哭的时候用
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
        "L...........L",
        "LL.........LL",
        ".LLL.....LLL.",
        "..LLLLLLLLL..",
        "....LLLLL....",
        ".............",
        ".............",
        ".............",
        ".............",
    ],
    "shut": [  # >< 的 >，右眼翻转后成 <
        ".............",
        ".............",
        ".............",
        "..LL.........",
        "...LLLL......",
        "......LLLL...",
        ".........LLL.",
        "......LLLL...",
        "...LLLL......",
        "..LL.........",
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
    ],
    "wide": [
        "....LLLLLLL..",
        "..LLLLLLLLLL.",
        ".LLwwwwwwwwLL",
        ".Lwwwwwwwwwwd",
        ".Lwwaaaaawww.",
        ".Lwawwaaaww..",
        ".Lwawwabaww..",
        ".Lwaabbbaww..",
        ".Lwabcccaww..",
        "..wabcdcaw...",
        "..wwaaaaww...",
        "...wwwwww....",
        "....wwww.....",
        ".....ssss....",
        ".............",
    ],
}

MOUTH_LEGEND = {"O": "OL", "m": "MO", "t": "TG", "w": "WH"}
MOUTHS = {
    "smug": ["OOOOOOOO", "OwmmmmmO", ".OmmttO.", "..OttO..", "...OO..."],
    "grin": ["OOOOOOOO", "OwmmmmmO", "OmmtttmO", ".OmtttO.", "..OOOO.."],
    "smile": ["O.....O", ".OOOOO."],
    "cat": ["O..O..O", ".OO.OO."],
    "wavy": [".O.O.O.", "O.O.O.O"],
    "o": [".OOO.", "OmmmO", "OmtmO", ".OOO."],
    "oo": [".OO.", "OmmO", ".OO."],
    "flat": [".OOOO."],
}

# 眉毛（相对左眼左上角），右眉镜像
BROWS = {
    "up": [(2, -3), (3, -4), (4, -4), (5, -5), (6, -5), (7, -5), (8, -5), (9, -4)],
    "calm": [(2, -3), (3, -3), (4, -4), (5, -4), (6, -4), (7, -4), (8, -4), (9, -3)],
    "angry": [(2, -6), (3, -6), (4, -5), (5, -5), (6, -4), (7, -4), (8, -3), (9, -2)],
    "worry": [(2, -2), (3, -2), (4, -3), (5, -3), (6, -4), (7, -4), (8, -5), (9, -6)],
}

# 每个表情对应挂件的一种状态（widget.pyw 的 base_face 按额度挑）
FACES = {
    #          左眼      右眼      嘴       眉       额外
    "smug": ("smug", "smug", "smug", "up", ()),              # 额度回满
    "smile": ("open", "open", "smile", "up", ()),            # 正常使用
    "calm": ("open", "open", "flat", "calm", ()),            # 用量过半
    "strain": ("shut", "shut", "wavy", "worry", ()),         # 快用完（><）
    "cry": ("sad", "sad", "wavy", "worry", ("tears", "blush+")),  # 额度耗尽
    "sleepy": ("sleepy", "sleepy", "oo", "calm", ()),        # 数据过期，等 Code 会话刷新（zzz 由挂件飘）
    "wow": ("wide", "wide", "o", "worry", ()),               # 刚跨过一档的那几秒
    "wink": ("open", "happy", "cat", "up", ()),              # 被点了一下
    "happy": ("happy", "happy", "grin", "up", ("blush+",)),
    "pout": ("shut", "shut", "wavy", "angry", ("blush+",)),  # 被连点了
}
BLINKABLE = {"smug", "smile", "calm", "wow", "sleepy"}


def face_spec(face: str):
    """'calm' 或 'calm:blink'（眨眼时眼睛换成闭上的，嘴和眉照旧）。"""
    base, _, mod = face.partition(":")
    le, re, mouth, brow, extra = FACES[base]
    if mod == "blink":
        le = re = "blink"
    return le, re, mouth, brow, extra


EYE_L = (33, 45)
EYE_R = (58, 45)
EYE_Y = EYE_L[1] + 8  # 眼睛中线（格子坐标，不含贴纸边）


# ---------------------------------------------------------------- 头发

def _mass(c: Canvas, outer_segs, tips, inner_ctrl, side: int) -> None:
    """一大片长发。outer_segs 外侧轮廓的几段贝塞尔（从头侧到底部，首尾相接），tips 底部几个尖的折线，
    inner_ctrl 内侧轮廓（从上到下）。

    side=-1 画面左边那片（外侧在左），+1 右边。上端和头顶同色，越靠身体内侧、越靠发尖越暗。
    """
    outer = []
    for seg in outer_segs:
        pts = _bez(seg, 24)
        outer += pts if not outer else pts[1:]
    layer = Canvas()
    layer.poly(outer + tips + _bez(inner_ctrl, 40)[::-1], "H2")
    px = layer.img.load()
    rows = {}
    for y in range(H):
        xs = [x for x in range(W) if px[x, y][3]]
        if xs:
            rows[y] = (min(xs), max(xs))
    y_top, y_bot = min(rows), max(rows)
    for y, (lo, hi) in rows.items():
        t = (y - y_top) / max(1, y_bot - y_top)
        for x in range(lo, hi + 1):
            if not px[x, y][3]:
                continue
            d_out = (x - lo) if side < 0 else (hi - x)
            d_in = (hi - x) if side < 0 else (x - lo)
            if d_in < 1 + 4 * t or t > 0.93:
                tone = "H4"
            elif d_in < 4 + 6 * t and t > 0.3 or t > 0.82:
                tone = "H3"
            elif 1 <= d_out <= 3 and 0.04 < t < 0.3:
                tone = "H1"
            else:
                tone = "H2"
            px[x, y] = rgba(tone)
    # 发尖之间的分束线：从每个凹口往上一截
    for i in range(1, len(tips), 2):
        x, y = tips[i]
        layer.line([(x, y), (x + (1 if side < 0 else -1), y - 9)], "H4")
    c.paste(layer)


def _back_hair() -> Canvas:
    """脑后和身后的长发。轮廓像腰：头那里最宽，到脖子收进去，肩膀以下再放开，发尾收尖到裙摆。"""
    c = Canvas()
    # 被肩膀挡住的里层，最暗（收在身体后面，别从收腰处露出来）
    c.poly([(34, 56), (70, 56), (76, 92), (78, 122), (26, 122), (28, 92)], "H5")
    # 左：贴着身体，被账本挡一部分
    _mass(c, [[(21, 44), (19, 60), (27, 72), (27, 82)],
              [(27, 82), (26, 92), (16, 110), (9, 125)]],
          [(12, 131), (16, 122), (20, 129), (24, 119), (27, 124), (29, 116)],
          [(30, 56), (28, 84), (28, 106), (29, 112)], side=-1)
    # 右：放开得更多（原图的头发是往这一侧甩的），发尾多一簇
    _mass(c, [[(83, 44), (85, 60), (77, 72), (77, 82)],
              [(77, 82), (78, 92), (88, 110), (95, 125)]],
          [(92, 131), (88, 122), (84, 129), (80, 119), (77, 124), (75, 116)],
          [(74, 56), (76, 84), (76, 106), (75, 112)], side=1)
    # 后脑勺
    c.ell(HEAD, "H3")
    return c


def _bangs() -> Canvas:
    """刘海 + 头顶：所有毛束都从发旋放射下来，叠成一整片，末端削尖；整层裁回头的圆里。"""
    c = Canvas()

    def cap_y(x):
        return 29 + 13 * ((x - 52) / 31) ** 2

    cap = Canvas()
    cap.ell(HEAD, "H2")
    for y in range(H):
        for x in range(W):
            if cap.get(x, y)[3] and y < cap_y(x):
                c.px(x, y, "H2")
    # 头顶两侧往后转的暗面，让头有体积
    c.strand([(30, 26), (23, 40), (22, 56), (24, 70)], 9, fill="H3", taper=0.6)
    c.strand([(76, 26), (82, 40), (82, 56), (80, 70)], 9, fill="H3", taper=0.6)
    # 发际线起笔，根部宽、快到末端才收尖；长短交错，眼睛上方的两束短一点；发梢都朝脸的方向收
    bangs = [
        # 根 x, 尖 x, 尖 y, 根宽
        (27, 25, 56, 12),
        (34, 32, 52, 14),
        (42, 39, 47, 14),
        (49, 47, 54, 11),
        (55, 56, 46, 12),
        (61, 61, 53, 11),
        (67, 67, 47, 14),
        (73, 74, 52, 14),
        (79, 80, 56, 12),
    ]
    for xr, xt, yt, w in bangs:
        yr = cap_y(xr) - 5
        bend = (xt - xr) * 0.6
        ctrl = [(xr, yr), (xr + bend * 0.2, yr + (yt - yr) * 0.4), (xt - bend * 0.3, yr + (yt - yr) * 0.75), (xt, yt)]
        side = 1 if xt < 52 else -1  # 每束靠脸中间的那一侧压暗
        c.strand(ctrl, w, fill="H2", shade="H3", side=side, shade_frac=0.3, cut="H4", cut_span=(0.35, 1.0),
                 taper=0.55, hi="H1", hi_span=(0.12, 0.3))
    # 天使环上零星几点最亮的高光
    for x in range(27, 80, 6):
        t = (x - 53) / 28
        y = 27 + 7 * t * t
        c.px(x, y, "HL")
        c.px(x + 1, y, "HL")
    c.clip_ellipse(HEAD)
    return c


def _side_locks() -> Canvas:
    """鬓发：都贴着脸颊走，不超出收腰的轮廓。左边一缕尖朝下巴、下端藏到账本后面；右边一缕搭在肩膀和袖子前面。"""
    c = Canvas()
    c.strand([(28, 46), (26, 66), (27, 88), (33, 101)], 0, fill="H2", shade="H3", side=1, shade_frac=0.38,
             hi="H1", hi_span=(0.1, 0.26), cut="H4", cut_span=(0.4, 1.0),
             prof=lambda t: 6 + 4 * math.sin(math.pi * min(1.0, t * 1.15)))
    c.strand([(78, 46), (79, 66), (82, 90), (81, 113)], 0, fill="H2", shade="H3", side=-1, shade_frac=0.36,
             hi="H1", hi_span=(0.1, 0.26), cut="H4", cut_span=(0.4, 1.0),
             prof=lambda t: 6 + 5 * math.sin(math.pi * min(1.0, t * 1.1)))
    return c


def _flow_lines() -> Canvas:
    """从发旋一路画进长发的发丝线，合成时只落在浅色头发上（压在鬓发、发饰下面的那段自然断开）。"""
    c = Canvas()
    for ctrl in ([(53, 14), (37, 17), (24, 44), (23, 74)],
                 [(24, 80), (22, 94), (16, 108), (12, 120)],
                 [(53, 14), (42, 16), (29, 38), (26, 60)],
                 [(53, 14), (49, 18), (45, 23), (42, 30)],
                 [(53, 14), (57, 18), (61, 23), (64, 30)],
                 [(53, 14), (66, 17), (80, 36), (81, 70)],
                 [(80, 80), (82, 94), (88, 108), (92, 120)]):
        c.curve(ctrl, "H3", 0.12, 1.0)
    return c


def _bang_shadow(c: Canvas, bangs: Canvas) -> None:
    """刘海投在额头上的影子：刘海形状往下错两格，落在皮肤上的部分压暗。"""
    for y in range(28, 64):
        for x in range(26, 80):
            if c.get(x, y)[:3] == P["SK"] and bangs.get(x - 1, y - 2)[3] and not bangs.get(x, y)[3]:
                c.px(x, y, "S2")


def _ornament(c: Canvas) -> None:
    """画面右侧的大花发饰（花瓣按 Claude 的星芒排）、黑丝带和流苏。"""
    cx, cy = 75, 24
    # 丝带：两个圈 + 两条尾巴
    c.poly([(75, 26), (86, 21), (89, 28), (81, 31)], "K1", "K0")
    c.line([(84, 23), (87, 27)], "K2")
    c.poly([(75, 28), (66, 31), (67, 36), (75, 33)], "K1", "K0")
    c.line([(69, 32), (72, 31)], "K2")
    c.poly([(80, 30), (87, 45), (85, 53), (80, 42)], "K1", "K0")
    c.line([(83, 34), (85, 45)], "K2")
    c.poly([(77, 32), (78, 43), (76, 48), (75, 38)], "K1", "K0")
    # 流苏：金珠 + 白穗
    for x, top in ((85, 54), (76, 49)):
        c.ell((x - 1, top - 1, x + 1, top + 1), "G1", "G3")
        c.px(x - 1, top - 1, "G0")
        for k in range(-1, 2):
            c.line([(x + k, top + 2), (x + k, top + 8 - abs(k))], "W1" if k else "W0")
        c.px(x, top + 2, "G2")
    # 花瓣：12 瓣，内外两层
    for k in range(12):
        a = k * math.pi / 6 + 0.13
        tip = (cx + math.cos(a) * 10, cy + math.sin(a) * 10)
        l = (cx + math.cos(a + 0.3) * 4.5, cy + math.sin(a + 0.3) * 4.5)
        r = (cx + math.cos(a - 0.3) * 4.5, cy + math.sin(a - 0.3) * 4.5)
        c.poly([(cx, cy), l, tip, r], "O2", "O3")
    for k in range(12):
        a = k * math.pi / 6 + 0.13 + math.pi / 12
        tip = (cx + math.cos(a) * 7, cy + math.sin(a) * 7)
        l = (cx + math.cos(a + 0.35) * 3.5, cy + math.sin(a + 0.35) * 3.5)
        r = (cx + math.cos(a - 0.35) * 3.5, cy + math.sin(a - 0.35) * 3.5)
        c.poly([(cx, cy), l, tip, r], "O1")
    c.ell((cx - 3, cy - 3, cx + 3, cy + 3), "G1", "G3")
    c.px(cx - 1, cy - 1, "G0")
    c.px(cx - 2, cy - 1, "G0")
    c.px(cx + 1, cy + 1, "G2")


# ---------------------------------------------------------------- 脸和五官

def _ears(c: Canvas) -> None:
    """尖耳朵（精灵耳）压在头发下面，只露耳尖；右耳戴耳坠。"""
    for flip in (False, True):
        def X(x):
            return 103 - x if flip else x
        c.poly([(X(32), 47), (X(13), 39), (X(21), 50), (X(31), 58)], "SK", "S3")
        c.line([(X(18), 43), (X(28), 51)], "S2")
        c.line([(X(14), 40), (X(21), 49)], "S3")
    c.ell((84, 50, 86, 52), "G1", "G3")
    c.px(84, 50, "G0")
    c.line([(85, 53), (85, 58)], "W1")
    c.px(85, 59, "G2")


def _face(c: Canvas, face: str) -> str:
    c.ell((30, 28, 74, 74), "SK", "S3")
    # 下巴：圆脸收一点尖
    c.poly([(35, 62), (69, 62), (63, 70), (52, 74), (41, 70)], "SK")
    c.line([(31, 58), (35, 65), (41, 70), (47, 73), (52, 74), (57, 73), (63, 70), (69, 65), (73, 58)], "S3")

    le, re, mouth, brow, extra = face_spec(face)
    c.patch(EYE_L[0], EYE_L[1], EYES[le], EYE_LEGEND)
    c.patch(EYE_R[0], EYE_R[1], EYES[re], EYE_LEGEND, flip=True)

    for (x, y) in ((33, 62), (34, 61), (36, 62), (37, 61), (39, 62), (40, 61)):
        c.px(x, y, "BL")
        c.px(103 - x, y, "BL")
    if "blush+" in extra:
        for (x, y) in ((32, 63), (35, 63), (38, 63), (41, 63), (35, 60), (38, 60)):
            c.px(x, y, "BL")
            c.px(103 - x, y, "BL")

    rows = MOUTHS[mouth]
    mw = max(len(r) for r in rows)
    c.patch(CX - mw // 2, 64, rows, MOUTH_LEGEND)

    if "tears" in extra:
        for x, y in ((33, 58), (33, 59), (32, 60), (32, 61), (32, 62), (70, 58), (70, 59), (71, 60), (71, 61), (71, 62)):
            c.px(x, y, "TE")
    return brow


def _brows(c: Canvas, brow: str) -> None:
    """眉毛压在刘海上（日系 Q 版常见的“透眉”）。"""
    for dx, dy in BROWS[brow]:
        c.px(EYE_L[0] + dx, EYE_L[1] + dy, "HO")
        c.px(EYE_R[0] + 12 - dx, EYE_R[1] + dy, "HO")


# ---------------------------------------------------------------- 身体和衣服

def _frill(c: Canvas, x0, x1, y, fill="W1", shade="W2", edge="W3", period=3, depth=2, yfn=None):
    """一排荷叶边：每 period 格一个弧，弧之间压暗，下沿描一道。yfn 给出时每列的起点按它算（弧形裙边）。"""
    for x in range(x0, x1 + 1):
        ph = (x - x0) % period
        y0 = y if yfn is None else yfn(x)
        bottom = y0 + (depth if ph == period // 2 else depth - 1)
        for yy in range(y0, bottom):
            c.px(x, yy, shade if ph == 0 else fill)
        c.px(x, bottom, edge)


def _hem_y(x: float) -> int:
    """外裙下摆：中间最低、两头往上收的弧。"""
    return round(124 + 2 * (1 - ((x - 52) / 34) ** 2))


def _body(c: Canvas) -> None:
    # 裙子里层（黑）+ 最底下一圈白蕾丝，下摆也是弧
    c.poly([(30, 106), (74, 106)] + [(x, _hem_y(x) + 3) for x in range(90, 13, -1)], "K1", "K0")
    _frill(c, 14, 90, 0, "W1", "W2", "W3", period=4, depth=3, yfn=lambda x: _hem_y(x) + 1)

    # 腿：裙摆和靴子之间露一截；右脚往前半步（低一格），两只脚微微外八
    c.rect((41, 127, 48, 134), "SK", "S3")
    c.line([(42, 128), (42, 133)], "S2")
    c.rect((56, 127, 63, 135), "SK", "S3")
    c.line([(57, 128), (57, 134)], "S2")
    for x0, y0, lean in ((40, 134, -1), (55, 135, 1)):
        c.poly([(x0, y0), (x0 + 9, y0), (x0 + 9 + lean, y0 + 12), (x0 + lean, y0 + 12)], "W1", "W3")
        c.line([(x0 + 1, y0 + 1), (x0 + 1 + lean, y0 + 11)], "W0")
        c.line([(x0 + 8, y0 + 1), (x0 + 8 + lean, y0 + 11)], "W2")
        for y in range(y0 + 2, y0 + 10, 3):
            c.px(x0 + 3, y, "B1")
            c.px(x0 + 6, y, "B1")
            c.px(x0 + 4, y + 1, "B2")
            c.px(x0 + 5, y + 1, "B2")
        c.rect((x0 + lean, y0 + 12, x0 + 9 + lean, y0 + 13), "B2")
        c.rect((x0 + lean + (6 if lean < 0 else 0), y0 + 13, x0 + lean + (9 if lean < 0 else 3), y0 + 14), "B3")

    # 外层米白裙：前面开口；下摆是弧，裙边黑底金纹、上沿锯齿
    c.poly([(37, 100), (67, 100)] + [(x, _hem_y(x)) for x in range(86, 17, -1)], "W1", "W3")
    for pts in ([(31, 106), (24, 119)], [(35, 104), (31, 119)], [(73, 106), (80, 119)], [(69, 104), (73, 119)]):
        c.line(pts, "W2")
    for pts in ([(28, 110), (26, 116)], [(76, 110), (78, 116)]):
        c.line(pts, "W0")
    # 前开口里的三层荷叶边：黑、橙、白
    c.poly([(47, 101), (57, 101), (63, 119), (41, 119)], "K1")
    _frill(c, 42, 62, 106, "K1", "K0", "K0", period=3, depth=3)
    for x in range(43, 62, 3):
        c.px(x, 106, "K2")
    c.poly([(42, 110), (62, 110), (63, 116), (41, 116)], "O2")
    _frill(c, 41, 63, 114, "O1", "O3", "O3", period=3, depth=3)
    c.poly([(41, 117), (63, 117), (64, 120), (40, 120)], "W0")
    _frill(c, 40, 64, 118, "W0", "W2", "W3", period=3, depth=2)
    # 开口两边的橙色滚边 + 金线
    c.line([(47, 101), (41, 120)], "O2", 2)
    c.line([(57, 101), (63, 120)], "O2", 2)
    for y in range(103, 119, 3):
        t = (y - 101) / 19
        c.px(47 - 6 * t - 2, y, "G1")
        c.px(57 + 6 * t + 2, y, "G1")
    # 裙边：黑底，上沿锯齿、金线，底下一排金点
    for x in range(18, 87):
        top = 120 + abs(((x - 18) % 8) - 4) // 2
        for y in range(top, _hem_y(x) + 1):
            c.px(x, y, "K1")
        c.px(x, top, "G1")
        c.px(x, _hem_y(x), "K0")
        if (x - 18) % 8 == 4:
            c.px(x, _hem_y(x) - 2, "G2")
            c.px(x, _hem_y(x) - 1, "G1")
    # 裙上的小橙花
    for fx, fy in ((27, 112), (78, 110), (32, 116)):
        for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
            c.px(fx + dx, fy + dy, "O1")
        c.px(fx, fy, "G1")
    # 腰两侧的金流苏
    for x, d in ((38, -1), (66, 1)):
        c.line([(x, 101), (x + d * 2, 108)], "G2")
        c.rect((x + d * 2 - 1, 108, x + d * 2 + 1, 110), "G1", "G3")
        c.px(x + d * 2 - 1, 108, "G0")
        for k in (-1, 0, 1):
            c.line([(x + d * 2 + k, 111), (x + d * 2 + k, 117 - abs(k))], "G2" if k else "G1")

    # 黑色胸衣 + 金色系带 + 金链 + 怀表
    c.poly([(40, 88), (64, 88), (67, 102), (37, 102)], "K1", "K0")
    c.line([(42, 90), (40, 100)], "K2")
    c.line([(62, 90), (64, 100)], "K0")
    for y in range(90, 101, 2):
        c.px(50, y, "G1")
        c.px(54, y, "G1")
        c.px(51, y + 1, "G2")
        c.px(53, y + 1, "G2")
        c.px(52, y, "G2")
    for x in range(39, 66):
        y = 98 + round(1.6 * math.sin((x - 39) / 26 * math.pi))
        c.px(x, y, "G1" if x % 2 else "G2")
    c.ell((61, 97, 67, 103), "G1", "G3")
    c.ell((62, 98, 66, 102), "W0", "G2")
    c.px(64, 99, "OL")
    c.px(64, 100, "OL")
    c.px(65, 100, "OL")

    # 披肩：米白底、下摆橙色花纹边 + 金线
    c.poly([(39, 76), (65, 76), (81, 93), (23, 93)], "W1", "W3")
    for pts in ([(37, 81), (31, 91)], [(44, 79), (42, 91)], [(67, 81), (73, 91)], [(60, 79), (62, 91)]):
        c.line(pts, "W2")
    c.poly([(25, 89), (79, 89), (81, 93), (23, 93)], "O3")
    c.line([(25, 89), (79, 89)], "G1")
    for x in range(26, 79, 4):
        c.px(x, 91, "O1")
        c.px(x + 1, 90, "O1")
        c.px(x + 2, 91, "G1")
    _frill(c, 22, 82, 93, "W1", "W2", "W3", period=4, depth=2)

    # 泡泡袖：肩膀在披肩边缘底下，袖子从披肩下沿露出来（左边大半被账本挡住）
    c.ell((18, 92, 33, 107), "W1", "W3")
    c.line([(21, 97), (26, 103)], "W2")
    c.ell((70, 92, 85, 107), "W1", "W3")
    c.line([(82, 97), (77, 103)], "W2")
    c.line([(73, 95), (78, 94)], "W0")
    # 右边：袖口荷叶边，手叉在腰上
    c.poly([(70, 105), (81, 105), (80, 110), (69, 109)], "W0", "W3")
    _frill(c, 69, 80, 109, "W0", "W2", "W3", period=3, depth=2)
    c.ell((65, 107, 72, 113), "SK", "S3")
    c.line([(67, 110), (70, 110)], "S2")

    # 脖子和高领荷叶边
    c.rect((47, 70, 57, 78), "SK", "S3")
    c.rect((48, 70, 56, 73), "S2")
    c.poly([(42, 75), (62, 75), (60, 80), (44, 80)], "W0", "W3")
    _frill(c, 43, 61, 79, "W0", "W2", "W3", period=3, depth=2)
    # 胸前的叠层领巾
    for i, y in enumerate((82, 85, 88)):
        c.poly([(47 - i, y), (57 + i, y), (56 + i, y + 3), (48 - i, y + 3)], "W0", "W3")
        _frill(c, 47 - i, 57 + i, y + 2, "W0", "W2", "W3", period=3, depth=2)
    # 黑丝带蝴蝶结 + 橙花胸针
    c.poly([(52, 79), (43, 75), (42, 83)], "K1", "K0")
    c.poly([(52, 79), (61, 75), (62, 83)], "K1", "K0")
    c.line([(44, 77), (44, 81)], "K2")
    c.line([(60, 77), (60, 81)], "K2")
    c.poly([(50, 80), (46, 91), (49, 90)], "K1", "K0")
    c.poly([(54, 80), (58, 91), (55, 90)], "K1", "K0")
    for dx, dy in ((0, -2), (-2, 0), (2, 0), (0, 2), (-1, -1), (1, 1), (1, -1), (-1, 1)):
        c.px(52 + dx, 79 + dy, "O1")
    c.px(52, 79, "G1")
    c.px(51, 78, "G0")


def _book(c: Canvas) -> None:
    """抱在胸前的账本：深棕封面、金包角、橙色星芒徽章、侧面露出书页。左手从袖子正下方垂下来握着书的左下角。"""
    c.poly([(40, 84), (43, 86), (45, 111), (42, 110)], "W1", "W3")
    c.line([(42, 87), (44, 109)], "W2")
    c.poly([(25, 112), (42, 110), (45, 111), (27, 114)], "W2", "W3")
    c.poly([(23, 86), (40, 84), (42, 110), (25, 112)], "B1", "B3")
    c.poly([(24, 87), (27, 87), (29, 111), (26, 111)], "B2")
    c.line([(28, 87), (30, 111)], "B3")
    c.line([(31, 87), (39, 86)], "B2")
    c.line([(31, 88), (38, 87)], "B1")
    for (x, y) in ((31, 88), (38, 87), (33, 109), (40, 108)):
        c.rect((x - 1, y - 1, x + 1, y + 1), "G1", "G3")
        c.px(x - 1, y - 1, "G0")
    cx, cy = 34, 98
    for k in range(8):
        a = k * math.pi / 4
        ln = 5 if k % 2 == 0 else 3.5
        c.line([(cx, cy), (cx + math.cos(a) * ln, cy + math.sin(a) * ln)], "O1")
    c.ell((cx - 1, cy - 1, cx + 1, cy + 1), "G1")
    c.px(cx, cy, "G0")
    # 左手：袖口荷叶边接在泡泡袖底下，手握着书的左下角，拇指搭在封面边上
    c.poly([(19, 104), (28, 104), (28, 108), (19, 108)], "W0", "W3")
    _frill(c, 19, 28, 107, "W0", "W2", "W3", period=3, depth=2)
    c.ell((19, 108, 29, 117), "SK", "S3")
    c.line([(21, 112), (27, 112)], "S2")
    c.line([(21, 114), (27, 114)], "S2")
    c.ell((25, 106, 29, 110), "SK", "S3")


# ---------------------------------------------------------------- 小 Clawd

CLAWD_LEGEND = {"c": "C1", "d": "C2", "l": "C3", "k": "K1", "g": "G1", "G": "G2", "r": "RD"}
CROWN = [
    "g.g.g",
    "gGrGg",
    "GGGGG",
]
CLAWD = {
    0: [
        "...llllllllllll...",
        "...cccccccccccc...",
        "...cckcccccckcc...",
        "...cckcccccckcc...",
        ".cccccccccccccccc.",
        ".cccccccccccccccc.",
        "...cccccccccccc...",
        "...dddddddddddd...",
        "....d.d....d.d....",
        "....d.d....d.d....",
    ],
    1: [  # 举起两只小手、换腿
        "...llllllllllll...",
        "cc.cccccccccccc.cc",
        "cc.cckcccccckcc.cc",
        ".cccckcccccckcccc.",
        "...cccccccccccc...",
        "...cccccccccccc...",
        "...cccccccccccc...",
        "...dddddddddddd...",
        ".....d.d..d.d.....",
        ".....d.d..d.d.....",
    ],
    2: [  # 眨眼
        "...llllllllllll...",
        "...cccccccccccc...",
        "...cccccccccccc...",
        "...cckcccccckcc...",
        ".cccccccccccccccc.",
        ".cccccccccccccccc.",
        "...cccccccccccc...",
        "...dddddddddddd...",
        "....d.d....d.d....",
        "....d.d....d.d....",
    ],
}


def build_clawd(frame: int) -> Image.Image:
    rows = CLAWD[frame]
    w = max(len(r) for r in rows)
    img = Image.new("RGBA", (w + 2, len(rows) + len(CROWN) + 2), (0, 0, 0, 0))
    for dy, row in enumerate(CROWN):
        for dx, ch in enumerate(row):
            if ch in CLAWD_LEGEND:
                img.putpixel((1 + (w - 5) // 2 + dx, 1 + dy), rgba(CLAWD_LEGEND[ch]))
    for dy, row in enumerate(rows):
        for dx, ch in enumerate(row):
            if ch in CLAWD_LEGEND:
                img.putpixel((1 + dx, 1 + len(CROWN) + dy), rgba(CLAWD_LEGEND[ch]))
    return _ring(img, (*P["OL"], 255))


def clawd_spot(im: Image.Image) -> tuple[int, int]:
    """小 Clawd（只带深色描边的那张）的左上角：脚踩在发顶。"""
    return CX - im.width // 2 + 1, 16 - im.height


# ---------------------------------------------------------------- 组装

PAD = 3


def _sticker(img: Image.Image, pad: int = PAD) -> Image.Image:
    """白衣贴边处先补一圈暖灰轮廓，再深色描边 + 两圈白边，像表情包那样的贴纸边。"""
    img = inner_outline(img, P["WO"], only=WHITES)
    big = Image.new("RGBA", (img.width + pad * 2, img.height + pad * 2), (0, 0, 0, 0))
    big.alpha_composite(img, (pad, pad))
    big = _ring(big, (*P["OL"], 255))
    big = _ring(big, (255, 255, 255, 255))
    return _ring(big, (255, 255, 255, 255))


@lru_cache(maxsize=4)
def _hair_layers():
    return _back_hair(), _side_locks(), _bangs(), _flow_lines()


@lru_cache(maxsize=8)
def _body_layer() -> Canvas:
    c = Canvas()
    _body(c)
    return c


@lru_cache(maxsize=32)
def _head_layer(face: str) -> Canvas:
    """耳朵、脸、鬓发、刘海、发饰、眉毛（都跟着头一起呼吸）。头发在这里还没描边。"""
    _, locks, bangs, _ = _hair_layers()
    head = Canvas()
    _ears(head)
    brow = _face(head, face)
    _bang_shadow(head, bangs)
    head.paste(locks)
    head.paste(bangs)
    _ornament(head)
    _brows(head, brow)
    return head


@lru_cache(maxsize=128)
def build_sprite(face: str = "smug", clawd: int | None = 0, bob: int = 0) -> Image.Image:
    """格子分辨率的整张立绘。

    face：FACES 里的名字，或 'calm:blink'；clawd=None 时头顶不画小 Clawd（它单独跳的时候用）；
    bob：呼吸相位 0/1，头（连同后发）往下一格时小 Clawd 往上一格。
    """
    back, _, _, flow = _hair_layers()
    c = Canvas()
    c.paste(back, bob)
    c.paste(_body_layer())
    c.paste(_head_layer(face), bob)
    c.paste(flow, bob, only=HAIR_LIGHT)
    c.replace(hair_outline(c.img))
    _book(c)
    if clawd is not None:
        im = build_clawd(clawd)
        x, y = clawd_spot(im)
        c.img.alpha_composite(im, (x, y + 1 - bob))
    return _sticker(c.img)


EYE_LINE = EYE_Y + PAD  # 贴纸图里眼睛的高度，挂件用来对齐气泡
ZZZ_SPOT = (16 + PAD, 30 + PAD)  # 瞌睡时 z 从头的左上方飘出来（贴纸图的格子坐标）


@lru_cache(maxsize=8)
def clawd_sticker(frame: int) -> tuple[Image.Image, tuple[int, int]]:
    """单独的小 Clawd 贴纸，和它坐在头顶时的左上角（贴纸图的格子坐标）。"""
    im = build_clawd(frame)
    x, y = clawd_spot(im)
    big = Image.new("RGBA", (im.width + 4, im.height + 4), (0, 0, 0, 0))
    big.alpha_composite(im, (2, 2))
    big = _ring(_ring(big, (255, 255, 255, 255)), (255, 255, 255, 255))
    return big, (x + PAD - 2, y + PAD - 2)


def scaled(face: str = "smug", clawd: int | None = 0, k: int = 4, bob: int = 0) -> Image.Image:
    img = build_sprite(face, clawd, bob)
    return img.resize((img.width * k, img.height * k), Image.NEAREST)


def silhouette(face: str = "smug", k: int = 4) -> Image.Image:
    """纯黑剪影，检查外轮廓哪里鼓出来用。"""
    img = build_sprite(face, 0)
    a = img.getchannel("A")
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste((20, 20, 20, 255), mask=a)
    return out.resize((img.width * k, img.height * k), Image.NEAREST)


# ---------------------------------------------------------------- 气泡里的大号像素数字

GLYPHS = {
    "0": [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": ["#####", "...#.", "..#..", "...#.", "....#", "#...#", ".###."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "6": ["..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    "9": [".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."],
    "%": ["##..#", "##..#", "...#.", "..#..", ".#...", "#..##", "#..##"],
    "-": [".....", ".....", ".....", "#####", ".....", ".....", "....."],
    "?": [".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."],
}


def pixel_text(text: str, color=(238, 118, 50)) -> Image.Image:
    """格子分辨率的像素字：单色填充、深色描边、一圈白边。"""
    glyphs = [GLYPHS.get(ch, GLYPHS["?"]) for ch in text]
    w = sum(len(g[0]) for g in glyphs) + (len(glyphs) - 1)
    img = Image.new("RGBA", (w, 7), (0, 0, 0, 0))
    x = 0
    for g in glyphs:
        for y, row in enumerate(g):
            for dx, ch in enumerate(row):
                if ch == "#":
                    img.putpixel((x + dx, y), (*color, 255))
        x += len(g[0]) + 1
    big = Image.new("RGBA", (w + 4, 11), (0, 0, 0, 0))
    big.alpha_composite(img, (2, 2))
    big = _ring(big, (*P["OL"], 255))
    return _ring(big, (255, 255, 255, 255))


# ---------------------------------------------------------------- 点击时飞出来的小粒子、瞌睡的 z

PARTICLES = {
    "heart": [".#.#.", "#####", "#####", ".###.", "..#.."],
    "star": ["..#..", ".###.", "#####", ".#.#.", "#...#"],
    "spark": ["..#..", "..#..", "##.##", "..#..", "..#.."],
    "note": ["..##", "..#.#", "..#..", "###..", "##..."],
    "dot": ["##", "##"],
    "z": ["###", "..#", ".#.", "###"],
    "Z": ["####", "...#", "..#.", ".#..", "####"],
}
PARTICLE_COLORS = [(255, 122, 150), (252, 208, 92), (240, 126, 62), (255, 255, 255), (150, 214, 255)]


@lru_cache(maxsize=64)
def particle(shape: str, color: tuple[int, int, int]) -> Image.Image:
    rows = PARTICLES[shape]
    w = max(len(r) for r in rows)
    img = Image.new("RGBA", (w + 2, len(rows) + 2), (0, 0, 0, 0))
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == "#":
                img.putpixel((x + 1, y + 1), (*color, 255))
    return _ring(img, (*P["OL"], 255))


if __name__ == "__main__":
    import pathlib

    out = pathlib.Path(__file__).with_name("preview")
    out.mkdir(exist_ok=True)
    # 按挂件状态的顺序排：回满 / 正常 / 过半 / 快用完 / 耗尽 / 数据过期 / 点击 / 连点，再加眨眼和开心
    order = ["smug", "smile", "calm", "strain", "cry", "sleepy", "wink", "pout", "smug:blink", "wow"]
    k = 3
    tile = scaled("smug", 0, k)
    sheet = Image.new("RGBA", (tile.width * 5, tile.height * 2), (31, 31, 30, 255))
    for i, f in enumerate(order):
        cl = 1 if f == "wink" else (2 if f.endswith(":blink") else 0)
        sheet.alpha_composite(scaled(f, cl, k, bob=i % 2), ((i % 5) * tile.width, (i // 5) * tile.height))
    sheet.save(out / "sheet.png")
    big = scaled("smug", 0, 6)
    bg = Image.new("RGBA", big.size, (31, 31, 30, 255))
    bg.alpha_composite(big)
    bg.save(out / "clawd_chan_big.png")
    sil = silhouette("smug", 3)
    bg = Image.new("RGBA", (sil.width * 2 + 20, sil.height), (200, 200, 200, 255))
    bg.alpha_composite(sil, (0, 0))
    bg.alpha_composite(sil.transpose(Image.FLIP_LEFT_RIGHT), (sil.width + 20, 0))
    bg.save(out / "silhouette.png")
    print("ok", sheet.size, build_sprite().size)
