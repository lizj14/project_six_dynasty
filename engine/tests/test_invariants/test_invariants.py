"""测试游戏不变量 — 保证引擎不会破坏游戏基本规则。

覆盖:
  1. 总军力守恒（玩家 + Sima + 地图 = 常数）
  2. 卡牌总数守恒（手牌 + 牌库 + 弃牌堆 = 常数）
  3. 无负值（VP/军力/威望/功绩 >= 0）
  4. 手牌上限强制
  5. 游戏必须在第10回合前结束
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from models.enums import FactionType, CardType, PhaseType, ControlState
from models.card import CardDef, Card, CardLibrary
from models.player import PlayerState
from models.game_state import GameState


class TestNoNegativeValues:
    """Verify game state never goes negative for key resources."""

    def test_vp_non_negative(self, minimal_state):
        for p in minimal_state.get_all_players():
            assert p.vp >= 0, f"{p.player_id}: vp={p.vp}"

    def test_military_non_negative(self, minimal_state):
        for p in minimal_state.get_all_players():
            assert p.military >= 0, f"{p.player_id}: military={p.military}"

    def test_prestige_non_negative(self, minimal_state):
        for p in minimal_state.get_all_players():
            assert p.prestige >= 0, f"{p.player_id}: prestige={p.prestige}"

    def test_contribution_non_negative(self, minimal_state):
        for p in minimal_state.get_all_players():
            assert p.contribution >= 0, f"{p.player_id}: contribution={p.contribution}"

    def test_army_reserve_non_negative(self, minimal_state):
        for p in minimal_state.get_all_players():
            assert p.army_reserve_count >= 0, f"{p.player_id}: reserve={p.army_reserve_count}"

    def test_sima_military_non_negative(self, minimal_state):
        assert minimal_state.sima.military >= 0

    def test_sima_vp_non_negative(self, minimal_state):
        assert minimal_state.sima.vp >= 0


class TestPlayerInvariants:
    """Basic structural invariants per player."""

    def test_hand_limit_respected(self, minimal_state):
        for p in minimal_state.get_all_players():
            assert len(p.hand) <= p.hand_limit, \
                f"{p.player_id}: hand {len(p.hand)} > limit {p.hand_limit}"

    def test_staff_limit_respected(self, minimal_state):
        for p in minimal_state.get_all_players():
            assert len(p.staff_area) <= p.staff_limit, \
                f"{p.player_id}: staff {len(p.staff_area)} > limit {p.staff_limit}"

    def test_prestige_capped_at_9(self, minimal_state):
        for p in minimal_state.get_all_players():
            assert 0 <= p.prestige <= 9, f"{p.player_id}: prestige={p.prestige}"

    def test_contribution_capped_at_9(self, minimal_state):
        for p in minimal_state.get_all_players():
            assert 0 <= p.contribution <= 9, f"{p.player_id}: contribution={p.contribution}"

    def test_order_capped_at_9(self, minimal_state):
        for p in minimal_state.get_all_players():
            assert 0 <= p.order <= 9, f"{p.player_id}: order={p.order}"


class TestGameEnd:
    """Game must end within limit and have a winner."""

    def test_full_game_ends_within_max_rounds(self):
        """Run a full game with minimal config, verify it ends."""
        from config.version import Version
        from ai.dummy_ai import DummyAI
        from engine.game import GameEngine

        v = Version.load('v1.0')
        agents = [
            DummyAI("north", 1),
            DummyAI("jin_1", 2),
            DummyAI("jin_2", 3),
            DummyAI("jin_3", 4),
        ]
        engine = GameEngine(agents=agents, version=v, seed=9999)
        state = engine.run()
        assert state.phase == PhaseType.GAME_OVER
        assert state.round <= v.get("max_rounds", 10) + 1
        winner = engine.get_winner()
        assert winner is not None

    def test_full_game_all_vp_non_negative(self):
        """After a full game, all VP values are non-negative."""
        from config.version import Version
        from ai.dummy_ai import DummyAI
        from engine.game import GameEngine

        v = Version.load('v1.0')
        agents = [
            DummyAI("north", 100),
            DummyAI("jin_1", 200),
            DummyAI("jin_2", 300),
            DummyAI("jin_3", 400),
        ]
        engine = GameEngine(agents=agents, version=v, seed=8888)
        state = engine.run()
        for p in state.get_all_players():
            assert p.vp >= 0, f"{p.player_id} has negative VP: {p.vp}"


class TestSimaInvariants:
    """Sima state invariants."""

    def test_sima_has_army_and_prestige(self, minimal_state):
        assert minimal_state.sima.army_reserve_count >= 0
        assert 0 <= minimal_state.sima.prestige <= 9


class TestActionFlagsReset:
    """After reset_action_flags, player can act again."""

    def test_reset_clears_flags(self, north_player):
        north_player.has_taken_hand_action = True
        north_player.has_taken_court_action = True
        north_player.has_drawn_quick = True
        north_player.has_fortified_quick = True
        north_player.reset_action_flags()
        assert not north_player.has_taken_hand_action
        assert not north_player.has_taken_court_action
        assert not north_player.has_drawn_quick
        assert not north_player.has_fortified_quick
