# -*- coding: utf-8 -*-
"""为设备预览页（showcase）产出演示截图。

用途：把学生端界面在手机 / 平板三种尺寸下的样子各截一张，
可以直接放进论文或答辩 PPT 当作界面图。

用法：先启动后端，再 python tools/shoot_showcase.py
产物：web/shots/device_*.png
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(ROOT, "web", "shots")
BASE = os.getenv("KEPU_WEB_URL", "http://127.0.0.1:8000/app/")

from playwright.sync_api import sync_playwright      # noqa: E402

problems = []


def check(ok, msg):
    print(("[OK  ] " if ok else "[FAIL] ") + msg)
    if not ok:
        problems.append(msg)


def main():
    os.makedirs(SHOTS, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        pg = b.new_page(viewport={"width": 1440, "height": 1080})

        # 1）预览页整体
        pg.goto(BASE + "showcase.html")
        pg.wait_for_timeout(5000)          # 等三个 iframe 里的应用都加载完
        frames = pg.frames
        check(len(frames) >= 4, "预览页加载了 %d 个内嵌页面（含主页面）" % len(frames))
        pg.screenshot(path=os.path.join(SHOTS, "device_01_三种屏幕.png"), full_page=True)

        # 2）手机尺寸下的完整主流程（在 iframe 里真点一遍）
        target = None
        for f in pg.frames:
            if f.name != "" and "index.html" in (f.url or ""):
                target = f
                break
        if target is None and len(frames) > 1:
            target = frames[1]
        if target is None:
            check(False, "没找到内嵌的学生端页面")
        else:
            target.locator(".chip").first.click()
            target.wait_for_timeout(400)
            target.locator("#start-ask").click()
            for _ in range(60):
                pg.wait_for_timeout(300)
                if target.locator(".option").count() >= 3:
                    break
            n = target.locator(".option").count()
            check(n >= 3, "手机尺寸下能正常答题（选项 %d 个）" % n)
            # 选一个并判题，确认手机壳里也能交互
            target.locator(".option").first.click()
            pg.wait_for_timeout(300)
            check(target.locator(".option.selected").count() == 1,
                  "手机尺寸下选项可以选中")
            target.locator("#quiz-btn").click()
            pg.wait_for_timeout(700)
            t = target.locator("#view").inner_text()
            check(any(k in t for k in ("解析", "知识点", "答对啦", "差一点点")),
                  "手机尺寸下判题后出现讲解")
            pg.screenshot(path=os.path.join(SHOTS, "device_02_手机答题.png"), full_page=True)

        b.close()

    print("\n截图目录：%s" % SHOTS)
    print("未通过：%d 项" % len(problems))
    for x in problems:
        print("  - " + x)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
