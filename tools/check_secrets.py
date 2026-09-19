# -*- coding: utf-8 -*-
"""自检：管理员口令轮换到底有没有生效。

为什么单独守这一项：`config.py` 里的默认口令 `kepu@2026` 与开发用 JWT 密钥、
管理端令牌都写在**公开仓库**里，而管理端能看全部学生的答题记录、也能改题库。
一旦服务对外监听（局域网 / 公网隧道 / 正式部署），没换口令就等于把它公开挂出去。

而这个坑极其容易复发：早先 `ensure_default_admin()` 只判"管理员账号是否已存在"，
存在就 return，于是改 `ADMIN_PASSWORD` 再重启**完全不起作用**——库里还是老口令的哈希，
改了配置的人以为自己安全了，其实老口令照样能登。现在配置是权威来源，
本脚本就是盯着这一条：轮换过口令之后，老默认口令必须登不进去。

用法：
    python tools/check_secrets.py                # 未轮换时只提示，不算失败
    python tools/check_secrets.py --require-rotated   # 要求必须已轮换（对外开之前用）
"""
import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kepu_env                                        # noqa: E402

BASE = os.getenv("KEPU_BASE_URL", "http://127.0.0.1:8000")
DEFAULT_ADMIN_PWD = "kepu@2026"
DEFAULT_ADMIN_TOKEN = "kepu-admin-token-dev"

problems = []
notes = []


def check(ok, msg):
    print(("[OK  ] " if ok else "[FAIL] ") + msg)
    if not ok:
        problems.append(msg)


def login(username, password):
    body = json.dumps({"username": username, "password": password}).encode("utf-8")
    req = urllib.request.Request(BASE + "/api/v1/admin/login", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8")).get("code")
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8")).get("code")
        except Exception:
            return -1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--require-rotated", action="store_true",
                    help="要求必须已轮换过口令（对外开之前用这个）")
    args = ap.parse_args()

    env_path = kepu_env.ENV_PATH
    rotated = bool(kepu_env.read_env().get("ADMIN_PASSWORD"))
    user, pwd = kepu_env.admin_credentials()

    print("backend/.env    ：%s" % ("已生成" if rotated else "不存在（在用 config.py 的默认值）"))
    print("当前生效账号    ：%s" % user)
    print("当前生效口令    ：%s" % ("（随机，已轮换）" if rotated else DEFAULT_ADMIN_PWD + "（默认值）"))
    print()

    check(login(user, pwd) == 0, "用当前配置的口令可以登录（说明服务和配置是一致的）")

    if rotated:
        check(login(user, DEFAULT_ADMIN_PWD) != 0,
              "仓库里公开的默认口令 %s 已经登不进去 —— 轮换确实生效" % DEFAULT_ADMIN_PWD)
    else:
        notes.append("还没轮换口令。本机自用没问题；**对外监听之前**请跑 "
                     "`python tools/gen_secrets.py` 并重启服务。")
        if args.require_rotated:
            check(False, "要求已轮换口令，但 backend/.env 不存在")

    # 固定管理端令牌：默认值同样是公开的，对外开之前必须换
    if rotated:
        check(kepu_env.admin_token() != DEFAULT_ADMIN_TOKEN,
              "固定管理端令牌已不是仓库里的默认值")

    print()
    for n in notes:
        print("注意：" + n)
    print("\n未通过：%d 项" % len(problems))
    for x in problems:
        print("  - " + x)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
