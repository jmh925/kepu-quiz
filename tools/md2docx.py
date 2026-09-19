# -*- coding: utf-8 -*-
"""把论文 Markdown 合并稿转换成符合学校规范的 .docx。

为什么自己写转换器：论文对格式有硬性要求（章标题三号黑体居中、节标题四号黑体、
三线表、图名在图下方五号黑体、正文小四宋体固定行距 20 磅），
通用的 Markdown 转换工具做不到，而逐条手工调整又容易漏改。

用法（在仓库根目录）：
    python tools/md2docx.py                      # 合并 docs/thesis/part_*.md 并导出
    python tools/md2docx.py --input a.md b.md    # 指定输入文件
    python tools/md2docx.py --no-merge           # 只转换已合并好的 05_论文全文.md

产物：docs/thesis/论文正文.docx
"""
import argparse
import glob
import os
import re
import sys

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
THESIS = os.path.join(ROOT, "docs", "thesis")
FIGURES = os.path.join(ROOT, "docs", "figures")

# ---------------- 字体与字号（按学校撰写规范） ----------------
FONT_SONG = "宋体"
FONT_HEI = "黑体"
FONT_KAI = "楷体"
FONT_EN = "Times New Roman"

SIZE_CH1 = Pt(16)      # 三号
SIZE_H2 = Pt(14)       # 四号
SIZE_H3 = Pt(12)       # 小四
SIZE_BODY = Pt(12)     # 小四
SIZE_CAPTION = Pt(10.5)  # 五号


# ==================================================================
# 基础工具
# ==================================================================
def set_run(run, size=SIZE_BODY, bold=False, font_cn=FONT_SONG, font_en=FONT_EN,
            color=None):
    run.font.size = size
    run.font.bold = bold
    run.font.name = font_en
    run._element.rPr.rFonts.set(qn("w:eastAsia"), font_cn)
    if color:
        run.font.color.rgb = color


def set_para_format(p, align=None, first_line_indent=True, line_spacing=20,
                    space_before=0, space_after=0):
    """固定行距 20 磅、正文首行缩进 2 字符。"""
    if align is not None:
        p.alignment = align
    pf = p.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(line_spacing)
    pf.space_before = Pt(space_before)
    pf.space_after = Pt(space_after)
    if first_line_indent and align is None:
        pf.first_line_indent = Pt(24)      # 2 字符 × 小四 12pt


def add_body(doc, text, indent=True, align=WD_ALIGN_PARAGRAPH.JUSTIFY):
    p = doc.add_paragraph()
    set_para_format(p, align=align, first_line_indent=indent)
    # 处理行内加粗 **xx**
    for seg in re.split(r"(\*\*[^*]+\*\*)", text):
        if not seg:
            continue
        if seg.startswith("**") and seg.endswith("**"):
            set_run(p.add_run(seg[2:-2]), bold=True)
        else:
            set_run(p.add_run(seg))
    return p


def add_heading(doc, level, text):
    """章标题三号黑体居中（段前 2 行段后 1 行），节四号黑体左起，小节小四黑体左起。"""
    p = doc.add_paragraph()
    if level == 1:
        set_para_format(p, align=WD_ALIGN_PARAGRAPH.CENTER, first_line_indent=False,
                        line_spacing=20, space_before=20, space_after=10)
        set_run(p.add_run(text), size=SIZE_CH1, bold=True, font_cn=FONT_HEI)
    elif level == 2:
        set_para_format(p, align=WD_ALIGN_PARAGRAPH.LEFT, first_line_indent=False,
                        space_before=8, space_after=4)
        set_run(p.add_run(text), size=SIZE_H2, bold=True, font_cn=FONT_HEI)
    else:
        set_para_format(p, align=WD_ALIGN_PARAGRAPH.LEFT, first_line_indent=False,
                        space_before=6, space_after=3)
        set_run(p.add_run(text), size=SIZE_H3, bold=True, font_cn=FONT_HEI)
    return p


def add_caption(doc, text):
    """图名在图下方、表名在表上方：五号黑体居中。"""
    p = doc.add_paragraph()
    set_para_format(p, align=WD_ALIGN_PARAGRAPH.CENTER, first_line_indent=False,
                    line_spacing=14, space_before=2, space_after=6)
    set_run(p.add_run(text), size=SIZE_CAPTION, font_cn=FONT_HEI)
    return p


def add_picture(doc, filename, width_cm=14.0):
    """插入插图：按文件名在 docs/figures 下查找，找不到则留占位说明。"""
    path = os.path.join(FIGURES, filename)
    if not os.path.exists(path):
        p = doc.add_paragraph()
        set_para_format(p, align=WD_ALIGN_PARAGRAPH.CENTER, first_line_indent=False)
        set_run(p.add_run("[缺少插图文件：%s]" % filename), size=SIZE_CAPTION,
                font_cn=FONT_KAI, color=RGBColor(0xC0, 0x39, 0x2B))
        return False
    p = doc.add_paragraph()
    set_para_format(p, align=WD_ALIGN_PARAGRAPH.CENTER, first_line_indent=False,
                    line_spacing=12)
    p.add_run().add_picture(path, width=Cm(width_cm))
    return True


def _set_cell_border(cell, edges):
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for edge, size in edges.items():
        el = OxmlElement("w:" + edge)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(size))
        el.set(qn("w:color"), "000000")
        borders.append(el)
    tc_pr.append(borders)


def _text_units(text):
    """按显示宽度估算字符数：中日韩字符记 2，其余记 1。"""
    units = 0
    for ch in text:
        units += 2 if ("\u4e00" <= ch <= "\u9fff" or "\u3000" <= ch <= "\u303f"
                       or "\uff00" <= ch <= "\uffef") else 1
    return units


def _set_col_widths(table, rows, total_cm=16.0):
    """按各列最长内容的宽度占比分配列宽。

    为什么要手动算：Word 的自动列宽遇到「路径 / 判题明细」这类长英文串，
    会把该列压得很窄、把短列撑得很宽，读起来很难受。
    这里按内容宽度比例分配，并给每列设下限，保证表格整齐且不超页宽。
    """
    cols = max(len(r) for r in rows)
    weights = []
    for j in range(cols):
        longest = 0
        for r in rows:
            if j < len(r):
                longest = max(longest, _text_units(r[j]))
        weights.append(max(4, min(longest, 60)))
    total = float(sum(weights)) or 1.0
    widths = [max(1.1, total_cm * w / total) for w in weights]
    # 归一化到页宽（可排版宽度 16cm）
    scale = total_cm / sum(widths)
    widths = [w * scale for w in widths]
    for row in table.rows:
        for j, cell in enumerate(row.cells):
            if j < len(widths):
                cell.width = Cm(widths[j])


def add_table(doc, rows):
    """三线表：顶线 1.5 磅、表头下线 0.75 磅、底线 1.5 磅，无竖线。"""
    if not rows:
        return
    cols = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    for i, row in enumerate(rows):
        for j in range(cols):
            cell = table.cell(i, j)
            text = row[j] if j < len(row) else ""
            cell.text = ""
            p = cell.paragraphs[0]
            set_para_format(p, align=WD_ALIGN_PARAGRAPH.CENTER, first_line_indent=False,
                            line_spacing=14)
            # 单元格内允许行内加粗
            for seg in re.split(r"(\*\*[^*]+\*\*)", text):
                if not seg:
                    continue
                if seg.startswith("**") and seg.endswith("**"):
                    set_run(p.add_run(seg[2:-2]), size=SIZE_CAPTION, bold=True)
                else:
                    set_run(p.add_run(seg), size=SIZE_CAPTION)
            # 三线表边框：仅首行上、首行下、末行下
            edges = {}
            if i == 0:
                edges["top"] = 12
                edges["bottom"] = 6
            if i == len(rows) - 1:
                edges["bottom"] = 12
            _set_cell_border(cell, edges)
    _set_col_widths(table, rows)
    doc.add_paragraph()


def add_code_block(doc, lines):
    for line in lines:
        p = doc.add_paragraph()
        set_para_format(p, align=WD_ALIGN_PARAGRAPH.LEFT, first_line_indent=False,
                        line_spacing=13, space_before=0, space_after=0)
        run = p.add_run(line if line else " ")
        run.font.size = Pt(10)
        run.font.name = "Consolas"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_SONG)
    doc.add_paragraph()


# ==================================================================
# Markdown 解析
# ==================================================================
def parse_markdown(doc, text):
    """按行解析论文 Markdown 并写入 docx。

    支持：章/节/小节标题、正文段落（含 **加粗**）、无序列表、表格、
      ``` 代码块、`> 图 x-y 名称（见 path）` 插图占位、`---` 分隔线。
    """
    lines = text.split("\n")
    i = 0
    para_buf = []
    in_code = False
    code_buf = []

    def flush_para():
        if not para_buf:
            return
        merged = " ".join(x.strip() for x in para_buf if x.strip())
        para_buf.clear()
        if not merged:
            return
        if merged.startswith("|"):
            return
        add_body(doc, merged)

    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()

        # 代码块
        if stripped.startswith("```"):
            if in_code:
                add_code_block(doc, code_buf)
                code_buf, in_code = [], False
            else:
                flush_para()
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(raw)
            i += 1
            continue

        # 空行
        if not stripped:
            flush_para()
            i += 1
            continue

        # 分隔线
        if re.match(r"^-{3,}$", stripped):
            flush_para()
            i += 1
            continue

        # 插图占位：> 图 4-1 xxx（见 docs/figures/xxx.png）
        m = re.match(r"^>\s*(图\s*\d+-\d+[^\n（(]*)[（(]\s*见\s*([^\s）)]+)\s*[）)]", stripped)
        if m:
            flush_para()
            caption, figpath = m.group(1).strip(), m.group(2).strip()
            add_picture(doc, os.path.basename(figpath))
            add_caption(doc, caption)
            i += 1
            continue

        # 引号引用的说明文字：作为小字号说明段落
        if stripped.startswith(">"):
            flush_para()
            note = stripped.lstrip(">").strip()
            if note:
                p = doc.add_paragraph()
                set_para_format(p, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
                                first_line_indent=False, line_spacing=16)
                set_run(p.add_run(note), size=Pt(10.5), font_cn=FONT_KAI,
                        color=RGBColor(0x44, 0x4A, 0x53))
            i += 1
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s*(.+)$", stripped)
        if m:
            flush_para()
            level = len(m.group(1))
            title = m.group(2).strip()
            add_heading(doc, min(level, 3), title)
            i += 1
            continue

        # 表格
        if stripped.startswith("|"):
            flush_para()
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i].strip())
                i += 1
            rows = []
            for bi, row_line in enumerate(block):
                cells = [c.strip() for c in row_line.strip("|").split("|")]
                if bi == 1 and all(re.match(r"^:?-{2,}:?$", c) for c in cells if c):
                    continue        # 分隔行
                rows.append([c.replace("<br>", " ").replace("&nbsp;", " ") for c in cells])
            # 表格标题：表格上方最近的一行若是「表 x-y ...」则由正文承载，此处直接输出表格
            add_table(doc, rows)
            continue

        # 表格标题行（表 4-1 xxx）单独成段，右上方：五号黑体居中
        if re.match(r"^表\s*\d+-\d+", stripped):
            flush_para()
            add_caption(doc, stripped)
            i += 1
            continue

        # 无序 / 有序列表
        m = re.match(r"^([-*]|\d+\.)\s+(.*)$", stripped)
        if m:
            flush_para()
            p = doc.add_paragraph()
            set_para_format(p, align=WD_ALIGN_PARAGRAPH.JUSTIFY, first_line_indent=False,
                            line_spacing=18)
            p.paragraph_format.left_indent = Pt(24)
            bullet = m.group(1)
            prefix = "· " if bullet in ("-", "*") else bullet + " "
            set_run(p.add_run(prefix + m.group(2).strip()))
            i += 1
            continue

        para_buf.append(stripped)
        i += 1

    flush_para()
    if in_code and code_buf:
        add_code_block(doc, code_buf)


# ==================================================================
# 主流程
# ==================================================================
def merge_inputs(paths):
    """把各分章 Markdown 合并为一份全文（保留顺序，统一换行）。"""
    parts = []
    for path in paths:
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read()
        # 去掉写作过程的字数统计注释
        content = re.sub(r"<!--.*?-->", "", content, flags=re.S)
        parts.append(content.strip())
    return "\n\n".join(parts) + "\n"


def setup_styles(doc):
    style = doc.styles["Normal"]
    style.font.name = FONT_EN
    style.font.size = SIZE_BODY
    style.element.rPr.rFonts.set(qn("w:eastAsia"), FONT_SONG)
    section = doc.sections[0]
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin = Cm(3.0)
    section.right_margin = Cm(2.6)


def main():
    parser = argparse.ArgumentParser(description="论文 Markdown → Word（符合学校规范）")
    parser.add_argument("--input", nargs="*", help="输入的 Markdown 文件（按顺序）")
    parser.add_argument("--output", default=os.path.join(THESIS, "论文正文.docx"))
    parser.add_argument("--no-merge", action="store_true",
                        help="不合并，直接使用 docs/thesis/05_论文全文.md")
    args = parser.parse_args()

    if args.input:
        inputs = args.input
    elif args.no_merge:
        inputs = [os.path.join(THESIS, "05_论文全文.md")]
    else:
        inputs = sorted(glob.glob(os.path.join(THESIS, "0[2-4]_*.md")))

    missing = [p for p in inputs if not os.path.exists(p)]
    if missing:
        print("缺少输入文件：%s" % missing)
        return 2
    if not inputs:
        print("没有找到任何分章 Markdown，请先完成论文写作。")
        return 2

    full_text = merge_inputs(inputs)
    merged_path = os.path.join(THESIS, "05_论文全文.md")
    with open(merged_path, "w", encoding="utf-8") as fh:
        fh.write(full_text)
    print("合并稿：%s（%d 字）" % (merged_path, len(re.sub(r"\s", "", full_text))))

    doc = Document()
    setup_styles(doc)
    parse_markdown(doc, full_text)
    doc.save(args.output)
    print("已生成：%s" % args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
