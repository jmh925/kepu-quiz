# -*- coding: utf-8 -*-
"""给桌面快捷方式生成图标：蓝底圆角 + 白色「科」字。

为什么自己画：快捷方式没有图标就是一页白纸的样子，放在桌面上认不出来。
用系统图标又和项目无关，一眼看不出是哪个东西。
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from PIL import Image, ImageDraw, ImageFont

OUT = r"E:\dev\kepu-quiz\assets\icon.ico"
SIZES = [256, 128, 64, 48, 32, 16]
BLUE = (2, 119, 189)      # 与主色 --c-primary-ink 一致
BLUE_D = (1, 87, 155)
WHITE = (255, 255, 255)


def find_font(size):
    """找一个能显示中文的粗体。找不到就退回默认字体（只画方块）。"""
    cands = [
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\Deng.ttf",
    ]
    for f in cands:
        if os.path.exists(f):
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                continue
    return ImageFont.load_default()


def draw(size):
    # 4 倍超采样，缩小后边缘才干净
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    r = int(s * 0.22)
    # 竖向渐变底：上浅下深，缩小后有一点立体感
    for y in range(s):
        t = y / float(s)
        col = tuple(int(BLUE[i] + (BLUE_D[i] - BLUE[i]) * t) for i in range(3))
        d.line([(0, y), (s, y)], fill=col + (255,))

    # 圆角：用四角遮罩把方形切成圆角
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=r, fill=255)
    img.putalpha(mask)

    # 白色「科」字
    font = find_font(int(s * 0.62))
    text = "科"
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((s - tw) / 2 - bbox[0], (s - th) / 2 - bbox[1]), text,
           font=font, fill=WHITE + (255,))

    return img.resize((size, size), Image.LANCZOS)


os.makedirs(os.path.dirname(OUT), exist_ok=True)
imgs = [draw(x) for x in SIZES]
imgs[0].save(OUT, format="ICO", sizes=[(x, x) for x in SIZES])
print("已生成图标：%s" % OUT)
for x in SIZES:
    print("  %d×%d" % (x, x))
print("  文件大小：%d 字节" % os.path.getsize(OUT))
