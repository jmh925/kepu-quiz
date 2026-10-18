# -*- coding: utf-8 -*-
"""校验问卷结果文档中的数据自洽性：人数 ÷ 样本量 是否等于所标比例。

为什么单独写这个：问卷文档里 30 多个百分比，任何一个和人数对不上，
答辩时被逐个核对就会露馅。人工核对容易漏，交给脚本。
"""
import io
import re
import sys
import zipfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

STANDALONE = r"C:\Users\dell\Desktop\靳慕淮毕设文件\问卷\问卷结果与分析.md"
THESIS = r"E:\dev\kepu-quiz\docs\thesis-draft\03_第3章.md"

fail = 0


def check_pairs(path, label, n_default=None):
    """扫描表格行，取「人数、比例」两列做核算。"""
    global fail
    text = io.open(path, encoding="utf-8").read()
    print("=== %s ===" % label)
    rows = 0
    bad = 0
    for line in text.split("\n"):
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        # 取最后两列里像「整数、xx.x%」的组合
        m_pct = re.search(r"(\d+(?:\.\d+)?)%", cells[-1])
        m_cnt = re.fullmatch(r"\d+", cells[-2]) if len(cells) >= 2 else None
        if not (m_pct and m_cnt):
            continue
        # 找样本量：表标题里的 n=xx
        rows += 1
    print("  表格中含比例的数值行：%d（下面按表逐张核对）" % rows)

    # 按表分块核对
    blocks = re.split(r"^表\s*\d+[^\n]*$", text, flags=re.M)
    headers = re.findall(r"^表\s*\d+[^\n]*$", text, re.M)
    for hdr, blk in zip(headers, blocks[1:]):
        m = re.search(r"n\s*=\s*(\d+)", hdr)
        n = int(m.group(1)) if m else n_default
        if not n:
            continue
        pairs = []
        for line in blk.split("\n"):
            if not line.strip().startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 2:
                continue
            pm = re.search(r"(\d+(?:\.\d+)?)%$", cells[-1])
            cm = re.fullmatch(r"\d+", cells[-2])
            if pm and cm:
                pairs.append((cells[0] + " / " + cells[-3] if len(cells) > 3 else cells[0],
                              int(cm.group(0)), float(pm.group(1))))
        if not pairs:
            continue
        total = 0
        for name, cnt, pct in pairs:
            calc = cnt * 100.0 / n
            total += cnt
            ok = abs(calc - pct) <= 0.06
            if not ok:
                bad += 1
                fail += 1
                print("  [FAIL] %s：%d/%d = %.2f%%，标注 %.1f%%"
                      % (name[:24], cnt, n, calc, pct))
        mark = "OK  " if not bad else "FAIL"
        print("  [%s] %-42s %d 项，样本 %d，人数合计 %d"
              % (mark, hdr[:40], len(pairs), n, total))
        bad = 0


def check_chapter3():
    global fail
    text = io.open(THESIS, encoding="utf-8").read()
    print("=== 论文第3章 表3-3（合计比例列）===")
    sec = text[text.find("表3-3"):text.find("从统计结果看")]
    bad = 0
    for line in sec.split("\n"):
        if not line.strip().startswith("|"):
            continue
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) != 4 or not c[1].isdigit():
            continue
        a, b = int(c[1]), int(c[2])
        pct = float(c[3].rstrip("%"))
        calc = (a + b) * 100.0 / 138
        if abs(calc - pct) > 0.06:
            bad += 1
            fail += 1
            print("  [FAIL] %s：(%d+%d)/138 = %.2f%%，标注 %.1f%%" % (c[0], a, b, calc, pct))
    print("  [%s] 表3-3 逐行核对完成" % ("OK  " if not bad else "FAIL"))

    print()
    print("=== 论文第3章 与独立文档的关键数字是否一致 ===")
    pairs = [("138", "有效问卷"), ("92", "家长"), ("46", "教师"),
             ("87.7", "学校课程"), ("69.6", "短视频"), ("21.0", "小程序"),
             ("69.1", "题目重复"), ("57.4", "无讲解"), ("44.2", "同伴对战"),
             ("94.9", "即时讲解"), ("18.8", "觉得没意思"), ("57.2", "题目+反馈合计")]
    solo = io.open(STANDALONE, encoding="utf-8").read()
    for val, desc in pairs:
        a = val in text
        b = val in solo
        ok = a and b
        if not ok:
            fail += 1
        print("  [%s] %-14s 论文:%s 独立文档:%s" % ("OK  " if ok else "FAIL", desc,
                                                 "有" if a else "无", "有" if b else "无"))
    print()
    print("=== 论文第3章 是否残留旧的错误数字 ===")
    for bad_s in ["共16题", "共6题", "19.1%", "58.3%"]:
        if bad_s in text:
            fail += 1
            print("  [FAIL] 仍存在「%s」" % bad_s)
        else:
            print("  [OK  ] 「%s」已清除" % bad_s)


def check_docx():
    global fail
    print()
    print("=== 生成的 Word 文件 ===")
    for path, expect in [(r"C:\Users\dell\Desktop\靳慕淮毕设文件\问卷\调查问卷.docx", "form"),
                         (r"C:\Users\dell\Desktop\靳慕淮毕设文件\问卷\问卷结果与分析.docx", "report")]:
        z = zipfile.ZipFile(path)
        xml = z.read("word/document.xml").decode("utf-8")
        text = re.sub(r"<[^>]+>", "", xml)
        ntab = len(re.findall(r"<w:tbl>", xml))
        nimg = len([n for n in z.namelist() if n.startswith("word/media/")])
        print("  %-22s 正文 %5d 字，表格 %2d 张，内嵌图 %d 张"
              % (path.split("\\")[-1], len(re.sub(r"\s", "", text)), ntab, nimg))
        if expect == "form":
            nq = len(re.findall(r"^\s*\d+[.．]", text, re.M))
            print("      题号数量（按行首数字统计）：%d" % nq)
            if "19" not in text:
                fail += 1
                print("      [FAIL] 未提到 19 题")
        else:
            if nimg != 4:
                fail += 1
                print("      [FAIL] 应内嵌 4 张图，实际 %d" % nimg)


def main():
    check_pairs(STANDALONE, "独立文档《问卷结果与分析》", n_default=138)
    print()
    check_chapter3()
    check_docx()
    print()
    print("=" * 50)
    print("未通过：%d 项" % fail)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
