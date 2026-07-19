# Phase 1：裂缝修复 & 引擎稳定化

> 目标：让 v1.0 新版卡牌系统跑起来，新旧两条路径统一，所有测试全绿。
>
> 前置条件：卡牌 JSON 校对已完成 ✅
>
> 预计时间：1 个开发会话

---

## 一、背景诊断

当前处于 vibe_coding 大冲刺之后的收尾阶段。引擎框架已经搭好（56 个 .py 文件，204/205 测试通过），但存在"两张皮"问题：

- **旧路径**：`load_card_design_csv(card_design.csv)` → 游戏循环测试用的这个，能跑通
- **新路径**：`Version.load('v1.0')` → `cards_compiled.json` → AST，**加载就崩**

新路径是未来的主线（支持多版本切换、特性开关），但还没跑通过。

---

## 二、待修复问题清单（已完成 ✅）

### Bug #1：`CardEffect` 不接受 `usurp_with_tie`

- **文件**：[engine/config/version.py](engine/config/version.py) 第 121 行
- **现象**：`CardEffect.__init__() got an unexpected keyword argument 'usurp_with_tie'`
- **原因**：`version.py` 往 `CardEffect()` 构造器传了 `usurp_with_tie`，但 AST 中这个字段早已迁移到 `AbilityBlock.modifier`（见 [effect_ast.py:58](engine/cards/effect_ast.py#L58)）
- **修法**：`version.py` 去掉 `CardEffect(...)` 调用中的 `usurp_with_tie=`，改为在构建 `AbilityBlock` 时写入 `modifier={"usurp_with_tie": True}`

### Bug #2：新亭对谈 — `filter` 字段不合法

- **文件**：[versions/v1.0/cards/cards_compiled.json](versions/v1.0/cards/cards_compiled.json)（`新亭对谈` 卡）
- **现象**：`EffectStep.__init__() got an unexpected keyword argument 'filter'`
- **原因**：JSON 中 `play_card` 步骤有一个 `"filter": {"exclude_marker": "military"}`，但 `EffectStep` 不接受 `filter` 参数
- **修法**：
  - 方案 A：`version.py` 的 `_dict_to_step()` 中把 `filter` 映射为 `condition`
  - 方案 B：修改 `cards_compiled.json`，将 `"filter"` 改为 `"condition"`，并适配 `Condition` 结构（`{"condition_type": "exclude_marker", "params": {"marker": "military"}}`）
  - **推荐方案 A+B**：JSON 层面用正确字段名，加载器层面也要健壮（遇到未知字段打 warning 而不是崩）

### Bug #3：测试使用的是旧 CSV 路径

- **文件**：[engine/tests/test_game/test_game_loop.py](engine/tests/test_game/test_game_loop.py)
- **现象**：所有游戏循环测试都走 `load_card_design_csv("card_design.csv")`，新版 `Version.load('v1.0')` 路径零覆盖
- **修法**：增加测试用例，使用 `Version.load('v1.0')` 加载卡牌跑完整对局

### Bug #4：`cards_compiled.json` 结构审查

修完上述 bug 后可能还会暴露更多 JSON 结构问题。需要：
1. 跑通 `Version.load('v1.0')` 
2. 加载后对每张卡做一次 `parsed_effect` 的 AST 重建校验
3. 把崩掉的卡全部修掉

---

## 三、实际对局测试发现的 13 个 Bug（全部修复 ✅）

以下 bug 是在 Phase 1 初始修复完成后，通过交互式对局测试发现的。

### #1: 弃牌提示信息不区分场景 ✅
- **现象**：费用弃牌显示"手牌超出上限"
- **文件**：[engine/ai/human_player.py](engine/ai/human_player.py), [engine/ai/interface.py](engine/ai/interface.py), [engine/ai/dummy_ai.py](engine/ai/dummy_ai.py), [engine/engine/game.py](engine/engine/game.py), [engine/play_game.py](engine/play_game.py)
- **修法**：`choose_discards()` 增加 `reason` 参数（"cost" / "hand_limit"），区分不同提示文案。全链路透传（interface → human_player → dummy_ai → game._choose_discard_for_cost → LoggingAgentWrapper）

### #2: 进军/占据/加固需要确认 ✅
- **现象**：进军/占据/加固行动弹出 y/n 确认
- **文件**：[engine/ai/human_player.py](engine/ai/human_player.py)
- **修法**：去掉确认逻辑，直接 `return action`

### #3: `play_requirement` 未统一为 `play_condition` ✅
- **现象**：刁协卡使用 `play_requirement` 被动块，而非卡级别的 `play_condition`
- **文件**：[versions/v1.0/cards/cards_compiled.json](versions/v1.0/cards/cards_compiled.json), [engine/cards/effect_parser.py](engine/cards/effect_parser.py)
- **修法**：
  - JSON: 刁协被动块改为 `play_condition` 字段
  - parser: 自动将 `play_requirement` 步骤转为 `play_condition`

### #4: 谢玄征发未过滤非军事标记牌 ✅
- **现象**：太学（文化标记）出现在谢玄征发候选中
- **文件**：[engine/cards/effect_operators.py](engine/cards/effect_operators.py)
- **根因**：`ChooseOperator` 创建嵌套 `EffectStep` 时，`filter`/`target`/`choice_options` 未从 dict 顶层移入 params
- **修法**：构建 nested step 时检查并移动这三个 key 到 params

### #5: `tracks.culture` 视窗查询返回空 ✅
- **现象**：加官进爵打完后 `tracks.culture` 无数据
- **文件**：[engine/engine/phases.py](engine/engine/phases.py), [engine/viewport/live.py](engine/viewport/live.py), [engine/viewport/snapshot.py](engine/viewport/snapshot.py), [engine/engine/viewport_adapter.py](engine/engine/viewport_adapter.py)
- **根因**：(a) `culture_tracks` 字典从未初始化三种 CultureType 条目；(b) 视窗代码属性名错误（`track.level`/`track.supply` 应为 `supply_level`/`map_count`）
- **修法**：初始化三条文化轨 + 修正所有视窗属性名

### #6: 太学三选项标签完全相同 ✅
- **现象**：太学的儒学/玄学/佛学选择看起来一模一样
- **文件**：[engine/cards/effect_operators.py](engine/cards/effect_operators.py)
- **修法**：为 culture 相关效果的选择标签附加文化类型名（如 `[儒学]传播文化`）

### #7: `_culture` 出现在 locations 列表 + 文化应 per-region ✅
- **文件**：[engine/viewport/utils.py](engine/viewport/utils.py), [engine/engine/actions/special_actions.py](engine/engine/actions/special_actions.py)
- **修法**：移除 setdefault 死代码；文化从 `rs.culture_slots` 读取；`spread_culture` 时填充 `rs.culture_slots`

### #8: 坞堡 — 无问题 ✅

### #9: 摘要应显示全部玩家，每人一行 ✅
- **文件**：[engine/viewport/query.py](engine/viewport/query.py)
- **修法**：重写 `_summary()`，每玩家一行，显示幕僚牌名和历史区

### #10: 皇帝骰子/任务/年龄输出 ✅
- **文件**：[engine/engine/game.py](engine/engine/game.py), [engine/engine/phases.py](engine/engine/phases.py)
- **修法**：准备阶段后打印皇帝骰子结果；结算阶段打印年龄/驾崩事件；每次行动后检查皇帝任务完成

### #11: 募兵 — OK ✅

### #12: `archive_this` 事件牌路径问题 ✅
- **现象**：刘隗等事件牌先进入 main_discard，效果结算后 archive 找不到牌
- **文件**：[engine/engine/actions/card_actions.py](engine/engine/actions/card_actions.py), [engine/engine/actions/special_actions.py](engine/engine/actions/special_actions.py)
- **修法**：新增 `_check_archive_this()` 辅助函数，检查 main_discard 和 staff_area 两处，移到 history_area

### #13: 转化相邻判定 + 北伐规则改造 ✅
- **文件**：[engine/models/game_state.py](engine/models/game_state.py), [engine/cards/effect_operators.py](engine/cards/effect_operators.py), [rulebook.md](rulebook.md)
- **修法**：
  - `get_adjacency_source_locations`: 北伐时改为所有友方（all friendly）
  - `ConvertOperator._get_filtered_locations`: 改用 `get_adjacency_source_locations`
  - 规则书三处更新：相邻地点、北伐标记、转化

---

## 四、额外修复（对局测试中附带发现）

| 修复 | 文件 | 说明 |
|------|------|------|
| 征募冗余输出 | [engine/engine/game_logger.py](engine/engine/game_logger.py) | 征募描述已含"换1军力"，跳过 `military:1` 结果行 |
| 暗置阶段 AI 手牌泄露 | [engine/play_game.py](engine/play_game.py) | 非人类玩家的初设手牌只显示数量不显示内容 |
| 摸牌隐私 | [engine/ai/human_player.py](engine/ai/human_player.py) | AI 玩家摸牌不显示牌名，仅显示"XX 摸牌" |
| `card_effect_summary` 去重 | [engine/ai/human_player.py](engine/ai/human_player.py) | `_brief_effect` 委托给共享的 `viewport/utils.py` |
| 视窗查询 CLI | [engine/ai/human_player.py](engine/ai/human_player.py) | 行动选择界面按 `v` 进入视窗查询 |
| 朝堂显示 per-faction | [engine/engine/game.py](engine/engine/game.py) | 按 faction 而非 per-player 显示朝堂/牌库 |
| 皇帝/司马家状态显示 | [engine/engine/game.py](engine/engine/game.py) | 回合公开信息中显示皇帝年龄、任务、司马家状态 |
| 区控奖励变化显示 | [engine/engine/game.py](engine/engine/game.py) | 回合开始时打印区控奖励带来的资源变化 |
| 东晋 Round 1 顺位 | [engine/engine/phases.py](engine/engine/phases.py) | Round 1 不再特殊处理顺位；初设时按先动値分配 order_seq |
| `CardDef.has_marker()` | [engine/models/card.py](engine/models/card.py) | 新增标记检查方法 |
| `ArchiveCardOperator` 过滤 | [engine/cards/effect_operators.py](engine/cards/effect_operators.py) | 排除 `cannot_be_archived` 限制的牌 |
| `DraftOperator` 过滤 | [engine/cards/effect_operators.py](engine/cards/effect_operators.py) | 排除 `cannot_be_drafted` 限制的牌 |
| 贡献度 trigger 去重 | [engine/engine/actions/special_actions.py](engine/engine/actions/special_actions.py), [engine/models/game_state.py](engine/models/game_state.py) | trigger 改由 `add_contribution()` 内部统一触发 |
| LoggingAgentWrapper `reason` | [engine/play_game.py](engine/play_game.py) | 缺 `reason` 参数导致苻坚激活崩溃 |

---

## 五、修改文件清单

| 文件 | 改动 | 风险 |
|------|------|------|
| `engine/config/version.py` | `_load_cards` 中：`usurp_with_tie` 移到 `AbilityBlock.modifier`；`_dict_to_step` 增加 `filter` → `condition` 映射 | 中 |
| `versions/v1.0/cards/cards_compiled.json` | 刁协 play_condition; 新亭对谈 filter→condition; 谢安去重 raise_contribution | 低 |
| `engine/cards/effect_parser.py` | play_requirement → play_condition 自动转换 | 低 |
| `engine/cards/effect_operators.py` | ChooseOperator 参数传递修复；ConvertOperator 相邻来源；Draft/Archive 限制过滤；选择标签增强 | 中 |
| `engine/models/game_state.py` | get_adjacency_source_locations 北伐改造；add_contribution 统一触发 trigger | 中 |
| `engine/models/card.py` | CardDef.has_marker() 新增 | 低 |
| `engine/engine/phases.py` | culture_tracks 初始化；Jin 顺位逻辑；_allocate_initial_order_seq；run_settlement_phase 返回事件 | 中 |
| `engine/engine/game.py` | 皇帝输出；archive_this 检查；区控奖励显示；视窗隐私回调；choose_discard reason | 中 |
| `engine/engine/actions/card_actions.py` | _check_archive_this 辅助函数 | 中 |
| `engine/engine/actions/special_actions.py` | spread_culture 填充 rs.culture_slots；ActivateEffect archive_this | 低 |
| `engine/engine/game_logger.py` | 征募跳过 military 结果 | 低 |
| `engine/ai/human_player.py` | reason 参数; 去掉确认; _brief_effect 委托; 视窗查询CLI; 摸牌隐私; 暗置阶段buffer修正 | 中 |
| `engine/ai/interface.py` | choose_discards reason 参数 | 低 |
| `engine/ai/dummy_ai.py` | choose_discards reason 参数 | 低 |
| `engine/play_game.py` | LoggingAgentWrapper reason 参数; AI手牌隐私; 暗置buffer回调修正 | 低 |
| `engine/viewport/live.py` | culture_tracks 属性名修正 | 低 |
| `engine/viewport/snapshot.py` | culture_tracks 属性名修正 | 低 |
| `engine/viewport/utils.py` | setdefault 死代码移除；culture 从 rs.culture_slots 读取 | 低 |
| `engine/viewport/query.py` | _summary 重写：全部玩家每人一行 | 低 |
| `engine/engine/viewport_adapter.py` | culture_tracks 属性名修正 | 低 |
| `engine/tests/test_cards/test_effect_resolver.py` | test_fires_trigger 接线 state.effect_resolver | 低 |
| `rulebook.md` | 相邻地点、北伐标记、转化相邻判定三处更新 | 低 |

---

## 六、验收标准

- [x] `Version.load('v1.0')` 不报错，返回完整 Version 对象
- [x] `version.card_library.all_cards` 数量 > 0
- [x] 每张卡 `parsed_effect` 的 AST 重建无异常
- [x] `pytest engine/tests/ -v` → **469 passed, 0 failed**
- [x] 新增：使用 `Version.load` 的完整对局测试通过
- [x] 新增：加载后遍历所有卡牌检查 `parsed_effect` 不为空或不崩的冒烟测试
- [x] 13 个对局测试 bug 全部修复
- [x] 规则书北伐规则更新

---

## 七、验收操作（依次执行）

全部通过即为 Phase 1 完成。

### 步骤 1：Version.load 加载不崩

```bash
cd d:\life\board_game\project_six_dynasty
python -c "
import sys; sys.path.insert(0, 'engine')
from config.version import Version
v = Version.load('v1.0')
print(f'版本: {v.name}')
print(f'卡牌总数: {len(v.card_library.all_cards)}')
print(f'地图邻接: {len(v.map_adjacencies)}')
print(f'特性开关: {[k for k,v2 in v.features.items() if v2]}')
"
```

**通过标准**：打印版本名、卡牌数 > 0、邻接数 > 0、特性开关列表。无任何报错。

### 步骤 2：全卡 AST 冒烟测试

```bash
python -c "
import sys; sys.path.insert(0, 'engine')
from config.version import Version
v = Version.load('v1.0')
failed = []
for cdef in v.card_library.all_cards:
    name = cdef.name
    pe = cdef.parsed_effect
    if pe is None:
        if cdef.card_type.value not in ('goal', 'emperor'):
            failed.append(f'{name}: parsed_effect is None')
        continue
    for i, block in enumerate(pe.blocks):
        for j, step in enumerate(block.steps):
            if not step.effect_type:
                failed.append(f'{name}: block[{i}] step[{j}] empty effect_type')
if failed:
    print(f'失败 {len(failed)} 张:')
    for f in failed: print(f'  - {f}')
else:
    print(f'全部 {len(v.card_library.all_cards)} 张卡 AST 校验通过')
"
```

**通过标准**：`全部 X 张卡 AST 校验通过`。

### 步骤 3：全量单元测试

```bash
cd d:\life\board_game\project_six_dynasty
python -m pytest engine/tests/ -v --tb=short
```

**通过标准**：`469 passed, 0 failed`（或更多）。

### 步骤 4：Version.load 完整对局

```bash
python -c "
import sys; sys.path.insert(0, 'engine')
from config.version import Version
from ai.dummy_ai import DummyAI
from engine.game import GameEngine

v = Version.load('v1.0')
agents = [
    DummyAI(player_id='north', seed=1),
    DummyAI(player_id='jin_1', seed=2),
    DummyAI(player_id='jin_2', seed=3),
    DummyAI(player_id='jin_3', seed=4),
]
engine = GameEngine(agents=agents, version=v, seed=42)
state = engine.run()
print(f'终局: round={state.round}, phase={state.phase.value}')
for p in state.get_all_players():
    print(f'  {p.player_id}: {p.vp} VP')
print(f'胜者: {engine.get_winner()}')
print('PASS: 完整对局跑通')
"
```

**通过标准**：打印 4 人 VP、胜者、`PASS: 完整对局跑通`。

### 步骤 5：10 局稳定性

```bash
python -c "
import sys; sys.path.insert(0, 'engine')
from config.version import Version
from ai.dummy_ai import DummyAI
from engine.game import GameEngine

v = Version.load('v1.0')
for i in range(10):
    seed = i * 100 + 1
    agents = [
        DummyAI(player_id='north', seed=seed),
        DummyAI(player_id='jin_1', seed=seed+1),
        DummyAI(player_id='jin_2', seed=seed+2),
        DummyAI(player_id='jin_3', seed=seed+3),
    ]
    engine = GameEngine(agents=agents, version=v, seed=seed)
    state = engine.run()
    assert state.phase.value == 'game_over', f'seed={seed} 未正常结束'
    print(f'  seed={seed:3d}: round={state.round}, winner={engine.get_winner()}')
print('PASS: 10局全部通过')
"
```

**通过标准**：10 局全部打印 round 和胜者，最后 `PASS: 10局全部通过`。

---

## 八、完成后状态

Phase 1 完成后：
- 新旧两条加载路径统一，都指向 `cards_compiled.json`
- v1.0 卡牌数据正式"激活"可用
- 13 个对局测试 bug 全部修复
- 469 个测试全部通过
- 规则书北伐规则已更新
- 可以进入 Phase 2：引擎完整性补完 & AI 批量测试

---

> 创建日期：2026-07-06
> 最后更新：2026-07-19（13 个对局测试 bug 全部修复）
