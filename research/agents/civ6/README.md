# LLM 玩文明 调研

> 创建日期: 2026-08-03 | 最后更新: 2026-08-03
>
> 深度解析: [Civ6-MCP / CivBench](01_civ6_mcp_civbench.md) | [CivRealm](02_civrealm.md) | [CivAgent / Digital Player](03_civagent_digital_player.md) | [Vox Deorum / CivBench (Civ V)](04_vox_deorum_civbench_civ5.md)
>
> 本项目 (`research/agents/civ6/`) 调研现有使用 LLM 玩文明（Civilization）系列游戏的研究工作。基于一手资料（论文 PDF + git clone 代码仓库）重新分析整理。

---

## 调研背景

文明系列游戏（Civilization I–VI）是 4X 策略游戏的标杆，具有适合 AI 研究的特征：

- **巨大决策空间**：后期每回合约 10^166 种可能行动，远超围棋
- **不完美信息**：地图迷雾、对手意图不可见
- **多智能体博弈**：外交、战争、贸易、间谍等多维度互动
- **长时域规划**：单局游戏跨越数百回合，需要跨回合战略连贯性
- **多胜利条件**：科技、文化、外交、统治、宗教——需要多维监控

这些特征使文明成为评估 LLM 在战略性推理、长期规划、多智能体交互方面能力的终极测试平台。

---

## 五大项目总览

| # | 项目 | 年份 | 游戏 | 核心方法 | 对局数 | AI 表现 |
|---|------|------|------|----------|--------|---------|
| 1 | **Civ6-MCP / CivBench** | 2025–26 | 文明 VI | MCP 76 工具 + 多模型 | 12 | 1胜/12局 |
| 2 | **CivRealm** | 2024 | Freeciv | RL + LLM 双范式 | — | 完整游戏几乎为 0 |
| 3 | **CivAgent / Digital Player** | 2024–25 | Unciv | 层级 Agent + 外交 + 模拟 | 50 | 低（GPT-3.5 基线） |
| 4 | **Vox Deorum** | 2025 | 文明 V | 混合 LLM+X | **2,327** | **统计持平算法 AI** |
| 5 | **CivBench (Civ V)** | 2025 | 文明 V | 进度基准评估 | 307 | 揭示策略画像 |

---

## 项目速览

### [Civ6-MCP / CivBench](01_civ6_mcp_civbench.md) — 最深刻的经验发现

**Liam Wilkinson** 用 76 个 MCP 工具将 Claude/GPT/Gemini/Kimi 直接接入《文明 VI》进行 12 场完整对局。配有完整的可观测性基础设施（日记 + 工具日志 + 空间注意力追踪）和 CivBench 评测框架。

**四大失败现象**：
- **Sensorium Effect**（感知器效应）：主动查询仅 1–2%
- **Reflection-Action Gap**（反思-行动鸿沟）：写出对的策略但做不到
- **Gravity of the Default**（默认引力）：战术谜题永远比战略优先
- **Hallucination of Competence**（能力幻觉）：叙事覆写现实

**唯一胜利**：马里 T271 科技胜利（金币购买绕过生产力惩罚），但仍有零剧院广场、177 回合不换政体、10,162 闲置信仰。

---

### [CivRealm](02_civrealm.md) — 最学术的环境设计

**BIGAI × 北京大学**，ICLR 2024 Spotlight。首个同时支持 RL 和 LLM 的文明基准。设计的两层 LLM 架构 Mastaba（金字塔）验证了层级架构在大规模策略游戏中的必要性。

---

### [CivAgent / Digital Player](03_civagent_digital_player.md) — 最完整的外交系统

**网易伏羲实验室**，基于 Unciv。唯一将自然语言外交作为核心特色的项目——Discord/飞书整合、意图理解系统、CivSim 模拟器（~10 回合/秒的前向搜索）。强调低成本数据飞轮的商业可行性。

---

### [Vox Deorum / CivBench (Civ V)](04_vox_deorum_civbench_civ5.md) — 最大规模的实验

**2,327 场对局**，混合 LLM+X 架构（LLM 负责战略，算法 AI 负责战术执行）。首个 LLM 策略师与算法 AI 统计持平的实验。CivBench 引入回合级胜利概率评估方法。

---

## 跨项目主题对比

| 维度 | Civ6-MCP | CivRealm | CivAgent | Vox Deorum |
|------|----------|----------|----------|------------|
| **游戏** | 文明 VI | Freeciv | Unciv | 文明 V |
| **交互方式** | MCP 76 工具 | 环境 API | 结构化 API + 存档 | 游戏内集成 |
| **感知** | 纯文本 | 自然语言+张量 | 结构化状态 | 自然语言摘要 |
| **记忆** | 日记系统 (JSONL) | 向量数据库 | LlamaIndex RAG | 回合摘要 |
| **架构** | 单 Agent | 金字塔/扁平 | 模块化层级 | 混合 LLM+X |
| **外交** | 游戏内 | 游戏内 | **Discord/飞书** | 游戏内 |
| **模拟/前向搜索** | ❌ | ❌ | ✅ CivSim | ❌ |
| **反思/学习** | ✅ 五种反思字段 | ❌ | ✅ Reflexion 启发 | ❌ |
| **可观测性** | ✅✅✅ 三层基础设施 | ⚠️ 基本 | ⚠️ 基本 | ⚠️ 基本 |
| **对局量** | 12 | 未大规模 | 50 (GPT-3.5) | **2,327** |
| **发表** | 开源项目 | ICLR 2024 Spotlight | arXiv 2025 | arXiv 2025 |

---

## 四类 LLM Agent 失败模式（来自 Civ6-MCP）

### 1. Sensorium Effect
信息不主动查询就不存在。Agent 的感知是被动轮询模型，而非人类的持续被动吸收。**量化**：1–2% 的主动全局查询率。

### 2. Reflection-Action Gap
Agent 写出完美的战略分析，然后完全不执行。分析质量 ≈ 策略指南级别；执行率接近于 0。

### 3. Gravity of the Default
战术谜题（移动单位、设置生产）总是优先于战略目标（扩张、探索、外交）。回合循环没有强制性的"停下来思考"时刻。

### 4. Hallucination of Competence
Agent 根据文本内部一致性而非环境客观反馈评估成功。如果日记读起来像获胜策略，Agent 就相信自己正在获胜——即使数据证明它在垫底。

---

## 核心教训与对六朝的启示

### 六个跨项目共识

1. **感知即一切**：需要设计强制周期性全局状态检查（如每 N 回合自动扫描所有对手胜利进度）
2. **知行鸿沟是工程问题**：需要外部计划-执行追踪器，偏差超过阈值触发强制反思
3. **层级架构是必需的**：扁平 Agent 在大规模策略游戏中必然失败。战略层 + 维度子 Agent（军事/文化/经济/外交）
4. **长时域规划仍是瓶颈**：数百回合的跨回合战略连贯性对所有模型都是未解决问题
5. **混合架构最实用**：LLM 不必要做一切——Vox Deorum 证明 LLM 战略 + 算法战术可以在 $0.86/局达到统计持平
6. **文明是 LLM Agent 的终极测试平台**：它正好暴露了当前 LLM Agent 的所有短板

### 结构化启示表

| 来源 | 具体设计建议 |
|------|------------|
| Civ6-MCP Sensorium | 强制周期性全局扫描——不要让 AI "选择"去查 |
| Civ6-MCP Reflection-Action Gap | 每轮对比"上轮计划"vs"本轮实际"——偏差超过阈值触发强制反思 |
| Civ6-MCP Hallucination | AI 写"我领先"前先对比排行榜——数字不支持的叙事标红 |
| Civ6-MCP 可观测性 | 日记 + 工具日志 + 空间追踪——三层基础设施对调试 AI 行为不可或缺 |
| Mastaba 金字塔 | 六朝 AI："战略 AI + 各维度子 AI（军事/文化/经济/外交）" |
| CivAgent 数据飞轮 | 玩家反馈 → Agent 反思 → 更强 Agent |
| CivAgent 外交 | 自然语言外交是 LLM 在策略游戏中最大的差异化优势——传统 AI 做不了 |
| CivAgent CivSim | 关键决策前"模拟推演"几个回合——约 10 回合/秒的轻量模拟 |
| Vox Deorum 混合架构 | 战术执行（如战斗单位移动）委托给传统算法——不必要全部 LLM |
| CivBench (Civ V) 进度评估 | 回合级进度指标 > 终局胜负——更密集的训练信号 |

---

## 文件索引

| 文件 | 内容 |
|------|------|
| [01_civ6_mcp_civbench.md](01_civ6_mcp_civbench.md) | Civ6-MCP 深度解析：76 工具、技术架构、12 场对局、四大失败现象、CivBench 评测 |
| [02_civrealm.md](02_civrealm.md) | CivRealm 深度解析：Freeciv 环境、BaseLang/Mastaba、ICLR 2024 Spotlight |
| [03_civagent_digital_player.md](03_civagent_digital_player.md) | CivAgent 深度解析：模块化架构、CivSim 模拟器、意图理解、Discord 外交、50 场实验 |
| [04_vox_deorum_civbench_civ5.md](04_vox_deorum_civbench_civ5.md) | Vox Deorum + CivBench：混合 LLM+X、2,327 场、回合级胜利概率评估 |

---

## 参考文献

- **Civ6-MCP**: Wilkinson, L. "civ6-mcp: An MCP server that lets LLM agents play Civilization VI." GitHub, 2025–2026. [github.com/lmwilki/civ6-mcp](https://github.com/lmwilki/civ6-mcp)
- **CivRealm**: Qi et al. "CivRealm: A Learning and Reasoning Odyssey in Civilization for Decision-Making Agents." ICLR 2024 Spotlight. [arXiv:2401.10568](https://arxiv.org/abs/2401.10568)
- **CivAgent / Digital Player**: Wang et al. "Digital Player: Evaluating Large Language Models based Human-like Agent in Games." arXiv, 2025. [arXiv:2502.20807](https://arxiv.org/abs/2502.20807)
- **Vox Deorum**: Chen et al. "Vox Deorum: A Hybrid LLM Architecture for 4X / Grand Strategy Game AI." arXiv, 2025. [arXiv:2512.18564](https://arxiv.org/abs/2512.18564)
- **CivBench (Civ V)**: Chen et al. "CivBench: Progress-Based Evaluation for LLMs' Strategic Decision-Making in Civilization V." arXiv, 2025. [arXiv:2604.07733](https://arxiv.org/abs/2604.07733)
