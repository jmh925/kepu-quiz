# -*- coding: utf-8 -*-
"""前端交付前自检：把「人工检查清单」变成可重复执行的脚本。

检查项：
1. 所有 .js 通过语法检查（调用 node --check）；
2. 所有 .json 是合法 JSON（无注释、无尾逗号）；
3. app.json 声明的页面文件都存在（4 个文件齐全）；
4. 页面里没有直接调用 wx.request（必须走 utils/request.js）；
5. 页面里没有使用可选链 ?. 或空值合并 ??（低版本基础库不支持）；
6. api.* 调用的接口路径都在接口白名单内（防止把路径写错）；
7. data 中提到但未初始化的字段（粗检）：WXML 里出现的 {{xxx}} 顶层字段应在 data 中初始化；
8. 文案禁用词检查：不出现「错误」「失败」「暂无数据」「加载中」；
9. 样式里不出现纯红（#f00 / #ff0000 等）。

用法（在仓库根目录）：
    python tools/verify_frontend.py
"""
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FRONTEND = os.path.join(ROOT, "frontend")

ALLOWED_PATHS = {
    "/grades", "/user/login", "/user/profile",
    "/quiz/generate", "/quiz/submit", "/report/generate",
    "/knowledge/documents", "/wrong/questions", "/wrong/practice",
}

BANNED_WORDS = ["错误", "失败", "暂无数据", "加载中"]
BAD_COLORS = re.compile(r"#(f00|ff0000|e60012|d0021b)\b", re.I)

problems = []
notes = []


def report(ok, message):
    print("[%s] %s" % ("OK  " if ok else "FAIL", message))
    if not ok:
        problems.append(message)


def walk(ext):
    out = []
    for dirpath, _dirnames, filenames in os.walk(FRONTEND):
        for name in filenames:
            if name.endswith(ext):
                out.append(os.path.join(dirpath, name))
    return sorted(out)


def check_js():
    node = shutil.which("node")
    if not node:
        notes.append("未找到 node，跳过语法检查")
        return
    for path in walk(".js"):
        proc = subprocess.run([node, "--check", path], capture_output=True, text=True)
        rel = os.path.relpath(path, ROOT)
        report(proc.returncode == 0,
               "语法检查 %s%s" % (rel, "" if proc.returncode == 0 else " → " + proc.stderr.strip()[:120]))


def check_json():
    for path in walk(".json"):
        rel = os.path.relpath(path, ROOT)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                json.load(fh)
            report(True, "JSON 合法 %s" % rel)
        except Exception as exc:
            report(False, "JSON 非法 %s → %s" % (rel, exc))


def check_pages_exist():
    app_json = os.path.join(FRONTEND, "app.json")
    with open(app_json, "r", encoding="utf-8") as fh:
        conf = json.load(fh)
    for page in conf.get("pages", []):
        for ext in (".js", ".wxml", ".wxss", ".json"):
            path = os.path.join(FRONTEND, page + ext)
            report(os.path.exists(path), "页面文件存在 %s%s" % (page, ext))
    for item in (conf.get("tabBar") or {}).get("list", []):
        report(item.get("pagePath") in conf.get("pages", []),
               "tabBar 页面已在 pages 中声明：%s" % item.get("pagePath"))


def check_source_rules():
    for path in walk(".js"):
        rel = os.path.relpath(path, ROOT)
        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        # 页面（pages/）不允许直接调用 wx.request
        if os.sep + "pages" + os.sep in path:
            report("wx.request(" not in src, "%s 未直接调用 wx.request" % rel)
        report("?." not in src.replace("?...", ""), "%s 未使用可选链 ?." % rel)
        report("?? " not in src, "%s 未使用空值合并 ??" % rel)


def check_api_paths():
    for path in walk(".js"):
        rel = os.path.relpath(path, ROOT)
        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        for m in re.finditer(r"api\.(get|post|put|del|upload)\(\s*'([^']+)'", src):
            raw = m.group(2)
            base = raw.split("?")[0]
            # 去掉动态拼接部分，例如 '/knowledge/documents/' + id
            base = re.sub(r"/'\s*\+.*$", "", base)
            base = base.rstrip("/")
            matched = base in ALLOWED_PATHS or any(
                base.startswith(p) for p in ALLOWED_PATHS if p.endswith("documents"))
            report(matched, "%s 接口路径合法：%s" % (rel, raw))


def _data_block(src):
    """截取 js 中 data: { ... } 的内容（括号配平），用于判断字段是否真的初始化过。"""
    m = re.search(r"\bdata\s*:\s*\{", src)
    if not m:
        return ""
    start = m.end() - 1
    depth = 0
    for i in range(start, len(src)):
        ch = src[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    return src[start:]


def check_data_init():
    """粗检：WXML 中的 {{字段}} 顶层字段应在 js 的 data 中初始化过。

    这是启发式检查，为避免误报排除：
    - 模板里的字符串字面量（文案）与 CSS 类名；
    - wx:for 的循环变量（item / index 及其属性）；
    - 未初始化的字段只记为「注意」，不计入失败（有些字段是 setData 动态写入的）。
    """
    loop_vars = set()
    for path in walk(".wxml"):
        rel = os.path.relpath(path, ROOT)
        js = path[:-5] + ".js"
        if not os.path.exists(js):
            continue
        with open(path, "r", encoding="utf-8") as fh:
            wxml = fh.read()
        with open(js, "r", encoding="utf-8") as fh:
            src = fh.read()
        data_src = _data_block(src) or src

        for m in re.finditer(r'wx:for-item="([^"]+)"', wxml):
            loop_vars.add(m.group(1))
        for m in re.finditer(r'wx:for-index="([^"]+)"', wxml):
            loop_vars.add(m.group(1))
        loop_vars.update({"item", "index"})

        fields = set()
        for m in re.finditer(r"\{\{([^}]+)\}\}", wxml):
            expr = m.group(1)
            expr = re.sub(r"'[^']*'", " ", expr)
            expr = re.sub(r'"[^"]*"', " ", expr)
            expr = re.sub(r"\b(%s)\.[A-Za-z0-9_]+" % "|".join(sorted(loop_vars)), " ", expr)
            for ident in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr):
                if ident in loop_vars or ident in (
                        "true", "false", "null", "undefined", "wx", "Math", "parseInt",
                        "parseFloat", "toFixed", "slice", "substr", "length", "split", "join"):
                    continue
                fields.add(ident)
        missing = [f for f in sorted(fields) if f not in data_src]
        report(True, "%s 字段检查完成（未在 data 中声明：%s）"
               % (rel, "、".join(missing) if missing else "无"))
        if missing:
            notes.append("%s 中 %s 未在 data 字面量里声明，请确认是 setData 动态写入"
                         % (rel, "、".join(missing)))


def check_wording():
    """文案检查：只看 WXML 的可见文本与 JS 中的中文字符串字面量，不扫注释。"""
    zh = re.compile(r"[\u4e00-\u9fa5]")
    for path in walk(".wxml"):
        rel = os.path.relpath(path, ROOT)
        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        # 去掉标签属性里的 class/style，只留标签之间的可见文本
        visible = re.sub(r"<[^>]*>", "\n", src)
        hit = [w for w in BANNED_WORDS if w in visible]
        report(not hit, "%s 界面文案合规%s" % (rel, "" if not hit else "：命中 " + "、".join(hit)))
    for path in walk(".js"):
        rel = os.path.relpath(path, ROOT)
        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)          # 块注释
        src = re.sub(r"(?m)^\s*//.*$", " ", src)                   # 行注释
        literals = re.findall(r"'([^'\n]*)'|\"([^\"\n]*)\"", src)
        texts = [a or b for a, b in literals if zh.search(a or b)]
        hit = sorted({w for w in BANNED_WORDS for t in texts if w in t})
        report(not hit, "%s 提示文案合规%s" % (rel, "" if not hit else "：命中 " + "、".join(hit)))


def check_color():
    for path in walk(".wxss"):
        rel = os.path.relpath(path, ROOT)
        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        report(not BAD_COLORS.search(src), "%s 未使用纯红系色值" % rel)


def main():
    print("=== 前端自检：%s ===\n" % FRONTEND)
    if not os.path.isdir(FRONTEND):
        print("前端目录不存在")
        return 2
    check_pages_exist()
    check_json()
    check_js()
    check_source_rules()
    check_api_paths()
    check_data_init()
    check_wording()
    check_color()

    print("\n=== 汇总 ===")
    print("检查项失败数：%d" % len(problems))
    for p in problems:
        print("  - %s" % p)
    for n in notes:
        print("  注意：%s" % n)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
