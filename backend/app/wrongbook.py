# -*- coding: utf-8 -*-
"""错题本：把答错的题结构化沉淀下来，支撑"只练错题"的个性化复习闭环。

设计说明：
- 只依赖 database 模块（不依赖 FastAPI / JWT / httpx），因此可以脱离 Web 层单独测试；
- 去重语义：同一用户、同一题干视为同一道错题，再次答错则 wrong_count 累加，便于排序出最该复习的题；
- 掌握语义：某题答对后即从错题本移除，表示已掌握；
- "只练错题"不需要调用大模型，直接用错题重组一套练习卷，秒级返回——
  这既改善体验，也让系统在大模型不可用时依然有可用的复习功能。
"""
import json

from . import database as db


def record_wrong(user_id, quiz_id, details):
    """把本次答错的题写入错题本，返回新增/更新的条数。"""
    if not user_id:
        return 0
    n = 0
    for d in details or []:
        if d.get("is_correct"):
            continue
        stem = (d.get("stem") or "").strip()
        if not stem:
            continue
        row = db.query_one(
            "SELECT id FROM wrong_questions WHERE user_id=? AND stem=?", (user_id, stem))
        if row:
            db.execute(
                "UPDATE wrong_questions SET wrong_count=wrong_count+1, user_answer=?, "
                "last_wrong_at=datetime('now','localtime') WHERE id=?",
                (d.get("user_answer"), row["id"]))
        else:
            db.execute(
                "INSERT INTO wrong_questions(user_id, quiz_id, stem, options_json, "
                "correct_answer, user_answer, analysis, knowledge_point) VALUES(?,?,?,?,?,?,?,?)",
                (user_id, quiz_id, stem,
                 json.dumps(d.get("options") or [], ensure_ascii=False),
                 d.get("correct_answer"), d.get("user_answer"),
                 d.get("analysis", ""), d.get("knowledge_point", "")))
        n += 1
    return n


def mark_mastered(user_id, details):
    """本次答对的题从错题本移除（表示已掌握），返回移除条数。"""
    if not user_id:
        return 0
    n = 0
    for d in details or []:
        if not d.get("is_correct"):
            continue
        stem = (d.get("stem") or "").strip()
        if not stem:
            continue
        row = db.query_one(
            "SELECT id FROM wrong_questions WHERE user_id=? AND stem=?", (user_id, stem))
        if row:
            db.execute("DELETE FROM wrong_questions WHERE id=?", (row["id"],))
            n += 1
    return n


def count_wrong(user_id):
    """错题总数。"""
    if not user_id:
        return 0
    row = db.query_one(
        "SELECT COUNT(*) AS c FROM wrong_questions WHERE user_id=?", (user_id,))
    return int(row["c"]) if row else 0


def list_wrong(user_id, limit=100):
    """错题列表，按错误次数与最近答错时间排序。

    返回字段同时服务两处场景：错题本页面需要「正确答案 / 你的答案」做展开讲解，
    「只练错题」需要把它直接还原成一道可作答的题目（见 build_practice_quiz）。
    """
    if not user_id:
        return []
    rows = db.query(
        "SELECT quiz_id, stem, options_json, correct_answer, user_answer, analysis, "
        "knowledge_point, wrong_count, last_wrong_at FROM wrong_questions WHERE user_id=? "
        "ORDER BY wrong_count DESC, last_wrong_at DESC LIMIT ?", (user_id, limit))
    out = []
    for r in rows:
        out.append({
            "quiz_id": r["quiz_id"],
            "stem": r["stem"],
            "options": json.loads(r["options_json"] or "[]"),
            "answer": r["correct_answer"],
            "user_answer": r["user_answer"] if r["user_answer"] is not None else -1,
            "analysis": r["analysis"] or "",
            "knowledge_point": r["knowledge_point"] or "科普知识",
            "wrong_count": r["wrong_count"],
            "last_wrong_at": r["last_wrong_at"],
        })
    return out


def weak_points(user_id, limit=8):
    """按知识点聚合，给出最需要复习的知识点排行。"""
    if not user_id:
        return []
    rows = db.query(
        "SELECT knowledge_point AS kp, COUNT(*) AS c, SUM(wrong_count) AS w "
        "FROM wrong_questions WHERE user_id=? GROUP BY knowledge_point "
        "ORDER BY w DESC LIMIT ?", (user_id, limit))
    return [
        {"knowledge_point": r["kp"] or "科普知识",
         "questions": r["c"], "wrong_times": r["w"] or 0}
        for r in rows
    ]


def clear(user_id):
    """清空某用户的错题本。"""
    if not user_id:
        return 0
    db.execute("DELETE FROM wrong_questions WHERE user_id=?", (user_id,))
    return 1


def build_practice_quiz(user_id, count=8):
    """只用错题重组一套练习卷；无需调用大模型，秒级返回。

    返回题目列表；错题本为空时返回 None。
    """
    items = list_wrong(user_id, limit=50)
    if not items:
        return None
    try:
        n = max(1, min(int(count), len(items)))
    except (TypeError, ValueError):
        n = min(8, len(items))
    questions = []
    for i, it in enumerate(items[:n]):
        questions.append({
            "id": i + 1,
            "type": "single",
            "stem": it["stem"],
            "options": it["options"],
            "answer": it["answer"],
            "analysis": it["analysis"],
            "knowledge_point": it["knowledge_point"],
        })
    return questions
