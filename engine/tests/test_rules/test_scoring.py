"""Tests for final scoring module."""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from models.enums import ControlState, Region, FactionType, CultureType, PhaseType
from models.location import LocationState
from models.player import PlayerState
from models.game_state import GameState, SimaState, CultureTrackState
from rules.scoring import (
    score_culture, score_sima_distribution, run_final_scoring,
    CULTURE_SUPPLY_VP,
)


def make_scoring_state():
    """Create a state for scoring tests."""
    north = PlayerState(player_id="north", faction=FactionType.NORTH, vp=10)
    jin1 = PlayerState(player_id="jin_1", faction=FactionType.JIN,
                        vp=20, prestige=5, contribution=4, order=0)
    jin2 = PlayerState(player_id="jin_2", faction=FactionType.JIN,
                        vp=15, prestige=3, contribution=6, order=1)
    jin3 = PlayerState(player_id="jin_3", faction=FactionType.JIN,
                        vp=12, prestige=2, contribution=2, order=2)

    state = GameState(
        round=10, phase=PhaseType.GAME_OVER,
        north_player=north, jin_players=[jin1, jin2, jin3],
        sima=SimaState(vp=25, prestige=5),
    )
    return state


class TestCultureScoring:
    """Tests for culture step."""

    def test_no_markers_no_vp(self):
        """When a culture has 0 markers, no VP is awarded."""
        state = make_scoring_state()
        result = score_culture(state)
        for culture in CultureType:
            assert result[culture.value]["markers"] == 0
            assert result[culture.value]["vp_awarded"] == {}

    def test_markers_reveal_positions(self):
        """3 markers → reveal positions 1-3: VP values 1, 2, 4."""
        state = make_scoring_state()
        # Set up culture track with 3 markers removed from supply (supply_level)
        state.culture_tracks[CultureType.CONFUCIANISM] = CultureTrackState(
            culture=CultureType.CONFUCIANISM, supply_level=3,
        )
        for loc_id in ["长安", "洛阳", "建康"]:
            if loc_id not in state.locations:
                state.locations[loc_id] = LocationState(location_id=loc_id)

        # Give contributions
        state.jin_players[0].culture_contributions[CultureType.CONFUCIANISM] = 5
        state.jin_players[1].culture_contributions[CultureType.CONFUCIANISM] = 3
        state.north_player.culture_contributions = {
            CultureType.CONFUCIANISM: 2,
            CultureType.TAOISM: 0,
            CultureType.BUDDHISM: 0,
        }

        result = score_culture(state)
        conf = result["confucianism"]
        assert conf["markers"] == 3
        # Revealed VP positions 1-3: [1, 2, 4]
        # Top 3 contributors get: 4, 2, 1
        vp_awarded = conf["vp_awarded"]
        # jin_1 (contrib=5) should get the highest VP
        assert "jin_1" in vp_awarded

    def test_supply_track_values(self):
        """Verify supply track values from board_info.md."""
        assert CULTURE_SUPPLY_VP[1] == 1
        assert CULTURE_SUPPLY_VP[3] == 4
        assert CULTURE_SUPPLY_VP[5] == 11
        assert CULTURE_SUPPLY_VP[9] == 37


class TestSimaDistribution:
    """Tests for Sima VP distribution."""

    def test_base_coefficient_from_sima_vp(self):
        """Sima has 25 VP → base = 2."""
        state = make_scoring_state()
        result = score_sima_distribution(state)
        assert result["base_coeff"] == 2  # 25 // 10

    def test_prestige_ranking(self):
        """Jin1 prestige=5, Jin2=3, Jin3=2 → coefficients 3,2,1."""
        state = make_scoring_state()
        result = score_sima_distribution(state)
        coeffs = result["coefficients"]
        assert coeffs["jin_1"]["coeff"] >= 3  # 1st prestige + something for contrib
        assert coeffs["jin_2"]["coeff"] >= 2

    def test_low_prestige_transfers_to_first(self):
        """Jin3 has prestige=2 (<3) → coefficient goes to 1st place."""
        state = make_scoring_state()
        result = score_sima_distribution(state)
        coeffs = result["coefficients"]
        # jin_3 has prestige=2 (<3), so their rank coefficient goes to jin_1
        # jin_3 has contribution=2 (<3), same
        assert coeffs["jin_3"]["coeff"] == 0

    def test_no_sima_vp_no_distribution(self):
        """When Sima VP is 0, no VP is distributed."""
        state = make_scoring_state()
        state.sima.vp = 0
        result = score_sima_distribution(state)
        assert result["base_coeff"] == 0
        for pid, cdata in result["coefficients"].items():
            assert cdata["vp"] == 0


class TestFinalScoring:
    """Integration tests for complete final scoring."""

    def test_winner_determined(self):
        state = make_scoring_state()
        result = run_final_scoring(state)
        assert result.winner is not None
        assert len(result.steps) == 5

    def test_all_players_have_scores(self):
        state = make_scoring_state()
        result = run_final_scoring(state)
        assert len(result.player_scores) == 4
        for pid in ["north", "jin_1", "jin_2", "jin_3"]:
            assert pid in result.player_scores

    def test_tiebreaker_history_cards(self):
        """Players tied on VP → most history cards wins."""
        state = make_scoring_state()
        state.sima.vp = 0  # No Sima distribution to break the tie
        # Equal VP
        state.north_player.vp = 50
        for p in state.jin_players:
            p.vp = 50
        # North has more history cards
        from models.card import CardDef, Card
        from models.enums import CardType, CardCategory
        dummy_def = CardDef(
            card_id="d1", name="dummy", owner_faction="通用",
            cost=0, card_type=CardType.EVENT,
            card_category=CardCategory.EVENT_UTILITY, effect_text="",
        )
        state.north_player.history_area = [Card(definition=dummy_def)] * 3
        state.jin_players[0].history_area = [Card(definition=dummy_def)] * 1

        result = run_final_scoring(state)
        assert result.winner == "north"

    def test_tiebreaker_north_over_jin(self):
        """VP tie + same history cards → North beats Jin."""
        state = make_scoring_state()
        state.sima.vp = 0  # No Sima distribution to break the tie
        state.north_player.vp = 50
        for p in state.jin_players:
            p.vp = 50
        result = run_final_scoring(state)
        assert result.winner == "north"
