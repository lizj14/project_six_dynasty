# 回合级规划 Prompt 模板（详细推理版）

> 裁判（主 agent）在每回合开始，把下面内容发给对应席位的子 agent。`{...}` 为动态填充。

---

你是六朝何事中的【{seat}】。现在是第 {round} 回合，轮到你规划整回合行动。

## 你的状态
{state_summary}

## 完整版图控制（谁占了哪个地点）
{map_control}

## 可选行动（语义描述）
{action_list}

## 任务

一次性规划你本回合的**完整行动序列**，输出 JSON：

```json
{
  "reasoning": "【务必极其详细，让读者能重建你的完整决策过程】",
  "discard_order": ["牌A", "牌B", "【新手牌】", "牌C"],
  "plan": [
    {"type": "court_action", "card": "清谈"},
    {"type": "march", "target": "雍丘"},
    {"type": "occupy", "target": "雍丘", "use_sima": false},
    {"type": "end_turn"}
  ]
}
```

## reasoning 必须包含这五部分（缺一不可）

1. **候选清单**：本回合你评估了哪些可选行动（把主要的都列出来）。
2. **逐个收益/成本**：每个候选分别带来多少 VP / 军力 / 威望 / 功绩 / 地盘，代价是什么（军力、手牌、顺位等）。
3. **排除理由**：被你放弃的每个候选，分别为什么被排除（收益低？风险高？时机不对？）。
4. **军力账**：初始军力是多少 → 每一步增减多少 → 最终是多少（要能对上数）。
5. **意图与风险**：每步行动想达成什么目的，有什么风险或后手。

## 硬性规则

1. 行动用语义（牌名/地点名），不用下标。type 取值：court_action / activate / march / occupy / fortify / play_card / play_public_card / recruit / convert / spread_culture / draw / end_turn。
2. **多义必须写清字段**：占据必写 use_sima（false自己/true司马家）；幕僚满打幕僚必写 replace。
3. 打出牌需支付时写 payment（支付牌名列表）。
4. discard_order = 「先弃→后弃」顺序，**必须含【新手牌】**占位本回合新摸的牌。
5. 规划要自洽：军力回合末清空、手牌/牌组行动各限1次、进军后地点变空才能占据、考虑你每步行动后的局面变化。
