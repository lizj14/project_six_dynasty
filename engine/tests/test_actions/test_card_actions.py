"""Tests for PlayCardAction and CourtAction."""

import pytest
from models.enums import ControlState, TerrainType, FactionType, CardType, CardCategory
from models.location import LocationState, AdjacencyDef
from models.player import PlayerState
from models.card import CardDef, Card
from models.game_state import GameState, PhaseType


def make_state():
    locs = {
        "长安": LocationState(location_id="长安", controller=ControlState.NORTH),
    }
    adjs = []
    north = PlayerState(
        player_id="north", faction=FactionType.NORTH,
        military=5, vp=0, army_reserve_count=8, army_placed_count=1,
    )
    jin1 = PlayerState(
        player_id="jin_1", faction=FactionType.JIN,
        military=5, vp=0, contribution=0,
        army_reserve_count=8, army_placed_count=0,
    )
    state = GameState(
        round=1, phase=PhaseType.ACTION,
        north_player=north,
        jin_players=[jin1,
            PlayerState(player_id="jin_2", faction=FactionType.JIN, army_reserve_count=8),
            PlayerState(player_id="jin_3", faction=FactionType.JIN, army_reserve_count=8),
        ],
        locations=locs, map_adjacencies=adjs,
        turn_order=["north", "jin_1", "jin_2", "jin_3"],
        active_player_index=0, seed=42,
    )
    return state


class TestPlayCardAction:
    """Tests for hand card play (手牌行动)."""

    def test_play_0_cost_card(self):
        from engine.actions.card_actions import PlayCardAction
        state = make_state()
        card_def = CardDef(
            card_id="test_1", name="test_event", owner_faction="通用",
            cost=0, card_type=CardType.EVENT,
            card_category=CardCategory.EVENT_UTILITY,
            effect_text="", history_vp=3,
        )
        state.north_player.hand = [Card(definition=card_def)]
        action = PlayCardAction(player_id="north", card_index=0, payment_indices=[])
        result = action.execute(state)
        assert result.success
        assert state.north_player.has_taken_hand_action
        # Event card goes to main discard
        assert len(state.main_discard) == 1

    def test_play_card_with_cost(self):
        from engine.actions.card_actions import PlayCardAction
        state = make_state()
        main_card = CardDef(
            card_id="main", name="expensive_event", owner_faction="通用",
            cost=2, card_type=CardType.EVENT,
            card_category=CardCategory.EVENT_UTILITY,
            effect_text="",
        )
        pay1 = CardDef(
            card_id="pay1", name="junk1", owner_faction="通用",
            cost=0, card_type=CardType.EVENT,
            card_category=CardCategory.EVENT_UTILITY,
            effect_text="",
        )
        pay2 = CardDef(
            card_id="pay2", name="junk2", owner_faction="通用",
            cost=0, card_type=CardType.EVENT,
            card_category=CardCategory.EVENT_UTILITY,
            effect_text="",
        )
        state.north_player.hand = [
            Card(definition=main_card),
            Card(definition=pay1),
            Card(definition=pay2),
        ]
        # Play card at index 0, pay with indices 1 and 2
        action = PlayCardAction(player_id="north", card_index=0, payment_indices=[1, 2])
        result = action.execute(state)
        assert result.success
        assert len(state.north_player.hand) == 0  # All 3 cards used
        assert len(state.main_discard) == 3  # 1 played + 2 payment

    def test_play_strategy_goes_to_deck(self):
        from engine.actions.card_actions import PlayCardAction
        state = make_state()
        card_def = CardDef(
            card_id="strat_1", name="test_strategy", owner_faction="通用",
            cost=1, card_type=CardType.STRATEGY,
            card_category=CardCategory.STRATEGY_MILITARY,
            effect_text="",
        )
        pay = CardDef(
            card_id="pay1", name="junk", owner_faction="通用",
            cost=0, card_type=CardType.EVENT,
            card_category=CardCategory.EVENT_UTILITY,
            effect_text="",
        )
        state.north_player.hand = [Card(definition=card_def), Card(definition=pay)]
        action = PlayCardAction(player_id="north", card_index=0, payment_indices=[1])
        result = action.execute(state)
        assert result.success
        # Strategy goes to north deck
        assert len(state.north_deck) == 1

    def test_play_friend_to_staff(self):
        from engine.actions.card_actions import PlayCardAction
        state = make_state()
        friend_def = CardDef(
            card_id="friend_1", name="test_friend", owner_faction="通用",
            cost=0, card_type=CardType.FRIEND,
            card_category=CardCategory.FRIEND_SPECIAL,
            effect_text="", is_friend=True,
        )
        state.north_player.hand = [Card(definition=friend_def)]
        action = PlayCardAction(player_id="north", card_index=0, payment_indices=[])
        result = action.execute(state)
        assert result.success
        assert len(state.north_player.staff_area) == 1

    def test_play_friend_staff_full(self):
        """When staff area is full, friend cards can still be played by
        replacing an existing staff member (default: replace_staff_index=0).
        """
        from engine.actions.card_actions import PlayCardAction
        state = make_state()
        existing = CardDef(
            card_id="exist", name="existing", owner_faction="通用",
            cost=0, card_type=CardType.FRIEND,
            card_category=CardCategory.FRIEND_SPECIAL,
            effect_text="", is_friend=True,
        )
        new_friend = CardDef(
            card_id="new", name="new_friend", owner_faction="通用",
            cost=0, card_type=CardType.FRIEND,
            card_category=CardCategory.FRIEND_SPECIAL,
            effect_text="", is_friend=True,
        )
        state.north_player.staff_area = [Card(definition=existing)] * 4  # North limit = 4
        state.north_player.hand = [Card(definition=new_friend)]
        action = PlayCardAction(player_id="north", card_index=0, payment_indices=[])
        # Validation passes — staff full no longer blocks
        assert action.validate(state).success
        # Execute replaces staff[0] with the new friend
        result = action.execute(state)
        assert result.success
        assert len(state.north_player.staff_area) == 4  # Still at limit
        assert state.north_player.staff_area[-1].name == "new_friend"  # New card added
        replaced = [e for e in result.events if e.get("type") == "staff_replaced"]
        assert len(replaced) == 1
        assert replaced[0]["replaced_by"] == "new_friend"

    def test_play_jin_strategy_gains_contribution(self):
        from engine.actions.card_actions import PlayCardAction
        state = make_state()
        card_def = CardDef(
            card_id="strat_1", name="test_strategy", owner_faction="通用",
            cost=0, card_type=CardType.STRATEGY,
            card_category=CardCategory.STRATEGY_SPECIAL,
            effect_text="",
        )
        state.jin_players[0].hand = [Card(definition=card_def)]
        action = PlayCardAction(player_id="jin_1", card_index=0, payment_indices=[])
        result = action.execute(state)
        assert result.success
        assert state.jin_players[0].contribution == 1

    def test_play_card_faction_restricted(self):
        """Faction restriction handled in execute(): card discarded with reason.

        This is the unified path for both normal play (safety net) and setup.
        """
        from engine.actions.card_actions import PlayCardAction
        state = make_state()
        card_def = CardDef(
            card_id="jin_only", name="jin_card", owner_faction="东晋",
            cost=0, card_type=CardType.EVENT,
            card_category=CardCategory.EVENT_POWER,
            effect_text="", faction_restriction="jin",
        )
        state.north_player.hand = [Card(definition=card_def)]
        action = PlayCardAction(player_id="north", card_index=0, payment_indices=[])
        # Validation passes (faction check is in execute, not validate)
        assert action.validate(state).success
        # Execute discards the card with faction_restriction reason
        result = action.execute(state)
        assert result.success  # Action completed, just with no effect
        assert len(state.north_player.hand) == 0  # Card discarded
        discarded = [e for e in result.events if e.get("type") == "card_discarded"]
        assert len(discarded) == 1
        assert discarded[0]["reason"] == "faction_restriction"

    def test_duplicate_payment_index(self):
        from engine.actions.card_actions import PlayCardAction
        state = make_state()
        main = CardDef(card_id="main", name="main", owner_faction="通用",
                        cost=2, card_type=CardType.EVENT,
                        card_category=CardCategory.EVENT_UTILITY, effect_text="")
        pay = CardDef(card_id="pay", name="pay", owner_faction="通用",
                       cost=0, card_type=CardType.EVENT,
                       card_category=CardCategory.EVENT_UTILITY, effect_text="")
        state.north_player.hand = [
            Card(definition=main), Card(definition=pay), Card(definition=pay),
        ]
        action = PlayCardAction(player_id="north", card_index=0, payment_indices=[1, 1])
        result = action.validate(state)
        assert not result.success


class TestCourtAction:
    """Tests for court action (牌组行动)."""

    def test_court_action_valid(self):
        from engine.actions.card_actions import CourtAction
        from cards.effect_parser import EffectParser
        state = make_state()
        card_def = CardDef(
            card_id="court_1", name="court_strategy", owner_faction="通用",
            cost=1, card_type=CardType.STRATEGY,
            card_category=CardCategory.STRATEGY_MILITARY,
            effect_text="行动：3军力", resource_military=3,
            parsed_effect=EffectParser().parse("court_strategy", "行动：3军力"),
        )
        state.north_court = [Card(definition=card_def)]
        action = CourtAction(player_id="north", card_id="court_1")
        result = action.execute(state)
        assert result.success
        assert state.north_player.military == 8  # 5 + 3
        assert state.north_player.has_taken_court_action
        assert len(state.north_court) == 0
        assert len(state.north_played_this_round) == 1

    def test_court_action_once_per_turn(self):
        from engine.actions.card_actions import CourtAction
        state = make_state()
        state.north_player.has_taken_court_action = True
        card_def = CardDef(
            card_id="court_1", name="court_strategy", owner_faction="通用",
            cost=1, card_type=CardType.STRATEGY,
            card_category=CardCategory.STRATEGY_MILITARY,
            effect_text="",
        )
        state.north_court = [Card(definition=card_def)]
        action = CourtAction(player_id="north", card_id="court_1")
        result = action.validate(state)
        assert not result.success

    def test_court_action_card_not_in_court(self):
        from engine.actions.card_actions import CourtAction
        state = make_state()
        action = CourtAction(player_id="north", card_id="nonexistent")
        result = action.validate(state)
        assert not result.success

    def test_court_action_jin_deck(self):
        """Jin players use the shared jin_court."""
        from engine.actions.card_actions import CourtAction
        from cards.effect_parser import EffectParser
        state = make_state()
        card_def = CardDef(
            card_id="jin_court_1", name="jin_strategy", owner_faction="通用",
            cost=1, card_type=CardType.STRATEGY,
            card_category=CardCategory.STRATEGY_SPECIAL,
            effect_text="行动：3军力", resource_military=3,
            parsed_effect=EffectParser().parse("jin_strategy", "行动：3军力"),
        )
        state.jin_court = [Card(definition=card_def)]
        action = CourtAction(player_id="jin_1", card_id="jin_court_1")
        result = action.execute(state)
        assert result.success
        assert state.jin_players[0].military == 8  # 5 + 3
        assert len(state.jin_played_this_round) == 1
