# -*- coding: utf-8 -*-
"""交付前总验收：一次跑完所有可自动化的检查。

包含：
1. 后端冒烟测试（40 功能 + 7 性能 + 9 降级用例）；
2. 管理端接口联通性（看板 / 用户停用 / 题库增删改查 / 日志）；
3. 前端静态检查（语法、JSON、接口路径、文案与配色规范）；
4. 论文成稿检查（字数、图表、禁用词、必备事实、参考文献）。

用法（先启动服务端：scripts\\run_server.cmd，然后）：
    python tools/acceptance.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(BACKEND, "tests"))

from client import Client                     # noqa: E402

PY = sys.executable
results = []


def section(title):
    print("\n" + "=" * 68)
    print(title)
    print("=" * 68)


def run(cmd, cwd=ROOT):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    tail = (proc.stdout or "").strip().split("\n")[-3:]
    for line in tail:
        if line.strip():
            print("   " + line.strip())
    return proc.returncode == 0


def main():
    base = os.getenv("KEPU_BASE_URL", "http://127.0.0.1:8000")

    section("1. 后端冒烟测试")
    c = Client(base)
    if c.get("/api/v1/health").status == 0:
        print("   服务端未启动，请先运行 scripts\\run_server.cmd")
        return 2
    ok = run([PY, os.path.join("tests", "smoke_test.py"), "--repeat", "3"], cwd=BACKEND)
    results.append(("后端冒烟测试（49 条用例）", ok))

    section("2. 管理端接口联通性")
    admin_ok = True
    sa = Client(base)
    login = sa.admin_login()
    print("   登录：code=%s" % login.code)
    admin_ok &= login.code == 0

    dash = sa.get("/api/v1/admin/dashboard")
    print("   看板：code=%s 用户数=%s" % (dash.code, (dash.data or {}).get("users", {}).get("total")))
    admin_ok &= dash.code == 0

    trend = sa.get("/api/v1/admin/trend?days=7")
    print("   趋势：code=%s 数据点=%s" % (trend.code, len((trend.data or {}).get("points") or [])))
    admin_ok &= trend.code == 0

    users = sa.get("/api/v1/admin/users?size=5")
    items = (users.data or {}).get("items") or []
    print("   用户列表：code=%s 返回 %d 条" % (users.code, len(items)))
    admin_ok &= users.code == 0
    if items:
        uid = items[0]["id"]
        st = sa.post("/api/v1/admin/users/%s/status?status=1" % uid)
        print("   用户状态设置：code=%s" % st.code)
        admin_ok &= st.code == 0

    made = sa.post("/api/v1/admin/questions", {
        "theme": "天文", "grade": "primary_high", "stem": "验收自检题：地球唯一的天然卫星是？",
        "options": ["太阳", "月球", "火星", "金星"], "answer": 1,
        "analysis": "月球是地球唯一的天然卫星。", "knowledge_point": "天体", "difficulty": 1})
    qid = (made.data or {}).get("id")
    print("   新增题目：code=%s id=%s" % (made.code, qid))
    admin_ok &= made.code == 0 and bool(qid)

    upd = sa.put("/api/v1/admin/questions/%s" % qid, {"difficulty": 2})
    print("   修改题目：code=%s（仅更新提交字段）" % upd.code)
    admin_ok &= upd.code == 0

    after = sa.get("/api/v1/admin/questions?size=5")
    row = next((x for x in (after.data or {}).get("items") or [] if x["id"] == qid), None)
    keep_theme = bool(row) and row.get("theme") == "天文"
    print("   修改后主题仍为「天文」：%s（验证只更新提交的字段）" % keep_theme)
    admin_ok &= keep_theme

    dele = sa.delete("/api/v1/admin/questions/%s" % qid)
    print("   删除题目：code=%s" % dele.code)
    admin_ok &= dele.code == 0

    logs = sa.get("/api/v1/admin/logs?limit=10")
    print("   操作日志：code=%s 条数=%s" % (logs.code, len((logs.data or {}).get("logs") or [])))
    admin_ok &= logs.code == 0 and len((logs.data or {}).get("logs") or []) > 0

    results.append(("管理端接口联通性（9 项）", admin_ok))

    section("3. 前端静态检查")
    ok = run([PY, os.path.join("tools", "verify_frontend.py")])
    results.append(("前端静态检查", ok))

    section("4. 错题本增删改查（接口层）")
    ok = run([PY, os.path.join("tools", "check_wrongbook_crud.py")])
    results.append(("错题本 CRUD（接口层，15 项）", ok))

    section("4.1 题库完整性与学段分级")
    ok = run([PY, os.path.join("tools", "check_bank_integrity.py")])
    results.append(("题库完整性 + 学段分离（150 题）", ok))
    ok = run([PY, os.path.join("tools", "check_grade_split.py")])
    results.append(("学段分级出题（低年级与初中不重题）", ok))

    section("5. 论文成稿检查")
    ok = run([PY, os.path.join("tools", "check_thesis.py")])
    results.append(("论文成稿检查", ok))

    section("6. 网页版端到端（真实浏览器点一遍）")
    ok = run([PY, os.path.join("tools", "verify_web.py")])
    results.append(("网页版端到端（27 项 + 截图）", ok))

    section("验收汇总")
    failed = 0
    for name, ok in results:
        print("   [%s] %s" % ("通过" if ok else "未通过", name))
        if not ok:
            failed += 1
    print("\n   共 %d 项检查，未通过 %d 项。" % (len(results), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
