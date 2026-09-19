# -*- coding: utf-8 -*-
"""题库完整性与学段分离自检（独立复核，不依赖子任务的自检脚本）。

检查项：
1. 每份 bank_part_*.json 都能解析、字段齐全、每题 4 个不重复选项、answer 下标合法；
2. **正确答案分布不坍缩**（任一位置占比不得过高，否则「全选 A」就能高分）；
3. **题干不跨学段重复**：同一道题不能既是低年级又是初中题，否则分级形同虚设；
4. 各学段题量充足（每个学段每主题至少 6 题，保证一轮闯关不重题）；
5. 题干/选项长度符合该学段上限；
6. **答案自洽性**：把 analysis 与「被选中的那个选项」放在一起看，
   若解析里明确写了「正确的是 X」而 X 不是该选项，则报可疑，供人工复核。

用法（在仓库根目录）：
    python tools/check_bank_integrity.py
"""
import glob
import io
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "backend", "app")
GRADES = ("primary_low", "primary_high", "junior")
GRADE_CN = {"primary_low": "小学低年级", "primary_high": "小学高年级", "junior": "初中"}
# 与 grades.py 保持一致：题干/选项长度上限
LIMITS = {"primary_low": (25, 6), "primary_high": (40, 10), "junior": (60, 16)}
MIN_PER_THEME_GRADE = 6

problems = []
warns = []


def note(ok, msg):
    print(("[OK  ] " if ok else "[FAIL] ") + msg)
    if not ok:
        problems.append(msg)


def warn(msg):
    print("[注意] " + msg)
    warns.append(msg)


def load_all():
    items = []
    for path in sorted(glob.glob(os.path.join(APP_DIR, "bank_part_*.json"))):
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for it in data:
            it["__file"] = os.path.basename(path)
            items.append(it)
    return items


def main():
    items = load_all()
    print("=== 题库自检：共 %d 题 ===" % len(items))
    if not items:
        note(False, "没有找到任何 bank_part_*.json")
        return 1

    # 1. 字段与选项
    bad = []
    for i, it in enumerate(items, 1):
        opts = it.get("options") or []
        ans = it.get("answer")
        if not it.get("stem") or len(opts) != 4 or len(set(opts)) != 4:
            bad.append((i, it.get("stem", "")[:24], "选项数量/重复"))
            continue
        if not isinstance(ans, int) or ans < 0 or ans >= len(opts):
            bad.append((i, it.get("stem", "")[:24], "answer 下标越界"))
        if not it.get("analysis") or not it.get("knowledge_point"):
            bad.append((i, it.get("stem", "")[:24], "解析或知识点为空"))
        if it.get("grade") not in GRADES:
            bad.append((i, it.get("stem", "")[:24], "学段取值非法：%s" % it.get("grade")))
    note(not bad, "字段/选项/下标校验（问题 %d 处%s）" % (len(bad), "：" + str(bad[:4]) if bad else ""))

    # 2. 答案位置分布
    dist = {0: 0, 1: 0, 2: 0, 3: 0}
    for it in items:
        if isinstance(it.get("answer"), int) and 0 <= it["answer"] <= 3:
            dist[it["answer"]] += 1
    top = max(dist.values()) / max(1, len(items))
    note(top <= 0.40, "正确答案分布不坍缩：%s（最高占比 %.0f%%）" % (dist, top * 100))

    # 3. 题干不跨学段重复
    by_stem = {}
    for it in items:
        by_stem.setdefault(it["stem"], set()).add(it["grade"])
    cross = {s: g for s, g in by_stem.items() if len(g) > 1}
    note(not cross, "题干不跨学段重复（跨学段重复 %d 处%s）"
         % (len(cross), "：" + str(list(cross.items())[:2]) if cross else ""))

    # 4. 每学段每主题题量
    counts = {}
    for it in items:
        counts[(it["theme"], it["grade"])] = counts.get((it["theme"], it["grade"]), 0) + 1
    themes = sorted(set(it["theme"] for it in items))
    thin = []
    print("\n题量分布：")
    print("  %-6s %-12s %-12s %-12s" % ("主题", "小学低年级", "小学高年级", "初中"))
    for t in themes:
        row = [counts.get((t, g), 0) for g in GRADES]
        print("  %-6s %-14s %-14s %-14s" % (t, row[0], row[1], row[2]))
        for g, n in zip(GRADES, row):
            if n < MIN_PER_THEME_GRADE:
                thin.append("%s/%s 只有 %d 题" % (t, GRADE_CN[g], n))
    note(not thin, "各学段各主题题量充足（每格≥%d；不足：%s）" % (MIN_PER_THEME_GRADE, thin or "无"))

    # 5. 长度上限
    over = []
    for it in items:
        stem_max, opt_max = LIMITS[it["grade"]]
        if len(it["stem"]) > stem_max:
            over.append("题干超长(%s)：%s" % (GRADE_CN[it["grade"]], it["stem"][:20]))
        for o in it["options"]:
            if len(o) > opt_max:
                over.append("选项超长(%s)：%s" % (GRADE_CN[it["grade"]], o[:16]))
                break
    note(not over, "题干/选项长度符合学段上限（超限 %d 处%s）"
         % (len(over), "：" + str(over[:3]) if over else ""))

    # 6. 答案自洽性粗检：解析里点名的选项应当就是被选中的那一个
    mismatch = []
    for it in items:
        ans_text = it["options"][it["answer"]]
        an = it.get("analysis", "")
        # 只在解析里出现「是/为/叫/称为 X」这种明确指认时才比对
        for other in it["options"]:
            if other == ans_text or len(other) < 2:
                continue
            for pat in ("是%s" % other, "为%s" % other, "叫%s" % other, "即%s" % other,
                        "称为%s" % other, "叫做%s" % other):
                if pat in an:
                    mismatch.append("%s → 解析说「%s」，但标答是「%s」"
                                    % (it["stem"][:18], other, ans_text))
                    break
            else:
                continue
            break
    if mismatch:
        warn("答案自洽性：%d 处需要人工复核" % len(mismatch))
        for m in mismatch[:8]:
            print("        " + m)
    else:
        print("[OK  ] 答案自洽性粗检：未发现「解析指向的选项与标答不一致」")

    print("\n" + "=" * 64)
    print("未通过：%d 项，注意：%d 项" % (len(problems), len(warns)))
    for p in problems:
        print("  - " + p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
