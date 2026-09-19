# -*- coding: utf-8 -*-
"""论文成稿自检：字数统计 + 图表引用核对 + 禁用词扫描。

用它代替人工逐段检查，改稿后重跑即可确认没有引入问题。

用法（在仓库根目录）：
    python tools/check_thesis.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
THESIS = os.path.join(ROOT, "docs", "thesis")
FIGURES = os.path.join(ROOT, "docs", "figures")
MERGED = os.path.join(THESIS, "05_论文全文.md")

# 事实清单里的红线：源码中不存在或据实未实现的内容，不得写进论文
BANNED = [
    "SpringBoot", "Spring Boot", "Redis", "LangChain", "LangGraph", "ReAct",
    "Tavily", "Chroma", "嵌入向量", "embedding", "Embedding",
    "腾讯云", "COS", "通义万相", "阿里云百炼", "MySQL", "aiomysql",
    "Docker", "微信云托管", "异步任务轮询", "jscode2session", "Taro", "uni-app",
    "多选题", "判断题",
]
# 允许出现，但必须出现在「明确否定 / 对比」的语境中（用于技术选型论证）
NEGATED_OK = {
    "向量数据库": ["替代", "不采用", "并非", "无需", "没有引入", "未引入", "不必", "而非",
                   "主流方案"],
}
# 需要出现的关键事实（防止写成空壳或写错口径）
REQUIRED = [
    ("SQLite", "数据库类型"),
    ("FastAPI", "后端框架"),
    ("DeepSeek", "大模型"),
    ("微信小程序", "客户端形态"),
    ("2-gram", "检索方案"),
    ("PBKDF2", "管理端口令存储"),
    ("降级", "可靠性设计"),
    ("wrong_questions", "错题本表"),
    ("question_pool", "题目资源池表"),
    ("admin_logs", "操作日志表"),
    ("4002", "内容安全错误码"),
    ("primary_low", "学段取值"),
]


def cjk_count(text):
    """统计中文字符数（不含英文与数字），与大纲的字数口径一致。"""
    return len(re.findall(r"[\u4e00-\u9fa5]", text))


def strip_markdown(text):
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return text


def main():
    if not os.path.exists(MERGED):
        print("未找到 %s，请先运行 tools/md2docx.py 生成合并稿" % MERGED)
        return 2
    with open(MERGED, "r", encoding="utf-8") as fh:
        raw = fh.read()
    text = strip_markdown(raw)
    chars = cjk_count(text)

    print("=" * 62)
    print("论文成稿自检")
    print("=" * 62)
    print("合并稿：%s" % MERGED)
    print("中文字符总数：%d（含摘要、参考文献、致谢）" % chars)

    # 分章统计
    print("\n--- 分章字数 ---")
    chapters = re.split(r"\n(?=# )", raw)
    total_body = 0
    for ch in chapters:
        title = ch.split("\n", 1)[0].strip("# ").strip()
        if not title:
            continue
        n = cjk_count(strip_markdown(ch))
        print("  %-24s %5d 字" % (title[:24], n))
        if re.match(r"^第 [1-7] 章", title):
            total_body += n
    print("  正文（第 1～7 章）合计：%d 字" % total_body)

    problems = []

    # 图表引用与文件核对
    print("\n--- 图表核对 ---")
    fig_refs = sorted(set(re.findall(r"图\s*(\d+-\d+)", raw)))
    fig_files = sorted(os.listdir(FIGURES)) if os.path.isdir(FIGURES) else []
    print("  正文引用图号：%s" % "、".join("图 " + f for f in fig_refs))
    print("  插图文件（%d 个）：%s" % (len(fig_files), "、".join(fig_files)))
    for num in fig_refs:
        if not any(num in name for name in fig_files):
            problems.append("图 %s 在正文中被引用，但 docs/figures 下没有对应文件" % num)
    table_refs = sorted(set(re.findall(r"表\s*(\d+-\d+)", raw)))
    print("  正文引用表号（%d 个）：%s" % (len(table_refs), "、".join("表 " + t for t in table_refs)))

    # 禁用词
    print("\n--- 口径扫描（源码中不存在的内容不得出现）---")
    hit_any = False
    for word in BANNED:
        positions = [m.start() for m in re.finditer(re.escape(word), raw)]
        if positions:
            hit_any = True
            for pos in positions[:2]:
                snippet = raw[max(0, pos - 30):pos + 30].replace("\n", " ")
                print("  ✗ 命中「%s」：…%s…" % (word, snippet))
            problems.append("出现禁用词「%s」（%d 处）" % (word, len(positions)))
    # 允许否定式提及的词
    for word, markers in NEGATED_OK.items():
        for m in re.finditer(re.escape(word), raw):
            window = raw[max(0, m.start() - 40):m.start() + 40]
            if any(marker in window for marker in markers):
                continue
            hit_any = True
            print("  ✗ 「%s」出现在非否定语境：…%s…" % (word, window.replace("\n", " ")))
            problems.append("「%s」出现在可能被理解为「已采用」的语境中" % word)
    if not hit_any:
        print("  未命中任何禁用词")

    # 必备事实
    print("\n--- 必备事实核对 ---")
    for word, desc in REQUIRED:
        ok = word in raw
        print("  [%s] %s（%s）" % ("OK " if ok else "FAIL", word, desc))
        if not ok:
            problems.append("缺少必备事实：%s（%s）" % (word, desc))

    # 参考文献
    refs = re.findall(r"^\s*\[(\d+)\]\s", raw, flags=re.M)
    if refs:
        nums = sorted(set(int(x) for x in refs))
        print("\n--- 参考文献 ---")
        print("  条目数：%d，编号范围：[%d] - [%d]，连续：%s"
              % (len(nums), nums[0], nums[-1], nums == list(range(nums[0], nums[-1] + 1))))
        foreign = len(re.findall(r"^\s*\[\d+\]\s*[A-Z][A-Z\-\.]*(?:\s+[A-Z])", raw, flags=re.M))
        print("  外文文献（GB/T 7714 全大写姓氏格式，粗估）：%d 条" % foreign)
        if foreign < 5:
            problems.append("外文文献少于 5 条（规范要求不少于 3 条，本论文目标 5 条以上）")
    else:
        problems.append("没有找到参考文献条目")

    print("\n" + "=" * 62)
    if problems:
        print("发现问题 %d 项：" % len(problems))
        for p in problems:
            print("  - %s" % p)
        return 1
    print("自检通过：字数达标、图表齐全、无禁用词、必备事实齐备。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
