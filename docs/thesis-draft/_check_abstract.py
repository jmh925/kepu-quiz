# -*- coding: utf-8 -*-
"""自查摘要与关键词是否符合《_规范模板.docx》的要求。"""
import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

t = io.open("00_摘要.md", encoding="utf-8").read()

# ---- 中文摘要字数：从「摘 要」标题后到「关键词」之前 ----
i0 = t.find("摘 要")
i1 = t.find("关键词")
zh = t[i0 + len("摘 要"):i1]
n = len(re.sub(r"\s", "", zh))
print("中文摘要字数：%d（规范要求 300-500 字）→ %s"
      % (n, "符合" if 300 <= n <= 500 else "★ 不合规"))

# ---- 中文关键词 ----
m = re.search(r"关键词：\*\*\s*(.+)", t)
kw = m.group(1).strip()
kws = [k for k in re.split(r"[，,]", kw) if k.strip()]
print("关键词个数：%d（规范要求 3-4 个）→ %s"
      % (len(kws), "符合" if 3 <= len(kws) <= 4 else "★ 不合规"))
print("  关键词：%s" % "，".join(kws))
print("  末词后是否带标点：%s"
      % ("是 ★" if kw.rstrip()[-1] in "，,。." else "否（规范要求不打标点）"))

# ---- 英文摘要 ----
j0 = t.find("## ABSTRACT")
j1 = t.find("KEY WORDS")
en = t[j0:j1]
words = re.findall(r"[A-Za-z][A-Za-z\-']*", en)
print()
print("英文摘要词数：约 %d 词" % len(words))
m2 = re.search(r"KEY WORDS:\*\*\s*(.+)", t)
ekw = m2.group(1).strip()
print("英文关键词：%s（%d 个）" % (ekw, len([x for x in ekw.split(",") if x.strip()])))
print("  末词后是否带标点：%s"
      % ("是 ★" if ekw.rstrip()[-1] in ",." else "否"))

# ---- 结构检查 ----
print()
print("结构：")
for need in ["# 中小学生科普知识闯关小程序设计与实现", "## 摘 要", "## ABSTRACT",
             "**关键词：**", "**KEY WORDS:**"]:
    print("  %-42s %s" % (need, "在" if need in t else "★ 缺失"))
