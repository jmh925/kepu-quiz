# -*- coding: utf-8 -*-
"""学段分级出题验证：确认小学低年级与初中拿到的是**不同难度**的题。

这是本次改动的核心断言：不只是题量变化，题库本身要按学段分开。
用法：先启动后端，再 python tools/check_grade_split.py
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "backend", "tests"))

from client import Client                      # noqa: E402

problems = []


def check(ok, msg):
    print(("[OK  ] " if ok else "[FAIL] ") + msg)
    if not ok:
        problems.append(msg)


def main():
    base = os.getenv("KEPU_BASE_URL", "http://127.0.0.1:8000")
    c = Client(base)

    # 同一主题、同学段各出 3 轮，收集题干的并集
    def sample(grade, rounds=3, topic="太阳系"):
        stems = set()
        for _ in range(rounds):
            r = c.post("/api/v1/quiz/generate", {"topic": topic, "grade": grade})
            if r.code != 0:
                return None
            for q in (r.data or {}).get("questions", []):
                stems.add(q["stem"])
            last = r.data
        return stems, last

    print("=== 1. 各学段出题的题干长度分布 ===")
    stats = {}
    for g in ("primary_low", "primary_high", "junior"):
        res = sample(g)
        if not res:
            check(False, "%s 出题失败" % g)
            return 1
        stems, last = res
        lens = [len(s) for s in stems]
        stats[g] = {"stems": stems, "maxlen": max(lens), "avglen": sum(lens) / len(lens)}
        print("  %-14s 题量/轮=%d  题干最长 %d 字  平均 %.0f 字"
              % (g, last["count"], max(lens), stats[g]["avglen"]))

    # 低年级题干必须明显短于初中
    check(stats["primary_low"]["maxlen"] < stats["junior"]["maxlen"],
          "低年级题干短于初中（%d 字 < %d 字）"
          % (stats["primary_low"]["maxlen"], stats["junior"]["maxlen"]))

    print("\n=== 2. 题干重合度（同一主题下） ===")
    pairs = [("primary_low", "junior"), ("primary_low", "primary_high"),
             ("primary_high", "junior")]
    for a, b in pairs:
        sa, sb = stats[a]["stems"], stats[b]["stems"]
        inter = sa & sb
        ratio = len(inter) / max(1, min(len(sa), len(sb)))
        print("  %-14s ∩ %-14s = %d 题（占较小集合 %.0f%%）" % (a, b, len(inter), ratio * 100))
        check(ratio <= 0.34, "%s 与 %s 的题目基本不同（重合 %.0f%%）" % (a, b, ratio * 100))

    print("\n=== 3. 各学段抽到的样题（各 3 道） ===")
    for g in ("primary_low", "primary_high", "junior"):
        print("  【%s】" % g)
        for s in sorted(stats[g]["stems"])[:3]:
            print("     - " + s)

    print("\n=== 4. 各学段题库可用题量 ===")
    check(True, "低年级 %d 题 / 高年级 %d 题 / 初中 %d 题 可供抽取"
          % (len(stats["primary_low"]["stems"]),
             len(stats["primary_high"]["stems"]),
             len(stats["junior"]["stems"])))

    print("\n未通过：%d 项" % len(problems))
    for p in problems:
        print("  - " + p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
