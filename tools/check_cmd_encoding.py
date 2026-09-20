# -*- coding: utf-8 -*-
"""自检：所有 .cmd / .bat 文件必须是纯 ASCII。

为什么这条规则值得单独守：cmd.exe 按 **OEM 代码页**（中文 Windows 上是 GBK/936）
逐字节读取批处理文件。UTF-8 的中文字节在 GBK 下会被重新配对成别的字符，其后果不只是
「乱码」——一个中文字符会**吃掉紧跟其后的那个 ASCII 字节**。如果那个字节正好是引号，
引号配对就断了，命令结构随之散架，cmd 会把中文文本的碎片当成命令去执行。

真实翻车现场（本仓库发生过）：scripts\\share.cmd 里有一行中文 echo，结果是双击后
报一堆 'are.cmd" (' is not recognized、'1' is not recognized，脚本完全跑不起来。
排查起来非常费劲，因为源文件看起来毫无问题。

所以约定：**.cmd 只做纯 ASCII 的转发**，所有中文输出交给 Python（UTF-8 安全）。
本脚本就是这条约定的守门人，已纳入 tools/acceptance.py。

用法：python tools/check_cmd_encoding.py
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

problems = []


def check(ok, msg):
    print(("[OK  ] " if ok else "[FAIL] ") + msg)
    if not ok:
        problems.append(msg)


def find_scripts():
    """仓库内所有 .cmd / .bat（跳过 .git 与依赖副本）。"""
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames
                       if d not in (".git", "deps", "__pycache__", "node_modules", "dist")]
        for fn in filenames:
            if fn.lower().endswith((".cmd", ".bat")):
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


def main():
    files = find_scripts()
    print("检查 %d 个批处理文件是否为纯 ASCII：\n" % len(files))
    for path in files:
        rel = os.path.relpath(path, ROOT)
        with open(path, "rb") as fh:
            raw = fh.read()
        bad = [(i, b) for i, b in enumerate(raw) if b > 127]
        if not bad:
            check(True, "%s（纯 ASCII）" % rel)
            continue
        # 定位前几处非 ASCII 字节所在的行，方便直接去改
        lines = raw.split(b"\n")
        hits = []
        for lineno, line in enumerate(lines, 1):
            if any(b > 127 for b in line):
                hits.append(lineno)
        check(False, "%s 含 %d 个非 ASCII 字节（第 %s 行）—— 中文要挪到 Python 里"
              % (rel, len(bad), "、".join(str(n) for n in hits[:8])
                 + ("…" if len(hits) > 8 else "")))
        # 打印第一处上下文，省得再去找
        first_line = hits[0] - 1
        print("        第 %d 行：%s" % (hits[0],
              lines[first_line].decode("utf-8", "replace")[:100].strip()))

    print()
    if problems:
        print("批处理文件里的中文会破坏 cmd.exe 的解析（详见本脚本头部说明）：")
        print("  把中文提示移到 Python 脚本里，.cmd 只留纯 ASCII 的转发。")
    print("未通过：%d 项" % len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
