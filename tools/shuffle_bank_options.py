# -*- coding: utf-8 -*-
"""把 bank_part_b.json 里正确答案的下标打散，避免“答案总在第一个”。

做法：保持每题的选项内容不变，只调整选项顺序，并同步更新 answer 下标。
用固定随机种子，保证结果可复现。
"""
import json
import os
import random

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "backend", "app", "bank_part_b.json")

with open(PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

rnd = random.Random(20240607)

# 先造一份“尽量均摊”的位置清单（0/1/2/3 各约 1/4），再打乱后逐题分配，
# 这样既看不出规律，也不会出现某个位置堆积答案的情况。
targets = [i % 4 for i in range(len(data))]
rnd.shuffle(targets)

for q, target in zip(data, targets):
    opts = q["options"]
    right = opts[q["answer"]]
    wrongs = [o for i, o in enumerate(opts) if i != q["answer"]]
    new_opts = list(wrongs)
    new_opts.insert(target, right)
    q["options"] = new_opts
    q["answer"] = target

with open(PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")

from collections import Counter
print("答案下标分布:", dict(sorted(Counter(q["answer"] for q in data).items())))
for t in ["物理", "化学", "科技"]:
    print("  %s: %s" % (t, dict(sorted(Counter(q["answer"] for q in data if q["theme"] == t).items()))))
for g in ["primary_low", "primary_high", "junior"]:
    print("  %-13s: %s" % (g, dict(sorted(Counter(q["answer"] for q in data if q["grade"] == g).items()))))
