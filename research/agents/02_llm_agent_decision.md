# 方向二：LLM Agent 的决策能力 — 代表性工作

> 调研日期: 2026-07-21
> 聚焦：大语言模型作为自主 Agent 的推理、规划、工具使用与反思能力，涵盖从 2023 到 2025 的核心进展

---

## 概述

2023 年是大语言模型 (LLM) Agent 的"元年"。研究者发现，LLM 不仅可以生成文本，还可以作为**自主决策体**：观察环境、推理、使用工具、从反馈中学习。本节收录 **8 个代表性工作**，覆盖 LLM Agent 决策能力的核心范式。

### 能力维度演化

```
基础推理 (CoT)
  → 推理+行动交织 (ReAct)
    → 自监督工具学习 (Toolformer)
      → 口头强化学习 (Reflexion)
        → 树搜索推理 (ToT)
          → 多 Agent 协作 (CAMEL / MetaGPT)
            → 规划-执行分离 (Beyond ReAct / Thinker)
```

---

## 1. ReAct: Synergizing Reasoning and Acting

| 维度 | 详情 |
|------|------|
| **发表时间** | 2023 年 3 月 (ICLR 2023) |
| **机构** | Princeton / Google DeepMind |
| **作者** | Shunyu Yao, Jeffrey Zhao, Dian Yu 等 |
| **会议** | ICLR 2023 |

### 核心思想

ReAct 提出了一种**交替式推理-行动范式**：LLM 生成一段推理文字 (thought)，然后执行一个行动 (action)，观察结果 (observation)，再生成下一段推理……如此循环，直到任务完成。

```
Thought → Action → Observation → Thought → Action → Observation → ...
```

### 关键创新

- **增强的行动空间**：将推理 trace 和可执行行动统一在同一序列中
- **可解释性**：推理 trace 提供了完整的决策过程记录
- **动态调整**：Agent 可以根据观察结果实时修正推理方向

### 关键成果

- **知识密集型任务** (HotPotQA)：ReAct + CoT 结合使用，显著优于纯 CoT
- **交互式决策** (AlfWorld)：ReAct 成功率远高于纯推理或纯行动基线
- 缓解了 LLM 的 **"幻觉"** 问题——当推理与外部观察关联时，模型更倾向于生成事实性内容

### 局限

- 逐步推理导致 **局部最优陷阱**——缺乏全局规划
- 每一步都需要完整的 LLM 前向调用，延迟高
- 对长任务链可能产生错误累积

### 影响

ReAct 奠定了 LLM Agent 的基础范式。后续几乎所有 LLM Agent 框架（AutoGPT、LangChain Agent、Claude Agent SDK）都继承了"推理→行动→观察→推理"的循环结构。

---

## 2. Toolformer: Language Models Can Teach Themselves to Use Tools

| 维度 | 详情 |
|------|------|
| **发表时间** | 2023 年 2 月 (NeurIPS 2023 Oral) |
| **机构** | Meta AI Research |
| **作者** | Timo Schick, Jane Dwivedi-Yu, Roberto Dessì 等 |

### 核心思想

大模型可以**自监督地学会何时以及如何调用外部工具 API**（计算器、搜索引擎、翻译、日历），无需大量人工标注。

### 自监督训练流程

1. **生成 API 调用候选**：用少量人工示例 (few-shot)，让模型在大量文本中插入 API 调用标记
2. **执行 API 并增强数据**：实际执行 API，将返回结果替换到文本中
3. **自监督过滤**：比较有无 API 调用时的 token 预测概率，仅保留真正有助于预测的 API 调用
4. **微调**：在过滤后的数据集上进行标准语言模型训练

### 关键成果

- 在 GPT-J (6.7B) 上微调的 Toolformer：
  - **数学推理**：在 ASDiv、SVAMP、MAWPS 上显著超越 OPT (66B) 和 GPT-3 (175B)
  - **问答**：在 Web Questions、Natural Questions、TriviaQA 上超越同规模基线，接近更大模型
  - **时间推理**：使用日历 API 处理 TEMPLAMA 时间推理任务远优于基线
- **无副作用**：工具使用能力对核心语言模型能力零损害
- **规模效应**：更大的 Toolformer 变体 **调用工具的需求反而减少**——更大模型内部化更多知识

### 局限

- 工具调用不能交互或链式组合（每次 API 调用独立）
- 工具集固定，添加新工具需要重新生成训练数据

### 影响

Toolformer 证明了一个关键原则：**LLM 可以在不需要架构修改的情况下学会"何时求助"外部工具**。这成为后续 Agent 框架中工具调用 (function calling) 功能的理论基础。

---

## 3. Reflexion: Language Agents with Verbal Reinforcement Learning

| 维度 | 详情 |
|------|------|
| **发表时间** | 2023 年 (NeurIPS 2023) |
| **机构** | Princeton / MIT |
| **作者** | Noah Shinn, Federico Cassano, Edward Berman 等 |

### 核心思想

Reflexion 的核心创新是**口头强化学习 (Verbal RL)**：Agent 不通过梯度下降或权重更新来"学习"，而是通过生成自然语言形式的**反思文本**，并存储在记忆缓冲区中，在后续尝试时注入上下文。

### 架构三组件

```
┌──────────────────────────────────────┐
│  Actor (执行者)                       │
│  ← 从记忆缓冲区获取之前的反思         │
│  → 生成文本/行动                     │
├──────────────────────────────────────┤
│  Evaluator (评估者)                  │
│  ← 接收行动轨迹                      │
│  → 输出标量奖励 + 启发式反馈          │
├──────────────────────────────────────┤
│  Reflector (反思者)                  │
│  ← 接收奖励 + 轨迹                   │
│  → 生成语言反思，存储到情节记忆       │
└──────────────────────────────────────┘
```

### 关键成果

- **编程 (HumanEval)**：pass@1 达到 **91%**，超越 GPT-4 的 80%
- **决策 (AlfWorld)**：ReAct + Reflexion 完成 130/134 任务
- **推理 (HotPotQA)**：持续优于纯 CoT 和 CoT + 情节记忆

### 适用场景

- 需要**试错学习**的任务
- 传统 RL 因数据/训练成本不可行的场景
- **可解释的学习过程**很重要的应用

### 影响

Reflexion 证明 LLM Agent 可以通过**语言进行"学习"**，这是对传统 RL 范式的重要补充——语言反馈比标量奖励更丰富、更具信息量。后续大量 Agent 框架（如 Claud Code 的 self-correction 机制）都受其影响。

---

## 4. Tree of Thoughts (ToT): Deliberate Problem Solving

| 维度 | 详情 |
|------|------|
| **发表时间** | 2023 年 5 月 (NeurIPS 2023 Oral) |
| **机构** | Princeton / Google DeepMind |
| **作者** | Shunyu Yao, Dian Yu, Jeffrey Zhao 等 |

### 核心思想

Chain-of-Thought (CoT) 的局限在于"**单链推理**"——一旦某步推理出错，整个链条断裂。ToT 将推理过程建模为**树搜索问题**：在每一步生成多个候选"想法"(thought)，用 LLM 自评估质量，用 BFS/DFS 进行剪枝和回溯。

### 方法框架

```
初始状态 → [思想 A1, A2, A3] (生成)
  → 评估: A1=0.8, A2=0.3, A3=0.6
    → 扩展 A1 → [B1, B2]
    → 扩展 A3 → [B3, B4]
      → ... → 回溯/剪枝 → 最终解答
```

### 关键成果

| 任务 | IO/标准提示 | CoT | ToT |
|------|-----------|-----|-----|
| Game of 24 (数学) | 7.3% | 4.0% | **74%** |
| Creative Writing | 6.19 | 6.93 | **7.56** |
| Mini Crosswords | 0% (词级) | 0% (词级) | **60%** (词级) |

### 代价

ToT 的计算成本远高于 CoT：每次搜索需要 ~20 次生成 + 20 次评估器分数（vs. CoT 的单次前向传播），token 消耗和延迟都成倍增加。

### 适用条件

ToT 在以下情况下值得使用：
- 任务需要**非平凡规划、探索或战略性前瞻**
- 单步推理容易出错的复杂问题
- 可以定义清晰的中间状态和评估标准

### 影响

ToT 开启了"**搜索增强 LLM 推理**"的新范式，后续工作如 Graph-of-Thought (GoT)、Reasoning via Planning (RAP) 都是其延伸。

---

## 5. CAMEL: Communicative Agents for "Mind" Exploration

| 维度 | 详情 |
|------|------|
| **发表时间** | 2023 年 3 月 (NeurIPS 2023) |
| **机构** | KAUST (阿卜杜拉国王科技大学) |
| **核心范式** | 角色扮演式多 Agent 对话协作 |

### 核心思想

CAMEL 是**首个基于 ChatGPT 的多 Agent 自主协作框架**（2023 年 3 月 21 日发布，早于 AutoGPT）。核心理念是：两个 LLM Agent 分别扮演"AI 用户"和"AI 助手"，通过持续对话完成复杂任务。

### 关键机制

- **Inception Prompting (起始提示)**：在准备阶段，人类提供一个粗略想法 → Task Specifier Agent 细化为具体任务 → 为两个 Agent 分配角色 → 对话阶段开始
- **Critic-in-the-Loop (可选)**：第三个"评论员"Agent 评估用户和助手的提案，提高决策质量
- **缓解常见失败模式**：角色颠倒、重复指令、无限对话循环

### 关键成果

- 在人类评估（453 票）和 GPT-4 评估中超越单模型 `gpt-3.5-turbo`
- 生成了 **AI Society** 和 **AI Code** 两个大规模指令微调数据集
- 在 CAMEL 生成数据上微调 LLaMA-7B，HumanEval 表现显著提升

### 意义

CAMEL 证明了**多 Agent 角色扮演式协作**的有效性——比单个 Agent 尝试所有角色更高效。

---

## 6. MetaGPT: Meta Programming for Multi-Agent Collaboration

| 维度 | 详情 |
|------|------|
| **发表时间** | 2023 年 8 月 |
| **机构** | 多机构合作 |
| **GitHub Stars** | ~29,700 (2023 年底) |
| **核心范式** | 基于 SOP (标准操作流程) 的流水线式多 Agent |

### 核心思想

将人类软件开发中的**瀑布式工作流 (SOP)** 编码为多 Agent 协作框架。每个 Agent 扮演一个固定角色（产品经理、工程师、QA 测试），按顺序产出结构化中间产物。

```
产品经理 → 需求文档 → 工程师 → 代码 → QA → 测试报告 → 最终交付
```

### 关键机制

- **共享消息池 (Shared Message Pool)**：Agent 发布消息并订阅与其角色相关的信息
- **面向产出物 (Artifact-Oriented)**：每个 Agent 产出一个具体的结构化文档
- **降低幻觉**：SOP 约束的流水线降低了单 Agent 自由探索带来的幻觉风险

### 意义

MetaGPT 证明了：**结构化的人类工作流程可以被直接"翻译"为多 Agent 协作框架**，这种方法在软件工程等需要严谨产出的领域尤其有效。

---

## 7. Beyond ReAct: Planner-Centric Framework (2025)

| 维度 | 详情 |
|------|------|
| **发表时间** | 2025 年 |
| **核心范式** | 规划-执行分离 (Plan-Execute) |

### 核心思想

ReAct 类方法的最大问题是**局部最优陷阱**——每步推理只考虑当前状态，缺乏全局规划。Beyond ReAct 提出将**全局规划**和**逐步执行**解耦：

1. **Planner**：将复杂查询翻译为**有向无环图 (DAG)** 执行计划，节点表示工具选择，边表示依赖关系
2. **Executor**：按 DAG 并行执行各分支，充分利用并行机会

### 训练方法

- SFT (监督微调) + GRPO (Group Relative Policy Optimization)
- 在 StableToolBench 上达到 SOTA

### 关键优势

- 利用 ReAct 式推理忽略的**并行机会**
- 全局视角避免局部最优
- 可解释性更好（DAG 便于调试和理解）

---

## 8. Thinker: State-Machine Augmented Generation (2025)

| 维度 | 详情 |
|------|------|
| **发表时间** | 2025 年 |
| **核心范式** | 状态机增强生成 (SMAG) |

### 核心思想

将**业务逻辑表示显式状态机**，作为 LLM Agent 的工具使用，结合 LLM 驱动的子工具和自适应上下文管理。

### 关键成果 (τ-bench Retail)

| 模型 | 成功率 |
|------|--------|
| GPT-4o 基线 | 68.3% |
| GPT-4o + Thinker | **82.6%** |
| Llama-3.1 405B 基线 | 49.6% |
| Llama-3.1 405B + Thinker | **81.9%** |

### 意义

Thinker 证明了一个重要观点：**工具接口设计的创新**（将业务流程编码为显式状态机）可以比提升基座模型的推理能力带来更大的性能增益。Llama 405B + Thinker 几乎追平 GPT-4o + Thinker，说明好的 Agent 框架可以弥补基座模型的差距。

---

## 关键趋势总结

### 1. 从反应式到规划式
ReAct → Beyond ReAct：从逐步被动推理到全局 DAG 规划。

### 2. 从隐式到显式记忆
Reflexion → FuseMind：从隐式上下文中的"学习"到显式情节记忆存储和检索。

### 3. 从单 Agent 到多 Agent
CAMEL → MetaGPT：从独立推理到分工协作、角色扮演。

### 4. 从通用到领域专用工具接口
Toolformer → Thinker：从通用 API 调用到领域专用的状态机/工作流工具。

### 5. 工具接口创新的重要性
Thinker、Beyond ReAct 表明：**工具接口设计的创新** ≥ 提升基座模型能力。

---

## 与六朝项目的关联

六朝 (Six Dynasties) 的游戏 AI 可以借鉴以下 LLM Agent 决策模式：

| 范式 | 在六朝中的潜在应用 |
|------|-------------------|
| **ReAct** | AI 玩家每回合"思考→行动→观察对手反应→调整策略" |
| **Reflexion** | AI 玩家从失败的策略中总结"反思"，下一局自动修正 |
| **ToT** | 在关键决策节点（如是否称帝），用树搜索评估多个候选方案 |
| **MetaGPT/SOP** | 多维度决策（军事/文化/经济）分配给专门的"子 Agent"协作 |
| **Plan-Execute** | 先规划整回合的宏观策略，再逐步执行各阶段动作 |
| **记忆系统** | AI 玩家维护"对手画像"（如某玩家偏好偷袭），跨对局学习 |

---

## 参考文献

- Yao, S. et al. (2023). ReAct: Synergizing Reasoning and Acting in Language Models. *ICLR 2023*.
- Schick, T. et al. (2023). Toolformer: Language Models Can Teach Themselves to Use Tools. *NeurIPS 2023 (Oral)*.
- Shinn, N. et al. (2023). Reflexion: Language Agents with Verbal Reinforcement Learning. *NeurIPS 2023*.
- Yao, S. et al. (2023). Tree of Thoughts: Deliberate Problem Solving with Large Language Models. *NeurIPS 2023 (Oral)*.
- Li, G. et al. (2023). CAMEL: Communicative Agents for "Mind" Exploration of Large Language Model Society. *NeurIPS 2023*.
- Hong, S. et al. (2023). MetaGPT: Meta Programming for Multi-Agent Collaborative Framework. *arXiv:2308.00352*.
- Wei, J. et al. (2025). Beyond ReAct: A Planner-Centric Framework for Complex Tool-Augmented LLM Reasoning. *arXiv:2511.10037*.
- Wu, Z. et al. (2025). Thinker: State-Machine Augmented Generation for Complex Task Completion.
- Anthropic. (2024–2025). Claude Agent SDK & Computer Use Documentation.
