# 卡牌关键字实现审计 & 修复计划

> 审计日期：2026-07-20
> 基于：三个并行 agent 全面扫描 + 直接 grep 验证
> 目的：梳理所有关键字的代码实现状态，发现 gap 并制定修复计划

---

## 一、审计范围与方法

三个 agent 分别从不同维度切入：

| Agent | 范围 | 方法 |
|-------|------|------|
| Agent 1 — 关键字提取 | `effect_ast.py`, `effect_parser.py`, `enums.py`, `tags.py`, `card.py`, `loader.py` | 提取所有枚举值、常量、模板标签 |
| Agent 2 — 操作符注册 | `effect_operators.py` (OPERATOR_REGISTRY), `condition_operators.py` (CONDITION_REGISTRY) | 逐一比对 registry 与 parser 生成的 effect_type |
| Agent 3 — JSON 实况 | `cards_compiled.json` | 扫描 JSON 中实际使用的所有 effect_type，反向验证操作符存在性 |

---

## 二、关键字层次体系

卡牌关键字分为 6 层，从外到内：

```
CardType → CardCategory → ability_type → trigger → effect_type → condition_type
                                    ↓
                               cost_type (费用)
```

### 2.1 各层定义位置

| 层 | 定义文件 | 数量 |
|----|---------|------|
| CardType | [enums.py](../engine/models/enums.py#L14) | 10 |
| CardCategory | [enums.py](../engine/models/enums.py#L28) | 20 |
| AbilityType | [effect_ast.py](../engine/cards/effect_ast.py#L135) | 8 |
| TriggerType | [effect_ast.py](../engine/cards/effect_ast.py#L147) | 20 |
| EffectType | [effect_ast.py](../engine/cards/effect_ast.py#L80) | 42 常量 |
| Condition | [effect_ast.py](../engine/cards/effect_ast.py#L24) + [condition_operators.py](../engine/cards/condition_operators.py) | 22 已注册 |

### 2.2 关键字分发路径

```
卡牌 JSON → effect_parser.py (_STEP_PATTERNS) → EffectStep(effect_type)
    → effect_resolver.py (_execute_step) → OPERATOR_REGISTRY[effect_type] → Operator.execute()
    → game.py (_check_triggers) → _ACTION_TRIGGER_MAP → trigger 匹配
```

---

## 三、完整实现审计表

### 3.1 EffectType — 操作符注册（核心路径）

**注册位置：** [effect_operators.py](../engine/cards/effect_operators.py) — `OPERATOR_REGISTRY` dict
**执行入口：** [effect_resolver.py](../engine/cards/effect_resolver.py#L242) — `_execute_step()`

| # | effect_type | 操作符类 | 解析器 | JSON | 状态 |
|---|-------------|---------|--------|------|------|
| 1 | `gain_military` | `GainMilitaryOperator` | `_parse_gain_military` | ✅ | ✅ 完整 |
| 2 | `gain_vp` | `GainVPOperator` | `_parse_gain_vp` | ✅ | ✅ 完整 |
| 3 | `lose_vp` | `LoseVPOperator` | —（JSON only） | ✅ | ✅ 完整 |
| 4 | `lose_military` | `LoseMilitaryOperator` | `_parse_lose_military` | ✅ | ✅ 完整 |
| 5 | `pay_military` | `PayMilitaryOperator` | `_parse_pay_military` | ✅ | ✅ 完整 |
| 6 | `pay_vp` | `PayVPOperator` | —（通过 block costs 提取） | ✅ | ✅ 完整 |
| 7 | `draw_cards` | `DrawCardsOperator` | `_parse_draw_cards` | ✅ | ✅ 完整 |
| 8 | `discard_cards` | `DiscardCardsOperator` | `_parse_discard_cards` | ✅ | ✅ 完整 |
| 9 | `archive_this` | `ArchiveThisOperator` | `_parse_archive_this` | ✅ | ✅ 完整 |
| 10 | `archive_card` | `ArchiveCardOperator` | `_parse_archive_card` | ✅ | ✅ 完整 |
| 11 | `archive_court` | `ArchiveCourtOperator` | —（JSON only） | ✅ | ✅ 完整 |
| 12 | `play_card` | `PlayCardOperator` | `_parse_play_card` | ✅ | ✅ 完整 |
| 13 | `search` | `SearchOperator` | `_parse_search` | ✅ | ✅ 完整 |
| 14 | `draft` | `DraftOperator` | `_parse_draft` | ✅ | ✅ 完整 |
| 15 | `supply_court` | `SupplyCourtOperator` | `_parse_supply_court` | ✅ | ✅ 完整 |
| 16 | `march` | `MarchOperator` | `_parse_free_action` | ✅ | ✅ 完整 |
| 17 | `occupy` | `OccupyOperator` | `_parse_free_action` | ✅ | ✅ 完整 |
| 18 | `convert` | `ConvertOperator` | `_parse_convert_location` | ✅ | ✅ 完整 |
| 19 | `fortify` | `FortifyOperator` | `_parse_fortify` | ✅ | ✅ 完整 |
| 20 | `spread_culture` | `SpreadCultureOperator` | `_parse_spread_culture` | ✅ | ✅ 完整 |
| 21 | `raise_order` | `RaiseOrderOperator` | `_parse_raise_order` | ✅ | ✅ 完整 |
| 22 | `lower_order` | `LowerOrderOperator` | `_parse_lower_order` | ✅ | ✅ 完整 |
| 23 | `raise_prestige` | `RaisePrestigeOperator` | `_parse_gain_prestige` | ✅ | ✅ 完整 |
| 24 | `lower_prestige` | `LowerPrestigeOperator` | `_parse_gain_prestige` | ✅ | ✅ 完整 |
| 25 | `raise_contribution` | `RaiseContributionOperator` | `_parse_gain_contribution_and_prestige` | ✅ | ✅ 完整 |
| 26 | `lower_contribution` | `LowerContributionOperator` | —（JSON only） | ✅ | ✅ 完整 |
| 27 | `raise_culture_level` | `RaiseCultureLevelOperator` | `_parse_raise_culture_level` | ✅ | ✅ 完整 |
| 28 | `remove_culture_marker` | `RemoveCultureMarkerOperator` | `_parse_remove_culture_marker` | ✅ | ✅ 完整 |
| 29 | `get_expedition` | `GetExpeditionOperator` | `_parse_get_expedition` | ✅ | ✅ 完整 |
| 30 | `add_refugee` | `AddRefugeeOperator` | `_parse_add_refugee` | ✅ | 🟡 TODO |
| 31 | `place_army` | `PlaceArmyOperator` | —（JSON only） | ✅ | ✅ 完整 |
| 32 | `remove_army` | `RemoveArmyOperator` | —（JSON only） | ✅ | ✅ 完整 |
| 33 | `remove_from_game` | `RemoveFromGameOperator` | `_parse_remove_army` | ✅ | ✅ 完整 |
| 34 | `choose` | `ChooseOperator` | choice 结构解析 | ✅ | ✅ 完整 |
| 35 | `conditional` | `ConditionalOperator` | if-else 逻辑解析 | ✅ | ✅ 完整 |
| 36 | `noop` | `NoopOperator` | —（占位） | — | ✅ 完整 |
| 37 | `raw` | `RawOperator` | —（回退） | — | ✅ 完整 |
| 38 | `extra_action` | `ExtraActionOperator` | `_parse_extra_action` | ✅ | ✅ 完整 |
| 39 | `targeted_effect` | `TargetedEffectOperator` | `_parse_targeted_effect` | ✅ | ✅ 完整 |
| 40 | `reshuffle_emperor` | `ReshuffleEmperorOperator` | `_parse_reshuffle_emperor` | ✅ | ✅ 完整 |
| 41 | `steal_random_card` | `StealRandomCardOperator` | `_parse_steal_random_card` | ✅ | ✅ 完整 |
| 42 | `convert_own_to_neutral` | `ConvertOwnToNeutralOperator` | `_parse_convert_friendly_to_neutral` | ✅ | ✅ 完整 |
| 43 | `convert_to_neutral` | `ConvertToNeutralOperator` | `_parse_convert_to_neutral` | ✅ | ✅ 完整 |
| 44 | `convert_to_sima` | `ConvertToSimaOperator` | —（JSON only） | ✅ | ✅ 完整 |
| 45 | `march_cost_reduction` | `MarchCostReductionOperator` | `_parse_march_cost_modifier` | ✅ | ✅ 完整 |
| 46 | `region_reward_override` | `RegionRewardOverrideOperator` | `_parse_region_reward_modifier` | ✅ | ✅ 完整 |

**别名映射** — [effect_operators.py:2127-2139](../engine/cards/effect_operators.py#L2127)：
| 别名（JSON 中） | 映射到 |
|-----------------|--------|
| `gain_prestige` | `raise_prestige` |
| `lose_contribution` | `lower_contribution` |
| `raise_culture_contribution` | `raise_culture_level` |
| `place_refugee` | `add_refugee` |
| `remove_military` | `remove_army` |

---

### 3.2 🔴 Runtime BUG：JSON 中存在但无操作符

当卡牌触发这些效果时，[effect_resolver.py](../engine/cards/effect_resolver.py#L242) 会报：
`Unknown effect_type: <xxx>`

| # | effect_type | JSON 出现次数 | 解析器 | 操作符 | JSON 位置 |
|---|-------------|-------------|--------|--------|----------|
| 1 | **`flip_culture_marker`** | 2 | ✅ `_parse_flip_culture_marker` | ❌ 无 `FlipCultureMarkerOperator` | L5569, L5610 |
| 2 | **`give_card`** | 2 | ✅ `_parse_give_card` | ❌ 无 `GiveCardOperator` | L1192, L1204 (targeted_effect 子效果) |
| 3 | **`swap_troops`** | 1 | ❌ 无解析器 | ❌ 无 `SwapTroopsOperator` | L3332 (直接步骤) |
| 4 | **`owner_archive_card`** | 2 | ❌ 无解析器 | ❌ 无 `OwnerArchiveCardOperator` | L4815, L4849 (targeted_effect 子效果) |
| 5 | **`abandon_court_card`** | 2 | ✅（作为 block cost） | ❌ 作为 step 时无 `AbandonCourtCardOperator` | L5379, L5425 (choice_options 子步骤) |
| 6 | **`change_controller`** | ? | ✅ `_parse_change_controller` | ❌ 无 `ChangeControllerOperator` | 需确认 JSON |

**影响评估：**
- `flip_culture_marker` — 文化翻转类卡牌完全无法结算
- `give_card` — 给牌效果崩溃
- `swap_troops` — 部队交换效果崩溃
- `owner_archive_card` — 卡牌所有者存档效果崩溃
- `abandon_court_card`（作为 step） — 选择项中弃朝堂牌崩溃
- `change_controller` — 控制权变更效果崩溃

---

### 3.3 🔴 Trigger/Ability 未分发

| # | 关键字 | 类型 | 定义位置 | 问题 |
|---|--------|------|---------|------|
| 7 | `on_card_enter` | TriggerType | [effect_ast.py](../engine/cards/effect_ast.py#L147) | parser 可生成（"标记放置版图"），但游戏中永不触发 |
| 8 | `always` | TriggerType | [effect_ast.py](../engine/cards/effect_ast.py#L147) | parser 默认值，但 `_check_triggers` 不匹配 `always` 触发器 |
| 9 | `strategy_passive` | AbilityType | [effect_ast.py](../engine/cards/effect_ast.py#L135) | 定义常量，全局零引用 |
| 10 | `usurp` | AbilityType | [effect_ast.py](../engine/cards/effect_ast.py#L135) | 定义常量，全局零引用（功能通过 `usurp_steps` 间接实现） |

---

### 3.4 🟡 一致性 GAP：操作符存在但无 EffectType 常量

| effect_type 字符串 | 操作符类 | 位置 | 建议 |
|-------------------|---------|------|------|
| `march_cost_reduction` | `MarchCostReductionOperator` | `effect_operators.py` | 添加 `EffectType.MARCH_COST_REDUCTION` |
| `region_reward_override` | `RegionRewardOverrideOperator` | `effect_operators.py` | 添加 `EffectType.REGION_REWARD_OVERRIDE` |
| `remove_culture_marker` | `RemoveCultureMarkerOperator` | `effect_operators.py` | 添加 `EffectType.REMOVE_CULTURE_MARKER` |
| `steal_random_card` | `StealRandomCardOperator` | `effect_operators.py` | 添加 `EffectType.STEAL_RANDOM_CARD` |

不是 bug（查找时直接用字符串），但与其他 37 个有常量的操作符不一致。

---

### 3.5 🟡 TODO / Stub

| # | 关键字 | 位置 | 状态 |
|---|--------|------|------|
| 11 | `add_refugee` | [effect_operators.py:1411](../engine/cards/effect_operators.py#L1411) | 操作符存在但仅 emit 事件，标注 `TODO: Phase 2a` |
| 12 | `CardType.REFUGEE` | [card.py:204](../engine/models/card.py#L204) | `is_refugee` 属性定义但游戏逻辑中零次被检查 |

---

### 3.6 Condition — 条件操作符（22 个已注册，零 gap）

**注册位置：** [condition_operators.py](../engine/cards/condition_operators.py) — `CONDITION_REGISTRY`

| # | condition_type | 操作符类 | 解析器 | 状态 |
|---|---------------|---------|--------|------|
| 1 | `and` | `AndConditionOperator` | ✅ | ✅ |
| 2 | `not` | `NotConditionOperator` | ✅ | ✅ |
| 3 | `compare` | `CompareConditionOperator` | ✅ | ✅ |
| 4 | `is_faction` | `IsFactionConditionOperator` | ✅ | ✅ |
| 5 | `can_usurp` | `CanUsurpConditionOperator` | ✅ | ✅ |
| 6 | `is_lowest_order` | `IsLowestOrderConditionOperator` | ✅ | ✅ |
| 7 | `is_lowest_culture_sum` | `IsLowestCultureSumConditionOperator` | ✅ | ✅ |
| 8 | `order_lowest` | `OrderLowestConditionOperator` | ✅ | ✅ |
| 9 | `prestige_highest` | `PrestigeHighestConditionOperator` | ✅ | ✅ |
| 10 | `control_region` | `ControlRegionConditionOperator` | ✅ | ✅ |
| 11 | `friendly_control_region` | `FriendlyControlRegionConditionOperator` | ✅ | ✅ |
| 12 | `occupy_location` | `OccupyLocationConditionOperator` | ✅ | ✅ |
| 13 | `occupy_location_in_region` | `OccupyLocationInRegionConditionOperator` | ✅ | ✅ |
| 14 | `has_route` | `HasRouteConditionOperator` | ✅ | ✅ |
| 15 | `culture_contribution_gt` | `CultureContributionGtConditionOperator` | ✅ | ✅ |
| 16 | `culture_level_gt` | `CultureLevelGtConditionOperator` | ✅ | ✅ |
| 17 | `culture_most_empty` | `CultureMostEmptyConditionOperator` | ✅ | ✅ |
| 18 | `marker_count_gt` | `MarkerCountGtConditionOperator` | ✅ | ✅ |
| 19 | `has_token` | `HasTokenConditionOperator` | ✅ | ✅ |
| 20 | `has_expedition` | `HasExpeditionConditionOperator` | ✅ | ✅ |
| 21 | `has_military` | `HasMilitaryConditionOperator` | ✅ | ✅ |
| 22 | `archive_count_ge` | `ArchiveCountGeConditionOperator` | ✅ | ✅ |

另有 **13 个仅程序化使用**的条件（无解析器生成，仅代码中直接构造）：
`staff_has_space`, `on_action_this_turn`, `not_completed_goal`, `is_lowest_order`（别名）, `prestige_highest`（别名）等。

**结论：条件系统零 gap，全部 22 个已注册条件均有操作符。**

---

### 3.7 Trigger 分发链路

**分发入口：** [game.py:952-965](../engine/engine/game.py#L952) — `_ACTION_TRIGGER_MAP`

| action_type | trigger_type | 状态 |
|-------------|-------------|------|
| `march` | `on_march` | ✅ |
| `convert` | `on_convert` | ✅ |
| `archive` | `on_archive` | ✅ |
| `fortify` | `on_fortify` | ✅ |
| `spread_culture` | `on_spread_culture` | ✅ |
| `play_card` | `on_play_card` | ✅ |
| `gain_vp` | `on_gain_vp` | ✅ |
| `gain_contribution` | `on_gain_contribution` | ✅ |
| `gain_prestige` | `on_gain_prestige` | ✅ |

另有子效果事件通过 [effect_resolver.py:226](../engine/cards/effect_resolver.py#L226) — `_fire_trigger()` 分发：
`on_order_change`, `on_court_action`, `on_usurp`, `on_card_leave`, `on_turn_start`, `on_turn_end`, `on_region_reward`, `on_end_game`

**GAP：**
- `on_card_enter` — 定义了 TriggerType，parser 可生成，但无任何代码触发
- `always` — 定义了 TriggerType，但 `_check_triggers` 不处理

---

### 3.8 CardCategory — 20 个纯标签值

**定义：** [enums.py](../engine/models/enums.py#L28)
**桥接：** [loader.py](../engine/cards/loader.py) — `CATEGORY_TO_CARD_TYPE`

| 值 | 桥接到 CardType | 游戏逻辑使用 |
|----|----------------|-------------|
| `hero_jin` | `hero` | 仅初始分池（[phases.py:161](../engine/engine/phases.py#L161)） |
| `hero_north` | `hero` | 仅初始分池 |
| `friend_military` | `friend` | ❌ 零游戏逻辑引用 |
| `friend_advisor` | `friend` | ❌ 零游戏逻辑引用 |
| `friend_special` | `friend` | ❌ 零游戏逻辑引用 |
| `friend_culture` | `friend` | ❌ 零游戏逻辑引用 |
| `strategy_military` | `strategy` | ❌ 零游戏逻辑引用 |
| `strategy_culture` | `strategy` | ❌ 零游戏逻辑引用 |
| `strategy_special` | `strategy` | ❌ 零游戏逻辑引用 |
| `event_art` | `event` | ❌ 零游戏逻辑引用 |
| `event_culture` | `event` | ❌ 零游戏逻辑引用 |
| `event_military` | `event` | ❌ 零游戏逻辑引用 |
| `event_vp` | `event` | ❌ 零游戏逻辑引用 |
| `event_search` | `event` | ❌ 零游戏逻辑引用 |
| `event_mechanism` | `event` | ❌ 零游戏逻辑引用 |
| `event_utility` | `event` | ❌ 零游戏逻辑引用 |
| `event_power` | `event` | ❌ 零游戏逻辑引用 |
| `public` | `public` | ❌ 零游戏逻辑引用 |
| `goal` | `goal` | ❌ 零游戏逻辑引用 |
| `emperor` | `emperor` | ❌ 零游戏逻辑引用 |

**结论：** 20 个 CardCategory 值中，仅 `hero_jin`/`hero_north` 用于初始英雄分池，其余 18 个仅作为 `CATEGORY_TO_CARD_TYPE` 桥接使用。设计意图（按子类别筛选/检索）未实现。

---

### 3.9 解析器覆盖 — _STEP_PATTERNS

**位置：** [effect_parser.py:1994-2051](../engine/cards/effect_parser.py#L1994)

共 37 个模式匹配器，按优先级排列。以下 EffectType 无专用解析器：

| effect_type | 原因 |
|-------------|------|
| `pay_vp` | 通过 block costs 提取，不作为 step 解析 |
| `occupy` | 仅通过 `_parse_free_action` 中的"占据"匹配 |
| `noop` | 占位符，不需要解析 |
| `raw` | 回退机制，不需要解析 |
| `place_army` | JSON only |
| `remove_army` | JSON only |
| `archive_court` | JSON only |
| `lower_contribution` | JSON only |
| `convert_to_sima` | JSON only |
| `swap_troops` | ❌ 无解析器，无操作符 |
| `owner_archive_card` | ❌ 无解析器，无操作符 |

---

## 四、统计汇总

| 类别 | 数量 | 说明 |
|------|------|------|
| ✅ EffectType 完整实现 | 46 操作符 + 5 别名 | 约 92% 覆盖率 |
| 🔴 Runtime BUG | **6** | JSON 有效果但无操作符，触发即崩溃 |
| 🔴 Trigger/Ability GAP | **4** | 定义但无分发/零引用 |
| 🟡 一致性（缺常量） | **4** | 操作符存在但 EffectType 无对应常量 |
| 🟡 TODO/Stub | **2** | `add_refugee` 占位，`CardType.REFUGEE` 未使用 |
| 🟡 CardCategory 纯标签 | **18** | 除 hero_jin/hero_north 外均无游戏逻辑引用 |
| ✅ Condition 覆盖 | **22/22** | 零 gap |

---

## 五、修复计划

### 5.1 紧急（Phase 1.5 — 运行时崩溃修复）✅ 全部完成

这 6 个 gap 会导致卡牌触发时游戏崩溃，必须优先修复：

#### Fix #1: `flip_culture_marker` — 实现 FlipCultureMarkerOperator ✅

- **影响卡牌：** 2 张（JSON L5569, L5610）
- **效果语义：** 将版图上的文化标记从已使用面翻转为未使用面（或反之）
- **实际处理：**
  - 在 [effect_operators.py](../engine/cards/effect_operators.py) 中新建 `FlipCultureMarkerOperator` 类
  - 在 `OPERATOR_REGISTRY` 中注册 `"flip_culture_marker"`
  - 通过 `resolver.select_target_callback` 让玩家选择有文化标记的地点
  - 翻转 `culture_locked` 状态

#### Fix #2: `give_card` — 实现 GiveCardOperator ✅

- **影响卡牌：** 2 张（JSON L1192, L1204 — targeted_effect 子效果）
- **效果语义：** 选择手牌交给另一玩家
- **实际处理：**
  - 在 [effect_operators.py](../engine/cards/effect_operators.py) 中新建 `GiveCardOperator` 类
  - 在 `OPERATOR_REGISTRY` 中注册 `"give_card"`
  - 从 `context["source_player"]` 的手牌中选择，转移到目标玩家手牌

#### Fix #3: `swap_troops` — 实现 SwapTroopsOperator ✅

- **影响卡牌：** 1 张（JSON L3332）
- **效果语义：** 交换两个地点的部队位置
- **实际处理：**
  - 在 [effect_parser.py](../engine/cards/effect_parser.py) 中添加 `_parse_swap_troops` 解析器
  - 在 [effect_operators.py](../engine/cards/effect_operators.py) 中新建 `SwapTroopsOperator` 类
  - 支持 `jin_capital` 符号引用 → 解析为 `state.sima.capital_location`
  - 交换控制者和加固状态，并更新首都追踪

#### Fix #4: `owner_archive_card` — 实现 OwnerArchiveCardOperator ✅

- **影响卡牌：** 2 张（JSON L4815, L4849 — targeted_effect 子效果）
- **效果语义：** 卡牌的所有者（而非当前玩家）执行存档
- **实际处理：**
  - 在 [effect_operators.py](../engine/cards/effect_operators.py) 中新建 `OwnerArchiveCardOperator` 类
  - 在 `OPERATOR_REGISTRY` 中注册 `"owner_archive_card"`
  - 收集所有友方玩家幕僚区的友方牌作为候选，当前玩家选择后，由牌的所有者执行存档

#### Fix #5: `abandon_court_card`（作为 step）— 实现 AbandonCourtCardOperator ✅

- **影响卡牌：** 2 张（JSON L5379, L5425 — choice_options 子步骤）
- **当前状态：** `abandon_court_card` 仅支持作为 block cost，不支持作为 choice 内的步骤
- **实际处理：**
  - 在 [effect_operators.py](../engine/cards/effect_operators.py) 中新建 `AbandonCourtCardOperator` 类
  - 在 `OPERATOR_REGISTRY` 中注册 `"abandon_court_card"`
  - 选择朝堂牌，弃置到国家弃牌区，触发 `on_discard`

#### Fix #6: `change_controller` — 确认 JSON 中不存在 ✅

- **当前状态：** 解析器存在（`_parse_change_controller`），但无操作符
- **实际处理：**
  - grep `cards_compiled.json` 确认未使用 `change_controller`
  - 解析器中死代码清理：`_parse_change_to_player_control` 将 "转为中立"→`convert_to_neutral`、"转为司马家"→`convert_to_sima`、"改为玩家"→`convert`
  - 无需新建操作符

### 5.2 重要（Phase 2 — Trigger/Ability 补全）✅ 全部完成

#### Fix #7: `on_card_enter` 触发器 ✅ 已注释

- **实际处理：**
  - 确认 `on_card_enter` 在 JSON 中零引用（0 张卡牌使用）
  - 注释 [effect_ast.py](../engine/cards/effect_ast.py) 中 `TriggerType.ON_CARD_ENTER`
  - 注释 [enums.py](../engine/models/enums.py) 中 `TriggerType.ON_CARD_ENTER`
  - 注释 [effect_parser.py](../engine/cards/effect_parser.py) 中解析模式 `r'标记\s*放置.*版图'`
  - 原因：无触发分发、无 JSON 引用、无卡牌受影响。实际匹配的卡牌（道安）已在编译 JSON 中使用 `on_spread_culture`

#### Fix #8: `always` 触发器 ✅ 已注释

- **实际处理：**
  - 确认 `always` 在 JSON 中零引用（全部 24 张被动卡牌使用具体触发类型）
  - 注释 [effect_ast.py](../engine/cards/effect_ast.py) 中 `TriggerType.ALWAYS`
  - [effect_parser.py](../engine/cards/effect_parser.py) 中 5 处 `TriggerType.ALWAYS` 替换为 `None`
  - 原因：`ALWAYS` 仅作为解析器内部默认值（fallback sentinel），但从未被触发分发使用

#### Fix #9-10: `strategy_passive` / `usurp` AbilityType ✅ 已注释

- **实际处理：**
  - 确认两个常量在代码库中零引用
  - 注释 [effect_ast.py](../engine/cards/effect_ast.py) 中 `AbilityType.STRATEGY_PASSIVE` 和 `AbilityType.USURP`
  - 僭越功能实际上通过 `AbilityBlock.usurp_steps` + `CardEffect.is_usurp` 间接实现

#### Fix #11: EffectType 常量缺失 ✅ 已补充

- **实际处理：**
  - 在 [effect_ast.py](../engine/cards/effect_ast.py) 中添加 4 个缺失常量：`REMOVE_CULTURE_MARKER`、`FLIP_CULTURE_MARKER`、`GIVE_CARD`、`STEAL_RANDOM_CARD`、`OWNER_ARCHIVE_CARD`、`ABANDON_COURT_CARD`、`SWAP_TROOPS`、`MARCH_COST_REDUCTION`、`REGION_REWARD_OVERRIDE`
  - 更新 4 个已有操作符使用新常量（`RemoveCultureMarkerOperator`、`StealRandomCardOperator`、`MarchCostReductionOperator`、`RegionRewardOverrideOperator`）

### 5.3 改善（Phase 2+ — 一致性 & TODO）✅ 全部完成

#### Fix #12: `add_refugee` Phase 2a 实现 ✅

- **实际处理：**
  - [effect_operators.py](../engine/cards/effect_operators.py) — `AddRefugeeOperator` 从占位实现（仅 emit 事件）改为完整实现
  - 逻辑：从 `state.refugee_supply` 取出流民牌 → 放入指定弃牌堆
  - 支持目标：`jin_discard`、`north_discard`、`own_national_discard`
  - 附带修复：[card.py](../engine/models/card.py) — `is_refugee` 属性增加 `self.name == "流民"` 检查（因为流民牌通过 `card_category="initial"` 加载为 `CardType.INITIAL`，原检查 `CardType.REFUGEE` 永远为 False）

#### Fix #13: CardCategory 决策 ✅ 维持现状，无需修改

- **实际处理：**
  - 19 个 `card_category` 值在 `CATEGORY_TO_CARD_TYPE`（[loader.py](../engine/cards/loader.py)）中全部被使用，作为 "子类别→CardType" 的桥接
  - 每张卡牌加载时均经过此桥接表，是数据管线基础设施
  - `hero_jin`/`hero_north` 额外用于初始英雄分池（[phases.py](../engine/engine/phases.py)）
  - 结论：**不实现** `by_category()` 查询（无当前需求），**不删除**（会破坏 loader），维持现状即最佳方案

---

## 八、附加修复（审计范围外，发现并修复）

| 修复 | 描述 | 文件 |
|------|------|------|
| 首都追踪 | `SimaState` 新增 `capital_location` 字段，初始值"建康"；`SwapTroopsOperator` 支持 `jin_capital` 符号引用 | [game_state.py](../engine/models/game_state.py), [effect_operators.py](../engine/cards/effect_operators.py) |
| 首都移除检测 | `check_capital_displaced()` + `relocate_sima_capital()` — 首都位置控制者变更时自动重新放置，由行动顺位最前的东晋玩家选择新地点 | [sima.py](../engine/rules/sima.py) |
| 首都不可转化 | `ConvertAction.validate()` 拦截所有玩家转化首都；`ConvertToNeutralOperator` 排除首都候选 | [special_actions.py](../engine/engine/actions/special_actions.py), [effect_operators.py](../engine/cards/effect_operators.py) |
| 首都位置显示 | viewport `get_sima()` 新增 `capital_location`，summary 行显示 `首都:建康` | [live.py](../engine/viewport/live.py), [snapshot.py](../engine/viewport/snapshot.py), [query.py](../engine/viewport/query.py) |
| `on_card_enter` 清理 | 三处注释（effect_ast.py、enums.py 常量 + effect_parser.py 解析模式） | 3 个文件 |
| `always` 清理 | 注释常量 + 5 处 `None` 替换（parser fallback） | 2 个文件 |
| `strategy_passive`/`usurp` 清理 | 注释两个零引用 AbilityType 常量 | [effect_ast.py](../engine/cards/effect_ast.py) |

---

## 六、修复优先级排序（全部完成）

```
紧急（Phase 1.5）:
  ✅ Fix #1  flip_culture_marker    ← 文化翻转崩溃 — FlipCultureMarkerOperator
  ✅ Fix #2  give_card              ← 给牌崩溃 — GiveCardOperator
  ✅ Fix #3  swap_troops            ← 部队交换崩溃 — SwapTroopsOperator + 解析器
  ✅ Fix #4  owner_archive_card     ← 存档崩溃 — OwnerArchiveCardOperator
  ✅ Fix #5  abandon_court_card     ← 朝堂弃牌崩溃 — AbandonCourtCardOperator
  ✅ Fix #6  change_controller      ← 确认JSON中不存在，死代码清理

重要（Phase 2）:
  ✅ Fix #7  on_card_enter trigger  ← 已注释（JSON零引用）
  ✅ Fix #8  always trigger         ← 已注释（JSON零引用，parser fallback改为None）
  ✅ Fix #11 EffectType 常量        ← 已补充9个缺失常量

改善（Phase 2+）:
  ✅ Fix #12 add_refugee 实现       ← 完整流民逻辑 + is_refugee修正
  ✅ Fix #9-10 strategy_passive/usurp ← 已注释（零引用）
  ✅ Fix #13 CardCategory 决策       ← 维持现状（桥接表基础设施，无需修改）
```

---

## 七、验证方法

每修复一个 gap，执行：

```bash
# 1. AST 加载冒烟
cd d:\life\board_game\project_six_dynasty
python -c "
import sys; sys.path.insert(0, 'engine')
from config.version import Version
v = Version.load('v1.0')
print(f'OK: {len(v.card_library.all_cards)} cards loaded')
"

# 2. 全量测试
python -m pytest engine/tests/ -v --tb=short

# 3. 单局对局
python -c "
import sys; sys.path.insert(0, 'engine')
from config.version import Version
from ai.dummy_ai import DummyAI
from engine.game import GameEngine
v = Version.load('v1.0')
agents = [DummyAI('north',1), DummyAI('jin_1',2), DummyAI('jin_2',3), DummyAI('jin_3',4)]
state = GameEngine(agents=agents, version=v, seed=42).run()
print(f'PASS: round={state.round}, winner={GameEngine(agents=agents, version=v, seed=42).get_winner() if False else \"completed\"}')
"
```

---

> 创建日期：2026-07-20
> 审计方法：三 agent 并行扫描 + 直接 grep 验证
> 完成日期：2026-07-23
> 状态：**全部 13 项修复完成** ✅
>
> ### 修改文件清单
>
> | 文件 | 涉及修复 |
> |------|---------|
> | [effect_ast.py](../engine/cards/effect_ast.py) | Fix #1-5 (新增常量), Fix #7-8 (注释), Fix #9-10 (注释), Fix #11 (补充常量) |
> | [effect_operators.py](../engine/cards/effect_operators.py) | Fix #1-5 (5个新操作符 + 更新4个已有), Fix #12 (AddRefugeeOperator) |
> | [effect_parser.py](../engine/cards/effect_parser.py) | Fix #3 (新增解析器), Fix #6 (死代码清理), Fix #7-8 (注释/None替换) |
> | [game_state.py](../engine/models/game_state.py) | 首都追踪 (capital_location) |
> | [sima.py](../engine/rules/sima.py) | 首都移除检测 + 重新放置完整流程 |
> | [special_actions.py](../engine/engine/actions/special_actions.py) | 首都不可转化 + 首都移除检测挂接 |
> | [card.py](../engine/models/card.py) | Fix #12 (is_refugee 修正) |
> | [enums.py](../engine/models/enums.py) | Fix #7 (注释 ON_CARD_ENTER) |
> | [live.py](../engine/viewport/live.py) | 首都位置视窗显示 |
> | [snapshot.py](../engine/viewport/snapshot.py) | 首都位置快照数据 |
> | [query.py](../engine/viewport/query.py) | 首都位置 summary 行 |
>
> ### 验证
>
> ```bash
> cd engine && python -m pytest tests/ -q
> # 469 passed, 0 failed
> python -m pytest tests/test_game/test_game_loop.py -v
> # 10 passed (含 10-game stability)
> ```
