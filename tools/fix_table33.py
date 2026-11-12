# -*- coding: utf-8 -*-
"""重建表3-3「各项功能的需求程度」。

问题：原表是「表头 1 行 + 数据全塞在第 2 行单元格」的结构，且第一列 9 段、
后三列 12 段（多出 3 个空段），导致数值与功能项错位——"错题自动收录并可复习"
显示为空白，而 81/46/92.0% 被排到了"查看孩子的薄弱知识点"那一行。

做法：沿用原表的表格属性（边框、宽度），按 10 行 × 4 列重建。
数据取自 docs/thesis-draft/03_第3章.md 的 表3-3，与正文表述一致。
"""
import copy
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt

SRC = r"E:\dev\kepu-quiz\work\修改版.docx"

HEADER = ["功能项", "非常需要", "比较需要", "合计比例"]
ROWS = [
    ["答错后即时给出讲解", "89", "42", "94.9%"],
    ["按学段分级出题", "84", "45", "93.5%"],
    ["错题自动收录并可复习", "81", "46", "92.0%"],
    ["查看孩子的薄弱知识点", "76", "48", "89.9%"],
    ["单次练习时长可控", "62", "56", "85.5%"],
    ["电脑与手机都能使用", "58", "45", "74.6%"],
    ["段位、等级等长期目标", "39", "47", "62.3%"],
    ["上传自己的讲义出题", "34", "45", "57.2%"],
    ["同伴对战", "26", "35", "44.2%"],
]


def main():
    doc = Document(SRC)

    # 定位：首格为「功能项」的表格
    target = None
    for i, t in enumerate(doc.tables):
        if t.rows and t.rows[0].cells[0].text.strip() == "功能项":
            target = t
            print("  找到目标表：第 %d 张（%d 行 × %d 列）" % (i + 1, len(t.rows), len(t.columns)))
            break
    if target is None:
        print("  [FAIL] 未找到「功能项」表")
        return 1

    old_tbl = target._tbl
    old_pr = old_tbl.find(qn("w:tblPr"))

    new = doc.add_table(rows=len(ROWS) + 1, cols=len(HEADER))
    # 继承原表的边框与宽度设置，避免样式突变
    if old_pr is not None:
        new._tbl.remove(new._tbl.find(qn("w:tblPr")))
        new._tbl.insert(0, copy.deepcopy(old_pr))

    for ci, h in enumerate(HEADER):
        cell = new.rows[0].cells[ci]
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(h)
        r.font.bold = True
        r.font.size = Pt(10.5)

    for ri, row in enumerate(ROWS, start=1):
        for ci, v in enumerate(row):
            cell = new.rows[ri].cells[ci]
            cell.text = ""
            p = cell.paragraphs[0]
            p.alignment = (WD_ALIGN_PARAGRAPH.LEFT if ci == 0 else WD_ALIGN_PARAGRAPH.CENTER)
            r = p.add_run(v)
            r.font.size = Pt(10.5)

    # 新表放到旧表位置，再删旧表
    old_tbl.addprevious(new._tbl)
    old_tbl.getparent().remove(old_tbl)

    doc.save(SRC)
    print("  已重建：%d 行 × %d 列（表头 + %d 项）" % (len(ROWS) + 1, len(HEADER), len(ROWS)))
    print("  已保存：%s" % SRC)
    return 0


if __name__ == "__main__":
    sys.exit(main())
