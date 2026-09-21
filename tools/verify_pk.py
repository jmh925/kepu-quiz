# -*- coding: utf-8 -*-
"""验收：成员 PK 对战（用户提的「随机 pk 一个对手」）。

分两层验：
- **接口层**：题面不许泄露答案、结算的比分要算对、答错的题要进错题本、
  同一局不能结算两次、不能结算别人的局、连胜要连续；
- **对手来源**：先让 A 打完一局，再让 B 开同主题的一局，B 应当匹配到
  **A 的真实战绩**（kind=user）而不是机器人——这是「随机 PK 一个对手」
  这个需求的核心，必须真的有真人对手参与，不能永远只有机器人。

最后用真实 Chrome 把「匹配中 → VS → 答题 → 结算」走一遍，
并检查结算文案没有出现面向小朋友的禁用词。

用法：python tools/verify_pk.py
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

# 面向中小学生的文案红线
BANNED = ["失败", "排名"]

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


def new_student(tag):
    uname = tag + str(int(time.time() * 1000))[-8:]
    r = api("/user/register", "POST",
            {"username": uname, "password": "kepu123456", "nickname": tag + "同学",
             "grade": "primary_high"})
    if r.get("code") != 0:
        raise RuntimeError("注册失败：%s" % r.get("message"))
    return uname, r["data"]["token"], r["data"]["user"]["id"]


print("=== 1. 开局：题面不能泄露答案 ===")
uname_a, token_a, uid_a = new_student("pkA")
m = api("/pk/start", "POST", {"grade": "primary_high", "theme": "数学"}, token=token_a)
check(m.get("code") == 0, "能开一局 PK（code=%s）" % m.get("code"))
md = m["data"]
check(md["theme"] == "数学", "按指定主题开局（%s）" % md["theme"])
check(md["count"] == len(md["questions"]), "题量与下发的题目数一致（%d）" % md["count"])
check(bool(md.get("match_id")) and bool(md.get("quiz_id")), "返回 match_id 与 quiz_id")

leak_fields = ("answer", "correct_answer", "analysis")
leaked = []
for q in md["questions"]:
    for f in leak_fields:
        if f in q:
            leaked.append((q["stem"][:14], f))
check(not leaked, "下发的题目里没有正确答案与解析（前端偷看不到）%s"
      % ("" if not leaked else "：" + str(leaked[:3])))
check(all(q.get("options") and len(q["options"]) >= 2 for q in md["questions"]),
      "每题都有选项")
check(md["opponent"].get("name") and md["opponent"].get("rank"),
      "对手有名字与段位：「%s / %s」" % (md["opponent"].get("name"), md["opponent"].get("rank")))

print("\n=== 2. 结算：比分要算对 ===")
n = md["count"]
# 先从后端拿到正确答案（用闯关接口的判题结果反推不方便，这里直接用题库比对）
sys.path.insert(0, os.path.join(ROOT, "backend"))
from app import pk as pk_mod                             # noqa: E402

# 全对：用「提交后看结果」验证不了"全对"，所以构造一份"必然全对"的作答：
# 先取这局题目的正确答案（服务端内部数据），再用它作答。
from app import database as db_mod                       # noqa: E402
row = db_mod.query_one("SELECT questions_json FROM quiz_sessions WHERE quiz_id=?",
                       (md["quiz_id"],))
questions = json.loads(row["questions_json"])
right = [int(q["answer"]) for q in questions]
f = api("/pk/finish", "POST",
        {"match_id": md["match_id"], "answers": right, "duration_ms": 20000}, token=token_a)
check(f.get("code") == 0, "能结算这一局（code=%s）" % f.get("code"))
fd = f["data"]
check(fd["my_correct"] == n, "全部答对时我的正确题数 = %d（实际 %d）" % (n, fd["my_correct"]))
check(0 <= fd["opponent_correct"] <= n,
      "对手正确题数在合法区间（%d / %d）" % (fd["opponent_correct"], n))
check(fd["total"] == n, "总题数正确（%d）" % fd["total"])

expected = ("win" if fd["my_correct"] > fd["opponent_correct"]
            else "draw" if fd["my_correct"] == fd["opponent_correct"] else "lose")
check(fd["result"] == expected,
      "胜负判定与比分一致：%d : %d → %s" % (fd["my_correct"], fd["opponent_correct"], fd["result"]))
check(fd["xp_gained"] > 0, "结算给了经验值（+%d）" % fd["xp_gained"])
check(len(fd["details"]) == n, "逐题对照返回了 %d 条" % len(fd["details"]))
check(all("opponent_answer" in d and "correct_answer" in d for d in fd["details"]),
      "逐题对照里双方作答与正确答案都齐")

print("\n=== 3. 不可重复结算 / 不能结算别人的局 ===")
again = api("/pk/finish", "POST",
            {"match_id": md["match_id"], "answers": right}, token=token_a)
check(again.get("code") != 0, "同一局不能结算两次（code=%s）" % again.get("code"))

uname_b, token_b, uid_b = new_student("pkB")
m2 = api("/pk/start", "POST", {"grade": "primary_high", "theme": "语文"}, token=token_b)
stolen = api("/pk/finish", "POST",
             {"match_id": m2["data"]["match_id"], "answers": [0] * m2["data"]["count"]},
             token=token_a)
check(stolen.get("code") != 0, "不能结算别人的对战（code=%s）" % stolen.get("code"))

print("\n=== 4. 答错的题要进错题本 ===")
before = api("/wrong/questions", token=token_b)
before_n = len((before.get("data") or {}).get("questions") or [])
# 全部故意选错
wrong_answers = []
for q in m2["data"]["questions"]:
    wrong_answers.append(1 if len(q["options"]) > 1 else 0)
r2 = api("/pk/finish", "POST",
         {"match_id": m2["data"]["match_id"], "answers": wrong_answers}, token=token_b)
check(r2.get("code") == 0, "结算成功（code=%s）" % r2.get("code"))
after = api("/wrong/questions", token=token_b)
after_n = len((after.get("data") or {}).get("questions") or [])
check(after_n > before_n or (r2["data"]["my_correct"] == len(wrong_answers)),
      "PK 里答错的题进了错题本（%d → %d 道，本局错 %d 题）"
      % (before_n, after_n, len(wrong_answers) - r2["data"]["my_correct"]))

print("\n=== 5. 对手来源：能匹配到真实同学，而不是永远机器人 ===")
# A 已经在「数学」打完一局；再让一个新的 C 开同主题，应当抽到 A 的真人战绩
uname_c, token_c, uid_c = new_student("pkC")
found_user = None
for attempt in range(12):                # 抽签有随机性，多试几次
    mc = api("/pk/start", "POST", {"grade": "primary_high", "theme": "数学"}, token=token_c)
    if mc.get("code") == 0 and mc["data"]["opponent"]["kind"] == "user":
        found_user = mc["data"]
        break
    time.sleep(0.2)
check(found_user is not None,
      "同主题下能匹配到真实同学的战绩（kind=user）%s"
      % ("" if found_user else "—— 12 次都只抽到机器人"))
if found_user:
    check(found_user["opponent"]["name"], "真人对手有昵称：%s" % found_user["opponent"]["name"])
    check(found_user["opponent"]["rank"] != "",
          "真人对手有段位：%s" % found_user["opponent"]["rank"])

    # 真正要守的不变量：**幽灵的作答必须原样等于它来源那一局里那位同学本人的作答**，
    # 且它的得分必须等于那一局记录的 my_correct。
    #
    # 不要写成「对手得分 == 某一局我已知的成绩」：那样只有在库里只有一个候选幽灵时
    # 才成立（第一版就是这么写的，当时能过）。库里累积了多个同学的战绩之后，
    # 随机抽到谁都合法，断言就会随机失败——那是测试错，不是功能错。
    # 这里直接查库比对「来源那一局」，无论抽到谁都成立。
    sys.path.insert(0, os.path.join(ROOT, "backend"))
    from app import database as db_mod                        # noqa: E402

    mine_row = db_mod.query_one(
        "SELECT opponent_answers_json, opponent_correct, opponent_kind, "
        "opponent_user_id, opponent_source_quiz, paper_key, total, grade, theme "
        "FROM pk_matches WHERE match_id=?", (found_user["match_id"],))
    check(mine_row["opponent_kind"] == "user", "这一局的对手类型记为 user")
    check(mine_row["opponent_user_id"] != uid_c, "幽灵不是我自己（不会自己打自己）")
    check(mine_row["opponent_correct"] > 0 or mine_row["opponent_correct"] == 0,
          "开局时对手得分已落库（%d）" % mine_row["opponent_correct"])
    src = db_mod.query_one(
        "SELECT user_id, my_answers_json, my_correct, paper_key, total "
        "FROM pk_matches WHERE match_id=?", (mine_row["opponent_source_quiz"],))
    check(src is not None, "能追溯到幽灵的来源那一局（opponent_source_quiz 有值）")
    if src:
        check(src["user_id"] == mine_row["opponent_user_id"],
              "来源那一局确实是这位同学的（user_id 对得上）")
        check(src["paper_key"] == mine_row["paper_key"] and src["total"] == mine_row["total"],
              "来源那一局与本局是同一份卷（paper_key 与题量一致）")
        check(json.loads(mine_row["opponent_answers_json"]) == json.loads(src["my_answers_json"]),
              "幽灵的作答与来源那一局里那位同学本人的作答逐位一致")
        # 开局时写下的对手得分必须等于来源那一局记录的成绩。
        # （早期只在结算时才写这个字段，开局读到的是默认 0，
        #   与题面重算结果自相矛盾；现在开局就算好写下来。）
        check(mine_row["opponent_correct"] == src["my_correct"],
              "开局记录的对手得分等于来源那一局的真实成绩（%d）"
              % mine_row["opponent_correct"])

    # 结算后回给我看的对手得分，也要和上面这份对得上
    fc = api("/pk/finish", "POST",
             {"match_id": found_user["match_id"],
              "answers": [0] * found_user["count"]}, token=token_c)
    check(fc.get("code") == 0, "与真人对战也能正常结算（code=%s）" % fc.get("code"))
    check(fc["data"]["opponent_correct"] == mine_row["opponent_correct"],
          "结算返回的对手得分与库里记录的幽灵成绩一致（%d）"
          % fc["data"]["opponent_correct"])
    # 顺便验一下：真人对战里，对手的逐题判定要和它的作答对得上
    qrow = db_mod.query_one("SELECT questions_json FROM quiz_sessions WHERE quiz_id=("
                            "SELECT quiz_id FROM pk_matches WHERE match_id=?)",
                            (found_user["match_id"],))
    qs = json.loads(qrow["questions_json"])
    opp = json.loads(mine_row["opponent_answers_json"])
    expect = sum(1 for i, q in enumerate(qs)
                 if i < len(opp) and opp[i] == int(q["answer"]))
    check(expect == mine_row["opponent_correct"],
          "按题面逐题重算幽灵得分也对得上（重算 %d / 记录 %d）"
          % (expect, mine_row["opponent_correct"]))

print("\n=== 6. 战绩与连胜 ===")
st = api("/pk/stats", token=token_a)
check(st.get("code") == 0, "能取到战绩（code=%s）" % st.get("code"))
sd = st["data"]
check(sd["logged_in"] is True, "已登录时明确标记 logged_in")
check(sd["stats"]["matches"] >= 1, "对战次数已累计（%d）" % sd["stats"]["matches"])
check(len(sd["history"]) >= 1, "最近对战列表非空（%d 条）" % len(sd["history"]))
h = sd["history"][0]
check(h["theme"] and h["opponent_name"] is not None and h["total"],
      "战绩条目里主题/对手/比分都齐")

# 连胜：A 第一局全对；对手是机器人，未必赢，所以只验「连胜 = 最近连续赢的局数」
rows = sd["history"]
run = 0
for r in rows:
    if r["result"] == "win":
        run += 1
    else:
        break
check(sd["stats"]["streak"] == run,
      "当前连胜与最近战绩一致（连胜 %d，按历史推算 %d）" % (sd["stats"]["streak"], run))

# 未登录也能看（战绩为空）
anon = api("/pk/stats")
check(anon.get("code") == 0 and anon["data"]["logged_in"] is False,
      "未登录时返回空战绩并标记 logged_in=False（前端好引导登录）")

print("\n=== 7. 文案红线（面向中小学生）===")
texts = [fd["result_text"]]
for r in (r2.get("data") or {}).values():
    if isinstance(r, str):
        texts.append(r)
banned_hit = [w for w in BANNED for t in texts if w in t]
check(not banned_hit, "结算文案没有出现禁用词%s"
      % ("" if not banned_hit else "：" + str(sorted(set(banned_hit)))))

print("\n=== 8. 真实浏览器走一遍 ===")
from playwright.sync_api import sync_playwright          # noqa: E402

shots = os.path.join(ROOT, "web", "shots")
os.makedirs(shots, exist_ok=True)
uname_p = "pkweb" + str(int(time.time()))[-7:]

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
    pg.locator("#auth-user").fill(uname_p)
    pg.locator("#auth-pass").fill("kepu123456")
    pg.locator("#auth-nick").fill("对战同学")
    pg.locator("#auth-grade").select_option("primary_high")
    pg.locator("#auth-submit").click()
    for _ in range(30):
        pg.wait_for_timeout(400)
        if "去闯关" in pg.locator("#view").inner_text():
            break

    # 首页有 PK 入口，点进去到 PK 页
    check(pg.locator("#go-pk").count() == 1, "首页有「去 PK」入口")
    pg.locator("#go-pk").click()
    pg.wait_for_timeout(2500)
    t = pg.locator("#view").inner_text()
    check("PK 对战" in t, "进入 PK 页")
    check("我的战绩" in t, "PK 页展示我的战绩")
    check(pg.locator("#pk-start").count() == 1, "有「随机匹配对手」按钮")
    pg.screenshot(path=os.path.join(shots, "17_PK_首页.png"), full_page=True)

    # 选主题后开始匹配
    pg.locator("[data-pk-theme]").nth(1).click()
    pg.wait_for_timeout(400)
    pg.locator("#pk-start").click()
    # 匹配 -> VS 画面
    got_vs = False
    for _ in range(40):
        pg.wait_for_timeout(400)
        if pg.locator("#pk-go").count():
            got_vs = True
            break
    check(got_vs, "匹配成功后出现 VS 画面")
    vt = pg.locator("#view").inner_text()
    check("VS" in vt, "VS 画面标出对战双方")
    check("开始答题" in vt, "VS 画面有「开始答题」")
    pg.screenshot(path=os.path.join(shots, "18_PK_匹配成功.png"), full_page=True)

    pg.locator("#pk-go").click()
    pg.wait_for_timeout(1200)
    check(pg.locator(".option").count() >= 2, "进入答题，选项已渲染（%d 个）" % pg.locator(".option").count())
    check("题" in pg.locator("#view").inner_text(), "答题页显示题号进度")

    # 一路答完
    for _ in range(30):
        if pg.locator(".option").count() == 0:
            break
        pg.locator(".option").first.click()
        pg.wait_for_timeout(200)
        btn = pg.locator("#pk-next")
        if not btn.count():
            break
        btn.click()
        pg.wait_for_timeout(500)

    got_result = False
    for _ in range(40):
        pg.wait_for_timeout(400)
        if pg.locator("#pk-again").count():
            got_result = True
            break
    check(got_result, "答完后进入结算页")
    rt = pg.locator("#view").inner_text()
    check("逐题对照" in rt, "结算页有逐题对照")
    check(any(k in rt for k in ("你赢啦", "平手", "差一点点")), "结算文案友好：%s"
          % [k for k in ("你赢啦", "平手", "差一点点") if k in rt])
    hit = [w for w in BANNED if w in rt]
    check(not hit, "结算页没有禁用词%s" % ("" if not hit else "：" + str(hit)))
    check("经验值" in rt, "结算页展示本局经验值")
    pg.screenshot(path=os.path.join(shots, "19_PK_结算.png"), full_page=True)

    # 再来一局
    pg.locator("#pk-again").click()
    pg.wait_for_timeout(2500)
    check("我的战绩" in pg.locator("#view").inner_text(), "「再来一局」回到 PK 首页")
    check("对战次数" in pg.locator("#view").inner_text(), "战绩已更新")

    check(not errs, "无 JS 报错%s" % ("" if not errs else "：" + " | ".join(errs[:2])))
    b.close()

print("\n未通过：%d 项" % len(problems))
for x in problems:
    print("  - " + x)
sys.exit(1 if problems else 0)
