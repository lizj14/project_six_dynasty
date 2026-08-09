# Geometric DL + SAC 深度解析

> 论文: "Playing Various Strategies in Dominion with Deep Reinforcement Learning"
> 作者: Jasper Gerigk & Benedikt Engels | 年份: 2023
> 发表: AAAI AIIDE 2023
> 链接: [ojs.aaai.org/index.php/AIIDE/article/view/27518](https://ojs.aaai.org/index.php/AIIDE/article/view/27518)
> 代码: 未公开发布

---

## 一、项目概述

这是**首个完全不依赖启发式（heuristic-free）的学习型 Dominion Agent**。所有决策——包括复杂的交互选择（Throne Room 选哪个动作、Remodel 销毁哪张牌获取哪张牌）——全部由神经网络自主决定。

### 核心数据

| 指标 | 数值 |
|------|------|
| RL 算法 | **Soft Actor-Critic (SAC)** |
| 状态表示 | **几何深度学习（Geometric DL）+ 多重集（Multiset）** |
| 动作空间 | **可变大小**——策略网络仅输出合法动作的概率 |
| 关键成就 | 首个无启发式 Agent；通过课程学习诱导出引擎策略（非自主发现）；揭示了标准RL在长序列决策中的根本性局限 |
| 性能 | Big Money Agent: 73% vs Big Money Bot；Engine Agent: 仅 14% vs Big Money Bot（学会了引擎但打不过纯钱） |

---

## 二、核心创新一：多重集状态表示

### 2.1 为什么不能用普通 MLP

Dominion 的状态天然是**多重集**（multiset）——手牌是 {Copper, Copper, Copper, Estate, Smithy}，而不是 [Copper, Copper, Copper, Estate, Smithy]。

关键区别：
- **序列的 one-hot 编码**：无法表达"有三个 Copper"这一信息的简洁形式
- **多重集**：{Copper: 3, Estate: 1, Smithy: 1} 天然表达了"有什么、各多少张"

### 2.2 几何深度学习方案

使用**等变神经网络**（equivariant neural networks）处理多重集结构：

```python
# 概念性伪代码
class MultisetEncoder(nn.Module):
    """
    输入: {(card_name, count)} 的多重集
    输出: 固定维度的嵌入向量
    
    关键性质: 对输入顺序不敏感
    """
    def __init__(self, n_cards, embed_dim):
        self.card_embedding = nn.Embedding(n_cards, embed_dim)
        
    def forward(self, multiset):
        # 每张牌 → 嵌入向量
        embeddings = self.card_embedding(multiset.card_indices)
        # 每种牌 × 数量 → 加权和（对顺序不敏感）
        weighted = embeddings * multiset.counts.unsqueeze(-1)
        # 全局池化 → 固定维度
        return weighted.sum(dim=0)
```

**优势**：
- 数学上精确表达了"手牌是无序的"这一事实
- 输入维度不随手牌数量变化——无论 5 张还是 50 张手牌，输出维度相同
- 相比全连接网络，参数效率更高

---

## 三、核心创新二：可变动作空间的 SAC

### 3.1 SAC 算法基础：Actor-Critic + Soft（熵正则化）

SAC（Soft Actor-Critic）由 Haarnoja et al. (2018) 提出。它有两个角色：

```
Actor（演员）: 负责"做决策"
  输入: 状态 s + 选项集合 {Village, Smithy, ...}
  输出: 每个选项的概率 → 按概率采样

Critic（评论家）: 负责"评价决策"
  输入: 状态 s + 动作 a
  输出: Q(s, a) → "选这张牌预期能得多少分"
```

训练循环：Actor 选动作 → Critic 打分 → Actor 朝高分的动作调整概率 → 循环。

**Soft 的含义——最大熵强化学习：**

标准 RL（如 DQN）选 Q 值最高的动作（硬 max）。SAC 输出概率分布（软采样）：

```
标准 RL:   Village Q=8.2, Smithy Q=8.1, Silver Q=3.0
           → 只选 Village（必然）

SAC:       Village Q=8.2, Smithy Q=8.1, Silver Q=3.0
           → Village 70%, Smithy 25%, Silver 5%（概率分布）
```

背后的数学：SAC 最大化 **"累计奖励 + 熵"**，而非仅最大化累计奖励。熵（entropy）度量"策略有多不确定"——熵越高，Agent 越倾向于探索多种选项，而非死守当前最优。

这对 Dominion 至关重要：
- Big Money 路径：Silver→Gold→Province，每一步都有明确的局部收益（金币增加），Q 值梯度清晰
- 引擎路径：买 Village（+0 金币）→ 买 Smithy（+0 金币）→ ... → 8 回合后爆发。前几步的 Q 值几乎是 0

SAC 的 Soft 意味着：即使某个动作当前 Q 值不高，只要 Critic 对它的评价"不确定"，Actor 仍会给它一定的探索概率——让 Agent 可能发现那些"短期无收益但长期爆发"的动作序列。虽然论文最终发现 SAC 的随机探索**仍然不足以**自行跳出 Big Money（见第四节），但相比 DQN 等硬性方法，其理论优势是明确的。

---

### 3.2 离散 SAC vs 连续 SAC：三个关键区别

论文用的是**离散 SAC**（Christodoulou 2019），与 Haarnoja 原版**连续 SAC** 有三个根本性差异：

#### 区别一：Actor 的输出

| | 原版 SAC（连续动作） | 离散 SAC（Dominion 场景） |
|---|---|---|
| **输出形式** | (μ, σ) → 高斯分布 | 概率向量 → 类别分布 |
| **采样** | a = μ + σ·ε（ε ~ N(0,1)） | 按概率直接选一个选项 |
| **例子** | 机器人关节："转 0.3±0.05 弧度" | Dominion："60% 打 Village，30% 打 Smithy" |

#### 区别二：是否需要重参数化技巧（Reparameterization Trick）

这是两个版本**数学上最根本的差异**。

原版 SAC 中，Actor 输出的是一个高斯分布，需要对采样出的动作求梯度。但"从分布中采样"这个操作**不可导**——梯度流不过去。原版 SAC 用 reparameterization trick 解决：

```
a = μ + σ · ε    (ε ~ N(0,1))
    ↓
μ 和 σ 是网络输出（可导），ε 是外部噪声（不参与梯度）
→ 梯度可以从 a 流回 μ 和 σ → 端到端训练可行
```

离散 SAC **不需要 trick**。离散动作空间可以穷举——直接算所有动作的加权期望，不需要采样：

```python
# 原版 SAC（连续）——必须采样 + trick
a = mu + sigma * epsilon           # 采样一次
q_value = critic(state, a)         # 评价这个具体的 a
loss = q_value - alpha * log_prob  # 基于采样的损失

# 离散 SAC —— 直接算精确期望，不需要采样
for each action a_i:
    q_i = critic(state, a_i)              # 评价每个动作
    prob_i = actor(state)[i]              # 每个动作的概率

loss = Σ prob_i * (q_i - alpha * log(prob_i))  # 加权求和 = 精确期望
```

连续空间有无穷多个动作，无法枚举 → 必须采样 + trick。离散空间只有十几个动作 → 直接穷举即可。

#### 区别三：熵的计算与目标熵

| | 原版 SAC | 离散 SAC |
|---|---|---|
| **熵公式** | H = −∫ π(a\|s) log π(a\|s) da | H = −Σᵢ π(aᵢ\|s) log π(aᵢ\|s) |
| **计算方式** | 近似估计（用 log σ 近似） | **精确计算**（直接求和，O(n)） |
| **目标熵** | −dim(Action Space) | 论文自定义: −0.5 × log(dim(Available_Actions) − 1) |

论文的目标熵公式 `−0.5 × log(K−1)` 是针对 Dominion 可变动作集的适配：K=3（3 个选项）→ 目标熵 −0.35（很确定）；K=20（20 个选项）→ 目标熵 −1.47（更不确定）。直觉：选项越多，Agent 应该越不确定。

---

### 3.3 论文的统一决策模型：所有选择 = "从集合中选一张牌"

这是论文最巧妙的设计。Dominion 的决策看似多种多样——打牌、买牌、销毁、复制——论文全部统一为一个操作：

> **输入 = 选项集合（卡片多重集）+ 决策类型** → **输出 = 选其中一张**

```
回合示例:

行动阶段:
  决策①: 打哪张行动牌？    选项 = {Village, Smithy, 结束行动}
  → 选 Village

  决策②: 打哪张行动牌？    选项 = {Smithy, 结束行动}       ← Village 已打出
  → 选 Smithy（终端牌，消耗最后 1 行动）

  决策③: 打哪张行动牌？    选项 = {结束行动}              ← 只剩这个
  → 选结束

购买阶段:
  决策④: 买哪张牌？        选项 = {Province, Gold, Silver, ..., 结束购买}
  → 买 Gold
```

关键：如何让同一个网络知道"现在是什么决策"？同一个 Village 出现在选项集合中——它是"可以打的牌"还是"可以买的牌"？为此论文引入**决策类型嵌入（Decision Type Embedding）**：

```
模型输入三样东西:

① 游戏状态表示          → backbone 编码的 32 维向量
② 选项集合              → 每张卡的嵌入 {e_Village, e_Smithy, ...}
③ 决策类型嵌入          → 4 维可学习向量
   ├─ "play_action"      → 当前是在选打哪张牌
   ├─ "buy_card"         → 当前是在选买哪张牌
   ├─ "chapel_trash"     → 当前是在选销毁哪张牌
   ├─ "remodel_gain"     → 当前是在选获取哪张牌（Remodel 销毁后）
   └─ "throne_room_target" → 当前是在选 Throne Room 的复制目标
```

```python
# 概念性伪代码
class UnifiedActorCritic(nn.Module):
    def __init__(self):
        self.backbone = GameStateEncoder()          # 状态 → 32 维
        self.decision_embedding = nn.Embedding(     # 决策类型嵌入
            num_decisions≈6, embed_dim=4
        )
        self.card_embedding = ...                   # 卡牌嵌入（16 维）
        self.head = MLP(...)                        # 评分头
        
    def forward(self, state, options, decision_type):
        state_vec = self.backbone(state)            # [32]
        dec_vec = self.decision_embedding(decision_type)  # [4]
        context = torch.cat([state_vec, dec_vec])   # [36]
        
        scores = []
        for card in options:
            card_emb = self.card_embedding(card)    # [16]
            score = self.head(context, card_emb)    # 标量
            scores.append(score)
        
        return softmax(scores)  # 每个选项的概率
```

所有决策共享网络权重——"打牌"和"买牌"的区别完全由 `decision_embedding` 编码。网络通过学习让不同的 decision_type 激活不同的内部通路。

**论文中约 6 种决策类型：**

| 决策类型 | 触发时机 | 选项集合 | 例子 |
|----------|----------|----------|------|
| `play_action` | 行动阶段 | 手牌中的行动牌 + "结束" | {Village, Smithy, 结束} |
| `buy_card` | 购买阶段 | 供应堆中买得起的牌 + "结束" | {Province, Gold, 结束} |
| `chapel_trash` | 打出 Chapel | 手牌 | {Copper, Estate, Copper} |
| `remodel_trash` | 打出 Remodel（第 1 步） | 手牌 | 同 chapel_trash |
| `remodel_gain` | Remodel 销毁后（第 2 步） | 费用 ≤ 被销毁牌费用+2 的供应牌 | {Gold, Silver, Village, ...} |
| `throne_room_target` | 打出 Throne Room | 手牌中其他行动牌 | {Village, Smithy} |

**多步卡牌的处理**：Remodel 需要选两次（先销毁、再获取），论文拆为两个独立的单步决策：

```
打出 Remodel:
  → 状态机: step = "trash"
  → 模型收到 decision_type = "remodel_trash"，选项 = 手牌
  → 模型选: Copper

  → 状态机: step = "gain", max_cost = 0 + 2 = 2
  → 模型收到 decision_type = "remodel_gain"，选项 = 费用≤2 的供应牌
  → 模型选: Estate

  → 状态机清除
```

论文明确承认这是折中方案：multistep 选择被建模为迭代的单步选择（选项集合每步递减）。虽然增加了学习难度，但避免了设计专门的序列决策架构。

**为什么不直接用固定大小的动作空间（DQN 方案）？**

```
DQN 方案: 输出层 = [346 维] ← 所有可能动作
          → 每回合大部分是非法的 → 需要 action masking → 浪费容量

SAC 方案: 输出层 = [K 维] ← K = 当前合法动作数
          → 只对当前可用的选项评分 → 网络容量只用于"这些选项中哪个最好"
```

---

### 3.4 SAC 更新公式（离散版）

```
Critic:  J(Q) = E[(Q(s,a) - (r + γ V_soft(s')))^2]
         V_soft(s) = Σ_a π(a|s) · [Q(s,a) - α log π(a|s)]

Actor:   J(π) = Σ_a π(a|s) · [α log π(a|s) - Q(s,a)]

α (自动调熵): J(α) = E_a~π[-α log π(a|s) - α · H_target]
```

离散版的关键差异在 `V_soft(s)`：原版连续 SAC 用采样期望 `E_a~π`，离散版用**精确求和** `Σ_a`——因为动作空间有限，直接穷举所有可选动作计算加权和，不需要采样近似。

论文的温度超参数：`c = 0.5`，α 被钳制在 [0, 4] 之间，额外 10% 随机探索。所有 Agent 训练 30 万步，单卡 NVIDIA RTX A4000 ~1 天/Agent。

---

## 四、策略涌现——并非"自主发现"，而是"诱导+迁移"

论文试图让 Agent 学会 Big Money / Rush / Trashing / Engine 四种策略。**关键发现是负面的**：标准 RL（直接优化胜率）**只会收敛到 Big Money**，永远跳不出来。

### 4.1 为什么标准 RL 学不会引擎

论文 Discussion 部分的原话：

> *"SAC's exploration efforts fail to break away from the local maximum."*
> — SAC 的随机探索不足以跳出 Big Money 这个局部最优

原因链：

```
买 Chapel 需要精确的序列:
  ① 早期买 Chapel（误差: 买晚了就废了）
  ② 在有废牌的手牌中打出 Chapel（误差: 没废牌时打出浪费行动）
  ③ 选择正确的牌销毁（误差: 销毁了重要的钱）

每一步出错 → 成绩变差 → RL 学到"别买 Chapel"
Big Money 路径: 买 Silver → 买 Gold → 买 Province
  每步都有明确的局部收益 → RL 轻松学会
```

Agent 需要的精准动作序列太长了，纯随机探索几乎不可能碰巧发现——即便发现了，SAC 的**无记忆随机探索**（每次探索独立采样）也无法维持：
> *"Even when the agent does not overbuy an Action Card due to a random exploration decision, it will do so at the next opportunity, as the random action is unlikely to repeat."*

### 4.2 论文的实际方法：课程学习（Curriculum Learning）

论文自己用的词是 **"trick"（骗）** Agent 学会引擎：

**Step 1 — 预设强力引擎起始牌组：**

```
2× Village, 2× Smithy, 1× Festival, 1× Chapel,
3× Laboratory, 1× Throne Room, 2× Gold
```

这组 12 张牌本身就能**每回合稳定买一张 Province**。

**Step 2 — 渐进混合训练：**

```
每局开始时:
  75% 的游戏 → 起始牌组混入引擎卡牌（按随机概率 p_engine 采样）
  25% 的游戏 → 标准起始牌组（7 Copper + 3 Estate）
```

**Step 3 — 行为迁移：**

> *"Since playing the Engine is optimal and quicker than Big Money in many of these positions, the agent will learn such a strategy for those positions and then apply it to the others."*

在"引擎已成型"的起始状态上，Agent 发现引擎比 Big Money 更快更优 → 学会了引擎的行为模式 → 然后**泛化到标准起始局**。

### 4.3 判断"学会了"的证据

论文没有做"出牌顺序分析"或"对抗验证"来严格证明策略涌现（这是我们上一轮讨论的假设方法——论文实际没用）。论文用的是**终局牌组构成分析（Figure 2）**作为主要证据：

| 卡牌类型 | Big Money Agent | Engine Agent |
|----------|:---:|:---:|
| **Action Cards** | 15% | **60%** |
| Treasure Cards | 62% | 22% |
| 剩余 Coppers | 多 | **2.57 张** |
| 剩余 Estates | 多 | **1.05 张** |
| 剩余 Curses | — | 0.05 张 |

Agent 具体使用了这些卡牌（论文明确列举）：
- **抽牌链**：Laboratory + Smithy
- **提供行动**：Village + Throne Room + Festival
- **销毁废牌**：Chapel → 销毁 Copper 和 Curse
- **金币来源**：Festival + Silver + Gold（Gold 部分通过 Bandit 获得）

### 4.4 实际对战表现（远不如我之前描述的）

| 对手 | Engine Agent 胜率 |
|------|:---:|
| Big Money Bot | **14%** |
| Gardens Bot | 52% |
| Random Bot | 输 6%（过度销毁导致 0 分） |

**关键局限**：Agent 有时销毁得太狠——Chapel 把所有 Copper 销毁了，导致没钱买东西 → 0 分告终。论文指出这是因为 Chapel 的销毁决策仍有启发式（heuristic）兜底，Agent 自己还不会控制销毁的"度"。

### 4.5 核心洞察

这不是一篇"Agent 自己发现了人类策略"的论文。它的真正贡献是**反面发现**：

| 发现 | 含义 |
|------|------|
| 标准 RL → **只收敛到 Big Money** | Dominion 的 reward 结构天然不利于引擎策略 |
| SAC 探索**不足以**跳出局部最优 | 需要更智能的探索方法（如 temporally correlated exploration） |
| 引擎策略需要**精确的卡牌获取序列** | 每一步单独看都可能是负收益，序列的精度要求远超随机探索能力 |
| 课程学习可以绕过，但**不够强** | 引擎 Agent 仍弱于 Big Money Bot（14% 胜率）|

> 论文最后一句话：*"The next level of performance will be achieved by agents aware of the sequence in which decisions are made."*
> — 要想真正学会引擎，Agent 必须理解**决策之间的序列关系**，而不是把每个决策独立看待。

---

## 五、性能与局限

### 性能层级（修正）

```
人类顶级玩家
    ↑
搜索型方法 (MCTS + 手动启发式)          ← 仍强于学习型
    ↑
Big Money Bot                        ← 竟比 Engine Agent 强得多
    ↑
Geometric SAC Big Money Agent (73% vs BM)
    ↑
Geometric SAC Engine Agent (14% vs BM)  ← 学会了引擎但打不过纯钱
    ↑
DQN / SARSA 等
```

**重要修正**：论文的 Engine Agent **不是"最强学习型"**——它学会了引擎策略但实际对战只有 14% 胜率 vs Big Money。真正强的是论文训练的 Big Money Agent（73% vs Big Money Bot），但它本质上仍是 Big Money 变体。

### 局限

1. **Throne Room 深度限制**：仅支持 1 层嵌套（Throne Room → 另一张牌），不支持 Throne Room → Throne Room 的递归
2. **训练时间长**：SAC 采样效率较低，需要大量对局
3. **不敌搜索型方法**：在需要精确计算的场景（如终局"我该买 Province 还是 Duchy"），搜索型方法仍有优势
4. **代码未公开**：社区无法复现或改进

---

## 六、对六朝的启示

1. **多重集表示**：六朝的手牌/场上单位也天然是多集——借鉴 Geometric DL 的无序编码
2. **可变动作空间**：SAC 的可变 actor 设计适用于任何"手牌决定合法动作"的游戏
3. **标准 RL 学不会复杂策略**：这是论文最重要的教训——在长序列+精确时序要求的游戏中，标准 RL（包括 SAC 的随机探索）天然收敛到"简单但次优"的策略
4. **课程学习是必要手段**：要学复杂策略必须先"骗" Agent 进入正确区域——给好的起始状态让它体验策略的价值，再逐步撤掉辅助
5. **序列感知是缺失的关键**：论文最后一句话指出——独立决策模型无法捕获"先买 Chapel → 等 Copper/Esate 在手上 → 再打出"这种跨多回合的序列逻辑。这对六朝意味着：Agent 架构必须捕获决策之间的时序依赖
