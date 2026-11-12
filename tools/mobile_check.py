# -*- coding: utf-8 -*-
"""手机适配实测：起临时服务 → 真 Chrome 在多种手机视口检查 → 截图 → 关服务。

为什么自己起服务：这个环境里常驻进程会被清掉，所以服务必须与检测同生共死。

检查项（每项都对应一个真实的手机问题）：
  1. 横向溢出：页面能不能左右拖动 —— 手机上最常见的排版事故；
  2. 越界元素：右边缘超出视口的元素，定位到具体选择器；
  3. 触摸目标：可点元素的宽或高是否 < 40px（手指点不准）；
  4. 文字截断：单行容器里文字被裁掉（scrollWidth > clientWidth）；
  5. 布局切换：手机宽度下底部标签栏应显示、顶栏导航应隐藏。
"""
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = r"E:\dev\kepu-quiz"
BASE = "http://127.0.0.1:8000"
SHOTS = os.path.join(ROOT, "work", "shots_mobile")

STUDENT_PAGES = [
    ("home", "#/home", "去闯关"),
    ("pk", "#/pk", "PK 对战"),
    ("ranks", "#/ranks", "成长阶梯"),
    ("wrong", "#/wrong", "错题本"),
    ("knowledge", "#/knowledge", "知识库"),
    ("profile", "#/profile", "我的"),
]
ADMIN_PAGES = [
    ("dashboard", "#/dashboard"),
    ("questions", "#/questions"),
    ("users", "#/users"),
    ("sessions", "#/sessions"),
    ("logs", "#/logs"),
]
VIEWPORTS = [(390, 844, "iPhone 12/13"), (360, 740, "Android 小屏"),
             (768, 1024, "平板"), (1440, 900, "桌面回归")]

AUDIT_JS = r"""
() => {
  const vw = window.innerWidth;
  const de = document.documentElement;
  const out = {vw, scrollW: de.scrollWidth, clientW: de.clientWidth,
               overflowing: [], tinyTaps: [], clipped: []};

  // 元素是否位于一个可横向滚动的容器内。
  // 管理端的导航条与数据表格本来就设计成「装不下就左右滑」，
  // 它们超出视口是有意为之，不该判成越界。
  function inScroller(el) {
    let n = el.parentElement;
    while (n && n !== document.body && n !== document.documentElement) {
      const st = getComputedStyle(n);
      if ((st.overflowX === 'auto' || st.overflowX === 'scroll') &&
          n.scrollWidth > n.clientWidth + 1) return true;
      n = n.parentElement;
    }
    return false;
  }

  function path(el) {
    const bits = [];
    let n = el;
    for (let i = 0; i < 4 && n && n.nodeType === 1; i++) {
      let s = n.tagName.toLowerCase();
      if (n.id) { s += '#' + n.id; bits.unshift(s); break; }
      if (n.className && typeof n.className === 'string') {
        const c = n.className.trim().split(/\s+/).slice(0, 2).join('.');
        if (c) s += '.' + c;
      }
      bits.unshift(s);
      n = n.parentElement;
    }
    return bits.join('>');
  }

  const all = document.querySelectorAll('body *');
  for (const el of all) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || cs.position === 'fixed') continue;
    if (inScroller(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    if (r.right > vw + 1.5) {
      out.overflowing.push({sel: path(el), right: Math.round(r.right), w: Math.round(r.width)});
    }
    if (el.scrollWidth > el.clientWidth + 2 && el.clientWidth > 0) {
      const ov = getComputedStyle(el).overflowX;
      if (ov === 'visible') {
        out.clipped.push({sel: path(el), need: el.scrollWidth, have: el.clientWidth,
                          txt: (el.textContent || '').trim().slice(0, 24)});
      }
    }
  }

  const clickable = document.querySelectorAll(
    'a[href], button, [role=button], .chip, .option, .grade-btn, select, input[type=submit]');
  const NATIVE = {A: 1, BUTTON: 1, SELECT: 1, INPUT: 1, TEXTAREA: 1};
  for (const el of clickable) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    // 只管真正可点的：原生控件，或带 cursor:pointer 的元素。
    // 管理端仪表盘里的「薄弱知识点」标签也用了 .chip，但它只是文字，
    // 不该按触摸目标去要求它 —— 早先没这层判断，把它误报成小目标。
    if (!NATIVE[el.tagName] && cs.cursor !== 'pointer') continue;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    const label = (el.textContent || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 16);
    // 阈值分两档：触屏 40px，鼠标 32px。
    // 之前在桌面也用 40px，把 34px 高的按钮全判成不合格——那是标准用错了。
    const need = (window.innerWidth < 700) ? 40 : 32;
    if (Math.min(r.width, r.height) < need) {
      out.tinyTaps.push({label, w: Math.round(r.width), h: Math.round(r.height), sel: path(el)});
    }
  }

  const tb = document.querySelector('.tabbar');
  const nl = document.querySelector('.navlinks');
  out.tabbarShown = tb ? getComputedStyle(tb).display !== 'none' : null;
  out.navlinksShown = nl ? getComputedStyle(nl).display !== 'none' : null;
  out.overflowing = out.overflowing.slice(0, 5);
  out.clipped = out.clipped.slice(0, 5);
  out.tinyTaps = out.tinyTaps.slice(0, 6);
  return out;
}
"""


def start_server():
    env = dict(os.environ)
    env["PYTHONPATH"] = r"E:\dev\.kepu-tools\backend-deps"
    env["PYTHONIOENCODING"] = "utf-8"
    log = open(os.path.join(ROOT, "work", "check_server.log"), "wb")
    p = subprocess.Popen(
        [r"E:\dev\Python314\python.exe", "-X", "utf8", "-m", "uvicorn",
         "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=os.path.join(ROOT, "backend"), env=env, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + "/api/v1/health", timeout=1).read()
            print("  服务已就绪（PID %d）" % p.pid)
            return p
        except Exception:
            time.sleep(0.4)
    p.terminate()
    raise RuntimeError("服务启动超时")


def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=10).read().decode())["data"]


def main():
    os.makedirs(SHOTS, exist_ok=True)
    print("=== 启动临时服务 ===")
    srv = start_server()
    try:
        guest = post("/api/v1/user/guest", {})
        print("  学生 token 就绪；管理员登录…")
        adm = post("/api/v1/admin/login", {"username": "admin", "password": "admin123"})

        from playwright.sync_api import sync_playwright
        problems = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome", headless=True)
            for w, h, tag in VIEWPORTS:
                print()
                print("=" * 66)
                print("【视口 %d×%d  %s】" % (w, h, tag))
                ctx = browser.new_context(viewport={"width": w, "height": h},
                                          device_scale_factor=2, is_mobile=(w < 700),
                                          has_touch=(w < 700))
                # 学生端：注入 token
                pg = ctx.new_page()
                pg.goto(BASE + "/app/", wait_until="load", timeout=60000)
                pg.evaluate("""([t,u]) => {
                    localStorage.setItem('kepu_token', t);
                    localStorage.setItem('kepu_user', JSON.stringify(u));
                }""", [guest["token"], guest["user"]])
                for name, hsh, label in STUDENT_PAGES:
                    pg.goto(BASE + "/app/" + hsh, wait_until="load", timeout=60000)
                    pg.wait_for_timeout(700)
                    r = pg.evaluate(AUDIT_JS)
                    tagp = "学生/%s" % name
                    bad = report(tagp, w, h, r, problems, mobile=(w < 700))
                    if w == 390:
                        pg.screenshot(path=os.path.join(SHOTS, "stu_390_%s.png" % name),
                                      full_page=False)
                    if w == 1440:
                        # 宽屏现在也应该是手机形态，留一张证据图
                        pg.screenshot(path=os.path.join(SHOTS, "stu_1440_%s.png" % name),
                                      full_page=False)
                    if bad and w == 390:
                        pg.screenshot(path=os.path.join(SHOTS, "bad_stu_%s_%d.png" % (name, w)),
                                      full_page=False)
                pg.close()

                # 管理端
                pg2 = ctx.new_page()
                pg2.goto(BASE + "/admin/", wait_until="load", timeout=60000)
                pg2.evaluate("""([t,n]) => {
                    sessionStorage.setItem('kepu_admin_token', t);
                    sessionStorage.setItem('kepu_admin_name', n);
                }""", [adm["token"], "admin"])
                # 必须重载一次：admin.js 在 DOMContentLoaded 时读 sessionStorage 决定
                # 显示登录层还是主界面；只改 hash 不会重新执行初始化，页面会一直停在登录页。
                pg2.reload(wait_until="load", timeout=60000)
                pg2.wait_for_timeout(1000)
                for name, hsh in ADMIN_PAGES:
                    pg2.goto(BASE + "/admin/" + hsh, wait_until="load", timeout=60000)
                    pg2.wait_for_timeout(900)
                    r = pg2.evaluate(AUDIT_JS)
                    report("管理/%s" % name, w, h, r, problems, mobile=(w < 700))
                    if w == 390:
                        pg2.screenshot(path=os.path.join(SHOTS, "adm_390_%s.png" % name),
                                       full_page=False)
                # 管理端登录页
                pg2.goto(BASE + "/admin/", wait_until="load", timeout=60000)
                pg2.evaluate("() => { sessionStorage.clear(); }")
                pg2.goto(BASE + "/admin/", wait_until="load", timeout=60000)
                pg2.wait_for_timeout(500)
                r = pg2.evaluate(AUDIT_JS)
                report("管理/登录页", w, h, r, problems, mobile=(w < 700))
                if w == 390:
                    pg2.screenshot(path=os.path.join(SHOTS, "adm_390_login.png"), full_page=False)
                pg2.close()
                ctx.close()
            browser.close()

        print()
        print("=" * 66)
        if problems:
            print("发现 %d 处问题：" % len(problems))
            for p in problems:
                print("  - " + p)
        else:
            print("全部通过：无横向溢出、无越界、触摸目标达标、布局切换正确")
        print()
        print("截图目录：%s" % SHOTS)
        return 0 if not problems else 1
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=8)
        except Exception:
            srv.kill()
        print()
        print("临时服务已关闭")


def report(tag, w, h, r, problems, mobile):
    bits = []
    if r["scrollW"] > r["clientW"] + 1:
        problems.append("%s @%d：页面横向溢出（内容 %d > 视口 %d）"
                        % (tag, w, r["scrollW"], r["clientW"]))
        bits.append("横向溢出 %d>%d" % (r["scrollW"], r["clientW"]))
    if r["overflowing"]:
        for o in r["overflowing"][:3]:
            problems.append("%s @%d：越界元素 %s 右边缘 %d > %d"
                            % (tag, w, o["sel"], o["right"], r["vw"]))
        bits.append("越界 %d 个" % len(r["overflowing"]))
    if r["tinyTaps"]:
        for t in r["tinyTaps"][:3]:
            problems.append("%s @%d：触摸目标过小「%s」%d×%d"
                            % (tag, w, t["label"], t["w"], t["h"]))
        bits.append("小目标 %d 个" % len(r["tinyTaps"]))
    if r["clipped"]:
        for c in r["clipped"][:2]:
            problems.append("%s @%d：文字截断 %s（需 %d，只有 %d）「%s」"
                            % (tag, w, c["sel"], c["need"], c["have"], c["txt"]))
        bits.append("截断 %d 处" % len(r["clipped"]))
    if mobile:
        if tag.startswith("学生") and r["tabbarShown"] is not True:
            problems.append("%s @%d：底部标签栏未显示" % (tag, w))
            bits.append("无标签栏")
        if tag.startswith("学生") and r["navlinksShown"] is True:
            problems.append("%s @%d：手机宽度下顶栏导航仍未隐藏" % (tag, w))
            bits.append("顶栏导航未隐藏")
    status = "OK  " if not bits else "问题"
    extra = ""
    if tag.startswith("学生"):
        extra = " 标签栏=%s 顶栏导航=%s" % ("显示" if r["tabbarShown"] else "隐藏",
                                        "显示" if r["navlinksShown"] else "隐藏")
    print("  [%s] %-14s %s%s" % (status, tag, ("；".join(bits) if bits else "通过"), extra))
    return bool(bits)


if __name__ == "__main__":
    sys.exit(main())
