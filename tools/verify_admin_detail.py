# -*- coding: utf-8 -*-
"""验收：管理端「单个学生的答题信息分类」面板 + 入口页的管理员登录页签。

覆盖用户提的三件事：
  1) 入口页上能直接切到管理员登录（不用自己敲 /admin/）；
  2) 管理端用户列表能看到登录名 / 游客标记 / 答题详情按钮；
  3) 详情面板把该学生的答题信息分成四块：逐次闯关记录、薄弱知识点、错题明细、知识库资料。
"""
import io
import json
import os
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright      # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(ROOT, "web", "shots")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kepu_env                                        # noqa: E402

WEB = "http://127.0.0.1:8000/app/"
ADMIN = "http://127.0.0.1:8000/admin/"
API = "http://127.0.0.1:8000/api/v1"
# 口令从 backend/.env 取（tools/gen_secrets.py 生成过就是随机的），不要写死默认值
ADMIN_USER, ADMIN_PWD = kepu_env.admin_credentials()

USER = "stu" + str(int(time.time()))[-8:]
PWD = "kepu123456"

problems = []


def check(ok, msg):
    print(("[OK  ] " if ok else "[FAIL] ") + msg)
    if not ok:
        problems.append(msg)


def api(method, path, body=None, token=None, admin_token=None):
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
        data = json.dumps(body).encode("utf-8")
    if token:
        headers["Authorization"] = "Bearer " + token
    if admin_token:
        headers["X-Admin-Token"] = admin_token
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))["data"]


# ---------- 0. 先用接口铺一份真实数据：新学生答错几题 ----------
reg = api("POST", "/user/register",
          {"username": USER, "password": PWD, "nickname": "验收同学", "grade": "primary_high"})
token = reg["token"]
uid = reg["user"]["id"]

gen = api("POST", "/quiz/generate",
          {"topic": "天文", "count": 5, "grade": "primary_high"}, token=token)
qid = gen["quiz_id"]
questions = gen["questions"]

answers = []
for i, q in enumerate(questions):
    # 前两题故意选个错的，确保错题本一定有内容；其余选正确项
    if i < 2:
        answers.append((q["answer"] + 1) % len(q["options"]))
    else:
        answers.append(q["answer"])

api("POST", "/quiz/submit", {"quiz_id": qid, "answers": answers, "duration_ms": 42000},
    token=token)
print("     已为 %s（用户 #%d）造好 1 次闯关记录" % (USER, uid))

# ---------- 1. 管理端接口本身 ----------
adm = api("POST", "/admin/login", {"username": ADMIN_USER, "password": ADMIN_PWD})
admin_token = adm["token"]
check(bool(admin_token), "管理员接口登录拿到 token")

detail = api("GET", "/admin/users/%d" % uid, admin_token=admin_token)
check(detail.get("profile", {}).get("username") == USER,
      "详情接口返回该学生的账号：%s" % detail.get("profile", {}).get("username"))
check(len(detail.get("sessions") or []) >= 1,
      "详情接口含逐次闯关记录 %d 条" % len(detail.get("sessions") or []))
check(len(detail.get("wrong_items") or []) >= 1,
      "详情接口含错题明细 %d 条" % len(detail.get("wrong_items") or []))
check("by_grade" in (detail.get("stats") or {}), "详情接口含按学段的统计")

with sync_playwright() as p:
    os.makedirs(SHOTS, exist_ok=True)
    b = p.chromium.launch(channel="chrome")
    ctx = b.new_context(viewport={"width": 1440, "height": 950})
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:200]))

    def shot(name):
        pg.screenshot(path=os.path.join(SHOTS, name + ".png"), full_page=True)

    # ---------- 2. 入口页的管理员页签 ----------
    pg.goto(WEB)
    pg.wait_for_timeout(2000)
    shot("11_入口页_学生登录")
    check(pg.locator("#tab-admin").count() == 1, "入口页有「管理员」页签")
    pg.locator("#tab-admin").click()
    pg.wait_for_timeout(400)
    t = pg.locator("#view").inner_text()
    check("进入管理端" in t, "切到管理员页签后出现管理员登录表单")
    check(pg.locator("#auth-guest").count() == 0, "管理员页签下不显示「游客体验」")
    shot("12_入口页_管理员登录")
    # 先故意输错，确认报错而不是静默跳转
    pg.locator("#auth-user").fill(ADMIN_USER)
    pg.locator("#auth-pass").fill("wrong-password-xyz")
    pg.locator("#auth-submit").click()
    pg.wait_for_timeout(2500)
    check("/app/" in pg.url, "口令不对时留在入口页（未跳转），URL=%s" % pg.url.split("8000")[-1])
    toast = pg.locator("#toast").inner_text().strip()
    check(bool(toast), "口令不对时给出提示：%s" % toast)

    # 再用正确口令登录，应当自动跳进 /admin/
    pg.locator("#auth-user").fill(ADMIN_USER)
    pg.locator("#auth-pass").fill(ADMIN_PWD)
    pg.locator("#auth-submit").click()
    pg.wait_for_url("**/admin/**", timeout=15000)
    pg.wait_for_timeout(1500)
    check("/admin/" in pg.url, "管理员登录后自动进入 /admin/（URL=%s）" % pg.url.split("8000")[-1])
    check(pg.locator("#app").is_visible(), "管理端主界面已展开（不用再登一次）")

    # ---------- 3. 用户列表 ----------
    pg.goto(ADMIN + "#/users")
    pg.wait_for_timeout(2500)
    if not pg.locator("#app").is_visible():
        # 万一 sessionStorage 没带上，补一次登录
        pg.locator("#username").fill(ADMIN_USER)
        pg.locator("#password").fill(ADMIN_PWD)
        pg.locator("#login-form button[type=submit]").click()
        pg.wait_for_timeout(2500)
    pg.locator("#u-keyword").fill(USER)
    pg.locator("#view-users button:has-text('搜索')").click()
    pg.wait_for_timeout(2000)
    rows = pg.locator("#u-table tr").count()
    check(rows >= 2, "按登录名 %s 能搜到该学生（表格 %d 行）" % (USER, rows))
    head = pg.locator("#u-table").inner_text()
    check(USER in head, "用户列表里显示登录名（不是只显示昵称）")

    # ---------- 4. 答题详情面板 ----------
    pg.locator("#u-table button:has-text('答题详情')").first.click()
    pg.wait_for_timeout(2500)
    check(pg.locator("#user-modal").is_visible(), "「答题详情」按钮打开了详情面板")
    shot("13_管理端_学生答题详情")
    d = pg.locator("#user-detail").inner_text()
    print("     面板文字（前 160 字）：", d[:160].replace("\n", " / "))

    for sec in ["一、逐次闯关记录", "二、薄弱知识点排行", "三、错题明细", "四、知识库资料"]:
        check(sec in d, "详情面板含分块：%s" % sec)
    check("经验值" in d and "平均正确率" in d, "详情面板顶部有经验值 / 平均正确率概览")
    check("验收同学" in d, "详情面板标题是该学生的昵称")
    check(USER in d, "详情面板标题带登录名")
    check("题库出题" in d or "AI 出题" in d or "错题重练" in d, "闯关记录标出了出题来源")
    check("小学高年级" in d, "闯关记录标出了学段")

    # 错题明细那一段要真的有题，不是「还没有错题」
    sec3 = d.split("三、错题明细")[-1].split("四、知识库资料")[0]
    check("还没有错题" not in sec3, "错题明细里有真实错题（学生刚答错 2 题）")
    check(len(sec3.strip()) > 20, "错题明细区块有内容")

    # 光看文字还不够：面板要真的是「宽弹窗 + 四块上下排开」，不能挤成一团或溢出
    box = pg.locator("#user-modal .modal-card").bounding_box()
    check(box and box["width"] >= 700, "详情面板是宽弹窗（宽 %.0f px）" % (box["width"] if box else 0))
    geom = pg.evaluate("""() => {
      const vw = window.innerWidth;
      const cards = [...document.querySelectorAll('#user-detail .detail-cards .card')];
      const panels = [...document.querySelectorAll('#user-detail .panel')];
      return {
        cardCount: cards.length,
        cardW: cards.length ? cards[0].getBoundingClientRect().width : 0,
        panelCount: panels.length,
        tops: panels.map(p => Math.round(p.getBoundingClientRect().top)),
        overflow: document.querySelector('#user-modal .modal-card').scrollWidth > vw,
      };
    }""")
    check(geom["cardCount"] == 4, "顶部四张概览卡都渲染出来了（%d 张）" % geom["cardCount"])
    check(geom["cardW"] > 100, "概览卡有实际宽度（%.0f px）" % geom["cardW"])
    check(geom["panelCount"] == 4, "四个分块面板都渲染出来了（%d 块）" % geom["panelCount"])
    check(geom["tops"] == sorted(geom["tops"]), "四个分块按顺序自上而下排列（top=%s）" % geom["tops"])
    check(not geom["overflow"], "弹窗没有横向溢出")

    pg.locator("#user-modal button:has-text('关闭')").click()
    pg.wait_for_timeout(500)
    check(pg.locator("#user-modal").is_hidden(), "详情面板可以关闭")

    check(not errs, "无 JS 报错%s" % ("" if not errs else "：" + " | ".join(errs[:2])))
    b.close()

print("\n未通过：%d 项" % len(problems))
for x in problems:
    print("  - " + x)
sys.exit(1 if problems else 0)
