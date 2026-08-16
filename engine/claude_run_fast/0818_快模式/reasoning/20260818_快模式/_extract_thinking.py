"""从子 agent 的 .output transcript 里提取「## 思考」原文，回填到 reasoning md。

用法：python _extract_thinking.py
产物：_extracted/{seat}.txt —— 每段是一个决策点的原始 text（含 ## 思考 + ## 决策）。
"""
import json
import os

BASE = r"C:\Users\Lenovo\AppData\Local\Temp\claude\d--life-board-game-project-six-dynasty\68a32ef2-c3a4-4971-9f6d-6bc880acb35a\tasks"

FILES = [
    ("a16732a48fffa7211", "north"),
    ("a7a8bd5fee874bba3", "jin_1"),
    ("ad44aa562022694f1", "jin_2"),
    ("ac7c80fab7d26b2a3", "jin_3"),
]

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_extracted")
os.makedirs(OUT_DIR, exist_ok=True)

for agent_id, seat in FILES:
    path = os.path.join(BASE, agent_id + ".output")
    if not os.path.exists(path):
        print(f"!! 缺失 {path}")
        continue
    texts = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") != "assistant":
                continue
            content = obj.get("message", {}).get("content", [])
            if isinstance(content, str):
                if content.strip():
                    texts.append(content)
            elif isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "text":
                        t = c.get("text", "").strip()
                        if t:
                            texts.append(t)
    out_path = os.path.join(OUT_DIR, seat + ".txt")
    with open(out_path, "w", encoding="utf-8") as f:
        for i, t in enumerate(texts, 1):
            f.write("\n\n" + "=" * 60 + f"\n[决策 #{i}]\n" + "=" * 60 + "\n" + t + "\n")
    print(f"{seat}: 提取 {len(texts)} 段 text -> {out_path}")
