# -*- coding: utf-8 -*-
"""把附录Ⅰ（核心代码）与附录Ⅱ（接口与测试记录）写进 Word。

做法：在「附 录」标题之后依次插入段落与表格，沿用文档已有的 Normal 样式；
代码段落用等宽字体 Consolas 9 磅，表格用三线表样式（Table Grid 之后再请你调边框）。
"""
import copy
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.text.paragraph import Paragraph

SRC = r"E:\dev\kepu-quiz\work\修改版.docx"

CODE1 = """def generate_questions(topic, count=None, grade=None):
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
            cleaned = [q for q in cleaned if len(str(q.get("stem", ""))) <= limit]
            cleaned = cleaned[:count]

            if cleaned:
                # 被过滤掉的题目用题库补齐，保证题量
                if len(cleaned) < count:
                    extra = _bank_questions(
                        topic, count - len(cleaned),
                        exclude_stems=[q.get("stem") for q in cleaned], grade=g)
                    cleaned.extend(extra)
                return {"title": data.get("title") or topic,
                        "questions": cleaned, "source": "ai"}
        except Exception:
            pass

    # 降级：内置题库按主题与学段抽题
    return {"title": topic, "questions": _bank_questions(topic, count, grade=g),
            "source": "bank"}"""

CODE2 = """def submit_answer(quiz_id, answers, user_id=None, duration_ms=0):
    row = db.query_one("SELECT * FROM quiz_sessions WHERE quiz_id=?", (quiz_id,))
    if not row:
        return None
    questions = db.loads(row["questions_json"]) or []
    total = len(questions)
    correct = 0
    details = []
    for i, q in enumerate(questions):
        user_ans = answers[i] if i < len(answers) else -1
        right = int(q.get("answer", 0))
        is_correct = (user_ans == right)
        if is_correct:
            correct += 1
        details.append({
            "id": q.get("id", i + 1),
            "stem": q.get("stem", ""),
            "options": q.get("options", []),
            "user_answer": user_ans,
            "correct_answer": right,
            "is_correct": is_correct,
            "analysis": q.get("analysis", ""),
            "knowledge_point": q.get("knowledge_point", ""),
        })
    accuracy = round(correct / total * 100, 1) if total else 0
    db.execute(
        "INSERT OR REPLACE INTO answer_records(quiz_id, user_id, records_json, "
        "total_questions, correct_count, accuracy, duration_ms) VALUES(?,?,?,?,?,?,?)",
        (quiz_id, user_id, db.dumps(details), total, correct, accuracy,
         int(duration_ms or 0)))

    # 经验值结算：完成闯关 +10，每答对一题 +2
    xp = XP_FINISH + correct * XP_PER_CORRECT
    if user_id:
        db.execute("UPDATE users SET total_xp=total_xp+?, "
                   "updated_at=datetime('now','localtime') WHERE id=?", (xp, user_id))

    # 错题本维护：答错入库并累加次数；答对视为已掌握，从错题本移除
    added = wrongbook.record_wrong(user_id, quiz_id, details)
    mastered = wrongbook.mark_mastered(user_id, details)

    return {"quiz_id": quiz_id, "total": total, "correct": correct,
            "accuracy": accuracy, "xp_gained": xp,
            "wrong_added": added, "mastered": mastered}"""

CODE3 = """def _real_ghost(grade, theme, exclude_user_id, paper_key, total):
    rows = db.query(
        "SELECT p.match_id, p.user_id, p.my_answers_json, p.my_correct, p.total, "
        "u.nickname FROM pk_matches p LEFT JOIN users u ON u.id = p.user_id "
        "WHERE p.status=1 AND p.grade=? AND p.theme=? AND p.user_id IS NOT NULL "
        "AND p.user_id != ? AND p.paper_key=? AND p.total=? "
        "AND p.my_answers_json != '[]' "
        "ORDER BY p.id DESC LIMIT 40",
        (grade, theme, exclude_user_id or -1, paper_key, total))
    if not rows:
        return None
    row = random.choice(rows)
    try:
        answers = json.loads(row["my_answers_json"])
    except Exception:
        return None
    if not isinstance(answers, list) or len(answers) != total:
        return None
    return {"kind": "user", "user_id": row["user_id"],
            "name": row["nickname"] or "一位同学",
            "answers": answers, "source_quiz": row["match_id"]}"""

CODE4 = """XP_PER_LEVEL = 50

def progress(total_xp):
    xp = max(0, int(total_xp or 0))
    level = level_of(xp)
    rank = rank_of_level(level)
    nxt = next_rank(level)

    in_level = xp % XP_PER_LEVEL
    level_progress = {
        "level": level,
        "xp_in_level": in_level,
        "xp_per_level": XP_PER_LEVEL,
        "xp_to_next_level": XP_PER_LEVEL - in_level,
        "percent": int(round(in_level * 100.0 / XP_PER_LEVEL)),
    }
    return {"level": level, "rank": rank, "level_progress": level_progress,
            "next_rank": nxt, "rank_progress": rank_progress}"""

API_STU = [
    ("1", "GET", "/api/v1/health", "服务健康检查"),
    ("2", "GET", "/api/v1/grades", "学段列表与规则"),
    ("3", "GET", "/api/v1/themes", "主题清单（科普与基础课程分组）"),
    ("4", "GET", "/api/v1/levels", "段位阶梯与当前进度"),
    ("5", "POST", "/api/v1/quiz/generate", "按学段与主题出题"),
    ("6", "POST", "/api/v1/quiz/submit", "提交作答并结算"),
    ("7", "POST", "/api/v1/report/generate", "生成复盘报告"),
    ("8", "POST", "/api/v1/user/register", "学生注册"),
    ("9", "POST", "/api/v1/user/login", "学生登录"),
    ("10", "POST", "/api/v1/user/guest", "免注册体验"),
    ("11", "POST", "/api/v1/user/merge-guest", "游客数据并入账号"),
    ("12", "GET", "/api/v1/user/profile", "个人中心数据"),
    ("13", "POST", "/api/v1/knowledge/documents", "上传或粘贴讲义"),
    ("14", "GET", "/api/v1/knowledge/documents", "讲义列表"),
    ("15", "DELETE", "/api/v1/knowledge/documents/{doc_id}", "删除讲义"),
    ("16", "GET", "/api/v1/wrong/questions", "错题列表"),
    ("17", "POST", "/api/v1/wrong/practice", "只练错题组卷"),
    ("18", "DELETE", "/api/v1/wrong/questions", "清空错题本"),
    ("19", "PUT", "/api/v1/wrong/questions", "修改错题内容"),
    ("20", "DELETE", "/api/v1/wrong/questions/item", "删除单条错题"),
    ("21", "DELETE", "/api/v1/wrong/questions/{stem}", "按题干删除错题"),
    ("22", "POST", "/api/v1/pk/start", "发起同伴对战"),
    ("23", "POST", "/api/v1/pk/finish", "结算同伴对战"),
    ("24", "GET", "/api/v1/pk/stats", "对战战绩统计"),
]
API_ADM = [
    ("1", "POST", "/api/v1/admin/login", "管理员登录"),
    ("2", "GET", "/api/v1/admin/me", "当前管理员信息"),
    ("3", "GET", "/api/v1/admin/dashboard", "运行看板"),
    ("4", "GET", "/api/v1/admin/trend", "数据趋势"),
    ("5", "GET", "/api/v1/admin/users", "用户列表"),
    ("6", "GET", "/api/v1/admin/users/{user_id}", "用户详情与学情分类"),
    ("7", "POST", "/api/v1/admin/users/{user_id}/status", "启用或停用账号"),
    ("8", "GET", "/api/v1/admin/questions", "题库列表"),
    ("9", "GET", "/api/v1/admin/questions/themes", "题库主题清单"),
    ("10", "POST", "/api/v1/admin/questions", "新增题目"),
    ("11", "PUT", "/api/v1/admin/questions/{qid}", "修改题目"),
    ("12", "DELETE", "/api/v1/admin/questions/{qid}", "删除题目"),
    ("13", "GET", "/api/v1/admin/sessions", "闯关记录列表"),
    ("14", "GET", "/api/v1/admin/logs", "操作日志"),
]
TEST_ROWS = [
    ("1", "后端冒烟测试", "49 条用例，重复执行 3 次", "通过"),
    ("2", "管理端接口联通性", "登录、看板、趋势、用户、题库增删改查、日志共 9 项", "通过"),
    ("3", "前端静态检查", "页面结构、脚本引用、资源类型", "通过"),
    ("4", "错题本增删改查", "接口层 15 项检查", "通过"),
    ("5", "题库完整性与学段分离", "225 道题的去重、选项、答案分布、长度、答案与解析一致性", "通过"),
    ("6", "学段分级出题", "小学低年级与初中题干无交集", "通过"),
    ("7", "文档一致性检查", "交付文档与系统实际数据一致", "通过"),
    ("8", "网页端端到端", "真实浏览器完成注册、答题、复盘、错题全流程并截图", "通过"),
    ("9", "账号与错题收录", "注册、登录、答题后错题正确入库", "通过"),
    ("10", "管理端答题详情分类", "六个分类区块数据正确", "通过"),
    ("11", "默认口令轮换自检", "项目公开的默认口令已失效", "通过"),
    ("12", "批处理文件编码自检", "批处理文件为纯 ASCII", "通过"),
    ("13", "基础课程题库自检", "语文、数学、英语共 75 题，数学题逐题重算", "通过"),
    ("14", "基础课程可用性", "不串科目、学段适配、首页入口展示", "通过"),
    ("15", "段位阶梯", "段位换算、边界值、成长阶梯页展示", "通过"),
    ("16", "同伴对战全流程", "匹配、试卷一致性、结算、对手来源可追溯", "通过"),
    ("17", "界面与渲染审计", "四种视口下的溢出、越界、触摸目标、截断、对比度", "通过"),
]


def main():
    doc = Document(SRC)
    body = doc.element.body
    paras = [c for c in body.iterchildren() if c.tag == qn("w:p")]
    P = [Paragraph(e, doc) for e in paras]

    # 定位「附 录」标题
    ap = None
    for i, p in enumerate(P):
        if p.style and p.style.name.startswith("Heading") and "附" in p.text and "录" in p.text:
            ap = p
            print("  找到附录标题：段%d「%s」" % (i, p.text.strip()))
            break
    if ap is None:
        print("  [FAIL] 未找到附录标题")
        return 1

    anchor = ap._element
    tmpl = None
    for p in P:
        if p.style and p.style.name == "Normal" and p.text.strip():
            tmpl = p._element
            break

    def add_para(text, bold=False, mono=False, size=10.5, center=False, space_before=0):
        nonlocal anchor
        el = copy.deepcopy(tmpl)
        anchor.addnext(el)
        anchor = el
        np = Paragraph(el, doc)
        for r in np.runs[1:]:
            r.text = ""
        if np.runs:
            np.runs[0].text = ""
        run = np.runs[0] if np.runs else np.add_run()
        run.text = text
        run.font.bold = bold
        run.font.size = Pt(size)
        if mono:
            run.font.name = "Consolas"
            run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
        if center:
            np.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pf = np.paragraph_format
        pf.space_before = Pt(space_before)
        pf.space_after = Pt(3)
        pf.first_line_indent = Pt(0)
        return np

    def add_table(headers, rows, widths=None):
        nonlocal anchor
        t = doc.add_table(rows=1, cols=len(headers))
        t.style = "Table Grid"
        for i, h in enumerate(headers):
            cell = t.rows[0].cells[i]
            cell.text = ""
            r = cell.paragraphs[0].add_run(h)
            r.font.bold = True
            r.font.size = Pt(9)
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        for row in rows:
            cells = t.add_row().cells
            for i, v in enumerate(row):
                cells[i].text = ""
                r = cells[i].paragraphs[0].add_run(v)
                r.font.size = Pt(9)
        anchor.addnext(t._tbl)
        anchor = t._tbl
        # 表格后补一个空段落，避免两表相连
        add_para("", size=6)
        return t

    print("=== 写 附录Ⅰ 核心代码 ===")
    add_para("附录Ⅰ 核心代码", bold=True, size=14, center=True, space_before=12)
    add_para("以下列出系统实现中的四段核心代码。为便于阅读，省略了与说明内容无关的异常处理与日志输出。",
             space_before=6)
    for title, code in [("一、出题与降级", CODE1), ("二、判题与经验值结算", CODE2),
                        ("三、同伴对战的真人对手选取", CODE3), ("四、段位进度计算", CODE4)]:
        add_para(title, bold=True, space_before=10)
        for line in code.split("\n"):
            add_para(line if line else " ", mono=True, size=9)
        print("  " + title)

    print("=== 写 附录Ⅱ 接口与测试记录 ===")
    add_para("附录Ⅱ 接口与测试记录", bold=True, size=14, center=True, space_before=16)
    add_para("一、接口清单", bold=True, space_before=8)
    add_para("系统接口共 38 个，统一使用 /api/v1 前缀，响应格式为 {code, message, data}。"
             "学生端 24 个，见表Ⅱ-1；管理端 14 个，请求需携带管理令牌，见表Ⅱ-2。")
    add_para("表Ⅱ-1 学生端接口", bold=True, size=10.5, center=True, space_before=8)
    add_table(["序号", "方法", "路径", "说明"], API_STU)
    add_para("表Ⅱ-2 管理端接口", bold=True, size=10.5, center=True, space_before=8)
    add_table(["序号", "方法", "路径", "说明"], API_ADM)
    add_para("二、测试记录", bold=True, space_before=10)
    add_para("系统的整体验收流程共 17 项检查，结果见表Ⅱ-3。")
    add_para("表Ⅱ-3 系统验收测试记录", bold=True, size=10.5, center=True, space_before=8)
    add_table(["序号", "检查项", "主要内容", "结果"], TEST_ROWS)
    add_para("测试汇总结果为 17 项检查全部通过，未通过 0 项。", space_before=6)

    doc.save(SRC)
    print()
    print("已保存：%s" % SRC)
    return 0


if __name__ == "__main__":
    sys.exit(main())
