"""Final scoring — 5-step end-game scoring per rulebook §4.4."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dataclasses import dataclass, field
from typing import Optional

from models.enums import CultureType, Region, FactionType, ControlState
from rules.area_control import check_all_regions, REGION_CONFIG


# === Culture Supply Track VP Values (board_info.md §六) ===
# Position N → VP value (N = number of that culture's markers on the map)
CULTURE_SUPPLY_VP: list[int] = [0, 1, 2, 4, 7, 11, 16, 22, 29, 37]
# Index 0 unused, positions 1-9 map to these values


@dataclass
class FinalScoreResult:
    """Complete final scoring result."""
    player_scores: dict[str, int] = field(default_factory=dict)
    winner: Optional[str] = None
    steps: list[dict] = field(default_factory=list)


def run_final_scoring(state: "GameState") -> FinalScoreResult:
    """Execute the complete 5-step final scoring.

    Returns FinalScoreResult with per-player VP and winner.
    Mutates state.vp_track with final values.
    """
    result = FinalScoreResult()

    # Step 1: Culture scoring
    culture_result = score_culture(state)
    result.steps.append({"step": 1, "name": "文化分数", "detail": culture_result})

    # Step 2: Region control + army reserve VP
    region_result = score_region_and_reserve(state)
    result.steps.append({"step": 2, "name": "区控与部队储备", "detail": region_result})

    # Step 3: History area — already scored during game, skip
    result.steps.append({"step": 3, "name": "史书区", "detail": "已在游戏过程中结算"})

    # Step 4: Sima VP distribution
    sima_result = score_sima_distribution(state)
    result.steps.append({"step": 4, "name": "司马家分数分配", "detail": sima_result})

    # Step 5: Goal cards
    goal_result = score_goals(state)
    result.steps.append({"step": 5, "name": "目标牌", "detail": goal_result})

    # Determine winner
    players = state.get_all_players()
    result.player_scores = {p.player_id: p.vp for p in players}

    if players:
        best = max(players, key=lambda p: p.vp)
        # Tiebreaker: most history area cards
        tied = [p for p in players if p.vp == best.vp]
        if len(tied) > 1:
            best = max(tied, key=lambda p: len(p.history_area))
            # Further tiebreaker: North > Jin; among Jin, earlier order
            still_tied = [p for p in tied if len(p.history_area) == len(best.history_area)]
            if len(still_tied) > 1:
                north_in = any(p.faction == FactionType.NORTH for p in still_tied)
                if north_in:
                    best = next(p for p in still_tied if p.faction == FactionType.NORTH)
                else:
                    best = min(still_tied, key=lambda p: p.order)

        result.winner = best.player_id

    return result


# ================================================================
# Step 1: Culture Scoring
# ================================================================

def score_culture(state: "GameState") -> dict:
    """Score all three culture tracks.

    For each culture:
      1. Count markers of that type on the map → N
      2. Reveal position N on supply track
      3. Distribute the largest 3 VP values to top 3 contributors
      4. Ties: VP split evenly (rounded down)
    """
    details = {}

    for culture in CultureType:
        # 文化等级 = 供应轨露出的格子数 (supply_level)
        # Includes markers removed from supply by spread_culture AND card effects (佛经翻译/太学)
        track = state.culture_tracks.get(culture)
        n = track.supply_level if track else 0

        if n == 0:
            details[culture.value] = {"markers": 0, "vp_awarded": {}}
            continue

        # Get VP values for revealed positions
        revealed_vp = CULTURE_SUPPLY_VP[1:n+1]  # positions 1..n
        revealed_vp.sort(reverse=True)

        # Rank players by contribution
        ranked = _rank_by_contribution(state, culture)

        # Award top 3 revealed VP values
        awards = {}
        for rank_idx in range(min(3, n, len(ranked))):
            if rank_idx >= len(revealed_vp):
                break
            vp_value = revealed_vp[rank_idx]
            # Check for ties at this rank
            tied_players = _get_tied_at_rank(ranked, rank_idx)

            if len(tied_players) > 1:
                split_vp = vp_value // len(tied_players)
                for pid in tied_players:
                    player = state.get_player(pid)
                    if player:
                        player.vp += split_vp
                        awards[pid] = awards.get(pid, 0) + split_vp
            else:
                pid = ranked[rank_idx]
                player = state.get_player(pid)
                if player:
                    player.vp += vp_value
                    awards[pid] = awards.get(pid, 0) + vp_value

        details[culture.value] = {
            "markers": n,
            "revealed_vp": revealed_vp[:3],
            "contributions": {pid: state.get_player(pid).culture_contributions.get(culture, 0)
                              for pid in _all_player_ids(state)},
            "vp_awarded": awards,
        }

    return details


def _rank_by_contribution(state: "GameState", culture: CultureType) -> list[str]:
    """Return player_ids ranked by contribution to this culture (highest first).

    Tiebreaker: earlier action order (顺位靠前的玩家排名靠前).
    """
    players = state.get_all_players()
    scored = [(p.player_id, p.culture_contributions.get(culture, 0), p.order)
              for p in players]
    # Sort: highest contribution first, then lowest order (earlier = better)
    scored.sort(key=lambda x: (-x[1], x[2]))
    return [pid for pid, _, _ in scored]


def _get_tied_at_rank(ranked: list[str], rank_idx: int) -> list[str]:
    """Get all players tied with the player at rank_idx."""
    if rank_idx >= len(ranked):
        return []
    return [pid for pid in ranked if pid == ranked[rank_idx]]


def _all_player_ids(state: "GameState") -> list[str]:
    """Get all player IDs."""
    ids = []
    if state.north_player:
        ids.append(state.north_player.player_id)
    for p in state.jin_players:
        ids.append(p.player_id)
    return ids


# ================================================================
# Step 2: Region Control + Army Reserve VP
# ================================================================

def score_region_and_reserve(state: "GameState") -> dict:
    """Score region control and army reserve VP.

    Awards VP for:
      - Regions controlled (partial + full control)
      - Army reserve revealed VP
    """
    details = {"regions": {}, "reserve_vp": {}}

    # Region control
    results = check_all_regions(state)
    for region, cr in results.items():
        region_vp = {}
        # Full control gives only full_vp, not partial_vp + full_vp
        if cr.full_controller:
            pid = cr.full_controller
            if pid == "sima":
                state.sima.vp += cr.full_vp
                region_vp["sima"] = cr.full_vp
            else:
                player = state.get_player(pid)
                if player:
                    player.vp += cr.full_vp
                    region_vp[pid] = cr.full_vp
        elif cr.partial_controller:
            pid = cr.partial_controller
            if pid == "sima":
                state.sima.vp += cr.partial_vp
                region_vp["sima"] = cr.partial_vp
            else:
                player = state.get_player(pid)
                if player:
                    player.vp += cr.partial_vp
                    region_vp[pid] = cr.partial_vp

        if region_vp:
            details["regions"][region.value] = region_vp

    # Army reserve VP (last revealed slot — simplified)
    for player in state.get_all_players():
        details["reserve_vp"][player.player_id] = player.army_reserve_revealed_vp
        player.vp += player.army_reserve_revealed_vp

    # Sima reserve VP
    details["reserve_vp"]["sima"] = state.sima.army_reserve_revealed_vp

    return details


# ================================================================
# Step 4: Sima VP Distribution
# ================================================================

def score_sima_distribution(state: "GameState") -> dict:
    """Distribute Sima's VP to Jin players based on prestige and contribution ranks.

    Rulebook §4.4:
      - Every 10 Sima VP → +1 base coefficient
      - Prestige rank: 1st=+3, 2nd=+2, 3rd=+1
      - Contribution rank: 1st=+3, 2nd=+2, 3rd=+1
      - If prestige/contribution < 3, that rank's coefficient goes to 1st place
      - Same rank: earlier order wins
    """
    jin_players = state.get_jin_players()
    details = {"sima_vp": state.sima.vp, "base_coeff": state.sima.vp // 10,
               "coefficients": {}}

    base = state.sima.vp // 10

    # Rank by prestige (highest first, order as tiebreaker)
    prestige_ranked = sorted(jin_players, key=lambda p: (-p.prestige, p.order))
    # Rank by contribution
    contrib_ranked = sorted(jin_players, key=lambda p: (-p.contribution, p.order))

    # Calculate coefficients
    coeffs = {p.player_id: 0 for p in jin_players}

    # Prestige coefficients
    prestige_coeffs = [3, 2, 1]
    for i, coeff in enumerate(prestige_coeffs):
        if i < len(prestige_ranked):
            pid = prestige_ranked[i].player_id
            if prestige_ranked[i].prestige >= 3:
                coeffs[pid] += coeff
            else:
                # Coefficient goes to 1st place
                coeffs[prestige_ranked[0].player_id] += coeff

    # Contribution coefficients
    contrib_coeffs = [3, 2, 1]
    for i, coeff in enumerate(contrib_coeffs):
        if i < len(contrib_ranked):
            pid = contrib_ranked[i].player_id
            if contrib_ranked[i].contribution >= 3:
                coeffs[pid] += coeff
            else:
                coeffs[contrib_ranked[0].player_id] += coeff

    # Award VP: base * coefficient
    for pid, coeff in coeffs.items():
        vp = base * coeff
        player = state.get_player(pid)
        if player:
            player.vp += vp
            details["coefficients"][pid] = {"coeff": coeff, "vp": vp}

    return details


# ================================================================
# Step 5: Goal Cards
# ================================================================

def score_goals(state: "GameState") -> dict:
    """Score Jin players' goal cards against final game state.

    Each Jin player should have 2 goal cards (1 public, 1 secret).
    Goal cards are stored as attributes on the player.
    """
    from rules.goals import evaluate_goal, GOAL_DEFINITIONS

    details = {}

    for player in state.get_jin_players():
        player_goals = {}
        total_goal_vp = 0

        # Get player's goal card names (stored during setup)
        goal_names = getattr(player, 'goal_cards', [])
        if not goal_names:
            # Fallback: try to load from game state
            pass

        for name in goal_names:
            goal = next((g for g in GOAL_DEFINITIONS if g["name"] == name), None)
            if not goal:
                continue
            vp = evaluate_goal(state, player.player_id, goal)
            if vp is not None and vp > 0:
                player.vp += vp
                total_goal_vp += vp
                player_goals[name] = {
                    "simple_vp": goal["simple_vp"],
                    "full_vp": goal["full_vp"],
                    "earned_vp": vp,
                    "level": "full" if vp == goal["full_vp"] else "simple",
                }
            else:
                player_goals[name] = {"earned_vp": 0, "level": "none"}

        details[player.player_id] = {"goals": player_goals, "total": total_goal_vp}

    return details


# ================================================================
# In-Game Scoring: Region Control (per-phase)
# ================================================================

def award_region_control_phase(state: "GameState", player_id: str = None):
    """Award region control VP during preparation or player action phase.

    Called:
      - Preparation phase: Sima's regions (face-up markers only)
      - Player action start: that player's regions (face-up markers only)

    Each region can only award VP ONCE per round. After awarding, the
    region's control marker is flipped face-down (control_face_up=False)
    for the rest of the round. Reset happens in settlement phase.
    """
    results = check_all_regions(state)

    for region, cr in results.items():
        # Ensure RegionState exists (lazy init)
        if region not in state.regions:
            from models.location import RegionState
            from models.location import CultureSlot
            from .area_control import REGION_CONFIG as _RC2
            slot_count = _RC2.get(region, {}).get("culture_slot_count", 1)
            state.regions[region] = RegionState(
                region=region,
                culture_slots=[CultureSlot() for _ in range(slot_count)],
            )

        region_state = state.regions[region]

        # Skip if already scored this round (marker face-down)
        if not region_state.control_face_up:
            continue

        # Determine who to award
        target = None
        if player_id is None:
            # Preparation phase: only Sima (partial or full)
            if cr.partial_controller == "sima" or cr.full_controller == "sima":
                target = "sima"
        else:
            # Player action phase: that specific player
            if cr.partial_controller == player_id or cr.full_controller == player_id:
                target = player_id

        if target:
            # Full control gives full_vp (not partial_vp + full_vp)
            if cr.full_controller == target:
                vp = cr.full_vp
            else:
                vp = cr.partial_vp

            # Apply region_reward_override if set on the player
            # (e.g. 草原部落 changes partial/full VP to 0/1)
            if target != "sima":
                player = state.get_player(target)
                override = getattr(player, 'region_reward_override', None) if player else None
                if override:
                    if cr.full_controller == target:
                        vp = override.get("full", vp)
                    else:
                        vp = override.get("partial", vp)

            if target == "sima":
                state.sima.vp += vp
                state.log_event("region_vp", phase="preparation",
                                region=region.value, sima_vp=vp)
            else:
                player = state.get_player(target)
                if player:
                    player.vp += vp
                    state.log_event("region_vp", phase="player_action",
                                    player=target, region=region.value, vp=vp)
                    state.check_vp_game_end(target)

            # Flip control marker face-down — this region can't score again this round
            region_state.control_face_up = False


def reset_region_control_markers(state: "GameState"):
    """Flip all region control markers face-up for the new round.

    Called during settlement phase (rulebook §4.3).
    """
    for region_state in state.regions.values():
        region_state.control_face_up = True
