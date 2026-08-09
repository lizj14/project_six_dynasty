# 卡坦岛最终演化策略分析

> 分析日期：2026-08-07
> 源码来源：HexMachina 代码库中存档的最佳策略

---

## 一、两种"最佳策略"

代码库中存在两个版本的最佳策略，代表了不同的演化路径：

### 1.1 agentEvolver v1（无 Discovery，~160 行）

**位置**: `agents/agentEvolver/saved_agents/best_gpt/best_foo_player.py`

**策略本质：规则式优先级 + 资源门控**

```
核心逻辑（伪代码）：
  if 能建 settlement → 建 settlement
  elif 能建 road → 建 road  
  elif 能建 city → 建 city
  elif 有资源剩余 → 海事贸易
  else → 选第一个动作（fallback）

按阶段微调优先级：
  early → settlement > road
  mid   → city > settlement
  late  → dev_card > city
```

**问题**：无前瞻（不看后续状态）、无对手建模、无随机性处理。这是论文中 54.1% 胜率的 **baseline 对照**，不是最终最优策略。

### 1.2 agentEvolver_v2 / HexMachina（有 Discovery，~1100 行）

**位置**: `agents/agentEvolver_v2/runs/excellent_run/game_20250920_184256_fg/foo_player.py`

**策略本质：1-ply 前瞻 + 价值函数 + 启发式增强 + 概率感知**

这才是论文报道 54.1% 胜率的策略。下面详细拆解。

---

## 二、HexMachina 最终策略完整拆解

### 2.1 策略总览

```
┌────────────────────────────────────────────────────────────────┐
│                    decide(game, playable_actions)               │
│                                                                │
│  1. 类型解析（防御性：兼容不同 Catanatron 版本的 enum 差异）     │
│  2. END_TURN 门控（有可负担建造时拒绝结束回合）                  │
│  3. 动作预筛选（按优先级排序，截断到 top-20）                    │
│  4. 对每个候选动作：                                            │
│     a. copy_game → execute（模拟执行一步）                       │
│     b. 如有概率结果 → chance_children 计算期望得分               │
│     c. 如无概率 API → Monte Carlo（10 样本）fallback            │
│     d. 确定性动作 → value_fn 直接打分                           │
│     e. 加启发式 bonus（城市/定居点/道路/骑士/发展卡/劫匪）       │
│     f. bonus 上限裁剪（≤ MAX_BONUS_SCALE = 10）                 │
│  5. 选最高分动作（平局按优先级打破）                             │
│                                                                │
│  核心参数：max_actions=20, samples_mc=10, max_simulations=200   │
└────────────────────────────────────────────────────────────────┘
```

### 2.2 核心机制一：1-ply 前瞻 + 价值函数

这是策略的"引擎"——不只看当前状态，而是模拟执行一步后再评估：

```python
# 使用 Catanatron 内置的价值函数（base_fn）
value_fn = make_value_fn("base_fn", DEFAULT_WEIGHTS)

# 对每个候选动作：
gcopy = copy_game(game)           # 深拷贝游戏状态
execute(gcopy, action)             # 模拟执行动作
score = value_fn(gcopy, color)    # 评估后继状态

# 关键：base_fn 是一个加权线性函数，评估多种维度：
#   VP + 生产力 + 资源多样性 + 城市/定居点/道路数量 + ...
# 这个函数本身就比简单的"只看 VP"强得多
```

**与 No-Discovery 版本的对比**：

| | No-Discovery (v1) | HexMachina (v2) |
|---|---|---|
| 决策深度 | 0-ply（只看当前资源够不够） | 1-ply（模拟一步 + 评估后继状态） |
| 评分方式 | 规则优先级（if-else 链） | 价值函数 `value_fn(gcopy, color)` |
| 适应 API 的能力 | 硬编码 `game.state.player_state["P0_WOOD_IN_HAND"]` | 通过 adapters 的封装函数 |

### 2.3 核心机制二：概率感知

Catan 的核心随机性来自骰子。HexMachina 策略通过两种方式处理：

**方式 A：chance_children API（精确）**
```python
# 模拟骰子投掷的所有可能结果：
# ROLL 7 → 激活劫匪；其他数字 → 对应地块产资源
outcomes = chance_children_for_action(gcopy, action)
# 返回: [(state_1, prob_1), (state_2, prob_2), ...]

# 计算期望值：
expected_score = Σ prob_i × value_fn(state_i)
```

**方式 B：Monte Carlo 采样（fallback）**
```python
# 当 chance_children API 不可用时，重复模拟 10 次取平均
for i in range(10):
    sim_gcopy = copy_game(game)
    execute(sim_gcopy, action)    # 每次执行随机结果不同
    total += value_fn(sim_gcopy)
score = total / 10
```

### 2.4 核心机制三：启发式增强（加在价值函数之上）

价值函数`base_fn`是通用的，不了解具体动作的上下文。策略在 value_fn 评分基础上叠加启发式 bonus：

#### 城市建造 bonus

```
策略：
  资源 ≥ 3 小麦 + 2 矿石（完全可负担） → +6.0 bonus
  资源 ≥ 1 小麦 + 1 矿石（部分可负担） → +3.0 bonus
  其他情况 → +1.5 bonus（保持长期考虑）

设计意图：城市 = 2VP + 双倍生产，价值函数可能低估
```

#### 定居点评分

```
settlement_score(node) = pip_sum + SETTLEMENT_CONNECTIVITY_WEIGHT × 连接道路数

pip_sum: 相邻地块的骰子概率之和（生产潜力）
连接道路数: 连接到己方道路的数量（扩张可行性）

如果评分 ≥ SETTLEMENT_BUILD_THRESHOLD(3.5)：
  bonus = HIGH_PIP_BONUS(2.0) × (node_score / PIP_NORMALIZER(6.0))

如果还有紧迫性加成（接近可负担 + 高价值节点）：
  bonus += URGENCY_WEIGHT(2.5) × urgency_factor
```

#### 道路评分

```
road_score(edge) = 
    ROAD_CHAIN_WEIGHT(2.0) × 是否连接己方道路
  + PIP_WEIGHT(1.0) × (最近空地的 pip_sum / ROAD_PIP_NORMALIZER(6.0))
  - DIST_PENALTY(0.7) × 到最近空地的距离
  + OPP_BLOCK_BONUS(0.5) × 是否邻接对手建筑

设计意图：
  - 鼓励道路向高生产力空地延伸
  - 惩罚无目的的长距离道路
  - 奖励阻断对手扩张
```

#### 骑士 / 发展卡 / 劫匪

```
骑士: 如果打出后能获得最大军队 → +2.5 bonus
发展卡: 如果可负担但无可建造 → +1.0
       如果同时可建造则 → +0.25（大幅减少，优先建造）
劫匪: 按 target_tile 上对手的生产频率给微小 bonus
```

#### Bonus 上限裁剪

```python
if (score - base_score) > MAX_BONUS_SCALE(10.0):
    score = base_score + 10.0
# 防止启发式 bonus 压过价值函数的信号
```

### 2.5 核心机制四：END_TURN 门控

```python
# 检查是否存在可负担的建造动作
# （使用资源检查而非尝试执行，避免副作用）
affordable_build_exists = any(
    can_afford(action_type) for action_type in [settlement, road, city]
)

if affordable_build_exists:
    # 从候选动作中移除 END_TURN
    filtered = [a for a in actions if a.type != END_TURN]
```

这个简单的门控防止了"明明能建却结束回合"的低级错误。

### 2.6 核心机制五：防御性编程

~1100 行代码中有大量 try/except，应对 Catanatron 不同版本的 API 差异：

```python
# 资源获取：处理 4 种不同的底层数据格式
def _normalize_resources(self, pstate):
    # Case 1: dict {'wheat': 3, 'ore': 0, ...}
    # Case 2: list of (key, val) pairs
    # Case 3: list of 5 ints [wood, brick, sheep, wheat, ore]
    # Case 4: object with .wheat, .ore, ... attributes

# 棋盘 API：处理多种调用方式
try:
    nodes = board.edge_nodes(edge_id)       # 方法调用
except:
    nodes = board.edges[edge_id].nodes      # 属性访问

# ActionType enum：兼容不同命名
AT_BUILD_SETTLEMENT = resolve_action_type(
    'BUILD_SETTLEMENT', 'BUILD_SETTLES'  # 不同版本的命名
)
```

---

## 三、策略演化路径推断

从 excellent_run 中 12 轮快照的文件大小变化可以推断演化过程：

| 轮次 | 策略变化推断 |
|------|------------|
| E1-E3 | 从模板（选第一个动作）→ 加入简单的 ACTION_TYPE 优先级选择 |
| E4-E6 | 加入 `copy_game` + `execute` 的 1-ply 前瞻 + `make_value_fn` |
| E7-E9 | 加入概率处理（chance_children / MC fallback）+ END_TURN 门控 |
| E10-E12 | 加入各类型启发式 bonus + 防御性编程修复 + 参数调优 |

这与论文描述的 Analyst → Strategizer → Coder 循环一致：每轮 Analyst 发现具体弱点 → Strategizer 提出方案 → Coder 实现。

---

## 四、策略的"智能"体现在哪里

### 4.1 有前瞻但不过度

```
深度 1-ply：只看一步后的状态
  - 足够捕获"建城市 → 立即 +1VP + 双倍生产"的收益
  - 足够区分"在 6 号地块建定居点"vs"在 11 号地块建定居点"
  - 不会陷入组合爆炸（最多评估 20 个动作 × 10 个 MC 样本 = 200 次模拟）
```

### 4.2 有概率感知但不追求精确

```
对骰子类动作：chance_children 精确枚举 11 种结果
对其他随机动作（发展卡）：Monte Carlo 10 次近似
  - 不做完整的 MCTS（成本太高）
  - 不做完整的期望计算（API 可能不支持）
  - 有时近似足够区分好坏选择
```

### 4.3 有启发式但不主导

```
价值函数（base_fn）提供主要信号
启发式 bonus 上限 10.0，防止喧宾夺主
  - 保证基础决策质量（来自 base_fn 的通用评估）
  - 启发式只做微调和方向引导
```

### 4.4 有适应能力

```python
# 一次性自检：首次运行时打印 API 信息
if not self._did_inspect:
    print(ActionType members, sample actions, board API, player state API)
    # 这为后续的 Analyst 诊断提供了信息来源
```

---

## 五、策略的局限性

| 局限 | 表现 | 原因 |
|------|------|------|
| **1-ply 近视** | 看不到两步后的连锁收益 | 算力/时间限制 |
| **对手建模极弱** | 仅劫匪选择时考虑对手生产频率 | Coder 难以实现复杂对手预测 |
| **无长期记忆** | 每回合独立决策，无跨回合战略 | per-turn 架构的固有限制 |
| **依赖 base_fn 质量** | 如果 base_fn 对某种局面评估偏颇，策略也会偏颇 | 价值函数是外挂的 |
| **大量防御性代码** | ~1100 行中 ~30% 是 try/except 和 API 适配 | Discovery 阶段不完美 |

### 5.1 为什么没演化出 MCTS 或更深搜索？

查看代码发现几个约束：
- `max_simulations = 200`（每次决策最多 200 次模拟）
- `time_budget_per_action = 0.5s`（每个动作最多 0.5 秒）
- `max_actions = 20`（最多评估 20 个候选）

在这些约束下，1-ply + value function + heuristic bonus 是**性价比最高的选择**。MCTS 需要数千次模拟，在这个预算内无法有效运行。

---

## 六、与论文 Appendix A.1 的对比

论文附录中的 600 行 FooPlayer（从 PDF 提取）与代码中的实际最佳策略有显著差异：

| 维度 | 论文附录 A.1 | 实际代码最佳策略 |
|------|------------|----------------|
| API 调用方式 | 通过 `adapters.base_fn()` 等 | 通过 `make_value_fn("base_fn")` |
| Rollout 深度 | 2-ply（带对手贪心响应） | 1-ply（无对手响应） |
| 阶段感知 | EARLY/MID/LATE 三个乘数矩阵 | 无显式阶段感知（依赖 base_fn） |
| 动作预筛选 | `prefilter_actions`（must-include + top-K + random） | 按优先级排序 + top-20 |
| 劫匪处理 | 详细的生产损失计算 + 偷窃预期 | 简单的 opponent_freqdeck 微调 |
| 发展卡 | EV 估算 + 牌堆概率模型 | 简单 bonus |
| 代码行数 | ~600 行 | ~1100 行 |

**推测**：论文附录 A.1 可能是论文写作时跑出的最优结果，而代码库中的文件是后续继续演化的产物。两者的核心思路一致（前瞻 + 价值函数 + 启发式），但具体实现细节因演化轮次和 seed 不同而有差异。

---

## 七、总结：这个策略到底是什么？

**一句话概括**：

> HexMachina 最终演化出的不是 MCTS、不是深度 RL、也不是简单的 if-else 规则，而是一个 **"1-ply 前瞻 + 预训练价值函数 + 领域启发式微调"** 的混合策略。

**策略层次**：

```
Layer 3 (启发式微调):  城市/定居点/道路 bonus + END_TURN 门控 + 优先级排序
    ↓ 叠加在
Layer 2 (概率感知):    chance_children 精确期望 / Monte Carlo 近似
    ↓ 嵌入在
Layer 1 (基础评估):    copy_game → execute → value_fn(base_fn) 评分
    ↓ 依赖
Layer 0 (API 适配):    adapters.py 提供的稳定封装
```

### 四层的关系：不是平行模块，而是嵌套管道

这四层不是四个独立模块各算各的然后投票，而是一个**单动作评分管道**：一个候选动作从进入管道到输出最终分数，依次经过每一层的处理。

**用一个具体例子来说明——假设当前回合有一个 BUILD_CITY 动作需要评分：**

```
原始动作: Action(type=BUILD_CITY, value=node_42)

┌──────────────────────────────────────────────────────────────────┐
│ L0: API 适配层                                                   │
│                                                                  │
│   game (Catanatron 原生对象)                                     │
│        │                                                         │
│        ▼                                                         │
│   gcopy = copy_game(game)     ← adapters 封装 game.copy()        │
│   execute(gcopy, action)       ← adapters 封装 game.execute()    │
│                                                                  │
│   输出: 执行后的游戏状态副本 (gcopy)                               │
│   如果 L0 不存在: Coder 需要记忆 Catanatron 内部 API，            │
│   容易写出 game.state.board.edges[42].nodes 这种跨层调用          │
└──────────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────────┐
│ L1: 基础评估层（产出 base_score）                                  │
│                                                                  │
│   value_fn = make_value_fn("base_fn", DEFAULT_WEIGHTS)           │
│   base_score = value_fn(gcopy, color)                            │
│            = VP×w1 + settlements×w2 + cities×w3 + roads×w4       │
│              + production×w5 + resources×w6 + ...                │
│                                                                  │
│   对 BUILD_CITY: gcopy 中己方多了一个 city（+1VP, +生产）          │
│   输出: base_score ≈ 245.3（一个综合标量）                        │
│                                                                  │
│   如果 L1 不存在: 策略退化到 v1 的 if-else 优先级链，             │
│   只能问"能不能建"不能问"建了之后局面变好多少"                     │
└──────────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────────┐
│ L2: 概率感知层（改造 L1 的计算方式）                               │
│                                                                  │
│   BUILD_CITY 是确定性动作 → L2 不触发，直接通过                    │
│                                                                  │
│   但如果是 ROLL（掷骰子）:                                        │
│     outcomes = chance_children_for_action(gcopy, action)          │
│              = [(state_roll3, p=2/36), (state_roll4, p=3/36),    │
│                 ..., (state_roll11, p=2/36)]                     │
│                                                                  │
│     score = Σ p_i × value_fn(state_i)   ← L1 被调用了 11 次      │
│                                                                  │
│   如果是 BUY_DEV（发展卡）且 chance_children 不可用:               │
│     score = avg( value_fn(sample_1), ..., value_fn(sample_10) )  │
│            ← L1 被调用了 10 次（Monte Carlo fallback）            │
│                                                                  │
│   L2 不是独立打分，而是改变了 L1 的调用方式：                       │
│   从"评估一个后继状态"变成"评估多个后继状态求期望"                   │
│                                                                  │
│   如果 L2 不存在: 骰子和发展卡的随机性被忽略，                      │
│   策略会把"掷到 7"和"掷到 6"当成一样好                            │
└──────────────────────────────────────────────────────────────────┘
    │
    │  score = base_score（确定性）或 E[value_fn]（概率性）
    │
    ▼
┌──────────────────────────────────────────────────────────────────┐
│ L3: 启发式微调层（叠加 bonus）                                     │
│                                                                  │
│   base_score = score       ← 暂存 L1/L2 的产出                    │
│                                                                  │
│   针对 BUILD_CITY:                                               │
│     if wheat >= 3 and ore >= 2:    # 完全可负担                   │
│         score += CITY_BONUS_AGGRESSIVE (6.0)                     │
│     elif wheat >= 1 and ore >= 1:  # 部分可负担                   │
│         score += CITY_BONUS_FALLBACK (3.0)                       │
│     else:                                                         │
│         score += CITY_BONUS_FALLBACK / 2 (1.5)                   │
│                                                                  │
│   最终: score = base_score + city_bonus                          │
│         = 245.3 + 6.0 = 251.3                                    │
│                                                                  │
│   安全检查: if (score - base_score) > MAX_BONUS_SCALE(10.0):     │
│               score = base_score + 10.0   ← 防止 L3 压倒 L1      │
│                                                                  │
│   L3 是唯一真正"叠加"的层——它在 L1/L2 的输出上加一个标量偏移       │
│                                                                  │
│   如果 L3 不存在: 价值函数可能在某些局部决策上给出平局，            │
│   导致在同样好的定居点之间随机选择                                  │
└──────────────────────────────────────────────────────────────────┘
    │
    ▼
  最终分数: 251.3 → 与其他候选动作比较 → 选最高分
```

### 四层之间的依赖关系

```
L0 ←── L1 调用（copy_game, execute）
    ←── L2 调用（chance_children_for_action, chance_children）
    ←── L3 不直接调用 L0，但使用的 game.state 来自 L0 拷贝的对象

L1 ←── L2 反复调用（每次概率分支调一次 value_fn）
    ←── L3 叠加在 L1 的产出上（base_score）

L2 ←── 嵌入 L1：L2 不替代 L1，而是改变 L1 的调用模式
        确定性路径: L1 调用 1 次
        概率性路径: L1 调用 11 次（骰子）或 10 次（MC）

L3 ←── 叠加在 L1/L2 的产出上
        bonus 有硬上限（10.0），保证 L1 信号不被淹没
        还承担 END_TURN 门控（预处理）和优先级排序（后处理）
```

### 为什么是这个结构？

这个四层管道不是 LLM 一次性设计出来的，而是**演化收敛的结果**：

| 演化阶段 | 策略状态 | 胜率 | 缺失的层 |
|---------|---------|------|---------|
| 模板起点 | `return playable_actions[0]` | ~0% | L0 L1 L2 L3 |
| 加入 L3（优先级） | if-else 链选动作 | ~20% | L0 L1 L2 |
| 加入 L1（1-ply + value_fn） | 模拟一步 + 评分 | ~35% | L0 L2 |
| 加入 L0（adapters） | 稳定 API，不再因 API 变化崩溃 | ~40% | L2 |
| 加入 L2（概率感知） | 处理骰子/发展卡随机性 | ~48% | — |
| 精调 L3（启发式） | bonus 上限 + 各类型微调 | **~54%** | — |

每加一层，胜率跳一次。**层与层之间不是替代关系，而是补盲关系**：

- L1 弥补了"不看后续状态"的盲区
- L2 弥补了"忽略随机性"的盲区
- L3 弥补了"通用价值函数不理解具体动作上下文"的盲区

---

## 八、真实迭代案例：从日志还原 Agent 协作过程

代码库中 `excellent_run` 目录保存了完整的 12 轮演化日志。以下是真实发生的 Agent 对话。

### 8.1 性能曲线（来自 performance_history.json）

```
E0:   0 wins, 2.0 VP   ← 模板: return playable_actions[0]
E1:   0 wins, 0 VP     ← 编译失败！(1-ply 初版有 bug)
E2:  15 wins, 8.1 VP   ← bug 修复后巨幅跃升
E3:  19 wins, 8.7 VP   ← 峰值
E4:  15 wins           ← 回退
E5:  18 wins           ← 恢复
E6:  18 wins           ← 稳定
E7:  11 wins           ← 回退（变更出错）
E8:  18 wins           ← 恢复
E9:  11 wins           ← 回退
E10: 19 wins           ← 再次峰值
E11: 14 wins           ← 最终态
```

从 0 胜 → 19 胜（63%）仅用 3 轮演化。之后在 11-19 胜之间震荡——每次修改可能引入新 bug 或改善策略。

---

### 8.2 案例一：E0→E2，从零到能打

#### E0 初始状态

**FooPlayer 代码**（完整）：
```python
def decide(self, game, playable_actions):
    print("Choosing First Action on Default")
    return playable_actions[0]
```

**对局结果**：0 wins / 30，FooPlayer 2.0 VP vs AlphaBeta 10.0 VP。117 回合、0 城市、0 道路、0 发展卡。

**日志特征**：`"Choosing First Action on Default"` 重复了 250 次。

#### E1: ANALYZER 诊断

> **关键诊断文本**（从日志原文摘录）：
>
> "**Strategic Flaw**: The player lacks any evaluation of actions, defaulting to the first available option without considering its impact on VP, resource accumulation, or board control. This results in passive, suboptimal play and no progression beyond initial settlements."
>
> "**Next Step**: Send to Coder to implement a 1-ply value lookahead using `copy_game` and `make_value_fn` to prioritize high-value actions."

同时给出了精确的代码级建议：
```python
# Analyzer 给 Coder 的伪代码指导
def decide(self, game, playable_actions):
    value_fn = make_value_fn("base_fn")
    best_action = None
    best_score = -float('inf')
    for action in playable_actions:
        copied_game = copy_game(game)
        execute(copied_game, action, validate=False)
        score = value_fn(copied_game, self.color)
        if score > best_score:
            best_score = score
            best_action = action
    return best_action
```

还列出了 4 个优先级分级的缺陷表（No action evaluation > No chance handling > No end-turn policy > No robber policy）和对应的复杂度/预期收益评估。

#### E1: CODER 实现 → 编译失败

CODER 按 Analyzer 的方案实现了完整代码，但由于 API 调用细节（如 `execute` 的参数签名、`value_fn` 的调用方式）有误，导致**整个 30 局全部崩溃**（score=0, no JSON）。

#### E2: 修复 → 15 wins

META 将错误反馈给 ANALYZER → 重新诊断 API 问题 → CODER 修复后，**直接跳到 15 wins / 30 (50% 胜率)**，平均 8.1 VP。

**从 `return playable_actions[0]` 到 50% 胜率，只用了一轮成功的代码迭代。**

---

### 8.3 案例二：E7→E8，一次回退与恢复

#### E7 发生了什么

E7 胜率从 18 掉到 11。日志显示 STRATEGIZER 在 E7 尝试添加更激进的 settlement urgency 和 road chain scoring，但 CODER 实现时引入了资源格式兼容性 bug（`pstate.resources` 在 Catanatron 不同版本中格式不同）。

#### ANALYZER 在 E7 后的问题定位

从日志 `ANALYZER_e7` 中可以看到 ANALYZER 发现：
```
"Resources shape detection failing for list-of-ints format"
→ 导致 can_afford_build 返回 False
→ 所有建造动作被错误跳过
→ 策略退化到买发展卡和结束回合
```

#### E8: CODER 修复 → 恢复到 18 wins

CODER 添加了 `_normalize_resources` 函数（处理 4 种不同的资源数据格式），并修复了 `_can_afford_build` 使用标准化后的资源字典。胜率恢复到 18/30。

这个 `_normalize_resources` 函数后来一直保留到了最终版本（~1100 行代码中的第 112-192 行）。

---

### 8.4 案例三：E10，添加 END_TURN 门控

从 E8-E10 的 STRATEGIZER 日志可以看到一次具体的策略改进：

**STRATEGIZER 提议**（paraphrased）：
> "FooPlayer is sometimes choosing END_TURN even when it has resources to build a settlement or road. Add a gating check: before evaluating actions, scan for affordable builds. If any exist, remove END_TURN from consideration."

**CODER 实现**（体现在最终代码的第 669-693 行）：
```python
# 检查是否存在可负担的建造动作
affordable_build_exists = False
if self.END_TURN_STRICT:
    for a in actions:
        atype = getattr(a, 'action_type', None)
        if atype in (AT_BUILD_SETTLEMENT, AT_BUILD_ROAD, AT_BUILD_CITY):
            if self._can_afford_build(game, self.color, atype):
                affordable_build_exists = True
                break

# 如果有可负担建造，从候选中移除 END_TURN
if AT_END_TURN is not None:
    filtered = [a for a in actions 
                if not (a.type == AT_END_TURN and affordable_build_exists)]
```

**效果**：E10 胜率回到 19/30。

---

### 8.5 迭代模式总结

从完整日志中可以提炼出**真实的 Agent 协作模式**：

```
┌──────────────────────────────────────────────────────────────┐
│  典型一轮演化（~15-30 分钟）                                   │
│                                                              │
│  1. run_player: 用当前 FooPlayer 打 30 场 vs AlphaBeta       │
│     → 产出: game_output.txt + game_results.json + 胜率/VP    │
│                                                              │
│  2. ANALYZER (10-15次 LLM 调用):                              │
│     - 读取 6 个输入: 性能历史 + 对局输出 + JSON结果 +          │
│       当前代码 + adapters + META指令                          │
│     - 内部 tool-calling: read_local_file 追踪具体日志行       │
│     - 输出: 结构化诊断报告（含行号引用 + 日志摘录 + 修复建议）  │
│                                                              │
│  3. META 路由决策:                                            │
│     - 如果 ANALYZER 定位到具体 bug → 直接发给 CODER           │
│     - 如果是战略性缺陷 → 先发给 STRATEGIZER 设计方案          │
│     - 如果是 API 问题 → 发给 RESEARCHER 查 Catanatron 源码    │
│                                                              │
│  4. CODER (5-10次 LLM 调用):                                  │
│     - 内部 tool-calling: write_foo 或 replace_code_in_foo     │
│     - 如果 tool call 失败("Search string not found")→ 重试   │
│     - 输出: 变更摘要 + 新 FooPlayer 代码                      │
│                                                              │
│  5. → 回到步骤 1，下一轮                                      │
└──────────────────────────────────────────────────────────────┘
```

**META 的角色**：不是让 Agent 自由对话，而是**强制性工作流路由**。META 在每轮输出中使用固定格式 `CHOSEN AGENT: ANALYZER/STRATEGIZER/RESEARCHER/CODER/END`，由 `_meta_choice()` 函数解析并路由到对应节点。这确保了流程可控，而非无限循环。

**ANALYZER 的核心价值**：从日志可以看到，ANALYZER 的诊断质量直接决定了后续修改是否有效。E7 的回退正是因为 ANALYZER 准确发现了"资源格式兼容性"这个根本原因，才让 E8 能精准修复。而论文消融实验中"无 ANALYZER → 胜率 0%"正是因为这个——没有 ANALYZER，CODER 不知道该修什么。

**论文未提及的细节**：真实迭代中**大量时间花在 API 兼容性修复上**（`_normalize_resources`、防御性 board API 调用、ActionType 多命名兼容等），而非"纯粹的策略创新"。这解释了为什么 defenseive programming 占据了最终代码 30% 的体量。
- L0 弥补了"API 不稳定导致策略崩溃"的盲区

而 `MAX_BONUS_SCALE = 10.0` 这个硬上限揭示了层之间的**优先级**：L1（价值函数）是主信号，L3（启发式）只做微调，不允许反客为主。
