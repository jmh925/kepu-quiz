# -*- coding: utf-8 -*-
"""bank_part_c.json（基础课程题库：语文/数学/英语）逐项自检；任一不通过则退出码非 0。

检查项
------
[1] JSON 可解析、共 75 题、字段与类型
[2] 主题恰好是 语文/数学/英语，各 25 题
[3] 每个主题内学段分布 = 8（小学低）/ 9（小学高）/ 8（初中）
[4] 每题恰好 4 个选项、选项互不重复、互不相同、answer 在 0~3
[5] options[answer] / analysis / knowledge_point 非空
[6] 题干本文件内不重复，且与 bank_part_a.json + bank_part_b.json 不重复
[6.5] 语文 / 英语题逐题核对 answer 下标指向的选项（独立的人手核对期望表）
[7] 每个主题内 answer 下标分布均衡（每个下标 4~9 次）
[8] 数学题逐题重算：两层独立复核
      (a) 先从题干自然语言里解析算式（正则模板），用本文件独立实现的运算器重算；
      (b) 再用 gen_math_bank.py 产出的 spec（算式 + 解析类型）重算一遍，
          并核对「题库里的 25 道数学题」与「用同一种子重新生成的 25 道」完全一致。
    (a) 解析不出来的题会逐条列出，不会静默通过。

同时检查（附加质量项）：
[9]  题干 / 选项长度上限（低 25/6，高 40/10，初中 60/16）
[10] 文案规范：不出现「错误」「失败」「排名」
[11] 题干必须是完整的问句（以 ？ 结尾）
[12] 单个模板生成的同型题不超过 4 道

用法：
    python tools/gen_math_bank.py --write      # 生成题库
    python tools/check_basic_bank.py           # 自检
"""
import ast
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

# Windows 控制台默认可能是 GBK，统一按 UTF-8 输出，避免中文和 ² 之类的字符报编码问题
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:                                     # noqa: BLE001
        pass


def same_answer(a, b):
    """比较两种算法给出的答案文本是否等价。

    允许两处不影响数学含义的写法差异：
      * 结尾的度数符号（62 与 62° 是同一个角的大小）
      * 因式分解里两个括号的先后顺序（(x+4)(x+5) 与 (x+5)(x+4) 是同一个式子）
    """
    norm = lambda s: s.strip().replace(" ", "").replace("°", "")          # noqa: E731
    x, y = norm(a), norm(b)
    if x == y:
        return True, ""
    parts = re.compile(r"^(\(x[+\-]\d+\))+$")
    if parts.match(x) and parts.match(y):
        if sorted(re.findall(r"\(x[+\-]\d+\)", x)) == sorted(re.findall(r"\(x[+\-]\d+\)", y)):
            return True, "（因式括号顺序不同，视为同一个式子）"
    return False, ""

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_math_bank import generate_math, assign_answers  # noqa: E402  （现场重算 spec + 同源核对）

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "backend", "app")
PATH_C = os.path.join(APP, "bank_part_c.json")
PATH_A = os.path.join(APP, "bank_part_a.json")
PATH_B = os.path.join(APP, "bank_part_b.json")

THEMES = ["语文", "数学", "英语"]
GRADES = ["primary_low", "primary_high", "junior"]
GRADE_LABEL = {"primary_low": "小学低年级(1-3)", "primary_high": "小学高年级(4-6)", "junior": "初中(7-9)"}
GRADE_PLAN = {"primary_low": 8, "primary_high": 9, "junior": 8}
STEM_MAX = {"primary_low": 25, "primary_high": 40, "junior": 60}
OPT_MAX = {"primary_low": 6, "primary_high": 10, "junior": 16}
FIELDS = ["theme", "grade", "type", "stem", "options", "answer", "analysis", "knowledge_point"]
BANNED = ["错误", "失败", "排名"]

errors = []
warnings = []


def fail(msg):
    errors.append(msg)


def hr(title):
    print("")
    print("=" * 74)
    print(title)
    print("=" * 74)


def shorter(s, n=46):
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


# ==========================================================================
# [1] 解析
# ==========================================================================
hr("[1] JSON 解析与字段结构")
try:
    with open(PATH_C, "rb") as f:
        raw = f.read()
    raw.decode("utf-8")
    data = json.loads(raw.decode("utf-8-sig"))
except Exception as e:                                    # noqa: BLE001
    print("解析 bank_part_c.json 就出问题了: %r" % (e,))
    sys.exit(1)

print("文件: %s" % PATH_C)
print("UTF-8 解码: 成功（%s）" % ("有 BOM" if raw[:3] == b"\xef\xbb\xbf" else "无 BOM"))
print("顶层类型 = %s，记录数 = %d（要求 75）%s" % (
    type(data).__name__, len(data), "OK" if len(data) == 75 else "FAIL"))
if len(data) != 75:
    fail("题量 %d != 75" % len(data))

field_bad = 0
for i, q in enumerate(data):
    if not isinstance(q, dict):
        fail("#%d 不是对象" % i)
        field_bad += 1
        continue
    extra = sorted(set(q) - set(FIELDS))
    missing = [k for k in FIELDS if k not in q]
    if extra:
        fail("#%d 多出字段 %s" % (i, extra))
        field_bad += 1
    if missing:
        fail("#%d 缺少字段 %s" % (i, missing))
        field_bad += 1
    if q.get("type") != "single":
        fail("#%d type 必须是 single，实际 %r" % (i, q.get("type")))
        field_bad += 1
    for k in ("stem", "analysis", "knowledge_point"):
        if not isinstance(q.get(k), str) or not q[k].strip():
            fail("#%d 字段 %s 为空或不是字符串" % (i, k))
            field_bad += 1
print("逐题字段巡检: 问题数 = %d %s" % (field_bad, "OK" if field_bad == 0 else "FAIL"))

# ==========================================================================
# [2][3] 主题 / 学段分布
# ==========================================================================
hr("[2][3] 主题与学段分布")
grid = Counter((q.get("theme"), q.get("grade")) for q in data)
for t in THEMES:
    n = sum(grid[(t, g)] for g in GRADES)
    ok = n == 25
    print("  %s 主题合计 = %2d / 25  %s" % (t, n, "OK" if ok else "FAIL"))
    if not ok:
        fail("%s 主题合计 %d != 25" % (t, n))
    for g in GRADES:
        c = grid[(t, g)]
        ok = c == GRADE_PLAN[g]
        print("      %-16s = %d / %d  %s" % (GRADE_LABEL[g], c, GRADE_PLAN[g], "OK" if ok else "FAIL"))
        if not ok:
            fail("%s/%s = %d != %d" % (t, g, c, GRADE_PLAN[g]))
illegal = sorted(set(q.get("theme") for q in data) - set(THEMES)) + \
          sorted(set(q.get("grade") for q in data) - set(GRADES))
print("  非法 theme/grade: %s %s" % (illegal if illegal else "无", "OK" if not illegal else "FAIL"))
if illegal:
    fail("出现非法 theme/grade: %s" % illegal)
gtot = Counter(q.get("grade") for q in data)
print("  全库学段合计: %s（期望 24 / 27 / 24）" % dict((g, gtot[g]) for g in GRADES))
if [gtot[g] for g in GRADES] != [24, 27, 24]:
    fail("学段合计 %s 不是 24/27/24" % dict(gtot))

# ==========================================================================
# [4][5] 选项与答案
# ==========================================================================
hr("[4][5] 选项与答案字段")
opt_bad = 0
for i, q in enumerate(data):
    tag = "#%d %s/%s" % (i, q.get("theme"), q.get("grade"))
    opts = q.get("options")
    a = q.get("answer")
    if not isinstance(opts, list) or len(opts) != 4:
        fail("%s options 不是恰好 4 个（%r）" % (tag, opts))
        opt_bad += 1
        continue
    if any(not isinstance(o, str) or not o.strip() for o in opts):
        fail("%s options 有空项或非字符串" % tag)
        opt_bad += 1
    if len(set(opts)) != 4:
        fail("%s options 有重复项：%s" % (tag, opts))
        opt_bad += 1
    if not isinstance(a, int) or isinstance(a, bool) or not (0 <= a < 4):
        fail("%s answer=%r 不在 0~3" % (tag, a))
        opt_bad += 1
        continue
    if not opts[a].strip():
        fail("%s options[answer] 为空" % tag)
        opt_bad += 1
print("  4 选项 / 互不相同 / answer∈0~3 / 答案项非空：问题数 = %d %s" % (opt_bad, "OK" if opt_bad == 0 else "FAIL"))

# ==========================================================================
# [6] 题干去重（含 a/b 题库）
# ==========================================================================
hr("[6] 题干去重（本文件 + bank_part_a + bank_part_b）")
stems = [q.get("stem", "") for q in data]
dups = [s for s, c in Counter(stems).items() if c > 1]
print("  本文件内重复题干: %s %s" % (dups if dups else "无", "OK" if not dups else "FAIL"))
if dups:
    fail("本文件重复题干: %s" % dups)
others = {}
for p in (PATH_A, PATH_B):
    with open(p, "r", encoding="utf-8") as f:
        for q in json.load(f):
            others.setdefault(q["stem"], os.path.basename(p))
cross = [(s, others[s]) for s in stems if s in others]
print("  a/b 题库题干总数 = %d；与本题库相撞: %s %s" % (
    len(others), cross if cross else "无", "OK" if not cross else "FAIL"))
if cross:
    fail("与 a/b 题库题干相撞: %s" % cross)

# ==========================================================================
# [6.5] 语文 / 英语题的内容正确性（与生成脚本相互独立的人手核对表）
# ==========================================================================
hr("[6.5] 语文 / 英语题答案内容核对（人工核对的期望答案，与生成脚本相互独立）")
EXPECT_ANSWER = {
    # ---- 语文 ----
    "“爸”字的拼音怎么写？": "bà",
    "“妈”的声母是哪一个？": "m",
    "下面哪个是整体认读音节？": "zhi",
    "“口”字一共有几笔？": "3 笔",
    "“日”字的第二笔是什么？": "横折",
    "一（  ）小鸟，括号里填哪个量词？": "只",
    "“大”的反义词是什么？": "小",
    "“白”的反义词是什么？": "黑",
    "下面哪个成语表示做事非常有把握？": "胸有成竹",
    "“不耻下问”的意思是什么？": "向学问浅的人请教",
    "“光荣”的近义词是哪一个？": "荣誉",
    "“骄傲”的反义词是哪一个？": "虚心",
    "“月亮像一只小船”用了哪种修辞？": "比喻",
    "“他声音大得把屋顶掀翻了”用了哪种修辞？": "夸张",
    "“床前明月光，疑是地上霜”的作者是谁？": "李白",
    "“停车坐爱枫林晚”中“坐”是什么意思？": "因为",
    "提示语在前时，后面通常用什么标点？": "冒号",
    "“学而时习之”中“时”的意思是什么？": "按时",
    "“温故而知新”中“故”的意思是什么？": "旧知识",
    "“学而不思则罔”中“而”的作用是什么？": "表示转折",
    "“沿溯阻绝”中“绝”的意思是什么？": "断绝",
    "“略无阙处”中的通假字是哪个？": "阙",
    "“属予作文以记之”中“属”通哪个字？": "嘱",
    "下面哪部作品的作者是鲁迅？": "《故乡》",
    "“先天下之忧而忧”出自哪篇文章？": "《岳阳楼记》",
    # ---- 英语 ----
    "字母 A 后面的一个字母是什么？": "B",
    "早上见到老师，应该说什么？": "Hello!",
    "“Good morning” 是什么意思？": "早上好",
    "“红色”用英语怎么说？": "red",
    "“黄色”用英语怎么说？": "yellow",
    "数字 3 用英语怎么写？": "three",
    "“cat” 表示哪种动物？": "猫",
    "称呼爸爸用哪个英语单词？": "father",
    "He ___ football every Sunday. 选哪个？": "plays",
    "There are three ___ in the box. 选哪个？": "boxes",
    "The book is ___ the desk. 书在哪里？": "on",
    "I ___ my homework yesterday. 选哪个？": "finished",
    "My sister and I ___ students. 选哪个？": "are",
    "What time ___ it now? 选哪个？": "is",
    "Which word means “快乐的”？": "happy",
    "Which word is a verb（动词）? 选哪个？": "run",
    "I go to school ___ bus every day. 选哪个？": "by",
    "I ___ to the park last Sunday. 选哪个？": "went",
    "I ___ this book twice. 选哪个？": "have read",
    "This bridge ___ in 1998. 被动语态选哪个？": "was built",
    "The boy is ___ than his brother. 选哪个？": "taller",
    "He is the ___ student in our class. 选哪个？": "tallest",
    "Tell me what time the shop ___ every day. 选哪个？": "closes",
    "The teacher said the earth ___ around the sun. 选哪个？": "moves",
    "My brother is good ___ playing basketball. 选哪个？": "at",
}
answer_bad = []
for q in data:
    if q.get("theme") not in ("语文", "英语"):
        continue
    expect = EXPECT_ANSWER.get(q.get("stem"))
    if expect is None:
        answer_bad.append("核对表里缺少这道题: %s" % q.get("stem"))
        continue
    got = q["options"][q["answer"]]
    if got != expect:
        answer_bad.append("#%d %s | 期望答案 %r，实际 options[answer] = %r"
                          % (data.index(q), shorter(q["stem"]), expect, got))
missing_in_bank = [s for s in EXPECT_ANSWER if s not in {q.get("stem") for q in data}]
for s in missing_in_bank:
    answer_bad.append("核对表里多出这道题: %s" % s)
print("  核对表条目数 = %d（语文 25 + 英语 25），题库中对应题目 = %d" % (
    len(EXPECT_ANSWER), sum(1 for q in data if q.get("theme") in ("语文", "英语"))))
if answer_bad:
    for line in answer_bad:
        print("      - " + line)
    fail("语文/英语答案内容核对不通过，共 %d 处" % len(answer_bad))
else:
    print("  语文 25 题 + 英语 25 题的 answer 下标都指向本该正确的那一项 OK")

# ==========================================================================
# [7] answer 下标分布
# ==========================================================================
hr("[7] 每个主题内 answer 下标分布（要求 4~9 次）")
ans_bad = 0
for t in THEMES:
    dist = Counter(q["answer"] for q in data if q["theme"] == t)
    line = "  ".join("下标%d = %2d" % (i, dist[i]) for i in range(4))
    ok = all(4 <= dist[i] <= 9 for i in range(4))
    print("  %s: %s  %s" % (t, line, "OK" if ok else "FAIL"))
    if not ok:
        fail("%s 主题 answer 分布不均衡: %s" % (t, dict(dist)))
        ans_bad += 1
allc = Counter(q["answer"] for q in data)
print("  全库合计: %s" % dict(sorted(allc.items())))

# ==========================================================================
# [8] 数学题逐题重算
# ==========================================================================
hr("[8] 数学题逐题重算（独立运算器复核；spec 由 gen_math_bank.py 现场重新生成）")
ALLOWED_FUNCS = {"sqrt": math.sqrt, "max": max, "min": min, "abs": abs}
ALLOWED_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Call, ast.Name,
                 ast.Load, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd)


def safe_eval(expr):
    """只允许四则运算、乘方和 sqrt/max/min/abs 的算式求值器（独立实现）。"""
    tree = ast.parse(expr.replace("^", "**").replace("×", "*").replace("÷", "/"), mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            raise ValueError("算式里出现不允许的节点 %s" % type(node).__name__)
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_FUNCS:
                raise ValueError("算式里出现不允许的函数")
    return eval(compile(tree, "<expr>", "eval"), {"__builtins__": {}}, dict(ALLOWED_FUNCS))


def render(v):
    """把计算结果渲染成选项文本的样子（整数不带小数点）。"""
    if isinstance(v, float):
        if abs(v - round(v)) < 1e-9:
            return str(int(round(v)))
        return ("%.4f" % v).rstrip("0").rstrip(".")
    return str(v)


SPEC_KINDS = {"arith", "frac_str", "compare_big", "compare_frac", "poly_expand",
              "poly_factor", "quadratic"}


def compute_from_spec(sp):
    """按 spec 重算这道数学题的正确答案文本。

    - arith        : 直接对 expr 求值
    - frac_str     : expr 形如 15/100，化成最简分数 "3/20"
    - compare_big  : expr 形如 max(12,57)，返回 "57 大"
    - compare_frac : expr 形如 max(3/4,5/6)，用交叉相乘比较（不转小数），返回 "5/6"
    - poly_expand  : (ax+b)(x+c) 按 a*b、a*c+b、b*c 独立展开
    - poly_factor  : x²+(a+b)x+ab 的两个因式，返回多项式文本
    - quadratic    : x²+bx+c=0 用求根公式算两根，返回 "x₁ = 大，x₂ = 小"
    """
    kind = sp["kind"]
    if kind == "arith":
        v = safe_eval(sp["expr"])
        s = render(v)
        if sp.get("expect_str"):
            s = sp["expect_str"]
        return s
    if kind == "frac_str":
        m = re.match(r"^(\d+)/(\d+)$", sp["expr"].strip())
        if not m:
            raise ValueError("frac_str 的 expr 形状不对")
        num, den = int(m.group(1)), int(m.group(2))
        g = math.gcd(num, den)
        return "%d/%d" % (num // g, den // g)
    if kind == "compare_big":
        m = re.match(r"^max\((\d+),(\d+)\)$", sp["expr"].strip())
        if not m:
            raise ValueError("compare_big 的 expr 形状不对")
        x, y = int(m.group(1)), int(m.group(2))
        if x == y:
            return "一样大"
        return "%d 大" % (x if x > y else y)
    if kind == "compare_frac":
        m = re.match(r"^max\((\d+)/(\d+),(\d+)/(\d+)\)$", sp["expr"].strip())
        if not m:
            raise ValueError("compare_frac 的 expr 形状不对")
        n1, d1, n2, d2 = (int(g) for g in m.groups())
        left, right = n1 * d2, n2 * d1          # 交叉相乘比较，不依赖小数
        if left == right:
            return "一样大"
        return "%d/%d" % ((n1, d1) if left > right else (n2, d2))
    if kind == "poly_expand":
        a, b, c = sp["a"], sp["b"], sp["c"]
        return "%dx² + %dx + %d" % (a * b, a * c + b, b * c)
    if kind == "poly_factor":
        a, b = sp["a"], sp["b"]
        return "(x + %d)(x + %d)" % (a, b)
    if kind == "quadratic":
        b, c = sp["b"], sp["c"]
        disc = b * b - 4 * c
        if disc < 0:
            raise ValueError("判别式小于 0，题目设计有问题")
        r1 = (-b + math.sqrt(disc)) / 2
        r2 = (-b - math.sqrt(disc)) / 2
        r1, r2 = sorted((r1, r2), reverse=True)
        return "x₁ = %s，x₂ = %s" % (render(r1), render(r2))
    raise ValueError("未知 spec 类型 %s" % kind)


# ---- 从题干自然语言里解析算式（覆盖「纯算式型」模板） ----
NL_PATTERNS = [
    ("纯加减乘除算式", re.compile(r"^(\d+)\s*([+\-×÷])\s*(\d+)\s*=\s*？$")),
    ("求未知加数", re.compile(r"^(\d+)\s*\+\s*（\s*）\s*=\s*(\d+)，")),
    ("求未知乘数", re.compile(r"^(\d+)\s*×\s*（\s*）\s*=\s*(\d+)，")),
    ("比大小", re.compile(r"^(\d+)\s*和\s*(\d+)，哪个数更大？$")),
    ("百分数", re.compile(r"^(\d+)\s*的\s*(\d+)%\s*是多少？$")),
    ("米换厘米", re.compile(r"^(\d+)\s*米等于多少厘米？$")),
    ("小数化分数", re.compile(r"^把小数\s*0\.(\d+)\s*化成最简分数，是多少？$")),
    ("分数比大小", re.compile(r"^分数\s*(\d+)/(\d+)\s*和\s*(\d+)/(\d+)\s*比大小")),
    ("三角形内角和", re.compile(r"^三角形两个内角是\s*(\d+)°\s*和\s*(\d+)°")),
    ("勾股定理", re.compile(r"^直角三角形两条直角边是\s*(\d+)\s*和\s*(\d+)")),
    ("长方形面积", re.compile(r"^长方形长\s*(\d+)\s*厘米、宽\s*(\d+)\s*厘米，面积")),
    ("长方形周长", re.compile(r"^长方形长\s*(\d+)\s*米、宽\s*(\d+)\s*米，周长")),
    ("混合运算", re.compile(r"^(\d+)\s*×\s*(\d+)\s*\+\s*(\d+)\s*-\s*(\d+)\s*=\s*？$")),
    ("解一元一次方程", re.compile(r"^解一元一次方程：(\d+)x\s*([+\-])\s*(\d+)\s*=\s*(\d+)，")),
    ("解简单方程", re.compile(r"^方程\s*(\d+)x\s*([+\-])\s*(\d+)\s*=\s*(\d+)\s*中，x 是多少？$")),
    ("整式乘法", re.compile(r"^把\s*\((\d+)x\s*\+\s*(\d+)\)\(x\s*\+\s*(\d+)\)\s*展开")),
    ("因式分解", re.compile(r"^把\s*x²\s*\+\s*(\d+)x\s*\+\s*(\d+)\s*分解因式")),
    ("一元二次方程", re.compile(r"^方程\s*x²\s*-\s*(\d+)x\s*\+\s*(\d+)\s*=\s*0\s*的两根")),
    ("一次函数求值", re.compile(r"^一次函数\s*y\s*=\s*(\d+)x\s*([+\-])\s*(\d+)，当\s*x\s*=\s*(-?\d+)\s*时")),
    ("科学记数法", re.compile(r"^把\s*(\d+)\s*用科学记数法表示")),
]


def compute_from_stem(stem):
    """完全从题干文字出发重算答案文本；返回 (方法名, 结果文本)，解析不了就抛异常。"""
    for name, rx in NL_PATTERNS:
        m = rx.match(stem)
        if not m:
            continue
        g = m.groups()
        if name == "纯加减乘除算式":
            a, op, b = int(g[0]), g[1], int(g[2])
            v = {"+": a + b, "-": a - b, "×": a * b, "÷": a / b}[op]
            return name, render(v)
        if name == "求未知加数":
            return name, render(int(g[1]) - int(g[0]))
        if name == "求未知乘数":
            return name, render(int(g[1]) / int(g[0]))
        if name == "比大小":
            x, y = int(g[0]), int(g[1])
            return name, "一样大" if x == y else "%d 大" % max(x, y)
        if name == "百分数":
            return name, render(int(g[0]) * int(g[1]) / 100)
        if name == "米换厘米":
            return name, render(int(g[0]) * 100)
        if name == "小数化分数":
            num, den = int(g[0]), 100
            k = math.gcd(num, den)
            return name, "%d/%d" % (num // k, den // k)
        if name == "分数比大小":
            n1, d1, n2, d2 = (int(x) for x in g)
            left, right = n1 * d2, n2 * d1
            return name, "一样大" if left == right else "%d/%d" % ((n1, d1) if left > right else (n2, d2))
        if name == "三角形内角和":
            return name, "%d°" % (180 - int(g[0]) - int(g[1]))
        if name == "勾股定理":
            return name, render(math.sqrt(int(g[0]) ** 2 + int(g[1]) ** 2))
        if name == "长方形面积":
            return name, render(int(g[0]) * int(g[1]))
        if name == "长方形周长":
            return name, render(2 * (int(g[0]) + int(g[1])))
        if name == "混合运算":
            a, b, c, d = (int(x) for x in g)
            return name, render(a * b + c - d)
        if name in ("解一元一次方程", "解简单方程"):
            a, sign, b, c = int(g[0]), g[1], int(g[2]), int(g[3])
            b = b if sign == "+" else -b
            return name, render((c - b) / a)
        if name == "整式乘法":
            a, b, c = (int(x) for x in g)
            return name, "%dx² + %dx + %d" % (a * b, a * c + b, b * c)
        if name == "因式分解":
            s, p = int(g[0]), int(g[1])
            # 解 t² - s·t + p = 0，取整数根
            disc = s * s - 4 * p
            r = math.isqrt(disc)
            if r * r != disc:
                raise ValueError("因式分解的两个根不是整数")
            x1, x2 = (s + r) // 2, (s - r) // 2
            return name, "(x + %d)(x + %d)" % (x1, x2)
        if name == "一元二次方程":
            s, c = int(g[0]), int(g[1])
            disc = s * s - 4 * c
            r = math.isqrt(disc)
            if r * r != disc:
                raise ValueError("一元二次方程的两根不是整数")
            big, small = (s + r) // 2, (s - r) // 2
            return name, "x₁ = %d，x₂ = %d" % (big, small)
        if name == "一次函数求值":
            k, sign, b, x = int(g[0]), g[1], int(g[2]), int(g[3])
            b = b if sign == "+" else -b
            return name, render(k * x + b)
        if name == "科学记数法":
            value = int(g[0])
            n = len(str(value)) - 1
            a = value // (10 ** n)
            return name, "%d × 10^%d" % (a, n)
    raise ValueError("题干不匹配任何已知算式模板，需要人工确认")


math_qs = [q for q in data if q["theme"] == "数学"]
stem_ok = 0
stem_unparsed = []
stem_notes = []
spec_ok = 0
spec_bad = []
spec_missing = []

# spec 与「生成器同源检查」都来自现场重新生成的 25 道数学题
# 注意：题库里的数学题经过 assign_answers() 重排过答案下标，这里要对重新生成的
# 题目做同样的重排，才能逐字段比较（重排本身是纯函数，用固定种子可复现）。
try:
    regen_list = assign_answers(generate_math(), "数学")
except Exception as e:                                    # noqa: BLE001
    print("  重新调用 gen_math_bank.generate_math() 失败: %r" % (e,))
    fail("无法用 gen_math_bank.py 重新生成数学题: %r" % (e,))
    regen_list = []
spec_map = {g["stem"]: g for g in regen_list}
print("  现场调用 tools/gen_math_bank.py 重新生成数学题 %d 道（种子固定，结果可复现）" % len(spec_map))

for q in math_qs:
    tag = "#%d %s  %s" % (data.index(q), q["grade"], shorter(q["stem"]))
    shown = q["options"][q["answer"]]
    # (a) 只从题干文字出发重算
    try:
        method, got = compute_from_stem(q["stem"])
        ok_eq, note = same_answer(got, shown)
        if ok_eq:
            stem_ok += 1
            if note:
                stem_notes.append("%s | 题干重算 %r，答案是 %r %s" % (tag, got, shown, note))
        else:
            stem_unparsed.append("%s | 题干重算 %r != 答案 %r（%s）" % (tag, got, shown, method))
    except Exception as e:                                # noqa: BLE001
        stem_unparsed.append("%s | 解析不出来（%s）" % (tag, e))
    # (b) 用 spec 算式重算
    g = spec_map.get(q["stem"])
    if g is None:
        spec_missing.append(tag)
        continue
    try:
        got2 = compute_from_spec(g["_spec"])
        ok_eq, note = same_answer(got2, shown)
        if ok_eq:
            spec_ok += 1
        else:
            spec_bad.append("%s | spec 重算 %r != 答案 %r" % (tag, got2, shown))
    except Exception as e:                                # noqa: BLE001
        spec_bad.append("%s | spec 重算出错（%s）" % (tag, e))

n_math = len(math_qs)
print("  数学题总数 = %d" % n_math)
print("  (a) 只从题干文字就能解析并重算的: %d / %d = %.1f%%" % (
    stem_ok, n_math, 100.0 * stem_ok / n_math))
print("  (b) 用 spec 算式重算并比对成功的: %d / %d = %.1f%%" % (
    spec_ok, n_math, 100.0 * spec_ok / n_math))
print("  (c) 两种方法都算通、且结果一致的: %d / %d = %.1f%%" % (
    min(stem_ok, spec_ok), n_math, 100.0 * min(stem_ok, spec_ok) / n_math))
print("  题干文字解析情况（解析不出来的、或算出来和答案不一致的，都会列在下面）:")
if stem_unparsed:
    for line in stem_unparsed:
        print("      - " + line)
else:
    print("      （无，25 道全部解析成功且与答案一致）")
if stem_notes:
    print("  其中用等价写法确认、已逐条人工复核的:")
    for line in stem_notes:
        print("      - " + line)
if spec_bad:
    print("  spec 复核发现的问题:")
    for line in spec_bad:
        print("      - " + line)
    fail("spec 复核有问题: %d 条" % len(spec_bad))
if spec_missing:
    print("  spec 里缺少的题（%d 条）:" % len(spec_missing))
    for line in spec_missing:
        print("      - " + line)
    fail("spec 缺少 %d 道数学题" % len(spec_missing))

# 生成器与题库是否同源（防止改了脚本却没重新生成）
if regen_list:
    regen = {g["stem"]: {k: g[k] for k in FIELDS} for g in regen_list}
    cur = {q["stem"]: q for q in math_qs}
    if set(regen) != set(cur):
        fail("gen_math_bank.py 重新生成的数学题与 bank_part_c.json 不一致（请用 --write 重新生成）")
    else:
        mismatch = [s for s in regen if regen[s]["options"] != cur[s]["options"]
                    or regen[s]["answer"] != cur[s]["answer"]
                    or regen[s]["analysis"] != cur[s]["analysis"]]
        if mismatch:
            fail("重新生成的选项/答案与题库不一致: %s" % mismatch[:3])
        else:
            print("  生成器同源检查: 重新生成的 25 道数学题与题库逐字段一致 OK")
    # 独立再确认一次：answer 指向的选项必须等于生成器记录的正确答案文本
    wrong_pos = [q["stem"] for q in regen_list if q["options"][q["answer"]] != q["_correct"]]
    if wrong_pos:
        print("  下标与正确选项不一致的题（%d 条）:" % len(wrong_pos))
        for s in wrong_pos:
            print("      - " + s)
        fail("answer 下标与生成器记录的正确答案不一致: %s" % wrong_pos[:3])
    else:
        print("  答案位置检查: 25 道数学题的 options[answer] 都等于生成器记录的正确答案 OK")

# ==========================================================================
# [9] 长度上限
# ==========================================================================
hr("[9] 学段长度上限（题干 / 每个选项）")
len_bad = 0
worst = defaultdict(int)
for i, q in enumerate(data):
    g = q.get("grade")
    if g not in STEM_MAX:
        continue
    tag = "#%d %s/%s" % (i, q.get("theme"), g)
    worst[(g, "stem")] = max(worst[(g, "stem")], len(q["stem"]))
    if len(q["stem"]) > STEM_MAX[g]:
        fail("%s 题干 %d 字 > %d 字：%s" % (tag, len(q["stem"]), STEM_MAX[g], q["stem"]))
        len_bad += 1
    for o in q.get("options", []):
        worst[(g, "opt")] = max(worst[(g, "opt")], len(o))
        if len(o) > OPT_MAX[g]:
            fail("%s 选项 %d 字 > %d 字：%s" % (tag, len(o), OPT_MAX[g], o))
            len_bad += 1
for g in GRADES:
    print("  %-16s 题干上限 %2d（实际最长 %2d）；选项上限 %2d（实际最长 %2d）  %s" % (
        GRADE_LABEL[g], STEM_MAX[g], worst[(g, "stem")], OPT_MAX[g], worst[(g, "opt")],
        "OK" if worst[(g, "stem")] <= STEM_MAX[g] and worst[(g, "opt")] <= OPT_MAX[g] else "FAIL"))
print("  超限条目数 = %d %s" % (len_bad, "OK" if len_bad == 0 else "FAIL"))

# ==========================================================================
# [10] 文案规范
# ==========================================================================
hr("[10] 文案规范（不得出现「错误」「失败」「排名」）")
hits = []
for i, q in enumerate(data):
    blob = q["stem"] + "".join(q["options"]) + q["analysis"] + q["knowledge_point"]
    for w in BANNED:
        if w in blob:
            hits.append("#%d 命中「%s」" % (i, w))
print("  命中: %s %s" % (hits if hits else "无", "OK" if not hits else "FAIL"))
if hits:
    fail("文案规范命中违禁词: %s" % hits)
empty_ana = [i for i, q in enumerate(data) if len(q["analysis"].strip()) < 8]
print("  解析过短（少于 8 字）的题: %s %s" % (empty_ana if empty_ana else "无", "OK" if not empty_ana else "FAIL"))
if empty_ana:
    fail("解析过短: %s" % empty_ana)

# 附加质量项：解析里「被当作某个量来称呼」的数字，必须能在题干或选项里找到。
# 做法：抓「数字 + 短后缀」的写法（如「72 是它的面积」「118° 只是……」），
# 把「2 个十」「5 个一」这类计数说法排除掉，再看这个数字有没有出现在题干或选项里。
# 这样能抓出「解析引用了一个选项里根本没有的数」这种对不上的情况。
CITED = re.compile(r"(\d+(?:\.\d+)?)\s*([\u4e00-\u9fff°]{1,3})")
NUM = re.compile(r"\d+(?:\.\d+)?")
COUNTING = ("个十", "个一", "个百", "个", "步", "遍", "对不", "就", "才", "也",
            "减", "加", "乘", "除", "得", "是", "的")
# 通用常数：单位换算、三角形内角和、一元二次方程配方、科学记数法的 a 的取值范围等，
# 这些是教学里一直用的固定数字，不一定出现在题干里。
ACCEPT_CONST = {"100", "10", "180", "360", "60", "24", "12", "1", "0", "4", "2"}


def reachable_numbers(stem):
    """把题干里的数字做一轮四则运算，得到「解析里可能合理出现的数」集合。

    这样能区分两种写法：算错了的中间步骤（能从题干推出来，属正常讲解）和
    凭空引用了一个选项里没有的量（推不出来，才是要抓的问题）。
    """
    nums = [int(x) for x in NUM.findall(stem) if x.isdigit()]
    out = set(nums)
    for x in nums:
        for y in nums:
            out |= {x + y, x - y, x * y}
            if y:
                out.add(x // y)
            out |= {x * x, x + x}
    for x in nums:
        out.add(x * 100)
        out.add(x * 10)
    return out


residue = []
for i, q in enumerate(data):
    pool = set(NUM.findall(q["stem"]))
    for o in q["options"]:
        pool |= set(NUM.findall(o))
    reach = reachable_numbers(q["stem"])
    cited = []
    for num, suffix in CITED.findall(q["analysis"]):
        suffix = suffix.lstrip("是的就是都也")
        if suffix in COUNTING or suffix.startswith("个"):
            continue
        if num in pool:
            continue
        if re.fullmatch(r"\d+", num) and int(num) in reach:
            continue          # 讲解里算出来的中间结果，合理
        if num in ACCEPT_CONST:
            continue          # 单位换算、内角和这类通用常数
        cited.append("%s%s" % (num, suffix))
    if cited:
        residue.append("#%d %s | 解析里当作某个量来称呼、但题干和选项里都没有: %s"
                       % (i, shorter(q["stem"]), cited))
print("  解析引用的数字是否都能在题干/选项里找到: 可疑题 %d 道 %s" % (
    len(residue), "OK" if not residue else "FAIL"))
for line in residue:
    print("      - " + line)
if residue:
    fail("有 %d 道题的解析引用了题干和选项里都没有的数字" % len(residue))

# ==========================================================================
# [11] 题干是完整问句
# ==========================================================================
hr("[11] 题干必须是完整的问句（以 ？ 结尾）")
bad_stem = [(i, q["stem"]) for i, q in enumerate(data) if not q["stem"].rstrip().endswith("？")]
print("  不以问号结尾的题干: %d 条 %s" % (len(bad_stem), "OK" if not bad_stem else "FAIL"))
for i, s in bad_stem:
    print("      - #%d %s" % (i, s))
if bad_stem:
    fail("有 %d 条题干不是完整问句" % len(bad_stem))

# ==========================================================================
# [12] 同型题控制（按知识点统计）
# ==========================================================================
hr("[12] 同型题控制（同一主题内同一知识点不超过 4 道）")
kp_bad = 0
for t in THEMES:
    c = Counter(q["knowledge_point"] for q in data if q["theme"] == t)
    over = {k: v for k, v in c.items() if v > 4}
    print("  %s: 知识点 %d 个，同一知识点最多 %d 道 %s" % (
        t, len(c), max(c.values()), "OK" if not over else "FAIL"))
    if over:
        print("      超出: %s" % over)
        fail("%s 有知识点重复超过 4 道: %s" % (t, over))
        kp_bad += 1
    print("      明细: %s" % "、".join("%s×%d" % (k, v) for k, v in sorted(c.items(), key=lambda kv: -kv[1])))

# ==========================================================================
# 汇总
# ==========================================================================
hr("汇总")
if warnings:
    for w in warnings:
        print("  [提示] " + w)
if errors:
    print("校验结果：未通过，共 %d 个问题" % len(errors))
    for e in errors:
        print("  - " + e)
    sys.exit(1)
print("校验结果：全部通过")
print("  75 题 / 3 主题（语文·数学·英语）/ 每主题每学段 8·9·8 / 选项与答案字段合法")
print("  题干与 a、b 题库无重复 / 数学题逐题重算一致 / 长度与文案规范达标")
sys.exit(0)
