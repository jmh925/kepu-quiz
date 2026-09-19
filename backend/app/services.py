# -*- coding: utf-8 -*-
"""业务服务层：登录鉴权 / 出题 / 判题 / 复盘报告 / 知识库检索 / 错题本。

分层约定（对应论文 5.1 节项目结构）：
- routers 只负责参数解析与响应封装，业务规则全部收敛到本层；
- 本层不依赖 FastAPI，只依赖 database / llm / grades / safety / wrongbook，
  因此可以脱离 Web 层单独测试；
- 检索增强采用「中文 2-gram 词频向量 + 余弦相似度」的轻量实现，
  在单文档规模下效果可用且零额外依赖（论文 2.3、5.6 节）。
"""
import math
import re
import time
import uuid

import jwt as pyjwt

from . import database as db
from . import grades
from . import llm
from . import safety
from . import wrongbook
from .config import settings

# 每完成一次闯关的经验值与每题答对的经验值（游戏化激励，论文 2.2 节）
XP_FINISH = 10
XP_PER_CORRECT = 2


# ---------------- 鉴权 ----------------
def issue_token(user_id: int, openid: str) -> str:
    """签发 HS256 JWT（有效期由配置决定，默认 7 天）。"""
    payload = {"uid": user_id, "openid": openid,
               "exp": int(time.time()) + settings.jwt_expire_days * 86400}
    return pyjwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str):
    try:
        return pyjwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except Exception:
        return None


# ---------------- 用户 ----------------
# 登录名规则：字母 / 数字 / 下划线，3~20 位；口令 6~32 位。
# 放宽成「字母数字下划线」而不是绑手机号，是为了让小朋友也能用昵称式账号。
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
PASSWORD_MIN, PASSWORD_MAX = 6, 32


def _hash_password(password, salt=None):
    """与管理员账号同一套：PBKDF2-HMAC-SHA256 + 每账号独立随机盐。"""
    import hashlib
    import secrets
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                             bytes.fromhex(salt), 120000)
    return dk.hex(), salt


def _verify_password(password, hash_hex, salt_hex):
    import hmac
    if not hash_hex or not salt_hex:
        return False
    calc, _ = _hash_password(password, salt_hex)
    return hmac.compare_digest(calc, hash_hex)


def register(username, password, nickname=None, grade=None):
    """注册新账号。返回 (结果, 错误信息)。"""
    name = (username or "").strip()
    pwd = password or ""
    if not USERNAME_RE.match(name):
        return None, "登录名用 3~20 位字母、数字或下划线"
    if len(pwd) < PASSWORD_MIN or len(pwd) > PASSWORD_MAX:
        return None, "口令请设 %d~%d 位" % (PASSWORD_MIN, PASSWORD_MAX)
    if db.query_one("SELECT id FROM users WHERE username=?", (name,)):
        return None, "这个登录名已经有人用了，换一个试试"

    hash_hex, salt = _hash_password(pwd)
    g = grades.normalize_grade(grade)
    openid = "local_" + uuid.uuid4().hex[:12]
    uid = db.execute(
        "INSERT INTO users(openid, username, password_hash, salt, nickname, grade, last_login_at) "
        "VALUES(?,?,?,?,?,?,datetime('now','localtime'))",
        (openid, name, hash_hex, salt, (nickname or name).strip() or name, g))
    user = db.query_one("SELECT * FROM users WHERE id=?", (uid,))
    return {"token": issue_token(user["id"], user["openid"]), "user": _user_vo(user)}, None


def login(code=None, nickname="小科学家", grade=None, username=None, password=None):
    """登录。支持两种方式：

    1. 账号 + 口令（网页版学生端使用）；
    2. 微信 code（小程序端使用，当前以本地账号实现，见 login_by_code）。

    返回 (结果, 错误信息)，便于路由层区分「参数错」与「账号口令错」。
    """
    if username:
        return login_with_password(username, password)
    return login_by_code(code, nickname, grade), None


def login_with_password(username, password):
    """账号 + 口令登录。返回 (结果, 错误信息)——**必须是二元组**。

    踩过的坑：这里一度在成功时只返回结果字典，而路由里写的是
    `result, err = services.login(...)`，于是字典被按 key 解包，
    err 变成了字符串 "user"，正确口令也会登录失败。
    凡是「可能失败」的函数，统一返回二元组，别让调用方去猜。
    """
    name = (username or "").strip()
    row = db.query_one("SELECT * FROM users WHERE username=?", (name,))
    if not row:
        return None, "没有找到这个登录名，先注册一个吧"
    if not row.get("password_hash"):
        return None, "这个账号还没有设置口令"
    if not _verify_password(password or "", row["password_hash"], row["salt"]):
        return None, "口令不对，再想想？"
    if row.get("status") == 0:
        return None, "这个账号已被停用，请联系老师"
    db.execute("UPDATE users SET last_login_at=datetime('now','localtime') WHERE id=?",
               (row["id"],))
    return {"token": issue_token(row["id"], row["openid"]), "user": _user_vo(row)}, None


def login_by_code(code=None, nickname="小科学家", grade=None):
    """以微信 code 建立/复用账号（小程序端路径，也是游客体验用的入口）。

    预留接入点：接入 jscode2session 后把 code 换成真实 openid 即可，
    其余逻辑不用改。当前以本地账号实现，便于不依赖微信后台也能演示。
    """
    openid = "local_" + uuid.uuid4().hex[:12] if not code else "wx_" + str(code)[:32]
    user = db.query_one("SELECT * FROM users WHERE openid=?", (openid,))
    if not user:
        db.execute("INSERT INTO users(openid, nickname, grade, last_login_at) "
                   "VALUES(?,?,?,datetime('now','localtime'))",
                   (openid, nickname or "小科学家", grades.normalize_grade(grade)))
        user = db.query_one("SELECT * FROM users WHERE openid=?", (openid,))
    else:
        db.execute("UPDATE users SET last_login_at=datetime('now','localtime') WHERE id=?",
                   (user["id"],))
    return {"token": issue_token(user["id"], user["openid"]), "user": _user_vo(user)}


def guest_login(grade=None):
    """游客体验：建一个不带口令的临时账号，让游客也能攒经验、存错题。

    「先试再注册」不该白玩——注册时会把这些数据并过去（见 merge_guest_data）。
    """
    return login_by_code(None, "小科学家", grade)


def merge_guest_data(guest_user_id, target_user_id):
    """把游客期间产生的数据并到正式账号上。

    为什么需要：孩子注册前往往已经答过几轮、攒了错题。如果注册后一切归零，
    他会觉得「白答了」——这是很糟的体验。这里把闯关记录、答题记录、
    复盘报告、知识库文档、错题、经验值全部改归属。
    """
    if not guest_user_id or not target_user_id or guest_user_id == target_user_id:
        return {"moved": 0}
    guest = db.query_one("SELECT * FROM users WHERE id=?", (guest_user_id,))
    target = db.query_one("SELECT * FROM users WHERE id=?", (target_user_id,))
    if not guest or not target:
        return {"moved": 0}

    moved = 0
    for table in ("quiz_sessions", "answer_records", "reports", "knowledge_docs"):
        row = db.query_one("SELECT COUNT(*) AS c FROM %s WHERE user_id=?" % table,
                           (guest_user_id,))
        if row and row["c"]:
            db.execute("UPDATE %s SET user_id=? WHERE user_id=?" % table,
                       (target_user_id, guest_user_id))
            moved += int(row["c"])

    # 错题要特别小心：同一个人可能有「同题干」两条记录，
    # 直接改 user_id 会撞上 (user_id, stem) 唯一索引，所以要先合并再删。
    for w in db.query("SELECT * FROM wrong_questions WHERE user_id=?", (guest_user_id,)):
        exist = db.query_one(
            "SELECT id FROM wrong_questions WHERE user_id=? AND stem=?",
            (target_user_id, w["stem"]))
        if exist:
            db.execute("UPDATE wrong_questions SET wrong_count=wrong_count+? WHERE id=?",
                       (w["wrong_count"], exist["id"]))
            db.execute("DELETE FROM wrong_questions WHERE id=?", (w["id"],))
        else:
            db.execute("UPDATE wrong_questions SET user_id=? WHERE id=?",
                       (target_user_id, w["id"]))
        moved += 1

    db.execute("UPDATE users SET total_xp=total_xp+?, "
               "updated_at=datetime('now','localtime') WHERE id=?",
               (guest["total_xp"] or 0, target_user_id))
    # 游客账号停用，避免它继续被当成有效账号
    db.execute("UPDATE users SET status=0 WHERE id=?", (guest_user_id,))
    return {"moved": moved}


def is_guest(user_id):
    """判断某账号是不是游客（没有设置口令的就是游客/托管账号）。"""
    if not user_id:
        return True
    row = db.query_one("SELECT username, password_hash FROM users WHERE id=?", (user_id,))
    return not (row and row.get("username") and row.get("password_hash"))


def get_profile(user_id):
    user = db.query_one("SELECT * FROM users WHERE id=?", (user_id,))
    if not user:
        return None
    sessions = db.query(
        "SELECT quiz_id, title, grade, source, created_at FROM quiz_sessions "
        "WHERE user_id=? ORDER BY id DESC LIMIT 20", (user_id,))
    return {"user": _user_vo(user), "sessions": sessions,
            "wrong_count": wrongbook.count_wrong(user_id),
            "weak_points": wrongbook.weak_points(user_id)}


def _user_vo(user):
    return {"id": user["id"], "nickname": user["nickname"],
            "avatar_url": user["avatar_url"], "total_xp": user["total_xp"],
            "grade": user.get("grade") or grades.DEFAULT_GRADE}


# ---------------- 出题 ----------------
def generate_quiz(topic, count=None, user_id=None, doc_id=None, grade=None):
    """出题：内容安全 → 可选文档检索 → 大模型/题库 → 落库，返回可答题的完整题目。"""
    g = grades.normalize_grade(grade)
    context, hit_chunks = None, 0
    if doc_id:
        context, hit_chunks = retrieve_context(doc_id, topic)

    if context and settings.deepseek_api_key:
        # 真检索增强：把命中的资料片段拼进 Prompt
        result = llm.generate_questions(
            topic + "\n\n参考资料（请严格依据以下资料出题，不要编造资料外的事实）：\n" + context,
            count, g)
    else:
        result = llm.generate_questions(topic, count, g)

    quiz_id = uuid.uuid4().hex[:16]
    questions = result["questions"]
    db.execute(
        "INSERT INTO quiz_sessions(quiz_id, user_id, title, summary, user_input, grade, "
        "source, questions_json) VALUES(?,?,?,?,?,?,?,?)",
        (quiz_id, user_id, result["title"], "", topic, g, result["source"],
         db.dumps(questions)))
    return {"quiz_id": quiz_id, "title": result["title"], "source": result["source"],
            "grade": g, "grade_label": grades.grade_rule(g)["label"],
            "count": len(questions), "hit_chunks": hit_chunks,
            "dropped_unsafe": result.get("dropped_unsafe", 0),
            "dropped_long": result.get("dropped_long", 0),
            "questions": questions}


# ---------------- 判题 ----------------
def submit_answer(quiz_id, answers, user_id=None, duration_ms=0):
    """判题与结算：逐题比对 → 记录明细 → 结算经验值 → 维护错题本。"""
    row = db.query_one("SELECT * FROM quiz_sessions WHERE quiz_id=?", (quiz_id,))
    if not row:
        return None
    questions = db.loads(row["questions_json"]) or []
    total = len(questions)
    correct = 0
    details = []
    weak_points = []
    for i, q in enumerate(questions):
        user_ans = answers[i] if i < len(answers) else -1
        right = int(q.get("answer", 0))
        is_correct = (user_ans == right)
        if is_correct:
            correct += 1
        else:
            weak_points.append(q.get("knowledge_point") or "科普知识")
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
        (quiz_id, user_id, db.dumps(details), total, correct, accuracy, int(duration_ms or 0)))

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
            "wrong_added": added, "mastered": mastered,
            "wrong_total": wrongbook.count_wrong(user_id),
            "weak_points": list(dict.fromkeys(weak_points)), "details": details}


# ---------------- 复盘报告 ----------------
def generate_report(quiz_id, user_id=None):
    rec = db.query_one("SELECT * FROM answer_records WHERE quiz_id=?", (quiz_id,))
    if not rec:
        return None
    total = rec["total_questions"]
    correct = rec["correct_count"]
    accuracy = rec["accuracy"]
    weak_points = list(dict.fromkeys(
        [d.get("knowledge_point") or "科普知识"
         for d in (db.loads(rec["records_json"]) or []) if not d.get("is_correct")]))
    # 报告语气跟随本局所选学段
    session = db.query_one("SELECT grade FROM quiz_sessions WHERE quiz_id=?", (quiz_id,))
    g = grades.normalize_grade(session["grade"] if session else None)
    report = llm.generate_report(total, correct, weak_points, grade=g)
    db.execute("INSERT OR REPLACE INTO reports(quiz_id, user_id, report_json) VALUES(?,?,?)",
               (quiz_id, user_id, db.dumps(report)))
    return {"quiz_id": quiz_id, "total": total, "correct": correct,
            "accuracy": accuracy, "report": report}


# ---------------- 知识库（轻量检索增强） ----------------
def add_document(filename, content, user_id=None, size_bytes=0):
    doc_id = uuid.uuid4().hex[:12]
    ext = (filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt")
    db.execute("INSERT INTO knowledge_docs(doc_id, user_id, filename, file_type, "
               "size_bytes, content, status) VALUES(?,?,?,?,?,?,?)",
               (doc_id, user_id, filename, ext, int(size_bytes), content, "ready"))
    chunks = _chunk(content)
    for i, c in enumerate(chunks):
        db.execute("INSERT INTO knowledge_chunks(doc_id, chunk_index, content) VALUES(?,?,?)",
                   (doc_id, i, c))
    return {"doc_id": doc_id, "filename": filename, "chunks": len(chunks),
            "file_type": ext, "size_bytes": int(size_bytes)}


def list_documents(user_id=None):
    return db.query(
        "SELECT doc_id, filename, file_type, size_bytes, status, created_at "
        "FROM knowledge_docs WHERE user_id IS ? ORDER BY id DESC", (user_id,))
    # 说明：user_id 为 None 时用 SQLite 的 IS 语义匹配游客上传的文档


def delete_document(doc_id):
    db.execute("DELETE FROM knowledge_chunks WHERE doc_id=?", (doc_id,))
    return db.execute("DELETE FROM knowledge_docs WHERE doc_id=?", (doc_id,))


def _chunk(content, size=300):
    """按段落 + 长度分块：把长文档切成约 300 字、语义相对完整的片段。"""
    chunks, cur = [], ""
    for p in re.split(r"\n+", content or ""):
        p = p.strip()
        if not p:
            continue
        if len(cur) + len(p) > size and cur:
            chunks.append(cur)
            cur = p
        else:
            cur = (cur + "\n" + p) if cur else p
    if cur:
        chunks.append(cur)
    return chunks


def _ngram_vector(text):
    """中文 2-gram + 单字词频向量，做 L2 归一化。"""
    text = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "", text or "")
    grams = [text[i:i + 2] for i in range(len(text) - 1)] + list(text)
    vec = {}
    for g in grams:
        if g:
            vec[g] = vec.get(g, 0) + 1
    norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {k: v / norm for k, v in vec.items()}


def _cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0) for k, v in a.items())


def retrieve_context(doc_id, query, top_k=None):
    """从文档分块中检索与 query 最相关的片段，返回 (拼接后的上下文, 命中片段数)。

    注意：向量只在这里按需计算，且 2-gram 向量规模很小，
    单文档（几十个分块）场景下耗时在毫秒级，无需引入向量数据库。
    """
    top_k = top_k or settings.rag_top_k
    chunks = db.query("SELECT content FROM knowledge_chunks WHERE doc_id=? "
                      "ORDER BY chunk_index", (doc_id,))
    if not chunks:
        return None, 0
    qv = _ngram_vector(query)
    scored = [(_cosine(qv, _ngram_vector(c["content"])), c["content"]) for c in chunks]
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [c for s, c in scored[:top_k] if s > 0]
    if not top:
        return None, 0
    return "\n".join(top)[:settings.rag_context_max], len(top)


# ---------------- 错题本与个性化复习 ----------------
def practice_wrong(user_id, count=8, grade=None):
    """只用错题重组一套练习卷：不调用大模型，秒级返回。

    这既是「个性化复习」的落地，也让复习功能在大模型不可用时依然可用。
    """
    if not user_id:
        return None
    questions = wrongbook.build_practice_quiz(user_id, count)
    if not questions:
        return None
    g = grades.normalize_grade(grade)
    quiz_id = uuid.uuid4().hex[:16]
    db.execute(
        "INSERT INTO quiz_sessions(quiz_id, user_id, title, summary, user_input, grade, "
        "source, questions_json) VALUES(?,?,?,?,?,?,?,?)",
        (quiz_id, user_id, "错题重练", "", "错题重练", g, "wrongbook",
         db.dumps(questions)))
    return {"quiz_id": quiz_id, "title": "错题重练", "source": "wrongbook",
            "grade": g, "grade_label": grades.grade_rule(g)["label"],
            "count": len(questions), "questions": questions}


def get_wrong_summary(user_id):
    """错题本总览：错题列表 + 薄弱知识点排行。"""
    if not user_id:
        return {"questions": [], "weak_points": [], "total": 0}
    return {"questions": wrongbook.list_wrong(user_id),
            "weak_points": wrongbook.weak_points(user_id),
            "total": wrongbook.count_wrong(user_id)}


def clear_wrong(user_id):
    return wrongbook.clear(user_id)


def delete_wrong_item(user_id, stem):
    """删除错题本里的单条错题（错题本页面的「删」）。"""
    return wrongbook.delete_wrong(user_id, stem)


def update_wrong_item(user_id, stem, payload):
    """修改错题本里的单条错题（错题本页面的「改」）。返回 (结果, 错误信息)。"""
    return wrongbook.update_wrong(user_id, stem, payload)


def check_topic(topic):
    """出题前的内容安全校验，返回 (是否通过, 错误码, 提示语)。"""
    passed, reason = safety.check_input(topic)
    if passed:
        return True, 0, ""
    code = 4002 if reason == safety.UNSAFE_INPUT_MSG else 4000
    return False, code, reason
