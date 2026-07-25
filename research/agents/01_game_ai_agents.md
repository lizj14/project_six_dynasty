# 方向一：游戏 AI Agent — 代表性工作

> 调研日期: 2026-07-21
> 聚焦：基于强化学习 / 搜索的经典游戏 AI Agent，涵盖完美信息博弈到不完美信息博弈的里程碑系统

---

## 概述

游戏 AI Agent 是人工智能研究的经典试验场。从国际象棋到围棋、从即时战略到扑克，游戏为 AI 提供了可控的复杂决策环境。本节收录 **7 个里程碑工作**，按时间线展示从"领域专用"到"通用算法"的演进趋势。

### 核心技术演化脉络

```
规则驱动 (Deep Blue)
    → SL + RL + MCTS (AlphaGo)
        → 纯自对弈 RL (AlphaZero)
            → 无规则模型学习 (MuZero)
                → 大规模分布式 RL (OpenAI Five)
                    → CFR + 抽象 (Pluribus)
                        → 演化博弈论 (DeepNash)
```

---

## 1. AlphaGo

| 维度 | 详情 |
|------|------|
| **发表时间** | 2016 年 1 月 (Nature) |
| **机构** | DeepMind |
| **作者** | David Silver, Aja Huang, Chris J. Maddison 等 |
| **目标游戏** | 围棋 (Go) — 完美信息棋盘游戏，博弈树复杂度 ~10^360 |
| **核心方法** | 监督学习 (SL) + 强化学习 (RL) + 蒙特卡洛树搜索 (MCTS) |

### 技术架构

- **策略网络 (Policy Network)**：在 3000 万人类对局棋谱上做监督学习预训练，再通过自对弈 RL 精调
- **价值网络 (Value Network)**：评估当前局面的胜率
- **MCTS**：用策略网络引导搜索宽度，价值网络评估叶子节点，替代随机 rollout
- **训练资源**：48 个 TPU，分布式训练

### 关键成果

- 5:0 击败欧洲围棋冠军樊麾
- 4:1 击败 18 次世界冠军李世石（2016 年 3 月）
- 首次在无让子的全尺寸围棋上击败顶尖职业棋手
- **影响力**：全球范围内引发 AI 讨论，被《自然》评为年度十大人物

### 局限与代价

- 依赖人类专家数据进行 SL 预训练
- 围棋专用（大量领域知识嵌入，如对称性增强）
- 计算资源庞大

### 意义

首次证明深度神经网络 + MCTS 可以在围棋这一长期被认为"直觉主导"的领域超越人类。确立了 **SL → RL → MCTS** 的三阶段范式的有效性。

---

## 2. AlphaZero

| 维度 | 详情 |
|------|------|
| **发表时间** | 2018 年 12 月 (Science) |
| **机构** | DeepMind |
| **作者** | David Silver, Thomas Hubert, Julian Schrittwieser 等 |
| **目标游戏** | 围棋、国际象棋、将棋 — 三种不同规则的完美信息棋盘游戏 |

### 核心创新：通用算法

- **从零开始 (tabula rasa)**：不依赖任何人类对局数据，纯自对弈 RL
- **统一网络**：单一神经网络同时输出策略 (policy) 和价值 (value)，共享特征提取层
- **相同超参数**：三种游戏使用完全相同的架构和超参数，仅输入游戏规则
- **无 rollout**：仅用神经网络评估，不做 MCTS rollout 模拟
- **训练效率**：4 个 TPU 训练，36 小时超越 AlphaGo Lee

### 关键成果

| 游戏 | 训练时间 | 击败的基准 |
|------|----------|-----------|
| 围棋 | 36h | AlphaGo Lee (100:0) |
| 国际象棋 | 4h | Stockfish (2016 TCEC 冠军) |
| 将棋 | 2h | Elmo (2017 CSA 世界冠军) |

### 意义

证明了"**通用算法 > 领域知识**"——单一算法通过纯自对弈可在多个完全不同的棋盘游戏上达到超人水平。这是对"通用人工智能 (AGI)"范式的一次重要验证。

---

## 3. MuZero

| 维度 | 详情 |
|------|------|
| **发表时间** | 2020 年 12 月 (Nature) |
| **机构** | DeepMind |
| **作者** | Julian Schrittwieser, Ioannis Antonoglou, Thomas Hubert 等 |

### 核心创新：无需游戏规则

MuZero 的最大突破是 **不需要游戏模拟器**。它学习一个隐式的环境模型：

| 网络 | 功能 |
|------|------|
| **Representation** | 将原始观测 (棋盘/屏幕像素) 映射到隐藏状态 |
| **Dynamics** | 在隐藏空间中预测下一状态 + 即时奖励 |
| **Prediction** | 从隐藏状态输出策略 + 价值 |

MCTS 完全在 **学习的隐藏空间** 中执行，而非真实模拟器。

### 关键成果

- 在围棋、国际象棋、将棋上匹配或略微超过 AlphaZero
- 同时在 **57 个 Atari 游戏** 上达到 SOTA（其中许多超过人类水平）
- 已应用于 **YouTube 视频压缩**
- **代价**：计算资源极大（训练需 16 TPU，自对弈需 1000 TPU）

### 意义

这是向"现实世界 AI"的关键一步——现实世界中我们没有完美的模拟器。MuZero 证明 AI 可以在不知道环境规则的情况下，通过学习隐式世界模型进行规划。

---

## 4. OpenAI Five

| 维度 | 详情 |
|------|------|
| **发表时间** | 2019 年 |
| **机构** | OpenAI |
| **目标游戏** | Dota 2 — MOBA 类实时策略，不完美信息，5v5 团队对战 |

### 核心方法：大规模分布式深度 RL

- **算法**：Proximal Policy Optimization (PPO) — 无模型的策略梯度方法
- **无树搜索**：实时游戏（每秒 30 帧决策）不允许 MCTS
- **自对弈 (Self-play)**：80% 纯自对弈 + 20% 历史策略池采样 (Population-based)
- **统一模型**：单一神经网络控制全部 5 个英雄
- **训练规模**：256 GPU + 128,000 CPU 核，每天模拟 ~180 年的游戏时间

### 关键成果

- 击败 Dota 2 世界冠军战队 OG（在简化版比赛中，17 个英雄限制）
- 在公开匹配中击败 99.4% 的玩家
- **首个在电子竞技项目中击败世界冠军的 AI**

### 局限

- 受限于简化版规则（禁止幻象/召唤物、限制英雄池）
- 反应时间远超人类（帧级精确执行）
- 需要海量计算资源
- 奖励设计高度依赖领域知识

### 意义

证明无模型的大规模分布式 RL 可以处理复杂的实时团队博弈，为多 Agent 协作奠定基础。

---

## 5. Pluribus

| 维度 | 详情 |
|------|------|
| **发表时间** | 2019 年 7 月 (Science) |
| **机构** | Facebook AI Research / CMU |
| **作者** | Noam Brown, Tuomas Sandholm |
| **目标游戏** | 六人无限注德州扑克 — 不完美信息，~10^164 博弈状态 |

### 核心方法：反事实遗憾最小化 (CFR)

- **MCCFR (Monte Carlo CFR)**：用采样代替全遍历，使 CFR 在大规模博弈中可行
- **蓝图策略 (Blueprint)**：通过抽象 (abstraction) 离线计算一个"浓缩"策略
- **在线深度受限搜索**：在对局中实时搜索，仅维持 **4 个策略** 的简化池用于对手建模
- **关键特性**：不使用深度神经网络！核心是经典 CFR/表格方法

### 关键成果

- 在六人扑克中击败 5 名职业选手
- 训练成本仅约 **$150 的计算资源**（相比之下，MuZero 需数千 TPU）
- 方法论与深度学习 AGI 完全不同的路线

### 局限

- 方法对更大规模博弈的扩展性有限（CFR 迭代成本 + 表格记忆限制）

### 意义

证明 **不完美信息博弈** 可以用计算效率极高的经典算法解决。与 AlphaZero 等形成方法论上的对比：并非所有游戏 AI 都需要深度神经网络。

---

## 6. AlphaStar

| 维度 | 详情 |
|------|------|
| **发表时间** | 2019 年 10 月 (Nature) |
| **机构** | DeepMind |
| **作者** | Oriol Vinyals, Igor Babuschkin, Wojciech M. Czarnecki 等 |
| **目标游戏** | 星际争霸 II (StarCraft II) — RTS，不完美信息，~10^1685 状态空间 |

### 核心方法

- **多 Agent 训练**：多个 Agent 互相对战形成"联赛"(league)，确保策略多样性
- **PFSP (Prioritized Fictitious Self-Play)**：优先虚拟自对弈，避免策略坍缩
- **Transformer + LSTM + Pointer Network**：混合架构处理不同类型的输出（单位选择、动作类型、目标位置）
- **模仿学习 → RL**：先用人类回放数据做监督学习初始化，再通过 RL 精调
- **API 级接口**：直接通过游戏 API 获取结构化状态，非像素级感知

### 关键成果

- 在战网 (Battle.net) 达到 **Grandmaster 级别**
- 在所有三个种族上都达到 GM 级别
- 展示了多 Agent 联赛训练的威力

### 局限

- 依赖结构化 API（非通用像素输入）
- APM (每分钟操作数) 限制放宽后行为异于人类
- 训练数据包含大量人类回放

### 意义

在状态/动作空间最大的游戏中达到人类顶级水平。多 Agent 联赛训练方法影响了后续许多工作。

---

## 7. DeepNash

| 维度 | 详情 |
|------|------|
| **发表时间** | 2022 年 7 月 |
| **机构** | DeepMind |
| **目标游戏** | Stratego (军棋) — 不完美信息，~10^535 博弈状态，需记忆、推理和虚张声势 |

### 核心方法：R-NaD (Regularized Nash Dynamics)

- **放弃树搜索**：博弈状态空间过大 + 不完美信息使 MCTS 不可行
- **演化博弈论方法**：R-NaD 将博弈论中的复制动力学 (Replicator Dynamics) 扩展到神经网络
- **四头神经网络**：价值、部署、棋子选择、棋子移动
- **纯模型驱动**：无树搜索、无专家数据、无模拟器模型

### 关键成果

- 在 Gravon Stratego 平台上达到 **全球第三名**（所有人类职业选手中）
- 几乎对所有现有 Stratego Bot 保持全胜
- 证明在不完美信息极大状态空间中，"无搜索"方法是一个可行方案

### 意义

DeepNash 是一类完全不同的问题的解决方案——当树搜索因状态空间过大而不可行时，博弈论 + 深度学习的组合提供了替代路径。

---

## 核心对比

| 系统 | 年份 | 信息类型 | 树搜索? | 专家数据? | 核心方法 | 关键突破 |
|------|------|----------|---------|-----------|----------|----------|
| AlphaGo | 2016 | 完美 | MCTS | 是 (SL) | SL+RL+MCTS | 首个超人围棋 AI |
| AlphaZero | 2018 | 完美 | MCTS | 否 | 纯自对弈 RL | 通用单一算法 |
| MuZero | 2020 | 完美 | MCTS (隐空间) | 否 | 模型学习+MCTS | 不需游戏规则 |
| OpenAI Five | 2019 | 不完美 | 否 | 否 | PPO+自对弈 | 首个电竞世界冠军 |
| Pluribus | 2019 | 不完美 | CFR 搜索 | 否 | CFR+抽象 | $150 计算成本 |
| AlphaStar | 2019 | 不完美 | 否 | 是 (回放) | 联赛训练 | RTS 最高水平 |
| DeepNash | 2022 | 不完美 | 否 | 否 | R-NaD | 无搜索达世界前三 |

---

## 与六朝项目的关联

六朝 (Six Dynasties) 属于**回合制策略棋盘游戏**，具有以下特征：

- **不完美信息**（卡牌手牌、对手意图未知）
- **策略深度**（多维度博弈：军事、文化、经济）
- **多 Agent**（2-4 名玩家）
- **长决策周期**（每回合多个阶段决策）

最相关的方法论参考：

1. **AlphaZero 的自对弈训练** — 可用于生成高质量对局数据训练 AI
2. **Pluribus 的 CFR+抽象** — 不完美信息博弈的经典方法，适合卡牌游戏的蓝图策略计算
3. **MuZero 的隐式环境模型** — 当六朝规则复杂时，学习环境模型可能比手工建模更高效
4. **DeepNash 的无搜索方法** — 六朝的状态空间很可能也超出树搜索能力范围

---

## 参考文献

- Silver, D. et al. (2016). Mastering the game of Go with deep neural networks and tree search. *Nature*, 529, 484–489.
- Silver, D. et al. (2018). A general reinforcement learning algorithm that masters chess, shogi, and Go through self-play. *Science*, 362(6419), 1140–1144.
- Schrittwieser, J. et al. (2020). Mastering Atari, Go, chess and shogi by planning with a learned model. *Nature*, 588, 604–609.
- Berner, C. et al. (2019). Dota 2 with Large Scale Deep Reinforcement Learning. *arXiv:1912.06680*.
- Brown, N. & Sandholm, T. (2019). Superhuman AI for multiplayer poker. *Science*, 365(6456), 885–890.
- Vinyals, O. et al. (2019). Grandmaster level in StarCraft II using multi-agent reinforcement learning. *Nature*, 575, 350–354.
- DeepMind. (2022). DeepNash learns to play Stratego at an expert level. *DeepMind Blog*.
- Li, H. et al. (2025). A concise review of intelligent game agent. *ScienceDirect*, 52, 100894.
