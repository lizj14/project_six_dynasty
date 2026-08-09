# LLM Agent 玩《历史巨轮》(Through the Ages) 调研

> 调研日期：2026-08-06
> 结论：**目前没有找到任何相关工作**

---

## 一、调研结果：空白

经多轮中英文搜索（Google Scholar、arXiv、会议论文、GitHub），**目前没有使用 LLM Agent 玩《历史巨轮》的研究论文或开源项目。**

### 相关搜索词覆盖

- `LLM Agent "Through the Ages" board game`
- `"Through the Ages" AI agent reinforcement learning`
- `"Through the Ages" board game AI research paper computational`
- `大语言模型 Agent 历史巨轮 桌游 Through the Ages`
- `TAG tabletop games framework "Through the Ages"`

以上搜索词均无结果。

---

## 二、为什么是空白

### 2.1 学术框架未收录

学术界最主流的桌游 AI 基准框架 [Tabletop Games Framework (TAG)](https://github.com/GAIGResearch/TabletopGames)（Gaina et al., 2020）已实现 **18 款**桌游：

> Catan、Terraforming Mars、Dominion、Pandemic、Battlelore、Colt Express、Love Letter、Stratego、Exploding Kittens、Uno、Connect 4、Poker、Blackjack、Can't Stop、Diamant、Dots and Boxes、Tic-Tac-Toe、Virus!

《历史巨轮》**不在已实现列表中**，也不在开发计划（Descent、Hanabi、7 Wonders）中。

### 2.2 数字版闭源

数字版由 CGE Digital 开发，AI 质量很高（社区推测基于 MCTS + 启发式评分），但：
- 无公开 API 供研究者接入外部 Agent
- 无开源游戏引擎可用
- 开发者未公开 AI 技术细节

### 2.3 游戏复杂度极高

《历史巨轮》的决策空间对当前 LLM Agent 构成严峻挑战：

| 维度 | 特征 |
|------|------|
| 卡牌池 | 300+ 张，分 4 个时代，每局仅出现部分 |
| 行动类型 | 拿牌、打牌、升级、建造、军事、殖民地、战争、条约等 |
| 资源系统 | 食物、矿产、科技、文化、军力、内政行动/军事行动，多维度耦合 |
| 规划跨度 | 需要跨时代布局（卡牌 combo、科技树路线、领袖/奇迹节奏） |
| 玩家互动 | 间接竞争（抢牌）+ 直接对抗（战争/侵略），需对手建模 |
| 单局决策数 | 通常 200-400 次决策 |

---

## 三、最接近的参考工作

### 3.1 HexMachina — 卡坦岛 LLM Agent ⭐⭐⭐

> **论文**: "Agents of Change: Self-Evolving LLM Agents for Strategic Planning"
> **作者**: Nikolas Belle et al. (UC Santa Barbara)
> **发表**: arXiv:2506.04651, 2025 年 6 月

**核心思路**：LLM 不做 per-turn 决策，而是做"策略架构师"——写 Python 代码迭代演化策略模块。

**架构**：
- **Discovery Phase**：Agent 自主探索 Catanatron API，无人类文档，诱导出适配层
- **Improvement Phase**：Analyst → Coder → Orchestrator 循环，演化编译型玩家模块
- 角色分工：Orchestrator、Analyst、Strategist、Researcher、Coder

**关键结果**：
- 从零演化出的玩家对最强手写 baseline（AlphaBeta depth-2）达到 **54% 胜率**
- 显著优于 ReAct/Reflexion 等 prompt 驱动方法（后者因上下文窗口饱和而表现差）
- Claude 3.7 和 GPT-4o 策略演化效果好，Mistral Large 较差

**启示**：对于高复杂度策略桌游，LLM 写策略代码 > LLM 做 per-turn 推理

### 3.2 BALROG — LLM/VLM 游戏 Benchmark ⭐⭐

> **论文**: "BALROG: Benchmarking Agentic LLM and VLM Reasoning on Games"
> **作者**: Paglieri et al.
> **发表**: ICLR 2025

多游戏环境 benchmark，关键发现：
- 当前模型在简单游戏上表现尚可，困难游戏上挣扎
- **视觉决策是严重弱点**——有些模型看到图像反而比纯文本输入表现更差
- 开放排行榜：[balrogai.com](https://balrogai.com)

### 3.3 Hanabi LLM Agent ⭐⭐

> **论文**: "Are LLMs Generalist Hanabi Agents?"
> **作者**: Ramesh et al.
> **发表**: NeurIPS 2025 / ICML 2025

合作类卡牌游戏，关键发现：
- 用 DeductCon prompt 引导 LLM 做贝叶斯推理，最强模型平均超 15/25 分
- 仍落后于有经验人类和专用 RL agent（稳定 20+ 分）
- 不同 prompt 策略诱导出完全不同的游戏风格

### 3.4 TAG: Terraforming Mars ⭐

> **论文**: "TAG: Terraforming Mars" (Gaina et al.)
> **发表**: AAAI AIIDE 2021

将《火星殖民》作为 AI benchmark 形式化，使用传统 AI（Random、OSLA、MCTS），**尚无 LLM Agent**。

游戏特征对比：

| 特征 | 火星殖民 | 历史巨轮 | 六朝 |
|------|----------|----------|------|
| 行动空间 | 大（平均 7，最大 46） | 大 | 大 |
| 游戏组件 | 400+ | 300+ 卡牌 | 多 |
| 隐藏信息 | 对手手牌、牌堆 | 对手手牌、牌堆 | 有 |
| 单局决策数 | ~460 | 200-400 | 多 |
| LLM Agent 研究 | ❌ 无 | ❌ 无 | ❌ 无 |

---

## 四、对六朝项目的启示

### 4.1 研究定位

《六朝》和《历史巨轮》同属**高复杂度文明建设类策略桌游**（长线规划、多系统耦合、资源引擎构建）。该领域 LLM Agent 研究基本空白，意味着：

- **创新空间大**——如果做出来，可能是首个攻克此类游戏的 LLM Agent
- **无现成 baseline**——需要自行定义评估标准和对比基准
- **需要自建环境**——无公开 API 或 benchmark 框架

### 4.2 技术路线建议

参考 HexMachina 的成功经验：

| 路线 | 描述 | 可行性 |
|------|------|--------|
| **LLM 写策略代码** | LLM 作为策略架构师，生成/演化 Python 策略模块 | ⭐⭐⭐ 高 |
| **LLM per-turn 推理** | 每回合输入游戏状态，LLM 直接输出决策 | ⭐⭐ 中（上下文窗口压力大） |
| **混合模式** | LLM 负责高层战略规划，传统搜索负责战术执行 | ⭐⭐⭐ 高 |
| **演化+自对弈** | LLM 生成策略变体，通过自对弈筛选 | ⭐⭐ 中（计算成本高） |

### 4.3 可直接参考的工作

- **HexMachina**（策略代码演化架构）
- **BALROG**（LLM 游戏 Agent 评估方法论）
- **Hanabi Agent**（复杂 prompt 工程，DeductCon 风格推理）
- **SPIN-Bench**（战略规划 + 社交推理 benchmark）

---

## 五、参考来源

- Belle et al., "Agents of Change: Self-Evolving LLM Agents for Strategic Planning", arXiv:2506.04651, 2025
- Paglieri et al., "BALROG: Benchmarking Agentic LLM and VLM Reasoning on Games", ICLR 2025
- Ramesh et al., "Are LLMs Generalist Hanabi Agents?", NeurIPS/ICML 2025
- Gaina et al., "TAG: Terraforming Mars", AAAI AIIDE 2021
- Gaina et al., "Tabletop Games Framework (TAG)", 2020 — [GitHub](https://github.com/GAIGResearch/TabletopGames)
- Cipolina-Kun et al., "Game Reasoning Arena", 2025
- Yao et al., "SPIN-Bench: How Well Do LLMs Plan Strategically and Reason Socially?", arXiv:2503.12349, 2025
- Stephenson et al., "Codenames as a Benchmark for Large Language Models", IEEE ToG 2025
