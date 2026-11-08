# -*- coding: utf-8 -*-
"""补画 图1-1 研究技术路线图。

为什么需要这张图：论文第1章只有文字，没有说明"研究是怎么一步步做的"，
而这是本科论文里最常见的缺失图。该图把 需求分析 → 可行性 → 设计 → 实现 → 测试
五个阶段和"边做边验"的反馈回路画出来，与第3至5章的实际工作对应。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_figures as M

BLUE, BLUE_L, BLUE_D = M.BLUE, M.BLUE_L, M.BLUE_D
ORANGE, ORANGE_L = M.ORANGE, M.ORANGE_L
GREEN, GREEN_L = M.GREEN, M.GREEN_L
YELLOW, YELLOW_L = M.YELLOW, M.YELLOW_L
INK, SUB, LINE, WHITE = M.INK, M.SUB, M.LINE, M.WHITE
BROWN = (150, 78, 20)

PHASES = [
    ("需求分析",
     ["文献梳理：同类研究 31 篇，归纳现有产品在错题诊断、难度自适应、激励机制上的不足",
      "问卷调查：发放 150 份、有效 138 份，得到功能需求的三个层次"],
     BLUE_L, BLUE),
    ("可行性论证",
     ["技术可行性：技术栈均为成熟方案，无攻关难点",
      "操作可行性：学生只需点击，教师端按分类展示学情",
      "社会可行性：与科学素质纲要方向一致，内容与数据安全可控"],
     YELLOW_L, YELLOW),
    ("系统设计",
     ["总体架构：前后端分离的五层结构",
      "功能模块：六个基础模块 + 三项扩展功能",
      "数据库：概念模型与 11 张数据表"],
     GREEN_L, GREEN),
    ("系统实现",
     ["出题链路：调用约束 + 接收校验 + 题库补足，三层降级",
      "六个基础模块与基础课程题库、同伴对战、段位阶梯",
      "24 个学生端接口 + 14 个管理端接口"],
     ORANGE_L, ORANGE),
    ("测试验证",
     ["单元测试：题库规范、答案一致性、学段分级、段位边界",
      "集成测试：冒烟 49 条用例、真实浏览器端到端、界面审计",
      "共 17 项检查，全部通过"],
     (245, 240, 255), (150, 120, 200)),
]


def box(c, x, y, w, h, lines, fill, outline, lsize=13):
    """内容框：只列要点，阶段名由左侧标签框承担，避免重复。"""
    c.rect(x, y, x + w, y + h, fill=fill, outline=outline)
    n = len(lines)
    top = y + h / 2.0 - (n - 1) * 13
    for i, s in enumerate(lines):
        c.text(x + 24, top + i * 26, "· " + s, size=lsize, color=INK, anchor="lm")


def main():
    W = 1500
    LX, LW = 150, 170
    RX0, RW = 320, 1130
    ROW_H = 118
    GAP = 42
    y = 120

    rows = []
    for name, lines, fill, outline in PHASES:
        h = 34 + len(lines) * 24 + 14
        rows.append((y, h, name, lines, fill, outline))
        y += h + GAP

    H = y + 130
    c = M.Canvas(W, H)
    c.text_center(W / 2.0, 44, "研究技术路线", size=26, bold=True, color=BLUE_D)
    c.text_center(W / 2.0, 80, "需求分析 → 可行性论证 → 系统设计 → 系统实现 → 测试验证",
                  size=13, color=SUB)

    for y0, h, name, lines, fill, outline in rows:
        c.rect(LX, y0, RX0, y0 + h, fill=WHITE, outline=outline)
        c.text_center((LX + RX0) / 2.0, y0 + h / 2.0, name, size=16, bold=True, color=BLUE_D)
        box(c, RX0, y0, RW, h, lines, fill, outline)

    # 阶段之间的下行箭头
    for (y0, h, *_), (y1, _h, *_rest) in zip(rows, rows[1:]):
        c.arrow(W / 2.0 - 300, y0 + h, W / 2.0 - 300, y1, color=SUB, width=1.4)

    # 结论
    last_y, last_h = rows[-1][0], rows[-1][1]
    cy = last_y + last_h + 46
    c.arrow(W / 2.0 - 300, last_y + last_h, W / 2.0 - 300, cy - 4, color=SUB, width=1.4)
    c.rect(RX0, cy, RX0 + RW, cy + 66, fill=WHITE, outline=BLUE_D, width=1.6)
    c.text_center(RX0 + RW / 2.0, cy + 33,
                  "结论：学段适配落成参数、反馈落到具体、可用性由降级保证、边做边验可发现静默错误",
                  size=14, bold=True, color=BLUE_D)

    # 左侧“边做边验”的反馈回路
    fb_x = 104
    y_test = rows[4][0] + rows[4][1] / 2.0
    y_impl = rows[3][0] + rows[3][1] / 2.0
    c.line(LX, y_test, fb_x, y_test, color=ORANGE, width=1.6, dash=(6, 4))
    c.line(fb_x, y_test, fb_x, y_impl, color=ORANGE, width=1.6, dash=(6, 4))
    c.arrow(fb_x, y_impl, LX, y_impl, color=ORANGE, width=1.6)
    c.text_center(fb_x - 24, (y_test + y_impl) / 2.0 - 18, "发现", size=12, color=ORANGE)
    c.text_center(fb_x - 24, (y_test + y_impl) / 2.0 + 2, "问题", size=12, color=ORANGE)
    c.text_center(fb_x - 24, (y_test + y_impl) / 2.0 + 22, "回改", size=12, color=ORANGE)

    c.text_center(W / 2.0, H - 34,
                  "说明：左侧虚线为“边做边验”的反馈路径——测试中发现的问题回到实现与设计环节修正后复测。",
                  size=12, color=SUB)
    return c.save("图1-1_研究技术路线图")


if __name__ == "__main__":
    sys.exit(main())
