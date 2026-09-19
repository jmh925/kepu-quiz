# -*- coding: utf-8 -*-
"""从源码自动生成接口清单与数据库字典。

为什么用脚本生成：手写的接口文档必然与代码脱节。这里直接从 FastAPI 的
路由表与 SQLite 的实际表结构生成文档，改代码后重跑一次即可保持同步，
论文第 4 章的接口清单与表结构也可以直接以本文档为准。

用法（在 backend 目录下）：
    python ../tools/gen_docs.py
产物：docs/repo/接口清单.md、docs/repo/数据库字典.md
"""
import inspect
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BACKEND = os.path.join(ROOT, "backend")
OUT_DIR = os.path.join(ROOT, "docs", "repo")
os.makedirs(OUT_DIR, exist_ok=True)

sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(BACKEND, "deps"))

from fastapi.routing import APIRoute          # noqa: E402

from app.main import app                      # noqa: E402
from app import database as db                # noqa: E402

# 表的中文名与说明（与论文表 4-1～表 4-10 对应）
TABLE_META = {
    "users": ("用户表", "表 4-1", "存储学生账号：openid、昵称、累计经验值、状态与常用学段"),
    "quiz_sessions": ("闯关会话表", "表 4-2", "一次出题对应一条会话，保存题目 JSON 与出题来源"),
    "answer_records": ("答题记录表", "表 4-3", "一次判题的明细结果：总题数、答对数、正确率、耗时"),
    "reports": ("复盘报告表", "表 4-4", "保存复盘报告的 JSON 结果（AI 生成或规则降级）"),
    "knowledge_docs": ("知识库文档表", "表 4-5", "上传的讲义 / 课外读本：文件名、类型、正文、状态"),
    "knowledge_chunks": ("知识库分块表", "表 4-6", "文档按段落 + 长度切分后的片段，是检索的最小单元"),
    "wrong_questions": ("错题本表", "表 4-7", "结构化沉淀的错题，含错误次数与最近答错时间"),
    "admins": ("管理端账号表", "表 4-8", "管理端账号：用户名、口令哈希、盐、角色"),
    "question_pool": ("题目资源池表", "表 4-9", "管理端维护的题目，出题时优先命中"),
    "admin_logs": ("操作日志表", "表 4-10", "管理端写操作留痕，便于审计"),
}

ERROR_CODES = [
    ("0", "成功", "业务处理成功，data 为返回数据"),
    ("4000", "参数错误", "入参缺失、格式错误或超出范围"),
    ("4001", "文档解析失败", "知识库只接受 txt / md / csv / pdf / docx，且内容不能为空"),
    ("4002", "内容不合规", "出题主题命中面向未成年人的内容安全词表"),
    ("4003", "错题本为空", "错题本没有内容时调用「只练错题」"),
    ("4010", "未登录", "学生端接口需要登录后才能访问（错题本、个人中心）"),
    ("4011", "管理端未认证", "缺少或使用了无效的 X-Admin-Token"),
    ("5000", "服务器内部错误", "兜底异常，对外只给统一提示，细节留在服务端日志"),
]


def schema_of(func):
    """把依赖注入参数排除后，生成简明的参数说明。"""
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return ""
    parts = []
    for name, param in sig.parameters.items():
        if name in ("admin", "user_id"):
            continue
        annotation = param.annotation
        type_name = getattr(annotation, "__name__", str(annotation))
        default = "" if param.default is inspect._empty else "（可选）"
        parts.append("%s: %s%s" % (name, type_name, default))
    return "、".join(parts)


def _walk_routes(routes, prefix="", seen=None):
    """递归展开路由树。

    新版 FastAPI 用 `_IncludedRouter` 包装 `include_router` 的结果，
    直接遍历 app.routes 拿不到子路由，因此这里递归下钻。
    """
    seen = seen if seen is not None else set()
    out = []
    for route in routes:
        if id(route) in seen:
            continue
        seen.add(id(route))
        sub = getattr(route, "routes", None)
        if sub is None:
            inner = getattr(route, "original_router", None)   # FastAPI _IncludedRouter
            sub = getattr(inner, "routes", None) if inner is not None else None
        if sub:
            out.extend(_walk_routes(sub, prefix + getattr(route, "prefix", "") or "", seen))
        if isinstance(route, APIRoute):
            out.append((prefix, route))
    return out


def collect_routes():
    student, admin = [], []
    for prefix, route in _walk_routes(app.routes):
        path = route.path
        if not path.startswith(prefix):
            path = (prefix.rstrip("/") + path) if prefix else path
        if not path.startswith("/api/v1"):
            continue
        methods = ",".join(sorted(m for m in route.methods if m not in ("HEAD", "OPTIONS")))
        summary = (route.summary or "").strip()
        doc = (inspect.getdoc(route.endpoint) or "").strip().split("\n")[0]
        item = {
            "path": path, "methods": methods, "name": route.name,
            "summary": summary, "doc": doc, "params": schema_of(route.endpoint),
        }
        (admin if "/admin/" in path else student).append(item)
    order = {"GET": 0, "POST": 1, "PUT": 2, "DELETE": 3}
    student.sort(key=lambda x: (x["path"], order.get(x["methods"], 9)))
    admin.sort(key=lambda x: (x["path"], order.get(x["methods"], 9)))
    return student, admin


# 接口功能的中文名（脚本无法从代码推断，这里显式维护，便于论文直接引用）
API_TITLES = {
    ("GET", "/api/v1/health"): "服务健康检查",
    ("GET", "/api/v1/grades"): "学段选项拉取",
    ("POST", "/api/v1/quiz/generate"): "出题（支持检索增强）",
    ("POST", "/api/v1/quiz/submit"): "答题提交与判题结算",
    ("POST", "/api/v1/report/generate"): "生成复盘报告",
    ("POST", "/api/v1/user/login"): "用户登录",
    ("GET", "/api/v1/user/profile"): "个人中心数据",
    ("POST", "/api/v1/knowledge/documents"): "上传知识库文档",
    ("GET", "/api/v1/knowledge/documents"): "知识库文档列表",
    ("DELETE", "/api/v1/knowledge/documents/{doc_id}"): "删除知识库文档",
    ("GET", "/api/v1/wrong/questions"): "错题本总览",
    ("POST", "/api/v1/wrong/practice"): "只练错题组卷",
    ("DELETE", "/api/v1/wrong/questions"): "清空错题本",
    ("POST", "/api/v1/admin/login"): "管理端登录",
    ("GET", "/api/v1/admin/me"): "校验管理端登录态",
    ("GET", "/api/v1/admin/dashboard"): "运行看板统计",
    ("GET", "/api/v1/admin/trend"): "近 N 天闯关量趋势",
    ("GET", "/api/v1/admin/users"): "用户分页查询",
    ("POST", "/api/v1/admin/users/{user_id}/status"): "启用 / 停用用户",
    ("GET", "/api/v1/admin/questions"): "题库资源池查询",
    ("GET", "/api/v1/admin/questions/themes"): "题库主题分布",
    ("POST", "/api/v1/admin/questions"): "新增题目",
    ("PUT", "/api/v1/admin/questions/{qid}"): "修改题目",
    ("DELETE", "/api/v1/admin/questions/{qid}"): "删除题目",
    ("GET", "/api/v1/admin/sessions"): "闯关记录查询",
    ("GET", "/api/v1/admin/logs"): "操作日志查询",
}


def title_of(item):
    return API_TITLES.get((item["methods"], item["path"])) or item["doc"] or item["name"]


def write_api_doc(student, admin):
    lines = []
    lines.append("# 接口清单（由源码自动生成）")
    lines.append("")
    lines.append("> 本文档由 `tools/gen_docs.py` 从 FastAPI 路由表导出，")
    lines.append("> 修改接口后请重跑脚本以保持同步。在线文档见 `http://127.0.0.1:8000/docs`。")
    lines.append("")
    lines.append("## 一、通用约定")
    lines.append("")
    lines.append("| 项目 | 约定 |")
    lines.append("| --- | --- |")
    lines.append("| 前缀 | `/api/v1` |")
    lines.append("| 响应体 | `{code, message, data}`，`code = 0` 表示成功 |")
    lines.append("| 学生端鉴权 | 请求头 `Authorization: Bearer <token>`（可选登录，游客可用大部分功能） |")
    lines.append("| 管理端鉴权 | 请求头 `X-Admin-Token`（登录接口签发，或 `.env` 中的固定 Token） |")
    lines.append("| 编码 | UTF-8，请求体 `Content-Type: application/json; charset=utf-8` |")
    lines.append("")
    lines.append("## 二、错误码")
    lines.append("")
    lines.append("| 错误码 | 含义 | 说明 |")
    lines.append("| --- | --- | --- |")
    for code, name, desc in ERROR_CODES:
        lines.append("| %s | %s | %s |" % (code, name, desc))
    lines.append("")

    lines.append("## 三、学生端接口（%d 个）" % len(student))
    lines.append("")
    lines.append("| 序号 | 方法 | 路径 | 功能 | 参数 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for i, item in enumerate(student, 1):
        lines.append("| %d | %s | `%s` | %s | %s |"
                     % (i, item["methods"], item["path"],
                        title_of(item),
                        item["params"] or "—"))
    lines.append("")

    lines.append("## 四、管理端接口（%d 个）" % len(admin))
    lines.append("")
    lines.append("| 序号 | 方法 | 路径 | 功能 | 参数 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for i, item in enumerate(admin, len(student) + 1):
        lines.append("| %d | %s | `%s` | %s | %s |"
                     % (i, item["methods"], item["path"],
                        title_of(item),
                        item["params"] or "—"))
    lines.append("")
    lines.append("> 合计 **%d** 个接口（学生端 %d + 管理端 %d）。"
                 % (len(student) + len(admin), len(student), len(admin)))
    lines.append("")

    path = os.path.join(OUT_DIR, "接口清单.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("生成 %s" % path)
    return path


def write_db_doc():
    conn = db.get_conn()
    lines = []
    lines.append("# 数据库字典（由实际表结构导出）")
    lines.append("")
    lines.append("> 由 `tools/gen_docs.py` 直接读取 SQLite 表结构生成，与运行中的库完全一致。")
    lines.append("> 数据库类型：SQLite（**%d 张表**），启动时自动建表并做补列迁移。" % len(TABLE_META))
    lines.append("")
    lines.append("## 一、表清单")
    lines.append("")
    lines.append("| 表名 | 中文名 | 论文编号 | 说明 |")
    lines.append("| --- | --- | --- | --- |")
    for table, (cn, tag, desc) in TABLE_META.items():
        lines.append("| `%s` | %s | %s | %s |" % (table, cn, tag, desc))
    lines.append("")

    for table, (cn, tag, desc) in TABLE_META.items():
        info = conn.execute("PRAGMA table_info(%s)" % table).fetchall()
        if not info:
            lines.append("## %s %s（%s）" % (tag, cn, table))
            lines.append("")
            lines.append("> 该表尚未创建，请先启动一次服务端以初始化数据库。")
            lines.append("")
            continue
        idx = conn.execute("PRAGMA index_list(%s)" % table).fetchall()
        lines.append("## %s %s（`%s`）" % (tag, cn, table))
        lines.append("")
        lines.append(desc)
        lines.append("")
        lines.append("| 字段名 | 类型 | 约束 | 默认值 | 说明 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in info:
            _cid, name, col_type, notnull, default, pk = row
            constraints = []
            if pk:
                constraints.append("主键")
            if notnull and not pk:
                constraints.append("非空")
            lines.append("| %s | %s | %s | %s | %s |" % (
                name, col_type or "—", "、".join(constraints) or "—",
                "" if default is None else str(default), _field_hint(name)))
        lines.append("")
        if idx:
            names = [r[1] for r in idx]
            lines.append("索引：%s" % "、".join("`%s`" % n for n in names))
            lines.append("")

    path = os.path.join(OUT_DIR, "数据库字典.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("生成 %s" % path)
    return path


FIELD_HINTS = {
    "id": "自增主键",
    "openid": "微信用户标识；未接入时由本地生成，形如 local_xxxx",
    "nickname": "昵称",
    "avatar_url": "头像地址（当前为空字符串）",
    "total_xp": "累计经验值",
    "status": "1 正常 / 0 停用（管理端可操作）",
    "grade": "学段：primary_low / primary_high / junior",
    "last_login_at": "最近登录时间",
    "created_at": "创建时间（本地时区）",
    "updated_at": "更新时间",
    "quiz_id": "闯关会话业务主键（16 位随机串）",
    "user_id": "所属用户；为空表示游客",
    "title": "闯关标题（主题或「错题重练」）",
    "summary": "预留摘要字段",
    "user_input": "用户原始输入",
    "source": "出题来源：ai / bank / wrongbook",
    "questions_json": "题目数组的 JSON 序列化结果",
    "records_json": "判题明细数组的 JSON 序列化结果",
    "total_questions": "总题数",
    "correct_count": "答对题数",
    "accuracy": "正确率（百分数，保留一位小数）",
    "duration_ms": "本次闯关耗时（毫秒）",
    "report_json": "复盘报告 JSON（掌握度、薄弱知识点、总结、建议、来源）",
    "doc_id": "文档业务主键",
    "filename": "原始文件名",
    "file_type": "扩展名：txt / md / csv / pdf / docx",
    "size_bytes": "文件大小（字节）",
    "content": "提取出的纯文本正文",
    "chunk_index": "分块序号（从 0 开始）",
    "stem": "题干",
    "options_json": "选项数组的 JSON 序列化结果",
    "correct_answer": "正确选项下标（从 0 开始）",
    "user_answer": "学生所选下标；未作答为 -1",
    "analysis": "解析文本",
    "knowledge_point": "知识点名称",
    "wrong_count": "累计答错次数",
    "last_wrong_at": "最近一次答错时间",
    "username": "账号名",
    "password_hash": "PBKDF2-HMAC-SHA256 哈希（12 万次迭代）",
    "salt": "每账号独立随机盐",
    "role": "角色：admin",
    "theme": "主题分类：天文 / 地理 / 生物 / 物理 / 化学 / 科技 / 通用",
    "answer": "正确选项下标",
    "difficulty": "难度：1 易 / 2 中 / 3 难",
    "enabled": "1 启用 / 0 停用（停用后不参与出题）",
    "action": "操作动作，如 pool.create / pool.update / login",
    "detail": "操作详情",
}


def _field_hint(name):
    return FIELD_HINTS.get(name, "—")


def main():
    db.get_conn()
    student, admin = collect_routes()
    write_api_doc(student, admin)
    write_db_doc()
    print("接口数：学生端 %d + 管理端 %d" % (len(student), len(admin)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
