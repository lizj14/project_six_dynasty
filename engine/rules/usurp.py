"""Usurp (僭越) judgment. Rulebook §5.3.1.

东晋玩家结算【僭越】效果时，如果威望高于其他东晋玩家和司马家，才能结算。
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models.enums import FactionType


def can_usurp(state: "GameState", player_id: str) -> bool:
    """Check if a Jin player can execute usurp (僭越) effects.

    Condition: player's prestige must be strictly higher than:
      - All other Jin players' prestige
      - Sima's prestige

    Special: 王敦 (Wang Dun) passive allows usurp when prestige is tied for highest.
    This is handled by the card effect system checking this function with a flag.
    """
    player = state.get_player(player_id)
    if not player:
        return False

    if player.faction != FactionType.JIN:
        return False

    my_prestige = player.prestige

    # Check against other Jin players
    for p in state.get_jin_players():
        if p.player_id != player_id and p.prestige >= my_prestige:
            return False

    # Check against Sima
    if state.sima.prestige >= my_prestige:
        return False

    return True


def can_usurp_with_tie(state: "GameState", player_id: str) -> bool:
    """Check if player can usurp when ties are allowed (王敦 effect).

    Same as can_usurp but prestige can be tied for highest.
    """
    player = state.get_player(player_id)
    if not player:
        return False

    if player.faction != FactionType.JIN:
        return False

    my_prestige = player.prestige

    # Check against other Jin players (allow ties)
    for p in state.get_jin_players():
        if p.player_id != player_id and p.prestige > my_prestige:
            return False

    # Check against Sima (allow ties)
    if state.sima.prestige > my_prestige:
        return False

    return True


def get_usurp_status(state: "GameState") -> dict:
    """Get usurp status for all Jin players. Useful for AI/UI display."""
    status = {}
    for player in state.get_jin_players():
        status[player.player_id] = {
            "prestige": player.prestige,
            "can_usurp": can_usurp(state, player.player_id),
            "can_usurp_with_tie": can_usurp_with_tie(state, player.player_id),
        }
    status["sima"] = {"prestige": state.sima.prestige}
    return status
