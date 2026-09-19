# -*- coding: utf-8 -*-
"""大模型调用层：有 DeepSeek Key 走真 AI 出题 / 报告，无 Key 自动降级内置题库。

对应论文 4.6 节「出题与检索增强链路」：
    主题预处理（内容安全校验）→ 可选文档检索 → 按学段组装 Prompt →
    调用 DeepSeek → JSON 解析与字段归一化 → 不合规题目过滤 →
    用题库补齐题量 → 失败整体降级内置题库

面向未成年人的两处加固：
1. 学段适配（grades）：题量、题干长度、用词难度按学段收敛，使「适合中小学生」可校验；
2. 内容安全（safety）：模型生成的题目先过安全过滤与长度过滤，
   不合规的题目直接丢弃，并由题库补齐题量，保证体验不塌。
"""
import json
import random
import re

import httpx

from . import grades
from . import safety
from .config import settings
from .question_bank import all_questions, match_theme

QUIZ_PROMPT = """你是一名面向中小学生的科普出题老师。请围绕主题「{topic}」生成 {count} 道科普闯关题。
要求：
1. 题型为单选题（type=single），每道题 4 个选项，只有 1 个正确答案；
2. 题目要科学准确、通俗有趣；
3. 每题给出简明易懂的解析 analysis 和对应知识点 knowledge_point；
{grade_clause}
7. 只输出 JSON，不要输出任何其他文字。格式如下：
{{"title":"{topic}","questions":[{{"type":"single","stem":"题干","options":["选项A","选项B","选项C","选项D"],"answer":0,"analysis":"解析","knowledge_point":"知识点"}}]}}
注意 answer 是正确选项的下标（0~3）。"""

REPORT_PROMPT = """你是一名学习复盘教练。根据下面的答题情况，生成一份面向中小学生的复盘报告。
答题情况：共 {total} 题，答对 {correct} 题，正确率 {accuracy}%。
薄弱知识点：{weak}
语气要求：{report_clause}。
请只输出 JSON，格式：
{{"mastery":0,"weak_points":["薄弱知识点"],"summary":"三句话知识总结","suggestion":"下一步学习建议"}}
其中 mastery 是 0~100 的掌握度评分。"""

# 题干长度容忍倍数：模型常有轻微超出，超过该倍数才判为超纲并丢弃
STEM_TOLERANCE = 2.0


def _call_llm(prompt: str) -> str:
    """调用 DeepSeek（OpenAI 兼容 /chat/completions 接口）。"""
    url = settings.deepseek_base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": "Bearer %s" % settings.deepseek_api_key,
               "Content-Type": "application/json"}
    payload = {
        "model": settings.deepseek_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": 4000,
    }
    with httpx.Client(timeout=settings.deepseek_timeout) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def _extract_json(text: str):
    """从模型输出中稳健地提取 JSON（容忍代码块标记与前后废话）。"""
    text = (text or "").strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(text[start:end + 1])
        raise


def _pool_questions(theme, count, exclude_stems=None):
    """从管理端维护的题目资源池取题（管理端启用后优先命中）。"""
    try:
        from . import database as db
        sql = "SELECT * FROM question_pool WHERE enabled=1"
        params = []
        if theme:
            sql += " AND theme=?"
            params.append(theme)
        rows = db.query(sql, tuple(params))
    except Exception:
        return []
    exclude = set(exclude_stems or [])
    picked = []
    for r in rows:
        if r["stem"] in exclude:
            continue
        picked.append({
            "type": "single", "stem": r["stem"],
            "options": json.loads(r["options_json"] or "[]"),
            "answer": r["answer"], "analysis": r["analysis"],
            "knowledge_point": r["knowledge_point"], "theme": r["theme"],
        })
    random.shuffle(picked)
    return picked[:count]


def _bank_questions(topic, count, exclude_stems=None):
    """从题库取题：优先「资源池 → 内置同主题 → 内置其他主题」，保证题量体验。"""
    theme = match_theme(topic)
    exclude = set(exclude_stems or [])
    picked = _pool_questions(theme, count, exclude)

    if len(picked) < count:
        pool = [q for q in all_questions() if q.get("stem") not in exclude]
        same = [q for q in pool if theme and q.get("theme") == theme]
        other = [q for q in pool if not (theme and q.get("theme") == theme)]
        need = count - len(picked)
        picked.extend(random.sample(same, min(need, len(same))))
        need = count - len(picked)
        if need > 0 and other:
            picked.extend(random.sample(other, min(need, len(other))))
    return picked


def generate_questions(topic: str, count=None, grade=None):
    """出题：优先 DeepSeek；失败 / 无 Key / 内容不合规 时降级题库。

    返回结构中的 source 字段标明题目来源（ai / bank），便于前端如实展示与测试断言。
    """
    g = grades.normalize_grade(grade)
    rule = grades.grade_rule(g)
    count = grades.clamp_count(count, g)

    if settings.deepseek_api_key:
        try:
            raw = _call_llm(QUIZ_PROMPT.format(
                topic=topic, count=count, grade_clause=grades.prompt_clause(g)))
            data = _extract_json(raw)
            cleaned = []
            for i, q in enumerate(data.get("questions") or []):
                if not isinstance(q, dict):
                    continue
                q["id"] = i + 1
                q.setdefault("type", "single")
                q.setdefault("knowledge_point", "科普知识")
                cleaned.append(q)

            # 第一层过滤：内容安全
            cleaned, dropped_unsafe = safety.filter_questions(cleaned)
            # 第二层过滤：题干长度（远超该学段承受范围视为超纲）
            limit = int(rule["stem_max"] * STEM_TOLERANCE)
            before = len(cleaned)
            cleaned = [q for q in cleaned if len(str(q.get("stem", ""))) <= limit]
            dropped_long = before - len(cleaned)
            cleaned = cleaned[:count]

            if cleaned:
                # 被过滤掉的题目用题库补齐，保证题量与体验
                if len(cleaned) < count:
                    extra = _bank_questions(
                        topic, count - len(cleaned),
                        exclude_stems=[q.get("stem") for q in cleaned])
                    for j, q in enumerate(extra):
                        q["id"] = len(cleaned) + j + 1
                    cleaned.extend(extra)
                return {"title": data.get("title") or topic, "questions": cleaned,
                        "source": "ai", "grade": g,
                        "dropped_unsafe": dropped_unsafe, "dropped_long": dropped_long}
            # 全部不合规 → 落到题库
        except Exception:
            pass

    # 题库降级
    picked = _bank_questions(topic, count)
    for i, q in enumerate(picked):
        q["id"] = i + 1
    theme = match_theme(topic)
    return {"title": topic or (theme or "科普知识闯关"),
            "questions": picked, "source": "bank", "grade": g,
            "dropped_unsafe": 0, "dropped_long": 0}


def generate_report(total, correct, weak_points, mastery=None, grade=None):
    """复盘报告：优先 DeepSeek，失败或内容不合规时降级规则模板。"""
    accuracy = round(correct / total * 100, 1) if total else 0
    weak = "、".join(weak_points) if weak_points else "无"
    g = grades.normalize_grade(grade)

    if settings.deepseek_api_key:
        try:
            raw = _call_llm(REPORT_PROMPT.format(
                total=total, correct=correct, accuracy=accuracy, weak=weak,
                report_clause=grades.report_clause(g)))
            data = _extract_json(raw)
            data.setdefault("mastery", mastery if mastery is not None else int(accuracy))
            data.setdefault("weak_points", weak_points)
            data.setdefault("summary", "继续加油，巩固薄弱知识点！")
            data.setdefault("suggestion", "建议针对错题对应的知识点进行复习。")
            # 报告直接给孩子看，同样要过安全过滤
            if safety.is_safe_text(data.get("summary", ""), data.get("suggestion", "")):
                data["source"] = "ai"
                data["grade"] = g
                return data
        except Exception:
            pass

    # 规则生成降级：按正确率分档
    if mastery is None:
        mastery = int(accuracy)
    if accuracy >= 90:
        level, summary = "优秀", "你已经掌握了绝大部分知识点，表现非常出色，继续保持！"
    elif accuracy >= 70:
        level, summary = "良好", "整体掌握得不错，个别知识点还需加强，再接再厉！"
    elif accuracy >= 50:
        level, summary = "及格", "基本概念已了解，但还有不少薄弱环节，需要系统复习。"
    else:
        level, summary = "待加强", "这次闯关有些吃力，建议从基础概念开始，多练多记。"
    suggestion = "建议针对薄弱知识点（%s）进行针对性复习，然后再次闯关检验学习效果。" % weak
    return {
        "mastery": mastery,
        "level": level,
        "weak_points": weak_points,
        "summary": summary,
        "suggestion": suggestion,
        "source": "rule",
        "grade": g,
    }
