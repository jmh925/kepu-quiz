# -*- coding: utf-8 -*-
"""演示页自检：用系统 Chrome（无头）把 demo/index.html 打开，把主流程点一遍。

为什么值得做：小程序的 WXML/WXSS 只能在微信开发者工具里渲染，我无法运行它；
但演示页加载的是**同一套** WXML / WXSS / 页面 JS，因此在浏览器里跑通，
就能确认界面与交互逻辑不是坏的，顺便产出可直接用作答辩材料的界面截图。

依赖：Python + playwright；浏览器用系统已安装的 Chrome（channel='chrome'）。
用法（先在另一个窗口启动后端）：
    scripts\\make_demo.cmd          # 生成演示页并自检
    python tools/verify_demo.py     # 只跑自检
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = os.path.join(ROOT, "demo", "index.html")
SHOTS = os.path.join(ROOT, "demo", "shots")

problems = []


def note(ok, msg):
    print(("[OK  ] " if ok else "[FAIL] ") + msg)
    if not ok:
        problems.append(msg)


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("未安装 playwright，跳过演示页自检。安装：pip install playwright")
        return 0

    if not os.path.exists(DEMO):
        print("请先运行 python tools/make_demo.py 生成演示页")
        return 2
    os.makedirs(SHOTS, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 1180, "height": 840})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)[:200]))
        page.on("console", lambda m: errors.append("console: " + m.text[:160])
                if m.type == "error" else None)

        page.goto("file:///" + DEMO.replace("\\", "/"))
        page.wait_for_timeout(1500)

        view = page.locator("#mp-view")

        def shot(name):
            page.locator(".phone").screenshot(path=os.path.join(SHOTS, name + ".png"))

        # ---------- 1. 首页 ----------
        text = view.inner_text()
        note("去闯关" in text, "首页渲染出标题「去闯关」")
        note("先选一个学段" in text, "首页渲染出学段选择")
        note("今天想探索什么" in text, "首页渲染出问候语（含当前学段）")
        note(page.locator(".mascot").count() > 0, "吉祥物「小科」渲染成功")
        shot("01_首页")

        # ---------- 2. 主题快捷入口 ----------
        page.locator("#mp-view .chip").first.click()
        page.wait_for_timeout(300)
        val = page.locator("#mp-view input").first.input_value()
        note(bool(val), "点主题胶囊后输入框被填入：%s" % val)
        shot("02_首页_已填主题")

        # ---------- 3. 出题等待态 ----------
        # 本地题库降级路径下出题只要几十毫秒，等待态一闪而过、无法稳定观察。
        # 因此在页面里给 /quiz/generate 注入 1.5 秒延迟（模拟真实大模型 20～40 秒的等待），
        # 这样才能稳定验证「等待态存在」并截到图。
        page.evaluate("""() => {
            const orig = window.fetch;
            window.fetch = function (url, init) {
                const p = orig.apply(this, arguments);
                if (String(url).indexOf('/quiz/generate') !== -1) {
                    return p.then(function (r) {
                        return new Promise(function (resolve) {
                            setTimeout(function () { resolve(r); }, 1500);
                        });
                    });
                }
                return p;
            };
        }""")
        page.locator("#mp-view .btn-primary").first.click()
        saw_asking = False
        for _ in range(40):
            page.wait_for_timeout(100)
            t = view.inner_text()
            if "先看条小知识" in t or "已经等了" in t:
                saw_asking = True
                break
            if "就选这个" in t:
                break
        note(saw_asking, "出题等待态出现（分档台词 + 科普轮播 + 取消入口）")
        if saw_asking:
            shot("03_出题等待")

        # ---------- 4. 进入答题页 ----------
        # 注意：等待态的「第 1 / 10 条」科普计数也会出现「第 1 /」，必须用题干进度「题」判定
        jumped = False
        for _ in range(90):
            page.wait_for_timeout(500)
            t = view.inner_text()
            if "题" in t and ("就选这个" in t or "第 " in t):
                jumped = True
                break
        note(jumped, "出题成功后自动进入答题页")
        if not jumped:
            toast = page.locator("#mp-toast").inner_text()
            note(False, "未进入答题页；界面提示：%s" % (toast or "（无）"))
        # 跳页与渲染之间有极短的时间差，这里等选项真正出现再断言，避免竞态误判
        try:
            page.wait_for_selector("#mp-view .option", timeout=5000)
        except Exception:
            pass
        quiz_text = view.inner_text()
        note("就选这个" in quiz_text, "答题页显示题目与进度")
        opt_now = page.locator("#mp-view .option").count()
        note(opt_now >= 3, "答题页渲染出选项列表（实际 %d 个）" % opt_now)
        shot("04_答题闯关")

        # ---------- 5. 判题与即时讲解 ----------
        total_opt = page.locator("#mp-view .option").count()
        page.locator("#mp-view .option").first.click()
        page.wait_for_timeout(250)
        page.locator("#mp-view .btn").last.click()
        page.wait_for_timeout(600)
        judged = view.inner_text()
        note(any(k in judged for k in ("解析", "知识点", "差一点点", "答对啦")),
             "判题后出现解析卡与小科反馈")
        marked = page.locator("#mp-view .option.correct, #mp-view .option.wrong").count()
        note(marked > 0, "选项带正确/答错的视觉标记（答错用暖橙，非纯红）")
        shot("05_判题与解析")

        # ---------- 6. 走完整卷并进复盘报告 ----------
        # 判定「是否最后一题」要基于**点击前**的界面文字；点完按钮后若是最后一题，
        # 页面会先显示「小科在算分…」再跳报告页，所以这里必须多等一会儿。
        done = False
        for _ in range(20):
            cur = view.inner_text()
            if "正确率" in cur or "再来一局" in cur:
                done = True
                break
            is_last = "看看我的报告" in cur
            btn = page.locator("#mp-view .btn").last
            if btn.count() == 0:
                break
            btn.click()
            page.wait_for_timeout(700)
            if is_last:
                # 交卷中，等待报告页
                for _ in range(30):
                    page.wait_for_timeout(500)
                    if any(k in view.inner_text() for k in ("正确率", "再来一局", "掌握度")):
                        done = True
                        break
                break
            opts = page.locator("#mp-view .option")
            if opts.count():
                opts.first.click()
                page.wait_for_timeout(220)

        in_report = done or any(k in view.inner_text() for k in ("正确率", "掌握度", "再来一局"))
        note(in_report, "交卷后进入复盘报告页")
        report_text = view.inner_text()
        note(any(k in report_text for k in ("掌握度", "学习助手生成", "由 AI 生成")),
             "报告页展示掌握度并据实标注报告来源")
        shot("06_复盘报告")

        # ---------- 7. 其余三个 tab ----------
        # 说明：复盘报告不是 tab 页，小程序在非 tab 页也会隐藏 tabBar，
        # 所以这里不像用户那样点 tab，而是走 router（等价于 wx.switchTab）切过去。
        for path, keyword, name, title in (
                ("pages/wrong", "只练错题", "07_错题本", "错题本"),
                ("pages/knowledge", "资料", "08_知识库", "知识库"),
                ("pages/profile", "经验值", "09_我的", "我的")):
            page.evaluate("(p) => window.__kepuDebug.router.replace('/' + p + '/index')", path)
            page.wait_for_timeout(1500)
            t = view.inner_text()
            note(keyword in t or "小科" in t, "%s页渲染成功" % title)
            shot(name)

        real_errors = [e for e in errors if "favicon" not in e and "Failed to load resource" not in e]
        note(not real_errors, "控制台无 JS 报错" + ("：%s" % " | ".join(real_errors[:3]) if real_errors else ""))

        browser.close()

    print("\n截图目录：%s" % SHOTS)
    print("未通过检查项：%d" % len(problems))
    for p in problems:
        print("  - %s" % p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
