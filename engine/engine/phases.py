"""Game phase logic — setup, preparation, action, settlement."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import random
from typing import Optional

from models.enums import PhaseType, FactionType, ControlState, CardType, CardCategory
from models.card import Card, CardDef, CardLibrary
from models.player import PlayerState
from models.location import LocationState, AdjacencyDef
from models.game_state import GameState, SimaState, EmperorState
from .actions.card_actions import PlayCardAction
from cards.effect_resolver import EffectResolver


# ================================================================
# Jin player ordering utilities
# ================================================================

def _get_jin_setup_order(state: GameState) -> list[PlayerState]:
    """Jin players sorted by 先动值 (start_order), descending (higher = earlier).

    Used during setup phase (hero enter + face-down cards).
    start_order is set from the hero card and never modified during gameplay.
    Direction is consistent with order (higher = earlier in turn).
    """
    return sorted(state.jin_players, key=lambda p: -p.start_order)


def _get_jin_turn_order(state: GameState) -> list[PlayerState]:
    """Jin players sorted for the action phase.

    Round 1 (初设后的第一回合): sorted by 先动値 (start_order) descending.
      start_order is the only criterion — higher = earlier in turn.

    Round 2+: sorted by 顺位 (order) descending, then 到达顺序 (order_seq) descending.
      Primary: higher order = earlier in turn.
      Tiebreaker: higher order_seq = arrived at this order later = 后到者优先.

    During gameplay, order_seq is updated from the global counter on each
    RaiseOrderAction/LowerOrderAction.
    """
    if state.round <= 1:
        # Round 1: 先动值决定行动顺序（越大越先，与顺位方向一致）
        return sorted(state.jin_players, key=lambda p: -p.start_order)
    # Round 2+: 顺位决定行动顺序（越高越先，同顺位则后到者优先）
    return sorted(state.jin_players, key=lambda p: (-p.order, -p.order_seq))


# ================================================================
# Setup game — orchestrator
# ================================================================

def setup_game(library: CardLibrary, agents: list,
               seed: int = 0, version=None,
               map_adjacencies: list = None,
               action_system=None, logger=None) -> GameState:
    """Initialize a complete game state from scratch.

    Args:
        library: CardLibrary with all card definitions
        agents: 4 GameAgents [north, jin_1, jin_2, jin_3]
        seed: Random seed for reproducibility
        action_system: ActionSystem for executing card actions (optional)
        logger: GameLogger for recording setup actions (optional)
    """
    rng = random.Random(seed)

    # Phase 1: Create players
    north, jin1, jin2, jin3 = _create_setup_players()
    players = [north, jin1, jin2, jin3]

    # Phase 2+3: Deal cards + agent setup decisions
    public_pool_cards, main_deck_cards, setup_discard_pile = _deal_and_select_cards(
        library, players, agents, rng)

    # Phase 4+5: Build national decks + assemble GameState
    state = _build_game_state(
        library, north, jin1, jin2, jin3,
        seed, version, map_adjacencies,
        action_system, logger,
        public_pool_cards, main_deck_cards, setup_discard_pile,
    )

    # Phase 6+7: Execute hero enter, face-down cards, count armies
    _execute_setup_effects(state, agents, action_system, logger, rng)

    state.phase = PhaseType.PREPARATION
    state.round = 1
    return state


# ================================================================
# Setup sub-functions
# ================================================================

def _create_setup_players() -> tuple[PlayerState, PlayerState, PlayerState, PlayerState]:
    """Create the four initial PlayerState objects with faction defaults."""
    north = PlayerState(
        player_id="north", faction=FactionType.NORTH,
        military=5, army_reserve_count=32, army_placed_count=0,
    )
    jin1 = PlayerState(
        player_id="jin_1", faction=FactionType.JIN,
        military=1, prestige=0, contribution=0, order=0,
        army_reserve_count=16, army_placed_count=0,
    )
    jin2 = PlayerState(
        player_id="jin_2", faction=FactionType.JIN,
        military=1, prestige=0, contribution=0, order=1,
        army_reserve_count=16, army_placed_count=0,
    )
    jin3 = PlayerState(
        player_id="jin_3", faction=FactionType.JIN,
        military=1, prestige=0, contribution=0, order=2,
        army_reserve_count=16, army_placed_count=0,
    )
    return north, jin1, jin2, jin3


def _deal_and_select_cards(library: CardLibrary, players: list[PlayerState],
                           agents: list, rng: random.Random
                           ) -> tuple[list[Card], list[Card], list[Card]]:
    """Shuffle pools, deal hero/goal candidates, build hands + main deck,
    then run agent setup_decision() to select hero/goal/face-down card.

    Returns:
        (public_pool_cards, main_deck_cards, setup_discard_pile)
    """
    from ai.interface import SetupContext, SetupDecision

    north, jin1, jin2, jin3 = players

    # === Collect hero/goal pools ===
    all_heroes = library.by_type(CardType.HERO)
    north_heroes = [c for c in all_heroes
                    if c.card_category.value.startswith("hero_north")]
    jin_heroes = [c for c in all_heroes
                  if c.card_category.value.startswith("hero_jin")]

    all_goals = library.by_type(CardType.GOAL)
    goal_pool = list(all_goals)
    rng.shuffle(goal_pool)

    _hero_choices_by_player: dict[str, list] = {}
    _goal_choices_by_player: dict[str, list] = {}

    rng.shuffle(jin_heroes)
    rng.shuffle(north_heroes)
    _jin_deal_index = 0

    # === Step 1: Assign candidates + build faction hands ===
    allocated_card_ids: set[str] = set()

    for player in [north, jin1, jin2, jin3]:
        # --- Hero candidates (non-overlapping) ---
        if player.faction == FactionType.NORTH:
            hero_choices = north_heroes[:2]
        else:
            start = _jin_deal_index
            hero_choices = jin_heroes[start:start + 2]
            _jin_deal_index += 2
        _hero_choices_by_player[player.player_id] = hero_choices

        # --- Goal candidates (Jin only) ---
        goal_choices = []
        if player.faction == FactionType.JIN:
            goal_choices = rng.sample(goal_pool, min(3, len(goal_pool)))
        _goal_choices_by_player[player.player_id] = goal_choices

        # --- Build hand: hero candidate faction cards ---
        for hero_def in hero_choices:
            for cdef in library.by_faction(hero_def.owner_faction):
                if cdef.card_type != CardType.HERO and cdef.card_id not in allocated_card_ids:
                    player.hand.append(Card(definition=cdef, owner_player_id=player.player_id))
                    allocated_card_ids.add(cdef.card_id)

    # --- Build main deck ---
    main_deck_cards = []
    public_pool_cards = []
    for cdef in library.all_cards:
        if cdef.card_type == CardType.PUBLIC:
            public_pool_cards.append(Card(definition=cdef))
            continue
        if cdef.card_type in (CardType.HERO, CardType.GOAL, CardType.EMPEROR,
                              CardType.REFUGEE, CardType.INITIAL):
            continue
        if cdef.owner_faction == "初始":
            continue
        if cdef.card_id in allocated_card_ids:
            continue
        main_deck_cards.append(Card(definition=cdef))
    rng.shuffle(main_deck_cards)

    # --- North: +2 faction friend cards ---
    north_friend_cards = [c for c in library.all_cards
                          if c.owner_faction == "北方"
                          and c.card_type == CardType.FRIEND
                          and c.card_id not in allocated_card_ids]
    chosen_north_friends = rng.sample(north_friend_cards, min(2, len(north_friend_cards)))
    for cdef in chosen_north_friends:
        north.hand.append(Card(definition=cdef, owner_player_id="north"))
        allocated_card_ids.add(cdef.card_id)

    # --- Draw from main deck: North→10, Jin→8 ---
    _setup_discard_pile: list = []
    target_hand = {"north": 10, "jin_1": 8, "jin_2": 8, "jin_3": 8}
    for player in [north, jin1, jin2, jin3]:
        needed = target_hand[player.player_id] - len(player.hand)
        drawn = 0
        attempts = 0
        while drawn < needed and attempts < len(main_deck_cards) + needed:
            if not main_deck_cards:
                break
            card = main_deck_cards.pop(0)
            if card.card_type == CardType.MECHANISM:
                _setup_discard_pile.append(card)
                attempts += 1
                continue
            card.owner_player_id = player.player_id
            player.hand.append(card)
            drawn += 1
            attempts += 1

    # === Step 2: Agent setup decisions ===
    for player, agent in [(north, agents[0]), (jin1, agents[1]),
                           (jin2, agents[2]), (jin3, agents[3])]:
        hero_choices = _hero_choices_by_player.get(player.player_id, [])
        goal_choices = _goal_choices_by_player.get(player.player_id, [])

        ctx = SetupContext(
            player_id=player.player_id,
            faction=player.faction.value,
            hero_choices=[{"name": h.name, "faction": h.owner_faction,
                           "start_order": h.start_order,
                           "effect_text": h.effect_text,
                           "category": h.card_category.value}
                          for h in hero_choices],
            goal_choices=[{"name": g.name, "simple_vp": g.goal_simple_vp,
                           "full_vp": g.goal_full_vp,
                           "simple_condition": g.goal_simple_condition,
                           "full_condition": g.goal_full_condition}
                          for g in goal_choices],
            hand_cards=[c.name for c in player.hand],
            hand_card_costs=[c.cost for c in player.hand],
            other_jin_heroes=[],
        )

        decision = agent.setup_decision(ctx)

        # --- Apply hero ---
        if 0 <= decision.hero_index < len(hero_choices):
            hero_def = hero_choices[decision.hero_index]
            player.hero = Card(definition=hero_def)
            player.start_order = hero_def.start_order

        # --- Apply goals ---
        if player.faction == FactionType.JIN and goal_choices:
            player.goal_cards = []
            if 0 <= decision.public_goal_index < len(goal_choices):
                player.goal_cards.append(goal_choices[decision.public_goal_index].name)
            if (decision.secret_goal_index >= 0 and
                decision.secret_goal_index < len(goal_choices) and
                decision.secret_goal_index != decision.public_goal_index):
                player.goal_cards.append(goal_choices[decision.secret_goal_index].name)

        # --- Store face-down decision ---
        player._setup_face_down_index = decision.face_down_card_index
        player._setup_payment_indices = decision.payment_indices

    return public_pool_cards, main_deck_cards, _setup_discard_pile


def _build_game_state(library: CardLibrary,
                      north: PlayerState, jin1: PlayerState,
                      jin2: PlayerState, jin3: PlayerState,
                      seed: int, version, map_adjacencies,
                      action_system, logger,
                      public_pool_cards: list[Card],
                      main_deck_cards: list[Card],
                      setup_discard_pile: list[Card]) -> GameState:
    """Build national decks, create and populate the GameState object."""

    # Helper: get a CardDef by name, or None
    def _get_def(name: str):
        return library.by_name_exact(name)

    jin_start = _get_def("士卒")
    refugee_def = _get_def("流民")
    court_def = _get_def("宫廷")
    zhengpi_def = _get_def("征辟人才")
    beifa_def = _get_def("北伐")
    jia_guan_def = _get_def("加官进爵")
    qingtan_def = _get_def("清谈")

    # --- Jin national deck (10 cards) ---
    jin_national = []
    if jin_start:
        for _ in range(3):
            jin_national.append(Card(definition=jin_start))
    if refugee_def:
        for _ in range(2):
            jin_national.append(Card(definition=refugee_def))
    for _def in [court_def, jia_guan_def, beifa_def, zhengpi_def, qingtan_def]:
        if _def:
            jin_national.append(Card(definition=_def))
    while len(jin_national) < 10 and jin_start:
        jin_national.append(Card(definition=jin_start))
    jin_national = jin_national[:10]

    # --- North national deck (10 cards) ---
    north_national = []
    if jin_start:
        for _ in range(5):
            north_national.append(Card(definition=jin_start))
    if refugee_def:
        for _ in range(2):
            north_national.append(Card(definition=refugee_def))
    for _def in [court_def, zhengpi_def]:
        if _def:
            north_national.append(Card(definition=_def))
    qing_qi = library.by_name_exact("轻骑兵")
    if qing_qi:
        north_national.append(Card(definition=qing_qi))
    while len(north_national) < 10 and jin_start:
        north_national.append(Card(definition=jin_start))
    north_national = north_national[:10]

    # --- Create GameState ---
    state = GameState(round=0, phase=PhaseType.SETUP, seed=seed)
    state.north_player = north
    state.jin_players = [jin1, jin2, jin3]
    state.turn_order = ["north", "jin_1", "jin_2", "jin_3"]

    # Public action card pool (5 shared cards, rulebook §2.1)
    state.public_action_pool = public_pool_cards

    # National decks — basic court cards go to the deck first.
    # Court is filled from the deck later (in _execute_setup_effects),
    # AFTER face-down strategy cards are resolved, so they appear in T1 court.
    state.jin_deck = jin_national
    state.north_deck = north_national

    # Main deck
    state.main_deck = main_deck_cards

    # Map setup
    state.locations = _create_initial_locations()
    state.main_discard.extend(setup_discard_pile)

    # Load map adjacencies
    if map_adjacencies:
        state.map_adjacencies = list(map_adjacencies)
    else:
        state.map_adjacencies = _load_adjacencies()

    # Emperor
    emperor_cards = library.by_type(CardType.EMPEROR)
    if emperor_cards:
        state.emperor = EmperorState(
            current_emperor=emperor_cards[0],
            emperor_deck=emperor_cards,
            age=1,
            prestige_initial=emperor_cards[0].initial_prestige,
        )

    # EffectResolver (created once, with log callback if logger available)
    state.effect_resolver = EffectResolver(action_system)
    if logger:
        state.effect_resolver.log_callback = _log_effect_wrapper(logger)
    state.action_system = action_system

    return state


def _execute_setup_effects(state: GameState, agents: list,
                           action_system, logger, rng: "random.Random" = None):
    """Execute hero enter effects, face-down cards, and count initial armies.

    Hero enter: North always first, then Jin sorted by 先动值 (start_order) descending (higher = earlier).
    """
    # Wire select_target_callback BEFORE any effect execution.
    # During setup_game(), the engine's _post_setup_init hasn't run yet,
    # so we must provide a temporary callback that uses the agents list.
    agent_map = {a.player_id: a for a in agents}
    if state.effect_resolver and not state.effect_resolver.select_target_callback:
        state.effect_resolver.select_target_callback = lambda pid, prompt: (
            agent_map[pid].select_target(state, prompt) if pid in agent_map else None
        )

    # --- Hero enter effects (登场), sorted by 先动值 ---
    # North always first, Jin players sorted by start_order descending (rulebook §2.2)
    _execute_hero_enter(state, state.north_player, agents[0])
    for jin_player in _get_jin_setup_order(state):
        _execute_hero_enter(state, jin_player, agent_map.get(jin_player.player_id))

    # --- Execute initial face-down cards (rulebook §4.1 step 7) ---
    state._setup_cards_played = _execute_setup_face_down_cards(
        state, action_system, logger,
    )

    # --- Fill court from national decks ---
    # Court is populated from the deck AFTER face-down cards are resolved,
    # so strategy cards that went to the deck top appear in T1 court.
    _fill_court_to(state, "north", 10, rng)
    _fill_court_to(state, "jin", 10, rng)

    # --- Count initial army placements from map ---
    state.north_player.army_placed_count = sum(
        1 for loc in state.locations.values()
        if loc.controller == ControlState.NORTH
    )
    state.north_player.army_reserve_count = 32 - state.north_player.army_placed_count
    state.sima.army_placed_count = sum(
        1 for loc in state.locations.values()
        if loc.controller == ControlState.SIMA
    )
    state.sima.army_reserve_count = 16 - state.sima.army_placed_count

    for jin_player in state.jin_players:
        cs = state._player_control_state(jin_player.player_id)
        jin_player.army_placed_count = sum(
            1 for loc in state.locations.values() if loc.controller == cs
        )
        jin_player.army_reserve_count = 16 - jin_player.army_placed_count


# ================================================================
# Existing phase functions
# ================================================================

def _log_effect_wrapper(logger):
    """Create a log_callback closure for EffectResolver (phases.py cannot reference self._log_effect)."""
    def callback(player_id, effect_type, params=None, events=None, source="card"):
        if logger:
            logger.log_effect(player_id, effect_type, params, events, source)
    return callback


def _execute_setup_face_down_cards(state: GameState, action_system,
                                    logger=None) -> dict:
    """Execute initial face-down cards (rulebook §4.1 step 7).

    North first, then Jin players sorted by 先动值 (start_order, descending).
    Delegates to PlayCardAction via action_system.execute() — same code path
    as normal card play.  Faction restriction and event condition checks are
    handled inside PlayCardAction.execute() (cards discarded on failure).

    Args:
        state: GameState with populated hands and _setup_face_down_index
        action_system: ActionSystem for executing PlayCardAction
        logger: Optional GameLogger for recording setup actions

    Returns:
        dict of {player_id: {card, cost, payment, success}}
    """
    if action_system is None:
        return {}

    jin_sorted = _get_jin_setup_order(state)
    setup_order = [state.north_player] + jin_sorted
    setup_cards_played = {}

    if logger:
        logger.log_round_start(0)

    for player in setup_order:
        if not player.hand:
            continue

        idx = getattr(player, '_setup_face_down_index', 0)
        payment = getattr(player, '_setup_payment_indices', [])
        if idx >= len(player.hand):
            idx = 0
        card = player.hand[idx]
        cost = card.cost

        # Auto-fill payment indices from remaining hand cards
        other_indices = [i for i in payment if i != idx and 0 <= i < len(player.hand)]
        if len(other_indices) < cost:
            remaining = [i for i in range(len(player.hand))
                        if i != idx and i not in other_indices]
            other_indices = other_indices + remaining[:cost - len(other_indices)]

        # Capture payment card names before execution
        payment_names = []
        for pi in sorted(other_indices[:cost], reverse=True):
            if 0 <= pi < len(player.hand) and pi != idx:
                payment_names.append(player.hand[pi].name)

        if len(other_indices) >= cost:
            # All card types route through PlayCardAction.execute() for unified
            # effect resolution. Reform VP and contribution are handled there.
            # STRATEGY play conditions are NOT checked here (they're enforced
            # at court execution via CourtAction).
            action = PlayCardAction(
                player_id=player.player_id,
                card_index=idx,
                payment_indices=other_indices[:cost],
            )

            # Execute via normal PlayCardAction flow
            result = action_system.execute(state, action)

            # Log via GameLogger
            if logger:
                from .game_logger import log_action_result
                log_action_result(logger, action, result, state)

            # Determine success: card was not discarded due to restriction/condition
            success = result.success
            for evt in (result.events or []):
                if evt.get("type") == "card_discarded":
                    success = False
                    break

            setup_cards_played[player.player_id] = {
                "card": card.name, "cost": cost,
                "payment": payment_names,
                "success": success,
            }
        else:
            # Insufficient cards for payment — discard directly
            state.main_discard.append(player.hand.pop(idx))
            setup_cards_played[player.player_id] = {
                "card": card.name, "cost": cost,
                "payment": [],
                "success": False, "error": "insufficient payment",
            }

    if logger:
        logger.log_round_end()

    return setup_cards_played


def _create_initial_locations() -> dict[str, LocationState]:
    """Create the initial map with default control settings.

    Returns a simplified location map for testing.
    In production, this would load from map_adjacency.yaml.
    """
    locations = {}
    region_locations = {
        "西凉": ["张掖", "姑臧", "金城"],
        "关中": ["安定", "天水", "长安"],
        "巴蜀": ["汉中", "巴郡", "蜀郡"],
        "荆襄": ["襄阳", "南郡", "巴东", "武昌", "宛城", "上洛"],
        "江南": ["浔阳", "建康", "京口", "吴", "会稽"],
        "中原": ["弘农", "洛阳", "雍丘", "彭城", "谯", "东平"],
        "山西": ["平阳", "太原", "上党"],
        "山东": ["济南", "广固", "琅琊"],
        "淮南": ["寿春", "合肥", "广陵"],
        "河北": ["中山", "襄国", "邺城", "信都"],
        "幽燕": ["蓟城", "龙城"],
        "关外": ["盛乐", "平城"],
    }
    north_starts = []
    sima_starts = [
        "建康", "京口", "吴", "会稽", "浔阳",
        "襄阳", "南郡", "巴东", "寿春", "合肥", "广陵",
        "张掖", "姑臧", "武昌",
    ]

    for region, locs in region_locations.items():
        for loc_name in locs:
            if loc_name in north_starts:
                controller = ControlState.NORTH
            elif loc_name in sima_starts:
                controller = ControlState.SIMA
            else:
                controller = ControlState.NEUTRAL
            locations[loc_name] = LocationState(
                location_id=loc_name,
                controller=controller,
            )
    return locations


def run_preparation_phase(state: GameState, rng: random.Random) -> list[dict]:
    """Execute the preparation phase for the current round.

    Returns emperor dice events for logging.
    """
    state.phase = PhaseType.PREPARATION

    # Refresh public action cards: all exhausted cards recover, then populate
    state.public_exhausted.clear()
    state.public_actions = [card.definition for card in state.public_action_pool]

    # Emperor dice — use real emperor module
    from rules.emperor import roll_emperor_dice
    emperor_events = roll_emperor_dice(state, rng)

    # Sima military distribution (after emperor dice)
    from rules.sima import distribute_sima_military
    distribute_sima_military(state)

    # Set action order: north first, then Jin by order track (higher = earlier)
    jin_sorted = _get_jin_turn_order(state)
    state.turn_order = ["north"] + [p.player_id for p in jin_sorted]
    state.active_player_index = 0

    state.phase = PhaseType.ACTION

    return emperor_events


def run_player_draw(state: GameState, player_id: str):
    """回合开始时摸2张牌。调用通用摸牌功能。"""
    return state.draw_cards(player_id, count=2)


def run_settlement_phase(state: GameState, rng: random.Random):
    """Execute the settlement phase."""
    state.phase = PhaseType.SETTLEMENT

    # Unselected court cards → resources
    for card in state.north_court:
        state.north_player.military += card.definition.resource_option_army
        state.north_player.vp += card.definition.resource_option_vp
    state.north_discard.extend(state.north_court)
    state.north_court = []

    for card in state.jin_court:
        state.sima.military = min(9, state.sima.military + card.definition.resource_option_army)
        state.sima.vp += card.definition.resource_option_vp
    state.jin_discard.extend(state.jin_court)
    state.jin_court = []

    # Rulebook §4.2: 司马家基于部队储备区露出数字获得军力
    from models.game_state import get_reserve_revealed
    sima_vp, sima_mil = get_reserve_revealed(state.sima.army_placed_count, is_north=False)
    state.sima.army_reserve_revealed_vp = sima_vp
    state.sima.army_reserve_revealed_military = sima_mil
    state.sima.military = min(9, state.sima.military + sima_mil)

    # Move played cards to discard
    state.north_discard.extend(state.north_played_this_round)
    state.north_played_this_round = []
    state.jin_discard.extend(state.jin_played_this_round)
    state.jin_played_this_round = []

    # Refresh court cards (draw new 10)
    _refresh_court(state, "north", rng)
    _refresh_court(state, "jin", rng)

    # Unlock culture markers
    for loc in state.locations.values():
        loc.culture_locked = False

    # Reset region control markers to face-up for new round
    from rules.scoring import reset_region_control_markers
    reset_region_control_markers(state)

    # Emperor age check — use real emperor module
    from rules.emperor import check_emperor_age
    check_emperor_age(state, rng)

    # Check end conditions
    if state.game_end_marker or state.round >= 10:
        state.phase = PhaseType.GAME_OVER
    else:
        state.round += 1
        state.phase = PhaseType.PREPARATION

    # Forced event reshuffle is now done per-player in _run_round
    # (rulebook: "任意玩家行动结束时" check and reshuffle)


def _refresh_court(state: GameState, faction: str, rng: random.Random):
    """Refresh court cards: discard unselected, draw 10 new ones."""
    if faction == "north":
        state.north_discard.extend(state.north_court)
        state.north_court = []
        deck = state.north_deck
        discard = state.north_discard
        target = state.north_court
    else:
        state.jin_discard.extend(state.jin_court)
        state.jin_court = []
        deck = state.jin_deck
        discard = state.jin_discard
        target = state.jin_court

    for _ in range(10):
        if not deck and discard:
            rng.shuffle(discard)
            deck.extend(discard)
            discard.clear()
        if deck:
            target.append(deck.pop(0))


def _fill_court_to(state: GameState, faction: str, target_size: int = 10,
                   rng: "random.Random" = None):
    """Fill the court to target_size from the national deck WITHOUT discarding.

    Unlike _refresh_court, this preserves existing court cards — used during
    setup when face-down strategy cards have been added to the national deck
    and the court needs to be topped up.
    """
    if rng is None:
        rng = random.Random()
    if faction == "north":
        court = state.north_court
        deck = state.north_deck
        discard = state.north_discard
    else:
        court = state.jin_court
        deck = state.jin_deck
        discard = state.jin_discard

    while len(court) < target_size:
        if not deck and discard:
            rng.shuffle(discard)
            deck.extend(discard)
            discard.clear()
        if deck:
            court.append(deck.pop(0))
        else:
            break


def _execute_hero_enter(state: GameState, player: PlayerState, agent):
    """Execute a hero card's 登场 (enter play) effect.

    Uses:
      - pre-parsed AST for conversions and military gains
      - hero card fields for initial stats (contribution/prestige/order)
    """
    if not player.hero:
        return

    defn = player.hero.definition
    from cards.effect_ast import AbilityType

    # Apply initial stats from hero card (not part of effect AST)
    player.contribution = min(9, defn.initial_contribution)
    player.prestige = min(9, defn.initial_prestige)
    player.order = defn.initial_order
    player.order_seq = 0  # 初始到达顺序均为0，先动值仅在初设阶段决定登场顺序

    # Delegate enter effects to EffectResolver
    parsed = defn.parsed_effect
    if not parsed:
        return

    resolver = getattr(state, 'effect_resolver', None)
    if resolver is None:
        from cards.effect_resolver import EffectResolver
        resolver = EffectResolver()

    for block in parsed.blocks:
        if block.ability_type != AbilityType.ENTER:
            continue
        resolver._resolve_block(block, state, player.player_id, context={})


def _return_army_to_reserve(state: GameState, cs: "ControlState"):
    """Return an army from the map to its owner's reserve."""
    from models.enums import ControlState
    if cs == ControlState.NORTH:
        state.north_player.army_placed_count = max(0, state.north_player.army_placed_count - 1)
        state.north_player.army_reserve_count += 1
    elif cs == ControlState.SIMA:
        state.sima.army_placed_count = max(0, state.sima.army_placed_count - 1)
        state.sima.army_reserve_count += 1
    elif cs in (ControlState.JIN_P1, ControlState.JIN_P2, ControlState.JIN_P3):
        jin_idx = {"jin_p1": 0, "jin_p2": 1, "jin_p3": 2}.get(cs.value, -1)
        if 0 <= jin_idx < len(state.jin_players):
            state.jin_players[jin_idx].army_placed_count -= 1
            state.jin_players[jin_idx].army_reserve_count += 1


def _load_adjacencies() -> list:
    """Load map adjacency data from YAML config file."""
    import yaml
    from models.location import AdjacencyDef
    from models.enums import TerrainType

    config_path = os.path.join(os.path.dirname(__file__), "..",
                               "config", "map_adjacency.yaml")
    if not os.path.exists(config_path):
        return []

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    adjacencies = []
    for entry in data.get("adjacencies", []):
        if len(entry) >= 3:
            terrain = TerrainType.DIFFICULT if entry[2] == "difficult" else TerrainType.SIMPLE
            adjacencies.append(AdjacencyDef(entry[0], entry[1], terrain))

    return adjacencies
