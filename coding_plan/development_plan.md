# 六朝何事 — 电子化开发计划

## 一、项目概述

**项目名称**：六朝何事（Six Dynasties）桌游电子化

**目标**：将实体桌游的规则和卡牌数据完整数字化，构建一个可自动结算的游戏引擎，最终产出带 GUI 的桌面应用，支持：
- **真人操作**：每个玩家位可由真人操控
- **AI 对战**：AI 通过 LLM 大模型 + Agent 提示词做决策
- **测试用途**：快速迭代规则、验证平衡性
- **联机对战**：多人远程游戏

**技术选型**：Python（用户熟悉该语言）

---

## 二、当前进度总览

### 2.1 已完成模块（56 个 Python 文件）

| 模块 | 文件 | 状态 | 说明 |
|------|------|------|------|
| **数据模型** | `engine/models/` (5 文件) | ✅ 完成 | `card.py`, `player.py`, `game_state.py`, `enums.py`, `location.py` |
| **卡牌加载** | `engine/cards/loader.py` | ✅ 完成 | CSV → CardDef 加载 |
| **效果系统** | `engine/cards/effect_ast.py` | ✅ 完成 | 效果 AST 定义（EffectStep, AbilityBlock, Condition, Cost） |
| **效果解析** | `engine/cards/effect_parser.py` | ✅ 完成 | 将编译后的 JSON 效果解析为 AST |
| **效果执行** | `engine/cards/effect_resolver.py` | ✅ 完成 | 运行时执行效果 AST |
| **标记系统** | `engine/cards/tags.py` | ✅ 完成 | 标记（军事/文化/内政/权谋）管理 |
| **行动系统** | `engine/engine/action_system.py` | ✅ 完成 | 行动调度框架 |
| **卡牌行动** | `engine/engine/actions/card_actions.py` | ✅ 完成 | 打出卡牌的行动逻辑 |
| **快速行动** | `engine/engine/actions/quick_actions.py` | ✅ 完成 | 征兵/占地/加固等标准行动 |
| **特殊行动** | `engine/engine/actions/special_actions.py` | ✅ 完成 | 僭越等特殊行动 |
| **游戏主循环** | `engine/engine/game.py` | ✅ 框架 | 游戏主流程控制 |
| **阶段管理** | `engine/engine/phases.py` | ✅ 框架 | 准备阶段/行动阶段/回合结束等 |
| **游戏日志** | `engine/engine/game_logger.py` | ✅ 完成 | JSON 格式日志记录，支持回放 |
| **区域控制** | `engine/rules/area_control.py` | ✅ 完成 | 部分控制/完全控制判定与结算 |
| **计分系统** | `engine/rules/scoring.py` | ✅ 框架 | VP 获取、终局计分 |
| **目标系统** | `engine/rules/goals.py` | ✅ 完成 | 目标牌判定 |
| **司马家** | `engine/rules/sima.py` | ✅ 完成 | 司马家军力/VP 机制 |
| **僭越系统** | `engine/rules/usurp.py` | ✅ 完成 | 僭越判定与执行 |
| **君主系统** | `engine/rules/emperor.py` | ✅ 完成 | 君主牌/任务机制 |
| **AI 接口** | `engine/ai/interface.py` | ✅ 完成 | AI 抽象接口定义 |
| **Dummy AI** | `engine/ai/dummy_ai.py` | ✅ 基础 | 简单随机 AI，用于测试 |
| **版本管理** | `engine/config/version.py` | ✅ 完成 | 多版本规则/卡牌/地图加载，`rules.toml` 特性开关 |
| **卡牌编译** | `engine/scripts/compile_cards.py` | ✅ 完成 | CSV → cards_compiled.json |
| **测试** | `engine/tests/` (14 文件) | ✅ 基础覆盖 | 模型/行动/规则/卡牌的单元测试 |

### 2.2 v1.0 版本数据

| 文件 | 状态 | 说明 |
|------|------|------|
| `versions/v1.0/cards/card_design.csv` | ✅ 有数据 | 卡牌设计主表 |
| `versions/v1.0/cards/card_goal.csv` | ✅ 有数据 | 目标牌 |
| `versions/v1.0/cards/card_emperor.csv` | ✅ 有数据 | 君主牌 |
| `versions/v1.0/cards/cards_compiled.json` | 🔧 校对中 | 编译后的卡牌 JSON，正在逐卡校对效果表达 |
| `versions/v1.0/map/map_adjacency.yaml` | ✅ 有数据 | 地图邻接关系 |
| `versions/v1.0/rules.toml` | ✅ 完成 | 规则参数与特性开关 |

---

## 三、架构概览

```
project_six_dynasty/
├── engine/                        # 游戏引擎（纯 Python）
│   ├── models/                    # 数据模型层
│   │   ├── card.py                #   卡牌定义 (CardDef, CardLibrary)
│   │   ├── player.py              #   玩家状态
│   │   ├── game_state.py          #   全局游戏状态
│   │   ├── location.py            #   地点/地图
│   │   └── enums.py               #   枚举定义
│   ├── cards/                     # 卡牌系统
│   │   ├── loader.py              #   卡牌加载器
│   │   ├── effect_ast.py          #   效果 AST 节点定义
│   │   ├── effect_parser.py       #   JSON → AST 解析
│   │   ├── effect_resolver.py     #   AST 运行时执行
│   │   └── tags.py                #   标记（军事/文化/内政/权谋）
│   ├── engine/                    # 引擎核心
│   │   ├── game.py                #   游戏主循环
│   │   ├── phases.py              #   阶段管理
│   │   ├── action_system.py       #   行动调度
│   │   ├── game_logger.py         #   JSON 日志记录
│   │   └── actions/               #   具体行动实现
│   │       ├── base.py            #     行动基类
│   │       ├── card_actions.py    #     卡牌行动
│   │       ├── quick_actions.py   #     快速行动（征兵/占地/加固）
│   │       └── special_actions.py #     特殊行动（僭越等）
│   ├── rules/                     # 规则系统
│   │   ├── area_control.py        #   区域控制
│   │   ├── scoring.py             #   计分
│   │   ├── goals.py               #   目标牌
│   │   ├── sima.py                #   司马家军力
│   │   ├── usurp.py               #   僭越
│   │   └── emperor.py             #   君主任务
│   ├── ai/                        # AI 系统
│   │   ├── interface.py           #   AI 抽象接口
│   │   └── dummy_ai.py            #   简单随机 AI
│   ├── config/
│   │   └── version.py             #   版本管理
│   ├── scripts/
│   │   └── compile_cards.py       #   CSV → JSON 编译
│   └── tests/                     # 测试
│       ├── test_models/           #   模型测试 (4 文件)
│       ├── test_actions/          #   行动测试 (4 文件)
│       ├── test_cards/            #   卡牌测试 (1 文件)
│       ├── test_game/             #   游戏循环测试 (1 文件)
│       └── test_rules/            #   规则测试 (4 文件)
├── versions/                      # 版本数据
│   └── v1.0/
│       ├── cards/                 #   卡牌 CSV + compiled JSON
│       ├── map/                   #   地图邻接关系
│       └── rules.toml             #   规则参数 & 特性开关
├── logs/                          # 游戏日志输出
├── coding_plan/                   # 开发计划（本文档）
├── rulebook.md                    # 规则书
├── conclusion.md                  # 测试结论与设计思考
└── board_info.md                  # 版图信息
```

---

## 四、待完成工作

### 4.1 高优先级 — v1.0 卡牌数据校对

**当前状态**：`cards_compiled.json` 已从 CSV 编译生成，但效果的结构化表达存在大量问题。

**具体问题清单**（来自 vibe_coding 会话中逐卡审查）：

| 类别 | 问题 | 涉及卡牌示例 |
|------|------|-------------|
| **效果遗漏** | 卡牌文本中的效果在 JSON 中缺失 | 谢道韫（缺少第2项 trigger 的 2VP）、郗鉴（转文化效果缺少 1VP+1牌）、姚苌（缺少 play_condition） |
| **效果多余** | JSON 中有不应存在的效果 | 角色牌登场效果中的"获得VP"（应删除） |
| **结构错误** | 效果结构不合理/冗余 | `usurp_steps` vs `steps`（应统一）、`sub_effect` 不必要的使用、`is_friend` 与 `card_type: friend` 重复 |
| **字段缺省值** | 默认值未省略导致 JSON 冗余 | `gain_vp` 的 `variable=false`、`draw_cards` 的 `amount=1` 不应输出 |
| **trigger 不准确** | always trigger 被滥用 | 部分被动效果应为具体 trigger（如 `on_archive`、`on_usurp`） |
| **靶向表达** | 目标选择逻辑不精确 | 谢安的 convert 使用了 `target_desc` 字符串而非结构化 `filter_dict`、涪陵的"选择对方玩家"缺少 `exclude_self` |
| **条件表达** | 条件/限制未结构化 | "幕僚有空位"用了 `staff_has_space` 而非比较表达式 |
| **费用表达** | 支付费用的结构不统一 | 加官进爵 vs 涪陵 —— 一个用 `costs` 数组，一个用 `pay_military` |
| **文本残留** | raw_text 中包含已结构化的信息 | 多张牌的 `source_text` 中保留了应转为结构化参数的信息 |
| **角色初始值** | 英雄牌的初始军力/威望/顺位不完整 | 多个角色缺少初始值，或等第值设为 0 |

**工作计划**：
1. 逐卡检查 `cards_compiled.json`，确保每张卡的效果完整且结构正确
2. 统一效果表达规范（见下方 4.2）
3. 修复所有已知问题
4. 写自动化校验脚本，检查 JSON 常见错误

### 4.2 高优先级 — 卡牌效果表达规范化

制定一份 **卡牌 JSON Schema 规范文档**，统一以下方面：
- `effect_type` 的完整枚举及参数定义
- `trigger` 的合法值（`on_play`, `on_archive`, `on_march`, `on_usurp`, `on_turn_start`, `on_turn_end`, `always` 等）
- `condition` 的结构化表达规范
- `target` 的结构化表达规范（`choose`, `all`, `self`, `opponent` 等）
- `costs` 的统一格式
- 默认值省略规则

### 4.3 中优先级 — 游戏引擎完善

| 任务 | 说明 |
|------|------|
| **游戏循环完善** | `game.py` 中部分阶段逻辑仍有空白，需要填完完整的主循环 |
| **阶段流转** | `phases.py` 中的所有阶段类型要实现完整的进入/执行/退出逻辑 |
| **朝堂行动** | 候选策略牌的选取/征发机制 |
| **摸牌阶段** | 牌库顶摸牌 vs 展示区摸牌的 3 选 1 逻辑（当前展示区特性已关闭） |
| **DBG 牌组操作** | trash（删除）、检索、洗回牌库等操作 |
| **被动效果触发** | 全局被动效果的注册与触发框架 |
| **事件牌结算** | 强制事件牌的特殊结算流程 |
| **文化传播** | 传播文化的完整结算（放置文化标记、获得VP、贡献度） |
| **终局计分** | 完整的终局 VP 汇总（区控 + 文化 + 目标牌 + 存档区） |
| **北伐标记** | 北伐标记的获取与顺位提升 |

### 4.4 中优先级 — AI 系统

| 任务 | 说明 |
|------|------|
| **Dummy AI 增强** | 当前只做最基础动作（摸牌/打牌），需要能执行完整的回合操作 |
| **LLM AI 实现** | 基于 `interface.py` 实现 LLM AI，调用大模型 API 做决策 |
| **游戏状态摘要** | 将 `GameState` 转为 LLM 可理解的文本/JSON 描述 |
| **Agent 提示词** | 设计提示词模板，引导 LLM 做出合理决策 |
| **多级 AI** | 支持不同难度/风格的 AI（激进/稳健/文化路线等） |

### 4.5 中优先级 — 测试覆盖

| 任务 | 说明 |
|------|------|
| **效果解析测试** | 覆盖所有 `effect_type` 的解析 |
| **效果执行测试** | 覆盖所有 `effect_type` 的执行 |
| **集成测试** | 完整 4 人游戏的自动化测试 |
| **平衡性测试** | 大批量 AI vs AI 自动对局，统计胜率 |

### 4.6 低优先级 — GUI & 联机

| 任务 | 说明 |
|------|------|
| **GUI 框架选型** | 评估 PySide6 / Dear PyGui / Web 前端 |
| **GUI 实现** | 版图、手牌、玩家面板、日志的 UI |
| **网络层** | 联机对战协议设计 |
| **服务器** | 房间管理、状态同步 |

---

## 五、里程碑规划

### M1：引擎可运行（当前阶段） 🔧
- [x] 数据模型完整
- [x] 卡牌加载 & 效果系统
- [x] 基础行动系统
- [x] 规则系统
- [x] Dummy AI 可运行完整游戏
- [ ] **卡牌效果 JSON 校对完毕**（当前主要阻塞项）
- [ ] 游戏主循环无断点可完整运行

### M2：规则完整
- [ ] 所有阶段流转正确
- [ ] DBG 操作完备
- [ ] 被动效果触发框架
- [ ] 终局计分准确
- [ ] 文化传播完整
- [ ] 单元测试覆盖率 > 60%

### M3：AI 可用
- [ ] LLM AI 可接入并做出合理决策
- [ ] 批量自动化测试可运行（N 局 AI vs AI）
- [ ] 游戏日志可回放分析

### M4：可玩原型
- [ ] GUI 可操作
- [ ] 真人可在 GUI 中完成一局游戏
- [ ] 支持人机对战

### M5：联机版本
- [ ] 网络对战
- [ ] 房间系统
- [ ] 版本自动匹配

---

## 六、当前阻塞

1. **卡牌 JSON 校对** — 这是当前最耗时的任务，vibe_coding 会话中已发现 ~30+ 张卡牌存在问题，需要逐卡检查修复
2. **效果表达规范未定型** — 部分效果的表达方式仍在探索中（如靶向选择、条件表达），需要在修卡过程中逐步沉淀规范

---

## 七、文件约定

- **规则修改**：修改 `versions/v1.0/rules.toml`，不改引擎代码
- **卡牌修改**：修改 `versions/v1.0/cards/*.csv`，然后运行 `compile_cards.py` 重新生成 JSON
- **地图修改**：修改 `versions/v1.0/map/map_adjacency.yaml`
- **新版本**：复制 `versions/v1.0/` → `versions/v2.0/`，修改后通过 `Version.load("v2.0")` 加载
- **日志输出**：游戏日志写入 `logs/` 目录
- **规则参考**：`rulebook.md` 为权威规则书

---

> 最后更新：2026-07-05
> 基于 vibe_coding 会话（6518 行对话）的实际产出整理
