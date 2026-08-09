# HexMachina 论文深度解析

> **论文**: "Agents of Change: Self-Evolving LLM Agents for Strategic Planning"
> **作者**: Nikolas Belle, Dakota Barnes, Alfonso Amayuelas, Ivan Bercovich, Xin Eric Wang, William Wang (UC Santa Barbara)
> **发表**: arXiv:2506.04651, 2025 年 6 月
> **解析日期**: 2026-08-06

---

## 一、核心问题：LLM Agent 的长线规划鸿沟

### 1.1 现有方法的致命缺陷

传统的 prompt-centric LLM Agent（ReAct、Reflexion 等）在长线策略游戏中存在根本性问题：

```
每回合流程：
  游戏状态(巨大文本) → LLM 推理 → 输出一个动作 → 下一回合状态(又是巨大文本) → ...
                         ↑
                    上下文窗口持续膨胀
                    策略一致性逐渐丧失
```

- **上下文窗口饱和**：每回合都要把完整游戏状态塞进 prompt，40-100 回合后上下文不堪重负
- **无持久记忆**：每回合都要重新"理解"环境，无法积累和复用知识
- **策略不一致**：前后回合的决策缺乏连贯性，全局战略无法贯彻

**实验结果**：Reflexion-style LLM Player（Claude 3.7 直接做 per-turn 决策）胜率仅 **16.4%**，几乎不具备竞争力。

#### 1.1.1 论文对"per-turn 推理为何失败"的论证评估

论文在这个问题上的论证**偏弱**——主要是定量结果 + 定性断言，缺乏细致的案例拆解。

**论文实际提供了什么：**

**① 定量对比（Table 2）—— 最有说服力的论据**

| 玩家 | 模型 | 胜率 | 胜利点 |
|------|------|------|--------|
| HexMachina (写代码) | GPT-5-mini | **54.1%** | 8.2±0.1 |
| **LLM Player (per-turn)** | **Claude 3.7** | **16.4%** | **5.2±1.2** |
| AlphaBeta (传统 AI) | - | 51.0% | 7.8±0.2 |
| Random | - | 0.2% | 2.4±0.0 |

LLM Player 仅比随机高出约 16 个百分点，这是论文最直接、最有力的论据。但胜率本身只告诉"结果不行"，不告诉"为什么不行"。

**② 定性描述 —— 只有一句话**

> "Asking the model to parse the full game state and independently choose every action while attempting to 'hold' a global plan proves unreliable and inconsistent."

论文没有展开说明"unreliable"和"inconsistent"的具体表现。

**③ 成本限制导致样本极小**

> "Due to inference cost (approx. 70 queries per game), we limited this evaluation to 20 games."

仅 20 局的样本量，置信区间宽达 [3%, 30%]，结论的统计显著性有限。

**④ 间接证据：No-Discovery FooPlayer 的策略退化**

附录 A.2 的代码是一个有说服力的间接案例——没有稳定 API 适配层时，演化收敛到了极其贫乏的策略：

```python
# No-Discovery 版本的 _evaluate_state —— 几乎只看 VP
score = float(vp)                         # 唯一真正的信号
if settlements:  score += 0.01 * settlements   # 极小的 tie-breaker
if cities:       score += 0.02 * cities
if roads:        score += 0.005 * roads
# 没有：生产力评估 / 阶段感知 / 资源多样性 / 对手建模 / rollout
```

而 HexMachina 版本有 600 行代码：阶段乘数矩阵、生产潜力计算、劫匪优化、对手响应模拟、浅层 rollout 等。

这间接说明：**当接口不稳定、信息获取困难时，策略会退化到最浅层的启发式**。per-turn LLM 面临类似困境——每回合从原始文本中重新提取结构化信息，认知负载过高。

**论文缺失的部分：**

| 缺失内容 | 重要性 | 说明 |
|----------|--------|------|
| LLM Player 的完整 prompt 模板 | 高 | 无法知道游戏状态如何格式化、system prompt 如何设定 |
| 具体回合的"翻车案例" | 高 | 没有展示"第 N 回合选 A，第 N+5 回合选矛盾 B"的实际日志 |
| 上下文窗口膨胀曲线 | 中 | 没有量化 prompt 长度随回合增长的趋势 |
| 多模型 per-turn 对比 | 中 | 仅测试了 Claude 3.7，不知道其他模型 per-turn 表现如何 |
| 与简单 heuristic 的对比 | 中 | 16.4% 到底是因为策略差，还是因为动作格式解析出错？ |

**总体评价**：论文通过"胜率 16.4% vs 54.1%"这一结果有力地证明了 per-turn 推理不行，但缺乏对**为什么不行**的机制性分析。对于想在六朝项目中验证此问题的研究者，建议自行设计对照实验：

```
实验组 A（per-turn）：每回合输入完整游戏状态 JSON/文本，LLM 直接输出动作
实验组 B（写代码） ：LLM 写 Python 策略模块，代码执行每回合决策
对照组 C（随机）  ：随机选合法动作
对照组 D（规则）  ：手写规则式 baseline

每组 100 局，记录：
  - 胜率 / 平均得分
  - per-turn 组的 prompt 长度增长曲线
  - per-turn 组的策略一致性指标（连续两回合选同类型动作的比例）
  - 每局平均 LLM API 调用次数和总 token 消耗
```

### 1.2 论文的核心洞察

> **把"思考"和"行动"分开**——让 LLM 做策略架构师（写代码），让编译后的代码做 per-turn 执行者。

```
HexMachina 的方式：
  LLM 写 Python 策略代码 → 编译执行 → 评估结果 → LLM 改进代码 → 再执行 → ...
       ↑                                                              |
       └──────────── 策略以代码形式持久化，不会丢失 ─────────────────┘
```

---

## 二、系统架构

### 2.1 两阶段设计

```
┌─────────────────────────────────────────────────────────────────┐
│                    HexMachina 架构                               │
│                                                                 │
│  ┌─────────────────────┐    ┌─────────────────────┐             │
│  │   Discovery Phase   │    │  Improvement Phase  │             │
│  │   (API 探索与适配)   │ → │  (策略演化与精炼)    │             │
│  │                     │    │                     │             │
│  │  所有 Agent 参与     │    │  仅 Orchestrator    │             │
│  │  Orchestrator       │    │  + Analyst          │             │
│  │  + Researcher       │    │  + Coder            │             │
│  │  + Strategist       │    │                     │             │
│  │  + Coder            │    │  输出: FooPlayer    │             │
│  │  + Analyst          │    │  (编译型策略模块)    │             │
│  │                     │    │                     │             │
│  │  输出: adapters.py  │    │                     │             │
│  │  (稳定的 API 适配层) │    │                     │             │
│  └─────────────────────┘    └─────────────────────┘             │
│                                                                 │
│  底层支撑: Experimentation Engine (确定性对局引擎)               │
│           Memory (游戏记忆 + 语义记忆)                           │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Agent 角色分工

| Agent | 职责 | 活跃阶段 | 工具 |
|-------|------|----------|------|
| **Orchestrator** | 全局规划，决定何时分析结果、请求新代码、回滚旧策略 | 全程 | 无（纯决策） |
| **Coder** | 将策略方案翻译为可编译的 Python 代码 | 全程 | Write/Edit file |
| **Analyst** | 赛后诊断，分析对局数据，指出具体问题 | 全程 | Read local file |
| **Researcher** | 探索 API/引擎事实，检索领域策略知识 | 仅 Discovery | Read file, Web search |
| **Strategist** | 提出具体可测试的策略方案 | 仅 Discovery | Read file, 查看历史实验, Web search |

每个 Agent 每轮最多调用 5 次工具，最终输出一条精简消息存入记忆。每条消息角色明确，输入输出标准化，支持不同模型互换。

### 2.3 关键的消融发现

| 配置 | 胜率 | 胜利点 |
|------|------|--------|
| 全部 Agent | 49.7% | 8.0 |
| 无 Analyst | **0.0%** | 2.1 |
| 无 Strategist + Researcher | **54.1%** | 8.2 |

**反直觉的发现**：在策略改进阶段，**砍掉 Strategist 和 Researcher 反而提升了性能**。原因：
- 额外的策略建议会**稀释策略的一致性**
- 减少角色交接 → 更清晰的策略翻译
- 精简化 pipeline = 更少的中间信息损耗

**但 Analyst 是必需的**：没有它，系统无法识别 `adapters.py` 中的函数引用错误，直接陷入失败循环。

### 2.4 实验引擎（Experimentation Engine）

```
固定种子 + 固定配置 → 重复对局 → 记录结果
                                    ↓
                              对比不同版本 FooPlayer
                              隔离策略改进 vs 随机噪声
```

关键特性：
- 确定性：同样种子 → 同样结果，可复现
- 隔离性：只改变 FooPlayer 代码，环境不变
- 可归因：胜率变化可追溯到具体代码修改

### 2.5 记忆系统

- **Game Memory**：存档历史玩家代码、评估结果、对局记录
- **Semantic Memory**：跨演化的知识积累（哪些策略有效、哪些失败）

---

## 三、两阶段详解

### 3.1 Discovery Phase（API 发现阶段）

**输入**：Catanatron API（无人类文档），只有原始代码库

**过程**：
1. Orchestrator 分配探索任务
2. Researcher 通过阅读源码、Web 搜索理解 API 结构和 Catan 领域知识
3. Strategist 基于 API 理解提出可测试的策略方案
4. Coder 在尝试中归纳出稳定的 API 调用模式
5. 所有角色共同"诱导"出一个 `adapters.py` 文件

**输出**：`adapters.py` —— 稳定、可复用的环境接口层，包含：
```python
# 关键封装函数示例
Game, Player, Color          # 核心类型
copy_game()                  # 游戏状态复制
execute_deterministic()      # 确定性执行动作
execute_spectrum()           # 概率展开（考虑骰子随机性）
list_prunned_actions()       # 获取剪枝后的合法动作列表
prune_robber_actions()       # 劫匪动作剪枝
base_fn()                    # 基础价值评估函数
value_production()           # 生产力价值评估
get_value_fn()               # 获取价值函数
```

**意义**：这个阶段确保后续策略改进建立在**可靠、可复用的 API 接口**之上，而不是每次都靠 LLM 猜测 API 用法。

### 3.2 Improvement Phase（策略改进阶段）

**输入**：`adapters.py` + 当前 `FooPlayer` + 历史对局数据

**主循环**（Orchestrator → Analyst → Coder）：
```
1. Orchestrator: "当前胜率 45%，Analyst 去分析为什么输"
2. Analyst: 读取对局日志 → "早期扩张太慢，对劫匪使用不够激进，城市升级时机偏晚"
3. Orchestrator: "Coder，根据 Analyst 的分析改进 FooPlayer"
4. Coder: 修改代码（增强早期 settlement bias、提高 robber 评分权重、优化城市触发条件）
5. 新 FooPlayer 打 30 场对局 → 胜率提升到 49%
6. 循环继续...
```

每次演化 10 步，每步 30 场对局。论文展示了从 30% 到超过 50% 的稳定提升曲线。

---

## 四、最佳 FooPlayer 的策略代码分析

论文附录 A.1 给出了 HexMachina 演化出的最强 FooPlayer（胜率 54.1%），约 600 行 Python 代码。以下是其核心设计：

### 4.1 游戏阶段感知（Phase Detection）

```python
EARLY_TURN_THRESHOLD = 20   # 回合数 < 20 → 早期
MID_TURN_THRESHOLD = 45     # 回合数 20-45 → 中期
                            # 回合数 > 45 → 后期

# 备选方案：根据最大胜利点判断
# max_vp < 4 → 早期, < 8 → 中期, >= 8 → 后期
```

### 4.2 阶段乘数矩阵

```python
MULTS = {
    "EARLY":  {"settlement": 2.0, "road": 1.8, "city": 0.8, "dev": 1.2},
    "MID":    {"settlement": 1.0, "road": 1.0, "city": 1.25, "dev": 1.0},
    "LATE":   {"settlement": 0.8, "road": 0.9, "city": 1.5, "dev": 1.0},
}
```

不同阶段对不同行动类型赋予不同的权重，实现战略重心转移。

### 4.3 启发式状态评估（_heuristic_value）

```
Score = VP × 100
      + settlements × 25 × settlement_mul
      + cities × 60 × city_mul
      + roads × 6 × road_mul
      + dev_vp × 50
      + resources_total × 1
      + resource_diversity × 3
      + city_resource_val × 5
      + production_potential × prod_weight (80/45/30 by phase)
```

关键设计：
- **生产力评估**：遍历玩家的 settlement/city，累加相邻地块的骰子概率 × 产出倍数
- **城市升级进度**：`min(wheat, ore)` 作为城市建造能力指标
- 结合 `adapters.base_fn()` 的评估值（0.85 权重）+ 自身启发式（0.15 权重）

### 4.4 动作预筛选（prefilter_actions）

为避免对所有合法动作做昂贵模拟，先筛选候选集合：

1. **Must-include tokens**：城市、定居点、道路、发展卡、骑士、劫匪、交易 → 强制纳入
2. **早期强制**：EARLY 阶段强制包含至少一个 settlement + road
3. **Top-K scoring**：用 `cheap_pre_score` 快速打分，取前 8 个
4. **随机补充**：不足 MAX_SIMULATIONS(24) 个时随机抽取

### 4.5 浅层 Rollout（rollout_value，深度 2）

```
对每个候选动作：
  1. execute_spectrum(game, action) → 概率化的后续状态分支
  2. 取最可能的分支
  3. 模拟对手的贪心响应（过滤掉劫匪/骑士类破坏性动作）
  4. 再执行我方一步最优动作
  5. 用 _evaluate_game_state 评估终局状态
  6. 综合 immediate(0.6) + rollout(0.4) 作为动作期望值
```

### 4.6 劫匪评估（evaluate_robber_action）

```python
ROBBER_BASE_SCORE_HIGH = 80.0     # 高基础分（激进策略）
PROD_LOSS_IMPORTANCE = 70.0       # 生产损失权重

# 评估逻辑：
for each target_hex:
    prod_loss = prob_of_hex × (opponent_settlements + 2 × opponent_cities)
    steal_expected = avg_resource_value × 0.5
# 选择使对手生产损失最大的地块
# 如果影响多个城市，额外加分
# 如果预期偷到高价值资源，再加分
```

### 4.7 最终决策（decide）

```
1. 获取 playable_actions → 预筛选 → 候选集 ≤ 24 个
2. 对每个候选执行 _evaluate_action_expectation (含 rollout)
3. 选最高分期望着（epsilon_greedy=4% 概率从 top-3 中随机选，避免可预测性）
4. 平局时按 settlement/road potential 打破平局
```

---

## 五、为什么 No-Discovery Baseline 失败

论文附录 A.2 给出了无 Discovery 阶段的 FooPlayer，暴露了根本缺陷：

| 维度 | No-Discovery FooPlayer | HexMachina FooPlayer |
|------|----------------------|---------------------|
| 前瞻深度 | 1-ply（只看即时后继状态） | 2-depth rollout + 对手建模 |
| 评估维度 | 几乎只看当前 VP | VP + 生产力 + 资源多样性 + 城市潜力 |
| 动作筛选 | 随机采样 12 个 | 智能预筛选 + must-include 保证 |
| 平局处理 | 完全随机 | 按 settlement/road potential 打破 |
| 阶段感知 | ❌ 无 | ✅ 早/中/晚 三阶段 |
| 劫匪策略 | ❌ 无 | ✅ 生产损失最大化 |
| 随机性建模 | ❌ 无 rollout | ✅ execute_spectrum 概率展开 |

**根本问题**：没有 Discovery 阶段 → adapters 不稳定 → FooPlayer 只能用最保守的方式调用 API → 无法实现复杂策略。

---

## 六、模型选择与消融

### 6.1 不同 Orchestrator 模型的表现

| Orchestrator 模型 | 胜率 | 胜利点 |
|-------------------|------|--------|
| GPT-5-mini | **54.1%** | 8.2±0.1 |
| Mistral-large | 49.2% | 7.8±0.2 |
| Claude 3.7 | 38.4% | 7.2±0.2 |

### 6.2 模型分工策略

论文采用**不同角色使用不同模型**的策略：

- **Orchestrator**：GPT-5-mini（需要最强推理）
- **Coder**：GPT-5-mini（代码生成精度关键）
- **Analyst / Strategist / Researcher**：Mistral-large（诊断性推理，降低成本）

### 6.3 实验成本

- 60 小时计算，两台机器（MacBook Pro 2019 16GB + MacBook M1 Max 32GB）
- 对局规模：每次演化 10 步 × 30 场 = 300 场；最终测试 10 轮 × 100 场 = 1000 场
- LLM Player（Reflexion 式）因推理成本限制仅评估 20 场

---

## 七、局限性与未来方向

### 7.1 论文自述局限

1. **粗粒度评估**：仅用胜率和最终 VP，可能掩盖细微的策略强弱差异
2. **代码幻觉**：LLM 偶尔生成幻觉代码，需要额外过滤
3. **推理成本高**：大量 API 调用限制了实验规模
4. **模型依赖性强**：性能与底层模型质量高度相关

### 7.2 未探索方向

- 扩展到 Catan 以外的持续学习 benchmark
- 超过 20 步的演化（受限于记忆管理）
- 3-4 人局的评估（论文仅做 2 人局）
- 更强的对手 baseline 构建

---

## 八、对六朝项目的启示

### 8.1 架构层面

| HexMachina 设计 | 六朝对应方案 |
|----------------|-------------|
| discovery phase → adapters.py | 先让 LLM 探索六朝游戏引擎 API，生成稳定的接口封装 |
| improvement phase → FooPlayer | LLM 写 Python 策略代码（不写 per-turn prompt） |
| Analyst 诊断 + Coder 实现 | 保留这两个核心角色 |
| 砍掉 Strategist/Researcher | 六朝可跳过这些角色，直接用精简 pipeline |

### 8.2 策略代码层面

HexMachina 最佳 FooPlayer 的做法可迁移到六朝：
- **阶段感知**：六朝有明确的朝代更替/时代推进，天然适合分阶段策略
- **启发式评分**：对棋盘状态做加权打分（资源、领地、军事、文化）
- **浅层 rollout**：模拟 2-3 步后的状态，而非无限深度搜索
- **动作预筛选**：用便宜的打分函数过滤候选动作
- **对手建模**：模拟对手的贪心响应

### 8.3 关键差异

| 维度 | Catan | 六朝 |
|------|-------|------|
| 玩家数 | 3-4（论文用 2） | 更多 |
| 随机性 | 骰子生产 | 骰子/卡牌/事件 |
| 隐藏信息 | 发展卡、手牌资源 | 手牌、意图 |
| 行动空间 | 中等 | 更大（多种行动类型） |
| 游戏时长 | 40-100 回合 | 可能更长 |

六朝的复杂度更高，HexMachina 的 **LLM 写策略代码** 路线比 **LLM per-turn 推理** 更有优势。

### 8.4 落地建议

1. **先做 Discovery**：让 LLM Agent 自主探索六朝游戏引擎，生成稳定的适配层
2. **精简 Agent 配置**：只用 Orchestrator + Analyst + Coder，不要过早引入多余角色
3. **策略以代码形式存在**：每次演化产出一个可执行的 Python 策略文件，可对比、可回滚
4. **确定性实验框架**：固定种子 + 固定对手，隔离随机性
5. **演化循环**：写代码 → 打对局 → 分析 → 改进代码，迭代 10-20 轮

---

## 九、关键引用

- HexMachina 论文: arXiv:2506.04651, June 2025
- Catanatron 框架: [github.com/bcollazo/catanatron](https://github.com/bcollazo/catanatron)
- 对比系统: Voyager (Wang et al., 2023), Eureka (Ma et al., 2024), AlphaEvolve (Novikov et al., 2025)

---

## 十、开源状态

### 10.1 HexMachina：已公开 ✅

**代码已通过项目网站公开发布。**

- 下载地址：[nbelle1.github.io/agents-of-change/](https://nbelle1.github.io/agents-of-change/)
- 已下载并分析，存放于 `projects/strategy-game-agents-main/`
- 论文 Section 9 的承诺已兑现：包含完整代码、实验框架、配置文件
- 代码结构清晰，包含 4 种 Evolver（promptEvolver / agentEvolver / agentEvolver_v2 / llmAgentEvolver）
- 还附带多轮演化运行的存档策略代码（best_gpt / best_claude / best_mistral + 演化快照）
- 详细代码分析见 [hexmachina_code_analysis.md](hexmachina_code_analysis.md)

### 10.2 开源组件（均随代码一同发布）

| 组件 | 说明 |
|------|------|
| **Catanatron** | 游戏引擎，随代码一起分发在 `catanatron/` 目录 |
| **LangChain / LangGraph** | 多 Agent 编排框架，通过 `requirements.txt` 安装 |
| **AlphaBeta 对手** | 包含在 `catanatron/catanatron_experimental/` 中 |
| **所有 Prompt** | `prompts.py` 完整公开了 700 行 System Prompt |
| **演化存档** | 多轮运行的完整策略代码快照 + 对局日志
