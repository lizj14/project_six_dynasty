# BRASS_PARL — 传统强化学习框架深度分析

> 仓库: [github.com/qikahh/BRASS_PARL](https://github.com/qikahh/BRASS_PARL)
> 作者: Yunfei Zhao (qikahh) | 唯一提交: 2025-05-06
> 语言: Python 93.4% + JavaScript 5.6% | Fork: 0

---

## 一、项目结构

```
BRASS_PARL-master/  (~30 个文件, ~3000 行)
├── env/                    # 游戏环境（最强部分, ~1200 行）
│   ├── factory.py          # 6 种工厂, 多态类层次 (443 行)
│   ├── city.py             # 22 个城市 + 友善原则 (290 行)
│   ├── road.py             # 39 条道路 + 时代限制 (274 行)
│   ├── birmingham_map.py   # 地图核心: BFS 资源网络、建造/售卖逻辑 (781 行)
│   ├── market_resource.py  # 煤/铁动态定价市场 (132 行)
│   └── era.py              # 运河/铁路两时代枚举
├── player/                 # 玩家系统
│   ├── player.py           # Player + PersonalBoard, 7 种行动类型 (208 行)
│   └── card.py             # 卡牌系统: 地点/类型/万能卡 (108 行)
├── agent/                  # RL 系统（最弱部分, ~1400 行）
│   ├── birmingham_model.py # MLP 网络: 5150→2048→1024→512 (87 行)
│   ├── birmingham_algorithm.py # REINFORCE 算法 (178 行)
│   ├── rl_agent.py         # Agent 封装: 特征工程 + 动作采样 (922 行)
│   └── train.py            # 训练入口: self-play + REINFORCE (251 行)
├── birmingham.py           # 游戏主控: BirminghamGame 类 (745 行)
├── apps_demo.py            # Flask + SocketIO Web 可视化 (91 行)
├── game_dict.json          # 游戏状态快照（调试用）
└── utils/utils.py          # 仅 4 行: seed_everything
```

---

## 二、游戏环境：规则实现质量

`env/` 层是这项目真正的价值所在。完整实现了 Brass: Birmingham 的几乎全部规则。

### 2.1 6 种工厂的多态实现 (factory.py)

```python
class Factory:     # 基类, 定义接口
class CoalMine:    # 4 级, 费用 [5,7,8,10], 产煤 [2,3,4,5]
class IronWork:    # 4 级, 费用 [5,7,9,12], 产铁 [4,4,5,6], 需 1 煤
class Brewery:     # 4 级, 费用 [5,7,9,9], 产酒 1-2 (取决于修建时代)
class Manufacturer:# 8 级, 费用差异大, 售卖需 0-2 酒
class Pottery:     # 5 级, 1/3 级不可研发
class CottonMill:  # 4 级, 费用 [12,14,16,18], 售卖需 1 酒
```

每种工厂实现了: `get_construction_cost()` / `get_construction_require()` / `get_sell_income()` / `get_sell_score()` / `get_road_score()` / `get_sell_require()` / `produce()` / `flip()`

**验证结果**: 工厂费用、资源消耗、收入、分数、路分均与官方规则匹配。

### 2.2 资源网络：BFS 最短距离 (birmingham_map.py)

```python
def find_coal(self, name, player=None):
    """
    BFS 搜索与当前城市/道路相连的煤厂, 使用最短距离优先:
    1. 相连的工业城市中存在未用完的煤 → 最近优先
    2. 无相连煤厂 → 从市场购买（价格更高）
    3. 同等距离多个可选 → 优先自己的煤厂
    """
    # 使用队列实现 BFS, 记录每层的城市和距离
    while unvisited_cities:
        city_name, distance = unvisited_cities.pop()
        if coal_distance >= 0 and distance > coal_distance:
            break
        # 检查该城市是否有未用完的煤
        for pos, factory in enumerate(city.factories):
            if factory and factory.factory_type == COAL_MINE and factory.resources["coal"] > 0:
                # 优先选择自己的煤厂
                ...
```

`find_iron()` 类似，但铁可以无视距离和连接——只需存在未用完的铁即可。

### 2.3 已实现 vs 未实现的规则

| 已完整实现 ✅ | 已实现但简化 ⚠️ | 未实现 ❌ |
|---|---|---|
| 6 种工厂 × 全部等级 | 用煤时"玩家自选"简化为 `random.choice()` | - |
| BFS 煤资源网络 | 用铁时"玩家自选"简化为 `random.choice()` | - |
| 煤/铁市场动态定价 (14/10 级) | - | - |
| 友善原则 | - | - |
| 建造工厂（含资源消耗） | - | - |
| 翻建工厂（自有升级 + 市场耗尽时可翻别人） | - | - |
| 产品售卖（含啤酒消耗 + 多酒桶合并） | - | - |
| 第二条路（铁路时代, 5 元 + 1 啤酒） | - | - |
| 运河/铁路时代切换（删 1 级工厂 + 清空道路） | - | - |
| 研发、贷款、换牌、跳过 | - | - |
| 卡牌匹配逻辑（地点/类型/万能） | - | - |
| 玩家顺序按花费排序 + 收入结算 | - | - |
| 39 条道路 × 22 个城市的官方拓扑 | - | - |
| 市场城市奖励（研发/分数/收入/金钱） | - | - |
| 翻面机制（资源耗尽时触发, 获收入） | - | - |

**结论：游戏规则层基本完整，没有发现的规则错误。**

---

## 三、RL Agent：致命 bug 分析

### 3.1 网络架构

```
状态向量 (5150 维 one-hot)
  → Linear(5150, 2048) → BN → ReLU → Dropout(0.5)
  → Linear(2048, 1024) → BN → ReLU → Dropout(0.5)
  → Linear(1024, 512)  → BN → ReLU → Dropout(0.5)
  → TaskDecoder(512 + task_specific_dim)  # 256 → 128, 独立于每个子任务
  → OutputLayer(128, output_dim)          # Linear + Softmax
```

8 个子任务各有独立的 TaskDecoder + OutputHead，共享同一个 `game_state_head`。

### 3.2 状态特征工程

`get_game_state()` 将游戏状态编码为 **5150 维 one-hot 向量**：

- 回合编号 (16) + 玩家顺序 (16) + 当前玩家 (4) + 手牌 (162)
- 每个玩家的金钱/收入/得分/花费/道路 (各用位数编码, ~153 维/玩家)
- 每玩家的产业等级 (72) + 出牌历史 (432) + 行动历史 (112)
- 地图状态: 时代 (2) + 市场 (42) + 城市 (1653) + 道路 (195)

**问题**：one-hot 编码使 5150 维中大部分恒为 0；城市拓扑关系被扁平化；出牌/行动历史被注释掉不参与计算。

### 3.3 🔴 致命 Bug 1: build_second_road 递归

[rl_agent.py:637-649]:
```python
def build_second_road(self, game_dict, card_list):
    game_state = self.get_game_state(game_dict, card_list)
    # BUG: 调用了自己！应该调用 self.alg.build_second_road(game_state)
    road_prod, beer_city_prod, beer_pos_prod = self.build_second_road(game_state)
```

该方法递归调用自身，且参数不匹配（`game_state` 是 numpy array 被当作 `game_dict` 传入）。**铁路时代的第二条路修建永远无法执行。**

### 3.4 🔴 致命 Bug 2: learn_change_card 缺少反向传播

[birmingham_algorithm.py:87-97]:
```python
def learn_change_card(self, state, card1, card2, reward):
    card_1_prob, card_2_prob = self.change_card(state)
    ...
    cost = log_prob * reward
    cost = paddle.mean(cost)
    # BUG: 缺少 cost.backward()！
    self.optimizer.step()    # 梯度为 0，参数不更新
    self.optimizer.clear_grad()
```

缺少 `cost.backward()`，梯度始终为 0，**换牌动作完全无法学习。**

### 3.5 🟠 训练为何不可行

1. **奖励极度稀疏**：整个 episode 只有终局一个实质奖励，中间每步 reward ≈ 0
2. **动作空间巨大**：8 个子任务各自有 6-39 个离散选择，组合爆炸
3. **无对手建模**：4 个玩家共享策略 self-play
4. **网络太浅**：3 层 FC 对 Brass 的策略复杂度远远不够
5. **REINFORCE 无 baseline**：方差极大，几乎无法收敛
6. **未使用 PARL 静态图**：注释掉了 200+ 行的 `build_program`，实际用动态图

---

## 四、代码质量问题

| 问题 | 位置 | 严重程度 |
|------|------|:---:|
| `self.state_dim = 5626` 但实际 assert 5150 | rl_agent.py:264,276 | 🟡 |
| `sell_beer` 中 `sell_city_hidden` 赋值两次 | rl_agent.py:894-895 | 🟡 |
| 出牌历史和行动历史的 one-hot 被注释掉 | rl_agent.py:221,231 | 🟡 |
| 调试用的硬编码断点 `qika = 0` | birmingham.py:492-493 | 🟡 |
| 无任何测试 | - | 🔴 |

---

## 五、LLM Agent 适配评估

### env 层可复用度: 极高

| 接口 | 说明 | LLM 适配难度 |
|------|------|:---:|
| `birmingham.py` 的 `get_dict()` | 返回结构化的游戏状态字典 | ⭐ 已可用 |
| `env/` 各模块的 `get_dict()` | 城市/道路/工厂/市场状态 | ⭐ 已可用 |
| `BirminghamGame.run_action()` | 7 种动作的执行入口 | ⭐⭐ 需包装为自然语言 |
| `BirminghamGame.get_available_actions()` | **不存在**，需自行实现 | ⭐⭐⭐ 需新增 |
| `BirminghamMap.find_coal()` | 资源网络查询 | ⭐ 可复用 |

### 需要新增的工作

1. **`get_available_actions(player)`**：遍历手牌 + 地图，返回所有合法动作及其代价
2. **状态文本化**：将 `get_dict()` 的 JSON 转为 LLM 友好的自然语言描述
3. **替换 agent/ 层**：RL 代码全部废弃，用 LLM 调用替代
4. **上下文管理**：Brass 一局 40-60 回合，需要 summary + sliding window 策略

---

## 六、总结

BRASS_PARL 是一个典型的"规则强、AI 弱"的项目。`env/` 层是目前全球唯一的 Brass Birmingham 完整规则实现，质量和覆盖度令人意外地高。但 RL agent 因多个致命 bug 和一些设计问题几乎不可用。

**最佳用途**: 将 `env/` + `birmingham.py` 作为 LLM Agent 的游戏环境基础，重写 `agent/` 层。
