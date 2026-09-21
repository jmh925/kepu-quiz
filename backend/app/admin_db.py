# -*- coding: utf-8 -*-
"""管理端数据访问层：账号、题库资源池、运行统计、操作日志。

安全设计（对应论文 4.8 节）：
- 口令不存明文：PBKDF2-HMAC-SHA256 + 每账号独立随机盐，迭代 12 万次；
- 登录失败锁定：连续失败达阈值后锁定一段时间，抵御口令爆破；
- 登录成功后签发管理端 Token（带过期时间），后续请求走 X-Admin-Token 头；
- 所有写操作记入 admin_logs，便于审计。
"""
import hashlib
import hmac
import os
import secrets
import time

import jwt as pyjwt

from . import database as db
from .config import settings

PBKDF2_ROUNDS = 120000

# 登录失败计数：{username: [失败次数, 锁定截止时间戳]}
_fail_state = {}


# ---------------- 口令 ----------------
def hash_password(password, salt=None):
    """返回 (hash_hex, salt_hex)。"""
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                             bytes.fromhex(salt), PBKDF2_ROUNDS)
    return dk.hex(), salt


def verify_password(password, hash_hex, salt_hex):
    calc, _ = hash_password(password, salt_hex)
    return hmac.compare_digest(calc, hash_hex)


# ---------------- 账号 ----------------
def ensure_default_admin():
    """首次启动时按配置创建默认管理员（幂等）。

    配置里的口令是**权威来源**：如果库里已存在的账号口令与当前配置对不上，
    就按配置重算哈希并写回。

    为什么要这样改：原来只判「用户名是否存在」，存在就直接 return，
    于是把 ADMIN_PASSWORD 改掉再重启完全不起作用——库里还是老口令的哈希。
    这个坑很隐蔽也很危险：有人以为改了 .env 就安全了，实际上公开仓库里那个
    默认口令照样能登进管理端（管理端能看所有学生的答题记录、能改题库）。
    现在「改 .env → 重启 → 生效」是真的成立的。

    管理端没有改口令的界面，口令只可能来自配置，所以这样覆盖不会顶掉别处设的值。
    """
    row = db.query_one("SELECT * FROM admins WHERE username=?", (settings.admin_username,))
    if not row:
        pw_hash, salt = hash_password(settings.admin_password)
        db.execute("INSERT INTO admins(username, password_hash, salt, role) VALUES(?,?,?,?)",
                   (settings.admin_username, pw_hash, salt, "admin"))
        return True
    if not verify_password(settings.admin_password, row["password_hash"], row["salt"]):
        pw_hash, salt = hash_password(settings.admin_password)
        db.execute("UPDATE admins SET password_hash=?, salt=? WHERE id=?",
                   (pw_hash, salt, row["id"]))
        log(settings.admin_username, "admin.password_sync",
            "按配置更新管理员口令（原库存口令与配置不一致）")
        return True
    return False


def locked_seconds(username):
    """返回剩余锁定秒数；未锁定时返回 0。"""
    state = _fail_state.get(username)
    if not state:
        return 0
    remain = int(state[1] - time.time())
    return remain if remain > 0 else 0


def admin_login(username, password):
    """管理端登录：返回 (token, admin) 或 (None, 错误信息)。"""
    remain = locked_seconds(username)
    if remain > 0:
        return None, "口令连续输入有误，请 %d 秒后再试" % remain

    row = db.query_one("SELECT * FROM admins WHERE username=?", (username,))
    if not row or not verify_password(password, row["password_hash"], row["salt"]):
        state = _fail_state.setdefault(username, [0, 0])
        state[0] += 1
        if state[0] >= settings.admin_max_fail:
            state[1] = time.time() + settings.admin_lock_seconds
            state[0] = 0
            return None, "口令连续输入有误，请 %d 秒后再试" % settings.admin_lock_seconds
        return None, "账号或口令不正确"

    _fail_state.pop(username, None)
    token = pyjwt.encode(
        {"sub": row["username"], "role": row["role"],
         "exp": int(time.time()) + 2 * 3600},
        settings.jwt_secret, algorithm="HS256")
    log(row["username"], "login", "登录管理端")
    return token, {"username": row["username"], "role": row["role"]}


def admin_token_is_configured(token):
    """兼容用固定 Token 直连（便于自动化测试与本地调试）。"""
    return bool(token) and hmac.compare_digest(token, settings.admin_token)


def verify_admin_token(token):
    """校验管理端 Token：支持「固定 Token」与「登录签发的 JWT」两种。"""
    if not token:
        return None
    if admin_token_is_configured(token):
        return {"username": settings.admin_username, "role": "admin"}
    try:
        payload = pyjwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        if payload.get("role"):
            return {"username": payload.get("sub"), "role": payload["role"]}
    except Exception:
        return None
    return None


def log(username, action, detail=""):
    db.execute("INSERT INTO admin_logs(username, action, detail) VALUES(?,?,?)",
               (username, action, detail))


# ---------------- 题库资源池 ----------------
def list_pool(theme=None, grade=None, keyword=None, page=1, size=20):
    where, params = ["1=1"], []
    if theme:
        where.append("theme=?")
        params.append(theme)
    if grade:
        where.append("grade=?")
        params.append(grade)
    if keyword:
        where.append("(stem LIKE ? OR knowledge_point LIKE ?)")
        params += ["%" + keyword + "%", "%" + keyword + "%"]
    clause = " AND ".join(where)
    total = int(db.scalar("SELECT COUNT(*) FROM question_pool WHERE " + clause, tuple(params)))
    offset = max(0, (int(page) - 1) * int(size))
    rows = db.query(
        "SELECT * FROM question_pool WHERE " + clause +
        " ORDER BY id DESC LIMIT ? OFFSET ?", tuple(params) + (int(size), offset))
    items = []
    for r in rows:
        items.append({
            "id": r["id"], "theme": r["theme"], "grade": r["grade"], "stem": r["stem"],
            "options": db.loads(r["options_json"]) or [], "answer": r["answer"],
            "analysis": r["analysis"], "knowledge_point": r["knowledge_point"],
            "difficulty": r["difficulty"], "enabled": r["enabled"],
            "created_at": r["created_at"],
        })
    return {"items": items, "total": total, "page": int(page), "size": int(size)}


def create_pool_question(payload, username="admin"):
    stem = (payload.get("stem") or "").strip()
    options = payload.get("options") or []
    if not stem or len(options) < 2:
        return None, "题干与选项不能为空（至少 2 个选项）"
    answer = int(payload.get("answer") or 0)
    if answer < 0 or answer >= len(options):
        return None, "正确答案下标超出选项范围"
    qid = db.execute(
        "INSERT INTO question_pool(theme, grade, stem, options_json, answer, analysis, "
        "knowledge_point, difficulty, enabled) VALUES(?,?,?,?,?,?,?,?,?)",
        (payload.get("theme") or "通用", payload.get("grade") or "primary_high", stem,
         db.dumps(options), answer, payload.get("analysis") or "",
         payload.get("knowledge_point") or "科普知识",
         int(payload.get("difficulty") or 2), 1 if payload.get("enabled", 1) else 0))
    log(username, "pool.create", "新增题目 #%s" % qid)
    return qid, None


def update_pool_question(qid, payload, username="admin"):
    row = db.query_one("SELECT * FROM question_pool WHERE id=?", (qid,))
    if not row:
        return False, "题目不存在"
    fields, params = [], []
    mapping = [("theme", "theme"), ("grade", "grade"), ("stem", "stem"),
               ("answer", "answer"), ("analysis", "analysis"),
               ("knowledge_point", "knowledge_point"), ("difficulty", "difficulty"),
               ("enabled", "enabled")]
    for key, column in mapping:
        if key in payload and payload[key] is not None:
            fields.append(column + "=?")
            params.append(payload[key])
    if "options" in payload and payload["options"]:
        fields.append("options_json=?")
        params.append(db.dumps(payload["options"]))
    if not fields:
        return False, "没有需要更新的字段"
    params.append(qid)
    db.execute("UPDATE question_pool SET " + ", ".join(fields) + " WHERE id=?", tuple(params))
    log(username, "pool.update", "修改题目 #%s" % qid)
    return True, None


def delete_pool_question(qid, username="admin"):
    row = db.query_one("SELECT id FROM question_pool WHERE id=?", (qid,))
    if not row:
        return False
    db.execute("DELETE FROM question_pool WHERE id=?", (qid,))
    log(username, "pool.delete", "删除题目 #%s" % qid)
    return True


def pool_themes():
    rows = db.query("SELECT theme, COUNT(*) AS c FROM question_pool GROUP BY theme ORDER BY c DESC")
    return [{"theme": r["theme"], "count": r["c"]} for r in rows]


# ---------------- 运行统计 ----------------
def dashboard():
    """管理端首页看板：核心运行指标一次取全。"""
    today = "date(created_at)=date('now','localtime')"
    return {
        "users": {
            "total": int(db.scalar("SELECT COUNT(*) FROM users")),
            "active": int(db.scalar("SELECT COUNT(*) FROM users WHERE status=1")),
            "today_new": int(db.scalar("SELECT COUNT(*) FROM users WHERE " + today)),
        },
        "quizzes": {
            "total": int(db.scalar("SELECT COUNT(*) FROM quiz_sessions")),
            "today": int(db.scalar("SELECT COUNT(*) FROM quiz_sessions WHERE " + today)),
            "by_source": db.query(
                "SELECT source, COUNT(*) AS c FROM quiz_sessions GROUP BY source"),
        },
        "answers": {
            "submitted": int(db.scalar("SELECT COUNT(*) FROM answer_records")),
            "avg_accuracy": round(float(db.scalar(
                "SELECT AVG(accuracy) FROM answer_records", default=0.0) or 0.0), 1),
        },
        "wrongbook": {
            "total": int(db.scalar("SELECT COUNT(*) FROM wrong_questions")),
            "top_points": db.query(
                "SELECT knowledge_point AS kp, COUNT(*) AS c, SUM(wrong_count) AS w "
                "FROM wrong_questions GROUP BY knowledge_point ORDER BY w DESC LIMIT 8"),
        },
        "knowledge": {
            "docs": int(db.scalar("SELECT COUNT(*) FROM knowledge_docs")),
            "chunks": int(db.scalar("SELECT COUNT(*) FROM knowledge_chunks")),
        },
        "pool": {
            "total": int(db.scalar("SELECT COUNT(*) FROM question_pool")),
            "enabled": int(db.scalar("SELECT COUNT(*) FROM question_pool WHERE enabled=1")),
        },
        "llm": {
            "configured": bool(settings.deepseek_api_key),
            "model": settings.deepseek_model,
        },
    }


def trend(days=7):
    """近 N 天闯关量趋势，用于管理端折线图。"""
    rows = db.query(
        "SELECT date(created_at) AS d, COUNT(*) AS c FROM quiz_sessions "
        "WHERE date(created_at) >= date('now','localtime', ?) "
        "GROUP BY d ORDER BY d", ("-%d day" % int(days),))
    return [{"date": r["d"], "count": r["c"]} for r in rows]


def user_detail(user_id):
    """单个学生的答题信息汇总（管理端「用户管理」点人进来看到的那些）。

    按用途分成几块，而不是把原始记录一股脑丢出去：
    - profile：账号基本情况
    - stats：闯关次数、平均正确率、错题数、掌握情况
    - sessions：逐次闯关记录（标题 / 学段 / 来源 / 正确率）
    - wrong_points：薄弱知识点排行（错得最多的排前面）
    - wrong_items：最近错的题（供老师看孩子到底卡在哪）
    - knowledge：这个孩子传过什么资料
    """
    user = db.query_one(
        "SELECT id, nickname, username, openid, total_xp, status, grade, "
        "created_at, last_login_at FROM users WHERE id=?", (user_id,))
    if not user:
        return None

    sessions = db.query(
        "SELECT s.quiz_id, s.title, s.grade, s.source, s.created_at, "
        "COALESCE(a.total_questions, 0) AS total, COALESCE(a.correct_count, 0) AS correct, "
        "COALESCE(a.accuracy, 0) AS accuracy, COALESCE(a.duration_ms, 0) AS duration_ms, "
        "(SELECT COUNT(*) FROM wrong_questions w WHERE w.quiz_id = s.quiz_id) AS wrong_count "
        "FROM quiz_sessions s LEFT JOIN answer_records a ON a.quiz_id = s.quiz_id "
        "WHERE s.user_id = ? ORDER BY s.id DESC LIMIT 50", (user_id,))

    answered = [s for s in sessions if s["total"]]
    avg_accuracy = round(sum(s["accuracy"] for s in answered) / len(answered), 1) if answered else 0

    wrong_points = db.query(
        "SELECT knowledge_point AS kp, COUNT(*) AS questions, SUM(wrong_count) AS times "
        "FROM wrong_questions WHERE user_id=? GROUP BY knowledge_point "
        "ORDER BY times DESC LIMIT 10", (user_id,))

    wrong_items = db.query(
        "SELECT stem, knowledge_point, wrong_count, last_wrong_at, analysis "
        "FROM wrong_questions WHERE user_id=? ORDER BY wrong_count DESC, last_wrong_at DESC "
        "LIMIT 20", (user_id,))

    docs = db.query(
        "SELECT filename, file_type, size_bytes, created_at FROM knowledge_docs "
        "WHERE user_id=? ORDER BY id DESC LIMIT 20", (user_id,))

    grade_stats = db.query(
        "SELECT grade, COUNT(*) AS c FROM quiz_sessions WHERE user_id=? GROUP BY grade",
        (user_id,))
    source_stats = db.query(
        "SELECT source, COUNT(*) AS c FROM quiz_sessions WHERE user_id=? GROUP BY source",
        (user_id,))

    # PK 战绩：老师往往想看「这孩子最近在跟人对战吗、赢面如何」
    pk_matches = db.query(
        "SELECT match_id, theme, grade, opponent_name, opponent_kind, opponent_rank, "
        "my_correct, opponent_correct, total, result, xp_gained, finished_at "
        "FROM pk_matches WHERE user_id=? AND status=1 ORDER BY id DESC LIMIT 20", (user_id,))
    pk_stats = {
        "matches": len(pk_matches),
        "wins": sum(1 for m in pk_matches if m["result"] == "win"),
        "draws": sum(1 for m in pk_matches if m["result"] == "draw"),
    }

    return {
        "profile": user,
        "is_guest": not (user.get("username") and _has_password(user_id)),
        "stats": {
            "quiz_count": len(sessions),
            "answered_count": len(answered),
            "avg_accuracy": avg_accuracy,
            "wrong_count": int(db.scalar(
                "SELECT COUNT(*) FROM wrong_questions WHERE user_id=?", (user_id,))),
            "by_grade": {r["grade"]: r["c"] for r in grade_stats},
            "by_source": {r["source"]: r["c"] for r in source_stats},
            "pk": pk_stats,
        },
        "sessions": sessions,
        "wrong_points": wrong_points,
        "wrong_items": wrong_items,
        "knowledge": docs,
        "pk_matches": pk_matches,
    }


def _has_password(user_id):
    row = db.query_one("SELECT password_hash FROM users WHERE id=?", (user_id,))
    return bool(row and row.get("password_hash"))


def list_users(keyword=None, page=1, size=20):
    where, params = ["1=1"], []
    if keyword:
        # 老师找学生通常直接报登录名（比如 xiaoming），所以登录名也要能搜
        where.append("(nickname LIKE ? OR openid LIKE ? OR username LIKE ?)")
        params += ["%" + keyword + "%", "%" + keyword + "%", "%" + keyword + "%"]
    clause = " AND ".join(where)
    total = int(db.scalar("SELECT COUNT(*) FROM users WHERE " + clause, tuple(params)))
    offset = max(0, (int(page) - 1) * int(size))
    rows = db.query(
        "SELECT u.id, u.nickname, u.username, u.openid, u.total_xp, u.status, u.grade, "
        "u.created_at, u.last_login_at, "
        "(SELECT COUNT(*) FROM quiz_sessions s WHERE s.user_id=u.id) AS quiz_count, "
        "(SELECT COUNT(*) FROM wrong_questions w WHERE w.user_id=u.id) AS wrong_count "
        "FROM users u WHERE " + clause + " ORDER BY u.id DESC LIMIT ? OFFSET ?",
        tuple(params) + (int(size), offset))
    for r in rows:
        # 没有登录名的就是游客账号（先试玩再注册的那批）
        r["is_guest"] = 0 if r.get("username") else 1
    return {"items": rows, "total": total, "page": int(page), "size": int(size)}


def set_user_status(user_id, status, username="admin"):
    if not db.query_one("SELECT id FROM users WHERE id=?", (user_id,)):
        return False
    db.execute("UPDATE users SET status=?, updated_at=datetime('now','localtime') WHERE id=?",
               (1 if int(status) else 0, user_id))
    log(username, "user.status", "用户 #%s 状态改为 %s" % (user_id, status))
    return True


def list_sessions(page=1, size=20, grade=None, source=None):
    where, params = ["1=1"], []
    if grade:
        where.append("grade=?")
        params.append(grade)
    if source:
        where.append("source=?")
        params.append(source)
    clause = " AND ".join(where)
    total = int(db.scalar("SELECT COUNT(*) FROM quiz_sessions WHERE " + clause, tuple(params)))
    offset = max(0, (int(page) - 1) * int(size))
    rows = db.query(
        "SELECT s.quiz_id, s.title, s.grade, s.source, s.created_at, "
        "COALESCE(u.nickname,'游客') AS nickname, "
        "(SELECT COUNT(*) FROM wrong_questions w WHERE w.quiz_id=s.quiz_id) AS wrong_count "
        "FROM quiz_sessions s LEFT JOIN users u ON u.id=s.user_id WHERE " + clause +
        " ORDER BY s.id DESC LIMIT ? OFFSET ?", tuple(params) + (int(size), offset))
    return {"items": rows, "total": total, "page": int(page), "size": int(size)}


def list_logs(limit=50):
    return db.query(
        "SELECT username, action, detail, created_at FROM admin_logs "
        "ORDER BY id DESC LIMIT ?", (int(limit),))
