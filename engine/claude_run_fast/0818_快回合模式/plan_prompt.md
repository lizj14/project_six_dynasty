# 回合级规划 Prompt 模板

> 裁判（主 agent）在每回合开始，把下面内容发给对应席位的子 agent。`{...}` 为动态填充。

---

你是六朝何事中的【{seat}】。现在是第 {round} 回合，轮到你规划整回合行动。

## 你的状态
{state_summary}

## 可选行动（语义描述，供你规划参考）
{action_list}

## 任务

一次性规划你本回合的**完整行动序列**，输出 JSON：

```json
{
  "reasoning": "完整记录你的决策原因（供日志审计，不要只给结论）：①当前局面判断 ②候选方案及各自利弊 ③军力/手牌/费用预算怎么分 ④每一步的意图 ⑤最终选择这条路线的原因——尽量详细",
  "discard_order": ["牌A", "牌B", "【新手牌】", "牌C"],
  "plan": [
    {"type": "court_action", "card": "士卒"},
    {"type": "activate", "card": "姚苌"},
    {"type": "march", "target": "雍丘"},
    {"type": "occupy", "target": "雍丘", "use_sima": false},
    {"type": "play_card", "card": "邓羌", "payment": ["招抚", "王猛"]},
    {"type": "end_turn"}
  ]
}
```

## 硬性规则

1. **行动用语义，不用下标**：行动用 `type`（类型）+ 牌名/地点名表达。类型取值：`court_action` / `activate` / `march` / `occupy` / `fortify` / `play_card` / `play_public_card` / `recruit` / `convert` / `spread_culture` / `draw` / `end_turn`。

2. **多义必须准确返回，不许留歧义**：
   - 占据空地时，必须写 `use_sima`（`false`=用自己部队 / `true`=用司马家部队）。
   - 幕僚区满时打出幕僚牌，必须写 `replace`（替换哪张幕僚）。
   - 打出牌需要支付时，写 `payment`（支付牌名列表）。

3. **弃牌顺序（必填，且必须含【新手牌】）**：`discard_order` 是「先弃→后弃」的完整顺序，把最该弃的放前面、重要的放后面。**必须包含 `【新手牌】` 占位本回合新摸到、你计划时还没看到的牌**——如果漏了，新牌会默认被最后弃掉，可能不符合你的意图。

4. **规划要自洽**：军力每回合结束清空（算清每步军力）；手牌行动、牌组行动每回合各只能用一次（`activate` 主动技能不占这两个）；考虑你每步行动后局面的变化（比如进军后地点变空、才能占据）。
