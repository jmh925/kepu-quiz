# -*- coding: utf-8 -*-
"""验收：语文 / 数学 / 英语三大基础课程（用户提的「把基础课程题目也加上」）。

重点不是"文件里有 75 道题"，而是**孩子真的能在界面上选到、抽到、答到**：
1. 主题清单把三科分在「基础课程」组里下发；
2. 用「数学」这个主题出题，拿到的**必须全是数学题**，不能混进科普题；
3. 三个学段各自抽题，题目必须都属于该学段（不能给低年级出初中的题）；
4. PK 也能选基础课程，且卷子确定性生成（同主题同题量永远是同一份）；
5. 真实浏览器里首页能看到「基础课程」分组、点「数学」能出数学题。

用法：python tools/verify_basic_courses.py
"""
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.getenv("KEPU_BASE_URL", "http://127.0.0.1:8000")
API = BASE + "/api/v1"
WEB = BASE + "/app/"

BASIC = ["语文", "数学", "英语"]
GRADES = ["primary_low", "primary_high", "junior"]

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
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"code": -1, "message": "HTTP %s" % e.code}


print("=== 1. 主题清单：三科要分在「基础课程」组 ===")
t = api("/themes")
check(t.get("code") == 0, "主题清单接口可用")
groups = t["data"]
check(set(BASIC).issubset(set(groups["basic"])),
      "「基础课程」组包含语文/数学/英语（实际 %s）" % groups["basic"])
check(not (set(BASIC) & set(groups["science"])),
      "三科没有被误放进「科普主题」组")
check(len(groups["science"]) >= 6, "科普主题组仍然完整（%d 个）" % len(groups["science"]))

print("\n=== 2. 直接查题库：三科各自的题量与学段分布 ===")
sys.path.insert(0, os.path.join(ROOT, "backend"))
from app import question_bank as qb                       # noqa: E402

loaded = qb._load()
for theme in BASIC:
    items = loaded.get(theme, [])
    by_grade = {}
    for q in items:
        by_grade[q["grade"]] = by_grade.get(q["grade"], 0) + 1
    check(len(items) >= 20, "%s 有足够题目（%d 题）" % (theme, len(items)))
    check(all(by_grade.get(g, 0) >= 6 for g in GRADES),
          "%s 三个学段都有至少 6 题（%s）" % (theme, by_grade))
    # 题干、选项、解析、答案都要齐
    bad = [q for q in items if not q.get("stem") or len(q.get("options") or []) != 4
           or not isinstance(q.get("answer"), int) or not 0 <= q["answer"] < 4
           or not q.get("analysis")]
    check(not bad, "%s 的题目字段完整、答案下标合法%s"
          % (theme, "" if not bad else "（%d 处有问题）" % len(bad)))

all_yes = sum(1 for q in qb.all_questions())
check(all_yes >= 220, "题库总量扩容到位（共 %d 题）" % all_yes)

print("\n=== 3. 按主题出题：不能串主题 ===")
uname = "bas" + str(int(time.time()))[-8:]
reg = api("/user/register", "POST",
          {"username": uname, "password": "kepu123456", "nickname": "基础课验证",
           "grade": "primary_high"})
token = reg["data"]["token"]

stem_by_theme = {}
for q in qb.all_questions():
    stem_by_theme[q["stem"]] = q["theme"]

for theme in BASIC:
    r = api("/quiz/generate", "POST",
            {"topic": theme, "count": 8, "grade": "primary_high"}, token=token)
    check(r.get("code") == 0, "以「%s」为主题能出题（code=%s）" % (theme, r.get("code")))
    if r.get("code") != 0:
        continue
    qs = r["data"]["questions"]
    check(len(qs) >= 5, "「%s」出到 %d 道题" % (theme, len(qs)))
    wrong = [q["stem"][:18] for q in qs if stem_by_theme.get(q["stem"]) != theme]
    check(not wrong, "「%s」出的题全部属于该科目%s"
          % (theme, "" if not wrong else "，混入了：" + str(wrong[:3])))
    check(all(q.get("analysis") for q in qs), "「%s」每题都带解析" % theme)

print("\n=== 4. 学段适配：每个学段抽到的题都属于该学段 ===")
grade_of_stem = {q["stem"]: q["grade"] for q in qb.all_questions()}
for theme in BASIC:
    for g in GRADES:
        r = api("/quiz/generate", "POST", {"topic": theme, "count": 6, "grade": g}, token=token)
        if r.get("code") != 0:
            check(False, "「%s」在 %s 出题失败：%s" % (theme, g, r.get("message")))
            continue
        qs = r["data"]["questions"]
        leaked = [q["stem"][:18] for q in qs if grade_of_stem.get(q["stem"]) != g]
        check(not leaked, "「%s」在 %s 出到 %d 题且没有跨学段%s"
              % (theme, g, len(qs), "" if not leaked else "：" + str(leaked[:2])))

print("\n=== 5. 关键词也能命中三科（不是只能点胶囊）===")
for text, want in [("数学", "数学"), ("拼音和汉字", "语文"), ("英语单词", "英语"),
                   ("解方程", "数学"), ("古诗", "语文"), ("时态", "英语")]:
    got = qb.match_theme(text)
    check(got == want, "输入「%s」→ 命中 %s（实际 %s）" % (text, want, got))

print("\n=== 6. PK 也能用基础课程，且卷子是确定性的 ===")
m1 = api("/pk/start", "POST", {"grade": "primary_high", "theme": "数学"}, token=token)
check(m1.get("code") == 0, "PK 能选「数学」开局（code=%s）" % m1.get("code"))
if m1.get("code") == 0:
    md = m1["data"]
    stems = [q["stem"] for q in md["questions"]]
    check(all(stem_by_theme.get(s) == "数学" for s in stems),
          "PK 的数学卷里全是数学题")
    # 同一主题再开一局，题目应当完全一样（确定性卷子）
    m2 = api("/pk/start", "POST", {"grade": "primary_high", "theme": "数学"}, token=token)
    stems2 = [q["stem"] for q in m2["data"]["questions"]]
    check(stems == stems2, "同主题再开一局拿到同一份卷（异步对战可比的前提）")

print("\n=== 7. 真实浏览器：首页能看到基础课程分组并出数学题 ===")
from playwright.sync_api import sync_playwright          # noqa: E402

shots = os.path.join(ROOT, "web", "shots")
os.makedirs(shots, exist_ok=True)
uname2 = "basweb" + str(int(time.time()))[-7:]

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    ctx = b.new_context(viewport={"width": 1180, "height": 950})
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:200]))

    pg.goto(WEB)
    pg.wait_for_timeout(2000)
    pg.locator("#tab-register").click()
    pg.wait_for_timeout(400)
    pg.locator("#auth-user").fill(uname2)
    pg.locator("#auth-pass").fill("kepu123456")
    pg.locator("#auth-nick").fill("基础课同学")
    pg.locator("#auth-grade").select_option("primary_high")
    pg.locator("#auth-submit").click()
    for _ in range(30):
        pg.wait_for_timeout(400)
        if "去闯关" in pg.locator("#view").inner_text():
            break

    home = pg.locator("#view").inner_text()
    check("基础课程" in home, "首页出现「基础课程」分组标题")
    check("科普主题" in home, "首页仍然保留「科普主题」分组")
    for theme in BASIC:
        check(pg.locator('[data-topic="%s"]' % theme).count() >= 1
              or theme in home, "首页有「%s」入口" % theme)
    groups_n = pg.locator(".chip-group").count()
    check(groups_n >= 2, "胶囊按 %d 个分组渲染" % groups_n)
    pg.screenshot(path=os.path.join(shots, "20_首页_基础课程分组.png"), full_page=True)

    # 点「数学」胶囊 -> 开始出题 -> 必须是数学题
    pg.locator('[data-topic="数学"]').first.click()
    pg.wait_for_timeout(400)
    check(pg.locator("#topic").input_value() == "数学", "点数学胶囊会填入主题")
    pg.locator("#start-ask").click()
    got = False
    for _ in range(60):
        pg.wait_for_timeout(400)
        if pg.locator(".option").count() >= 3:
            got = True
            break
    check(got, "点数学后能出题（选项已渲染）")
    # 闯关页把题干渲染在 .h2 里（PK 页才用 .stem），这里两个都试一下更稳
    stem = ""
    for sel in ("#view .h2", "#view .stem", ".stem"):
        loc = pg.locator(sel)
        if loc.count():
            stem = loc.first.inner_text().strip()
            if stem:
                break
    check(stem_by_theme.get(stem) == "数学",
          "界面上这道题确实是数学题：「%s」" % stem[:30])
    pg.screenshot(path=os.path.join(shots, "21_数学题.png"), full_page=True)

    check(not errs, "无 JS 报错%s" % ("" if not errs else "：" + " | ".join(errs[:2])))
    b.close()

print("\n未通过：%d 项" % len(problems))
for x in problems:
    print("  - " + x)
sys.exit(1 if problems else 0)
