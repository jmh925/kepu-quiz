# -*- coding: utf-8 -*-
"""全局配置：环境变量优先，全部提供默认值，保证「零配置也能跑」。

设计说明：
- 所有路径默认相对 backend/ 目录解析，避免"换个目录启动就找不到库"的问题；
- DeepSeek Key 留空时系统自动降级到内置题库，答辩演示不依赖网络与付费额度；
- 管理端口令与 JWT 密钥都支持环境变量注入，源码中不含真实密钥。
"""
import os

# backend/ 目录（本文件位于 backend/app/config.py）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _path(value, default):
    """相对路径按 backend/ 解析，绝对路径原样返回。"""
    p = value or default
    return p if os.path.isabs(p) else os.path.join(BASE_DIR, p)


class Settings:
    # ---------- 服务 ----------
    app_host: str = os.getenv("APP_HOST", "127.0.0.1")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    # 联调阶段允许跨域；生产建议改成小程序合法域名并关闭 *
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")

    # ---------- 数据库 ----------
    db_path: str = _path(os.getenv("DB_PATH"), os.path.join("data", "kepu.db"))
    db_echo: bool = os.getenv("DB_ECHO", "0") == "1"

    # ---------- DeepSeek（OpenAI 兼容接口） ----------
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    deepseek_timeout: int = int(os.getenv("DEEPSEEK_TIMEOUT", "120"))

    # ---------- JWT ----------
    jwt_secret: str = os.getenv("JWT_SECRET", "kepu-quiz-dev-secret-change-me")
    jwt_expire_days: int = int(os.getenv("JWT_EXPIRE_DAYS", "7"))

    # ---------- 管理端 ----------
    admin_username: str = os.getenv("ADMIN_USERNAME", "admin")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "kepu@2026")
    admin_token: str = os.getenv("ADMIN_TOKEN", "kepu-admin-token-dev")
    # 管理端登录失败锁定：连续失败 n 次后锁定 m 秒（防口令爆破，测试用例会验证）
    admin_max_fail: int = int(os.getenv("ADMIN_MAX_FAIL", "5"))
    admin_lock_seconds: int = int(os.getenv("ADMIN_LOCK_SECONDS", "60"))

    # ---------- 出题参数 ----------
    default_question_count: int = 8
    max_question_count: int = 15
    # 检索增强：注入 Prompt 的参考资料最大字数
    rag_context_max: int = int(os.getenv("RAG_CONTEXT_MAX", "2000"))
    rag_top_k: int = int(os.getenv("RAG_TOP_K", "3"))
    # 知识库文档单文件大小上限（字节），默认 2MB
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(2 * 1024 * 1024)))


settings = Settings()
