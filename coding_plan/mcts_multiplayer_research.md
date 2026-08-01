# 多人 MCTS 研究汇总：从麻将到六朝

> 创建: 2026-07-30 | 基于本次会话中关于 IS-MCTS 的讨论整理

---

## 一、IS-MCTS 基础

### 1.1 为什么需要 IS-MCTS

标准 MCTS 假设完全信息（棋盘上所有棋子都可见）。但六朝、麻将等卡牌游戏存在大量隐藏信息：

| 隐藏信息来源 | 六朝 | 麻将 |
|------------|------|------|
| 对手手牌 | ✓ | ✓ |
| 牌库顺序 | ✓ | ✓（墙牌） |
| 秘密目标 | ✓ | — |
| 对手未来策略 | ✓ | ✓ |

标准 MCTS 强行应用于不完全信息游戏会产生**策略融合（Strategy Fusion）**问题：

```
假设: 你是东晋玩家，手上有一张僭越牌

世界A: 北方有反制牌 → 最优: 不僭越
世界B: 北方无反制牌 → 最优: 发动僭越

标准 MCTS (PIMC):
  对世界A和B分别搜索，然后对两个世界的结果取平均
  → "半吊子"策略: 两个字世界的最优策略平均后是最差策略
  
IS-MCTS:
  搜索"信息集"的树而非"状态"的树
  信息集 = {世界A, 世界B} ← 所有可能性的集合
  统计量在信息集层面汇总而非具体世界层面
```

### 1.2 三种 IS-MCTS 变体

| 变体 | 全称 | 做法 | 优缺点 |
|------|------|------|--------|
| **SO-ISMCTS** | Single Observer | 单棵树，所有玩家共享信息集节点 | 最快，但对手模型中存在信息泄漏 |
| **MO-ISMCTS** | Multiple Observer | 每个玩家一棵独立的树 | 消除策略融合，但内存×玩家数，搜索变浅 |
| **RIS-MCTS** | Root Information Sampling | 每个节点重新 determinize | 消除信息泄漏，但理论上可能回传不可能结果 |

**实践结论**（Goodman et al., 2023 — 11款多人游戏测试）：SO-ISMCTS 在大多数游戏中足够好，MO-ISMCTS 仅在同时行动游戏中显著优势。

### 1.3 原始论文

- Cowling, Powley, Whitehouse (2012). *Information Set Monte Carlo Tree Search*. IEEE Transactions on Computational Intelligence and AI in Games.
- 链接: https://ieeexplore.ieee.org/document/6203567
- 包含 SO-ISMCTS、MO-ISMCTS 的完整伪代码，**免费**

---

## 二、多人 MCTS 实践案例

### 2.1 Goodman et al. — 10 款多人桌面游戏系统研究 (FDG 2023) ⭐

**论文**: *Following the Leader in Multiplayer Tabletop Games*

**作者**: James Goodman, Diego Perez-Liébana, Simon Lucas (Queen Mary University of London)

**发表**: FDG 2023, Lisbon, 11页 | **框架**: TAG (Tabletop Games AI) | **链接**: https://dl.acm.org/doi/10.1145/3582437.3582449

#### 研究动机

两人零和游戏中 MCTS 的目标很明确——最大化胜率。但三人以上的多人游戏中，"胜率"不再是唯一自然的优化目标。玩家应该追求最高分数？排名第一？还是关注与领先者的差距？论文在 **10 款不同类型的多人桌面游戏**上系统测试了不同的**游戏无关启发式（game-agnostic heuristic）**对 IS-MCTS 决策质量的影响。

#### 测试的 10 款游戏

| 游戏 | 类型 | 特征 |
|------|------|------|
| **Colt Express** (2014) | 编程+抢劫 | 部分可观察行动序列，抢劫对手 |
| **Dots and Boxes** (1889) | 抽象棋 | 7×5 网格，唯一完全信息游戏 |
| **Diamant** (2005) | 同时行动/下注 | 每步二选一（Stay/Leave），分支因子极小 |
| **Dominion** (2008) | DBG | 10/25 牌型，需先构建引擎再拿 VP |
| **Exploding Kittens** (2015) | 淘汰制 | 抽到爆炸猫出局，最后幸存者胜 |
| **Love Letter** (2012) | 角色推理 | 5 回合制，直接攻击淘汰对手 |
| **Poker** (Texas Hold'em) | 赌博 | 筹码为分数，零和 |
| **Sushi Go!** (2013) | 同时行动/凑套 | 轮抽制，终局一次性计分 |
| **Uno** (1971) | 手牌管理 | 打光手牌，对手剩余牌计分 |
| **Virus** (2015) | 器官构筑 | 4 个健康器官为胜，可用病毒攻击对手 |

#### 五种目标启发式

MCTS 的 rollout 结束后需要对终局状态打分，这个打分函数就是 Agent 的"优化目标"。论文比较了五种：

| 启发式 | 公式 | 说明 |
|--------|------|------|
| **Win** | +1 赢 / -1 输 / 0 其他 | 传统二元胜率 |
| **Score** | 原始游戏分数 | 纯粹的"自顾自" |
| **Score+** | Score，若终局获胜则 ×150%，若终局失败则 ×50% | **游戏过程自顾自 + 末期切换到击败对手** |
| **Leader** | 玩家分数 − 当前最高分对手的分数，若终局再 ×150% | **全程追踪与领先者的相对差距** |
| **Default** | 各游戏 TAG 实现的手工启发式 | 复杂度不一，基本是 Win + 小量分数 |

**Leader vs Score+ 的核心区别**：
- Score+ 在游戏过程中完全忽略对手，仅在 rollout 触及的终局才关心赢没赢
- Leader 在游戏的每一步都计算"我和第一名差多少"，这会激励阻止对手得分，即使对自己当前分数没有直接增益

#### 实验设置

- **算法**：IS-MCTS（open-loop 信息集），K=1，分数自动缩放到 [0, +1]
- **同时行动游戏**（Diamant, Sushi Go!）：Sequential UCT + IS-MCTS
- **Rollout 调优**：NTBEA 算法，500 局/run，在 {0,1,3,7,10,20,30,50,100,200,300} 中搜索最优长度，对每个 heuristic × player count (2,4) × budget (40ms,200ms) 组合独立调优
- **最终测试**：每种 heuristic 在所有 player count (2,3,4,5) × budget (40ms,200ms,1000ms) 组合上跑 round robin 锦标赛，按 rank（非原始胜率）比较（以均衡不同游戏/人数的胜率基准差异）

#### 五个核心实验结论

**结论 1：Score >> Win，Score+/Leader >> Score**

| 启发式 | 平均 Win Rank (1=最优) | p-value vs Leader |
|--------|----------------------|-------------------|
| Win | 3.9 | <0.0001 |
| Score | 3.1 | <0.0001 |
| Default | 3.2 | <0.0001 |
| Score+ | 2.6 | 0.039 |
| **Leader** | **2.2** | — |

Win 即使**滚到终局**也表现不佳（mean rank 仅 3.5），因为一旦局势已不可赢就失去信号、开始随机行动。Score 提供了更丰富、更早的信号。但**把 Score 和 Winning 结合的启发式（Leader/Score+）** 在 8/10 游戏中表现最优。

**结论 2：游戏分为两个群体**

Leader 优于 Score+ 的游戏（6 款）：**Colt Express, Dots and Boxes, Diamant, Uno, Love Letter, Virus**
— 共同特征：存在**对抗性反击行动**（抢劫、射击、迫使抽牌、攻击器官、设置陷阱）

Score+ 优于 Leader 的游戏（3 款）：**Dominion, Poker, Sushi Go!**
— 共同特征：更像"多人单人游戏"，玩家间直接对抗行动少

无显著差异（1 款）：**Exploding Kittens**（随机性太高，哪种启发式都差不多）

**结论 3：Rollout 长度取决于游戏类型**

| 最佳 Rollout | 游戏 | 原因 |
|-------------|------|------|
| **0** | Dots and Boxes | 对抗性反击 → 短 rollout 有效 |
| 7-10 | Uno, Virus | 同上 |
| **100-300（≈终局）** | Sushi Go, Colt Express, Dominion | 终局 VP 占比大 / 需长期规划 / 前期 VP 有欺骗性 |
| **无所谓**（熵 ~2.3-2.4） | Diamant, Expl. Kittens, Love Letter, Poker | 调优返回均匀分布 |

**关键发现**：Dominion 是滚到终局才有效的典型案例——因为前期 VP 是"欺骗性"的（好玩家故意避免前期拿 VP）。

**结论 4：玩家数量和计算预算影响不大**

- 2P vs 3P vs 4P：仅弱证据表明 2P 更偏对抗性（Leader 略好），p-values 大多不显著
- 40ms vs 1000ms（25× 范围）：Leader 始终最优，Win 随预算增加略改善（p=0.01）

**结论 5：存在两个特殊游戏**

- **Diamant**：唯一 Win 最优的游戏。原因是分支因子极小（每步仅 Stay/Leave 二选一），树天然搜索很深，rollout 经常滚到终局，Win 信号充足
- **Dominion**：唯一 Score 最优的游戏——甚至优于 Score+。因为在 Dominion 中**试图赢反而降低胜率**：Leader 的"保持领先"与 DBG 的"先投资后收割"哲学冲突

#### 三个深度案例分析

##### Dots and Boxes：Leader 大胜，揭示"三面格"病理

Dots and Boxes 是所有游戏中 Leader 优势最大的。原因是一个精妙的病理案例：

- **Score 策略的盲区**：在格点棋中，帮对手围出三面格是致命错误——对手立即吃掉获得 +1 分 + 额外回合。但 Score 策略只会看到"偶尔我也能拿到这格"，而看不到"多数时候是对手吃掉它"
- **随预算增加反而更差**：预算越大，MCTS 越精确地建模对手吃掉三面格 → 对手得分 +1，我们 0 → 但因为 0 是所有不犯错行动的分数下界，MCTS 无法区分"得 0 分的好行动"和"得 0 分的坏行动"
- **Leader 的自修正**：对手吃格 → 对手分数 +1 → Leader 回传 −1 → agent 学会避免

##### Dominion：Score 胜过 Score+，DBG 的悖论

- Score 的胜率**最高**，甚至优于 Score+
- 原因：Dominion 中**好玩家刻意避免早期拿 VP**（省份/公国卡污染牌库），先构筑引擎（行动牌 + 购买力），后期再爆发式收割
- Leader 试图"全程保持领先"与这一原则根本冲突——早期拿了 VP 就领先，但长期必输
- Rollout **必须滚到终局**（tuned 300 steps），因为前期 VP 是欺骗性信号
- TAG 默认的 Dominion 启发式（9 个手工特征的加权组合）被简单的 Score+ 完爆

##### Diamant：Win 唯一有效的稀有案例

- 每步仅 Stay/Leave 二选一，分支因子极小
- 即使 40ms 预算，树深度也达 16（2P），rollout 加上 30 步后，90% 的 rollout 到达终局
- Win 在 2P 中表现最佳（图 6），但随着人数增加 Advantage 递减（树变浅）
- 与 Dominion 不同，Diamant 的短期分数**不是欺骗性的**——但 Leader 仍优于 Score+，因为有"我拿小份 vs 对手拿大份"的选择困境

#### 对六朝的直接启示

| 论文发现 | 六朝映射 | 设计指导 |
|----------|---------|---------|
| Dominion = "Score 最优" | 六朝同属 DBG + 延迟 VP（区域终局计分、司马家分配） | **不能用裸 VP 做短期评估**，必须评估"VP 生成潜力" |
| 对抗性反击 → Leader 最优 | 僭越、区域争夺、文化赛跑、对手弃牌 | 东晋 Agent 的评估函数应包含 Leader 项（与领先者差距） |
| Dots and Boxes "三面格"病理 | 僭越反制牌、进军被伏击等"帮对手搭梯子"的行动 | 需显式惩罚"让对手获利"的行动，不能只奖励"自己获利" |
| Rollout 必须到终局（DBG） | 六朝 10 回合 200+ 步 → 不可能滚到终局 | 必须用截断评估 + 补偿性的"未来 VP 潜力"指标 |
| 手工 Default 被简单 Score+ 完爆 | 不要高估自己设计的复杂评估函数 | 先跑最简单的 Score+/Leader 做 baseline，再考虑是否值得加复杂度 |
| 25× 预算范围对结论几乎无影响 | 六朝 Agent 时间预算可以灵活 | Leader 在 40ms–1000ms 都可靠，不用为预算微调 |

**最重要的一条**：论文提供了实证——**DBG 类型的游戏，MCTS 的评估函数设计走错方向的代价非常大**。Dominion 中 Score 优于 Score+ 优于 Leader 的排序完全反转了多数其他游戏的结论。六朝的评估函数设计需要以 Dominion 为参照模板，而非 Dots and Boxes 或 Uno。

### 2.2 MultiTree MCTS (IEEE CoG 2023)

**作者**: 同样来自 Goodman, Perez-Liébana, Lucas

**核心创新**: 每个玩家构建独立的 MCTS 树（MT-MCTS）

**测试**: 11 款桌面游戏

**发现**:
- 主要收益出现在**同时行动**游戏中
- 在其他游戏中，低计算预算时 MT-MCTS 优于 vanilla MCTS
- 高计算预算下优势消失——独立树带来的较差对手建模抵消了深层搜索的收益

### 2.3 麻将 MCTS — MeowCaTS (计算机奥林匹克 2023 冠军)

**论文**: Tang, Chen, Wu. *Applying Importance Sampling to MCTS for Mahjong*. IEEE Transactions on Games, 2025.

**链接**: https://ieeexplore.ieee.org/document/10856513 | DOI: `10.1109/TG.2025.3535740`

**成就**: 2023 年计算机奥林匹克麻将项目第一名

**三个核心技术**:

#### (a) MSTM — 合并孤立牌模型

```
问题: 手牌 13-14 张，每步选哪张打出，分支因子 ~14

MSTM 做法:
  1. 识别手牌结构: 顺子候选 > 刻子候选 > 搭子 > 孤立牌
  2. 将功能相似的孤立牌合并:
     - 孤立中张数牌 → 一组
     - 孤立役牌（字牌） → 一组
     - 孤立端牌 → 一组
  3. 分支因子: 14 → ~4-6
```

#### (b) 重要性采样

- 不按均匀分布采样隐藏信息（对手手牌、墙牌顺序）
- 根据对手的历史弃牌和吃碰杠行为，推断对手手牌的概率分布
- 按概率分布采样——更多采样"可能性高"的世界

#### (c) 重要性加权 Backpropagation

```
标准 MCTS 回传:
  node.visits += 1
  node.value += reward

重要性采样 MCTS 回传:
  重要性权重 w = P_target(世界) / P_sample(世界)
  node.visits += w
  node.value += w × reward
  
→ 修正了"故意多采样某些世界"带来的统计偏差
```

#### (d) 多深度置换表

- 跨搜索深度共享相似局面的统计
- "相似"由 MSTM 的分组决定
- 补偿 MSTM 合并带来的精度损失

**与六朝的相关性**: 高 — 4人不完全信息卡牌游戏，六朝可借鉴 MSTM 的分组合并思路（合并同类型朝堂牌）和重要性加权回传

### 2.4 Dominion — DBG 的 MCTS 研究

被纳入 Goodman 的 10 款游戏测试中，结论：

- Dominion 属于"聚焦自身分数型"游戏
- DBG 的回报延迟是 MCTS 的根本挑战——购买决策的收益在 2-5 回合后才显现
- 需要缩短 rollout 长度 + 手工评估函数补充
- **对六朝的直接启示**: 六朝的 DBG 部分（将策略牌加入国家牌库、若干回合后抽到并使用）与 Dominion 面临完全相同的搜索挑战

### 2.5 Dhumbal — MCTS 的惨败 (2024) ⚠️

**论文**: Malla. *AI Agents for the Dhumbal Card Game: A Comparative Study*

**结果**:

| Agent | 胜率 |
|-------|------|
| Rule-based (激进) | **88.3%** |
| IS-MCTS | 9.0% |
| PPO (RL) | 1.5% |

**失败原因**:
- Dhumbal 有特殊的"Jhyap 宣言"机制——手牌点数和 ≤10 时可宣布获胜
- IS-MCTS 在搜索中无法有效模拟对手对这种宣言的响应
- 策略融合（strategy fusion）在 Dhumbal 中特别致命

**对六朝的警示**: 六朝的僭越机制、终局触发决策（"是否耗尽部队提前结束"）是类似的离散高影响力决策——需要特殊处理，不能仅依赖通用 MCTS

### 2.6 其他案例速览

| 游戏 | 方法 | 结果 | 对六朝启示 |
|------|------|------|----------|
| **Boop** (2025) | MCTS + 组合优化 | 96% 胜率 vs MCTS 基线，BGA 排名 56/5316 | MCTS + 领域知识注入可大幅提升 |
| **Amazons** (2024) | MCTS + Move Groups + 并行评估 | 23% 更高胜率，获中国高校计算机游戏大赛一等奖 | 行动分组合并减少分支因子 |
| **Chinese Checkers** (2023) | MCTS + CNN 价值网络 | CNN 从 MCTS 弱标签中无监督学习 | 价值网络可从 MCTS 自对弈中训练 |
| **Hanabi** (合作) | IS-MCTS + 对手行为预测 | 预测增强版 IS-MCTS 显著优于 vanilla | 合作游戏需要显式队友建模 |

---

## 三、IS-MCTS 计算需求分析

### 3.1 单次迭代成本

```
Step 1: 树遍历 + 节点展开    ~0.0001s  ← 可忽略
Step 2: Determinization       ~0.001s   ← 可忽略
Step 3: 叶节点评估            ← ← ← 决定性瓶颈
Step 4: 回传统计              ~0.0001s  ← 可忽略
```

### 3.2 评估方式对比

| 评估方式 | 单次耗时 | 1000迭代总耗时 | 可用？ |
|---------|----------|--------------|--------|
| 完整 Rollout（HeuristicAI 滚 200 步到终局） | ~10s | 2.8 小时 | ❌ |
| 截断 Rollout（滚 1 回合 ≈ 28 步） | ~1.4s | 23 分钟 | ❌ |
| **手工评估函数** | 0.001-0.01s | **1-10s** | ✅ |
| 神经网络评估 (CPU) | 0.005-0.02s | **5-20s** | ✅ |

**核心结论**: 不做 rollout，用评估函数直接在叶节点打分，是 IS-MCTS 可行的唯一方式。这与 Goodman 等人的做法一致（他们在 10 款游戏上都用了截断评估而非完整 rollout）。

### 3.3 六朝场景估算（朝堂选牌：10 候选，深度 5，2000 迭代）

| 维度 | 数值 | 评估 |
|------|------|------|
| 单次决策时间 | 10s (Python) | ✅ 非实时游戏可接受 |
| 整局总 MCTS 时间 | ~100s (10次朝堂选牌) | ✅ |
| 内存 | ~2 MB/搜索树 | ✅ 可忽略 |
| GPU | 不需要（手工评估函数） | ✅ |
| **最大瓶颈** | **评估函数的准确性** | ⚠️ |

### 3.4 与 C++ 实现的差距

| | Goodman 研究 (C++) | 六朝估算 (Python) |
|--|-------------------|------------------|
| 迭代数 | 10,000 | 2,000 |
| 单迭代 | ~0.0002s | ~0.005s |
| 单决策 | 0.5-2s | 10s |
| Python 慢 ~25 倍 | — | 仍在可用范围内 |

---

## 四、麻将 MCTS（MeowCaTS）算法流程

> ⚠️ 以下伪代码基于论文摘要中确认的三个组件（MSTM、重要性采样、多深度置换表）+ IS-MCTS 标准框架推断。论文全文在 IEEE Xplore 付费墙后 (DOI: 10.1109/TG.2025.3535740)，精确算法以原文为准。

```python
def meowcats_search(info_set, iterations=10000):
    """麻将 IS-MCTS + 重要性采样"""
    
    root = ISMCTSNode(info_set)
    
    for i in range(iterations):
        # ── Step 1: 重要性采样 ──
        # Q 的设计结合对手弃牌/吃碰杠历史推断的分布
        world = importance_sample(info_set, proposal_Q)
        
        # ── Step 2: MSTM 压缩 ──
        # 将孤立牌按功能相似度合并，分支因子 14 → 4-6
        compressed = mstm_compress(world)
        
        # ── Step 3: IS-MCTS 树搜索 ──
        node = root
        path = [node]
        
        # Selection: 在信息集树上用 UCB 选路
        while node.is_fully_expanded() and not node.is_terminal():
            action = node.ucb_select()
            node = node.children[action]
            path.append(node)
            compressed.apply(action)
        
        # Expansion: 叶节点展开
        if not node.is_terminal():
            legal = compressed.legal_actions()  # MSTM 压缩后的动作空间
            node.expand(legal)
            action = random.choice(node.untried)
            compressed.apply(action)
            node = node.add_child(action)
            path.append(node)
        
        # Simulation: 用启发式策略滚到终局
        reward = heuristic_rollout(compressed)
        
        # ── Step 4: 重要性加权 Backpropagation ──
        w = P_target(world) / P_sample(world)  # 重要性权重
        for n in reversed(path):
            n.visits += w           # 不是 +=1
            n.value += w * reward   # 加权回报
        
        # 存入多深度置换表
        tt_store(compressed.mstm_signature, depth, node.stats)
    
    # 决策: 选加权访问最多的动作
    return max(root.children, key=lambda a: root.children[a].visits)


def mstm_compress(world):
    """合并孤立牌: 将功能相似的牌分组"""
    hand = world.my_tiles  # 13-14 张
    
    groups = {"melds": [], "pairs": [], "connected": [], "solitary": []}
    
    for tile in hand:
        if is_part_of_meld(tile, hand):
            groups["melds"].append(tile)
        elif is_part_of_pair(tile, hand):
            groups["pairs"].append(tile)
        elif has_neighbor(tile, hand):
            groups["connected"].append(tile)
        else:
            # 孤立牌按类型合并
            if tile.is_honor():
                groups["solitary"].append(("honor", tile))
            elif tile.is_terminal():
                groups["solitary"].append(("terminal", tile))
            else:
                groups["solitary"].append(("middle", tile))
    
    return CompressedState(groups)
```

---

## 五、六朝 Agent 方案一：MCTS 搜索

> 将 IS-MCTS 应用于六朝，面临搜索空间巨大、不完全信息、多人非零和等挑战。必须采用分层架构 + 截断评估。

### 5.1 六朝的决策复杂度

| 维度 | 数值 | 对搜索的影响 |
|------|------|------------|
| 玩家数 | 4（1北方 + 3东晋） | 多人博弈，非零和，需要 Max^n 或退化搜索 |
| 每回合每人行动数 | 5-10 个 | 一回合树深度 20-40 层 |
| 每行动选项数 | 15-30 个 | 分支因子大 |
| 一局总行动数 | ~200+ | 不可能搜索到终局（20^200 ≈ 天文数字） |
| 信息不完全 | 对手手牌、牌库顺序、秘密目标 | 需要 determinization |
| 延迟回报 | DBG 牌今天加入，3回合后才抽到 | 信用分配极难 |

### 5.2 可行架构：分层 MCTS

直接对每步行动跑 MCTS 不可行（20^7 × 1000 rollout × 0.2s = 200s/步）。必须分层：

```
┌─────────────────────────────────────────────┐
│           Hierarchical MCTS                  │
│                                              │
│  L2: 战略层 (每回合跑一次)                    │
│  ├── 搜索空间：回合级"策略"                  │
│  │   "军事扩张" "文化推进" "牌组构筑" "防守"  │
│  ├── 分支因子：~4-6                          │
│  ├── 搜索深度：剩余回合数 (~5-8)              │
│  ├── 节点数：~6^5 ≈ 7776 (可控!)             │
│  └── 叶节点评估：用 HeuristicAI 滚完整回合    │
│                                              │
│  L1: 战术层 (每步跑一次)                      │
│  ├── 搜索空间：当前回合内的行动序列            │
│  ├── 分支因子：~20                            │
│  ├── 搜索深度：~7 个行动 (一个玩家的回合)      │
│  ├── 节点数：MCTS ~2000 iterations            │
│  ├── 叶节点评估：训练好的价值网络              │
│  └── 约束：L2 选定的战略方向限制了行动权重     │
└─────────────────────────────────────────────┘
```

### 5.3 四个核心技术挑战

#### 挑战 1：多人博弈搜索

标准 MCTS 假设二人零和。四人非零和需要不同算法：

| 算法 | 原理 | 适用性 |
|------|------|--------|
| **Max^n** | 每个玩家独立最大化自己的分数 | ✓ 最合适，但搜索效率低（每层×4 UCB） |
| **Paranoid** | 假设所有其他玩家结盟对付你 | 太悲观，不符合东晋合作现实 |
| **退化单 Agent** | 只对当前玩家 MCTS，对手用 HeuristicAI 预测 | ✅ **推荐**，计算量可接受 |

#### 挑战 2：不完全信息

```
来源                    已知信息                  未知信息
─────────────────────────────────────────────────────────
对手手牌                 已打出/弃掉的牌            手牌内容
牌库                     已抽出的牌（可推算）        牌库剩余顺序
对手秘密目标             公开目标（1张）            秘密目标（1张）
```

**标准做法：Determinization** — 每轮迭代采样一个"世界状态"（对手手牌、牌库顺序随机化），在采样世界上搜索，多轮平均。

**六朝特有问题**：东晋三家共用一个牌库 → 你的出牌影响盟友后续抽牌 → 共同资源管理问题，determinization 很难捕捉。

#### 挑战 3：局面评估函数

不能搜索到终局 → 必须在中间节点评估。六朝需覆盖 7 个维度：

```
Eval(s) = w1 × VP_current
        + w2 × VP_expected_final（区域控制 × 区控VP + 文化排名预期）
        + w3 × area_control_score（控制区域数量 × 区域价值）
        + w4 × culture_rank_score（三条文化轨各自的排名预期）
        + w5 × deck_quality_score（流民比例、平均费用/效果值）
        + w6 × army_progress_score（部队部署进度、终局触发风险）
        + w7 × sima_share_score（威望/功绩排名 → 司马家VP分配预期）
```

如何获得？

| 方式 | 优点 | 缺点 |
|------|------|------|
| **手工设计** | 可解释，无训练成本 | 不准确，权重靠猜 |
| **自对弈训练** | 自动发现最优权重 | 需要百万局 GPU 训练（AlphaZero 级别） |
| **从 HeuristicAI 对局学习** | 利用已有数据 | 学到 HeuristicAI 水平，非最优 |

#### 挑战 4：Rollout 策略偏差

唯一快速 rollout 选项是 HeuristicAI。但 HeuristicAI 行为若与真实玩家差异大 → rollout 给出有偏估计 → 偏差传导到根节点决策。"用一个弱 AI 的模拟结果指导强 AI 的决策。"

### 5.4 MCTS 路线小结

```
优势：
  ✓ 形式化保证（足够迭代下 UCT 收敛到最优）
  ✓ 不需要 LLM，纯本地运行
  ✓ 可批量并行跑（一晚上数千局自对弈）
  ✓ 搜索过程中自然发现战术组合

劣势：
  ✗ 局面评估函数极难设计（7+ 维度 × 非线性交互）
  ✗ Determinization 对共享牌库的处理很粗糙
  ✗ 多人 Max^n 搜索效率低
  ✗ Rollout 策略偏差会传导到根节点决策
  ✗ 需要海量自对弈训练（百万局级别）
  ✗ 规则改动后整个评估函数需重新训练
  ✗ 无法解释"为什么选这个行动"（对 L2/L3 分析不友好）
```

---

## 六、六朝 Agent 方案二：LLM-Hybrid

> 核心设计理念（来自 EnvGen 洞察）：**LLM 离执行层越远、离战略设计层越近，效果越好、成本越低。** LLM 定每回合战略方向，Heuristic Executor 执行具体行动。

### 6.1 架构设计

```
┌──────────────────────────────────────────────────┐
│               LLM-Hybrid Agent                    │
│                                                   │
│  每回合开始（~10次/局）:                            │
│  ┌─────────────────────────────────────┐          │
│  │ StateEncoder                         │          │
│  │ GameState → SnapshotViewport → Markdown │       │
│  │                                       │          │
│  │ 输出示例 (~1500 tokens):              │          │
│  │ ## 第5回合 — 你（谢安）的状态          │          │
│  │ ### 基础资源                          │          │
│  │ VP: 45 | 军力: 3 | 手牌: 6张          │          │
│  │ 威望: 4 (排名1/3) | 功绩: 2 (排名2/3)  │          │
│  │ ### 朝堂候选策略牌                     │          │
│  │ 1. 佛寺 (1费) — 传播佛学 +2vp          │          │
│  │ 2. 募兵 (1费) — 支付2vp获5军力         │          │
│  │ ...                                   │          │
│  │ ### 文化排名                          │          │
│  │ 儒学: 你第2 (贡献3级)                  │          │
│  │ 玄学: 你第1 (贡献5级)                  │          │
│  │ ### 对手概要                          │          │
│  │ 北方-拓跋珪: VP 52 控制河北+山西        │          │
│  │ ### 君主任务                          │          │
│  │ 骰子1: 扩张(关中) 骰子2: 文化           │          │
│  └─────────────────────────────────────┘          │
│           ↓                                       │
│  ┌─────────────────────────────────────┐          │
│  │ LLM → 结构化 StrategicDirective      │          │
│  │ {                                    │          │
│  │   "round_goal": "军事扩张",           │          │
│  │   "reasoning": "北方正在逼近江南，    │          │
│  │    必须先占据淮南作为缓冲...",        │          │
│  │   "priority_actions": [              │          │
│  │     "march","occupy","play_card"],   │          │
│  │   "key_locations": ["寿春","合肥"],   │          │
│  │   "preferred_court_cards": ["募兵"],  │          │
│  │   "budget_allocation": {             │          │
│  │     "march":0.5,"occupy":0.2,...     │          │
│  │   }                                  │          │
│  │ }                                    │          │
│  └─────────────────────────────────────┘          │
│           ↓                                       │
│  每次行动选择:                                     │
│  ┌─────────────────────────────────────┐          │
│  │ Heuristic Executor                    │          │
│  │   base_score (行动本身价值)             │          │
│  │   + alignment_bonus (与战略方向一致)     │          │
│  │   + location_bonus (目标在关键地点)      │          │
│  │   + card_bonus (涉及优先卡牌)           │          │
│  │   → 选最高分                           │          │
│  └─────────────────────────────────────┘          │
│                                                   │
│  关键决策点 (可选 LLM 微调 ~3-5次/局):              │
│  ├── 朝堂选牌（信息量大）                          │
│  ├── 僭越决策（威望比较）                          │
│  ├── 终局触发（要不要耗尽部队?）                    │
│  └── 计划被打乱后的重新评估                         │
└──────────────────────────────────────────────────┘
```

### 6.2 成本估算

| | SPRING (Crafter) | LLM-Hybrid (六朝) |
|--|-----------------|-------------------|
| LLM 角色 | 每步选动作 | 每回合定战略 |
| 调用频率 | 2,700次/局 | ~15次/局 |
| 成本 | $270/局 | **~$0.10-0.50/局** |
| 执行层 | LLM 直接选 | Heuristic Executor |

### 6.3 四个核心技术挑战

#### 挑战 1：状态编码质量

利用已有的 **SnapshotViewport** 系统（`engine/viewport/snapshot.py`），已处理可见性规则。需新增 **Markdown 渲染器**。

| 编码策略 | 优点 | 缺点 |
|---------|------|------|
| 全量 JSON dump | 信息完整 | ~5000 tokens，冗余多 |
| **精选摘要（推荐）** | ~1500 tokens | 可能遗漏关键信息 |
| 分层编码（先摘要，可追问） | 灵活 | 增加调用次数 |

#### 挑战 2：结构化战略指令的可靠性

LLM-Hybrid 最大风险点。缓解措施：

```
StrategicDirective 校验层:
  LLM 输出 → JSON parse → schema 校验
     ↓
  合法性检查:
    - key_locations 都在地图上？
    - preferred_court_cards 在朝堂区？
    - 行动优先级是合法类型？
     ↓
  合理性检查（规则引擎）:
    - 军力=0 但 priority 第一项是 march？ → 自动调整为 recruit 优先
    - 没有部队可部署但 priority 有 occupy？ → 移除 occupy
     ↓
  最终指令 → Heuristic Executor
```

#### 挑战 3：战略-战术鸿沟

LLM 战略 vs Heuristic Executor 执行之间的偏差：

```
LLM 战略: "本回合优先军事扩张，目标寿春方向"

Executor 选择:
  A. 征募（弃1牌→+1军力）        score = 0.3
  B. 打出谢玄（军事幕僚）          score = 0.6  ← 正确
  C. 进军→寿春（但军力不够，不可用）
  
如果 Executor 评分权重不当:
  B. 谢玄                      score = 0.2  ← 幕僚长期价值被低估
  C. 摸牌                      score = 0.4  ← 短期价值被高估
  → 选了摸牌，违背了战略意图
```

**缓解**：LLM 提供动态权重向量 + 禁止项/必备项 + 关键行动直接由 LLM 决策。

#### 挑战 4：对手建模（LLM 的绝对优势）

```
MCTS 的对手建模：
  "所有对手选择最大化其 VP 的行动" → 同质化假设

LLM-Hybrid 的对手建模：
  "王导公开目标是控制荆州，他在往襄阳推。
   北方3回合没主动进军，可能在攒军力。
   刘裕威望比我高1，我需要提防僭越。"
  → 个性化、情境化推理（Theory of Mind）
```

### 6.4 LLM-Hybrid 路线小结

```
优势：
  ✓ 战略层面推理能力强（理解局势、识别威胁、长期规划）
  ✓ 自然语言可解释（每个战略决策有 reasoning 字段）
  ✓ 对手建模（Theory of Mind，个性化推理）
  ✓ 规则变更友好（LLM 读新规则书即可，无需重训练）
  ✓ 与 L2/L3 天然集成（战略指令是分析素材）
  ✓ 成本可控（~$0.10-0.50/局，GPT-4o-mini 级别）

劣势：
  ✗ 战术执行依赖 Heuristic Executor（战略-战术鸿沟）
  ✗ LLM 可能误解游戏规则（需要校验层）
  ✗ 输出不稳定（同一局面两次可能不同战略）
  ✗ 上下文窗口有限（~1500 tokens 编码是信息瓶颈）
  ✗ 有延迟（每回合等待 LLM API ~2-5s）
  ✗ 无法批量并行跑数百局（API rate limit）
```

---

## 七、逐维度对比

### 7.1 决策质量

| 场景 | MCTS | LLM-Hybrid | 优势 |
|------|------|-----------|------|
| 战术组合发现 | **强** — 搜索自然发现 combo | 弱 — 依赖 Heuristic Executor | MCTS |
| 长期战略一致性 | 弱 — 每步独立，缺乏跨回合连贯性 | **强** — 回合之间的连贯计划 | LLM |
| 对手意图理解 | 弱 — 隐含在 determinization 中 | **强** — Theory of Mind 显式推理 | LLM |
| 共享资源管理（DBG） | 中 — 可搜索但评估困难 | **强** — 理解"现在加牌、以后抽到" | LLM |
| 僭越/威望博弈 | 弱 — 需精确多人博弈建模 | **强** — 理解社交博弈逻辑 | LLM |
| 精确资源计算 | **强** — 确定性搜索保证 | 中 — LLM 有时算错数值 | MCTS |
| 终局触发决策 | 中 — 可 search 到终局 | **强** — 理解"提前结束对我有利" | LLM |

### 7.2 计算成本

| 维度 | MCTS | LLM-Hybrid |
|------|------|-----------|
| 每步决策时间 | 1-5s（2000 iter × eval） | ~0.01s（Heuristic Executor） |
| 每回合战略时间 | 0（无额外战略层） | 2-5s（LLM API） |
| 每局总时间 | ~200步 × 2s = 400s | ~10回合×3s + 190步×0.01s ≈ 32s |
| 每局金钱成本 | $0（本地） | ~$0.10-0.50 |
| 批量 100 局 | ~11h（串行）或 ~1h（8 GPU） | ~1h（API rate limit） |
| 自对弈训练 | 百万局级别 | 不需要 |

### 7.3 实现复杂度

| 模块 | MCTS | LLM-Hybrid |
|------|------|-----------|
| 行动空间抽象 | **高** — 需设计分层/macro-action | 低 — 直接用 Heuristic Executor |
| 局面评估 | **极高** — 7+ 维度价值网络 | 中 — LLM 隐式理解，需 StateEncoder |
| 对手建模 | 中 — determinization 采样 | 低 — LLM 自带 ToM |
| 训练管道 | **极高** — 自对弈+网络训练+超参 | 无 — zero-shot |
| 规则变更适应 | 极高 — 重新训练 | **低** — 更新 prompt 和校验规则 |
| 调试/诊断 | 低 — 价值网络不可解释 | **高** — 每步战略有 reasoning |

### 7.4 与上层分析（L2/L3）的协同 — 关键差异

```
MCTS → L2/L3:
  输出：选择的行动序列
  可分析性：低（不知道为什么选）
  需额外工作：另外跑 LLM 分析 MCTS 决策质量

LLM-Hybrid → L2/L3:
  输出：每回合战略指令 + reasoning + 行动序列
  可分析性：高（LLM 自己解释了"为什么"）
  附加值：战略指令是 L2 直接素材
         跨局战略模式 → L3 平衡分析素材
```

**具体例子**：L3 统计发现"谢安胜率 18%"。

- MCTS：只知道谢安输了，不知道为什么
- LLM-Hybrid：直接读 LLM reasoning → "第3回合，文化路线被北方军事压力打断" → L3 建议给谢安增加防守能力

### 7.5 风险对比

| 风险 | MCTS | LLM-Hybrid |
|------|------|-----------|
| **最大技术风险** | 评估函数偏差→系统性错误决策 | LLM 对规则的根本性误解 |
| **最大工程风险** | 自对弈训练 GPU 需求，可能训不出来 | API 不稳定/不可用 |
| **可验证性** | 可自我对弈验证 | 需人类专家审查战略决策 |
| **天花板** | 受限于评估函数质量 | 受限于 LLM 能力（持续进步中） |

### 7.6 路线本质

```
MCTS 路线：                  LLM-Hybrid 路线：

"让机器自己算出来"           "让 LLM 理解并规划"

适合：                       适合：
- 战术密集、搜索可控          - 战略复杂、需长期规划
- 评估标准明确（胜负分明）    - 多人博弈、社交推理
- 有海量训练资源             - 训练资源有限
- 规则稳定不变               - 规则仍在迭代
```

六朝：**战略复杂 > 战术复杂，多人博弈 > 单人优化，规则仍在迭代** → 指向 LLM-Hybrid。

---

## 八、结论与推荐架构

### 8.1 推荐方案：LLM-Hybrid 为主，MCTS 局部增强

```
┌─────────────────────────────────────────────────┐
│           推荐的混合架构                          │
│                                                  │
│  战略层 (LLM)                                    │
│  ├── 每回合1次：定战略方向，输出 StrategicDirective │
│  └── 关键决策点：朝堂选牌、僭越、终局触发          │
│                                                  │
│  战术层 (Heuristic Executor + 局部 MCTS)          │
│  ├── 常规行动：Heuristic Executor 按战略评分       │
│  ├── 朝堂选牌：MCTS 浅层搜索（深度3，候选10张）     │
│  └── 复杂卡牌结算：LLM 微调用                      │
│                                                  │
│  元层 (L2/L3 共享)                                │
│  └── LLM 的战略推理文本 → L2 经验总结的直接素材     │
└─────────────────────────────────────────────────┘
```

### 8.2 实现优先级

| 优先级 | 模块 | 理由 |
|--------|------|------|
| **P0** | StateEncoder（Viewport → Markdown） | 一切 LLM 调用的前提，已有 Viewport，只需加渲染器 |
| **P1** | StrategicDirective schema + 校验层 | 保证 LLM 输出可执行 |
| **P1** | Heuristic Executor（支持动态权重） | 战术执行层，也是 MCTS 的 fallback |
| **P2** | LLM-Hybrid Agent 主循环 | 整合 P0+P1，形成可对局的完整 Agent |
| **P2** | 关键决策点 LLM 微调用 | 朝堂选牌、僭越、终局触发 |
| **P3** | 局部 MCTS（朝堂选牌） | 10 候选项上浅搜索，增强战术精度 |
| **P3** | L2 Post-Game Analyzer | 消费 LLM 战略推理文本 |

### 8.3 不做的事

- **不做完整 MCTS Agent**：搜索空间太大，评估函数太难。仅局部使用。
- **不做 HeuristicAI 增强**：作为对局参考价值不大。仅作为 Executor 基底和 MCTS rollout。
- **不做纯 LLM Agent（SPRING 模式）**：$270/局，成本太高且效果不如 EnvGen 模式。

### 8.4 可直接借鉴的外部技术

| 来源 | 技术 | 六朝应用 |
|------|------|---------|
| 麻将 MSTM | 按功能相似度分组合并 | 朝堂牌按"资源型/文化型/军事型/特殊型"分组 |
| 麻将重要性采样 | 非均匀 Determinization + 加权回传 | 对手手牌/秘密目标的推断分布驱动采样 |
| Goodman et al. | "追随领先者"目标函数 | 东晋 MCTS 优化"相对 VP"而非"绝对 VP" |
| Goodman et al. | 截断评估替代完整 rollout | 六朝 200 步太深 → 搜索深度 3-5 层后用评估函数截断 |
| 麻将置换表 | 跨深度共享统计 | 相似区域控制/文化配置的跨回合复用 |

---

## 九、参考文献

| 论文 | 链接 | 关键词 |
|------|------|--------|
| Cowling et al. (2012) — IS-MCTS 原始论文 | https://ieeexplore.ieee.org/document/6203567 | SO-ISMCTS, MO-ISMCTS, **免费** |
| Goodman et al. (2023) — Following the Leader | https://dl.acm.org/doi/10.1145/3582437.3582449 | 10款多人游戏, Dominion, IS-MCTS |
| Goodman et al. (2023) — MultiTree MCTS | IEEE CoG 2023 | 每玩家独立树 |
| Tang et al. (2025) — MeowCaTS | https://ieeexplore.ieee.org/document/10856513 | 麻将, 重要性采样, MSTM, **付费** |
| Malla (2024) — Dhumbal AI | https://ar5iv.labs.arxiv.org/html/2510.11736 | IS-MCTS vs Rule-based |
| García-Sánchez et al. (2025) — Boop | EvoApplications 2025 | MCTS + 组合优化 |
| Zhang et al. (2024) — Amazons | Algorithms 2024 | Move Groups, 并行评估 |

---

*文档创建: 2026-07-30 | 最后更新: 2026-07-30*
