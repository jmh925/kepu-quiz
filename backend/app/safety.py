# -*- coding: utf-8 -*-
"""内容安全过滤（基础版）：面向未成年人的输入 / 输出双重过滤。

为什么需要它：本系统用大模型给中小学生现场出题，若不过滤，
可能出现暴力、恐怖、低俗、成人向或超纲内容，这是未成年人在线产品的合规底线。

实现说明：
- 纯标准库实现（不依赖第三方包），便于单元测试与离线运行；
- 词表是「最小可用集合」，按类别组织，便于维护和替换；
- 生产环境建议替换为微信内容安全接口或更完整的词库，
  本模块的 check_input / filter_questions 接口保持不变即可平滑替换。
"""

# 最小可用黑名单：按类别组织，便于后续扩展
BLOCKED_CATEGORIES = {
    "色情低俗": ["色情", "裸体", "裸露", "做爱", "性行为", "黄色网站", "约炮", "成人视频"],
    "暴力恐怖": ["杀人", "自杀", "自残", "血腥", "恐怖袭击", "制造炸弹", "枪支制造", "虐待动物"],
    "赌博毒品": ["赌博", "赌球", "毒品", "吸毒", "冰毒", "海洛因", "大麻"],
    "违法犯罪": ["诈骗", "洗钱", "黑客攻击", "盗号", "买卖账号", "开锁技巧"],
}

MAX_TOPIC_LEN = 60

# 命中的统一提示语：面向儿童，不解释具体原因，避免诱导追问
UNSAFE_INPUT_MSG = "这个主题不太适合小朋友哦，换一个科学小知识试试看吧"


def _all_words():
    words = []
    for group in BLOCKED_CATEGORIES.values():
        words.extend(group)
    return words


def hit_word(text):
    """返回命中的敏感词；未命中返回 None。"""
    if text is None:
        return None
    t = str(text)
    if not t:
        return None
    for w in _all_words():
        if w in t:
            return w
    return None


def check_input(text):
    """校验用户输入的主题。

    返回 (是否通过, 错误原因)；
    错误原因面向儿童，不暴露具体命中的词。
    """
    if text is None or not str(text).strip():
        return False, "请输入想学习的主题"
    t = str(text).strip()
    if len(t) > MAX_TOPIC_LEN:
        return False, "主题太长啦，请控制在 %d 个字以内" % MAX_TOPIC_LEN
    if hit_word(t):
        return False, UNSAFE_INPUT_MSG
    return True, ""


def is_safe_text(*parts):
    """判断若干文本片段是否安全。"""
    for p in parts:
        if hit_word(p):
            return False
    return True


def is_safe_question(question):
    """单题安全校验：题干、选项、解析、知识点全部检查。"""
    if not isinstance(question, dict):
        return False
    texts = [
        question.get("stem", ""),
        question.get("analysis", ""),
        question.get("knowledge_point", ""),
    ]
    options = question.get("options") or []
    if isinstance(options, list):
        texts.extend([str(o) for o in options])
    return is_safe_text(*texts)


def filter_questions(questions):
    """过滤模型生成的题目。

    返回 (保留的题目列表, 被丢弃的条数)。
    丢弃后的空缺由调用方用内置题库补齐（见 llm.generate_questions）。
    """
    kept, dropped = [], 0
    for q in questions or []:
        if is_safe_question(q):
            kept.append(q)
        else:
            dropped += 1
    return kept, dropped


def unsafe_reason(question):
    """返回单题命中的敏感词，供日志排查；安全则返回 None。"""
    if not isinstance(question, dict):
        return None
    texts = [question.get("stem", ""), question.get("analysis", ""),
             question.get("knowledge_point", "")]
    texts.extend([str(o) for o in (question.get("options") or [])])
    for t in texts:
        w = hit_word(t)
        if w:
            return w
    return None
