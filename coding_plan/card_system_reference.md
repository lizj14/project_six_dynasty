# 六朝卡牌系统参考文档

> 生成日期：2026-07-05  
> 基于 `versions/v1.0/cards/cards_compiled.json` (v0.9)  
> 所有中文描述文本已形式化为结构化 AST，不含 `raw_text` 或占位符。

---

## 目录

1. [卡牌类型与 JSON 格式](#1-卡牌类型与-json-格式)
2. [ability_type（能力类型）](#2-ability_type能力类型)
3. [effect_type（效果类型）](#3-effect_type效果类型)
4. [condition_type（条件类型）](#4-condition_type条件类型)
5. [cost_type（费用类型）](#5-cost_type费用类型)
6. [trigger（触发器）](#6-trigger触发器)
7. [Filter（过滤器）](#7-filter过滤器)
8. [targeted_effect（目标效果）](#8-targeted_effect目标效果)
9. [choice 结构](#9-choice-结构)
10. [代码实现索引](#10-代码实现索引)

---

## 1. 卡牌类型与 JSON 格式

### 1.1 顶层结构

`cards_compiled.json` 包含四个数组：

| 数组 | 数量 | 说明 |
|------|------|------|
| `hero_cards` | 11 | 角色牌（东晋/北方） |
| `action_cards` | 139 | 所有可打出的牌（策略、事件、幕僚、强制、初始、公共、流民） |
| `goal_cards` | 16 | 目标牌 |
| `emperor_cards` | 5 | 君主牌 |

### 1.2 卡牌类型枚举 (`CardType`)

**定义文件：** [enums.py](../engine/models/enums.py#L14)

| 值 | 中文 | 说明 |
|----|------|------|
| `hero` | 角色牌 | 玩家角色，含登场效果和持续被动 |
| `event` | 事件牌 | 一次性打出，执行效果后存档 |
| `strategy` | 策略牌 | 需先放入朝堂区，通过牌组行动执行 |
| `friend` | 幕僚牌 | 打出到幕僚区，提供持续效果/被动 |
| `mechanism` | 强制事件牌 | 满足条件时强制触发 |
| `goal` | 目标牌 | 终局计分条件 |
| `emperor` | 君主牌 | 司马家威望轨道 |
| `public` | 公共行动牌 | 朝堂区固定可用行动 |
| `refugee` | 流民牌 | 特殊负面牌 |
| `initial` | 初始牌 | 游戏初始设置的伪卡牌类型 |

### 1.3 卡牌子类别 (`CardCategory`)

**定义文件：** [enums.py](../engine/models/enums.py#L28)

| 值 | 中文 |
|----|------|
| `hero_jin` | 东晋角色 |
| `hero_north` | 北方角色 |
| `friend_military` | 幕僚-名将 |
| `friend_advisor` | 幕僚-谋主 |
| `friend_special` | 幕僚-特殊 |
| `friend_culture` | 幕僚-艺术文化 |
| `strategy_military` | 策略-军备 |
| `strategy_culture` | 策略-文化 |
| `strategy_special` | 策略-特殊 |
| `event_art` | 事件-艺术 |
| `event_culture` | 事件-文化 |
| `event_military` | 事件-军事 |
| `event_vp` | 事件-VP |
| `event_search` | 事件-检索 |
| `event_mechanism` | 事件-机制 |
| `event_utility` | 事件-功能 |
| `event_power` | 事件-权谋 |
| `public` | 公共 |
| `goal` | 目标 |
| `emperor` | 君主 |

---

### 1.4 角色牌 (Hero Card) JSON 格式

```json
{
  "card_id": "苻坚_苻坚_1",
  "name": "苻坚",
  "card_category": "hero_north",
  "owner_faction": "苻坚",
  "start_order": 0,
  "initial_contribution": 0,
  "initial_prestige": 0,
  "initial_order": 1,
  "staff_limit": 4,
  "text": "主动：弃1张手牌，然后摸1张牌，可以执行1个手牌行动。登场：转化[长安][弘农][安定][平阳]",
  "markers": { "affair": 1 },
  "parsed_effect": {
    "blocks": [
      {
        "ability_type": "active",
        "steps": [
          { "effect_type": "draw_cards", "params": { "count": 1 } },
          { "effect_type": "extra_action", "params": { "count": 1, "action_type": "hand_action", "may": true } }
        ],
        "costs": [
          { "cost_type": "discard_cards", "params": { "count": 1, "from_hand": true } }
        ]
      },
      {
        "ability_type": "enter",
        "steps": [
          { "effect_type": "convert", "params": { "count": 4, "specific_locations": ["长安","弘农","安定","平阳"] } }
        ]
      }
    ],
    "restrictions": []
  }
}
```

**角色牌特有字段：**
- `start_order`: 先动值（越小越先行动）
- `initial_contribution`: 初始功绩
- `initial_prestige`: 初始威望
- `initial_order`: 初始顺位
- `staff_limit`: 幕僚区上限（东晋=3, 北方=4, 刘裕=5）

---

### 1.5 行动牌 (Action Card) JSON 格式

涵盖策略牌、事件牌、幕僚牌、强制事件牌、公共牌、初始牌。

```json
{
  "card_id": "通用_募兵_1",
  "name": "募兵",
  "cost": 1,
  "card_type": "strategy",
  "card_category": "strategy_military",
  "owner_faction": "通用",
  "text": "行动：支付2vp，获得5军力。",
  "parsed_effect": {
    "is_usurp": false,
    "faction_restriction": null,
    "restrictions": [],
    "blocks": [
      {
        "ability_type": "strategy_action",
        "steps": [
          { "effect_type": "gain_military", "params": { "amount": 5 } }
        ],
        "costs": [
          { "cost_type": "pay_vp", "params": { "amount": 2 } }
        ]
      }
    ],
    "play_condition": null
  },
  "history_vp": -6,
  "markers": { "military": 1 },
  "resource_option": { "army": 2, "vp": 0 }
}
```

**行动牌通用字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `cost` | int | 打出费用 (0-3) |
| `card_type` | string | "strategy" / "event" / "friend" / "mechanism" / "initial" / "public" / "refugee" |
| `card_category` | string | 见 §1.3 |
| `owner_faction` | string | 归属势力 |
| `text` | string | 原始中文效果文本（仅用于显示/调试） |
| `parsed_effect.is_usurp` | bool | 含僭越效果 |
| `parsed_effect.faction_restriction` | string\|null | "jin" / "north" / null |
| `parsed_effect.restrictions` | list | 如 `["cannot_be_archived", "cannot_be_drafted"]` |
| `parsed_effect.blocks` | list | 能力块数组 |
| `parsed_effect.play_condition` | Condition\|null | 打出条件 |
| `history_vp` | int | 存档时获得的史书 VP |
| `markers` | dict | 标记类型 → 数量，如 `{"military": 1, "culture": 1}` |
| `culture_tags` | dict | 文化贡献，如 `{"confucianism": 1}` |
| `resource_option` | dict\|null | 朝堂资源产出，如 `{"army": 2, "vp": 0}` |
| `is_public` | bool | 是否为公共行动牌 |

---

### 1.6 目标牌 (Goal Card) JSON 格式

```json
{
  "card_id": "goal_天府之土_1",
  "name": "天府之土",
  "simple_vp": 7,
  "full_vp": 14,
  "simple_condition_ast": {
    "condition_type": "friendly_control_region",
    "params": { "region": "巴蜀" }
  },
  "full_condition_ast": {
    "condition_type": "control_region",
    "params": { "region": "巴蜀" }
  }
}
```

目标牌的所有条件均已从中文文本转换为 Condition AST，存储在 `simple_condition_ast` 和 `full_condition_ast` 字段中。

---

### 1.7 君主牌 (Emperor Card) JSON 格式

```json
{
  "card_id": "emperor_守成_1",
  "name": "守成",
  "initial_prestige": 5,
  "emperor_tasks": ["march","march","fortify","fortify","reform","spread_culture"],
  "effect_ast": { "effect_type": "skip_emperor_die", "params": {} }
}
```

君主骰任务面已从中文转为英文关键字：
- `march` = 扩张
- `fortify` = 加固
- `reform` = 改革
- `spread_culture` = 文化
- `art` = 艺术

---

## 2. ability_type（能力类型）

**定义文件：** [effect_ast.py](../engine/cards/effect_ast.py#L135)

| 值 | 中文 | 说明 |
|----|------|------|
| `active` | 主动 | 玩家支付 cost 后手动激活，有 `costs` 和 `steps` |
| `passive` | 被动 | 满足 trigger 条件时自动触发，有 `trigger`、`trigger_scope`、`trigger_filter`、`steps` |
| `enter` | 登场 | 角色/幕僚登场时立即执行，无 cost |
| `forced` | 强制 | 机制牌/流民牌的强制效果，无条件自动执行 |
| `strategy_action` | 行动 | 策略牌/初始牌在朝堂区的行动效果，通过 CourtAction 执行 |

`AbilityBlock` 数据结构：

```python
@dataclass
class AbilityBlock:
    ability_type: str = ""          # "active" | "passive" | "enter" | "forced" | "strategy_action"
    trigger: Optional[str] = None   # 仅 passive: on_march / on_archive / ...
    trigger_scope: str = "self"     # "self" | "any"
    trigger_filter: Optional[dict] = None  # {"marker": "power"} / {"card": "流民"}
    costs: list[Cost] = []          # 块级费用
    steps: list[EffectStep] = []    # 效果步骤
    usurp_steps: list[EffectStep] = []     # 僭越额外效果
    choice_options: list = []       # 选择项
    resource_option: Optional[dict] = None # 朝堂资源
```

---

## 3. effect_type（效果类型）

**定义文件：** [effect_ast.py](../engine/cards/effect_ast.py#L80) + [effect_parser.py](../engine/cards/effect_parser.py#L1979) + 实际 JSON 使用

### 3.1 资源变化

| effect_type | params | 说明 |
|-------------|--------|------|
| `gain_military` | `amount` (int) | 获得军力 |
| `gain_vp` | `amount` (int) | 获得 VP |
| `lose_vp` | `amount` (int) | 失去 VP |
| `lose_military` | `amount` (int) | 失去军力 |
| `pay_military` | `amount` (int) | 支付军力（作为步骤） |
| `pay_vp` | `amount` (int) | 支付 VP（作为步骤） |

> **注意：** 支付效果应优先使用 `costs` 数组中的 `cost_type` 项（见 §5），而非 step 中的 `lose_vp`/`pay_military`。

### 3.2 卡牌操作

| effect_type | params | 说明 |
|-------------|--------|------|
| `draw_cards` | `count` (int), `may` (bool, optional) | 摸牌 |
| `discard_cards` | `count` (int), `from_hand` (bool) | 弃牌 |
| `archive_this` | (none) | 存档此牌 |
| `archive_card` | `count` (int), `card_type` ("friend"\|"court"\|"any"), `from` ("staff"\|null) | 存档指定类型的牌 |
| `owner_archive_card` | `count` (int), `card_type` ("friend"), `from` ("staff") | 卡牌所有者存档（非当前玩家存档） |
| `search` | `count` (int), `search_type` ("strategy"\|"friend"\|"military"\|"culture"\|"power"\|"affair") | 检索牌组 |
| `draft` | `count` (int) | 征发（从对应弃牌区拿牌） |
| `supply_court` | `count` (int) | 补充牌到朝堂区 |
| `play_card` | `count` (int), `card_type` ("friend"\|"any"), `may` (bool), `free` (bool) | 从手牌打出 |
| `remove_from_game` | `count` (int), `from_reserve` (bool), `target` ("troop"\|null) | 从游戏中移除 |

### 3.3 地图操作

| effect_type | params | 说明 |
|-------------|--------|------|
| `march` | `free` (bool), `count` (int) | 进军 |
| `convert` | `count` (int), `filter` (dict), `specific_locations` (list) | 转化地点（转为当前玩家占据） |
| `convert_to_neutral` | (none) | 转为中立占据（用于 targeted_effect 的 sub_effect） |
| `convert_to_sima` | (none) | 转为司马家占据（用于 targeted_effect 的 sub_effect） |
| `fortify` | `free` (bool), `count` (int), `target` ("friendly"\|null), `bonus_vp_if_not_own` (int) | 加固 |
| `spread_culture` | `count` (int), `culture` ("confucianism"\|"taoism"\|"buddhism"\|null) | 传播文化 |

### 3.4 轨道变更

| effect_type | params | 说明 |
|-------------|--------|------|
| `raise_order` | `amount` (int) | 提高顺位 |
| `lower_order` | `amount` (int) | 降低顺位 |
| `raise_prestige` | `amount` (int) | 提高威望 |
| `lower_prestige` | `amount` (int) | 降低威望 |
| `raise_contribution` | `amount` (int) | 提高功绩 |
| `lower_contribution` | `amount` (int) / `lose_contribution` | 降低功绩 |
| `gain_prestige` | `amount` (int) | 获得威望（同 raise_prestige） |

### 3.5 文化操作

| effect_type | params | 说明 |
|-------------|--------|------|
| `raise_culture_contribution` | `culture` (str) | 提高文化贡献度 |
| `remove_culture_marker` | `count` (int), `culture` (str) | 移除文化标记 |
| `flip_culture_marker` | (none) | 翻转文化标记 |
| `spread_culture` | `count` (int), `culture` (str) | 传播文化 |

### 3.6 标记/令牌/特殊

| effect_type | params | 说明 |
|-------------|--------|------|
| `get_expedition` | (none) | 获得[北伐]标记 |
| `place_refugee` | `target` ("own_national_discard"\|"jin_discard"\|"north_discard") | 放置流民牌 |
| `reshuffle_emperor` | (none) | 重洗君主牌 |
| `steal_random_card` | `count` (int) | 随机偷牌 |
| `give_card` | `count` (int), `from_hand` (bool) | 给牌 |
| `swap_troops` | (none) | 交换军队位置 |
| `convert_own_to_neutral` | `count` (int) | 转化己方地点为中立 |

### 3.7 复合/元效果

| effect_type | params | 说明 |
|-------------|--------|------|
| `choice` | `choice_options` (list) | 选择一项执行（见 §9） |
| `targeted_effect` | `target` (dict), `sub_effect` (dict) / `sub_effects` (list) | 目标选择后执行效果（见 §8） |
| `extra_action` | `count` (int), `action_type` ("hand_action"\|"court_action"), `may` (bool) | 额外行动机会 |
| `march_cost_reduction` | `per_turn_limit` (int), `amount` (int) | 进军费用减免（被动） |
| `region_reward_override` | `partial` (int), `full` (int) | 区域奖励覆盖 |
| `skip_emperor_die` | (none) | 不投掷君主骰（君主牌纯质） |

---

## 4. condition_type（条件类型）

**定义文件：** [effect_ast.py](../engine/cards/effect_ast.py#L24) + [effect_parser.py](../engine/cards/effect_parser.py#L756) + [game.py](../engine/engine/game.py#L327)

Condition 数据结构：

```python
@dataclass
class Condition:
    condition_type: str = ""        # e.g. "control_region", "compare", "and"
    params: dict[str, Any] = {}
```

### 4.1 逻辑条件

| condition_type | params | 说明 |
|----------------|--------|------|
| `and` | `conditions` (list of Condition) | 所有子条件均满足 |
| `not` | `condition` (Condition) | 条件取反 |
| `compare` | `left` (str), `op` (str), `right` (int\|str) | 数值比较 |

`compare` 的 `left` 取值：`"hand_count"`, `"military"`, `"prestige"`, `"contribution"`, `"order"`, `"history_count"`, `"power_marker_count"`, `"prestige_lead"`

`compare` 的 `op` 取值：`">"`, `">="`, `"=="`, `"<"`, `"<="`

### 4.2 势力/僭越条件

| condition_type | params | 说明 |
|----------------|--------|------|
| `is_faction` | `faction` ("jin"\|"north") | 玩家属于指定势力 |
| `can_usurp` | (none) | 玩家可以执行僭越效果 |
| `is_lowest_order` | (none) | 顺位最低（最高 order 值） |
| `is_lowest_culture_sum` | (none) | 文化贡献总和最低 |
| `order_lowest` | (none) | 同 is_lowest_order |
| `prestige_highest` | (none) | 威望最高 |

### 4.3 地图/区域条件

| condition_type | params | 说明 |
|----------------|--------|------|
| `control_region` | `region` (str) | 玩家完全控制该区域 |
| `friendly_control_region` | `region` (str) | 友方控制该区域 |
| `occupy_location` | `location` (str) | 占据指定地点 |
| `occupy_location_in_region` | `region` (str) | 占据该区域中至少一个地点 |
| `has_route` | `from` (str), `to` (str), `controller` (str) | 存在指定控制者的线路 |

区域名称取值（中文）：`"西凉"`, `"关中"`, `"巴蜀"`, `"荆襄"`, `"江南"`, `"中原"`, `"山西"`, `"山东"`, `"淮南"`, `"河北"`, `"幽燕"`, `"关外"`

### 4.4 文化/标记条件

| condition_type | params | 说明 |
|----------------|--------|------|
| `culture_contribution_gt` | `culture` (str), `threshold` (int) | 文化贡献度超过 X |
| `culture_level_gt` | `culture` (str), `threshold` (int) | 文化等级超过 X |
| `culture_most_empty` | `culture` (str) | 该文化轨道露出空格最多 |
| `marker_count_gt` | `marker` (str), `threshold` (int) | 标记数超过 X |
| `has_token` | (varies) | 拥有指定标记/令牌 |
| `has_expedition` | (none) | 拥有[北伐]标记 |
| `has_military` | `amount` (int) | 军力不少于 X |

culture 取值：`"confucianism"`, `"taoism"`, `"buddhism"`

### 4.5 其他条件

| condition_type | params | 说明 |
|----------------|--------|------|
| `archive_count_ge` | `count` (int) | 存档区牌数 ≥ X |
| `staff_has_space` | (none) | 幕僚区有空位 |
| `on_action_this_turn` | `action` ("march"\|"occupy"\|"fortify"\|"convert") | 本回合执行过指定行动 |
| `not_completed_goal` | `goal` (str) | 未完成指定目标牌 |
| `order_lowest` | (none) | 东晋玩家中顺位最低 |

---

## 5. cost_type（费用类型）

**定义文件：** [effect_ast.py](../engine/cards/effect_ast.py#L32) + [effect_parser.py](../engine/cards/effect_parser.py#L346)

Cost 数据结构：

```python
@dataclass
class Cost:
    cost_type: str = ""             # "discard_cards" | "pay_military" | "pay_vp" | "abandon_court_card"
    params: dict[str, Any] = {}     # {"count": N, "from_hand": true, ...}
```

| cost_type | params | 说明 | 使用位置 |
|-----------|--------|------|----------|
| `discard_cards` | `count` (int), `from_hand` (bool) | 弃置手牌 | block.costs / option.costs |
| `pay_military` | `amount` (int) | 支付军力 | block.costs / option.costs |
| `pay_vp` | `amount` (int) | 支付 VP | block.costs / option.costs |
| `abandon_court_card` | `count` (int) | 弃置朝堂牌 | block.costs |

**费用放置位置：**

1. **Block 级别**（`strategy_action` / `active` block 的 `costs` 字段）— 整个能力块的费用
   ```json
   { "ability_type": "strategy_action", "costs": [{ "cost_type": "pay_military", "params": { "amount": 7 } }], "steps": [...] }
   ```

2. **Choice option 级别**（choice 中每个选项的 `costs` 字段）— 该选项独有费用
   ```json
   { "steps": [...], "costs": [{ "cost_type": "pay_vp", "params": { "amount": 3 } }] }
   ```

---

## 6. trigger（触发器）

**定义文件：** [effect_ast.py](../engine/cards/effect_ast.py#L147) + [enums.py](../engine/models/enums.py#L163)

仅用于 `ability_type: "passive"` 的 AbilityBlock。

```json
{
  "ability_type": "passive",
  "trigger": "on_spread_culture",
  "trigger_scope": "any",
  "trigger_filter": { "culture": "buddhism" },
  "steps": [ { "effect_type": "draw_cards" } ]
}
```

| trigger | 触发时机 | 典型 scope |
|---------|----------|------------|
| `on_march` | 进军后 | self / any |
| `on_convert` | 转化后 | self / any |
| `on_archive` | 存档后 | self / any |
| `on_discard` | 弃牌后 | self / any |
| `on_fortify` | 加固后 | self / any |
| `on_spread_culture` | 传播文化后 | self / any |
| `on_play_card` | 打出牌后 | self / any |
| `on_gain_vp` | 获得 VP 后 | self / any |
| `on_gain_contribution` | 获得功绩后 | self / any |
| `on_gain_prestige` | 获得威望后 | self / any |
| `on_order_change` | 顺位变化后 | self / any |
| `on_court_action` | 执行牌组行动后 | self / any |
| `on_usurp` | 结算僭越效果时 | self / any |
| `on_card_leave` | 幕僚牌离场时 | self |
| `on_card_enter` | 卡牌登场时 | self / any |
| `on_region_reward` | 获得区域奖励时 | self |
| `on_turn_start` | 回合开始时 | self / any |
| `on_turn_end` | 回合结束时 | self / any |
| `on_end_game` | 游戏结束时 | self |
| `always` | 始终生效（静态能力） | self |

**trigger_scope：**
- `"self"` — 仅拥有者触发
- `"any"` — 任意玩家触发

**trigger_filter 常用格式：**
- `{"marker": "power"}` — 打出含[权谋]标记的牌时
- `{"marker": "military"}` — 打出含[军事]标记的牌时
- `{"marker": "culture"}` — 打出含[文化]标记的牌时
- `{"culture": "buddhism"}` — 文化为佛学时
- `{"card": "流民"}` — 特定卡牌

---

## 7. Filter（过滤器）

### 7.1 Convert 地点过滤器

用于 `convert` 效果的 `params.filter`：

| 字段 | 取值 | 说明 |
|------|------|------|
| `controller` | `"sima"` / `"jin"` / `"north"` / `"neutral"` / `"friendly"` / `"non_friendly"` | 地点控制者 |
| `adjacent` | `true` | 仅相邻地点 |
| `exclude_locations` | `["建康", ...]` | 排除指定地点 |
| `exclude_regions` | `["江南", "荆襄"]` | 排除指定区域 |

### 7.2 Location 选择过滤器

用于 `targeted_effect` 的 `target.filters`（见 §8.2）：

| filter key | 格式 | 说明 |
|------------|------|------|
| `type: "not_fortified"` | `{"type": "not_fortified"}` | 未加固 |
| `type: "not_jin_controlled"` | `{"type": "not_jin_controlled"}` | 非东晋占据 |
| `culture_region` | `{"culture_region": "taoism"}` | 文化区域（儒学/玄学/佛学） |
| `region_name` | `{"region_name": "关中"}` | 地理区域名称 |
| `region_name` (multi) | `{"region_name": ["江南", "荆襄"]}` | 多个地理区域（OR） |
| `controller` | `{"controller": "friendly"}` | 友方 |
| `controller` | `{"controller": "sima"}` | 司马家 |

---

## 8. targeted_effect（目标效果）

**实现：** [effect_parser.py](../engine/cards/effect_parser.py) — `_parse_targeted_effect`, `_parse_target`

`targeted_effect` 是"选择目标 → 对目标执行效果"的复合模式。结构：

```json
{
  "effect_type": "targeted_effect",
  "params": {
    "target": {
      "type": "location",
      "count": 1,
      "selection": "choose",
      "filters": [ ... ]
    },
    "sub_effect": {
      "effect_type": "convert_to_neutral",
      "params": {}
    }
  }
}
```

### 8.1 Target 类型

| target.type | 说明 | selection 取值 |
|-------------|------|----------------|
| `player` | 任意玩家 | choose / random / all |
| `jin_player` | 东晋玩家 | choose / each |
| `other_jin_player` | 其他东晋玩家 | choose / each |
| `friendly_player` | 友方玩家 | choose |
| `location` | 地图地点 | choose / random |
| `card` | 卡牌 | choose |
| `friend_card` | 幕僚牌 | choose |
| `court_card` | 朝堂区牌 | choose |
| `hand_card` | 手牌 | choose |
| `sima` | 司马家（无需选择） | — |
| `chancellor` | 宰辅（无需选择） | — |
| `culture_marker_on_map` | 版图文化标记 | choose |

### 8.2 sub_effect vs sub_effects

- `sub_effect` (单数)：对每个目标执行的单一效果
- `sub_effects` (复数)：对每个目标执行的多个效果（数组），支持独立的 `condition` 和 `source_text`

```json
"sub_effects": [
  {
    "effect_type": "convert_to_sima",
    "params": {},
    "condition": { "condition_type": "not", "params": { "condition": { "condition_type": "can_usurp", "params": {} } } },
    "source_text": "转为司马家占据"
  },
  {
    "effect_type": "convert",
    "params": {},
    "condition": { "condition_type": "can_usurp", "params": {} },
    "source_text": "转为玩家占据"
  }
]
```

---

## 9. choice 结构

**choice** 是"从多个选项中选择一项执行"的模式。用于 effect step 中。

### 9.1 简单 choice（无每选项费用）

```json
{
  "effect_type": "choice",
  "choice_options": [
    [
      { "effect_type": "gain_military", "params": { "amount": 3 } },
      { "effect_type": "gain_vp", "params": { "amount": 2 } }
    ],
    [
      { "effect_type": "draw_cards" }
    ]
  ]
}
```

`choice_options` 是 `list[list[EffectStep]]` — 外层数组的每个元素是一个选项，每个选项是一个步骤列表。

### 9.2 带费用的 choice

```json
{
  "effect_type": "choice",
  "choice_options": [
    {
      "costs": [{ "cost_type": "pay_vp", "params": { "amount": 3 } }],
      "steps": [{ "effect_type": "gain_military", "params": { "amount": 5 } }]
    },
    {
      "costs": [{ "cost_type": "pay_military", "params": { "amount": 3 } }],
      "steps": [{ "effect_type": "archive_this" }]
    }
  ]
}
```

当每个选项有不同的费用时，使用对象格式 `{costs: [...], steps: [...]}`。

### 9.3 choice 的位置

`choice` 作为 step 嵌入在 block 的 `steps` 数组中，执行顺序由其位置确定。可以在 choice 前后放置其他步骤：

```json
"steps": [
  { "effect_type": "choice", "choice_options": [...] },
  { "effect_type": "gain_vp", "params": { "amount": 3 } }
]
```

---

## 10. 代码实现索引

| 模块 | 文件 | 职责 |
|------|------|------|
| **数据模型** | | |
| 枚举定义 | [engine/models/enums.py](../engine/models/enums.py) | CardType, CardCategory, FactionType, Region, CultureType, MarkerType, ActionType, EventTrigger, ControlState 等 |
| 卡牌模型 | [engine/models/card.py](../engine/models/card.py) | CardDef (不可变定义), Card (运行时实例), CardLibrary (查询) |
| 玩家模型 | [engine/models/player.py](../engine/models/player.py) | Player 数据类 |
| 游戏状态 | [engine/models/game_state.py](../engine/models/game_state.py) | GameState, 地点查询方法 |
| **AST** | | |
| 效果 AST | [engine/cards/effect_ast.py](../engine/cards/effect_ast.py) | EffectStep, Condition, Cost, AbilityBlock, CardEffect, EffectType/AbilityType/TriggerType 常量 |
| 标签系统 | [engine/cards/tags.py](../engine/cards/tags.py) | 卡牌标签分类 |
| **解析** | | |
| 效果解析器 | [engine/cards/effect_parser.py](../engine/cards/effect_parser.py) | EffectParser 类，_STEP_PATTERNS (35个模式匹配器)，文本→AST |
| 卡牌加载器 | [engine/cards/loader.py](../engine/cards/loader.py) | CSV→CardDef，编译到 cards_compiled.json |
| **执行** | | |
| 效果解析器 | [engine/cards/effect_resolver.py](../engine/cards/effect_resolver.py) | EffectResolver: AST→实际操作 |
| 行动系统 | [engine/engine/action_system.py](../engine/engine/action_system.py) | 行动框架 |
| 手牌行动 | [engine/engine/actions/card_actions.py](../engine/engine/actions/card_actions.py) | PlayCardAction, CourtAction |
| 快速行动 | [engine/engine/actions/quick_actions.py](../engine/engine/actions/quick_actions.py) | OccupyAction, MarchAction, DrawAction, RecruitAction, FortifyAction |
| 特殊行动 | [engine/engine/actions/special_actions.py](../engine/engine/actions/special_actions.py) | ConvertAction, ArchiveAction, SpreadCultureAction, SearchAction, LevyAction, RaiseOrderAction, LowerOrderAction |
| **游戏逻辑** | | |
| 游戏主循环 | [engine/engine/game.py](../engine/engine/game.py) | Game 类, _check_event_condition (事件卡打出条件检查) |
| 游戏日志 | [engine/engine/game_logger.py](../engine/engine/game_logger.py) | 结构化日志 |
| 阶段 | [engine/engine/phases.py](../engine/engine/phases.py) | 回合阶段管理 |
| 区域控制 | [engine/rules/area_control.py](../engine/rules/area_control.py) | 区域控制判定，REGION_CONFIG |
| 目标计分 | [engine/rules/goals.py](../engine/rules/goals.py) | 终局目标牌计分 |
| 僭越 | [engine/rules/usurp.py](../engine/rules/usurp.py) | 僭越规则 |
| 司马家 | [engine/rules/sima.py](../engine/rules/sima.py) | 司马家威望逻辑 |
| 计分 | [engine/rules/scoring.py](../engine/rules/scoring.py) | 阶段计分 |
| **数据** | | |
| 编缉卡牌 | [versions/v1.0/cards/cards_compiled.json](../versions/v1.0/cards/cards_compiled.json) | 所有卡牌的编译后 JSON |
| 卡牌设计 | [versions/v1.0/cards/card_design.csv](../versions/v1.0/cards/card_design.csv) | 卡牌设计 CSV |
| 目标牌 | [versions/v1.0/cards/card_goal.csv](../versions/v1.0/cards/card_goal.csv) | 目标牌 CSV |
| 君主牌 | [versions/v1.0/cards/card_emperor.csv](../versions/v1.0/cards/card_emperor.csv) | 君主牌 CSV |
| 地图数据 | [engine/config/map_adjacency.yaml](../engine/config/map_adjacency.yaml) | 地图邻接与区域定义 |

---

## 附录：本次整理移除的遗留模式

以下模式已被完全消除，不应再出现在 JSON 中：

| 遗留模式 | 替代方案 |
|----------|----------|
| `play_condition_note` (文本) | `play_condition` (Condition AST) |
| `archive_friend` | `archive_card` + `card_type: "friend"` + `from: "staff"` |
| `target_archive_friend` | `targeted_effect` + `archive_card` sub_effect |
| `play_card_excluding_tag` | `play_card` + `filter: {exclude_marker: "..."}` |
| `faction_label` (作为 step) | `condition: {condition_type: "is_faction"}` 加在 step 上 |
| `change_controller` | `convert_to_sima` / `convert_to_neutral` / `convert` |
| `raw_text` (condition) | 具体 condition_type |
| `choice_options` 作为 block 的平级字段 | `choice` step 嵌入 `steps[]` 数组 |
| 中文 `variable_source` | 英文 `amount` 关键字 |
| 中文 trigger | 英文 trigger + trigger_filter |
| 中文 emperor_tasks | 英文关键字数组 |
| 中文 goal conditions | Condition AST |
