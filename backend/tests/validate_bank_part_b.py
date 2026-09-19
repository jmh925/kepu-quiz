# -*- coding: utf-8 -*-
"""校验 bank_part_b.json 是否满足出题规格（纯标准库，可直接运行）。

运行：python backend/tests/validate_bank_part_b.py
"""
import json
import os
import sys
from collections import Counter, defaultdict

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "bank_part_b.json")

THEMES = ["物理", "化学", "科技"]
GRADES = ["primary_low", "primary_high", "junior"]
STEM_MAX = {"primary_low": 25, "primary_high": 40, "junior": 60}
OPT_MAX = {"primary_low": 6, "primary_high": 10, "junior": 16}
GRADE_LABEL = {"primary_low": "小学低年级(1-3)", "primary_high": "小学高年级(4-6)", "junior": "初中(7-9)"}

errors = []
notes = []

# ---------- 1. JSON 可解析 ----------
with open(PATH, "rb") as f:
    raw = f.read()
try:
    raw.decode("utf-8")
    notes.append("UTF-8 解码成功（含 BOM 检查：%s）" % ("有 BOM" if raw[:3] == b"\xef\xbb\xbf" else "无 BOM"))
except UnicodeDecodeError as e:
    errors.append("文件不是合法 UTF-8: %s" % e)
data = json.loads(raw.decode("utf-8-sig"))
print("[1] JSON 解析: 成功，顶层类型 = %s，共 %d 条记录" % (type(data).__name__, len(data)))
for n in notes:
    print("    " + n)

# ---------- 2. 题量 ----------
print("[2] 题量校验")
print("    总数 = %d（要求 75）%s" % (len(data), "OK" if len(data) == 75 else "FAIL"))
if len(data) != 75:
    errors.append("总数 %d != 75" % len(data))

grid = defaultdict(int)
for q in data:
    grid[(q.get("theme"), q.get("grade"))] += 1

for t in THEMES:
    n = sum(grid[(t, g)] for g in GRADES)
    print("    %s 主题合计 = %d（要求 25）%s" % (t, n, "OK" if n == 25 else "FAIL"))
    if n != 25:
        errors.append("%s 主题合计 %d != 25" % (t, n))
    for g in GRADES:
        c = grid[(t, g)]
        ok = 8 <= c <= 9
        print("        %-13s %s = %d（要求 8~9）%s" % (g, GRADE_LABEL[g], c, "OK" if ok else "FAIL"))
        if not ok:
            errors.append("%s/%s 题量 %d 不在 8~9" % (t, g, c))

extra_themes = sorted(set(q.get("theme") for q in data) - set(THEMES))
extra_grades = sorted(set(q.get("grade") for q in data) - set(GRADES))
if extra_themes or extra_grades:
    errors.append("出现非法 theme/grade: %s %s" % (extra_themes, extra_grades))
print("    非法 theme/grade: %s" % (extra_themes + extra_grades or "无"))
print("    实际分布 = %s" % dict(sorted(grid.items(), key=lambda kv: (THEMES.index(kv[0][0]), GRADES.index(kv[0][1])))))

# ---------- 3. 字段与选项 ----------
print("[3] 字段/选项校验（answer 下标、options 恰好 4 个、字段非空）")
REQUIRED = ["theme", "grade", "type", "stem", "options", "answer", "analysis", "knowledge_point"]
bad_field = 0
for i, q in enumerate(data):
    tag = "#%d %s/%s" % (i, q.get("theme"), q.get("grade"))
    for k in REQUIRED:
        if k not in q or q[k] in (None, "", [], {}):
            errors.append("%s 字段缺失或为空: %s" % (tag, k))
            bad_field += 1
    opts = q.get("options")
    if not isinstance(opts, list) or len(opts) != 4:
        errors.append("%s options 不是恰好 4 个" % tag)
        bad_field += 1
    else:
        if any((not isinstance(o, str)) or o.strip() == "" for o in opts):
            errors.append("%s options 存在空选项" % tag)
            bad_field += 1
        if len(set(opts)) != 4:
            errors.append("%s options 存在重复项" % tag)
            bad_field += 1
    a = q.get("answer")
    if not isinstance(a, int) or isinstance(a, bool) or not (0 <= a < 4):
        errors.append("%s answer=%r 下标非法" % (tag, a))
        bad_field += 1
    if q.get("type") != "single":
        errors.append("%s type 必须为 single" % tag)
        bad_field += 1
print("    逐题巡检 75 题，问题数 = %d %s" % (bad_field, "OK" if bad_field == 0 else "FAIL"))
ans_dist = Counter(q.get("answer") for q in data)
print("    正确答案下标分布 = %s" % dict(sorted(ans_dist.items())))
# 附加质量项：正确答案不能总落在同一个位置，否则学生可以靠“全选 A”蒙分
for idx in range(4):
    share = ans_dist.get(idx, 0) / len(data)
    if share > 0.4:
        errors.append("正确答案有 %.0f%% 落在下标 %d，位置分布失衡" % (share * 100, idx))
print("    位置分布失衡检查（任一位置占比超过四成即失败）: %s" % (
    "OK" if max(ans_dist.get(i, 0) for i in range(4)) / len(data) <= 0.4 else "FAIL"))

# ---------- 4. 题干去重 ----------
print("[4] 题干去重")
stems = [q.get("stem", "") for q in data]
dups = [s for s, c in Counter(stems).items() if c > 1]
print("    全局完全相同的题干: %s" % (dups if dups else "无"))
if dups:
    errors.append("重复 stem: %s" % dups)
for t in THEMES:
    ts = [q.get("stem") for q in data if q.get("theme") == t]
    td = [s for s, c in Counter(ts).items() if c > 1]
    print("    %s 主题内重复: %s" % (t, td if td else "无"))
    if td:
        errors.append("%s 主题内重复 stem" % t)

# ---------- 5. 长度上限 ----------
print("[5] 学段长度上限校验（题干 / 每个选项）")
len_bad = 0
worst = defaultdict(int)
for i, q in enumerate(data):
    g = q.get("grade")
    tag = "#%d %s/%s" % (i, q.get("theme"), g)
    smax, omax = STEM_MAX.get(g), OPT_MAX.get(g)
    s = q.get("stem", "")
    worst[(g, "stem")] = max(worst[(g, "stem")], len(s))
    if len(s) > smax:
        errors.append("%s 题干 %d 字 > %d: %s" % (tag, len(s), smax, s))
        len_bad += 1
    for o in q.get("options", []):
        worst[(g, "opt")] = max(worst[(g, "opt")], len(o))
        if len(o) > omax:
            errors.append("%s 选项 %d 字 > %d: %s" % (tag, len(o), omax, o))
            len_bad += 1
for g in GRADES:
    print("    %-13s 题干上限 %2d 字（实际最长 %2d）；选项上限 %2d 字（实际最长 %2d）  %s" % (
        g, STEM_MAX[g], worst[(g, "stem")], OPT_MAX[g], worst[(g, "opt")],
        "OK" if worst[(g, "stem")] <= STEM_MAX[g] and worst[(g, "opt")] <= OPT_MAX[g] else "FAIL"))
print("    超限条目数 = %d %s" % (len_bad, "OK" if len_bad == 0 else "FAIL"))

# ---------- 6. 知识点不重复（同主题内） ----------
print("[6] 同一主题内知识点去重")
kp_bad = 0
for t in THEMES:
    kps = [q.get("knowledge_point") for q in data if q.get("theme") == t]
    d = [k for k, c in Counter(kps).items() if c > 1]
    print("    %s 知识点 %d 个，重复: %s" % (t, len(kps), d if d else "无"))
    if d:
        errors.append("%s 主题内知识点重复: %s" % (t, d))
        kp_bad += 1

# ---------- 7. 未成年人安全用语快检 ----------
print("[7] 安全用语快检（暴力/恐怖/低俗/危险操作关键词）")
BANNED = ["自杀", "血腥", "暴力", "恐怖", "死掉", "毒品", "赌博", "自己配药", "玩火", "爆炸实验"]
hits = []
for i, q in enumerate(data):
    blob = q.get("stem", "") + "".join(q.get("options", [])) + q.get("analysis", "")
    for w in BANNED:
        if w in blob:
            hits.append((i, w))
print("    命中: %s %s" % (hits if hits else "无", "OK" if not hits else "FAIL"))
if hits:
    errors.append("安全关键词命中: %s" % hits)

# ---------- 汇总 ----------
print("-" * 62)
if errors:
    print("校验结果: 未通过，共 %d 个问题" % len(errors))
    for e in errors:
        print("  - " + e)
    sys.exit(1)
print("校验结果: 全部通过（75 题 / 3 主题 / 每主题每学段 8~9 题 / 字段与长度合法 / 题干无重复）")
sys.exit(0)
