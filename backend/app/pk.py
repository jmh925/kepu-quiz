# -*- coding: utf-8 -*-
"""PK 对战：随机匹配对手，异步比谁答得准。

## 为什么是「异步幽灵」而不是实时联机

需求是「随机 PK 一个对手」。真要实时联机，得引入 WebSocket、匹配队列、
断线重连、以及两个客户端同时在线——对本系统（单进程 + SQLite + 面向课堂演示）
来说，复杂度陡增，而且**一个人在场时根本开不了局**，答辩演示直接卡住。

所以这里做的是异步对战：开局时服务端就替对手把答案定好，我答完再一起比。
对手有两个来源，按优先级：

1. **真实同学的历史战绩**（优先）：从已完成结算的 PK 局里随机抽一位**别的同学**，
   把他在同一学段 + 同一主题下的作答原样拿来当对手。这是真实数据，可复现，
   而且「我在跟隔壁班同学比」比「我在跟机器人比」有意思得多。
2. **按等级生成的机器人**（兜底）：没有可用的真实战绩时（比如库里只有一个用户、
   或者这个主题还没人打过），按我的段位生成一个正确率相当的对手。

瓶颈都注明了：真实战绩池靠 `idx_pk_pool` 索引查，不会随数据增长而变慢。

## 文案规范（面向中小学生，硬性）

不出现「失败」「排名」。输掉一局说的是「这次差一点点」，不说「你输了」；
机器人不提「电脑」「AI」这些词，就叫「神秘对手」。
"""
import json
import random
import uuid

from . import database as db
from . import levels
from . import question_bank as qb

# 每局题量：和闯关一致，按学段收敛，避免 PK 拖太久
PK_QUESTION_COUNT = {"primary_low": 5, "primary_high": 6, "junior": 8}

# 机器人正确率区间（按我的段位浮动）：既不碾压也不放水太明显
_BOT_BASE_ACCURACY = 0.52
_BOT_ACCURACY_PER_RANK = 0.045
_BOT_ACCURACY_MIN = 0.40
_BOT_ACCURACY_MAX = 0.92

# 神秘对手的名字池：不带「电脑」「机器人」字样，保持「是个人」的错觉
_BOT_NAMES = [
    "神秘的转学生", "隔壁班的小雨", "爱提问的小宇", "图书馆的常客",
    "背书包的小星", "操场上的小北", "实验室的小南", "戴眼镜的小航",
    "爱画画的小满", "总在举手的小可", "跑得最快的小飞", "笔记最工整的小然",
]

# 赢/平/负 的经验值奖励。赢了多给，平局也给一点，避免「白打一局」的挫败感。
XP_PK_WIN = 30
XP_PK_DRAW = 15
XP_PK_LOSE = 8
# 连胜额外奖励（第 2 连胜 +4，第 3 连胜 +8，之后每连胜 +8 封顶）
XP_STREAK_BONUS = 4
XP_STREAK_BONUS_MAX = 16


def _bot_name():
    return random.choice(_BOT_NAMES)


def _bot_accuracy(my_level):
    """按我的等级给出机器人正确率：等级越高，对手越强。"""
    acc = _BOT_BASE_ACCURACY + (my_level - 1) * _BOT_ACCURACY_PER_RANK
    return max(_BOT_ACCURACY_MIN, min(_BOT_ACCURACY_MAX, acc))


def _bot_answers(questions, accuracy):
    """生成机器人的作答：以 accuracy 的概率答对，其余答错（且不选到正确答案）。"""
    out = []
    for q in questions:
        right = int(q.get("answer", 0))
        n = len(q.get("options") or [])
        if n <= 1:
            out.append(right)
            continue
        if random.random() < accuracy:
            out.append(right)
        else:
            wrong_choices = [i for i in range(n) if i != right]
            out.append(random.choice(wrong_choices))
    return out


def _real_ghost(grade, theme, exclude_user_id, paper_key, total):
    """从已结算的 PK 局里找一位真实对手，把**他本人的作答**拿来当对手。

    两个必须同时满足的条件，缺一个比出来就是错的：

    1. **要取他本人的作答**（`my_answers_json`），不是他那局的对手的作答。
       早期版本取错了列，界面写着「对手是另一位同学的成绩」，拿到的却是
       那位同学遇到的机器人答案——文案在骗人。
    2. **必须是同一份卷子**（`paper_key` 相同、题量相同）。PK 的卷子由
       (学段, 主题, 题量) 确定性生成（见 question_bank.paper_signature），
       所以同主题同题量的人做的就是同一份卷。不做这个校验的话，拿甲卷的
       答案去对乙卷，比分纯属噪声。
    """
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
    return {
        "kind": "user",
        "user_id": row["user_id"],
        "name": row["nickname"] or "一位同学",
        "answers": answers,
        "source_quiz": row["match_id"],
    }


def _pick_theme(grade, theme):
    """没指定主题时，从题库里随机挑一个有该学段题目的主题（避免抽到空主题）。"""
    if theme:
        return theme
    groups = qb.theme_groups()
    all_themes = [t for t in groups["science"]] + [t for t in groups["basic"]]
    have = [t for t in all_themes if qb.practice_questions(grade, t, 1)]
    return random.choice(have) if have else (all_themes[0] if all_themes else "天文")


def start_match(user_id, grade=None, theme=None, count=None):
    """开一局 PK：定题、定对手，把对手的答案先固定下来。"""
    from . import grades as grades_mod
    g = grades_mod.normalize_grade(grade)
    theme = _pick_theme(g, theme)
    n = count or PK_QUESTION_COUNT.get(g, 6)
    n = max(3, min(10, int(n)))

    # 确定性卷子：同 (学段, 主题, 题量) 永远是同一份题、同样的顺序。
    # 这是异步对战能成立的前提——只有大家做同一份卷，把别人的作答拿来比才有意义。
    paper_key = qb.paper_signature(g, theme, n)
    questions = qb.practice_questions(g, theme, n, seed=paper_key)
    if not questions:
        return None, "这个主题在这个学段还没有题目，换一个试试"
    n = len(questions)

    # 对手：优先真实同学，其次机器人
    my_level = 1
    if user_id:
        row = db.query_one("SELECT total_xp, nickname FROM users WHERE id=?", (user_id,))
        my_level = levels.level_of((row or {}).get("total_xp") or 0)

    ghost = _real_ghost(g, theme, user_id, paper_key, n) if user_id else None
    if ghost:
        opp_answers = [int(a) if isinstance(a, int) else -1 for a in ghost["answers"]]
        opp_kind = "user"
        opp_name = ghost["name"]
        opp_user_id = ghost["user_id"]
        opp_source = ghost["source_quiz"]
        # 对手段位：按他账号的真实经验值算，让「他在哪个段位」也是真的
        other = db.query_one("SELECT total_xp FROM users WHERE id=?", (ghost["user_id"],))
        opp_xp = (other or {}).get("total_xp") or 0
        opp_rank = levels.rank_of_level(levels.level_of(opp_xp))["name"]
    else:
        acc = _bot_accuracy(my_level)
        opp_answers = _bot_answers(questions, acc)
        opp_kind = "bot"
        opp_name = _bot_name()
        opp_user_id = None
        opp_source = None
        # 机器人的段位定在比我高一档或同档，制造「有得打」的感觉
        bot_level = max(1, my_level + random.choice([0, 0, 1, 1, 2]))
        opp_rank = levels.rank_of_level(bot_level)["name"]

    # 对手答案长度对齐到本局题量：不够的按「没答」(-1) 处理
    opp_answers = (opp_answers + [-1] * n)[:n]

    # 开局就把对手的得分算出来存下，不要留到结算时才写。
    # 开局时答案已经定死了，得分就是确定的；留成默认 0 会让这一行在结算前
    # 处于自相矛盾的状态（题面重算得出 6，字段却写着 0），任何在结算前读库的
    # 地方（管理端排查、验收脚本、以后可能加的战况预览）都会被这个 0 误导。
    opp_correct = sum(1 for i, q in enumerate(questions)
                      if i < len(opp_answers) and opp_answers[i] == int(q.get("answer", 0)))

    quiz_id = uuid.uuid4().hex[:16]
    match_id = uuid.uuid4().hex[:16]

    # 复用闯关会话表存题：出题/判题的既有逻辑（含错题本维护）就能直接用
    db.execute(
        "INSERT INTO quiz_sessions(quiz_id, user_id, title, summary, user_input, grade, "
        "source, questions_json) VALUES(?,?,?,?,?,?,?,?)",
        (quiz_id, user_id, "%s · PK 对战" % theme, "", theme, g, "pk",
         db.dumps(questions)))

    db.execute(
        "INSERT INTO pk_matches(match_id, quiz_id, user_id, grade, theme, opponent_kind, "
        "opponent_user_id, opponent_name, opponent_rank, opponent_source_quiz, "
        "opponent_answers_json, opponent_correct, paper_key, total, status) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)",
        (match_id, quiz_id, user_id, g, theme, opp_kind, opp_user_id, opp_name,
         opp_rank, opp_source, db.dumps(opp_answers), opp_correct, paper_key, n))

    return {
        "match_id": match_id,
        "quiz_id": quiz_id,
        "grade": g,
        "grade_label": grades_mod.grade_rule(g)["label"],
        "theme": theme,
        "count": n,
        "opponent": {"name": opp_name, "kind": opp_kind, "rank": opp_rank},
        "questions": [_public_question(q, i) for i, q in enumerate(questions)],
    }, None


def _public_question(q, index):
    """下发给客户端的题目：不包含正确答案与解析（否则前端能直接偷看）。"""
    return {
        "id": q.get("id", index + 1),
        "index": index,
        "type": q.get("type", "single"),
        "stem": q.get("stem", ""),
        "options": q.get("options", []),
        "knowledge_point": q.get("knowledge_point", ""),
    }


def finish_match(match_id, answers, user_id=None, duration_ms=0):
    """结算：比正确题数，给经验，落战绩。"""
    row = db.query_one("SELECT * FROM pk_matches WHERE match_id=?", (match_id,))
    if not row:
        return None, "没有找到这局对战"
    if row["status"] == 1:
        return None, "这局已经结算过了"
    if user_id is not None and row["user_id"] not in (None, user_id):
        return None, "这局不是你的对战"

    quiz = db.query_one("SELECT questions_json FROM quiz_sessions WHERE quiz_id=?",
                        (row["quiz_id"],))
    if not quiz:
        return None, "题目丢失了，重新匹配一局吧"
    questions = db.loads(quiz["questions_json"]) or []
    total = len(questions)
    if total == 0:
        return None, "题目丢失了，重新匹配一局吧"

    try:
        opp_answers = json.loads(row["opponent_answers_json"] or "[]")
    except Exception:
        opp_answers = []

    my_correct = 0
    opp_correct = 0
    details = []
    for i, q in enumerate(questions):
        right = int(q.get("answer", 0))
        mine = answers[i] if i < len(answers) else -1
        theirs = opp_answers[i] if i < len(opp_answers) else -1
        ok_mine = (mine == right)
        if ok_mine:
            my_correct += 1
        if theirs == right:
            opp_correct += 1
        details.append({
            "id": q.get("id", i + 1),
            "stem": q.get("stem", ""),
            "options": q.get("options", []),
            "correct_answer": right,
            "user_answer": mine,
            "opponent_answer": theirs,
            "is_correct": ok_mine,
            "opponent_correct": (theirs == right),
            "analysis": q.get("analysis", ""),
            "knowledge_point": q.get("knowledge_point", ""),
        })

    if my_correct > opp_correct:
        result = "win"
    elif my_correct == opp_correct:
        result = "draw"
    else:
        result = "lose"

    streak = current_streak(user_id) if user_id else 0
    if result == "win":
        bonus = min(XP_STREAK_BONUS_MAX, max(0, (streak + 1 - 1)) * XP_STREAK_BONUS)
        xp = XP_PK_WIN + bonus
    elif result == "draw":
        xp = XP_PK_DRAW
    else:
        xp = XP_PK_LOSE

    if user_id:
        db.execute("UPDATE users SET total_xp=total_xp+?, "
                   "updated_at=datetime('now','localtime') WHERE id=?", (xp, user_id))

    # 存我自己的作答，长度补齐到本局题量：以后别人匹配到我时要按位对齐重放，
    # 短一截会让「按位对答案」整体错位。
    mine = []
    for i in range(total):
        v = answers[i] if i < len(answers) else -1
        mine.append(int(v) if isinstance(v, int) else -1)

    db.execute(
        "UPDATE pk_matches SET my_correct=?, opponent_correct=?, result=?, xp_gained=?, "
        "my_answers_json=?, status=1, finished_at=datetime('now','localtime') "
        "WHERE match_id=?",
        (my_correct, opp_correct, result, xp, db.dumps(mine), match_id))

    # 复用闯关的判题落库与错题本维护，保证 PK 答错的题也进错题本
    from . import services
    graded = services.submit_answer(row["quiz_id"], answers, user_id, duration_ms)

    stats = summary(user_id) if user_id else None
    return {
        "match_id": match_id,
        "result": result,
        "result_text": result_text(result),
        "my_correct": my_correct,
        "opponent_correct": opp_correct,
        "total": total,
        "xp_gained": xp,
        "streak": (streak + 1) if result == "win" else 0,
        "opponent": {"name": row["opponent_name"], "kind": row["opponent_kind"],
                     "rank": row["opponent_rank"]},
        "details": details,
        "wrong_added": (graded or {}).get("wrong_added", 0),
        "stats": stats,
    }, None


def result_text(result):
    """结算文案：面向小朋友，不出现「失败」「排名」。"""
    return {
        "win": "你赢啦！",
        "draw": "打成平手，势均力敌！",
        "lose": "这次差一点点，再来一局？",
    }.get(result, "这局结束啦")


def summary(user_id):
    """我的 PK 战绩：总场次、赢的场次、平局、连胜、最近一条。"""
    if not user_id:
        return {"matches": 0, "wins": 0, "draws": 0, "streak": 0, "best_streak": 0,
                "win_rate": 0}
    matches = int(db.scalar(
        "SELECT COUNT(*) FROM pk_matches WHERE user_id=? AND status=1", (user_id,)))
    wins = int(db.scalar(
        "SELECT COUNT(*) FROM pk_matches WHERE user_id=? AND status=1 AND result='win'",
        (user_id,)))
    draws = int(db.scalar(
        "SELECT COUNT(*) FROM pk_matches WHERE user_id=? AND status=1 AND result='draw'",
        (user_id,)))
    best = 0
    run = 0
    for r in db.query("SELECT result FROM pk_matches WHERE user_id=? AND status=1 "
                      "ORDER BY id", (user_id,)):
        if r["result"] == "win":
            run += 1
            best = max(best, run)
        else:
            run = 0
    return {
        "matches": matches,
        "wins": wins,
        "draws": draws,
        "streak": current_streak(user_id),
        "best_streak": best,
        "win_rate": int(round(wins * 100.0 / matches)) if matches else 0,
    }


def current_streak(user_id):
    """当前连胜：从最新一局往前数，遇到非 win 就停。"""
    if not user_id:
        return 0
    run = 0
    for r in db.query("SELECT result FROM pk_matches WHERE user_id=? AND status=1 "
                      "ORDER BY id DESC LIMIT 50", (user_id,)):
        if r["result"] == "win":
            run += 1
        else:
            break
    return run


def history(user_id, limit=10):
    """最近的 PK 记录，给前端画战绩列表。"""
    if not user_id:
        return []
    return db.query(
        "SELECT match_id, theme, grade, opponent_name, opponent_kind, opponent_rank, "
        "my_correct, opponent_correct, total, result, xp_gained, finished_at "
        "FROM pk_matches WHERE user_id=? AND status=1 ORDER BY id DESC LIMIT ?",
        (user_id, int(limit)))
