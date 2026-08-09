# CivRealm 深度解析

> 论文: "CivRealm: A Learning and Reasoning Odyssey in Civilization for Decision-Making Agents"
> 作者: Siyuan Qi, Shuo Chen, Yexin Li, Xiangyu Kong, Junqi Wang, Bangcheng Yang, Pring Wong, Yifan Zhong, Xiaoyuan Zhang, Zhaowei Zhang, Nian Liu, Wei Wang, Yaodong Yang, Song-Chun Zhu
> 机构: BIGAI（北京通用人工智能研究院）× 北京大学
> 发表: ICLR 2024 **Spotlight** (Vienna, May 2024)
> 论文: [arXiv:2401.10568](https://arxiv.org/abs/2401.10568) | PDF 已下载
> 目标游戏: Freeciv（文明系列开源复刻版）

---

## 一、项目概述

CivRealm 是首个同时为**强化学习（RL）**和**大语言模型（LLM）**两种范式设计统一接口的文明游戏基准。其核心主张：

> "当前的 AI 基准要么只需要从经验中学习（Atari、StarCraft II），要么只需要从上下文中推理（语言测试）——但真正的智能需要两者兼备。文明类游戏同时需要这两种能力。"

论文发表于 ICLR 2024 Spotlight 环节，在 AI 游戏 Agent 领域有重要影响。

### 为什么选 Freeciv？

- 开源，可完全控制游戏逻辑
- 回合制——适合 LLM 推理时间需求
- 支持随机地图、可变玩家数、可修改规则——天然适合**泛化测试**
- 拥有完整的 4X 要素（探索、扩张、开发、征服）

---

## 二、环境设计

### 2.1 三层架构

```
┌─────────────────────────────┐
│         Agent(s)            │  ← 各种 Agent 架构可即插即用
├─────────────────────────────┤
│           Proxy             │  ← 分发游戏状态，收集动作
├─────────────────────────────┤
│     Freeciv Game Server     │  ← 实际游戏逻辑执行
└─────────────────────────────┘
```

**Proxy 层**的关键作用：将游戏状态转换为 Agent 可处理的格式，将 Agent 的动作转换回游戏指令。这允许 RL 和 LLM Agent 共享同一环境。

### 2.2 双 API 设计

| API 类型 | 适用 Agent | 数据格式 | 动作空间 |
|----------|-----------|---------|---------|
| **Tensor API** | RL Agent | 固定维度张量 | 离散动作 ID |
| **Language API** | LLM Agent | 自然语言描述 | 自然语言指令 |

### 2.3 小游戏（Mini-Games）

CivRealm 设计了 **10 类小游戏 × 10,000 实例**，分为三大类：

| 类别 | 小游戏 | 测试能力 |
|------|--------|---------|
| **发展** | CityTile, CityTileWonder, CityTileSettler, CityBuilding | 城市管理、建造优先级 |
| **战斗** | BattleBase, BattleMixed | 军事单位控制、战术 |
| **外交** | DiplomacyAlliance, DiplomacyWar | 外交关系管理 |

**设计目的**：提供密集学习信号（完整游戏只有稀疏的终局胜负）、隔离测试特定能力维度、降低研究门槛。

### 2.4 完整游戏特征

- 不完美信息（战争迷雾）
- 一般和（general-sum）多智能体动态
- 可变玩家数量
- 随机事件
- 技术进步带来的状态/动作空间爆炸
- **后期每回合约 10^166 种可能行动**——远超围棋

---

## 三、Agent 架构

### 3.1 Tensor RL Agent

受 **AlphaStar** 启发的 PPO（Proximal Policy Optimization）：
- 使用 Tensor API
- 通过自对弈训练
- 在多个小游戏上分别训练

### 3.2 BaseLang（LLM Agent — 扁平架构）

**设计理念**：每个单位分配一个独立的 LLM，采用 **AutoGPT 风格**的三阶段推理。

```
每个单位的 LLM Agent:
  Observation (5×5 tile 局部视野)
       ↓
  Thought → Reasoning → Command
       ↓
  Action: move / attack / ...
```

**关键特征**：
- **5×5 局部视野**：每个单位只能看到周围 25 个地块
- **三阶段推理**：Thought（观察）→ Reasoning（推理）→ Command（决策）
- **向量数据库**：存储历史记录和游戏手册，Agent 可检索
- **独立上下文**：每个单位的 LLM 有独立历史，但**缺乏跨单位协调**

### 3.3 Mastaba（LLM Agent — 层级架构）

**设计理念**：古埃及 Mastaba（马斯塔巴墓）金字塔——上层俯瞰全局，下层执行具体任务。

```
┌──────────────────────────────────────┐
│           Advisor (顶层 LLM)          │
│  全国视角：单位数、城市指标、敌情     │
│  生成高层建议，分发至工人            │
├──────────┬──────────┬────────────────┤
│ Worker 1 │ Worker 2 │ ... Worker N   │
│ 单位 A   │ 单位 B   │                │
└──────────┴──────────┴────────────────┘
```

**关键创新**：

1. **金字塔地图视图**：将 15×15 压缩为 **9 个区块**（每个 5×5）——在信息量和 prompt 大小间取得平衡

2. **两层 LLM**：
   - **Advisor（顾问）**：俯瞰全国——各单位数、各城市产出、敌对方信息
   - **Workers（工人）**：类似 BaseLang 的逐单位 Agent，但接收 Advisor 的战略指导

3. **决策流程**：
   - Advisor 每回合评估国家状况
   - 生成高层战略建议（"防守北部边境""优先发展科技"）
   - 传达给各 Worker
   - Worker 在 Advisor 指导下独立选择各实体行动

4. **向量数据库**：Worker 可查询游戏手册和历史经验

---

## 四、实验结果

### 4.1 小游戏结果

| Agent 类型 | CityTileWonder | BattleBase | DiplomacyAlliance |
|-----------|---------------|------------|-------------------|
| **RL Agent (PPO)** | ~90% 成功率 | 中等 | 中等 |
| **BaseLang (LLM)** | 有限成功 | 有限成功 | 有限成功 |
| **Mastaba (LLM)** | 优于 BaseLang | 优于 BaseLang | 优于 BaseLang |

**关键发现**：RL 在小游戏中表现更好，但层级 LLM（Mastaba）始终优于扁平 LLM（BaseLang）。

### 4.2 完整游戏结果

| Agent 类型 | 完整游戏 |
|-----------|---------|
| **RL Agent (PPO)** | ❌ 无法取得实质性进展 |
| **BaseLang (LLM)** | ❌ 无法取得实质性进展 |
| **Mastaba (LLM)** | ⚠️ 略优于 BaseLang，但仍无法取得实质性进展 |

**完整游戏对所有 Agent 类型仍是一个未解决的重大挑战。**

### 4.3 失败模式

**RL Agent**：
- **短视策略**：倾向于单位刷屏而非长期城市扩张
- 小游戏中学到的技能无法迁移到完整游戏
- 完整游戏的状态/动作空间远超训练分布

**LLM Agent**：
- **接地困难**：尽管拥有大量人类知识，但无法有效平衡军事、经济、外交优先级
- BaseLang 中各 Agent 各自为战，缺乏协调
- Mastaba 虽然更好，但 Advisor 建议仍不够具体以指导实际执行

---

## 五、与 Civ6-MCP 的对比

| 维度 | CivRealm | Civ6-MCP |
|------|----------|----------|
| **游戏** | Freeciv（开源） | Civilization VI（商业） |
| **范式** | RL + LLM 双范式 | 纯 LLM（MCP 工具） |
| **Agent 架构** | BaseLang + Mastaba | 单 Agent + 76 MCP 工具 |
| **完整对局** | 未报告大规模数据 | 12 场详细记录 |
| **AI 表现** | 无法取得进展 | 1/12 胜，但显著进步 |
| **核心贡献** | 环境设计 + 层级架构验证 | 经验性发现 + 评测基础设施 |
| **可观测性** | 未强调 | 日记 + 工具日志 + 空间追踪 |
| **发表** | ICLR 2024 Spotlight | 开源项目（未正式发表） |

---

## 六、贡献与局限

### 关键贡献

1. **首个同时支持 RL 和 LLM 的文明基准**——为两种范式设计统一接口
2. **层级架构必要性验证**——Mastaba 显著优于 BaseLang
3. **小游戏+完整游戏的课程设计**——从易到难的渐进路径
4. **泛化测试能力**——随机地图生成允许测试未见场景

### 局限

- LLM 接地能力弱——推荐更好的 prompt 工程、结构化输出
- RL 短视——推荐更好的信用分配、层级 RL
- 小游戏技能不迁移——推荐课程学习
- Mastaba 协调仍不足——推荐更细粒度的 Advisor 输出
- 完整游戏太难以至于无法评估 Agent 质量

---

## 七、对六朝的启示

| 启示 | 具体建议 |
|------|---------|
| **层级架构是必需的** | 扁平 Agent 在大规模策略游戏中必然失败 |
| **Advisor 质量决定一切** | 顶层 Advisor 的信息视图和 prompt 设计是最关键的投资 |
| **先小后大** | 六朝 AI 应先在简化的子场景验证，再进入完整游戏 |
| **双接口设计** | 考虑同时支持 RL（高效训练）+ LLM（灵活推理） |
| **泛化测试** | 在随机生成的局面/对手上测试，而非固定测试集 |
| **金字塔视野** | Mastaba 的 9 区块压缩值得借鉴——信息太多 LLM 处理不过来，太少则决策错误 |
