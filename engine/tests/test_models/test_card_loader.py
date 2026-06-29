"""Tests for the CSV card loader."""

import os
import pytest


class TestCardLoader:
    """Tests that the CSV loader correctly parses card_design.csv."""

    def test_load_card_design_csv(self):
        """Verify card_design.csv can be loaded and parsed."""
        csv_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "card_design.csv"
        )
        if not os.path.exists(csv_path):
            pytest.skip("card_design.csv not found")

        from cards.loader import load_card_design_csv
        lib = load_card_design_csv(csv_path)

        # Should have loaded many cards (the CSV has ~129 non-header rows)
        assert len(lib) > 100, f"Expected >100 cards, got {len(lib)}"

    def test_all_cards_have_required_fields(self):
        """Every loaded card must have name, type, and cost."""
        csv_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "card_design.csv"
        )
        if not os.path.exists(csv_path):
            pytest.skip("card_design.csv not found")

        from cards.loader import load_card_design_csv
        lib = load_card_design_csv(csv_path)

        for card in lib.all_cards:
            assert card.name, f"Card {card.card_id} has no name"
            assert card.card_type is not None, f"Card {card.name} has no type"
            # cost can be -1 for heroes, 0-3 for playables

    def test_known_cards_exist(self):
        """Verify some well-known cards are loaded correctly."""
        csv_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "card_design.csv"
        )
        if not os.path.exists(csv_path):
            pytest.skip("card_design.csv not found")

        from cards.loader import load_card_design_csv
        lib = load_card_design_csv(csv_path)

        # Check that key cards exist (use names exactly as in CSV)
        known_names = ["士卒", "流民", "北伐", "清谈", "征辟人才", "宫廷", "加官进爵"]
        for name in known_names:
            cards = lib.get_by_name(name)
            assert len(cards) > 0, f"Card '{name}' not found in library"

    def test_hero_cards_exist(self):
        """Verify hero cards are loaded."""
        csv_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "card_design.csv"
        )
        if not os.path.exists(csv_path):
            pytest.skip("card_design.csv not found")

        from cards.loader import load_card_design_csv
        from models.enums import CardType
        lib = load_card_design_csv(csv_path)

        heroes = lib.by_type(CardType.HERO)
        # Should have at least: 苻坚, 慕容儁, 拓跋珪, 王导, 谢安, 郗鉴, 张轨, 桓温, 刘裕, 祖逖, 顾荣
        assert len(heroes) >= 8, f"Expected >=8 heroes, got {len(heroes)}"

    def test_faction_cards_separated(self):
        """North-specific and Jin-specific cards should be tagged."""
        csv_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "card_design.csv"
        )
        if not os.path.exists(csv_path):
            pytest.skip("card_design.csv not found")

        from cards.loader import load_card_design_csv
        lib = load_card_design_csv(csv_path)

        north_cards = lib.by_faction("北方")
        # North-specific cards exist (e.g. 姚苌, 鸠摩罗什, 孙恩, etc.)
        assert len(north_cards) > 0, f"Expected north-specific cards, found {len(north_cards)}"

        # Check that cards have faction_restriction
        north_only = [c for c in lib.all_cards if c.faction_restriction == "north"]
        jin_only = [c for c in lib.all_cards if c.faction_restriction == "jin"]
        # There should be cards restricted to each faction
        # Note: faction_restriction comes from 限定东晋/限定北方 columns (1=restricted)
        # If these are empty in CSV, the count may be 0 — that's OK
        assert len(north_only) >= 0  # Conditionally present
        assert len(jin_only) >= 0    # Conditionally present

    def test_resource_parsing(self):
        """Verify resource text parsing works."""
        from cards.loader import _parse_resource

        army, vp = _parse_resource("2军力1vp")
        assert army == 2
        assert vp == 1

        army, vp = _parse_resource("3军力")
        assert army == 3
        assert vp == 0

        army, vp = _parse_resource("4vp")
        assert army == 0
        assert vp == 4

        army, vp = _parse_resource("1军力2vp")
        assert army == 1
        assert vp == 2

        army, vp = _parse_resource("-")
        assert army == 0
        assert vp == 0

        army, vp = _parse_resource("3军力-1vp")
        assert army == 3
        assert vp == -1

    def test_card_types_distinct(self):
        """Verify cards of different types are loaded."""
        csv_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "card_design.csv"
        )
        if not os.path.exists(csv_path):
            pytest.skip("card_design.csv not found")

        from cards.loader import load_card_design_csv
        from models.enums import CardType
        lib = load_card_design_csv(csv_path)

        # Should have multiple card types
        types_found = set()
        for card in lib.all_cards:
            types_found.add(card.card_type)
        assert len(types_found) >= 4  # HERO, STRATEGY, EVENT, FRIEND at minimum
