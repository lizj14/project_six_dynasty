# LLM 回合规划能力实验

## 目的

在写任何代码之前，先验证 LLM 能否基于**规则书 + 卡表 + 地图连接 + 当前玩家游戏视图**，产出有质量的回合战略分析和行动计划。

核心原则：**先探明 LLM 能力边界，再设计系统架构**——避免设计了一个精妙的方案，结果 LLM 根本产不出那种格式的输出。

## 隔离设计

LLM 只能看到以下四类信息：

| 输入 | 来源 | 说明 |
|------|------|------|
| 规则书摘要 | `rulebook.md` | 游戏概述、回合流程、行动效果、僭越、关键数值（~1600 chars） |
| 卡牌总表 | `card_design.csv` | 全部 150 张牌，按类型分4组，含效果文本（~6400 chars） |
| 地图连接 | `map_adjacency.yaml` | 12 区域信息 + 全部邻接关系（~1550 chars） |
| 游戏视图 | `SnapshotViewport` | 一个玩家的完整视图：手牌、朝堂、地图、轨道、对手、皇帝司马家（~2800 chars） |

**不包含**：测试日志、历史分析、代码上下文、其他玩家的手牌内容、任何之前的设计文档。

## 实验状态

使用真实游戏引擎（`GameEngine` + 4个 `DummyAI`）初始化一局，自动打完前2回合，在第3回合行动阶段开始前截取状态。**所有状态由真实对局产生**，不存在手编数据。

### 生成方式

```
Version.load("v1.0") → GameEngine + 4×DummyAI → setup_game()
→ _run_round() × 2  (完整打第1+2回合)
→ run_preparation_phase() (第3回合准备阶段)
→ 截取状态，选 turn_order 中第一个东晋玩家作为 viewer
```

每次运行因随机种子固定（seed=42），产出相同的确定性状态。

## 使用方法

```bash
# 1. 设置 API Key
export OPENAI_API_KEY="sk-xxx"

# 2. 可选：指定模型
export LLM_MODEL="gpt-4o"

# 3. 运行
cd d:/life/board_game/project_six_dynasty
python experiments/llm_turn_planning/run_experiment.py
```

## 输出

每次运行在 `outputs/<timestamp>/` 下保存：

| 文件 | 内容 |
|------|------|
| `prompt.txt` | 发送给 LLM 的完整 prompt（system + user） |
| `response.json` | API 原始响应（含 token 统计） |
| `response.txt` | LLM 输出的纯文本 |
| `config.json` | 本次实验配置（模型、温度等） |

## 迭代流程

1. 跑第一次 → 看 LLM 输出质量
2. 根据问题调整 prompt（格式、信息密度、输出约束）
3. 重复直到 LLM 能稳定产出可用结果
4. 基于实际产出的格式设计系统架构

## 脚本结构

`run_experiment.py`（单文件，~1100行）：

- `build_experiment_state()` — 手动构建中期 GameState（不依赖 setup_game）
- `build_rulebook_digest()` — 从 rulebook.md 提取关键章节
- `build_card_table()` — 从 card_design.csv 整理卡表
- `build_map_connections()` — 从 map_adjacency.yaml 生成地图文本
- `build_game_view_text()` — 通过 SnapshotViewport 生成玩家视图
- `build_prompt()` — 组装完整 prompt
- `call_llm()` — 调用 OpenAI API
- `save_results()` — 保存所有产物

## 相关文档

- [v1 LLM Hybrid Agent 实施计划](../../coding_plan/v1_llm_hybrid_agent_实施计划.md)
- [六朝AI方案设计](../../coding_plan/六朝AI方案设计.md)
- [MCTS 多人桌游研究](../../coding_plan/mcts_multiplayer_research.md)
