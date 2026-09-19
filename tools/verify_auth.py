# -*- coding: utf-8 -*-
"""验收：注册 → 登录 → 答题 → 错题本真的收录（用户反馈的那条）。"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright      # noqa: E402

URL = "http://127.0.0.1:8000/app/"
# 每次跑用不同的登录名，避免与上一轮留下的账号冲突（脚本要能反复运行）
USER = "stu" + str(int(__import__("time").time()))[-8:]
PWD = "kepu123456"

problems = []


def check(ok, msg):
    print(("[OK  ] " if ok else "[FAIL] ") + msg)
    if not ok:
        problems.append(msg)


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    ctx = b.new_context(viewport={"width": 1180, "height": 900})
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:200]))

    # ---------- 1. 未登录时应落到登录页 ----------
    pg.goto(URL)
    pg.wait_for_timeout(2000)
    t = pg.locator("#view").inner_text()
    check("登录" in t and "注册" in t, "未登录时进入登录/注册页")
    check(pg.locator("#auth-user").count() == 1, "登录页有登录名与口令输入框")

    # ---------- 2. 注册 ----------
    pg.locator("#tab-register").click()
    pg.wait_for_timeout(300)
    pg.locator("#auth-user").fill(USER)
    pg.locator("#auth-pass").fill(PWD)
    pg.locator("#auth-nick").fill("小明")
    pg.locator("#auth-grade").select_option("primary_low")
    pg.locator("#auth-submit").click()
    pg.wait_for_timeout(2500)
    t = pg.locator("#view").inner_text()
    check("去闯关" in t, "注册成功后进入首页")
    check("小明" in pg.locator("#who").inner_text(), "顶栏显示昵称：%s" % pg.locator("#who").inner_text())

    # ---------- 3. 答题（故意答错）并检查错题本 ----------
    pg.locator(".chip").first.click()
    pg.wait_for_timeout(300)
    pg.locator("#start-ask").click()
    for _ in range(60):
        pg.wait_for_timeout(300)
        if pg.locator(".option").count() >= 3:
            break
    wrong = 0
    for _ in range(20):
        if pg.locator(".option").count() == 0:
            break
        is_last = "看看我的报告" in pg.locator("#view").inner_text()
        pg.locator(".option").last.click()
        pg.wait_for_timeout(150)
        pg.locator("#quiz-btn").click()
        pg.wait_for_timeout(350)
        if pg.locator(".option.wrong").count():
            wrong += 1
        if is_last:
            break
        pg.locator("#quiz-btn").click()
        pg.wait_for_timeout(350)
    check(wrong > 0, "本次故意答错 %d 题" % wrong)

    for _ in range(30):
        pg.wait_for_timeout(400)
        if "正确率" in pg.locator("#view").inner_text():
            break

    # 直接看错题本页（这就是用户说「收录不了」的地方）
    pg.goto(URL + "#/wrong")
    pg.wait_for_timeout(2500)
    wt = pg.locator("#view").inner_text()
    items = pg.locator("[data-toggle]").count()
    check("要登录" not in wt, "错题本页没有再显示「要登录」")
    check(items >= 1, "错题本收录了 %d 道错题（界面条目数）" % items)
    print("     页面文字：", wt[:120].replace("\n", " / "))

    # ---------- 4. 退出后重新登录 ----------
    pg.goto(URL + "#/profile")
    pg.wait_for_timeout(2000)
    pt = pg.locator("#view").inner_text()
    check("累计经验值" in pt, "个人中心显示经验值")
    pg.locator("#auth-switch").click()
    pg.wait_for_timeout(400)
    modal = pg.locator("#modal.show")
    if modal.count():
        pg.locator("#modal-ok").click()
        pg.wait_for_timeout(1200)
    t = pg.locator("#view").inner_text()
    check("登录" in t, "退出后回到登录页")

    pg.locator("#auth-user").fill(USER)
    pg.locator("#auth-pass").fill(PWD)
    pg.locator("#auth-submit").click()
    pg.wait_for_timeout(2500)
    pg.goto(URL + "#/wrong")
    pg.wait_for_timeout(2500)
    items2 = pg.locator("[data-toggle]").count()
    check(items2 >= 1, "重新登录后错题仍在（%d 道）" % items2)

    # ---------- 5. 游客也能试玩 ----------
    # 用全新 context：新页面会共享 localStorage，那样就还是登录态，不是游客
    ctx2 = b.new_context(viewport={"width": 1180, "height": 900})
    pg2 = ctx2.new_page()
    pg2.goto(URL)
    pg2.wait_for_timeout(1800)
    pg2.locator("#auth-guest").click()
    pg2.wait_for_timeout(2500)
    check("去闯关" in pg2.locator("#view").inner_text(), "游客可以直接进入首页试玩")
    check("游客" in pg2.locator("#who").inner_text(),
          "顶栏标明游客身份：%s" % pg2.locator("#who").inner_text())

    check(not errs, "无 JS 报错%s" % ("" if not errs else "：" + " | ".join(errs[:2])))
    b.close()

print("\n未通过：%d 项" % len(problems))
for x in problems:
    print("  - " + x)
sys.exit(1 if problems else 0)
