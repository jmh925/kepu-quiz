# -*- coding: utf-8 -*-
"""给验收脚本读 backend/.env 用的小工具（只用标准库）。

背景：管理员口令现在由 `tools/gen_secrets.py` 随机生成并写进 backend/.env，
再靠 `admin_db.ensure_default_admin()` 同步进库。脚本如果还把 `kepu@2026`
写死，一旦轮换过口令就会全部失败——所以统一从这里取。

刻意不 import backend/app/config.py：验收脚本要能独立跑，不该被拉进
FastAPI 那一套依赖里。
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(ROOT, "backend", ".env")

DEFAULTS = {
    "ADMIN_USERNAME": "admin",
    "ADMIN_PASSWORD": "kepu@2026",     # config.py 里的默认值
    "ADMIN_TOKEN": "kepu-admin-token-dev",
}


def read_env(path=ENV_PATH):
    """把 .env 读成 dict；文件不存在返回空 dict。"""
    out = {}
    if not os.path.exists(path):
        return out
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or line.startswith("export "):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                if key:
                    out[key] = value
    except OSError:
        pass
    return out


def value(key, default=None):
    """取配置值：真实环境变量 > backend/.env > 内置默认值。"""
    got = os.getenv(key)
    if got:
        return got
    got = read_env().get(key)
    if got:
        return got
    return DEFAULTS.get(key, default)


def admin_credentials():
    """返回 (账号, 口令)。"""
    return value("ADMIN_USERNAME"), value("ADMIN_PASSWORD")


def admin_token():
    return value("ADMIN_TOKEN")


def base_url():
    return os.getenv("KEPU_BASE_URL", "http://127.0.0.1:8000")
