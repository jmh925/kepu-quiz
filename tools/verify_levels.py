# -*- coding: utf-8 -*-
"""验收：段位阶梯（用户提的「要能看出有哪些关卡、最高能到哪一级」）。

覆盖三件事：
1. 后端段位表自洽：等级区间连续不重叠、经验阈值单调递增、恰好一个最高段位；
2. 接口 GET /levels 返回的段位表与随机经验值下的段位归属都正确
   （边界值逐个验，避免出现「刚好卡在阈值上掉档」这类问题）；
3. 真实浏览器里「成长阶梯」页能渲染出全部段位、标出「你在这里」与「最高段位」，
   并且明确告诉用户还差多少经验到顶。

另外比对 **前端兜底段位表**（web/assets/app.js 里的 util.ranks）与后端是否漂移——
两份数据不一致的话，接口挂掉时前端会显示错误的段位名。

用法：python tools/verify_levels.py
"""
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.getenv("KEPU_BASE_URL", "http://127.0.0.1:8000")
API = BASE + "/api/v1"
WEB = BASE + "/app/"

sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kepu_env                                        # noqa: E402

problems = []


def check(ok, msg):
    print(("[OK  ] " if ok else "[FAIL] ") + msg)
    if not ok:
        problems.append(msg)


def api(path, method="GET", body=None, token=None):
    h = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(API + path, data=data, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------- 1. 后端段位表自洽 ----------
print("=== 1. 段位表结构 ===")
from app import levels                                # noqa: E402

ranks = levels.RANKS
check(len(ranks) >= 5, "段位数量足够形成阶梯（%d 个）" % len(ranks))
check(ranks[-1]["max_level"] is None, "最后一个段位不封顶（就是最高段位）")
check(sum(1 for r in ranks if r["max_level"] is None) == 1, "恰好只有一个最高段位")

# 区间连续且不重叠
prev_max = 0
contiguous = True
for r in ranks:
    if r["min_level"] != prev_max + 1:
        contiguous = False
    prev_max = r["max_level"] if r["max_level"] is not None else r["min_level"]
check(contiguous, "各段位的等级区间首尾相接、没有空隙也没有重叠")

# 经验阈值单调递增
xps = [levels.xp_for_level(r["min_level"]) for r in ranks]
check(xps == sorted(xps) and len(set(xps)) == len(xps), "段位所需经验值单调递增：%s" % xps)

# 每个段位都有名字/颜色/标语（前端要直接渲染）
check(all(r.get("name") and r.get("emoji") and r.get("color") and r.get("slogan")
          for r in ranks), "每个段位都有名称、图标、颜色与标语")

# ---------- 2. 边界值：等级 → 段位归属 ----------
print("\n=== 2. 等级到段位的归属（含边界）===")
wrong = []
for r in ranks:
    lo = r["min_level"]
    if levels.rank_of_level(lo)["name"] != r["name"]:
        wrong.append("Lv.%d 应为 %s" % (lo, r["name"]))
    if r["max_level"] is not None:
        hi = r["max_level"]
        if levels.rank_of_level(hi)["name"] != r["name"]:
            wrong.append("Lv.%d 应为 %s" % (hi, r["name"]))
        # 跨过上限应当进入下一段位
        if levels.rank_of_level(hi + 1)["name"] == r["name"]:
            wrong.append("Lv.%d 之后应换段位" % hi)
check(not wrong, "每个段位的上下边界都归属正确%s" % ("" if not wrong else "：" + "；".join(wrong[:4])))

check(levels.rank_of_level(1)["index"] == 1, "Lv.1 落在最低段位")
check(levels.rank_of_level(9999)["index"] == len(ranks), "极高等级落在最高段位（不会溢出）")
check(levels.rank_of_level(0)["index"] == 1, "等级 0 之类的异常输入也安全")

# ---------- 3. 进度计算 ----------
print("\n=== 3. 成长进度计算 ===")
top_xp = levels.xp_for_level(ranks[-1]["min_level"])
cases = [
    (0, 1, ranks[0]["name"], top_xp),
    (top_xp - 1, None, None, 1),
    (top_xp, None, ranks[-1]["name"], 0),
    (top_xp + 5000, None, ranks[-1]["name"], 0),
]
ok = True
for xp, want_level, want_rank, want_left in cases:
    p = levels.progress(xp)
    if want_level is not None and p["level_progress"]["level"] != want_level:
        ok = False
    if want_rank is not None and p["rank"]["name"] != want_rank:
        ok = False
    if p["xp_to_max_rank"] != want_left:
        ok = False
check(ok, "经验值 → 等级/段位/距最高段位 的换算正确（含 0 与封顶边界）")

p0 = levels.progress(0)
check(p0["rank_progress"] is not None and p0["rank_progress"]["next_name"] == ranks[1]["name"],
      "0 经验时能给出「下一段位」")
p_top = levels.progress(top_xp)
check(p_top["is_max_rank"] and p_top["rank_progress"] is None,
      "到达最高段位后不再提示下一段位")
check(p_top["xp_to_max_rank"] == 0, "最高段位时「距最高段位」为 0")

# 进度百分比在合理范围
bad_pct = []
for xp in range(0, top_xp + 200, 37):
    pr = levels.progress(xp)
    for key in ("percent",):
        v = pr["level_progress"][key]
        if not (0 <= v <= 100):
            bad_pct.append((xp, v))
    if pr["rank_progress"] and not (0 <= pr["rank_progress"]["percent"] <= 100):
        bad_pct.append((xp, pr["rank_progress"]["percent"]))
check(not bad_pct, "各级进度百分比都在 0~100 之间%s" % ("" if not bad_pct else str(bad_pct[:3])))

# ---------- 4. 接口 ----------
print("\n=== 4. GET /levels 接口 ===")
d = api("/levels")["data"]
check(d["total_ranks"] == len(ranks), "接口返回的段位数量与后端一致（%d）" % d["total_ranks"])
check(d["max_rank_name"] == ranks[-1]["name"],
      "接口明确给出最高段位名：「%s」" % d["max_rank_name"])
check(len(d["ranks"]) == len(ranks), "接口下发完整段位表（前端不用自己维护一份）")
check(all("min_xp" in r and "is_top" in r for r in d["ranks"]),
      "每个段位都带经验阈值与「是否最高段位」标记")
check(d["me"]["total_xp"] == 0, "未登录时进度从 0 开始（但段位表照常可见）")

# 登录后应返回真实进度
uname = "lvl" + str(int(__import__("time").time()))[-8:]
reg = api("/user/register", "POST",
          {"username": uname, "password": "kepu123456", "nickname": "阶梯验证",
           "grade": "primary_high"})
token = reg["data"]["token"]
d2 = api("/levels", token=token)["data"]
check(d2["me"]["total_xp"] == 0, "新账号经验值为 0，落在最低段位")
check(d2["me"]["rank"]["index"] == 1, "新账号是最低段位（%s）" % d2["me"]["rank"]["name"])

# ---------- 5. 前端兜底段位表有没有和后端漂移 ----------
print("\n=== 5. 前端兜底数据一致性 ===")
with open(os.path.join(ROOT, "web", "assets", "app.js"), "r", encoding="utf-8") as fh:
    js = fh.read()
m = re.search(r"ranks:\s*\[(.*?)\n    \]", js, re.S)
check(bool(m), "能在 app.js 里找到兜底段位表")
if m:
    block = m.group(1)
    names = re.findall(r"name:\s*'([^']+)'", block)
    levels_found = re.findall(r"min_level:\s*(\d+)", block)
    check(names == [r["name"] for r in ranks],
          "前端兜底段位名与后端一致（前端 %d 个 / 后端 %d 个）" % (len(names), len(ranks)))
    check([int(x) for x in levels_found] == [r["min_level"] for r in ranks],
          "前端兜底等级阈值与后端一致：%s" % levels_found)

# ---------- 6. 真实浏览器 ----------
print("\n=== 6. 真实浏览器里的成长阶梯页 ===")
from playwright.sync_api import sync_playwright      # noqa: E402

shots = os.path.join(ROOT, "web", "shots")
os.makedirs(shots, exist_ok=True)
uname2 = "lvlp" + str(int(__import__("time").time()))[-7:]

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    ctx = b.new_context(viewport={"width": 1180, "height": 900})
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:200]))

    pg.goto(WEB)
    pg.wait_for_timeout(2000)
    pg.locator("#tab-register").click()
    pg.wait_for_timeout(400)
    pg.locator("#auth-user").fill(uname2)
    pg.locator("#auth-pass").fill("kepu123456")
    pg.locator("#auth-nick").fill("阶梯同学")
    pg.locator("#auth-grade").select_option("primary_high")
    pg.locator("#auth-submit").click()
    for _ in range(30):
        pg.wait_for_timeout(400)
        if "去闯关" in pg.locator("#view").inner_text():
            break

    # 顶栏应当显示「段位名 · Lv.N」
    top = pg.locator("#lv-chip").inner_text()
    check("Lv." in top and ranks[0]["name"] in top,
          "顶栏同时显示段位与等级：「%s」" % top)

    pg.goto(WEB + "#/ranks")
    pg.wait_for_timeout(2500)
    t = pg.locator("#view").inner_text()
    print("     阶梯页文字（前 200 字）：", t[:200].replace("\n", " / "))

    check(ranks[-1]["name"] in t, "阶梯页出现最高段位「%s」" % ranks[-1]["name"])
    check("最高段位" in t, "阶梯页明确标出「最高段位」")
    missing = [r["name"] for r in ranks if r["name"] not in t]
    check(not missing, "全部 %d 个段位都列了出来%s"
          % (len(ranks), "" if not missing else "，缺：" + str(missing)))
    check("你在这里" in t, "标出了「你在这里」")
    check("离下一段位" in t or "下一段位" in t, "给出了到下一段位的进度")
    check("还需要" in t or "再攒" in t, "明确告诉用户还差多少经验到最高段位")

    # 版面：段位行要真的排开，不能挤在一起
    geom = pg.evaluate("""() => {
      const rows = [...document.querySelectorAll('.rank-row')];
      return { n: rows.length,
               tops: rows.map(r => Math.round(r.getBoundingClientRect().top)),
               w: rows.length ? rows[0].getBoundingClientRect().width : 0 };
    }""")
    check(geom["n"] == len(ranks), "版面上渲染出 %d 行段位（%d 行）" % (len(ranks), geom["n"]))
    check(geom["tops"] == sorted(geom["tops"]), "段位行按从低到高自上而下排列")
    check(geom["w"] > 200, "段位行有实际宽度（%.0f px）" % geom["w"])
    pg.screenshot(path=os.path.join(shots, "16_成长阶梯.png"), full_page=True)

    # 顶栏胶囊可点，点了能跳到阶梯页
    pg.goto(WEB + "#/home")
    pg.wait_for_timeout(1500)
    pg.locator("#lv-chip").click()
    pg.wait_for_timeout(1500)
    check("#/ranks" in pg.url, "点顶栏段位胶囊能进成长阶梯（%s）" % pg.url.split("/app/")[-1])

    check(not errs, "无 JS 报错%s" % ("" if not errs else "：" + " | ".join(errs[:2])))
    b.close()

print("\n未通过：%d 项" % len(problems))
for x in problems:
    print("  - " + x)
sys.exit(1 if problems else 0)
