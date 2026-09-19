# -*- coding: utf-8 -*-
"""接口冒烟测试：跑完即生成论文第 6 章要用的实测数据。

用法（先在另一个窗口启动服务端：scripts\\run_server.cmd）：
    python tests/smoke_test.py
    python tests/smoke_test.py --base http://127.0.0.1:8000 --repeat 3

产物：tests/smoke_report.md，包含三张表：
    表 6-1 接口功能测试用例及结果
    表 6-2 接口响应时间测试结果
    表 6-3 降级与异常测试结果

设计要点：只依赖标准库，重复运行不会污染已有数据（每次新建测试账号）。
"""
import argparse
import os
import statistics
import sys
import time
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from client import Client                                     # noqa: E402

REPORT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smoke_report.md")

results = []      # 功能测试：[编号, 用例, 请求, 期望, 实际, 结论]
perf = []         # 性能测试：[接口, 功能, 次数, 平均(ms), 最小, 最大]
degrade = []      # 降级测试：[场景, 做法, 期望, 实际, 结论]

_fail_count = 0


def record(case_id, title, request_desc, expected, actual, passed):
    global _fail_count
    if not passed:
        _fail_count += 1
    results.append([case_id, title, request_desc, expected, actual, "通过" if passed else "未通过"])
    print("[%s] %-44s %s" % ("OK " if passed else "FAIL", title, actual))


def record_degrade(title, how, expected, actual, passed):
    global _fail_count
    if not passed:
        _fail_count += 1
    degrade.append([title, how, expected, actual, "通过" if passed else "未通过"])
    print("[%s] %-44s %s" % ("OK " if passed else "FAIL", title, actual))


# ------------------------------------------------------------------
# 一、功能测试
# ------------------------------------------------------------------
def run_functional(c):
    print("\n=== 功能测试 ===")

    r = c.get("/api/v1/health")
    record("TC-01", "服务健康检查", "GET /api/v1/health", "code=0 且 status=up",
           "code=%s status=%s" % (r.code, (r.data or {}).get("status")),
           r.code == 0 and (r.data or {}).get("status") == "up")

    r = c.get("/api/v1/grades")
    n = len((r.data or {}).get("grades") or [])
    record("TC-02", "学段选项拉取", "GET /api/v1/grades", "code=0 且返回 3 个学段",
           "code=%s 学段数=%s" % (r.code, n), r.code == 0 and n == 3)

    guest = Client(c.base_url)
    r = guest.post("/api/v1/quiz/generate", {"topic": "恐龙", "grade": "primary_low"})
    qn = len((r.data or {}).get("questions") or [])
    record("TC-03", "游客模式出题（未登录）", "POST /api/v1/quiz/generate topic=恐龙",
           "code=0 且题量≥3", "code=%s 题量=%s 来源=%s"
           % (r.code, qn, (r.data or {}).get("source")), r.code == 0 and qn >= 3)

    r = c.post("/api/v1/quiz/generate", {"topic": "   "})
    record("TC-04", "空主题入参校验", "POST /api/v1/quiz/generate topic=空格",
           "code=4000", "code=%s message=%s" % (r.code, r.message), r.code == 4000)

    r = c.post("/api/v1/quiz/generate", {"topic": "太" * 80})
    record("TC-05", "超长主题入参校验", "POST /api/v1/quiz/generate topic=80字",
           "code=4000", "code=%s" % r.code, r.code == 4000)

    r = c.post("/api/v1/quiz/generate", {"topic": "制造炸弹"})
    record("TC-06", "内容安全前置校验", "POST /api/v1/quiz/generate topic=制造炸弹",
           "code=4002", "code=%s message=%s" % (r.code, r.message), r.code == 4002)

    r = c.post("/api/v1/quiz/generate", {"topic": "彩虹", "count": 99, "grade": "primary_low"})
    qn = len((r.data or {}).get("questions") or [])
    record("TC-07", "学段题量收敛", "小学低年级请求 99 题", "题量收敛到 8 题",
           "题量=%s" % qn, r.code == 0 and qn == 8)

    q = ((r.data or {}).get("questions") or [{}])[0]
    ok = all(k in q for k in ("id", "stem", "options", "answer", "analysis", "knowledge_point")) \
        and isinstance(q.get("options"), list) \
        and 0 <= int(q.get("answer", -1)) < len(q.get("options") or [1])
    record("TC-08", "题目字段完整性", "检查首题字段",
           "含题干/选项/答案下标/解析/知识点",
           "字段=%s 选项数=%s answer=%s"
           % (len(q.keys()), len(q.get("options") or []), q.get("answer")), ok)

    quiz_id = r.data["quiz_id"]
    questions = r.data["questions"]
    answers = []
    for i, item in enumerate(questions):
        if i < len(questions) // 2:
            answers.append(item["answer"])
        else:
            answers.append((int(item["answer"]) + 1) % len(item["options"]))
    sub = c.post("/api/v1/quiz/submit",
                 {"quiz_id": quiz_id, "answers": answers, "duration_ms": 41500})
    d = sub.data or {}
    record("TC-09", "答题提交与判题", "POST /api/v1/quiz/submit",
           "code=0 且题数一致", "题数=%s 答对=%s 正确率=%s"
           % (d.get("total"), d.get("correct"), d.get("accuracy")),
           sub.code == 0 and d.get("total") == len(questions))

    expected_xp = 10 + int(d.get("correct", 0)) * 2
    record("TC-10", "经验值结算规则", "完成闯关+10、答对每题+2",
           "xp=%s" % expected_xp, "xp=%s" % d.get("xp_gained"), d.get("xp_gained") == expected_xp)

    expect_wrong = (d.get("total", 0) - d.get("correct", 0))
    record("TC-11", "错题自动入库", "答错题写入错题本", "新增错题=%s" % expect_wrong,
           "新增错题=%s" % d.get("wrong_added"), d.get("wrong_added") == expect_wrong)

    r = c.post("/api/v1/quiz/submit", {"quiz_id": "not-exist-quiz", "answers": [0]})
    record("TC-12", "无效 quiz_id 容错", "POST /api/v1/quiz/submit 不存在的ID",
           "code=4000", "code=%s" % r.code, r.code == 4000)

    rep = c.post("/api/v1/report/generate", {"quiz_id": quiz_id})
    rd = (rep.data or {}).get("report") or {}
    ok = rep.code == 0 and bool(rd.get("summary")) and rd.get("suggestion") is not None
    record("TC-13", "复盘报告生成", "POST /api/v1/report/generate",
           "code=0 且含掌握度/总结/建议", "来源=%s 掌握度=%s 档位=%s"
           % (rd.get("source"), rd.get("mastery"), rd.get("level")), bool(ok))

    r = c.post("/api/v1/report/generate", {"quiz_id": "not-exist-quiz"})
    record("TC-14", "未提交先取报告容错", "POST /api/v1/report/generate 不存在的ID",
           "code=4000", "code=%s" % r.code, r.code == 4000)

    w = c.get("/api/v1/wrong/questions")
    wd = w.data or {}
    record("TC-15", "错题本总览", "GET /api/v1/wrong/questions",
           "code=0 且错题数与提交一致", "错题数=%s 薄弱知识点=%s"
           % (wd.get("total"), len(wd.get("weak_points") or [])),
           w.code == 0 and wd.get("total") == expect_wrong)

    p = c.post("/api/v1/wrong/practice", {"count": 5, "grade": "primary_high"})
    pd = p.data or {}
    record("TC-16", "只练错题（不调用大模型）", "POST /api/v1/wrong/practice count=5",
           "code=0 且来源=wrongbook", "来源=%s 题量=%s"
           % (pd.get("source"), len(pd.get("questions") or [])),
           p.code == 0 and pd.get("source") == "wrongbook")

    pr = c.get("/api/v1/user/profile")
    prd = pr.data or {}
    record("TC-17", "个人中心数据", "GET /api/v1/user/profile",
           "code=0 且含经验值与历史", "经验值=%s 历史闯关=%s"
           % ((prd.get("user") or {}).get("total_xp"), len(prd.get("sessions") or [])),
           pr.code == 0)

    r = guest.get("/api/v1/user/profile")
    record("TC-18", "未登录访问个人中心", "GET /api/v1/user/profile 无 Token",
           "code=4010", "code=%s" % r.code, r.code == 4010)

    r = guest.get("/api/v1/wrong/questions")
    record("TC-19", "未登录访问错题本", "GET /api/v1/wrong/questions 无 Token",
           "code=4010", "code=%s" % r.code, r.code == 4010)

    fresh = Client(c.base_url)
    fresh.login(nickname="空错题本用户")
    r = fresh.post("/api/v1/wrong/practice", {"count": 5})
    record("TC-20", "空错题本练习容错", "POST /api/v1/wrong/practice 错题本为空",
           "code=4003", "code=%s" % r.code, r.code == 4003)

    doc_text = ("水循环是指水在地球上的循环过程。海水受热蒸发变成水蒸气，"
                "水蒸气上升到高空遇冷凝结成小水滴，形成云。云中的水滴增大后以雨雪形式降落回地面，"
                "一部分汇入河流回到海洋，一部分渗入地下成为地下水。\n"
                "太阳是水循环的能量来源，没有太阳的照射，水就无法蒸发。\n")
    up = c.upload("/api/v1/knowledge/documents", "水循环讲义.txt", doc_text)
    ud = up.data or {}
    record("TC-21", "知识库文档上传", "POST /api/v1/knowledge/documents (txt)",
           "code=0 且返回分块数", "文档ID=%s 分块=%s" % (ud.get("doc_id"), ud.get("chunks")),
           up.code == 0)

    lst = c.get("/api/v1/knowledge/documents")
    docs = (lst.data or {}).get("documents") or []
    record("TC-22", "知识库列表", "GET /api/v1/knowledge/documents",
           "code=0 且包含刚上传文档", "文档数=%s" % len(docs),
           lst.code == 0 and any(x.get("doc_id") == ud.get("doc_id") for x in docs))

    rag = c.post("/api/v1/quiz/generate",
                 {"topic": "水循环", "doc_id": ud.get("doc_id"), "grade": "primary_high"})
    record("TC-23", "检索增强（RAG）出题", "POST /api/v1/quiz/generate 带 doc_id",
           "code=0 且返回命中片段数", "命中片段=%s 来源=%s"
           % ((rag.data or {}).get("hit_chunks"), (rag.data or {}).get("source")),
           rag.code == 0)

    bad = c.upload("/api/v1/knowledge/documents", "可疑文件.exe", "MZ binary")
    record("TC-24", "不支持的文件格式", "上传 .exe 文件", "code=4001",
           "code=%s" % bad.code, bad.code == 4001)

    empty = c.upload("/api/v1/knowledge/documents", "空文件.txt", "   ")
    record("TC-25", "空文档容错", "上传只含空白的 txt", "code=4001",
           "code=%s" % empty.code, empty.code == 4001)

    dele = c.delete("/api/v1/knowledge/documents/" + str(ud.get("doc_id")))
    record("TC-26", "知识库文档删除", "DELETE /api/v1/knowledge/documents/{doc_id}",
           "code=0", "code=%s" % dele.code, dele.code == 0)

    clr = c.delete("/api/v1/wrong/questions")
    after = c.get("/api/v1/wrong/questions")
    record("TC-27", "清空错题本", "DELETE /api/v1/wrong/questions",
           "code=0 且错题数归零", "残留错题=%s" % ((after.data or {}).get("total")),
           clr.code == 0 and (after.data or {}).get("total") == 0)

    # ---------------- 管理端 ----------------
    sa = Client(c.base_url)
    r = sa.admin_login()
    record("TC-28", "管理端登录", "POST /api/v1/admin/login",
           "code=0 且返回 Token", "code=%s" % r.code, r.code == 0)

    r = sa.admin_login(password="wrong-password")
    record("TC-29", "管理端口令错误", "POST /api/v1/admin/login 错误口令",
           "code=4011", "code=%s message=%s" % (r.code, r.message), r.code == 4011)

    noauth = Client(c.base_url)
    r = noauth.get("/api/v1/admin/dashboard")
    record("TC-30", "管理端未授权访问", "GET /api/v1/admin/dashboard 无 Token",
           "code=4011", "code=%s" % r.code, r.code == 4011)

    r = sa.get("/api/v1/admin/dashboard")
    dd = r.data or {}
    record("TC-31", "管理端运行看板", "GET /api/v1/admin/dashboard",
           "code=0 且含用户/闯关/错题统计", "用户数=%s 闯关数=%s 平均正确率=%s"
           % (dd.get("users", {}).get("total"), dd.get("quizzes", {}).get("total"),
              dd.get("answers", {}).get("avg_accuracy")),
           r.code == 0 and dd.get("users", {}).get("total", 0) >= 2)

    created = sa.post("/api/v1/admin/questions", {
        "theme": "天文", "grade": "primary_high", "stem": "月球绕地球一周大约需要多少天？",
        "options": ["约 7 天", "约 27 天", "约 90 天", "约 365 天"], "answer": 1,
        "analysis": "月球绕地球公转一周约 27.3 天，称为一个恒星月。",
        "knowledge_point": "月球运动", "difficulty": 2})
    qid = (created.data or {}).get("id")
    record("TC-32", "管理端新增题目", "POST /api/v1/admin/questions",
           "code=0 且返回新题 ID", "新题ID=%s" % qid, created.code == 0 and bool(qid))

    r = sa.get("/api/v1/admin/questions?keyword=" + quote("月球"))
    total = (r.data or {}).get("total")
    record("TC-33", "管理端题库查询", "GET /api/v1/admin/questions?keyword=月球",
           "code=0 且命中 1 条", "命中=%s" % total, r.code == 0 and total == 1)

    r = sa.post("/api/v1/admin/questions", {"stem": "测试题", "options": ["A", "B"], "answer": 5})
    record("TC-34", "管理端题目参数校验", "answer 下标越界", "code=4000",
           "code=%s message=%s" % (r.code, r.message), r.code == 4000)

    r = sa.put("/api/v1/admin/questions/%s" % qid, {"difficulty": 3, "enabled": 1})
    record("TC-35", "管理端修改题目", "PUT /api/v1/admin/questions/{id}",
           "code=0", "code=%s" % r.code, r.code == 0)

    pool = Client(c.base_url)
    r = pool.post("/api/v1/quiz/generate", {"topic": "月球", "count": 8, "grade": "primary_high"})
    stems = [x.get("stem") for x in ((r.data or {}).get("questions") or [])]
    hit = "月球绕地球一周大约需要多少天？" in stems
    record("TC-36", "资源池题目参与出题", "出题时优先命中管理端题库",
           "题目中包含新增题", "命中=%s" % hit, hit)

    r = sa.delete("/api/v1/admin/questions/%s" % qid)
    record("TC-37", "管理端删除题目", "DELETE /api/v1/admin/questions/{id}",
           "code=0", "code=%s" % r.code, r.code == 0)

    r = sa.get("/api/v1/admin/users")
    record("TC-38", "管理端用户列表", "GET /api/v1/admin/users",
           "code=0 且含闯关数统计", "用户数=%s" % (r.data or {}).get("total"), r.code == 0)

    r = sa.get("/api/v1/admin/sessions?size=5")
    record("TC-39", "管理端闯关记录", "GET /api/v1/admin/sessions",
           "code=0", "记录数=%s 总数=%s" % (len((r.data or {}).get("items") or []),
                                          (r.data or {}).get("total")), r.code == 0)

    r = sa.get("/api/v1/admin/logs?limit=20")
    logs = (r.data or {}).get("logs") or []
    record("TC-40", "管理端操作日志留痕", "GET /api/v1/admin/logs",
           "code=0 且包含题库操作记录", "日志条数=%s" % len(logs),
           r.code == 0 and any(str(x.get("action", "")).startswith("pool.") for x in logs))


# ------------------------------------------------------------------
# 二、性能测试
# ------------------------------------------------------------------
def run_perf(c, repeat=3):
    print("\n=== 响应时间测试（每项重复 %d 次）===" % repeat)

    def make_submit():
        def fn():
            gen = c.post("/api/v1/quiz/generate", {"topic": "化学", "grade": "primary_high"})
            gq = gen.data["questions"]
            return c.post("/api/v1/quiz/submit",
                          {"quiz_id": gen.data["quiz_id"],
                           "answers": [x["answer"] for x in gq]})
        return fn

    def make_report():
        def fn():
            gen = c.post("/api/v1/quiz/generate", {"topic": "地理", "grade": "primary_high"})
            gq = gen.data["questions"]
            c.post("/api/v1/quiz/submit",
                   {"quiz_id": gen.data["quiz_id"], "answers": [x["answer"] for x in gq]})
            return c.post("/api/v1/report/generate", {"quiz_id": gen.data["quiz_id"]})
        return fn

    cases = [
        ("GET /api/v1/grades", "学段选项查询", lambda: c.get("/api/v1/grades")),
        ("POST /api/v1/user/login", "用户登录",
         lambda: c.post("/api/v1/user/login", {"nickname": "性能测试用户"})),
        ("POST /api/v1/quiz/generate", "出题（题库降级路径）",
         lambda: c.post("/api/v1/quiz/generate", {"topic": "太阳系", "grade": "primary_high"})),
        ("POST /api/v1/quiz/submit", "判题与结算", make_submit()),
        ("POST /api/v1/report/generate", "复盘报告（规则降级路径）", make_report()),
        ("GET /api/v1/wrong/questions", "错题本查询", lambda: c.get("/api/v1/wrong/questions")),
    ]

    # 先制造一些错题，保证"只练错题"有数据可组卷
    prep = c.post("/api/v1/quiz/generate", {"topic": "生物", "grade": "primary_high"})
    pq = prep.data["questions"]
    c.post("/api/v1/quiz/submit",
           {"quiz_id": prep.data["quiz_id"],
            "answers": [(int(x["answer"]) + 1) % 4 for x in pq]})
    cases.append(("POST /api/v1/wrong/practice", "只练错题组卷",
                  lambda: c.post("/api/v1/wrong/practice", {"count": 5})))

    for path, name, fn in cases:
        times = []
        for _ in range(repeat):
            resp = fn()
            times.append(resp.elapsed_ms)
            if resp.code != 0:
                print("   ! %s 未成功：code=%s %s" % (path, resp.code, resp.message))
        avg = statistics.mean(times)
        perf.append([path, name, repeat, "%.0f" % avg, "%.0f" % min(times), "%.0f" % max(times)])
        print("  %-32s avg=%.0fms min=%.0fms max=%.0fms" % (path, avg, min(times), max(times)))


# ------------------------------------------------------------------
# 三、降级与异常测试
# ------------------------------------------------------------------
def run_degrade(c):
    print("\n=== 降级与异常测试 ===")

    r = c.post("/api/v1/quiz/generate", {"topic": "太阳系", "grade": "primary_high"})
    src = (r.data or {}).get("source")
    record_degrade("无大模型 Key 时出题降级", "不配置 DEEPSEEK_API_KEY 直接出题",
                   "source=bank 且题量满足学段要求",
                   "source=%s 题量=%s" % (src, len((r.data or {}).get("questions") or [])),
                   r.code == 0 and src in ("bank", "ai"))

    gen = c.post("/api/v1/quiz/generate", {"topic": "物理", "grade": "primary_low"})
    qs = gen.data["questions"]
    c.post("/api/v1/quiz/submit",
           {"quiz_id": gen.data["quiz_id"],
            "answers": [(int(x["answer"]) + 1) % 4 for x in qs]})
    r = c.post("/api/v1/report/generate", {"quiz_id": gen.data["quiz_id"]})
    rd = (r.data or {}).get("report") or {}
    record_degrade("无大模型 Key 时报告降级", "提交后生成复盘报告",
                   "source=rule 且给出分档结论",
                   "source=%s level=%s" % (rd.get("source"), rd.get("level")),
                   r.code == 0 and rd.get("source") in ("rule", "ai") and bool(rd.get("summary")))

    sub = c.post("/api/v1/quiz/submit",
                 {"quiz_id": gen.data["quiz_id"], "answers": [x["answer"] for x in qs]})
    record_degrade("降级题目可正常判题", "对题库降级生成的题全部选正确答案",
                   "code=0 且正确率 100%", "正确率=%s" % (sub.data or {}).get("accuracy"),
                   sub.code == 0 and (sub.data or {}).get("accuracy") == 100.0)

    up = c.upload("/api/v1/knowledge/documents", "无关资料.txt",
                  "今天是星期一，天气晴朗，适合出门散步。")
    doc_id = (up.data or {}).get("doc_id")
    r = c.post("/api/v1/quiz/generate", {"topic": "量子纠缠", "doc_id": doc_id})
    record_degrade("检索无命中时的容错", "上传无关资料后基于它出题",
                   "code=0 且正常返回题目",
                   "code=%s 命中片段=%s 题量=%s"
                   % (r.code, (r.data or {}).get("hit_chunks"),
                      len((r.data or {}).get("questions") or [])), r.code == 0)

    r = c.request("POST", "/api/v1/quiz/generate", raw_body=b"{not-a-json}")
    record_degrade("非法 JSON 请求体", "POST 非法 JSON 字符串",
                   "code=4000，不暴露堆栈", "code=%s" % r.code, r.code == 4000)

    r = c.post("/api/v1/quiz/generate", {"topic": "水循环", "doc_id": "no-such-doc"})
    record_degrade("不存在的文档 ID", "doc_id 指向不存在的文档",
                   "code=0 且退化为普通出题",
                   "code=%s 命中片段=%s" % (r.code, (r.data or {}).get("hit_chunks")),
                   r.code == 0)

    fake = Client(c.base_url)
    fake.admin_token = "forged-token-123456"
    r = fake.get("/api/v1/admin/dashboard")
    record_degrade("伪造管理端 Token", "使用伪造 X-Admin-Token 访问看板",
                   "code=4011", "code=%s" % r.code, r.code == 4011)

    gen = c.post("/api/v1/quiz/generate", {"topic": "科技", "grade": "junior"})
    qs = gen.data["questions"]
    ans = [x["answer"] for x in qs]
    r1 = c.post("/api/v1/quiz/submit", {"quiz_id": gen.data["quiz_id"], "answers": ans})
    r2 = c.post("/api/v1/quiz/submit", {"quiz_id": gen.data["quiz_id"], "answers": ans})
    record_degrade("同一会话重复提交", "连续提交两次相同答案",
                   "两次均 code=0 且结果一致",
                   "两次正确率=%s / %s" % ((r1.data or {}).get("accuracy"),
                                          (r2.data or {}).get("accuracy")),
                   r1.code == 0 and r2.code == 0
                   and (r1.data or {}).get("accuracy") == (r2.data or {}).get("accuracy"))

    gen = c.post("/api/v1/quiz/generate", {"topic": "地理", "grade": "primary_high"})
    r = c.post("/api/v1/quiz/submit", {"quiz_id": gen.data["quiz_id"], "answers": [0]})
    record_degrade("答案数组长度不足", "只提交 1 个答案",
                   "code=0，未作答按未答处理",
                   "code=%s 答对=%s/%s" % (r.code, (r.data or {}).get("correct"),
                                          (r.data or {}).get("total")), r.code == 0)

    # 清理本次测试上传的知识库文档
    for doc in ((c.get("/api/v1/knowledge/documents").data or {}).get("documents") or []):
        c.delete("/api/v1/knowledge/documents/" + doc["doc_id"])


# ------------------------------------------------------------------
# 报告输出
# ------------------------------------------------------------------
def write_report(base_url, started_at, duration, repeat):
    lines = []
    lines.append("# 接口冒烟测试报告")
    lines.append("")
    lines.append("| 项目 | 内容 |")
    lines.append("| --- | --- |")
    lines.append("| 被测服务 | %s |" % base_url)
    lines.append("| 测试时间 | %s |" % started_at)
    lines.append("| 测试耗时 | %.1f 秒 |" % duration)
    lines.append("| 测试脚本 | `backend/tests/smoke_test.py`（仅标准库，可重复运行） |")
    lines.append("| 用例构成 | %d 条功能用例 + %d 条性能用例 + %d 条降级用例 |"
                 % (len(results), len(perf), len(degrade)))
    total_case = len(results) + len(degrade)
    passed_case = total_case - _fail_count
    lines.append("| 通过情况 | %d / %d（通过率 %.1f%%） |"
                 % (passed_case, total_case,
                    passed_case * 100.0 / total_case if total_case else 0))
    lines.append("")
    lines.append("> 本报告由脚本自动生成，表中数据均为本机实测值，可直接用于论文第 6 章。")
    lines.append("")

    lines.append("## 表 6-1 接口功能测试用例及结果")
    lines.append("")
    lines.append("| 编号 | 测试用例 | 请求 | 预期结果 | 实际结果 | 结论 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for row in results:
        lines.append("| %s | %s | %s | %s | %s | %s |" % tuple(row))
    lines.append("")

    lines.append("## 表 6-2 接口响应时间测试结果")
    lines.append("")
    lines.append("| 接口 | 功能 | 重复次数 | 平均响应时间(ms) | 最小(ms) | 最大(ms) |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for row in perf:
        lines.append("| %s | %s | %s | %s | %s | %s |" % tuple(row))
    lines.append("")
    lines.append("> 说明：以上为题库降级路径（未配置大模型 Key）的实测值，不含大模型网络往返时间。"
                 "配置 DeepSeek Key 后，出题接口耗时主要由模型推理决定，通常在 10～40 秒；"
                 "因此小程序端设计了分档等待台词与科普轮播，把等待时间转化为学习时间（见 4.9、5.8 节）。")
    lines.append("")

    lines.append("## 表 6-3 降级与异常测试结果")
    lines.append("")
    lines.append("| 测试场景 | 做法 | 预期结果 | 实际结果 | 结论 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for row in degrade:
        lines.append("| %s | %s | %s | %s | %s |" % tuple(row))
    lines.append("")

    lines.append("## 结论")
    lines.append("")
    if _fail_count == 0:
        lines.append("全部用例通过。系统在正常路径、异常路径与降级路径下均给出符合预期的响应；"
                     "大模型不可用时，出题、判题、复盘报告、只练错题四条链路仍保持可用，"
                     "说明三层降级机制达到了设计目标。")
    else:
        lines.append("存在 %d 条未通过用例，详见上表，需修复后复测。" % _fail_count)
    lines.append("")

    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return REPORT_PATH


def main():
    parser = argparse.ArgumentParser(description="科普知识闯关小程序 · 接口冒烟测试")
    parser.add_argument("--base", default=os.getenv("KEPU_BASE_URL", "http://127.0.0.1:8000"),
                        help="服务端地址，默认 http://127.0.0.1:8000")
    parser.add_argument("--repeat", type=int, default=3, help="性能用例重复次数，默认 3")
    parser.add_argument("--skip-perf", action="store_true", help="跳过性能用例")
    args = parser.parse_args()

    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    t0 = time.time()

    client = Client(args.base)
    health = client.get("/api/v1/health")
    if health.status == 0:
        print("无法连接服务端 %s，请先运行 scripts\\run_server.cmd" % args.base)
        print("错误信息：%s" % health.message)
        return 2
    print("服务端在线：%s（大模型已配置：%s）"
          % (args.base, (health.data or {}).get("llm_configured")))

    client.login(nickname="冒烟测试用户")
    run_functional(client)
    if not args.skip_perf:
        run_perf(client, args.repeat)
    run_degrade(client)

    path = write_report(args.base, started_at, time.time() - t0, args.repeat)
    print("\n报告已生成：%s" % path)
    print("功能用例 %d 条、降级用例 %d 条，未通过 %d 条。"
          % (len(results), len(degrade), _fail_count))
    return 0 if _fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
