# -*- coding: utf-8 -*-
"""学段（年级）适配：把"面向中小学生"落到可执行的出题参数上。

纯标准库实现，不依赖任何第三方包，便于单独单元测试。
设计要点：题量、题干长度、用词难度、选项长度都按学段收敛，
使"适合中小学生"从一句口号变成可校验的参数约束。
"""

DEFAULT_GRADE = "primary_high"

GRADES = {
    "primary_low": {
        "label": "小学低年级（1—3年级）",
        "short": "小学低年级",
        "count": 5,
        "max_count": 8,
        "stem_max": 25,
        "vocab": "只使用生活化、口语化的词汇，不出现专业术语，一句话只说一件事",
        "option_style": "选项用词简短，每个选项不超过 6 个字",
        "report_clause": "用小学低年级学生能听懂的话写，句子要短，多鼓励，不要出现“错误”“失败”这类词",
    },
    "primary_high": {
        "label": "小学高年级（4—6年级）",
        "short": "小学高年级",
        "count": 8,
        "max_count": 12,
        "stem_max": 40,
        "vocab": "可以使用简单科学名词（如光合作用、太阳系），但必须在解析里用一句话解释清楚",
        "option_style": "每个选项不超过 10 个字",
        "report_clause": "用小学高年级学生能听懂的话写，先肯定再提建议，不要出现“错误”“失败”这类词",
    },
    "junior": {
        "label": "初中（7—9年级）",
        "short": "初中",
        "count": 10,
        "max_count": 15,
        "stem_max": 60,
        "vocab": "可以使用学科术语（如密度、化学式、细胞结构），解析中要说明推理过程",
        "option_style": "选项可含数据或简单公式，每个不超过 16 个字",
        "report_clause": "用初中学生能接受的口吻写，讲清知识点的来龙去脉，指出下一步该补什么",
    },
}

_ALIASES = {
    "low": "primary_low", "primary_low": "primary_low", "primarylow": "primary_low",
    "小学低年级": "primary_low", "低年级": "primary_low", "1-3": "primary_low",
    "high": "primary_high", "primary_high": "primary_high", "primaryhigh": "primary_high",
    "primary": "primary_high", "小学": "primary_high", "小学高年级": "primary_high",
    "高年级": "primary_high", "4-6": "primary_high",
    "junior": "junior", "middle": "junior", "junior_high": "junior",
    "初中": "junior", "中学": "junior", "7-9": "junior",
}


def normalize_grade(grade):
    """把任意输入归一化到合法学段；无法识别时回落到默认学段。"""
    if not grade:
        return DEFAULT_GRADE
    key = str(grade).strip().lower()
    return _ALIASES.get(key, DEFAULT_GRADE)


def grade_rule(grade):
    """返回某学段的完整参数规则。"""
    return GRADES[normalize_grade(grade)]


def clamp_count(count, grade):
    """按学段限制题量，避免超出该年龄段的承受范围。"""
    rule = grade_rule(grade)
    if count is None:
        return rule["count"]
    try:
        n = int(count)
    except (TypeError, ValueError):
        return rule["count"]
    if n <= 0:
        return rule["count"]
    return max(3, min(n, rule["max_count"]))


def prompt_clause(grade):
    """拼接到出题 Prompt 中的难度约束段（编号 4—6，接在 1—3 条之后）。"""
    rule = grade_rule(grade)
    return (
        "4. 面向{label}学生：{vocab}；\n"
        "5. 题干不超过 {stem_max} 个字，{option_style}；\n"
        "6. 不得出现暴力、恐怖、低俗、成人向或超出该年龄段认知的内容。"
    ).format(
        label=rule["label"],
        vocab=rule["vocab"],
        stem_max=rule["stem_max"],
        option_style=rule["option_style"],
    )


def report_clause(grade):
    """拼接到复盘报告 Prompt 中的语气约束段。"""
    return grade_rule(grade)["report_clause"]


def list_grades():
    """供前端拉取学段选项。"""
    return [
        {"value": k, "label": v["label"], "short": v["short"], "count": v["count"]}
        for k, v in GRADES.items()
    ]
