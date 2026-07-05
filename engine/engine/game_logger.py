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


class GameLogger:
    """Captures structured game events during play."""

    def __init__(self):
        self.log = GameLog()
        self._current_round: Optional[dict] = None
        self._pending_actions: list[dict] = []

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
        }

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

    def log_round_end(self):
        """Finalize current round and append to log."""
        if self._current_round:
            self.log.rounds.append(self._current_round)
            self._current_round = None

    # ======== Player Actions ========

    def log_draw(self, player_id: str, cards_drawn: list[str],
                 forced_events: list[str]):
        """Record card draws at start of player's turn."""
        turn = self._get_or_create_turn(player_id)
        turn["draw"] = {
            "cards": cards_drawn,
            "forced_events_triggered": forced_events,
        }

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

        turn["actions"].append(action_entry)

    def log_end_turn(self, player_id: str, hand_discarded: int,
                     final_military: int, final_vp: int):
        """Record end-of-turn state."""
        turn = self._get_or_create_turn(player_id)
        turn["end_state"] = {
            "hand_size": "?",
            "discarded_to_limit": hand_discarded,
            "military": final_military,
            "vp": final_vp,
        }

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

            # Preparation
            prep = r.get("preparation", {})
            dice = prep.get("emperor_dice", [])
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
                if draw.get("cards"):
                    lines.append(f"    摸牌: {', '.join(draw['cards'])}")
                if draw.get("forced_events_triggered"):
                    lines.append(f"    强制事件触发: {', '.join(draw['forced_events_triggered'])}")

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

                end = turn.get("end_state", {})
                if end:
                    lines.append(f"    结束 — VP:{end.get('vp', '?')} 军力:{end.get('military', '?')}")

            # Settlement
            settle = r.get("settlement", {})
            if settle:
                lines.append(f"  [结算] 阶段完成")

        # Final scoring
        lines.append(f"")
        lines.append(f"═══════════════════════════════════")
        lines.append(f"  终局计分")
        lines.append(f"═══════════════════════════════════")
        lines.append(f"  结束原因: {self.log.end_reason}")
        lines.append(f"  总回合数: {self.log.total_rounds}")
        lines.append(f"")
        for pid, score in self.log.final_scores.items():
            marker = " ★胜者" if pid == self.log.winner else ""
            lines.append(f"  {pid}: {score} VP{marker}")

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


def describe_action(action: "GameAction", state: "GameState") -> tuple[str, dict, dict, dict]:
    """Produce a Chinese description + params/costs/results for an action.

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
        desc = f"占据 → {target}"

    elif atype == "play_card":
        idx = getattr(action, 'card_index', -1)
        payment_indices = getattr(action, 'payment_indices', [])
        # Capture payment card names BEFORE they get discarded
        payment_names = []
        if player:
            for pi in sorted(payment_indices, reverse=True):
                if 0 <= pi < len(player.hand) and pi != idx:
                    payment_names.append(player.hand[pi].name)
        costs["payment_cards"] = payment_names if payment_names else None

        if player and 0 <= idx < len(player.hand):
            card = player.hand[idx]
            params["card"] = card.name
            params["cost"] = card.cost
            desc = f"打出 {card.name}"
            if payment_names:
                desc += f"（支付: {' '.join(payment_names)}）"
            if card.is_friend:
                desc += " → 幕僚区"
            elif card.card_type.value == "strategy":
                desc += " → 国家牌库"
            else:
                desc += " (事件)"
        else:
            desc = "打出 (手牌)"

    elif atype == "court_action":
        cid = getattr(action, 'card_id', '')
        params["card_id"] = cid
        court = state.get_court_cards(getattr(action, 'player_id', ''))
        for c in court:
            if c.definition.card_id == cid:
                defn = c.definition
                params["card"] = c.name
                # Describe court action using pre-parsed AST
                from cards.effect_ast import AbilityType, EffectType
                parsed = defn.parsed_effect
                effects = []
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
                desc = f"牌组行动: {c.name}"
                if effects:
                    desc += f"（{'，'.join(effects)}）"
                break
        if not desc:
            desc = f"牌组行动"

    elif atype == "draw":
        desc = "摸牌 (快速行动)"

    elif atype == "recruit":
        idx = getattr(action, 'card_to_discard_index', 0)
        card_name = "?"
        if player and 0 <= idx < len(player.hand):
            card_name = player.hand[idx].name
        desc = f"征募: 弃{card_name}换1军力"

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

    else:
        desc = str(atype)

    return desc, params, costs, results
