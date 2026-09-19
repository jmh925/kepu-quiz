# -*- coding: utf-8 -*-
"""用代码生成论文插图（零外部素材，全部为矢量式绘制的 PNG）。

为什么用脚本画图：论文插图若由第三方工具生成，后期改一处文字就要重画；
用脚本生成后，修改内容只需重跑一条命令，且图形风格统一（同字号、同配色、同线宽）。

用法（在仓库根目录）：
    python tools/make_figures.py

产物：docs/figures/*.png 与同名 *.svg（SVG 便于插入 Word 后仍可缩放）
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

# ---------------- 输出目录 ----------------
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "docs", "figures")
os.makedirs(OUT, exist_ok=True)

SCALE = 2                      # 2 倍超采样，插入 Word 后更清晰

# ---------------- 配色（与小程序视觉规范一致的浅色系） ----------------
INK = (31, 42, 55)
SUB = (107, 122, 141)
BLUE = (43, 124, 211)
BLUE_L = (232, 241, 251)
BLUE_D = (24, 78, 140)
ORANGE = (232, 131, 58)
ORANGE_L = (253, 241, 231)
GREEN = (46, 158, 107)
GREEN_L = (234, 247, 240)
YELLOW = (255, 202, 40)
YELLOW_L = (255, 249, 226)
LINE = (196, 209, 223)
WHITE = (255, 255, 255)

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
]


def font(size, bold=False):
    """按需加载中文字体；找不到时退回默认字体（保证脚本不会因缺字体崩溃）。"""
    path = FONT_CANDIDATES[1 if bold else 0]
    if not os.path.exists(path):
        path = next((p for p in FONT_CANDIDATES if os.path.exists(p)), None)
    if not path:
        return ImageFont.load_default()
    return ImageFont.truetype(path, size * SCALE)


class Canvas(object):
    """极简绘图封装：坐标一律按 1 倍逻辑像素传入，内部自动放大 SCALE 倍。"""

    def __init__(self, width, height, bg=WHITE):
        self.w, self.h = width, height
        self.img = Image.new("RGB", (width * SCALE, height * SCALE), bg)
        self.d = ImageDraw.Draw(self.img)

    def _s(self, box):
        return [int(v * SCALE) for v in box]

    def text(self, x, y, s, size=14, color=INK, bold=False, anchor="lt"):
        self.d.text((int(x * SCALE), int(y * SCALE)), s, font=font(size, bold),
                    fill=color, anchor=anchor)

    def text_center(self, cx, cy, s, size=14, color=INK, bold=False):
        self.d.text((int(cx * SCALE), int(cy * SCALE)), s, font=font(size, bold),
                    fill=color, anchor="mm")

    def wrap_center(self, cx, cy, lines, size=13, color=INK, gap=None, bold=False):
        """多行文本垂直居中绘制。"""
        gap = gap or (size + 6)
        total = gap * (len(lines) - 1)
        top = cy - total / 2.0
        for i, line in enumerate(lines):
            self.text_center(cx, top + i * gap, line, size=size, color=color, bold=bold)

    def rect(self, x0, y0, x1, y1, fill=None, outline=LINE, width=1.4, radius=8):
        self.d.rounded_rectangle(self._s([x0, y0, x1, y1]), radius=radius * SCALE,
                                 fill=fill, outline=outline, width=max(1, int(width * SCALE)))

    def line(self, x0, y0, x1, y1, color=LINE, width=1.4, dash=None):
        if dash:
            self._dashed_line(x0, y0, x1, y1, color, width, dash)
            return
        self.d.line(self._s([x0, y0, x1, y1]), fill=color, width=max(1, int(width * SCALE)))

    def _dashed_line(self, x0, y0, x1, y1, color, width, dash):
        import math
        total = math.hypot(x1 - x0, y1 - y0)
        if total == 0:
            return
        ux, uy = (x1 - x0) / total, (y1 - y0) / total
        pos = 0.0
        on_len, off_len = dash
        while pos < total:
            end = min(pos + on_len, total)
            self.line(x0 + ux * pos, y0 + uy * pos, x0 + ux * end, y0 + uy * end,
                      color=color, width=width)
            pos = end + off_len

    def arrow(self, x0, y0, x1, y1, color=BLUE, width=1.4, head=7, dash=None):
        self.line(x0, y0, x1, y1, color=color, width=width, dash=dash)
        import math
        ang = math.atan2(y1 - y0, x1 - x0)
        for sign in (1, -1):
            a = ang + sign * math.radians(152)
            self.line(x1, y1, x1 + math.cos(a) * head, y1 + math.sin(a) * head,
                      color=color, width=width)

    def elbow(self, x0, y0, x1, y1, color=LINE, width=1.4):
        """先竖后横的折线。"""
        self.line(x0, y0, x0, y1, color=color, width=width)
        self.line(x0, y1, x1, y1, color=color, width=width)

    def save(self, name):
        path = os.path.join(OUT, name + ".png")
        self.img.save(path, "PNG")
        print("生成 %s  (%dx%d)" % (path, self.img.width, self.img.height))
        return path


# ==================================================================
# 图 4-1 系统总体设计模块图
# ==================================================================
def figure_4_1():
    c = Canvas(880, 520)
    c.text_center(440, 30, "中小学生科普知识闯关小程序", size=20, bold=True, color=BLUE_D)
    c.text_center(440, 56, "系统总体设计模块", size=13, color=SUB)

    # 两大角色
    c.rect(60, 96, 400, 138, fill=BLUE_L, outline=BLUE, radius=10)
    c.text_center(230, 117, "学生端（微信小程序）", size=15, bold=True, color=BLUE_D)
    c.rect(480, 96, 820, 138, fill=ORANGE_L, outline=ORANGE, radius=10)
    c.text_center(650, 117, "管理端（Web 后台）", size=15, bold=True, color=(168, 90, 28))

    # 连线
    c.line(230, 138, 230, 178, color=BLUE)
    c.line(650, 138, 650, 178, color=ORANGE)

    student = [("去闯关", "选学段 / 输主题"), ("答题闯关", "逐题作答与讲解"),
               ("复盘报告", "掌握度与建议"), ("错题本", "错题重练"),
               ("知识库", "上传资料出题"), ("我的", "经验值与历史")]
    admin = [("运行看板", "用户 / 闯关 / 错题"), ("题库资源池", "增删改查"),
             ("用户管理", "启用 / 停用"), ("闯关记录", "来源与错题"),
             ("操作日志", "操作留痕"), ("接口文档", "OpenAPI")]
    colors = [BLUE_L, GREEN_L, YELLOW_L, ORANGE_L, BLUE_L, GREEN_L]
    outlines = [BLUE, GREEN, (214, 168, 20), ORANGE, BLUE, GREEN]
    xs = [30, 176, 322, 468, 614, 760]
    for i, ((title, desc), fill, outline) in enumerate(zip(student, colors, outlines)):
        x = xs[i]
        c.rect(x - 68, 190, x + 68, 262, fill=fill, outline=outline, radius=8)
        c.text_center(x, 214, title, size=14, bold=True)
        c.text_center(x, 238, desc, size=11, color=SUB)
        c.line(x, 178, x, 190, color=BLUE)
        c.line(x, 262, x, 288, color=outline)
    xa = [30, 176, 322, 468, 614, 760]
    for i, ((title, desc), fill, outline) in enumerate(zip(admin, colors, outlines)):
        x = xa[i]
        c.rect(x - 68, 300, x + 68, 372, fill=WHITE, outline=outline, radius=8)
        c.text_center(x, 324, title, size=14, bold=True)
        c.text_center(x, 348, desc, size=11, color=SUB)
        c.line(x, 288, x, 300, color=ORANGE if i >= 0 else LINE)
        c.line(x, 372, x, 398, color=outline)

    # 公共服务层
    c.rect(30, 400, 830, 470, fill=BLUE_L, outline=BLUE, radius=10)
    c.text_center(430, 420, "公共服务层（学生端与管理端共用）", size=14, bold=True, color=BLUE_D)
    services = ["出题引擎（DeepSeek / 题库降级）", "判题与经验值结算", "检索增强（2-gram 词频向量）",
                "内容安全过滤", "学段适配", "JWT 鉴权"]
    for i, s in enumerate(services):
        c.text_center(112 + i * 141, 448, s, size=10.5, color=(40, 60, 84))
    c.text_center(430, 498, "数据层：SQLite（10 张表，连接复用 + 线程锁，可平滑迁移 MySQL）",
                  size=11.5, color=SUB)
    return c.save("图4-1_系统总体设计模块图")


# ==================================================================
# 图 4-2 系统功能结构图
# ==================================================================
def figure_4_2():
    c = Canvas(880, 500)
    c.text_center(440, 26, "科普知识闯关小程序", size=19, bold=True, color=BLUE_D)

    # 主菜单层
    c.rect(340, 56, 540, 92, fill=YELLOW_L, outline=(214, 168, 20), radius=8)
    c.text_center(440, 74, "主菜单", size=15, bold=True)

    c.line(440, 92, 440, 116, color=(214, 168, 20))
    c.line(120, 116, 760, 116, color=(214, 168, 20))

    # 用户登录层
    c.rect(330, 132, 550, 168, fill=BLUE_L, outline=BLUE, radius=8)
    c.text_center(440, 150, "用户登录（可选登录 / 游客模式）", size=14, bold=True, color=BLUE_D)
    c.line(440, 116, 440, 132, color=(214, 168, 20))

    # 角色层
    roles = [("学生角色", 110, 300, BLUE, BLUE_L), ("管理角色", 580, 770, ORANGE, ORANGE_L)]
    c.line(440, 168, 440, 196, color=BLUE)
    c.line(205, 196, 675, 196, color=BLUE)
    for title, x0, x1, outline, fill in roles:
        cx = (x0 + x1) / 2
        c.line(cx, 196, cx, 210, color=outline)
        c.rect(x0, 210, x1, 248, fill=fill, outline=outline, radius=8)
        c.text_center(cx, 229, title, size=15, bold=True,
                      color=BLUE_D if outline == BLUE else (168, 90, 28))

    # 学生功能
    s_funcs = [("闯关出题", "主题 + 学段"), ("答题闯关", "单选与即时讲解"),
               ("复盘报告", "掌握度与建议"), ("错题本", "沉淀与重练"),
               ("知识库", "上传与检索出题"), ("个人中心", "经验值与历史")]
    for i, (name, desc) in enumerate(s_funcs):
        x = 44 + i * 90
        c.line(x + 45, 248, x + 45, 268, color=BLUE)
        c.rect(x, 268, x + 90, 330, fill=WHITE, outline=BLUE, radius=7)
        c.text_center(x + 45, 288, name, size=12.5, bold=True)
        c.text_center(x + 45, 310, desc, size=10, color=SUB)

    a_funcs = [("运行看板", "运行指标"), ("题库资源池", "增删改查"),
               ("用户管理", "查询与停用"), ("闯关记录", "来源统计"),
               ("操作日志", "审计留痕")]
    for i, (name, desc) in enumerate(a_funcs):
        x = 556 + i * 88
        c.line(x + 44, 248, x + 44, 268, color=ORANGE)
        c.rect(x, 268, x + 88, 330, fill=WHITE, outline=ORANGE, radius=7)
        c.text_center(x + 44, 288, name, size=12.5, bold=True)
        c.text_center(x + 44, 310, desc, size=10, color=SUB)

    # 支撑层
    c.rect(44, 366, 836, 470, fill=(247, 251, 255), outline=LINE, radius=10)
    c.text_center(440, 388, "支撑能力（贯穿各功能模块）", size=13.5, bold=True, color=BLUE_D)
    caps = ["内容安全过滤", "学段适配（三档）", "题库降级", "检索增强", "经验值激励", "操作审计"]
    for i, cap in enumerate(caps):
        x0 = 60 + i * 128
        c.rect(x0, 408, x0 + 116, 450, fill=WHITE, outline=BLUE, radius=7)
        c.text_center(x0 + 58, 429, cap, size=11.5, color=(40, 60, 84))
    return c.save("图4-2_系统功能结构图")


# ==================================================================
# 图 4-3 系统总体架构图
# ==================================================================
def figure_4_3():
    c = Canvas(860, 560)
    c.text_center(430, 26, "系统总体架构（四层）", size=19, bold=True, color=BLUE_D)

    layers = [
        ("表现层", "微信小程序（WXML / WXSS / JS）", "管理端 Web（HTML / CSS / JS）",
         BLUE_L, BLUE),
        ("接入层", "HTTP / RESTful · 统一前缀 /api/v1", "统一响应 {code, message, data}",
         YELLOW_L, (214, 168, 20)),
        ("应用服务层", "routers 路由 · services 业务 · llm 模型调用 · question_bank 题库 · "
                       "grades 学段 · safety 内容安全 · wrongbook 错题本 · admin 管理端",
         "业务规则全部收敛在服务层，可脱离 Web 层单独测试",
         BLUE_L, BLUE),
        ("数据层", "SQLite（10 张表）· 知识库分块 · 题目资源池", "连接复用 + 线程锁，可平滑迁移 MySQL",
         GREEN_L, GREEN),
    ]
    y = 56
    for name, left, right, fill, outline in layers:
        height = 96 if name == "应用服务层" else 78
        c.rect(40, y, 820, y + height, fill=fill, outline=outline, radius=10)
        c.rect(40, y, 158, y + height, fill=WHITE, outline=outline, radius=10)
        c.text_center(99, y + height / 2.0, name, size=15, bold=True,
                      color=BLUE_D if outline == BLUE else (140, 100, 20))
        if name == "应用服务层":
            c.wrap_center(489, y + height / 2.0,
                          ["routers 路由层 · services 业务服务层 · llm 模型调用层",
                           "question_bank 题库与降级 · grades 学段适配 · safety 内容安全",
                           "wrongbook 错题本 · admin / admin_db 管理端"],
                          size=12, color=INK, gap=24)
        else:
            c.text_center(489, y + height / 2.0, left, size=13)
            if right:
                c.text_center(489, y + height / 2.0 + 22, right, size=12, color=SUB)
        if y + height < 500:
            c.arrow(430, y + height, 430, y + height + 14, color=LINE, width=1.2)
        y += height + 14

    # 外部依赖
    c.rect(40, 496, 820, 540, fill=ORANGE_L, outline=ORANGE, radius=10, width=1.2)
    c.text_center(430, 518, "外部依赖：DeepSeek 大模型接口（OpenAI 兼容 /chat/completions）"
                            "——未配置密钥时自动降级，系统仍可完整运行", size=11.5,
                  color=(168, 90, 28))
    return c.save("图4-3_系统总体架构图")


# ==================================================================
# 图 4-4 数据库 E-R 图
# ==================================================================
def figure_4_4():
    c = Canvas(900, 600)
    c.text_center(450, 26, "数据库 E-R 图（10 张表）", size=19, bold=True, color=BLUE_D)
    c.text_center(450, 50, "矩形为实体，连线标注为一对多联系（1 : n）", size=11.5, color=SUB)

    def entity(cx, cy, title, fields, w=196, fill=BLUE_L, outline=BLUE):
        h = 34 + len(fields) * 17
        c.rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, fill=WHITE,
               outline=outline, radius=8)
        c.rect(cx - w / 2, cy - h / 2, cx + w / 2, cy - h / 2 + 24, fill=fill,
               outline=outline, radius=8)
        c.text_center(cx, cy - h / 2 + 12, title, size=12.5, bold=True,
                      color=BLUE_D if outline == BLUE else (168, 90, 28))
        for i, f in enumerate(fields):
            c.text(cx - w / 2 + 10, cy - h / 2 + 32 + i * 17, f, size=10.5, color=INK)
        return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)

    users = entity(150, 150, "users 用户表",
                   ["id 主键", "openid 唯一", "nickname", "total_xp 经验值", "status 状态", "grade 学段"])
    quizzes = entity(450, 150, "quiz_sessions 闯关会话表",
                     ["id 主键", "quiz_id 唯一", "user_id 外键", "title / grade / source",
                      "questions_json"])
    answers = entity(750, 150, "answer_records 答题记录表",
                     ["id 主键", "quiz_id 外键", "total / correct", "accuracy", "duration_ms"])
    reports = entity(750, 320, "reports 复盘报告表",
                     ["id 主键", "quiz_id 唯一", "report_json", "created_at"])
    wrong = entity(450, 330, "wrong_questions 错题本表",
                   ["id 主键", "user_id 外键", "stem / options_json", "correct_answer",
                    "wrong_count", "last_wrong_at"])
    docs = entity(150, 330, "knowledge_docs 知识库文档表",
                  ["id 主键", "doc_id 唯一", "filename / file_type", "content / status"])
    chunks = entity(150, 500, "knowledge_chunks 分块表",
                    ["id 主键", "doc_id 外键", "chunk_index", "content"])
    pool = entity(450, 500, "question_pool 题目资源池表",
                  ["id 主键", "theme / grade", "stem / answer", "difficulty", "enabled"])
    admins = entity(750, 500, "admins 管理端账号表",
                    ["id 主键", "username 唯一", "password_hash", "salt / role"])
    logs = entity(750, 660, "admin_logs 操作日志表",
                  ["id 主键", "username", "action", "detail"])

    def rel(a, b, label, side="h", color=BLUE):
        """在两个实体间画联系线并标注 1:n。"""
        if side == "h":
            (x0, y0, x1, y1), (u0, v0, u1, v1) = a, b
            if x1 < u0:
                c.line(x1, (y0 + y1) / 2, u0, (v0 + v1) / 2, color=color)
                c.text_center((x1 + u0) / 2, (y0 + y1) / 2 - 12, label, size=10.5, color=color)
            else:
                c.line(u1, (v0 + v1) / 2, x0, (y0 + y1) / 2, color=color)
                c.text_center((u1 + x0) / 2, (v0 + v1) / 2 - 12, label, size=10.5, color=color)
        else:
            c.line((a[0] + a[2]) / 2, a[3], (b[0] + b[2]) / 2, b[1], color=color)
            c.text_center((a[0] + a[2]) / 2 + 30, (a[3] + b[1]) / 2, label, size=10.5, color=color)

    rel(users, quizzes, "1 : n")
    rel(quizzes, answers, "1 : 1")
    rel(quizzes, reports, "1 : 1")
    rel(users, wrong, "1 : n")
    rel(users, docs, "1 : n", side="v", color=GREEN)
    rel(docs, chunks, "1 : n", side="v", color=GREEN)
    c.line((users[0] + users[2]) / 2, users[3], (docs[0] + docs[2]) / 2, docs[1], color=GREEN)
    c.text_center(150, 250, "1 : n", size=10.5, color=GREEN)
    c.line(wrong[3] - 20, wrong[3], wrong[3] - 20, pool[1] - 24, color=ORANGE)
    c.text_center(wrong[3] - 44, (wrong[3] + pool[1]) / 2, "错题来源", size=10.5, color=ORANGE)
    c.line((pool[0] + pool[2]) / 2, pool[3], (admins[0] + admins[2]) / 2, admins[1], color=ORANGE)
    c.text_center(600, 585, "管理端维护", size=10.5, color=ORANGE)
    c.line((admins[0] + admins[2]) / 2, admins[3], (logs[0] + logs[2]) / 2, logs[1], color=ORANGE)
    return c.save("图4-4_数据库E-R图")


# ==================================================================
# 图 3-1 系统用例图
# ==================================================================
def figure_3_1():
    c = Canvas(880, 620)
    c.text_center(440, 26, "系统用例图", size=19, bold=True, color=BLUE_D)

    def actor(cx, cy, name, color=BLUE):
        """简笔小人：头部圆 + 躯干 + 手臂 + 双腿。"""
        head_r = 7
        head_cy = cy - 34
        c.d.ellipse([(cx - head_r) * SCALE, (head_cy - head_r) * SCALE,
                     (cx + head_r) * SCALE, (head_cy + head_r) * SCALE],
                    outline=color, width=2 * SCALE)
        c.line(cx, head_cy + head_r, cx, cy - 6, color=color, width=2)
        c.line(cx - 12, cy - 22, cx + 12, cy - 22, color=color, width=2)
        c.line(cx - 9, cy + 8, cx, cy - 6, color=color, width=2)
        c.line(cx + 9, cy + 8, cx, cy - 6, color=color, width=2)
        c.text_center(cx, cy + 24, name, size=13, bold=True, color=color)

    actor(70, 300, "学生")
    actor(810, 300, "管理员", color=ORANGE)

    def usecase(cx, cy, text, fill=BLUE_L, outline=BLUE, w=250):
        c.rect(cx - w / 2, cy - 17, cx + w / 2, cy + 17, fill=fill, outline=outline, radius=17)
        c.text_center(cx, cy, text, size=12, color=INK)

    student_cases = [
        (145, "登录 / 游客模式进入"),
        (197, "按主题出题（可基于知识库资料）"),
        (249, "答题闯关与即时讲解"),
        (301, "查看复盘报告"),
        (353, "错题本与只练错题"),
        (405, "知识库资料上传与管理"),
        (457, "查看个人中心与经验值"),
    ]
    for cy, txt in student_cases:
        usecase(300, cy, txt)
        c.line(110, 300, 175, cy, color=LINE, width=1.0)

    admin_cases = [
        (145, "管理端登录与鉴权"),
        (197, "查看运行看板与趋势"),
        (249, "题库资源池增删改查"),
        (301, "用户查询与停用"),
        (353, "查看闯关记录"),
        (405, "查看操作日志"),
    ]
    for cy, txt in admin_cases:
        usecase(625, cy, txt, fill=ORANGE_L, outline=ORANGE, w=210)
        c.line(770, 300, 730, cy, color=LINE, width=1.0)

    usecase(300, 525, "内容安全过滤与学段适配", fill=YELLOW_L, outline=(214, 168, 20), w=280)
    c.text_center(440, 585, "说明：虚线表示「包含」关系——内容安全过滤与学段适配被出题、"
                            "答题、复盘报告三类用例复用", size=10.5, color=SUB)
    for cy in (197, 249, 301):
        c.line(300, cy + 17, 300, 508, color=(214, 168, 20), width=1.0, dash=(5, 5))
    return c.save("图3-1_系统用例图")


# ==================================================================
# 图 5-1 AI 出题处理流程图
# ==================================================================
def figure_5_1():
    c = Canvas(720, 900)
    c.text_center(360, 26, "AI 出题处理流程", size=19, bold=True, color=BLUE_D)
    cx = 300
    w = 330

    def box(cy, text, fill=BLUE_L, outline=BLUE, h=44, lines=None, size=12):
        c.rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, fill=fill, outline=outline, radius=8)
        if lines:
            c.wrap_center(cx, cy, lines, size=size, color=INK, gap=17)
        else:
            c.text_center(cx, cy, text, size=size, color=INK)

    def diamond(cy, text, h=58):
        c.d.polygon([(cx * SCALE, (cy - h / 2) * SCALE), ((cx + w / 2) * SCALE, cy * SCALE),
                     (cx * SCALE, (cy + h / 2) * SCALE), ((cx - w / 2) * SCALE, cy * SCALE)],
                    fill=YELLOW_L, outline=(214, 168, 20), width=2 * SCALE)
        c.text_center(cx, cy, text, size=11.5)

    def down(y0, y1, label=None):
        c.arrow(cx, y0, cx, y1, color=BLUE)
        if label:
            c.text(cx + 10, (y0 + y1) / 2 - 8, label, size=10.5, color=SUB)

    box(78, "", lines=["用户输入学习主题（一句话）", "可选：携带知识库文档 doc_id"], h=52)
    down(104, 140)
    box(164, "", lines=["内容安全校验与长度校验（safety）", "命中敏感词或超长 → 返回 4002 / 4000"],
        fill=ORANGE_L, outline=ORANGE, h=52)
    down(190, 226)
    diamond(262, "是否携带 doc_id？")
    c.line(cx + w / 2, 262, 610, 262, color=GREEN)
    c.text(620, 254, "是", size=11, color=GREEN)
    c.rect(490, 300, 706, 372, fill=GREEN_L, outline=GREEN, radius=8)
    c.wrap_center(598, 336, ["2-gram 词频向量余弦相似度检索", "取 Top-3 片段注入 Prompt"],
                  size=11, gap=18)
    c.line(598, 262, 598, 300, color=GREEN)
    c.line(598, 372, 598, 400, color=GREEN)
    c.line(598, 400, cx, 400, color=GREEN)
    c.text(624, 254 + 130, "", size=11)
    c.text(cx - 60, 254, "否（直接进入下一步）", size=10.5, color=SUB)
    down(262 + 29, 372)
    box(400, "", lines=["按学段组装 Prompt", "（题量 / 题干长度 / 用词难度 / 安全约束）"], h=52)
    down(426, 462)
    diamond(494, "是否配置大模型密钥？")
    c.line(cx + w / 2, 494, 610, 494, color=ORANGE)
    c.text(620, 486, "否", size=11, color=ORANGE)
    c.line(610, 494, 610, 530, color=ORANGE)
    c.line(610, 530, 540, 530, color=ORANGE)
    down(523, 560)
    box(586, "", lines=["调用 DeepSeek /chat/completions", "（httpx，temperature 0.8）"], h=50)
    down(611, 646)
    box(672, "", lines=["提取 JSON 与字段归一化", "内容安全过滤 + 题干长度过滤"], h=50)
    down(697, 732)
    diamond(770, "题目数量是否达标？", h=56)
    c.line(cx + w / 2, 770, 610, 770, color=ORANGE)
    c.text(620, 762, "不足", size=11, color=ORANGE)
    c.line(610, 770, 610, 800, color=ORANGE)
    c.line(610, 800, 540, 800, color=ORANGE)
    box(846, "", lines=["用内置题库 / 题目资源池补齐题量", "落库并返回可作答的题目列表"],
        fill=GREEN_L, outline=GREEN, h=50)
    c.line(cx, 798, cx, 821, color=BLUE)
    c.text(cx + 12, 806, "是", size=10.5, color=SUB)

    # 失败分支
    c.line(540, 586, 96, 586, color=ORANGE)
    c.line(96, 586, 96, 846, color=ORANGE)
    c.arrow(96, 846, cx - w / 2 - 6, 846, color=ORANGE)
    c.text(112, 566, "调用失败 / 返回非法 JSON / 全部题目不合规", size=10.5, color=ORANGE)
    c.text(112, 830, "降级：内置题库（6 大主题 60 题）", size=10.5, color=ORANGE)
    return c.save("图5-1_AI出题处理流程图")


if __name__ == "__main__":
    figure_3_1()
    figure_4_1()
    figure_4_2()
    figure_4_3()
    figure_4_4()
    figure_5_1()
    print("\n全部插图已生成到 %s" % OUT)
    sys.exit(0)
