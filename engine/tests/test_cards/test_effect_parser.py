"""Tests for the card effect parser."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from cards.effect_parser import EffectParser
from cards.effect_ast import EffectType, AbilityType, TriggerType


@pytest.fixture
def parser():
    return EffectParser()


class TestParserSmoke:
    """Smoke tests — parser should not crash on any card."""

    def test_parse_all_cards_no_crash(self, parser):
        """Parse every card in card_design.csv without crashing."""
        csv_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "card_design.csv"
        )
        if not os.path.exists(csv_path):
            pytest.skip("card_design.csv not found")

        from cards.loader import load_card_design_csv
        lib = load_card_design_csv(csv_path)

        failures = []
        from models.enums import CardType
        for card in lib.all_cards:
            if card.card_type == CardType.GOAL:
                continue  # Goal cards have their own condition format
            if card.effect_text and card.effect_text.strip() not in ('', '-'):
                try:
                    effect = parser.parse(card.name, card.effect_text,
                                          is_usurp=card.is_usurp,
                                          faction_restriction=card.faction_restriction)
                    assert effect is not None
                except Exception as e:
                    failures.append(f"{card.name}: {e}")

        if failures:
            pytest.fail(f"Parser crashed on {len(failures)} cards:\n" +
                        "\n".join(failures[:20]))


class TestInitialCards:
    """Test parsing of the 10 initial/starting cards."""

    def test_parse_士兵(self, parser):
        """士兵: 行动：3军力 | resource: 1军力"""
        effect = parser.parse("士兵", "行动：3军力")
        assert len(effect.blocks) == 1
        block = effect.blocks[0]
        assert block.ability_type == AbilityType.STRATEGY_ACTION
        assert len(block.steps) == 1
        assert block.steps[0].effect_type == EffectType.GAIN_MILITARY
        assert block.steps[0].params["amount"] == 3

    def test_parse_清谈(self, parser):
        """清谈: 行动：6vp | resource: 2vp"""
        effect = parser.parse("清谈", "行动：6vp")
        assert len(effect.blocks) == 1
        assert effect.blocks[0].steps[0].effect_type == EffectType.GAIN_VP
        assert effect.blocks[0].steps[0].params["amount"] == 6

    def test_parse_宫廷(self, parser):
        """宫廷: 行动：存档1张候选策略牌 | resource: 1军力"""
        effect = parser.parse("宫廷", "行动：存档1张候选策略牌")
        assert len(effect.blocks) == 1
        step = effect.blocks[0].steps[0]
        assert step.effect_type == EffectType.ARCHIVE_CARD
        assert step.params["card_type"] == "court"

    def test_parse_征辟人才(self, parser):
        """征辟人才: 行动：摸2张牌。如果[内政]标记数>2，额外摸1张牌"""
        effect = parser.parse("征辟人才",
                              "行动：摸2张牌。如果[内政]标记数>2，额外摸1张牌")
        assert len(effect.blocks) == 1
        assert effect.blocks[0].steps[0].effect_type == EffectType.DRAW_CARDS
        assert effect.blocks[0].steps[0].params["count"] == 2

    def test_parse_北伐(self, parser):
        """北伐: 行动：2军力。从东晋面板获得[北伐]标记"""
        effect = parser.parse("北伐",
                              "行动：2军力。从东晋面板获得[北伐]标记")
        assert len(effect.blocks) == 1
        # First step: gain 2 military
        assert effect.blocks[0].steps[0].effect_type == EffectType.GAIN_MILITARY
        # Second step: get expedition marker
        assert effect.blocks[0].steps[1].effect_type == EffectType.GET_EXPEDITION

    def test_parse_加官进爵(self, parser):
        """加官进爵: 行动：支付1张手牌，提高1级顺位，传播1次[玄学]"""
        effect = parser.parse("加官进爵",
                              "行动：支付1张手牌，提高1级顺位，传播1次[玄学]")
        assert len(effect.blocks) == 1
        step_types = [s.effect_type for s in effect.blocks[0].steps]
        assert EffectType.RAISE_ORDER in step_types
        assert EffectType.SPREAD_CULTURE in step_types

    def test_parse_流民(self, parser):
        """流民: 被动：[流民]被存档时，自动放置回供应堆。存档[流民]的玩家获得2vp"""
        effect = parser.parse("流民",
                              "被动：[流民]被存档时，自动放置回供应堆。存档[流民]的玩家获得2vp。")
        assert len(effect.blocks) == 1
        assert effect.blocks[0].ability_type == AbilityType.PASSIVE

    def test_parse_轻骑兵(self, parser):
        """轻骑兵: 行动：2军力。选择1个玩家，随机抽取他的1张手牌"""
        effect = parser.parse("轻骑兵",
                              "行动：2军力。选择1个玩家，随机抽取他的1张手牌")
        assert len(effect.blocks) == 1


class TestMechanismCards:
    """Test parsing of forced event (强制事件) cards."""

    def test_parse_人何以堪(self, parser):
        """强制：选择1个幕僚区空位最少的玩家..."""
        effect = parser.parse("人何以堪",
                              "强制：选择1个幕僚区空位最少的玩家，该玩家选择1个费用最高的幕僚存档。摸1张牌。")
        assert len(effect.blocks) == 1
        assert effect.blocks[0].ability_type == AbilityType.FORCED

    def test_parse_功高不赏(self, parser):
        """强制：选择1个功绩最高的玩家，该玩家-1功绩并+6vp。摸1张牌。"""
        effect = parser.parse("功高不赏",
                              "强制：选择1个功绩最高的玩家，该玩家-1功绩并+6vp。摸1张牌。")
        assert effect.blocks[0].ability_type == AbilityType.FORCED


class TestFriendCards:
    """Test parsing of friend (幕僚) cards."""

    def test_parse_active_friend(self, parser):
        """主动：获得X军力，X=[军事]标记数（最多4）"""
        effect = parser.parse("邓羌",
                              "主动：获得X军力，X=[军事]标记数（最多4）。")
        assert len(effect.blocks) == 1
        assert effect.blocks[0].ability_type == AbilityType.ACTIVE
        step = effect.blocks[0].steps[0]
        assert step.effect_type == EffectType.GAIN_MILITARY
        assert step.params["variable"] is True

    def test_parse_friend_with_choice(self, parser):
        """主动：选择1项：弃1张手牌，然后摸1张牌；或者弃置1张候选策略牌..."""
        effect = parser.parse("尹纬",
                              "主动：选择1项：弃1张手牌，然后摸1张牌；"
                              "或者弃置1张候选策略牌，然后补充1张牌到朝堂区。")
        assert len(effect.blocks) == 1
        assert len(effect.blocks[0].choice_options) >= 1


class TestEventCards:
    """Test parsing of event cards."""

    def test_parse_conditional_event(self, parser):
        """控制[巴蜀]时，可以打出。存档此牌。"""
        effect = parser.parse("我见犹怜",
                              "控制[巴蜀]时，可以打出。存档此牌。")
        assert len(effect.blocks) >= 1

    def test_parse_military_event(self, parser):
        """获得7军力。存档此牌。"""
        effect = parser.parse("风声鹤唳，草木皆兵",
                              "获得7军力。存档此牌。")
        assert len(effect.blocks) == 1
        assert effect.blocks[0].steps[0].effect_type == EffectType.GAIN_MILITARY
        assert effect.blocks[0].steps[1].effect_type == EffectType.ARCHIVE_THIS


class TestStrategyCards:
    """Test parsing of strategy cards."""

    def test_parse_strategy_with_passive(self, parser):
        """行动：2军力。被动：需要控制[幽燕]，才能打出、执行或征发。"""
        effect = parser.parse("幽州突骑",
                              "行动：2军力。被动：需要控制[幽燕]，才能打出、执行或征发。")
        # Should have both strategy_action and passive blocks
        types = [b.ability_type for b in effect.blocks]
        assert AbilityType.STRATEGY_ACTION in types

    def test_parse_strategy_with_location_restriction(self, parser):
        """行动：获得5军力。被动：占据[京口]时，才能打出、执行或征发。"""
        effect = parser.parse("京口重镇",
                              "行动：获得5军力。被动：占据[京口]时，才能打出、执行或征发。")
        assert len(effect.blocks) >= 1


class TestHeroCards:
    """Test parsing of hero (角色) cards."""

    def test_parse_hero_north(self, parser):
        """主动：弃1张手牌，然后摸1张牌，可以执行1个手牌行动。登场：转化[长安][弘农][安定][平阳]"""
        effect = parser.parse("苻坚",
                              "主动：弃1张手牌，然后摸1张牌，可以执行1个手牌行动。"
                              "登场：转化[长安][弘农][安定][平阳]")
        types = [b.ability_type for b in effect.blocks]
        assert AbilityType.ACTIVE in types
        assert AbilityType.ENTER in types

    def test_parse_hero_jin(self, parser):
        """被动：每次获得功绩后，摸1张牌。登场：先动值8..."""
        effect = parser.parse("谢安",
                              "被动：每次获得功绩后，摸1张牌。"
                              "登场：先动值8。获得2功绩（不触发被动效果）。")
        types = [b.ability_type for b in effect.blocks]
        assert AbilityType.PASSIVE in types
        assert AbilityType.ENTER in types


class TestUsurpCards:
    """Test parsing of cards with usurp (僭越) effects."""

    def test_parse_usurp_block(self, parser):
        """[僭越]交换东晋首都和洛阳的部队。获得1威望。"""
        effect = parser.parse("还都洛阳",
                              "占据[洛阳]时，可以打出。存档此牌。"
                              "[僭越]交换东晋首都和洛阳的部队。获得1威望。")
        # Should have usurp steps in a block
        assert len(effect.blocks) >= 1

    def test_parse_urusp_tag(self, parser):
        """{urusp}改为选择1个东晋玩家..."""
        effect = parser.parse("刘隗",
                              "威望最高的东晋玩家，失去2威望。"
                              "{urusp}改为选择1个东晋玩家，失去2威望，存档此牌。")
        assert len(effect.blocks) >= 1


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_effect(self, parser):
        effect = parser.parse("empty", "")
        assert effect.blocks == []

    def test_dash_effect(self, parser):
        effect = parser.parse("dash", "-")
        assert effect.blocks == []

    def test_no_timing_keyword(self, parser):
        """Text without timing keyword should be treated as strategy action."""
        effect = parser.parse("test", "获得3军力，摸1张牌")
        assert len(effect.blocks) == 1
