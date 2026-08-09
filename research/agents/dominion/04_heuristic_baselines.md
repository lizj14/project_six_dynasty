# 启发式基线方法深度解析

> 覆盖项目: Dominiate (rspeer, 2013–14) | dominion-rl / DQN+IL (Thompson, 2019) | 遗传算法 (Mok, 2016) | MC/SARSA/DQL (Yang & Kuo, 2019)
> 地位: Dominion AI 的经典基线和入门方法

---

## 一、Dominiate — 最经典的规则引擎（2013–14）

> GitHub: [github.com/rspeer/dominiate](https://github.com/rspeer/dominiate)
> 语言: CoffeeScript | 地位: Dominion 社区最知名的 AI 模拟器

### 1.1 核心设计

Dominiate 的 `BasicAI` 使用**优先级列表 + 数值价值函数**驱动全部决策：

```python
# Dominiate BasicAI 的决策逻辑（伪代码复现）
class BasicAI:
    # 购买优先级（越前越优先）
    gainPriority = [
        "Province",    # 6 VP
        "Duchy",       # 3 VP (游戏快结束时)
        "Estate",      # 1 VP (游戏马上结束时)
        "Gold",        # +3 coins
        # ... 王国卡按策略插入
        "Silver",      # +2 coins
    ]
    
    # 行动优先级
    actionPriority = [
        "Village",     # +1 Card, +2 Actions (先打，提供行动)
        "Smithy",      # +3 Cards (再打，消费行动抽牌)
        "Market",      # +1 Card, +1 Action, +1 Buy, +1 Coin
    ]

    def chooseAction(self, hand):
        for card in self.actionPriority:
            if card in hand:
                return play(card)
        return endPhase()

    def chooseBuy(self, coins, supply):
        for card in self.gainPriority:
            if card.cost <= coins and supply[card] > 0:
                return buy(card)
        return endPhase()
```

### 1.2 12 级行动优先级体系

Dominiate 有一套完整的 12 级行动打出逻辑：

| 级别 | 类型 | 代表卡牌 | 决策逻辑 |
|------|------|----------|----------|
| 1 | 牌组操作 | Chancellor | 可选是否立即洗牌 |
| 2 | 村庄类 | Village, Festival | +2 Actions — 先打 |
| 3 | 抽牌终端 | Smithy, Council Room | +Cards 但是终端 |
| 4 | 销毁 | Chapel, Remodel | 移除废牌 |
| 5 | +Buy | Market, Woodcutter | 增加购买次数 |
| 6 | 攻击 | Militia, Witch | 干扰对手 |
| 7 | 获取 | Workshop | 免费获取卡牌 |
| 8 | 金币 | Moneylender | 直接产出 coins |
| 9 | 特殊 | Throne Room | 复制另一张行动牌 |
| 10 | 反应 | Moat | 仅当有攻击时才打 |
| 11 | 弱牌 | 所有剩余 | 价值最低的行动牌 |
| 12 | — | — | 无行动牌可打 → 结束行动阶段 |

### 1.3 价值函数 fallback

当优先级列表无法决策时（如多张卡牌相同优先级），fallback 到数值价值函数：

```python
def cardValue(card, gameState):
    value = 0
    value += card.coinValue * 1.0     # 金币产出
    value += card.cardDraw * 0.7      # 抽牌价值
    value += card.actions * 0.5       # 行动价值
    value += card.buys * 0.3          # 购买次数的价值
    value += card.trashValue(state)   # 销毁废牌的价值
    return value
```

---

## 二、Big Money — 永远不过时的基线

Big Money 策略是 Dominion AI 评测的"Hello World"：

```
回合开始:
  行动阶段: 跳过
  购买阶段:
    打出所有手牌中的 Treasure
    if coins >= 8: 买 Province
    elif coins >= 6: 买 Gold
    elif coins >= 3: 买 Silver
    else: 不买
  清理阶段: 弃牌 + 抽 5 张
```

### 为什么 Big Money 出人意料地强

1. **不稀释牌组**：不买行动牌意味着每次洗牌后手牌更"纯"——只有钱
2. **钱永远不骗你**：Silver 永远是 +2 coins；不像 Smithy 可能抽不到
3. **统计稳定性**：大数定律让 Big Money 的期望回报非常稳定

在约 **30% 的随机王国卡组合**中，Big Money 的胜率超过 50%（对阵中等水平的行动牌组合策略）。一个只买钱的策略能赢 1/3 的对局——这说明许多王国卡组合其实根本不需要行动牌。

---

## 三、DQN + 模仿学习（2019）

> GitHub: [github.com/sdthompson1/dominion-rl](https://github.com/sdthompson1/dominion-rl)
> 语言: Python | 卡牌: ~20 张 (Base + Alchemy + Seaside)

### 3.1 架构

```python
# 简化的 DQN Agent
class DominionDQN(nn.Module):
    def __init__(self, state_dim, action_dim):
        self.net = nn.Sequential(
            nn.Linear(state_dim, 256),
            nn.ReLU(),
            nn.Linear(256, 256),
            nn.ReLU(),
            nn.Linear(256, action_dim)
        )

class DQNAgent:
    def __init__(self):
        self.q_network = DominionDQN(...)
        self.target_network = DominionDQN(...)  # 目标网络
        self.replay_buffer = deque(maxlen=10000)
        self.epsilon = 1.0
    
    def act(self, state, valid_actions):
        if random.random() < self.epsilon:
            return random.choice(valid_actions)  # 探索
        q_values = self.q_network(state)
        mask = torch.tensor(valid_actions)
        return valid_actions[argmax(q_values * mask)]
    
    def train(self, batch):
        # 标准 DQN 更新: Q(s,a) ← r + γ max Q(s',a')
        ...
```

### 3.2 模仿学习增强

项目支持从预定义的 "Buy Menu" 策略开始学习：

```python
# Buy Menu: 每种卡牌的价格阈值
BUY_MENU = {
    'Province': 8,
    'Gold': 6,
    'Wharf': 5,      # +2 Cards, +1 Buy (下回合也触发)
    'Silver': 3,
    # ...
}

# 混合训练: 先用 Buy Menu 指导，再逐步过渡到自主 RL
def hybrid_act(state, valid_actions, episode):
    if episode < WARMUP_EPISODES:
        return buy_menu_act(state)     # 模仿
    else:
        return epsilon_greedy_act(state)  # RL
```

### 3.3 结果

| 策略 | 平均得分 |
|------|----------|
| Big Money（纯钱）| ~24 |
| Big Money + Wharf（纯 RL）| **~31** |
| 混合（Buy Menu + RL）| **40–60** |

混合训练（模仿学习 + RL）显著优于纯 RL——这暗示了"先教基本策略，再让 RL 优化"的路径在卡牌游戏中非常有效。

---

## 四、遗传算法（2016）

> Stanford CS229: Mok, D. "Creating a Dominion AI using Genetic Algorithms"

### 4.1 核心思路

把 Dominion 策略编码为**染色体（目标牌组）**：

```python
class DominionChromosome:
    """
    染色体编码:
    {
        'Silver': (preference=0.8, delay=0),     # 高偏好，无延迟
        'Gold': (preference=0.9, delay=2),        # 高偏好，等到第 2 回合
        'Province': (preference=1.0, delay=8),    # 最高偏好，等 8 回合
        'Village': (preference=0.3, delay=0),     # 低偏好
    }
    """
    
    def chooseBuy(self, coins, supply, turn):
        """贪心选择最能靠近目标牌组的牌"""
        best_card = None
        best_distance = float('inf')
        for card in supply:
            if card.cost <= coins:
                hypothetical = self.deck + [card]
                dist = distance_to_target(hypothetical)
                if dist < best_distance:
                    best_distance = dist
                    best_card = card
        return best_card
```

### 4.2 进化流程

```python
# 进化循环
population = [random_chromosome() for _ in range(100)]
for generation in range(50):
    # 锦标赛: 每对染色体对打 N 局
    winners = tournament(population, games_per_match=10)
    # 交叉: 两个胜者的染色体混合
    # 变异: 随机微调某些偏好值
    population = breed(winners, mutation_rate=0.1)
```

### 4.3 优势与局限

| 优势 | 局限 |
|------|------|
| ✅ 可以意外发现人类的"非主流"策略 | ❌ 收敛极慢（50 代 × 100 个 × 10 局 = 50,000 局） |
| ✅ 无梯度要求 | ❌ 对随机性敏感 |
| ✅ 适合策略分析和"元游戏" | ❌ 表现弱于 RL |
| ✅ 概念直观 | ❌ 染色体设计高度依赖领域知识 |

---

## 五、MC / SARSA / DQL 对比（2019）

> Stanford CS230: Yang, E. & Kuo, A.

在简化版 Dominion（12 张行动牌）上对比三种 Model-Free RL：

| 算法 | 胜率 vs SmithyBot | 特点 |
|------|-------------------|------|
| **Monte Carlo** | **> 85%** | 最适合回合制游戏 |
| SARSA | ~45% | On-policy，方差大 |
| Deep Q-Learning | ~50% | 不稳定，需要大量调参 |

### 关键发现

1. **奖励设计 > 算法选择**：终端 +50 胜率奖励 + 回合 VP 塑形奖励是最优组合
2. **对手多样性**：对多种对手训练 → 更鲁棒的策略
3. **MC 意外主导**：在长时域回合制游戏中，MC 的完整轨迹回溯比 TD 的逐步引导更有效

---

## 六、方法汇总对比

| 方法 | 训练量 | 胜率水平 | 可解释性 | 上手难度 |
|------|--------|----------|----------|----------|
| Big Money | 0 | 基线 | 完全透明 | 无 |
| Dominiate 优先级 | 0（手工） | 中等 | 高 | 中 |
| 遗传算法 | 50,000+ 局 | 中等 | 中（可查看目标牌组） | 中 |
| DQN + 模仿学习 | ~5,000 局 | 中高 | 低 | 中 |
| Geometric SAC | 大量 | 高 | 低 | 高 |

---

## 七、对六朝的启示

1. **永远先建 Big Money 等价基线**：六朝的"最强简单策略"是什么？只攒某种资源？只打某种牌？——先找到这个基线
2. **优先级列表可转化为 LLM prompt**：Dominiate 的 12 级行动优先级可以直接改写为系统 prompt 的策略指导
3. **模仿学习 + RL 是务实路径**：如果六朝有真人玩家数据，先用行为克隆初始化，再用 RL 微调
4. **MC 方法被低估**：在回合制游戏中，完整轨迹回溯可能比 TD 学习更有效
5. **遗传算法适合策略探索**：当 RL 收敛到局部最优时，遗传算法的多样性可以打开新局面
