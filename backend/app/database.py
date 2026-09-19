# -*- coding: utf-8 -*-
"""SQLite 数据访问层。

设计说明（对应论文 5.2 节）：
- 零依赖：只用标准库 sqlite3，无需安装数据库服务，便于部署与答辩演示；
- 连接复用 + 线程锁：Uvicorn 的线程池会并发调用，SQLite 连接对象不跨线程共享，
  因此用 check_same_thread=False 打开、并用 Lock 串行化写操作；
- 自动建表：CREATE TABLE IF NOT EXISTS + 迁移函数 _migrate，
  升级版本时旧库可直接打开，不需要手工改表；
- 表结构对齐论文第 4 章表 4-1～表 4-10，生产可平滑迁移至 MySQL。
"""
import json
import sqlite3
import threading

from .config import settings

_conn = None
_lock = threading.RLock()

_SCHEMA = """
-- 表 4-1 用户表
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    openid TEXT NOT NULL UNIQUE,
    nickname TEXT NOT NULL DEFAULT '学习者',
    avatar_url TEXT NOT NULL DEFAULT '',
    total_xp INTEGER NOT NULL DEFAULT 0,
    status INTEGER NOT NULL DEFAULT 1,              -- 1 正常 / 0 停用（管理端可操作）
    grade TEXT NOT NULL DEFAULT 'primary_high',     -- 常用学段，用于个性化默认值
    last_login_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 表 4-2 闯关会话表
CREATE TABLE IF NOT EXISTS quiz_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id TEXT NOT NULL UNIQUE,
    user_id INTEGER,
    title TEXT NOT NULL DEFAULT '',
    summary TEXT,
    user_input TEXT,
    grade TEXT NOT NULL DEFAULT 'primary_high',
    source TEXT NOT NULL DEFAULT 'bank',            -- ai / bank / wrongbook
    questions_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 表 4-3 答题记录表
CREATE TABLE IF NOT EXISTS answer_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id TEXT NOT NULL UNIQUE,
    user_id INTEGER,
    records_json TEXT NOT NULL,
    total_questions INTEGER NOT NULL DEFAULT 0,
    correct_count INTEGER NOT NULL DEFAULT 0,
    accuracy REAL NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 表 4-4 复盘报告表
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id TEXT NOT NULL UNIQUE,
    user_id INTEGER,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 表 4-5 知识库文档表
CREATE TABLE IF NOT EXISTS knowledge_docs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL UNIQUE,
    user_id INTEGER,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL DEFAULT 'txt',
    size_bytes INTEGER NOT NULL DEFAULT 0,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ready',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 表 4-6 知识库分块表（轻量检索的最小单元）
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_doc ON knowledge_chunks(doc_id);

-- 表 4-7 错题本表
CREATE TABLE IF NOT EXISTS wrong_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    quiz_id TEXT,
    stem TEXT NOT NULL,
    options_json TEXT NOT NULL DEFAULT '[]',
    correct_answer INTEGER NOT NULL DEFAULT 0,
    user_answer INTEGER,
    analysis TEXT DEFAULT '',
    knowledge_point TEXT DEFAULT '',
    wrong_count INTEGER NOT NULL DEFAULT 1,
    last_wrong_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_wrong_user ON wrong_questions(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_wrong_user_stem ON wrong_questions(user_id, stem);

-- 表 4-8 管理端账号表
CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'admin',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 表 4-9 题目资源池表（管理端维护，出题时优先命中）
CREATE TABLE IF NOT EXISTS question_pool (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    theme TEXT NOT NULL DEFAULT '通用',
    grade TEXT NOT NULL DEFAULT 'primary_high',
    stem TEXT NOT NULL,
    options_json TEXT NOT NULL,
    answer INTEGER NOT NULL DEFAULT 0,
    analysis TEXT NOT NULL DEFAULT '',
    knowledge_point TEXT NOT NULL DEFAULT '科普知识',
    difficulty INTEGER NOT NULL DEFAULT 2,          -- 1 易 / 2 中 / 3 难
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_pool_theme ON question_pool(theme, grade);

-- 表 4-10 操作日志表（管理端可审计）
CREATE TABLE IF NOT EXISTS admin_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""

# 旧库平滑升级：早期版本的库缺列，这里按需补齐，
# 避免"有了新表结构却打不开旧库"（CREATE TABLE IF NOT EXISTS 不会补列）。
_MIGRATIONS = [
    ("users", "status", "INTEGER NOT NULL DEFAULT 1"),
    ("users", "grade", "TEXT NOT NULL DEFAULT 'primary_high'"),
    ("users", "last_login_at", "TEXT"),
    ("quiz_sessions", "grade", "TEXT NOT NULL DEFAULT 'primary_high'"),
    ("quiz_sessions", "source", "TEXT NOT NULL DEFAULT 'bank'"),
    ("answer_records", "duration_ms", "INTEGER NOT NULL DEFAULT 0"),
    ("knowledge_docs", "file_type", "TEXT NOT NULL DEFAULT 'txt'"),
    ("knowledge_docs", "size_bytes", "INTEGER NOT NULL DEFAULT 0"),
]


def get_conn():
    """获取（并复用）全局 SQLite 连接，首次调用时建表并迁移。"""
    global _conn
    if _conn is None:
        with _lock:
            if _conn is None:
                import os
                os.makedirs(os.path.dirname(settings.db_path), exist_ok=True)
                conn = sqlite3.connect(settings.db_path, check_same_thread=False)
                conn.row_factory = sqlite3.Row
                conn.executescript(_SCHEMA)
                _migrate(conn)
                conn.commit()
                _conn = conn
    return _conn


def _migrate(conn):
    for table, column, ddl in _MIGRATIONS:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(%s)" % table).fetchall()]
        if column not in cols:
            conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, column, ddl))


def query(sql, params=()):
    """查询多行，返回 dict 列表。"""
    cur = get_conn().execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def query_one(sql, params=()):
    """查询单行，返回 dict 或 None。"""
    cur = get_conn().execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row else None


def execute(sql, params=()):
    """执行写操作并提交，返回自增主键（无自增时为 rowcount）。"""
    conn = get_conn()
    with _lock:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid


def scalar(sql, params=(), default=0):
    """取单个标量值（统计接口高频使用）。"""
    row = query_one(sql, params)
    if not row:
        return default
    value = list(row.values())[0]
    return default if value is None else value


def reset_connection():
    """关闭并丢弃全局连接（测试用例隔离数据库时使用）。"""
    global _conn
    with _lock:
        if _conn is not None:
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False)


def loads(text):
    return json.loads(text) if text else None
