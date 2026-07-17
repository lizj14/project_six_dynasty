"""Game orchestrator — main game loop with logging support."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import random
from typing import Optional

from models.enums import PhaseType, CardType, FactionType
from models.card import CardLibrary
from models.game_state import GameState, get_reserve_revealed
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
                 logger: "GameLogger" = None,
                 on_action_executed: callable = None):
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
        self.on_action_executed = on_action_executed  # Optional: fn(state, player_id, action, result)
        self.check_early_quit = None  # Optional: fn() -> bool, called after each player turn

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
            self.state.effect_resolver.select_target_callback = self._select_target_for_effect
            self.state.effect_resolver.make_choice_callback = self._make_choice_for_effect
            self.state.effect_resolver.choose_discard_callback = self._choose_discard_for_cost
            self.state.effect_resolver.choose_court_callback = self._choose_court_for_cost
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

            # Print setup summary for human players (same format as test log)
            self._print_setup_for_human(initial_hands)

    def _has_human_player(self) -> bool:
        """Check if any agent is a HumanPlayer (interactive)."""
        for agent in self.agents:
            if agent.__class__.__name__ == 'HumanPlayer':
                return True
        return False

    def _print_round_public_info(self, state: GameState):
        """Print public information visible to all players at round start.

        Shows: turn order, VP, contribution/prestige, deck/discard sizes,
        court cards, and controlled locations for all players.
        """
        if not self._has_human_player():
            return

        print(f"\n{'='*60}")
        print(f"  第 {state.round} 回合 — 公开信息")
        print(f"{'='*60}")

        # Turn order
        faction_labels = {"north": "北方", "jin": "东晋"}
        print(f"\n【行动顺位】")
        order_parts = []
        for pid in state.turn_order:
            p = state.get_player(pid)
            if p:
                f = faction_labels.get(p.faction.value if hasattr(p.faction, 'value') else str(p.faction), '?')
                order_parts.append(f"{pid}({f})")
        print(f"  {' → '.join(order_parts)}")

        # Player stats table
        print(f"\n【玩家状态】")
        print(f"  {'玩家':<8} {'阵营':<6} {'VP':>4} {'军力':>4} {'功绩':>4} {'威望':>4} {'顺位':>4} {'手牌':>4}")
        print(f"  {'-'*48}")
        for p in state.get_all_players():
            f = faction_labels.get(p.faction.value if hasattr(p.faction, 'value') else str(p.faction), '?')
            contrib = str(p.contribution) if p.faction.value == "jin" else "-"
            prestige = str(p.prestige) if p.faction.value == "jin" else "-"
            order = str(p.order) if p.faction.value == "jin" else "-"
            print(f"  {p.player_id:<8} {f:<6} {p.vp:>4} {p.military:>4} {contrib:>4} {prestige:>4} {order:>4} {len(p.hand):>4}")

        # Deck sizes
        print(f"\n【牌库信息】")
        for p in state.get_all_players():
            deck = state.get_national_deck(p.player_id)
            discard = state.get_national_discard(p.player_id)
            court = state.get_court_cards(p.player_id)
            print(f"  {p.player_id}: 抽牌区={len(deck)}张  弃牌区={len(discard)}张  朝堂区={len(court)}张")
            if court:
                court_str = ", ".join(
                    f"{c.name}(+{c.definition.resource_option_army}军/+{c.definition.resource_option_vp}vp)"
                    for c in court
                )
                print(f"    朝堂牌: {court_str}")

        # Controlled locations
        print(f"\n【地盘控制】")
        for p in state.get_all_players():
            friendly = state.get_friendly_locations(p.player_id)
            own = state.get_own_locations(p.player_id)
            if own:
                print(f"  {p.player_id}: 控制 {' '.join(own)}")
            elif friendly:
                print(f"  {p.player_id}: 友方 {' '.join(friendly)} (无己方据点)")
            else:
                print(f"  {p.player_id}: 无据点")

        # Public action pool
        if state.public_action_pool:
            exhausted = getattr(state, 'public_exhausted', set())
            print(f"\n【公共行动牌池】")
            for card in state.public_action_pool:
                cid = card.definition.card_id
                status = " (已用)" if cid in exhausted else ""
                print(f"  {card.name} (费用{card.cost}){status}")

        print(f"{'='*60}\n")
        """Check if any agent is a HumanPlayer (interactive)."""
        for agent in self.agents:
            if agent.__class__.__name__ == 'HumanPlayer':
                return True
        return False

    def _print_setup_for_human(self, initial_hands: dict[str, list[str]]):
        """Print setup summary for the human player, matching test log format.

        Shows: player heroes, face-down cards, and face-down card effects.
        Called from _post_setup_init() after logging is complete.
        """
        if not self._has_human_player():
            return
        if not self.logger:
            return

        log = self.logger.log
        setup_cards = getattr(log, 'setup_cards', {})
        if not setup_cards:
            return

        # Build faction label map
        faction_labels = {"north": "北方", "jin": "东晋", "sima": "司马家"}

        print(f"\n{'='*60}")
        print(f"  初设结果 — 所有玩家选择与暗置牌结算")
        print(f"{'='*60}")

        # --- Player heroes ---
        print(f"\n【英雄选择】")
        for p in log.players:
            if p.get("id") == "sima":
                continue
            f = faction_labels.get(p.get("faction", ""), p.get("faction", ""))
            print(f"  {p['id']} — {f} — {p['hero']}")

        # --- Face-down cards ---
        print(f"\n【初始暗置打出的牌（已弃置）】")
        for pid, card_info in setup_cards.items():
            hand_str = ""
            if pid in initial_hands:
                hand_str = f"（手牌: {' '.join(initial_hands[pid])}）"
            print(f"  {pid}: {card_info} {hand_str}")

        # --- Face-down card effects (round 0) ---
        setup_rounds = [r for r in log.rounds if r["round"] == 0]
        if setup_rounds:
            r = setup_rounds[0]
            print(f"\n┌─ 初始暗置牌结算 ─────────────────────────────")
            from .game_logger import _format_effect
            for turn in r.get("player_turns", []):
                pid = turn["player"]
                for act in turn.get("actions", []):
                    desc = act.get("description", act.get("type", "?"))
                    print(f"│ {pid}: {desc}")
                    costs = act.get("costs", {})
                    if costs:
                        cost_parts = []
                        for k, v in costs.items():
                            if v:
                                cost_parts.append(f"{k}:{v}")
                        if cost_parts:
                            print(f"│   费用: {', '.join(cost_parts)}")
                    results = act.get("results", {})
                    if results:
                        res_parts = []
                        for k, v in results.items():
                            if v:
                                res_parts.append(f"{k}:{v}")
                        if res_parts:
                            print(f"│   结果: {', '.join(res_parts)}")
                    effects = act.get("effects", [])
                    if effects:
                        print(f"│   ↪ 效果结算:")
                        for e in effects:
                            print(f"│     {_format_effect(e)}")
                            evts = e.get("events", []) or []
                            for evt in evts:
                                t = evt.get("type", "")
                                if t and t not in ("effect_resolved",):
                                    detail = ", ".join(
                                        f"{k}={v}" for k, v in evt.items()
                                        if k != "type")
                                    if detail:
                                        print(f"│       ↳ {t}: {detail}")
                                    else:
                                        print(f"│       ↳ {t}")
            triggers = r.get("triggers_fired", [])
            if triggers:
                for t in triggers:
                    src = t.get("source_card", "?")
                    tt = t.get("trigger", "?")
                    sp = t.get("source_player", "?")
                    print(f"│ 触发: {tt} — {sp}的[{src}]")
            print(f"└──────────────────────────────────────────────")

        # --- Initial court cards ---
        nc = getattr(log, 'north_initial_court', [])
        jc = getattr(log, 'jin_initial_court', [])
        if nc or jc:
            print(f"\n【初始朝堂牌】")
            if nc:
                cards_str = ", ".join(
                    f"{c['name']}(+{c['army']}军/+{c['vp']}vp)" for c in nc)
                print(f"  北方: {cards_str}")
            if jc:
                cards_str = ", ".join(
                    f"{c['name']}(+{c['army']}军/+{c['vp']}vp)" for c in jc)
                print(f"  东晋: {cards_str}")

        print(f"\n{'='*60}")
        print(f"  游戏正式开始!")
        print(f"{'='*60}\n")

    def _run_round(self):
        """Execute one full round."""
        state = self.state

        if self.logger:
            self.logger.log_round_start(state.round)
            self.logger.log_jin_round_status(state)

        # Print public info for human players at round start
        self._print_round_public_info(state)

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
            self._run_player_turn(state, player_id)
            # Check for early quit (human player pressed 'q')
            if self.check_early_quit and self.check_early_quit():
                state.phase = PhaseType.GAME_OVER
                state.game_end_reason = "early_quit"
                return

        # === Settlement Phase ===
        run_settlement_phase(state, self.rng)

        if self.logger:
            self.logger.log_settlement(
                court_vp={}, military_gain={}, emperor_age=[],
            )
            self.logger.log_round_end_decks(state)
            self.logger.log_round_end_locations(state)
            self.logger.log_round_end()

    def _run_player_turn(self, state: GameState, player_id: str):
        """Execute one player's complete turn within the action phase.

        Includes: guard checks, region reward, turn-start triggers, draw,
        iterative action loop (decide → execute → triggers), turn-end
        triggers, military reset, hand-limit enforcement, and forced-event
        pile reshuffle.
        """
        from rules.scoring import award_region_control_phase

        player = state.get_player(player_id)
        if not player:
            return

        agent = self._get_agent(player_id)
        if not agent:
            return

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

        # Print forced event triggers to terminal (for all players — useful debugging)
        for e in draw_events:
            if e.get("type") == "forced_event_drawn":
                card_name = e.get("card", "?")
                card_text = e.get("card_text", "")
                print(f"\n  ⚡ [强制事件] {card_name} 触发!")
                if card_text:
                    print(f"     效果: {card_text}")
                print()

        if self.logger:
            cards_drawn = [e.get("card", "?") for e in draw_events
                           if e.get("type") == "draw"]
            forced = [e.get("card", "?") for e in draw_events
                      if e.get("type") == "forced_event_drawn"]
            self.logger.log_draw(player_id, cards_drawn, forced, draw_events)
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

            # Notify observer (e.g. human player UI) about the action result
            if self.on_action_executed:
                self.on_action_executed(state, player_id, action, result)

            # Handle play_card_requested events (e.g. 桓石虔 active effect)
            # These require the player to immediately choose and play a card.
            # The play is granted by the effect — it doesn't consume the player's
            # regular hand action for the turn.
            if result.success:
                for evt in result.events:
                    if evt.get("type") == "play_card_requested":
                        filter_spec = evt.get("filter", {})
                        eligible = []
                        for i, c in enumerate(player.hand):
                            if self._card_matches_filter(c, filter_spec):
                                eligible.append(i)
                        if eligible:
                            # Grant a temporary extra hand action so
                            # PlayCardAction.validate() passes the action check
                            player.extra_hand_actions += 1
                            try:
                                play_action = agent.request_card_play(
                                    state, eligible, filter_spec)
                                if play_action is not None:
                                    r2 = self.action_system.execute(state, play_action)
                                    if self.logger:
                                        log_action_result(self.logger, play_action, r2, state)
                                    if self.on_action_executed:
                                        self.on_action_executed(
                                            state, player_id, play_action, r2)
                                else:
                                    player.extra_hand_actions -= 1
                            except Exception:
                                player.extra_hand_actions -= 1
                                raise
                            # else: player declined — continue
                        break  # Only handle one play_card_requested per action

        # Log skipped extra actions (may=True actions not used)
        if self.logger and player.extra_hand_actions > 0:
            used = player.hand_action_taken_count
            limit = 1 + player.extra_hand_actions
            if used < limit:
                self.logger.log_action(player_id, "skip_extra_hand_action",
                    f"跳过额外手牌行动 ({used}/{limit} 已用)",
                    params={"extra_granted": player.extra_hand_actions,
                            "used": used, "skipped": limit - used})
        if self.logger and player.extra_court_actions > 0:
            used = player.court_action_taken_count
            limit = 1 + player.extra_court_actions
            if used < limit:
                self.logger.log_action(player_id, "skip_extra_court_action",
                    f"跳过额外牌组行动 ({used}/{limit} 已用)",
                    params={"extra_granted": player.extra_court_actions,
                            "used": used, "skipped": limit - used})

        # Fire turn_end triggers
        self._check_triggers("on_turn_end", {"player_id": player_id})

        # Rulebook §3.4: 基于部队储备区露出的数字获得军力，然后清零
        is_north = (player.faction == FactionType.NORTH)
        revealed_vp, revealed_mil = get_reserve_revealed(
            player.army_placed_count, is_north)
        player.army_reserve_revealed_vp = revealed_vp
        player.army_reserve_revealed_military = revealed_mil
        player.military = revealed_mil

        # Enforce hand limit — agent chooses which cards to discard
        discarded = 0
        excess = len(player.hand) - player.hand_limit
        if excess > 0:
            hand_card_names = [c.name for c in player.hand]
            discard_indices = agent.choose_discards(state, hand_card_names, excess)
            # Discard in reverse index order to keep indices valid
            for idx in sorted(discard_indices, reverse=True):
                if 0 <= idx < len(player.hand):
                    state.main_discard.append(player.hand.pop(idx))
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
        activate = self.action_system.get_available_activate_actions(state, player_id)
        return quick + hand + court + public + activate

    def _log_effect(self, player_id: str, effect_type: str,
                    params: dict = None, events: list = None,
                    source: str = "card"):
        """Callback from EffectResolver — log each effect step execution."""
        if self.logger:
            self.logger.log_effect(player_id, effect_type, params, events, source)

    def _select_target_for_effect(self, player_id: str, prompt: dict) -> Optional[str]:
        """Callback from EffectResolver — ask agent to select a target.

        Bridges the resolver's target request to agent.select_target().
        Returns the selected target identifier, or None if no agent/choice.
        """
        agent = self._get_agent(player_id)
        if not agent:
            return None
        return agent.select_target(self.state, prompt)

    def _make_choice_for_effect(self, player_id: str, prompt: dict) -> int:
        """Callback from EffectResolver — ask agent to make a choice.

        Bridges the resolver's choice request to agent.make_choice().
        Used by ChooseOperator for step-level choice_options
        (e.g. 刘穆之 active: draw 1 card OR draft 1 strategy).
        Returns the chosen option index, or 0 if no agent.
        """
        agent = self._get_agent(player_id)
        if not agent:
            return 0
        return agent.make_choice(self.state, prompt)

    def _choose_discard_for_cost(self, player_id: str, hand_cards: list[str],
                                  count: int) -> list[int]:
        """Callback from EffectResolver — ask agent to choose cards to discard as cost.

        Bridges the resolver's cost-payment request to agent.choose_discards().
        Used when a cost_type='discard_cards' is paid (e.g. 郗超 active: 弃1张手牌).
        Returns list of indices to discard.
        """
        agent = self._get_agent(player_id)
        if not agent:
            return list(range(max(0, len(hand_cards) - count), len(hand_cards)))
        return agent.choose_discards(self.state, hand_cards, count)

    def _choose_court_for_cost(self, player_id: str, court_cards: list[str],
                                count: int) -> list[int]:
        """Callback from EffectResolver — ask agent to choose court cards to abandon.

        Bridges the resolver's cost-payment request for abandon_court_card costs
        (e.g. 郗超 active: 弃置1张候选策略牌).
        Returns list of indices (into the original list) to abandon, in reverse-sorted order.
        """
        agent = self._get_agent(player_id)
        if not agent or count == 0:
            return []
        # For human players, use make_choice with court card options.
        if agent.__class__.__name__ == 'HumanPlayer':
            chosen = []
            remaining = list(court_cards)  # Local copy to track remaining choices
            remaining_map = list(range(len(court_cards)))  # Map to original indices
            for _ in range(count):
                if not remaining:
                    break
                idx = agent.make_choice(self.state, {
                    "title": f"选择要弃置的朝堂牌 ({len(chosen)+1}/{count})",
                    "options": [{"label": name} for name in remaining],
                })
                if 0 <= idx < len(remaining):
                    chosen.append(remaining_map[idx])
                    remaining.pop(idx)
                    remaining_map.pop(idx)
            return sorted(chosen, reverse=True)
        else:
            return list(range(max(0, len(court_cards) - count), len(court_cards)))

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

                # Execute the passive block with card info for per-turn tracking
                block_ctx = dict(context)
                block_ctx["passive_card_id"] = card.definition.card_id
                block_ctx["passive_trigger"] = trigger_type
                resolver._resolve_block(block, state, owner_id, block_ctx)

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
        Delegates to GameState.get_all_passive_sources() which scans
        hero, staff_area, history_area, and court cards.
        """
        return self.state.get_all_passive_sources()

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

    @staticmethod
    def _card_matches_filter(card: "Card", filter_spec: dict) -> bool:
        """Check if a card matches a play_card filter spec.

        Supported filter keys:
          - marker: card must have the specified marker type
          - exclude_marker: card must NOT have the specified marker type
          - card_type: card type must match (e.g. "friend", "event")
        """
        if not filter_spec:
            return True
        defn = card.definition
        if not defn:
            return False

        if "marker" in filter_spec:
            marker_type = filter_spec["marker"]
            markers = getattr(defn, 'markers', None) or {}
            if markers.get(marker_type, 0) <= 0:
                return False

        if "exclude_marker" in filter_spec:
            marker_type = filter_spec["exclude_marker"]
            markers = getattr(defn, 'markers', None) or {}
            if markers.get(marker_type, 0) > 0:
                return False

        if "card_type" in filter_spec:
            ct = filter_spec["card_type"]
            if str(card.card_type) != ct:
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
