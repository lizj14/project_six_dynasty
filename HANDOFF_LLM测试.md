# 六朝何事 · LLM Agent 测试交接文档

> 目标读者：新开的 Claude Code 窗口（以下简称「裁判」）。读完本文档，即可接手「用 LLM agent 玩六朝何事」的测试。

---

## 1. 一句话概述

「六朝何事」是一款自研四人半合作桌游（1 北方 vs 3 东晋 + 非玩家「司马家」）。这个项目在做的事：**让 LLM agent 作为玩家打这个游戏**，研究「LLM 读代码/读规则要点打高复杂度桌游」的能力。

方法：**文件驱动 + 确定性回放** —— 对局状态 = `seed + moves.jsonl` 的纯函数，每一步决策追加到 `moves.jsonl`，随时可从 seed 完整回放。

## 2. 核心概念

- **裁判**：就是你（主 agent）。负责编排子 agent、调用引擎命令、落盘日志。
- **子 agent**：4 个独立上下文的 coding agent（北方 north / 东晋1 jin_1 / 东晋2 jin_2 / 东晋3 jin_3），各自扮演一个席位。
- **快模式**：子 agent **只读裁判提炼的规则要点**（`rules_brief.md`），不读引擎代码/卡表。这是「喂规则摘要的 LLM」模式。
- **逐步决策**：每到一个决策点，子 agent 决策一次（一次 LLM 调用）。
- **回合级规划**：每个玩家行动开始时，子 agent **一次性规划整回合**（输出语义行动序列 plan），裁判逐条执行。

## 3. 关键文件地图

```
项目根目录/
├── HANDOFF_LLM测试.md              ← 本文档
├── board_info.md                   ← 地图（地点/连接/区域VP/初始归属）
├── versions/v1.0/rulebook.md       ← 权威规则书
├── versions/v1.0/cards/cards_compiled.json  ← 编译后的卡牌数据（text 含「仅限东晋/北方」）
│
├── engine/
│   ├── play_claude.py              ← 驱动器（原版，STATE_DIR=claude_run）
│   ├── play_claude_fast.py         ← 驱动器（快模式版，STATE_DIR=claude_run_fast）
│   ├── claude_run/                 ← 原版状态目录（另一窗口在用）
│   └── claude_run_fast/            ← 快模式状态目录（本测试用）
│       ├── rules_brief.md          ← 北方规则要点（子 agent 读这个）
│       ├── rules_brief_jin.md      ← 东晋规则要点（东晋子 agent 读这个）
│       ├── plan_prompt.md          ← 回合级规划 Prompt 模板（含额度状态区块）
│       ├── 0818_快模式/            ← 逐步决策测试归档（含 reasoning 日志）
│       └── 0818_快回合模式/        ← 回合级规划测试归档（含问题分析、重规划模板）
│
└── research/llm_coding_agent_test/ ← 调研文档 + 测试总结
    └── 六朝何事_4agent测试总结.md  ← 第一轮测试总结（重要背景）
```

## 4. 引擎命令速查（play_claude_fast.py）

```bash
# 在项目根目录执行（python 已支持中文路径）
python engine/play_claude_fast.py new --seed 20260819 --human observer   # 开新局（清空 moves.jsonl）
python engine/play_claude_fast.py step          # 从 seed+moves 回放，dump 下一个决策点到 claude_state.json
python engine/play_claude_fast.py move '<json>'  # 记录一步决策（追加到 moves.jsonl）
python engine/play_claude_fast.py undo --count N  # 回退末尾 N 步（回合级规划执行失败时用）
python engine/play_claude_fast.py show          # 紧凑打印当前决策点
python engine/play_claude_fast.py status        # 看进度
python engine/play_claude_fast.py discard_order '<json>'  # 写弃牌顺序 {"north": ["牌A","牌B","【新手牌】"]}
```

`--human observer` 表示四席全是子 agent，裁判只做编排。

## 5. 决策协议（moves.jsonl 每行一个 JSON）

| 决策类型 | 格式 |
|---|---|
| 初设 | `{"player":"north","type":"setup","hero":0,"face_down":6,"payment":[]}` |
| 行动（下标模式） | `{"player":"north","type":"action","index":3}`（-1=结束行动） |
| 行动（语义模式） | `{"player":"north","type":"march","target":"洛阳"}` |
| 结束回合（语义） | `{"player":"north","type":"end_turn"}` |
| 目标选择 | `{"player":"north","type":"target","index":1}` |
| 弃牌 | `{"player":"north","type":"discard","indices":[0,3]}` |
| 打牌选择 | `{"player":"north","type":"card_play","index":0}`（-1=拒绝） |
| 二选一 | `{"player":"north","type":"choice","index":0}` |

**语义模式**（回合级规划用）：type 取值 `march`/`occupy`/`fortify`/`play_card`/`court_action`/`play_public_card`/`recruit`/`draw`/`activate`/`end_turn`。
- `occupy` 必带 `use_sima`（false=自己部队，true=司马家部队）
- `play_card`/`play_public_card`/`recruit` 用 `card`（牌名），需要支付时带 `payment`（牌名列表）
- `march`/`occupy`/`fortify`/`convert` 用 `target`（**地点名**，不是区域名）

## 6. 开一局测试的完整流程

### 6.1 准备

1. 选一个 seed（如 `20260820`）
2. 开新局：`python engine/play_claude_fast.py new --seed <seed> --human observer`

### 6.2 spawn 4 个子 agent

用 Agent 工具 spawn 4 个 `general-purpose` 子 agent，每个 prompt 要点：
- 你是【北方/东晋X】玩家，参与「快模式」测试
- 规则要点在 `engine/claude_run_fast/rules_brief.md`（北方）/ `rules_brief_jin.md`（东晋），**现在 Read 它一次**
- **不要读引擎代码、规则书、卡表 JSON**
- （回合级规划模式）说明：初设逐步决策，之后每回合一次性规划整回合

### 6.3 逐步决策模式（快模式）

循环执行：
1. `step` → 看 claude_state.json 的 `player` 和 `type`
2. 把决策点（viewport 或 choices）用 SendMessage 发给对应子 agent
3. 收决策 → `move '<json>'`
4. 回到 1，直到游戏结束

setup 阶段（type=setup）是每席一次决策；登场阶段可能触发 target/choice；行动阶段是逐步的 action 决策。

### 6.4 回合级规划模式（快回合模式）

setup + 登场仍用逐步决策；从第 1 回合行动阶段开始：

1. `step` 到某席 action 决策点
2. 把「手牌效果 + 可选行动 + `plan_prompt.md` 模板（含额度状态）」发给该席子 agent
3. 收整回合 `plan`（reasoning + discard_order + plan 数组）
4. 先 `discard_order '<json>'` 写弃牌顺序
5. 逐条 `move` plan 的语义行动（加 player 字段）
6. 遇到子决策点（target/choice/discard/card_play）按 plan 意图处理；plan 没写就回传子 agent
7. 执行失败（no_match）→ `undo` 回退 → 用「重规划反馈模板」回传当前状态 → 拿新 plan 重来
8. 执行到 `end_turn`，轮到下一席

## 7. 已知的坑（务必先读）

1. **语义字段**：子 agent 可能用 `name`（应 `card`）、`recruit` 用 `payment`（应 `card`）、`march target` 写区域名（应地点名）。执行会 no_match，需要按意图纠正或回传。
2. **额度状态**：回合级规划时，子 agent 会靠「推理」判断手牌/牌组行动额度，容易误判。**务必把额度状态喂给它**——`plan_prompt.md` 已有「额度状态」区块（从 viewport 的 `can_take_hand_action`/`has_drawn_quick` 等字段填）。重规划时用 `0818_快回合模式/重规划反馈模板.md`。
3. **回退**：`move` 只追加不校验，no_match 后错误步骤残留。用 `undo --count N` 回退（别手工改文件）。
4. **子 agent 输出落盘**：完整记录子 agent 的 reasoning + plan 原文到 reasoning 日志，**不要提炼**（详见 `0818_快回合模式/_extract.py` 的提取方式）。
5. **已修的引擎 bug**（commit `41d8b06`）：苏峻等「选择一项」事件牌不结算、风声鹤唳阵营限定 text 缺失、姚苌唯一牌重复发牌。这些已修但**尚未在新对局中完整验证**，测试时留意。

## 8. 下一步建议

1. **重跑回合级规划**：用新 seed 验证「苏峻修复 + 额度模板 + undo」是否让执行顺畅（上次卡在北方/东晋1 的执行层问题）。
2. 观测指标：每回合平均中断重规划次数、单回合规划耗时、语义错误率。
3. 若继续完善执行基建：`move` 时预检语义匹配（错了不落盘，替代「先落盘再 undo」）。

## 9. 快速上手检查清单

- [ ] 能跑通 `new + step`，看懂决策点 dump
- [ ] 会 spawn 北方子 agent 做一次 setup 决策
- [ ] 会用 `move` 落子、`step` 回放、`undo` 回退
- [ ] 回合级规划：会填 plan_prompt 的额度状态、会用重规划反馈模板
- [ ] 知道语义协议的字段（card/target/use_sima，不是 name/区域名）
