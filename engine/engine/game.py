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
            action_system=self.action_system,
            logger=self.logger,
        )
        self._post_setup_init()

        # Main game loop
        while self.state.phase != PhaseType.GAME_OVER:
            self._run_round()

        # Fire end-game triggers
        self._check_triggers("on_end_game", {})

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
        """Run until a specific round (for testing).

        Has identical initialization to run(), including:
        - EffectResolver with callbacks
        - Face-down card execution via setup_game()
        - Logging (if logger is set)
        """
        self.state = setup_game(
            self.library, self.agents,
            self.rng.randint(0, 999999),
            version=self.version,
            map_adjacencies=self.map_adjacencies,
            action_system=self.action_system,
            logger=self.logger,
        )
        self._post_setup_init()

        while (self.state.phase != PhaseType.GAME_OVER and
               self.state.round <= target_round):
            self._run_round()

        return self.state

    def _post_setup_init(self):
        """Wire callbacks and log setup summary after setup_game() returns."""
        # Wire trigger_callback — can only be done here (needs self._check_triggers)
        if self.state and self.state.effect_resolver:
            self.state.effect_resolver.trigger_callback = self._check_triggers
            # Re-attach log_callback via engine (takes priority over wrapper)
            if self.logger:
                self.state.effect_resolver.log_callback = self._log_effect

        if self.logger:
            self.logger.log_game_start(self.state, self.state.seed)
            initial_hands = {}
            for p in self.state.get_all_players():
                initial_hands[p.player_id] = [c.name for c in p.hand]

            setup_cards_played = getattr(self.state, '_setup_cards_played', {})
            setup_cards_simple = {
                pid: f"{v['card']}（支付: {' '.join(v.get('payment', []))}）"
                      if v.get('payment') else v['card']
                for pid, v in setup_cards_played.items()
            }
            self.logger.log_setup_cards(self.state, setup_cards_simple, initial_hands)
            self.logger.log_initial_court(self.state)

    def _run_round(self):
        """Execute one full round."""
        state = self.state

        if self.logger:
            self.logger.log_round_start(state.round)

        # === Preparation Phase ===
        emperor_events = run_preparation_phase(state, self.rng)

        # Rulebook §4.2: 准备阶段结算区控奖励
        from rules.scoring import award_region_control_phase
        award_region_control_phase(state, player_id=None)

        if self.logger:
            self.logger.log_preparation(
                emperor_events=emperor_events, sima_dist=[], region_vp=[],
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
            self._check_triggers("on_region_reward",
                                 {"player_id": player_id, "phase": "player_action"})

            # Fire turn_start triggers
            self._check_triggers("on_turn_start", {"player_id": player_id})

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

            # Iterative action loop: re-query available actions after each action
            # so the agent always sees the latest state
            max_actions = 50  # Safety limit
            for _ in range(max_actions):
                available = self._get_available_actions(state, player_id)
                action = agent.decide_action(state, available)
                if action is None:
                    break

                result = self.action_system.execute(state, action)

                # Fire passive triggers based on action type
                if result.success:
                    trigger_type = self._ACTION_TRIGGER_MAP.get(
                        getattr(action, 'action_type', ''))
                    if trigger_type:
                        self._check_triggers(trigger_type, {
                            "player_id": player_id,
                            "action": action,
                            "result": result,
                        })

                if self.logger:
                    from .game_logger import log_action_result
                    log_action_result(self.logger, action, result, state)

                if not result.success:
                    pass

            # Fire turn_end triggers
            self._check_triggers("on_turn_end", {"player_id": player_id})

            # Rulebook §3.4: 军力行动结束时清0
            # Remaining military is lost — prevents hoarding between turns.
            player.military = 0

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

    def _get_available_actions(self, state: "GameState",
                               player_id: str) -> list["GameAction"]:
        """Gather all legal actions for a player from the current state.

        Called before each decide_action() call so the agent always sees
        the latest state after previous actions have been executed.
        """
        quick = self.action_system.get_available_quick_actions(state, player_id)
        hand = self.action_system.get_available_hand_actions(state, player_id)
        court = self.action_system.get_available_court_actions(state, player_id)
        public = self.action_system.get_available_public_actions(state, player_id)
        return quick + hand + court + public

    def _log_effect(self, player_id: str, effect_type: str,
                    params: dict = None, events: list = None,
                    source: str = "card"):
        """Callback from EffectResolver — log each effect step execution."""
        if self.logger:
            self.logger.log_effect(player_id, effect_type, params, events, source)

    # ================================================================
    # Passive trigger system
    # ================================================================

    # Maps action_type → trigger_type for action-level hooks
    _ACTION_TRIGGER_MAP: dict[str, str] = {
        "march": "on_march",
        "occupy": "on_occupy",
        "fortify": "on_fortify",
        "convert": "on_convert",
        "play_card": "on_play_card",
        "play_public_card": "on_play_card",
        "court_action": "on_court_action",
        "spread_culture": "on_spread_culture",
        "archive": "on_archive",
        "raise_order": "on_order_change",
        "lower_order": "on_order_change",
    }

    def _check_triggers(self, trigger_type: str, context: dict = None):
        """Scan all in-play passive cards and fire matching triggers.

        Called after any game event that may trigger passive abilities.
        Scans staff_area + history_area of all players for blocks with
        matching trigger, checks scope/filter, then executes via resolver.
        """
        if context is None:
            context = {}

        state = self.state
        resolver = getattr(state, 'effect_resolver', None)
        if not resolver:
            return

        for card, owner_id in self._get_passive_sources():
            parsed = card.definition.parsed_effect
            if not parsed:
                continue

            for block in parsed.blocks:
                if block.ability_type != "passive":
                    continue
                if block.trigger != trigger_type:
                    continue

                # Scope check: "self" → only owner's events trigger it
                if (block.trigger_scope == "self"
                        and context.get("player_id") != owner_id):
                    continue

                # Trigger filter check (e.g. only for [流民] cards)
                if block.trigger_filter:
                    if not self._match_trigger_filter(
                        block.trigger_filter, context):
                        continue

                # Execute the passive block
                resolver._resolve_block(block, state, owner_id, context)

                # Log the trigger firing
                if self.logger:
                    ctx_summary = {
                        "triggered_by": trigger_type,
                        "event_player": context.get("player_id", ""),
                    }
                    action = context.get("action")
                    if action:
                        ctx_summary["action_type"] = getattr(action, 'action_type', '')
                    self.logger.log_trigger(
                        trigger_type, owner_id, card.name, ctx_summary,
                    )

    def _get_passive_sources(self) -> list[tuple["Card", str]]:
        """Collect all in-play cards that may have passive abilities.

        Returns list of (card, owner_player_id).
        """
        sources = []
        for player in self.state.get_all_players():
            pid = player.player_id
            for card in player.staff_area:
                sources.append((card, pid))
            for card in player.history_area:
                sources.append((card, pid))
        return sources

    @staticmethod
    def _match_trigger_filter(filter_dict: dict, context: dict) -> bool:
        """Check if the event context matches a trigger filter.

        Supported filter keys:
          - marker: card must have specified marker type
          - card: card name must contain specified text
        """
        # marker filter: the triggering event/action must involve the marker type
        if "marker" in filter_dict:
            marker_type = filter_dict["marker"]
            # Check if the action/context involves this marker
            action = context.get("action")
            if action:
                params = getattr(action, 'params', None) or {}
                if params.get("marker") != marker_type:
                    return False
        # card filter: the card involved must match
        if "card" in filter_dict:
            card_name = filter_dict["card"]
            card = context.get("card")
            if card and card_name not in (card.name if hasattr(card, 'name') else str(card)):
                return False
        return True

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
