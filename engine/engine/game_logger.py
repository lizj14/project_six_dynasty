"""Structured game logger — records every action for JSON export & human reading.

Produces a complete, timestamped log of a game session.
JSON format is designed for AI consumption; text format for human review.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class GameLog:
    """Complete log of one game session."""
    game_id: str = ""
    seed: int = 0
    players: list[dict] = field(default_factory=list)
    rounds: list[dict] = field(default_factory=list)
    final_scoring: Optional[dict] = None
    winner: Optional[str] = None
    final_scores: dict[str, int] = field(default_factory=dict)
    total_rounds: int = 0
    end_reason: str = ""


def _format_effect(e: dict) -> str:
    """Format a single effect entry for human-readable display."""
    et = e.get("effect", "?")
    pid = e.get("player", "?")
    src = e.get("source", "?")
    p = e.get("params", {})

    # Build detail parts from params
    parts = []
    if p.get("amount") is not None:
        parts.append(f"+{p['amount']}")
    if p.get("count") is not None:
        parts.append(f"x{p['count']}")
    if p.get("target"):
        parts.append(f"target={p['target']}")
    if p.get("marker"):
        parts.append(f"marker={p['marker']}")
    if p.get("culture_type"):
        parts.append(f"culture={p['culture_type']}")
    if p.get("region"):
        parts.append(f"region={p['region']}")
    if p.get("operate"):
        parts.append(f"op={p['operate']}")
    # Catch remaining params
    for k, v in p.items():
        if k not in ("amount", "count", "target", "marker",
                      "culture_type", "region", "operate"):
            parts.append(f"{k}={v}")

    detail = ", ".join(parts) if parts else ""
    if detail:
        return f"{pid} [{src}] {et}: {detail}"
    return f"{pid} [{src}] {et}"


class GameLogger:
    """Captures structured game events during play."""

    def __init__(self):
        self.log = GameLog()
        self._current_round: Optional[dict] = None
        self._pending_actions: list[dict] = []
        self._effect_buffer: dict[str, list[dict]] = {}  # Effects by player_id waiting for next action
        self._trigger_buffer: list[dict] = []   # Triggers waiting for next action

    # ======== Setup ========

    def log_game_start(self, state: "GameState", seed: int):
        """Record game initialization."""
        self.log.game_id = f"game_{seed}"
        self.log.seed = seed
        self.log.players = []
        for p in state.get_all_players():
            hero_name = p.hero.definition.name if p.hero else "?"
            locations = [lid for lid, loc in state.locations.items()
                         if state._player_control_state(p.player_id) == loc.controller]
            self.log.players.append({
                "id": p.player_id,
                "faction": p.faction.value,
                "hero": hero_name,
                "army_reserve": p.army_reserve_count,
                "initial_hand_size": len(p.hand),
                "initial_locations": locations,
            })
        if state.sima:
            sima_locs = [lid for lid, loc in state.locations.items()
                         if loc.controller.value == "sima"]
            self.log.players.append({
                "id": "sima",
                "faction": "sima",
                "hero": getattr(state.emperor.current_emperor, 'name', '?') if state.emperor else '?',
                "army_reserve": state.sima.army_reserve_count,
                "initial_locations": sima_locs,
            })

    def log_setup_cards(self, state: "GameState", initial_cards: dict,
                         initial_hands: dict):
        """Record setup details.

        initial_cards: {player_id: card_name} — face-down card played
        initial_hands: {player_id: [card_names]} — full starting hand
        """
        self.log.setup_cards = initial_cards
        self.log.initial_hands = initial_hands

    def log_initial_court(self, state: "GameState"):
        """Record the initial court cards for both factions."""
        self.log.north_initial_court = [
            {"name": c.name, "army": c.definition.resource_option_army,
             "vp": c.definition.resource_option_vp}
            for c in state.north_court
        ]
        self.log.jin_initial_court = [
            {"name": c.name, "army": c.definition.resource_option_army,
             "vp": c.definition.resource_option_vp}
            for c in state.jin_court
        ]

    # ======== Round Structure ========

    def log_round_start(self, round_num: int):
        """Start a new round."""
        self._current_round = {
            "round": round_num,
            "preparation": {},
            "player_turns": [],
            "settlement": {},
            "jin_status": [],  # Jin players' status snapshot at round start
        }

    def log_round_deck_state(self, state: "GameState"):
        """Capture main deck count and forced event pile at round start."""
        if not self._current_round:
            return
        self._current_round["deck_state"] = {
            "main_count": len(state.main_deck),
            "forced_events": [c.name for c in state.forced_event_pile],
        }

    def log_jin_round_status(self, state: "GameState"):
        """Capture all Jin players' prestige/contribution/order at round start."""
        if not self._current_round:
            return
        status_list = []
        for p in state.jin_players:
            status_list.append({
                "id": p.player_id,
                "hero": p.hero.definition.name if p.hero else "?",
                "vp": p.vp,
                "prestige": p.prestige,
                "contribution": p.contribution,
                "order": p.order,
                "military": p.military,
            })
        self._current_round["jin_status"] = status_list

    def log_preparation(self, emperor_events: list[dict], sima_dist: list[dict],
                        region_vp: list[dict]):
        """Record preparation phase events."""
        if self._current_round:
            self._current_round["preparation"] = {
                "emperor_dice": emperor_events,
                "sima_military_distribution": sima_dist,
                "region_control_vp": region_vp,
            }

    def log_settlement(self, court_vp: dict, military_gain: dict,
                       emperor_age: list[dict]):
        """Record settlement phase events."""
        if self._current_round:
            self._current_round["settlement"] = {
                "unselected_court_vp": court_vp,
                "military_from_reserve": military_gain,
                "emperor_age": emperor_age,
            }

    def log_round_end_decks(self, state: "GameState"):
        """Record deck/discard/court state for all factions at round end."""
        if not self._current_round:
            return
        deck_info = {
            "north": {
                "deck": [c.name for c in state.north_deck],
                "discard": [c.name for c in state.north_discard],
                "court": [c.name for c in state.north_court],
            },
            "jin": {
                "deck": [c.name for c in state.jin_deck],
                "discard": [c.name for c in state.jin_discard],
                "court": [c.name for c in state.jin_court],
            },
        }
        self._current_round["deck_state"] = deck_info

    def log_round_end_locations(self, state: "GameState"):
        """Record location control and region control for all players + Sima at round end."""
        if not self._current_round:
            return

        # Recalculate all region controls before recording — ensures
        # RegionState.control_marker is up to date even if on_location_change
        # wasn't called for recent location controller changes.
        from rules.area_control import check_all_regions
        check_all_regions(state)

        # Map control state to player IDs
        from models.location import ControlState
        cs_to_player = {
            ControlState.NORTH: "north",
            ControlState.JIN_P1: "jin_1",
            ControlState.JIN_P2: "jin_2",
            ControlState.JIN_P3: "jin_3",
            ControlState.SIMA: "sima",
        }

        loc_info: dict[str, dict] = {}  # player_id → {locations: [], regions: []}

        # Occupied locations
        for loc_id, loc in state.locations.items():
            pid = cs_to_player.get(loc.controller)
            if pid:
                if pid not in loc_info:
                    loc_info[pid] = {"locations": [], "regions": []}
                fortified = "★" if loc.is_fortified else ""
                loc_info[pid]["locations"].append(f"{loc_id}{fortified}")

        # Controlled regions
        for region, rs in state.regions.items():
            pid = cs_to_player.get(rs.control_marker)
            if pid:
                if pid not in loc_info:
                    loc_info[pid] = {"locations": [], "regions": []}
                loc_info[pid]["regions"].append(region.value)

        self._current_round["location_state"] = loc_info

    def log_round_end(self):
        """Finalize current round and append to log."""
        if self._current_round:
            self.log.rounds.append(self._current_round)
            self._current_round = None

    # ======== Player Actions ========

    def log_draw(self, player_id: str, cards_drawn: list[str],
                 forced_events: list[str], draw_events: list[dict] = None):
        """Record card draws at start of player's turn.

        Args:
            cards_drawn: Names of cards drawn into hand (for backward compat).
            forced_events: Names of mechanism cards drawn (for backward compat).
            draw_events: Raw draw events from state.draw_cards() for detailed display.
        """
        # Flush any pending effects (e.g. from setup) before draw logging
        self._flush_buffers_to_turn(player_id)
        turn = self._get_or_create_turn(player_id)
        turn["draw"] = {
            "cards": cards_drawn,
            "forced_events_triggered": forced_events,
        }
        if draw_events:
            turn["draw"]["events"] = draw_events

    def log_action(self, player_id: str, action_type: str,
                   description: str, params: dict = None,
                   costs: dict = None, results: dict = None,
                   state_snapshot: dict = None):
        """Record a single player action with context.

        Args:
            player_id: Who acted
            action_type: "march", "occupy", "court_action", "play_card", etc.
            description: Human-readable description in Chinese
            params: Key parameters (target, card played, etc.)
            costs: What was paid
            results: What was gained/changed
            state_snapshot: Brief post-action state (optional)
        """
        turn = self._get_or_create_turn(player_id)
        action_entry = {
            "type": action_type,
            "description": description,
        }
        if params:
            action_entry["params"] = params
        if costs:
            action_entry["costs"] = costs
        if results:
            action_entry["results"] = results
        if state_snapshot:
            action_entry["state"] = state_snapshot

        # Flush buffered effects for this player into this action
        if player_id in self._effect_buffer and self._effect_buffer[player_id]:
            action_entry["effects"] = self._effect_buffer.pop(player_id)
        if self._trigger_buffer:
            action_entry["triggers"] = list(self._trigger_buffer)
            self._trigger_buffer.clear()

        turn["actions"].append(action_entry)

    def _flush_buffers_to_turn(self, player_id: str):
        """Flush any remaining buffered effects/triggers to a turn entry.

        Called when effects fire without a subsequent action being logged
        (e.g. draw phase effects, turn-end triggers).
        """
        if not self._effect_buffer and not self._trigger_buffer:
            return
        turn = self._get_or_create_turn(player_id)
        # Flush effects belonging to this player
        if player_id in self._effect_buffer and self._effect_buffer[player_id]:
            turn.setdefault("effects", []).extend(self._effect_buffer.pop(player_id))
        # Also flush any orphan effects (from other players) to their respective turns
        for pid, effects in list(self._effect_buffer.items()):
            if effects:
                t = self._get_or_create_turn(pid)
                t.setdefault("effects", []).extend(effects)
            del self._effect_buffer[pid]
        if self._trigger_buffer:
            turn.setdefault("triggers", []).extend(list(self._trigger_buffer))
            self._trigger_buffer.clear()

    def log_end_turn(self, player_id: str, hand_discarded: int,
                     final_military: int, final_vp: int):
        """Record end-of-turn state."""
        self._flush_buffers_to_turn(player_id)
        turn = self._get_or_create_turn(player_id)
        turn["end_state"] = {
            "hand_size": "?",
            "discarded_to_limit": hand_discarded,
            "military": final_military,
            "vp": final_vp,
        }

    # ======== Passive Triggers ========

    def log_trigger(self, trigger_type: str, source_player_id: str,
                    source_card: str, context: dict = None):
        """Record a passive trigger firing.

        Triggers are buffered and flushed into the next action logged, so they
        appear inline with the action that caused them.
        """
        entry = {
            "trigger": trigger_type,
            "source_player": source_player_id,
            "source_card": source_card,
        }
        if context:
            entry["context"] = context
        self._trigger_buffer.append(entry)

    def log_effect(self, player_id: str, effect_type: str,
                   params: dict = None, events: list[dict] = None,
                   source: str = "card"):
        """Record an individual effect being resolved (state modification).

        Called from EffectResolver after each step executes, for both
        active card plays and passive trigger resolutions.

        Effects are buffered and flushed into the next action logged via
        log_action(), so they appear inline with the action that caused them.
        """
        entry = {
            "player": player_id,
            "effect": effect_type,
            "source": source,
        }
        if params:
            entry["params"] = params
        if events:
            entry["events"] = events
        self._effect_buffer.setdefault(player_id, []).append(entry)
    # ======== State Snapshots (periodic) ========

    def log_state_snapshot(self, label: str, state_data: dict):
        """Record a named point-in-time snapshot of game state.

        Args:
            label: e.g. "round_start", "after_action_phase"
            state_data: dict of relevant state values
        """
        if not self._current_round:
            return
        snapshots = self._current_round.setdefault("state_snapshots", [])
        snapshots.append({"label": label, "data": state_data})

    # ======== Final Scoring ========

    def log_final_scoring(self, scoring_result: dict, winner: str,
                          scores: dict[str, int], end_reason: str,
                          total_rounds: int):
        """Record final scoring results."""
        self.log.final_scoring = scoring_result
        self.log.winner = winner
        self.log.final_scores = scores
        self.log.end_reason = end_reason
        self.log.total_rounds = total_rounds

    # ======== Helpers ========

    def _get_or_create_turn(self, player_id: str) -> dict:
        """Get or create the turn entry for a player in the current round."""
        if not self._current_round:
            return {"actions": []}

        for turn in self._current_round["player_turns"]:
            if turn["player"] == player_id:
                return turn

        turn = {"player": player_id, "actions": [], "draw": {}}
        self._current_round["player_turns"].append(turn)
        return turn

    # ======== Export ========

    def to_json(self, pretty: bool = True) -> str:
        """Export log as JSON string."""
        data = {
            "game_id": self.log.game_id,
            "seed": self.log.seed,
            "players": self.log.players,
            "total_rounds": self.log.total_rounds,
            "end_reason": self.log.end_reason,
            "winner": self.log.winner,
            "final_scores": self.log.final_scores,
            "final_scoring": self.log.final_scoring,
            "rounds": self.log.rounds,
        }
        if pretty:
            return json.dumps(data, ensure_ascii=False, indent=2)
        return json.dumps(data, ensure_ascii=False)

    def to_text(self) -> str:
        """Export log as human-readable Chinese text."""
        lines = []
        lines.append(f"═══════════════════════════════════")
        lines.append(f"  六朝何事 — 游戏日志")
        lines.append(f"  Game ID: {self.log.game_id}")
        lines.append(f"  Seed: {self.log.seed}")
        lines.append(f"═══════════════════════════════════")
        lines.append("")

        # Players
        lines.append("【玩家】")
        for p in self.log.players:
            faction_label = {"north": "北方", "jin": "东晋", "sima": "司马家"}
            f = faction_label.get(p.get("faction", ""), p.get("faction", ""))
            locs = p.get("initial_locations", [])
            loc_str = f"，初始地点: {' '.join(locs)}" if locs else ""
            lines.append(f"  {p['id']} — {f} — {p['hero']} (部队储备: {p['army_reserve']}){loc_str}")
        lines.append("")

        # Setup cards
        setup = getattr(self.log, 'setup_cards', {})
        hands = getattr(self.log, 'initial_hands', {})
        if setup:
            lines.append("【初始暗置打出的牌（已弃置）】")
            for pid, card_name in setup.items():
                hand_str = ""
                if pid in hands:
                    hand_str = f"（手牌: {' '.join(hands[pid])}）"
                lines.append(f"  {pid}: {card_name} {hand_str}")
            lines.append("")

        # ── Setup round (round 0) — show full effect resolution ──
        setup_rounds = [r for r in self.log.rounds if r["round"] == 0]
        if setup_rounds:
            r = setup_rounds[0]
            lines.append("┌─ 初始暗置牌结算 ─────────────────────────────")
            for turn in r.get("player_turns", []):
                pid = turn["player"]
                for act in turn.get("actions", []):
                    desc = act.get("description", act.get("type", "?"))
                    lines.append(f"│ {pid}: {desc}")
                    costs = act.get("costs", {})
                    if costs:
                        cost_str = ", ".join(f"{k}:{v}" for k, v in costs.items())
                        lines.append(f"│   费用: {cost_str}")
                    results = act.get("results", {})
                    if results:
                        res_str = ", ".join(f"{k}:{v}" for k, v in results.items())
                        lines.append(f"│   结果: {res_str}")
                    # Inline effects from this action (same format as main rounds)
                    effects = act.get("effects", [])
                    if effects:
                        lines.append(f"│   ↪ 效果结算:")
                        for e in effects:
                            lines.append(f"│     {_format_effect(e)}")
                            evts = e.get("events", []) or []
                            for evt in evts:
                                t = evt.get("type", "")
                                if t and t not in ("effect_resolved",):
                                    detail = ", ".join(f"{k}={v}" for k, v in evt.items() if k != "type")
                                    if detail:
                                        lines.append(f"│       ↳ {t}: {detail}")
                                    else:
                                        lines.append(f"│       ↳ {t}")
            # Legacy round-level effects (backward compat)
            effects = r.get("effects_resolved", [])
            if effects:
                lines.append(f"│")
                lines.append(f"│ 效果结算 ({len(effects)} 步):")
                for e in effects:
                    lines.append(f"│   {_format_effect(e)}")
                    evts = e.get("events", []) or []
                    for evt in evts:
                        t = evt.get("type", "")
                        if t and t not in ("effect_resolved",):
                            detail = ", ".join(f"{k}={v}" for k, v in evt.items() if k != "type")
                            if detail:
                                lines.append(f"│     ↳ {t}: {detail}")
            triggers = r.get("triggers_fired", [])
            if triggers:
                for t in triggers:
                    src = t.get("source_card", "?")
                    tt = t.get("trigger", "?")
                    sp = t.get("source_player", "?")
                    lines.append(f"│ 触发: {tt} — {sp}的[{src}]")
            lines.append("└──────────────────────────────────────────────")
            lines.append("")
            # Remove round 0 from the rounds list so it's not rendered again below
            self.log.rounds = [r for r in self.log.rounds if r["round"] != 0]

        # Initial court
        nc = getattr(self.log, 'north_initial_court', [])
        jc = getattr(self.log, 'jin_initial_court', [])
        if nc or jc:
            lines.append("【初始朝堂牌】")
            if nc:
                cards_str = ", ".join(f"{c['name']}(+{c['army']}军/+{c['vp']}vp)" for c in nc)
                lines.append(f"  北方: {cards_str}")
            if jc:
                cards_str = ", ".join(f"{c['name']}(+{c['army']}军/+{c['vp']}vp)" for c in jc)
                lines.append(f"  东晋: {cards_str}")
            lines.append("")

        # Rounds
        for r in self.log.rounds:
            rn = r["round"]
            lines.append(f"───────────────────────────────────")
            lines.append(f"  第 {rn} 回合")
            lines.append(f"───────────────────────────────────")

            # Deck state at round start
            deck_info = r.get("deck_state", {})
            if deck_info:
                main_cnt = deck_info.get("main_count", 0)
                fe_list = deck_info.get("forced_events", [])
                fe_part = f"  已打出强制事件: [{', '.join(fe_list)}]" if fe_list else ""
                lines.append(f"  [牌库] 剩余: {main_cnt}张{fe_part}")

            # Preparation
            prep = r.get("preparation", {})
            dice = prep.get("emperor_dice", [])

            # Jin player status snapshot at round start
            jin_status = r.get("jin_status", [])
            if jin_status:
                lines.append(f"  [回合开始 东晋状态]")
                for js in jin_status:
                    hero = js.get("hero", "?")
                    lines.append(
                        f"    {js['id']} ({hero}): "
                        f"VP:{js.get('vp',0)} "
                        f"威望:{js.get('prestige',0)} "
                        f"功绩:{js.get('contribution',0)} "
                        f"顺位:{js.get('order',0)} "
                        f"军力:{js.get('military',0)}"
                    )

            if dice:
                lines.append(f"  [准备] 君主骰: {len(dice)} 个")
                for d in dice:
                    lines.append(f"    - {d.get('result', '?')}: {d}")

            # Player turns
            for turn in r.get("player_turns", []):
                pid = turn["player"]
                lines.append(f"")
                lines.append(f"  ▸ {pid} 行动")
                draw = turn.get("draw", {})
                raw_events = draw.get("events", [])
                if raw_events:
                    # Detailed display: group events by mechanism card boundaries
                    lines.append(f"    摸牌阶段 (摸2张):")
                    in_mechanism = False
                    for evt in raw_events:
                        t = evt.get("type", "")
                        card = evt.get("card", "?")
                        if t == "draw":
                            in_mechanism = False
                            lines.append(f"      ▸ {card} → 加入手牌")
                        elif t == "forced_event_drawn":
                            in_mechanism = True
                            lines.append(f"      ▸ {card} → [强制事件] 立即结算:")
                        elif t == "effect_errors":
                            lines.append(f"         ⚠ 错误: {evt.get('errors', [])}")
                        else:
                            prefix = "         ↳" if in_mechanism else "        ↳"
                            detail = ", ".join(f"{k}={v}" for k, v in evt.items()
                                             if k not in ("type",))
                            if detail:
                                lines.append(f"{prefix} {t}: {detail}")
                            else:
                                lines.append(f"{prefix} {t}")
                elif draw.get("cards") or draw.get("forced_events_triggered"):
                    # Fallback: simple display
                    if draw.get("cards"):
                        lines.append(f"    摸牌: {', '.join(draw['cards'])}")
                    if draw.get("forced_events_triggered"):
                        lines.append(f"    强制事件触发: {', '.join(draw['forced_events_triggered'])}")

                # Turn-level effects/triggers from the draw phase (forced events, etc.)
                # Rendered here so they immediately follow the draw display
                turn_effects = turn.get("effects", [])
                if turn_effects:
                    lines.append(f"       ↪ 效果结算 (摸牌阶段):")
                    for e in turn_effects:
                        lines.append(f"         {_format_effect(e)}")
                        evts = e.get("events", []) or []
                        for evt in evts:
                            t = evt.get("type", "")
                            if t and t not in ("effect_resolved",):
                                detail = ", ".join(f"{k}={v}" for k, v in evt.items() if k != "type")
                                if detail:
                                    lines.append(f"           ↳ {t}: {detail}")
                turn_triggers = turn.get("triggers", [])
                if turn_triggers:
                    for t in turn_triggers:
                        src = t.get("source_card", "?")
                        tt = t.get("trigger", "?")
                        sp = t.get("source_player", "?")
                        lines.append(f"       ↪ 触发: {tt} — {sp}的[{src}]")

                for act in turn.get("actions", []):
                    desc = act.get("description", act.get("type", "?"))
                    if act.get("type") == "turn_start":
                        snap = act.get("state", {})
                        parts = [f"VP:{snap.get('vp','?')}"]
                        if "prestige" in snap:
                            parts.append(f"威望:{snap['prestige']}")
                        if "contribution" in snap:
                            parts.append(f"功绩:{snap['contribution']}")
                        if "order" in snap:
                            parts.append(f"顺位:{snap['order']}")
                        lines.append(f"    → 回合开始（{'，'.join(parts)}）")
                    else:
                        lines.append(f"    → {desc}")
                    costs = act.get("costs", {})
                    if costs:
                        cost_str = ", ".join(f"{k}:{v}" for k, v in costs.items())
                        lines.append(f"       费用: {cost_str}")
                    results = act.get("results", {})
                    if results:
                        res_str = ", ".join(f"{k}:{v}" for k, v in results.items())
                        lines.append(f"       结果: {res_str}")

                    # Inline effects triggered by this action
                    effects = act.get("effects", [])
                    if effects:
                        lines.append(f"       ↪ 效果结算:")
                        for e in effects:
                            lines.append(f"         {_format_effect(e)}")
                            evts = e.get("events", []) or []
                            for evt in evts:
                                t = evt.get("type", "")
                                if t and t not in ("effect_resolved",):
                                    detail = ", ".join(f"{k}={v}" for k, v in evt.items() if k != "type")
                                    if detail:
                                        lines.append(f"           ↳ {t}: {detail}")
                                    else:
                                        lines.append(f"           ↳ {t}")

                    # Inline triggers fired by this action
                    triggers = act.get("triggers", [])
                    if triggers:
                        for t in triggers:
                            src = t.get("source_card", "?")
                            tt = t.get("trigger", "?")
                            sp = t.get("source_player", "?")
                            ctx = t.get("context", {})
                            ctx_str = ""
                            if ctx.get("action_type"):
                                ctx_str = f" → {ctx['action_type']}"
                            lines.append(f"       ↪ 触发: {tt} — {sp}的[{src}]{ctx_str}")

                end = turn.get("end_state", {})
                if end:
                    lines.append(f"    结束 — VP:{end.get('vp', '?')} 军力:{end.get('military', '?')}")

            # Settlement
            settle = r.get("settlement", {})
            if settle:
                lines.append(f"  [结算] 阶段完成")

            # Deck state at round end
            deck_info = r.get("deck_state", {})
            if deck_info:
                lines.append(f"  [回合结束 牌库状态]")
                for faction_key, faction_label in [("north", "北方"), ("jin", "东晋")]:
                    info = deck_info.get(faction_key, {})
                    deck_cards = ' '.join(info.get('deck', [])) or '(空)'
                    discard_cards = ' '.join(info.get('discard', [])) or '(空)'
                    court_cards = ' '.join(info.get('court', [])) or '(空)'
                    lines.append(f"    {faction_label}:")
                    lines.append(f"      牌库({len(info.get('deck', []))}): {deck_cards}")
                    lines.append(f"      弃牌({len(info.get('discard', []))}): {discard_cards}")
                    lines.append(f"      朝堂({len(info.get('court', []))}): {court_cards}")

            # Location control at round end
            loc_state = r.get("location_state", {})
            if loc_state:
                lines.append(f"  [回合结束 地区控制]")
                # Sort: north first, then jin players, then sima
                priority = {"north": 0, "jin_1": 1, "jin_2": 2, "jin_3": 3, "sima": 4}
                for pid in sorted(loc_state.keys(), key=lambda p: priority.get(p, 99)):
                    info = loc_state[pid]
                    locs = ' '.join(info.get('locations', [])) or '(无)'
                    regions = ' '.join(info.get('regions', [])) or '(无)'
                    lines.append(f"    {pid}:")
                    lines.append(f"      占据地点: {locs}")
                    lines.append(f"      控制区域: {regions}")

        # Final scoring
        lines.append(f"")
        lines.append(f"═══════════════════════════════════")
        lines.append(f"  终局计分")
        lines.append(f"═══════════════════════════════════")
        lines.append(f"  结束原因: {self.log.end_reason}")
        lines.append(f"  总回合数: {self.log.total_rounds}")
        lines.append(f"")

        # Detailed scoring steps
        scoring = self.log.final_scoring or {}
        steps = scoring.get("steps", [])
        if steps:
            for s in steps:
                lines.append(f"  ▸ {s.get('name', '?')}")
                detail = s.get("detail", "")
                if isinstance(detail, dict):
                    for k, v in detail.items():
                        if isinstance(v, dict):
                            lines.append(f"      {k}:")
                            for sub_k, sub_v in v.items():
                                if isinstance(sub_v, (int, float)):
                                    lines.append(f"        {sub_k}: {sub_v} VP")
                                else:
                                    lines.append(f"        {sub_k}: {sub_v}")
                        elif isinstance(v, list):
                            lines.append(f"      {k}: {', '.join(str(x) for x in v)}")
                        else:
                            lines.append(f"      {k}: {v}")
                elif isinstance(detail, list):
                    for item in detail:
                        if isinstance(item, dict):
                            for dk, dv in item.items():
                                lines.append(f"      {dk}: {dv}")
                        else:
                            lines.append(f"      - {item}")
                elif detail:
                    lines.append(f"      {detail}")
                lines.append(f"")

        # Final scores — build labels from actual hero names
        hero_map = {p["id"]: p.get("hero", "?") for p in self.log.players}
        faction_labels = {"north": "北方", "sima": "司马家"}
        for pid, score in self.log.final_scores.items():
            marker = " ★胜者" if pid == self.log.winner else ""
            if pid in faction_labels:
                label = faction_labels[pid]
            elif pid.startswith("jin_"):
                hero = hero_map.get(pid, "?")
                label = f"东晋-{hero}"
            else:
                label = pid
            lines.append(f"  {label} ({pid}): {score} VP{marker}")

        return "\n".join(lines)

    def save(self, filepath: str, format: str = "json"):
        """Save log to file. format: 'json' or 'text'."""
        if format == "json":
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(self.to_json())
        elif format == "text":
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(self.to_text())


# ======== Quick state snapshot for action context ========

def snapshot_player_state(state: "GameState", player_id: str) -> dict:
    """Create a brief state snapshot for logging."""
    player = state.get_player(player_id)
    if not player:
        return {}
    return {
        "hand_size": len(player.hand),
        "staff_size": len(player.staff_area),
        "military": player.military,
        "vp": player.vp,
        "prestige": player.prestige if player.faction.value == "jin" else None,
        "contribution": player.contribution if player.faction.value == "jin" else None,
        "army_on_map": player.army_placed_count,
        "army_in_reserve": player.army_reserve_count,
    }


def describe_action(action: "GameAction", state: "GameState",
                    result: "ActionResult" = None) -> tuple[str, dict, dict, dict]:
    """Produce a Chinese description + params/costs/results for an action.

    Args:
        action: The executed GameAction.
        state: Current game state snapshot.
        result: Optional ActionResult from execute(). When provided, card/payment
                names are extracted from result.events (which are captured before
                hand mutation) rather than re-reading player.hand (which has
                already been modified by execution).

    Returns: (description, params, costs, results)
    """
    atype = getattr(action, 'action_type', '?')
    player = state.get_player(getattr(action, 'player_id', ''))

    desc = ""
    params = {}
    costs = {}
    results = {}

    if atype == "march":
        target = getattr(action, 'target_location', '?')
        params["target"] = target
        cost = getattr(action, '_last_cost', None)
        if cost is None:
            try:
                cost = action._calculate_cost(state) if hasattr(action, '_calculate_cost') else '?'
            except Exception:
                cost = '?'
        costs["military"] = cost if cost is not None else '?'
        desc = f"进军 → {target}"
        results["vp"] = 1
        if player and player.faction.value == "jin":
            results["prestige"] = 1

    elif atype == "occupy":
        target = getattr(action, 'target_location', '?')
        params["target"] = target
        costs["military"] = 1
        sima = getattr(action, 'use_sima_army', False)
        desc = f"占据 → {target}" + (" (司马家)" if sima else "")

    elif atype == "play_card":
        # Prefer result.events for card/payment names — they are captured
        # before execution mutates the hand. Fall back to reading the hand
        # (for callers that don't pass result).
        card_name = None
        payment_names = None
        card_cost = 0
        is_friend = False
        card_type_value = None

        if result and result.events:
            for evt in result.events:
                if evt.get("type") == "play_card":
                    card_name = evt.get("card")
                    payment_names = evt.get("payment_cards", [])
                    break
            # Determine card fate from events (hand may be mutated after execution)
            for evt in result.events:
                if evt.get("type") == "friend_played":
                    is_friend = True
                elif evt.get("type") == "strategy_played":
                    card_type_value = "strategy"
                elif evt.get("type") == "event_played":
                    card_type_value = "event"

        if card_name is None:
            # Fallback: re-read from hand (may be stale after execution)
            idx = getattr(action, 'card_index', -1)
            payment_indices = getattr(action, 'payment_indices', [])
            payment_names = []
            if player:
                for pi in sorted(payment_indices, reverse=True):
                    if 0 <= pi < len(player.hand) and pi != idx:
                        payment_names.append(player.hand[pi].name)
            if player and 0 <= idx < len(player.hand):
                card = player.hand[idx]
                card_name = card.name
                card_cost = card.cost
                is_friend = card.is_friend
                card_type_value = card.card_type.value if card.card_type else None

        costs["payment_cards"] = payment_names if payment_names else None
        params["card"] = card_name or "?"
        params["cost"] = card_cost

        desc = f"打出 {card_name or '(手牌)'}"
        if payment_names:
            desc += f"（支付: {' '.join(payment_names)}）"
        if is_friend:
            desc += " → 幕僚区"
        elif card_type_value == "strategy":
            desc += " → 国家牌库"
        elif card_type_value == "event":
            desc += " (事件)"

    elif atype == "play_public_card":
        cid = getattr(action, 'card_id', '')
        payment_indices = getattr(action, 'payment_indices', [])
        payment_names = []
        if player:
            for pi in sorted(payment_indices, reverse=True):
                if 0 <= pi < len(player.hand):
                    payment_names.append(player.hand[pi].name)
        costs["payment_cards"] = payment_names if payment_names else None

        # Find card name from public pool
        card_name = cid
        card_cost = 0
        for c in state.public_action_pool:
            if c.definition.card_id == cid:
                card_name = c.name
                card_cost = c.cost
                break
        params["card"] = card_name
        params["card_id"] = cid
        params["cost"] = card_cost
        desc = f"公共行动: {card_name}"
        if payment_names:
            desc += f"（支付: {' '.join(payment_names)}）"

    elif atype == "court_action":
        cid = getattr(action, 'card_id', '')
        params["card_id"] = cid

        # Prefer card name from result.events (captured before court mutation)
        card_name = None
        if result and result.events:
            for evt in result.events:
                if evt.get("type") == "court_action" and evt.get("card"):
                    card_name = evt["card"]
                    break

        if card_name is None:
            # Fallback: look up in court (may be empty after execution)
            court = state.get_court_cards(getattr(action, 'player_id', ''))
            for c in court:
                if c.definition.card_id == cid:
                    card_name = c.name
                    break

        # Describe court action using pre-parsed AST if card found
        effects = []
        if card_name:
            params["card"] = card_name
            # Try to get effect description from any known def
            from cards.effect_ast import AbilityType, EffectType
            court = state.get_court_cards(getattr(action, 'player_id', ''))
            for c in court:
                if c.definition.card_id == cid:
                    parsed = c.definition.parsed_effect
                    if parsed:
                        for block in parsed.blocks:
                            if block.ability_type == AbilityType.STRATEGY_ACTION:
                                for step in block.steps:
                                    if step.effect_type == EffectType.GAIN_MILITARY:
                                        effects.append(f"+{step.params.get('amount','?')}军力")
                                    elif step.effect_type == EffectType.GAIN_VP:
                                        effects.append(f"+{step.params.get('amount','?')}vp")
                                    elif step.effect_type == EffectType.DRAW_CARDS:
                                        effects.append(f"摸{step.params.get('count','?')}张牌")
                                    elif step.effect_type == EffectType.ARCHIVE_CARD:
                                        effects.append("存档候选牌")
                                    elif step.effect_type == EffectType.RAISE_ORDER:
                                        effects.append("提高顺位")
                                    elif step.effect_type == EffectType.SPREAD_CULTURE:
                                        effects.append("传播文化")
                                    elif step.effect_type == EffectType.DISCARD_CARDS:
                                        effects.append(f"弃{step.params.get('count','?')}手牌")
                    break

        if card_name:
            desc = f"牌组行动: {card_name}"
            if effects:
                desc += f"（{'，'.join(effects)}）"
        else:
            desc = f"牌组行动"

    elif atype == "draw":
        card_name = None
        if result and result.events:
            for evt in result.events:
                if evt.get("type") == "draw":
                    card_name = evt.get("card", "?")
                    break
        if card_name:
            desc = f"摸牌 (快速行动): 「{card_name}」"
        else:
            desc = "摸牌 (快速行动)"

    elif atype == "recruit":
        # Card was already discarded, get name from result events not hand.
        # Fall back to reading from hand if result not available (preview mode).
        card_name = "?"
        if result and result.events:
            for evt in result.events:
                if evt.get("type") == "recruit" and evt.get("discarded"):
                    card_name = evt["discarded"]
                    break
        if card_name == "?" and player:
            idx = getattr(action, 'card_to_discard_index', -1)
            if 0 <= idx < len(player.hand):
                card_name = player.hand[idx].name
        desc = f"征募: 弃「{card_name}」换1军力"

    elif atype == "fortify":
        target = getattr(action, 'target_location', '?')
        params["target"] = target
        costs["military"] = 1
        desc = f"加固 → {target}"

    elif atype == "convert":
        target = getattr(action, 'target_location', '?')
        params["target"] = target
        desc = f"转化 → {target}"

    elif atype == "archive":
        desc = "存档"

    elif atype == "spread_culture":
        culture = getattr(action, 'culture_type', '?')
        region = getattr(action, 'target_region', '?')
        culture_label = {"confucianism": "儒学", "taoism": "玄学", "buddhism": "佛学"}.get(culture, culture)
        params["culture"] = culture_label
        params["region"] = region
        desc = f"传播文化: {culture_label} → {region}"

    elif atype == "search":
        desc = "检索牌库"

    elif atype == "levy":
        desc = "征发候选策略牌"

    elif atype == "raise_order":
        desc = "提高行动顺位"

    elif atype == "lower_order":
        desc = "降低行动顺位"

    elif atype == "activate_effect":
        # Extract card name and effect summary from result events.
        # Fall back to looking up card from state if result not available (preview mode).
        card_name = None
        effects_desc = []
        if result and result.events:
            for evt in result.events:
                if evt.get("type") == "activate_effect":
                    card_name = evt.get("card", "?")
                elif evt.get("type") == "discard":
                    discarded = evt.get("card", "?")
                    source = evt.get("source", "")
                    if source == "court":
                        effects_desc.append(f"弃朝堂「{discarded}」")
                    else:
                        effects_desc.append(f"弃「{discarded}」")
                elif evt.get("type") == "draw":
                    drawn = evt.get("card", "?")
                    effects_desc.append(f"摸「{drawn}」")
                elif evt.get("type") == "gain_military":
                    effects_desc.append(f"+{evt.get('amount', '?')}军力")
                elif evt.get("type") == "gain_vp":
                    effects_desc.append(f"+{evt.get('amount', '?')}vp")
                elif evt.get("type") == "fortify_requested":
                    target = evt.get("target", "?")
                    if evt.get("skipped"):
                        effects_desc.append(f"加固→{target}(跳过:{evt.get('reason','')})")
                    else:
                        effects_desc.append(f"加固→{target}")
                elif evt.get("type") == "convert_requested":
                    if not evt.get("skipped"):
                        target = evt.get("target", "?")
                        effects_desc.append(f"转化→{target}")
                elif evt.get("type") == "spread_culture_vp":
                    effects_desc.append(f"传播文化+{evt.get('vp','?')}vp")
                elif evt.get("type") == "raise_order":
                    effects_desc.append(f"顺位→{evt.get('new_order','?')}")

        # Fallback: look up card from state when result is not available
        if card_name is None and player:
            card_id = getattr(action, 'card_id', '')
            if card_id:
                if player.hero and player.hero.definition.card_id == card_id:
                    card_name = player.hero.name
                else:
                    for c in player.staff_area:
                        if c.definition.card_id == card_id:
                            card_name = c.name
                            break

        desc = f"激活「{card_name or '?'}」"
        if effects_desc:
            desc += f"（{'，'.join(effects_desc)}）"

    else:
        desc = str(atype)

    return desc, params, costs, results


def log_action_result(logger, action, result, state):
    """Shared logging helper: describe → execute result → log action.

    Used by both _run_round() (normal play) and _execute_setup_face_down_cards()
    (setup phase) so the logging format is identical.

    Args:
        logger: GameLogger instance
        action: GameAction that was executed
        result: ActionResult from action_system.execute()
        state: GameState snapshot
    """
    desc, params, costs, _ = describe_action(action, state, result)

    atype = getattr(action, 'action_type', '')
    skip_military_result = (atype == "recruit")  # Description already says "换1军力"

    results = {}
    for evt in (result.events or []):
        if evt.get("type") == "court_action" and "card" in evt:
            params["card"] = evt["card"]
        if "vp_gained" in evt:
            results["vp"] = evt.get("vp_gained", 0)
        if "military_gained" in evt and not skip_military_result:
            results["military"] = evt.get("military_gained", 0)
        if evt.get("type") == "card_discarded":
            results["discard_reason"] = evt.get("reason", "")
        if evt.get("type") == "friend_played":
            results["staffed"] = evt.get("card", "")
        if evt.get("type") == "strategy_played":
            results["added_to"] = "国家牌库"
        if evt.get("type") == "event_played":
            results["resolved"] = "event"
        if evt.get("type") == "staff_replaced":
            results["replaced"] = evt.get("replaced_by", ""); results["removed"] = evt.get("card", "")
        if evt.get("type") == "draw":
            params["drawn_card"] = evt.get("card", "?")
        if evt.get("type") == "forced_event_drawn":
            params["forced_event"] = evt.get("card", "?")
        # Block-level costs
        if evt.get("type") == "pay_military":
            costs["pay_military"] = evt.get("amount", 0)
        if evt.get("type") == "pay_vp":
            costs["pay_vp"] = evt.get("amount", 0)
        if evt.get("type") == "gain_vp":
            results["vp"] = (results.get("vp") or 0) + evt.get("amount", 0)
        if evt.get("type") == "reform_vp":
            results["reform_vp"] = evt.get("vp", 0)
        if evt.get("type") == "archive_this":
            results["archived"] = True
        if evt.get("type") == "capital_relocated":
            results["capital_relocated"] = {
                "to": evt.get("to", "?"),
                "chosen_by": evt.get("chosen_by", "?"),
                "was_player_location": evt.get("was_player_location", False),
            }

    snap = snapshot_player_state(state, action.player_id)
    logger.log_action(
        player_id=action.player_id,
        action_type=getattr(action, 'action_type', '?'),
        description=desc,
        params=params,
        costs=costs,
        results=results,
        state_snapshot=snap,
    )
