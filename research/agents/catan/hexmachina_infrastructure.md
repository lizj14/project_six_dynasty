# HexMachina 基础设施：工具、Agent 调用、Function Calling

> 来源：`agents/agentEvolver_v2/creator_agent.py`
> 涉及三个问题：工具如何编写配置 / Agent 节点如何调用 LLM / 工具调用机制本质

---

## 一、工具的定义和配置

### 1.1 工具就是普通 Python 函数

每个工具是 `creator_agent.py` 中一个带 **type hints + docstring** 的普通函数。LangChain 自动把函数签名转成 OpenAI function-calling 格式的 JSON Schema。

**最简示例 — `think_tool`**（来自 LangChain open_deep_research）：

```python
def think_tool(reflection: str) -> str:
    """Tool for strategic reflection on research progress and decision-making.

    Use this tool after each search to analyze results and plan next steps systematically.
    This creates a deliberate pause in the research workflow for quality decision-making.

    Reflection should address:
    1. Analysis of current findings - What concrete information have I gathered?
    2. Gap assessment - What crucial information is still missing?
    3. Quality evaluation - Do I have sufficient evidence/examples for a good answer?
    4. Strategic decision - Should I continue searching or provide my answer?

    Args:
        reflection: Your detailed reflection on research progress, findings, gaps, and next steps

    Returns:
        Confirmation that reflection was recorded for decision-making
    """
    return f"Reflection recorded: {reflection}"
```

**有副作用 — `write_foo`**（写入磁盘）：

```python
def write_foo(new_text: str) -> str:
    """Overwrite Agent File with new_text (UTF-8)."""
    if len(new_text.encode()) > FOO_MAX_BYTES:       # 64KB 上限
        raise ValueError("Refusing to write >64 kB")
    FOO_TARGET_FILE.write_text(new_text, encoding="utf-8")
    return f"{FOO_TARGET_FILENAME} updated successfully"
```

**精确替换 — `replace_code_in_foo`**（防范幻觉写坏代码）：

```python
def replace_code_in_foo(search: str, replace: str) -> str:
    """Replace a block of code in the Agent File."""
    content = read_foo()
    new_content = content.replace(search, replace)
    if new_content == content:
        return "Search string not found in file. No changes made."  # 不匹配 → 直接拒绝
    write_foo(new_content)
    return f"Successfully replaced code in {FOO_TARGET_FILENAME}"
```

设计要点：用**精确字符串匹配**做替换。如果 LLM 给的 `search` 参数和文件中实际内容有任何差异（包括空白字符），操作直接失败并返回错误消息，LLM 收到错误后可以修正重试。

**带安全沙箱 — `read_local_file`**：

```python
def read_local_file(rel_path: str) -> str:
    """Return the text content of rel_path if it's inside BASE_DIR."""
    # 多层路径校验：
    # 1. 如果是 foo_player.py → 直接调 read_foo()
    # 2. catanatron/ 前缀 → 只允许 catanatron 子目录
    # 3. 相对 run_dir → 只允许性能历史中的文件
    # 4. 所有路径 resolve() 后强制校验是否在允许目录内
    # 5. 文件大小上限 64KB
    if not str(candidate).startswith(str(LOCAL_CATANATRON_BASE_DIR)):
        raise ValueError("Access denied or not a file")
```

**Web 搜索 — `web_search_tool_call`**：

```python
def web_search_tool_call(query: str) -> str:
    """Perform a web search using the Tavily API."""
    tavily_search = TavilySearchResults(max_results=3)
    search_docs = tavily_search.invoke(query)
    formatted_search_docs = "\n\n---\n\n".join(
        f'<Document href="{doc["url"]}"/>\n{doc["content"]}\n</Document>'
        for doc in search_docs
    )
    return formatted_search_docs
```

**adapter 专用 — `write_adapter` / `replace_code_in_adapter`**：

```python
def write_adapter(new_text: str) -> str:
    """Overwrite adapters.py with new_text (UTF-8)."""
    if len(new_text.encode()) > FOO_MAX_BYTES:
        raise ValueError("Refusing to write >64 kB")
    ADAPTER_TARGET_FILE.write_text(new_text, encoding="utf-8")
    return f"{ADAPTER_TARGET_FILENAME} updated successfully."

def replace_code_in_adapter(search: str, replace: str) -> str:
    """Replace a block of code in the adapters.py File."""
    content = read_adapter()
    new_content = content.replace(search, replace)
    if new_content == content:
        return "Search string not found in file. No changes made."
    write_adapter(new_content)
    return f"Successfully replaced code in {ADAPTER_TARGET_FILENAME}."
```

### 1.2 工具的绑定：`llm.bind_tools()`

```python
def _tool_calling_state_graph(self, llm, sys_msg, msgs, tools):
    llm_with_tools = llm.bind_tools(tools)
    # ↑ LangChain 把 Python 函数的 type hints + docstring
    #   转成标准的 OpenAI function-calling JSON Schema
```

`bind_tools()` 做了什么：
1. 遍历 Python 函数列表
2. 从函数签名提取参数名、类型、是否必填
3. 从 docstring 提取功能描述
4. 生成标准的 JSON Schema，注入到每次 LLM API 请求的 `tools` 字段中

### 1.3 工具的执行：LangGraph `ToolNode`

```python
builder.add_node("tools", ToolNode(tools))
```

`ToolNode` 是 LangGraph 内置的节点类型，自动完成：
1. 接收 LLM 返回的 `tool_calls`（结构化对象，不是文本）
2. 用函数名匹配到 Python 函数
3. 用 JSON 解析的参数调用函数
4. 把函数返回值包装成 `ToolMessage(role="tool", tool_call_id=...)`
5. 返回到 LLM 的上下文窗口

### 1.4 每个 Agent 的工具分配

不同 Agent 节点调用 `_tool_calling_state_graph()` 时传入不同的 `tools` 列表：

| Agent | 工具列表 | 规律 |
|-------|---------|------|
| **META** | `[think_tool]` | 只做调度决策，不操作文件 |
| **ANALYZER** | `[read_local_file, think_tool, read_adapter]` | 只读 |
| **STRATEGIZER** | `[read_local_file, read_game_results_file, read_older_foo_file, web_search_tool_call, think_tool, read_adapter]` | 读 + 搜索 + web |
| **RESEARCHER** | `[read_local_file, web_search_tool_call, think_tool, read_adapter]` | 读 + 搜索 |
| **CODER** (improvement) | `[write_foo, replace_code_in_foo, think_tool, read_adapter]` | 只写策略代码 |
| **CODER** (discovery) | `[read_adapter, write_adapter, replace_code_in_adapter, think_tool]` | 写 adapter |

**原则**：
- ANALYZER/STRATEGIZER/RESEARCHER 不能写代码
- CODER 不能读对局日志
- 只有 discovery 阶段的 CODER 能写 `adapters.py`
- 只有 META 能调 `think_tool`（其他 Agent 的 think_tool 是独立的）

### 1.5 工具调用的软限制

每个 Agent 的 System Prompt 末尾都有：

```
YOU ARE LIMITED TO {MAX_MESSAGES_TOOL_CALLING} TOOL CALLS
```

实际配置 `MAX_MESSAGES_TOOL_CALLING = 4`。这是**软限制**（靠 LLM 自己遵守），不是代码硬限制。ReAct 子图实际会跑到 LLM 不再输出 `tool_call` 为止（由 LangGraph 内置的 `tools_condition` 判断）。

---

## 二、Agent 节点：直接调用 LLM API，不调用子 Agent

### 2.1 两层 LangGraph 嵌套

整个系统是**两层图结构**，不是 Agent 自己决定调用其他 Agent：

**外层 — 主状态图**（Agent 间的路由，由图的边决定）：

```
START → init → run_player → ANALYZER → meta ─┬→ ANALYZER
                                              ├→ STRATEGIZER
                                              ├→ RESEARCHER
                                              ├→ CODER → run_player (循环)
                                              └→ END
```

**内层 — 每个 Agent 内部的 ReAct 子图**（LLM + 工具的循环）：

```
START → assistant (LLM with tools) ─┬→ END (LLM 输出最终文本)
                                    └→ tools (ToolNode 执行函数) → assistant
```

### 2.2 每个 Agent 节点就是 LLM API 调用

以 ANALYZER 为例：

```python
def _analyzer_node(self, state):
    # 1. 拼 System Prompt
    sys_msg = SystemMessage(content=ANALYZER_SYSTEM_PROMPT.format(...))

    # 2. 拼上下文消息（都是普通的 HumanMessage）
    msgs = [performance_msg, game_output_msg, game_results_msg,
            current_foo_msg, adapter_msg, state["recent_meta_message"]]

    # 3. 创建内层 ReAct 子图
    output = self._tool_calling_state_graph(
        self.analyzer_llm,   # ← ChatMistralAI 实例（就是 LLM API）
        sys_msg,             # ← System Prompt 文本
        msgs,                # ← 输入消息列表
        [read_local_file, think_tool, read_adapter]  # ← 工具
    )
    # ↑ 里面没有调用任何"子 Agent"，只有 LLM API 请求 + ToolNode 执行工具
```

### 2.3 不同的 Agent 节点使用不同的 LLM 实例

```python
def __init__(self):
    self.coder_llm       = self._create_llm("claude", "claude-sonnet-4-0")
    self.analyzer_llm    = self._create_llm("mistral", "mistral-large-latest")
    self.researcher_llm  = self._create_llm("mistral", "mistral-large-latest")
    self.strategizer_llm = self._create_llm("mistral", "mistral-large-latest")
    self.meta_llm        = self._create_llm("claude", "claude-sonnet-4-0")
```

`_create_llm` 就是标准的 LangChain ChatModel 工厂——创建的是 LLM API 客户端，不是子 Agent：

```python
def _create_llm(self, backend, model):
    if backend == "openai":
        return ChatOpenAI(model=model, max_retries=10)
    elif backend == "mistral":
        return ChatMistralAI(model=model, temperature=0, max_retries=10)
    elif backend == "claude":
        return ChatAnthropic(model="claude-sonnet-4-0", max_retries=10)
```

### 2.4 "Agent 间调度"的本质

**不是 Agent 自己决定调用谁**，而是：
1. META 输出固定格式文本：`CHOSEN AGENT: ANALYZER`
2. LangGraph 的 `_meta_choice()` 函数用正则解析这段文本
3. 返回字符串 `"ANALYZER"` 作为条件边的路由目标
4. LangGraph 框架把状态传到对应的 Agent 节点
5. 那个 Agent 节点调自己的 LLM API

```python
def _meta_choice(self, state):
    meta_message = state["meta_messages"][-1].content
    match = re.search(r"CHOSEN AGENT:\s*\**\s*([A-Za-z_]+)", meta_message)
    if match:
        agent_name = match.group(1)
        if agent_name == "END":
            return END
        if agent_name in AGENT_KEYS:
            return agent_name
    return CODER_NAME  # 默认 fallback
```

### 2.5 唯一的非 LLM 节点

`run_player` 是唯一不调 LLM 的节点——它执行 `subprocess.run("catanatron-play --players=AB,AE2 --num=30 ...")`，启动真实的 Catan 对局进程。

---

## 三、Function Calling vs 文本拼接

### 3.1 HexMachina 使用的是 Function Calling，不是文本拼接

以 CODER 调用 `write_foo` 为例，整个链路：

```
1. Python 函数定义:
   def write_foo(new_text: str) -> str:
       """Overwrite Agent File with new_text (UTF-8)."""
       ...

2. llm.bind_tools([write_foo])
   → LangChain 自动生成 JSON Schema (不在 prompt 文本里！):
   {
     "type": "function",
     "function": {
       "name": "write_foo",
       "description": "Overwrite Agent File with new_text (UTF-8).",
       "parameters": {
         "type": "object",
         "properties": {"new_text": {"type": "string"}},
         "required": ["new_text"]
       }
     }
   }

3. API 请求:
   POST /v1/chat/completions
   {
     "messages": [...],
     "tools": [上述 JSON Schema]     ← 独立的 tools 字段
   }

4. LLM 返回结构化 tool_calls (不是文本！):
   {
     "choices": [{
       "message": {
         "tool_calls": [{
           "id": "call_abc123",
           "type": "function",
           "function": {
             "name": "write_foo",
             "arguments": "{\"new_text\": \"class FooPlayer...\"}"
           }
         }]
       }
     }]
   }

5. ToolNode 解析 → 匹配函数名 → 执行 write_foo("class FooPlayer...")
   → 文件真的被写入磁盘
   → 返回 ToolMessage:
   {
     "role": "tool",
     "tool_call_id": "call_abc123",
     "content": "foo_player.py updated successfully"
   }

6. LLM 收到 ToolMessage → 知道函数已执行 → 继续推理或输出最终报告
```

### 3.2 两种方式的本质区别

| | 文本拼接（老派做法） | Function Calling（HexMachina） |
|---|---|---|
| 工具定义在哪 | System Prompt 文本里 | API 请求的 `tools` 字段 |
| LLM 如何"调用" | 生成文本 `{"action": "write_file", ...}` | 输出结构化 `tool_calls` 数组 |
| 如何解析 | 正则/JSON.parse 从文本中提取 | API 层直接返回结构化对象 |
| 函数执行 | 框架自己解析文本 → 执行 → 生成文本拼接回 prompt | LangGraph `ToolNode` 自动匹配函数名 → 执行 |
| 结果回传 | 拼成 `HumanMessage("执行结果: xxx")` | 标准的 `ToolMessage(role="tool", tool_call_id=...)` |
| 错误处理 | 正则没匹配到 → 静默失败或猜测 | 函数名不存在 → ToolNode 直接报错调用方可见 |
| 并发调用 | 难以解析多个混在一起的指令 | 一个响应多个 `tool_calls`，各自独立的 `tool_call_id` |
| LLM 训练 | 不一定被专门训练过这种文本格式 | 模型被 fine-tune 过 function calling，知道 tool_calls 的语义 |

### 3.3 为什么 Function Calling 对这类系统重要

1. **工具调用是机器可验证的**：`write_foo` 要么成功返回 `"foo_player.py updated successfully"`，要么抛异常。不存在"LLM 写了代码但没真正写入文件"的灰色地带。

2. **错误可溯源**：如果 `replace_code_in_foo` 返回 `"Search string not found"`，LLM 收到的是结构化的 ToolMessage，它知道自己需要修正 `search` 参数重试。

3. **并发安全**：LLM 可以同时调用 `read_adapter` 和 `read_foo`，两个 ToolMessage 各自携带独立的 `tool_call_id`，不会混淆。

4. **LLM 理解工具的语义**：Function Calling 模型在训练时就被教导"tool_calls 意味着外部函数将被执行，ToolMessage 是执行结果"。它不会把 ToolMessage 当成用户说的话来回复"谢谢你的结果"。

---

## 四、think_tool 的深度分析

### 4.1 think_tool 的实现

```python
def think_tool(reflection: str) -> str:
    """Tool for strategic reflection on research progress and decision-making.
    ...
    """
    return f"Reflection recorded: {reflection}"
```

它接收一段文本，返回 `"Reflection recorded: " + 输入文本`。**函数的返回值 = 输入**（只加了个前缀）。

### 4.2 那它到底有什么用？

核心答案：**think_tool 的价值不在返回值，而在调用这个动作本身把一次 LLM 生成拆分成了"推理 → 确认 → 输出"两段。**

### 4.3 对比：有 vs 没有 think_tool

**没有 think_tool**：META 的推理和调度指令混在一次 LLM 生成中——

```
嗯，Analyzer 确认了 root cause：总是选第一个动作。
我需要让 Strategizer 设计一个 1-ply 方案。
具体来说要包含 copy_game + make_value_fn，
还要考虑 tie-breaker，限制 max_actions 防超时……
好，那我现在决定：

- META THOUGHTS: Analyzer confirmed root cause...
- CHOSEN AGENT: STRATEGIZER
- AGENT OBJECTIVE: Design a 1-ply lookahead strategy...
```

全部一次输出。推理过程混进了最终文本，下游 Agent 看到的 OBJECTIVE 前面夹杂着推理碎片。

**有 think_tool**：流程变成两个独立的 LLM 回合：

```
[回合 1] LLM 输出 tool_call:
  think_tool(reflection="Analyzer confirmed root cause... Need to implement 
  1-ply lookahead... must avoid timeouts... plan: action filtering, scoring, 
  tie-break rules, efficiency constraints (max_actions=20)...")
  → ToolNode 执行 → 返回 ToolMessage "Reflection recorded: ..."
  → LLM 收到 ToolMessage，知道自己"已经想过了"

[回合 2] LLM 基于刚才的思考，输出干净的调度指令：
  - META THOUGHTS: (简要总结)
  - CHOSEN AGENT: STRATEGIZER
  - AGENT OBJECTIVE: (精确的任务描述，不含推理碎片)
```

两次 LLM API 调用。第一次是"思考"，第二次是"决策"。两次之间有明确的 state transition。

### 4.4 真实调用示例（来自 excellent_run 日志）

**META 使用 think_tool（E1）**：

```
Tool Calls:
  think_tool (call_Dxilct0IJnmRAlHYMeVTwWic)
  Args:
    reflection: Findings: Analyzer confirmed root cause: always selecting first 
    action. Need to propose minimal-change strategy that is low complexity and 
    high impact: implement 1-ply lookahead scoring with make_value_fn('base_fn') 
    using copy_game and execute. Consider tie-breakers to prefer build actions. 
    Must avoid timeouts by limiting to 1-ply and possibly capping number of 
    actions evaluated. Also consider excluding EndTurn from initial evaluation... 
    Plan: produce a clear step-by-step strategy with action filtering, scoring, 
    tie-break rules, efficiency constraints (max_actions), and suggested logging 
    for debugging...

→ ToolNode 返回: "Reflection recorded: Findings: Analyzer confirmed root cause..."

→ 然后 META 输出:
  - META THOUGHTS: The Analyzer confirmed the root cause...
  - A minimal, high-impact fix is a 1-ply lookahead...
  - CHOSEN AGENT: STRATEGIZER
  - AGENT OBJECTIVE: (精确的调度指令，干净分离)
```

**ANALYZER 使用 think_tool 诊断错误（E2）**：

```
Tool Calls:
  think_tool (Mrdv4JjE5)
  Args:
    reflection: ### Analysis of Current Situation
    1. **Error Summary**: The game failed due to AttributeError in foo_player.py 
       line 48. **Error**: PLAY_DEVELOPMENT_CARD. Did you mean: 'BUY_DEVELOPMENT_CARD'?
    2. **Likely Cause**: The PRIORITY dictionary includes ActionType.PLAY_DEVELOPMENT_CARD
       which does not exist in the ActionType enum...
    3. **Quick Fix Focus**: Replace ActionType.PLAY_DEVELOPMENT_CARD with 
       ActionType.BUY_DEVELOPMENT_CARD...
```

**STRATEGIZER 使用 think_tool 设计方案（E3）**：

```
Tool Calls:
  think_tool (caR0309bc)
  Args:
    reflection: Current State Analysis:
    - Evolution 2's FooPlayer achieved 15 wins and avg_score 8.1, significant 
      improvement. This confirms the 1-ply deterministic lookahead is effective 
      but lacks chance handling (dice rolls, dev card draws, robber outcomes).
    Key Gaps:
    1. Chance Handling: no stochastic outcomes...
    2. Robber/Resource Heuristics: no explicit targeting...
    3. Efficiency: must cap simulations and early abort...
    Proposed Strategy: 1. Chance-Aware Evaluation: ...
```

### 4.5 四个真正的作用

**① 强制推理/决策分离**

思考内容放在 tool_call 的 arguments 里，最终调度指令是独立的 AiMessage。下游 Agent 读到的是干净的 OBJECTIVE，不是混着推理碎片的文本。

**② 延长推理链（对无原生 thinking 模型尤其重要）**

多一轮 tool-calling 循环 = 多一次 LLM 推理。对于 Mistral 这样没有原生 thinking mode 的模型，这就是低成本版的 chain-of-thought 引导。

**③ 防止并行调用**

System Prompt 明确约束：

> *"Do not call think_tool with any other tools in parallel."*

强制 LLM 必须先想清楚，再调其他工具。如果不加这个约束，LLM 可能同时 call `think_tool` 和 `write_foo`，文件写完了但"思考"的内容和实际写入不一致。

**④ 强制总结（仅 META）**

META 的 System Prompt 中还特别加了一句：

> *"The think_tool messages will only be visible to you for your current turn, so ensure to summarize your thoughts in META THOUGHTS"*

这告诉 LLM"你的思考过程不会被持久化到消息历史"，关键结论必须写进 META THOUGHTS。虽然实际代码中 ToolMessage 确实被保留在消息历史中（`meta_messages` 累积所有消息），但这条提示起到了**强迫 LLM 做总结**的作用。

### 4.6 一句话总结

> `think_tool` 就是给 LLM 的 **"你先在脑子里过一遍再开口"** 按钮。真正的价值不在返回内容，而在调用这个动作本身把一次生成拆分成了"推理 → 确认 → 输出"两段。
