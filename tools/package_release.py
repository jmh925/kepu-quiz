# -*- coding: utf-8 -*-
"""打包交付物：源码 + 文档 + 论文与插图 + 测试报告 + 脚本。

产物：dist/科普知识闯关小程序_交付物_YYYYMMDD.zip
不含运行期产物：数据库、.env、缓存、日志。

为什么从 .cmd 搬到 Python：原先这段逻辑写在 scripts/package.cmd 里，而压缩包名字
是中文，写在 .cmd 的引号里会踩一个很隐蔽的坑——cmd.exe 按 OEM 代码页（中文
Windows 是 GBK）读 .cmd 文件，UTF-8 的中文字节会被重新配对，**吃掉紧跟其后的
那个 ASCII 字符**，包括引号。引号一旦被吃掉，命令结构就散了，cmd 会把中文文本的
碎片当成命令去执行。Python 读写 UTF-8 没有这个问题，所以中文命名这类事情都放这儿，
.cmd 只做纯 ASCII 的转发（见 tools/check_cmd_encoding.py）。

用法：
    python tools/package_release.py
    python tools/package_release.py --no-zip     # 只准备目录，不压缩
"""
import argparse
import datetime
import io
import os
import shutil
import sqlite3
import sys
import zipfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")

# 要收进交付包的目录（目录名）
COPY_DIRS = ["backend", "frontend", "admin", "web", "demo", "docs", "scripts", "tools"]
COPY_FILES = ["README.md", "LICENSE", ".gitignore"]
# 这些不打包：只排除纯缓存。
# 注意 backend/deps（仓库自带的依赖副本）**必须打包** —— README 承诺"不装依赖也能
# 直接启动"，把它排掉的话交付包就变成必须先 pip install 才能跑了。
# 同理 web/shots 与 demo/shots 里的截图是验收证据，也一并带上。
SKIP_DIR_NAMES = {"__pycache__", ".pytest_cache", "node_modules", ".git"}
SKIP_FILE_SUFFIX = (".pyc", ".log", ".db", ".db-wal", ".db-shm")
SKIP_FILE_EXACT = {".env", "kepu.db"}


def ignore(dirpath, names):
    out = set()
    for n in names:
        if n in SKIP_DIR_NAMES or n in SKIP_FILE_EXACT:
            out.add(n)
        elif n.endswith(SKIP_FILE_SUFFIX):
            out.add(n)
    return out


def collect_data_stats(db_path):
    """从数据库里读几个数字，写进包里的说明文档，让人一眼知道这份数据是什么。"""
    stats = {}
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        for key, sql in (
            ("用户数", "SELECT COUNT(*) FROM users"),
            ("闯关记录", "SELECT COUNT(*) FROM quiz_sessions"),
            ("答题记录", "SELECT COUNT(*) FROM answer_records"),
            ("错题本条目", "SELECT COUNT(*) FROM wrong_questions"),
            ("PK 对战", "SELECT COUNT(*) FROM pk_matches"),
            ("知识库文档", "SELECT COUNT(*) FROM knowledge_docs"),
            ("管理端操作日志", "SELECT COUNT(*) FROM admin_logs"),
        ):
            try:
                stats[key] = conn.execute(sql).fetchone()[0]
            except Exception:
                stats[key] = "（读不到）"
        conn.close()
    except Exception as exc:
        stats["读取失败"] = str(exc)
    return stats


def write_readme(pkg, with_data, stats, admin_user, admin_pwd):
    """在包根目录放一份「运行说明.md」：怎么跑、数据是什么、口令是什么。"""
    lines = []
    lines.append("# 运行说明\n")
    lines.append("本包是《中小学生科普知识闯关系统的设计与实现》的毕业设计交付物。\n")

    lines.append("## 一、怎么跑起来\n")
    lines.append("```bash")
    lines.append("cd backend")
    lines.append("pip install -r requirements.txt")
    lines.append("python -m uvicorn app.main:app --host 127.0.0.1 --port 8000")
    lines.append("```\n")
    lines.append("Windows 上也可以直接双击 `scripts\\run_server.cmd`（等同上面三步），")
    lines.append("或双击 `scripts\\share.cmd` 一键起服务并生成一个公网地址给别人看。\n")
    lines.append("启动后打开：\n")
    lines.append("| 地址 | 是什么 |")
    lines.append("| --- | --- |")
    lines.append("| http://127.0.0.1:8000/app/ | 学生端（网页版） |")
    lines.append("| http://127.0.0.1:8000/admin/ | 管理端 |")
    lines.append("| http://127.0.0.1:8000/docs | 接口文档（Swagger） |\n")

    lines.append("## 二、账号与口令\n")
    lines.append("| 角色 | 账号 | 口令 |")
    lines.append("| --- | --- | --- |")
    if with_data:
        lines.append("| 管理员 | %s | %s |" % (admin_user, admin_pwd))
    else:
        lines.append("| 管理员 | admin | kepu@2026（默认值，建议改） |")
    lines.append("| 学生 | 自己注册 | 自己设（6~32 位） |\n")
    if with_data:
        lines.append("管理员口令来自随包附带的 `backend/.env`，可以直接改那个文件里的 "
                     "`ADMIN_PASSWORD=` 然后重启。\n")
        lines.append("> 这个 `.env` 是**给你自己部署用的**，不要连同公网地址一起发给别人。\n")
    else:
        lines.append("> 本包为「仅源码」模式，未包含 `backend/.env` 与数据库，")
        lines.append("> 首次启动会用 `config.py` 里的默认口令建管理员。\n")

    lines.append("## 三、包里有什么\n")
    lines.append("| 目录 | 内容 |")
    lines.append("| --- | --- |")
    lines.append("| `backend/` | FastAPI 服务端（路由、业务、数据访问分层） |")
    lines.append("| `backend/app/bank_part_*.json` | 内置题库数据（225 题，9 个主题） |")
    lines.append("| `frontend/` | 微信小程序原生代码（需微信开发者工具运行） |")
    lines.append("| `web/` | 网页版学生端（零构建原生单页应用，挂载在 `/app/`） |")
    lines.append("| `admin/` | Web 管理端（同样零构建，挂载在 `/admin/`） |")
    lines.append("| `demo/` | 小程序在浏览器里的可交互预览 |")
    lines.append("| `docs/` | 论文正文、插图、接口清单、数据库字典、部署与答辩说明 |")
    lines.append("| `scripts/` | 一键启动 / 一键对外演示 / 一键打包等批处理 |")
    lines.append("| `tools/` | 题库生成与校验、密钥生成、验收与审计脚本 |\n")

    if with_data:
        lines.append("## 四、随包附带的运行数据\n")
        lines.append("数据库：`backend/data/kepu.db`（SQLite 单文件，直接拷走就是全部数据）\n")
        if stats:
            lines.append("| 内容 | 条数 |")
            lines.append("| --- | --- |")
            for k, v in stats.items():
                lines.append("| %s | %s |" % (k, v))
            lines.append("")
        lines.append("> 这些是开发与验收过程中累积的测试数据（含大量 `ui…`/`pk…` 开头的测试账号）。")
        lines.append("> 想要一个干净库：删掉 `backend/data/kepu.db` 再启动，会自动重建空库并建好管理员。\n")

        lines.append("## 五、论文用到的实测数据从哪来\n")
        lines.append("```bash")
        lines.append("python tools/acceptance.py      # 17 组验收一把跑，含真实浏览器端到端")
        lines.append("```")
        lines.append("它会同时产出 `backend/tests/smoke_report.md`（论文第 6 章表 6-1～6-3 的数据来源）。\n")

    with open(os.path.join(pkg, "运行说明.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-zip", action="store_true", help="只准备目录，不压缩")
    ap.add_argument("--with-data", action="store_true",
                    help="连同运行数据一起打包（数据库 + backend/.env + 说明文档）")
    args = ap.parse_args()

    stamp = datetime.datetime.now().strftime("%Y%m%d")
    name = "科普知识闯关小程序_交付物_%s%s" % ("含数据_" if args.with_data else "", stamp)
    pkg = os.path.join(DIST, name)

    if os.path.exists(pkg):
        print("清掉上一次的目录：%s" % pkg)
        shutil.rmtree(pkg, ignore_errors=True)
    os.makedirs(pkg, exist_ok=True)

    print("[1/3] 复制源码与文档 …")
    for d in COPY_DIRS:
        src = os.path.join(ROOT, d)
        if not os.path.isdir(src):
            print("      跳过（不存在）：%s" % d)
            continue
        shutil.copytree(src, os.path.join(pkg, d), ignore=ignore, dirs_exist_ok=True)
        print("      %s" % d)
    for f in COPY_FILES:
        src = os.path.join(ROOT, f)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(pkg, f))
            print("      %s" % f)

    print("[2/3] 清理运行期产物 …")
    removed = 0
    for dirpath, dirnames, filenames in os.walk(pkg):
        for fn in list(filenames):
            if fn in SKIP_FILE_EXACT or fn.endswith(SKIP_FILE_SUFFIX):
                os.remove(os.path.join(dirpath, fn))
                removed += 1
    print("      清掉 %d 个文件（数据库 / 缓存 / 日志 / .env）" % removed)

    # ---- 可选：把运行数据与配置放回去 ----
    # 必须在上面那步清理**之后**做，否则刚放进去的 .db/.env 会被一起清掉。
    if args.with_data:
        print("[2.5/3] 附加运行数据与配置 …")
        data_dir = os.path.join(pkg, "backend", "data")
        os.makedirs(data_dir, exist_ok=True)
        db_src = os.path.join(ROOT, "backend", "data", "kepu.db")
        if os.path.isfile(db_src):
            # 用 SQLite 的在线备份接口拷库，而不是直接 copy 文件。
            # 服务可能正在写库：直接拷 .db 会拿到"写了一半"的状态，
            # WAL 模式下的最新事务还躺在 -wal 里，只拷 .db 会丢数据。
            # 在线备份会把一个事务一致的快照写进目标文件，不需要停服务。
            dst = os.path.join(data_dir, "kepu.db")
            src_conn = sqlite3.connect(db_src)
            dst_conn = sqlite3.connect(dst)
            try:
                with dst_conn:
                    src_conn.backup(dst_conn)
            finally:
                dst_conn.close()
                src_conn.close()
            print("      数据库：kepu.db（%.1f MB，在线备份快照）"
                  % (os.path.getsize(dst) / 1048576.0))
        else:
            print("      没有找到数据库，跳过")
        env_src = os.path.join(ROOT, "backend", ".env")
        if os.path.isfile(env_src):
            shutil.copy2(env_src, os.path.join(pkg, "backend", ".env"))
            print("      配置：backend/.env（含管理员口令，注意别外传）")
        stats = collect_data_stats(db_src) if os.path.isfile(db_src) else {}
        admin_user, admin_pwd = "admin", "kepu@2026"
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import kepu_env
            admin_user, admin_pwd = kepu_env.admin_credentials()
        except Exception:
            pass
        write_readme(pkg, True, stats, admin_user, admin_pwd)
        print("      说明：运行说明.md")
    else:
        write_readme(pkg, False, {}, "admin", "kepu@2026")
        print("      说明：运行说明.md（仅源码模式）")

    if args.no_zip:
        print("[3/3] 跳过压缩（--no-zip）")
        print("\n交付目录：%s" % pkg)
        return 0

    print("[3/3] 压缩 …")
    zip_path = pkg + ".zip"
    if os.path.exists(zip_path):
        os.remove(zip_path)
    count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for dirpath, dirnames, filenames in os.walk(pkg):
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                zf.write(full, os.path.relpath(full, DIST))
                count += 1
    size_mb = os.path.getsize(zip_path) / 1048576.0
    print("\n交付包：%s" % zip_path)
    print("         %d 个文件，%.1f MB" % (count, size_mb))
    print("\ndist/ 目录下现有：")
    for n in sorted(os.listdir(DIST)):
        print("   " + n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
