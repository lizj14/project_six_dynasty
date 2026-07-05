"""Sima (司马家) NPC logic. Rulebook §3.4, §3.2.

- Military distribution: when Sima military > 6, distribute to Jin players
- Capital management: capital marker movement
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


def move_sima_capital(state: "GameState", new_location: str,
                      chosen_by_player: str) -> list[dict]:
    """Move the Sima capital marker.

    Rule: 首都标记被移除时，由行动顺位最靠前的东晋玩家选择新地点。
    可以选择司马家占据的地点或该东晋玩家占据的地点。
    如果是后者，该东晋玩家获得1功绩。
    """
    events = []

    old_loc = new_location  # Simplified: just place at new location
    loc = state.locations.get(new_location)
    if not loc:
        return events

    # Check if chosen location is Jin-player-occupied (not Sima)
    from models.enums import ControlState
    jin_cs = state._player_control_state(chosen_by_player)
    is_player_location = (loc.controller == jin_cs)

    # Place capital
    loc.controller = ControlState.SIMA
    events.append({"type": "capital_moved", "to": new_location})

    if is_player_location:
        player = state.get_player(chosen_by_player)
        if player:
            player.contribution = min(9, player.contribution + 1)
            events.append({"type": "contribution_for_capital",
                           "player": chosen_by_player})

    return events
