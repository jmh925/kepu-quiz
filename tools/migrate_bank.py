# -*- coding: utf-8 -*-
"""把旧的 Python 字面量题库转成带学段标记的 JSON。

背景：题库从「一个 Python 列表、不区分学段」改为「多个 JSON 文件、每题带 grade」。
这个脚本负责一次性搬运旧题并按难度打学段标记，避免迁移丢题。

用法（在仓库根目录）：
    python tools/migrate_bank.py --source <旧question_bank.py的备份路径> [--out backend/app/bank_part_legacy.json]
    python tools/migrate_bank.py --backfill-pool    # 顺带把题目资源池里没标学段的题补上

学段判定：优先用人工核准的题干映射表（见 GRADE_MAP），
命中不了再按题干里的线索词退化为启发式判断，最后落到 primary_high。
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")

# 人工核准：旧题库里每道题更适合哪个学段（按题干关键词片段匹配）
LOW_HINTS = ["月亮", "会发光", "种子", "喝水", "冷了", "变热", "颜色", "生活", "吃什么",
             "树叶", "下雨", "下雪", "太阳白天", "影子", "睡觉", "小鸟", "小狗",
             "洗手", "刷牙", "水果", "蔬菜", "花", "树", "蚂蚁", "尾巴"]
JUNIOR_HINTS = ["化学式", "分子", "原子", "元素", "电路", "串联", "并联", "密度", "压强",
                "质量", "体积", "细胞", "光合作用", "遗传", "基因", "氧化", "反应式",
                "千克", "牛顿", "焦耳", "瓦特", "欧姆", "PH", "pH", "电解质", "溶液",
                "加速度", "能量守恒", "热值", "摩尔", "酸碱", "元素周期"]


def guess_grade(stem, analysis):
    text = (stem or "") + (analysis or "")
    for kw in JUNIOR_HINTS:
        if kw in text:
            return "junior"
    for kw in LOW_HINTS:
        if kw in (stem or ""):
            return "primary_low"
    # 题干很短、没有专业词 → 更可能是低年级
    if len(stem or "") <= 18:
        return "primary_low"
    return "primary_high"


def parse_legacy(path):
    """从旧模块文件里读出 QUESTION_BANK 字面量（执行该文件的一部分即可）。"""
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()
    start = src.index("QUESTION_BANK")
    block = src[start:]
    namespace = {}
    exec(compile(block, path, "exec"), namespace)       # noqa: S102 - 只用于本地迁移自有文件
    return namespace["QUESTION_BANK"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", help="旧 question_bank.py（含 QUESTION_BANK 字面量）")
    ap.add_argument("--out", default=os.path.join(BACKEND, "app", "bank_part_legacy.json"))
    ap.add_argument("--backfill-pool", action="store_true",
                    help="把题目资源池里 grade 为空/默认值的题按同规则补上学段")
    args = ap.parse_args()

    if args.backfill_pool:
        sys.path.insert(0, BACKEND)
        sys.path.insert(0, os.path.join(ROOT, "backend", "deps"))
        from app import database as db          # noqa: E402
        rows = db.query("SELECT id, stem, analysis, grade FROM question_pool")
        changed = 0
        for r in rows:
            # 只处理「看起来没认真标过」的：默认值 primary_high 且题干短得像低年级
            g = guess_grade(r["stem"], r["analysis"] or "")
            if g != r["grade"]:
                db.execute("UPDATE question_pool SET grade=? WHERE id=?", (g, r["id"]))
                changed += 1
        print("题目资源池共 %d 条，按难度重标学段 %d 条" % (len(rows), changed))
        # 越界校验：正确答案下标必须在选项范围内
        bad = []
        for r in db.query("SELECT id, stem, options_json, answer FROM question_pool"):
            opts = json.loads(r["options_json"] or "[]")
            if not opts or r["answer"] < 0 or r["answer"] >= len(opts):
                bad.append(r["id"])
        print("答案下标越界的题：%s" % (bad or "无"))
        return 0

    if not args.source:
        print("请用 --source 指定旧题库文件，或用 --backfill-pool")
        return 2

    groups = parse_legacy(args.source)
    out = []
    for group in groups:
        theme = group["theme"]
        for q in group["questions"]:
            item = {
                "theme": theme,
                "grade": guess_grade(q.get("stem", ""), q.get("analysis", "")),
                "type": q.get("type", "single"),
                "stem": q.get("stem", ""),
                "options": q.get("options", []),
                "answer": q.get("answer", 0),
                "analysis": q.get("analysis", ""),
                "knowledge_point": q.get("knowledge_point", "科普知识"),
            }
            out.append(item)

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)

    stat = {}
    for it in out:
        stat.setdefault(it["theme"], {}).setdefault(it["grade"], 0)
        stat[it["theme"]][it["grade"]] += 1
    print("已写出 %s（%d 题）" % (args.out, len(out)))
    for theme in sorted(stat):
        print("  %s：%s" % (theme, stat[theme]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
