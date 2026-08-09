# Principality AI / MCP 深度解析

> 项目: Principality AI | 作者: Evan DeLord | 年份: 2025–2026
> GitHub: [github.com/edd426/principality_ai](https://github.com/edd426/principality_ai)
> 目标游戏: Dominion (Base Set, 25 张王国卡)
> 代码: 已 git clone 至 `projects/principality_ai/`，可直接运行

---

## 一、项目概述

Principality AI 是**目前唯一一个让 LLM 通过 MCP 协议直接玩 Dominion 的开源项目**。完整实现了 Dominion 基础版 25 张王国卡、CLI/Web/MCP 三种接口、双人对战支持、97%+ 测试覆盖率。

### 核心数据

| 指标 | 数值 |
|------|------|
| 代码规模 | ~6,700 行 TypeScript（5 个 packages） |
| MCP 工具数 | **6** (3 本地 + 3 Web 代理) |
| 王国卡 | **25** 张（1E / 2E / mixed 三种卡池） |
| 测试文件 | **100** 个 |
| 测试覆盖率 | 声称 97%+（有部分 broken tests） |
| LLM 支持 | Claude (Haiku/Sonnet/Opus) via Anthropic SDK + MCP |
| 规则 AI | Big Money（内置 baseline） |
| AI 对战路径 | CLI（仅 Big Money）、MCP Server（Claude Code 当玩家）、API Server（Anthropic SDK） |

### 动机

Dominion 的独特性质——卡牌构筑而非传统 TCG/CCG——使其成为 LLM Agent 的有趣测试平台。DeLord 将项目定位为 "solo-first"（单人沙盒优先），强调 AI 集成而非竞技对战。

---

## 二、整体架构

### 2.1 五包 Monorepo

```
principality_ai/
├── packages/
│   ├── core/              # 游戏引擎 (3,700 行)
│   ├── cli/               # 命令行界面
│   ├── mcp-server/        # MCP 集成 (~2,000 行)
│   ├── api-server/        # HTTP/WebSocket API
│   └── web/               # React Web UI (未完成)
├── docs/                  # 详尽文档
└── CLAUDE.md              # 开发者指南
```

### 2.2 三条交互路径

```
路径 A: CLI
  Human ──终端输入──► CLI ──RulesBasedAI──► GameEngine
  适用于: 本地快速对局，对手仅为 Big Money

路径 B: MCP Server (LLM 自主游戏)
  Claude Code ──MCP/stdio──► MCPGameServer ──► GameEngine
  适用于: Claude Code 作为玩家，通过对话操控游戏

路径 C: API Server (Web 对战)
  Browser ──HTTP/WS──► API Server ──Anthropic SDK──► Claude API
  适用于: Web UI 中 Human vs Claude AI 对战
```

### 2.3 关键组件关系

```
┌──────────────────────────────────────────────┐
│              GameEngine (core)                │
│                                              │
│  GameState (不可变)    PendingEffect (状态机)  │
│  getValidMoves()      executeMove()          │
│  RulesBasedAI (Big Money 基线)               │
└──────┬───────────────────────────────────────┘
       │
       ├──► CLI (PrincipalityCLI)
       │      - 交互式游戏循环
       │      - 多人模式: Player 1 = Human, Player 2+ = RulesBasedAI
       │      - 无 Claude API 集成
       │
       ├──► MCP Server (MCPGameServer)
       │      - game_session: 创建/结束/列出游戏
       │      - game_observe: 三级详细度状态查询
       │      - game_execute: 执行动作 + 自动回传状态
       │      - GameRegistryManager: 多局并发管理
       │
       └──► API Server
              - ClaudeAIStrategy: Anthropic SDK 调用
              - BigMoneyStrategy: fallback
              - AIService: 策略链 (Claude → Big Money)
```

---

## 三、MCP 设计深度解析

### 3.1 六个工具总览

| 工具 | 用途 | 关键设计 |
|------|------|----------|
| `game_session` | 游戏生命周期 (new/end/list) | 支持 seed、edition、numPlayers、kingdomCards |
| `game_observe` | 查询游戏状态 | **三级详细度** (minimal/standard/full) |
| `game_execute` | 执行动作 | **自动回传状态** + 可操作错误消息 |
| `web_game_create` | Web 游戏创建 | API Server 的 HTTP 代理 |
| `web_game_observe` | Web 游戏观察 | API Server 的 HTTP 代理 |
| `web_game_execute` | Web 游戏执行 | API Server 的 HTTP 代理 |

### 3.2 三级详细度设计 — Token 效率最佳实践

这是项目最值得学习的设计。根据 Anthropic MCP 最佳实践按需提供信息：

| 级别 | Token 消耗 | 内容 | 适用场景 |
|------|-----------|------|----------|
| **minimal** | ~60 | phase, turnNumber, activePlayer, gameOver, validMoves 摘要 | 确认"现在该谁动" |
| **standard** | ~250 | + 手牌分组、当前资源 (coins/actions/buys) | 简单决策 |
| **full** | ~1000 | + 完整供应堆、牌组统计、VP 计算 | 长线战略规划 |

```typescript
// 实现要点
const response = {
  phase: state.phase,
  turnNumber: state.turnNumber,
  gameOver: isGameOver(state),
};

if (detail_level === 'full') {
  response.supply = formatSupply(state);           // 所有供应堆
  response.state.stats = { handCount, deckCount, discardCount, victoryPoints };
}

// 合法动作始终返回，附带格式化命令字符串
response.validMoves = formatValidMoves(validMoves, detail_level);
// 例如: [{ command: "play_action Village", description: "Play action card: Village" }]
```

### 3.3 自动回传状态 — 减少 50% 调用

每次 `game_execute` 成功后，响应自动附带新游戏状态和合法动作列表：

```
LLM 典型决策循环:
  game_observe(full)  → 战略分析
  game_execute("play Village")  → 自动获得新状态 + 新合法动作  ← 无需再调 observe
  game_execute("play Smithy")   → 自动获得新状态 + 新合法动作
  game_execute("end")           → 自动获得新状态 + 新合法动作
  game_execute("buy Province")  → 自动获得新状态 + 新合法动作
```

### 3.4 PendingEffect 状态机 — 多步交互卡牌的统一建模

许多 Dominion 卡牌需要多步交互。引擎用一个 `PendingEffect` 统一建模：

```typescript
// Remodel 的两步交互
// Step 1: 打Remodel → engine设置 pendingEffect = { card: "Remodel", effect: "trash_for_remodel" }
// Step 2: LLM选择销毁目标 → engine设置 pendingEffect = { effect: "gain_card", maxGainCost: 6 }
// Step 3: LLM选择获取目标 → engine清除 pendingEffect

interface PendingEffect {
  card: CardName;          // 触发卡
  effect: string;          // 当前步骤标识
  maxTrash?: number;       // Remodel: 最大可获取费用
  maxGainCost?: number;    // Workshop: 最大可获取费用
  destination?: 'hand' | 'discard' | 'topdeck';
  // ... 更多状态字段
}
```

工作流：`executeMove()` → 检查 pending effect → `getValidMoves()` 只返回当前步骤合法动作 → LLM 做选择 → 可能设置下一步 pending effect 或清除。

MCP Server 通过 `pendingEffect.options` 把选项暴露为可复制的命令字符串：

```typescript
{
  pendingEffect: {
    card: "Remodel",
    effect: "gain_card",
    options: [
      { index: 0, description: "Gain Silver (cost 3)", command: "gain Silver" },
      { index: 1, description: "Gain Gold (cost 6)", command: "gain Gold" }
    ]
  }
}
```

### 3.5 错误恢复设计

`game_execute` 在出错时返回可操作的错误提示，LLM 可据此纠正：

```typescript
// 成功
{ success: true, gameState: {...}, validMoves: [...] }

// 失败
{
  success: false,
  error: {
    message: "Cannot buy Province: not enough coins (have 6, need 8)",
    suggestion: "Consider buying Gold (6 coins) or Silver (3 coins) instead."
  }
}
```

### 3.6 多局并发管理

`GameRegistryManager` 支持最多 10 局并发，1 小时 TTL 自动清理：

```typescript
class GameRegistryManager {
  private games: Map<string, ExtendedGameInstance>;
  private defaultGameId: string | null;

  createGame(seed, model, edition, numPlayers, kingdomCards): ExtendedGameInstance;
  getGame(gameId?): ExtendedGameInstance | null;  // 无参使用默认游戏
  endGame(gameId?): ExtendedGameInstance | null;
  // 每 5 分钟清理过期游戏
}
```

---

## 四、游戏引擎设计亮点

### 4.1 不可变状态 + 确定性随机

所有操作返回新状态对象，不修改原对象。种子可复现完整对局：

```typescript
const engine = new GameEngine('fixed-seed');
const state1 = engine.initializeGame(2, { edition: '2E' });
// 每次相同 seed 产生相同的王国卡选择和洗牌顺序
```

### 4.2 25 张王国卡全部实现

卡牌分为六大系统，覆盖了 Dominion 基础版全部机制：

| 系统 | 卡牌 |
|------|------|
| **抽牌/行动** | Village, Smithy, Laboratory, Market, Festival, Council Room, Cellar |
| **销毁** | Chapel, Remodel, Mine, Moneylender |
| **获取** | Workshop, Feast |
| **攻击** | Militia, Witch, Bureaucrat, Spy, Thief |
| **反应** | Moat |
| **特殊** | Throne Room, Adventurer, Chancellor, Library, Gardens |

### 4.3 版本区分

正确支持 1E / 2E / mixed 三种卡池：
- **2E**（默认）：替换了 6 张设计较差的一版卡（如 Adventurer → Harbinger）
- **1E**：原始基础版
- **mixed**：全部 25 张

---

## 五、双通道 LLM 集成

### 5.1 MCP 路径 — Claude Code 当玩家

这是**"真正的 LLM 玩游戏"路径**。Claude Code 通过 stdio 连接到 MCP Server，每次需要决策时：

1. 调用 `game_observe` 获取状态
2. 在自然语言中做战略推理
3. 调用 `game_execute` 执行动作
4. 从响应中自动获取新状态
5. 重复直到游戏结束

**优势**：Claude 的对话历史天然充当"日记"和"记忆"；不需要额外 API key；可以边玩边解释策略。

### 5.2 API 路径 — Anthropic SDK 直接调用

`ClaudeAIStrategy` 类调用 Anthropic SDK，system prompt 包含完整规则 + 策略指导 + JSON 响应格式：

```typescript
// ai-prompts.ts 的核心结构
buildSystemPrompt() {
  return `
    ## Game Rules (完整的 Dominion 规则)
    ## Strategy Guidelines (Province > Gold > 行动引擎)
    ## Response Format (JSON: { moveType, card, cards, reasoning })
  `;
}

buildUserPrompt(context) {
  return `
    ## Turn ${turnNumber} - ${phase} Phase
    **Your Hand**: Copper, Copper, Estate, Silver, Smithy
    **Resources**: 1 Action, 1 Buy, 2 Coins
    **Supply**: Province: 8, Gold: 28, ...
    **Valid Moves**: [play_action Smithy, play_treasure Copper, ...]
  `;
}
```

响应经过 `parseClaudeResponse()` 验证（提取 JSON → 验证 move 在合法动作列表中 → 返回 Move），失败则 fallback 到 Big Money。

---

## 六、完成度评估

### ✅ 已完成且稳定

- 游戏引擎：25 张王国卡、全部规则、版本区分
- MCP Server：6 个工具、三级详细度、自动回传状态、多局管理
- CLI：单人/双人、命令系统、连锁输入、pending effect 交互
- 测试：100 个测试文件，核心逻辑 97%+ 覆盖率
- 文档：README + CLAUDE.md + API 参考 + 最佳实践 + 架构文档

### ⚠️ 部分完成

- **LLM 对战**：MCP 路径可工作但需手动配置 `.mcp.json`；API 路径需 `ANTHROPIC_API_KEY`
- **Web UI**：React 代码存在但无测试，功能不完整
- **多人支持**：宣称 1-4 人但仅 2 人模式有充分测试

### ❌ 未实现

- 扩展包（Intrigue/Seaside 等）
- 策略学习/自适应
- 可视化界面
- 在线多人对战
- CI/CD 自动化

### 完成度总评

```
引擎规则完整性  ████████████████████░  95%
卡片效果覆盖    ████████████████████░  95%
MCP 协议实现    ███████████████████░░  90%
LLM 集成        ████████████████░░░░░  80%
测试覆盖        █████████████████░░░░  85%
Web UI          ██████░░░░░░░░░░░░░░░  30%
多人支持        ████████████░░░░░░░░░  60%

总体: 约 75% 完成度 — 核心可用，外围半成品
```

---

## 七、对六朝的启示

### 可直接复用的模式

| 模式 | 说明 |
|------|------|
| **三级详细度** | 六朝类似：局势报告分 minimal/standard/full |
| **自动回传状态** | 每次 execute 后自动返回新状态 + 新合法动作 |
| **PendingEffect 状态机** | 六朝的多步操作（战斗结算、事件链、卡牌发动）用同一模式建模 |
| **命令字符串预生成** | validMoves 附带可复制的命令，减少 LLM 格式错误 |
| **错误可操作提示** | 出错时给 suggestion，而非仅报错 |
| **不可变状态 + 种子** | 确保对局可复现，便于调试 AI 行为 |

### 需要增强的地方

| Principality 的局限 | 六朝的建议 |
|---------------------|-----------|
| 无多步前瞻/搜索 | 集成 MCTS 用于关键决策节点 |
| prompt 静态不变 | 用 Agents of Change 的 self-evolving prompt |
| LLM 无结构化记忆 | 引入 bounded-memory contract |
| 仅基础版卡牌 | 六朝卡牌更多，需更强的泛化策略 |
| 仅 2 人对战 | 六朝多人博弈需重新设计 MCP 工具 |
| CLI 无 LLM 集成 | 直接在 CLI 中集成 Claude/GPT |
