# -*- coding: utf-8 -*-
"""生成 backend/.env，把默认口令与密钥换成随机值。

为什么必须有这一步：仓库是公开的，config.py 里的默认值（管理员 admin /
kepu@2026、开发用 JWT 密钥、开发用管理端令牌）任何人都看得到。一旦服务对外
监听——哪怕只是开个临时隧道给老师看——不改口令就等于把管理端公开挂出去，
而管理端能看全部学生的答题记录、也能改题库。

用法：
    python tools/gen_secrets.py            # 已存在 .env 时拒绝覆盖
    python tools/gen_secrets.py --force    # 覆盖重写（旧的会备份成 .env.bak）
    python tools/gen_secrets.py --show     # 只打印当前生效的账号口令
"""
import argparse
import io
import os
import secrets
import shutil
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(ROOT, "backend", ".env")
BACKUP = ENV_PATH + ".bak"

# 去掉容易看错的字符（0/O、1/l/I），口令要能照着屏幕上念给老师听
ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def human_password(n=14):
    return "".join(secrets.choice(ALPHABET) for _ in range(n))


def parse_env(path):
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="覆盖已存在的 .env（先备份）")
    ap.add_argument("--show", action="store_true", help="只显示当前生效的账号与口令")
    args = ap.parse_args()

    if args.show or (os.path.exists(ENV_PATH) and not args.force):
        cur = parse_env(ENV_PATH)
        if not cur:
            print("还没有 backend/.env —— 现在跑的是 config.py 里的默认值：")
            print("   管理员账号：admin")
            print("    管理员口令：kepu@2026      ← 公开仓库里就有，别对外开")
            print("\n跑 `python tools/gen_secrets.py` 生成随机口令。")
            return 0
        print("backend/.env 里当前生效的值：")
        for k in ("ADMIN_USERNAME", "ADMIN_PASSWORD", "ADMIN_TOKEN", "JWT_SECRET"):
            v = cur.get(k, "")
            if k in ("ADMIN_TOKEN", "JWT_SECRET") and v:
                v = v[:8] + "…（已隐藏）"
            print("   %-15s = %s" % (k, v or "（未设置，用默认值）"))
        if not args.show:
            print("\n.env 已存在，未改动。要重新生成请加 --force。")
        return 0

    if os.path.exists(ENV_PATH):
        shutil.copy2(ENV_PATH, BACKUP)
        print("旧文件已备份到 backend/.env.bak")

    admin_pwd = human_password()
    admin_token = secrets.token_urlsafe(32)
    jwt_secret = secrets.token_urlsafe(48)

    lines = [
        "# 本机/演示用配置。文件已在 .gitignore 里，不会被提交。",
        "# 由 tools/gen_secrets.py 生成，生成时间无关紧要，重跑会换成新的随机值。",
        "",
        "# ---------- 管理员（管理端登录用） ----------",
        "ADMIN_USERNAME=admin",
        "ADMIN_PASSWORD=%s" % admin_pwd,
        "# 接口自动化测试/脚本用的固定令牌，等价于管理员登录后的令牌",
        "ADMIN_TOKEN=%s" % admin_token,
        "",
        "# ---------- 学生 JWT 签名密钥 ----------",
        "JWT_SECRET=%s" % jwt_secret,
        "",
        "# ---------- 服务监听 ----------",
        "# 想让同一 WiFi 下的同学也能访问就取消下面一行的注释（0.0.0.0 = 监听所有网卡）",
        "# APP_HOST=0.0.0.0",
        "APP_PORT=8000",
        "",
        "# ---------- 大模型（留空则走内置 150 题库，答辩演示不依赖网络） ----------",
        "# DEEPSEEK_API_KEY=",
        "",
    ]
    with open(ENV_PATH, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))

    print("已生成：backend/.env")
    print()
    print("  ┌──────────────────────────────────────────────────┐")
    print("  │  管理端账号：admin                               │")
    print("  │  管理端口令：%-34s │" % admin_pwd)
    print("  └──────────────────────────────────────────────────┘")
    print()
    print("  请把口令抄下来 —— 它只存在这个文件里，丢了就重跑本脚本 --force。")
    print("  重启服务后生效。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
