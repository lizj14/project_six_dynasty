"""Sima (司马家) NPC logic. Rulebook §3.4, §3.2, §3.3.

- Military distribution: when Sima military > 6, distribute to Jin players
- Capital management: capital marker movement and relocation
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def distribute_sima_military(state: "GameState") -> list[dict]:
    """Distribute excess Sima military to Jin players.

    Rule: 每回合准备阶段，投掷君主骰后，
    若司马家军力>6，则分配给三名东晋玩家各1军力，司马家军力-3。
    重复此步骤，直至司马家军力≤6。
    """
    events = []
    jin_players = state.get_jin_players()

    while state.sima.military > 6:
        for player in jin_players:
            player.military += 1
        state.sima.military -= 3
        events.append({"type": "sima_military_distribution",
                       "sima_remaining": state.sima.military,
                       "each_jin_received": 1})

    return events


def can_place_sima_army(state: "GameState") -> bool:
    """Check if a Jin player can place a Sima army instead of their own.

    Rule: 东晋玩家执行占据时，如果司马家军力大于0，
    可以不放置自己的部队，而是放置司马家的部队。此时司马家军力减1。
    """
    return state.sima.military > 0 and state.sima.army_reserve_count > 0


def place_sima_army(state: "GameState", location_id: str,
                    jin_player_id: str) -> dict:
    """Place a Sima army instead of a Jin player's army.

    Costs 1 Sima military. Returns event.
    """
    from models.enums import ControlState

    state.sima.military -= 1
    state.sima.army_placed_count += 1
    state.sima.army_reserve_count -= 1
    state.locations[location_id].controller = ControlState.SIMA

    event = {"type": "sima_army_placed", "location": location_id,
             "by_jin_player": jin_player_id}

    # Check game end: last Sima army placed — no effect (rulebook states
    # Sima's last army does NOT trigger game end)

    return event


def check_capital_displaced(state: "GameState", location_id: str,
                           old_controller) -> list[dict]:
    """Check if capital marker was displaced by a controller change.

    Call this after any controller change on a location.
    If the location was the Sima capital and the old controller was SIMA,
    triggers the capital relocation flow.

    Args:
        state: GameState
        location_id: The location whose controller changed
        old_controller: The ControlState before the change

    Returns:
        Events list (empty if capital was not displaced)
    """
    from models.enums import ControlState

    cap_loc = getattr(state.sima, 'capital_location', '建康')
    if location_id != cap_loc:
        return []

    if old_controller != ControlState.SIMA:
        return []

    # Capital was displaced!
    state.sima.is_capital_on_map = False

    # Get select callback from effect_resolver (wired by engine)
    select_cb = None
    er = getattr(state, 'effect_resolver', None)
    if er:
        select_cb = getattr(er, 'select_target_callback', None)

    return relocate_sima_capital(state, select_cb)


def relocate_sima_capital(state: "GameState", select_callback=None) -> list[dict]:
    """Relocate the Sima capital marker after it was removed from the map.

    Rule (§3.3 首都标记):
    首都标记被移除时，需要立刻重新放置。
    重新放置的地点由行动顺位最靠前的东晋玩家选择；
    可以选择司马家占据的地点，也可以选择该东晋玩家占据的地点。
    被选择的地点，原来的部队放回储备区。
    如果是后者（东晋玩家占据的地点），该东晋玩家获得1功绩。

    Args:
        state: GameState
        select_callback: Optional callback(pid, prompt) -> str for agent interaction.
                         If None, auto-selects the first candidate.

    Returns:
        Events list
    """
    from models.enums import ControlState, FactionType

    events = []

    # Find the frontmost Jin player (by turn order — highest order first,
    # ties broken by order_seq, smaller seq = earlier in same order)
    jin_players = state.get_jin_players()
    if not jin_players:
        # No Jin players: auto-place on first available Sima location
        sima_locs = [lid for lid, loc in state.locations.items()
                     if loc.controller == ControlState.SIMA]
        if sima_locs:
            chosen = sima_locs[0]
            state.sima.capital_location = chosen
            state.sima.is_capital_on_map = True
            events.append({"type": "capital_relocated", "to": chosen,
                           "auto": True, "reason": "no_jin_players"})
        else:
            events.append({"type": "capital_relocated",
                           "error": "no_valid_locations",
                           "reason": "no_sima_locations"})
        return events

    # Sort Jin players: higher order = earlier, same order → smaller seq first
    jin_sorted = sorted(jin_players, key=lambda p: (-p.order, p.order_seq))
    frontmost = jin_sorted[0]

    # Build candidate locations
    jin_cs = state._player_control_state(frontmost.player_id)

    sima_candidates = [lid for lid, loc in state.locations.items()
                       if loc.controller == ControlState.SIMA
                       and lid != getattr(state.sima, 'capital_location', '建康')]
    # ^ exclude current capital location (it was just displaced)
    player_candidates = [lid for lid, loc in state.locations.items()
                         if loc.controller == jin_cs]
    all_candidates = sima_candidates + player_candidates

    if not all_candidates:
        # Fallback: any Sima location including the one just displaced
        # (if no other options, capital stays where it was... but this
        #  is an edge case that shouldn't happen in normal play)
        sima_any = [lid for lid, loc in state.locations.items()
                    if loc.controller == ControlState.SIMA]
        if sima_any:
            all_candidates = sima_any
        else:
            events.append({"type": "capital_relocated",
                           "error": "no_valid_locations"})
            return events

    # Ask frontmost Jin player to choose
    chosen = None
    if select_callback:
        prompt = {
            "type": "location",
            "options": all_candidates,
            "message": (
                f"首都标记被移除！请 {frontmost.player_id} "
                f"选择新的首都地点（可选择司马家占据的地点或你占据的地点）"
            ),
        }
        chosen = select_callback(frontmost.player_id, prompt)

    if not chosen or chosen not in all_candidates:
        # Fallback: prefer Sima candidate, then any
        chosen = sima_candidates[0] if sima_candidates else all_candidates[0]

    loc = state.locations.get(chosen)
    if not loc:
        return events

    old_controller = loc.controller
    was_player_location = (old_controller == jin_cs)

    # Return old army at the new capital location to its owner's reserve
    if old_controller == ControlState.SIMA:
        state.sima.army_placed_count -= 1
        state.sima.army_reserve_count += 1
    elif old_controller not in (ControlState.NEUTRAL, ControlState.EMPTY):
        # Player-controlled — find the owning player and return their army
        old_owner = _control_state_to_player(old_controller, state)
        if old_owner:
            old_owner.army_placed_count -= 1
            old_owner.army_reserve_count += 1

    # Clear fortification at new location
    loc.is_fortified = False

    # Place Sima capital at new location
    loc.controller = ControlState.SIMA
    state.sima.army_placed_count += 1
    state.sima.army_reserve_count -= 1
    state.sima.capital_location = chosen
    state.sima.is_capital_on_map = True

    events.append({
        "type": "capital_relocated",
        "to": chosen,
        "chosen_by": frontmost.player_id,
        "was_player_location": was_player_location,
    })

    # Award 1 contribution if player's own location was chosen
    if was_player_location:
        events.extend(state.add_contribution(frontmost.player_id, 1))

    return events


def _control_state_to_player(cs, state: "GameState"):
    """Map a ControlState to the corresponding PlayerState, or None."""
    mapping = {
        "north": "north",
        "jin_1": "jin_1",
        "jin_2": "jin_2",
        "jin_3": "jin_3",
    }
    # cs is a ControlState enum; get its value (e.g. "north", "jin_1", "sima")
    cs_value = cs.value if hasattr(cs, 'value') else str(cs)
    pid = mapping.get(cs_value)
    if pid:
        return state.get_player(pid)
    return None
