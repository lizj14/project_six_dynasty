"""Card CSV loader — parses card_design.csv into CardDef objects."""

import csv
import os
from pathlib import Path
from typing import Optional

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from models.enums import CardType, CardCategory, FactionType, MarkerType, CultureType
from models.card import CardDef, CardLibrary


# === Category mapping from CSV text to CardCategory ===

CATEGORY_MAP: dict[str, CardCategory] = {
    # Hero
    "角色-北方": CardCategory.HERO_NORTH,
    "角色-东晋": CardCategory.HERO_JIN,
    "角色牌-北方": CardCategory.HERO_NORTH,
    "角色牌-东晋": CardCategory.HERO_JIN,
    # Friend
    "幕僚-名将": CardCategory.FRIEND_MILITARY,
    "幕僚-谋主": CardCategory.FRIEND_ADVISOR,
    "幕僚-特殊": CardCategory.FRIEND_SPECIAL,
    "幕僚-艺术文化": CardCategory.FRIEND_CULTURE,
    # Strategy
    "策略-军备": CardCategory.STRATEGY_MILITARY,
    "策略-文化": CardCategory.STRATEGY_CULTURE,
    "策略-特殊": CardCategory.STRATEGY_SPECIAL,
    # Event
    "事件-艺术": CardCategory.EVENT_ART,
    "事件-文化": CardCategory.EVENT_CULTURE,
    "事件-军事": CardCategory.EVENT_MILITARY,
    "事件-VP": CardCategory.EVENT_VP,
    "事件-检索": CardCategory.EVENT_SEARCH,
    "事件-机制": CardCategory.EVENT_MECHANISM,
    "事件-功能": CardCategory.EVENT_UTILITY,
    "事件-权谋": CardCategory.EVENT_POWER,
    # Other
    "公共": CardCategory.PUBLIC,
    "目标": CardCategory.GOAL,
    "君主": CardCategory.EMPEROR,
    "初始": CardCategory.INITIAL,
    "强制事件": CardCategory.EVENT_MECHANISM,
}

CATEGORY_TO_CARD_TYPE: dict[CardCategory, CardType] = {
    CardCategory.HERO_JIN: CardType.HERO,
    CardCategory.HERO_NORTH: CardType.HERO,
    CardCategory.FRIEND_MILITARY: CardType.FRIEND,
    CardCategory.FRIEND_ADVISOR: CardType.FRIEND,
    CardCategory.FRIEND_SPECIAL: CardType.FRIEND,
    CardCategory.FRIEND_CULTURE: CardType.FRIEND,
    CardCategory.STRATEGY_MILITARY: CardType.STRATEGY,
    CardCategory.STRATEGY_CULTURE: CardType.STRATEGY,
    CardCategory.STRATEGY_SPECIAL: CardType.STRATEGY,
    CardCategory.EVENT_ART: CardType.EVENT,
    CardCategory.EVENT_CULTURE: CardType.EVENT,
    CardCategory.EVENT_MILITARY: CardType.EVENT,
    CardCategory.EVENT_VP: CardType.EVENT,
    CardCategory.EVENT_SEARCH: CardType.EVENT,
    CardCategory.EVENT_MECHANISM: CardType.MECHANISM,
    CardCategory.EVENT_UTILITY: CardType.EVENT,
    CardCategory.EVENT_POWER: CardType.EVENT,
    CardCategory.PUBLIC: CardType.PUBLIC,
    CardCategory.GOAL: CardType.GOAL,
    CardCategory.EMPEROR: CardType.EMPEROR,
    CardCategory.INITIAL: CardType.INITIAL,
    CardCategory.REFUGEE: CardType.REFUGEE,
}


def _parse_int(value: str, default: int = 0) -> int:
    """Parse an integer from a CSV cell, returning default on failure."""
    if not value or value.strip() == "" or value.strip() == "-":
        return default
    try:
        return int(float(value.strip()))
    except (ValueError, TypeError):
        return default


def _parse_category(raw: str) -> CardCategory:
    """Map Chinese category text to CardCategory enum."""
    raw = raw.strip()
    if raw in CATEGORY_MAP:
        return CATEGORY_MAP[raw]

    # Try to match by known prefixes
    for key, val in CATEGORY_MAP.items():
        if key in raw:
            return val

    # Fallback: try to guess from the text
    if "角色" in raw:
        return CardCategory.HERO_JIN if "东晋" in raw else CardCategory.HERO_NORTH
    if "幕僚" in raw:
        return CardCategory.FRIEND_SPECIAL
    if "策略" in raw:
        return CardCategory.STRATEGY_SPECIAL
    if "事件" in raw:
        return CardCategory.EVENT_UTILITY
    if "初始" in raw:
        return CardCategory.INITIAL
    if "目标" in raw:
        return CardCategory.GOAL
    if "君主" in raw:
        return CardCategory.EMPEROR
    if "公共" in raw:
        return CardCategory.PUBLIC

    return CardCategory.EVENT_UTILITY  # Absolute fallback


def _parse_faction_restriction(limit_jin: str, limit_north: str) -> Optional[str]:
    """Parse faction restriction from the two flag columns."""
    if limit_jin.strip() == "1":
        return "jin"
    if limit_north.strip() == "1":
        return "north"
    return None


def _parse_resource(resource_text: str) -> tuple[int, int]:
    """Parse resource field like '1军力' or '1军力2vp' -> (army, vp)."""
    army = 0
    vp = 0
    if not resource_text or resource_text.strip() in ("", "-"):
        return army, vp

    text = resource_text.strip()
    # Parse patterns like "2军力1vp", "1军力", "4vp", "3军力-1vp"
    import re

    # Military
    army_match = re.search(r'(-?\d+)\s*军力', text)
    if army_match:
        army = int(army_match.group(1))

    # VP
    vp_match = re.search(r'(-?\d+)\s*vp', text, re.IGNORECASE)
    if vp_match:
        vp = int(vp_match.group(1))

    return army, vp


def load_card_design_csv(csv_path: str) -> CardLibrary:
    """Load all cards from card_design.csv into a CardLibrary.

    The CSV has these relevant columns:
    归属, 卡牌名称, 费用, 类型, 卡牌分类, 效果, 资源, 史书vp,
    文化标记, 军事标记, 权谋标记, 内政标记, 限定东晋, 限定北方, 僭越,
    total, 儒学, 玄学, 佛学
    """
    cards: list[CardDef] = []
    # Track copies for unique IDs
    name_counts: dict[str, int] = {}

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=2):
            # Skip the summary/header rows
            name = row.get("卡牌名称", "").strip()
            if not name or name == "统计":
                continue

            owner = row.get("归属", "").strip()
            cost = _parse_int(row.get("费用", "0"))
            raw_type = row.get("类型", "").strip()
            raw_category = row.get("卡牌分类", "").strip()
            effect_text = row.get("效果", "").strip()
            resource_text = row.get("资源", "").strip()
            history_vp = _parse_int(row.get("史书vp", "0"))

            # Parse categories
            category = _parse_category(raw_category if raw_category else raw_type)
            if raw_type == "初始":
                category = CardCategory.INITIAL

            card_type = CATEGORY_TO_CARD_TYPE.get(category, CardType.EVENT)

            # Markers
            marker_culture = _parse_int(row.get("文化标记", "0"))
            marker_military = _parse_int(row.get("军事标记", "0"))
            marker_power = _parse_int(row.get("权谋标记", "0"))
            marker_affair = _parse_int(row.get("内政标记", "0"))

            # Faction restriction
            faction_restriction = _parse_faction_restriction(
                row.get("限定东晋", ""), row.get("限定北方", "")
            )

            # Usurp
            usurp_text = row.get("僭越", "").strip()
            is_usurp = usurp_text == "1"

            # Resource
            resource_army, resource_vp = _parse_resource(resource_text)

            # Culture
            culture_confucianism = _parse_int(row.get("儒学", "0"))
            culture_taoism = _parse_int(row.get("玄学", "0"))
            culture_buddhism = _parse_int(row.get("佛学", "0"))

            # Public
            is_public = raw_category == "公共" or (raw_type and "公共" in raw_type)

            # Generate unique ID: "{owner}_{name}_{copy}"
            key = f"{owner}_{name}"
            name_counts[key] = name_counts.get(key, 0) + 1
            card_id = f"{key}_{name_counts[key]}"

            # For friend cards
            is_friend = "幕僚" in raw_category or category.name.startswith("FRIEND")

            # For strategy cards — the resource text IS the resource option
            resource_option_army = resource_army
            resource_option_vp = resource_vp

            card_def = CardDef(
                card_id=card_id,
                name=name,
                owner_faction=owner,
                cost=cost,
                card_type=card_type,
                card_category=category,
                effect_text=effect_text,
                resource_vp=resource_vp,
                resource_military=resource_army,
                history_vp=history_vp,
                marker_military=marker_military,
                marker_culture=marker_culture,
                marker_affair=marker_affair,
                marker_power=marker_power,
                faction_restriction=faction_restriction,
                is_usurp=is_usurp,
                is_public=is_public,
                culture_confucianism=culture_confucianism,
                culture_taoism=culture_taoism,
                culture_buddhism=culture_buddhism,
                is_friend=is_friend,
                resource_option_army=resource_option_army,
                resource_option_vp=resource_option_vp,
            )
            cards.append(card_def)

    return CardLibrary(cards)


def load_goal_cards_csv(csv_path: str) -> list[CardDef]:
    """Load goal cards from card_goal.csv."""
    goals: list[CardDef] = []
    name_counts: dict[str, int] = {}

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("text_top", "").strip()
            if not name:
                continue

            effect_text = row.get("text_bottom", "").strip()

            key = f"goal_{name}"
            name_counts[key] = name_counts.get(key, 0) + 1
            card_id = f"{key}_{name_counts[key]}"

            card_def = CardDef(
                card_id=card_id,
                name=name,
                owner_faction="通用",
                cost=-1,
                card_type=CardType.GOAL,
                card_category=CardCategory.GOAL,
                effect_text=effect_text,
            )
            goals.append(card_def)
    return goals


def load_emperor_cards_csv(csv_path: str) -> list[CardDef]:
    """Load emperor cards from card_emperor.csv."""
    emperors: list[CardDef] = []
    name_counts: dict[str, int] = {}

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("text_top", "").strip()
            if not name:
                continue

            effect_text = row.get("text_bottom", "").strip()

            key = f"emperor_{name}"
            name_counts[key] = name_counts.get(key, 0) + 1
            card_id = f"{key}_{name_counts[key]}"

            # Parse initial prestige from effect_text: "初始威望：N"
            import re
            prestige = 5
            match = re.search(r'初始威望[：:](\d+)', effect_text)
            if match:
                prestige = int(match.group(1))

            card_def = CardDef(
                card_id=card_id,
                name=name,
                owner_faction="君主",
                cost=-1,
                card_type=CardType.EMPEROR,
                card_category=CardCategory.EMPEROR,
                effect_text=effect_text,
                initial_prestige=prestige,
            )
            emperors.append(card_def)
    return emperors


def load_all_cards(data_dir: str) -> CardLibrary:
    """Load all card CSVs from a data directory into a single CardLibrary."""
    all_cards: list[CardDef] = []

    # Main card design
    design_path = os.path.join(data_dir, "card_design.csv")
    if os.path.exists(design_path):
        lib = load_card_design_csv(design_path)
        all_cards.extend(lib.all_cards)

    # Goal cards
    goal_path = os.path.join(data_dir, "card_goal.csv")
    if os.path.exists(goal_path):
        all_cards.extend(load_goal_cards_csv(goal_path))

    # Emperor cards
    emperor_path = os.path.join(data_dir, "card_emperor.csv")
    if os.path.exists(emperor_path):
        all_cards.extend(load_emperor_cards_csv(emperor_path))

    return CardLibrary(all_cards)
