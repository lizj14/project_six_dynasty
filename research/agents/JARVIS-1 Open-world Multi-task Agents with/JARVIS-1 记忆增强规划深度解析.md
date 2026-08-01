# JARVIS-1 记忆增强规划深度解析

> **论文**: JARVIS-1: Open-World Multi-task Agents with Memory-Augmented Multimodal Language Models
> **作者**: Zihao Wang, Shaofei Cai, Anji Liu et al. (PKU, UCLA, BUPT, BIGAI — Team CraftJarvis)
> **发表**: arXiv 2311.05997 (2023.11), 后发表于 IEEE TPAMI Vol.47 (2025)
> **项目页**: craftjarvis.org/JARVIS-1 | **代码**: github.com/CraftJarvis/JARVIS-1

---

## 一、核心定位：为什么需要记忆增强？

JARVIS-1 要解决的是一个本质问题：**在开放世界（Minecraft）中，Agent 面对的潜在任务数量是无限的，而且任务难度会随科技树攀升而急剧增长。** 传统的 LLM Planner（如 GPT + ReAct / DEPS）虽然能在短视距任务上表现不错，但有一个致命缺陷——**每次面对新任务都从零开始规划，无法利用过去的成功经验**。

JARVIS-1 的核心洞察是：Minecraft 的科技树具有**高度关联性**。比如 `ObtainDiamondPickaxe` 和 `ObtainDiamondAxe` 需要几乎完全相同的材料链。如果 Agent 已经学会了如何做钻石镐，这个经验理应能帮助它做钻石斧——但传统方法做不到这一点。

**记忆增强规划（Memory-Augmented Planning）** 就是 JARVIS-1 对这个问题的完整解答。

---

## 二、记忆增强规划：三层架构

JARVIS-1 的记忆增强规划不是简单地把历史塞进 prompt，而是一个精心设计的三层系统：

```
┌─────────────────────────────────────────────────────┐
│              记忆增强规划的完整流水线                  │
├─────────────────────────────────────────────────────┤
│  ① 查询生成 (Query Gen)                              │
│     任务 → 反向推理 → 识别所需子目标 → 多模态查询      │
│                         ↓                            │
│  ② 多模态检索 (Multimodal Retrieval)                  │
│     文本相似度初筛 → 视觉相似度排序 → Top-1 per sub-goal│
│                         ↓                            │
│  ③ 交互式规划 (Interactive Planning)                  │
│     检索经验作为 in-context demo → 生成计划           │
│     → Self-Check 主动验证 → Self-Explain 错误恢复     │
│                         ↓                            │
│  ④ 记忆写入 (Memory Storage)                         │
│     成功计划 + 任务 + 场景状态 → 存入记忆             │
└─────────────────────────────────────────────────────┘
```

### 2.1 多模态记忆的物理结构

每条记忆条目是一个三元组：

```
Memory Entry = {
    "task":      "obtain diamond pickaxe",     // 任务指令
    "situation": {                             // 规划时的场景
        "visual":  <MineCLIP embedding>,       // 视觉观测的嵌入向量
        "text":    "I can see oak trees in the plains biome. 
                    Inventory: 3 wooden planks, 2 sticks...",
        "biome":   "plains",
        "inventory_status": {...}
    },
    "plan": [g₁, g₂, ..., g_K]                // 成功的子目标序列
}
```

关键设计决策：
- **视觉信息不是存原始图像**，而是先通过 MineCLIP 提取关键词（如 "acacia tree", "sheep"），再用 GPT 生成描述句（如 "I can see sheep in the acacia plains"）。这比端到端图像描述**幻觉更少**。
- **文本部分用模板填充**：biome、inventory 状态等结构化信息通过固定模板转为文本，保证格式一致性。
- 论文中经过 4 个 epoch 的自主学习后，记忆库积累了 **425 条成功轨迹**。

### 2.2 检索增强规划 (RAG Formulation)

JARVIS-1 将记忆增强规划形式化为标准的 RAG 公式：

```
p(y|x) ≈ Σ_{z ∈ top-k(p(·|x))}  p_η(z|x) · p_θ(y|x,z)
```

其中：
- `x` = 任务指令 + 当前观测
- `y` = 生成的计划（子目标序列）
- `z` = 从记忆中检索到的参考经验
- `p_η` = 检索模型（MineCLIP 文本+视觉双塔）
- `p_θ` = 规划模型（MLM = MineCLIP + LLM 串联）

**与标准 RAG 的核心区别**：知识库不是静态的外部文档，而是 Agent **自己的交互历史**。这意味着记忆会随着游戏时间不断增长，且内容高度个性化。

### 2.3 查询生成：反向推理 + 多模态融合

这是记忆增强规划中最精巧的环节。给定一个新任务，JARVIS-1 不是简单地用任务描述去匹配记忆，而是先做**反向推理**。

#### 什么是反向推理？

反向推理（Backward Reasoning）就是从目标出发，**递归追问"这个东西的前置条件是什么"**，构建一棵从目标倒推到已知节点的依赖树。它与正向规划的方向完全相反：

```
正向规划（从当前状态出发）:              反向推理（从目标出发）:
  我现在有空手 + 面前有树                   我要合成附魔台
    ↓ 我能做什么？                           ↓ 附魔台需要什么？
  砍树 → 获得原木                           书 + 钻石 + 黑曜石
    ↓ 我能做什么？                           ↓ 书需要什么？
  合成木板 → 获得木板                       皮革 + 纸
    ↓ 我能做什么？                           ↓ 钻石需要什么工具挖？
  合成木棍 → ...                           钻石镐（铁镐也行）
    ↓ (一步一步往前推)                       ↓ 钻石镐需要什么？
  最终 → 附魔台                             3 钻石 + 2 木棍
                                            ↓ (继续往下追问...)
```

正向规划的问题是：**Minecraft 有上千种可合成物品，从当前状态出发有无数条可能路径，绝大部分通向死胡同。** 而反向推理每次只追问"当前这个目标的前置条件"，路径高度聚焦，不会在无关的可能性中迷失。

具体来说，JARVIS-1 的 MLM 执行反向推理时，每一层都在问同一个问题：

> *"要完成 [子目标 X]，我需要先完成哪些更小的子目标？"*

这个追问在三种情况下停止：
1. **记忆命中**：子目标在记忆库中已有成功经验（如 "obtain leather"）→ 加入查询键
2. **深度限制**：递归层数达到预设上限，避免无限展开
3. **原子任务**：子目标足够基础（如 "chop wood"），LLM 不需要额外经验也能规划

#### 完整案例：附魔台的反向推理过程

下面是具体的实现机制和完整案例。

##### 实现方式：Prompt 驱动的 LLM 推理，而非硬编码图搜索

反向推理不是 BFS/DFS 算法——JARVIS-1 **没有内置任何 Minecraft 配方数据库**。它完全通过 prompt 让 GPT 自行推理。论文 Figure 5 中可见核心 prompt 模板：

```
User: My current task is [craft 1 enchanting table], but I have never
accomplished this task before. What related tasks might be helpful for
me to complete [craft 1 enchanting table]?

Assistant:  ← GPT 在此输出反向推理的结果
```

GPT 收到这个 prompt 后，基于预训练时学到的 Minecraft Wiki 知识，自行输出附魔台的依赖树。整个过程是一轮 LLM 调用，不是多轮递归：

1. **单轮推理**：一次 LLM 调用完成整个反向分解，GPT 在单次生成中写出从附魔台到基础材料的完整依赖链
2. **深度限制**：prompt 中隐式或显式地限制了推理深度（"reasoning stops"），防止 GPT 无限展开到过于底层的细节
3. **记忆交叉比对**：GPT 输出分解结果后，系统将每个子目标与记忆库的 key 集合做**字符串匹配**（不是语义搜索），确定哪些命中、哪些未命中

```
LLM 推理输出:                      系统交叉比对记忆库:
  enchanting table                    (不在记忆中)
    ├── obsidian                      (不在记忆中) → 需要从零规划
    ├── diamond                       (在记忆中!)  → 加入查询键
    ├── book                          (不在记忆中) → 需要从零规划
    │   ├── leather                   (在记忆中!)  → 加入查询键
    │   └── paper                     (在记忆中!)  → 加入查询键
    └── diamond pickaxe               (不在记忆中) → 需要从零规划
        └── iron pickaxe              (在记忆中!)  → 加入查询键

最终 text query = {Diamond, Leather, Paper, Iron Pickaxe}
```

**关键设计**：记忆交叉比对用的是简单的 key 匹配，不涉及 embedding 或语义搜索。这是因为反向推理输出的子目标已经是标准化的任务描述（如 "obtain diamond"），而记忆条目的 task key 也是同格式——直接字符串匹配就足够精确。embedding 检索只在后续的多模态排序阶段才使用（见 2.3 节多模态检索部分）。

##### 为什么是单轮 LLM 调用而不是递归？

这与直觉相反——如果每层都递归调用 LLM，不仅 token 消耗爆炸，而且：
- GPT 在单次生成中完全有能力一次展开多层依赖（这是它擅长的结构化推理）
- 如果拆成多次调用，每轮都需要把上一轮的结果拼回 prompt，上下文越来越长
- 深度限制在单轮中更容易控制（prompt 中暗示 "reasoning stops" 即可）

##### 反向推理的天花板：LLM 的预训练知识边界

反向推理完全依赖 LLM 的预训练知识来构建依赖关系。如果 LLM 在预训练时没有接触过某个领域的语料，它根本不知道 "附魔台需要黑曜石"，反向推理就会从第一步开始就输出错误。

论文 Figure 6 直接验证了这一点——**这是 JARVIS-1 论文中最被低估的一张图**：

| 模型 + 任务 | WoodenPickaxe | StonePickaxe | IronPickaxe | **Diamond** |
|---|---|---|---|---|
| GPT-4 | 96% | 95% | 55% | **9%** |
| ChatGPT | 95% | 90% | 50% | **5%** |
| LLaMA2-70B (预训练) | 90% | 35% | 5% | **0%** |
| LLaMA2-13B (微调后) | 85% | 75% | 25% | **5%** |

LLaMA2-70B 预训练版在 Diamond 任务上成功率为 **0%**——一个比它小 5 倍的微调版模型反而能做到 5%。为什么？因为 **LLaMA2 的预训练语料中 Minecraft 相关内容严重不足**，它根本不知道钻石需要铁镐才能挖掘、钻石通常在 y<16 的深度生成。反向推理的第一步就错了，后续的记忆检索完全无法挽救。

更有意思的对比：LLaMA2-13B **微调后**在 StonePickaxe 上从 35% 跳到 75%，在 IronPickaxe 上从 5% 跳到 25%。微调注入的正是**领域知识**——说明反向推理能力的瓶颈本质上是知识瓶颈，不是推理能力瓶颈。

##### JARVIS-1 本身做训练吗？不做。

这是 JARVIS-1 与 VPT（需要 RL fine-tune 140 万 episode）最根本的区别。JARVIS-1 的设计哲学是：

```
传统路线:  预训练模型 → 领域 fine-tune → 部署
JARVIS-1:  预训练模型 → 记忆积累（in-context）→ 部署
                ↑
          不需要梯度更新
```

论文中反复强调了这一点：

> *"no additional model update is needed as the MLM in JARVIS-1 makes it possible to leverage these experiences in an in-context manner."*
> *"there is no gradient update in this thanks to the memory-augmented MLM, i.e. we can do in-context life-long learning."*

JARVIS-1 使用的 GPT-4/ChatGPT 是 **off-the-shelf 的，没有经过任何 fine-tune**。所有的"学习"都发生在记忆库层面——新的成功经验被写入 JSON，被检索到的概率增加，plan 质量因此提升。模型权重自始至终没有变化。

唯一的训练相关实验就是上面提到的 LLaMA2 微调（Figure 6），但那是一个**消融实验**，目的是回答"如果基座模型缺乏领域知识，能否通过微调弥补"。这不是 JARVIS-1 的主体设计——主体设计是假设基座模型已经有足够的领域知识，JARVIS-1 负责补充"执行经验"。

##### 双层知识架构：预训练知识（what）+ 记忆经验（how）

这引出了 JARVIS-1 最核心的设计决策——一个严格分层的知识架构：

```
Layer 1: 预训练知识（LLM 权重，只读）
  ├── 来源: 预训练语料（Wikipedia, Minecraft Wiki, 论坛...）
  ├── 内容: 物品配方、属性关系、游戏机制
  ├── 作用: 反向推理时拆解任务树
  ├── 更新: 不可更新（除非换模型或 fine-tune）
  └── 风险: 语料缺失 → 反向推理从根上错误

Layer 2: 执行经验（多模态记忆库，读写）
  ├── 来源: Agent 自身交互历史
  ├── 内容: 具体场景 + 成功计划
  ├── 作用: 为 Planner 提供 in-context reference
  ├── 更新: 每次成功执行后写入，持续增长
  └── 风险: 记忆不足时退化为纯 LLM Planner（≈ DEPS 水平）
```

这意味着：
- **Layer 1 是 Layer 2 的前提**：LLM 首先必须知道 "diamond 需要 iron pickaxe"，才能把 "obtain diamond" 拆出来作为子目标去记忆库检索
- **Layer 2 是 Layer 1 的放大器**：即使 LLM 知道配方，没有执行经验的 Planner（DEPS）在 Diamond 任务上也只有 ~2.4% 成功率；加上记忆后 JARVIS-1 达到 ~9%，记忆越大越高
- **两者缺一不可**：LLaMA2-70B（有记忆但没知识）= 0%；DEPS（有知识但没记忆）= 2.4%；JARVIS-1（有知识+有记忆）= 9-12.5%





```
任务: "craft 1 enchanting table with empty inventory"

Step 1 — 反向推理（MLM 执行，有深度限制）:
  enchanting table
    ├── obsidian        ← 在记忆中? NO  → 需要从零规划
    ├── diamond         ← 在记忆中? YES → 作为查询键
    ├── book            ← 在记忆中? NO  → 需要从零规划
    │   ├── leather     ← 在记忆中? YES → 作为查询键
    │   └── paper       ← 在记忆中? YES → 作为查询键
    └── diamond pickaxe ← 在记忆中? NO  → 需要从零规划
        └── iron pickaxe ← 在记忆中? YES → 作为查询键

Step 2 — 构造多模态查询:
  text query  = {Diamond, Leather, Paper, Iron Pickaxe}
  visual query = <当前画面中看到的橡树林、平原生物群系>

Step 3 — 两阶段检索:
  (a) 文本编码器计算 query 与所有 memory entries 的 task key 相似度
      → 筛选超过置信阈值的候选项
  (b) 视觉编码器 (MineCLIP) 计算 query visual state 与候选 entry visual state 的余弦相似度
      → 排序，每个子目标只取 Top-1
```

**关键问题：附魔台 → obsidian/diamond/book 这个知识从哪来？**

答案是 **GPT 自身的预训练知识，不是记忆库**。附魔台的合成配方（1 书 + 2 钻石 + 4 黑曜石）是 Minecraft Wiki 等公开语料中的常识，GPT 在预训练时已经学到了。JARVIS-1 的反向推理只是在"回忆" LLM 内部已有的配方知识，然后对每个子目标去记忆库中查"我有没有做过类似的事"。

这揭示了 JARVIS-1 架构的一个核心分工：

```
LLM 预训练知识  →  "要什么"（what）—— 合成配方、物品关系、科技树结构
多模态记忆库    →  "怎么做"（how）—— 具体在什么场景下、按什么步骤执行成功过
```

两者的结合方式：**LLM 先用自身知识拆解任务树，然后用记忆库为树的每个节点填充可执行的经验参考。** 对于那些 LLM 本身就不熟悉的冷门物品（如 LLaMA2 缺乏 Minecraft 知识，见 Figure 6），即使记忆再强也无从拆解——所以 LLM 基座的领域知识是硬前提。

**这个设计的精妙之处**：
- **反向推理避免了暴力匹配**：不是在整个记忆库中搜索 "enchanting table"（可能一条都没有），而是利用 LLM 的配方知识分解为已有经验的子目标
- **LLM 知识 + 记忆经验互补**：LLM 知道"钻石镐需要 3 钻石 + 2 木棍"，但不知道"在平原 biome、周围有橡树的具体情况下，怎么高效获取这些材料"——这正是记忆提供的东西
- **视觉条件增强了场景适配**：两个记忆条目即使任务相同，在不同的 biome 和视觉环境下执行方式可能完全不同。CLIP 排序确保了检索到的经验与当前场景最匹配
- **深度限制保证了效率**：无限反向推理会退化为穷举，深度限制在工程上很必要

### 2.4 交互式规划：Self-Check + Self-Explain

检索到参考经验后，JARVIS-1 将其作为 in-context demonstration 注入 MLM Planner 的 prompt。但这只是起点——规划过程本身是**交互式**的，包含两个互补机制：

#### Self-Check（主动验证）

在计划执行**之前**，MLM 逐步模拟每个子目标的执行，预测每一步后的库存状态，验证是否满足后续子目标的前置条件。

```
论文 Figure 4 的具体案例：

任务: Obtain a diamond in Minecraft

原始计划 (有 bug):
  3 wood planks → 3 sticks → 1 wooden pickaxe → 1 stone pickaxe
  → 1 furnace → 3 iron ingots → 1 iron pickaxe → ... → 1 diamond

Self-Check 模拟执行过程:
  在模拟 "craft sticks from planks" 这一步时发现:
  
  "3 wood planks are not enough (lack of 2 sticks).
   So I need craft more planks from log.
   More planks require more log.
   So I need to mine more log."

修正后的计划:
  3 logs → 12 planks → 4 sticks → 1 wooden pickaxe
  → 1 stone pickaxe → 1 furnace → 4 logs → 16 planks
  → 8 sticks → 1 iron pickaxe → ... → 1 diamond
  (数量和中间步骤都被修正)
```

这个案例展示了 Self-Check 的实用价值：在真实 Minecraft 中，如果 Agent 挖到地下才发现木材不够，必须返回地表——这在时间限制下通常是致命的。**提前发现并修复计划缺陷，避免了危险的运行时恢复。**

#### Self-Explain（错误恢复）

当计划执行中仍然发生失败，Self-Explain 利用环境反馈进行闭环重规划：

```
论文 Figure 4 的具体案例：

执行过程中子目标失败: "mine cobblestone"

环境多模态反馈:
  "I failed on mining cobblestone.
   My current state is: wooden pickaxe is broken;
   I still have 2 sticks in the inventory. My position is..."

Self-Explain 错误解释:
  "Because mining cobblestone needs a stone pickaxe,
   which I do not have in the inventory.
   Crafting a stone pickaxe needs 2 sticks and 3 cobblestones.
   But I don't have cobblestones yet — I need to mine them with a wooden pickaxe.
   The wooden pickaxe is broken — so I need to craft a new one first."

重新规划:
  1. craft 1 wooden pickaxe (用已有的 2 sticks + 新挖的 3 planks)
  2. mine 3 cobblestone with wooden pickaxe
  3. craft 1 stone pickaxe (2 sticks + 3 cobblestone)
  4. continue mining cobblestone with stone pickaxe
  ... → 继续原始任务
```

**Self-Check 和 Self-Explain 形成互补**：一个在事前防患于未然，一个在事后快速恢复。论文的数据表明，JARVIS-1 通常只需 **2-3 轮重规划**即可生成正确计划，而 DEPS（无记忆）需要 **6+ 轮**。

---

## 三、终身学习：记忆从哪来，如何自我进化？

### 3.1 Self-Instruct：自主课程生成

记忆不是手工构建的，而是 Agent 通过 **Self-Instruct** 自主探索积累的。过程如下：

```
每个 round:
  1. MLM 评估 Agent 当前的能力水平
  2. 从一个大型任务池中选择适合当前能力的任务
  3. Agent 尝试执行这些任务
  4. 成功经验和失败经验都存入记忆
  5. 进入下一轮，任务难度自然递增

观察结果: 生成的课程几乎完全遵循 Minecraft 科技树的成长方向
  (Wood → Stone → Iron → Gold → Diamond)
```

### 3.2 分布式经验收集

为了加速学习，JARVIS-1 采用分布式架构：

- **多个 JARVIS-1 实例**在各自独立的 Minecraft 环境中并行运行
- 所有实例**共享同一个中央多模态记忆**
- 一个实例的成功经验可以被所有其他实例检索使用
- 论文称之为 "speculative execution" 策略

### 3.3 记忆规模增长与性能提升

论文 Figure 7 展示了最直接的证据——**随着记忆从 0 增长到 425 条轨迹，关键物品的获取成功率持续上升**：

| 物品 | Epoch 0 (无记忆) | Epoch 1 | Epoch 2 | Epoch 3 | Epoch 4 (425 条) |
|------|:---:|:---:|:---:|:---:|:---:|
| Stone Pickaxe | ~85% | ~90% | ~92% | ~94% | **~95%** |
| Iron Pickaxe | ~25% | ~40% | ~45% | ~50% | **~55%** |
| Diamond | ~5% | ~10% | ~15% | ~20% | **~24%** |

**关键发现**：越难的任务（如 Diamond），记忆带来的提升越大。因为难任务的子目标更多，可以复用的经验也更多。

---

## 四、消融实验：记忆各组件的贡献

论文 Figure 8 对比了三种检索方式的性能：

```
baseline (无记忆):                 ████░░░░░░  极低
Text Memory (仅文本嵌入匹配):      ██████░░░░  中等
Text Memory + Reasoning (文本+推理): ████████░░  较好
Multimodal Memory + Reasoning (多模态+推理): ██████████  最优
```

结论：
1. **纯文本记忆优于无记忆**：说明即使是最简单的经验复用也有显著收益
2. **推理先于检索优于直接检索**：反向推理分解子目标大幅提升了检索精度
3. **多模态优于纯文本**：视觉场景信息帮助筛选出与当前环境最匹配的经验

### Why LLM Matters

论文还对比了不同 LLM 基座的表现（Figure 6）：

| 模型 | CraftingTable | WoodenPickaxe | StonePickaxe | IronPickaxe | Diamond |
|------|:---:|:---:|:---:|:---:|:---:|
| GPT-4 | 97% | 96% | 95% | 55% | 9% |
| ChatGPT | 95% | 95% | 90% | 50% | 5% |
| LLaMA2-70B (预训练) | 94% | 90% | 35% | 5% | 0% |
| LLaMA2-13B (微调后) | 85% | 85% | 75% | 25% | 5% |

结论：**记忆增强对 LLM 本身的知识有补偿效应**。ChatGPT 尽管参数少于 GPT-4，在配备记忆后表现接近；开源模型 LLaMA2 缺乏 Minecraft 知识，但微调后可接近 ChatGPT 水平。

---

## 五、记忆增强规划的效果：ObtainDiamondPickaxe

这是 Minecraft AI 的经典终极测试，需要完成 20+ 个子目标。论文 Figure 9 展示了完整的对比：

| 方法 | 成功率 (20 min) | 成功率 (60 min) |
|------|:---:|:---:|
| VPT (RL fine-tuned) | 2.5% | 3.0% |
| DEPS (无记忆 LLM) | ~0.6% | — |
| **JARVIS-1** | **6.2%** | **12.5%** |
| 熟练人类玩家 (10 min) | ~12% | — |

对比中特别值得注意的是 **VPT 的时间延长几乎不提升成功率**（2.5%→3.0%）。原因是 VPT 在镐子损坏后会做出困惑行为（用错误的工具挖矿、合成不必要的物品）。而 JARVIS-1 的 Self-Explain 机制能在镐子损坏时**基于库存状态动态重新规划**，合成新镐子继续任务。

右侧曲线还显示：随着游戏时间增加，**所有中间里程碑物品的获取成功率都在提升**——JARVIS-1 确实在"持续提升技能"。

---

## 六、核心设计理念总结

### 为什么记忆增强规划有效？

1. **经验的 in-context 复用避免了梯度更新**：大模型不需要 fine-tune，只需要在 prompt 中看到相关的成功案例，就能产生更好的计划。这对大型基座模型极其重要。

2. **反向推理 + 子目标匹配实现了跨任务泛化**：通过把复杂任务分解为已知子目标，Agent 即使是面对从未见过的任务（如 "craft enchanting table"），也能从已有的 "craft diamond"、"craft book" 等经验中受益。

3. **多模态检索确保了场景适配**：文本维度确保任务相关，视觉维度确保场景适配。两阶段级联避免了纯文本检索的 "水土不服"。

4. **Self-Check + Self-Explain = 计划鲁棒性**：事前验证避免了高危错误，事后恢复保证了执行可靠性。记忆提供的参考计划降低了重规划次数（2-3 轮 vs 6+ 轮）。

5. **记忆的正反馈循环**：越好的计划 → 越多的成功经验 → 越大的记忆库 → 越好的计划。这是一个自我增强的系统。

### 在 Minecraft 世界中的实际意义

JARVIS-1 是首个能**稳定获取钻石镐**的 AI Agent。钻石镐需要至少 3 颗钻石和 2 根木棍，涉及挖矿、冶炼、合成等 20+ 步操作，且必须在地下生存足够长时间。在没有记忆增强的情况下，纯 LLM Planner（DEPS）在这个任务上的成功率仅 ~0.6%。

---

## 七、对六朝（Six Dynasties）项目的启示

六朝项目同样面临开放世界、多任务、长视距规划、不完美信息等挑战。JARVIS-1 的记忆增强规划理念可以多维度迁移：

### 7.1 可复用策略的记忆库

六朝中的策略模式（如特定势力开局、特定兵种组合、特定科技树路线）具有高度重复性。可以构建类似的多模态记忆：
- **Key**: 局势描述（势力、年代、资源、相邻势力关系）
- **Value**: 成功的策略序列（外交 → 内政 → 军事的步骤组合）
- **Retrieval**: 面对新局势时，检索相似历史局势的成功策略作为参考

### 7.2 交互式规划（Self-Check + Self-Explain）

六朝决策的特点是一步走错可能满盘皆输（如贸然称帝引来围攻）。JARVIS-1 的 Self-Check 理念可以直接适用：

- **Self-Check**: 在提交决策前模拟推演若干回合，检查资源是否足够、是否会触发负面事件
- **Self-Explain**: 当策略失败时（如被其他势力宣战），分析失败原因并动态调整策略

### 7.3 终身学习（Self-Instruct + Self-Improve）

六朝可以通过自对弈积累经验，这些经验可以：
- 让 AI 逐渐掌握不同势力的最优开局
- 在不同版本/规则下持续积累新战术
- 跨势力迁移经验（如 "高机动兵种" 的通用使用策略）

### 7.4 跨任务迁移

六朝中的不同目标（统一、经济发展、文化胜利）看似不同，但底层有大量共享的子策略（资源管理、军队建设、外交斡旋）。记忆增强规划可以利用这种关联性。

| JARVIS-1 概念 | 六朝对应概念 |
|------|------|
| Minecraft 科技树 (Wood→Stone→Iron→Diamond) | 六朝发展树（屯田→扩军→攻城→统一） |
| 合成配方 (3 diamonds + 2 sticks → pickaxe) | 策略链 (外交结盟 → 军事同盟 → 联合进攻) |
| 反向推理子目标分解 | 从 "统一天下" 分解为 "灭A→灭B→灭C" 子目标 |
| 多模态记忆检索 | 基于局势特征检索相似历史对局的胜利策略 |
| Self-Check 库存前置条件验证 | 决策前验证资源、兵力、外交关系是否满足前置条件 |
| Self-Explain 镐子损坏恢复 | 战败后分析原因（兵种克制？后勤不足？）并调整 |
| Self-Instruct 课程生成 | 从简单势力开局逐步过渡到困难势力 |

---

## 八、局限与未来方向

1. **记忆的时效性**：记忆条目来自过去的经验，如果环境发生了重大改变（如游戏版本更新），旧记忆可能不再适用。需要引入记忆的"过期"或"更新"机制。

2. **检索的精度-效率权衡**：当前的 CLIP 排序虽然有效，但在记忆规模巨大时可能成为瓶颈。需要更高效的索引结构。

3. **负样本的价值利用**：当前只存储成功经验。但失败经验（"这样做会失败"）可能同样有价值——这是一个待探索的方向。

4. **低层 Controller 是瓶颈**：论文明确指出，在钻石相关任务中，瓶颈往往不是 Planner，而是低层 Controller 无法完美执行文本指令。这对六朝的启示是：高层策略和底层执行需要同步优化。

5. **代码未完全开源**：多模态描述器（Multimodal Descriptor）和多模态检索（Multimodal Retrieval）的实际代码未公开，`learning.py` 标记为 "Coming Soon"。这对复现构成了实质性障碍。

---

## 参考文献

- Wang, Z., Cai, S., Liu, A., et al. (2023). *JARVIS-1: Open-World Multi-task Agents with Memory-Augmented Multimodal Language Models*. arXiv:2311.05997. Published in IEEE TPAMI, Vol.47, 2025.
- Fan, L., et al. (2022). *MineCLIP: Foundation Model for Embodied AI in Minecraft*. NeurIPS 2022.
- Wang, G., et al. (2023). *Voyager: An Open-Ended Embodied Agent with Large Language Models*. arXiv:2305.16291.
- Wang, Z., et al. (2023). *DEPS: Describe, Explain, Plan and Select with LLMs*. NeurIPS 2023.
- Baker, B., et al. (2022). *VPT: Video PreTraining for Minecraft*. NeurIPS 2022.
- Lewis, P., et al. (2020). *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*. NeurIPS 2020.
- Shinn, N., et al. (2023). *Reflexion: Language Agents with Verbal Reinforcement Learning*. NeurIPS 2023.
