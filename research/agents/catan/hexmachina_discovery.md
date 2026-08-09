# HexMachina Discovery 阶段深度分析

> 分析日期：2026-08-08
> 源码来源：HexMachina 代码库 `agents/agentEvolver_v2/`

---

## 一、Discovery 是什么

Discovery 是 HexMachina 的**自举（bootstrapping）阶段**，在 Improvement 之前运行。核心目标：

> **自动构建 `adapters.py`** —— 一个对 Catanatron 游戏引擎的高层稳定封装 API。

### 为什么需要 Discovery

Catanatron 是一个复杂的游戏引擎，有多个子包（`catanatron.game`、`catanatron.models`、`catanatron.state_functions`、`catanatron_experimental` 等）。直接让 LLM 在策略代码中调用这些 API 会出现：

- **导入路径错误**：LLM 记忆中的 API 路径可能与实际不符
- **函数签名偏差**：参数名/类型/返回值与 LLM 理解的不同
- **运行时崩溃**：幻觉出的 API 导致策略代码直接报错

Discovery 的思路是：**先让 LLM Agent 读源码 → 提取真实 API → 封装成薄 wrapper → 验证可用**，然后再让 Improvement 阶段的策略代码只调用这个稳定层。

---

## 二、与 Improvement 阶段的核心区别

| | Discovery | Improvement |
|---|---|---|
| **目标** | 构建 API 适配层 (`adapters.py`) | 进化游戏策略 (`foo_player.py`) |
| **验证方式** | 语法检查 + 运行时函数调用测试 | 实际跑 30 局游戏看胜率 |
| **核心循环** | CODER → VALIDATE → META | CODER → RUN_PLAYER → ANALYZER → META |
| **产物** | `adapters.py`（~170行） | `foo_player.py`（策略代码） |
| **META 角色** | Lead API Architect | Lead Scientist |
| **ANALYZER 角色** | Code Reviewer（诊断验证失败） | 赛后分析师（诊断对局失败原因） |

---

## 三、架构与图结构

### 3.1 触发条件

```python
# creator_agent.py 第 57-58 行
START_PHASE = "improvement"  # "discovery" | "improvement"
CURRENT_PHASE = START_PHASE
```

在 `run_react_graph()` 中（第 902-923 行）：

```python
def run_react_graph(self):
    if START_PHASE == "discovery":
        # 1. 先跑 Discovery
        self._run_phase("discovery")
        # 2. 自动转入 Improvement
        CreatorAgent.current_evolution = 0
        self._run_phase("improvement")
    elif START_PHASE == "improvement":
        # 只跑 Improvement（假设 adapters.py 已存在）
        self._run_phase("improvement")
```

### 3.2 Discovery 图结构

```
START → init → validate_adapter → meta
                                    |
        (conditional: meta_choice)   |
    ANALYZER ← STRATEGIZER ← RESEARCHER ← CODER
       |           |              |           |
       +-----------+--------------+-----------+→ meta
                                                  |
                                            CODER → validate_adapter (循环)
```

关键结构差异：

1. **`validate_adapter` 替代 `run_player`**：Discovery 不打游戏，只验证代码
2. **CODER → validate_adapter 边**：每次代码修改后立即验证
3. **所有 Agent 汇报回 META**：META 是唯一的调度中心

### 3.3 阶段初始化

```python
# 第 254-261 行：复制模板作为起点
if phase_name == "discovery":
    src = ADAPTER_TEMPLATE_FILE.resolve()   # __TEMPLATE__adapters.py
    dst = ADAPTER_TARGET_FILE.resolve()     # adapters.py
    shutil.copy2(src, dst)
```

### 3.4 阶段结束

```python
# 第 276-286 行：完成后保存产物
shutil.copy2(ADAPTER_TARGET_FILE, run_dir / "adapters_after_discovery.py")
```

---

## 四、五个 Agent 的 Discovery 角色

所有 Agent 节点根据 `CURRENT_PHASE` 选择不同的 System Prompt 和工具集。

### 4.1 META — Lead API Architect

- **Prompt**: `DISCOVERY_META_SYSTEM_PROMPT`
- **工具**: `[think_tool]`
- **职责**: 规划 API 封装架构，决定封装顺序，判断何时完成

META 的构建策略（来自 Prompt）：

1. **Discover**: 指导 RESEARCHER 分析 Catanatron 关键源文件，提取验证过的 import 语句
2. **Curate**: 区分基本类型（`Game`, `Player`, `Color`）和功能函数（`copy_game`, `playable_actions`）
3. **Build Wrappers**: 指导 STRATEGIZER 为每个函数设计薄封装
4. **Iterate**: 重复直到所有核心函数都被封装，输出 `CHOSEN AGENT: END`

期望的 `adapters.py` 最终分区：
- Core re-exports（直接导入 + 文档）
- Thin convenience wrappers（一行 wrapper 函数）
- Heuristic builders（`make_value_fn`、`production_features_sampler` 等）

### 4.2 RESEARCHER — Code Extractor

- **Prompt**: `DISCOVERY_RESEARCHER_SYSTEM_PROMPT`
- **工具**: `[read_local_file, web_search_tool_call, think_tool, read_adapter]`
- **职责**: 阅读 Catanatron 源文件，提取精确的 import 语句、函数签名、参数类型、返回类型

严格约束（来自 Prompt）：

> *"DO NOT report functions or classes that you did not see in an import statement."*
> *"DO NOT summarize."*
> *"Return EXACT, LITERAL import statements and full function signatures."*

### 4.3 STRATEGIZER — API Designer & Curator

- **Prompt**: `DISCOVERY_STRATEGIZER_SYSTEM_PROMPT`
- **工具**: `[read_local_file, web_search_tool_call, think_tool, read_adapter]`
- **职责**: 对每个 API 决定封装方案

两种封装模式：

**Option A — Re-export（用于简单类型/枚举）**:
```python
from catanatron.models.enums import ActionType  # Enum for all action types
```

**Option B — Thin Convenience Wrapper（用于每个函数）**:
```python
def playable_actions(game: Game) -> List[Action]:
    """Legal actions in the current state."""
    return list(game.state.playable_actions)
```

### 4.4 CODER — Adapter Implementer（Dumb Scribe）

- **Prompt**: `DISCOVERY_CODER_SYSTEM_PROMPT`
- **工具**: `[read_adapter, write_adapter, replace_code_in_adapter, think_tool]`
- **职责**: 精确写入 META/STRATEGIZER 给出的代码，**不自己写新逻辑**

这是 Discovery 最关键的约束：

> *"You do NOT write new logic. You only add the code you are given. Use `replace_code_in_adapter` to surgically insert imports and wrappers."*

CODER 被刻意设计为 "dumb scribe"：
- 所有设计决策在 STRATEGIZER 层面完成
- CODER 不能擅自添加逻辑（防止幻觉出的 API）
- 保证 adapters.py 的一致性

### 4.5 ANALYZER — Code Reviewer

- **Prompt**: `DISCOVERY_ANALYZER_SYSTEM_PROMPT`
- **工具**: `[read_local_file, think_tool, read_adapter]`
- **职责**: 诊断验证失败——分析语法错误或运行时崩溃的原因

在 Discovery 中 ANALYZER 收到的上下文是验证输出 + `adapters.py` 内容，而非游戏对局数据。

---

## 五、验证机制（VALIDATE 节点）

Discovery 的验证分两阶段，由 `_validate_adapter_node()` 实现（第 445-517 行）：

### Stage 1：语法检查

```bash
python -m py_compile adapters.py
```

### Stage 2：运行时测试

执行 `run_adapter_test.py`，该脚本：

1. 导入 `adapters` 模块
2. 构造一个 dummy Game 对象
3. 用 `inspect.signature` 分析 `adapters` 中每个函数的参数
4. 自动构造参数（根据类型注解和参数名推断）
5. 逐个调用函数，捕获异常

```python
# run_adapter_test.py 核心逻辑
functions = [
    obj for _, obj in inspect.getmembers(adapters)
    if inspect.isfunction(obj) and obj.__module__ == "adapters"
]

for func in functions:
    args = _build_args(func, game, game_state, sample_action)
    try:
        func(**args)
        print(f"  ✅ PASSED: {func.__name__}")
    except Exception as e:
        all_passed = False
        print(f"  ❌ FAILED: {func.__name__}: {e}")
```

参数构造策略（启发式）：
- 参数名为 `game` / 类型为 `Game` → 传入 dummy game
- 参数名为 `color` + 存在 `Color` 导出 → 传入 `Color.BLUE`
- 参数名为 `action_type` + 存在 `ActionType` 导出 → 传入 `ActionType.END_TURN`
- `validate` 参数 → `False`
- `seed` 参数 → `42`
- `*_fn` 参数 → `lambda *a, **k: None`

---

## 六、完整范例：从模板到最终产物

### 6.1 起点：模板文件（16 行）

```python
"""Unified adapter for Catanatron agents.
..."""
### KEEP THESE IMPORTS BELOW THIS LINE ###
from catanatron.game import Game
from catanatron.models.player import Player, Color
### KEEP THESE IMPORTS ABOVE THIS LINE ###
```

只有文档字符串 + 两个占位 import。没有函数，没有 wrapper。

### 6.2 第一轮迭代（典型流程）

```
Step 1: INIT -- 复制模板 → adapters.py

Step 2: VALIDATE
  语法检查 ✅
  运行时检查 → "No functions defined" → 无函数可测，exit(0) → 视为通过
  → 进入 META

Step 3: META（Lead API Architect）
  分析当前 adapters.py → 只有 2 个 import，远远不够
  决定：先发现 Catanatron 的核心类型和状态查询 API
  输出: CHOSEN AGENT: RESEARCHER

Step 4: RESEARCHER
  调用 read_local_file("catanatron/models/enums.py")
  调用 read_local_file("catanatron/state_functions.py")
  返回:
    From enums.py: Action, ActionType, RESOURCES, SETTLEMENT, CITY, ...
    From state_functions.py: get_player_buildings(state, color, type) -> Iterable[node_id]
                             get_dev_cards_in_hand(state, color, card) -> int
                             ...
  → 汇报给 META

Step 5: META
  审查 RESEARCHER 的发现 → 这些是核心 API，需要封装
  输出: CHOSEN AGENT: STRATEGIZER

Step 6: STRATEGIZER
  对类型/枚举 → Option A (re-export)
  对函数 → Option B (thin wrapper)
  输出: 完整的代码块，包含 import 语句和 wrapper 函数定义

Step 7: META
  审查 STRATEGIZER 的设计 → 批准
  输出: CHOSEN AGENT: CODER

Step 8: CODER
  调用 replace_code_in_adapter(
    old_str="### KEEP THESE IMPORTS ABOVE THIS LINE ###",
    new_str="""... 新增 imports + wrappers ..."""
  )
  → 验证 tool call 成功

Step 9: VALIDATE
  语法检查 ✅
  运行时检查:
    Testing current_color(game: Game) → ✅
    Testing playable_actions(game: Game) → ✅
    Testing get_player_buildings(game: Game, color: Color) → ✅
    ...
  → 全部通过 → 进入 META

Step 10: META
  第一批 API 封装完成。接下来：
  - 需要树搜索工具（tree_search_utils.py）
  - 需要价值函数（value.py）
  → 新一轮迭代...
```

### 6.3 最终产物（~170 行）

经过若干轮迭代后产出的 `adapters.py` 包含四个逻辑区块：

| 区块 | 行数 | 内容示例 |
|------|------|---------|
| **Core types & enums** | ~15行 | `Game`, `Player`, `Color`, `Action`, `ActionType`, `RESOURCES`, `SETTLEMENT`, `CITY` |
| **State helpers** | ~8行 | `get_player_buildings`, `get_dev_cards_in_hand`, `get_player_freqdeck`, `get_enemy_colors` |
| **Map/Features/Search** | ~25行 | `number_probability`, `build_production_features`, `DEFAULT_WEIGHTS`, `execute_spectrum`, `expand_spectrum`, `list_prunned_actions` |
| **Thin wrappers (20个函数)** | ~110行 | `current_color()`, `playable_actions()`, `copy_game()`, `execute()`, `chance_children()`, `pruned_actions()`, `make_value_fn()`, `p_roll()` 等 |

### 6.4 循环直到完成

META 判断 `adapters.py` 已覆盖所有需要的 API 表面后：

```
CHOSEN AGENT: END
```

Discovery 阶段结束 → 自动转入 Improvement 阶段。

---

## 七、论文中的讨论

### 7.1 No-Discovery 的策略退化（附录 A.2）

论文附录给出了没有 Discovery 时演化出的 FooPlayer，评估函数退化到几乎只看 VP：

```python
# No-Discovery 版本的 _evaluate_state
score = float(vp)                              # 唯一真正的信号
if settlements:  score += 0.01 * settlements   # 极小的 tie-breaker
if cities:       score += 0.02 * cities
if roads:        score += 0.005 * roads
# 没有：生产力 / 阶段感知 / 资源多样性 / 对手建模 / rollout
```

对比有 Discovery 的版本（~600 行），后者包含阶段乘数矩阵、生产潜力计算、劫匪优化、对手响应模拟、浅层 rollout。

**退化原因**：没有 stable adapters → LLM 写的复杂代码因 API 调用错误而崩溃 → 只有最保守的代码能通过验证 → 策略退化到浅层启发式。

### 7.2 代码量对比

| | agentEvolver v1（无 Discovery） | agentEvolver_v2（有 Discovery） |
|---|---|---|
| 策略代码量 | ~160 行 | ~1100 行 |
| 决策深度 | 0-ply（if-else 链） | 1-ply 前瞻 + 价值函数 |
| API 调用方式 | 直接访问 `game.state.player_state["P0_WOOD_IN_HAND"]` | 通过 adapters 封装函数 |
| 防御性代码 | 低（硬编码路径） | ~30% 是 try/except 和适配 |

### 7.3 消融实验（反直觉发现）

| 配置 | 胜率 | 胜利点 |
|------|------|--------|
| 全部 Agent | 49.7% | 8.0 |
| 无 Strategist + Researcher | **54.1%** | 8.2 |
| 无 Analyst | **0.0%** | 2.1 |

砍掉 Strategist 和 Researcher（Discovery 阶段的专属 Agent）后，**Improvement 阶段**的胜率反而提升。论文解释：额外的策略建议会稀释策略一致性，减少角色交接 → 更清晰的策略翻译。

**但这不等于 Discovery 没用**——这个消融的前提是 `adapters.py` 已存在。Discovery 产出的适配层仍然被使用。

### 7.4 论文缺失的评估

论文**没有**提供：
- No-Discovery 的独立胜率数据（只给了代码，没给胜率）
- "完整两阶段 pipeline" vs "纯 Improvement（手写 adapters）"的对比
- 不同质量 adapters 对后续策略影响的梯度

---

## 八、对六朝项目的启示

### 8.1 Discovery 的核心价值

Discovery 解决的本质问题是：**LLM 不能可靠地记住和调用大型代码库的 API**。通过让 LLM Agent 自己去读源码、提取 API、封装验证，产出一个稳定的适配层。

对于六朝项目：
- 如果你的游戏引擎 API 较简单（< 20 个函数），可能不需要 Discovery，手写 adapters 更可控
- 如果引擎复杂、API 面宽，Discovery 可以自动完成 API 诱导工作

### 8.2 设计原则

1. **CODER 应该是 dumb scribe**：限制 CODER 不写新逻辑，所有设计决策统一由 DESIGNER（STRATEGIZER）做
2. **验证必须自动化**：语法检查 + 运行时调用测试，每次代码改动后立即验证
3. **从少数关键 API 开始**：不需要一次性封装所有 API，分批次迭代
4. **META 需要明确终止条件**：知道什么时候 adapters 是"完整的"

### 8.3 可迁移的模式

```
Discovery 的通用模式：
  1. 提供 API 骨架模板（docstring + 占位 import）
  2. RESEARCHER Agent 读源文件 → 提取真实函数签名
  3. DESIGNER Agent 决定封装方式（re-export vs wrapper）
  4. CODER Agent 精确写入
  5. VALIDATOR 自动验证（语法 + 运行时）
  6. META Agent 协调全流程 + 判断终止
```

即使不采用完整的多 Agent 架构，"先让 LLM 读源码生成适配层"这个思路本身就可以减少后续策略代码中的 API 幻觉。

---

## 九、关键文件索引

| 文件 | 路径 | 说明 |
|------|------|------|
| 入口 | `creator_agent.py` | `run_react_graph()`, `_run_phase()`, `create_discovery_graph()` |
| 验证节点 | `creator_agent.py:445-517` | `_validate_adapter_node()` |
| 测试脚本 | `run_adapter_test.py` | 自动构造参数、逐个调用函数 |
| 模板 | `__TEMPLATE__adapters.py` | 16 行骨架 |
| 完成品 | `runs/good_sample/adapters.py` | 170 行完整适配器 |
| Discovery Prompts | `prompts.py:408-681` | 5 个 DISCOVERY_* system prompt |
| Discovery Graph | `creator_agent.py:851-893` | `create_discovery_graph()` |
| 配置常量 | `creator_agent.py:52-119` | `START_PHASE`, `ADAPTER_TARGET_FILENAME` 等 |
