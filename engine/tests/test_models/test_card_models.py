"""Tests for CardDef, Card, and CardLibrary data models."""

import pytest
from models.enums import CardType, CardCategory, FactionType, MarkerType
from models.card import CardDef, Card, CardLibrary


class TestCardDef:
    """Tests for CardDef (immutable card definition)."""

    def test_create_basic_card(self):
        card = CardDef(
            card_id="test_1",
            name="士兵",
            owner_faction="初始",
            cost=0,
            card_type=CardType.STRATEGY,
            card_category=CardCategory.INITIAL,
            effect_text="行动：3军力",
            resource_military=1,
            history_vp=1,
            marker_military=1,
        )
        assert card.name == "士兵"
        assert card.cost == 0
        assert card.card_type == CardType.STRATEGY
        assert card.resource_military == 1
        assert card.marker_military == 1

    def test_markers_property(self):
        card = CardDef(
            card_id="test_2",
            name="test",
            owner_faction="通用",
            cost=1,
            card_type=CardType.EVENT,
            card_category=CardCategory.EVENT_MILITARY,
            effect_text="",
            marker_military=2,
            marker_culture=1,
        )
        markers = card.markers
        assert MarkerType.MILITARY in markers
        assert MarkerType.CULTURE in markers
        assert markers[MarkerType.MILITARY] == 2
        assert markers[MarkerType.CULTURE] == 1
        assert MarkerType.AFFAIR not in markers

    def test_total_markers(self):
        card = CardDef(
            card_id="test_3",
            name="test",
            owner_faction="通用",
            cost=1,
            card_type=CardType.EVENT,
            card_category=CardCategory.EVENT_MILITARY,
            effect_text="",
            marker_military=1,
            marker_culture=1,
            marker_affair=1,
            marker_power=1,
        )
        assert card.total_markers == 4

    def test_faction_playable_jin_only(self):
        card = CardDef(
            card_id="test_jin",
            name="jin_only_card",
            owner_faction="东晋",
            cost=1,
            card_type=CardType.EVENT,
            card_category=CardCategory.EVENT_POWER,
            effect_text="",
            faction_restriction="jin",
        )
        assert card.is_playable_by(FactionType.JIN)
        assert not card.is_playable_by(FactionType.NORTH)

    def test_faction_playable_north_only(self):
        card = CardDef(
            card_id="test_north",
            name="north_only_card",
            owner_faction="北方",
            cost=1,
            card_type=CardType.EVENT,
            card_category=CardCategory.EVENT_MILITARY,
            effect_text="",
            faction_restriction="north",
        )
        assert card.is_playable_by(FactionType.NORTH)
        assert not card.is_playable_by(FactionType.JIN)

    def test_faction_playable_no_restriction(self):
        card = CardDef(
            card_id="test_common",
            name="common_card",
            owner_faction="通用",
            cost=1,
            card_type=CardType.EVENT,
            card_category=CardCategory.EVENT_UTILITY,
            effect_text="",
        )
        assert card.is_playable_by(FactionType.JIN)
        assert card.is_playable_by(FactionType.NORTH)

    def test_culture_tags(self):
        card = CardDef(
            card_id="test_culture",
            name="cultural_card",
            owner_faction="通用",
            cost=1,
            card_type=CardType.STRATEGY,
            card_category=CardCategory.STRATEGY_CULTURE,
            effect_text="",
            culture_confucianism=2,
            culture_taoism=1,
        )
        from models.enums import CultureType
        tags = card.culture_tags
        assert CultureType.CONFUCIANISM in tags
        assert CultureType.TAOISM in tags
        assert CultureType.BUDDHISM not in tags

    def test_is_frozen(self, sample_card_def):
        """CardDef should be immutable (frozen dataclass)."""
        with pytest.raises(Exception):
            sample_card_def.cost = 5  # type: ignore


class TestCard:
    """Tests for Card (runtime card instance)."""

    def test_create_card_instance(self, sample_card_def):
        card = Card(definition=sample_card_def, owner_player_id="north")
        assert card.name == "士兵"
        assert card.owner_player_id == "north"
        assert card.card_type == CardType.STRATEGY

    def test_card_delegation(self, sample_card_def):
        card = Card(definition=sample_card_def)
        assert card.cost == 0
        assert card.effect_text == "行动：3军力"

    def test_card_is_friend(self):
        friend_def = CardDef(
            card_id="friend_test",
            name="邓羌",
            owner_faction="苻坚",
            cost=3,
            card_type=CardType.FRIEND,
            card_category=CardCategory.FRIEND_MILITARY,
            effect_text="主动：获得X军力",
            is_friend=True,
        )
        card = Card(definition=friend_def)
        assert card.is_friend

    def test_card_is_refugee(self):
        refugee_def = CardDef(
            card_id="refugee_1",
            name="流民",
            owner_faction="初始",
            cost=0,
            card_type=CardType.REFUGEE,
            card_category=CardCategory.REFUGEE,
            effect_text="",
        )
        card = Card(definition=refugee_def)
        assert card.is_refugee


class TestCardLibrary:
    """Tests for CardLibrary."""

    def test_create_empty(self):
        lib = CardLibrary([])
        assert len(lib) == 0

    def test_add_and_query(self, sample_card_def):
        lib = CardLibrary([sample_card_def])
        assert len(lib) == 1
        assert lib.get("initial_士兵_1") is sample_card_def

    def test_get_nonexistent(self, sample_card_def):
        lib = CardLibrary([sample_card_def])
        assert lib.get("nonexistent") is None

    def test_by_type(self, sample_card_def, sample_refugee_def):
        lib = CardLibrary([sample_card_def, sample_refugee_def])
        strategies = lib.by_type(CardType.STRATEGY)
        assert len(strategies) == 2

    def test_by_faction(self, sample_card_def):
        lib = CardLibrary([sample_card_def])
        results = lib.by_faction("初始")
        assert len(results) == 1
        assert results[0].name == "士兵"

    def test_by_marker(self):
        military_card = CardDef(
            card_id="mil_1", name="军事牌", owner_faction="通用",
            cost=1, card_type=CardType.EVENT, card_category=CardCategory.EVENT_MILITARY,
            effect_text="", marker_military=1,
        )
        culture_card = CardDef(
            card_id="cul_1", name="文化牌", owner_faction="通用",
            cost=1, card_type=CardType.EVENT, card_category=CardCategory.EVENT_CULTURE,
            effect_text="", marker_culture=1,
        )
        lib = CardLibrary([military_card, culture_card])
        assert len(lib.by_marker(MarkerType.MILITARY)) == 1
        assert len(lib.by_marker(MarkerType.CULTURE)) == 1
        assert len(lib.by_marker(MarkerType.POWER)) == 0

    def test_by_name_exact(self, sample_card_def):
        lib = CardLibrary([sample_card_def])
        found = lib.by_name_exact("士兵")
        assert found is sample_card_def
        assert lib.by_name_exact("不存在") is None

    def test_search(self, sample_card_def):
        lib = CardLibrary([sample_card_def])
        results = lib.search(cost=0)
        assert len(results) >= 1
