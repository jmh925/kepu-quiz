# -*- coding: utf-8 -*-
"""重置 / 初始化数据库。

用途：
- 答辩前把演示数据清空，从干净状态开始演示；
- 数据库结构被改坏时快速重建；
- 首次部署时不启动服务也能先建好表。

用法（在 backend 目录下）：
    python ../tools/reset_db.py                # 删库重建（自动建表 + 创建默认管理员）
    python ../tools/reset_db.py --demo         # 额外灌入一批演示数据
    python ../tools/reset_db.py --keep         # 只建表，不清空已有数据
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(BACKEND, "deps"))

from app import admin_db, database as db            # noqa: E402
from app import services                            # noqa: E402
from app.config import settings                     # noqa: E402

DEMO_TOPICS = ["太阳系", "恐龙", "彩虹是怎么来的", "水循环", "人工智能"]


def drop_db():
    for suffix in ("", "-journal", "-wal", "-shm"):
        path = settings.db_path + suffix
        if os.path.exists(path):
            os.remove(path)
            print("已删除 %s" % path)
    db.reset_connection()


def seed_demo():
    """灌入演示数据：1 个学生账号、5 次闯关、若干错题、1 份知识库文档、2 道资源池题目。"""
    login = services.login(nickname="演示小科学家", grade="primary_high")
    user_id = login["user"]["id"]
    print("演示用户：%s（id=%s）" % (login["user"]["nickname"], user_id))

    for i, topic in enumerate(DEMO_TOPICS):
        quiz = services.generate_quiz(topic, None, user_id, None, "primary_high")
        questions = quiz["questions"]
        # 前几题答对、后面的故意答错，形成错题本与薄弱知识点
        answers = []
        for idx, q in enumerate(questions):
            if idx < max(1, len(questions) - 3 - i):
                answers.append(int(q["answer"]))
            else:
                answers.append((int(q["answer"]) + 1) % max(1, len(q["options"])))
        services.submit_answer(quiz["quiz_id"], answers, user_id, duration_ms=30000 + i * 3000)
        services.generate_report(quiz["quiz_id"], user_id)
        print("  闯关 %d：%s（%d 题）" % (i + 1, topic, len(questions)))

    doc = services.add_document(
        "水循环讲义.txt",
        "水循环是指水在地球上的循环过程。海水受热蒸发变成水蒸气，上升遇冷凝结成云，"
        "再以雨雪形式降落回地面，汇入河流或渗入地下，最终回到海洋。\n"
        "太阳是水循环的能量来源。",
        user_id, size_bytes=520)
    print("演示文档：%s（%d 个分块）" % (doc["filename"], doc["chunks"]))

    for payload in (
        {"theme": "天文", "grade": "primary_high", "stem": "月球绕地球一周大约需要多少天？",
         "options": ["约 7 天", "约 27 天", "约 90 天", "约 365 天"], "answer": 1,
         "analysis": "月球绕地球公转一周约 27.3 天，称为一个恒星月。",
         "knowledge_point": "月球运动", "difficulty": 2, "enabled": 1},
        {"theme": "生物", "grade": "junior", "stem": "植物进行光合作用的主要场所是？",
         "options": ["线粒体", "叶绿体", "细胞核", "液泡"], "answer": 1,
         "analysis": "叶绿体含有叶绿素，是光合作用的主要场所；线粒体主要负责呼吸作用。",
         "knowledge_point": "细胞结构", "difficulty": 2, "enabled": 1},
    ):
        qid, err = admin_db.create_pool_question(payload, "seed")
        print("资源池题目 #%s：%s" % (qid, err or "已加入"))

    print("演示数据灌入完成。")


def seed_pool_from_bank():
    """把内置分级题库导入题目资源池。

    为什么需要：资源池是管理端维护的，出题时优先命中；
    但它初始为空时，管理端「题库资源池」页面看不到任何数据，
    也没法按学段筛选查看。这个函数把内置的 150 道分级题导入池子，
    让管理端一打开就有内容可看、可改、可删。
    """
    sys.path.insert(0, BACKEND)
    from app.question_bank import all_questions
    from app import admin_db

    added = 0
    for q in all_questions():
        theme = q.get("theme") or "通用"
        grade = q.get("grade") or "primary_high"
        stem = q.get("stem")
        if not stem:
            continue
        exists = db.query_one("SELECT id FROM question_pool WHERE stem=?", (stem,))
        if exists:
            continue
        options = q.get("options") or []
        answer = int(q.get("answer") or 0)
        if len(options) < 2 or answer < 0 or answer >= len(options):
            continue         # 宁可少导一条，也不往池子里塞不合法数据
        admin_db.create_pool_question({
            "theme": theme, "grade": grade, "stem": stem, "options": options,
            "answer": answer, "analysis": q.get("analysis") or "",
            "knowledge_point": q.get("knowledge_point") or "科普知识",
            "difficulty": {"primary_low": 1, "primary_high": 2, "junior": 3}.get(grade, 2),
            "enabled": 1,
        }, "seed")
        added += 1
    print("题库导入资源池：新增 %d 道（已存在的跳过）" % added)


def main():
    parser = argparse.ArgumentParser(description="重置 / 初始化数据库")
    parser.add_argument("--demo", action="store_true", help="额外灌入演示数据")
    parser.add_argument("--seed-pool", action="store_true",
                        help="把内置分级题库导入题目资源池（管理端可见、可改）")
    parser.add_argument("--keep", action="store_true", help="只建表，不清空已有数据")
    args = parser.parse_args()

    if not args.keep:
        drop_db()
    db.get_conn()
    created = admin_db.ensure_default_admin()
    tables = [r["name"] for r in db.query(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name")]
    print("数据库：%s" % settings.db_path)
    print("已建表 %d 张：%s" % (len(tables), "、".join(tables)))
    print("默认管理员：%s%s" % (settings.admin_username,
                              "（本次新建）" if created else "（已存在）"))
    if args.seed_pool:
        seed_pool_from_bank()
    if args.demo:
        seed_demo()
    return 0


if __name__ == "__main__":
    sys.exit(main())
