# -*- coding: utf-8 -*-
"""内置题库：无大模型 API Key 时降级使用。

题库分两类：
- **科普主题**（天文 / 地理 / 生物 / 物理 / 化学 / 科技）：背靠"想探索什么主题"的提问式出题；
- **基础课程**（语文 / 数学 / 英语）：三大主科，学生可以直接选科目刷题。

每道题都带 grade 字段（primary_low 小学低年级 / primary_high 小学高年级 / junior 初中），
取题时按学段过滤。这一点很关键——小学低年级和初中做同一批同难度的题，
既不合适也不安全，所以「学段适配」不只是题量变化，题库本身也要分开。

题库数据在 bank_part_*.json 里，便于单独维护与校验（见 tools/check_bank_integrity.py）。
"""
import json
import os
import random

_HERE = os.path.dirname(os.path.abspath(__file__))

# 主题分组：前端据此把快捷入口分成「科普主题」与「基础课程」两块
SCIENCE_THEMES = ("天文", "地理", "生物", "物理", "化学", "科技")
BASIC_THEMES = ("语文", "数学", "英语")

# 主题 → 关键词（用于把用户输入的主题映射到题库分组）
THEME_KEYWORDS = [
    ("天文", ["天文", "宇宙", "太阳系", "行星", "恒星", "月球", "月亮", "火星", "太阳",
              "银河", "航天", "卫星", "太空", "星座", "流星", "彗星", "日食", "月食"]),
    ("地理", ["地理", "地球", "山脉", "海洋", "河流", "火山", "地震", "气候", "天气",
              "板块", "沙漠", "高原", "季风", "洋流", "岩石", "矿物"]),
    ("生物", ["生物", "植物", "动物", "细胞", "光合", "叶绿", "种子", "昆虫", "鸟类",
              "人体", "骨骼", "消化", "呼吸", "遗传", "基因", "生态", "食物链", "细菌"]),
    ("物理", ["物理", "力", "运动", "速度", "密度", "浮力", "杠杆", "滑轮", "声", "光",
              "电", "磁", "电路", "能量", "摩擦", "压强", "温度", "热"]),
    ("化学", ["化学", "分子", "原子", "元素", "化合物", "氧气", "二氧化碳", "水", "酸碱",
              "燃烧", "金属", "溶液", "化学式", "氧化", "反应"]),
    ("科技", ["科技", "计算机", "电脑", "互联网", "人工智能", "AI", "编程", "芯片", "5G",
              "机器人", "发明", "软件", "手机", "数据", "算法", "通信"]),
    # ---- 基础课程 ----
    # 关键词刻意用「语文 / 数学 / 英语」及其常见同义说法，避免与科普主题的关键词打架
    # （例如"力"属于物理，但"数学"里也有"运算"，两者不重叠）。
    ("语文", ["语文", "拼音", "汉字", "笔画", "偏旁", "成语", "古诗", "唐诗", "宋词",
              "文言文", "文言", "修辞", "比喻", "拟人", "标点", "病句", "近义词",
              "反义词", "阅读", "作文", "量词"]),
    ("数学", ["数学", "算术", "计算", "加减", "乘除", "乘法", "除法", "口算", "分数",
              "小数", "百分数", "方程", "几何", "面积", "周长", "体积", "单位换算",
              "应用题", "因数", "倍数", "函数"]),
    ("英语", ["英语", "单词", "词汇", "语法", "时态", "字母", "拼写", "英语单词",
              "现在时", "过去时", "完成时", "被动语态", "介词", "名词复数", "英文"]),
]

GRADES = ("primary_low", "primary_high", "junior")

_cache = None


def _load():
    """载入题库 JSON（带缓存）。缺文件时不崩，只是题少一些。"""
    global _cache
    if _cache is not None:
        return _cache
    groups = {}
    for name in sorted(os.listdir(_HERE)):
        if not (name.startswith("bank_part_") and name.endswith(".json")):
            continue
        try:
            with open(os.path.join(_HERE, name), "r", encoding="utf-8") as fh:
                items = json.load(fh)
        except Exception:
            continue
        for q in items:
            theme = q.get("theme")
            if not theme:
                continue
            groups.setdefault(theme, []).append(q)
    _cache = groups
    return groups


def all_questions():
    """展平为题目列表，附带主题信息。"""
    flat = []
    for theme, items in _load().items():
        for q in items:
            item = dict(q)
            item["theme"] = theme
            flat.append(item)
    return flat


def questions_by_grade(grade):
    """取某个学段的全部题目。"""
    from . import grades as grades_mod
    g = grades_mod.normalize_grade(grade)
    return [q for q in all_questions() if q.get("grade") == g]


def match_theme(user_input):
    """根据用户输入匹配主题，未命中返回 None。

    先按关键词匹配；「数学」这类基础课程的关键词不会与科普主题重叠，
    但为了稳妥，纯主题名的兜底放在关键词之后。
    """
    text = user_input or ""
    for theme, keywords in THEME_KEYWORDS:
        for kw in keywords:
            if kw in text:
                return theme
    for theme, _ in THEME_KEYWORDS:
        if theme in text:
            return theme
    return None


def theme_groups():
    """主题清单，分「科普主题 / 基础课程」两组下发（前端按分组渲染）。

    只返回**当前题库里真的有题**的主题，避免前端显示了胶囊但点进去没题。
    """
    loaded = set(_load().keys())
    return {
        "science": [t for t in SCIENCE_THEMES if t in loaded],
        "basic": [t for t in BASIC_THEMES if t in loaded],
        "labels": {"science": "科普主题", "basic": "基础课程"},
    }


def theme_category(theme):
    if theme in BASIC_THEMES:
        return "basic"
    return "science"


def counts_by_grade():
    """统计各学段题量，供自检与界面展示。"""
    out = {g: 0 for g in GRADES}
    for q in all_questions():
        g = q.get("grade")
        if g in out:
            out[g] += 1
    return out


def practice_questions(grade, theme=None, limit=None, seed=None):
    """按学段（可再加主题）抽题。

    选不到同主题的题时，退化为「该学段内的任意主题」，
    保证任何学段都能出够题——宁可换主题也不要跨学段拿超纲题。

    `seed` 给了就做**确定性抽题**：同样的 (seed, grade, theme, limit) 永远得到
    同样的题目、同样的顺序。PK 对战需要这个性质——只有所有人在同一主题下拿到
    同一份卷子，异步对手（把别人那一局的作答拿过来比）才是可比的，
    否则就是拿甲卷的答案去对乙卷，比出来毫无意义。
    """
    pool = questions_by_grade(grade)
    if theme:
        same = [q for q in pool if q.get("theme") == theme]
        if same:
            pool = same
    if seed is None:
        random.shuffle(pool)
    else:
        # 固定种子洗牌：顺序由 seed 决定，与调用时机无关
        rnd = random.Random(seed)
        pool = sorted(pool, key=lambda q: q.get("stem", ""))   # 先定序，避免依赖文件顺序
        rnd.shuffle(pool)
    return pool[:limit] if limit else pool


def paper_signature(grade, theme, limit):
    """一份 PK 卷子的指纹：用来判断两局是不是同一份题。"""
    return "pk:%s:%s:%d" % (grade, theme, limit)
