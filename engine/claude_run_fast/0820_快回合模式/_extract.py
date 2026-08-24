"""从子 agent 的 .output transcript 提取完整输出，落盘到 reasoning/。

用法：python _extract.py
"""
import json
import os

BASE = r"C:\Users\Lenovo\AppData\Local\Temp\claude\d--life-board-game-project-six-dynasty\68a32ef2-c3a4-4971-9f6d-6bc880acb35a\tasks"

# 有 .output 记录的 agent（北方/东晋3 被 SendMessage 续接过）
FILES = [
    ("a2fd1f48fd51cf7bc", "north"),
    ("a2e38ce60627d6c84", "jin_3"),
]

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reasoning")
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
    out = os.path.join(OUT_DIR, seat + ".md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# {seat} 席位决策日志 · 回合级规划测试\n\n")
        f.write("> seed=20260820 · 快模式 + 回合级规划\n")
        f.write("> 子 agent 原始输出（未删改），含完整 reasoning + plan\n\n")
        for i, t in enumerate(texts, 1):
            f.write("\n\n" + "=" * 60 + f"\n[决策 #{i}]\n" + "=" * 60 + "\n" + t + "\n")
    print(f"{seat}: 提取 {len(texts)} 段 -> {out}")
