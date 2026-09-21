# -*- coding: utf-8 -*-
"""生成/汇总 bank_part_c.json（基础课程题库：语文 / 数学 / 英语，各 25 题）。

分工
----
* 数学 25 题：本脚本用多种题型模板**计算生成**。题干里的数字随机取，正确答案
  由 Python 算出来，干扰项由「正确答案的邻居」或「这类题最容易算错的结果」生成，
  并在生成时断言四个选项互不相同。每题同时产出一条 `spec`（算式 + 解析类型），
  交给 tools/check_basic_bank.py 用独立实现的运算器重算比对。
* 语文 / 英语 各 25 题：人工编写，作为常量表写在下方 LANG_ITEMS / ENG_ITEMS 里。
* 三个主题的正确答案下标都在最后统一重排，保证每个主题内 0~3 各出现 5~8 次。

用法
----
    python tools/gen_math_bank.py                       # 打印 75 题
    python tools/gen_math_bank.py --write                # 写出 backend/app/bank_part_c.json
    python tools/gen_math_bank.py --spec x.json          # 顺便导出数学题校验用的 spec
"""
import argparse
import json
import os
import random
import sys
from collections import Counter
from fractions import Fraction

SEED = 20240517
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK_PATH = os.path.join(ROOT, "backend", "app", "bank_part_c.json")
GRADE_ORDER = ["primary_low", "primary_high", "junior"]
THEME_ORDER = ["语文", "数学", "英语"]
FIELDS = ["theme", "grade", "type", "stem", "options", "answer", "analysis", "knowledge_point"]

# 每个学段需要的题量
GRADE_PLAN = [("primary_low", 8), ("primary_high", 9), ("junior", 8)]
# 每个主题内正确答案下标的配额（合计 25，每个下标都在 5~8 之内）
ANSWER_QUOTA = {
    "语文": [7, 6, 6, 6],
    "数学": [6, 6, 6, 7],
    "英语": [6, 7, 6, 6],
}


# ==========================================================================
# 通用小工具
# ==========================================================================
def opt(n):
    """数字 / 分数 -> 选项文本。"""
    if isinstance(n, Fraction):
        n = n.numerator / n.denominator
    if isinstance(n, float):
        if abs(n - round(n)) < 1e-9:
            return str(int(round(n)))
        return ("%.4f" % n).rstrip("0").rstrip(".")
    return str(n)


def clean_distractors(correct, distractors):
    """剔除与正确答案相同的、非正数的、重复的干扰项。"""
    correct_s = opt(correct)
    out = []
    for d in distractors:
        ds = opt(d)
        if ds == correct_s or ds in out:
            continue
        if ds.startswith("-") or ds in ("0",):
            continue
        out.append(ds)
    return out


def fill_options(correct, distractors):
    """返回正确的选项列表（未打乱），正确答案固定在 options[0]。

    保证：恰好 4 个选项、互不相同、不含答案本身、不含负数。
    """
    correct_s = opt(correct)
    opts = [correct_s] + clean_distractors(correct, distractors)[:3]
    step = 1
    guard = 0
    base = float(correct) if isinstance(correct, Fraction) else correct
    while len(opts) < 4:
        for cand in (opt(base + step), opt(base - step), opt(base + 2 * step)):
            if cand != correct_s and cand not in opts and not cand.startswith("-") and cand != "0":
                opts.append(cand)
            if len(opts) == 4:
                break
        step += 1
        guard += 1
        if guard > 40:
            raise AssertionError("无法为 %s 生成足够选项" % correct_s)
    if len(set(opts)) != 4:
        raise AssertionError("选项重复：%s" % opts)
    return opts


def neighbor_distractors(v, spread=3):
    """正确答案的邻居。"""
    out = []
    for delta in range(1, spread + 1):
        out.append(v + delta)
        if v - delta > 0:
            out.append(v - delta)
    return out


def build(theme, grade, stem, options, analysis, kp, spec=None, correct=None):
    """构造一道题。correct 记录「正确选项的文本」，最终由 assign_answers() 统一重排下标。

    约定：如果没显式给 correct，就认为 options[0] 是正确选项（fill_options() 的产物）。
    """
    q = {"theme": theme, "grade": grade, "type": "single", "stem": stem,
         "options": list(options), "answer": 0, "analysis": analysis,
         "knowledge_point": kp, "_spec": spec,
         "_correct": correct if correct is not None else options[0]}
    assert q["_correct"] in q["options"], (stem, q["_correct"], q["options"])
    return q


def poly1(k, b, var="x"):
    """一次式文本：3x + 5 / x - 4 / 2x"""
    left = "%d%s" % (k, var) if k != 1 else var
    if b == 0:
        return left
    return "%s %s %d" % (left, "+" if b > 0 else "-", abs(b))


# ==========================================================================
# 数学 · 小学低年级（1~3 年级）：20 以内加减、100 以内加减、表内乘法、比大小
# ==========================================================================
def t_add20(rng):
    a = rng.randint(3, 9)
    b = rng.randint(2, 20 - a)
    c = a + b
    stem = "%d + %d = ？" % (a, b)
    ana = ("%d 加 %d，就是把 %d 和 %d 合起来，一共是 %d，所以选 %d。"
           "两个数合在一起要用加法算。" % (a, b, a, b, c, c))
    return build("数学", "primary_low", stem, fill_options(c, neighbor_distractors(c)), ana,
                 "20以内加法", spec={"kind": "arith", "expr": "%d+%d" % (a, b), "unit": ""})


def t_sub20(rng):
    a = rng.randint(11, 20)
    b = rng.randint(2, a - 3)
    c = a - b
    stem = "%d - %d = ？" % (a, b)
    ana = ("%d 减去 %d，就是先从 %d 个里拿走 %d 个，剩下 %d 个，所以选 %d。"
           "从总数里去掉一部分，要用减法。" % (a, b, a, b, c, c))
    return build("数学", "primary_low", stem, fill_options(c, neighbor_distractors(c)), ana,
                 "20以内减法", spec={"kind": "arith", "expr": "%d-%d" % (a, b), "unit": ""})


def t_missing_add(rng):
    a = rng.randint(3, 9)
    total = rng.randint(a + 4, 18)
    c = total - a
    stem = "%d + （ ）= %d，括号里填几？" % (a, total)
    ana = ("想 %d 加上几等于 %d，用 %d 减 %d 得 %d，所以括号里填 %d。"
           "求一个加数，可以用和减掉另一个加数。" % (a, total, total, a, c, c))
    return build("数学", "primary_low", stem, fill_options(c, neighbor_distractors(c)), ana,
                 "求未知加数", spec={"kind": "arith", "expr": "%d-%d" % (total, a), "unit": ""})


def t_add100(rng):
    a = rng.randrange(10, 60, 10)
    b = 0
    for _ in range(200):
        candidate = rng.randint(12, 39)
        candidate -= candidate % 10
        if candidate >= 10 and (a % 10) + (candidate % 10) < 10 and candidate != a:
            b = candidate
            break
    if b == 0:
        a, b = 30, 20
    c = a + b
    stem = "%d + %d = ？" % (a, b)
    ana = ("把 %d 看成 %d 个十，把 %d 看成 %d 个十，%d 个十加 %d 个十是 %d 个十，"
           "也就是 %d，所以选 %d。整十数相加，按「几个十」来数又快又稳。"
           % (a, a // 10, b, b // 10, a // 10, b // 10, c // 10, c, c))
    return build("数学", "primary_low", stem, fill_options(c, neighbor_distractors(c, 4)), ana,
                 "100以内加法", spec={"kind": "arith", "expr": "%d+%d" % (a, b), "unit": ""})


def t_sub100(rng):
    a = rng.randint(35, 99)
    b = 0
    for _ in range(200):
        candidate = rng.randint(12, a - 13)
        if (a % 10) >= (candidate % 10):
            b = candidate
            break
    if b == 0:
        a, b = 78, 45
    c = a - b
    stem = "%d - %d = ？" % (a, b)
    ana = ("个位 %d 减 %d 得 %d，十位 %d 减 %d 得 %d，合起来是 %d，所以选 %d。"
           "按数位一位一位地减，答案就稳稳的。"
           % (a % 10, b % 10, a % 10 - b % 10, a // 10, b // 10, a // 10 - b // 10, c, c))
    return build("数学", "primary_low", stem, fill_options(c, neighbor_distractors(c, 4)), ana,
                 "100以内减法", spec={"kind": "arith", "expr": "%d-%d" % (a, b), "unit": ""})


def t_mul_table(rng):
    a = rng.randint(3, 9)
    b = 0
    for _ in range(50):
        candidate = rng.randint(3, 9)
        if a * candidate >= 12:
            b = candidate
            break
    if b == 0:
        a, b = 4, 5
    c = a * b
    stem = "%d × %d = ？" % (a, b)
    small, big = min(a, b), max(a, b)
    ana = ("乘法口诀里「%d%d%d」说的就是这道题：%d 个 %d 相加等于 %d，所以选 %d。"
           "记住口诀，算乘法就会又快又准。"
           % (small, big, c, big, small, c, c))
    return build("数学", "primary_low", stem,
                 fill_options(c, [c + a, c - a, c + b, c - b, c + 1, c - 1, c + 10]), ana,
                 "表内乘法", spec={"kind": "arith", "expr": "%d*%d" % (a, b), "unit": ""})


def t_mul_missing(rng):
    a = rng.randint(3, 9)
    b = rng.randint(3, 9)
    c = a * b
    stem = "%d × （ ）= %d，括号里填几？" % (a, c)
    ana = ("想几乘 %d 等于 %d：%d 除以 %d 得 %d，所以括号里填 %d。"
           "求另一个乘数，用积除以已知的乘数就行。" % (a, c, c, a, b, b))
    return build("数学", "primary_low", stem,
                 fill_options(b, [b + 1, b - 1, b + 2, a, a + 1, b + 3]), ana,
                 "乘法口诀求乘数", spec={"kind": "arith", "expr": "%d/%d" % (c, a), "unit": ""})


def t_compare(rng):
    a = rng.randint(11, 48)
    b = rng.randint(51, 98)
    opts = ["%d 大" % a, "%d 大" % b, "一样大", "不能比"]
    rng.shuffle(opts)
    stem = "%d 和 %d，哪个数更大？" % (a, b)
    ana = ("比大小先看十位：%d 的十位是 %d，%d 的十位是 %d，十位大的数就更大，"
           "所以 %d 更大。" % (a, a // 10, b, b // 10, b))
    return build("数学", "primary_low", stem, opts, ana, "比较数的大小",
                 spec={"kind": "compare_big", "expr": "max(%d,%d)" % (a, b), "unit": ""},
                 correct="%d 大" % b)


def t_add100_carry(rng):
    a = rng.randint(15, 48)
    b = 0
    for _ in range(300):
        candidate = rng.randint(13, 49)
        if (a % 10) + (candidate % 10) >= 10 and a + candidate <= 99:
            b = candidate
            break
    if b == 0:
        a, b = 27, 45
    c = a + b
    stem = "%d + %d = ？" % (a, b)
    ana = ("先算个位：%d + %d = %d，写 %d 再进 1；十位 %d + %d + 1 = %d，"
           "合起来是 %d，所以选 %d。"
           % (a % 10, b % 10, a % 10 + b % 10, (a % 10 + b % 10) % 10,
              a // 10, b // 10, c // 10, c, c))
    return build("数学", "primary_low", stem, fill_options(c, neighbor_distractors(c, 4)), ana,
                 "进位加法", spec={"kind": "arith", "expr": "%d+%d" % (a, b), "unit": ""})


# ==========================================================================
# 数学 · 小学高年级（4~6 年级）：混合运算、分数小数、方程、面积周长、单位换算、百分数
# ==========================================================================
def t_mixed(rng):
    a = rng.randint(3, 9)
    b = rng.randint(6, 20)
    c = rng.randint(2, 6)
    d = rng.randint(2, 12)
    e = a * b + c - d
    stem = "%d × %d + %d - %d = ？" % (a, b, c, d)
    ana = ("先乘除后加减：%d × %d = %d，%d + %d = %d，%d - %d = %d，所以选 %d。"
           "要是先算 %d + %d = %d，再拿 %d 去乘 %d，结果 %d 就对不上了。"
           % (a, b, a * b, a * b, c, a * b + c, a * b + c, d, e, e,
              c, d, c + d, a, c + d, a * (c + d)))
    return build("数学", "primary_high", stem,
                 fill_options(e, [a * (b + c) - d, a * b + c + d, a * b - c - d, e + 10, e - 10]), ana,
                 "四则混合运算", spec={"kind": "arith", "expr": "%d*%d+%d-%d" % (a, b, c, d), "unit": ""})


def t_lineq_ph(rng):
    a = rng.randint(2, 9)
    x = rng.randint(2, 12)
    b = rng.randint(1, 20)
    c = a * x + b
    stem = "方程 %s = %d 中，x 是多少？" % (poly1(a, b), c)
    ana = ("先把 %d 移到右边：%dx = %d - %d = %d，再两边同时除以 %d，得 x = %d，"
           "所以选 %d。检验：%d × %d + %d = %d，正好相等。"
           % (b, a, c, b, c - b, a, x, x, a, x, b, c))
    return build("数学", "primary_high", stem,
                 fill_options(x, [x + 1, x + 2, b, a + b, x - 1, c]), ana,
                 "解简单方程", spec={"kind": "arith", "expr": "(%d-%d)/%d" % (c, b, a), "unit": ""})


def t_fraction_cmp(rng):
    d1, d2 = rng.sample([2, 3, 4, 5, 6, 8, 10], 2)
    n1 = rng.randint(1, d1 - 1)
    n2 = rng.randint(1, d2 - 1)
    while n1 * d2 == n2 * d1:
        n2 = rng.randint(1, d2 - 1)
    f1, f2 = Fraction(n1, d1), Fraction(n2, d2)
    if f1 > f2:
        big, small = "%d/%d" % (n1, d1), "%d/%d" % (n2, d2)
    else:
        big, small = "%d/%d" % (n2, d2), "%d/%d" % (n1, d1)
    opts = [big, small, "一样大", "不能比较"]
    rng.shuffle(opts)
    stem = "分数 %s 和 %s 比大小，哪个更大？" % (big, small)
    ana = ("把两个分数化成小数看：%s ≈ %.2f，%s ≈ %.2f，所以 %s 更大。"
           "分母不同的时候，化成小数或者通分再比最稳妥。"
           % (big, float(Fraction(big)), small, float(Fraction(small)), big))
    return build("数学", "primary_high", stem, opts, ana, "分数大小比较",
                 spec={"kind": "compare_frac", "expr": "max(%d/%d,%d/%d)" % (n1, d1, n2, d2), "unit": ""},
                 correct=big)


def t_decimal_frac(rng):
    num = rng.choice([5, 15, 25, 35, 45, 55, 65, 75, 85, 95])
    f = Fraction(num, 100)
    correct = "%d/%d" % (f.numerator, f.denominator)
    pct = "0.%02d" % num
    stem = "把小数 %s 化成最简分数，是多少？" % pct
    g = __import__("math").gcd(num, 100)
    ana = ("%s 表示百分之 %d，先写成 %d/100，再把分子分母同时除以 %d，"
           "就得到最简分数 %s，所以选 %s。" % (pct, num, num, g, correct, correct))
    return build("数学", "primary_high", stem,
                 fill_options(correct, ["%d/%d" % (num, 10), "%d/%d" % (f.numerator, f.denominator * 2),
                                        "%d/%d" % (f.numerator + 1, f.denominator), "%d/100" % num]), ana,
                 "小数化分数", spec={"kind": "frac_str", "expr": "%d/100" % num, "unit": ""})


def t_rect_area(rng):
    a = rng.randint(6, 15)
    b = 0
    for _ in range(100):
        candidate = rng.randint(4, 14)
        if candidate != a and a * candidate != 2 * (a + candidate):
            b = candidate
            break
    if b == 0:
        a, b = 8, 5
    s = a * b
    p = 2 * (a + b)
    stem = "长方形长 %d 厘米、宽 %d 厘米，面积是多少？" % (a, b)
    ana = ("长方形面积 = 长 × 宽 = %d × %d = %d 平方厘米，所以选 %d。"
           "%d 是它的周长（%d + %d 再乘 2），求面积不要用周长那个算法。"
           % (a, b, s, s, p, a, b))
    return build("数学", "primary_high", stem, fill_options(s, [p, a + b, s + a, s - b, a * b + a]), ana,
                 "长方形面积", spec={"kind": "arith", "expr": "%d*%d" % (a, b), "unit": "平方厘米"})


def t_unit_convert(rng):
    m = rng.randint(2, 9)
    cm = m * 100
    stem = "%d 米等于多少厘米？" % m
    ana = ("1 米 = 100 厘米，%d 米就是 %d 个 100 厘米，等于 %d 厘米，所以选 %d。"
           "米化厘米是乘 100，不是乘 10。" % (m, m, cm, cm))
    return build("数学", "primary_high", stem,
                 fill_options(cm, [m * 10, m * 1000, cm + 100, m * 10 + 10]), ana,
                 "长度单位换算", spec={"kind": "arith", "expr": "%d*100" % m, "unit": "厘米"})


def t_percent(rng):
    total = rng.choice([20, 25, 40, 50, 60, 80, 100, 120, 150, 200])
    p = rng.choice([10, 20, 25, 40, 50, 60, 75])
    c = Fraction(total * p, 100)
    stem = "%d 的 %d%% 是多少？" % (total, p)
    ana = ("求一个数的百分之几用乘法：%d × %d%% = %d × %d ÷ 100 = %s，所以选 %s。"
           % (total, p, total, p, opt(c), opt(c)))
    if opt(total - c) != opt(c):
        ana += "另外，剩下的部分是 %d - %s = %s，问的是「多少」而不是「剩下多少」，别选错。" % (
            total, opt(c), opt(total - c))
    return build("数学", "primary_high", stem,
                 fill_options(c, [total - c, c + p, c - p, total // 10, total // p if p else 1]), ana,
                 "百分数计算", spec={"kind": "arith", "expr": "%d*%d/100" % (total, p), "unit": ""})


def t_perimeter(rng):
    a = rng.randint(5, 20)
    b = 0
    for _ in range(100):
        candidate = rng.randint(3, 15)
        if candidate != a and a * candidate != 2 * (a + candidate):
            b = candidate
            break
    if b == 0:
        a, b = 9, 4
    p = 2 * (a + b)
    s = a * b
    stem = "长方形长 %d 米、宽 %d 米，周长是多少米？" % (a, b)
    ana = ("长方形周长 = （长 + 宽）× 2 = （%d + %d）× 2 = %d 米，所以选 %d。"
           "%d 是它的面积，单位是平方米；周长算的是一圈的长度。"
           % (a, b, p, p, s))
    return build("数学", "primary_high", stem,
                 fill_options(p, [a + b, s, p + 2, p - 2, 2 * a + b]), ana,
                 "长方形周长", spec={"kind": "arith", "expr": "2*(%d+%d)" % (a, b), "unit": "米"})


# ==========================================================================
# 数学 · 初中（7~9 年级）：一元一次方程、整式、因式分解、一元二次、几何、函数
# ==========================================================================
def t_lineq_j(rng):
    a = rng.randint(2, 9)
    x = rng.randint(2, 12)
    b = rng.randint(1, 15)
    c = a * x + b
    stem = "解一元一次方程：%s = %d，x 是多少？" % (poly1(a, b), c)
    ana = ("移项得 %dx = %d - %d = %d，两边同时除以 %d，x = %d，"
           "检验：%d × %d + %d = %d，等式成立，所以选 %d。"
           % (a, c, b, c - b, a, x, a, x, b, c, x))
    return build("数学", "junior", stem, fill_options(x, [x + 1, x + 2, c - b, a + b, b]), ana,
                 "一元一次方程", spec={"kind": "arith", "expr": "(%d-%d)/%d" % (c, b, a), "unit": ""})


def t_expand(rng):
    a = rng.randint(2, 9)
    b = rng.randint(2, 9)
    c = rng.randint(1, 9)
    while c == b:          # 避免题干出现 (2x + 5)(x + 5) 这类两个常数相同的写法，读起来容易混淆
        c = rng.randint(1, 9)
    correct = "%dx² + %dx + %d" % (a * b, a * c + b, b * c)
    stem = "把 (%s)(x + %d) 展开，结果是多少？" % (poly1(a, b), c)
    ana = ("用乘法分配律逐项相乘：%dx·x = %dx²，%dx·%d = %dx，%d·x = %dx，"
           "%d·%d = %d，合并同类项得 %s，所以选 %s。"
           % (a, a * b, a, c, a * c, b, b, b, c, b * c, correct, correct))
    return build("数学", "junior", stem,
                 fill_options(correct, ["%dx² + %d" % (a * b, a + c + b),
                                        "%dx + %d" % (a * b, a * c + b),
                                        "%dx² + %dx + %d" % (a * b, a * c + b * c, b * c),
                                        "%dx² + %dx + %d" % (a * b + a, a * c + b, b * c)]), ana,
                 "整式乘法", spec={"kind": "poly_expand", "a": a, "b": b, "c": c, "unit": ""})


def t_factor(rng):
    a = rng.randint(2, 9)
    b = rng.randint(2, 9)
    c = a + b
    d = a * b
    correct = "(x + %d)(x + %d)" % (a, b)
    stem = "把 x² + %dx + %d 分解因式，结果是多少？" % (c, d)
    ana = ("要找两个数，乘积是 %d、和是 %d，正好是 %d 和 %d，所以 x² + %dx + %d = %s。"
           "把括号展开就能验证回原式。" % (d, c, a, b, c, d, correct))
    return build("数学", "junior", stem,
                 fill_options(correct, ["(x + %d)(x + %d)" % (a, d), "(x - %d)(x - %d)" % (a, b),
                                        "(x + %d)(x + %d)" % (c, d),
                                        "(x + %d)(x + %d)" % (d, c)]), ana,
                 "因式分解", spec={"kind": "poly_factor", "a": a, "b": b, "unit": ""})


def t_quadratic(rng):
    r1 = rng.randint(1, 7)
    r2 = rng.randint(2, 8)
    while r2 == r1:
        r2 = rng.randint(2, 8)
    b = -(r1 + r2)
    c = r1 * r2
    big, small = max(r1, r2), min(r1, r2)
    correct = "x₁ = %d，x₂ = %d" % (big, small)
    stem = "方程 x² - %dx + %d = 0 的两根是多少？" % (-b, c)
    ana = ("因式分解：x² - %dx + %d = (x - %d)(x - %d)，所以 x = %d 或 x = %d。"
           "两根相加等于 %d、相乘等于 %d，和原方程正好对得上。"
           % (-b, c, big, small, big, small, big + small, c))
    return build("数学", "junior", stem,
                 fill_options(correct, ["x₁ = %d，x₂ = %d" % (-big, small),
                                        "x₁ = %d，x₂ = %d" % (big + 1, small),
                                        "x₁ = %d，x₂ = %d" % (big + 2, small + 1),
                                        "x₁ = %d，x₂ = %d" % (big, small + 7)]), ana,
                 "一元二次方程", spec={"kind": "quadratic", "b": b, "c": c, "unit": ""})


def t_triangle(rng):
    a = rng.randint(30, 80)
    b = 0
    for _ in range(300):
        candidate = rng.randint(30, 80)
        if 90 < a + candidate < 150:
            b = candidate
            break
    if b == 0:
        a, b = 55, 65
    c = 180 - a - b
    stem = "三角形两个内角是 %d° 和 %d°，第三个角是多少？" % (a, b)
    ana = ("三角形内角和是 180°，第三个角 = 180° - %d° - %d° = %d°，所以选 %d°。"
           "%d° 只是另外两个角的和，不是第三个角。" % (a, b, c, c, a + b))
    distractors = ["%d°" % (180 - a), "%d°" % (180 - b), "%d°" % (a + b), "%d°" % (360 - a - b)]
    rng.shuffle(distractors)
    return build("数学", "junior", stem, fill_options("%d°" % c, distractors), ana, "三角形内角和",
                 spec={"kind": "arith", "expr": "180-%d-%d" % (a, b), "unit": "度"})


def t_pythagoras(rng):
    a, b, c = rng.choice([(3, 4, 5), (6, 8, 10), (5, 12, 13), (9, 12, 15), (8, 15, 17)])
    stem = "直角三角形两条直角边是 %d 和 %d，斜边是多少？" % (a, b)
    ana = ("勾股定理：斜边² = %d² + %d² = %d + %d = %d，所以斜边 = %d。"
           "%d、%d、%d 是一组常用的勾股数，记住它能算得又快又准。"
           % (a, b, a * a, b * b, a * a + b * b, c, a, b, c))
    distractors = [a + b, c + 1, c - 1, c + 2, a * b]
    rng.shuffle(distractors)
    return build("数学", "junior", stem, fill_options(c, distractors), ana, "勾股定理",
                 spec={"kind": "arith", "expr": "sqrt(%d**2+%d**2)" % (a, b), "unit": ""})


def t_linear_func(rng):
    k = rng.choice([2, 3, 4, 5])
    b = rng.randint(-8, 8)
    x = rng.randint(-4, 6)
    y = k * x + b
    stem = "一次函数 y = %s，当 x = %d 时 y 等于多少？" % (poly1(k, b), x)
    ana = ("把 x = %d 代入 y = %s：y = %d × (%d) %s %d = %d，所以选 %d。"
           "代入的时候别忘了常数项 %d 也要一起算。"
           % (x, poly1(k, b), k, x, "+" if b >= 0 else "-", abs(b), y, y, b))
    return build("数学", "junior", stem,
                 fill_options(y, [k * x, y + k, k * x - b, y - 2, k * x + b + k]), ana,
                 "一次函数求值", spec={"kind": "arith", "expr": "%d*%d+%d" % (k, x, b), "unit": ""})


def t_sci_notation(rng):
    a = rng.randint(2, 9)
    n = rng.randint(3, 7)
    value = a * (10 ** n)
    correct = "%d × 10^%d" % (a, n)
    stem = "把 %d 用科学记数法表示，结果是多少？" % value
    ana = ("科学记数法写成 a × 10^n，其中 1 ≤ a < 10。%d 就是 %d 后面跟 %d 个 0，"
           "所以等于 %s，选它。" % (value, a, n, correct))
    return build("数学", "junior", stem,
                 fill_options(correct, ["%d × 10^%d" % (a, n + 1), "%d × 10^%d" % (a, n - 1),
                                        "%d × 10^%d" % (a * 10, n - 1),
                                        "%d × 10^%d" % (a, n + 2)]), ana,
                 "科学记数法", spec={"kind": "arith", "expr": "%d*10**%d" % (a, n), "unit": "",
                                     "expect_str": correct})


# 模板清单：(生成函数, 使用次数)。同一模板最多 2 次，避免同型题堆太多。
TEMPLATES = {
    "primary_low": [
        (t_add20, 1), (t_sub20, 1), (t_missing_add, 1), (t_add100, 1),
        (t_sub100, 1), (t_mul_table, 1), (t_mul_missing, 1), (t_add100_carry, 1),
    ],
    "primary_high": [
        (t_mixed, 2), (t_lineq_ph, 1), (t_fraction_cmp, 1), (t_decimal_frac, 1),
        (t_rect_area, 1), (t_perimeter, 1), (t_unit_convert, 1), (t_percent, 1),
    ],
    "junior": [
        (t_lineq_j, 1), (t_expand, 1), (t_factor, 1), (t_quadratic, 1),
        (t_triangle, 1), (t_pythagoras, 1), (t_linear_func, 1), (t_sci_notation, 1),
    ],
}


def generate_math():
    rng = random.Random(SEED)
    out = []
    for grade, need in GRADE_PLAN:
        plan = []
        for fn, times in TEMPLATES[grade]:
            plan.extend([fn] * times)
        if len(plan) != need:
            raise SystemExit("%s 模板槽位 %d 个，需要 %d 个" % (grade, len(plan), need))
        rng.shuffle(plan)
        out.extend(fn(rng) for fn in plan)
    stems = [q["stem"] for q in out]
    dup = [s for s, n in Counter(stems).items() if n > 1]
    if dup:
        raise SystemExit("数学题题干重复：%s" % dup)
    return out


# ==========================================================================
# 语文 25 题（人工编写：小学低 8 / 小学高 9 / 初中 8）
# ==========================================================================
def L(grade, stem, options, answer, analysis, kp):
    """构造一道语文题。answer 是手写答案在 options 里的下标，_correct 记录正确选项文本。"""
    q = build("语文", grade, stem, options, analysis, kp, spec=None, correct=options[answer])
    q["answer"] = answer
    return q


LANG_ITEMS = [
    # ---- 小学低年级 8 题 ----
    L("primary_low", "“爸”字的拼音怎么写？", ["bà", "pà", "bā", "dà"], 0,
      "“爸”读第四声 bà，声母是 b 不是 p。pà 的声母是 p，bā 是第一声，dà 是另一个字“大”的音。", "拼音"),
    L("primary_low", "“妈”的声母是哪一个？", ["b", "m", "n", "f"], 1,
      "“妈”读 mā，开头是双唇闭合发出的 m，所以声母是 m。b、n、f 分别对应“八、那、发”的开头。", "声母"),
    L("primary_low", "下面哪个是整体认读音节？", ["zhi", "ba", "mi", "tu"], 0,
      "整体认读音节要整个记住、不用拼，zhi 就是其中一个。ba、mi、tu 都能拆成声母加韵母拼出来。", "整体认读音节"),
    L("primary_low", "“口”字一共有几笔？", ["2 笔", "3 笔", "4 笔", "5 笔"], 1,
      "“口”的笔顺是竖、横折、横，一共 3 笔。数笔画要按笔顺一笔一笔地数。", "笔画"),
    L("primary_low", "“日”字的第二笔是什么？", ["竖", "横折", "横", "撇"], 1,
      "“日”的笔顺是竖、横折、横、横，第二笔是横折。撇不出现在“日”字里。", "笔顺"),
    L("primary_low", "一（  ）小鸟，括号里填哪个量词？", ["条", "只", "把", "张"], 1,
      "小鸟是动物，用“只”来数。一条用于长长的东西，一把用于有柄的东西，一张用于扁平的纸或桌子。", "量词"),
    L("primary_low", "“大”的反义词是什么？", ["高", "小", "多", "长"], 1,
      "“大”和“小”意思正好相反，是一对反义词。高、多、长说的都是别的方面，不跟“大”相对。", "反义词"),
    L("primary_low", "“白”的反义词是什么？", ["黑", "红", "亮", "净"], 0,
      "“白”和“黑”是颜色上相对的一对反义词。红是另一种颜色，亮和净都不是“白”的反面。", "反义词"),

    # ---- 小学高年级 9 题 ----
    L("primary_high", "下面哪个成语表示做事非常有把握？", ["胸有成竹", "画蛇添足", "守株待兔", "亡羊补牢"], 0,
      "“胸有成竹”说画竹子之前心里已经有了竹子的样子，比喻心里有把握。画蛇添足是白费功夫，守株待兔是想不劳而获，亡羊补牢是出事后及时补救。", "成语理解"),
    L("primary_high", "“不耻下问”的意思是什么？", ["向学问浅的人请教", "向学问高的人请教", "不好意思开口问", "不想回答别人"], 0,
      "“不耻下问”指不因为向地位或学问不如自己的人请教而觉得丢脸，所以是“向学问浅的人请教”。“耻”在这里是“以……为耻”。", "成语理解"),
    L("primary_high", "“光荣”的近义词是哪一个？", ["荣誉", "光线", "光荣榜", "明亮"], 0,
      "“荣誉”和“光荣”意思相近，都指值得骄傲的名声。光线、明亮说的是光，光荣榜是一个名称，都不是近义词。", "近义词"),
    L("primary_high", "“骄傲”的反义词是哪一个？", ["虚心", "自满", "高兴", "得意"], 0,
      "“骄傲”在“自以为了不起”这个意思上，反义词是“虚心”。自满和得意跟骄傲是同一个方向，不能作反义词。", "反义词"),
    L("primary_high", "“月亮像一只小船”用了哪种修辞？", ["比喻", "拟人", "夸张", "排比"], 0,
      "把月亮说成“小船”，是用打比方的方式，所以是比喻。拟人是把物当人写，夸张是故意说大或说小，排比要三个以上结构相似的句子。", "比喻"),
    L("primary_high", "“他声音大得把屋顶掀翻了”用了哪种修辞？", ["夸张", "比喻", "拟人", "设问"], 0,
      "声音再大也掀不翻屋顶，这里故意把程度说得很大，所以是夸张。比喻要有“像”“仿佛”这类打比方的说法。", "夸张"),
    L("primary_high", "“床前明月光，疑是地上霜”的作者是谁？", ["李白", "杜甫", "白居易", "王维"], 0,
      "这两句出自李白的《静夜思》，李白是唐代诗人。杜甫、白居易、王维也都是唐代诗人，但这首诗不是他们写的。", "古诗作者"),
    L("primary_high", "“停车坐爱枫林晚”中“坐”是什么意思？", ["因为", "坐下", "座位", "乘坐"], 0,
      "这里的“坐”是“因为”的意思，说的是因为喜爱枫林傍晚的景色才停下车。当作“坐下”讲，整句就说不通了。", "古诗字义"),
    L("primary_high", "提示语在前时，后面通常用什么标点？", ["冒号", "问号", "顿号", "省略号"], 0,
      "提示语在前，后面用冒号，再用引号引出说的话，例如：他说：“我们走吧。”问号用在疑问句末尾，顿号用于并列词语之间。", "标点符号"),

    # ---- 初中 8 题 ----
    L("junior", "“学而时习之”中“时”的意思是什么？", ["按时", "时间", "有时候", "当时"], 0,
      "“时”在《论语》这句里是“按时”的意思，指按时温习。解释成“时间”或“有时候”，整句意思就不通了。", "文言实词"),
    L("junior", "“温故而知新”中“故”的意思是什么？", ["旧知识", "所以", "故意", "故事"], 0,
      "“故”在这里是名词，指学过的旧知识，全句说温习旧知识能有新体会。“所以”“故意”都是现代汉语里的用法。", "文言实词"),
    L("junior", "“学而不思则罔”中“而”的作用是什么？", ["表示转折", "表示并列", "表示顺承", "表示修饰"], 0,
      "“学而不思”是说只学习却不思考，“而”前后意思相反，表示转折。表示并列时前后意思相近，这里显然不是。", "文言虚词"),
    L("junior", "“沿溯阻绝”中“绝”的意思是什么？", ["断绝", "极高", "绝对", "绝句"], 0,
      "“绝”在这里是“断绝”，说的是上行下行的航道都被阻断。表示“极高”的是“绝顶”这类词，意思不同。", "文言实词"),
    L("junior", "“略无阙处”中的通假字是哪个？", ["阙", "略", "连", "岸"], 0,
      "“阙”通“缺”，意思是空缺、中断，写两岸都是山，没有一点缺口。其他三个字都是本字，没有通假。", "通假字"),
    L("junior", "“属予作文以记之”中“属”通哪个字？", ["嘱", "注", "祝", "著"], 0,
      "“属”通“嘱”，是嘱托的意思，说的是嘱托我写一篇文章来记这件事。注、祝、著都不能替换成这里的用法。", "通假字"),
    L("junior", "下面哪部作品的作者是鲁迅？", ["《故乡》", "《背影》", "《春》", "《济南的冬天》"], 0,
      "《故乡》出自鲁迅的小说集《呐喊》。《背影》和《春》是朱自清写的，《济南的冬天》是老舍写的。", "文学常识"),
    L("junior", "“先天下之忧而忧”出自哪篇文章？", ["《岳阳楼记》", "《醉翁亭记》", "《爱莲说》", "《陋室铭》"], 0,
      "这句出自范仲淹的《岳阳楼记》。《醉翁亭记》是欧阳修的，《爱莲说》是周敦颐的，《陋室铭》是刘禹锡的。", "文学常识"),
]


# ==========================================================================
# 英语 25 题（人工编写：小学低 8 / 小学高 9 / 初中 8）
# ==========================================================================
def E(grade, stem, options, answer, analysis, kp):
    """构造一道英语题。answer 是手写答案在 options 里的下标，_correct 记录正确选项文本。"""
    q = build("英语", grade, stem, options, analysis, kp, spec=None, correct=options[answer])
    q["answer"] = answer
    return q


ENG_ITEMS = [
    # ---- 小学低年级 8 题 ----
    E("primary_low", "字母 A 后面的一个字母是什么？", ["B", "C", "D", "E"], 0,
      "字母表按顺序是 A、B、C、D、E，A 的后面紧跟 B。C 是 B 后面的字母，隔了一个。", "字母顺序"),
    E("primary_low", "早上见到老师，应该说什么？", ["Hello!", "Bye!", "Good!", "Sorry!"], 0,
      "早上见面打招呼用 Hello! 最合适，也可以说 Good morning!。Bye! 是再见时说的，Sorry! 是道歉时说的。", "问候语"),
    E("primary_low", "“Good morning” 是什么意思？", ["早上好", "下午好", "晚上好", "晚安"], 0,
      "morning 是早上，所以 Good morning 是“早上好”。下午好用 Good afternoon，晚上好用 Good evening。", "日常问候"),    E("primary_low", "“红色”用英语怎么说？", ["red", "blue", "green", "yellow"], 0,
      "红色的英语是 red。blue 是蓝色，green 是绿色，yellow 是黄色，别弄混。", "颜色单词"),
    E("primary_low", "“黄色”用英语怎么说？", ["yellow", "red", "black", "white"], 0,
      "黄色的英语是 yellow。red 是红色，black 是黑色，white 是白色。", "颜色单词"),
    E("primary_low", "数字 3 用英语怎么写？", ["three", "two", "four", "five"], 0,
      "数字 3 是 three。two 是 2，four 是 4，five 是 5，按顺序数就能记住。", "数字单词"),
    E("primary_low", "“cat” 表示哪种动物？", ["猫", "狗", "鸟", "鱼"], 0,
      "cat 是猫。狗是 dog，鸟是 bird，鱼是 fish，这几个小动物单词要分清楚。", "动物单词"),
    E("primary_low", "称呼爸爸用哪个英语单词？", ["father", "mother", "uncle", "sister"], 0,
      "爸爸是 father，也可以说 dad。mother 是妈妈，uncle 是叔叔或舅舅，sister 是姐妹。", "称呼单词"),

    # ---- 小学高年级 9 题 ----
    E("primary_high", "He ___ football every Sunday. 选哪个？", ["plays", "play", "playing", "played"], 0,
      "主语 He 是第三人称单数，一般现在时的动词要加 s，所以用 plays。play 用于 I 或复数主语，playing 需要 be 动词，played 是过去式。", "第三人称单数"),
    E("primary_high", "There are three ___ in the box. 选哪个？", ["boxes", "box", "boxs", "a box"], 0,
      "three 后面要用可数名词的复数形式，box 以 x 结尾，复数加 es，所以是 boxes。boxs 是拼写不正确的形式。", "名词复数"),
    E("primary_high", "The book is ___ the desk. 书在哪里？", ["on", "in", "under", "behind"], 0,
      "在桌子的表面上用 on。in 表示在里面，under 表示在下面，behind 表示在后面，都和“在上面”不符。", "方位介词"),
    E("primary_high", "I ___ my homework yesterday. 选哪个？", ["finished", "finish", "finishes", "finishing"], 0,
      "yesterday 说明事情发生在过去，要用过去式 finished。finish 和 finishes 是现在时，finishing 不能单独作谓语。", "一般过去时"),
    E("primary_high", "My sister and I ___ students. 选哪个？", ["are", "is", "am", "be"], 0,
      "主语是两个人，属于复数，be 动词用 are。is 用于第三人称单数，am 只跟 I 搭配，be 是原形不能直接放在这里。", "be 动词"),
    E("primary_high", "What time ___ it now? 选哪个？", ["is", "are", "am", "be"], 0,
      "问时间用 What time is it?，主语 it 是第三人称单数，be 动词用 is。", "be 动词"),
    E("primary_high", "Which word means “快乐的”？", ["happy", "hungry", "angry", "tired"], 0,
      "happy 是快乐的。hungry 是饿的，angry 是生气的，tired 是累的，这几个形容词描述的心情不一样。", "词汇辨析"),
    E("primary_high", "Which word is a verb（动词）? 选哪个？", ["run", "red", "desk", "quickly"], 0,
      "run 表示跑，是动词。red 是形容词，desk 是名词，quickly 是副词。", "词性辨析"),
    E("primary_high", "I go to school ___ bus every day. 选哪个？", ["by", "on", "in", "with"], 0,
      "“乘公交车”固定说 by bus，by 后面直接跟交通工具，不加冠词。要说 on a bus 才用 on。", "固定搭配"),

    # ---- 初中 8 题 ----
    E("junior", "I ___ to the park last Sunday. 选哪个？", ["went", "go", "have gone", "am going"], 0,
      "last Sunday 是过去的时间，要用一般过去时 went。have gone 是现在完成时，不能和表示过去的时间状语连用。", "一般过去时"),
    E("junior", "I ___ this book twice. 选哪个？", ["have read", "read", "am reading", "will read"], 0,
      "twice 表示到目前为止的次数，要用现在完成时 have read。一般过去时 read 不能表达“到现在为止两次”。", "现在完成时"),
    E("junior", "This bridge ___ in 1998. 被动语态选哪个？", ["was built", "built", "is built", "builds"], 0,
      "桥是被建造的，要用被动语态；1998 是过去时间，所以用 was built。built 是主动的过去式，is built 是现在的被动。", "被动语态"),
    E("junior", "The boy is ___ than his brother. 选哪个？", ["taller", "tall", "tallest", "more tall"], 0,
      "than 前面要用比较级 taller，单音节词加 -er。tallest 是最高级，more tall 不是正确的比较级形式。", "比较级"),
    E("junior", "He is the ___ student in our class. 选哪个？", ["tallest", "taller", "tall", "more tall"], 0,
      "the 加上 in our class 表示在班里这个范围里最高，要用最高级 tallest。taller 是比较级，要和 than 一起用。", "最高级"),
    E("junior", "Tell me what time the shop ___ every day. 选哪个？", ["closes", "close", "closed", "closing"], 0,
      "宾语从句说的是每天固定的营业安排，属于经常发生的事，要用一般现在时；主语 the shop 是第三人称单数，所以用 closes。", "宾语从句"),
    E("junior", "The teacher said the earth ___ around the sun. 选哪个？", ["moves", "move", "moving", "moved"], 0,
      "宾语从句说的是客观真理，不管主句用什么时态，从句都用一般现在时；the earth 是第三人称单数，所以用 moves。move、moving 不是单数形式，moved 是过去式。", "宾语从句"),
    E("junior", "My brother is good ___ playing basketball. 选哪个？", ["at", "in", "on", "for"], 0,
      "be good at 是固定搭配，表示擅长做某事，at 后面接动名词 playing。in、on、for 都不能和 good 构成这个意思。", "固定搭配"),
]


# ==========================================================================
# 答案下标统一重排 + 汇总输出
# ==========================================================================
def answer_targets(count, theme):
    """按 ANSWER_QUOTA 生成一个打乱后的目标下标序列（纯函数，可复现）。"""
    idx = []
    for i, n in enumerate(ANSWER_QUOTA[theme]):
        idx.extend([i] * n)
    assert len(idx) == count, (theme, len(idx), count)
    random.Random(SEED + 1).shuffle(idx)
    return idx


def assign_answers(items, theme, targets=None):
    """按 targets 重排正确答案下标，使 0~3 的分布符合 ANSWER_QUOTA。

    正确选项由每题自己记录的 `_correct` 文本定位（不假设它在下标 0），
    再和下标 target 处的选项交换，最后断言 options[answer] 就是正确选项。
    """
    idx = targets if targets is not None else answer_targets(len(items), theme)
    assert len(idx) == len(items), (theme, len(idx), len(items))
    for q, target in zip(items, idx):
        opts = list(q["options"])
        cur = opts.index(q["_correct"])          # 正确选项现在的位置
        opts[cur], opts[target] = opts[target], opts[cur]
        q["options"] = opts
        q["answer"] = target
        assert opts[target] == q["_correct"], (theme, q["stem"], opts, target)
    return items


def all_items():
    """返回 75 题：语文 25 -> 数学 25 -> 英语 25，每个主题内按学段排序。"""
    items = []
    for theme, group in (("语文", LANG_ITEMS), ("数学", generate_math()), ("英语", ENG_ITEMS)):
        ordered = []
        for g in GRADE_ORDER:
            ordered.extend([q for q in group if q["grade"] == g])
        assert len(ordered) == 25, (theme, len(ordered))
        assign_answers(ordered, theme)
        for q in ordered:
            assert len(set(q["options"])) == 4, (theme, q["stem"])
            assert q["options"][q["answer"]] == q["_correct"], (theme, q["stem"])
            assert q["options"][q["answer"]].strip() != "", q["stem"]
        items.extend(ordered)
    return items


def to_public(q):
    return {k: q[k] for k in FIELDS}


def specs_of(items):
    out = []
    for q in items:
        if q.get("_spec"):
            out.append({"stem": q["stem"], "answer_text": q["options"][q["answer"]], "spec": q["_spec"]})
    return out


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:                                 # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="写出 backend/app/bank_part_c.json")
    ap.add_argument("--bank", default=None, help="题库输出路径")
    ap.add_argument("--spec", default=None, help="数学题校验 spec 输出路径")
    args = ap.parse_args()

    items = all_items()
    public = [to_public(q) for q in items]

    grid = Counter((q["theme"], q["grade"]) for q in public)
    assert len(public) == 75, len(public)
    for t in THEME_ORDER:
        assert sum(grid[(t, g)] for g in GRADE_ORDER) == 25, t
        for g, n in GRADE_PLAN:
            assert grid[(t, g)] == n, (t, g, grid[(t, g)])

    text = json.dumps(public, ensure_ascii=False, indent=2) + "\n"
    if args.write or args.bank:
        path = args.bank or BANK_PATH
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        sys.stderr.write("已写出 %d 题 -> %s\n" % (len(public), path))
    else:
        print(text)

    if args.spec:
        specs = specs_of(items)
        with open(args.spec, "w", encoding="utf-8", newline="\n") as f:
            json.dump(specs, f, ensure_ascii=False, indent=2)
        sys.stderr.write("已写出 %d 条数学 spec -> %s\n" % (len(specs), args.spec))

    for t in THEME_ORDER:
        dist = Counter(q["answer"] for q in public if q["theme"] == t)
        sys.stderr.write("  %s answer 分布: %s\n" % (t, dict(sorted(dist.items()))))
    sys.stderr.write("分布：%s\n" % json.dumps(
        {"%s/%s" % k: v for k, v in sorted(grid.items())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
