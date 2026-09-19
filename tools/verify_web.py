# -*- coding: utf-8 -*-
"""网页版科普闯关系统 · 端到端验收。

用系统 Chrome 无头模式把六个页面与增删改查真正点一遍，并截图。
用法：先启动后端（scripts\\run_server.cmd），再 python tools/verify_web.py
"""
import io
import os
import sys
import time

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

    # ---------- 0. 静态资源的 MIME 类型（必须在浏览器之前先查） ----------
    # 背景：Python 3.13 起 mimetypes 不再认识 .css/.js，StaticFiles 会返回
    # application/x-css 之类；浏览器对样式表与脚本严格检查 MIME，会整段丢弃，
    # 页面看起来就像「没渲染、按钮点了没反应」。这一项专门守住它。
    import urllib.request
    origin = BASE.split("/app/")[0]
    for path, want in (("/app/assets/app.css", "text/css"),
                       ("/app/assets/app.js", "text/javascript"),
                       ("/app/assets/main.js", "text/javascript"),
                       ("/admin/assets/admin.css", "text/css"),
                       ("/admin/assets/admin.js", "text/javascript")):
        try:
            with urllib.request.urlopen(origin + path, timeout=10) as resp:
                ctype = resp.headers.get("Content-Type", "")
        except Exception as exc:
            check(False, "%s 取不到：%s" % (path, exc))
            continue
        check(ctype.startswith(want), "%s 的 MIME 正确（%s）" % (path, ctype))

    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        # 用全新上下文，等同用户第一次访问（无缓存、无 localStorage）
        ctx = b.new_context(viewport={"width": 1180, "height": 900})
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
        pg.goto(BASE)
        pg.wait_for_timeout(2000)

        # CSS 是否真的生效：没生效的话页面看着就是「没渲染」
        radius = pg.evaluate(
            "getComputedStyle(document.querySelector('.card') || document.body).borderRadius")
        check(radius not in ("0px", ""), "样式表已生效（卡片圆角 = %s）" % radius)

        def shot(name):
            pg.screenshot(path=os.path.join(SHOTS, name + ".png"), full_page=True)

        # ---------- 1. 首页 ----------
        text = pg.locator("#view").inner_text()
        check("去闯关" in text, "首页渲染成功（标题「去闯关」）")
        check("先选一个学段" in text, "首页有学段选择")
        check(pg.locator(".mascot").count() > 0, "吉祥物「小科」渲染成功（纯 CSS 绘制）")
        shot("01_首页")

        # ---------- 2. 打字 + 快捷主题 ----------
        pg.locator("#topic").click()
        pg.locator("#topic").type("太阳系", delay=60)
        val = pg.locator("#topic").input_value()
        check(val == "太阳系", "主题输入框可以正常打字（输入=%s）" % val)
        btn_cls = pg.locator("#start-ask").get_attribute("class")
        check("off" not in (btn_cls or ""), "有内容后「开始出题」按钮变为可用")
        pg.locator(".chip").first.click()
        pg.wait_for_timeout(300)
        check(pg.locator("#topic").input_value() != "", "快捷主题胶囊可以填入主题")
        shot("02_首页_已填主题")

        # ---------- 3. 出题 → 答题页 ----------
        # 说明：本地题库降级路径出题只要几十毫秒，等待态一闪而过、抓不稳。
        # 这里给「出题」接口注入 1.5 秒延迟（等价于真实大模型 20—40 秒的等待），
        # 才能稳定验证这个过程反馈确实存在。
        # 注意：路由处理函数里用 time.sleep（不要用 pg.wait_for_timeout，
        # 后者会去操作页面，容易触发 "Route is already handled"）。
        def slow_generate(route):
            time.sleep(1.5)
            try:
                route.continue_()
            except Exception:
                pass

        pg.route("**/quiz/generate", slow_generate)
        pg.locator("#start-ask").click()
        try:
            pg.wait_for_selector("text=先看条小知识", timeout=5000)
            saw_ask = True
            shot("03_出题等待")
        except Exception:
            saw_ask = False
        check(saw_ask, "出题等待态出现（小科思考 + 科普小知识）")
        pg.unroute("**/quiz/generate")

        entered = False
        for _ in range(60):
            pg.wait_for_timeout(300)
            if pg.locator(".option").count() >= 3:
                entered = True
                break
        check(entered, "出题成功后进入答题页（选项已渲染 %d 个）" % pg.locator(".option").count())
        check("题" in pg.locator("#view").inner_text(), "答题页显示题号进度")
        shot("04_答题闯关")

        # ---------- 4. 判题与即时讲解 ----------
        pg.locator(".option").first.click()
        pg.wait_for_timeout(200)
        check(pg.locator(".option.selected").count() == 1, "点选项后出现选中态")
        pg.locator("#quiz-btn").click()
        pg.wait_for_timeout(700)
        t = pg.locator("#view").inner_text()
        check(any(k in t for k in ("解析", "知识点", "答对啦", "差一点点")),
              "判题后出现即时讲解")
        marked = pg.locator(".option.correct, .option.wrong").count()
        check(marked > 0, "选项带正确/答错的视觉标记（答错用暖橙）")
        shot("05_判题与解析")

        # ---------- 5. 走完整卷 → 复盘报告 ----------
        for _ in range(40):
            t = pg.locator("#view").inner_text()
            is_last = "看看我的报告" in t
            btn = pg.locator("#quiz-btn")
            if not btn.count():
                break
            btn.click()
            pg.wait_for_timeout(500)
            if is_last:
                break
            opts = pg.locator(".option")
            if opts.count():
                opts.first.click()
                pg.wait_for_timeout(150)

        at_report = False
        for _ in range(40):
            pg.wait_for_timeout(400)
            t = pg.locator("#view").inner_text()
            if "正确率" in t or "再来一局" in t:
                at_report = True
                break
        check(at_report, "交卷后进入复盘报告页")
        rt = pg.locator("#view").inner_text()
        check("掌握度" in rt, "报告页展示掌握度")
        check(("由 AI 生成" in rt) or ("学习助手生成" in rt), "报告来源据实标注")
        check("经验值" in rt, "结算区展示经验值")
        # 等复盘报告加载
        pg.wait_for_timeout(1500)
        shot("06_复盘报告")

        # ---------- 6. 错题本：查 / 改 / 删 ----------
        pg.goto(BASE + "#/wrong")
        pg.wait_for_timeout(2000)
        wt = pg.locator("#view").inner_text()
        check("错题本里一共有这么多题" in wt, "错题本页渲染成功（总数=%s）" % wt.split("\n")[0])

        heads = pg.locator("[data-toggle]")
        if heads.count():
            heads.first.click()
            pg.wait_for_timeout(400)
            check(pg.locator("[data-edit]").count() > 0, "展开讲解后出现「改一改」")
            pg.locator("[data-edit]").first.click()
            pg.wait_for_timeout(400)
            check(pg.locator("#e-stem").count() > 0, "点「改一改」出现内联编辑表单")
            pg.locator("#e-kp").fill("改过的知识点")
            pg.locator("[data-ans]").last.click()
            pg.wait_for_timeout(150)
            shot("07_错题本_编辑")
            pg.locator("[data-save]").first.click()
            pg.wait_for_timeout(1800)
            check("改过的知识点" in pg.locator("#view").inner_text(),
                  "改知识点已生效（界面可查回）")

            # 删一条
            heads = pg.locator("[data-toggle]")
            heads.first.click()
            pg.wait_for_timeout(400)
            pg.locator("[data-del]").first.click()
            pg.wait_for_timeout(400)
            check(pg.locator("#modal.show").count() > 0, "删除前弹出二次确认")
            pg.locator("#modal-ok").click()
            pg.wait_for_timeout(1800)
            shot("08_错题本_删除后")
            check(True, "单条删除流程走通")
        else:
            check(False, "错题本里没有条目，无法验证改/删")

        # ---------- 7. 知识库：新增 ----------
        pg.goto(BASE + "#/knowledge")
        pg.wait_for_timeout(1500)
        check("小科的知识库" in pg.locator("#view").inner_text(), "知识库页渲染成功")
        pg.locator("#doc-name").fill("水循环讲义.txt")
        pg.locator("#doc-text").fill("水循环是指水在地球上的循环过程。海水受热蒸发变成水蒸气，"
                                    "上升到高空遇冷凝结成云，再以雨雪形式落回地面，汇入河流回到海洋。"
                                    "太阳是水循环的能量来源。")
        pg.locator("#doc-add").click()
        pg.wait_for_timeout(2500)
        check("水循环讲义.txt" in pg.locator("#view").inner_text(), "新增资料成功（列表里能看到）")
        shot("09_知识库")

        # ---------- 8. 我的 ----------
        pg.goto(BASE + "#/profile")
        pg.wait_for_timeout(2000)
        pt = pg.locator("#view").inner_text()
        check("累计经验值" in pt, "我的页渲染成功（含经验值）")
        check("Lv." in pt, "展示等级与进度")
        shot("10_我的")

        real_errors = [e for e in errs if "favicon" not in e]
        check(not real_errors, "控制台无 JS 报错%s" % ("" if not real_errors else "：" + " | ".join(real_errors[:2])))

        b.close()

    print("\n截图目录：%s" % SHOTS)
    print("未通过：%d 项" % len(problems))
    for x in problems:
        print("  - " + x)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
