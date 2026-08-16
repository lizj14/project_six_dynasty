"""把 _extracted/{seat}.txt 的「## 思考」原文 + 耗时回填进 reasoning/{seat}.md。

用法：python _backfill.py
"""
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
EXTRACTED = os.path.join(BASE, "_extracted")

HEADERS = {
    "north": (
        "# 北方（north）席位决策日志 · 快模式测试\n\n"
        "> seed=20260818 · 快模式（只读 rules_brief.md，不读代码）· 英雄：苻坚\n"
        "> 全程 0 工具调用（除首读规则）；21 次决策；耗时随回合上升（193s → 698s）\n\n"
        "## 决策原文（完整思考过程，未删改）\n"
    ),
    "jin_1": (
        "# 东晋1（jin_1）席位决策日志 · 快模式测试\n\n"
        "> seed=20260818 · 快模式 · 英雄：王导 · 公开目标加九锡(威望≥6) · 秘密目标河洛旧都(友方控制中原)\n"
        "> 10 次决策；✅ 第2回合达成加九锡\n\n"
        "## 决策原文（完整思考过程，未删改）\n"
    ),
    "jin_2": (
        "# 东晋2（jin_2）席位决策日志 · 快模式测试\n\n"
        "> seed=20260818 · 快模式 · 英雄：顾荣 · 公开目标加九锡(威望≥6) · 秘密目标崇奉三宝(佛学≥3)\n"
        "> 8 次决策；佛学 1/3（进行中）\n\n"
        "## 决策原文（完整思考过程，未删改）\n"
    ),
    "jin_3": (
        "# 东晋3（jin_3）席位决策日志 · 快模式测试\n\n"
        "> seed=20260818 · 快模式 · 英雄：桓温 · 公开目标配享太庙(功绩≥7) · 秘密目标家财万贯(手牌≥5)\n"
        "> 8 次决策；功绩 2→4（进行中），✅ 家财万贯达成\n\n"
        "## 决策原文（完整思考过程，未删改）\n"
    ),
}

# 每席每次决策的耗时（秒），顺序与 _extracted/{seat}.txt 的 [决策 #N] 一一对应
COSTS = {
    "north": [193, 68, 98, 317, 521, 116, 183, 277, 315, 360, 7,
              24, 181, 274, 311, 363, 424, 450, 529, 577, 698],
    "jin_1": [125, 13, 104, 156, 65, 98, 42, 69, 116, 232],
    "jin_2": [204, 146, 182, 266, 341, 50, 77, 114],
    "jin_3": [222, 58, 146, 166, 208, 345, 81, 119],
}

for seat, header in HEADERS.items():
    src = os.path.join(EXTRACTED, seat + ".txt")
    dst = os.path.join(BASE, seat + ".md")
    if not os.path.exists(src):
        print(f"!! 缺失 {src}")
        continue
    with open(src, encoding="utf-8") as f:
        body = f.read()

    costs = COSTS[seat]
    counter = [0]

    def repl(m):
        idx = counter[0]
        counter[0] += 1
        cost = f"（耗时 {costs[idx]}s）" if idx < len(costs) else ""
        return f"[决策 #{m.group(1)}{cost}]"

    body = re.sub(r"\[决策 #(\d+)\]", repl, body)

    with open(dst, "w", encoding="utf-8") as f:
        f.write(header + body + "\n")
    print(f"{seat}: 已回填（含耗时）-> {dst}")
