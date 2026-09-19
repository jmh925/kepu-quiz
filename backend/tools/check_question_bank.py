# -*- coding: utf-8 -*-
"""题库自检工具：扫描 backend/app/bank_part_*.json 并校验分级题库的硬性规则。

用法（在 backend 目录下）：
    python tools/check_question_bank.py

校验项：
  1. 每个文件是合法 JSON，顶层为数组；
  2. 每题字段齐全非空：theme/grade/type/stem/options/answer/analysis/knowledge_point；
  3. theme 属于 天文/地理/生物/物理/化学/科技，grade 属于三个学段，type 为 single；
  4. 每题恰好 4 个互不相同的选项，answer 是 0 起且落在范围内的整数；
  5. 学段越级检查：题干与选项的字数不超过该学段上限；
  6. 题干精确去重（跨文件）；
  7. 同一主题内 knowledge_point 不重复；
  8. 打印「主题 × 学段」题量分布表、答案下标分布、各学段最长题干/选项。
"""
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "app")

THEMES = ("天文", "地理", "生物", "物理", "化学", "科技")
GRADES = ("primary_low", "primary_high", "junior")
# 学段 -> (题干字数上限, 选项字数上限)
GRADE_LIMITS = {"primary_low": (25, 6), "primary_high": (40, 10), "junior": (60, 16)}
GRADE_CN = {"primary_low": "小学低年级", "primary_high": "小学高年级", "junior": "初中"}
FIELDS = ("theme", "grade", "type", "stem", "options", "answer", "analysis", "knowledge_point")


def main(argv=None):
    """argv 里给出文件名时只检查这些文件，否则检查全部 bank_part_*.json。"""
    errors = []
    items = []          # (来源文件, 题目)
    wanted = [os.path.basename(a) for a in (argv or sys.argv[1:])]
    files = sorted(f for f in os.listdir(APP)
                   if f.startswith("bank_part_") and f.endswith(".json"))
    if wanted:
        missing = [w for w in wanted if w not in files]
        for m in missing:
            errors.append("指定的文件不存在: %s" % m)
        files = [f for f in files if f in wanted]
    if not files:
        print("找不到 bank_part_*.json")
        return 1

    for name in files:
        with open(os.path.join(APP, name), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            errors.append("%s 顶层不是数组" % name)
            continue
        for q in data:
            items.append((name, q))

    by_theme = Counter()
    by_tg = Counter()          # (theme, grade) -> n
    by_grade = Counter()
    stems = Counter()
    kp_all = {}
    max_len = {g: {"stem": 0, "option": 0} for g in GRADES}

    for idx, (src, q) in enumerate(items, 1):
        tag = "%s#%d" % (src, idx)
        if not isinstance(q, dict):
            errors.append("%s 不是对象" % tag)
            continue
        for f in FIELDS:
            if f not in q or (isinstance(q[f], str) and not q[f].strip()):
                errors.append("%s 缺少字段或字段为空: %s" % (tag, f))
        theme, grade = q.get("theme"), q.get("grade")
        if theme not in THEMES:
            errors.append("%s theme 非法: %r" % (tag, theme))
        if grade not in GRADES:
            errors.append("%s grade 非法: %r" % (tag, grade))
        if q.get("type") != "single":
            errors.append("%s type 必须为 single" % tag)

        opts = q.get("options")
        if not isinstance(opts, list) or len(opts) != 4:
            errors.append("%s 选项数不为 4: %r" % (tag, opts))
        else:
            if len(set(opts)) != 4:
                errors.append("%s 选项重复: %r" % (tag, opts))
            ans = q.get("answer")
            if isinstance(ans, bool) or not isinstance(ans, int) or not 0 <= ans < 4:
                errors.append("%s answer 下标非法: %r" % (tag, ans))
            elif not isinstance(opts[ans], str) or not opts[ans].strip():
                errors.append("%s 正确答案文本为空: %r" % (tag, opts[ans]))

        stem = q.get("stem") if isinstance(q.get("stem"), str) else ""
        stems[stem] += 1
        if stems[stem] > 1:
            errors.append("%s 题干重复: %s" % (tag, stem))

        if theme in THEMES and grade in GRADES:
            by_theme[theme] += 1
            by_grade[grade] += 1
            by_tg[(theme, grade)] += 1
            kp_all.setdefault(theme, []).append(q.get("knowledge_point"))
            stem_max, opt_max = GRADE_LIMITS[grade]
            if len(stem) > stem_max:
                errors.append("%s(%s) 题干 %d 字 > 上限 %d 字: %s"
                              % (tag, grade, len(stem), stem_max, stem))
            max_len[grade]["stem"] = max(max_len[grade]["stem"], len(stem))
            for o in (opts if isinstance(opts, list) else []):
                o = o if isinstance(o, str) else str(o)
                if len(o) > opt_max:
                    errors.append("%s(%s) 选项 %d 字 > 上限 %d 字: %s"
                                  % (tag, grade, len(o), opt_max, o))
                max_len[grade]["option"] = max(max_len[grade]["option"], len(o))

    for theme, kps in kp_all.items():
        for kp, c in Counter(kps).items():
            if c > 1:
                errors.append("主题 %s 内知识点重复: %s x%d" % (theme, kp, c))

    # ---------------- 报告 ----------------
    print("=" * 72)
    print("题库文件:", ", ".join(files))
    print("总题量  : %d" % len(items))
    print("-" * 72)
    header = "%-6s" % "主题" + "".join("%-16s" % GRADE_CN[g] for g in GRADES) + "合计"
    print(header)
    for t in THEMES:
        if by_theme[t] == 0:
            continue
        row = [by_tg[(t, g)] for g in GRADES]
        print("%-6s" % t + "".join("%-16d" % n for n in row) + str(sum(row)))
    print("%-6s" % "合计" + "".join("%-16d" % by_grade[g] for g in GRADES) + str(len(items)))
    print("-" * 72)
    print("答案下标分布:", dict(sorted(Counter(q["answer"] for _, q in items
                                          if isinstance(q.get("answer"), int)).items())))
    print("题干去重    : 唯一 stem %d / 总题 %d" % (len(stems), len(items)))
    for g in GRADES:
        print("  %-13s 题干上限 %2d 字/实测最长 %2d 字；选项上限 %2d 字/实测最长 %2d 字"
              % (g, GRADE_LIMITS[g][0], max_len[g]["stem"],
                 GRADE_LIMITS[g][1], max_len[g]["option"]))
    print("-" * 72)
    if errors:
        print("校验未通过，共 %d 个问题：" % len(errors))
        for e in errors:
            print("  [X] " + e)
        print("=" * 72)
        return 1
    print("校验通过：JSON 合法、字段非空、answer 下标合法、每题 4 个不重复选项、")
    print("          题干无完全重复、同主题内知识点无重复、题干与选项长度全部符合学段上限。")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
