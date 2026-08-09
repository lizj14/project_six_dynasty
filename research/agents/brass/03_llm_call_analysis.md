# Intelligent Board Games — LLM 调用时序分析

> 以 Brass Birmingham 对局为例，追踪所有 Gemini API 调用，分析 prompt 内容和决策流

---

## 一、调用全景图

### 阶段一：游戏初始化（每个 AI 玩家 1 次调用）

```
POST /api/games/create
│
├── AI Player 0: enhanced_learning.deep_learn_character() → Gemini ×1
├── AI Player 1: enhanced_learning.deep_learn_character() → Gemini ×1
├── AI Player 2: enhanced_learning.deep_learn_character() → Gemini ×1
└── AI Player 3: enhanced_learning.deep_learn_character() → Gemini ×1

总计: 4 次（4 AI 全自动对局）
```

**作用**: 将硬编码的角色 lore 文本（8-10 行英文描述）发给 Gemini，提取 Big Five 人格得分 + 决策权重。例如 Brass 的 lore：

```python
"brass_birmingham": {
    "default": [
        "Industrial entrepreneur in Victorian Birmingham during the Industrial Revolution",
        "Focused on building canal and rail networks across the Midlands",
        "Establishes cotton mills, coal mines, iron works, breweries, and potteries",
        "Strategic thinker who balances short-term profits with long-term infrastructure",
        ...
    ]
}
```

→ Gemini 返回 JSON: `{"personality": {"extraversion": 0.6, ...}, "decision_weights": {...}, ...}`

> 同时 `nano_banana_pro.train_character_personality()` 被触发但**不调 LLM**——只是把人格数字拼成 numpy 向量。

---

### 阶段二：每个 AI 回合（每次行动 10 次调用）

发生在 `POST /api/games/<game_id>/ai_turn`，是项目中 LLM 调用最密集的热路径。

```
execute_ai_turn()                              [app.py:453-540]
│
├─ ① character_mimicry.mimic_character_decision()
│     └─ Gemini ×1                            ◀── 实际采用的动作来源！
│
├─ ② nano_banana_pro.predict_action()
│     └─ 无 LLM                               ◀── NumPy 规则打分
│
├─ ③ decision_engine.process_turn()
│     └─ collective_reasoning.make_collective_decision()
│        ├─ society.generate_multi_perspective_reasoning()
│        │  ├─ Perspective 0 → Gemini ×1
│        │  ├─ Perspective 1 → Gemini ×1
│        │  ├─ Perspective 2 → Gemini ×1      } N=5 (SOCIETY_PERSPECTIVES)
│        │  ├─ Perspective 3 → Gemini ×1
│        │  ├─ Perspective 4 → Gemini ×1
│        │  └─ Synthesis/Debate → Gemini ×1
│        ├─ persona_system.generate_character_decision()
│        │  └─ Gemini ×1
│        └─ bias_masking.apply_bias_correction()
│           └─ Gemini ×1
│                                             ◀── 以上全部结果被丢弃！
│
└─ ④ character_mimicry.generate_character_dialogue()
      └─ Gemini ×1                            ◀── 纯装饰（前端显示台词）
```

---

## 二、核心 Prompt：mimic_character_decision（唯一有效的调用）

### Prompt 模板

```python
# character_mimicry.py:19-45
mimic_prompt = f"""You are EXACTLY {character_name} from {game_type}.

Your complete character profile:
Personality: {character_data.get('personality', {})}
Decision weights: {character_data.get('decision_weights', {})}
Risk tolerance: {character_data.get('risk_tolerance', 0.5)}
Cooperation level: {character_data.get('cooperation_level', 0.5)}
Signature phrases: {character_data.get('signature_phrases', [])}
Tactical preferences: {character_data.get('tactical_preferences', [])}
Behavior patterns: {character_data.get('behavior_patterns', [])}

Current game state:
{self._format_game_state(game_state)}

Available actions:
{self._format_actions(available_actions)}

Choose the action that {character_name} would EXACTLY choose.
Think as {character_name} would think.

Respond with JSON:
{{
    "action_id": "chosen action ID",
    "reasoning": "why {character_name} would choose this",
    "in_character_quote": "what {character_name} would say",
    "confidence": 0.0-1.0
}}"""
```

### 以 Brass 第 0 回合为例的完整 Prompt

```
You are EXACTLY default from brass_birmingham.

Your complete character profile:
Personality: {'extraversion': 0.6, 'agreeableness': 0.4, 'conscientiousness': 0.8,
              'neuroticism': 0.3, 'openness': 0.7}
Decision weights: {'economic': 0.9, 'military': 0.1, 'diplomatic': 0.4,
                   'aggressive': 0.3, 'defensive': 0.2}
Risk tolerance: 0.55
Cooperation level: 0.35
Signature phrases: ['Efficiency is the engine of progress', 'Time is money']
Tactical preferences: ['infrastructure', 'resource_management', 'long_term_investment']
Behavior patterns: ['plans_ahead', 'values_network_effects', 'opportunistic']

Current game state:
Turn: 0
Phase: canal

Players:
  - Alice
  - Bob
  - Charlie
  - Diana

Available actions:
1. ID: build_coal_birmingham
   Type: build
   Description: Build level 1 coal in birmingham for £10
   Cost: 10

2. ID: build_coal_coventry
   Type: build
   Description: Build level 1 coal in coventry for £10
   Cost: 10

3. ID: build_iron_birmingham
   Type: build
   Description: Build level 1 iron in birmingham for £10
   Cost: 10

... (通常 ~100 个可选动作)

98. ID: take_loan
    Type: loan
    Description: Take £30 loan (reduce income by 3)

99. ID: pass
    Type: pass
    Description: Pass turn

Choose the action that default would EXACTLY choose.
Think as default would think.

Respond with JSON:
{
    "action_id": "chosen action ID",
    "reasoning": "why default would choose this, using their thought process",
    "in_character_quote": "what default would say about this decision",
    "confidence": 0.0-1.0
}
```

---

## 三、游戏状态信息的严重缺失

### Brass `get_game_state()` 返回了

```python
{
    "turn": 0,
    "phase": "canal",
    "board": {                    # 16 城市 + 道路 + 市场
        "cities": {...},
        "canals": [], "rails": [],
        "coal_market": [...], "iron_market": [...]
    },
    "players": [{
        "name": "Alice",
        "money": 17,              # 金钱
        "income": 10,             # 收入等级
        "hand": [...],            # 手牌
        "industries": {...},      # 可建工厂
        "links": 10,              # 剩余道路
        "score": 0
    }, ...],
    "current_player": {...},
    "deck_remaining": 48
}
```

### `_format_game_state()` 实际展示了

```python
def _format_game_state(self, state):
    lines = []
    if 'turn' in state:
        lines.append(f"Turn: {state['turn']}")
    if 'phase' in state:
        lines.append(f"Phase: {state['phase']}")
    if 'current_player' in state:
        lines.append(f"Current player: {state.get('current_player', {}).get('name', 'Unknown')}")
    if 'players' in state:
        lines.append("\nPlayers:")
        for player in state['players']:
            lines.append(f"  - {player.get('name', 'Unknown')}")
    if 'resources' in state:              # ← Brass game_state 不返回此键！
        lines.append(f"\nResources: {state['resources']}")
    return "\n".join(lines)
```

**对比**：

| 字段 | Brass 返回了 | _format 展示了 |
|------|:--:|:--:|
| 回合号 | ✅ | ✅ |
| 阶段 | ✅ | ✅ |
| 当前玩家名 | ✅ | ✅ |
| 玩家名列表 | ✅ | ✅ |
| **board（地图、产业、道路）** | ✅ | ❌ |
| **players[].money（各玩家金钱）** | ✅ | ❌ |
| **players[].hand（手牌）** | ✅ | ❌ |
| **players[].industries（可建厂表）** | ✅ | ❌ |
| **players[].income（收入等级）** | ✅ | ❌ |
| **players[].score** | ✅ | ❌ |
| **players[].links（剩余道路）** | ✅ | ❌ |
| **deck_remaining** | ✅ | ❌ |

**LLM 做决策时可见的全部游戏状态信息**：

```
Turn: 0
Phase: canal
Players:
  - Alice
  - Bob
  - Charlie
  - Diana
```

### 这意味着什么

Gemini 做 Brass 决策时：

- ❌ 看不到地图——不知道城市在哪里、谁建了什么工厂、哪些道路已修
- ❌ 看不到自己有多少钱——build action 虽然有 cost，但不知道能否负担
- ❌ 看不到手牌——不知道有哪些卡可以出
- ❌ 看不到对手状态——不知道对手的经济/产业/策略
- ✅ 唯一的决策依据：**可用动作列表中的 ID、类型、描述、费用**

LLM 本质上是在**完全盲棋**状态下做选择——只根据角色的人格描述和一个看似合理的动作描述来猜测该做什么。这解释了为什么这个项目的 AI 没有任何棋力可言。

---

## 四、调用效率分析

### 总调用量（4 人局，~16 回合，每回合每人 2 动）

| 事件 | 调用次数 | 有效调用 | 浪费率 |
|------|:--:|:--:|:--:|
| 游戏初始化 | 4 | 4 | 0% |
| 每 AI 每次行动 | 10 | 1 | 90% |
| 完整一局 | **~1,284** | ~132 | ~90% |

### 调用时间线（单次 AI 行动）

```
0ms   ─┬─ mimic_character_decision ────→ Gemini (实际决策)
       │
       ├─ nano_banana_pro ────→ NumPy (<1ms)
       │
       ├─ society Perspective 0 ────→ Gemini
       ├─ society Perspective 1 ────→ Gemini
       ├─ society Perspective 2 ────→ Gemini   } 5 个并行？
       ├─ society Perspective 3 ────→ Gemini     (代码中是 for 循环串行!)
       ├─ society Perspective 4 ────→ Gemini
       ├─ society synthesis ────────→ Gemini
       ├─ persona decision ─────────→ Gemini
       ├─ bias correction ──────────→ Gemini
       │
       └─ generate_dialogue ────────→ Gemini
```

由于 Python `for` 循环 + `await` 是串行的，Society of Thought 的 6 次调用（5 视角 + 1 综合）是**顺序执行**的。加上其他 4 次调用，单次 AI 行动可能需要等待 **10 次串行的 API 往返延迟**。假设每次 Gemini 调用 2-3 秒，单个 AI 行动可能需要 20-30 秒。

---

## 五、与主流 LLM Game Agent 架构的对比

| 维度 | Intelligent Board Games | 合理的 LLM Game Agent |
|------|------------------------|----------------------|
| 每次行动 LLM 调用 | 10 次 | 1-2 次 |
| 有效调用率 | 10% | 100% |
| 游戏状态信息 | 几乎为空 | 完整传递（地图、资源、对手） |
| 多视角推理 | 串行 N+1 调用 | 单次 CoT / self-refine |
| 决策透明性 | 显示被丢弃的推理 | 直接显示实际决策的 reasoning |
| Token 效率 | ~90% token 浪费 | 每个 token 服务于决策 |
| 架构模式 | 装饰型——更多调用为了展示 | 务实型——最少调用完成决策 |

---

## 六、总结

Intelligent Board Games 的 LLM 调用架构有三个核心问题：

1. **信息瓶颈**：`_format_game_state()` 像一个过滤器，把 Brass 的游戏状态（地图/资源/经济/手牌）全部滤掉了。LLM 在几乎完全盲棋的状态下做决策。

2. **调用浪费**：每次 AI 行动触发 10 次 Gemini 调用，其中 9 次的结果被丢弃（仅用于前端展示"AI 的思考过程"）。这是一个 UX 驱动的设计——给人类玩家看的，不是让 AI 下好棋的。

3. **串行执行**：Society of Thought 的 6 次调用在 `for` 循环中顺序执行，导致单个 AI 行动的等待时间可能是必要的 10 倍。

这些设计选择的根源是项目的定位：它不是一个研究系统（验证什么方法更好），也不是一个竞技系统（让 AI 赢得更多），而是一个**展示系统**（让用户看到"AI 在思考"的视觉效果）。
