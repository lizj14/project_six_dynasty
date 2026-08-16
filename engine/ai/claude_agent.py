"""ClaudeCodeAgent — a GameAgent whose decisions are made by Claude Code.

Each decision point (setup, action choice, effect choices, target selection,
discard, forced card play) is delegated to a Claude Code agent through the
Claude Agent SDK (``claude-agent-sdk``).  The agent sees the game through the
viewport system (its own perspective, with private info filtered) and returns a
structured JSON decision.

Prerequisites
-------------
    pip install claude-agent-sdk
    export ANTHROPIC_API_KEY=sk-ant-...        # or configure the bundled CLI auth

The SDK is imported lazily inside methods, so importing this module (and running
the other game modes) does NOT require the SDK to be installed.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Optional

from .interface import GameAgent, SetupContext, SetupDecision

# ---------------------------------------------------------------------------
# Condensed game rules — placed in the system prompt so the model has a stable
#, cheap reference without re-reading rulebook.md every turn.
# ---------------------------------------------------------------------------
_GAME_RULES = """\
你是桌游《六朝何事》的一名玩家。这是一个 1v3 的回合制策略桌游：北方玩家 1 人，
对抗东晋 3 名玩家（东晋玩家与司马家同阵营、共享部分地盘）。

【胜利目标】终局时 VP（胜利分）最高者获胜。VP 来自：占据区域、文化贡献、
史书区、目标牌、以及终局时司马家分数分配。

【回合流程】每回合：摸牌阶段 → 行动阶段（各玩家依次行动）→ 结算阶段。共 10 回合。

【行动阶段】每名玩家在自己的行动阶段可反复执行行动，直到"空过（结束）"：
  - 快速行动：进军、占据、摸牌、征募、加固（部分每回合限一次）
  - 手牌行动：打出手牌（需支付费用）
  - 牌组行动：执行朝堂区的一张候选策略牌（每回合限一次）
  - 公共行动：执行公共行动牌
  - 激活效果：激活英雄/幕僚的主动效果

【关键资源】
  - 军力：执行进军/占据/加固等需要支付军力
  - VP：胜利分
  - 威望（东晋）：进军+1，影响终局系数
  - 功绩（东晋）：存档朝堂牌等+1，影响终局系数
  - 手牌：上限 8 张
  - 部队：放置在地图上（占据地点）或储备区

【地图】地点由某方控制（北方/东晋某玩家/司马家/中立/空）。进军需相邻、占据需
支付军力，加固使地点更难被攻下。

【重要】你只能看到你自己的手牌与秘密目标，其他玩家手牌内容不可见。
输出决策时，请严格遵守每题的 JSON 格式，不要输出任何解释性文字。
"""


class ClaudeCodeAgent(GameAgent):
    """A game player driven by a Claude Code agent via the Agent SDK."""

    def __init__(
        self,
        player_id: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        allowed_tools: tuple[str, ...] = (),
        cwd: Optional[str] = None,
        max_turns: int = 2,
    ):
        self.player_id = player_id
        self.model = model
        self.system_prompt = system_prompt or _GAME_RULES
        self.allowed_tools = list(allowed_tools)
        self.cwd = cwd
        self.max_turns = max_turns

    # ==================================================================
    # SDK invocation (async -> sync bridge)
    # ==================================================================

    def _options(self):
        """Build ClaudeAgentOptions, importing the SDK lazily."""
        from claude_agent_sdk import ClaudeAgentOptions  # lazy import

        opts = dict(
            system_prompt=self.system_prompt,
            allowed_tools=self.allowed_tools,
            max_turns=self.max_turns,
        )
        if self.model:
            opts["model"] = self.model
        if self.cwd:
            opts["cwd"] = self.cwd
        return ClaudeAgentOptions(**opts)

    def _query(self, prompt: str) -> str:
        """Run a one-shot query synchronously and return the final text.

        The SDK is async (anyio); we bridge to the sync GameAgent interface by
        running a fresh event loop per decision.  Decisions are infrequent
        (one per game decision point), so this is acceptable.
        """
        from claude_agent_sdk import query  # lazy import

        async def _collect() -> str:
            parts: list[str] = []
            async for msg in query(prompt=prompt, options=self._options()):
                content = getattr(msg, "content", None)
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, str):
                            parts.append(block)
                        else:
                            text = getattr(block, "text", None)
                            if text:
                                parts.append(text)
            return "\n".join(parts)

        try:
            return asyncio.run(_collect())
        except ImportError as e:
            raise RuntimeError(
                "claude-agent-sdk 未安装。请先运行: pip install claude-agent-sdk "
                "并设置 ANTHROPIC_API_KEY。"
            ) from e

    # ==================================================================
    # JSON parsing helpers
    # ==================================================================

    @staticmethod
    def _extract_json(text: str) -> Optional[dict]:
        """Extract the first JSON object from free-form agent output."""
        if not text:
            return None
        # Prefer a fenced JSON block, else the first balanced {...}.
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            candidate = m.group(1)
        else:
            start = text.find("{")
            if start == -1:
                return None
            # naive balanced-brace scan
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start : i + 1]
                        break
            else:
                return None
        try:
            obj = json.loads(candidate)
            return obj if isinstance(obj, dict) else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _extract_int(text: str) -> Optional[int]:
        """Extract the first integer from agent output."""
        m = re.search(r"-?\d+", text or "")
        return int(m.group()) if m else None

    # ==================================================================
    # State serialization
    # ==================================================================

    def _state_summary(self, state, available_actions=None) -> str:
        """Build a compact state summary + numbered action list for the model."""
        from viewport import create_viewport, QueryEngine
        from viewport.utils import action_to_summary

        vp = create_viewport(state, self.player_id, available_actions or [], mode="live")
        qe = QueryEngine(vp)
        summary = qe.query("summary")

        parts = [f"# 当前盘面（你的视角：{self.player_id}）\n", str(summary), ""]

        if available_actions is not None:
            player = state.get_player(self.player_id)
            hand = player.hand if player else []
            court = state.get_court_cards(self.player_id) if hasattr(state, "get_court_cards") else []
            public = state.public_action_pool if hasattr(state, "public_action_pool") else []
            staff = player.staff_area if player else []
            hero = player.hero if player else None
            parts.append("\n# 可选行动")
            for i, action in enumerate(available_actions, 1):
                s = action_to_summary(
                    action, self.player_id,
                    hand_cards=hand, court_cards=court, public_cards=public,
                    player_staff=staff, player_hero=hero,
                )
                desc = s.get("description", getattr(action, "action_type", "?"))
                cost = s.get("cost", "")
                line = f"{i}. {desc}"
                if cost:
                    line += f" — 费用: {cost}"
                parts.append(line)
        return "\n".join(parts)

    # ==================================================================
    # Decision methods (GameAgent interface)
    # ==================================================================

    def setup_decision(self, ctx: SetupContext) -> SetupDecision:
        heroes = "\n".join(
            f"{i}. {h.get('name', '?')} — {h.get('effect_text', '')}"
            for i, h in enumerate(ctx.hero_choices)
        )
        goals = "\n".join(
            f"{i}. {g.get('name', '?')} ({g.get('simple_condition', '')} / "
            f"{g.get('full_condition', '')})"
            for i, g in enumerate(ctx.goal_choices)
        )
        hand = "\n".join(f"{i}. {c}" for i, c in enumerate(ctx.hand_cards))
        prompt = f"""\
你正在进行游戏初设（你是 {ctx.player_id}，阵营 {ctx.faction}）。

可选英雄：
{heroes}

可选目标牌（东晋有，北方可忽略）：
{goals}

起始手牌：
{hand}

请选择：
- hero：英雄编号（从0开始）
- face_down：暗置打出的手牌编号（从0开始）
- payment：作为支付的其它手牌编号列表（如 [1,2]）
- public_goal：公开目标编号（东晋；北方填 0）
- secret_goal：秘密目标编号（东晋；无则填 -1）

只输出 JSON，格式：{{"hero": 0, "face_down": 0, "payment": [1], "public_goal": 0, "secret_goal": -1}}
"""
        raw = self._query(prompt)
        obj = self._extract_json(raw) or {}

        def _idx(key, default, size):
            v = obj.get(key)
            if isinstance(v, int) and 0 <= v < size:
                return v
            return default

        hero_idx = _idx("hero", 0, len(ctx.hero_choices))
        public_goal = _idx("public_goal", 0, len(ctx.goal_choices))
        secret_goal = obj.get("secret_goal", -1)
        if not isinstance(secret_goal, int) or not (0 <= secret_goal < len(ctx.goal_choices)):
            secret_goal = -1
        face_down = _idx("face_down", 0, len(ctx.hand_cards))
        payment = [i for i in (obj.get("payment") or [])
                   if isinstance(i, int) and 0 <= i < len(ctx.hand_cards)]

        return SetupDecision(
            hero_index=hero_idx,
            public_goal_index=public_goal,
            secret_goal_index=secret_goal,
            face_down_card_index=face_down,
            payment_indices=payment,
        )

    def decide_action(self, state, available_actions) -> Optional[Any]:
        if not available_actions:
            return None
        prompt = (
            self._state_summary(state, available_actions)
            + f"\n\n请选择你要执行的一个行动，只输出 JSON：{{\"action\": 编号}}（编号从1开始）。"
            f"如果你想结束本回合行动（空过），输出 {{\"action\": 0}}。"
        )
        raw = self._query(prompt)
        obj = self._extract_json(raw)
        if obj is not None and isinstance(obj.get("action"), int):
            n = obj["action"]
            if n == 0:
                return None
            if 1 <= n <= len(available_actions):
                return available_actions[n - 1]
        # fallback: bare integer
        n = self._extract_int(raw)
        if n is None:
            return None
        if n == 0:
            return None
        if 1 <= n <= len(available_actions):
            return available_actions[n - 1]
        return None

    def make_choice(self, state, prompt: dict) -> int:
        options = prompt.get("options", []) if isinstance(prompt, dict) else []
        opts = "\n".join(
            f"{i}. {o.get('label', o) if isinstance(o, dict) else o}"
            for i, o in enumerate(options, 1)
        )
        q = f"""\
{prompt.get('title', '选择一个选项') if isinstance(prompt, dict) else ''}
{opts}
只输出 JSON：{{"choice": 编号}}（编号从1开始）。
"""
        raw = self._query(q)
        obj = self._extract_json(raw)
        if obj is not None and isinstance(obj.get("choice"), int):
            n = obj["choice"]
            if 1 <= n <= len(options):
                return n - 1
        n = self._extract_int(raw)
        if n is not None and 1 <= n <= len(options):
            return n - 1
        return 0

    def select_target(self, state, prompt: dict) -> Optional[str]:
        options = prompt.get("options", []) if isinstance(prompt, dict) else []
        title = prompt.get("title", prompt.get("message", "选择一个目标")) if isinstance(prompt, dict) else ""
        opts = "\n".join(
            f"{i}. {o}" for i, o in enumerate(options, 1)
        )
        q = f"""\
{title}
{opts}
只输出 JSON：{{"target": "目标名称"}}（从上面列表里选一个，名称用原文）。
"""
        raw = self._query(q)
        obj = self._extract_json(raw)
        if obj is not None and isinstance(obj.get("target"), str):
            chosen = obj["target"].strip()
            # allow numeric selection too
            if chosen in options:
                return chosen
            n = self._extract_int(chosen)
            if n is not None and 1 <= n <= len(options):
                return options[n - 1]
            # case-insensitive / fuzzy match
            for o in options:
                if str(o) == chosen:
                    return o
        # fallback: if options are ids, try to match the raw text
        n = self._extract_int(raw)
        if n is not None and 1 <= n <= len(options):
            return options[n - 1]
        return None

    def choose_discards(self, state, hand_cards: list[str], count: int,
                        reason: str = "hand_limit") -> list[int]:
        if count <= 0 or not hand_cards:
            return []
        opts = "\n".join(f"{i}. {c}" for i, c in enumerate(hand_cards, 1))
        q = f"""\
需要弃 {count} 张手牌（原因：{reason}）。你的手牌：
{opts}
只输出 JSON：{{"indices": [编号1, 编号2]}}（编号从1开始，共 {count} 个）。
"""
        raw = self._query(q)
        obj = self._extract_json(raw)
        chosen = []
        if obj is not None and isinstance(obj.get("indices"), list):
            for v in obj["indices"]:
                if isinstance(v, int) and 1 <= v <= len(hand_cards):
                    chosen.append(v - 1)
        if not chosen:
            n = self._extract_int(raw)
            if n is not None and 1 <= n <= len(hand_cards):
                chosen.append(n - 1)
        # dedupe, cap at count, ensure enough
        chosen = list(dict.fromkeys(chosen))[:count]
        if len(chosen) < count:
            for i in range(len(hand_cards)):
                if i not in chosen and len(chosen) < count:
                    chosen.append(i)
        return chosen

    def request_card_play(self, state, eligible_indices: list[int],
                          filter_spec: dict = None, free: bool = False) -> Optional[Any]:
        player = state.get_player(self.player_id)
        if not player or not eligible_indices:
            return None
        opts = "\n".join(
            f"{i}. {player.hand[idx].name}（费用 {0 if free else player.hand[idx].cost}）"
            for i, idx in enumerate(eligible_indices, 1)
        )
        q = f"""\
效果要求立刻打出一张手牌。可选：
{opts}
只输出 JSON：{{"card": 编号}}（编号从1开始）；不打出则 {{"card": 0}}。
"""
        raw = self._query(q)
        obj = self._extract_json(raw)
        n = obj.get("card") if obj is not None else None
        if not isinstance(n, int):
            n = self._extract_int(raw)
        if isinstance(n, int) and 1 <= n <= len(eligible_indices):
            card_idx = eligible_indices[n - 1]
            card = player.hand[card_idx]
            cost = 0 if free else card.cost
            payment = []
            if not free and cost > 0:
                payment = self._select_payment(player, card_idx, cost)
            from engine.actions.card_actions import PlayCardAction
            return PlayCardAction(
                player_id=self.player_id,
                card_index=card_idx,
                payment_indices=payment,
                free=free,
            )
        return None

    def _select_payment(self, player, card_index: int, cost: int) -> list[int]:
        others = [i for i in range(len(player.hand)) if i != card_index]
        opts = "\n".join(
            f"{i}. {player.hand[idx].name}" for i, idx in enumerate(others, 1)
        )
        q = f"""\
要打出「{player.hand[card_index].name}」（费用 {cost}），请选择 {cost} 张其它手牌作为支付。
{opts}
只输出 JSON：{{"payment": [编号]}}（编号是上面列表中的编号，从1开始，共 {cost} 个）。
"""
        raw = self._query(q)
        obj = self._extract_json(raw)
        chosen = []
        if obj is not None and isinstance(obj.get("payment"), list):
            for v in obj["payment"]:
                if isinstance(v, int) and 1 <= v <= len(others):
                    chosen.append(others[v - 1])
        chosen = list(dict.fromkeys(chosen))[:cost]
        while len(chosen) < cost:
            for i in others:
                if i not in chosen:
                    chosen.append(i)
                    break
        return chosen

    def request_court_play(self, state, eligible_cards=None,
                           filter_spec=None) -> Optional[Any]:
        player = state.get_player(self.player_id)
        if not player:
            return None
        court = eligible_cards if eligible_cards is not None else (
            state.get_court_cards(self.player_id) if hasattr(state, "get_court_cards") else [])
        if not court:
            return None
        opts = "\n".join(f"{i}. {c.name}" for i, c in enumerate(court, 1))
        q = f"""\
获得额外朝堂行动，可执行一张朝堂牌。可选：
{opts}
只输出 JSON：{{"card": 编号}}（编号从1开始）；跳过则 {{"card": 0}}。
"""
        raw = self._query(q)
        obj = self._extract_json(raw)
        n = obj.get("card") if obj is not None else None
        if not isinstance(n, int):
            n = self._extract_int(raw)
        if isinstance(n, int) and 1 <= n <= len(court):
            from engine.actions.card_actions import CourtAction
            return CourtAction(
                player_id=self.player_id,
                card_id=court[n - 1].definition.card_id,
            )
        return None
