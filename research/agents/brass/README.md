# LLM / AI 玩 Brass（工业革命：伯明翰）调研

> 创建日期: 2026-08-08 | 最后更新: 2026-08-08
>
> 深度解析: [BRASS_PARL — 传统 RL 框架](01_brass_parl.md) | [Intelligent Board Games — LLM 多智能体方案](02_intelligent_board_games.md) | [LLM 调用时序分析](03_llm_call_analysis.md)
>
> 本项目 (`research/agents/brass/`) 调研现有使用 AI（传统 RL 和 LLM Agent）玩 Brass（工业革命：伯明翰）的代表性工作。基于一手资料（项目代码 + 实际深度阅读分析）重新整理。

---

## 调研背景

Brass: Birmingham（《工业革命：伯明翰》）是 Martin Wallace 设计、Roxley Games 于 2018 年出版的经济策略桌游。它在 BoardGameGeek 上长期排名前 3，重度评分约 3.9/5。适合作为 AI 研究平台的特征：

- **高度复杂的资源网络**：煤、铁、啤酒三种资源，BFS 最短路径消耗机制，市场动态定价
- **双时代结构**：运河时代（前半局）→ 铁路时代（后半局），时代切换时删除 1 级工厂和全部道路
- **卡牌驱动的动作约束**：手牌决定了玩家可在哪些地点/建造哪些类型的工厂
- **多维度策略空间**：建厂、修路、售卖产品、研发、贷款、换牌，每种动作都有复杂的资源依赖
- **长时序依赖**：约 40-60 个回合，早期布局影响终局得分

---

## 调研结论：近乎空白

经多轮中英文搜索（Google Scholar、arXiv、GitHub），**目前没有任何专门使用 AI 玩 Brass: Birmingham 的学术研究论文。** 仅有以下两个项目提供了部分基础设施：

| # | 项目 | 年份 | 核心方法 | 游戏规则完整度 | AI 质量 |
|---|------|------|----------|:---:|:---:|
| 1 | **BRASS_PARL** | 2025 | MLP + REINFORCE (传统RL) | ⭐⭐⭐⭐⭐ 完整 | ⭐ 不可用 |
| 2 | **Intelligent Board Games** | 2025 | Gemini API + 多 prompt 角色扮演 | ⭐ 严重简化 | ⭐⭐ 可展示但无棋力 |

两个项目均**未达到可评估 AI 棋力的水平**。

---

## 项目速览

### [BRASS_PARL](01_brass_parl.md) — 规则完整的游戏环境（AI 不可用）

**Yunfei Zhao (qikahh)** 用 Python 构建的 Brass Birmingham 强化学习框架。**游戏规则实现是这项目真正的价值所在。**

**环境亮点**：
- 完整的 6 种工厂 × 4-8 等级（费用/需求/收入/分数精确匹配官方规则）
- BFS 最短距离煤资源网络（`find_coal`、`find_iron`）
- 煤/铁市场动态定价（14/10 级价格位）
- 友善原则、翻面机制、售卖产品（含啤酒消耗）、翻建
- 时代切换（删除 1 级工厂 + 全部道路 + 计分）
- 39 条道路 × 22 个城市的官方地图拓扑
- 精确的卡牌组成和发牌系统

**RL 致命缺陷**：
- `build_second_road` 递归调用自身 → 永不工作
- `learn_change_card` 缺少 `.backward()` → 无法学习
- 5150 维 one-hot 状态编码，扁平化丢失拓扑结构
- 4 玩家共享策略 self-play，无 baseline，REINFORCE 方差极高
- 作者自认"训练效果不佳"

**结论**：`env/` 层可直接作为 LLM Agent 的游戏环境；`agent/` 层建议全部重写。

---

### [Intelligent Board Games](02_intelligent_board_games.md) — LLM 驱动的演示平台（游戏不完整）

**SamiraSamrose** 的 Flask + Gemini API 多游戏平台。自称"实现了 Google/DeepMind 的 Society of Thought 和 Mask/Mirror 论文"。

**LLM 架构**：
- `mimic_character_decision()` — 唯一影响游戏决策的调用（1 次/回合/AI）
- `SocietyOfThought.generate_multi_perspective_reasoning()` — N+1 次调用，结果丢弃
- `BiasMasking.apply_bias_correction()` — 1 次调用，结果丢弃
- 每次 AI 行动共 10 次 Gemini 调用，其中 **9 次（90%）结果被丢弃**——仅用于前端展示

**Brass 实现的严重缺陷**：
- 16 个城市（真实 22 个），城市有相同功能，无市场/工业区分
- **无煤/铁资源网络**（Brass 的核心机制）
- 无啤酒机制、无翻面、无友善原则
- 费用表自编（全部错误）
- 计分方式完全编造
- 无售卖产品、研发、换牌动作
- `_format_game_state()` 传给 LLM 的信息仅含回合号 + 阶段 + 玩家名——**LLM 看不到地图/金钱/手牌**

**结论**：工程型演示项目，非研究型。Brass 部分不可用于严肃研究。

---

## 两种方法对比

| 维度 | BRASS_PARL | Intelligent Board Games |
|------|:---:|:---:|
| **AI 范式** | 传统 RL (REINFORCE) | LLM (Gemini prompt) |
| **游戏规则完整度** | ⭐⭐⭐⭐⭐ | ⭐ |
| **AI 可用性** | ⭐ (有 bug) | ⭐⭐ (可用但不产生合理决策) |
| **是否需要训练** | ✅ ~3000 episodes | ❌ 零样本 |
| **开源** | ✅ | ✅ |
| **实际可跑** | ✅ (env 层 + demo) | ✅ (启动即用) |
| **LLM 集成难度** | ⭐⭐ (需从头构建文本接口) | ⭐⭐⭐ (已集成但游戏太浅) |
| **研究价值** | env 层可直接复用 | 架构参考价值 |

---

## 为什么 Brass 是 AI 研究空白

Brass 被 AI 学术圈忽视的原因与[《历史巨轮》](../through_the_ages.md)高度相似：

1. **规则复杂度极高** — 资源网络（煤/铁/啤酒 BFS）、动态市场、友善原则、双时代切换，实现完整游戏规则本身就是巨大的工程挑战
2. **没有成熟的数字实现** — 不像 Catan Universe 或 Dominion Online，Brass 缺乏可直接接入 API 的电子版（官方数字版 2025 年才发布，无 API）
3. **状态表示困难** — 棋盘拓扑（22 城市 + 39 道路 + 资源网络）、经济状态（市场定价）、卡牌手牌管理，文本化表示对 LLM 极其冗长
4. **长时序依赖** — 一局 40-60 回合，远超当前 LLM 桌游 Agent 基准测试的游戏长度
5. **主流学术框架未收录** — TAG（Tabletop Games Framework）的 18 款游戏中不包含 Brass

---

## 对六朝的启示

### 核心洞察

1. **环境基础设施是最大瓶颈**：BRASS_PARL 的 `env/` 层是目前全球唯一可用的 Brass 规则完整实现。任何想做 Brass + AI 的工作，要么从它出发，要么从头写一个——后者保守估计需要 2-3 个月的专职开发。

2. **Brass 和六朝的结构相似性极高**：
   - 都是**卡牌驱动**的策略游戏
   - 都有**区域/网络**相关机制（Brass 的资源网络 vs 六朝的地域争霸）
   - 都有**多阶段**进程（Brass 的运河→铁路 vs 六朝的朝代演进）
   - 动作空间都是**高度上下文依赖**的（打什么卡、在什么位置/条件做什么事）

3. **LLM 调用架构的教训**：Intelligent Board Games 证明了一个反面教材——**不要在无关紧要的地方疯狂调用 LLM**。它的 90% 调用被丢弃，真正的决策信息（游戏状态）反而没传给 LLM。有效的 LLM Game Agent 应该：
   - 一次行动 1-2 次 LLM 调用（决策 + 可选的 self-critique）
   - 游戏状态必须完整传给 LLM（金钱/手牌/地图/对手状态）
   - 动作空间必须精确（合法动作列表 + 代价 + 预期收益）

4. **"游戏规则完整 + LLM 决策"是当前最优路线**：BRASS_PARL 提供了规则完整的游戏环境，Intelligent Board Games 提供了 LLM 集成的架构参考，但两者从未被结合——这恰好是最可行的方向。

### 建议的 Brass + LLM 架构

```
BRASS_PARL env/ 层（游戏规则引擎）
     │
     ├─ get_game_state() → 结构化文本描述
     │     （地图拓扑、资源网络、市场状态、手牌、对手信息）
     │
     ├─ get_available_actions() → 合法动作列表 + 代价
     │
     └─ execute_action(action) → 新状态

LLM Agent 层（替换 agent/）
     │
     ├─ 1 次 LLM 调用：状态 + 动作 → 决策
     └─ 可选：self-critique（反思 + 重选）
```

---

## 文件索引

| 文件 | 内容 |
|------|------|
| [01_brass_parl.md](01_brass_parl.md) | BRASS_PARL 深度分析：env 层规则实现、RL agent 的 bug、代码质量问题、LLM 适配评估 |
| [02_intelligent_board_games.md](02_intelligent_board_games.md) | Intelligent Board Games 深度分析：工程架构、游戏规则缺失、核心代码解读、研究价值判断 |
| [03_llm_call_analysis.md](03_llm_call_analysis.md) | LLM 调用时序分析：完整的 prompt 模板、调用链追踪、90% 调用被丢弃的架构问题 |

---

## 参考文献

- **BRASS_PARL**: Zhao, Y. "BRASS_PARL: 面向桌游'工业革命：伯明翰'的强化学习 AI 框架." GitHub, 2025. [github.com/qikahh/BRASS_PARL](https://github.com/qikahh/BRASS_PARL)
- **Intelligent Board Games**: Samrose, S. "Intelligent Board Games with AI Opponents." GitHub, 2025. [github.com/SamiraSamrose/intelligent-board-games](https://github.com/SamiraSamrose/intelligent-board-games)
- **Societies of Thought**: Kim, J. et al. "Reasoning Models Generate Societies of Thought." arXiv, 2025. [arXiv:2601.10825](https://arxiv.org/abs/2601.10825)
- **To Mask or to Mirror**: Qian, C. et al. "To Mask or to Mirror: Human-AI Alignment in Collective Reasoning." Google DeepMind, 2025.
- **TAG Framework**: Gaina, R.D. et al. "TAG: A Tabletop Games Framework." ECAI, 2020. [github.com/GAIGResearch/TabletopGames](https://github.com/GAIGResearch/TabletopGames)
