# Reflexion: Language Agents with Verbal Reinforcement Learning — 深度解析

> 论文: Shinn et al. (2023), NeurIPS 2023
> arXiv: [2303.11366](https://arxiv.org/abs/2303.11366)
> 代码: [github.com/noahshinn024/reflexion](https://github.com/noahshinn024/reflexion)
> 本文基于论文原文整理，所有示例均来自论文 verbatim。

---

## 目录

1. [核心 Motivation](#1-核心-motivation)
2. [整体架构：三组件 + 双层记忆 + 迭代循环](#2-整体架构三组件--双层记忆--迭代循环)
3. [三个模型的输入分别是什么](#3-三个模型的输入分别是什么)
4. [论文中的完整示例](#4-论文中的完整示例)
5. [反思模式提炼](#5-反思模式提炼)
6. [实验表现](#6-实验表现)
7. [局限与讨论](#7-局限与讨论)

---

## 1. 核心 Motivation

### 困境：传统 RL 不适合大模型

2023 年初，ReAct 已经证明了 LLM 可以成为自主决策 Agent。但有一个关键问题悬而未决：

> **Agent 失败了怎么办？怎么让它从错误中学习、下次做得更好？**

传统的强化学习答案是**梯度下降 + 权重更新**。但这对于 LLM 来说极其昂贵：

- 需要海量训练样本（成千上万次交互）
- 需要昂贵的模型微调（反向传播 + GPU 集群）
- 每次策略更新都需要重新部署模型

论文原文直接指出：传统 RL 需要 **"substantial amounts of compute and time"** 和 **"extensive training samples and expensive model fine-tuning"**。

### 洞察：语言本身就是一种"梯度信号"

Reflexion 做了一个类比转移：

```
传统 RL：  标量奖励 (scalar reward) → 梯度信号 → 更新权重 → 改进行为
Reflexion：失败经验                  → 自然语言反思 → 存入记忆 → 下次作为 prompt 注入
                                          ↑
                                    "语义梯度信号"
```

**标量奖励**（`+1` 或 `-1`）只告诉你"好"或"不好"。

**自然语言反思**（"I should have looked for the desklamp first, then the mug"）包含了具体的错误定位、失败原因分析和明确的改进方向。

### 论文列出的四个显式优势

| 优势 | 含义 |
|------|------|
| **轻量 (Lightweight)** | 完全不需要微调 LLM |
| **细粒度反馈 (Nuanced feedback)** | 语言反思精确定位"哪一步错了、为什么错" |
| **可解释的情节记忆 (Explicit, interpretable episodic memory)** | 反思以可读文本形式存储，人类可直接理解和调试 |
| **直接指导未来行动 (Explicit hints for future actions)** | 反思文本注入后续 prompt，直接作为 in-context 的行动指南 |

---

## 2. 整体架构：三组件 + 双层记忆 + 迭代循环

### 架构图

```
┌─────────────────────────────────────────────────────────┐
│                    Reflexion 循环                        │
│                                                         │
│   任务输入                                               │
│     ↓                                                   │
│   ┌──────────────────────┐                              │
│   │  Actor (Mₐ)          │ ← 策略 π_θ(a|s, mem)         │
│   │  执行者 LLM           │   输入: task + obs + mem     │
│   └──────────┬───────────┘                              │
│              ↓ 轨迹 τ                                    │
│   ┌──────────────────────┐                              │
│   │  Evaluator (Mₑ)      │ → 奖励 r (标量/二值)          │
│   │  评估者（不一定是LLM） │   输入: τ                    │
│   └──────────┬───────────┘                              │
│              ↓ (τ, r)                                    │
│   ┌──────────────────────┐                              │
│   │  Self-Reflection(Mₛᵣ)│ → "语义梯度" sr               │
│   │  反思者 LLM            │   输入: τ + r + mem          │
│   └──────────┬───────────┘                              │
│              ↓                                           │
│   memory.append(sr)       ← 情节记忆缓冲区 (追加式)      │
│     ↓                                                   │
│   ┌─── 循环 ──────────────────────┐                     │
│   │  Actor 下次执行时，prompt 中    │                     │
│   │  注入所有历史反思               │                     │
│   └────────────────────────────────┘                     │
└─────────────────────────────────────────────────────────┘
```

### 三个组件

| 组件 | 一定是 LLM? | 输入 | 作用 |
|------|------------|------|------|
| **Actor** | ✅ 是 | task + 当前观测 + 历史反思 mem | 生成动作/文本 |
| **Evaluator** | ❌ 不一定 | 轨迹 τ | 判断成败 |
| **Self-Reflection** | ✅ 是 | τ + 成败信号 r + 前序反思 | 生成自然语言教训 |

### 双层记忆

```
┌─ 短期记忆（一个 episode 内）
│  当前轨迹的完整历史：
│  observation₁ → action₁ → observation₂ → action₂ → ...
│  作用：让 Actor 知道"现在发生了什么"
│
└─ 长期情节记忆（跨 episode）
   只存储反思文本，不存储完整轨迹：
   [sr₀, sr₁, sr₂, ...]
   通常限制最近 Ω = 1~3 条，以遵守 LLM 上下文窗口限制
   作用：让 Actor 知道"之前试过什么、为什么失败"
```

### 算法伪代码（论文 Algorithm 1 原文）

```
Initialize Actor, Evaluator, Self-Reflection: Mₐ, Mₑ, Mₛᵣ
Initialize policy π_θ(aᵢ|sᵢ), θ = {Mₐ, mem}
Generate initial trajectory τ₀ using π_θ
Evaluate τ₀ using Mₑ
Generate initial self-reflection sr₀ using Mₛᵣ
Set mem ← [sr₀]
Set t = 0

while Mₑ not pass or t < max_trials do
    Generate τₜ = [a₀, o₀, ... aᵢ, oᵢ] using π_θ
    Evaluate τₜ using Mₑ
    Generate self-reflection srₜ using Mₛᵣ
    Append srₜ to mem
    Increment t
end while
```

---

## 3. 三个模型的输入分别是什么

### Actor (Mₐ) 的输入

```
┌─────────────────────────────────────────┐
│ ① 任务描述 (task)                        │
│    "examine the mug with the desklamp"  │
│                                         │
│ ② 短期记忆（当前轨迹中的环境观测）         │
│    "On the desk 1, you see a mug 1..."  │
│                                         │
│ ③ 长期记忆 mem（历史反思文本）            │
│    sr₀: "上次失败因为先找mug..."          │
│    sr₁: "第二次失败因为..."               │
│                                         │
│ ④ 系统指令 (Actor prompt) + few-shot    │
└─────────────────────────────────────────┘
```

Actor 的 prompt 示例（编程任务，原文 Section C.2）：

> *"You are a Python writing assistant. You will be given your previous implementation of a function, a series of unit tests results, and your self-reflection on your previous implementation. Apply the necessary changes below by responding only with the improved body of the function. Do not include the signature in your response. The first line of your response should have 4 spaces of indentation so that it fits syntactically with the user provided signature."*

### Evaluator (Mₑ) 的输入

Evaluator 有三种形态，**不一定是 LLM**：

| 类型 | 输入 | 输出 | 是否 LLM |
|------|------|------|----------|
| **环境二值反馈** (AlfWorld/HotPotQA) | 轨迹 τₜ | `Status: Fail` / `Success` | ❌ 环境直接给 |
| **预定义启发式** (AlfWorld) | 轨迹中的动作序列 | 检测到幻觉/低效规划 | ❌ if 语句 |
| **LLM 自评** (编程) | 函数实现 + 自生成单元测试 | pass/fail | ✅ LLM |

AlfWorld 启发式的具体规则（原文 Section 4.1）：

> *"The heuristic is simple: if the agent executes the same action and receives the same response for more than 3 cycles, or if the number of actions taken in the current environment exceeds 30 (inefficient planning), we self-reflect."*

### Self-Reflection (Mₛᵣ) 的输入

Self-Reflection **一定是 LLM**。输入包含三样东西：

```
┌─────────────────────────────────────────┐
│ ① 奖励信号 rₜ (来自 Evaluator)            │
│    "Status: Fail" (二值)                 │
│                                         │
│ ② 当前轨迹 τₜ (完整历史)                  │
│    [a₀, o₀, a₁, o₁, ... aᵢ, oᵢ]        │
│    即 Actor 从开始到结束的完整执行过程     │
│                                         │
│ ③ 持久记忆 mem（之前累积的反思文本）       │
│    用于累积学习，避免重复犯同样的错误      │
└─────────────────────────────────────────┘
```

AlfWorld 反思 prompt（原文 Appendix A.1）：

> *"You will be given the history of a past experience in which you were placed in an environment and given a task to complete. You were unsuccessful in completing the task. Do not summarize your environment, but rather think about the strategy and path you took to attempt to complete the task. Devise a concise, new plan of action that accounts for your mistake with reference to specific actions that you should have taken. For example, if you tried A and B but forgot C, then devise a plan to achieve C with environment-specific actions. You will need this later when you are solving the same task. Give your plan after 'Plan'."*

---

## 4. 论文中的完整示例

### 4.1 AlfWorld 决策任务（论文 Figure 5）

**环境**：
> You are in the middle of a room. Looking quickly around you, you see a bed 1, a desk 2, a desk 1, a drawer 6, a drawer 5, a drawer 4, a drawer 3, a drawer 2, a drawer 1, a garbagecan 1, a laundryhamper 1, a safe 1, a shelf 6, a shelf 5, a shelf 4, a shelf 3, a shelf 2, and a shelf 1.

**任务**：`examine the mug with the desklamp.`

#### Trial #1（失败）

```
>think: To solve the task, I need to find and take a mug, then find and use a desklamp.
>think: First I need to find a mug. A mug is more likely to appear in drawer (1-6),
        desk (1-2), shelf (1-6), garbagecan (1), laundryhamper (1). I can check one
        by one, starting with drawer 1.
>go to drawer 1       → The drawer 1 is closed.
...（搜索了 drawer 1-6，都没有 mug）
>open drawer 6         → In it, you see a keychain 2.
>go to desk 1          → On the desk 1, you see a creditcard 3, a desklamp 1,
                         a laptop 2, a mug 1, a pen 1, and a pencil 1.
>think: Now I find a mug (1). Next, I need to take it.
>take mug 1 from desk 1 → You pick up the mug 1 from the desk 1.
>think: Now I take a mug (1). Next, I need to find a desklamp.
>go to desk 1          → Nothing happens.
>go to desk 2          → On the desk 2, you see a alarmclock 1, a bowl 1, ...
>think: Now I find a desklamp (1). Next, I need to use it.
>use desklamp 1        → Nothing happens.
>use desklamp 1        → Nothing happens.

Status: Fail
```

**反思（论文原文）**：
> *"In this environment, my plan was to find a mug then find and use a desklamp. However, the task says to examine the mug with the desklamp. I should have looked for the desklamp first, then looked for the mug. I noticed that the desklamp was found on desk 1. In the next trial, I will go to desk 1, find the lamp, then look for the mug and examine it with the desklamp."*

#### Trial #2（反思后成功）

```
>go to desk 1          → On the desk 1, you see a creditcard 3, a desklamp 1,
                         a laptop 2, a mug 1, a pen 1, and a pencil 1.
>think: To solve the task, I need to find and take a mug, then find and use a desklamp.
>take mug 1 from desk 1 → You pick up the mug 1 from the desk 1.
>use desklamp 1         → You turn on the desklamp 1.

Status: Success
```

**关键改进**：Trial 2 直接去 desk 1（利用了反思中的位置记忆），动作从 10+ 步缩减到 3 步（利用了反思中的顺序纠正）。

#### Few-shot 示例：`heat some mug and put it in coffeemachine`

**失败轨迹**：
```
>go to countertop 1  → On the countertop 1, you see a butterknife 1, a cup 1,
                       a fork 2, and a mug 1.
>take mug 1 from countertop 1 → You pick up the mug 1 from the countertop 1.
>go to stoveburner 1  → On the stoveburner 1, you see a pan 2.
>examine stoveburner 1 → On the stoveburner 1, you see a pan 2.
>examine stoveburner 1 → On the stoveburner 1, you see a pan 2.  ← 重复
>examine stoveburner 1 → On the stoveburner 1, you see a pan 2.  ← 重复
>examine stoveburner 1 → On the stoveburner 1, you see a pan 2.  ← 第4次！

Status: FAIL
```

**反思（论文原文）**：
> *"New plan: I was stuck in a loop in which I continually examined stoveburner 1 instead of heating mug 1 with stoveburner 1. I should have taken mug 1 from countertop 1, then heated it with stoveburner 1, then put it in coffeemachine 1. It did not help to execute two identical actions in a row. I will try to execute a different action if I am stuck in a loop again."*

---

### 4.2 HotPotQA 检索 + 推理（论文 Figure 7）

**问题**：
> Grown-Ups starred the actor who was best known for which role on "'Allo 'Allo!"?

#### Trial #1（失败）

```
Thought 1: I need to search Grown-Ups and "'Allo 'Allo!", find the actor who starred
           in Grown-Ups, then find the role he was best known for in "'Allo 'Allo!".
Action 1: Search[Grown-Ups]
Observation 1: Grown-Ups is a 1980 British BBC television film devised and directed
               by Mike Leigh. It stars Lesley Manville, Philip Davis, Brenda Blethyn,
               Janine Duvitski, Lindsay Duncan and Sam Kelly.

Thought 2: Grown-Ups starred Lesley Manville, Philip Davis, Brenda Blethyn, Janine
           Duvitski, Lindsay Duncan and Sam Kelly. I need to search "'Allo 'Allo!"
           and find which actor was best known for which role.
Action 2: Search["'Allo 'Allo!"]
Observation 2: Could not find ["'Allo 'Allo!"]. Similar: ["'Allo 'Allo!",
               "List of 'Allo 'Allo! characters", 'Gorden Kaye', ...]

Thought 3: To find the actor who was best known for which role on "'Allo 'Allo!",
           I can search Gorden Kaye.
Action 3: Search[Gorden Kaye]
Observation 3: Gordon Irving Kaye...was an English actor, best known for playing
               womanising café owner René Artois in 'Allo 'Allo!.

Thought 4: Gorden Kaye was best known for playing René Artois.
           So the answer is Rene Artois.
Action 4: Finish[Rene Artois]
Observation 4: Answer is INCORRECT
```

**反思（论文原文）**：
> *"I searched the wrong title for the show, "'Allo 'Allo!", which resulted in no results. I should have searched the show's main character, Gorden Kaye, to find the role he was best known for in the show."*

等等——反思说应该搜索 Gorden Kaye，但 Agent 确实搜索了 Gorden Kaye！真正的问题是：**Gorden Kaye 根本不在 Grown-Ups 的演员表中**（演员表里有 Sam Kelly）。反思虽然不完全准确，但它传递了一个正确的方向——**先确定哪个演员在 Grown-Ups 中，再查该演员在 'Allo 'Allo! 中的角色**。

#### Trial #2（正确）

```
Thought 1: I need to search the actor who was best known for a role on
           "'Allo 'Allo!" and find out what role they were best known for.
Action 1: Search[Grown-Ups]
Observation 1: ...stars Lesley Manville, Philip Davis, Brenda Blethyn,
               Janine Duvitski, Lindsay Duncan and Sam Kelly.

Thought 2: The paragraph does not mention the actor who was best known for a role
           on "'Allo 'Allo!". I need to search the actor's name instead.
Action 2: Search[Sam Kelly]
Observation 2: Sam Kelly...is best known for his roles as Captain Hans Geering
               in 'Allo 'Allo!, Warren in Porridge, ...

Thought 3: Sam Kelly is best known for his role as Captain Hans Geering in
           "'Allo 'Allo!", so the answer is Captain Hans Geering.
Action 3: Finish[Captain Hans Geering]
Observation 3: Answer is CORRECT
```

---

### 4.3 HotPotQA Chain-of-Thought + Reflexion（论文 Appendix D.2）

**问题**：
> What profession does John Lanchester and Alan Dean Foster have in common?

#### Trial #1（失败）

```
Thought 1: ...John Lanchester is a novelist, journalist, and critic. Alan Dean
           Foster is a novelist and screenwriter. So the profession they have
           in common is novelist and screenwriter.
Action 1: Finish[novelist and screenwriter]
Observation 1: Answer is INCORRECT
```

**反思（论文原文）**：
> *"My reasoning for the profession John Lanchester and Alan Dean Foster have in common failed because I incorrectly assumed that they both had the same profession. In the future, when attempting this question, I should focus on better researching the individual backgrounds of both authors to ensure that I am accurately identifying their professions. Additionally, I should consider the possibility that they may have multiple professions in common."*

#### Trial #2（正确）

```
Thought 1: ...John Lanchester is a novelist, journalist, and financial journalist.
           Alan Dean Foster is a novelist and screenwriter. So the profession they
           have in common is novelist.
Action 1: Finish[novelist]
Observation 1: Answer is CORRECT
```

**关键修正**：Trial 1 错误地声称共同职业是 "novelist **and screenwriter**"（实际上 screenwriter 不共享）。反思让 Agent 更严谨地逐个比较。

---

### 4.4 CoT (GT) + Reflexion 推理精确性（论文 Appendix D.3）

**问题**：
> What was a series of battles during the Revolutionary War, for control of New York City and the state of New Jersey, fought on October 28, 1776 near White Plains, New York?

**上下文已提供**：...The Battle of White Plains was a battle in the **New York and New Jersey campaign**...

#### Trial #1（失败）

```
Thought 1: ...this was the Battle of White Plains.
Action 1: Finish[Battle of White Plains]
Observation 1: Answer is INCORRECT
```

**反思（论文原文）**：
> *"Upon reflecting on the incorrect answer I provided, I realize that I may not have provided enough context to accurately answer the question. The question asked for a series of battles, but I only provided the name of one battle. To better answer this question in the future, I will make sure to provide more context, such as the name of the campaign, which was the New York and New Jersey campaign, and the fact that it was a series of battles."*

#### Trial #2（正确）

```
Thought 1: ...this series of battles was the New York and New Jersey campaign.
Action 1: Finish[The New York and New Jersey campaign]
Observation 1: Answer is CORRECT
```

**关键修正**：问题问的是 **"a series of battles"（一系列战役）**——即整个 campaign，而不是其中一场单独的 battle。反思精准识别了"颗粒度不匹配"错误。

---

### 4.5 HotPotQA 记忆消融实验（论文 Appendix D.4）

**问题**：
> Which of Jonny Craig and Pete Doherty has been a member of more bands?

#### Trial #1（失败）

```
Thought 1: Jonny Craig has been a member of six bands... Pete Doherty has been a
           member of seven bands... So Pete Doherty has been a member of more bands.
Action 1: Finish[Pete Doherty]
Observation 1: Answer is INCORRECT
```

**反思（论文原文）**：
> *"My reasoning for which musician has been a member of more bands failed because I did not take into account that Jonny Craig has been a member of more bands in the past, even though Pete Doherty is currently a member of more bands. In the future, when attempting this question, I should focus on researching the past and current bands of both musicians to ensure that I am accurately comparing their band memberships."*

#### Trial #2（正确）

```
Thought 1: I will research the past and current bands of both musicians... Jonny
           Craig has been a member of seven bands... Pete Doherty has been a member
           of seven bands... So Jonny Craig has been a member of more bands.
Action 2: Finish[Jonny Craig]
Observation 2: Answer is CORRECT
```

**关键修正**：反思的洞察是"不能只看当前活跃的乐队，要看历史记录"——Jonny Craig 历史总乐队数多于 Pete Doherty。

---

## 5. 反思模式提炼

从论文全部例子中可以提炼出四种核心反思模式：

| 模式 | 示例片段 | 错误类型 |
|------|---------|----------|
| **顺序纠正** | "I should have looked for the desklamp **first**, then looked for the mug" | 动词先后顺序弄反 |
| **搜索策略** | "I searched the **wrong title**... I should have searched the **actor's name**" | 搜索关键词选择错误 |
| **颗粒度匹配** | "The question asked for a **series of battles**, but I only provided **one battle**" | 回答粒度不对 |
| **假设纠正** | "I **incorrectly assumed** that they both had the **same profession**" | 过度推断 |

每个反思都遵循一个隐含结构模板：

```
1. 描述当时的计划
   "In this environment, my plan was to..."

2. 指出问题所在
   "However, the task says... / I was stuck in a loop..."

3. 断言应该怎么做（"I should have..."）
   "I should have looked for the desklamp first..."

4. 记录关键信息（如物品位置）
   "I noticed that the desklamp was found on desk 1."

5. 给出下一次的具体策略
   "In the next trial, I will go to desk 1, find the lamp..."
```

---

## 6. 实验表现

### 关键结果

| 任务 | 基线 | Reflexion | 提升 |
|------|------|-----------|------|
| **AlfWorld** (134 任务) | ReAct: ~63% | **97%** (130/134) | +22% (绝对值) |
| **HotPotQA** (ReAct) | ReAct: 39% | **51%** | +12% |
| **HotPotQA** (CoT GT) | CoT GT: 68% | **80%** | +12% |
| **HumanEval** (Python) | GPT-4: 80.1% | **91.0%** | +10.9% |
| **HumanEval** (Rust, 50 hardest) | GPT-4: 60.0% | **68.0%** | +8% |
| **LeetcodeHardGym** | GPT-4: 7.5% | **15.0%** | 2× |

### AlfWorld 失败分析（论文 Figure 3b）

ReAct 基线在 22% 的任务中出现**幻觉**（声称有某物品但实际没有），且**无法恢复**。Reflexion 通过反思几乎消除了这类错误——Agent 学会在反思中指出丢失物品的位置并修正后续计划。

### 消融实验（论文 Table 3，HumanEval Rust 50 hardest）

| 实验设置 | 自生成测试 | 自反思 | Pass@1 |
|---------|-----------|--------|--------|
| 基线 | ❌ | ❌ | 60% |
| 只用反思（无测试） | ❌ | ✅ | 52% ← 更差！ |
| 只用测试（无反思） | ✅ | ❌ | 60% ← 无改善 |
| **完整 Reflexion** | ✅ | ✅ | **68%** |

**关键洞察**：(1) 没有单元测试时，反思反而有害——Agent 无法判断实现是否正确；(2) 单元测试 + 反思**必须同时使用**才能产生增益。

---

## 7. 局限与讨论

### 论文明确指出的局限

1. **局部最优陷阱**：Reflexion 本质是策略优化，仍可能收敛到非最优的局部极小值
2. **记忆容量受限**：论文使用滑动窗口（最大 Ω=1~3 条），更大规模的结构化记忆（如向量数据库）有待探索
3. **依赖 LLM 自评能力**：反思的质量受限于 LLM 本身的自我评估能力，缺乏形式化保证
4. **不适用于需要大量探索的任务**：在 WebShop 实验中，Reflexion 未能改善性能——当搜索空间过于模糊时，反思无法提供有效指导
5. **编程的假阳性问题**：MBPP Python 上出现 16.3% 的假阳性率（测试通过但实现实际错误），导致 Agent 过早终止

### MBPP 反常表现

| Benchmark | GPT-4 Baseline | Reflexion | 差异 |
|-----------|---------------|-----------|------|
| HumanEval Python | 80% | **91%** | ✅ +11% |
| MBPP Python | 80% | **77%** | ❌ -3% |

原因：MBPP 的假阳性测试执行率高达 16.3%（HumanEval 仅 1.4%），意味着大量错误实现被内部测试误判为正确，Agent 提前退出。

### 论文引用信息

```
@article{shinn2023reflexion,
  title={Reflexion: Language Agents with Verbal Reinforcement Learning},
  author={Shinn, Noah and Cassano, Federico and Berman, Edward and
          Gopinath, Ashwin and Narasimhan, Karthik and Yao, Shunyu},
  journal={Advances in Neural Information Processing Systems (NeurIPS)},
  year={2023}
}
```
