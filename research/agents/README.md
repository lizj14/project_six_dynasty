# Agent 调研存档

> 创建日期: 2026-07-20 | 最后更新: 2026-07-21
> 本项目 (`research/agents/`) 存档对 AI Agent 三个方向的系统调研。

---

## 调研方向与文件索引

### [方向一：游戏 AI Agent](01_game_ai_agents.md)
**基于 RL/搜索的经典游戏 AI 里程碑**

| # | 代表工作 | 年份 | 核心方法 | 目标游戏 |
|---|---------|------|----------|----------|
| 1 | **AlphaGo** | 2016 | SL + RL + MCTS | 围棋 |
| 2 | **AlphaZero** | 2018 | 纯自对弈 RL + MCTS | 围棋/象棋/将棋 |
| 3 | **MuZero** | 2020 | 隐式环境模型 + MCTS | 棋盘+Atari |
| 4 | **OpenAI Five** | 2019 | 分布式 PPO + 自对弈 | Dota 2 |
| 5 | **Pluribus** | 2019 | CFR + 抽象 | 六人德州扑克 |
| 6 | **AlphaStar** | 2019 | 联赛训练 + 模仿学习 | 星际争霸 II |
| 7 | **DeepNash** | 2022 | R-NaD (演化博弈论) | Stratego |

**关键洞察**：游戏 AI 从领域专用走向通用算法，从完美信息走向不完美信息博弈。

---

### [方向二：LLM Agent 的决策能力](02_llm_agent_decision.md)
**大语言模型作为自主决策体**

| # | 代表工作 | 年份 | 核心范式 | 关键贡献 |
|---|---------|------|----------|----------|
| 1 | **ReAct** | 2023 | 推理+行动交织 | LLM Agent 基础范式的奠基 |
| 2 | **Toolformer** | 2023 | 自监督工具学习 | 无需人工标注学会调用 API |
| 3 | **Reflexion** | 2023 | 口头强化学习 | 语言级试错学习，HumanEval 91% |
| 4 | **Tree of Thoughts** | 2023 | 树搜索推理 | Game of 24 从 4%→74% |
| 5 | **CAMEL** | 2023 | 角色扮演多 Agent | 首个多 Agent 自主协作框架 |
| 6 | **MetaGPT** | 2023 | SOP 流水线多 Agent | 瀑布式软件开发 |
| 7 | **Beyond ReAct** | 2025 | 规划-执行分离 | DAG 规划，突破局部最优 |
| 8 | **Thinker** | 2025 | 状态机增强生成 | Llama 405B+SMAG≈GPT-4o |

**关键洞察**：LLM Agent 正从反应式走向规划式，工具接口设计的创新 ≥ 基座模型能力提升。

---

### [方向三：LLM Agent 驱动游戏 AI](03_llm_driven_game_ai.md)
**用 LLM 直接玩游戏、驱动 NPC、探索世界**

| # | 代表工作 | 年份 | 目标游戏 | 核心创新 |
|---|---------|------|----------|----------|
| 1 | **Generative Agents** | 2023 | Smallville | 记忆+反思+规划 → 涌现社会行为 |
| 2 | **Voyager** | 2023 | Minecraft | 终身学习+自动课程+技能库 |
| 3 | **Cradle** | 2024 | RDR2/多游戏 | 通用计算机控制，截图→键鼠 |
| 4 | **PokéLLMon** | 2024 | Pokémon | In-Context RL，人类水平对战 |
| 5 | **JARVIS-1** | 2023 | Minecraft | 记忆增强多模态，200+ 任务 |
| 6 | **GITM** | 2023 | Minecraft | 层级规划，70+ 通用任务 |
| 7 | **MindAgent** | 2023 | Overcooked | 多 Agent 协作基准 |
| 8 | **SPRING** | 2024 | 多游戏 | 读说明书→玩游戏 |

**关键洞察**：LLM Agent 可以零样本理解游戏、生成策略、与人类对战。87% 的开发者已在采用。

---

## 三方向交叉关系

```
方向一 (经典游戏 AI)          方向二 (LLM Agent 决策)
  RL + MCTS + CFR     ←→     推理 + 规划 + 工具 + 反思
         ↘                    ↙
         方向三 (LLM 驱动游戏 AI)
          记忆架构 + 代码生成 + 视觉交互
                     ↓
            六朝 (Six Dynasties) AI
```

---

## 对六朝项目的核心启示

| 来源 | 可直接借鉴的思路 |
|------|-----------------|
| AlphaZero 自对弈 | 大规模生成高质量对局数据，训练六朝专用 AI |
| Pluribus CFR + 抽象 | 不完美信息卡牌博弈的蓝图策略计算 |
| Reflexion 口头 RL | AI 从失败对局中总结反思，跨对局持续成长 |
| Tree of Thoughts | 关键决策节点（称帝/迁都）的多路径树搜索评估 |
| Generative Agents 记忆 | AI 维护持久的对手画像和策略偏好 |
| Voyager 技能库 | 有效策略模板的存储、检索和组合复用 |
| PokéLLMon ICRL | 根据回合反馈进行在线策略调整 |
| Cradle 视觉交互 | 通过截图理解游戏局面（如果六朝有 GUI） |
| MetaGPT SOP | 多维度（军事/文化/经济）分配给专门的子 Agent |
