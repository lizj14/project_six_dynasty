# LLM / AI 玩 Dominion（领土）调研

> 创建日期: 2026-08-04 | 最后更新: 2026-08-04
>
> 深度解析: [Principality AI (MCP/LLM)](01_principality_ai_mcp.md) | [Dominion RL Benchmark (Rainbow DQN)](02_dominion_rl_benchmark.md) | [Geometric DL + SAC](03_geometric_deep_learning_sac.md) | [启发式基线方法](04_heuristic_baselines.md) | [相邻工作 & 补充调研](05_adjacent_works.md)
>
> 本项目 (`research/agents/dominion/`) 调研现有使用 AI 玩 Dominion（领土/皇舆争霸）卡牌构筑游戏的代表性研究工作。基于一手资料（论文 + GitHub 代码仓库 + 实际运行验证）重新分析整理。

---

## 调研背景

Dominion（领土/皇舆争霸）是 Donald X. Vaccarino 于 2008 年设计的卡牌构筑（Deck-Building）游戏，开创了这一游戏类型。适合 AI 研究的特征：

- **巨大的策略空间**：每局从 350+ 张王国卡中随机选 10 张，组合数约 6×10¹⁸
- **可变动作空间**：每回合可购买的卡牌取决于手牌金币数，动作空间动态变化
- **长时域规划**：早期买牌决定数十回合后的牌组质量，需要跨回合战略连贯性
- **随机性与控制**：洗牌引入随机性，但牌组管理能力决定了随机性的上限
- **组合爆發**：正确搭配卡牌可产生非线性收益（Village + Smithy 引擎）

这些特征使 Dominion 成为评估 AI 在**动态动作空间、组合推理、长时域规划**方面能力的优秀测试平台。

---

## 五大代表性工作总览

| # | 项目 | 年份 | 核心方法 | 游戏规模 | 关键表现 |
|---|------|------|----------|----------|---------|
| 1 | **Principality AI** | 2025–26 | LLM via MCP + Claude | 25 张王国卡 (Base Set) | 概念验证，MCP 接口设计优秀 |
| 2 | **Dominion RL Benchmark** | 2024 | Rainbow DQN | 完整游戏 | ~7,000 局超越 Provincial Bot |
| 3 | **Geometric DL + SAC** | 2023 | Soft Actor-Critic + 多重集表示 + 课程学习 | 26 张王国卡 | 首次诱导出引擎策略（14% vs BM），揭示了标准RL学不会复杂策略的根本原因 |
| 4 | **Dominion RL (DQN + IL)** | 2019 | DQN + 模仿学习 | ~20 张 (3 扩展) | 31–60 分 (Big Money + Wharf) |
| 5 | **Dominiate** | 2013–14 | 优先级/价值规则引擎 | 基础版 | 经典启发式基线 |

---

## 项目速览

### [Principality AI](01_principality_ai_mcp.md) — 唯一的 LLM 路径

**Evan DeLord** 用 TypeScript 构建的完整 Dominion 引擎 + MCP Server。**唯一**让 Claude/GPT 作为玩家通过 MCP 协议操控 Dominion 的开源项目。支持 CLI/Web/MCP 三种接口，97%+ 测试覆盖率。游戏引擎 + PendingEffect 状态机设计精巧，三级详细度状态查询是 LLM 游戏 Agent 的 token 效率最佳实践。

**关键发现**：
- MCP 三层工具（game_session / game_observe / game_execute）足以覆盖完整游戏交互
- 三级详细度（minimal/standard/full）设计使单决策 token 消耗可控（60–1000 tokens）
- 自动回传状态减少 50% MCP 调用
- CLI 仅内置 Big Money 规则 AI，真正的 LLM 对战需要 MCP 路径

---

### [Dominion RL Benchmark (Rainbow DQN)](02_dominion_rl_benchmark.md) — 最大规模 RL 实验

**Halawi et al. (2024)** 正式提出 Dominion 作为下一代 RL 基准。关键贡献：

- **Dominion Online Dataset**：2,000,000+ 真人玩家对局数据
- **Rainbow DQN Bot**：仅需 ~7,000 局训练（单 GPU ~45 分钟）超越之前最好的启发式 Bot
- 测试了 6 种基线（Big Money → Provincial），建立完整评测体系
- 识别出三个 RL 核心挑战：可变动作集、随机性、动态卡池

---

### [Geometric DL + SAC](03_geometric_deep_learning_sac.md) — 最前沿的学习方法

**Gerigk & Engels (2023, AAAI AIIDE)** 发表。**首个完全不依赖启发式的学习型 Agent**，所有决策（包括 Throne Room 选择、Remodel 目标）均由神经网络决定。

**核心创新**：
- **多重集（Multiset）状态表示**：手牌/牌组天然是多重集，用 Geometric DL 处理
- **SAC 适配可变动作空间**：策略网络只输出当前合法动作的 logits
- **发现人类策略**：Agent 自主发现了 Village + Smithy 引擎组合

---

### [Dominion RL (DQN + 模仿学习)](04_heuristic_baselines.md) — 开源实现

**sdthompson1 (2019)** 的 GitHub 项目。使用 DQN + 经验回放 + 可选 Buy Menu 模仿学习。在简化版（~20 张卡）上验证，是理解 RL → 卡牌游戏的入门级参考。

---

### [Dominiate / Big Money / 遗传算法](04_heuristic_baselines.md) — 经典基线

**Dominiate (rspeer, 2013–14)**：CoffeeScript 实现的优先级/价值规则引擎，是 Dominion 社区最知名的模拟器。其 `BasicAI` 用优先级列表驱动全部决策。同时承载了 **Big Money** 策略（只买钱不买行动牌）作为经典性能基线，以及 **octachrome** 的遗传算法"目标牌组"方案。

---

## 五种方法对比

| 维度 | Principality AI | Rainbow DQN | Geometric SAC | DQN + IL | Dominiate |
|------|:---:|:---:|:---:|:---:|:---:|
| **AI 范式** | LLM (MCP) | 深度 RL | 深度 RL | 深度 RL | 规则引擎 |
| **是否需要训练** | ❌ 零样本 | ✅ ~7,000 局 | ✅ 大量 | ✅ | ❌ 手工规则 |
| **游戏覆盖度** | 25 张 (Base) | 完整 | 完整 | ~20 张 | Base 版本 |
| **动作空间处理** | LLM 自然语言 | 离散 Q 值 | 可变 actor | 离散 Q 值 | 条件分支 |
| **泛化到新卡牌** | ✅ (LLM 理解) | ⚠️ 需重训 | ⚠️ 需重训 | ❌ | ❌ 需手写规则 |
| **开源** | ✅ MIT | ✅ 论文公开 | ❌ 论文公开 | ✅ MIT | ✅ MIT |
| **实际可用性** | ✅ 可跑 | ⚠️ 需复现 | ❌ 无公开代码 | ✅ 可跑 | ✅ 可跑 |
| **对局强度** | 未评测 | ~2/3 胜率 vs Provincial | 超越学习型，不敌搜索型 | Big Money+ 水平 | Big Money 基线 |

---

## 三类方法的本质差异

```
┌─────────────────────────────────────────────────────┐
│                   Dominion AI 方法论                   │
│                                                     │
│  规则引擎（Dominiate）     RL（DQN/SAC）    LLM（Principality） │
│  ┌──────────┐          ┌──────────┐     ┌──────────┐ │
│  │手写优先级│          │神经网络   │     │零样本推理│ │
│  │无法超越  │          │需要训练   │     │需要接口  │ │
│  │设计者    │          │泛化有限   │     │token 成本│ │
│  └──────────┘          └──────────┘     └──────────┘ │
│                                                     │
│        确定性              学习型               理解型  │
└─────────────────────────────────────────────────────┘
```

---

## 核心教训与对六朝的启示

### 五个跨项目共识

1. **动态动作空间是核心挑战**：Dominion 每回合可执行的动作取决于手牌/金币状态。SAC 的可变 actor 设计（仅对合法动作输出概率）是 RL 侧的最优解；LLM 侧通过 MCP 的 `getValidMoves()` 预生成合法动作列表。

2. **状态表示决定了学习效率**：Geometric DL 用多重集（multiset）处理手牌的数学结构——比简单的 one-hot 编码更能捕捉卡牌游戏的组合性质。

3. **LLM 零样本 > RL 训练效率**：LLM 不需要数千局的训练就能理解规则并做出合理决策。但 RL 在精调后的大规模对局强度上仍有优势。

4. **混合架构最有前景**：Vox Deorum（Civ V）的"LLM 战略 + 算法战术"模式尚未在 Dominion 上验证。LLM 负责卡牌组合推理和长线策略，规则引擎或 RL 负责单回合最优执行——这可能是在复杂桌游 AI 中的最优方案。

5. **接口设计 ≥ 模型能力**：Principality AI 证明，设计良好的 MCP 工具接口（三级详细度 + 自动回传状态 + PendingEffect）比模型升级更能提升 LLM 的游戏表现。

### 结构化启示表

| 来源 | 具体设计建议 |
|------|------------|
| Principality MCP | 三级详细度状态查询——不要给 LLM 不需要的信息 |
| Principality 自动回传 | 每次 execute 后自动返回新状态——减少 50% 调用 |
| Principality PendingEffect | 多步交互卡牌用状态机建模——LLM 只做选择不维护状态 |
| Rainbow DQN 基线 | 永远先跑 Big Money 基线——最简单的策略往往出乎意料地强 |
| Geometric SAC | 手牌/牌组用多重集表示，不是序列——无序性很关键 |
| Dominiate 优先级 | 复杂决策可分解为多个优先级列表——LLM prompt 也适用 |
| AgenticSTS (Slay the Spire) | Bounded-memory contract——长程游戏的上下文管理关键 |

---

## 文件索引

| 文件 | 内容 |
|------|------|
| [01_principality_ai_mcp.md](01_principality_ai_mcp.md) | Principality AI 深度解析：MCP 架构、三级详细度、PendingEffect 状态机、LLM 双通道 |
| [02_dominion_rl_benchmark.md](02_dominion_rl_benchmark.md) | Dominion RL Benchmark + Rainbow DQN：2M 数据集、6 种基线、RL 三挑战 |
| [03_geometric_deep_learning_sac.md](03_geometric_deep_learning_sac.md) | Geometric DL + SAC：多重集表示、可变动作空间、首个无启发式学习 Agent |
| [04_heuristic_baselines.md](04_heuristic_baselines.md) | 启发式基线：Dominiate 规则引擎、Big Money、遗传算法、DQN+IL |
| [05_adjacent_works.md](05_adjacent_works.md) | 相邻工作：LLM + Slay the Spire、Temple Gates 官方AI、MCTS方案、Playtrace Clustering |

---

## 参考文献

- **Principality AI**: DeLord, E. "Principality AI: A Dominion inspired card game with MCP support." GitHub, 2025–2026. [github.com/edd426/principality_ai](https://github.com/edd426/principality_ai)
- **Dominion RL Benchmark**: Halawi, D. et al. "Dominion: A New Frontier for AI Research." arXiv, 2024. [arXiv:2405.06846](https://arxiv.org/abs/2405.06846)
- **Geometric DL + SAC**: Gerigk, J. & Engels, B. "Playing Various Strategies in Dominion with Deep Reinforcement Learning." AAAI AIIDE, 2023. [ojs.aaai.org/index.php/AIIDE/article/view/27518](https://ojs.aaai.org/index.php/AIIDE/article/view/27518)
- **Dominion RL (DQN)**: Thompson, S. "dominion-rl: Reinforcement learning for the Dominion card game." GitHub, 2019. [github.com/sdthompson1/dominion-rl](https://github.com/sdthompson1/dominion-rl)
- **Dominiate**: Speer, R. "Dominiate: A Dominion simulator with AI support." GitHub, 2013–2014. [github.com/rspeer/dominiate](https://github.com/rspeer/dominiate)
- **Genetic Algorithm**: Mok, D. "Creating a Dominion AI using Genetic Algorithms." Stanford CS229, 2016.
- **MC/SARSA/DQL**: Yang, E. & Kuo, A. "Playing Dominion with Reinforcement Learning." Stanford CS230, 2019.
- **AgenticSTS**: "AgenticSTS: A Bounded-Memory Testbed for Long-Horizon LLM Agents." arXiv, 2025. (Slay the Spire 2 — 同品类卡牌构筑游戏 LLM 工作)
