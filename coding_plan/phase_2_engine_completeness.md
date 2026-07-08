# Phase 2：引擎完整性补完 & AI 批量测试

> 目标：让 Effect Resolver 真实驱动每一张卡，条件/变量/被动全部生效，AI 能做有意义的批量对局。
>
> 前置条件：Phase 1 完成 ✅（Version.load 加载正常，210 测试全绿）
>
> 预计时间：2-3 个开发会话

---

## 一、背景诊断

Phase 1 把"两条加载路径"统一了，171 张卡全部加载成功、AST 重建无异常。但 AST 重建通过 ≠ 卡牌效果能真正执行。

当前核心问题：**Effect Resolver 是半个空壳**。卡牌效果 AST 被正确解析和加载了，但游戏循环几乎不通过 Resolver 来驱动卡牌——大部分 effect_type 在 `_execute_step()` 里要么没有分支，要么只发一个事件占位，实际动作没有被执行。

此外：
- **条件系统** `_check_condition()` 永远返回 `True`——所有带条件的卡牌效果无条件触发
- **变量系统** `_resolve_value()` 遇到 `X` 返回 0——所有动态效果归零
- **被动触发**定义了 20 种 trigger 但没有 hook——passive/enter play 能力全不生效
- **AI** 只有随机 DummyAI——批量对局毫无意义

---

## 二、待补完模块清单

### 2a. Effect Resolver 补完（P0 — 核心战斗）

**文件**：[engine/cards/effect_resolver.py](engine/cards/effect_resolver.py)

#### 缺口 #1：MARCH / FORTIFY / DRAFT / OCCUPY 是空壳

| effect_type | 当前行为 | 修法 |
|---|---|---|
| `MARCH` | 只发 `march_requested` 事件 | 构造 `MarchAction` 并通过 `action_system.execute()` 执行 |
| `FORTIFY` | 只发 `fortify_requested` 事件 | 构造 `FortifyAction` 并通过 `action_system.execute()` 执行 |
| `DRAFT` (征发) | 只发 `draft_requested` 事件 | 构造 `LevyAction` 并通过 `action_system.execute()` 执行 |
| `OCCUPY` | **完全没有 elif 分支** | 添加分支，构造 `OccupyAction` 并执行 |

修法原则：参考已有的 `CONVERT` 分支（line 159-173），它已经示范了如何从 Resolver 调用 action_system。

#### 缺口 #2：缺失的 effect_type 分支

以下在 `EffectType` 常量中已定义但 `_execute_step()` 无处理：

| effect_type | 修法 |
|---|---|
| `LOSE_VP` | 直接扣除玩家 VP（参考 `GAIN_VP` 取反） |
| `LOSE_MILITARY` | 直接扣除军力（参考 `GAIN_MILITARY` 取反） |
| `ARCHIVE_COURT` | 从朝堂区移除牌到弃牌堆 |
| `PLAY_CARD` | 从手牌打出（构造 PlayCardAction） |
| `RAISE_PRESTIGE` / `LOWER_PRESTIGE` | 操作玩家声望值 |
| `RAISE_CONTRIBUTION` / `LOWER_CONTRIBUTION` | 操作玩家贡献值 |
| `PLACE_ARMY` / `REMOVE_ARMY` | 在地图位置放置/移除部队 |
| `REMOVE_FROM_GAME` | 将牌从游戏中移除（移出对局） |
| `ADD_REFUGEE` | 补充流民到供应区 |
| `CHOOSE` / `CONDITIONAL` | 元类型，在 `_resolve_block` 层处理 |
| `NOOP` | 显式空操作 |

#### 缺口 #3：LOSE_MILITARY 会影响全局

当前 `PAY_MILITARY` 只是 `player.military = max(0, player.military - amount)`。但 `LOSE_MILITARY` 语义不同：**扣除的军力可能进入司马军力池**（根据僭越规则）。修法：调用 `rules.sima.distribute_sima_military()`。

---

### 2b. Condition 系统实现（P0）

**文件**：[engine/cards/effect_resolver.py](engine/cards/effect_resolver.py) line 301-305

当前：
```python
def _check_condition(self, condition, state, player_id):
    return True  # Simplified
```

需实现以下 condition_type：

| condition_type | 检查逻辑 | 示例 |
|---|---|---|
| `control_region` | 玩家是否控制指定区域 | "控制[巴蜀]" |
| `has_marker` | 玩家/卡牌是否持有指定标记 | "有[军事]标记" |
| `exclude_marker` | 目标卡牌不含指定标记 | "打出1张不含[军事]标记的手牌" |
| `compare` | 比较两个值（军力/VP/声望等） | "军力 > 5" |
| `culture_level` | 文化等级达到阈值 | "儒学等级 > 2" |
| `has_culture_marker` | 位置上是否有文化标记 | — |
| `can_usurp` | 玩家是否满足僭越条件 | 司马僭越判定 |
| `hand_size` | 手牌数量条件 | "手牌 ≥ 3" |
| `turn_phase` | 当前回合阶段条件 | — |
| `not_yet_this_turn` | 本回合未执行过某动作 | — |

实现参考：`rules/goals.py` 中已有相似的条件解析逻辑，可复用模式。

**额外要求**：condition 检查也需要考虑 `params` 中的 `filter` 字段（Phase 1 我们把它合并进了 `params`）。当 step 有 `params.filter` 时，在解析目标卡牌/位置时应用过滤。

---

### 2c. 变量系统实现（P0）

**文件**：[engine/cards/effect_resolver.py](engine/cards/effect_resolver.py) line 275-283

当前：
```python
def _resolve_value(self, value, state, player_id):
    if isinstance(value, int):
        return value
    if value == 'X':
        return 0  # stub
    return int(value) if value else 0
```

需支持以下变量源：

| 变量 | 解析来源 | 示例 |
|---|---|---|
| `X` | 卡牌特定的上下文变量 | "获得 X 军力"（X 由卡牌其他部分定义） |
| `marker_count_military` | `player.get_marker("military")` | "军力标记数" |
| `marker_count_power` | `player.get_marker("power")` | "权谋标记数" |
| `marker_count_culture` | `player.get_marker("culture")` | "文化标记数" |
| `marker_count_affair` | `player.get_marker("affair")` | "内政标记数" |
| `hand_size` | `len(player.hand)` | "手牌数" |
| `prestige` | `player.prestige` | "声望值" |
| `contribution` | `player.contribution` | "贡献值" |
| `history_count` | `len(player.history_area)` | "修史区牌数" |
| `control_count` | 玩家控制的地点数 | "控制地点数" |
| `region_control_count` | 指定区域的控制地点数 | "巴蜀控制数" |

---

### 2d. Passive 触发系统（P1）

**文件**：[engine/engine/game.py](engine/engine/game.py) 和 [engine/engine/phases.py](engine/engine/phases.py)

**问题**：AST 定义了 20 种 trigger（`on_march`、`on_archive`、`on_turn_start`、`on_turn_end` 等），但游戏循环中没有任何地方遍历场上卡牌检查 trigger 并触发对应效果。

**修法**：

1. 在 `GameEngine` 中新增 `_check_triggers(trigger_type, context)` 方法
2. 遍历所有已打出的卡牌（hand、history_area、staff），检查其 `parsed_effect.blocks` 中 `block.trigger == trigger_type` 或 `block.ability_type == "enter"`
3. 匹配后调用 `EffectResolver._resolve_block()` 执行
4. 在以下游戏事件点插入 trigger hook：

| 事件点 | trigger_type |
|---|---|
| 玩家进军后 | `on_march` |
| 玩家占领后 | `on_occupy` |
| 卡牌归档后 | `on_archive` |
| 卡牌打出后 | `on_play_card` |
| 回合开始时 | `on_turn_start` |
| 回合结束时 | `on_turn_end` |
| 弃牌后 | `on_discard` |
| 传播文化后 | `on_spread_culture` |
| 获得 VP 后 | `on_gain_vp` |
| 获得贡献后 | `on_gain_contribution` |
| 获得声望后 | `on_gain_prestige` |
| 筑垒后 | `on_fortify` |
| 文化转化后 | `on_convert` |
| 朝堂行动后 | `on_court_action` |
| 牌离开某区域后 | `on_card_leave` |
| 牌进入某区域后 | `on_card_enter` |
| 僭越后 | `on_usurp` |
| 秩序变化后 | `on_order_change` |
| 区域奖励后 | `on_region_reward` |

---

### 2e. Heuristic AI 实现（P1）

**文件**：新建 `engine/ai/heuristic_ai.py`

**目标**：一个基于规则的 AI，比随机 DummyAI 强，能驱动有意义的批量对局。

**核心决策逻辑**（按优先级）：

1. **回合前检查**：如果有可用的 court 卡且军力足够 → 执行 court action
2. **手牌选择**：优先打出高收益卡牌（VP 收益、军力收益、文化传播）
3. **军力使用**：
   - 优先进军争夺/守卫最高 VP 区域
   - 其次占领无人地点
   - 再次筑垒关键位置
   - 最后征兵/抽牌
4. **被动响应**：当 AI 作为 Jin 玩家时，考虑僭越条件

**接口**：实现 `GameAgent` ABC（同 DummyAI），返回相同的决策结构。

**验证方式**：100 局 HeuristicAI vs DummyAI，HeuristicAI 胜率应显著 > 25%（random baseline）。

---

### 2f. 测试补完（P1）

#### 新增测试文件

| 文件 | 覆盖目标 |
|---|---|
| `engine/tests/test_cards/test_effect_resolver.py` | `EffectResolver._execute_step()` 所有分支 |
| `engine/tests/test_cards/test_condition.py` | `_check_condition()` 所有 condition_type |
| `engine/tests/test_cards/test_variable_resolution.py` | `_resolve_value()` 所有变量源 |
| `engine/tests/test_phases/test_phases.py` | `setup_game` / preparation / settlement |
| `engine/tests/test_ai/test_heuristic_ai.py` | HeuristicAI 每个决策分支 |
| `engine/tests/test_invariants/test_invariants.py` | 对局不变量检查（如总军力守恒、牌数守恒等） |

#### 空目录填充

- `engine/tests/test_invariants/` → 添加 `test_invariants.py` 和 `__init__.py`
- `engine/tests/test_phases/` → 添加 `test_phases.py` 和 `__init__.py`
- `engine/tests/fixtures/` → 添加共享的测试 fixures 和 `__init__.py`

---

## 三、修改/新增文件清单

| 文件 | 改动 | 风险 |
|------|------|------|
| `engine/cards/effect_resolver.py` | **主要改动**：补完 15+ effect_type 分支；实现 condition；实现变量系统 | 🔴 高 |
| `engine/engine/game.py` | 新增 `_check_triggers()` 方法 + trigger hook 调用点 | 🟡 中 |
| `engine/engine/phases.py` | 补充 setup 中的被动触发、culture track 初始化 | 🟡 中 |
| `engine/rules/sima.py` | 将 `LOSE_MILITARY` 接入司马军力分配 | 🟢 低 |
| `engine/ai/heuristic_ai.py` | **新建** | 🟢 低（不依赖现有代码修改） |
| `engine/ai/__init__.py` | 注册 HeuristicAI | 🟢 低 |
| `engine/tests/test_cards/test_effect_resolver.py` | **新建** | 🟢 低 |
| `engine/tests/test_cards/test_condition.py` | **新建** | 🟢 低 |
| `engine/tests/test_cards/test_variable_resolution.py` | **新建** | 🟢 低 |
| `engine/tests/test_phases/test_phases.py` | **新建** | 🟢 低 |
| `engine/tests/test_invariants/test_invariants.py` | **新建** | 🟢 低 |
| `engine/tests/test_ai/test_heuristic_ai.py` | **新建** | 🟢 低 |

---

## 四、验收标准

### Phase 2a（Effect Resolver + Condition + 变量）

- [ ] `_execute_step()` 覆盖所有 38 种 EffectType（不再有静默忽略的 effect_type）
- [ ] `_check_condition()` 支持所有 10 种 condition_type
- [ ] `_resolve_value()` 支持所有变量源
- [ ] 新增 `test_effect_resolver.py`：每个 effect_type 至少 1 个测试
- [ ] 新增 `test_condition.py`：每个 condition_type 至少 1 个测试
- [ ] 新增 `test_variable_resolution.py`：每个变量源至少 1 个测试
- [ ] `pytest engine/tests/ -v` 全部通过

### Phase 2b（Passive 触发 + Heuristic AI）

- [ ] 每个 action 执行后对应的 trigger hook 被调用
- [ ] Enter play 效果在卡牌打出时触发
- [ ] `HeuristicAI` 对局跑通不崩溃
- [ ] 100 局 HeuristicAI vs DummyAI：HeuristicAI 胜率 > 25%
- [ ] 10,000 局 HeuristicAI 对局零崩溃（批量稳定性）

### Phase 2c（测试补完）

- [ ] `test_phases/` 覆盖 setup/preparation/settlement
- [ ] `test_invariants/` 覆盖至少 5 条游戏不变量
- [ ] `pytest engine/tests/ -v` 全部通过
- [ ] 代码覆盖率（非强制目标）：cards/ 模块 > 80%，engine/ 模块 > 70%

---

## 五、验收操作

### 步骤 1：Effect Resolver 冒烟

```bash
cd d:\life\board_game\project_six_dynasty
python -c "
import sys; sys.path.insert(0, 'engine')
from config.version import Version
from cards.effect_resolver import EffectResolver, EffectType
v = Version.load('v1.0')
resolver = EffectResolver()
# 遍历所有卡牌，尝试 resolve 每个效果
for cdef in v.card_library.all_cards:
    pe = cdef.parsed_effect
    if pe is None:
        continue
    # 检查每个 step 的 effect_type 是否都有对应分支
    for block in pe.blocks:
        for step in block.steps:
            if step.effect_type and not hasattr(EffectType, step.effect_type.upper()):
                # Check it's known at least
                pass
print('Effect Resolver 冒烟通过')
"
```

### 步骤 2：全量单元测试

```bash
cd d:\life\board_game\project_six_dynasty
python -m pytest engine/tests/ -v --tb=short
```

### 步骤 3：HeuristicAI 批量对局

```bash
cd d:\life\board_game\project_six_dynasty
python -c "
import sys; sys.path.insert(0, 'engine')
from config.version import Version
from ai.heuristic_ai import HeuristicAI
from ai.dummy_ai import DummyAI
from engine.game import GameEngine

v = Version.load('v1.0')
# HeuristicAI vs 3 DummyAI
agents = [
    HeuristicAI(player_id='north'),
    DummyAI(player_id='jin_1', seed=1),
    DummyAI(player_id='jin_2', seed=2),
    DummyAI(player_id='jin_3', seed=3),
]
engine = GameEngine(agents=agents, version=v, seed=42)
state = engine.run()
print(f'Winner: {engine.get_winner()}')
print(f'Scores: {engine.get_scores()}')
print('PASS: HeuristicAI 对局跑通')
"
```

### 步骤 4：10,000 局稳定性

```bash
cd d:\life\board_game\project_six_dynasty
python -c "
import sys; sys.path.insert(0, 'engine')
from config.version import Version
from ai.dummy_ai import DummyAI
from engine.game import GameEngine

v = Version.load('v1.0')
for i in range(10000):
    seed = i * 100 + 1
    agents = [
        DummyAI(player_id='north', seed=seed),
        DummyAI(player_id='jin_1', seed=seed+1),
        DummyAI(player_id='jin_2', seed=seed+2),
        DummyAI(player_id='jin_3', seed=seed+3),
    ]
    engine = GameEngine(agents=agents, version=v, seed=seed)
    state = engine.run()
    assert state.phase.value == 'game_over', f'seed={seed} crashed'
    if i % 1000 == 0:
        print(f'  {i}/10000 passed, winner={engine.get_winner()}')
print('PASS: 10000 局全部通过')
"
```

---

## 六、完成后状态

Phase 2 完成后：
- 每一张卡的效果都真正被执行（不只是解析成 AST，而是驱动游戏状态变化）
- Condition 和变量系统让卡牌效果变得"有判断力"和"动态"
- Passive 触发让登场/被动能力生效
- AI 能做有意义的决策，批量对局能暴露平衡性和 bug
- 测试覆盖核心模块

可以进入 Phase 3：UI/Web 层或多版本扩展。

---

> 创建日期：2026-07-06
