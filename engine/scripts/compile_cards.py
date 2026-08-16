"""Dev-time card compiler: CSV → parsed AST → cards_compiled.json.

Outputs three lists:
  - action_cards: hero, event, strategy, friend, mechanism, initial, public, refugee
  - goal_cards:   goal cards with their own schema
  - emperor_cards: emperor cards
"""

import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cards.loader import load_card_design_csv, load_goal_cards_csv, load_emperor_cards_csv
from cards.effect_parser import EffectParser
from cards.effect_ast import CardEffect, AbilityBlock, EffectStep, Condition


def compile_version(version_dir: str):
    cards_dir = os.path.join(version_dir, "cards")
    output_path = os.path.join(cards_dir, "cards_compiled.json")

    print(f"Compiling cards for {version_dir}...")
    parser = EffectParser()

    action_cards = []
    hero_cards = []
    goal_cards = []
    emperor_cards = []

    # Load from CSV
    design_path = os.path.join(cards_dir, "card_design.csv")
    if os.path.exists(design_path):
        lib = load_card_design_csv(design_path)
        for cdef in lib.all_cards:
            ct = cdef.card_type.value

            if ct == "goal":
                goal_cards.append(_serialize_goal(cdef))
                continue
            if ct == "emperor":
                emperor_cards.append(_serialize_emperor(cdef))
                continue

            # Parse effect text
            parsed = None
            if cdef.effect_text and cdef.effect_text.strip() not in ('', '-'):
                try:
                    parsed = parser.parse(cdef.name, cdef.effect_text,
                                          is_usurp=cdef.is_usurp,
                                          faction_restriction=cdef.faction_restriction)
                    object.__setattr__(cdef, 'parsed_effect', parsed)
                except Exception as e:
                    print(f"  ERROR parsing {cdef.name}: {e}")
                    raise

            if ct == "hero":
                hero_cards.append(_serialize_hero(cdef))
            else:
                action_cards.append(_serialize_action(cdef))

    # Load goal CSV
    goal_path = os.path.join(cards_dir, "card_goal.csv")
    if os.path.exists(goal_path):
        for g in load_goal_cards_csv(goal_path):
            goal_cards.append(_serialize_goal(g))

    # Load emperor CSV
    emperor_path = os.path.join(cards_dir, "card_emperor.csv")
    if os.path.exists(emperor_path):
        for e in load_emperor_cards_csv(emperor_path):
            emperor_cards.append(_serialize_emperor(e))

    output = {
        "hero_cards": hero_cards,
        "action_cards": action_cards,
        "goal_cards": goal_cards,
        "emperor_cards": emperor_cards,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = len(hero_cards) + len(action_cards) + len(goal_cards) + len(emperor_cards)
    parsed_count = sum(1 for c in action_cards if c.get("parsed_effect"))
    size = os.path.getsize(output_path)
    print(f"  {total} cards ({len(hero_cards)} hero + {len(action_cards)} action + {len(goal_cards)} goal + {len(emperor_cards)} emperor)")
    print(f"  {parsed_count} parsed, {size} bytes → {output_path}")


# ======== Serializers ========

def _serialize_action(cdef) -> dict:
    """Serialize an action card with only relevant fields."""
    from cards.effect_ast import CardEffect as CE
    pe = cdef.parsed_effect
    d = {
        "card_id": cdef.card_id,
        "name": cdef.name,
        "cost": cdef.cost,
        "card_type": cdef.card_type.value,
        "card_category": cdef.card_category.value,
        "owner_faction": cdef.owner_faction,
    }
    text = cdef.effect_text
    if text:
        # 把阵营限定拼进 text，让只读 text 的玩家/agent 能感知「仅限东晋/北方」
        fr = cdef.faction_restriction
        if fr == "jin":
            text = "【仅限东晋】" + text
        elif fr == "north":
            text = "【仅限北方】" + text
        d["text"] = text

    if pe:
        d["parsed_effect"] = {
            "is_usurp": pe.is_usurp,
            "faction_restriction": pe.faction_restriction,
            "restrictions": pe.restrictions,
            "blocks": [_serialize_block(b) for b in pe.blocks],
        }
        if pe.play_condition:
            d["parsed_effect"]["play_condition"] = _serialize_condition(pe.play_condition)

    # Resources (stored in parsed_effect blocks as resource_option)
    if cdef.history_vp:
        d["history_vp"] = cdef.history_vp

    markers = {}
    if cdef.marker_military: markers["military"] = cdef.marker_military
    if cdef.marker_culture: markers["culture"] = cdef.marker_culture
    if cdef.marker_affair: markers["affair"] = cdef.marker_affair
    if cdef.marker_power: markers["power"] = cdef.marker_power
    if markers: d["markers"] = markers

    culture = {}
    if cdef.culture_confucianism: culture["confucianism"] = cdef.culture_confucianism
    if cdef.culture_taoism: culture["taoism"] = cdef.culture_taoism
    if cdef.culture_buddhism: culture["buddhism"] = cdef.culture_buddhism
    if culture: d["culture_tags"] = culture

    if cdef.faction_restriction:
        d["faction_restriction"] = cdef.faction_restriction
    if cdef.is_usurp:
        d["is_usurp"] = True
    if cdef.is_public:
        d["is_public"] = True
    if cdef.start_order:
        d["start_order"] = cdef.start_order
    # Resource option (strategy cards gain this when not selected as court action)
    if cdef.resource_option_army or cdef.resource_option_vp:
        d["resource_option"] = {"army": cdef.resource_option_army, "vp": cdef.resource_option_vp}

    return d


def _serialize_hero(cdef) -> dict:
    """Serialize a hero card."""
    d = {
        "card_id": cdef.card_id,
        "name": cdef.name,
        "card_category": cdef.card_category.value,
        "owner_faction": cdef.owner_faction,
        "start_order": cdef.start_order,
        "initial_contribution": getattr(cdef, 'initial_contribution', 0),
        "initial_prestige": getattr(cdef, 'initial_prestige', 0),
        "initial_order": getattr(cdef, 'initial_order', 1),
        "staff_limit": getattr(cdef, 'staff_limit', 3),
    }
    if cdef.effect_text:
        d["text"] = cdef.effect_text
    # Markers (non-zero only)
    hero_markers = {}
    if cdef.marker_military: hero_markers["military"] = cdef.marker_military
    if cdef.marker_culture: hero_markers["culture"] = cdef.marker_culture
    if cdef.marker_affair: hero_markers["affair"] = cdef.marker_affair
    if cdef.marker_power: hero_markers["power"] = cdef.marker_power
    if hero_markers:
        d["markers"] = hero_markers
    if cdef.parsed_effect:
        d["parsed_effect"] = {
            "blocks": [_serialize_block(b) for b in cdef.parsed_effect.blocks],
            "restrictions": cdef.parsed_effect.restrictions,
        }
    return d


def _serialize_goal(cdef) -> dict:
    """Serialize a goal card."""
    return {
        "card_id": cdef.card_id,
        "name": cdef.name,
        "simple_vp": cdef.goal_simple_vp,
        "full_vp": cdef.goal_full_vp,
        "simple_condition": cdef.goal_simple_condition,
        "full_condition": cdef.goal_full_condition,
    }


def _serialize_emperor(cdef) -> dict:
    """Serialize an emperor card."""
    return {
        "card_id": cdef.card_id,
        "name": cdef.name,
        "initial_prestige": cdef.initial_prestige,
        "emperor_tasks": cdef.emperor_tasks,
        "effect_text": cdef.effect_text,
    }


def _serialize_block(block) -> dict:
    d = {
        "ability_type": block.ability_type,
        "steps": [_serialize_step(s) for s in block.steps],
    }
    if block.trigger:
        d["trigger"] = block.trigger
    if block.trigger_scope and block.trigger_scope != "self":
        d["trigger_scope"] = block.trigger_scope
    if block.trigger_filter:
        d["trigger_filter"] = block.trigger_filter
    if block.costs:
        d["costs"] = [{"cost_type": c.cost_type, "params": c.params} for c in block.costs]
    if block.choice_options:
        serialized = []
        for opt in block.choice_options:
            if opt and isinstance(opt[0], dict):
                serialized.append(opt)  # Already a dict, use as-is
            else:
                serialized.append([_serialize_step(s) for s in opt])
        d["choice_options"] = serialized
    if block.resource_option:
        d["resource_option"] = block.resource_option
    if block.modifier:
        d["modifier"] = block.modifier
    return d


def _serialize_step(step) -> dict:
    # Strip default values from params
    params = {}
    for k, v in step.params.items():
        if k == "sub_effect":
            continue
        if k == "variable" and v is False:
            continue  # default
        if k == "count" and v == 1:
            continue  # default
        if k == "from_hand" and v is True:
            continue  # default when true
        if v is None or v == "" or v == []:
            continue
        if isinstance(v, bool):
            params[k] = v
        else:
            params[k] = v
    # Only include params if non-empty
    d = {"effect_type": step.effect_type}
    if params:
        d["params"] = params
    if "sub_effects" in step.params and step.params["sub_effects"]:
        d["sub_effects"] = step.params["sub_effects"]
    elif "sub_effect" in step.params and step.params["sub_effect"]:
        d["sub_effect"] = step.params["sub_effect"]
    if step.condition:
        d["condition"] = _serialize_condition(step.condition)
    return d


def _serialize_condition(cond) -> dict:
    if cond is None:
        return None
    return {"condition_type": cond.condition_type, "params": cond.params}


if __name__ == "__main__":
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    version_dir = os.path.join(project_root, "versions", "v1.0")
    compile_version(version_dir)
