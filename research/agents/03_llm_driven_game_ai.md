# 方向三：LLM Agent 驱动游戏 AI — 代表性工作

> 调研日期: 2026-07-21
> 聚焦：用大语言模型作为游戏 AI 核心，驱动 NPC 行为、关卡探索、策略对抗和开放世界交互

---

## 概述

2023-2025 年见证了 LLM 驱动游戏 AI 的爆发式增长。与传统 RL 游戏 Agent（如 AlphaGo）不同，LLM 驱动的游戏 Agent 利用语言模型的世界知识和推理能力，在**无需专门训练**的情况下完成复杂的游戏任务。本节收录 **8 个代表性工作**。

### 应用全景

```
生成式 NPC (Generative Agents)
  → 开放世界探索 (Voyager / GITM / JARVIS-1)
    → 战术对抗 (PokéLLMon)
      → 通用计算机控制 (Cradle)
        → 多 Agent 协作博弈 (MindAgent / ProAgent)
          → 文档自学玩游戏 (SPRING)
```

---

## 1. Generative Agents: Interactive Simulacra of Human Behavior

| 维度 | 详情 |
|------|------|
| **发表时间** | 2023 年 4 月 |
| **会议** | UIST 2023 (ACM Symposium on User Interface Software and Technology) |
| **机构** | Stanford University / Google Research |
| **作者** | Joon Sung Park, Joseph C. O'Brien, Carrie J. Cai, Meredith Ringel Morris, Percy Liang, Michael S. Bernstein |
| **代码** | `github.com/joonspk-research/generative_agents` |

### 核心思想

创建 25 个 **由 LLM (ChatGPT API) 驱动的生成式 Agent**，放入一个名为 **Smallville** 的虚拟小镇。每个 Agent 只有一段简短的个人简介（姓名、年龄、职业、家庭、兴趣），其他所有行为（日常活动、社交、计划）都由 LLM 自主生成。

### 架构：三个核心组件

```
┌────────────────────────────────────────┐
│  Memory Stream (记忆流)                 │
│  - 以自然语言记录 Agent 的完整经历      │
│  - 检索模型：新近性 + 重要性 + 相关性   │
├────────────────────────────────────────┤
│  Reflection (反思)                      │
│  - 将记忆综合为高层次推论               │
│  - Agent 对自己和他人形成认知            │
├────────────────────────────────────────┤
│  Planning (规划)                        │
│  - 将反思 + 当前情境 → 高层次行动规划   │
│  - 递归分解为具体行为                   │
└────────────────────────────────────────┘
```

### 涌现行为（均非预编程）

| 现象 | 描述 |
|------|------|
| **信息传播** | Sam 决定竞选市长 → 小镇代理之间自然传播 |
| **关系记忆** | Agent 数天后引用之前对话的内容 |
| **派对协调** | Isabella 提议情人节派对 → Agent 自发传播邀请、约会、协调到场时间 |
| **日常安排** | Agent 自主生成每天的完整日程：起床、工作、社交、娱乐 |

### 关键发现

在评估中，众包评审认为**完整的生成式 Agent 架构比角色扮演同一角色的真实人类更"像人"**。消融实验证明：记忆、反思、规划三个组件**缺一不可**。

### 局限

- Agent 偶尔行为怪异（对家人说话过于正式、同时使用浴室、在酒吧吃午餐）
- 继承 LLM 的过于正式的语言风格
- 记忆检索有时遗漏相关信息

### 意义

这是**LLM 驱动游戏 NPC 的奠基性工作**。首次证明 LLM 可以驱动可信的、涌现社会行为的游戏 NPC，而不需要任何手写行为树。

---

## 2. Voyager: An Open-Ended Embodied Agent with Large Language Models

| 维度 | 详情 |
|------|------|
| **发表时间** | 2023 年 5 月 |
| **机构** | NVIDIA / Caltech / UT Austin / Stanford / ASU |
| **作者** | Guanzhi Wang, Yuqi Xie, Yunfan Jiang, Ajay Mandlekar, Chaowei Xiao, Yuke Zhu, Linxi (Jim) Fan, Anima Anandkumar |
| **代码** | `voyager.minedojo.org` |

### 核心思想

Voyager 是**首个 LLM 驱动的终身学习 Minecraft Agent**。它持续探索世界、获取新技能、做出新发现——完全无需人类干预。关键创新是：GPT-4 作为"大脑"，通过代码生成与环境交互，而非直接输出动作。

### 三大组件

```
┌───────────────────────────────────────────┐
│  1. Automatic Curriculum (自动课程)        │
│     - 根据当前技能水平 + 世界状态提议任务  │
│     - 最大化探索：从砍树到合成钻石         │
├───────────────────────────────────────────┤
│  2. Skill Library (技能库)                 │
│     - 可增长的代码仓库                      │
│     - 存储 + 检索复杂行为                  │
│     - 技能可以组合 (composition)            │
│     - 缓解灾难性遗忘                       │
├───────────────────────────────────────────┤
│  3. Iterative Prompting (迭代提示)         │
│     - 环境反馈 + 执行错误 → 程序改进       │
│     - Self-Verification (自验证)           │
│       ★ 移除自验证 → 物品发现率下降 73%    │
└───────────────────────────────────────────┘
```

### 关键成果

相比 MineDojo、ReAct、AutoGPT 基线：

| 指标 | 提升倍数 |
|------|----------|
| 发现独特物品数 | **3.3×** (63 种 / 160 轮) |
| 旅行距离 | **2.3×** |
| 解锁木器时代 | **15.3× 更快** |
| 解锁石器时代 | **8.5× 更快** |
| 解锁铁器时代 | **6.4× 更快** |
| 解锁钻石级别 | **唯一做到** |

### 零样本泛化

在新世界从零开始时，Voyager 可以利用技能库快速解决问题——体现了真正意义上的**学习**。

### 意义

Voyager 证明：LLM 可以通过"**写代码→执行→犯错→改进**"的循环，在复杂 3D 世界中实现终身学习。这对游戏 AI 的革命性在于：**不需要专门训练，Agent 就能理解新游戏并取得进展**。

---

## 3. Cradle: Towards General Computer Control

| 维度 | 详情 |
|------|------|
| **发表时间** | 2024 年 3 月 (ICML 2025 Poster) |
| **机构** | 北京智源人工智能研究院 (BAAI) / 南洋理工大学 / 北京大学 / 昆仑万维 |
| **代码** | `github.com/BAAI-Agents/Cradle` |

### 核心思想

Cradle 提出 **通用计算机控制 (General Computer Control, GCC)** 设定：Agent 通过**与人完全相同的接口**（截图作为输入，键盘鼠标操作作为输出）操控**任何软件**，包括 AAA 游戏、生产力软件和操作系统。

### 六模块架构

```
┌───────────────────────────────────────────┐
│  Information Gathering (信息收集)          │
│    从截图中提取文本 + 视觉信息             │
├───────────────────────────────────────────┤
│  Self-Reflection (自反思)                  │
│    检查过去动作是否成功，如何改进           │
├───────────────────────────────────────────┤
│  Task Inference (任务推断)                 │
│    决定是否需要调整当前目标                │
├───────────────────────────────────────────┤
│  Skill Curation (技能管理)                 │
│    生成 + 管理可复用的键鼠操作技能         │
├───────────────────────────────────────────┤
│  Action Planning (动作规划)                │
│    选择合适的技能并实例化为具体动作         │
├───────────────────────────────────────────┤
│  Memory (记忆)                             │
│    情节记忆 (历史信息) + 程序记忆 (技能)    │
└───────────────────────────────────────────┘
```

决策原则：**"反思过去、总结现在、规划未来"**。

### Red Dead Redemption 2 表现

Cradle 是**首个在 AAA 商业游戏中完成长时间主线任务的 AI Agent**：

- 跟随主线故事情节，完成 **40 分钟的真实任务**
- 开放世界探索：骑马、打猎、战斗、与 NPC 对话、使用物品、查看地图、商店购物
- 从游戏内教程和提示中**自主学习技能**，建立可复用技能库
- 通过自反思从错误中恢复

### 跨领域泛化

| 环境 | 表现 |
|------|------|
| Cities: Skylines | 建设 1000 人口的城市 |
| Stardew Valley | 清理农场、种植收获、购买种子 |
| Dealer's Life 2 | 与顾客讨价还价，周利润高达 87% |
| Chrome / Outlook / 飞书 | 完成办公任务 |
| 美图秀秀 / CapCut | 图片编辑、视频剪辑 |
| OSWorld 基准 | 超越使用真值标签的基线方法 |

### 意义

Cradle 实现了"**一个 Agent，操作所有软件**"的愿景。它不需要游戏的 API 接口或模型微调——完全通过视觉理解 + 键鼠操作与任何游戏/软件交互，是向通用游戏 AI 迈出的重要一步。

---

## 4. PokéLLMon: A Human-Parity Agent for Pokémon Battles

| 维度 | 详情 |
|------|------|
| **发表时间** | 2024 年 2 月 |
| **机构** | Georgia Institute of Technology |
| **作者** | Sihao Hu, Tiansheng Huang, Ling Liu |
| **代码** | `github.com/git-disl/PokeLLMon` |

### 核心思想

PokéLLMon 是**首个在战术对抗游戏中达到人类水平的 LLM Agent**。它通过阅读游戏状态文本描述，做出对战决策，并在 Pokémon Showdown 在线对战平台上与人类玩家实战。

### 三大策略

```
┌─────────────────────────────────────────────┐
│  1. In-Context RL (上下文强化学习)           │
│     实时文本反馈 (HP 变化、招式效果) 作为   │
│     "奖励信号"，在线调整策略                 │
│     例如：如果招式被对手特性无效化，立即切换 │
├─────────────────────────────────────────────┤
│  2. Knowledge-Augmented Generation (KAG)     │
│     检索外部 Pokédex 知识库                  │
│     类型克制关系、招式效果、特性描述          │
│     模拟人类玩家"查攻略"的行为               │
├─────────────────────────────────────────────┤
│  3. Consistent Action Generation             │
│     独立生成多个候选动作，投票选择最一致的    │
│     解决"恐慌换人 (panic switching)" 问题     │
│     面对强力对手时不再频繁无意义换人          │
└─────────────────────────────────────────────┘
```

### 关键成果

| 对战类型 | 胜率 |
|----------|------|
| Ladder (随机人类玩家) | **49%** |
| 邀请赛 (15 年经验老玩家) | **56%** |
| 对人类消耗战策略 | 18.75% (弱点) |

### 优势与弱点

- **优势**：凭借 KAG 策略，招式选择精准，可用单只 Pokémon 击穿对方全队。会使用"猛毒素 + 反复回复"的消耗战术。
- **弱点**：易受人类长期消耗策略影响，缺乏对对手**下一步行动**的预测能力。

### 意义

PokéLLMon 证明：**LLM Agent 可以在有竞争性的战术对抗游戏中达到人类水平**，且不需要任何游戏专用的 RL 训练。其 ICRL (In-Context RL) 策略提供了一种在推理时（而非训练时）进行策略调整的新范式。

---

## 5. JARVIS-1: Open-World Multi-Task Agents with Memory-Augmented Multimodal Models

| 维度 | 详情 |
|------|------|
| **发表时间** | 2023 年 11 月 |
| **机构** | 北京大学 / 多机构合作 |
| **环境** | Minecraft |

### 核心思想

JARVIS-1 是一个**记忆增强的多模态 Minecraft Agent**，可以在开放世界中完成多达 200+ 个多样化任务。关键创新是将**多模态感知**与**记忆增强规划**结合。

### 关键技术

- **多模态感知**：结合视觉信息和文本描述理解游戏状态
- **记忆增强**：存储过去的成功经验，在遇到类似情境时检索复用
- **任务分解**：将复杂目标分解为子任务序列
- **规划与重规划**：遇到失败时动态调整计划

### 意义

JARVIS-1 强调**记忆系统**在长时域游戏 Agent 中的核心作用——没有记忆的 Agent 每次都从零开始，效率极低。记忆增强使 Agent 能够累积经验、加速学习。

---

## 6. Ghost in the Minecraft (GITM)

| 维度 | 详情 |
|------|------|
| **发表时间** | 2023 年 2 月 |
| **机构** | 北京大学 |
| **环境** | Minecraft |

### 核心思想

GITM 是**首个能够稳健完成 70+ 个 Minecraft 任务的通用 Agent**。它使用基于文本的 LLM (GPT-3.5/GPT-4) 直接输出高层级计划，由底层控制器执行。

### 关键特性

- **层级化规划**：高层级目标 → 中层子任务 → 底层动作
- **结构化任务分解**：将复杂目标分解为有序的依赖树
- **错误恢复**：任务失败时自动回溯和重试
- **开放环境适应**：不需要特定任务的微调

### 与 Voyager 的对比

| 维度 | GITM | Voyager |
|------|------|---------|
| 任务覆盖 | 70+ 预定义任务 | 开放式探索 |
| 代码生成 | 不使用 | 核心机制 |
| 技能积累 | 无持久技能库 | 技能库持续增长 |
| 规划范式 | 层级分解 | 自动课程 + 技能检索 |

### 意义

GITM 和 Voyager 代表了 LLM 游戏 Agent 的两种不同范式：前者强调**通用任务覆盖**，后者强调**开放式终身学习**。两者共同定义了 Minecraft 作为 Agent 测试平台的价值。

---

## 7. MindAgent: Multi-Agent Cooperation Benchmark

| 维度 | 详情 |
|------|------|
| **发表时间** | 2023 年 |
| **环境** | Overcooked (烹饪协作游戏) / CUISINEWORLD |

### 核心思想

MindAgent 是一个**多 Agent 游戏协作基准**，评估两个或多个 LLM Agent 在游戏中协作达成共同目标的效率。与单 Agent 游戏不同，MindAgent 要求 Agent 具备**协作智能**：分工、沟通、动态任务调度。

### 评估维度

- 任务完成效率
- Agent 间的信息共享质量
- 动态环境下的适应性
- 协调失败的模式分析

### 意义

MindAgent 代表的**多 Agent 协作游戏测试**是 LLM Agent 评估的前沿方向。对六朝的多玩家博弈具有直接参考价值。

---

## 8. SPRING: Studying Papers and Reasoning to Play Games

| 维度 | 详情 |
|------|------|
| **发表时间** | 2024 年 |
| **作者** | Wu, Min 等 |

### 核心思想

SPRING 的核心思路极具启发性：**让 LLM Agent 阅读游戏文档/说明书，然后用推理能力玩游戏**——就像一个人类玩家先读说明书再玩游戏一样。不需要训练数据、不需要 API、不需要环境模拟器。

### 关键机制

- **文档理解**：从游戏规则书/论文中提取关键信息
- **结构化知识表示**：将文档转化为可查询的游戏知识库
- **推理驱动决策**：结合当前游戏状态和知识库进行推理和动作选择

### 意义

SPRING 代表了一个理想化的目标：**给定任何游戏的说明书，Agent 就能玩起来**。这比"为每个游戏训练专用模型"的路线更具扩展性。对六朝的启发：如果 AI 能"读懂"六朝的游戏规则，它就能自动生成合理的策略。

---

## 行业趋势：87% 的游戏开发者已经在使用 AI Agent

根据 Google 2024-2025 年对 615 名游戏开发者的调查：

| 指标 | 比例 |
|------|------|
| 认为 GenAI 正在改变行业 | **97%** |
| 已经使用 AI Agent | **87%** |
| 用于内容优化 | 44% |
| 用于动态游戏平衡 | 38% |
| 用于游戏内教练/教程 | 38% |

开发者最看好的未来方向：**动态世界变化 (23%)、学习型 NPC (23%)、个性化营销 (22%)、自动审核 (22%)**。

---

## 核心对比

| 系统 | 年份 | 游戏 | 范式 | LLM 角色 | 关键创新 |
|------|------|------|------|----------|----------|
| Generative Agents | 2023 | Smallville | NPC 行为生成 | 记忆+反思+规划 | 涌现社会行为 |
| Voyager | 2023 | Minecraft | 终身学习 | 代码生成+自验证 | 自动课程+技能库 |
| GITM | 2023 | Minecraft | 层级规划 | 文本规划 | 70+ 通用任务 |
| JARVIS-1 | 2023 | Minecraft | 记忆增强 | 多模态+记忆检索 | 200+ 任务记忆复用 |
| PokéLLMon | 2024 | Pokémon | 战术对抗 | In-Context RL+KAG | 人类水平对战 |
| Cradle | 2024 | RDR2/多游戏 | 通用计算机控制 | 截图→键鼠 | AAA 游戏通关 |
| SPRING | 2024 | 多游戏 | 文档理解 | 读说明书→玩 | 无需训练数据 |
| MindAgent | 2023 | Overcooked | 多 Agent 协作 | 分工+沟通 | 协作基准 |

---

## 与六朝项目的关联

六朝 (Six Dynasties) 是**回合制策略棋盘游戏**，LLM Agent 驱动的游戏 AI 在以下方面具有直接应用前景：

| 范式 | 在六朝中的应用场景 |
|------|-------------------|
| **Generative Agents 记忆架构** | AI 玩家维护"对手画像"：张某偏好军事扩张，李某保守等。跨回合、跨对局的持久记忆 |
| **Voyager 技能库** | 将有效策略存储为可复用的"策略模板"，在新对局中检索组合 |
| **PokéLLMon ICRL** | 每回合根据执行结果（攻城失败/外交被拒）进行 In-Context 策略调整 |
| **Cradle 视觉交互** | 如果六朝有图形界面，Agent 可直接通过截图理解局面，无需 API |
| **SPRING 规则理解** | 让 AI 阅读六朝规则书，自动理解游戏机制并生成策略 |
| **MindAgent 多 Agent** | 多个 AI 玩家之间的协作（组队）或对抗策略生成 |

### LLM vs. 传统 RL 的权衡

| 维度 | 传统 RL (AlphaZero) | LLM Agent |
|------|--------------------|------------|
| 需要训练 | 大量自对弈/训练 | 零样本/少样本 |
| 计算资源 | 训练时极高 | 推理时中等 |
| 策略可解释性 | 低 (黑盒) | 高 (自然语言推理) |
| 泛化到新游戏 | 需重新训练 | 读规则即可 |
| 延迟 | 低 (单次推理) | 较高 (多次 LLM 调用) |
| 策略最优性 | 可以达到最优/超人 | 接近人类但不一定最优 |

---

## 参考文献

- Park, J.S. et al. (2023). Generative Agents: Interactive Simulacra of Human Behavior. *UIST 2023*.
- Wang, G. et al. (2023). Voyager: An Open-Ended Embodied Agent with Large Language Models. *arXiv:2305.16291*.
- Wu, Y. et al. (2024). Cradle: Towards General Computer Control. *ICML 2025 Poster*. arXiv:2403.03186.
- Hu, S. et al. (2024). PokéLLMon: A Human-Parity Agent for Pokémon Battles with Large Language Models. *arXiv:2402.01118*.
- Wang, Z. et al. (2023). Ghost in the Minecraft: Generally Capable Agents for Open-World Environments via Large Language Models.
- JARVIS-1: Memory-Augmented Multimodal Agents for Open-World Multi-Task Completion. (2023).
- Wu, M. et al. (2024). SPRING: Studying Papers and Reasoning to Play Games.
- Hu, S. et al. (2024). A Survey on Large Language Model-Based Game Agents. *arXiv:2404.02039*.
- Xu, X. et al. (2024). A Survey on Game Playing Agents and Large Models. *arXiv:2403.10249*.
