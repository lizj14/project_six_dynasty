# CivAgent / Digital Player 深度解析

> 论文: "Digital Player: Evaluating Large Language Models based Human-like Agent in Games"
> 作者: Wang Jiawei, Wang Kai, Lin Shaojie, Runze Wu, Tangjie Lyu, Renyu Zhu 等
> 机构: 网易伏羲实验室（NetEase Fuxi AI Lab）× 中国科学院大学 × 闽南师范大学
> 投递: NeurIPS 2024 Datasets and Benchmarks Track（未中）| arXiv: 2025-02
> 论文: [arXiv:2502.20807](https://arxiv.org/abs/2502.20807) | PDF 已下载
> 代码: [github.com/fuxiAIlab/CivAgent](https://github.com/fuxiAIlab/CivAgent)（已迁移至 [github.com/asdqsczser/CivAgent](https://github.com/asdqsczser/CivAgent)）
> 目标游戏: Unciv（文明 V 的开源复刻版）

---

## 一、项目概述

CivAgent 是网易伏羲实验室开发的 **LLM 驱动的类人游戏 Agent 框架**，运行在开源策略游戏 **Unciv** 中。本文提出了 CivSim 测试平台和对应的 CivAgent 基线 Agent。

### 设计哲学

> **SLG（Simulation & Strategy Game）是 AI-native 游戏的理想形态。**

| SLG 优势 | 说明 |
|----------|------|
| **大决策空间** | 数百种科技/建筑/单位——丰富 AI 挑战 |
| **低美术资源需求** | 不依赖 3D 渲染，文本/2D 即可 |
| **自然涌现玩法** | 策略组合自然产生多样性 |
| **自由外交对话** | 少数需要自然语言谈判和说服的游戏类型 |
| **数据飞轮潜力** | 玩家反馈 → Agent 反思 → 更强 Agent → 更多数据 |

### 核心理念：数据飞轮

设计目标不是"造最强 AI"，而是构建**低成本 AI 玩家数据飞轮**：

```
玩家反馈 → Agent 反思改进 → 更好的 Agent → 更多玩家数据 → ...
```

初步内部试玩已成功邀请**约百名玩家**，验证了可行性。

---

## 二、系统架构

### 2.1 整体架构

```
┌──────────────────────────────────────────────────┐
│              Discord / 飞书（外交界面）             │
├──────────────────────────────────────────────────┤
│              ChatServer (Flask) — 消息路由         │
├──────────────────────────────────────────────────┤
│              RedisStreamMQ — 异步消息队列          │
├──────────────┬───────────────────────────────────┤
│  MQListener  │         CivAgent 核心              │
│  (消息处理)   │  Memory (LlamaIndex RAG)          │
│              │  Skills System (JSON 技能库)       │
│              │  Workflow Utilities (LLM 查询)      │
│              │  PromptHub (7 类模板)             │
├──────────────┴───────────────────────────────────┤
│              CivSim — JPype 桥接 Python↔Java/Unciv │
├──────────────────────────────────────────────────┤
│              Unciv Game Server (Java)             │
└──────────────────────────────────────────────────┘
```

### 2.2 CivAgent 核心模块

#### Memory Management
- **LlamaIndex** 进行 RAG（检索增强生成）
- 短期记忆：最近 20 行对话/行动
- 长期记忆：通过反思生成的技能使用经验

#### Skills System
JSON 定义的技能库：宣战、防御协定、共同敌人、求和平、研究协议、贸易提案等。

#### PromptHub — 7 类模板

| 模板 | 用途 |
|------|------|
| **React** | 对游戏事件的即时反应 |
| **Reflection** | 对过往决策的反思总结 |
| **Analysis** | 对当前局势的深度分析 |
| **Recognition** | 识别对手意图和模式 |
| **Planning** | 制定中长期战略计划 |
| **Decision** | 具体行动的最终决策 |
| **Response** | 对外交信息的自然语言回复 |

#### 意图理解系统（Intention Understanding）

解析其他玩家的外交消息，分类为：友好意图（结盟、开放边界）、敌对意图（威胁、谴责）、欺骗性意图（表面友好实则准备背刺）、中性意图（信息交换）。

**双重验证**：高置信度的"强意图"进行二次验证，防止把玩笑误认为战争威胁。

### 2.3 决策流程

```
每回合:
  1. 提取观测（从存档提取离散代表性信息）
  2. 整合上下文 + 检索记忆
  3. 推理（可选：使用 CivSim 模拟器预测行动后果）
  4. 制定长/短期计划
  5. 通过 HTTP 执行动作至游戏引擎
  6. 反思表现
  7. 将经验存入长期记忆
```

### 2.4 CivSim — 游戏模拟器

使用 **JPype** 桥接 Python AI 逻辑和 Java Unciv 引擎。

**关键能力**：
- 能在 **约 1 秒内运行约 10 回合**模拟
- 预测不同决策的结果——弥补 LLM 数值推理局限
- 外交评估：签约意愿、边界开放意愿、防御协定、贸易可接受性
- 文明管理：科技建议、建造建议、敌方城市优先级

### 2.5 LLM 集成

| 选项 | 说明 |
|------|------|
| **默认** | OpenAI ChatGPT / GPT-4 |
| **本地部署** | Ollama 支持各种开源模型 |
| **输出结构化** | Pydantic Data Models：FunctionDataModel, SkillDataModel, ReflectionDataModel, DiplomacyResponseDataModel |

---

## 三、实验结果（来自论文）

### 3.1 完整游戏任务

**设置**：50 场比赛，每场 4 个文明，使用 **GPT-3.5-turbo**（非 GPT-4）。

四种 CivAgent 变体对比：

| 变体 | 配置 | 平均得分 |
|------|------|---------|
| **CivAgent-N** | Naive，单 prompt | 17.6 |
| **CivAgent-W** | 基础工作流，无模拟/反思 | ~21 |
| **CivAgent-S** | + 模拟器 | ~31 |
| **CivAgent-SR** | + 模拟器 + 反思 | **39.2** |

**关键发现**：
- CivAgent-SR 在"共同敌人"和"组建联盟"等外交技能上的成功率显著最高
- 模拟器和反思模块各自带来显著提升
- 技能成功率与总得分呈正相关

### 3.2 谈判小游戏

- **GPT-4 显著优于** Gemma-7B、Mistral-7B、Llama3-8B（无论买方还是卖方）
- LLM 仍弱于人类专家——未能完全掌握"极限施压"等策略
- **关键差距**：LLM 缺乏适应性策略网络，在长谈判中数值漂移

### 3.3 欺骗小游戏

- GPT-4 作为**欺骗者**得分**高于人类**
- LLM 作为**检测者**弱于人类——识别虚假信息的准确率更低
- 有趣的不对称性：LLM 更擅长说谎，不擅长识别谎言

---

## 四、与 Civ6-MCP 和 CivRealm 的对比

| 维度 | CivAgent | Civ6-MCP | CivRealm |
|------|----------|----------|----------|
| **游戏** | Unciv (Civ V 复刻) | 文明 VI | Freeciv |
| **核心贡献** | 数据飞轮 + 外交 | 经验性基准 | 环境 + 双范式 |
| **LLM 接口** | 结构化 API + Pydantic | MCP 76 工具 | 自然语言 API |
| **外交** | ✅ 核心特色（Discord/飞书） | ⚠️ 游戏内 | ⚠️ 仅小游戏 |
| **模拟/前向搜索** | ✅ CivSim（~10 回合/秒） | ❌ | ❌ |
| **反思学习** | ✅ Reflexion 启发 | ✅ 五种反思字段 | ❌ |
| **人类互动** | ✅ Discord/飞书 | ❌ | ❌ |
| **完整对局量** | 50 场 (GPT-3.5) | 12 场 (多种模型) | 未大规模 |
| **AI 胜率** | 较低（GPT-3.5 基线） | 1/12 | 接近 0 |
| **成本** | 低（GPT-3.5） | 中（前沿模型） | N/A |
| **发表** | arXiv 2025（NeurIPS 未中） | 开源项目 | ICLR 2024 Spotlight |

**CivAgent 的独特贡献**：
- 唯一将**外交自然语言交互**作为核心特色的项目
- 唯一包含**游戏内模拟器**用于前向搜索
- 唯一强调**数据飞轮**商业可行性的项目

**CivAgent 的局限**：
- 仅测试了 GPT-3.5-turbo（非前沿模型）
- 仅测试了一个游戏（Unciv），泛化性未知
- 人类反馈数据的进一步利用尚未实验
- 对比的消融实验量（50 场）远小于 Vox Deorum（2,327 场）

---

## 五、对六朝项目的启示

| 启示 | 具体建议 |
|------|---------|
| **数据飞轮设计** | 每局结束后反思自动改进 Agent——设计为持续学习系统 |
| **模块化架构** | 军事/文化/经济/外交各自独立模块，可独立迭代 |
| **外交是 LLM 杀手应用** | 自然语言外交谈判是 LLM 在策略游戏中最大的差异化优势 |
| **仿真/前向搜索** | 关键决策前"模拟推演"几个回合并发——CivSim 的 10 回合/秒值得参考 |
| **Prompt Hub** | 建立专用模板库：React/Reflection/Analysis/Recognition/Planning/Decision/Response |
| **意图理解** | 让 AI "读懂"对手行为潜台词——超越显式动作的推理 |
| **结构化输出** | Pydantic 等框架确保 LLM 输出符合格式——对可靠性至关重要 |
| **结构化反思** | 五种反思字段（tactical/strategic/tooling/planning/hypothesis）是经过验证的好模板 |
| **低门槛起步** | 从简化的子场景开始验证，再接入完整游戏 |
