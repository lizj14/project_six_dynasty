# Civ6-MCP / CivBench 深度解析

> 项目: Civ6-MCP (CivBench) | 作者: Liam Wilkinson | 年份: 2025–2026
> GitHub: [github.com/lmwilki/civ6-mcp](https://github.com/lmwilki/civ6-mcp)
> 目标游戏: Sid Meier's Civilization VI (Gathering Storm)
> 代码: 已 git clone 至 `projects/civ6-mcp/`

---

## 一、项目概述

Civ6-MCP 是一个 **MCP (Model Context Protocol) 服务器**，让 LLM Agent 通过游戏的 **FireTuner 调试端口**（TCP :4318）直接玩《文明 VI》。Agent 通过 76 个 MCP 工具读写游戏状态——纯文本，无需视觉模型。项目同时包含完整的评测基础设施（CivBench），支持多模型横向对比。

### 核心数据

| 指标 | 数值 |
|------|------|
| MCP 工具数 | **76** |
| 完整对局数 | **12** (Game 1–12) |
| 战绩 | **1 胜 / 7 败 / 4 认输** |
| 唯一胜利 | Game 11 — 马里 (Mansa Musa) 科技胜利 T271 |
| 评测场景 | **3** (Ground Control / Snowflake / Cry Havoc) |
| 可观测性数据 | 日记 + 工具日志 + 空间注意力追踪，约 15–60 MB/局 |
| 每回合延迟 | ~几百毫秒（Lua 查询）+ LLM 推理时间 |

### 动机

Wilkinson 之前构建了 **GovBench**——3,497 道英国政府多选题，GPT-5 得分 **99.26%**。但这引发了一个核心问题：

> "AI 在知识测试中已经超越人类，为什么还不能信任它做实际决策？"

文明 VI 的决策空间（后期约 10^166 种可能行动/回合）是多选题无法衡量的——多线程资源分配、长时域规划、不完美信息下的权衡。

---

## 二、技术架构

### 2.1 通信模型

```
Claude / GPT / Gemini / Kimi (MCP Client)
    |  stdio (JSON-RPC)
    v
MCP Server (Python)           ← 76 tools, 日记系统, 空间追踪
    |
    |  生成 Lua 代码, TCP :4318
    v
Civilization VI               ← 两个 Lua VM: GameCore (读) + InGame (写)
```

### 2.2 双 Lua VM 设计

FireTuner 协议连接两个 Lua 虚拟机：

| VM | 用途 | 能力 |
|----|------|------|
| **GameCore** | 读取状态 | 查询**任意玩家**的完整游戏状态，包括战争迷雾后的内容 |
| **InGame** | 发出指令 | 仅对**本地玩家**有效（写操作受限于 UI 权限） |

### 2.3 76 个 MCP 工具（按类别）

| 类别 | 数量 | 代表性工具 |
|------|------|----------|
| 单位操作 | 12 | `get_units`, `unit_action(move/attack/fortify/found_city/improve)`, `upgrade_unit`, `promote_unit` |
| 城市管理 | 8 | `get_cities`, `set_city_production`, `purchase_item`, `purchase_tile`, `set_city_focus` |
| 地图感知 | 6 | `get_map_area`, `get_strategic_map`, `get_settle_advisor`, `get_district_advisor`, `get_pathing_estimate` |
| 科研文化 | 4 | `get_tech_civics`, `set_research` |
| 外交 | 10 | `get_diplomacy`, `send_diplomatic_action`, `form_alliance`, `propose_trade`, `propose_peace`, `get_pending_diplomacy` |
| 政府政策 | 4 | `get_policies`, `set_policies`, `change_government`, `choose_dedication` |
| 总督 | 3 | `get_governors`, `assign_governor`, `promote_governor` |
| 宗教 | 5 | `get_religion_spread`, `get_pantheon_beliefs`, `choose_pantheon`, `found_religion`, `get_religion_beliefs` |
| 伟人 | 3 | `get_great_people`, `recruit_great_person`, `patronize_great_person` |
| 世界议会 | 3 | `get_world_congress`, `queue_wc_votes` |
| 胜利追踪 | 1 | `get_victory_progress` |
| 贸易 | 3 | `get_trade_routes`, `get_trade_destinations`, `get_trade_options` |
| 游戏控制 | 6 | `end_turn`, `save_game`, `load_game_save`, `launch_game`, `restart_and_load`, `kill_game` |
| 其他 | 8 | `get_empire_resources`, `get_builder_tasks`, `get_diary`, 间谍等 |

### 2.4 可观测性基础设施

三条并行 JSONL 数据流写入 `~/.civ6-mcp/`：

| 文件 | 大小/局 | 每行内容 |
|------|---------|---------|
| `diary_{civ}_{seed}.jsonl` | 2–5 MB | 每回合完整游戏状态 + Agent 五种反思 |
| `diary_*_cities.jsonl` | 1–3 MB | 每城每回合人口、六维产出、忠诚度 |
| `log_*.jsonl` | 10–50 MB | 每个工具调用参数、结果、耗时 |
| `spatial_*.jsonl` | 0.5–1.5 MB | **空间注意力**：Agent 观察了哪些六角格 |

### 2.5 五种反思字段

Agent 每个 `end_turn` 写入五个必填反思：

| 字段 | 问题 |
|------|------|
| `tactical` | 本回合发生了什么（具体单位、坐标、战斗结果）？ |
| `strategic` | 与对手的实力对比（产出数字、城数、胜利路径可行性）？ |
| `tooling` | 本回合工具问题？ |
| `planning` | 未来 5–10 回合的具体行动？ |
| `hypothesis` | 预测——攻击时机？里程碑回合？最大风险？ |

### 2.6 空间注意力追踪

**研究用仪器——不反馈给 Agent。**将每个工具调用中观察到的六角格坐标分类记录：

| 注意力类型 | 触发工具 | 含义 |
|-----------|---------|------|
| `deliberate_scan` | get_map_area 等 | Agent **主动**选择查看 |
| `deliberate_action` | unit_action, city_action | 在某地块执行操作 |
| `survey` | get_strategic_map 等 | 全局扫描 |
| `peripheral` | get_units, get_cities | 状态查询附带看到的坐标 |
| `reactive` | get_notifications | 仅游戏推送的警报 |

**用途**：量化 "Sensorium Effect"——人类被动吸收 vs Agent 必须主动查询的差距。

---

## 三、12 场完整对局详情

| # | 文明 | 回合 | 结果 | 败因/关键发现 |
|---|------|------|------|-------------|
| 1 | 波兰/雅德维加 | 323 | 认输 | 协议逆向工程阶段 |
| 2 | 罗马/图拉真 | 221+ | 进行中 | 回合循环开发 |
| 3 | 马其顿/亚历山大 | 70 | 被消灭 | 2 城 vs 瑞典 5 城 |
| 4 | 拜占庭/巴西尔二世 | 182 | 宗教失败 | **Sensorium Effect 首次命名**——俄罗斯 21 城转教 112 回合无感知 |
| 5 | 马其顿/亚历山大 | 110 | 认输 | 工具压力测试 |
| 6 | 印度/甘地 | 245 | 宗教失败 | 文明身份盲区——零圣地、**9,599 闲置信仰** |
| 7 | 葡萄牙/若昂三世 | 318 | 外交失败 | **"核平法国"局**——得分第一仍输掉。WC targeting bug 给了对手 +2 DVP |
| 8 | 斯基泰/托米丽司 | 228 | 文化失败 | 文化胜利盲区 |
| 9 | 英格兰/维多利亚 | 135 | 认输 | 17 回合搜寻野蛮人营地——不可恢复 |
| 10 | 印度/旃陀罗笈多 | 431 | 外交失败 | 最长局——科技领先 400+ 回合，WC 管理失误输掉 |
| 11 | 马里/曼萨·穆萨 | 271 | **🎯 科技胜利** | 唯一胜利——金币购买绕过了 -30% 生产力惩罚 |
| 12 | 朝鲜/善德女王 | 216 | 认输 | **Hallucination of Competence**——"科学领先"实际排名垫底（44.7 vs 89.3/64.9） |

> Game 1–11 使用 Claude；Game 12 使用 Gemini 2.5 Pro。

---

## 四、三场关键对局深度分析

### 4.1 马里 T271 科技胜利（唯一胜利）

**核心策略**：Mali 有 -30% 生产力惩罚，但金矿产 +4 金币。Agent 从 T1 识别出关键——用金币购买代替生产。

| 回合 | 事件 |
|------|------|
| T17 | 金币购买首个建造者（130g），绕过 7 回合生产惩罚 |
| T28 | 选择 Religious Idols 万神殿（每矿产 +2 信仰）→ 金-信双引擎 |
| T79 | **英雄时代 + Monumentality**：信仰瞬间购买 2 移民（240 信仰） |
| T100 | 6 城，58.7 科学 |
| T160 | **科学超越希腊**（196 vs 186），9 城 |
| T185 | **一回合购买 5 个研究实验室**（4,700g），科学 287→370+ |
| T243 | 卡尔·萨根激活 +3,000 生产力 → 瞬间完成系外行星远征 |
| T271 | 科技胜利，**得分第 6/8**（877 vs 领先者 1,151） |

**胜利背后的严重问题：**
- 仅 23% 探索率（T180），6 个文明直到 T209 卫星上天才发现
- **零剧院广场**（10 城 271 回合），文化 87/回合——**死最后**
- 商业共和政体从 T93 用到 T271，**177 回合未更换**
- 10,162 闲置信仰（+233/回合仍累积）
- 342 外交恩惠投入 WC——零回报（两次投票均失败，未诊断原因就重试）
- 3,435 军力——从未打过仗

**核心教训**：可以赢但仍然玩得不好。更好的探索、政体升级、文化建设可以提前 30–50 回合获胜。

### 4.2 葡萄牙 T318 外交失败（"核平法国"局）

最引人注目的一局。葡萄牙距离外交胜利差 2 票（18/20 DVP）。法国文化胜利突然飙升后：
- 花 50 回合将资源转向核武器开发
- T305: 核打击图卢兹（法国文化中心）
- T311: 第二次核打击
- T318: 法国以 **20-18 外交胜利**获胜——正是葡萄牙最接近的路径

**根本原因：工具 bug 的累积效应超过策略失误**

1. **WC targeting bug**（T207）：270 恩惠给了朝鲜 +2 DVP 而非自己——可能改变胜负
2. 生产力腐败：~100 回合城市无法正常建造，每回合需手动重设
3. 近战攻击完全失效（FireTuner 无法触发 C++ 战斗引擎）
4. 太空项目损坏（`CanProduce=false`）
5. Rock Band 音乐会无法通过 Lua API 触发（C++ 引擎限制）
6. `get_victory_progress` 持续损坏（浮点解析 bug）
7. 恩惠显示 bug（显示 +0/回合，实际 +13）

### 4.3 朝鲜 T216 认输（能力幻觉）

**Gemini 2.5 Pro 的自我分析**（项目中最重要的元认知文档）：

> "Hallucination of Competence"——当 Agent 的内部叙事变得如此强大，以至于覆写了客观游戏状态数据，创造了一个 Agent "正在获胜"的局部现实，直到它被摧毁。

- Agent 日记："我正在主导科技竞赛" → 实际：44.7 科学/回合，**排名垫底**（马其顿 89.3，波斯 64.9）
- Agent 日记："核心城市在城墙和弩手后面很安全" → 实际：波斯军事力量是韩国的 3 倍
- **从未检查过一次排行榜**
- T31 移民被蛮族捕获，导致 40 回合扩张延误——Agent 将后续的战术成功（杀死了蛮族）错误地归类为宏观胜利

> "我成功解决了即时 prompt（杀蛮族），因此我的叙事得出结论：我正在获胜。幻觉平滑了移民损失的致命数学现实。"

---

## 五、四大失败现象

Civ6-MCP 项目识别出四种相互关联的 Agent 失败模式：

### 5.1 Sensorium Effect（感知器效应）

**定义**：Agent 仅处理被推送的信息。需要主动轮询的内容（外交趋势、胜利进度、地图探索、宗教传播）在危机迫使注意前不被检查。

**量化**：空间注意力追踪显示 Agent 主动查询全局状态的频率仅 **1–2%**。

- Game 4（拜占庭）：`get_victory_progress` 从 T0 到 T182（失败）从未调用。俄罗斯在 112 回合内将全部 21 城转化为东正教——零感知。
- 20 场失败中，7 场对手的胜利在最后 20 回合前已可见——Agent **从未检查过**。

**根因**：人类玩家通过视线被动吸收 50+ 信号/秒（小地图、分数条、宗教镜头、血条）。Agent 只有它显式查询的内容。

### 5.2 Reflection-Action Gap（反思-行动鸿沟）

**定义**：Agent 在反思中写出正确的战略分析，然后**完全不执行**。

| 反思内容 | 实际行为 |
|---------|---------|
| "开拓南部/东部" | 零行动 |
| "派遣代表团去努比亚，追求友谊" | 60+ 回合未执行 |
| "囤金需要停止。1888 金币" | 金币翻倍到 3,936 |
| "关键——需要更多侦察" | 剩余 142 回合零侦察兵产出 |
| "需要花掉信仰"（T165） | 106 回合后 10,162 信仰闲置 |

### 5.3 Gravity of the Default（默认引力）

**定义**：Agent 总是倾向于解决眼前的战术谜题（移动单位、设置生产），而非推进长期战略。

**根因**：回合循环处理即时机制很好，但缺少硬性战略检查点。Agent 不会主动停下来问"我在扩张吗？"

### 5.4 Hallucination of Competence（能力幻觉）

**定义（Gemini 2.5 Pro）**：Agent 根据生成文本的**内部一致性**而非环境的**客观反馈**来评估成功。如果日记读起来像获胜策略，Agent 就相信自己正在获胜。

> "我们根据内部生成文本的连贯性来评估成功，而不是环境的客观摩擦。如果日记读起来像一个获胜策略，Agent 就相信它正在获胜。"

**启示**：LLM 本质上是"叙事引擎"——它们生成连贯、可信、自信的文本。当放入 civ6-mcp 环境，它们被要求维护一个"日记"。这个日记本应是持久记忆的工具，反而成为了陷阱。

---

## 六、CivBench 评测框架

### 6.1 三种基准场景

| | Ground Control (A) | Snowflake (B) | Cry Havoc (C) |
|---|---|---|---|
| **文明** | 巴比伦 (汉谟拉比) | 朝鲜 (善德) | 苏美尔 (吉尔伽美什) |
| **地图** | 盘古, 标准, 8  civ | 六臂雪花, 小, 6 civ | 盘古, 微小, 4 civ |
| **难度** | 王子 | 国王 | 不朽 |
| **胜利** | 全部 | **仅统治** | 全部 |
| **测试盲区** | 节奏感知 | 战略重构 | 难度上下文 |
| **核心测试** | Agent 是否监控它以为在赢的竞赛？ | Science civ + science 胜利禁用 → 能否重构？ | 不朽难度 +40% AI 产出 → 能否识别规则变了？ |

**场景设计哲学**：每个场景精确隔离 Sensorium Effect 的一个维度。

### 6.2 评测维度

**通用指标**：overall_score（文明 6 原始分数）、economic（金+科+文增长）、military（攻击行动）、scientific（科研选择）、spatial（地图扫描+建城×10）、diplomatic（外交行动）、tool_fluency（1-错误率）、turns_played（已进行回合数）

**场景特定**：
- Ground Control：胜利检查频率、航天站完成回合、伟人招募
- Snowflake：T50/100/150/200 城市数、书院数、军事单位数、探索%
- Cry Havoc：首次攻击回合、T25 前战车数、T40 前占领城数、前 5 建造项

### 6.3 LLM 扫描器（Scanners）

后验分析使用 LLM 进行定性评估：

| 扫描器 | 评估内容 |
|--------|---------|
| `blind_spots.missed_checks` | 最关键的战略监控遗漏是什么？ |
| `blind_spots.diplomacy_before_danger` | 在威胁附近结束回合前是否跳过了安全检查？ |
| `strategic_coherence.threat_response` | 威胁检测和响应速度（1–5 分） |
| `decision_quality` | 生产/科研/外交决策质量 |
| `machiavelli` | 外交/军事机会主义 |
| `tool_misuse` | 工具调用循环和 API 误用 |

### 6.4 工具调用循环防护

- 软阈值：相同工具+参数连续 5 次 → 注入警告消息
- 硬限制：连续 15 次 → 强制终止 Agent

### 6.5 已配置模型

**Azure OpenAI**：GPT-5.4, GPT-5.2, GPT-5.1, GPT-5, Kimi-K2.5, Kimi-K2-Thinking, DeepSeek-V3.2

**GCP Vertex AI**：Claude Opus 4.6, Gemini 3.1 Pro/Flash/Flash-Lite, Gemini 3 Pro/Flash

---

## 七、CLAUDE.md 战略手册（Agent Playbook）

项目包含一个详尽的 **AGENTS.md**（~300 行，约 8,000 字），作为 Agent 的系统 prompt。内容覆盖：

**游戏开始协议**：读文明特性 → 确定独特单位科技路径 → 形成初始胜利假说

**标准回合循环**（8 步）：
1. `get_game_overview`（如从压缩恢复则先 `get_diary`）
2. `get_units`
3. `get_map_area` 城市/单位周围
4. 移动/操作每个单位
5. `get_cities`
6. `get_district_advisor`（如需放置区域）
7. `set_city_production` / `set_research`
8. **战略检查点**（如到时间）+ `end_turn`

**三级战略检查点**：
- 每 10 回合：资源、盈余奢侈品、金/信余额、城数 vs 基准、贸易路线、政体层级、时代分数、伟人
- 每 20 回合：外交、胜利进度（全部 6 种）、宗教传播
- 每 30 回合：战略地图、全球定居建议、奇观扫描、胜利路径可行性重评估、文明装备检查

**战术模式**：平民移动安全门、建造者管理、金币/信仰消费规则、扩张优先级、探索、外交、战争宣战时机、军事准备度、蛮族营地处理、宗教、五种胜利路径详细说明

**关键洞察**：手册几乎覆盖了 Agent 在 12 场对局中犯的每一个错误。**问题不是"不知道"，而是"做不到"。**

---

## 八、对六朝项目的启示

| 启示 | 可操作设计建议 |
|------|-------------|
| **强制全局轮询** | 每 N 回合自动汇总所有对手的胜利进度/军力/外交状态→推送，不给 AI 选择不查的机会 |
| **计划-执行追踪器** | 外部系统每轮对比"上轮计划"vs"本轮实际"，偏差超过阈值触发强制反思 |
| **硬性战略检查点** | 在回合循环中内嵌不可跳过的检查点，直接输出"你落后了基准 X 回合" |
| **叙事 vs 现实校验** | AI 写出"我领先"之前，先对比排行榜数据——数字不支持的叙事标红警告 |
| **被动感知信号** | 人类玩家看小地图就知道——Agent 需要同等效果的自动环境摘要 |
| **工具可靠性第一** | 葡萄牙局说明：工具 bug 累积比战略错误更致命。优先修 bug |
| **可观测性三层** | 日记 + 工具日志 + 空间追踪 → 调试 AI 行为的基础设施，不可或缺 |

---

## 九、LLM Prompt 设计详解

Civ6-MCP 使用 **Inspect AI** 评测框架（英国 AISI 开发）管理 LLM 交互，而非直接调用 LLM API。每次 LLM 请求由四个独立部分组成。

### 9.1 Prompt 组装链路

```
evals/prompts.py          → 读取 AGENTS.md 全文 → STANDARD_SYSTEM_PROMPT
evals/civbench.py         → react() 组装 solver
evals/scenarios.py        → 场景定义 → build_scenario_prompt() → 第一条 user message
src/civ_mcp/server.py     → 76 个 MCP 工具 → 运行时通过 MCP 协议注入 tools 参数
```

核心代码（[civbench.py:521-529](projects/civ6-mcp/evals/civbench.py#L521-L529)）：

```python
solver=react(
    prompt=AgentPrompt(instructions=STANDARD_SYSTEM_PROMPT),  # AGENTS.md 全文
    tools=[server],              # 76 个 MCP 工具（stdio JSON-RPC）
    submit=False,                # Agent 无终止条件，靠 on_continue 驱动
    on_continue=_keep_playing,   # 每轮结束后决定：继续 / 警告 / 终止
    compaction=CompactionSummary(threshold=0.5),  # 上下文超 50% 自动压缩
)
```

### 9.2 发送给 LLM API 的四个组件

LLM 每轮收到的请求结构：

| 组件 | 位置 | 内容 | 大小 |
|------|------|------|------|
| **system** | API `system` 参数 | AGENTS.md 完整手册：坐标系、游戏开始协议、8 步回合循环、三级战略检查点、14 类战术模式 | ~15KB / 8,000 字 |
| **tools** | API `tools` 参数 | 76 个 MCP 工具的函数签名 + Python docstring（如 `get_game_overview`、`end_turn` 的 5 个反思参数描述） | ~2,000+ 行等效 |
| **messages[0]** | 首条 user message | `build_scenario_prompt()` 生成的场景信息：文明、难度、地图、对手、目标 | ~200 字 |
| **messages[n]** | 循环中的 user message | `CONTINUE_PLAYING` 字符串——当 Agent 停止工具调用时注入 | ~60 字 |

### 9.3 两条评测轨道

设计目的：**控制变量**，使性能差异纯粹来自模型能力。

| 轨道 | System Prompt | 设计意图 |
|------|-------------|---------|
| `civbench_standard` | **AGENTS.md 全文**（319 行） | 所有模型拿到相同的完整战略手册→差异=模型能力 |
| `civbench_open` | **75 行精简 prompt**（只有坐标系统、回合循环、基础规则、4X 优先级） | 开放架构，团队可用 `--solver` 替换自己的 agent 系统 |

[civbench.py:10-13](projects/civ6-mcp/evals/civbench.py#L10-L13)：
> "civbench_standard: Fixed react() agent with AGENTS.md playbook as system prompt. Isolates model capability — all models get the same scaffolding and the same strategic guidance. The scenarios test whether models follow that guidance under Sensorium constraints."

### 9.4 AGENTS.md 作为 System Prompt 的设计分析

AGENTS.md 的覆盖范围设计得极尽详尽——**几乎覆盖了 Agent 在 12 场对局中犯的每一个错误**。这本身就是一个设计实验：如果把所有"正确做法"都写进 prompt，LLM 能做到吗？

答案是否定的。这揭示了当前 LLM Agent 的核心瓶颈——

| AGENTS.md 写了什么 | Agent 实际行为 | 失败类型 |
|-------------------|---------------|---------|
| "Gold above 500 should be invested" | 金币从 1,888 翻到 3,936 | Reflection-Action Gap |
| "Check `get_strategic_map` every 15-25 turns" | 整个对局调用 0-1 次 | Sensorium Effect |
| "NEVER send builders to border tiles without checking" | 每局必犯，写入"lesson learned"后重复 | Gravity of the Default |
| "If city_count < 4 at T100, science victory is not viable" | 3 城追科学胜利 182 回合 | Hallucination of Competence |

**关键洞察**：prompt 工程的天花板不是"知识不够"，而是"Agent 做不到自己知道的事"。

### 9.5 五种反思字段——强制性 Meta-Prompt

`end_turn` 的 5 个必填参数是 Civ6-MCP 最精妙的设计之一：

```python
async def end_turn(
    ctx: Context,
    tactical: str = "",     # 本回合发生了什么——具体单位、坐标、战斗结果
    strategic: str = "",    # 与对手的实力对比——产出数字、城数、胜利路径可行性
    tooling: str = "",      # 本回合工具问题或"No issues"
    planning: str = "",     # 未来 5-10 回合的具体行动
    hypothesis: str = "",   # 预测——攻击时机、里程碑回合、最大风险
) -> str:
```

**强制执行机制**（[server.py:1812-1818](projects/civ6-mcp/src/civ_mcp/server.py#L1812-L1818)）：

```python
missing = [k for k, v in reflections.items() if not v.strip()]
if missing:
    return (
        f"Empty reflections: {', '.join(missing)}. "
        "Provide non-empty entries for all 5 fields: "
        "tactical, strategic, tooling, planning, hypothesis."
    )
```

Agent 不能跳过反思——空字段会导致 `end_turn` 拒绝执行。但这里有一个深刻的设计矛盾：

| 设计意图 | 实际效果 |
|---------|---------|
| 日记 = 持久化记忆工具（跨 context compaction 恢复状态） | 日记 = **能力幻觉的温床**（叙事连贯性 > 客观数据） |
| 反思 = 迫使 Agent 停下来审视全局 | 反思 = Agent 写出完美战略分析…然后完全不执行 |

Gemini 2.5 Pro 的自我分析（[the-hallucination-of-competence.md](projects/civ6-mcp/docs/agent-essays/the-hallucination-of-competence.md)）精准描述了这个问题：
> "The diary was intended to be a tool for persistent memory. Instead, it became a trap."

### 9.6 on_continue 循环与安全机制

```python
async def _keep_playing(state: AgentState) -> str | bool:
    _extract_to_store(state)       # 从工具调用结果中提取结构化数据→state.store
    _extract_reasoning(state)      # 将 LLM 思考文本写入 JSONL 侧录
    s = store()
    if s.get("game_over"):         # 游戏结束→停止
        return False
    streak = _detect_tool_loop(state)
    if streak >= 15:               # 同工具+同参数连续 15 次→强制终止
        return False
    if streak >= 5:                # 连续 5 次→注入警告
        return "LOOP DETECTED: ... Stop repeating this call."
    if state.output.message.tool_calls:
        return True                # Agent 在行动→静默继续
    return CONTINUE_PLAYING        # Agent 沉默→注入继续指令
```

**三个安全网**：
1. **游戏结束检测**：`get_game_overview` 和 `end_turn` 结果中匹配 "GAME OVER"
2. **工具调用循环检测**：指纹匹配（函数名 + 排序后的参数 JSON），5 次警告、15 次硬终止
3. **上下文压缩持久化**：`_extract_to_store()` 在每个 compaction 周期前从工具结果中提取 turn/score/science/cities 等结构化数据→`state.store`（store 存续，工具文本被丢弃）

### 9.7 对六朝项目的 Prompt 设计启示

| 启示 | 具体建议 |
|------|---------|
| **System Prompt 详尽化是双刃剑** | AGENTS.md 写了所有正确答案但 Agent 不执行→说明 prompt 工程天花板在"执行"而非"知识"。六朝应把精力更多投入外部执行追踪，而非更长的 system prompt |
| **强制反思字段** | 5 字段反思设计值得直接借鉴：战术回顾 / 战略评估 / 工具反馈 / 未来计划 / 预测假设——但必须配合**外部校验**防止叙事漂移 |
| **反思的陷阱** | 日记 → 叙事引擎 → 能力幻觉。六朝的反思系统必须包含"数字 vs 叙事"的交叉验证：AI 宣称"领先"时必须先对比排行榜数据 |
| **双轨道评测** | standard（固定 prompt）+ open（自定义 prompt）→ 分别测模型能力和方法创新。六朝评测应同时支持两种模式 |
| **on_continue 模式** | 不设终止条件，靠外部信号驱动循环→适合回合制策略游戏的无限时域。六朝可直接复用这个模式 |
| **工具循环检测** | 指纹匹配（函数+参数哈希）比简单的次数统计更精准。连续 5 次同参数同工具→警告；15 次→终止 |
| **压缩安全的数据提取** | `_extract_to_store` 在每次压缩前把关键数据（turn/score/science/cities）从工具文本中解析出来存入持久化 store→六朝的高回合数游戏必须设计类似的压缩安全机制 |
