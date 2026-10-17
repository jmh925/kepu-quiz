# -*- coding: utf-8 -*-
"""重绘论文插图的脚本（v2）。

重绘原因：v1 生成的图有四类问题——
1. 画布宽度算小，左右两侧的框被裁切（图4-1「去闯关」「运行看板」、图4-2「个人中心」）；
2. 连线用单点发散，多条线穿过其它框，或从框里穿出后落到空白处（图4-1、4-3、5-1）；
3. 菱形判断框没按文字长度撑开，文字压出边框（图5-1）；
4. 图内数据过时：写着「10 张表」（实为 11）、「6 大主题」（实为 9）、
   「2-gram 词频向量」（正文已改为关键词匹配），且漏画 pk_matches、admin_logs
   两张表，以及「网页版学生端」「pk / levels 两个模块」「同伴对战、成长阶梯两个用例」。

绘制约定：
- 先算布局再画，画布尺寸由内容推导，最外侧框离边缘至少 40 像素；
- 层级关系一律用「母线 + 支线」的正交折线，不用单点发散；
- 菱形按文字宽度撑开，必要时分两行；
- 每条连线都必须落到某个框的边上，不允许悬空；
- 两条不同颜色的通道用不同的横坐标，避免叠在一起看不清。

用法：python tools/make_figures_v2.py
产物：覆盖 docs/figures/ 下的 6 张图
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


def tw(c, s, size=15, bold=False):
    return c.d.textlength(s, font=M.font(size, bold)) / M.SCALE


def box(c, x, y, w, h, title, sub=None, fill=BLUE_L, outline=BLUE,
        tsize=15, ssize=12, tcolor=INK):
    c.rect(x, y, x + w, y + h, fill=fill, outline=outline)
    if sub:
        c.text_center(x + w / 2.0, y + h / 2.0 - 11, title, size=tsize, bold=True, color=tcolor)
        c.text_center(x + w / 2.0, y + h / 2.0 + 13, sub, size=ssize, color=SUB)
    else:
        c.text_center(x + w / 2.0, y + h / 2.0, title, size=tsize, bold=True, color=tcolor)


def lane_label(c, x, y, w, h, t1, t2=None, fill=BLUE_L, outline=BLUE, tcolor=BLUE_D):
    c.rect(x, y, x + w, y + h, fill=fill, outline=outline)
    if t2:
        c.text_center(x + w / 2.0, y + h / 2.0 - 12, t1, size=16, bold=True, color=tcolor)
        c.text_center(x + w / 2.0, y + h / 2.0 + 14, t2, size=12, color=SUB)
    else:
        c.text_center(x + w / 2.0, y + h / 2.0, t1, size=16, bold=True, color=tcolor)


def bracket_down(c, centers, y_bus, y_top, color=BLUE, label_x=None, label_y=None):
    """一排并列的框：画一条母线，再逐框下垂支线。"""
    c.line(centers[0], y_bus, centers[-1], y_bus, color=color, width=1.5)
    for x in centers:
        c.line(x, y_bus, x, y_top, color=color, width=1.5)
    if label_x is not None:
        c.line(label_x, label_y, label_x, y_bus, color=color, width=1.5)
        c.line(label_x, y_bus, centers[0] if label_x < centers[0] else centers[-1],
               y_bus, color=color, width=1.5)


def diamond(c, cx, cy, w, h, text, fill=YELLOW_L, outline=YELLOW, size=15):
    pts = [(cx, cy - h / 2.0), (cx + w / 2.0, cy), (cx, cy + h / 2.0), (cx - w / 2.0, cy)]
    c.d.polygon([(int(p[0] * M.SCALE), int(p[1] * M.SCALE)) for p in pts],
                fill=fill, outline=outline, width=max(1, int(1.6 * M.SCALE)))
    if tw(c, text, size) <= w * 0.62:
        c.text_center(cx, cy, text, size=size, bold=True, color=INK)
    else:
        half = (len(text) + 1) // 2
        c.text_center(cx, cy - 11, text[:half], size=size, bold=True, color=INK)
        c.text_center(cx, cy + 13, text[half:], size=size, bold=True, color=INK)


# ==================================================================
# 图 4-1 系统总体设计模块图
# ==================================================================
def figure_4_1():
    W, H = 1620, 600
    c = M.Canvas(W, H)
    c.text_center(W / 2.0, 44, "中小学生科普知识闯关系统", size=26, bold=True, color=BLUE_D)
    c.text_center(W / 2.0, 82, "系统总体设计模块", size=14, color=SUB)

    LX, LW = 40, 165
    ROW_H = 150
    y1 = 138
    lane_label(c, LX, y1, LW, ROW_H, "学生端", "小程序 / 网页版")
    w1, g1 = 152, 16
    xs1 = [228 + i * (w1 + g1) for i in range(6)]
    mods1 = [("去闯关", "选学段 · 主题"), ("答题闯关", "逐题作答"), ("复盘报告", "掌握度与建议"),
             ("错题本", "沉淀与重练"), ("知识库", "上传资料出题"), ("我的", "经验值与历史")]
    for x, (t, s) in zip(xs1, mods1):
        box(c, x, y1, w1, ROW_H, t, s)
    bracket_down(c, [x + w1 / 2.0 for x in xs1], y1 - 24, y1,
                 label_x=LX + LW / 2.0, label_y=y1)

    y2 = 334
    lane_label(c, LX, y2, LW, ROW_H, "管理端", "Web 后台", fill=ORANGE_L, outline=ORANGE,
               tcolor=BROWN)
    w2, g2 = 188, 20
    xs2 = [228 + i * (w2 + g2) for i in range(5)]
    mods2 = [("运行看板", "关键指标"), ("题库资源池", "增删改查"), ("用户管理", "查询与停用"),
             ("闯关记录", "来源与错题"), ("操作日志", "操作留痕")]
    for x, (t, s) in zip(xs2, mods2):
        box(c, x, y2, w2, ROW_H, t, s, fill=ORANGE_L, outline=ORANGE)
    bracket_down(c, [x + w2 / 2.0 for x in xs2], y2 - 24, y2,
                 label_x=LX + LW / 2.0, label_y=y2, color=ORANGE)

    px, pw = 1290, 290
    py = y1
    ph = (y2 + ROW_H) - y1
    c.rect(px, py, px + pw, py + ph, fill=(245, 249, 253), outline=LINE)
    c.text_center(px + pw / 2.0, py + 30, "公共服务层", size=17, bold=True, color=BLUE_D)
    c.text_center(px + pw / 2.0, py + 54, "学生端与管理端共用", size=12, color=SUB)
    caps = ["出题引擎（模型 / 题库降级）", "判题与经验值结算", "关键词检索增强",
            "内容安全过滤", "学段适配", "身份认证与鉴权"]
    for i, t in enumerate(caps):
        cy = py + 84 + i * 44
        c.rect(px + 18, cy, px + pw - 18, cy + 34, fill=WHITE, outline=LINE, radius=6)
        c.text_center(px + pw / 2.0, cy + 17, t, size=12, color=INK)

    c.arrow(xs1[-1] + w1, y1 + ROW_H / 2.0, px, y1 + ROW_H / 2.0, color=BLUE)
    c.arrow(xs2[-1] + w2, y2 + ROW_H / 2.0, px, y2 + ROW_H / 2.0, color=ORANGE)

    c.text_center(W / 2.0, 545,
                  "数据层：SQLite（11 张数据表）＋ 内置题库 JSON（225 道题 / 9 个主题）",
                  size=13, color=SUB)
    return c.save("图4-1_系统总体设计模块图")


# ==================================================================
# 图 4-2 系统功能结构图
# ==================================================================
def figure_4_2():
    W, H = 1620, 930
    c = M.Canvas(W, H)
    c.text_center(W / 2.0, 44, "科普知识闯关系统功能结构", size=26, bold=True, color=BLUE_D)

    box(c, W / 2.0 - 120, 86, 240, 58, "主菜单", fill=YELLOW_L, outline=YELLOW)
    c.line(W / 2.0, 144, W / 2.0, 178)
    box(c, W / 2.0 - 250, 178, 500, 58, "用户登录（注册登录 / 游客体验）")

    c.line(W / 2.0, 236, W / 2.0, 266)
    c.line(400, 266, 1220, 266)
    c.line(400, 266, 400, 300)
    c.line(1220, 266, 1220, 300)

    box(c, 280, 300, 240, 58, "学生角色", fill=BLUE_L, outline=BLUE, tcolor=BLUE_D)
    s_mods = [("闯关出题", "主题 + 学段"), ("答题闯关", "单选与即时讲解"), ("复盘报告", "掌握度与建议"),
              ("错题本", "沉淀与重练"), ("知识库", "上传与检索出题"), ("个人中心", "经验值与历史")]
    sw, sg, sx0 = 205, 26, 40
    sy1, sy2 = 400, 540
    for i, (t, s) in enumerate(s_mods):
        col, row = i % 3, i // 3
        box(c, sx0 + col * (sw + sg), sy1 if row == 0 else sy2, sw, 94, t, s)
    bracket_down(c, [sx0 + col * (sw + sg) + sw / 2.0 for col in range(3)], 372, sy1)
    for col in range(3):
        x = sx0 + col * (sw + sg) + sw / 2.0
        c.line(x, sy1 + 94, x, sy2, color=BLUE)
    c.line(400, 358, 400, 372, color=BLUE)

    box(c, 1100, 300, 240, 58, "管理角色", fill=ORANGE_L, outline=ORANGE, tcolor=BROWN)
    a_mods = [("运行看板", "关键指标"), ("题库资源池", "增删改查"), ("用户管理", "查询与停用"),
              ("闯关记录", "来源与错题"), ("操作日志", "操作留痕")]
    aw, ag, ax0 = 205, 26, 860
    for i, (t, s) in enumerate(a_mods):
        col, row = i % 3, i // 3
        box(c, ax0 + col * (aw + ag), sy1 if row == 0 else sy2, aw, 94, t, s,
            fill=ORANGE_L, outline=ORANGE)
    bracket_down(c, [ax0 + col * (aw + ag) + aw / 2.0 for col in range(3)], 372, sy1, color=ORANGE)
    for col in range(2):
        x = ax0 + col * (aw + ag) + aw / 2.0
        c.line(x, sy1 + 94, x, sy2, color=ORANGE)
    c.line(1220, 358, 1220, 372, color=ORANGE)

    c.rect(40, 700, 1580, 860, fill=(245, 249, 253), outline=LINE)
    c.text_center(810, 736, "支撑能力（贯穿各功能模块）", size=16, bold=True, color=BLUE_D)
    sup = ["内容安全过滤", "学段适配（三档）", "题库降级", "关键词检索增强", "经验值激励", "操作审计"]
    uw, ug = 232, 20
    ux0 = (1620 - (6 * uw + 5 * ug)) / 2.0
    for i, t in enumerate(sup):
        x = ux0 + i * (uw + ug)
        c.rect(x, 776, x + uw, 822, fill=WHITE, outline=BLUE, radius=6)
        c.text_center(x + uw / 2.0, 799, t, size=13, color=INK)
    return c.save("图4-2_系统功能结构图")


# ==================================================================
# 图 4-3 系统总体架构图
# ==================================================================
def figure_4_3():
    W, H = 1620, 1090
    c = M.Canvas(W, H)
    c.text_center(W / 2.0, 44, "系统总体架构（四层）", size=26, bold=True, color=BLUE_D)

    LX, LW, RX = 40, 170, 1480
    layers = [
        (110, 150, "表现层", BLUE_L, BLUE, [
            ["微信小程序（WXML / WXSS / JS）", "网页版学生端（原生 HTML / CSS / JS）",
             "管理端（原生 HTML / CSS / JS）"]]),
        (290, 110, "接入层", YELLOW_L, YELLOW, [
            ["HTTP / RESTful · 统一前缀 /api/v1",
             "统一响应 {code, message, data} · 学生令牌与管理令牌分离"]]),
        (430, 230, "应用服务层", GREEN_L, GREEN, [
            ["routers 路由层", "services 业务服务层", "llm 模型调用与降级"],
            ["question_bank 题库", "grades 学段适配", "safety 内容安全"],
            ["wrongbook 错题本", "pk 同伴对战", "levels 段位阶梯", "admin / admin_db 管理端"]]),
        (690, 150, "数据层", (247, 243, 255), (150, 120, 200), [
            ["SQLite（11 张数据表）", "内置题库 JSON（225 题 / 9 主题）",
             "知识库分块与题目资源池"]]),
    ]
    sp = 1480
    for y, h, name, fill, outline, rows in layers:
        c.rect(LX, y, sp, y + h, fill=fill, outline=outline)
        c.rect(LX, y, LX + LW, y + h, fill=WHITE, outline=outline)
        c.text_center(LX + LW / 2.0, y + h / 2.0, name, size=17, bold=True, color=BLUE_D)
        for ri, row in enumerate(rows):
            # 每行按自己的列数分宽度，避免行与行之间左右不齐
            n_row = len(row)
            cw = (sp - (LX + LW) - 48 - (n_row - 1) * 16) / float(n_row)
            ry = y + 26 + ri * 46
            for ci, t in enumerate(row):
                cx = LX + LW + 24 + ci * (cw + 16)
                c.rect(cx, ry, cx + cw, ry + 34, fill=WHITE, outline=outline, radius=6)
                c.text_center(cx + cw / 2.0, ry + 17, t, size=12, color=INK)

    for (y1, h1, *_), (y2, *_) in zip(layers, layers[1:]):
        c.arrow(810, y1 + h1, 810, y2, color=SUB, width=1.3)

    dy = 920
    c.rect(LX, dy, 1580, dy + 80, fill=ORANGE_L, outline=ORANGE)
    c.text_center(810, dy + 28,
                  "外部依赖：DeepSeek 大模型接口（兼容 OpenAI 规范 /chat/completions）",
                  size=14, bold=True, color=BROWN)
    c.text_center(810, dy + 56,
                  "未配置密钥或调用失败时自动降级到内置题库与规则模板，系统仍可完整运行",
                  size=12, color=SUB)
    spine = 1512
    c.line(RX, 545, spine, 545, color=ORANGE, width=1.4)
    c.arrow(spine, 545, spine, dy, color=ORANGE, width=1.4)
    return c.save("图4-3_系统总体架构图")


# ==================================================================
# 图 4-4 数据库 E-R 图（11 张表）
# ==================================================================
def figure_4_4():
    W, H = 1500, 1060
    c = M.Canvas(W, H)
    c.text_center(W / 2.0, 44, "数据库 E-R 图（11 张数据表）", size=25, bold=True, color=BLUE_D)
    c.text_center(W / 2.0, 78, "矩形为实体，连线标注联系类型（1:n 一对多，1:1 一对一）",
                  size=13, color=SUB)

    bh = 160

    def entity(x, y, w, name, fields, fill=BLUE_L, outline=BLUE):
        c.rect(x, y, x + w, y + bh, fill=fill, outline=outline)
        c.line(x, y + 34, x + w, y + 34, color=outline, width=1.2)
        c.text_center(x + w / 2.0, y + 17, name, size=14, bold=True, color=BLUE_D)
        for i, f in enumerate(fields):
            c.text(x + 12, y + 44 + i * 17, f, size=11, color=INK)

    ux, uy, uw = 40, 190, 250
    entity(ux, uy, uw, "users（用户）",
           ["id 主键", "username 登录名", "password_hash / salt", "total_xp 经验值",
            "grade 学段", "status 账号状态"])

    mx, mw = 400, 270
    mids = [
        (140, "quiz_sessions（闯关会话）",
         ["id 主键", "quiz_id 唯一", "user_id 外键", "grade / source", "questions_json"]),
        (320, "wrong_questions（错题本）",
         ["id 主键", "user_id 外键", "stem 题干", "correct_answer", "wrong_count 错次"]),
        (500, "knowledge_docs（知识库文档）",
         ["id 主键", "doc_id 唯一", "user_id 外键", "filename / file_type", "status 状态"]),
        (680, "pk_matches（同伴对战）",
         ["id 主键", "user_id 外键", "paper_key 试卷标识",
          "my_correct / opponent_correct", "result 结果"]),
    ]
    for y, name, fields in mids:
        entity(mx, y, mw, name, fields)

    rx, rw = 790, 290
    rights = [
        (140, "answer_records（答题记录）",
         ["id 主键", "quiz_id 外键", "correct_count / accuracy", "duration_ms 用时"]),
        (320, "reports（复盘报告）", ["id 主键", "quiz_id 唯一", "report_json 报告内容"]),
        (500, "knowledge_chunks（资料片段）",
         ["id 主键", "doc_id 外键", "chunk_index 序号", "content 片段内容"]),
    ]
    for y, name, fields in rights:
        entity(rx, y, rw, name, fields)

    ax, aw = 1140, 300
    entity(ax, 140, aw, "admins（管理员）",
           ["id 主键", "username 唯一", "password_hash / salt", "role 角色"],
           fill=ORANGE_L, outline=ORANGE)
    entity(ax, 320, aw, "admin_logs（操作日志）",
           ["id 主键", "username 操作人", "action 操作类型", "detail 操作详情"],
           fill=ORANGE_L, outline=ORANGE)
    entity(ax, 500, aw, "question_pool（题目资源池）",
           ["id 主键", "theme / grade", "answer 答案下标", "difficulty / enabled"],
           fill=ORANGE_L, outline=ORANGE)

    spine = 340
    uy_mid = uy + bh / 2.0
    y_first = mids[0][0] + bh / 2.0
    y_last = mids[3][0] + bh / 2.0
    c.line(ux + uw, uy_mid, spine, uy_mid, color=BLUE, width=1.4)
    c.line(spine, y_first, spine, y_last, color=BLUE, width=1.4)
    for y, _n, _f in mids:
        yy = y + bh / 2.0
        c.line(spine, yy, mx, yy, color=BLUE, width=1.4)
        c.text_center((spine + mx) / 2.0, yy - 11, "1:n", size=11, color=BLUE_D)

    c.line(mx + mw, mids[0][0] + bh / 2.0, rx, rights[0][0] + bh / 2.0, color=BLUE, width=1.4)
    c.text_center((mx + mw + rx) / 2.0, rights[0][0] + bh / 2.0 - 11, "1:1",
                  size=11, color=BLUE_D)

    gx = 760
    y_src = mids[0][0] + bh / 2.0 + 24
    y_dst = rights[1][0] + bh / 2.0
    c.line(mx + mw, y_src, gx, y_src, color=BLUE, width=1.4)
    c.line(gx, y_src, gx, y_dst, color=BLUE, width=1.4)
    c.line(gx, y_dst, rx, y_dst, color=BLUE, width=1.4)
    c.text_center(gx - 32, y_dst - 11, "1:1", size=11, color=BLUE_D)

    c.line(mx + mw, mids[2][0] + bh / 2.0, rx, rights[2][0] + bh / 2.0, color=BLUE, width=1.4)
    c.text_center((mx + mw + rx) / 2.0, rights[2][0] + bh / 2.0 - 11, "1:n",
                  size=11, color=BLUE_D)

    c.line(ax + aw / 2.0, 140 + bh, ax + aw / 2.0, 320, color=ORANGE, width=1.4)
    c.text_center(ax + aw / 2.0 + 30, 302, "1:n", size=11, color=BROWN)

    c.text_center(ax + aw / 2.0, 700, "题目资源池由管理端维护，独立于用户数据",
                  size=12, color=SUB)

    c.text_center(W / 2.0, 906,
                  "说明：quiz_sessions、wrong_questions、knowledge_docs、pk_matches 的 user_id 均指向 users；",
                  size=12, color=SUB)
    c.text_center(W / 2.0, 932,
                  "answer_records 与 reports 的 quiz_id 指向 quiz_sessions，knowledge_chunks 的 doc_id 指向 knowledge_docs。",
                  size=12, color=SUB)
    c.text_center(W / 2.0, 958,
                  "pk_matches 以 paper_key 标识同一份试卷，仅在试卷一致时才比较双方得分。",
                  size=12, color=SUB)
    return c.save("图4-4_数据库E-R图")


# ==================================================================
# 图 3-1 系统用例图
# ==================================================================
def figure_3_1():
    W, H = 1500, 1210
    c = M.Canvas(W, H)
    c.text_center(W / 2.0, 44, "系统用例图", size=26, bold=True, color=BLUE_D)

    s_uc = ["注册登录 / 游客模式", "按主题出题（可基于资料）", "答题闯关与即时讲解",
            "查看复盘报告", "错题本与只练错题", "知识库资料上传与管理",
            "查看个人中心与经验值", "同伴对战", "成长阶梯与段位"]
    a_uc = ["管理端登录与鉴权", "查看运行看板与趋势", "题库资源池增删改查",
            "用户查询与停用", "查看闯关记录与操作日志"]

    bw, bh, bgap = 560, 86, 18
    bx = 320
    ys = [110 + i * (bh + bgap) for i in range(len(s_uc))]
    for y, t in zip(ys, s_uc):
        c.rect(bx, y, bx + bw, y + bh, fill=BLUE_L, outline=BLUE, radius=43)
        c.text_center(bx + bw / 2.0, y + bh / 2.0, t, size=15, color=INK)

    busx = 268
    c.line(busx, ys[0] + bh / 2.0, busx, ys[-1] + bh / 2.0, color=BLUE, width=1.4)
    for y in ys:
        c.line(busx, y + bh / 2.0, bx, y + bh / 2.0, color=BLUE, width=1.4)

    actor_y = 660
    c.line(150, actor_y, busx, actor_y, color=BLUE, width=1.5)
    c.d.ellipse([int(112 * M.SCALE), int((actor_y - 44) * M.SCALE),
                 int(148 * M.SCALE), int((actor_y - 8) * M.SCALE)],
                outline=BLUE, width=max(1, int(2 * M.SCALE)))
    c.line(130, actor_y - 8, 130, actor_y + 22, color=BLUE, width=2)
    c.line(112, actor_y, 148, actor_y, color=BLUE, width=2)
    c.line(130, actor_y + 22, 116, actor_y + 48, color=BLUE, width=2)
    c.line(130, actor_y + 22, 144, actor_y + 48, color=BLUE, width=2)
    c.text_center(130, actor_y + 66, "学生", size=15, bold=True, color=BLUE_D)

    abw, abh, abgap = 430, 86, 22
    abx = 980
    ays = [200 + i * (abh + abgap) for i in range(len(a_uc))]
    for y, t in zip(ays, a_uc):
        c.rect(abx, y, abx + abw, y + abh, fill=ORANGE_L, outline=ORANGE, radius=43)
        c.text_center(abx + abw / 2.0, y + abh / 2.0, t, size=14, color=INK)
    abusx = 1450
    c.line(abusx, ays[0] + abh / 2.0, abusx, ays[-1] + abh / 2.0, color=ORANGE, width=1.4)
    for y in ays:
        c.line(abx + abw, y + abh / 2.0, abusx, y + abh / 2.0, color=ORANGE, width=1.4)

    acy = 300
    c.line(abusx, acy, 1470, acy, color=ORANGE, width=1.5)
    c.d.ellipse([int(1452 * M.SCALE), int((acy - 36) * M.SCALE),
                 int(1488 * M.SCALE), int(acy * M.SCALE)],
                outline=ORANGE, width=max(1, int(2 * M.SCALE)))
    c.line(1470, acy, 1470, acy + 30, color=ORANGE, width=2)
    c.line(1452, acy + 8, 1488, acy + 8, color=ORANGE, width=2)
    c.line(1470, acy + 30, 1456, acy + 56, color=ORANGE, width=2)
    c.line(1470, acy + 30, 1484, acy + 56, color=ORANGE, width=2)
    c.text_center(1470, acy + 74, "管理员", size=15, bold=True, color=BROWN)

    c.rect(bx, 1060, bx + bw, 1140, fill=YELLOW_L, outline=YELLOW)
    c.text_center(bx + bw / 2.0, 1086, "支撑能力：内容安全过滤、学段分级适配",
                  size=15, bold=True, color=(120, 90, 0))
    c.text_center(bx + bw / 2.0, 1112, "贯穿「按主题出题」「答题闯关」「查看复盘报告」三类用例",
                  size=12, color=SUB)

    c.text_center(W / 2.0, 1180,
                  "说明：左侧为学生在小程序端与网页端可用的用例，右侧为管理员在管理端可用的用例。",
                  size=12, color=SUB)
    return c.save("图3-1_系统用例图")


# ==================================================================
# 图 5-1 出题处理流程图
# ==================================================================
def figure_5_1():
    W, H = 1300, 1570
    c = M.Canvas(W, H)
    c.text_center(W / 2.0, 44, "出题处理流程", size=26, bold=True, color=BLUE_D)

    CX, BW = 380, 560
    RH = 760          # 降级通道横坐标
    BH = 92

    y1 = 100
    box(c, CX - BW / 2.0, y1, BW, BH, "用户输入学习主题", "可选：携带知识库资料", fill=BLUE_L)
    y2 = 232
    box(c, CX - BW / 2.0, y2, BW, BH, "内容安全与长度校验",
        "命中敏感词或超长则直接返回提示", fill=ORANGE_L, outline=ORANGE)

    c.arrow(CX, y1 + BH, CX, y2, color=BLUE)
    c.arrow(CX + BW / 2.0, y2 + BH / 2.0, 720, y2 + BH / 2.0, color=ORANGE)
    box(c, 720, y2 + 6, 300, 80, "返回错误提示", "本次不出题", fill=ORANGE_L, outline=ORANGE, tsize=14)

    d1y = 420
    c.arrow(CX, y2 + BH, CX, d1y - 55, color=BLUE)
    diamond(c, CX, d1y, 330, 110, "是否携带资料？")

    c.arrow(CX + 165, d1y, 720, d1y, color=GREEN)
    c.text_center(CX + 215, d1y - 15, "是", size=13, bold=True, color=GREEN)
    box(c, 720, d1y - 52, 440, 104, "关键词检索",
        "分词 + 词频加权，取前若干片段注入提示词",
        fill=GREEN_L, outline=GREEN, tsize=14, ssize=12)

    y3 = 540
    c.arrow(CX, d1y + 55, CX, y3, color=BLUE)
    c.text_center(CX + 28, d1y + 80, "否", size=13, bold=True, color=BLUE_D)
    box(c, CX - BW / 2.0, y3, BW, BH, "按学段组装提示词",
        "题量 / 题干长度 / 选项长度 / 安全约束", fill=BLUE_L)
    c.line(720, d1y + 52, 690, d1y + 52, color=GREEN)
    c.line(690, d1y + 52, 690, y3 + 46, color=GREEN)
    c.arrow(690, y3 + 46, CX + BW / 2.0, y3 + 46, color=GREEN)

    d2y = 720
    c.arrow(CX, y3 + BH, CX, d2y - 55, color=BLUE)
    diamond(c, CX, d2y, 350, 110, "是否配置模型密钥？")

    y4 = 830
    c.arrow(CX, d2y + 55, CX, y4, color=BLUE)
    c.text_center(CX + 28, d2y + 80, "是", size=13, bold=True, color=BLUE_D)
    box(c, CX - BW / 2.0, y4, BW, BH, "调用大语言模型生成题目",
        "JSON 结构约束 + 字段取值约束", fill=BLUE_L)

    y5 = 972
    c.arrow(CX, y4 + BH, CX, y5, color=BLUE)
    box(c, CX - BW / 2.0, y5, BW, BH, "提取 JSON 并逐题校验",
        "内容安全 + 题干长度 + 选项与下标合法性", fill=ORANGE_L, outline=ORANGE)

    d3y = 1142
    c.arrow(CX, y5 + BH, CX, d3y - 55, color=BLUE)
    diamond(c, CX, d3y, 350, 110, "题目数量是否达标？")

    y6 = 1250
    box(c, 720, y6, 440, BH, "用内置题库补齐题量",
        "按学段与主题抽取，排除已出现的题干", fill=GREEN_L, outline=GREEN)

    y7 = 1400
    box(c, CX - BW / 2.0, y7, BW, 80, "返回可作答题目列表",
        "附题量、学段与来源标识（模型 / 题库）", fill=YELLOW_L, outline=YELLOW)

    # 达标：直接向下到「返回」
    c.arrow(CX, d3y + 55, CX, y7, color=BLUE)
    c.text_center(CX + 28, d3y + 80, "是", size=13, bold=True, color=BLUE_D)

    # 不达标：向右进「补齐题量」
    c.arrow(CX + 175, d3y, 720, d3y, color=GREEN)
    c.text_center(CX + 225, d3y - 15, "否", size=13, bold=True, color=GREEN)
    c.line(720, d3y, 700, d3y, color=GREEN)
    c.line(700, d3y, 700, y6 + BH / 2.0, color=GREEN)
    c.arrow(700, y6 + BH / 2.0, 720, y6 + BH / 2.0, color=GREEN)

    # 降级通道：未配置密钥 / 调用失败 → 补齐题量
    c.line(CX + 175, d2y, RH, d2y, color=ORANGE, width=1.4)
    c.text_center(CX + 225, d2y - 15, "否", size=13, bold=True, color=ORANGE)
    c.line(CX + BW / 2.0, y4 + BH / 2.0, RH, y4 + BH / 2.0, color=ORANGE, width=1.4)
    c.text_center(CX + BW / 2.0 + 52, y4 + BH / 2.0 - 15, "调用失败", size=12, color=ORANGE)
    c.line(RH, d2y, RH, y6 + 18, color=ORANGE, width=1.4)
    c.line(RH, y6 + 18, 1160, y6 + 18, color=ORANGE, width=1.4)
    c.arrow(1160, y6 + 18, 1160, y6, color=ORANGE, width=1.4)

    # 补齐后回到「返回」
    c.line(940, y6 + BH, 940, y7 + 40, color=GREEN, width=1.4)
    c.arrow(940, y7 + 40, CX + BW / 2.0, y7 + 40, color=GREEN)

    c.text_center(W / 2.0, 1500,
                  "说明：橙色为异常与降级路径，绿色为知识库检索与题库补齐路径；三类降级最终都回到内置题库，",
                  size=12, color=SUB)
    c.text_center(W / 2.0, 1528,
                  "因此未配置密钥或调用失败时系统仍能正常出题。", size=12, color=SUB)
    return c.save("图5-1_AI出题处理流程图")


def main():
    figure_4_1()
    figure_4_2()
    figure_4_3()
    figure_4_4()
    figure_3_1()
    figure_5_1()
    return 0


if __name__ == "__main__":
    sys.exit(main())
