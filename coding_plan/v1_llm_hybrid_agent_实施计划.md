# 六朝 L1 对局 Agent v1 — 实施计划

> LLM 战略分析 + Beam Search 行动生成 | 2026-08-01

---

## 一、v1 范围与目标

### 1.1 做什么

- L1 对局 Agent：能接入 GameEngine，完成完整对局
- 架构：**LLM Agent 分析 + Beam Search 行动生成**
- 输入：规则书 + 牌表 + 当前玩家的游戏视图
- 输出：合法的 Action（通过 GameAgent 接口返回给引擎）

### 1.2 不做什么（留到 v2+）

- L2（赛后分析）、L3（规则建议）
- 自对弈训练、价值网络
- 多玩家建模的精细调优
- 性能极致优化（先跑通对局）

### 1.3 设计原则

1. **利用引擎现有能力**：SnapshotViewport、GameAgent 接口、ActionSystem、EffectResolver 均已可用，不重写
2. **手工规则 + LLM 推理，零训练**：v1 不做任何模型训练
3. **先跑通，再调优**：v1 目标是完成对局，v2 才做胜率优化

---

## 二、总体架构

### 2.1 数据流

```
┌─────────────────────────────────────────────────────────────────┐
│                        L1Agent                                   │
│                                                                  │
│  引擎回调              Agent 内部处理                  引擎      │
│  ────────            ──────────────                  ──────     │
│                                                                  │
│  decide_action() ──→ 判断是否需要新一轮战略分析                   │
│         │                   │                                    │
│         │            ┌──────┴─────── 每回合首次调用 ─────┐       │
│         │            │  StateEncoder.encode(state)       │       │
│         │            │  + RuleBook (规则书摘要)           │       │
│         │            │  + CardTable (牌表摘要)            │       │
│         │            │       ↓                           │       │
│         │            │  LLMAnalyzer.analyze_round()      │       │
│         │            │       ↓                           │       │
│         │            │  DirectiveValidator.validate()    │       │
│         │            │       ↓                           │       │
│         │            │  DirectiveCache.set(directive)    │       │
│         │            └───────────────────────────────────┘       │
│         │                   │                                    │
│         │            ┌──────┴─────── 每次行动调用 ──────┐        │
│         │            │  判断决策类型:                     │        │
│         │            │                                   │        │
│         │            │  常规行动 → HeuristicExecutor     │        │
│         │            │   用 directive 的权重调整打分      │        │
│         │            │                                   │        │
│         │            │  朝堂选牌 → BeamSearchPlanner     │        │
│         │            │   CourtAction 在候选列表中时       │        │
│         │            │                                   │        │
│         │            │  关键决策 → LLMAnalyzer           │        │
│         │            │  僭越 / 终局触发 / 异常打断       │        │
│         │            └───────────────────────────────────┘        │
│         │                   │                                    │
│  ←── return Action ←───────┘                                    │
│                                                                  │
│  make_choice() ──→ HeuristicExecutor.choose()                    │
│  select_target() → HeuristicExecutor.target()                    │
│  choose_discards() → HeuristicExecutor.discard()                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 模块结构

```
engine/ai/llm_hybrid/           ← 新建包
├── __init__.py
├── agent.py                    ← L1Agent (GameAgent 实现)
├── state_encoder.py            ← 状态 → Markdown 渲染
├── llm_analyzer.py             ← LLM 调用 + 结构化输出
├── beam_planner.py             ← Determinized Beam Search
├── heuristic_executor.py       ← 启发式行动选择（带动态权重）
├── evaluator.py                ← 局面评估函数（Beam Search + Executor 共用）
├── directive.py                ← StrategicDirective 数据类
├── validator.py                ← LLM 输出校验
├── cache.py                    ← 战略指令缓存
├── view_provider.py            ← 游戏视图封装
├── knowledge.py                ← 规则书 + 牌表加载
├── simulator.py                ← 轻量前向模拟封装
└── prompts/                    ← Prompt 模板
    ├── system_analyst.md       ← 系统提示词
    ├── round_analysis.md       ← 回合战略分析
    └── critical_decision.md    ← 关键决策分析
```

---

## 三、逐模块设计

### 3.1 `directive.py` — 数据结构

```python
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class StrategicDirective:
    """LLM 产出的结构化战略指令"""

    round_number: int
    round_goal: str                           # "军事扩张" | "文化推进" | "牌组构筑" | "防守待机" | "混合"
    reasoning: str                            # 自然语言解释（给 L2/L3 用）

    # 行动优先级（排序 = 权重递减）
    priority_action_types: List[str] = field(default_factory=list)
    # 例: ["march", "occupy", "court_action", "play_card", "recruit", "draw"]

    # 关键位置（本回合优先推进/占领的区域名）
    key_locations: List[str] = field(default_factory=list)

    # 偏好朝堂牌（牌名列表，Beam Search 中加分）
    preferred_court_cards: List[str] = field(default_factory=list)

    # 禁止行动（LLM 认为绝对不该做的，校验层也会自动补充）
    forbidden_actions: List[str] = field(default_factory=list)

    # 可选: 动态权重覆盖
    weight_overrides: Optional[dict] = None
    # 例: {"march": 2.0, "occupy": 1.5, "draw": 0.5}  ← 覆盖默认权重
```

### 3.2 `cache.py` — 缓存

```python
class DirectiveCache:
    """缓存当前回合的战略指令，避免重复调用 LLM"""

    def __init__(self):
        self._directive: Optional[StrategicDirective] = None
        self._round: int = -1

    def is_valid_for(self, current_round: int) -> bool:
        """判断缓存是否仍有效（同回合内复用）"""
        return self._directive is not None and self._round == current_round

    def get(self) -> StrategicDirective:
        return self._directive

    def set(self, directive: StrategicDirective):
        self._directive = directive
        self._round = directive.round_number

    def invalidate(self):
        """当发生重大意外事件时（如被僭越），强制下次重新分析"""
        self._directive = None
```

### 3.3 `view_provider.py` — 视图封装

```python
class GameViewProvider:
    """
    封装 SnapshotViewport，提供按当前玩家的可见性过滤的游戏视图。

    引擎已有的 SnapshotViewport 已经处理了可见性规则（对手手牌隐藏、
    牌库只暴露数量等）。这个类在它的基础上做结构化提取。
    """

    def __init__(self, state: GameState, viewer_id: str):
        self.viewport = create_viewport(state, viewer_id, mode="snapshot")
        self.viewer_id = viewer_id

    # ── 顶层结构化视图 ──

    def get_player_view(self) -> dict:
        """当前玩家的完整可见状态"""
        return {
            "player_name": self.viewport.get_player_name(self.viewer_id),
            "hero": self._hero_summary(),
            "resources": self._resource_summary(),
            "hand": self._hand_summary(),
            "staff": self._staff_summary(),
            "army_reserve": self._army_reserve_summary(),
            "faction": self._faction_summary(),
        }

    def get_public_view(self) -> dict:
        """所有玩家可见的公共状态"""
        return {
            "round": self.viewport.get_round_number(),
            "map": self._map_summary(),
            "culture_tracks": self._culture_summary(),
            "court": self._court_summary(),
            "public_actions": self._public_actions_summary(),
            "emperor_dice": self._emperor_summary(),
            "goals": self._goals_summary(),
        }

    def get_opponent_view(self) -> dict:
        """对手信息（只有可见部分）"""
        opponents = []
        for pid in self.viewport.get_all_player_ids():
            if pid != self.viewer_id:
                opponents.append({
                    "name": self.viewport.get_player_name(pid),
                    "hero": self.viewport.get_player_hero(pid),
                    "vp": self.viewport.get_player_vp(pid),
                    "prestige": self.viewport.get_player_prestige(pid),
                    "merit": self.viewport.get_player_merit(pid),
                    "hand_count": self.viewport.get_player_hand_count(pid),
                    "controlled_regions": self.viewport.get_player_regions(pid),
                    "army_positions": self.viewport.get_player_army_positions(pid),
                    "played_cards": self.viewport.get_player_played_cards(pid),
                })
        return opponents

    # ── 子视图（供 StateEncoder 组合使用，以下为部分示例） ──

    def _resource_summary(self) -> dict:
        p = self.viewport._state.get_player(self.viewer_id)
        return {
            "vp": p.vp,
            "military": p.military,
            "hand_count": len(p.hand),
            "prestige": p.prestige,
            "merit": p.merit,
            "prestige_rank": self.viewport.get_prestige_rank(self.viewer_id),
            "merit_rank": self.viewport.get_merit_rank(self.viewer_id),
        }

    def _hand_summary(self) -> list:
        return [
            {"name": c.name, "type": c.card_type.value, "cost": c.cost,
             "effect_summary": c.effect_text[:80]}
            for c in self.viewport._state.get_player(self.viewer_id).hand
        ]

    def _map_summary(self) -> list:
        regions = []
        for r in self.viewport._state.regions:
            regions.append({
                "name": r.name,
                "controller": r.controller,
                "vp_value": r.vp_value,
                "culture_markers": r.culture_markers,
                "armies": {pid: count for pid, count in r.armies.items() if count > 0},
                "adjacent": [adj.name for adj in r.adjacent_regions],
            })
        return regions

    def _court_summary(self) -> list:
        faction = self.viewport.get_player_faction(self.viewer_id)
        court = self.viewport._state.get_court_cards(faction)
        return [
            {"name": c.name, "effect": c.effect_text[:80],
             "resource_option": f"army={c.resource_army}, vp={c.resource_vp}"}
            for c in court
        ]

    def _culture_summary(self) -> dict:
        tracks = {}
        for track_name in ["confucianism", "xuanxue", "buddhism"]:
            track = self.viewport._state.culture_tracks[track_name]
            tracks[track_name] = {
                "contributions": {
                    pid: level for pid, level in track.contributions.items()
                },
                "current_spread_level": track.spread_level,
            }
        return tracks
```

### 3.4 `knowledge.py` — 规则书 + 牌表

```python
class RuleBookLoader:
    """加载规则书，按主题分块，供 StateEncoder 按需引用"""

    def __init__(self, rulebook_path: str = "rulebook.md"):
        self._load(rulebook_path)

    def _load(self, path: str):
        """解析 rulebook.md，按 ## 标题拆分为段落"""
        # 实现: 读取 markdown，按 ## 标题切块
        # 存储为: {section_title: content}
        pass

    def get_section(self, title: str) -> str:
        """按标题取规则段落"""
        pass

    def get_game_flow(self) -> str:
        """获取游戏流程相关的规则摘要"""
        pass

    def get_scoring_rules(self) -> str:
        """获取终局计分规则"""
        pass

    def get_action_types(self) -> str:
        """获取可用行动类型列表及说明"""
        pass


class CardTableLoader:
    """加载牌表，提供卡牌信息的快速查询"""

    def __init__(self, card_table_path: str = "card_design.csv"):
        self._load(card_table_path)

    def _load(self, path: str):
        """解析 CSV，按 ownership + name 建立索引"""
        pass

    def get_card(self, name: str, ownership: str = None) -> dict:
        """查询单张牌的全部字段"""
        pass

    def get_cards_summary(self, names: List[str]) -> str:
        """批量查询 → 生成精简摘要文本（供 prompt 使用）"""
        pass

    def get_hero_detail(self, hero_name: str) -> str:
        """查询角色的完整能力"""
        pass
```

### 3.5 `state_encoder.py` — 状态编码 ⭐ P0

```python
class StateEncoder:
    """
    将游戏状态编码为 LLM 可读的 Markdown 文本。

    这是整个 LLM-Hybrid 的信息瓶颈。编码质量 = Agent 战略质量的上限。

    编码策略:
      - 全量编码（每回合 1 次战略分析用）: ~2000 tokens
      - 精简编码（关键决策点用）: ~800 tokens
    """

    def __init__(self, view_provider: GameViewProvider,
                 rulebook: RuleBookLoader,
                 cardtable: CardTableLoader):
        self.view = view_provider
        self.rules = rulebook
        self.cards = cardtable

    # ── 公开方法 ──

    def encode_for_round_analysis(self) -> str:
        """每回合战略分析用全量编码 → 拼装 Markdown"""
        sections = [
            self._game_overview(),
            self._my_state(),
            self._hand_detail(),
            self._court_detail(),
            self._map_state(),
            self._culture_state(),
            self._opponent_summary(),
            self._goals_and_tasks(),
            self._scoring_reminder(),
        ]
        return "\n\n---\n\n".join(sections)

    def encode_for_critical_decision(self, decision_type: str) -> str:
        """关键决策用精简编码"""
        # 只包含与决策类型相关的信息
        pass

    # ── 各 section 生成方法 ──

    def _game_overview(self) -> str:
        player = self.view.get_player_view()
        return f"""## 游戏概况
- **当前回合**: 第 {self.view.get_public_view()['round']} / 10 回合
- **你的角色**: {player['hero']['name']}
- **你的阵营**: {player['faction']}
- **VP 目标**: 150 触发终局"""

    def _my_state(self) -> str:
        p = self.view.get_player_view()
        r = p['resources']
        return f"""## 你的状态
| 资源 | 数值 |
|------|------|
| VP | {r['vp']} |
| 军力 | {r['military']} |
| 手牌数 | {r['hand_count']} / 8 |
| 威望 | {r['prestige']} (排名 {r['prestige_rank']}) |
| 功绩 | {r['merit']} (排名 {r['merit_rank']}) |
| 部队部署 | {self._format_army()} |"""

    def _hand_detail(self) -> str:
        hand = self.view.get_player_view()['hand']
        if not hand:
            return "## 手牌\n无"
        lines = ["## 手牌"]
        for c in hand:
            lines.append(f"- **{c['name']}** ({c['type']}) | 费用: {c['cost']} | {c['effect_summary']}")
        return "\n".join(lines)

    def _court_detail(self) -> str:
        court = self.view.get_public_view()['court']
        if not court:
            return "## 朝堂区\n空"
        lines = ["## 朝堂区候选策略牌（可激活）"]
        for i, c in enumerate(court):
            lines.append(f"{i+1}. **{c['name']}** — {c['effect']}")
            lines.append(f"   (未激活则回合结束自动结算: +{c['resource_option']})")
        return "\n".join(lines)

    def _map_state(self) -> str:
        regions = self.view.get_public_view()['map']
        lines = ["## 地图"]
        lines.append("| 区域 | 控制者 | VP值 | 文化标记 | 驻军 | 邻接 |")
        lines.append("|------|--------|------|---------|------|------|")
        for r in regions:
            armies = ", ".join(f"{pid}:{n}" for pid, n in r['armies'].items())
            adj = ", ".join(r['adjacent'][:4])  # 只显示前4个邻接
            lines.append(f"| {r['name']} | {r['controller'] or '无'} | {r['vp_value']} | {r['culture_markers']} | {armies} | {adj} |")
        return "\n".join(lines)

    def _culture_state(self) -> str:
        culture = self.view.get_public_view()['culture_tracks']
        lines = ["## 文化轨排名"]
        lines.append("| 轨道 | 排名 (玩家: 贡献级) |")
        lines.append("|------|---------------------|")
        for track, data in culture.items():
            ranking = sorted(data['contributions'].items(), key=lambda x: x[1], reverse=True)
            rank_str = " > ".join(f"{pid}:{level}" for pid, level in ranking)
            lines.append(f"| {track} | {rank_str} |")
        return "\n".join(lines)

    def _opponent_summary(self) -> str:
        opps = self.view.get_opponent_view()
        lines = ["## 对手概要"]
        for o in opps:
            regions = ", ".join(o['controlled_regions'][:3]) or "无"
            lines.append(f"- **{o['name']}** ({o['hero']}) | VP: {o['vp']} | 手牌: {o['hand_count']}张 | 控制: {regions}")
        return "\n".join(lines)

    def _goals_and_tasks(self) -> str:
        return "## 君主任务\n(从 emperor_dice 提取)"

    def _scoring_reminder(self) -> str:
        return self.rules.get_section("终局计分")

    # ── 辅助 ──

    def _format_army(self) -> str:
        """格式化部队部署状态"""
        p = self.view._state.get_player(self.view.viewer_id)
        deployed = sum(1 for a in p.army_reserve if a.deployed)
        total = len(p.army_reserve)
        return f"{deployed}/{total} 已部署"
```

### 3.6 `llm_analyzer.py` — LLM 调用

```python
import json
from openai import OpenAI

class LLMAnalyzer:
    """
    调用 LLM 进行战略分析和关键决策。

    设计原则:
      - 使用 structured output (JSON schema) 保证格式可靠
      - Temperature=0 保证稳定性
      - 每个 Prompt 包含规则书上下文 + 牌表上下文
    """

    def __init__(self,
                 model: str = "gpt-4o-mini",
                 temperature: float = 0.0,
                 api_key: str = None):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self._load_prompts()
        self._build_schemas()

    def _load_prompts(self):
        """从 prompts/ 目录加载模板"""
        base = Path(__file__).parent / "prompts"
        self.system_prompt = (base / "system_analyst.md").read_text(encoding="utf-8")
        self.round_template = (base / "round_analysis.md").read_text(encoding="utf-8")
        self.critical_template = (base / "critical_decision.md").read_text(encoding="utf-8")

    def _build_schemas(self):
        """构建 JSON Schema 用于 structured output"""
        self.round_analysis_schema = {
            "type": "json_schema",
            "json_schema": {
                "name": "strategic_directive",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "round_goal": {
                            "type": "string",
                            "enum": ["军事扩张", "文化推进", "牌组构筑", "防守待机", "混合"]
                        },
                        "reasoning": {"type": "string"},
                        "priority_action_types": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["march", "occupy", "fortify", "draw", "recruit",
                                         "play_card", "court_action", "activate_ability",
                                         "public_action"]
                            }
                        },
                        "key_locations": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "preferred_court_cards": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "forbidden_actions": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "weight_overrides": {
                            "type": "object",
                            "properties": {
                                "march": {"type": "number"},
                                "occupy": {"type": "number"},
                                "fortify": {"type": "number"},
                                "draw": {"type": "number"},
                                "recruit": {"type": "number"},
                                "court_action": {"type": "number"},
                                "play_card": {"type": "number"},
                                "activate_ability": {"type": "number"},
                            },
                            "additionalProperties": False
                        }
                    },
                    "required": ["round_goal", "reasoning", "priority_action_types"],
                    "additionalProperties": False
                }
            }
        }

        self.critical_decision_schema = {
            "type": "json_schema",
            "json_schema": {
                "name": "critical_decision",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "decision": {"type": "string"},
                        "reasoning": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    },
                    "required": ["decision", "reasoning", "confidence"],
                    "additionalProperties": False
                }
            }
        }

    # ── 公开方法 ──

    def analyze_round(self, state_encoding: str,
                      rule_context: str,
                      card_context: str,
                      history: str = "") -> StrategicDirective:
        """每回合一次的战略分析"""

        prompt = self.round_template.format(
            rule_context=rule_context,
            card_context=card_context,
            state_encoding=state_encoding,
            history=history,
        )

        response = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
            response_format=self.round_analysis_schema,
        )

        result = json.loads(response.choices[0].message.content)
        return self._to_directive(result)

    def analyze_critical_decision(self, state_encoding: str,
                                   decision_type: str,
                                   rule_context: str) -> dict:
        """关键决策点（僭越/终局触发）的 LLM 分析"""

        prompt = self.critical_template.format(
            rule_context=rule_context,
            state_encoding=state_encoding,
            decision_type=decision_type,
        )

        response = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
            response_format=self.critical_decision_schema,
        )

        return json.loads(response.choices[0].message.content)

    # ── 内部 ──

    def _to_directive(self, result: dict) -> StrategicDirective:
        return StrategicDirective(
            round_number=0,  # 由调用方设置
            round_goal=result["round_goal"],
            reasoning=result["reasoning"],
            priority_action_types=result.get("priority_action_types", []),
            key_locations=result.get("key_locations", []),
            preferred_court_cards=result.get("preferred_court_cards", []),
            forbidden_actions=result.get("forbidden_actions", []),
            weight_overrides=result.get("weight_overrides"),
        )
```

### 3.7 `validator.py` — 校验

```python
class DirectiveValidator:
    """
    校验 LLM 产出的 StrategicDirective 是否与当前游戏状态兼容。

    三层校验:
      1. JSON Schema 校验（由 LLM structured output 保证，此处做 double-check）
      2. 合法性校验（引用的区域/卡牌/行动类型是否存在）
      3. 合理性校验（自动修正明显矛盾，如"军力=0 但 march 优先级最高"）
    """

    def __init__(self, view_provider: GameViewProvider):
        self.view = view_provider

    def validate(self, directive: StrategicDirective) -> tuple[bool, List[str], StrategicDirective]:
        """
        校验并返回 (是否通过, 警告列表, 修正后的指令)

        注意: 默认策略是"自动修正"而非"拒绝"——不阻塞对局。
        """
        warnings = []

        # ── 合法性校验 ──
        warnings += self._check_locations(directive)
        warnings += self._check_court_cards(directive)
        warnings += self._check_action_types(directive)

        # ── 合理性自动修正 ──
        directive, fix_warnings = self._auto_correct(directive)
        warnings += fix_warnings

        return len([w for w in warnings if w.startswith("[ERROR]")]) == 0, \
               warnings, \
               directive

    def _check_locations(self, d: StrategicDirective) -> List[str]:
        """检查 key_locations 是否都在地图上"""
        warnings = []
        valid_regions = {r.name for r in self.view._state.regions}
        for loc in d.key_locations:
            if loc not in valid_regions:
                warnings.append(f"[WARN] 未知区域 '{loc}'，已移除")
        d.key_locations = [loc for loc in d.key_locations if loc in valid_regions]
        return warnings

    def _check_court_cards(self, d: StrategicDirective) -> List[str]:
        """检查 preferred_court_cards 是否在朝堂区"""
        warnings = []
        court_names = {c.name for c in self.view._state.get_court_cards(
            self.view.viewport.get_player_faction(self.view.viewer_id)
        )}
        for card in d.preferred_court_cards:
            if card not in court_names:
                warnings.append(f"[WARN] 朝堂区无 '{card}'，已移除")
        d.preferred_court_cards = [c for c in d.preferred_court_cards if c in court_names]
        return warnings

    def _check_action_types(self, d: StrategicDirective) -> List[str]:
        """检查 priority_action_types 是否都是合法类型"""
        valid = {"march", "occupy", "fortify", "draw", "recruit",
                 "play_card", "court_action", "activate_ability",
                 "public_action", "end_turn"}
        warnings = []
        for a in d.priority_action_types:
            if a not in valid:
                warnings.append(f"[WARN] 未知行动类型 '{a}'，已移除")
        d.priority_action_types = [a for a in d.priority_action_types if a in valid]
        return warnings

    def _auto_correct(self, d: StrategicDirective) -> tuple[StrategicDirective, List[str]]:
        """自动修正明显不合理的指令"""
        warnings = []
        p = self.view._state.get_player(self.view.viewer_id)

        # 军力=0 → march 不能是第一优先
        if p.military == 0 and d.priority_action_types and d.priority_action_types[0] == "march":
            warnings.append("[AUTO] 军力=0，将 march 优先级下调")
            d.priority_action_types.remove("march")
            d.priority_action_types.append("march")

        # 手牌=0 → play_card 不能执行
        if len(p.hand) == 0:
            if "play_card" in d.priority_action_types:
                warnings.append("[AUTO] 无手牌，移除 play_card")
                d.priority_action_types.remove("play_card")

        # Court action 用完了
        if not p.can_take_court_action():
            if "court_action" in d.priority_action_types:
                warnings.append("[AUTO] Court action 已用完，移除")
                d.priority_action_types.remove("court_action")

        return d, warnings
```

### 3.8 `evaluator.py` — 评估函数

```python
class ActionEvaluator:
    """
    局面评估函数 — Beam Search 和 Heuristic Executor 共用。

    设计原则 (来自 Goodman 论文教训):
      - 不能只看当前 VP（Dominion 的欺骗性信号问题）
      - 必须评估"未来 VP 生成能力"：区域控制、文化排名、牌库质量
      - Leader 项（与领先者的差距）用于捕捉对抗性互动

    所有权重为手工设定，v1 不做训练。
    """

    # v1 默认权重（后续可调）
    DEFAULT_WEIGHTS = {
        "vp": 1.0,
        "military": 1.5,
        "area_control": 0.8,
        "culture_rank": 1.5,
        "hand_quality": 2.0,
        "deck_quality": 2.0,
        "army_progress": 1.0,
        "prestige": 0.5,
        "merit": 0.5,
        "leader_gap": -0.3,       # 与领先者的 VP 差距（负权重 = 落后越多越焦虑）
    }

    def __init__(self, weights: dict = None):
        self.weights = weights or self.DEFAULT_WEIGHTS

    # ── 顶层评估 ──

    def evaluate(self, state: GameState, player_id: str) -> float:
        """全面评估局面价值（回合结束截断点用）"""
        p = state.get_player(player_id)
        score = 0.0

        score += self.weights["vp"] * p.vp
        score += self.weights["military"] * p.military
        score += self.weights["area_control"] * self._area_control_value(state, player_id)
        score += self.weights["culture_rank"] * self._culture_rank_value(state, player_id)
        score += self.weights["hand_quality"] * self._hand_quality(state, player_id)
        score += self.weights["deck_quality"] * self._deck_quality(state, player_id)
        score += self.weights["army_progress"] * self._army_progress(state, player_id)
        score += self.weights["prestige"] * p.prestige
        score += self.weights["merit"] * p.merit
        score += self.weights["leader_gap"] * self._leader_gap(state, player_id)

        return score

    def evaluate_quick(self, state: GameState, player_id: str) -> float:
        """快速评估（Beam Search 中间节点用，跳过昂贵计算）"""
        p = state.get_player(player_id)
        return (
            self.weights["vp"] * p.vp
            + self.weights["military"] * p.military
            + self.weights["area_control"] * self._area_control_value(state, player_id)
            + self.weights["hand_quality"] * self._hand_quality(state, player_id)
        )

    # ── 各维度评分 ──

    def _area_control_value(self, state: GameState, player_id: str) -> float:
        """已控制区域的 VP 价值总和（折扣：可能被夺走）"""
        total = 0.0
        for r in state.regions:
            if r.controller == player_id:
                total += r.vp_value
            elif r.partial_controller == player_id:
                total += r.vp_value * 0.5
        return total

    def _culture_rank_value(self, state: GameState, player_id: str) -> float:
        """三条文化轨的排名预期 VP"""
        rank_vp = {1: 10, 2: 6, 3: 3, 4: 0}
        total = 0.0
        for track in state.culture_tracks.values():
            rank = track.get_rank(player_id)
            total += rank_vp.get(rank, 0)
        return total

    def _hand_quality(self, state: GameState, player_id: str) -> float:
        """手牌质量：高分牌多 = 好，流民多 = 差"""
        p = state.get_player(player_id)
        score = 0.0
        for card in p.hand:
            if card.card_type.value == "strategy":
                score += 3.0
            elif card.card_type.value == "friend":
                score += 2.0
            elif card.card_type.value == "event":
                score += 1.0
            elif "流民" in card.name:
                score -= 1.0
        return score

    def _deck_quality(self, state: GameState, player_id: str) -> float:
        """牌库质量（通用牌库的已知组成）"""
        # v1: 基于弃牌堆的已知信息估算
        # 弃牌堆中策略牌/幕僚牌多 = 牌库中剩余的好牌少
        discard = state.main_discard
        good_in_discard = sum(1 for c in discard
                             if c.card_type.value in ("strategy", "friend"))
        return -good_in_discard * 0.5 + len(discard) * 0.1

    def _army_progress(self, state: GameState, player_id: str) -> float:
        """部队部署进度"""
        p = state.get_player(player_id)
        deployed = sum(1 for a in p.army_reserve if a.deployed)
        return deployed / max(len(p.army_reserve), 1) * 5.0

    def _leader_gap(self, state: GameState, player_id: str) -> float:
        """与最高分对手的 VP 差距"""
        max_opponent_vp = max(
            (p.vp for p in state.players if p.id != player_id),
            default=0
        )
        return max_opponent_vp - state.get_player(player_id).vp

    # ── 动态权重 ──

    def evaluate_with_directive(self, state: GameState, player_id: str,
                                 directive: StrategicDirective) -> float:
        """在战略指令指导下评估（Heuristic Executor 用）"""
        base = self.evaluate(state, player_id)

        # 对齐加分: 如果行动与战略方向一致，额外加分
        # （由调用方在外层加法处理，这里只是基础评估）
        return base
```

### 3.9 `heuristic_executor.py` — 战术执行

```python
class HeuristicExecutor:
    """
    战术层行动选择 — 在 LLM 战略指令约束下用启发式打分选择行动。

    处理大部分常规行动（~90% 的决策），不调用 LLM。
    """

    def __init__(self, evaluator: ActionEvaluator):
        self.evaluator = evaluator

    def select_action(self, state: GameState, player_id: str,
                      available_actions: List[Action],
                      directive: StrategicDirective) -> Action:
        """
        从 available_actions 中选择最优行动。

        打分 = base_score(行动本身价值)
             + alignment_bonus(与 directive.priority_action_types 一致)
             + location_bonus(目标在 directive.key_locations 中)
             + card_bonus(涉及 directive.preferred_court_cards)
             - forbidden_penalty(在 directive.forbidden_actions 中)
        """
        scored = []
        for action in available_actions:
            score = self._score_action(state, player_id, action, directive)
            scored.append((score, action))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    def _score_action(self, state: GameState, player_id: str,
                      action: Action, directive: StrategicDirective) -> float:
        score = 0.0

        action_type = self._classify_action(action)

        # 1. 基础价值（快速评估执行后的状态变化）
        score += self._base_value(state, player_id, action)

        # 2. 战略对齐加分
        if action_type in directive.priority_action_types:
            rank = directive.priority_action_types.index(action_type)
            score += (len(directive.priority_action_types) - rank) * 0.5

        # 3. 位置加分
        if self._involves_location(action, directive.key_locations):
            score += 2.0

        # 4. 卡牌加分
        if self._involves_court_card(action, directive.preferred_court_cards):
            score += 3.0

        # 5. 禁止惩罚
        if action_type in directive.forbidden_actions:
            score -= 100.0

        return score

    def _classify_action(self, action: Action) -> str:
        """将 Action 对象映射为类型字符串"""
        mapping = {
            "MarchAction": "march",
            "OccupyAction": "occupy",
            "FortifyAction": "fortify",
            "DrawAction": "draw",
            "RecruitAction": "recruit",
            "PlayCardAction": "play_card",
            "CourtAction": "court_action",
            "ActivateAction": "activate_ability",
            "PublicAction": "public_action",
        }
        return mapping.get(type(action).__name__, "unknown")

    def _base_value(self, state: GameState, player_id: str,
                    action: Action) -> float:
        """执行该行动后的状态增量评估"""
        try:
            new_state = copy.deepcopy(state)
            # 使用引擎的 apply_action
            from engine.engine.game import _apply_action_to_state
            _apply_action_to_state(new_state, action, player_id)
            return self.evaluator.evaluate_quick(new_state, player_id) \
                   - self.evaluator.evaluate_quick(state, player_id)
        except Exception:
            return 0.0

    def _involves_location(self, action: Action, key_locations: List[str]) -> bool:
        if hasattr(action, 'target_region') and action.target_region:
            return action.target_region in key_locations
        return False

    def _involves_court_card(self, action: Action, preferred: List[str]) -> bool:
        if hasattr(action, 'card') and action.card:
            return action.card.name in preferred
        return False
```

### 3.10 `simulator.py` — 轻量模拟

```python
class GameSimulator:
    """
    Beam Search 用的轻量前向模拟器。

    封装 GameEngine 的 apply_action，提供:
      - apply_action(state, action) → new_state
      - get_legal_actions(state, player_id) → List[Action]
      - is_terminal(state, player_id) → bool  (当前玩家回合是否结束)

    为什么不用完整的 GameEngine:
      - 不需要触发完整的被动效果链（太重）
      - 不需要 GameLogger
      - 不需要 Viewport 更新

    v1 简化: 直接 deepcopy + 调用引擎的 apply_action。
    如果性能不够，v2 再优化为增量状态更新。
    """

    def __init__(self, action_system: ActionSystem):
        self.action_system = action_system

    def clone_and_apply(self, state: GameState, action: Action,
                        player_id: str) -> GameState:
        """深拷贝状态并应用行动"""
        new_state = copy.deepcopy(state)
        action.execute(new_state)  # 引擎已有的 execute 方法
        return new_state

    def get_legal_actions(self, state: GameState, player_id: str) -> List[Action]:
        """获取当前玩家的合法行动（复用引擎 ActionSystem）"""
        # 快速模式: 只获取 CourtAction 相关的，或者全部
        quick = self.action_system.get_available_quick_actions(state, player_id)
        court = self.action_system.get_available_court_actions(state, player_id)
        hand = self.action_system.get_available_hand_actions(state, player_id)
        activate = self.action_system.get_available_activate_actions(state, player_id)
        public = self.action_system.get_available_public_actions(state, player_id)

        return quick + court + hand + activate + public

    def is_turn_end(self, state: GameState, player_id: str) -> bool:
        """判断模拟中是否应视为回合结束"""
        # 如果没有任何可用行动 → 自动结束
        actions = self.get_legal_actions(state, player_id)
        return len(actions) == 0
```

### 3.11 `beam_planner.py` — Beam Search ⭐

```python
class BeamSearchPlanner:
    """
    Determinized Beam Search — 朝堂选牌和短视界战术规划。

    输入: 局面 + 战略指令
    输出: 最优根行动

    算法:
      For N determinizations:
        1. 随机固定已知牌库顺序
        2. Beam Search (K=5-10) 找最优行动序列
        3. 记录最优序列的根行动
      选被选中最多次的根行动
    """

    def __init__(self, simulator: GameSimulator, evaluator: ActionEvaluator,
                 beam_width: int = 5,
                 num_determinizations: int = 20,
                 max_depth: int = 20):
        self.simulator = simulator
        self.evaluator = evaluator
        self.beam_width = beam_width
        self.num_determinizations = num_determinizations
        self.max_depth = max_depth

    # ── 公开方法 ──

    def plan_action(self, state: GameState, player_id: str,
                    directive: StrategicDirective,
                    available_actions: List[Action]) -> Action:
        """
        主入口: 对当前可用的所有行动（含 CourtAction 等）做 Beam Search，
        返回最优根行动。
        """
        action_wins = defaultdict(int)
        action_scores = defaultdict(list)

        for d in range(self.num_determinizations):
            # Determinize
            world = copy.deepcopy(state)
            self._determinize(world)

            # Beam Search
            best_seq, best_score = self._beam_search(
                world, player_id, directive
            )

            if best_seq:
                root = best_seq[0]
                action_wins[self._action_key(root)] += 1
                action_scores[self._action_key(root)].append(best_score)

        # 决策: 选"获胜"次数最多 + 平均分最高的根行动
        if not action_wins:
            return available_actions[0]  # fallback

        best = max(action_wins, key=lambda a:
            (action_wins[a], np.mean(action_scores[a])))

        # 映射回原始 Action 对象
        for action in available_actions:
            if self._action_key(action) == best:
                return action
        return available_actions[0]

    # ── Beam Search ──

    def _beam_search(self, world: GameState, player_id: str,
                     directive: StrategicDirective
                     ) -> tuple[List, float]:
        """单玩家确定性 Beam Search"""

        beam = [(world, [], self.evaluator.evaluate(world, player_id))]

        for depth in range(self.max_depth):
            candidates = []

            for state, seq, _ in beam:
                legal = self.simulator.get_legal_actions(state, player_id)

                if not legal:
                    candidates.append((
                        state, seq,
                        self._terminal_score(state, player_id, directive)
                    ))
                    continue

                for action in legal:
                    new_state = self.simulator.clone_and_apply(
                        state, action, player_id
                    )
                    score = self.evaluator.evaluate_quick(new_state, player_id)
                    # 战略对齐加分
                    score += self._alignment_bonus(action, directive)
                    candidates.append((new_state, seq + [action], score))

            if not candidates:
                break

            candidates.sort(key=lambda x: x[2], reverse=True)
            beam = candidates[:self.beam_width]

            # 提前终止检查
            if self._all_terminal(beam, player_id):
                beam = candidates[:1]
                break

        best = beam[0]
        return best[1], best[2]

    # ── 辅助 ──

    def _determinize(self, world: GameState):
        """随机固定隐藏信息"""
        import random
        rng = random.Random()

        # 公共牌库顺序（主要噪声源）
        rng.shuffle(world.main_deck)

        # 阵营牌库（10 张，内容已知 → 噪声小）
        rng.shuffle(world.jin_deck)
        rng.shuffle(world.north_deck)

        # v1: 对手手牌不做采样（保持当前 Viewport 可见内容）
        # v2: 基于已知弃牌+公开信息推断分布后采样

    def _terminal_score(self, state: GameState, player_id: str,
                        directive: StrategicDirective) -> float:
        """回合结束截断评估"""
        base = self.evaluator.evaluate(state, player_id)
        # 回合结束特有: 未激活朝堂牌自动结算价值
        p = state.get_player(player_id)
        unplayed_court = sum(
            c.resource_vp
            for c in state.get_court_cards(p.faction)
        )
        faction_share = 1.0 if p.faction == "north" else 1.0 / 3
        return base + unplayed_court * faction_share

    def _alignment_bonus(self, action, directive: StrategicDirective) -> float:
        """行动与战略指令的对齐加分"""
        action_type = self._classify(action)
        if action_type in directive.priority_action_types:
            rank = directive.priority_action_types.index(action_type)
            return (len(directive.priority_action_types) - rank) * 0.3
        return 0.0

    def _action_key(self, action) -> str:
        """生成行动的唯一标识（用于跨 determinization 统计）"""
        return f"{type(action).__name__}:{getattr(action, 'card', None)}:{getattr(action, 'target_region', None)}"

    def _classify(self, action) -> str:
        mapping = {
            "MarchAction": "march", "OccupyAction": "occupy",
            "FortifyAction": "fortify", "DrawAction": "draw",
            "RecruitAction": "recruit", "PlayCardAction": "play_card",
            "CourtAction": "court_action", "ActivateAction": "activate_ability",
            "PublicAction": "public_action",
        }
        return mapping.get(type(action).__name__, "unknown")

    def _all_terminal(self, beam, player_id) -> bool:
        """检查 beam 的 top-3 是否都是终止状态"""
        return all(
            len(self.simulator.get_legal_actions(s, player_id)) == 0
            for s, _, _ in beam[:3]
        )
```

### 3.12 `agent.py` — 主 Agent ⭐

```python
class L1Agent(GameAgent):
    """
    v1 六朝 L1 对局 Agent。

    架构: LLM 战略分析 + Beam Search 行动生成。

    实现 GameAgent 接口（engine/ai/interface.py）:
      - setup_decision(ctx) → SetupDecision
      - decide_action(state, available_actions) → Action
      - make_choice(state, prompt) → Choice
      - select_target(state, prompt) → Target
      - choose_discards(state, count, prompt) → List[Card]
      - request_card_play(state) → Action
      - request_court_play(state) → Action
    """

    def __init__(self,
                 model: str = "gpt-4o-mini",
                 beam_width: int = 5,
                 num_determinizations: int = 20):
        super().__init__()
        self.player_id = None

        # ── 子模块 ──
        self.rulebook = RuleBookLoader()
        self.cardtable = CardTableLoader()
        self.evaluator = ActionEvaluator()
        self.llm = LLMAnalyzer(model=model)
        self.cache = DirectiveCache()
        self.executor = HeuristicExecutor(self.evaluator)
        # simulator 在 setup 中根据 action_system 创建

    # ═══════════════════════════════════════════════════════
    # GameAgent 接口实现
    # ═══════════════════════════════════════════════════════

    def setup_decision(self, ctx: SetupContext) -> SetupDecision:
        """开局前: 选择角色、初始手牌、公开策略牌"""
        # v1: 用简单启发式 + LLM 辅助选择
        # 暂不涉及 Beam Search
        self.player_id = ctx.player_id
        return self._heuristic_setup(ctx)

    def decide_action(self, state: GameState,
                      available_actions: List[Action]) -> Optional[Action]:
        """
        核心决策: 每步行动选择。

        路由逻辑:
          1. 是否是新回合？→ 调用 LLM 战略分析
          2. 是否是朝堂选牌场景？→ Beam Search
          3. 是否是关键决策？→ LLM 直接决策
          4. 否则 → Heuristic Executor
        """
        if not available_actions:
            return None  # 结束回合

        # Step 1: 初始化本轮视图
        view = GameViewProvider(state, self.player_id)
        current_round = state.round

        # Step 2: 是否需要（重新）战略分析？
        if not self.cache.is_valid_for(current_round):
            self._run_strategic_analysis(view, state)

        directive = self.cache.get()

        # Step 3: 按场景路由
        # 朝堂选牌场景
        if self._has_court_actions(available_actions) \
           and self._should_beam_search(state, directive):
            return self._beam_search_decision(state, available_actions, directive)

        # 关键决策场景
        if self._is_critical_scenario(state, available_actions):
            return self._critical_decision(state, view, directive)

        # 常规场景
        return self.executor.select_action(
            state, self.player_id, available_actions, directive
        )

    def make_choice(self, state: GameState, prompt: str) -> str:
        """被动选择: 效果给出多选项时"""
        # v1: 基于当前战略指令的启发式选择
        return self._heuristic_choice(state, prompt)

    def select_target(self, state: GameState, prompt: str) -> str:
        """被动指定目标: 选区域/玩家/卡牌"""
        return self._heuristic_target(state, prompt)

    def choose_discards(self, state: GameState, count: int,
                        prompt: str) -> List[str]:
        """被动弃牌: 手牌超限时或效果要求时"""
        return self._heuristic_discard(state, count)

    def request_card_play(self, state: GameState) -> Optional[Action]:
        """被要求出牌时"""
        return self._heuristic_card_play(state)

    def request_court_play(self, state: GameState) -> Optional[Action]:
        """额外 Court Action 时"""
        return self._heuristic_court_play(state)

    # ═══════════════════════════════════════════════════════
    # 内部决策方法
    # ═══════════════════════════════════════════════════════

    def _run_strategic_analysis(self, view: GameViewProvider,
                                 state: GameState):
        """调用 LLM 进行回合战略分析"""
        encoder = StateEncoder(view, self.rulebook, self.cardtable)

        state_md = encoder.encode_for_round_analysis()
        rule_context = self.rulebook.get_game_flow()
        card_context = self.cardtable.get_cards_summary(
            [c.name for c in state.get_player(self.player_id).hand]
        )

        directive = self.llm.analyze_round(
            state_encoding=state_md,
            rule_context=rule_context,
            card_context=card_context,
        )
        directive.round_number = state.round

        # 校验 + 自动修正
        validator = DirectiveValidator(view)
        ok, warnings, directive = validator.validate(directive)
        if warnings:
            logger.warning(f"Directive validation warnings: {warnings}")

        self.cache.set(directive)

    def _should_beam_search(self, state: GameState,
                            directive: StrategicDirective) -> bool:
        """判断当前场景是否值得跑 Beam Search"""
        # 如果战略指令优先级中有 court_action 或用完 court action 就不跑
        if "court_action" not in directive.priority_action_types:
            return False
        p = state.get_player(self.player_id)
        if not p.can_take_court_action():
            return False
        return True

    def _beam_search_decision(self, state: GameState,
                               available_actions: List[Action],
                               directive: StrategicDirective) -> Action:
        """用 Beam Search 做朝堂选牌决策"""
        planner = BeamSearchPlanner(
            simulator=self.simulator,
            evaluator=self.evaluator,
            beam_width=5,
            num_determinizations=20,
        )
        return planner.plan_action(state, self.player_id, directive, available_actions)

    def _is_critical_scenario(self, state: GameState,
                               available_actions: List[Action]) -> bool:
        """判断是否是关键决策场景"""
        # 僭越可用？
        # 终局触发条件满足？
        # 被僭越后重新评估？
        # v1: 先检查僭越
        p = state.get_player(self.player_id)
        if hasattr(p, 'can_usurp') and p.can_usurp():
            return True
        return False

    def _critical_decision(self, state: GameState,
                            view: GameViewProvider,
                            directive: StrategicDirective) -> Action:
        """关键决策: 调用 LLM 直接决策"""
        encoder = StateEncoder(view, self.rulebook, self.cardtable)
        state_md = encoder.encode_for_critical_decision("usurp")
        result = self.llm.analyze_critical_decision(
            state_encoding=state_md,
            decision_type="usurp",
            rule_context=self.rulebook.get_section("僭越"),
        )
        # 根据 result 决定是否僭越
        if result.get("decision") == "usurp":
            # 找到僭越行动并返回
            ...
        # 否则返回常规行动
        return self.executor.select_action(state, self.player_id,
                                           self._get_available(state), directive)

    def _has_court_actions(self, actions: List[Action]) -> bool:
        return any(isinstance(a, CourtAction) for a in actions)

    def _get_available(self, state: GameState) -> List[Action]:
        """获取当前所有可用行动（从 ActionSystem）"""
        return self.simulator.get_legal_actions(state, self.player_id)

    # ═══════════════════════════════════════════════════════
    # 启发式 fallback 方法（v1 简化版）
    # ═══════════════════════════════════════════════════════

    def _heuristic_setup(self, ctx: SetupContext) -> SetupDecision:
        """开局选择的启发式实现"""
        # 从可用英雄中选一个（按偏好顺序或随机）
        pass

    def _heuristic_choice(self, state: GameState, prompt: str) -> str:
        pass

    def _heuristic_target(self, state: GameState, prompt: str) -> str:
        pass

    def _heuristic_discard(self, state: GameState, count: int) -> List[str]:
        pass

    def _heuristic_card_play(self, state: GameState) -> Optional[Action]:
        pass

    def _heuristic_court_play(self, state: GameState) -> Optional[Action]:
        pass
```

### 3.13 `prompts/` — Prompt 模板

#### `prompts/system_analyst.md`

```markdown
你是一个桌游 AI 策略分析师，专精于《六朝何事》这款非对称 4 人 DBG 桌游。

## 你的角色
你不是在直接选择行动，而是在每个回合开始时为战术执行层制定战略方向。
战术执行层会用 Beam Search 和启发式评分来实现你的战略。

## 你需要理解的核心机制
- 4 玩家：1 北方（独立牌库、VP 胜利）+ 3 东晋（共享司马家资源、竞争文化排名）
- 10 回合，VP 达 150 触发终局
- 12 区域，区控给 VP + 文化传播
- DBG：策略牌加入阵营牌库 → 朝堂区 → 激活获得效果
- 僭越：威望超过对手时可发动，改变阵营关系
- 3 条文化轨：儒学/玄学/佛学，终局按排名给 VP

## 输出要求
- 根据当前局面判断本回合最优方向
- 给出具体的行动优先级、关键位置、偏好朝堂牌
- 用 "reasoning" 字段解释你的判断（会被用于赛后分析）
- 不要给出"进军到 XX" 这样的具体行动——那是战术层的职责
```

#### `prompts/round_analysis.md`

```markdown
{rule_context}

{card_context}

## 当前局面的游戏视图

{state_encoding}

## 上回合历史

{history}

---

请分析当前局面并输出本回合的战略指令。
```

#### `prompts/critical_decision.md`

```markdown
{rule_context}

## 当前局面

{state_encoding}

## 需要决策

决策类型: {decision_type}

---

请分析局面并给出你的决策。如果 decision_type 是 "usurp"（僭越），请在 decision 中返回 "usurp" 或 "no_usurp"，并说明理由。
```

---

## 四、关键流程伪代码

### 4.1 完整回合流程

```python
# ── 引擎调用入口 ──

def decide_action(state, available_actions):
    """一次行动决策的完整流程"""

    # 1. 首次调用 → 战略分析
    if not cache.is_valid_for(state.round):
        view = GameViewProvider(state, player_id)
        encoder = StateEncoder(view, rulebook, cardtable)
        state_md = encoder.encode_for_round_analysis()        # ~2000 tokens
        directive = llm.analyze_round(state_md, rule_context, card_context)
        directive = validator.validate(directive)
        cache.set(directive)

    directive = cache.get()

    # 2. 场景路由
    if has_court_actions(available_actions) and should_beam_search(state, directive):
        # 朝堂选牌 → Beam Search (~10s)
        planner = BeamSearchPlanner(simulator, evaluator,
                                    beam_width=5, num_determinizations=20)
        action = planner.plan_action(state, player_id, directive, available_actions)

    elif is_critical_scenario(state):
        # 僭越/终局 → LLM 直接决策 (~2s)
        action = llm_based_critical(state, view)

    else:
        # 常规行动 → Heuristic Executor (~0.01s)
        action = executor.select_action(state, player_id, available_actions, directive)

    return action
```

### 4.2 Beam Search 单次迭代

```python
def _beam_search(world, player_id, directive):
    beam = [(world, [], evaluator.evaluate(world, player_id))]

    for depth in range(max_depth):
        candidates = []
        for state, seq, _ in beam:
            for action in simulator.get_legal_actions(state, player_id):
                new_state = simulator.clone_and_apply(state, action, player_id)
                score = evaluator.evaluate_quick(new_state, player_id)
                score += alignment_bonus(action, directive)
                candidates.append((new_state, seq + [action], score))

        candidates.sort(key=lambda x: x[2], reverse=True)
        beam = candidates[:beam_width]   # 只保留 top-K

        if all_terminal(beam, player_id):
            break

    return beam[0][1], beam[0][2]   # (最优序列, 得分)
```

---

## 五、与引擎的集成

### 5.1 引擎改动（最小化）

v1 需要引擎做的最小改动：

| 改动 | 位置 | 说明 |
|------|------|------|
| 注册 L1Agent | `engine/engine/game.py` | 在创建 GameEngine 时传入 `agents={"player_1": L1Agent(...)}` |
| 暴露 ActionSystem | `engine/engine/action_system.py` | Beam Search 的 Simulator 需要复用，当前已可访问 |
| (可选) 快速 apply | `engine/engine/game.py` | 如果 `deepcopy + execute` 太慢，可暴露一个纯状态转移函数 |

v1 预期**不需要修改引擎核心逻辑**——GameAgent 接口已经覆盖了所有决策点。

### 5.2 配置文件

```python
# config/llm_hybrid_v1.yaml
agent:
  model: "gpt-4o-mini"
  temperature: 0.0
  beam_width: 5
  num_determinizations: 20
  max_beam_depth: 20

evaluator:
  weights:
    vp: 1.0
    military: 1.5
    area_control: 0.8
    culture_rank: 1.5
    hand_quality: 2.0
    deck_quality: 2.0

paths:
  rulebook: "rulebook.md"
  card_table: "card_design.csv"
```

### 5.3 使用示例

```python
from engine.engine.game import GameEngine
from engine.ai.llm_hybrid import L1Agent

# 创建 Agent
agent_north = L1Agent(model="gpt-4o-mini", beam_width=5)
agent_jin_1  = L1Agent(model="gpt-4o-mini", beam_width=5)
agent_jin_2  = L1Agent(model="gpt-4o-mini", beam_width=5)
agent_jin_3  = L1Agent(model="gpt-4o-mini", beam_width=5)

agents = {
    "north": agent_north,
    "jin_1": agent_jin_1,
    "jin_2": agent_jin_2,
    "jin_3": agent_jin_3,
}

# 创建引擎并运行
engine = GameEngine(agents=agents)
engine.run()
```

---

## 六、实施顺序

| 阶段 | 任务 | 预估时间 | 可测试性 |
|------|------|---------|---------|
| **S1** | `directive.py` + `cache.py` + `knowledge.py` | 0.5d | 数据结构，无需对局 |
| **S2** | `view_provider.py` | 1d | 可对 SnapshotViewport 输出做单元测试 |
| **S3** | `state_encoder.py` | 1.5d | 可检查输出的 Markdown 质量 |
| **S4** | `llm_analyzer.py` + `prompts/` + `validator.py` | 1.5d | 可 mock 状态，手动检查 LLM 输出 |
| **S5** | `evaluator.py` | 1d | 可与 HeuristicAI 对比评估分数 |
| **S6** | `simulator.py` + `heuristic_executor.py` | 1d | 可单步测试行动选择 |
| **S7** | `beam_planner.py` | 2d | 可对固定局面测试 Beam Search 输出 |
| **S8** | `agent.py` (主循环 + 路由 + fallback) | 1.5d | 可接入引擎跑完整对局 |
| **S9** | 调试 + 对局测试 + 调优 | 2d | 完整对局、日志审查 |

**总计**: ~12 天（单人）

---

## 七、v2 展望（不在本期范围）

- 对手手牌的重要性采样（determinization 不再是纯均匀随机）
- 价值网络替代手工评估函数（需自对弈训练数据）
- LLM 缓存跨局经验（"上次对拓跋珪时，第 5 回合他通常会..."）
- 多玩家建模（东晋三家之间用博弈论框架，而非同质化 HeuristicAI 模拟）
- 性能优化（C++ 重写 Beam Search 热点、增量状态更新）

---

*文档创建: 2026-08-01 | v1 实施计划*
