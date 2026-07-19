"""Quick actions: occupy, march, draw, recruit, fortify."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dataclasses import dataclass
from typing import Optional

from .base import GameAction, ActionResult
from models.enums import ControlState, TerrainType, FactionType

# ============================================================
# Occupy (占据)
# ============================================================

@dataclass
class OccupyAction(GameAction):
    """占据：支付1军力，在相邻空地点放置己方部队。

    Cost: 1 military
    Restrictions: target must be adjacent, unoccupied, and not enemy-controlled

    Jin players may use Sima army (use_sima_army=True) if Sima has military > 0
    (rulebook §3.4). This places a Sima control marker instead of the Jin
    player's own army and deducts 1 Sima military.
    """
    action_type: str = "occupy"
    player_id: str = ""
    target_location: str = ""
    use_sima_army: bool = False

    def validate(self, state: "GameState") -> ActionResult:
        player = state.get_player(self.player_id)
        if not player:
            return ActionResult.fail(f"Player {self.player_id} not found")

        # Check military
        if player.military < 1:
            return ActionResult.fail(f"Need 1 military, have {player.military}")

        # Check target exists
        loc = state.locations.get(self.target_location)
        if not loc:
            return ActionResult.fail(f"Location {self.target_location} not found")

        # Target must be empty (not occupied by any forces)
        if loc.controller != ControlState.EMPTY:
            return ActionResult.fail(f"Location {self.target_location} is occupied — must march first")

        # Must be adjacent to an adjacency source location
        # (own locations; own + Sima with expedition marker)
        sources = state.get_adjacency_source_locations(self.player_id)
        neighbors = state.get_adjacent_locations(self.target_location)
        if not any(n in sources for n in neighbors):
            return ActionResult.fail(f"Location {self.target_location} is not adjacent to any of your adjacency sources")

        # Validate use_sima_army
        if self.use_sima_army:
            from rules.sima import can_place_sima_army
            if not can_place_sima_army(state):
                return ActionResult.fail("Sima army not available (military=0 or no reserves)")

        return ActionResult.ok()

    def execute(self, state: "GameState") -> ActionResult:
        validation = self.validate(state)
        if not validation.success:
            return validation

        player = state.get_player(self.player_id)
        loc = state.locations[self.target_location]

        if self.use_sima_army:
            # Place Sima army instead of own army
            from rules.sima import place_sima_army
            sima_event = place_sima_army(state, self.target_location, self.player_id)
            # Pay military cost (Jin player still pays their own military)
            player.military -= 1
            events = [{"type": "occupy", "player": self.player_id,
                       "location": self.target_location, "sima_army": True},
                      sima_event]
        else:
            # Determine control state
            cs = state._player_control_state(self.player_id)
            loc.controller = cs

            # Pay cost
            player.military -= 1

            # Update army counts
            player.army_placed_count += 1
            player.army_reserve_count -= 1

            events = [{"type": "occupy", "player": self.player_id,
                       "location": self.target_location}]

            # Check game end: last army placed
            if player.army_reserve_count == 0:
                state.game_end_marker = self.player_id
                state.game_end_reason = "last_army"
                events.append({"type": "game_end_trigger", "reason": "last_army",
                               "player": self.player_id})

        # Track region control change
        from rules.area_control import on_location_change
        on_location_change(state, self.target_location)

        state.log_event("occupy", player=self.player_id, location=self.target_location)
        return ActionResult.ok(events)

    def cost_description(self, state: "GameState") -> str:
        return "1军力"

# ============================================================
# March (进军)
# ============================================================

@dataclass
class MarchAction(GameAction):
    """进军：移除目标地点部队，放置己方部队。

    Base cost: 3 military
    Modifiers:
      - Difficult terrain (虚线): +1
      - Fortified target (加固): +1
      - Isolated location (孤立): -1
      - Multiple cost reductions don't stack
    Minimum cost: 1 military

    Rewards:
      - 1 VP (for non-friendly target)
      - 1 prestige (东晋 only)
    """
    action_type: str = "march"
    player_id: str = ""
    target_location: str = ""
    source_location: Optional[str] = None  # Optional: which adjacent location to march from

    def _calculate_cost(self, state: "GameState") -> int:
        """Calculate the military cost for this march."""
        cost = 3  # base

        # Difficult terrain
        # Find which adjacency source location we're marching from
        sources = state.get_adjacency_source_locations(self.player_id)
        neighbors = state.get_adjacent_locations(self.target_location)
        for nb in neighbors:
            if nb in sources:
                terrain = state.get_terrain(nb, self.target_location)
                if terrain == TerrainType.DIFFICULT:
                    cost += 1
                break

        # Fortified target
        target_loc = state.locations.get(self.target_location)
        if target_loc and target_loc.is_fortified:
            cost += 1

        # Isolated location
        # A location is isolated if NONE of its neighbors are friendly to the target.
        # Only applies to player/Sima-controlled targets — neutral/empty locations
        # have no faction allegiance, so there is no concept of "isolated".
        target_cs = target_loc.controller if target_loc else None
        if target_cs and target_cs not in (ControlState.NEUTRAL, ControlState.EMPTY):
            isolated = True
            for nb in neighbors:
                nb_loc = state.locations.get(nb)
                if nb_loc and nb_loc.is_friendly_to(target_cs):
                    isolated = False
                    break
            if isolated:
                cost -= 1

        # Passive cost reduction (e.g. 草原部落: 进军费用-1)
        # Query all in-play passives for march_cost_reduction effects.
        # This is a true pre-cost reduction, not a post-hoc reimbursement.
        reduction = state.query_march_cost_reduction(
            self.player_id,
            context={"player_id": self.player_id, "action": self})
        cost -= reduction

        return max(1, cost)  # minimum 1

    def validate(self, state: "GameState") -> ActionResult:
        player = state.get_player(self.player_id)
        if not player:
            return ActionResult.fail(f"Player {self.player_id} not found")

        cost = self._calculate_cost(state)
        if player.military < cost:
            return ActionResult.fail(f"Need {cost} military, have {player.military}")

        # Target must exist
        target_loc = state.locations.get(self.target_location)
        if not target_loc:
            return ActionResult.fail(f"Location {self.target_location} not found")

        # Cannot march on own/friendly locations
        cs = state._player_control_state(self.player_id)
        if target_loc.is_friendly_to(cs):
            return ActionResult.fail(f"Cannot march on friendly location {self.target_location}")

        # Neutral locations are occupied by neutral forces — marching is valid
        # (rulebook §3.2: locations can be 玩家占据/司马家占据/中立势力占据/未被占据)
        # Only truly empty (unoccupied) locations should use occupy, not march

        # Must be adjacent to an adjacency source location
        # (own locations; own + Sima with expedition marker)
        sources = state.get_adjacency_source_locations(self.player_id)
        neighbors = state.get_adjacent_locations(self.target_location)
        if not any(n in sources for n in neighbors):
            return ActionResult.fail(f"No adjacency source adjacent to {self.target_location}")

        return ActionResult.ok()

    def execute(self, state: "GameState") -> ActionResult:
        validation = self.validate(state)
        if not validation.success:
            return validation

        player = state.get_player(self.player_id)
        cost = self._calculate_cost(state)
        target_loc = state.locations[self.target_location]

        events = []

        # Pay cost (already reduced by passive effects in _calculate_cost)
        player.military -= cost

        # Remove existing unit (return to owner's reserve, or remove neutral)
        old_controller = target_loc.controller
        old_owner_id = self._control_state_to_player_id(old_controller)
        if old_owner_id:
            old_player = state.get_player(old_owner_id)
            if old_player:
                old_player.army_placed_count -= 1
                old_player.army_reserve_count += 1
            elif old_controller == ControlState.SIMA:
                state.sima.army_placed_count -= 1
                state.sima.army_reserve_count += 1
        # Neutral troops are just removed — no reserve tracking needed

        # Remove fortification if present
        target_loc.is_fortified = False

        # March clears the location (→ EMPTY) but does NOT place own unit.
        # The player must use Occupy action separately to claim the location.
        # This allows march → occupy chaining for AIs.
        target_loc.controller = ControlState.EMPTY

        # Rewards
        # 1 VP for non-friendly target (always the case since validate checks this)
        player.vp += 1
        events.append({"type": "march", "player": self.player_id,
                        "target": self.target_location, "cost": cost,
                        "vp_gained": 1})

        # 1 prestige for 东晋 players
        if player.faction == FactionType.JIN:
            events.extend(state.add_prestige(self.player_id, 1))

        state.log_event("march", player=self.player_id,
                         target=self.target_location, cost=cost)
        return ActionResult.ok(events)

    def cost_description(self, state: "GameState") -> str:
        cost = self._calculate_cost(state)
        return f"{cost}军力"

    @staticmethod
    def _control_state_to_player_id(cs: "ControlState") -> Optional[str]:
        mapping = {
            ControlState.NORTH: "north",
            ControlState.JIN_P1: "jin_1",
            ControlState.JIN_P2: "jin_2",
            ControlState.JIN_P3: "jin_3",
            ControlState.SIMA: "sima",
        }
        return mapping.get(cs)

# ============================================================
# Draw (摸牌) — quick action
# ============================================================

@dataclass
class DrawAction(GameAction):
    """摸牌：支付2军力，从主版图牌库摸1张牌。每回合限1次。"""
    action_type: str = "draw"
    player_id: str = ""

    def validate(self, state: "GameState") -> ActionResult:
        player = state.get_player(self.player_id)
        if not player:
            return ActionResult.fail(f"Player {self.player_id} not found")

        if player.has_drawn_quick:
            return ActionResult.fail("Already used quick draw this turn")

        if player.military < 2:
            return ActionResult.fail(f"Need 2 military, have {player.military}")

        if not state.main_deck and not state.main_discard:
            return ActionResult.fail("No cards available to draw")

        return ActionResult.ok()

    def execute(self, state: "GameState") -> ActionResult:
        validation = self.validate(state)
        if not validation.success:
            return validation

        player = state.get_player(self.player_id)
        player.military -= 2
        player.has_drawn_quick = True

        events = state.draw_cards(self.player_id, count=1)
        return ActionResult.ok(events)

    def cost_description(self, state: "GameState") -> str:
        return "2军力"

# ============================================================
# Recruit (征募) — quick action
# ============================================================

@dataclass
class RecruitAction(GameAction):
    """征募：弃1张手牌，获得1军力。无次数限制。"""
    action_type: str = "recruit"
    player_id: str = ""
    card_to_discard_index: int = 0  # Index in hand

    def validate(self, state: "GameState") -> ActionResult:
        player = state.get_player(self.player_id)
        if not player:
            return ActionResult.fail(f"Player {self.player_id} not found")

        if not player.hand:
            return ActionResult.fail("No cards in hand to discard")

        if self.card_to_discard_index < 0 or self.card_to_discard_index >= len(player.hand):
            return ActionResult.fail(f"Invalid card index {self.card_to_discard_index}")

        return ActionResult.ok()

    def execute(self, state: "GameState") -> ActionResult:
        validation = self.validate(state)
        if not validation.success:
            return validation

        player = state.get_player(self.player_id)
        card = player.hand.pop(self.card_to_discard_index)
        discard_events = state.discard_cards(
            self.player_id, [card], target="main", source="hand",
            reason="recruit")
        player.military += 1

        state.log_event("recruit", player=self.player_id, discarded=card.name)
        return ActionResult.ok([{"type": "recruit", "player": self.player_id,
                                  "discarded": card.name, "military_gained": 1}]
                                + discard_events)

    def cost_description(self, state: "GameState") -> str:
        return "弃1张手牌"

# ============================================================
# Fortify (加固) — quick action
# ============================================================

@dataclass
class FortifyAction(GameAction):
    """加固：支付1军力，对友方地点执行加固。每回合限1次。"""
    action_type: str = "fortify"
    player_id: str = ""
    target_location: str = ""

    def validate(self, state: "GameState") -> ActionResult:
        player = state.get_player(self.player_id)
        if not player:
            return ActionResult.fail(f"Player {self.player_id} not found")

        if player.has_fortified_quick:
            return ActionResult.fail("Already used quick fortify this turn")

        if player.military < 1:
            return ActionResult.fail(f"Need 1 military, have {player.military}")

        loc = state.locations.get(self.target_location)
        if not loc:
            return ActionResult.fail(f"Location {self.target_location} not found")

        if not state.is_friendly_location(self.target_location, self.player_id):
            return ActionResult.fail(f"Location {self.target_location} is not friendly")

        if loc.is_fortified:
            return ActionResult.fail(f"Location {self.target_location} is already fortified")

        return ActionResult.ok()

    def execute(self, state: "GameState") -> ActionResult:
        validation = self.validate(state)
        if not validation.success:
            return validation

        player = state.get_player(self.player_id)
        player.military -= 1
        player.has_fortified_quick = True

        loc = state.locations[self.target_location]
        loc.is_fortified = True

        state.log_event("fortify", player=self.player_id, location=self.target_location)
        return ActionResult.ok([{"type": "fortify", "player": self.player_id,
                                  "location": self.target_location}])

    def cost_description(self, state: "GameState") -> str:
        return "1军力"
