"""Game orchestrator — main game loop with logging support."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import random
from typing import Optional

from models.enums import PhaseType, CardType
from models.card import CardLibrary
from models.game_state import GameState
from ai.interface import GameAgent
from .action_system import ActionSystem
from .phases import (
    setup_game, run_preparation_phase, run_player_draw,
    run_settlement_phase,
)


class GameEngine:
    """Main game orchestrator. Ties together phases, agents, and action system.

    Accepts either a Version object (recommended) or a CardLibrary (backward compat).
    """

    def __init__(self, agents: list[GameAgent],
                 library: CardLibrary = None,
                 version: "Version" = None,
                 seed: int = 0, action_system: ActionSystem = None,
                 logger: "GameLogger" = None):
        # Support both old (library=) and new (version=) API
        if version is not None:
            self.library = version.card_library
            self.version = version
            self.map_adjacencies = version.map
        elif library is not None:
            self.library = library
            self.version = None
            self.map_adjacencies = []
        else:
            raise ValueError("Must provide either library= or version=")

        self.agents = agents
        self.rng = random.Random(seed)
        self.action_system = action_system or ActionSystem()
        self.state: Optional[GameState] = None
        self.max_rounds = self.version.get("max_rounds", 10) if self.version else 10
        self.logger = logger

    def run(self) -> GameState:
        """Run a complete game from setup to game over."""
        self.state = setup_game(
            self.library, self.agents,
            self.rng.randint(0, 999999),
            version=self.version,
            map_adjacencies=self.map_adjacencies,
        )
        self.state.action_system = self.action_system

        # Inject EffectResolver so card actions can use it
        from cards.effect_resolver import EffectResolver
        self.state.effect_resolver = EffectResolver(self.action_system)

        if self.logger:
            self.logger.log_game_start(self.state, self.state.seed)
            initial_hands = {}
            for p in self.state.get_all_players():
                initial_hands[p.player_id] = [c.name for c in p.hand]
            self.logger.log_setup_cards(self.state, {}, initial_hands)
            self.logger.log_initial_court(self.state)

        # === Execute initial face-down cards (rulebook §4.1 step 7) ===
        # North first, then Jin by start order
        from .actions.card_actions import PlayCardAction
        jin_sorted = sorted(self.state.jin_players, key=lambda p: p.order)
        setup_order = [self.state.north_player] + jin_sorted
        setup_cards_played = {}
        for player in setup_order:
            if player.hand:
                idx = getattr(player, '_setup_face_down_index', 0)
                payment = getattr(player, '_setup_payment_indices', [])
                if idx >= len(player.hand):
                    idx = 0
                card = player.hand[idx]
                cost = card.cost
                # Use agent-chosen payment, or find from other cards
                other_indices = [i for i in payment if i != idx and 0 <= i < len(player.hand)]
                if len(other_indices) < cost:
                    remaining = [i for i in range(len(player.hand)) if i != idx and i not in other_indices]
                    other_indices = other_indices + remaining[:cost - len(other_indices)]

                # Capture payment card names BEFORE execution
                payment_names = []
                for pi in sorted(other_indices[:cost], reverse=True):
                    if 0 <= pi < len(player.hand) and pi != idx:
                        payment_names.append(player.hand[pi].name)

                if len(other_indices) >= cost:
                    # Check if event card condition is met
                    condition_met = True
                    from models.enums import CardType as CT
                    if card.card_type == CT.EVENT:
                        condition_met = _check_event_condition(card, player, self.state)

                    action = PlayCardAction(
                        player_id=player.player_id,
                        card_index=idx,
                        payment_indices=other_indices[:cost],
                    )
                    if condition_met:
                        result = self.action_system.execute(self.state, action)
                    else:
                        # Pay cost but no effect — discard manually
                        discarding = sorted(other_indices[:cost] + [idx], reverse=True)
                        for di in discarding:
                            if 0 <= di < len(player.hand):
                                self.state.main_discard.append(player.hand.pop(di))
                        result = None
                    setup_cards_played[player.player_id] = {
                        "card": card.name, "cost": cost,
                        "payment": payment_names,
                        "success": condition_met,
                        "condition_met": condition_met,
                    }
                else:
                    self.state.main_discard.append(player.hand.pop(idx))
                    setup_cards_played[player.player_id] = {
                        "card": card.name, "cost": cost,
                        "payment": [],
                        "success": False, "error": "insufficient payment",
                    }

        if self.logger:
            setup_cards_simple = {
                pid: f"{v['card']}（支付: {' '.join(v.get('payment', []))}）"
                      if v.get('payment') else v['card']
                for pid, v in setup_cards_played.items()
            }
            self.logger.log_setup_cards(self.state, setup_cards_simple, initial_hands)

        # Main game loop
        while self.state.phase != PhaseType.GAME_OVER:
            self._run_round()

        # Run final scoring
        from rules.scoring import run_final_scoring
        scoring_result = run_final_scoring(self.state)

        if self.logger:
            scores = {p.player_id: p.vp for p in self.state.get_all_players()}
            winner = self._determine_winner()
            self.logger.log_final_scoring(
                scoring_result={"steps": [s["name"] for s in scoring_result.steps]},
                winner=winner,
                scores=scores,
                end_reason=self.state.game_end_reason or "round_10",
                total_rounds=self.state.round,
            )

        return self.state

    def run_until_round(self, target_round: int) -> GameState:
        """Run until a specific round (for testing)."""
        self.state = setup_game(
            self.library, self.agents,
            self.rng.randint(0, 999999),
            version=self.version,
            map_adjacencies=self.map_adjacencies,
        )

        while (self.state.phase != PhaseType.GAME_OVER and
               self.state.round <= target_round):
            self._run_round()

        return self.state

    def _run_round(self):
        """Execute one full round."""
        state = self.state

        if self.logger:
            self.logger.log_round_start(state.round)

        # === Preparation Phase ===
        run_preparation_phase(state, self.rng)

        # Rulebook §4.2: 准备阶段结算区控奖励
        from rules.scoring import award_region_control_phase
        award_region_control_phase(state, player_id=None)

        if self.logger:
            self.logger.log_preparation(
                emperor_events=[], sima_dist=[], region_vp=[],
            )

        # === Action Phase ===
        for player_id in state.turn_order:
            player = state.get_player(player_id)
            if not player:
                continue

            agent = self._get_agent(player_id)
            if not agent:
                continue

            # Reset action flags (but keep military from settlement)
            player.reset_action_flags()

            # Rulebook §4.2: 玩家行动开始时结算区控奖励
            award_region_control_phase(state, player_id=player_id)

            # Draw 2 cards
            draw_events = run_player_draw(state, player_id)

            if self.logger:
                cards_drawn = [e.get("card", "?") for e in draw_events
                               if e.get("type") == "draw"]
                forced = [e.get("card", "?") for e in draw_events
                          if e.get("type") == "forced_event_drawn"]
                self.logger.log_draw(player_id, cards_drawn, forced)
                # Log current status (VP, prestige, contribution, order)
                status = {
                    "vp": player.vp,
                    "military": player.military,
                }
                if player.faction.value == "jin":
                    status["prestige"] = player.prestige
                    status["contribution"] = player.contribution
                    status["order"] = player.order
                self.logger.log_action(player_id, "turn_start", "回合开始",
                                       state_snapshot=status)

            # Let the agent take their turn
            actions = agent.take_turn(state)
            for action in actions:
                # Capture description BEFORE execution
                if self.logger:
                    from .game_logger import describe_action, snapshot_player_state
                    desc, params, costs, _ = describe_action(action, state)

                result = self.action_system.execute(state, action)

                if self.logger:
                    # Extract results from execution events
                    results = {}
                    for evt in (result.events or []):
                        if evt.get("type") == "court_action":
                            if "card" in evt:
                                params["card"] = evt["card"]
                        if "vp_gained" in evt:
                            results["vp"] = evt.get("vp_gained", 0)
                        if "military_gained" in evt:
                            results["military"] = evt.get("military_gained", 0)
                    snap = snapshot_player_state(state, player_id)
                    self.logger.log_action(
                        player_id=player_id,
                        action_type=getattr(action, 'action_type', '?'),
                        description=desc,
                        params=params,
                        costs=costs,
                        results=results,
                        state_snapshot=snap,
                    )

                if not result.success:
                    pass

            # Enforce hand limit
            discarded = 0
            while len(player.hand) > player.hand_limit:
                state.main_discard.append(player.hand.pop())
                discarded += 1

            if self.logger:
                self.logger.log_end_turn(player_id, discarded,
                                         player.military, player.vp)

            # 任意玩家行动结束时，弃牌区全部洗入主牌库（重洗牌堆）
            if len(state.forced_event_pile) >= 3:
                state.main_discard.extend(state.forced_event_pile)
                state.forced_event_pile = []
                self.rng.shuffle(state.main_discard)
                state.main_deck.extend(state.main_discard)
                state.main_discard = []

        # === Settlement Phase ===
        run_settlement_phase(state, self.rng)

        if self.logger:
            self.logger.log_settlement(
                court_vp={}, military_gain={}, emperor_age=[],
            )
            self.logger.log_round_end()

    def _get_agent(self, player_id: str) -> Optional[GameAgent]:
        for agent in self.agents:
            if agent.player_id == player_id:
                return agent
        return None

    def _determine_winner(self) -> Optional[str]:
        if not self.state:
            return None
        players = self.state.get_all_players()
        if not players:
            return None
        best = max(players, key=lambda p: p.vp)
        # Tiebreaker
        tied = [p for p in players if p.vp == best.vp]
        if len(tied) > 1:
            best = max(tied, key=lambda p: len(p.history_area))
            still_tied = [p for p in tied
                          if len(p.history_area) == len(best.history_area)]
            if len(still_tied) > 1:
                from models.enums import FactionType
                north_in = any(p.faction == FactionType.NORTH for p in still_tied)
                if north_in:
                    best = next(p for p in still_tied
                                if p.faction == FactionType.NORTH)
                else:
                    best = min(still_tied, key=lambda p: p.order)
        return best.player_id

    def get_winner(self) -> Optional[str]:
        return self._determine_winner()

    def get_scores(self) -> dict[str, int]:
        if not self.state:
            return {}
        return {p.player_id: p.vp for p in self.state.get_all_players()}


def _check_event_condition(card, player, state) -> bool:
    """Check if an event card's play condition is met using pre-parsed AST.

    Delegates to EffectResolver.check_condition() for all supported condition types.
    """
    parsed = card.definition.parsed_effect
    if not parsed or not parsed.play_condition:
        return True  # No condition → always playable

    cond = parsed.play_condition
    resolver = getattr(state, 'effect_resolver', None)
    if resolver:
        return resolver.check_condition(cond, state, player.player_id)

    # Fallback: no resolver available
    return True
