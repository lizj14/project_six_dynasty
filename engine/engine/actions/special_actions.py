"""Special actions: convert, archive, spread_culture, search, levy, order changes."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dataclasses import dataclass
from typing import Optional

from .base import GameAction, ActionResult
from models.enums import ControlState, FactionType, CardType, CardCategory, CultureType, Region

# ============================================================
# Convert (转化)
# ============================================================

@dataclass
class ConvertAction(GameAction):
    """转化：移除目标地点部队，放置己方部队。

    Cost: varies (0 for card effects, 4 standard, 2.5 for neutral-only)
    Rewards (non-friendly target): 2 VP + 1 prestige (Jin only)

    东晋转化友方地点的特殊惩罚：
    如果转化后该地所有相邻地点都是友方，需选择失去4vp/1功绩/1威望
    (除非没有其他可选项)
    """
    action_type: str = "convert"
    player_id: str = ""
    target_location: str = ""
    free: bool = False           # If True, no military cost (from card effect)
    neutral_only: bool = False   # If True, can only target neutral locations
    source: str = "card_effect"  # "card_effect" | "standard"

    def validate(self, state: "GameState") -> ActionResult:
        player = state.get_player(self.player_id)
        if not player:
            return ActionResult.fail(f"Player {self.player_id} not found")

        loc = state.locations.get(self.target_location)
        if not loc:
            return ActionResult.fail(f"Location {self.target_location} not found")

        # Cannot convert own locations (unless specific card allows)
        cs = state._player_control_state(self.player_id)
        if loc.controller == cs:
            return ActionResult.fail(f"Cannot convert your own location {self.target_location}")

        # Neutral-only restriction
        if self.neutral_only and loc.controller != ControlState.NEUTRAL:
            return ActionResult.fail("Can only convert neutral locations")

        # Jin special: cannot convert the capital (建康)
        if player.faction.value == "jin" and self.target_location == "建康":
            return ActionResult.fail("Cannot convert the Jin capital (建康)")

        return ActionResult.ok()

    def execute(self, state: "GameState") -> ActionResult:
        validation = self.validate(state)
        if not validation.success:
            return validation

        player = state.get_player(self.player_id)
        loc = state.locations[self.target_location]

        events = []

        old_controller = loc.controller
        was_friendly = loc.is_friendly_to(state._player_control_state(self.player_id))

        # Remove existing unit
        old_owner_id = _control_state_to_player_id(old_controller)
        if old_owner_id:
            old_player = state.get_player(old_owner_id)
            if old_player:
                old_player.army_placed_count -= 1
                old_player.army_reserve_count += 1
            elif old_controller == ControlState.SIMA:
                state.sima.army_placed_count -= 1
                state.sima.army_reserve_count += 1

        # Clear fortification
        loc.is_fortified = False

        # Place own unit
        cs = state._player_control_state(self.player_id)
        loc.controller = cs
        player.army_placed_count += 1
        player.army_reserve_count -= 1

        # Rewards for non-friendly conversion
        if not was_friendly:
            player.vp += 2
            events.append({"type": "convert_vp", "vp": 2})
            if player.faction == FactionType.JIN:
                player.prestige = min(9, player.prestige + 1)
                events.append({"type": "convert_prestige", "prestige": 1})

        # Jin special penalty: converting friendly locations
        if was_friendly and player.faction == FactionType.JIN:
            friendly_neighbors = state.get_friendly_locations(self.player_id)
            all_adjacent_friendly = all(
                nb in friendly_neighbors
                for nb in state.get_adjacent_locations(self.target_location)
            )
            if all_adjacent_friendly:
                # Penalty: lose 4vp, 1 contribution, or 1 prestige
                # For now auto-choose VP loss (AI/choice system will handle this later)
                penalty_event = {
                    "type": "jin_convert_penalty_required",
                    "location": self.target_location,
                    "options": ["lose_4vp", "lose_1_contribution", "lose_1_prestige"]
                }
                events.append(penalty_event)
                # Default: lose 4 VP
                player.vp = max(0, player.vp - 4)
                events.append({"type": "jin_convert_penalty", "chosen": "lose_4vp"})

        state.log_event("convert", player=self.player_id,
                         target=self.target_location, was_friendly=was_friendly)
        return ActionResult.ok(events)

    def cost_description(self, state: "GameState") -> str:
        if self.free:
            return "免费"
        return "4军力 (标准) / 2.5军力 (中立限定)"

# ============================================================
# Archive (存档)
# ============================================================

@dataclass
class ArchiveAction(GameAction):
    """存档：将一张牌放入史书区，获得史书vp。东晋获得1功绩。"""
    action_type: str = "archive"
    player_id: str = ""
    card_index: int = -1          # Index in hand (-1 = from court, use card_id)
    card_id: str = ""             # Card identifier
    source: str = "hand"          # "hand" | "court" | "card_effect"

    def validate(self, state: "GameState") -> ActionResult:
        player = state.get_player(self.player_id)
        if not player:
            return ActionResult.fail(f"Player {self.player_id} not found")

        if self.source == "hand":
            if self.card_index < 0 or self.card_index >= len(player.hand):
                return ActionResult.fail(f"Invalid hand index {self.card_index}")
        elif self.source == "court":
            court = state.get_court_cards(self.player_id)
            found = any(c.definition.card_id == self.card_id for c in court)
            if not found:
                return ActionResult.fail(f"Card {self.card_id} not in court")

        return ActionResult.ok()

    def execute(self, state: "GameState") -> ActionResult:
        validation = self.validate(state)
        if not validation.success:
            return validation

        player = state.get_player(self.player_id)

        card = None
        if self.source == "hand":
            card = player.hand.pop(self.card_index)
        elif self.source == "court":
            court = state.get_court_cards(self.player_id)
            for i, c in enumerate(court):
                if c.definition.card_id == self.card_id:
                    card = court.pop(i)
                    break

        if not card:
            return ActionResult.fail("Card not found")

        events = []

        # Special handling for refugee cards (流民)
        if card.is_refugee or card.name == "流民":
            # Return to supply, player gets 2 VP
            state.refugee_supply.append(card)
            player.vp += 2
            events.append({"type": "refugee_archived", "vp": 2})
        else:
            # Normal archive
            player.history_area.append(card)
            history_vp = card.definition.history_vp
            if history_vp > 0:
                player.vp += history_vp
                events.append({"type": "archive_vp", "vp": history_vp})

        # Jin players gain 1 contribution for archiving
        if player.faction == FactionType.JIN:
            player.contribution = min(9, player.contribution + 1)
            events.append({"type": "contribution_gained", "amount": 1})

        state.log_event("archive", player=self.player_id,
                         card=card.name, source=self.source)
        return ActionResult.ok(events)

    def cost_description(self, state: "GameState") -> str:
        return "存档1张牌"

# ============================================================
# Spread Culture (传播文化)
# ============================================================

@dataclass
class SpreadCultureAction(GameAction):
    """传播文化：在地图区域放置文化标记。

    Can only be done via card effects (not a quick action).
    Placement conditions:
      - Player controls the region, OR
      - Region is adjacent to a region that already has this culture

    If slot is empty: placement reward (from map data)
    If slot is occupied: replace existing marker
    New marker is locked (背面朝上) until settlement phase.

    VP: equal to count of this culture in this region + adjacent regions (max 5)
    Then: increase contribution by 1 (max 10, otherwise +3VP)
    """
    action_type: str = "spread_culture"
    player_id: str = ""
    culture_type: str = ""      # "confucianism" | "taoism" | "buddhism"
    target_region: str = ""     # Region name, e.g. "关中"

    def validate(self, state: "GameState") -> ActionResult:
        player = state.get_player(self.player_id)
        if not player:
            return ActionResult.fail(f"Player {self.player_id} not found")

        if self.culture_type not in ("confucianism", "taoism", "buddhism"):
            return ActionResult.fail(f"Invalid culture type: {self.culture_type}")
        # Check region exists
        try:
            region = Region(self.target_region)
        except ValueError:
            return ActionResult.fail(f"Invalid region: {self.target_region}")

        # Check region has culture slot
        # (For now, assume 1 slot per region — refined when region defs loaded)

        # Must have control or adjacency to existing culture
        # Simplified check for now
        return ActionResult.ok()

    def execute(self, state: "GameState") -> ActionResult:
        validation = self.validate(state)
        if not validation.success:
            return validation

        player = state.get_player(self.player_id)

        culture = CultureType(self.culture_type)
        events = []

        # Count culture markers in this region + adjacent regions
        # Simplified: count the total map markers of this type
        same_culture_count = sum(
            1 for loc in state.locations.values()
            if loc.culture_marker == culture
        )
        vp = min(5, same_culture_count + 1)  # +1 for the new one
        player.vp += vp
        events.append({"type": "spread_culture_vp", "culture": self.culture_type, "vp": vp})

        # Increase contribution (max 10)
        contrib = player.culture_contributions.get(culture, 0)
        if contrib < 10:
            player.culture_contributions[culture] = contrib + 1
            events.append({"type": "culture_contribution", "culture": self.culture_type,
                           "new_level": contrib + 1})
        else:
            player.vp += 3
            events.append({"type": "culture_max_contribution_bonus", "vp": 3})

        # Place marker (locked) and award placement bonus
        # Find a location in the target region with a culture slot
        was_empty = False
        for loc in state.locations.values():
            if self.target_region in _get_location_regions(loc.location_id):
                was_empty = (loc.culture_marker is None)
                loc.culture_marker = culture
                loc.culture_locked = True
                events.append({"type": "culture_placed",
                               "location": loc.location_id,
                               "culture": self.culture_type,
                               "was_empty": was_empty})
                break

        # Placement bonus (only if slot was empty)
        if was_empty:
            from rules.area_control import REGION_CONFIG
            try:
                region_enum = Region(self.target_region)
                cfg = REGION_CONFIG.get(region_enum, {})
                bonus = cfg.get("culture_bonus")
                if bonus:
                    btype = bonus["type"]
                    amount = bonus["amount"]
                    if btype == "vp":
                        player.vp += amount
                        events.append({"type": "culture_placement_bonus",
                                       "bonus_type": "vp", "amount": amount})
                    elif btype == "military":
                        player.military += amount
                        events.append({"type": "culture_placement_bonus",
                                       "bonus_type": "military", "amount": amount})
                    elif btype == "draw_card":
                        draw_events = state.draw_cards(self.player_id, amount)
                        events.extend(draw_events)
            except ValueError:
                pass

        state.log_event("spread_culture", player=self.player_id,
                         culture=self.culture_type, region=self.target_region)
        return ActionResult.ok(events)

    def cost_description(self, state: "GameState") -> str:
        return "3.5军力 (仅卡牌效果)"

# ============================================================
# Search (检索)
# ============================================================

@dataclass
class SearchAction(GameAction):
    """检索：从牌库顶依次展示，找到符合条件的牌加入手牌，其余弃置。

    强制事件牌放在一旁不触发，检索结束后洗回牌库。
    """
    action_type: str = "search"
    player_id: str = ""
    search_count: int = 1         # How many to find
    search_type: str = ""         # "strategy", "friend", "culture", "power", "military", etc.
    search_tag: str = ""          # Specific marker to search for

    def validate(self, state: "GameState") -> ActionResult:
        if self.search_count < 1:
            return ActionResult.fail("Search count must be >= 1")
        if not state.main_deck:
            return ActionResult.fail("Main deck is empty")
        return ActionResult.ok()

    def execute(self, state: "GameState") -> ActionResult:
        validation = self.validate(state)
        if not validation.success:
            return validation

        player = state.get_player(self.player_id)
        events = []
        found_cards = []
        forced_events_set_aside = []

        for _ in range(self.search_count):
            # Search through deck
            examined = []
            found = None
            while state.main_deck and not found:
                card = state.main_deck.pop(0)
                if self._matches_search(card):
                    found = card
                elif card.card_type.value == "mechanism":
                    forced_events_set_aside.append(card)
                else:
                    examined.append(card)

            if found:
                player.hand.append(found)
                found_cards.append(found.name)
                events.append({"type": "search_found", "card": found.name})

            # Discard examined cards
            state.main_discard.extend(examined)

        # Shuffle forced event cards back into deck
        if forced_events_set_aside:
            import random
            random.shuffle(forced_events_set_aside)
            state.main_deck = forced_events_set_aside + state.main_deck
            events.append({"type": "search_forced_events_returned",
                           "count": len(forced_events_set_aside)})

        state.log_event("search", player=self.player_id,
                         search_type=self.search_type, found=len(found_cards))
        return ActionResult.ok(events)

    def _matches_search(self, card: "Card") -> bool:
        """Check if a card matches the search criteria."""

        type_mapping = {
            "strategy": CardType.STRATEGY,
            "friend": CardType.FRIEND,
            "culture": "culture",    # by tag
            "power": "power",        # by tag
            "military": "military",  # by tag
            "event": CardType.EVENT,
        }

        target = type_mapping.get(self.search_type)
        if target is None:
            return False

        if isinstance(target, CardType):
            return card.card_type == target

        # Search by tag/marker
        tag_mapping = {
            "culture": "marker_culture",
            "power": "marker_power",
            "military": "marker_military",
        }
        attr = tag_mapping.get(self.search_type)
        if attr:
            return getattr(card.definition, attr, 0) > 0

        return False

    def cost_description(self, state: "GameState") -> str:
        return "仅卡牌效果"

# ============================================================
# Levy (征发)
# ============================================================

@dataclass
class LevyAction(GameAction):
    """征发：从朝堂区选择候选策略牌，获得其资源效果，然后将牌放入出牌区。（仅卡牌效果）"""
    action_type: str = "levy"
    player_id: str = ""
    card_id: str = ""             # Card to levy from court

    def validate(self, state: "GameState") -> ActionResult:
        court = state.get_court_cards(self.player_id)
        if not any(c.definition.card_id == self.card_id for c in court):
            return ActionResult.fail(f"Card {self.card_id} not in court")
        return ActionResult.ok()

    def execute(self, state: "GameState") -> ActionResult:
        validation = self.validate(state)
        if not validation.success:
            return validation

        player = state.get_player(self.player_id)
        court = state.get_court_cards(self.player_id)

        card = None
        for i, c in enumerate(court):
            if c.definition.card_id == self.card_id:
                card = court.pop(i)
                break

        if not card:
            return ActionResult.fail("Card not found in court")

        # Gain resource option
        defn = card.definition
        player.military += defn.resource_option_army
        player.vp += defn.resource_option_vp

        # Move to played area for this round
        if self.player_id == "north":
            state.north_played_this_round.append(card)
        else:
            state.jin_played_this_round.append(card)

        events = [{
            "type": "levy", "player": self.player_id, "card": card.name,
            "army_gained": defn.resource_option_army,
            "vp_gained": defn.resource_option_vp,
        }]

        state.log_event("levy", player=self.player_id, card=card.name)
        return ActionResult.ok(events)

    def cost_description(self, state: "GameState") -> str:
        return "1.5军力 (仅卡牌效果)"

# ============================================================
# Order changes (提高/降低顺位)
# ============================================================

@dataclass
class RaiseOrderAction(GameAction):
    """提高行动顺位：将自己的顺位值+1（顺位值越大越先行动）。仅东晋。"""
    action_type: str = "raise_order"
    player_id: str = ""
    amount: int = 1

    def validate(self, state: "GameState") -> ActionResult:
        player = state.get_player(self.player_id)
        if not player:
            return ActionResult.fail(f"Player {self.player_id} not found")
        if player.faction != FactionType.JIN:
            return ActionResult.fail("Only Jin players can change order")
        return ActionResult.ok()

    def execute(self, state: "GameState") -> ActionResult:
        validation = self.validate(state)
        if not validation.success:
            return validation

        player = state.get_player(self.player_id)
        player.order = min(10, player.order + self.amount)  # Higher = earlier
        player.order_seq = state.allocate_order_seq()  # 后到者优先
        # Note: order change doesn't affect current round's turn order

        state.log_event("raise_order", player=self.player_id, new_order=player.order)
        return ActionResult.ok([{"type": "raise_order", "player": self.player_id,
                                  "new_order": player.order}])

    def cost_description(self, state: "GameState") -> str:
        return "1.5军力 (仅卡牌效果)"

@dataclass
class LowerOrderAction(GameAction):
    """降低行动顺位：将目标顺位值-1（顺位值越小越晚行动）。"""
    action_type: str = "lower_order"
    player_id: str = ""           # Who is using this
    target_player_id: str = ""    # Whose order to lower
    amount: int = 1

    def validate(self, state: "GameState") -> ActionResult:
        target = state.get_player(self.target_player_id)
        if not target:
            return ActionResult.fail(f"Target player {self.target_player_id} not found")
        if target.faction != FactionType.JIN:
            return ActionResult.fail("Can only lower Jin player's order")
        return ActionResult.ok()

    def execute(self, state: "GameState") -> ActionResult:
        validation = self.validate(state)
        if not validation.success:
            return validation

        target = state.get_player(self.target_player_id)
        target.order = max(0, target.order - self.amount)  # Lower = later
        target.order_seq = state.allocate_order_seq()  # 后到者优先

        state.log_event("lower_order", target=self.target_player_id,
                         new_order=target.order)
        return ActionResult.ok([{"type": "lower_order", "player": self.target_player_id,
                                  "new_order": target.order}])

    def cost_description(self, state: "GameState") -> str:
        return "仅卡牌效果"

# ============================================================
# Helpers
# ============================================================

def _control_state_to_player_id(cs: "ControlState") -> Optional[str]:
    mapping = {
        ControlState.NORTH: "north",
        ControlState.JIN_P1: "jin_1",
        ControlState.JIN_P2: "jin_2",
        ControlState.JIN_P3: "jin_3",
        ControlState.SIMA: "sima",
    }
    return mapping.get(cs)

def _get_location_regions(location_id: str) -> list[str]:
    """Get which regions a location belongs to. Source: board_info.md."""
    region_map = {
        # 西凉
        "张掖": ["西凉"], "姑臧": ["西凉"], "金城": ["西凉"],
        # 关中
        "安定": ["关中"], "天水": ["关中"], "长安": ["关中"],
        # 巴蜀
        "汉中": ["巴蜀"], "巴郡": ["巴蜀"], "蜀郡": ["巴蜀"],
        # 荆襄 (含上洛)
        "襄阳": ["荆襄"], "南郡": ["荆襄"], "巴东": ["荆襄"],
        "武昌": ["荆襄"], "宛城": ["荆襄"], "上洛": ["荆襄"],
        # 江南 (浔阳替代豫章)
        "浔阳": ["江南"], "建康": ["江南"], "京口": ["江南"],
        "吴": ["江南"], "会稽": ["江南"],
        # 中原 (上洛移出)
        "弘农": ["关中", "中原"], "洛阳": ["中原"],
        "雍丘": ["中原"], "彭城": ["中原"], "谯": ["中原"], "东平": ["中原"],
        # 山西
        "平阳": ["山西"], "太原": ["山西"], "上党": ["山西"],
        # 山东
        "济南": ["山东"], "广固": ["山东"], "琅琊": ["山东"],
        # 淮南
        "寿春": ["淮南"], "合肥": ["淮南"], "广陵": ["淮南"],
        # 河北
        "中山": ["河北"], "襄国": ["河北"], "邺城": ["河北"], "信都": ["河北"],
        # 幽燕
        "蓟城": ["幽燕"], "龙城": ["幽燕"],
        # 关外
        "盛乐": ["关外"], "平城": ["关外"],
    }
    return region_map.get(location_id, [])
