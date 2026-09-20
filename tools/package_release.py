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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-zip", action="store_true", help="只准备目录，不压缩")
    args = ap.parse_args()

    stamp = datetime.datetime.now().strftime("%Y%m%d")
    name = "科普知识闯关小程序_交付物_%s" % stamp
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
