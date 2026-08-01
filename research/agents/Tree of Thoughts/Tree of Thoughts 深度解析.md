# Tree of Thoughts (ToT): Deliberate Problem Solving with Large Language Models

> 论文: Shunyu Yao, Dian Yu, Jeffrey Zhao, Izhak Shafran, Thomas L. Griffiths, Yuan Cao, Karthik Narasimhan — Princeton University / Google DeepMind
> 发表: NeurIPS 2023 (Oral) | 代码: [github.com/princeton-nlp/tree-of-thought-llm](https://github.com/princeton-nlp/tree-of-thought-llm)

---

## 1. 核心 Motivation

### Chain-of-Thought (CoT) 的根本局限

CoT 的本质是**从左到右的单链解码**。模型一旦写下某个 token，就不可逆转地"commit"了这条推理路径。论文在 Game of 24 上的分析发现：**约 60% 的 CoT 样本在生成第一个步骤（前三个 token）后就已经失败了**——比如写下 `4 + 9 = 13` 之后，整个链条就被带歪，没有回头路。

这是 CoT 的致命缺陷：**人类思考时会同时探索多条路径、评估、回溯、换方向**，但 CoT 做不到。

### ToT 的核心洞察

将 LLM 推理视为**在"思想单元"（thought）上的树搜索问题**——就像 AlphaGo 在围棋落子上做 MCTS 一样：

```
CoT:     A → B → C → D    （单链，错了无法挽回）

ToT:            A₁ → B₁ → C₁
              ↗   ↘
    Root → A₂   A₃ → B₂ → C₂    （多叉，评估+剪枝+回溯）
              ↘       ↘
            A₄ → B₃   B₄ (prune)
```

**ToT 不是一种"更好的 prompt"——它是一种将搜索算法嵌入 LLM 推理的系统架构。**

---

## 2. 整体架构

### 四个设计维度

ToT 为每个任务定制以下四个组件：

| 维度 | 选项 | 说明 |
|------|------|------|
| **Thought 分解** | 粒度可大可小 | Game of 24: 一行算式；Crosswords: 几个词；写作: 一整段计划 |
| **Thought 生成** | propose / sample | propose=顺序生成候选（空间有限时）；sample=i.i.d. 采样（空间丰富时） |
| **Thought 评估** | value / vote | value=独立对每个状态打分；vote=跨状态比较投票 |
| **搜索算法** | BFS / DFS | BFS=广度优先（适合浅树）；DFS=深度优先+回溯（适合深度不确定、需要回溯的任务） |

### 通用算法流程

```
输入: 问题 x, 最大深度 T, 候选数 k, beam 宽度 b

1. 初始化: 根节点 = x, 候选集 S₀ = {x}

2. for t = 1 to T:
     S'_t = {}  # 新候选集
     for s in S_{t-1}:  # 当前层的每个幸存状态
         # Step A: 生成 k 个候选 thought
         candidates = generate_thoughts(s, k)
         # Step B: 评估每个候选
         for c in candidates:
             c.value = evaluate(c, x)
         # Step C: 剪枝
         candidates = filter(candidates, threshold)
         S'_t.extend(candidates)
     # Step D: 保留 top-b（全局排序）
     S_t = top_b(S'_t)

3. 返回 S_T 中得分最高的完整路径
```

---

## 3. 三大任务的完整 Case

### 3.1 Game of 24（数学推理）

**任务**: 给定 4 个数字，用 + - × ÷ 凑出 24。测试集来自 4nums.com 困难题（#901-1000）。

#### 3.1.1 标准 IO Prompt（5-shot 对照基线）

```
Use numbers and basic arithmetic operations (+ - * /) to obtain 24.
Input: 4 4 6 8
Answer: (4 + 8) * (6 - 4) = 24
Input: 2 9 10 12
Answer: 2 * 12 * (10 - 9) = 24
Input: 4 9 10 13
Answer: (13 - 9) * (10 - 4) = 24
Input: 1 4 8 8
Answer: (8 / 4 + 1) * 8 = 24
Input: 5 5 5 9
Answer: 5 + 5 + 5 + 9 = 24
Input: {user_input}
```

#### 3.1.2 ToT Propose Prompt（1-shot，生成候选下一步）

```
Input: 2 8 8 14
Possible next steps:
2 + 8 = 10 (left: 8 10 14)
8 / 2 = 4 (left: 4 8 14)
14 + 2 = 16 (left: 8 8 16)
2 * 8 = 16 (left: 8 14 16)
8 - 2 = 6 (left: 6 8 14)
14 - 8 = 6 (left: 2 6 8)
14 / 2 = 7 (left: 7 8 8)
14 - 2 = 12 (left: 8 8 12)
Input: {current_numbers}
Possible next steps:
```

**设计选择**: 使用 `propose` 而非 `sample`，因为算式的搜索空间高度受限于 4 个数字的排列组合，不需要随机采样来增加多样性。

#### 3.1.3 ToT Value Prompt（5-shot，评估候选状态）

```
Evaluate if given numbers can reach 24 (sure/likely/impossible)
10 14
10 + 14 = 24
sure
11 12
11 + 12 = 23
12 - 11 = 1
11 * 12 = 132
11 / 12 = 0.91
impossible
4 4 10
4 + 4 + 10 = 8 + 10 = 18
4 * 10 - 4 = 40 - 4 = 36
(10 - 4) * 4 = 6 * 4 = 24
sure
4 9 11
9 + 11 + 4 = 20 + 4 = 24
sure
5 7 8
5 + 7 + 8 = 12 + 8 = 20
(8 - 5) * 7 = 3 * 7 = 21
I cannot obtain 24 now, but numbers are within a reasonable range
likely
5 6 6
5 + 6 + 6 = 17
(6 - 5) * 6 = 1 * 6 = 6
I cannot obtain 24 now, but numbers are within a reasonable range
likely
10 10 11
10 + 10 + 11 = 31
(11 - 10) * 10 = 10
10 10 10 are all too big
impossible
1 3 3
1 * 3 * 3 = 9
(1 + 3) * 3 = 12
1 3 3 are all too small
impossible
{remaining_numbers}
```

**评估机制**:
- 每个候选状态被评估 **3 次**，取多数票
- `sure` 和 `likely` 的状态保留，`impossible` 的状态被剪枝
- 论文发现，LLM 在判断"数字太大/太小无法到 24"上有良好的 commonsense

#### 3.1.4 案例: `4 9 10 13` 的 BFS 搜索全过程

**ToT 配置**: 深度 T=3，beam 宽度 b=5，每节点生成 k=3 个候选

```
初始状态: [4, 9, 10, 13]

═══════════════════════════════════════════
BFS 第 1 层 (深度=1): 从根节点生成 3 个候选第一步
═══════════════════════════════════════════
候选:
  ① 13 - 9 = 4  (left: 4, 4, 10)   → value: 3× sure    ← 保留
  ② 10 - 4 = 6  (left: 6, 9, 13)   → value: 2× maybe    ← 保留
  ③ 4 × 9 = 36  (left: 10, 13, 36)  → value: 3× impossible ← 剪枝!

评估依据 (候选③): "36, 10, 13 are all too big to reach 24"
保留 top-5 (此处简化为 top-2): ①, ②

═══════════════════════════════════════════
BFS 第 2 层 (深度=2): 从幸存状态扩展
═══════════════════════════════════════════
从状态 ① [4, 4, 10] 扩展:
  ④ 10 - 4 = 6     (left: 4, 6)   → value: 3× sure     ← 保留
  ⑤ 4 + 4 = 8      (left: 8, 10)  → value: 2× maybe     ← 保留

从状态 ② [6, 9, 13] 扩展:
  ⑥ 13 - 9 = 4    (left: 4, 6)    → value: 3× sure     ← 保留
  ⑦ 9 + 6 = 15    (left: 13, 15)  → value: 3× impossible ← 剪枝

评估依据 (候选⑦): "13, 15 can't make 24 with only one operation"
全域 top-5: ④, ⑥, ⑤

═══════════════════════════════════════════
BFS 第 3 层 (深度=3): 最后一步
═══════════════════════════════════════════
从状态 ④ [4, 6] 扩展:
  ⑧ 4 × 6 = 24    → 找到解！✓

输出: (13 - 9) × (10 - 4) = 24
      或等价: (10 - 4) × (13 - 9) = 24
```

**CoT 为什么在这个 case 上失败**: 论文发现 CoT 会在第一步 commit 到错误的方向（如 "4 + 9 = 13"），而一旦写下就无法撤销。ToT 的核心优势在于**第一步不 commit，同时保留多条通路**。

---

### 3.2 Creative Writing（创意写作）

**任务**: 给定 4 个随机句子作为结尾句，写一篇 4 段短文，每段以其中一个句子结尾。随机句子来自 randomwordgenerator.com。

**ToT 配置**: 深度=2（只有 1 个中间 thought = 写作计划），beam b=1，k=5

#### 3.2.1 输入: 4 个随机句子

> 1. *It isn't difficult to do a handstand if you just stand on your hands.*
> 2. *It caught him off guard that space smelled of seared steak.*
> 3. *When she didn't like a guy who was trying to pick her up, she started using sign language.*
> 4. *Each person who knows you has a different perception of who you are.*

#### 3.2.2 候选写作计划（k=5 i.i.d. 采样）

**Plan 1:**
> Introduce and explain the technique of doing a handstand. Switch to a story about an astronaut's first time in space. Describe a situation where a woman uses sign language to avoid unwanted attention. The final paragraph explains how everyone has different perceptions of others.

**Plan 2:**
> Introduction to an unusual self-help book, mentioning a handstand as a metaphor for embracing challenges. Discuss the unexpected things learned from astronauts, including the smell of space. Describe a woman's clever tactic for avoiding unwanted attention at a bar. Contemplate how different perceptions of oneself can shape one's identity.

**Plan 3:**
> Start with a physical education class teaching handstands as a lesson in perseverance. Transition to scientific facts about space that surprise people. Show a social interaction at a party where a woman cleverly communicates non-verbally. Reflect on how identity is multifaceted.

**Plan 4:**
> Open with a circus performer's daily routine and the simplicity of handstands. Move to a NASA engineer's anecdote about unexpected sensory experiences in space. Present a scene at a coffee shop where someone uses creative communication to deter an admirer. Close with philosophical musing on perception.

**Plan 5:**
> Begin with a motivational speaker using handstands as an example of overcoming fear. Interview an astronaut about small surprises of space travel. Narrate a personal story of a deaf woman navigating dating. Conclude with how everyone's view of you differs.

#### 3.2.3 Vote Prompt（跨状态比较投票）

```
Given an instruction and several choices, decide which choice
is most promising. Analyze each choice in detail, then conclude
in the last line 'The best choice is s', where s is the integer
id of the choice.
```

**实际投票输出 (5 次投票后取多数):**

> Choice 1, while incorporating the required end sentences, seems to lack a clear connection between the paragraphs. The transitions feel abrupt and the themes disjointed.
>
> Choice 2 offers an interesting perspective by using the required end sentences to present a self-help book's content. It connects the paragraphs with the theme of self-improvement and embracing challenges, making for a coherent passage. The astronaut and sign language anecdotes fit naturally within this framework.
>
> Choice 3 provides decent connections but the PE class framing feels forced and may not sustain reader interest.
>
> Choice 4 uses a circus theme that seems disconnected from the deeper philosophical messages in the later paragraphs.
>
> Choice 5 is reasonable but the motivational speaker format is somewhat cliché.
>
> **The best choice is 2.**

**结果**: Plan 2 胜出 → 基于 Plan 2 生成 5 篇完整文章 → 再次投票选最优 → 输出最终文章

#### 3.2.4 设计选择分析

| 设计维度 | 选择 | 原因 |
|---------|------|------|
| Thought 粒度 | 整段计划（而非逐句） | 写作需要全局规划，段落级的 thought 才有意义 |
| 生成方式 | `sample` (i.i.d.) | 写作计划的空间是开放的、丰富的，采样比顺序生成更有多样性 |
| 评估方式 | `vote` (跨状态) | 文章连贯性是主观的，不能像数字一样打绝对分数，需要比较判断 |
| 搜索算法 | BFS, b=1 | 写作不需要回溯——不需要同时走 3 条不同的写作计划到最后再选 |

---

### 3.3 Mini Crosswords（5×5 填字游戏）

**任务**: 给定 10 条线索（5 横 5 纵），填满 5×5 字母网格。测试集为 GooBix 的 20 个谜题。

#### 3.3.1 完整谜题（论文 Table 1）

| # | 方向 | 线索 | 答案 |
|---|------|------|------|
| h1 | 横向 | Presented; revealed | **SHOWN** |
| h2 | 横向 | An interjection expressing sorrow | **WIRRA** |
| h3 | 横向 | Benefit; result | **AVAIL** |
| h4 | 横向 | A cigarette | **RETTE** |
| h5 | 横向 | Chased up a tree | **TREED** |
| v1 | 纵向 | Swarthy; tawny | **SWART** |
| v2 | 纵向 | An apiarist or bee keeper | **HIVER** |
| v3 | 纵向 | To speak formally | **ORATE** |
| v4 | 纵向 | To indite; to scribble | **WRITE** |
| v5 | 纵向 | An insecticide | **NALED** |

**完成的 5×5 网格:**
```
S H O W N
W I R R A
A V A I L
R E T T E
T R E E D
```

#### 3.3.2 ToT Propose Prompt（生成候选词）

```
{current_board_state}

list all possible answers for unfilled or changed words,
and your confidence levels (certain/high/medium/low),
using the format 'h1. apple (medium)'.
Use 'certain' cautiously and only when you are 100% sure
this is the correct word.
```

**示例输出:**
```
h1. SHOWN (high)
v1. SWIFT (medium)
v1. SWART (low)
h3. AVAIL (certain)
...
```

#### 3.3.3 ToT Value Prompt（评估状态可行性）

判断给定线索 + 字母约束下是否还有合法单词。输出三档:

| 评级 | 含义 | 示例 |
|------|------|------|
| `sure` | 找到了匹配词 | `h3. Benefit: _ v _ _ l → AVAIL ✓ sure` |
| `maybe` | 没找到但约束足够松散 | `v1. Swarthy: s _ _ _ _ → maybe (有很多可能)` |
| `impossible` | 约束太紧不可能有解 | `An inn: _ d _ w f → impossible` |

**impossible → 立即剪枝该子树 + DFS 回溯到父节点尝试其他选项**

#### 3.3.4 DFS 搜索过程示意

```
根节点: 所有线索待填

Step 1: 填 h1=SHOWN (high)
    → 约束: v1=s____, v2=h____, v3=o____, v4=w____, v5=n____
    → 评估: 所有线索 still possible → 继续

Step 2: 填 v1=SWART (medium)
    → 约束: h2=w____ (叠加后)
    → 评估: h2 "An interjection" = w____ → sure (WIRRA) → 继续

Step 3: 填 h2=WIRRA (high)
    → 约束: v2=hi___ (前两个字母锁定!)
    → 评估: v2 "An apiarist" = hi___ → sure (HIVER) → 继续

Step 4: 填 v2=HIVER (certain) → ...

... (继续填满所有线索)

═══ 如果在某步出现 impossible ═══

Step N: 填 h4=RATIO (medium)
    → 交叉约束: v4 = _ i _ _ _
    → 评估: v4 "To indite" = w_i_e vs _i___ → 冲突! → impossible
    → 剪枝 + 回溯到 Step N-1，尝试 h4 的其他候选

Step N': 回溯后, 填 h4=RETTE (high)
    → 评估: 所有约束满足 → 继续
```

#### 3.3.5 为什么 Crosswords 用 DFS 而非 BFS

| 原因 | 说明 |
|------|------|
| 深度不固定 | 5-10 步，不像 Game of 24 固定 3 步 |
| 约束传播 | 填错一个词会导致连锁 impossible，需要立即回溯 |
| BFS 灾难 | 如果每层保留 b 个状态做广度搜索，组合爆炸无法控制 |
| DFS 高效 | 深度优先+及时剪枝 = 在约束最强的路径上快速试错 |

---

## 4. 实验结果

### 4.1 Game of 24

| 方法 | 成功率 |
|------|--------|
| IO prompt (标准 few-shot) | 7.3% |
| CoT prompt | 4.0% |
| CoT-SC (k=100, 自洽性) | 9.0% |
| IO + Refine (k=10) | 27% |
| IO (best of 100) | 33% |
| CoT (best of 100) | 49% |
| **ToT (b=1)** | **45%** |
| **ToT (b=5)** | **74%** |

**关键发现**:
- CoT 甚至不如标准 IO prompt（4.0% vs 7.3%）——因为 CoT 会自信地走上错误路径
- 即使 b=1（每层只保留最优），ToT 也达到 45%，远超 CoT 的 4%
- b=5 时 ToT 达到 74%，说明**保持多条候选路径本身就是价值**

### 4.2 Creative Writing

| 方法 | GPT-4 评分 (1-10) | 人工偏好胜率 |
|------|-------------------|-------------|
| IO (标准 prompt) | 6.19 | — |
| CoT | 6.93 | 21% |
| **ToT** | **7.56** | **41%** |
| ToT + iterative-refine | **7.91** | — |

**人工评估**: 100 对比较中，ToT 胜 41 次，CoT 胜 21 次，38 次平手。

### 4.3 Mini Crosswords

| 方法 | 词级成功率 | 字母级成功率 | 完全解出的游戏数 |
|------|-----------|-------------|----------------|
| IO | 14% | — | 0 / 20 |
| CoT | 15.6% | — | 1 / 20 |
| **ToT + DFS** | **60%** | **78%** | **4 / 20** |

**消融实验**（词级成功率）:

| 变体 | 成功率 | 损失 |
|------|--------|------|
| 完整 ToT + DFS | **60%** | — |
| ToT - 剪枝 (不做 impossible 判断) | 41.5% | -18.5 pp |
| ToT - 回溯 (纯贪心，不回头) | 20% | -40.0 pp |
| BFS 替代 DFS | ~20% | -40 pp |

剪枝和回溯各自贡献了 ~20-40 个百分点的提升，证明两者都是必要的。

---

## 5. 四个范式的对比分析

### 5.1 ToT vs CoT

| 维度 | CoT | ToT |
|------|-----|-----|
| 推理路径 | 单链，线性的 | 多叉树，可选择 |
| 纠错能力 | 无——错了就错了 | 有——评估 + 剪枝 + 回溯 |
| 决策哲学 | "想一步走一步" | "多想几步，保留最好的" |
| Token 消耗 | 1× | ~10-20× |
| 核心风险 | 第一步错全盘输 | 评估器不可靠时剪错枝 |
| 何时用 | 线性推理，路径基本唯一 | 组合搜索，需要探索+前瞻 |

### 5.2 ToT vs ReAct

| 维度 | ReAct | ToT |
|------|-------|-----|
| 信息流 | 推理→行动→**环境反馈**→推理 | 推理→评估→**自评分数**→扩展 |
| 反馈来源 | 外部环境 (ground truth) | LLM 自我评估 |
| 决策时域 | 在线，每步收到真实反馈 | 离线，事先规划完整路径 |
| 典型任务 | AlfWorld、Web 导航、工具调用 | 数学推理、谜题、写作规划 |
| 适用条件 | 环境能给出 reliable feedback | 中间状态可以通过 LLM 合理评估 |
| 核心风险 | 环境反馈有噪声或延迟 | LLM 自评不可靠（overconfident） |

**关键区分**: ReAct 需要环境告诉你"这一步对不对"；ToT 靠自己判断。所以环境可靠 → ReAct；自己能合理评估 → ToT。

### 5.3 ToT vs Reflexion

| 维度 | Reflexion | ToT |
|------|-----------|-----|
| 学习方式 | 跨 **Episode** 的反思积累 | 单次 **Episode 内**的多路径探索 |
| 记忆 | 持久的情节记忆（跨对局） | 无记忆（每次从零搜索） |
| 时间尺度 | 长期改进 | 即时优化 |
| 纠错粒度 | "上次我用了加法，不对，应该用乘法" | "这一步有 3 个选项，我同时保留 A 和 C" |
| 典型任务 | 编程、需要反复试错的任务 | 单次机会、必须一次做对的任务 |
| 核心风险 | 反思质量差导致错误固化 | 单次成本高 |

**关键区分**: ToT 解决"**这一次怎么做对**"；Reflexion 解决"**下一次怎么做得更好**"。两者正交——理论上可以在每次 ToT 尝试失败后，用 Reflexion 写反思存入记忆。

### 5.4 综合对比

```
              搜索时域
                 ↑
         跨Episode | Reflexion          | ToT + Reflexion
                 |                     |
         单Episode | CoT / ReAct        | ToT
                 |
                 +—————————————————————→ 路径数量
                  单链/反应式    多路径/搜索式
```

---

## 6. ToT 适合什么类型的问题？

### 必要条件（缺一不可）

#### 条件 ①: 中间状态可以定义和评估

这是 ToT 的**硬前提**。你必须能把问题分解成离散的 "thought" 单元，并且能判断某个 thought 的好坏。

- ✅ Game of 24: thought = 一个算式，评估 = 剩余数字能否到 24
- ✅ Crosswords: thought = 填入一个词，评估 = 剩余线索是否还有解
- ✅ 创意写作: thought = 写作计划，评估 = 计划是否连贯
- ❌ 开放对话: 什么是"中间状态"？怎么评估一段对话的中间步骤？
- ❌ 实时操作: 一个键鼠动作序列的"中间状态"难以定义

#### 条件 ②: 早期决策的质量对最终结果影响很大（不可逆性高）

如果每步相对独立、早期选择不影响后续，CoT 就够了，ToT 是浪费。

- ✅ Game of 24: 第一步算错，后面全错
- ✅ Crosswords: 填错一个词 = 交叉字母全错，约束传播不可逆
- ❌ 简单问答: "法国的首都是什么"——不需要搜索

#### 条件 ③: 搜索空间适中

| 空间大小 | 策略 |
|---------|------|
| 极小 (深度 1-2) | CoT 够了，ToT 浪费 |
| 适中 (深度 3-10, 分枝 < 20) | **ToT 最佳** |
| 巨大 (围棋、象棋) | LLM 评估不够，需要专用价值网络 + MCTS |

#### 条件 ④: 存在可验证的最终结果

- ✅ Game of 24: 算出来是不是 24，无歧义
- ✅ Crosswords: 网格是否一致，所有线索是否填满
- ⚠️ 创意写作: 主观评分，ToT 优势有限
- ❌ 完全开放、无评价标准: ToT 不知道该搜索什么

#### 条件 ⑤: 对延迟和成本的容忍度高

ToT 的 token 消耗是 CoT 的 10-20 倍。如果任务对延迟敏感（如实时游戏 AI），ToT 不适用。

### 判断流程图

```
问题需要多步推理？
  ├── 否 → CoT 或直接回答就够了
  └── 是 → 中间状态可以定义和评估吗？
            ├── 否 → ReAct（依赖环境反馈）或 Reflexion（依赖事后反思）
            └── 是 → 搜索空间大小？
                      ├── 巨大（围棋级）→ 需要专用 RL + MCTS, LLM 评估不够
                      ├── 很小 → CoT 单链就够, ToT 浪费
                      └── 适中 → 早期决策质量关键吗？
                                  ├── 否 → CoT-SC（多次采样投票）更经济
                                  └── 是 → 需要回溯/剪枝吗？
                                            ├── 否 → ToT + BFS
                                            └── 是（有约束传播）→ ToT + DFS
```

---

## 7. 对六朝项目的启示

### 7.1 适用场景映射

| 六朝决策场景 | 推荐范式 | 原因 |
|-------------|---------|------|
| **是否称帝** | **ToT** | 单步决策但后果深远；可枚举选项（称/不称）；可前瞻评估后果链 |
| **整回合军事路线规划** | **ToT + BFS** | 多步骤（调兵→行军→攻城）；中间状态可评估（兵力对比）；b=1-3 够用 |
| **迁都/重大建设选择** | **ToT** | 选项有限（几个候选城池）；可模拟后续几回合的收益/损失 |
| **根据对手行动动态响应** | ReAct | 需要环境反馈（对手实际出牌）；在线决策 |
| **随机事件响应（天灾等）** | CoT | 单步推理，路径基本唯一 |
| **跨对局的策略学习** | Reflexion | 长期记忆，从过去失败中总结 |
| **外交谈判多选项评估** | **ToT** | 可枚举候选方案；可评估各方案带来的联盟/敌对后果 |

### 7.2 实际操作建议

六朝的 AI 可以采用**分层策略**：

```
┌─────────────────────────────────────────┐
│ 战略层 (每局 2-5 次关键决策)              │
│ 称帝、迁都、重大战争宣战                  │
│ → ToT + BFS（花 token 买精度）            │
├─────────────────────────────────────────┤
│ 战术层 (每回合常规操作)                   │
│ 移动、小规模战斗、资源分配                │
│ → ReAct（在线响应，低成本）               │
├─────────────────────────────────────────┤
│ 元学习层 (跨对局)                         │
│ 对手建模、策略偏好记忆、失败模式总结      │
│ → Reflexion（持久记忆）                   │
└─────────────────────────────────────────┘
```

### 7.3 ToT 在六朝中的实现要点

1. **Thought 粒度**: 整回合的宏观计划为一组 thought（而非每个微操作为 thought）
2. **评估函数**: 需要设计六朝专用的价值评估 prompt——当前局面的得分、不同胜利条件的进度
3. **搜索深度**: 六朝的回合数远多于 ToT 的典型任务，需要限制前瞻深度（如前瞻 3 回合）
4. **剪枝策略**: 明显劣势的路径（如兵力悬殊的进攻）直接剪掉
5. **与其他方法的结合**: ToT 的搜索结果可以喂给 Reflexion 作为反思材料

---

## 8. 参考文献

- Yao, S., Yu, D., Zhao, J., Shafran, I., Griffiths, T. L., Cao, Y., & Narasimhan, K. (2023). Tree of Thoughts: Deliberate Problem Solving with Large Language Models. *NeurIPS 2023 (Oral)*. arXiv:2305.10601.
- 代码仓库: [github.com/princeton-nlp/tree-of-thought-llm](https://github.com/princeton-nlp/tree-of-thought-llm)
- Wei, J. et al. (2022). Chain-of-Thought Prompting Elicits Reasoning in Large Language Models. *NeurIPS 2022*.
- Yao, S. et al. (2023). ReAct: Synergizing Reasoning and Acting in Language Models. *ICLR 2023*.
- Shinn, N. et al. (2023). Reflexion: Language Agents with Verbal Reinforcement Learning. *NeurIPS 2023*.
- Wang, X. et al. (2023). Self-Consistency Improves Chain of Thought Reasoning in Language Models. *ICLR 2023*.
