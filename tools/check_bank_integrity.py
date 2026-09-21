# -*- coding: utf-8 -*-
"""题库完整性与学段分离自检（独立复核，不依赖子任务的自检脚本）。

检查项：
1. 每份 bank_part_*.json 都能解析、字段齐全、每题 4 个不重复选项、answer 下标合法；
2. **正确答案分布不坍缩**（任一位置占比不得过高，否则「全选 A」就能高分）；
3. **题干不跨学段重复**：同一道题不能既是低年级又是初中题，否则分级形同虚设；
4. 各学段题量充足（每个学段每主题至少 6 题，保证一轮闯关不重题）；
5. 题干/选项长度符合该学段上限（按**显示宽度**算：一个汉字算 2，一个西文字符算 1。
   直接数字符个数会让英文题永远超标，那是尺子不对）；
6. **答案自洽性**，分两档：
   (a) 解析里出现「答案是 X」「第 N 笔是 X」这类**明确指认**，而 X 不是标答 → 直接不通过；
   (b) 解析提到某个非标答选项（通常是解释它为什么不对）→ 只提示人工复核，
       并跳过「不是 X」「并非 X」这类否定说法，否则噪音大到没人看。

第 6(a) 档是踩坑之后加的：语文题「"日"字的第二笔是什么？」里，解析写的是
「笔顺是竖、横折、横、横，第二笔是横折」，但 answer 指到了「竖」。旧版把这种
情况混在"需要人工复核"里，很容易被忽略过去。

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
# 与 grades.py 保持一致：题干/选项长度上限（单位是"显示宽度"，一个汉字 = 2）
LIMITS = {"primary_low": (25, 6), "primary_high": (40, 10), "junior": (60, 16)}
MIN_PER_THEME_GRADE = 6

problems = []
warns = []


def display_width(text):
    """显示宽度：CJK 与全角标点算 2，其余算 1。"""
    w = 0
    for ch in text or "":
        code = ord(ch)
        if (0x1100 <= code <= 0x115F or 0x2E80 <= code <= 0xA4CF
                or 0xAC00 <= code <= 0xD7A3 or 0xF900 <= code <= 0xFAFF
                or 0xFE30 <= code <= 0xFE6F or 0xFF00 <= code <= 0xFF60
                or 0xFFE0 <= code <= 0xFFE6 or 0x20000 <= code <= 0x3FFFD):
            w += 2
        else:
            w += 1
    return w


def note(ok, msg):
    print(("[OK  ] " if ok else "[FAIL] ") + msg)
    if not ok:
        problems.append(msg)


def bad(msg):
    print("[FAIL] " + msg)
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
    # 按**显示宽度**算，不按字符个数：一个汉字占两个西文字符的宽度，英文选项
    # （例如 "Good night!"，11 个字符）在屏幕上的宽度和 5 个汉字差不多。
    # 早期版本直接数 len()，结果英文题永远超标——那是尺子不对，不是题目不对。
    over = []
    for it in items:
        stem_max, opt_max = LIMITS[it["grade"]]
        if display_width(it["stem"]) > stem_max * 2:
            over.append("题干超长(%s)：%s" % (GRADE_CN[it["grade"]], it["stem"][:20]))
        for o in it["options"]:
            if display_width(o) > opt_max * 2:
                over.append("选项超长(%s)：%s" % (GRADE_CN[it["grade"]], o[:20]))
                break
    note(not over, "题干/选项长度符合学段上限（按显示宽度算；超限 %d 处%s）"
         % (len(over), "：" + str(over[:3]) if over else ""))

    # 6. 答案自洽性。
    #
    # 分两档，因为它们的确信度完全不同：
    #
    # (a) 硬性：解析里出现了**明确指认答案**的句式（「答案是X」「正确答案是X」
    #     「应选X」「第N笔是X」）。这类句子里的 X 就是解析认定的答案，
    #     一旦 X 不是标答选项，那就是题错了 → 直接不通过。
    #     这一档是为了抓住一个真实发生过的 bug：「日」字第二笔那题，
    #     解析写「竖、横折、横、横，第二笔是横折」，但 answer 指到了「竖」。
    #     旧版把它混在"需要人工复核"里，很容易被忽略过去。
    #
    # (b) 软性：解析里提到某个非标答选项，可能是「在解释它为什么不对」，
    #     也可能是在指认答案。这一档只提示人工复核。
    #     必须做**否定词判断**，否则「不是非生物成分」「并不是只能打电话」
    #     会被误当成"解析说答案是非生物成分"，噪音大到没人愿意看。
    hard = []
    soft = []
    for it in items:
        ans_text = it["options"][it["answer"]]
        an = it.get("analysis", "")
        for other in it["options"]:
            if other == ans_text or len(other) < 2:
                continue
            # (a) 明确指认句式
            for shape in ("答案是%s", "正确答案是%s", "答案为%s", "应选%s", "应该选%s",
                          "笔是%s", "笔为%s", "故选%s"):
                idx = an.find(shape % other)
                if idx >= 0:
                    hard.append("%s → 解析明确写「%s」，但标答是「%s」"
                                % (it["stem"][:18], shape % other, ans_text))
                    break
            # (b) 松散指认，跳过被否定的说法
            for pat in ("是%s" % other, "为%s" % other, "叫%s" % other, "即%s" % other,
                        "称为%s" % other, "叫做%s" % other):
                idx = an.find(pat)
                while idx >= 0:
                    prev = an[max(0, idx - 1)]
                    if prev not in "不非没未无别":
                        soft.append("%s → 解析提到「%s」，标答是「%s」"
                                    % (it["stem"][:18], other, ans_text))
                        break
                    idx = an.find(pat, idx + 1)
                else:
                    continue
                break

    if hard:
        bad("答案自洽性：解析明确指认的答案与标答不一致（%d 处）—— 这是题的错，必须改"
            % len(hard))
        for m in hard[:8]:
            print("        " + m)
    else:
        print("[OK  ] 答案自洽性：解析没有出现「明确指认某选项为答案却与标答不符」")

    if soft:
        warn("答案自洽性：%d 处解析提到了非标答选项（多为在解释它为什么不对），供人工复核"
             % len(soft))
        for m in soft[:6]:
            print("        " + m)
    else:
        print("[OK  ] 答案自洽性：解析未提及任何非标答选项")

    print("\n" + "=" * 64)
    print("未通过：%d 项，注意：%d 项" % (len(problems), len(warns)))
    for p in problems:
        print("  - " + p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
