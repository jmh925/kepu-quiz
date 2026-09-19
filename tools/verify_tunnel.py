# -*- coding: utf-8 -*-
"""验收：这个系统从**外网**能不能真的用起来（临时隧道 / 已部署域名都适用）。

与 tools/verify_web.py 的区别：
    verify_web.py 打的是 127.0.0.1，验的是「功能对不对」；
    本脚本打的是公网地址，验的是「别人在别的网络上打开，能不能真的走完流程」——
    包含 https、静态资源 MIME、同源接口调用、注册与答题、管理端登录。

用法：
    python tools/verify_tunnel.py https://xxxx.trycloudflare.com
    python tools/verify_tunnel.py https://your-domain.com --quick   # 只查静态与接口
"""
import argparse
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kepu_env                                        # noqa: E402

problems = []


def check(ok, msg):
    print(("[OK  ] " if ok else "[FAIL] ") + msg)
    if not ok:
        problems.append(msg)


def fetch(base, path, method="GET", body=None, headers=None):
    h = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, headers=h, method=method)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read(), (time.time() - t0) * 1000
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read(), (time.time() - t0) * 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base", help="公网地址，例如 https://xxxx.trycloudflare.com")
    ap.add_argument("--quick", action="store_true", help="只查静态资源与接口，不开浏览器")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    print("被测地址：%s\n" % base)
    print("--- 1. https 与静态资源（浏览器对 MIME 很严格，这里必须逐项过） ---")
    for path, want in (("/api/v1/health", "application/json"),
                       ("/app/", "text/html"),
                       ("/admin/", "text/html"),
                       ("/app/assets/app.css", "text/css"),
                       ("/app/assets/app.js", "text/javascript"),
                       ("/app/assets/main.js", "text/javascript"),
                       ("/admin/assets/admin.css", "text/css"),
                       ("/admin/assets/admin.js", "text/javascript")):
        try:
            st, ct, raw, ms = fetch(base, path)
        except Exception as exc:
            check(False, "%s 取不到：%s" % (path, exc))
            continue
        check(st == 200 and ct.startswith(want),
              "%s -> %s %s（%d bytes, %.0f ms）" % (path, st, ct.split(";")[0], len(raw), ms))

    print("\n--- 2. 外部接口调用 ---")
    st, ct, raw, ms = fetch(base, "/api/v1/grades")
    try:
        code = json.loads(raw.decode("utf-8")).get("code")
    except Exception:
        code = None
    check(st == 200 and code == 0, "/api/v1/grades 可访问（%.0f ms）" % ms)

    uname = "net" + str(int(time.time()))[-8:]
    st, ct, raw, ms = fetch(base, "/api/v1/user/register", "POST",
                            {"username": uname, "password": "kepu123456",
                             "nickname": "外网同学", "grade": "primary_high"})
    body = json.loads(raw.decode("utf-8")) if raw else {}
    check(st == 200 and body.get("code") == 0,
          "外网注册学生账号成功（%s，%.0f ms）" % (uname, ms))
    token = (body.get("data") or {}).get("token")

    if token:
        st, ct, raw, ms = fetch(base, "/api/v1/quiz/generate", "POST",
                                {"topic": "天文", "count": 5, "grade": "primary_high"},
                                {"Authorization": "Bearer " + token})
        gen = json.loads(raw.decode("utf-8"))
        check(gen.get("code") == 0, "外网出题成功（%.0f ms，%d 题）"
              % (ms, len((gen.get("data") or {}).get("questions") or [])))

    admin_user, admin_pwd = kepu_env.admin_credentials()
    st, ct, raw, ms = fetch(base, "/api/v1/admin/login", "POST",
                            {"username": admin_user, "password": admin_pwd})
    check(st == 200 and json.loads(raw.decode("utf-8")).get("code") == 0,
          "外网管理端登录成功（%.0f ms）" % ms)
    st, ct, raw, ms = fetch(base, "/api/v1/admin/login", "POST",
                            {"username": admin_user, "password": "kepu@2026"})
    check(st == 401, "外网用旧默认口令登不进去（HTTP %s）—— 口令轮换生效" % st)

    if args.quick:
        print("\n未通过：%d 项" % len(problems))
        for x in problems:
            print("  - " + x)
        return 1 if problems else 0

    print("\n--- 3. 真实浏览器走一遍（别人打开就是这个样子） ---")
    from playwright.sync_api import sync_playwright      # noqa: E402

    shots = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "web", "shots")
    os.makedirs(shots, exist_ok=True)
    web_user = "pub" + str(int(time.time()))[-8:]

    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        ctx = b.new_context(viewport={"width": 1180, "height": 900})
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:200]))

        pg.goto(base + "/app/", timeout=90000)
        pg.wait_for_timeout(3000)
        radius = pg.evaluate(
            "getComputedStyle(document.querySelector('.card') || document.body).borderRadius")
        check(radius not in ("0px", ""), "样式表在外网也生效（卡片圆角 = %s）" % radius)
        entry = pg.locator("#view").inner_text()
        check("学生注册" in entry and "管理员" in entry, "入口页三个页签都在")
        pg.screenshot(path=os.path.join(shots, "14_外网_入口页.png"), full_page=True)

        pg.locator("#tab-register").click()
        pg.wait_for_timeout(500)
        pg.locator("#auth-user").fill(web_user)
        pg.locator("#auth-pass").fill("kepu123456")
        pg.locator("#auth-nick").fill("外网同学")
        pg.locator("#auth-grade").select_option("primary_low")
        pg.locator("#auth-submit").click()
        entered = False
        for _ in range(40):
            pg.wait_for_timeout(500)
            if "去闯关" in pg.locator("#view").inner_text():
                entered = True
                break
        check(entered, "外网注册后能进首页（账号 %s）" % web_user)

        pg.locator(".chip").first.click()
        pg.wait_for_timeout(500)
        pg.locator("#start-ask").click()
        got = False
        for _ in range(80):
            pg.wait_for_timeout(500)
            if pg.locator(".option").count() >= 3:
                got = True
                break
        check(got, "外网出题能拿到选项（%d 个）" % pg.locator(".option").count())
        pg.screenshot(path=os.path.join(shots, "15_外网_答题页.png"), full_page=True)

        if got:
            pg.locator(".option").last.click()
            pg.wait_for_timeout(400)
            pg.locator("#quiz-btn").click()
            pg.wait_for_timeout(1200)
            t = pg.locator("#view").inner_text()
            check(any(k in t for k in ("解析", "知识点", "答对啦", "差一点点")),
                  "外网判题后有即时讲解")

        check(not errs, "外网无 JS 报错%s" % ("" if not errs else "：" + " | ".join(errs[:2])))
        b.close()

    print("\n未通过：%d 项" % len(problems))
    for x in problems:
        print("  - " + x)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
