# -*- coding: utf-8 -*-
"""验收：注册 → 登录 → 答题 → 错题本真的收录（用户反馈的那条）。"""
import io
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright      # noqa: E402

URL = "http://127.0.0.1:8000/app/"
# 每次跑用不同的登录名，避免与上一轮留下的账号冲突（脚本要能反复运行）
USER = "stu" + str(int(time.time()))[-8:]
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

# ---------- 6. 游客期间的记录，注册后要能并过来（界面文案承诺过） ----------
# 单独开一次浏览器：新 context 才有干净的 localStorage，否则还是登录态。
USER3 = "mg" + str(int(time.time()))[-8:]
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    ctx = b.new_context(viewport={"width": 1180, "height": 900})
    pg = ctx.new_page()
    errs3 = []
    pg.on("pageerror", lambda e: errs3.append(str(e)[:200]))

    pg.goto(URL)
    pg.wait_for_timeout(1800)
    pg.locator("#auth-guest").click()
    pg.wait_for_timeout(2500)

    # 游客答一局，故意全错，让错题本里有东西
    pg.locator(".chip").first.click()
    pg.wait_for_timeout(300)
    pg.locator("#start-ask").click()
    for _ in range(60):
        pg.wait_for_timeout(300)
        if pg.locator(".option").count() >= 3:
            break
    for _ in range(20):
        if pg.locator(".option").count() == 0:
            break
        is_last = "看看我的报告" in pg.locator("#view").inner_text()
        pg.locator(".option").last.click()
        pg.wait_for_timeout(150)
        pg.locator("#quiz-btn").click()
        pg.wait_for_timeout(350)
        if is_last:
            break
        pg.locator("#quiz-btn").click()
        pg.wait_for_timeout(350)
    for _ in range(30):
        pg.wait_for_timeout(400)
        if "正确率" in pg.locator("#view").inner_text():
            break
    pg.goto(URL + "#/wrong")
    pg.wait_for_timeout(2500)
    guest_items = pg.locator("[data-toggle]").count()
    check(guest_items >= 1, "游客答错后错题本里也有记录（%d 道）" % guest_items)

    # 顶栏那个「注册以保存记录」应该把游客带到注册页
    pg.locator("#auth-switch").click()
    pg.wait_for_timeout(1200)
    t = pg.locator("#view").inner_text()
    check("注册" in t, "游客点顶栏按钮进入注册页")
    pg.locator("#auth-user").fill(USER3)
    pg.locator("#auth-pass").fill(PWD)
    pg.locator("#auth-nick").fill("合并同学")
    pg.locator("#auth-submit").click()
    pg.wait_for_timeout(3000)
    toast = pg.locator("#toast").inner_text()
    check("并到账号里" in toast or "账号建好啦" in toast, "注册后提示数据合并：%s" % toast)

    pg.goto(URL + "#/wrong")
    pg.wait_for_timeout(2500)
    merged = pg.locator("[data-toggle]").count()
    check(merged >= 1,
          "游客期间的 %d 道错题合并到了新账号（现在 %d 道）" % (guest_items, merged))
    pg.goto(URL + "#/profile")
    pg.wait_for_timeout(2000)
    check("累计经验值" in pg.locator("#view").inner_text(), "合并后个人中心可用")

    check(not errs3, "游客 → 注册流程无 JS 报错%s" % ("" if not errs3 else "：" + " | ".join(errs3[:2])))
    b.close()

print("\n未通过：%d 项" % len(problems))
for x in problems:
    print("  - " + x)
sys.exit(1 if problems else 0)
