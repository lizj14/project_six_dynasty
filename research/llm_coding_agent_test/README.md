# LLM Coding Agent 测试 — 工作总结

> 本目录记录「用桌游 Dominion 作为 LLM Agent 测试床」的一次完整调研 + 落地实验。
> 核心产出：两个可运行的 Python 脚本（人机对战驱动、LLM vs 基线 bot 对局记录框架），以及第 1 局实验的完整日志。

## 0. 一句话概述

围绕牌库构筑游戏 **Dominion** 展开：调研 GitHub 开源实现 → 深入分析 **pyminion** 引擎架构 → 基于它搭建「LLM 当 Decider」的对局测试框架 → 完成第 1 局实验（**LLM 27 : 27 BigMoney，BigMoney 按回合数 tiebreak 险胜**）。

---

## 1. 背景与目标

这是「六朝历史桌游 + LLM Agent 研究」的延伸。Dominion 的核心机制——**每买一张牌都永久改变未来手牌的概率分布**——让它成为测试 LLM「长程规划 / 时序推理」的理想场景：

- 状态是「牌库组成」这个缓慢演化的隐藏变量，而非当前手牌；
- 购买有延迟收益（约半个洗牌周期后才生效）；
- 「何时停止建设、开始买分」（greening）是典型的最优停时问题；
- 有客观基线（Big Money 策略）可度量胜率。

**目标**：找到可参考的实现、理解其引擎/决策接口设计、搭一个能记录「每回合手牌 + 操作 + 决策原因」的对局框架，为后续评测 LLM 策略铺路。

---

## 2. 调研部分

### 2.1 GitHub 上的 Dominion 实现（按用途分类）

| 类别 | 代表仓库 | 语言 | Commit | 特点 |
|---|---|---|---|---|
| **AI / 研究向** | [evanofslack/pyminion](https://github.com/evanofslack/pyminion) | Python | 802 | 引擎 + 模拟器库，抽象 `Bot` 接口，可 pip 安装 |
| | [chelsea0x3b/dominion](https://github.com/chelsea0x3b/dominion) | Python | 35 | RL 强化学习测试床（2018 停更） |
| | [edd426/principality_ai](https://github.com/edd426/principality_ai) | TypeScript | 245 | 牌库构筑 + **MCP / LLM** 结合 |
| **完整游戏** | [the-gigi/dominion](https://github.com/the-gigi/dominion) | Python | 198 | gRPC + Docker，架构最全 |
| | [paulbatum/Dominion](https://github.com/paulbatum/Dominion) | C# | 220 | Web/WinForms client（2011 停更） |
| **模拟器** | [Geronimoo/DominionSim](https://github.com/Geronimoo/DominionSim) | Java | 142 | 老牌模拟器 |
| | [myShoggoth/deckbuilder](https://github.com/myShoggoth/deckbuilder) | Haskell | 156 | 函数式实现，含扩展 |
| **工具** | [sumpfork/dominiontabs](https://github.com/sumpfork/dominiontabs) | Python | 821 | 卡牌分隔条生成器 |

**结论**：Python 系（pyminion）最贴近「引擎 + 可插拔 AI」的需求，故选定 **pyminion** 作为参考与底座。

### 2.2 pyminion 架构分析（核心发现）

pyminion 共 ~10.6k 行、零第三方依赖。分层清晰：

| 模块 | 行数 | 职责 |
|---|---|---|
| `core.py` | 566 | 卡牌类层次、`Cost`、`CardType` 枚举、牌堆抽象、`Supply` |
| `game.py` | 421 | 对局主循环、胜负判定、额外回合 |
| `player.py` | 601 | `Player`、回合内 `State`、四阶段流程 |
| `decider.py` | 183 | **`Decider` 协议**（~17 个决策点） |
| `effects.py` | 817 | **`EffectRegistry` 事件系统** + 效果排序 |
| `bot.py` | 241 | `BotDecider` 默认实现 + `Bot` |
| `simulator.py` | 80 | 批量模拟统计胜率 |
| `expansions/*.py` | ~4700 | 4 个扩展的卡牌定义 |

**四个关键设计**（对六朝引擎有直接参考价值）：

1. **`Decider` 协议**（`typing.Protocol`）：决策与引擎彻底解耦，运行时可替换（Possession 卡直接换掉对手的 decider）。这是「接 LLM」的最宽松接口。
2. **`EffectRegistry` 事件系统**：15 类游戏事件（on_buy/on_gain/on_trash/on_turn_start…）+ `EffectAction` 优先级排序，处理 Dominion 最难的「触发式效果 + 触发顺序」。
3. **牌堆抽象 + 回调**：所有卡牌容器带 `on_add/on_remove/on_shuffle` 钩子，接到效果注册表，抽牌/弃牌自动触发相关效果。
4. **Bot 策略 = 生成器优先级**：`action_priority` / `buy_priority` 按优先级 `yield` 想打的牌，几十行就能写一个策略。

### 2.3 Dominion 的策略与数学模型（要点）

- **钱密度** ρ = 牌库总钱 ÷ 张数，手牌期望钱 = n·ρ（线性期望定理）。
- **方差修正因子** `(N-n)/(N-1)`：牌库越小（N↓）方差越小 → 抽穿牌库的引擎「稳」在方差低，不是期望高。
- **超几何分布** `P(X=x) = C(K,x)·C(N-K,n-x)/C(N,n)`：不放回抽牌的原子公式。
- **购买延迟** ≈ D/10 回合（半个洗牌周期）→ 同样一张牌，早买是神之一手、晚买是废操作。
- **greening = 最优停时问题**：买 Victory 卡是负资产，何时从「建设」切换「买分」是 MDP 里最标准的利用 vs 探索权衡。
- **Big Money 是及格线**：任何「看似聪明」的引擎若打不过纯买钱的 Big Money，就是负价值策略。

---

## 3. 实现部分（代码产出）

新增两个脚本（位于 `projects/pyminion/`，**未修改 pyminion 原始源码**）：

### 3.1 `play.py` — 人机对战驱动

`Claude 当对手 + 裁判` 的交互式脚本。通过命令行子命令驱动 pyminion 引擎：

```bash
python play.py new                    # 开局
python play.py show                   # 看当前局面
python play.py preview "village,smithy"   # 预演打完行动牌后的手牌/钱
python play.py move Human "village,smithy" "market"   # 落子
```

### 3.2 `llm_game.py` — LLM vs BigMoney 对局记录框架

LLM（Claude 手动决策 + 记录理由）对 BigMoney（自动 bot），每回合写 JSONL 日志：

```bash
python llm_game.py new                          # 新局（game_id 自增）
python llm_game.py preview "village,smithy"     # 预演
python llm_game.py move "village,smithy" "market" "推理原因"   # 落子+记录
```

### 3.3 核心架构设计（三件事）

1. **`ScriptedDecider`**：把「打什么/买什么」变成命令行参数喂给引擎。
2. **确定性回放**：因为 pyminion 的 Game 对象含 lambda 效果（不可 pickle），改用「存 seed + 移动日志，每次从头重建回放」的方式维持状态——`状态 = f(moves, seed)` 是纯函数，所以能随意「回退重打」。
3. **`RecordingDecider` + JSONL 日志**：包装 decider，记录每次决策 + 手牌快照；日志每行一个回合。

### 3.4 过程中修复的两个 bug（都在自己的脚本里）

| Bug | 根因 | 影响 |
|---|---|---|
| `preview` 漏调 `start_turn` | Merchant 的「+$1 银币加成」效果未在回合开始正确清除，残留到下一回合 | 预览金额虚高 $1，导致购买静默失败 |
| `load_state` 漏 `encoding="utf-8"` | Windows 默认 GBK 解码中文报错 | 读状态文件崩溃 |

---

## 4. 实验结果

### 4.1 第 1 局：LLM（我） vs BigMoney

- **结果**：LLM 27 VP : 27 VP BigMoney，**BigMoney 胜**（tiebreak：BigMoney 14 回合 < LLM 15 回合）。
- **我的策略**：Moneylender 清铜 + Village/Laboratory/Market 搭引擎 + 买 Gold 追钱 + 适时买 Province。
- **日志**：`projects/pyminion/llm_vs_bigmoney_log.jsonl`，共 29 条回合记录。

### 4.2 日志格式（JSONL，每行一个回合）

| 字段 | 说明 |
|---|---|
| `game_id` / `turn` / `player` | 第几局 / 第几回合 / 谁 |
| `starting_hand` / `deck` | 起手牌 / 牌库组成 |
| `actions_played` / `treasures_played` / `cards_bought` | 行动 / 财宝 / 购买 |
| `money_available` | 购买阶段可用金币 |
| `reasoning` | **LLM 的决策原因**（BigMoney 为空） |

---

## 5. 关键发现与教训

1. **BigMoney 是很强的基线**：纯买钱的贪心策略已经能打平「引擎 + trashing」的启发式 LLM 策略。
2. **引擎成型太慢**：本王国无 Chapel，Moneylender 一回合才废 1 铜，trashing 弱，等引擎「抽穿牌库」时 Province 已被买走一半。
3. **钱密度差距不可硬拼**：第 9 回合我方 0.85 vs BigMoney 1.14 时，「买 Laboratory 差异化」事后看偏慢，更合理的做法可能是先买 Gold 止损。
4. **日志的价值**：每手 reasoning 都留存，能精确指出「哪一步基于什么判断、为什么错」，比只看胜负有用。

---

## 6. 下一步

- [ ] **多局测试**：不同 seed 跑 N 局，算 LLM 对 BigMoney 的胜率（才是真正的「测试」）。
- [ ] **换对手**：BigMoneySmithy / ChapelBot / optimized_bot（在 `build_game` 加参数切换）。
- [ ] **换王国**：加入 Chapel 等强 trashing 卡，观察引擎策略是否更容易赢。
- [ ] **接真实 LLM API**：把 `ScriptedDecider` 换成「读模型输出」的 Decider，实现自动化对局。
- [ ] **日志分析脚本**：汇总每回合钱密度、$8 触发率、greening 时机。

---

## 附录：文件清单

| 文件 | 位置 | 说明 |
|---|---|---|
| `play.py` | `projects/pyminion/` | 人机对战驱动脚本 |
| `llm_game.py` | `projects/pyminion/` | LLM vs BigMoney 对局记录框架 |
| `play_state.json` | `projects/pyminion/` | 人机对战局的移动日志 |
| `llm_vs_bm_state.json` | `projects/pyminion/` | LLM vs BigMoney 当前局状态 |
| `llm_vs_bigmoney_log.jsonl` | `projects/pyminion/` | 第 1 局 29 回合完整记录 |
