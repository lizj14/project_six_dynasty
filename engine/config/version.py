"""Version loader — no CSV parsing, no regex on card text at runtime."""

import os
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Version:
    """Complete configuration for one game version. Loads from pre-compiled JSON."""
    name: str
    description: str = ""
    parameters: dict = field(default_factory=dict)
    features: dict = field(default_factory=dict)
    card_library: Optional["CardLibrary"] = None
    map_adjacencies: list = field(default_factory=list)
    _root_dir: str = ""

    # ======== Public API ========

    @classmethod
    def load(cls, version_name: str) -> "Version":
        root = cls._find_root(version_name)
        v = cls(name=version_name, _root_dir=root)
        v._load_toml(os.path.join(root, "rules.toml"))
        v._load_cards(os.path.join(root, "cards"))
        v._load_map(os.path.join(root, "map"))
        return v

    @property
    def cards(self):
        return self.card_library

    @property
    def map(self):
        return self.map_adjacencies

    def has(self, feature: str) -> bool:
        return bool(self.features.get(feature, False))

    def get(self, key: str, default=None):
        return self.parameters.get(key, default)

    # ======== Internal ========

    @classmethod
    def _find_root(cls, name: str) -> str:
        current = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current))
        vdir = os.path.join(project_root, "versions", name)
        if not os.path.isdir(vdir):
            raise FileNotFoundError(f"Version '{name}' not found at {vdir}")
        return vdir

    def _load_toml(self, path: str):
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        with open(path, "rb") as f:
            data = tomllib.load(f)
        self.description = data.get("version", {}).get("description", "")
        self.parameters = data.get("parameters", {})
        self.features = data.get("features", {})

    def _load_cards(self, cards_dir: str):
        """Load from cards_compiled.json (3-list format)."""
        from models.card import CardDef, CardLibrary
        from models.enums import CardType, CardCategory
        from cards.effect_ast import CardEffect, AbilityBlock, EffectStep, Condition

        path = os.path.join(cards_dir, "cards_compiled.json")
        if not os.path.exists(path):
            raise FileNotFoundError(f"{path} not found. Run: python scripts/compile_cards.py")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        all_cards = []

        # === Hero cards ===
        for d in data.get("hero_cards", []):
            pe = d.get("parsed_effect")
            parsed = None
            if pe:
                blocks = [_dict_to_block(bd) for bd in pe.get("blocks", [])]
                parsed = CardEffect(
                    card_name=d["name"], raw_text=d.get("effect_text", ""),
                    blocks=blocks, restrictions=pe.get("restrictions", []),
                )
            hero_markers = d.get("markers", {})
            all_cards.append(CardDef(
                card_id=d["card_id"], name=d["name"],
                owner_faction=d["owner_faction"], cost=-1,
                card_type=CardType.HERO,
                card_category=CardCategory(d.get("card_category", "hero_jin")),
                effect_text=d.get("text", ""), parsed_effect=parsed,
                start_order=d.get("start_order", 0),
                initial_contribution=d.get("initial_contribution", 0),
                initial_prestige=d.get("initial_prestige", 0),
                initial_order=d.get("initial_order", 1),
                staff_limit=d.get("staff_limit", 3),
                marker_military=hero_markers.get("military", 0),
                marker_culture=hero_markers.get("culture", 0),
                marker_affair=hero_markers.get("affair", 0),
                marker_power=hero_markers.get("power", 0),
            ))

        # === Action cards ===
        for d in data.get("action_cards", []):
            markers = d.get("markers", {})
            culture = d.get("culture_tags", {})
            ro = d.get("resource_option", {})

            parsed = None
            pe = d.get("parsed_effect")
            if pe:
                blocks = [_dict_to_block(bd) for bd in pe.get("blocks", [])]
                play_cond = _dict_to_condition(pe.get("play_condition"))
                parsed = CardEffect(
                    card_name=d["name"], raw_text=d.get("text", ""),
                    blocks=blocks, is_usurp=pe.get("is_usurp", False),
                    faction_restriction=pe.get("faction_restriction"),
                    play_condition=play_cond,
                    restrictions=pe.get("restrictions", []),
                )

            all_cards.append(CardDef(
                card_id=d["card_id"], name=d["name"],
                owner_faction=d["owner_faction"], cost=d["cost"],
                card_type=CardType(d["card_type"]),
                card_category=CardCategory(d.get("card_category", "event_utility")),
                effect_text=d.get("text", ""), parsed_effect=parsed,
                resource_vp=d.get("resource_vp", 0), resource_military=d.get("resource_military", 0),
                history_vp=d.get("history_vp", 0),
                marker_military=markers.get("military", 0),
                marker_culture=markers.get("culture", 0),
                marker_affair=markers.get("affair", 0),
                marker_power=markers.get("power", 0),
                faction_restriction=d.get("faction_restriction"),
                is_usurp=d.get("is_usurp", False),
                is_public=d.get("is_public", False),
                culture_confucianism=culture.get("confucianism", 0),
                culture_taoism=culture.get("taoism", 0),
                culture_buddhism=culture.get("buddhism", 0),
                start_order=d.get("start_order", 0),
                is_friend=d.get("is_friend", False),
                resource_option_army=ro.get("army", 0),
                resource_option_vp=ro.get("vp", 0),
            ))

        # === Goal cards ===
        for d in data.get("goal_cards", []):
            all_cards.append(CardDef(
                card_id=d["card_id"], name=d["name"],
                owner_faction="通用", cost=-1,
                card_type=CardType.GOAL, card_category=CardCategory.GOAL,
                effect_text=f"{d.get('simple_condition','')} / {d.get('full_condition','')}",
                goal_simple_vp=d.get("simple_vp", 0), goal_full_vp=d.get("full_vp", 0),
                goal_simple_condition=d.get("simple_condition", ""),
                goal_full_condition=d.get("full_condition", ""),
            ))

        # === Emperor cards ===
        for d in data.get("emperor_cards", []):
            all_cards.append(CardDef(
                card_id=d["card_id"], name=d["name"],
                owner_faction="君主", cost=-1,
                card_type=CardType.EMPEROR, card_category=CardCategory.EMPEROR,
                effect_text=d.get("effect_text", ""),
                initial_prestige=d.get("initial_prestige", 0),
                emperor_tasks=d.get("emperor_tasks", []),
            ))

        self.card_library = CardLibrary(all_cards)

    def _load_map(self, map_dir: str):
        try:
            import yaml
        except ImportError:
            return
        path = os.path.join(map_dir, "map_adjacency.yaml")
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        from models.location import AdjacencyDef
        from models.enums import TerrainType
        for entry in data.get("adjacencies", []):
            if len(entry) >= 3:
                terrain = TerrainType.DIFFICULT if entry[2] == "difficult" else TerrainType.SIMPLE
                self.map_adjacencies.append(AdjacencyDef(entry[0], entry[1], terrain))

    def __repr__(self) -> str:
        on = [k for k, v in self.features.items() if v]
        return f"Version({self.name}, features={on})"


# ======== AST reconstruction helpers (module-level, not class) ========

def _dict_to_block(bd: dict) -> "AbilityBlock":
    from cards.effect_ast import AbilityBlock
    steps = [_dict_to_step(s) for s in bd.get("steps", [])]
    choices = [[_dict_to_step(s) for s in opt] for opt in bd.get("choice_options", [])]
    costs = []
    for cd in bd.get("costs", []):
        from cards.effect_ast import Cost
        costs.append(Cost(cost_type=cd["cost_type"], params=cd.get("params", {})))

    return AbilityBlock(
        ability_type=bd["ability_type"], trigger=bd.get("trigger"),
        trigger_scope=bd.get("trigger_scope", "self"),
        trigger_filter=bd.get("trigger_filter"),
        condition=_dict_to_condition(bd.get("condition")),
        costs=costs, steps=steps, choice_options=choices,
        resource_option=bd.get("resource_option"),
        modifier=bd.get("modifier"),
    )


def _dict_to_step(sd: dict) -> "EffectStep":
    from cards.effect_ast import EffectStep
    params = dict(sd.get("params", {}))
    if sd.get("sub_effect"):
        params["sub_effect"] = sd["sub_effect"]
    if sd.get("sub_effects"):
        params["sub_effects"] = sd["sub_effects"]
    # Compatibility: step-level fields that should be in params
    for key in ("filter", "choice_options", "target"):
        if key in sd and sd[key] is not None:
            params[key] = sd[key]
    return EffectStep(
        effect_type=sd["effect_type"], params=params,
        condition=_dict_to_condition(sd.get("condition")),
        source_text=sd.get("source_text", ""),
    )


def _dict_to_condition(cd: dict) -> Optional["Condition"]:
    if cd is None:
        return None
    from cards.effect_ast import Condition
    return Condition(condition_type=cd.get("condition_type", ""), params=cd.get("params", {}))
