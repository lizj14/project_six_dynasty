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


def setup_game(library: CardLibrary, agents: list,
               seed: int = 0, version=None,
               map_adjacencies: list = None) -> GameState:
    """Initialize a complete game state from scratch.

    Args:
        library: CardLibrary with all card definitions
        agents: 4 GameAgents [north, jin_1, jin_2, jin_3]
        seed: Random seed for reproducibility
    """
    rng = random.Random(seed)

    # === Create players ===
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

    # === Setup: unified decision per player ===
    from ai.interface import SetupContext, SetupDecision

    # Collect hero pools
    all_heroes = library.by_type(CardType.HERO)
    north_heroes = [c for c in all_heroes
                    if c.card_category.value.startswith("hero_north")]
    jin_heroes = [c for c in all_heroes
                  if c.card_category.value.startswith("hero_jin")]

    # Collect goal pool (Jin only)
    all_goals = library.by_type(CardType.GOAL)
    goal_pool = list(all_goals)
    rng.shuffle(goal_pool)

    # Track per-player info for later decision
    _hero_choices_by_player: dict[str, list] = {}
    _goal_choices_by_player: dict[str, list] = {}

    # Shuffle pools
    rng.shuffle(jin_heroes)
    rng.shuffle(north_heroes)
    _jin_deal_index = 0

    # ============================================================
    # Step 1: Assign candidates + Build full hands FIRST
    # ============================================================
    allocated_card_ids: set[str] = set()

    for player, agent in [(north, agents[0]), (jin1, agents[1]),
                           (jin2, agents[2]), (jin3, agents[3])]:
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

        # --- Build hand: hero candidate cards ---
        for hero_def in hero_choices:
            for cdef in library.by_faction(hero_def.owner_faction):
                if cdef.card_type != CardType.HERO and cdef.card_id not in allocated_card_ids:
                    player.hand.append(Card(definition=cdef, owner_player_id=player.player_id))
                    allocated_card_ids.add(cdef.card_id)

    # --- Build main deck ---
    # Rulebook §2.1: 公共行动牌 (public action cards) are shared, not in main deck.
    # Initial cards are pseudo-cards used during setup only.
    # Cards with faction_restriction should only go to matching faction.
    main_deck_cards = []
    for cdef in library.all_cards:
        if cdef.card_type in (CardType.HERO, CardType.GOAL, CardType.EMPEROR,
                              CardType.REFUGEE, CardType.PUBLIC, CardType.INITIAL):
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
    # Forced events: discard and redraw (rulebook §4.1 step 5)
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
                # Forced event — discard and redraw (rulebook §4.1 step 5)
                _setup_discard_pile.append(card)
                attempts += 1
                continue
            card.owner_player_id = player.player_id
            player.hand.append(card)
            drawn += 1
            attempts += 1

    # ============================================================
    # Step 2: Now make decisions with the COMPLETE hand
    # ============================================================
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
            hand_cards=[c.name for c in player.hand],  # Complete hand now!
            other_jin_heroes=[],
        )

        decision = agent.setup_decision(ctx)

        # --- Apply hero ---
        if 0 <= decision.hero_index < len(hero_choices):
            player.hero = Card(definition=hero_choices[decision.hero_index])

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

    # === National starting decks ===
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

    state = GameState(round=0, phase=PhaseType.SETUP, seed=seed)
    state.north_player = north
    state.jin_players = [jin1, jin2, jin3]
    state.turn_order = ["north", "jin_1", "jin_2", "jin_3"]

    # Jin national deck (10 cards)
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
    # Fill to 10 with soldiers
    while len(jin_national) < 10 and jin_start:
        jin_national.append(Card(definition=jin_start))
    state.jin_court = jin_national[:10]

    # North national deck (10 cards)
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
    # 轻骑兵
    qing_qi = library.by_name_exact("轻骑兵")
    if qing_qi:
        north_national.append(Card(definition=qing_qi))
    while len(north_national) < 10 and jin_start:
        north_national.append(Card(definition=jin_start))
    state.north_court = north_national[:10]

    # === Main deck ===
    state.main_deck = main_deck_cards

    # === Map setup (simplified) ===
    state.locations = _create_initial_locations()
    # Add setup-discarded forced events to main discard
    state.main_discard.extend(_setup_discard_pile)

    # Load map adjacencies from version config or YAML
    if map_adjacencies:
        state.map_adjacencies = list(map_adjacencies)
    else:
        state.map_adjacencies = _load_adjacencies()

    # === Emperor ===
    emperor_cards = library.by_type(CardType.EMPEROR)
    if emperor_cards:
        state.emperor = EmperorState(
            current_emperor=emperor_cards[0],
            emperor_deck=emperor_cards,
            age=1,
            prestige_initial=emperor_cards[0].initial_prestige,
        )

    # Inject temporary EffectResolver for hero enter effects
    from engine.action_system import ActionSystem
    from cards.effect_resolver import EffectResolver
    state.effect_resolver = EffectResolver(ActionSystem())

    # === Execute hero enter effects (登场) ===
    _execute_hero_enter(state, state.north_player, agents[0])
    for i, (jin_player, agent) in enumerate(zip([jin1, jin2, jin3], agents[1:])):
        _execute_hero_enter(state, jin_player, agent)

    # Count initial army placements from map
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

    # Count Jin player armies from map
    for i, jin_player in enumerate([jin1, jin2, jin3]):
        cs = state._player_control_state(jin_player.player_id)
        jin_player.army_placed_count = sum(
            1 for loc in state.locations.values() if loc.controller == cs
        )
        jin_player.army_reserve_count = 16 - jin_player.army_placed_count

    state.phase = PhaseType.PREPARATION
    state.round = 1
    return state


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
    # Initial control (source: board_info.md)
    # North: starts with no locations
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


def run_preparation_phase(state: GameState, rng: random.Random):
    """Execute the preparation phase for the current round."""
    state.phase = PhaseType.PREPARATION

    # Reset public actions
    state.public_actions = []  # Will be populated from card library

    # Emperor dice — use real emperor module
    from rules.emperor import roll_emperor_dice
    roll_emperor_dice(state, rng)

    # Sima military distribution (after emperor dice)
    from rules.sima import distribute_sima_military
    distribute_sima_military(state)

    # Set action order: north first, then Jin by order track
    jin_sorted = sorted(state.jin_players, key=lambda p: p.order)
    state.turn_order = ["north"] + [p.player_id for p in jin_sorted]
    state.active_player_index = 0

    state.phase = PhaseType.ACTION


def run_player_draw(state: GameState, player_id: str):
    """Execute the draw phase for a player (draw 2 cards, handle forced events)."""
    player = state.get_player(player_id)
    if not player:
        return []

    events = []
    for _ in range(2):
        if state.main_deck:
            card = state.main_deck.pop(0)
            # Handle forced event cards
            if card.card_type == CardType.MECHANISM:
                state.forced_event_pile.append(card)
                events.append({"type": "forced_event_drawn", "card": card.name})
                # Don't add to hand — will be resolved separately
            else:
                player.hand.append(card)
                events.append({"type": "draw", "card": card.name})
        else:
            # Reshuffle discard into deck
            if state.main_discard:
                rng = random.Random(state.seed + state.round)
                rng.shuffle(state.main_discard)
                state.main_deck = state.main_discard
                state.main_discard = []
                # Try drawing again
                if state.main_deck:
                    card = state.main_deck.pop(0)
                    player.hand.append(card)
                    events.append({"type": "draw", "card": card.name})

    return events


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
