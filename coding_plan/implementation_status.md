# 关键字实现状态检查报告

> 检查日期：2026-07-05  
> 数据来源：`versions/v1.0/cards/cards_compiled.json` → `engine/` 代码  
> 格式：✅ 已实现 / ⚠️ 部分实现 / ❌ 未实现 / 🔧 实现但路径不一致

---

## 总览

| 类别 | 总数 | 已实现 | 未实现 | 覆盖率 |
|------|------|--------|--------|--------|
| effect_type | 47 | 22 | 25 | 47% |
| condition_type | 25 | 6 | 19 | 24% |
| cost_type | 4 | 3 | 1 | 75% |
| trigger | 19 | 0¹ | 19 | 0% |

> ¹ trigger 由 AbilityBlock 定义，但 `effect_resolver._resolve_block` 未处理 passive block（不检查 trigger，不监听事件）。

---

## 1. effect_type 实现状态

**检查目标：** `engine/cards/effect_resolver.py` — `_execute_step()` 方法

### 1.1 资源变化

| effect_type | 状态 | 实现位置 | 备注 |
|-------------|------|----------|------|
| `gain_military` | ✅ | effect_resolver.py:103 | |
| `gain_vp` | ✅ | effect_resolver.py:109 | 含 150VP 终局检测 |
| `lose_vp` | ❌ | — | 仅在 targeted_effect 的 sub_effect 中使用，无独立处理 |
| `lose_military` | ❌ | — | |
| `pay_military` | ✅ | effect_resolver.py:118 | |
| `pay_vp` | ✅ | effect_resolver.py:123 | |

### 1.2 卡牌操作

| effect_type | 状态 | 实现位置 | 备注 |
|-------------|------|----------|------|
| `draw_cards` | ⚠️ | effect_resolver.py:128 | 仅从 main_deck 抽，不支持 faction_deck |
| `discard_cards` | ⚠️ | effect_resolver.py:137 | 仅弃手牌，不支持指定卡牌 |
| `archive_this` | ⚠️ | effect_resolver.py:143 | 仅发事件，由调用方处理 |
| `archive_card` | ⚠️ | effect_resolver.py:147 | 仅从手牌存档，不支持 from: "staff" |
| `owner_archive_card` | ❌ | — | 卡牌所有者存档，非当前玩家 |
| `search` | ⚠️ | effect_resolver.py:188 | 委托 SearchAction，但 search_type 解析有限 |
| `draft` | ⚠️ | effect_resolver.py:238 | 仅发事件，未实现实际征发 |
| `supply_court` | ✅ | effect_resolver.py:243 | |
| `play_card` | ❌ | — | 无执行逻辑 |
| `remove_from_game` | ❌ | — | |
| `extra_action` | ❌ | — | 无执行逻辑 |

### 1.3 地图操作

| effect_type | 状态 | 实现位置 | 备注 |
|-------------|------|----------|------|
| `march` | ⚠️ | effect_resolver.py:199 | 仅发事件请求，无实际 march 执行 |
| `convert` | ⚠️ | effect_resolver.py:159 | 仅支持 `specific_locations`，不支持 `filter` (controller/adjacent/exclude) |
| `convert_to_neutral` | ❌ | — | 仅在 targeted_effect sub_effect 中引用 |
| `convert_to_sima` | ❌ | — | 仅在 targeted_effect sub_effect 中引用 |
| `fortify` | ⚠️ | effect_resolver.py:208 | 仅发事件请求，无实际 fortify 执行 |
| `spread_culture` | ⚠️ | effect_resolver.py:175 | 委托 SpreadCultureAction，但 target_region 硬编码为空 |
| `convert_own_to_neutral` | ❌ | — | |

### 1.4 轨道变更

| effect_type | 状态 | 实现位置 | 备注 |
|-------------|------|----------|------|
| `raise_order` | ✅ | effect_resolver.py:216 | |
| `lower_order` | ✅ | effect_resolver.py:226 | |
| `raise_prestige` | ❌ | — | |
| `lower_prestige` | ❌ | — | 仅在 targeted_effect sub_effect 中使用 |
| `raise_contribution` | ❌ | — | |
| `lower_contribution` / `lose_contribution` | ❌ | — | |

### 1.5 文化操作

| effect_type | 状态 | 实现位置 | 备注 |
|-------------|------|----------|------|
| `raise_culture_level` | ✅ | effect_resolver.py:261 | |
| `raise_culture_contribution` | ❌ | — | |
| `remove_culture_marker` | ❌ | — | |
| `flip_culture_marker` | ❌ | — | |

### 1.6 标记/令牌

| effect_type | 状态 | 实现位置 | 备注 |
|-------------|------|----------|------|
| `get_expedition` | ✅ | effect_resolver.py:252 | |
| `place_refugee` | ❌ | — | |
| `reshuffle_emperor` | ❌ | — | |
| `steal_random_card` | ❌ | — | |
| `give_card` | ❌ | — | |
| `swap_troops` | ❌ | — | |

### 1.7 复合/元效果

| effect_type | 状态 | 实现位置 | 备注 |
|-------------|------|----------|------|
| `choice` (step 类型) | ❌ | — | `_resolve_block` 仅处理 block-level choice_options，不处理 step 中的 choice |
| `targeted_effect` | ❌ | — | **最大的缺口** — 大量卡牌依赖此模式 |
| `march_cost_reduction` | ❌ | — | 被动效果，需在 march 费用计算时查询 |
| `region_reward_override` | ❌ | — | 被动效果，需在区域奖励计算时查询 |
| `skip_emperor_die` | ❌ | — | 君主牌效果 |

---

## 2. condition_type 实现状态

### 2.1 `_check_event_condition` (game.py:327)

用于事件牌打出条件检查。

| condition_type | 状态 | 备注 |
|----------------|------|------|
| `order_lowest` | ✅ | game.py:336 |
| `control_region` | ✅ | game.py:343 (仅匹配 location 名→region，不支持 region 名) |
| `occupy_location_in_region` | ✅ | game.py:352 (本次新增) |
| `has_expedition` | ✅ | game.py:362 |
| `has_military` | ✅ | game.py:365 |
| `staff_has_space` | ✅ | game.py:369 |
| **以下全部缺失：** | | |
| `and` | ❌ | 复合条件的基础构建块 |
| `not` | ❌ | 取反条件的基础构建块 |
| `compare` | ❌ | 数值比较的基础构建块 |
| `can_usurp` | ❌ | 僭越判断 |
| `is_faction` | ❌ | 势力判断 |
| `culture_contribution_gt` | ❌ | 文化贡献判断 |
| `culture_level_gt` | ❌ | 文化等级判断 |
| `marker_count_gt` | ❌ | 标记数判断 |
| `is_lowest_order` | ❌ | 顺位最低判断 |
| `is_lowest_culture_sum` | ❌ | 文化总和最低判断 |
| `friendly_control_region` | ❌ | 友方控制区域判断 |
| `occupy_location` | ❌ | 占据特定地点判断 |
| `archive_count_ge` | ❌ | 存档数判断 |
| `has_token` | ❌ | 拥有标记判断 |
| `has_route` | ❌ | 线路判断 |
| `on_action_this_turn` | ❌ | 回合行动判断 |
| `prestige_highest` | ❌ | 威望最高判断 |
| `not_completed_goal` | ❌ | 目标牌完成判断 |
| `culture_most_empty` | ❌ | 文化轨道空位判断 |

### 2.2 `_check_condition` (effect_resolver.py:301)

```python
def _check_condition(self, condition, state, player_id) -> bool:
    return True  # 完全未实现
```

### 2.3 `_check_condition` (goals.py:80)

**路径不一致：** 使用 regex 匹配中文文本，而非读取 `simple_condition_ast` / `full_condition_ast`。

---

## 3. cost_type 实现状态

| cost_type | 状态 | 实现位置 | 备注 |
|-----------|------|----------|------|
| `discard_cards` | ⚠️ | parser 提取到 block.costs | effect_resolver 不处理 costs |
| `pay_military` | ⚠️ | 同上 | effect_resolver 不处理 costs |
| `pay_vp` | ⚠️ | 同上 | effect_resolver 不处理 costs |
| `abandon_court_card` | ❌ | — | |

**根本问题：** `effect_resolver._resolve_block` 不检查 `block.costs`。Cost 只在 parser 中被提取到 `AbilityBlock.costs`，但执行时被忽略。

---

## 4. trigger/passive 实现状态

| 能力 | 状态 | 备注 |
|------|------|------|
| passive block 触发 | ❌ | `_resolve_block` 不区分 passive 和其他类型 — 直接执行 steps |
| trigger 过滤 | ❌ | 不检查 `trigger` / `trigger_scope` / `trigger_filter` |
| 事件监听系统 | ❌ | 无事件总线，被动效果无法自动触发 |
| usurp_steps 执行 | ❌ | 有代码 (`_resolve_block:83`) 但 condition 检查是 stub |

---

## 5. 关键缺口优先级

### P0: 阻塞大多数卡牌

| 缺口 | 影响 |
|------|------|
| `targeted_effect` 解析与执行 | 28+ 张卡牌使用此模式（选择目标→执行效果） |
| `choice` step 类型 | 15+ 张卡牌使用 choice 嵌入 steps |
| `_check_condition` (effect_resolver) | 所有带条件的 step 都无法正确判断 |
| block.costs 执行 | 所有带费用的能力都不扣费 |

### P1: 阻塞核心玩法

| 缺口 | 影响 |
|------|------|
| `play_card` 执行 | 5+ 张卡牌要求从手牌打出牌 |
| `convert` filter 支持 | 8+ 张卡牌使用 controller/adjacent filter |
| `march`/`fortify` 实际执行 | 免费 march/fortify 不执行 |
| `spread_culture` target_region | 传播文化缺少目标区域选择 |
| 被动效果系统 | 所有 passive ability 无法自动触发 |

### P2: 阻塞特定卡牌

| 缺口 | 影响 |
|------|------|
| `place_refugee` | 3+ 张卡牌 |
| `raise_prestige` / `lower_prestige` | 6+ 张卡牌 |
| `raise_contribution` / `lower_contribution` | 4+ 张卡牌 |
| `owner_archive_card` | 鸩酒等 |
| `convert_to_neutral` / `convert_to_sima` | 天师道、遣使请降等 |
| 条件类型（15个） | 大量事件卡打出条件不检查 |
| `draft` 实际征发 | 3+ 张卡牌 |
| `search` 完整支持 | 4+ 张卡牌 |
| goal AST 条件（goals.py） | 目标牌仍用中文 regex 判断，不用 AST |

### P3: 边缘/锦上添花

| 缺口 | 影响 |
|------|------|
| `extra_action` | 少数角色牌 |
| `steal_random_card` / `give_card` | 1-2 张卡牌 |
| `reshuffle_emperor` | 1 张卡牌 |
| `swap_troops` | 1 张卡牌 |
| `remove_from_game` | 1-2 张卡牌 |
| `march_cost_reduction` | 1 张卡牌（被动） |
| `region_reward_override` | 1 张卡牌（被动） |

---

## 6. 架构建议

### 6.1 当前架构问题

```
CSV → effect_parser.py → AST (✅ 完成)
AST → effect_resolver.py → GameState (❌ 大量缺口)
AST → _check_event_condition → bool (❌ 大量缺口)
AST → goals.py → VP (❌ 未使用 AST)
```

解析层（parser→AST）基本完成，但执行层（AST→操作）有大量缺失。

### 6.2 推荐修复顺序

1. **实现 `_check_condition` 递归引擎** — 这是所有条件判断的基础，一次实现后覆盖所有 condition_type
2. **实现 `targeted_effect` 解析执行** — 最大的单点缺口，解锁 28+ 张卡牌
3. **实现 `choice` step 类型** — 解锁 15+ 张卡牌
4. **处理 block.costs** — 解锁费用系统
5. **实现被动效果系统**（事件总线） — 解锁所有被动能力
6. **补充各 effect_type 执行** — 按 P0→P1→P2→P3 逐步覆盖
7. **goals.py 迁移到 AST** — 用 `simple_condition_ast`/`full_condition_ast` 替换 regex
