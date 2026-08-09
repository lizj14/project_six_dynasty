# 相邻工作：LLM + 同品类游戏 & 非LLM最强AI

> 创建日期: 2026-08-04
> 定位: 补充调研 — 直接相关的 LLM + 卡牌构筑游戏工作，以及 Dominion 领域最强的非 LLM AI

---

## 核心结论

**截至 2026 年 8 月，Principality AI 是唯一让 LLM 作为 Agent 直接操控 Dominion 的开源项目。** arXiv、ACM、IEEE 等学术数据库中没有任何以 "LLM playing Dominion" 为主题的论文。

但这不代表没有相关工作。以下是四个方向上的相邻研究：

---

## 一、LLM + Slay the Spire — 同一品类的 LLM Agent 工作

Slay the Spire（杀戮尖塔）与 Dominion 同属**卡牌构筑（Deck-Building）**品类。核心差异：StS 是单人 PvE roguelike，Dominion 是双人 PvP 竞技。但卡牌选择、资源管理、组合推理的挑战高度相似。

### 1.1 Language-Driven Play（FDG 2024）

> Bateni, B. & Whitehead, J. "Language-Driven Play: Large Language Models as Game-Playing Agents in Slay the Spire." FDG 2024.
> ACM: [doi.org/10.1145/3649921.3650013](https://doi.org/10.1145/3649921.3650013)

**核心思路**：用 LLM 作为通用游戏 Agent，仅凭自然语言卡牌描述理解游戏规则并决策。

**实验设置**：
- 在 **MiniSTS**（简化的 Slay the Spire headless 版本）上测试
- 测试了 GPT-3.5、Llama 2 7B、Mistral 7B 等多个模型
- 不需要针对游戏规则进行专项训练

**关键发现**：

| 发现 | 详情 |
|------|------|
| ✅ LLM 能理解卡牌协同 | 仅凭文字描述（如 "每打出一张技能牌，获得 3 点格挡"）推理配合 |
| ✅ 长线规划能力突出 | LLM Agent 在需要多回合积累的策略上优于短视的基线 |
| ⚠️ 非最优单步决策 | LLM 可能在某个具体回合做出次优选择 |
| ❌ 小型模型表现差 | Llama 2 7B / Mistral 7B 无法可靠理解复杂卡牌交互 |

**对 Dominion 的启示**：LLM 理解卡牌文字 → 零样本适配新王国卡组合，不需要为每种卡重训模型。这与 Dominion RL 需要"每换一组王国卡就重训"形成鲜明对比。

### 1.2 AgenticSTS — 长程游戏的记忆管理（2025）

> "AgenticSTS: A Bounded-Memory Testbed for Long-Horizon LLM Agents." arXiv, 2025.
> HuggingFace: [huggingface.co/papers/2607.02255](https://huggingface.co/papers/2607.02255)

**核心思路**：在 Slay the Spire 2 中研究 LLM Agent 的**记忆管理**问题。StS 一局通常需要数百次决策——如果把所有历史放到 prompt 里，token 消耗很快失控。

**关键设计 — Bounded-Memory Contract**：

```
传统方案（Native Memory）:
  每次决策 → 追加到对话历史 → Prompt 线性增长 → 第 200 回合 prompt 可能是第 1 回合的 200 倍

Bounded-Memory Contract:
  每次决策 → 保存到结构化记忆库
  下次决策 → 从记忆库按类型检索相关条目 → 组装"新鲜"的 prompt
  → Prompt 大小始终有界
```

**实验结果**：

| 配置 | 胜率 (10 局) |
|------|-------------|
| 前沿 LLM（公开基准）| **0%** (0/10) |
| 人类最低难度 | **16%** |
| + 策略技能记忆 | **30%** (3/10) |
| + 触发性策略技能 | **60%** (6/10) |

**对 Dominion 的启示**：
- Dominion 一局 15–40 回合，比 StS 短，但同样面临"早期买牌 → 数十回合后产生效果"的长时域信用分配问题
- Bounded-memory contract 可直接应用于 Dominion LLM Agent——按"手牌变化""供应堆变化""对手行动"等类型建立结构化记忆
- 0% 胜率暴露了 LLM 在需要精确数值计算的长程规划上的根本性弱点

### 1.3 LLM 卡牌协同静态评估（2025）

> Bateni, B. et al. "Rule Synergy Analysis using LLMs: State of the Art and Implications." arXiv, 2025.
> arXiv: [2508.19484](https://arxiv.org/abs/2508.19484)

**核心思路**：不实际玩游戏，让 LLM 直接判断两张卡牌是否有协同效应（synergy）。

**实验规模**：5,625 对卡牌（75 张 × 75 张），每对标记为正面/负面/无协同。

**关键结果**：

| 指标 | GPT-4o 表现 |
|------|------------|
| 总体准确率 | **81%** |
| 无协同 F1 | **0.88** ✅ |
| 正面协同 F1 | **0.65** ⚠️ |
| 负面协同 F1 | **0.16** ❌ |

**典型错误类型**：
- 时序错误（误解效果触发的先后顺序）
- 规则错误（错误应用游戏机制）
- 状态想象错误（假设不存在的理想局面）
- 描述误读（错误理解卡牌文字）
- 相似性混淆（把"放大效果"当成"协同"）

**对 Dominion 的启示**：LLM 可以在**不实际对局的情况下**判断卡牌组合的协同潜力——这对六朝的 AI 卡牌设计评估有直接价值。但负面协同（"这两张卡看起来好，实际一起用很糟"）的 0.16 F1 是硬伤。

---

## 二、Temple Gates Games 官方 App AI — 最强的 Dominion AI（非 LLM）

> 开发者: Keldon Jones / Temple Gates Games | 上线: 2021
> 平台: iOS / Android / Steam
> Polygon 报道: [polygon.com/22440924](https://www.polygon.com/22440924/dominion-app-neural-network-ai-release-date-price)
> GameTek 深度文章: [gametek.substack.com/p/big-brain-small-phone-ai-for-dominion](https://gametek.substack.com/p/big-brain-small-phone-ai-for-dominion)

### 2.1 技术架构

这是**首个商业化的 AlphaZero 风格 Dominion AI**：

```
训练阶段（离线）:
  神经网络 ← 数万局自对弈（self-play）
  └── 嵌入层: 学习卡牌的构成要素（费用/VP/加牌/加行动/加购买）
      而非学习具体卡牌

推理阶段（本地设备）:
  MCTS 搜索树 + 神经网络引导剪枝
  └── 全部在用户手机上运行，不需要云端
```

### 2.2 关键创新：卡牌要素嵌入

不学习"Village 是什么"，而是学习"费用 3 / +1 Card / +2 Actions 的组合是什么"：

```
传统方案: 每张卡 = 一个 one-hot ID → 新卡 = 未知
Temple Gates: 每张卡 = (cost=3, +cards=1, +actions=2, vp=0, ...) → 新卡 = 已理解
```

这意味着 AI 可以**零训练玩从未见过的扩展包卡牌**。开发者在内部测试中证实：用已有扩展训练的 AI，直接打新扩展仍然能赢。

### 2.3 实际表现

| 难度 | 原理 | 玩家评价 |
|------|------|----------|
| Easy | 减少 AI 的记忆精度 | 适合新手 |
| Medium | 部分遗忘游戏状态 | 有挑战 |
| Hard | 完整 MCTS + 神经网络 | 每日挑战胜率 ~80% |
| — | 引擎型王国 | ⚠️ AI 在复杂抽牌引擎上表现下降 |

社区共识：Hard AI 非常强，但经验丰富的玩家在"引擎型"王国（需要精细的 Village/Smithy 类连锁）上能保持 >80% 胜率。

### 2.4 与 LLM 方法的本质差异

| 维度 | Temple Gates AI | LLM Agent (Principality) |
|------|:---:|:---:|
| 训练量 | 数万局自对弈 | 零 |
| 决策方式 | MCTS + 神经网络剪枝 | 自然语言推理 |
| 泛化方式 | 卡牌要素嵌入 | 语言理解 |
| 运行位置 | 用户手机本地 | 云端 API |
| 对战强度 | 极高（接近人类顶级） | 未系统评测 |
| 可解释性 | 低（神经网络黑盒） | 高（可以解释策略推理） |

---

## 三、MCTS 方案 — 被低估的中间路线（2014–2015）

> Jansen, J.V., Tollisen, R., Goodwin, M. & Glimsdal, S. "AIs for Dominion Using Monte-Carlo Tree Search." IEA/AIE 2015.
> Springer: [doi.org/10.1007/978-3-319-19066-2_5](https://doi.org/10.1007/978-3-319-19066-2_5)
> 更早版本: "An AI for Dominion Based on Monte-Carlo Methods" (2014)

### 3.1 核心方法

两种 MCTS 变体：
1. **UCB**（Upper Confidence Bounds）
2. **UCT**（Upper Confidence Bounds applied to Trees）— 带树结构的增强版

### 3.2 结果

- UCT 方案达到 **67% 胜率** vs 已知最佳有限状态机（且对方先手）
- 显著优于当时的文献中的所有方法
- 证明 MCTS 可以有效处理 Dominion 的随机性和隐藏信息

### 3.3 为什么这个方向没有被更多探索

1. 2015 年正是深度学习全面接管 AI 研究的拐点——MCTS 被视为"旧范式"
2. Dominion 社区规模小，缺乏像围棋/国际象棋那样的 MCTS 调优社区
3. Temple Gates 的 AlphaZero 风格（神经网络 + MCTS）实际上是 MCTS 的进化版

### 3.4 对 LLM Agent 的启示

MCTS + LLM 是理论上最有前景的混合架构：

```
LLM 负责: 战略推理（"这局该打钱还是打引擎？"）
MCTS 负责: 战术搜索（"当前手牌打哪张最优？"）

与 Vox Deorum（Civ V 的 LLM 战略 + 算法战术）架构一致
```

---

## 四、Playtrace Clustering — 数据驱动的策略分析（2024）

> Owen, A. "Identifying Strategies in Dominion Using Playtrace Clustering." IEEE Transactions on Games, 2025 (online Dec 2024).
> IEEE: [doi.org/10.1109/TG.2024.3524707](https://doi.org/10.1109/TG.2024.3524707)

### 4.1 核心方法

从**人类玩家和多种 AI Agent** 的对局日志中提取两类特征：

1. **卡牌数量时间序列**：每回合牌组中每种卡牌的数量变化
2. **N-Gram 动作序列**：连续的玩家动作模式

用 K-Means / K-Medoids / DBSCAN 聚类 → 自动发现策略类型和卡牌协同。

### 4.2 关键贡献

- **Restricted Play Framework**：限制 AI 的可用卡牌 → 强制探索更多样化的策略空间
- **N-Gram 方法是游戏无关的**——可以直接应用于六朝或任何其他卡牌/桌游
- 聚类结果清晰区分了"金钱流""引擎流""攻击流"等不同策略流派

### 4.3 对 LLM Agent 的启示

这是一个**互补方向**——Playtrace Clustering 负责"分析已有的 AI 策略是什么"，LLM Agent 负责"创造新策略"。两者结合可以形成"分析 → 理解 → 生成 → 验证"的闭环。

---

## 五、LLM 作为非正式策略顾问

在 Steam 社区和 Dominion Strategy Forum 上，有一些玩家报告了**非正式的 LLM 使用**：

> "我把这局的王国卡列表和当前手牌发给 ChatGPT，它能给出相当合理的策略建议。"
> — Steam 社区用户, 2024

这不算"LLM Agent 玩游戏"，但揭示了一个中间路径：

```
LLM 策略顾问模式:
  Human 负责: 操作游戏界面
  LLM 负责: 每回合分析 + 建议最优动作
  → 不需要 MCP/API 集成，纯对话即可
```

这种模式的实际效果取决于 LLM 对 Dominion 规则的理解深度。GPT-4/Claude 级别的模型通常能正确理解基础版规则，但在复杂扩展交互上会出错。

---

## 六、总结：LLM + Dominion 的工作全景

```
                        LLM 直接玩游戏
                             │
              ┌──────────────┼──────────────┐
              │              │              │
         Principality   非正式使用      不存在其他
         AI (MCP)      (策略顾问)      开源/学术项目
              │
    ┌─────────┼─────────┐
    │         │         │
  MCP路径   API路径   (唯一)
(Claude    (SDK
  Code)    调用)

═══════════════════════════════════════════════

              相邻品类 (LLM + 卡牌构筑)
                    │
    ┌───────────────┼───────────────┐
    │               │               │
Language-Driven  AgenticSTS    Rule Synergy
Play (StS)       (StS 2)       Analysis
FDG 2024         2025          2025
    │               │               │
LLM能理解卡牌    Bounded-       LLM静态评估
协同+长线规划    Memory Contract 卡牌协同(81%)

═══════════════════════════════════════════════

              非LLM的Dominion最强AI
                    │
    ┌───────────────┼───────────────┐
    │               │               │
Temple Gates     MCTS (2015)    Playtrace
(AlphaZero风格)  UCT 67%胜率    Clustering
商业化最强       学术方案        IEEE 2024
```

### 关键空白

| 空白 | 描述 | 机会 |
|------|------|------|
| **LLM 自对弈** | 没有任何工作让 LLM 通过自对弈改进 Dominion 策略 | 高 |
| **MCTS + LLM 混合** | Vox Deorum 的"LLM 战略 + 搜索战术"未在 Dominion 上验证 | 最高 |
| **LLM 策略评估** | LLM 是否能判断"这局该打钱还是打引擎"？未系统评测 | 中 |
| **多 LLM Agent** | 2+ LLM 互相对战的 emergent behavior 研究 | 中 |
| **Bounded-Memory** | AgenticSTS 的记忆管理未在 Dominion 上验证 | 高 |

---

## 七、对六朝的启示

1. **Principality AI 的独占地位 = 方法论空白**：没有现成的 "LLM + 竞技卡牌构筑" 最佳实践可借鉴。六朝的 LLM Agent 设计需要大量原创工作。

2. **Slay the Spire 的工作高度可迁移**：两个游戏都是"从随机卡池中选择卡牌加入牌组"的构筑游戏。Language-Driven Play 的发现（LLM 理解卡牌协同、长线规划好、单步可能非最优）可直接指导六朝 LLM Agent 的设计。

3. **Bounded-Memory Contract 是必需品**：六朝一局可能更长，AgenticSTS 的记忆管理方案值得直接移植。

4. **卡牌要素嵌入 = 泛化关键**：Temple Gates AI 的"学习卡牌要素而非具体卡牌"可以直接映射到六朝——如果六朝卡牌也用要素向量（费用/效果/类型）表示，LLM 可以零样本理解新卡牌。

5. **MCTS + LLM 混合是最有前景的下一步**：用 LLM 做战略决策（"这局打快攻还是控制"），MCTS 做战术搜索（"当前手牌最优打出顺序"）。这是目前完全没有被探索的方向。
