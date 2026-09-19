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
    """首次启动时按配置创建默认管理员（幂等）。"""
    row = db.query_one("SELECT id FROM admins WHERE username=?", (settings.admin_username,))
    if row:
        return False
    pw_hash, salt = hash_password(settings.admin_password)
    db.execute("INSERT INTO admins(username, password_hash, salt, role) VALUES(?,?,?,?)",
               (settings.admin_username, pw_hash, salt, "admin"))
    return True


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


def list_users(keyword=None, page=1, size=20):
    where, params = ["1=1"], []
    if keyword:
        where.append("(nickname LIKE ? OR openid LIKE ?)")
        params += ["%" + keyword + "%", "%" + keyword + "%"]
    clause = " AND ".join(where)
    total = int(db.scalar("SELECT COUNT(*) FROM users WHERE " + clause, tuple(params)))
    offset = max(0, (int(page) - 1) * int(size))
    rows = db.query(
        "SELECT u.id, u.nickname, u.openid, u.total_xp, u.status, u.grade, u.created_at, "
        "(SELECT COUNT(*) FROM quiz_sessions s WHERE s.user_id=u.id) AS quiz_count, "
        "(SELECT COUNT(*) FROM wrong_questions w WHERE w.user_id=u.id) AS wrong_count "
        "FROM users u WHERE " + clause + " ORDER BY u.id DESC LIMIT ? OFFSET ?",
        tuple(params) + (int(size), offset))
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
