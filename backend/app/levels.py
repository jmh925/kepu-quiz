# -*- coding: utf-8 -*-
"""段位阶梯（成长体系）：经验值 → 等级 → 段位。

为什么要有这一层：只有一个孤零零的「Lv.7」对孩子没有意义——他不知道自己
走了多远、上面还有什么、最高能到哪儿。所以把等级归成 8 个有名字的段位，
像闯关游戏那样一档一档往上爬，并且**明确告诉他最高段位是什么**，
这样「继续答题」才有一个看得见的目标。

段位定义在这里是**唯一来源**：
- 后端通过 GET /api/v1/levels 下发；
- 前端从接口取，取不到时用 web/assets/app.js 里的同内容兜底；
- 管理端要展示段位时也走接口，避免两边各写一套导致对不上。

设计约定：
- 等级本身是连续的、不封顶：level = total_xp // XP_PER_LEVEL + 1。
  所以最高段位之后等级还会继续涨，只是段位停在最高档（和常见游戏一致）。
- 段位用「等级区间」划档而不是直接写经验值，这样以后调整 XP_PER_LEVEL
  不会让段位表整体错位。
- 每个段位给一个颜色与 emoji，前端直接拿来渲染，不用在前端再维护一份配色。
"""

# 每多少经验值升一级。前端 app.js 里的 levelInfo 必须与这里保持一致。
XP_PER_LEVEL = 50

# 段位阶梯：从低到高。
# min_level / max_level 是闭区间；最高段位 max_level 为 None 表示不封顶。
RANKS = [
    {
        "index": 1,
        "name": "科学小新芽",
        "emoji": "🌱",
        "min_level": 1,
        "max_level": 2,
        "color": "#7CB342",
        "slogan": "刚开始发芽，先随便逛逛",
        "tip": "答对一题就有 2 点经验，很快就能升上来。",
    },
    {
        "index": 2,
        "name": "好奇心学徒",
        "emoji": "🔍",
        "min_level": 3,
        "max_level": 4,
        "color": "#43A047",
        "slogan": "开始主动问为什么了",
        "tip": "试试换个学段，题目会更有挑战。",
    },
    {
        "index": 3,
        "name": "问题小侦探",
        "emoji": "🕵️",
        "min_level": 5,
        "max_level": 7,
        "color": "#00ACC1",
        "slogan": "错题本开始派上用场",
        "tip": "「只练错题」不调用出题服务，随时都能练。",
    },
    {
        "index": 4,
        "name": "实验小助手",
        "emoji": "⚗️",
        "min_level": 8,
        "max_level": 10,
        "color": "#039BE5",
        "slogan": "能把知识讲给别人听了",
        "tip": "去 PK 场试试，赢一局有额外经验。",
    },
    {
        "index": 5,
        "name": "知识小达人",
        "emoji": "📚",
        "min_level": 11,
        "max_level": 14,
        "color": "#3949AB",
        "slogan": "知识面已经很宽了",
        "tip": "语文、数学、英语三科也来几局？",
    },
    {
        "index": 6,
        "name": "探索小队长",
        "emoji": "🧭",
        "min_level": 15,
        "max_level": 19,
        "color": "#8E24AA",
        "slogan": "会带着别人一起学",
        "tip": "连胜能攒得更快，注意保持手感。",
    },
    {
        "index": 7,
        "name": "科学小博士",
        "emoji": "🎓",
        "min_level": 20,
        "max_level": 25,
        "color": "#D81B60",
        "slogan": "离最高段位只差一步",
        "tip": "把知识库里的讲义传上来，能让出题更对味。",
    },
    {
        "index": 8,
        "name": "传奇科学家",
        "emoji": "🏆",
        "min_level": 26,
        "max_level": None,
        "color": "#F57C00",
        "slogan": "最高段位，可以一直待下去",
        "tip": "到了最高段位等级还会继续涨，继续积累吧。",
    },
]

MAX_RANK_NAME = RANKS[-1]["name"]


def xp_for_level(level):
    """升到第 level 级所需的累计经验值（level 从 1 开始）。"""
    return max(0, (int(level) - 1) * XP_PER_LEVEL)


def level_of(total_xp):
    """经验值 → 等级。不封顶。"""
    xp = max(0, int(total_xp or 0))
    return xp // XP_PER_LEVEL + 1


def rank_of_level(level):
    """等级 → 段位定义（dict）。超出最高档时返回最高段位。"""
    lv = max(1, int(level or 1))
    for r in RANKS:
        if r["max_level"] is None:
            if lv >= r["min_level"]:
                return r
            continue
        if r["min_level"] <= lv <= r["max_level"]:
            return r
    return RANKS[0]


def rank_index_of_level(level):
    return rank_of_level(level)["index"]


def next_rank(level):
    """返回下一段位定义；已在最高段位返回 None。"""
    cur = rank_of_level(level)
    for r in RANKS:
        if r["index"] == cur["index"] + 1:
            return r
    return None


def progress(total_xp):
    """完整的成长进度：当前等级、段位、到下一级的进度、到下一段位的进度。

    前端只要拿这一个结构就能把「我的」页和「成长阶梯」页都画出来。
    """
    xp = max(0, int(total_xp or 0))
    level = level_of(xp)
    rank = rank_of_level(level)
    nxt = next_rank(level)

    in_level = xp % XP_PER_LEVEL
    level_progress = {
        "level": level,
        "xp_in_level": in_level,
        "xp_per_level": XP_PER_LEVEL,
        "xp_to_next_level": XP_PER_LEVEL - in_level,
        "percent": int(round(in_level * 100.0 / XP_PER_LEVEL)),
    }

    rank_progress = None
    if nxt:
        # 到下一段位：从本段位起始等级算起，避免把上一段位的积累算进来
        start_xp = xp_for_level(rank["min_level"])
        target_xp = xp_for_level(nxt["min_level"])
        span = max(1, target_xp - start_xp)
        done = max(0, min(span, xp - start_xp))
        rank_progress = {
            "next_name": nxt["name"],
            "next_emoji": nxt["emoji"],
            "next_level": nxt["min_level"],
            "xp_needed": max(0, target_xp - xp),
            "percent": int(round(done * 100.0 / span)),
        }

    return {
        "total_xp": xp,
        "level_progress": level_progress,
        "rank": rank,
        "rank_progress": rank_progress,
        "is_max_rank": nxt is None,
        # 到最高段位还需要多少经验（已在最高段位时为 0）——直接回答「最高能到哪」
        "xp_to_max_rank": max(0, xp_for_level(RANKS[-1]["min_level"]) - xp),
    }


def ladder():
    """完整段位表，供「成长阶梯」页渲染。"""
    out = []
    for r in RANKS:
        item = dict(r)
        item["min_xp"] = xp_for_level(r["min_level"])
        item["max_xp"] = (xp_for_level(r["max_level"] + 1) - 1
                          if r["max_level"] is not None else None)
        item["is_top"] = r["max_level"] is None
        out.append(item)
    return out


def overview(total_xp=0):
    """段位表 + 我的进度，一次给全（前端一个请求就够了）。

    `total_ranks` / `max_rank_name` 放在**顶层**而不是 `me` 里：
    它们是这张阶梯表的属性（共有几档、最高叫什么），与"我是谁"无关。
    """
    return {
        "xp_per_level": XP_PER_LEVEL,
        "total_ranks": len(RANKS),
        "max_rank_name": MAX_RANK_NAME,
        "max_rank_xp": xp_for_level(RANKS[-1]["min_level"]),
        "ranks": ladder(),
        "me": progress(total_xp),
    }
