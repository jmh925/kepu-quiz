# -*- coding: utf-8 -*-
"""直接在 Word 文件上执行文本修改（保留原有格式）。

原则：
1. 段内替换用「run 级手术」，不重写整段，避免丢失字体与缩进；
2. 结论整章替换时，沿用原有段落的格式，只换文字；
3. 每处改动都先断言目标文本存在，改完再复核一次，不合就报错退出。
"""
import copy
import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

SRC = r"E:\dev\kepu-quiz\work\修改版.docx"
CONCL = r"E:\dev\kepu-quiz\docs\thesis-draft\第6章_结论_大章版.md"


def replace_in_paragraph(p, old, new):
    """在段落内做跨 run 的安全替换，保留第一个受影响 run 的格式。"""
    runs = p.runs
    if not runs:
        return False
    full = "".join(r.text for r in runs)
    idx = full.find(old)
    if idx < 0:
        return False
    starts, pos = [], 0
    for r in runs:
        starts.append(pos)
        pos += len(r.text)
    end = idx + len(old)
    first = True
    for i, r in enumerate(runs):
        s, e = starts[i], starts[i] + len(r.text)
        if e <= idx or s >= end:
            continue
        ls = max(idx, s) - s
        le = min(end, e) - s
        if first:
            r.text = r.text[:ls] + new + r.text[le:]
            first = False
        else:
            r.text = r.text[:ls] + r.text[le:]
    return True


doc = Document(SRC)
body = doc.element.body
paras = [c for c in body.iterchildren() if c.tag == qn("w:p")]
P = [Paragraph(e, doc) for e in paras]

ok, fail = 0, 0


def do(idx, old, new, label):
    global ok, fail
    if old not in P[idx].text:
        print("  [FAIL] %s：段%d 内找不到目标文本" % (label, idx))
        fail += 1
        return
    if replace_in_paragraph(P[idx], old, new):
        ok += 1
        print("  [OK  ] %s（段%d）" % (label, idx))
    else:
        print("  [FAIL] %s：run 级替换失败" % label)
        fail += 1


print("=== 第3章 3.2.3 ===")
do(168, "这一时间特征决定了练习类应用的单次使用时长不能过长。",
   "这一时间特征意味着练习类应用的单次使用时长不宜过长。需要说明的是，该判断来自家长与教师的"
   "报告，学生本人的注意力持续时间未直接测量，因此它只能作为设计参考。",
   "决定了→意味着 + 测量限定")

do(177, "19.1%", "18.8%", "19.1%→18.8%")
do(177, "58.3%", "57.2%", "58.3%→57.2%")
do(177, "结果相互一致", "结果方向一致", "相互一致→方向一致")

print()
print("=== 第4章 / 第5章 标题 ===")
do(248, "4.2.2 答题与判断模块设计", "4.2.2 答题与判题模块设计", "4.2.2 判断→判题")
do(340, "5.2.2 答题与判断模块实现", "5.2.2 答题与判题模块实现", "5.2.2 判断→判题")

print()
print("=== 第5章 5.3.2 ===")
do(383, "本章说明的十四项检查全部通过", "本章列出的14项用例全部通过", "14 项用例口径")
do(383, "完整的验收流程共十七项检查，亦全部通过。",
   "完整验收流程的17项检查亦全部通过（清单见附录Ⅱ）。前者用于说明测试思路，"
   "后者是交付时的验收口径，两者不是同一统计口径。",
   "17 项验收口径 + 区分说明")

print()
print("=== 第6章 结论整章替换 ===")
md = io.open(CONCL, encoding="utf-8").read()
new_paras = [x.strip() for x in md.split("\n") if x.strip() and not x.startswith("#")]
print("  改稿段落数：%d" % len(new_paras))

# 结论正文：段390—397 共 8 段
old_idx = list(range(390, 398))
print("  原有段落数：%d（段390—397）" % len(old_idx))

# 1) 前面 8 段直接换文字（沿用原格式）
for k, idx in enumerate(old_idx):
    p = P[idx]
    if not p.runs:
        # 没有 run 时补一个
        p.add_run("")
    # 清掉多余 run，只留第一个
    for r in p.runs[1:]:
        r.text = ""
    p.runs[0].text = new_paras[k] if k < len(new_paras) else ""
print("  [OK  ] 前 %d 段已替换" % len(old_idx))

# 2) 多出来的 2 段：克隆最后一段的格式，插在其后
extra = new_paras[len(old_idx):]
last_el = P[397]._element
anchor = last_el
for text in extra:
    new_el = copy.deepcopy(last_el)
    anchor.addnext(new_el)
    anchor = new_el
    np = Paragraph(new_el, doc)
    for r in np.runs[1:]:
        r.text = ""
    if np.runs:
        np.runs[0].text = text
    else:
        np.add_run(text)
    ok += 1
    print("  [OK  ] 追加一段：%s…" % text[:26])

doc.save(SRC)
print()
print("应用 %d 处，失败 %d 处" % (ok, fail))
print("已保存：%s" % SRC)
