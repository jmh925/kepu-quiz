# -*- coding: utf-8 -*-
"""错题本增删改查（CRUD）联调验证。

覆盖：新增（答题答错自动入库）→ 查询 → 修改（题干/答案/知识点）→ 删除单条 → 清空。
用法：先在另一个窗口启动后端，然后 python tools/check_wrongbook_crud.py
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend", "tests"))
from client import Client          # noqa: E402

problems = []


def check(ok, msg):
    print(("[OK  ] " if ok else "[FAIL] ") + msg)
    if not ok:
        problems.append(msg)


def main():
    base = os.getenv("KEPU_BASE_URL", "http://127.0.0.1:8000")
    c = Client(base)
    c.login(nickname="CRUD 验证用户")
    c.delete("/api/v1/wrong/questions")          # 干净起点

    # ---------- 新增：答错自动入库 ----------
    gen = c.post("/api/v1/quiz/generate", {"topic": "太阳系", "grade": "primary_high"})
    qs = gen.data["questions"]
    c.post("/api/v1/quiz/submit",
           {"quiz_id": gen.data["quiz_id"],
            "answers": [(int(q["answer"]) + 1) % len(q["options"]) for q in qs]})
    listing = c.get("/api/v1/wrong/questions").data
    total = listing["total"]
    check(total == len(qs), "新增（答错自动入库）：入库 %d 条，与答错题数一致" % total)

    first = listing["questions"][0]
    stem = first["stem"]
    check(bool(first.get("user_answer") is not None), "查询：返回「你的答案」字段（user_answer=%s）"
          % first.get("user_answer"))

    # ---------- 修改：改知识点与解析 ----------
    r = c.put("/api/v1/wrong/questions",
              {"stem": stem, "knowledge_point": "改过的知识点", "analysis": "改过的解析"})
    check(r.code == 0, "修改：改知识点与解析 → code=%s" % r.code)
    after = c.get("/api/v1/wrong/questions").data
    row = next((x for x in after["questions"] if x["stem"] == stem), None)
    check(row and row["knowledge_point"] == "改过的知识点" and row["analysis"] == "改过的解析",
          "修改：改动已生效（知识点=%s）" % (row or {}).get("knowledge_point"))

    # ---------- 修改：改题干（同时验证唯一性保护） ----------
    new_stem = stem + "（修订版）"
    r = c.put("/api/v1/wrong/questions", {"stem": stem, "new_stem": new_stem})
    check(r.code == 0, "修改：改题干 → code=%s" % r.code)
    after = c.get("/api/v1/wrong/questions").data
    check(any(x["stem"] == new_stem for x in after["questions"]), "修改：新题干可查回")
    check(not any(x["stem"] == stem for x in after["questions"]), "修改：旧题干已不再存在")

    # ---------- 修改：非法答案下标应被拒绝 ----------
    r = c.put("/api/v1/wrong/questions", {"stem": new_stem, "answer": 99})
    check(r.code == 4000, "修改：答案下标越界被拒绝（code=%s）" % r.code)

    # ---------- 修改：不存在的题 ----------
    r = c.put("/api/v1/wrong/questions", {"stem": "这道题根本不存在", "analysis": "x"})
    check(r.code == 4003, "修改：题目不存在时返回 4003（code=%s）" % r.code)

    # ---------- 删除单条 ----------
    r = c.delete("/api/v1/wrong/questions/" + new_stem)
    check(r.code == 0, "删除：删除单条 → code=%s" % r.code)
    after = c.get("/api/v1/wrong/questions").data
    check(after["total"] == total - 1, "删除：总数由 %d 变为 %d" % (total, after["total"]))

    r = c.delete("/api/v1/wrong/questions/" + new_stem)
    check(r.code == 4003, "删除：重复删除返回 4003（code=%s）" % r.code)

    # ---------- 清空 ----------
    r = c.delete("/api/v1/wrong/questions")
    after = c.get("/api/v1/wrong/questions").data
    check(r.code == 0 and after["total"] == 0, "清空：错题本归零（total=%s）" % after["total"])

    # ---------- 未登录保护 ----------
    guest = Client(base)
    check(guest.put("/api/v1/wrong/questions", {"stem": "x"}).code == 4010,
          "未登录：修改接口返回 4010")
    check(guest.delete("/api/v1/wrong/questions/xx").code == 4010,
          "未登录：删除接口返回 4010")

    print("\n未通过：%d 项" % len(problems))
    for p in problems:
        print("  - " + p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
