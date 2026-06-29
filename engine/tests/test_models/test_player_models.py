"""Tests for PlayerState model."""

import pytest
from models.enums import FactionType, MarkerType
from models.player import PlayerState


class TestPlayerState:
    """Tests for PlayerState."""

    def test_create_north_player(self):
        p = PlayerState(player_id="north", faction=FactionType.NORTH)
        assert p.player_id == "north"
        assert p.faction == FactionType.NORTH
        assert p.staff_limit == 4
        assert len(p.hand) == 0
        assert p.military == 0

    def test_create_jin_player(self):
        p = PlayerState(player_id="jin_1", faction=FactionType.JIN)
        assert p.player_id == "jin_1"
        assert p.faction == FactionType.JIN
        assert p.staff_limit == 3
        assert p.prestige == 0
        assert p.contribution == 0

    def test_staff_free_slots(self):
        p = PlayerState(player_id="jin_1", faction=FactionType.JIN)
        assert p.staff_free_slots == 3

    def test_can_play_friend(self):
        p = PlayerState(player_id="jin_1", faction=FactionType.JIN)
        # Create a mock card for staff area
        from models.card import CardDef, Card
        from models.enums import CardType, CardCategory
        friend_def = CardDef(
            card_id="f1", name="test_friend", owner_faction="通用",
            cost=1, card_type=CardType.FRIEND,
            card_category=CardCategory.FRIEND_SPECIAL,
            effect_text="", is_friend=True,
        )
        p.staff_area = [Card(definition=friend_def)] * 3
        assert not p.can_play_friend()

    def test_hand_limit(self):
        p = PlayerState(player_id="jin_1", faction=FactionType.JIN)
        assert p.hand_limit == 8

    def test_turn_state_reset(self):
        p = PlayerState(
            player_id="north", faction=FactionType.NORTH,
            military=10, has_taken_hand_action=True, has_taken_court_action=True,
            has_drawn_quick=True, has_fortified_quick=True,
        )
        p.reset_turn_state()
        assert p.military == 0
        assert not p.has_taken_hand_action
        assert not p.has_taken_court_action
        assert not p.has_drawn_quick
        assert not p.has_fortified_quick

    def test_can_take_hand_action_initial(self):
        p = PlayerState(player_id="jin_1", faction=FactionType.JIN)
        assert p.can_take_hand_action()

    def test_can_take_court_action_initial(self):
        p = PlayerState(player_id="jin_1", faction=FactionType.JIN)
        assert p.can_take_court_action()

    def test_markers(self):
        p = PlayerState(player_id="jin_1", faction=FactionType.JIN)
        p.add_marker(MarkerType.MILITARY)
        p.add_marker(MarkerType.MILITARY)
        p.add_marker(MarkerType.CULTURE)
        assert p.marker_military == 2
        assert p.marker_culture == 1
        assert p.total_markers == 3
        assert p.distinct_markers == 2

    def test_get_marker(self):
        p = PlayerState(player_id="jin_1", faction=FactionType.JIN,
                         marker_military=3, marker_power=1)
        assert p.get_marker(MarkerType.MILITARY) == 3
        assert p.get_marker(MarkerType.POWER) == 1
        assert p.get_marker(MarkerType.CULTURE) == 0


class TestNorthVsJinDifferences:
    """Verify key differences between North and Jin players."""

    def test_staff_limits(self):
        north = PlayerState(player_id="north", faction=FactionType.NORTH)
        jin = PlayerState(player_id="jin_1", faction=FactionType.JIN)
        assert north.staff_limit == 4
        assert jin.staff_limit == 3

    def test_jin_has_prestige_contribution(self):
        jin = PlayerState(player_id="jin_1", faction=FactionType.JIN)
        assert hasattr(jin, 'prestige')
        assert hasattr(jin, 'contribution')

    def test_initial_military_values(self):
        """Per rulebook: North starts at 5, Jin at 1."""
        north = PlayerState(player_id="north", faction=FactionType.NORTH, military=5)
        jin = PlayerState(player_id="jin_1", faction=FactionType.JIN, military=1)
        assert north.military == 5
        assert jin.military == 1
