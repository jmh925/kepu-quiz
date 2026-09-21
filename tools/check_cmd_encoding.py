# -*- coding: utf-8 -*-
"""自检：源码编码卫生。两条规则，都是踩过坑才加的。

## 规则一：所有 .cmd / .bat 必须是纯 ASCII

cmd.exe 按 **OEM 代码页**（中文 Windows 上是 GBK/936）逐字节读取批处理文件。
UTF-8 的中文字节在 GBK 下会被重新配对成别的字符，其后果不只是「乱码」——
一个中文字符会**吃掉紧跟其后的那个 ASCII 字节**。如果那个字节正好是引号，
引号配对就断了，命令结构随之散架，cmd 会把中文文本的碎片当成命令去执行。

真实翻车现场：scripts\\share.cmd 里有一行中文 echo，结果是双击后报一堆
'are.cmd" (' is not recognized、'1' is not recognized，脚本完全跑不起来。
排查起来非常费劲，因为源文件看起来毫无问题。

## 规则二：文本源码不能带 UTF-8 BOM

Python 的 tokenizer 会跳过 BOM，所以 `python 脚本.py` 照跑不误——但
`ast.parse(源码字符串)` 会直接抛 SyntaxError，任何读源码做静态检查的工具
（包括本仓库的若干自检脚本）都会莫名其妙地失败。Windows PowerShell 5.1 里
`Set-Content -Encoding UTF8` 默认**带 BOM**，一次顺手改写就可能埋下去。

真实翻车现场：用 Set-Content 改了一次 tools/acceptance.py，BOM 就进去了，
随后 ast.parse 检查报 "invalid non-printable character U+FEFF"。

## 约定

**.cmd 只做纯 ASCII 的转发**，所有中文输出交给 Python（UTF-8 安全）；
**文本源码一律 UTF-8 无 BOM**。本脚本是这两条约定的守门人，已纳入 acceptance.py。

用法：python tools/check_cmd_encoding.py
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOM = b"\xef\xbb\xbf"
NO_BOM_EXT = (".py", ".js", ".json", ".cmd", ".bat", ".html", ".css", ".md")
SKIP_DIRS = {".git", "deps", "__pycache__", "node_modules", "dist"}

problems = []


def check(ok, msg):
    print(("[OK  ] " if ok else "[FAIL] ") + msg)
    if not ok:
        problems.append(msg)


def walk_files(exts):
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.lower().endswith(exts):
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


def main():
    # ---------- 规则一：批处理纯 ASCII ----------
    files = walk_files((".cmd", ".bat"))
    print("规则一：检查 %d 个批处理文件是否为纯 ASCII\n" % len(files))
    for path in files:
        rel = os.path.relpath(path, ROOT)
        with open(path, "rb") as fh:
            raw = fh.read()
        bad = [(i, b) for i, b in enumerate(raw) if b > 127]
        if not bad:
            check(True, "%s（纯 ASCII）" % rel)
            continue
        lines = raw.split(b"\n")
        hits = [n for n, line in enumerate(lines, 1) if any(b > 127 for b in line)]
        check(False, "%s 含 %d 个非 ASCII 字节（第 %s 行）—— 中文要挪到 Python 里"
              % (rel, len(bad), "、".join(str(n) for n in hits[:8])
                 + ("…" if len(hits) > 8 else "")))
        print("        第 %d 行：%s" % (hits[0],
              lines[hits[0] - 1].decode("utf-8", "replace")[:100].strip()))

    # ---------- 规则二：源码无 BOM ----------
    print("\n规则二：检查文本源码是否带 UTF-8 BOM\n")
    scanned = 0
    bom_files = []
    for path in walk_files(NO_BOM_EXT):
        scanned += 1
        try:
            with open(path, "rb") as fh:
                head = fh.read(3)
        except OSError:
            continue
        if head == BOM:
            bom_files.append(os.path.relpath(path, ROOT))
    check(not bom_files, "扫描 %d 个文本源码，带 BOM 的 %d 个%s"
          % (scanned, len(bom_files), "" if not bom_files else "：" + str(bom_files)))
    if bom_files:
        print("        去掉 BOM：读成 bytes，若以 b'\\xef\\xbb\\xbf' 开头就写回去掉前 3 字节的内容。")
        print("        PowerShell 5.1 的 Set-Content -Encoding UTF8 会加 BOM，")
        print("        改用 [System.IO.File]::WriteAllText($p,$c,(New-Object System.Text.UTF8Encoding($false)))。")

    print()
    if problems:
        print("编码卫生有问题（详见本脚本头部说明）：")
        print("  .cmd 里的中文会破坏 cmd.exe 解析，中文提示请放 Python；")
        print("  文本源码请存成 UTF-8 无 BOM。")
    print("未通过：%d 项" % len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
