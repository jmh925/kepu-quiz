# -*- coding: utf-8 -*-
"""内置科普题库：无大模型 API Key 时降级使用。

覆盖天文 / 地理 / 生物 / 物理 / 化学 / 科技六大主题，**并按学段分级**：
每道题都带 grade 字段（primary_low 小学低年级 / primary_high 小学高年级 / junior 初中），
取题时按学段过滤。这一点很关键——小学低年级和初中做同一批同难度的题，
既不合适也不安全，所以「学段适配」不只是题量变化，题库本身也要分开。

题库数据在 bank_part_*.json 里，便于单独维护与校验（见 tools/check_question_bank.py）。
"""
import json
import os
import random

_HERE = os.path.dirname(os.path.abspath(__file__))

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
    """根据用户输入匹配主题，未命中返回 None。"""
    text = user_input or ""
    best = None
    for theme, keywords in THEME_KEYWORDS:
        for kw in keywords:
            if kw in text:
                return theme
        # 没有精确命中时，记录「主题名本身出现在输入里」的兜底
        if theme in text and best is None:
            best = theme
    return best


def counts_by_grade():
    """统计各学段题量，供自检与界面展示。"""
    out = {g: 0 for g in GRADES}
    for q in all_questions():
        g = q.get("grade")
        if g in out:
            out[g] += 1
    return out


def practice_questions(grade, theme=None, limit=None):
    """按学段（可再加主题）抽题。

    选不到同主题的题时，退化为「该学段内的任意主题」，
    保证任何学段都能出够题——宁可换主题也不要跨学段拿超纲题。
    """
    pool = questions_by_grade(grade)
    if theme:
        same = [q for q in pool if q.get("theme") == theme]
        if same:
            pool = same
    random.shuffle(pool)
    return pool[:limit] if limit else pool
