# HexMachina 代码分析

> 源码来源：[nbelle1.github.io/agents-of-change/](https://nbelle1.github.io/agents-of-change/)
> 分析日期：2026-08-07

---

## 一、项目结构总览

```
strategy-game-agents-main/
├── main.py                          # 入口：选择 Evolver 类型并启动
├── testing.py                       # 评估脚本：对局 + 结果解析
├── setup.py                         # 包安装
├── langgraph.json                   # LangGraph 配置
├── requirements.txt
│
├── agents/                          # 核心：多 Agent 系统
│   ├── base_llm.py                  # LLM 后端封装（OpenAI/Mistral/Anthropic/DeepSeek）
│   ├── foo_player.py                # 当前正在演化的策略代码（被写入的目标文件）
│   ├── langgraph_graph_viz.py       # 可视化工具
│   │
│   ├── agentEvolver/                # v1：最早的 Agent Evolver（无 discovery 阶段）
│   │   ├── creator_agent.py
│   │   ├── __TEMPLATE__foo_player.py
│   │   ├── foo_player.py
│   │   └── saved_agents/            # 存档的最佳策略（best_claude/best_gpt/best_mistral）
│   │
│   ├── agentEvolver_v2/             # v2：HexMachina 本体（有 discovery + improvement 双阶段）
│   │   ├── creator_agent.py         # LangGraph 状态图 + 所有 Agent 节点 + 工具函数
│   │   ├── prompts.py               # 全部 System Prompt（~700 行，极其详细）
│   │   ├── __TEMPLATE__foo_player.py # 策略初始模板（仅返回第一个合法动作）
│   │   ├── __TEMPLATE__adapters.py   # 适配器初始模板（仅 3 个基础 import）
│   │   ├── adapters.py              # Discovery 阶段诱导出的稳定适配器
│   │   ├── run_adapter_test.py      # 适配器运行时验证
│   │   ├── foo_player.py            # 当前策略代码
│   │   └── runs/                    # 历次运行记录（claude/gpt + 策略快照）
│   │
│   ├── promptEvolver/               # Prompt Evolver：演化 prompt 而非代码
│   ├── llmAgentEvolver/             # LLM Agent Evolver：另一种变体
│   ├── structuredAgent/             # 人工编写 prompt 的 baseline Agent
│   └── baseAgent/                   # 最简陋的 baseline
│
├── catanatron/                      # 游戏引擎（开源 Catanatron）
│   ├── catanatron_core/             # 核心游戏逻辑
│   ├── catanatron_experimental/     # AlphaBeta 等高级 AI 玩家
│   ├── catanatron_gym/              # Gym 接口
│   └── catanatron_server/           # Web UI
│
├── supplementary/                   # 补充材料（初始 adapters 快照等）
└── plotting/                        # 可视化脚本
```

## 二、核心架构：agentEvolver_v2（HexMachina）

### 2.1 整体流程

```
main.py: EVOLVER_TYPE = "agentEvolver2"
    │
    ▼
creator_agent.run_react_graph()
    │
    ├─ [可选] Discovery Phase: create_discovery_graph()
    │   │
    │   ┌──────────────────────────────────────────────────────────┐
    │   │  validate_adapter → meta → agent → meta → ...           │
    │   │       ↑                              │                   │
    │   │       └── coder 写完后回到验证 ──────┘                   │
    │   │                                                        │
    │   │  agent ∈ {analyzer, strategizer, researcher, coder}    │
    │   │  输出: adapters.py（稳定 API 适配层）                    │
    │   └──────────────────────────────────────────────────────────┘
    │
    └─ Improvement Phase: create_improvement_graph()
        │
        ┌──────────────────────────────────────────────────────────┐
        │  init → run_player → analyzer → meta → ...             │
        │              ↑                         │                │
        │              └── coder → run_player ────┘               │
        │                                                        │
        │  meta 做路由决策: analyzer / strategizer / researcher / coder / END │
        │  循环 20 次演化                                           │
        └──────────────────────────────────────────────────────────┘
```

### 2.2 LangGraph 状态图设计

HexMachina 使用 **LangGraph** 实现确定性的多 Agent 编排，不是让 Agent 自由对话，而是通过状态图控制流程：

```python
class CreatorGraphState(TypedDict):
    meta_messages: list          # META 节点的完整消息历史
    analyzer_messages: list      # Analyzer 的消息历史
    strategizer_messages: list   # Strategizer 的消息历史
    researcher_messages: list    # Researcher 的消息历史
    coder_messages: list         # Coder 的消息历史
    recent_meta_message: HumanMessage   # 最新的 META 指令
    recent_helper_response: HumanMessage # 最新 Agent 响应
    game_results: HumanMessage   # 最新对局结果
    tool_calling_messages: list  # 工具调用消息
```

**Improvement Phase 图**：

```
START → init → run_player → analyzer → meta ─┬→ analyzer
                                              ├→ strategizer
                                              ├→ researcher
                                              ├→ coder → run_player (循环)
                                              └→ END (达到 20 轮)
```

**Discovery Phase 图**：

```
START → init → validate_adapter → meta ─┬→ analyzer → meta
                                         ├→ strategizer → meta
                                         ├→ researcher → meta
                                         ├→ coder → validate_adapter (循环)
                                         └→ END
```

### 2.3 META 节点：调度中心

META 是核心路由节点，扮演"首席科学家"角色：

```python
# META System Prompt 核心逻辑:
"""
1) Analyze: 每局后必须先调用 ANALYZER，诊断根因
2) Strategize: Analyzer 发现策略缺陷后，调用 STRATEGIZER 提出方案
3) Code: Strategizer 给出可执行方案后，调用 CODER 实现
4) Repeat: 循环直到 20 轮演化
"""

# _meta_choice(): 解析 META 输出中的 "CHOSEN AGENT: XXX" 决定路由
# 格式要求: "CHOSEN AGENT: ANALYZER" → 路由到 analyzer 节点
```

### 2.4 每个 Agent 的实现模式

所有 Agent 节点遵循相同模式：

1. **选择 System Prompt**：根据 `CURRENT_PHASE`（discovery/improvement）使用不同 prompt
2. **注入上下文**：将性能历史、对局结果、当前代码、adapters 内容等作为 HumanMessage 注入
3. **调用内部 Tool-Calling 子图**：每个 Agent 有自己的内部 _tool_calling_state_graph()，支持最多 `MAX_MESSAGES_TOOL_CALLING`(4) 轮工具调用
4. **记录日志**：输入/输出分别记录到独立日志文件

```python
# 以 analyzer_node 为例:
def _analyzer_node(self, state):
    # 1. 选择 system prompt
    sys_msg = SystemMessage(content=ANALYZER_SYSTEM_PROMPT.format(...))
    
    # 2. 注入上下文
    msgs = [performance_msg, game_output_msg, game_results_msg, 
            current_foo_msg, adapter_msg, state["recent_meta_message"]]
    
    # 3. 内部 tool-calling 子图（analyzer 可用: read_local_file, think_tool, read_adapter）
    output = self._tool_calling_state_graph(self.analyzer_llm, sys_msg, msgs, tools)
    
    # 4. 更新全局状态
    return {"recent_helper_response": response, "meta_messages": meta_messages}
```

### 2.5 _run_player_node：对局执行

这是整个循环的"真实世界反馈"节点：

```python
def _run_player_node(self, state):
    # 1. 调用 catanatron-play CLI 执行对局
    game_results = self._run_testfoo(short_game=False)
    #   FOO_RUN_COMMAND = "catanatron-play --players=AB,AE2 --num=30 ..."
    #   AB = AlphaBeta, AE2 = 我们的 FooPlayer
    
    # 2. 解析 JSON 结果，提取 Win/Avg VP/Avg Turns
    # 3. 更新 performance_history.json
    # 4. 存档当前 foo_player.py 快照
    # 5. 输出截断到 20KB（避免上下文溢出）
```

**关键设计**：
- 每次演化打 30 场（`--num=30`），提供统计显著性
- 结果存入 `performance_history.json`，支持回溯对比
- 自动解析 Catanatron 的 JSON 输出格式
- 超时设置 14400 秒（4 小时），防止卡死

---

## 三、Discovery Phase：API 适配层的自动诱导

### 3.1 起点：最小化的模板

```python
# __TEMPLATE__adapters.py（初始状态，仅 3 行 import）
from catanatron.game import Game
from catanatron.models.player import Player, Color
# 其他都是空的——LLM 需要从零开始探索
```

### 3.2 终点：完整适配器

```python
# adapters.py（Discovery 完成后，~50 行）
# 包含:
# - 核心类型: Game, Player, Color, Action, ActionType
# - 搜索算法: copy_game, execute_deterministic, execute_spectrum, expand_spectrum
# - 剪枝: list_prunned_actions, prune_robber_actions
# - 价值函数: base_fn, contender_fn, value_production, get_value_fn
# - 对手引用: AlphaBetaPlayer, ValueFunctionPlayer
# 每个函数都有文档注释 + 类型签名
```

### 3.3 Discovery 的角色分工

| 角色 | Prompt 定位 | 工具 | 输入 |
|------|-----------|------|------|
| **META** | Lead API Architect | think_tool | 验证结果 |
| **Researcher** | Code Extractor | read_local_file, think_tool | Catanatron 文件列表 |
| **Strategizer** | API Designer | read_adapter, think_tool | Researcher 的签名报告 |
| **Coder** | Adapter Implementer | write_adapter, replace_code_in_adapter | Strategizer 的设计提案 |
| **Analyzer** | Code Reviewer | read_adapter, think_tool | 编译/运行时错误 |

工作流示例（论文中的真实流程）：

```
META: "分析 minimax.py 的依赖" → Researcher
Researcher: "提取到: from catanatron_experimental... import execute_deterministic, execute_spectrum, expand_spectrum..."
META: "为 execute_deterministic 设计 wrapper" → Strategizer
Strategizer: "def execute_deterministic(game, action) -> List[Tuple[Game, float]]: ..."
META: "实现这个 wrapper" → Coder
Coder: [调用 replace_code_in_adapter] → "成功添加"
→ 回到 validate_adapter: 编译检查 + 运行时导入检查
```

### 3.4 验证机制

```python
# _validate_adapter_node 的两阶段检查:
# Stage 1: 语法检查
python -m py_compile adapters.py

# Stage 2: 运行时检查（run_adapter_test.py）
# 实际上 import adapters 并调用每个函数，确保无 ImportError/AttributeError
```

---

## 四、Improvement Phase：策略代码演化

### 4.1 起点：最简单的策略

```python
# __TEMPLATE__foo_player.py
class FooPlayer(Player):
    def decide(self, game, playable_actions):
        print("Choosing First Action on Default")
        return playable_actions[0]  # ← 永远选第一个合法动作
```

### 4.2 Prompt 中的关键约束

**META（首席科学家）的核心指令**：
- 强制使用算法策略（搜索/前瞻），**禁止**简单规则式启发
- 强制使用 `adapters.py` 暴露的函数
- 如果连续 3 轮无提升 → 告诉 Strategizer 换整体策略

**Coder 的核心约束**：
- **硬约束**：`from .adapters import`，禁止 `from catanatron` 或 `import catanatron`
- 这个约束确保了 adapters.py 是唯一的 API 接口，隔离底层变化
- 文件上限 64KB，防止代码膨胀

**Strategizer 的失败处理**：
```python
# 前 5 轮如果一直编译失败(Scores=0)，建议降到最简单：
for action in playable_actions:
    if action.action_type == ActionType.BUILD_SETTLEMENT:
        return action

# 如果连续 3 轮成功运行但无提升 → 建议换整体策略
# 如果历史中有更好版本 → 建议回滚到那个版本
```

### 4.3 Analyzer 的诊断模板

```python
DEFAULT_ANALYZE_MSG = """
如果游戏失败（无 JSON 或 score==0）:
  - 错误摘要（精确行号、异常类型）
  - 可能原因（1-2 条假设）
  - 快速修复方向

如果游戏成功（有 JSON）:
  1) 表现摘要（Win/Loss/VP diff/关键计数）
  2) 判定分级（Good/Borderline/Poor）
  3) 如 Borderline/Poor → 2-4 个具体问题（含行号引用）
     - 缺少 1-ply value lookahead？
     - 无 Chance 处理（骰子/发展卡/劫匪）？
     - placement helpers 是 stub？
  4) 下一步建议（如 "Send to Coder to add 1-ply value lookahead"）
"""
```

### 4.4 演化日志系统

每次演化生成完整的审计轨迹：
```
runs/creator_20250925_041340/
├── log/
│   ├── debug_log.txt           # 全局调试日志
│   ├── llm_log.txt             # LLM 输出摘要
│   ├── llm_log_full.txt        # LLM 完整输出
│   ├── ANALYZER/               # 按 Agent 分目录的详细日志
│   │   └── improvement_e1_20250925_041340.txt
│   ├── STRATEGIZER/
│   ├── RESEARCHER/
│   ├── CODER/
│   └── META/
├── game_20250925_041340_fg/    # 每轮对局的完整输出
│   ├── foo_player.py           # 该轮策略代码快照
│   ├── game_output.txt         # CLI 原始输出
│   └── <run_id>.json           # 结构化对局结果
├── adapters/                   # 每轮 adapters 快照 + 验证日志
├── performance_history.json    # 累积的性能记录
└── config.txt                  # 完整配置记录
```

---

## 五、四种 Evolver 的对比

代码库中包含 4 种演化器，代表了论文中的渐进架构：

| Evolver | 演化对象 | 来源 | 特点 |
|---------|---------|------|------|
| **agentEvolver** | foo_player.py（无 adapters） | v1 早期版本 | 无 Discovery 阶段，直接从原始 API 演化 |
| **agentEvolver_v2** | adapters.py + foo_player.py | **HexMachina 本体** | Discovery + Improvement 双阶段，论文最终方案 |
| **promptEvolver** | Prompt 文本 | StructuredAgent 的 prompt | 演化 prompt 而非代码 |
| **llmAgentEvolver** | 混合 | 另一个变体 | LLM 写 prompt + 代码 |

**agentEvolver (v1) vs agentEvolver_v2 (HexMachina) 的关键区别**：

```
v1 (agentEvolver):
  无 adapters → foo_player.py 直接 import catanatron
  → LLM 需要同时理解游戏引擎 + 写策略
  → 收敛到浅层启发式（论文中的 No-Discovery baseline）

v2 (agentEvolver_v2):
  Discovery: adapters.py 先稳定 API 接口
  Improvement: foo_player.py 只用 adapters 的封装
  → LLM 聚焦于策略设计
  → 收敛到深度策略（54.1% 胜率）
```

---

## 六、工具系统

### 6.1 通用工具

| 工具 | 功能 | 使用 Agent |
|------|------|-----------|
| `think_tool(reflection)` | 策略反思（来自 LangChain deep research agent） | 全部 |
| `read_local_file(rel_path)` | 读取本地文件（安全沙箱，限制路径+大小） | Analyzer, Researcher, Strategizer |
| `read_adapter()` | 读取当前 adapters.py | 全部 |
| `web_search_tool_call(query)` | Tavily 搜索（最多 3 条结果） | Strategizer, Researcher |

### 6.2 Coder 专用工具

| 工具 | 功能 |
|------|------|
| `write_foo(new_text)` | 完整覆写 foo_player.py（≤64KB） |
| `replace_code_in_foo(search, replace)` | 精准替换代码块 |
| `write_adapter(new_text)` | 完整覆写 adapters.py |
| `replace_code_in_adapter(search, replace)` | 精准替换 adapters 代码块 |

### 6.3 性能分析工具

| 工具 | 功能 |
|------|------|
| `read_full_performance_history()` | 读取 performance_history.json |
| `read_game_output_file(num)` | 读取指定演化轮次的 CLI 输出 |
| `read_game_results_file(num)` | 读取指定轮次的 JSON 结果 |
| `read_older_foo_file(num)` | 读取历史版本的 foo_player.py |
| `list_catanatron_files()` | 列出 catanatron 目录所有 .py/.txt/.md 文件 |

---

## 七、LLM 后端架构

### 7.1 两种 LLM 体系

代码中有两套 LLM 调用方式：

| 体系 | 文件 | 用途 | 特征 |
|------|------|------|------|
| **base_llm.py** | 简单 wrapper | 测试/简单调用 | 单一 `query(prompt)` 接口 |
| **creator_agent.py (LangChain)** | LangChain ChatModel | 正式 Agent 系统 | 支持 tool calling、结构化输出 |

### 7.2 模型分工（creator_agent.py 配置）

```python
# 代码中的实际默认配置:
CODER_LLM_BACKEND = "claude"          # Coder: Claude 3.7（代码生成）
ANALYZER_LLM_BACKEND = "mistral"      # Analyzer: Mistral Large（诊断）
RESEARCHER_LLM_BACKEND = "mistral"    # Researcher: Mistral Large（探索）
STRATEGIZER_LLM_BACKEND = "mistral"   # Strategizer: Mistral Large（策略设计）
META_LLM_BACKEND = "claude"           # META: Claude 3.7（全局调度）
```

### 7.3 支持的 LLM 后端（base_llm.py）

- OpenAI: `gpt-4`, `gpt-3.5-turbo`, `gpt-4-turbo-preview`
- Azure OpenAI: `gpt-4o`, `gpt-4o-mini`, `o1`, `o1-mini`
- Mistral: `mistral-large-latest`, `mistral-small-latest`, `mistral-medium`
- Anthropic: `claude-3.7`（通过 AWS Bedrock）
- DeepSeek: `deepseek-chat`, `deepseek-reasoner`
- OpenRouter: `deepseek/deepseek-r1:free` 等

---

## 八、对比论文附录与代码

### 8.1 论文附录 A.1 的策略代码

论文附录中的 600 行 FooPlayer 在代码库中对应 **agentEvolver 的 saved_agents/best_gpt/** 目录下的存档文件（多次演化快照）。核心特征全部匹配：
- `MAX_SIMULATIONS = 24`、`ROLLOUT_DEPTH = 2`
- `MULTS` 阶段乘数矩阵（EARLY/MID/LATE）
- `MUST_INCLUDE_TOKENS` 集合
- 劫匪评估、骑士评估、发展卡 EV 估算
- `prefilter_actions` + `cheap_pre_score` + `rollout_value` + `decide`

### 8.2 论文中的 prompt 设计 vs 代码中的 prompt

论文未公开完整 prompt，但代码中 `prompts.py` 的 700 行 prompt 是完整的实现细节，包含：
- META 的工作流指导（Analyze → Strategize → Code → Repeat）
- Analyzer 的诊断模板（区分编译失败 vs 运行失败的分析方式）
- Strategizer 的失败处理策略（回滚、换策略、降低复杂度）
- Coder 的硬约束（必须 `from .adapters import`，禁止 `import catanatron`）
- Discovery 阶段的 4 个专用 prompt（Researcher 提取签名、Strategizer 设计 wrapper 等）

### 8.3 论文未提及的实现细节

| 细节 | 说明 |
|------|------|
| **文件大小上限 64KB** | `FOO_MAX_BYTES = 64000`，防止 LLM 生成过大的策略文件 |
| **上下文管理** | `MAX_MESSAGES_TOOL_CALLING = 4`（每 Agent 最多 4 轮工具调用），`MAX_MESSAGES_IN_AGENT = 20`（最多保留 20 条历史消息），`MAX_META_MESSAGES_GIVEN_TO_CODER = 6` |
| **对局超时 4 小时** | `timeout=14400`，防止策略卡死 |
| **CLI 输出截断 20KB** | 防止对局日志撑爆 LLM 上下文 |
| **结果 JSON 轮询** | 最多等 3 秒（30×0.1s）找到 catanatron 写入的结果文件 |
| **Epsilon-Greedy** | 最佳策略中的 4% 随机性避免可预测 |
| **performance_history.json** | 结构化性能记录，支持历史对比和回滚 |

---

## 九、对六朝项目的实用参考

### 9.1 可直接复用的模式

1. **两阶段分离**：先让 LLM 探索引擎生成 `adapters.py`，再演化策略 —— 降低了 LLM 的认知负载
2. **LangGraph 编排**：确定性的状态图比自由对话更适合策略演化（可控、可复现、可审计）
3. **专门的诊断 Agent（Analyzer）**：论文消融实验证明 ANALYZER 是必需的（移除后胜率从 49.7% → 0%）
4. **硬约束**：`from .adapters import` 禁止直接 `import catanatron` —— 强制接口隔离
5. **性能历史追踪**：`performance_history.json` + 每轮快照 → 支持策略回滚

### 9.2 可以跳过的部分

1. **Strategizer + Researcher**：论文消融实验证明砍掉反而提升（49.7% → 54.1%）
2. **Web Search 工具**：对六朝特定引擎非必要
3. **多模型混合**：可以先用同一模型跑通，再优化成本
4. **promptEvolver / llmAgentEvolver**：论文中的中间架构，不是最优方案

### 9.3 最小可行配置

```
仅需 3 个 Agent:
  Orchestrator (META)  → 路由 + 全局规划
  Analyst               → 对局诊断（必需！）
  Coder                 → 写策略代码

工具:
  think_tool            → 策略反思
  read_file / write_file / replace_code → 代码操作
  run_game              → 执行对局

流程:
  init → run_game → analyst → meta → coder → run_game → ... (20轮)
```
