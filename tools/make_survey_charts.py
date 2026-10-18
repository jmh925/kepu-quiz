# -*- coding: utf-8 -*-
"""生成问卷结果分析用的条形图。

四张图对应正文的四张统计表：
  图3-2 学生接触科普知识的途径       （表3-1，n=138，多选）
  图3-3 现有在线答题类应用的主要问题 （表3-2，n=68，多选）
  图3-4 各项功能的需求程度           （表3-3，n=138，五级量表合并「非常需要+比较需要」）
  图3-5 学生容易放弃练习的环节       （单选，n=138）

所有数值与 docs/thesis-draft/03_第3章.md 保持一致；改数字时两处要同时改。
产物：docs/figures/图3-*.png（同时由调用方复制到桌面「问卷」文件夹）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_figures as M

BLUE, ORANGE, GREEN = M.BLUE, M.ORANGE, M.GREEN
INK, SUB, LINE, WHITE = M.INK, M.SUB, M.LINE, M.WHITE
BLUE_D = M.BLUE_D

# ---------------------------------------------------------------- 数据
DATA_TRACK = [                      # 表3-1
    ("学校科学课等课程", 121, 87.7),
    ("短视频或科普视频", 96, 69.6),
    ("科普图书或杂志", 83, 60.1),
    ("科技馆、博物馆等场馆", 47, 34.1),
    ("科普类小程序或App", 29, 21.0),
]
DATA_PROBLEM = [                    # 表3-2
    ("题目重复，做几次就腻", 47, 69.1),
    ("答错只有对错，没有讲解", 39, 57.4),
    ("难度不适合孩子水平", 33, 48.5),
    ("没有错题复习功能", 31, 45.6),
    ("广告或付费内容过多", 28, 41.2),
    ("界面不适合孩子独立操作", 17, 25.0),
]
DATA_NEED = [                       # 表3-3
    ("答错后即时给出讲解", 131, 94.9),
    ("按学段分级出题", 129, 93.5),
    ("错题自动收录并可复习", 127, 92.0),
    ("查看孩子的薄弱知识点", 124, 89.9),
    ("单次练习时长可控", 118, 85.5),
    ("电脑与手机都能使用", 103, 74.6),
    ("段位、等级等长期目标", 86, 62.3),
    ("上传自己的讲义出题", 79, 57.2),
    ("同伴对战", 61, 44.2),
]
DATA_QUIT = [                       # 第（4）节「最容易放弃的环节」，单选 n=138
    ("题目太难或太简单", 45, 32.6),
    ("答错不知道错在哪", 34, 24.6),
    ("练习时间太长", 33, 23.9),
    ("觉得没意思、不想继续", 26, 18.8),
]


def barh(c, x0, y0, width, rows, color, max_val=100.0, row_h=44, bar_h=22,
         label_w=330, note=None):
    """横向条形图。左侧标签、中间条形、右侧百分比。"""
    base = y0
    for i, (name, cnt, pct) in enumerate(rows):
        y = base + i * row_h
        c.text(x0, y + bar_h / 2.0, name, size=14, color=INK, anchor="lm")
        bx = x0 + label_w
        bw = width - label_w - 110
        # 轨道
        c.rect(bx, y, bx + bw, y + bar_h, fill=(243, 246, 250), outline=LINE, width=1, radius=4)
        # 实值
        c.rect(bx, y, bx + bw * (pct / max_val), y + bar_h,
               fill=color, outline=color, radius=4)
        c.text(bx + bw + 12, y + bar_h / 2.0, "%.1f%%" % pct, size=14, bold=True,
               color=BLUE_D, anchor="lm")
        c.text(bx + bw * (pct / max_val) - 10, y + bar_h / 2.0, str(cnt), size=12,
               color=WHITE, anchor="rm")
    return base + len(rows) * row_h


def one(name, title, subtitle, rows, color, note):
    H = 190 + len(rows) * 44 + 70
    c = M.Canvas(1440, H)
    c.text(60, 46, title, size=24, bold=True, color=BLUE_D)
    c.text(60, 82, subtitle, size=13, color=SUB)
    barh(c, 60, 130, 1320, rows, color)
    c.text(60, H - 40, note, size=12, color=SUB)
    return c.save(name)


def main():
    one("图3-2_接触科普知识的途径",
        "学生接触科普知识的主要途径",
        "多选题，有效样本 138 份，各选项可同时选择",
        DATA_TRACK, BLUE,
        "数据来源：本次调查（n=138）")
    one("图3-3_现有应用的主要问题",
        "现有在线答题或学习类应用的主要问题",
        "多选题，仅使用过此类应用的 68 名填写者作答，最多选三项",
        DATA_PROBLEM, ORANGE,
        "数据来源：本次调查（n=68）")
    one("图3-4_各项功能的需求程度",
        "各项功能的需求程度",
        "五级量表中选「非常需要」与「比较需要」的人数合计，有效样本 138 份",
        DATA_NEED, GREEN,
        "数据来源：本次调查（n=138）")
    one("图3-5_学生容易放弃练习的环节",
        "家长与教师认为学生容易放弃练习的环节",
        "单选题，有效样本 138 份",
        DATA_QUIT, (150, 120, 200),
        "数据来源：本次调查（n=138）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
