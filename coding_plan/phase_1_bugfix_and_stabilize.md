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

## 二、待修复问题清单

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

## 三、修改文件清单

| 文件 | 改动 | 风险 |
|------|------|------|
| `engine/config/version.py` | `_load_cards` 中：`usurp_with_tie` 移到 `AbilityBlock.modifier`；`_dict_to_step` 增加 `filter` → `condition` 映射 | 中 |
| `versions/v1.0/cards/cards_compiled.json` | "新亭对谈"：`"filter"` → `"condition"` 结构 | 低 |
| `engine/tests/test_game/test_game_loop.py` | 新增 `test_game_with_version_loader` 测试 | 低 |
| `engine/cards/effect_ast.py` | 如需要，`EffectStep` 增加 `filter` 字段或做兼容 | 低 |

---

## 四、验收标准

- [ ] `Version.load('v1.0')` 不报错，返回完整 Version 对象
- [ ] `version.card_library.all_cards` 数量 > 0
- [ ] 每张卡 `parsed_effect` 的 AST 重建无异常
- [ ] `pytest engine/tests/ -v` → **205 passed, 0 failed**
- [ ] 新增：使用 `Version.load` 的完整对局测试通过
- [ ] 新增：加载后遍历所有卡牌检查 `parsed_effect` 不为空或不崩的冒烟测试

---

## 五、验收操作（依次执行）

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

**通过标准**：`205 passed, 0 failed`（或更多）。

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

## 六、完成后状态

Phase 1 完成后：
- 新旧两条加载路径统一，都指向 `cards_compiled.json`
- v1.0 卡牌数据正式"激活"可用
- 可以进入 Phase 2：引擎完整性补完 & AI 批量测试

---

> 创建日期：2026-07-06
