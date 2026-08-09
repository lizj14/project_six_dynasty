# Dominion RL Benchmark / Rainbow DQN 深度解析

> 论文: "Dominion: A New Frontier for AI Research" | 作者: Halawi, D. et al. | 年份: 2024
> arXiv: [2405.06846](https://arxiv.org/abs/2405.06846)
> 数据集: Dominion Online Dataset (2,000,000+ 对局)
> 代码: 论文公开但未见独立开源仓库

---

## 一、项目概述

这是**第一个正式提出将 Dominion 作为 RL 基准的学术论文**。作者构建了完整的评测体系：发布 200 万+ 真人玩家对局数据集、实现 Rainbow DQN Bot、测试 6 种基线、提出三个核心 RL 挑战。

### 核心数据

| 指标 | 数值 |
|------|------|
| 数据集规模 | **2,000,000+** 真人玩家对局 |
| RL 算法 | **Rainbow DQN** |
| 训练量 | **~7,000** 局（单 GPU ~45 分钟） |
| 测试卡片池 | 完整 Dominion（350+ 王国卡） |
| 基线数量 | **6** 种（Big Money → Provincial） |
| 关键结果 | 约 **2/3** 胜率 vs 之前最强启发式 Bot |

---

## 二、为什么 Dominion 是好的 RL 基准

论文识别出三个 RL 核心挑战，使其区别于 Atari/围棋等传统基准：

### 2.1 可变动作空间（Variable Action Sets）

每回合可购买的卡牌取决于手牌金币数。RL Agent 不能假设动作空间固定——需要"动作掩码"（action masking）或专门的策略架构。

### 2.2 随机性与长时域

洗牌引入随机性，早期买牌影响数十回合后的牌组质量。这要求 Agent 学习"统计意义上的好决策"而非"确定性的最优路径"。

### 2.3 动态卡池（Dynamic Card Sets）

每局随机 10 张王国卡从 350+ 张中选取。Agent 必须在**每局不同的游戏规则下**进行推理——这与 Atari（固定游戏）或围棋（固定规则）有本质区别。

```
对比:
  Atari Breakout: 总是相同的 paddle + ball 规则
  围棋: 总是相同的 19×19 规则
  Dominion: 每局规则不同——因为可用的王国卡不同
```

---

## 三、六种基线体系

论文建立了一套递进的基线系统：

| 基线 | 策略 | 性能级别 |
|------|------|----------|
| **Big Money** | 只买 Silver/Gold/Province，不买行动牌 | 最低基线 |
| **Big Money + X** | Big Money + 单一强力行动牌 | 入门级 |
| **Smithy Bot** | Big Money + Smithy（+3 牌）| 低 |
| **Witch Bot** | Big Money + Witch（攻击）| 中低 |
| **Provincial** | 启发式规则引擎 + 各卡牌手写策略 | **之前最强** |
| **Rainbow DQN** | 端到端 RL | **新最强** |

### Big Money — 出人意料地强

```
Big Money 策略:
  行动阶段: 跳过（不做任何事）
  购买阶段:
    if coins >= 8: buy Province
    elif coins >= 6: buy Gold
    elif coins >= 3: buy Silver
    else: buy nothing
```

即使这么简单的策略，在大约 30% 的随机王国卡组合中，Big Money 能**击败**许多不熟练的人类玩家。这揭示了 Dominion 的一个重要特性：**钱永远不骗你**——复杂的行动牌组合需要正确的引擎支持，瞎买行动牌不如只买钱。

---

## 四、Rainbow DQN 实现

### 4.1 状态表示

```
输入层:
├── 手牌 (hand): 每种卡牌的数量
├── 牌组 (deck): 每种卡牌的数量
├── 弃牌堆 (discard): 每种卡牌的数量
├── 场上 (in_play): 当前回合打出的牌
├── 供应堆 (supply): 每堆剩余数量
├── 资源 (resources): actions, buys, coins
├── 回合数 (turn): 当前回合编号
└── 垃圾堆 (trash): 已被销毁的牌
```

### 4.2 动作空间处理

使用**非法动作掩码**（invalid action masking）——DQN 输出所有动作的 Q 值，然后对非法动作的 Q 值设 -∞，只从合法动作中选最大 Q：

```python
def select_action(state, valid_actions):
    q_values = q_network(state)        # [n_all_actions]
    mask = torch.full_like(q_values, -float('inf'))
    mask[valid_actions] = 0
    masked_q = q_values + mask
    return valid_actions[torch.argmax(masked_q)]
```

### 4.3 奖励函数

| 事件 | 奖励 |
|------|------|
| 终局胜利 | **+50** |
| 每回合 VP 变化 | **+ΔVP × 0.1** |
| 每回合金币变化 | **+Δcoins × 0.01**（轻微鼓励经济增长）|

VP 塑形奖励帮助 Agent 理解"买 Province 是好事"，但论文发现终端奖励（+50）对最终性能影响最大。

### 4.4 Rainbow DQN 组件

| 组件 | 作用 |
|------|------|
| Double DQN | 解耦选择与评估，减少过估计 |
| Prioritized Replay | 优先重放高 TD-error 的经验 |
| Dueling Networks | 分离状态价值 V(s) 和动作优势 A(s,a) |
| Multi-step Returns | N 步 TD 目标，加速信用分配 |
| Distributional RL | 学习回报分布而非标量 Q 值 |
| Noisy Nets | 自适应探索替代 ε-greedy |

### 4.5 关键结果

- 仅需 **~7,000 局训练**（单 GPU ~45 分钟）即超过 Provincial Bot
- 约 **2/3** 的胜率 vs Provincial
- 证明了 RL 在 Dominion 上的可行性——之前普遍认为游戏状态空间太大

---

## 五、Dominion Online Dataset

论文发布的数据集：

| 属性 | 值 |
|------|-----|
| 总对局数 | 2,000,000+ |
| 玩家数 | 数十万 |
| 时间跨度 | 数年 |
| 数据格式 | 每步动作 + 卡牌 + 结果 |
| 包含内容 | 玩家等级、卡牌选择、购买顺序、终局分数 |

这个数据集对于行为克隆、Offline RL、策略分析等下游任务有巨大价值。

---

## 六、局限与后续方向

1. **仅测试 Base Set**：未涉及扩展包的更复杂交互（如 Duration 牌、Events、Projects）
2. **Rainbow DQN 是最简配置**：未调整 Rainbow 各组件的超参数以适应 Dominion
3. **无多智能体实验**：仅单人 vs 启发式 Bot，未测试自对弈（self-play）
4. **动作空间简化**：部分复杂卡牌（如 Throne Room 的连锁）被简化处理

---

## 七、对六朝的启示

1. **先建基线**：六朝 AI 也应该从最简单的规则 AI 开始，建立递进基线体系
2. **动作掩码是关键**：六朝也有可变动作空间（手牌决定可用动作），RL 方案必须处理非法动作
3. **数据集价值**：如果可以收集真人玩家数据，对 AI 训练是巨大加速
4. **奖励塑形需要谨慎**：Dominion 经验表明简单的终端奖励可能优于复杂的中间奖励
