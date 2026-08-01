# Beyond ReAct: A Planner-Centric Framework — 深度解析

> 论文: Xiaolong Wei (北航), Yuehu Dong (百度), Xingliang Wang (北邮), Xingyu Zhang (北交大), Zhejun Zhao, Dongdong Shen, Long Xia, Dawei Yin (百度)
> 发表: AAAI 2026 (Poster) | arXiv: 2511.10037 | 代码: [github.com/weixiaolong94-hub/Beyond-React](https://github.com/weixiaolong94-hub/Beyond-React)

---

## 1. 核心 Motivation

### ReAct 的"局部最优陷阱"

ReAct 的基本范式是"推理一步 → 行动一步 → 观察 → 推理下一步"。这个模式有一个**结构性的缺陷**：每一步的决策只基于当前状态，看不到全局依赖关系。

论文用了一个比喻：

> **"像在没有蓝图的情况下盖房子——墙都砌好了才发现忘了打地基。"**

具体来说，ReAct 有三个固有问题：

| 问题 | 表现 | 后果 |
|------|------|------|
| **短视决策** | 每步只看到"现在需要什么"，不知道"后面还需要什么" | 顺序错误、遗漏依赖 |
| **重复/冗余调用** | 回头发现缺数据，重新调用或废弃之前产物 | Token 浪费、延迟增加 |
| **无法识别并行** | 天然串行，即便多个工具之间无依赖 | 慢 |

### 为什么 Tree Search 也没解决？

DFSDT 等方法在 ReAct 基础上加了树搜索——探索多条路径再选最优。但论文指出这种做法**没有从架构上解决局部最优问题**——它只是在多个局部最优序列中挑一个，而且计算开销巨大。

### 核心洞察

> **把"规划"和"执行"分离。** 规划时一次性看清所有工具和依赖关系（全局视角），执行时并行调度（效率最大化）。

---

## 2. 整体架构

### Plan-Execute 两阶段

```
用户 Query
    │
    ▼
┌──────────────────┐
│  Planner (精调)   │  ← 一次性生成完整 DAG
│  Qwen3-8B + RL   │     单次前向传播
└────────┬─────────┘
         │ DAG 计划
         ▼
┌──────────────────┐
│  Executor        │  ← 按 DAG 调度执行
│  GPT-4o          │     无依赖节点并行
└────────┬─────────┘     有依赖节点串行
         │
         ▼
      最终回答
```

### DAG 的定义

```
节点 (Node) = 一个工具调用 (如 get_weather, search_flights)
边 (Edge)   = 数据依赖关系 (B 的输入需要 A 的输出)
无边的节点  = 可以并行执行
```

### 两层 Decoupling 的含义

| 层面 | 分离了什么 | 好处 |
|------|-----------|------|
| **架构上** | Planner (小模型) vs Executor (大模型) | 8B 小模型管规划，GPT-4o 管执行——省钱 |
| **逻辑上** | 想 (Planning) vs 做 (Execution) | 想的时候看到全局，做的时候最大化并行 |

---

## 3. 三个具体 Case

### Case 1: 天气查询 + 条件推荐（论文 Figure 1）

**用户 Query**:
> "查询北京明天的天气。如果下雨，推荐室内活动。如果不下雨，推荐户外景点。"

**ReAct 的做法**（串行试探）:

```
Step 1: Thought: 需要查天气
        Action: get_weather(city="Beijing", date="tomorrow")
        Observation: Rain, 15°C

Step 2: Thought: 下雨了 → 推荐室内活动
        Action: recommend_indoor_activities(city="Beijing")
        Observation: [博物馆, 商场, 电影院...]

Step 3: 整理输出
```

**问题**: 3 步串行。而且有两个隐藏的坏处：(1) 如果未来再加一个条件分支（如下雪），ReAct 需要额外 reasoning step；(2) 室内活动和户外景点 API 其实**语义上等同**——只是条件不同——但 ReAct 把它们当成两个完全独立的决策点。

**Beyond ReAct 的 DAG**（一次性生成）:

```
                    ┌─────────────────┐
                    │ get_weather     │
                    │ (Beijing, tmr)  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  condition:     │
                    │  rain?          │
                    └──┬──────────┬───┘
                       │YES       │NO
                       ▼          ▼
              ┌──────────┐  ┌──────────────┐
              │indoor_   │  │outdoor_      │
              │activities│  │attractions   │
              └──────────┘  └──────────────┘
```

**优势**: Planner 在第一步就"看到"了这个条件分支结构——整个任务骨架在一次前向传播中确定。

---

### Case 2: 股票分析（论文 Figure 1 并行依赖案例）

**用户 Query**:
> "分析特斯拉 Q2 表现，结合当前政策和宏观经济指标，生成可视化报告并评估风险。"

**ReAct 的做法**（局部最优的典型案例）:

```
Step 1: Thought: 需要股票数据
        Action: get_stock_data("TSLA", "Q2")
        Observation: [股价、财报数据...]

Step 2: Thought: 数据拿到了。光看股票不够，还得看政策
        Action: get_policy_data("2024-Q2")         ← 第二步才"发现"需要
        Observation: [新能源补贴、关税调整...]

Step 3: Thought: 有股票和政策数据了，先画个股价图
        Action: generate_chart(data=stock_data)     ← 致命错误！
        Observation: [股价走势图]                   ← 这张图后来作废了

Step 4: Thought: 等等，还缺宏观经济数据！
        Action: get_economic_indicators("2024-Q2")  ← 画完图才想起来
        Observation: [CPI, PMI, 利率...]

Step 5: Thought: 三数据齐了，评估风险
        Action: predict_risk(stock, policy, econ)
        Observation: [风险评估报告]

Step 6: Thought: 之前的股价图没包含政策和经济数据，重新画！
        Action: generate_chart_v2(stock, policy, econ) ← 重复劳动！
```

**为什么这是"局部最优"？**

每一步单看都合理：
- Step 1 查股票 ✓
- Step 2 补政策数据 ✓
- Step 3 有数据了就画图 ✓
- Step 4 发现缺经济数据 → 补充 ✓

但 Step 3 是在"还不知道需要经济数据"的时候做的决策。单步最优 ≠ 全局最优。**Step 3 和 Step 6 之间是一次完全的浪费。**

**Beyond ReAct 的 DAG**:

```
get_stock_data ─────┬──────────────┐
                    │              │
get_policy_data ────┤              │
                    │              ▼
get_economic ───────┤    ┌─────────────────┐
_indicators         │    │ predict_risk    │
                    │    │ (需要全部3个)    │
                    │    └─────────────────┘
                    │              
                    ▼              
            ┌──────────────┐
            │ generate_    │
            │ visualization│
            │ (需要全部3个) │
            └──────────────┘
```

Executor 调度:
- **Step 1**: `get_stock_data` ‖ `get_policy_data` ‖ `get_economic_indicators`（三个同时发出）
- **Step 2**: `predict_risk` ‖ `generate_visualization`（两个同时发出）

**总计 2 步，零冗余，零废弃。**

---

### Case 3: 旅行规划（论文 Table 17 完整实际输出）

**用户 Query**:
> "Plan a 5-person, 3-day trip from Charlotte to Hilton Head from March 26-28, 2022, with a $7,000 budget. We prefer Italian and French cuisine."

**DAG 结构**:

```
        ┌─────────────────────────┐
        │  SearchFlights          │
        │  CLT → HHH, 3/26       │
        └────────────┬────────────┘
                     │
        ┌────────────▼────────────┐
        │  SearchAccommodation    │
        │  Hilton Head, 5人      │
        └────────────┬────────────┘
                     │
    ┌────────────────┼────────────────┐
    │                │                │
    ▼                ▼                ▼
┌──────────┐  ┌────────────┐  ┌──────────────┐
│Search    │  │Search      │  │SearchFlights │
│Restau-   │  │Attrac-     │  │HHH → CLT     │
│rants     │  │tions       │  │3/28          │
│(意/法)   │  │            │  │              │
└──────────┘  └────────────┘  └──────────────┘
    │                │                │
    └────────────────┼────────────────┘
                     ▼
            ┌────────────────┐
            │  整合 + 预算   │
            │  校验          │
            └────────────────┘
```

**关键观察**: 餐厅搜索、景点搜索、返程航班三者**无依赖、可并行**。ReAct 必须一个一个串行调完。

**最终输出**:

| 天 | 交通 | 早餐 | 景点 | 午餐 | 晚餐 | 住宿 |
|----|------|------|------|------|------|------|
| Day 1 | 航班 F4055090 CLT→HHH 18:07-19:27 | Hunger's Hub ($97) | Coastal Discovery Museum | Ashirbad ($50, 地中海/海鲜) | Wrapster ($18, 法餐/意餐/海鲜) | Hip Vibrant Downtown ($763) |
| Day 2 | — | Hunger's Hub | Harbour Town Lighthouse + Coligny Beach Park | Ashirbad | Wrapster | Hip Vibrant Downtown |
| Day 3 | 航班 F4056985 HHH→CLT 20:07-21:31 | Hunger's Hub | Books Monument (夏洛特) | Ashirbad | Wrapster | — |

---

## 4. 训练方法

### 数据: ComplexTool-Plan Benchmark

| 指标 | 数值 |
|------|------|
| API 来源 | ModelScope 上的 **4,535 个真实 API** |
| 难度分级 | Easy (并行) / Medium / Hard (嵌套逻辑) |
| SFT 数据 | **3,000 条** |
| RL 数据 | **787 条**（高方差筛选，8:2 split） |

#### 数据生成 pipeline（DeepSeek-V3 做 teacher）

```
Step 1: Workflow Generation
        从工具库抽样 API 子集 → LLM 为其生成 DAG 工作流

Step 2: Query Reverse-Engineering
        从 DAG 反向生成自然语言 query

Step 3: Re-planning Validation
        从 query 重新生成 plan → 检查一致性 → 过滤不一致的
```

### 两阶段训练

#### Stage 1: SFT（冷启动）

- 基座: Qwen3 (0.6B / 1.7B / 4B / 8B)
- 用 LLaMA-Factory 做全参数微调
- 目标: 学会 DAG 的基本语法和格式

#### Stage 2: GRPO（强化学习优化）

用 verl 框架 + **层级奖励函数** (`[-10.0, +10.0]`):

```
Level 1 (语法)
  ├── 非 JSON 格式 → -10.0 (直接终止评估)
  └── 格式正确 → 进入 Level 2

Level 2 (结构)
  ├── DAG 存在环 → -10.0 (直接终止)
  ├── 存在孤立节点 → -2.0
  └── 全连通无环 → 进入 Level 3

Level 3 (语义)
  ├── Edge F1 Score × 5 → 部分匹配奖励
  └── Perfect Match → +5.0 bonus
```

**关键设计**: fail-fast 机制——语法和结构错误立即终止评估、给最大惩罚，不让模型在无效输出上浪费训练信号。同时只筛选高方差样本做 RL（排除太简单和太难的），防止策略退化。

### 训练结果

| 训练模式 | Easy DAG EM | Hard DAG EM |
|---------|------------|------------|
| SFT only (8B) | 0.781 | 0.295 |
| **SFT + GRPO (8B)** | **0.803** | **0.319** (+8.1%) |
| GPT-4o (zero-shot) | 0.635 | 0.098 |

- SFT 提供了基本能力（冷启动）
- GRPO 在困难任务上额外提升 8.1%
- **8B 精调模型超越 GPT-4o zero-shot**（0.319 vs 0.098）——说明通用大模型不擅长 DAG 规划，专门训练的小模型反而更强

---

## 5. 实验结果

### StableToolBench 端到端评估

| 方法 | SoPR | 平均推理步数 |
|------|------|-------------|
| GPT-4 (ReAct) | 48.2% | 3-5 |
| ToolLLaMA (ReAct) | 37.9% | 3-5 |
| LLMCompiler | 36.2% | — |
| DTA-Llama | — | 2.48 |
| **Beyond ReAct (8B RL + GPT-4o Executor)** | **59.8%** | **2.29** |

**解读**:

- 相比 GPT-4 ReAct: SoPR **+11.6pp**，步数减少到 **2.29 步**
- 注意: 这里的 Beyond ReAct 的 **Executor 也是 GPT-4o**——所以两个方法用的是同一个执行模型。唯一区别是 Planner 用 DAG 替代了 ReAct 的逐步推理。**这表明: 对同一个 GPT-4o，给它 DAG plan 比让它自己一步一步想，做得好得多。**

### 规模效应

| 模型 | Easy DAG EM | Hard DAG EM | 衰减 |
|------|-----------|-----------|------|
| Qwen3-1.7B (RL) | 0.634 | 0.183 | **-71.2%** |
| Qwen3-8B (RL) | 0.803 | 0.319 | **-60.3%** |

更大的模型从 Easy 到 Hard 的下降更平滑——明显的 scaling law。

---

## 6. SoPR 指标解析

### 为什么 ToolBench 的原始 Pass Rate 不够？

原始 ToolBench 的测试集里有些 query **本身就是不可解的**（要求调用的工具在 API 库里不存在）。如果直接用 Pass Rate，模型在"不可解"任务上的表现（无论好坏）都会干扰真实能力评估。

### SoPR 的计算

```
Step 1: GPT-4 逐条判断每个 query 是否 Solvable（可解）
        Unsolvable → 排除，不参与计分

Step 2: 对每个 Solvable query 评估模型输出:
        Solved  = 1.0
        Unsure  = 0.5
        Unsolved = 0.0

SoPR = Σ(分数) / Solvable任务数
```

**通俗理解**: SoPR 只考核"你该做对的任务"上的表现。那些"给定现有工具集，理论上就不可能完成"的任务不算分。"神仙也做不到的，我不要求你做到。"

### 数值含义

| SoPR | 含义 |
|------|------|
| 48.2% (GPT-4 ReAct) | 可解任务中，近半数能正确处理 |
| 59.8% (Beyond ReAct) | 可解任务中，近六成完全正确 |
| 差距 11.6pp | 同样的 Executor (GPT-4o) + 不同的规划方式 → ~12% 的可解任务从失败变成成功 |

---

## 7. 五个范式对比

| 维度 | CoT | ReAct | ToT | Reflexion | **Beyond ReAct** |
|------|-----|-------|-----|-----------|-----------------|
| 决策方式 | 单链推理 | 推理⇄行动交替 | 树搜索 | 事后反思 | **DAG 全局规划** |
| 时间尺度 | 单次 | 在线、逐步 | 单次内搜索 | 跨 episode | **单次、一次性 plan** |
| 并行能力 | ❌ | ❌ | ❌ (同层可并行) | ❌ | **✅ 最大并行** |
| 纠错机制 | 无 | 环境反馈 | 评估+回溯 | 反思记忆 | **无（plan 错则全错）** |
| 步数/成本 | 1× | 3-5× | 10-20× | 多次尝试 | **~2.3 步** |
| 核心风险 | 第一步错全盘输 | 局部最优 | 评估不可靠 | 反思质量差 | **plan 错则全错，不可中途修正** |
| 适用场景 | 线性推理 | 交互式任务 | 组合搜索 | 可反复试错 | **多工具、依赖可预判** |

### 核心优势 vs 代价

DAG 的核心优势不是"更快"，而是：

> **在第一个工具被调用之前，整个任务的骨架就已经确定。ReAct 是在执行中逐步"发现"任务结构，每一步都可能因为信息不完整而做出次优决策。并行只是全局视角的副产品。**

代价也很明确：

> **一旦 plan 错了，全盘皆错，没有回头路。ReAct 虽然慢且可能局部最优，但每一步都有机会根据观察调整。**

---

## 8. 对六朝项目的启示

### 适用场景

| 六朝场景 | 是否适合 DAG Planner | 原因 |
|---------|---------------------|------|
| 整回合多阶段操作（调度→行军→战斗→占领） | ✅ | 回合内的操作依赖关系明确、可预判 |
| 多维度并行决策（经济+军事+文化同步推进） | ✅ | 三个维度天然独立，DAG 天然并行 |
| 对对手行动的应对 | ❌ | 对手行为不可预测，无法提前规划依赖 |
| 多工具组合查询（查规则+查卡牌+查历史对局） | ✅ | 工具间依赖关系已知、可建模为 DAG |

### 可借鉴的设计

1. **两层 Decoupling**: 规划用小模型（便宜）+ 执行用大模型（强）。六朝中可以用 8B 模型规划回合路线，GPT-4 负责关键战斗决策
2. **层级奖励函数**: fail-fast + structure + semantic 的三级评估——可以直接用于训练六朝的规划模型
3. **全局规划 vs 响应式决策的边界**: 可预判的部分（自身操作序列）→ DAG plan；不可预判的部分（对手反应）→ ReAct loop

---

## 9. 参考文献

- Wei, X. et al. (2025). Beyond ReAct: A Planner-Centric Framework for Complex Tool-Augmented LLM Reasoning. *AAAI 2026 (Poster)*. arXiv:2511.10037.
- Yao, S. et al. (2023). ReAct: Synergizing Reasoning and Acting in Language Models. *ICLR 2023*.
- Guo, Z. et al. (2024). StableToolBench: Towards Stable Large-Scale Benchmarking of Tool-Augmented LLMs. *arXiv:2403.07714*.
- 代码: [github.com/weixiaolong94-hub/Beyond-React](https://github.com/weixiaolong94-hub/Beyond-React)
