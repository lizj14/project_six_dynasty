# Bug 报告：风声鹤唳（jin 限定）被发给了北方玩家

> 来源：快模式 4 席测试（seed 20260818，`engine/play_claude_fast.py`）
> 状态：待排查修复
> 严重度：中（影响所有「仅限阵营」的事件/策略牌的发牌与结算）

## 一、现象

北方（north）玩家第 1 回合摸牌时，摸到了「风声鹤唳，草木皆兵」，并在手牌行动中打出了它。打出后：

| | 预期 | 实际 |
|---|---|---|
| 军力 | +7（5 → 12） | **不变（仍 5）** |
| 牌的去向 | 存档进史书区（history_area） | **进主弃牌区（main_discard）** |
| 史书区 | 增加 1 张 | **空** |

**复现路径**：
- seed=20260818，北方第 1 回合，card_play 决策打出「风声鹤唳，草木皆兵」（eligible index 7）
- move：`{"player":"north","type":"card_play","index":7,"payment":[2,5,1]}`
- 事后核对 [claude_state.json](engine/claude_run_fast/claude_state.json)：north `military` 仍 5、`history_names` 空、「风声鹤唳」出现在 `decks.main.discard`

## 二、根因

**「风声鹤唳，草木皆兵」是「仅限东晋玩家」的牌，北方玩家根本不应该摸到它。**

`versions/v1.0/cards/cards_compiled.json:6347` 中它的定义：

```json
{
  "card_id": "通用_风声鹤唳，草木皆兵_1",
  "name": "风声鹤唳，草木皆兵",
  "card_type": "event",
  "card_category": "event_military",
  "text": "获得7军力。存档此牌。",
  "parsed_effect": {
    "faction_restriction": "jin",   // ← 仅限东晋
    "blocks": [{ "ability_type": "strategy_action",
      "steps": [
        {"effect_type": "gain_military", "params": {"amount": 7}},
        {"effect_type": "archive_this"}
      ]}
    ]
  },
  "faction_restriction": "jin"
}
```

同效果的**北方版**是另一张牌「投鞭断流」（`cards_compiled.json:6380`），`faction_restriction: "north"`。北方本应摸到「投鞭断流」，而不是「风声鹤唳」。

### 两条 bug 链

1. **发牌/摸牌未按 faction 过滤**：主牌库（main deck）摸牌时，把 `faction_restriction="jin"` 的「风声鹤唳」发给了北方。北方持有/打出「仅限东晋」的牌，是第一层 bug。
2. **打出时的「安全网」把牌静默吞掉**：[engine/engine/actions/card_actions.py:108-120](engine/engine/actions/card_actions.py#L108-L120) 的 faction 检查：

```python
# === Faction restriction check ===
# ... This is the unified path for both normal play (safety net — agents never
# select restricted cards) and setup (cards pre-assigned may not match faction).
if not card.definition.is_playable_by(player.faction):
    state.main_discard.append(card)
    events.append({"type": "card_discarded", "card": card.name,
                   "reason": "faction_restriction"})
    ...
    return ActionResult.ok(events)
```

即：北方打出「风声鹤唳」→ `is_playable_by(north)` 返回 False → 牌被丢进 `main_discard`、`gain_military` / `archive_this` 都不执行。这正是「军力没加、牌进弃牌区」的直接原因。

注释明确假设了「agents never select restricted cards」——但这次子 agent（快模式）确实选中了，说明上游没过滤干净，安全网才被触发。

## 三、关键证据位置

| 内容 | 位置 |
|---|---|
| 风声鹤唳定义（faction_restriction=jin） | `versions/v1.0/cards/cards_compiled.json:6347` |
| 投鞭断流定义（faction_restriction=north，北方版） | `versions/v1.0/cards/cards_compiled.json:6380` |
| faction 检查（is_playable_by） | `engine/models/card.py:147-151` |
| 打出时 faction 安全网（吞牌） | `engine/engine/actions/card_actions.py:108-120` |
| 公共牌 faction 检查 | `engine/engine/actions/card_actions.py:278-281` |
| 摸牌/发牌逻辑 | 待定位（见下） |

## 四、建议排查方向

1. **摸牌/发牌入口**：定位北方从主牌库摸牌的函数（可能在下发 2 张回合摸牌、或 setup 初始手牌），确认摸到的牌是否按 `faction_restriction` 过滤。预期：北方只能摸到 `faction_restriction ∈ {None, "north"}` 的牌。
2. **可打出牌列表（eligible）生成**：`card_play` 的 eligible 是否也应过滤 `faction_restriction`。预期：北方的 eligible 里不应出现 `jin` 限定牌。
3. **安全网是否该更显式**：现在 faction 不符的牌被静默丢进 main_discard（日志 `reason="faction_restriction"`），既不加效果也不回退已支付的费用。确认这是否是预期行为，还是应该报错/告警（方便测试期发现）。

## 五、旁证（同类问题可能不止一张牌）

「风声鹤唳」和「投鞭断流」是同一效果（获得7军力+存档）的阵营双版，如果发牌未过滤，其余 `jin`/`north` 限定的牌也可能发错阵营（例如「幽州突骑」「凉州大马」「京口重镇」等带限定条件的策略牌）。建议修复后全量核查一次 `faction_restriction != null` 的牌的发牌路径。
