"""Viewport utility functions — card/player/action summaries.

All functions return plain dicts/lists/strings — never expose internal Card
or GameState references.  These are the shared building blocks used by
LiveViewport, SnapshotViewport, and the CLI query interface.
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from models.card import Card, CardDef
    from models.player import PlayerState
    from models.location import LocationState
    from models.enums import CardType, CultureType
    from engine.actions.base import GameAction


# ================================================================
# Card summaries (never expose Card objects)
# ================================================================

def card_to_summary(card: "Card") -> dict:
    """Convert a Card instance to a safe, serialisable summary dict.

    Returns a plain dict with no internal references — safe to hand to
    agents, serialize to JSON, or cache in snapshots.
    """
    d = card.definition
    return {
        "name": card.name,
        "card_id": d.card_id,
        "cost": d.cost,
        "card_type": d.card_type.value,
        "card_category": d.card_category.value if d.card_category else "",
        "effect_text": d.effect_text,
        "effect_summary": card_effect_summary(d),
        "markers": {
            "军事": d.marker_military,
            "文化": d.marker_culture,
            "内政": d.marker_affair,
            "权谋": d.marker_power,
        },
        "is_friend": card.is_friend,
        "is_strategy": card.is_strategy,
        "is_event": card.is_event,
        "owner_faction": d.owner_faction,
        "owner_player_id": card.owner_player_id,
        "history_vp": d.history_vp,
        "resource_option_army": d.resource_option_army,
        "resource_option_vp": d.resource_option_vp,
        "culture_tags": {
            k.value: v for k, v in d.culture_tags.items()
        } if d.culture_tags else {},
    }


def card_name_list(cards: list) -> dict:
    """Return a lightweight {count, names} dict from a list of Card/CardDef objects.

    Use this for zone-level queries (my.hand, court.north, etc.) so the
    default output is readable.  Callers that need full detail can use
    card_to_summary() per card or request the .detail sub-query.
    """
    names = []
    for c in cards:
        if hasattr(c, 'name'):
            names.append(c.name)
        elif hasattr(c, 'definition') and hasattr(c.definition, 'name'):
            names.append(c.definition.name)
        else:
            names.append(str(c))
    return {"count": len(cards), "names": names}


def carddef_to_summary(card_def: "CardDef") -> dict:
    """Convert a CardDef to a summary dict (no Card instance needed)."""
    return {
        "name": card_def.name,
        "card_id": card_def.card_id,
        "cost": card_def.cost,
        "card_type": card_def.card_type.value,
        "card_category": card_def.card_category.value if card_def.card_category else "",
        "effect_text": card_def.effect_text,
        "effect_summary": card_effect_summary(card_def),
        "markers": {
            "军事": card_def.marker_military,
            "文化": card_def.marker_culture,
            "内政": card_def.marker_affair,
            "权谋": card_def.marker_power,
        },
        "is_friend": card_def.is_friend or card_def.card_type.value == "friend",
        "owner_faction": card_def.owner_faction,
        "history_vp": card_def.history_vp,
        "resource_option_army": card_def.resource_option_army,
        "resource_option_vp": card_def.resource_option_vp,
    }


def card_effect_summary(definition: "CardDef") -> str:
    """Extract a one-line effect summary from a card's parsed effect.

    Extracted from HumanPlayer._brief_effect().  Lives here so it can be
    shared by LiveViewport, SnapshotViewport, and HumanPlayer itself.
    """
    parsed = definition.parsed_effect
    if not parsed:
        return ""

    from cards.effect_ast import AbilityType, EffectType

    parts = []
    for block in parsed.blocks:
        for step in block.steps:
            et = step.effect_type or ""
            p = step.params
            if et == EffectType.GAIN_MILITARY:
                amount = p.get("amount", "?")
                parts.append(f"+{amount}军力")
            elif et == EffectType.GAIN_VP:
                amount = p.get("amount", "?")
                parts.append(f"+{amount}VP")
            elif et == EffectType.LOSE_MILITARY:
                amount = p.get("amount", "?")
                parts.append(f"-{amount}军力")
            elif et == EffectType.LOSE_VP:
                amount = p.get("amount", "?")
                parts.append(f"-{amount}VP")
            elif et == EffectType.PAY_MILITARY:
                amount = p.get("amount", "?")
                parts.append(f"支付{amount}军力")
            elif et == EffectType.DRAW_CARDS:
                amount = p.get("amount", 1)
                parts.append(f"摸{amount}牌" if amount > 1 else "摸牌")
            elif et == EffectType.DISCARD_CARDS:
                parts.append("弃牌")
            elif et == EffectType.MARCH:
                parts.append("进军")
            elif et == EffectType.OCCUPY:
                parts.append("占据")
            elif et == EffectType.CONVERT:
                parts.append("转化")
            elif et == EffectType.FORTIFY:
                parts.append("加固")
            elif et == EffectType.DRAFT:
                parts.append("征发")
            elif et == EffectType.ARCHIVE_THIS:
                parts.append("存档此牌")
            elif et == EffectType.ARCHIVE_CARD:
                parts.append("存档")
            elif et == EffectType.ARCHIVE_COURT:
                parts.append("存档朝堂牌")
            elif et == EffectType.SEARCH:
                parts.append("检索")
            elif et == EffectType.SPREAD_CULTURE:
                c = p.get("culture", "")
                culture_map = {"confucianism": "儒学", "taoism": "玄学", "buddhism": "佛学"}
                culture = culture_map.get(c, c)
                parts.append(f"传播{culture}" if culture else "传播文化")
            elif et == EffectType.RAISE_ORDER:
                amount = p.get("amount", "?")
                parts.append(f"+{amount}顺位")
            elif et == EffectType.LOWER_ORDER:
                amount = p.get("amount", "?")
                parts.append(f"-{amount}顺位")
            elif et == EffectType.RAISE_PRESTIGE:
                amount = p.get("amount", "?")
                parts.append(f"+{amount}威望")
            elif et == EffectType.LOWER_PRESTIGE:
                amount = p.get("amount", "?")
                parts.append(f"-{amount}威望")
            elif et == EffectType.RAISE_CONTRIBUTION:
                amount = p.get("amount", "?")
                parts.append(f"+{amount}功绩")
            elif et == EffectType.LOWER_CONTRIBUTION:
                amount = p.get("amount", "?")
                parts.append(f"-{amount}功绩")
            elif et == EffectType.PLACE_ARMY:
                parts.append("放置部队")
            elif et == EffectType.REMOVE_ARMY:
                parts.append("移除部队")
            elif et == EffectType.GET_EXPEDITION:
                parts.append("远征标记")
            elif et == EffectType.ADD_REFUGEE:
                parts.append("增加流民")
            elif et == EffectType.SUPPLY_COURT:
                parts.append("补充朝堂")
            elif et == EffectType.PLAY_CARD:
                parts.append("打出卡牌")
            elif et == EffectType.RAISE_CULTURE_LEVEL:
                parts.append("提升文化")
            elif et == EffectType.REMOVE_FROM_GAME:
                parts.append("移出游戏")
            elif et == EffectType.CHOOSE:
                parts.append("[选择效果]")
            if len(parts) >= 3:
                break
        if len(parts) >= 3:
            break

    # Fallback: show ability_type if no steps matched
    if not parts:
        for block in parsed.blocks:
            ab = block.ability_type or ""
            if ab == AbilityType.ACTIVE:
                parts.append("[主动]")
            elif ab == AbilityType.PASSIVE:
                trigger = block.trigger or ""
                parts.append(f"[被动:{trigger}]" if trigger else "[被动]")
            elif ab == AbilityType.ENTER:
                parts.append("[登场]")
            elif ab == AbilityType.FORCED:
                parts.append("[强制]")
            elif ab == AbilityType.STRATEGY_ACTION:
                parts.append("[牌组行动]")
            if len(parts) >= 2:
                break

    return " | ".join(parts[:3])


# ================================================================
# Player summaries (public vs private)
# ================================================================

def public_player_summary(player: "PlayerState", state=None) -> dict:
    """Extract only publicly-visible fields from a PlayerState.

    All players can see: faction, hero, staff/history counts, VP, military,
    prestige/contribution/order (Jin), army counts, marker counts, expedition
    marker, hand COUNT (not contents).

    Marker counts use get_marker_total() (dynamic sum from hero + staff +
    history + court cards) when state is provided; falls back to static
    counts otherwise.
    """
    from models.enums import MarkerType

    faction_val = player.faction.value if hasattr(player.faction, 'value') else str(player.faction)

    # Compute dynamic marker totals when state is available
    if state:
        marker_mil = player.get_marker_total(MarkerType.MILITARY, state)
        marker_cul = player.get_marker_total(MarkerType.CULTURE, state)
        marker_aff = player.get_marker_total(MarkerType.AFFAIR, state)
        marker_pow = player.get_marker_total(MarkerType.POWER, state)
    else:
        marker_mil = player.marker_military
        marker_cul = player.marker_culture
        marker_aff = player.marker_affair
        marker_pow = player.marker_power

    summary = {
        "player_id": player.player_id,
        "faction": faction_val,
        "hero": card_to_summary(player.hero) if player.hero else None,
        "staff_count": len(player.staff_area),
        "staff_names": [c.name for c in player.staff_area],
        "history_count": len(player.history_area),
        "history_names": [c.name for c in player.history_area],
        "military": player.military,
        "vp": player.vp,
        "army_placed_count": player.army_placed_count,
        "army_reserve_count": player.army_reserve_count,
        "army_reserve_revealed_vp": player.army_reserve_revealed_vp,
        "army_reserve_revealed_military": player.army_reserve_revealed_military,
        "hand_count": len(player.hand),
        "marker_military": marker_mil,
        "marker_culture": marker_cul,
        "marker_affair": marker_aff,
        "marker_power": marker_pow,
        "has_expedition_marker": player.has_expedition_marker,
        "game_end_marker": player.game_end_marker,
        "start_order": player.start_order,
    }

    # Jin-specific public fields
    if faction_val == "jin":
        summary["prestige"] = player.prestige
        summary["contribution"] = player.contribution
        summary["order"] = player.order
        summary["order_seq"] = player.order_seq

    # Culture contributions (public track)
    summary["culture_contributions"] = {
        k.value if hasattr(k, 'value') else str(k): v
        for k, v in player.culture_contributions.items()
    }

    return summary


def private_player_summary(player: "PlayerState") -> dict:
    """Extract private fields visible only to the owning player.

    Card zones return {count, names} by default for readability.
    Use get_my_hand() / get_my_staff() / get_my_history() on the viewport
    for full card details, or query my.hand.detail / my.hand.<N> via CLI.
    """
    return {
        "hand": card_name_list(player.hand),
        "staff": card_name_list(player.staff_area),
        "history": card_name_list(player.history_area),
        "hero": card_to_summary(player.hero) if player.hero else None,
        "can_take_hand_action": player.can_take_hand_action(),
        "can_take_court_action": player.can_take_court_action(),
        "extra_hand_actions": player.extra_hand_actions,
        "extra_court_actions": player.extra_court_actions,
        "extra_hand_action_filter": player.extra_hand_action_filter,
        "has_drawn_quick": player.has_drawn_quick,
        "has_fortified_quick": player.has_fortified_quick,
        "has_taken_hand_action": player.has_taken_hand_action,
        "has_taken_court_action": player.has_taken_court_action,
        "hand_action_taken_count": player.hand_action_taken_count,
        "court_action_taken_count": player.court_action_taken_count,
        "activated_card_ids": list(player.activated_card_ids),
        "staff_free_slots": player.staff_free_slots,
        "staff_limit": player.staff_limit,
        "hand_limit": player.hand_limit,
    }


def full_player_summary(player: "PlayerState", state=None) -> dict:
    """Combined public + private summary (for the owning player's view)."""
    pub = public_player_summary(player, state)
    priv = private_player_summary(player)
    pub.update(priv)
    return pub


# ================================================================
# Location summaries
# ================================================================

def location_summary(loc: "LocationState", state=None) -> dict:
    """Convert a LocationState to a safe summary dict."""
    data = {
        "controller": loc.controller.value if hasattr(loc.controller, 'value') else str(loc.controller),
        "is_fortified": loc.is_fortified,
        "region": _get_location_region(loc.location_id),
    }
    # Capital marker
    if state is not None:
        sima = getattr(state, 'sima', None)
        cap_loc = getattr(sima, 'capital_location', '建康') if sima else '建康'
        data["is_capital"] = (loc.location_id == cap_loc)
    else:
        data["is_capital"] = False

    return data


def _get_location_region(location_id: str) -> str:
    """Get the primary region name for a location."""
    region_map = {
        "张掖": "西凉", "姑臧": "西凉", "金城": "西凉",
        "安定": "关中", "天水": "关中", "长安": "关中",
        "汉中": "巴蜀", "巴郡": "巴蜀", "蜀郡": "巴蜀",
        "襄阳": "荆襄", "南郡": "荆襄", "巴东": "荆襄",
        "武昌": "荆襄", "宛城": "荆襄", "上洛": "荆襄",
        "浔阳": "江南", "建康": "江南", "京口": "江南",
        "吴": "江南", "会稽": "江南",
        "弘农": "关中", "洛阳": "中原",
        "雍丘": "中原", "彭城": "中原", "谯": "中原", "东平": "中原",
        "平阳": "山西", "太原": "山西", "上党": "山西",
        "济南": "山东", "广固": "山东", "琅琊": "山东",
        "寿春": "淮南", "合肥": "淮南", "广陵": "淮南",
        "中山": "河北", "襄国": "河北", "邺城": "河北", "信都": "河北",
        "蓟城": "幽燕", "龙城": "幽燕",
        "盛乐": "关外", "平城": "关外",
    }
    return region_map.get(location_id, "")


def region_summary(region_name: str, rs, state_locations: dict, regions_data: dict = None) -> dict:
    """Build a region summary with culture and control info.

    Culture markers are per-region (§board_info: 文化空位 per region).
    We collect culture markers from locations in this region.
    """
    # Collect all locations in this region
    region_locs = {}
    for loc_id, loc in state_locations.items():
        if hasattr(loc, 'location_id'):
            lid = loc.location_id
        else:
            lid = loc_id
        rname = _get_location_region(lid)
        if rname == region_name:
            region_locs[lid] = {
                "controller": loc.controller.value if hasattr(loc.controller, 'value') else str(loc.controller),
                "is_fortified": getattr(loc, 'is_fortified', False),
            }
    # Collect culture markers — per-region via RegionState.culture_slots
    culture_markers = []
    if rs and getattr(rs, 'culture_slots', None):
        for cs in rs.culture_slots:
            if cs.culture is not None:
                ct_str = cs.culture.value if hasattr(cs.culture, 'value') else str(cs.culture)
                culture_markers.append({"type": ct_str, "locked": cs.locked})
    else:
        # Fallback for regions without culture_slots (shouldn't happen)
        pass

    # Determine control marker — rs is the RegionState passed directly.
    # (regions_data is keyed by Region enum, not string name, so looking up
    # by region_name would always miss. Use rs directly instead.)
    control = None
    if rs:
        cm = getattr(rs, 'control_marker', None)
        if cm and hasattr(cm, 'value'):
            control = cm.value
        elif cm:
            control = str(cm)

    return {
        "name": region_name,
        "control_marker": control,
        "locations": list(region_locs.keys()),
        "location_details": region_locs,
        "culture_markers": culture_markers,
        "culture_slot_count": len(culture_markers),
    }


# ================================================================
# Action summary (for viewport available_actions display)
# ================================================================

def action_to_summary(action: "GameAction", player_id: str,
                      hand_cards: list = None,
                      court_cards: list = None,
                      public_cards: list = None,
                      player_staff: list = None,
                      player_hero: Any = None) -> dict:
    """Convert a GameAction to a human-readable summary dict.

    This is a simplified, self-contained version of what HumanPlayer's
    _describe_action_preview() does.  It takes pre-fetched card lists
    so it does not need a live GameState reference.
    """
    atype = getattr(action, 'action_type', '?')
    base = {"action_type": atype}

    # --- Quick actions ---
    if atype == "march":
        base["description"] = f"进军 → {getattr(action, 'target_location', '?')}"
        base["target"] = getattr(action, 'target_location', '')
        base["cost"] = "3+军力"
    elif atype == "occupy":
        base["description"] = f"占据 → {getattr(action, 'target_location', '?')}"
        base["target"] = getattr(action, 'target_location', '')
        base["cost"] = "1军力"
    elif atype == "fortify":
        base["description"] = f"加固 → {getattr(action, 'target_location', '?')}"
        base["target"] = getattr(action, 'target_location', '')
        base["cost"] = "1军力"
    elif atype == "draw":
        base["description"] = "摸牌 (快速行动)"
        base["cost"] = "2军力"
    elif atype == "recruit":
        idx = getattr(action, 'card_to_discard_index', -1)
        card_name = "?"
        if hand_cards and 0 <= idx < len(hand_cards):
            card_name = hand_cards[idx].name if hasattr(hand_cards[idx], 'name') else str(hand_cards[idx])
        base["description"] = f"征募: 弃「{card_name}」换1军力"
        base["cost"] = "弃1手牌"
        base["card_index"] = idx

    # --- Card actions ---
    elif atype == "play_card":
        idx = getattr(action, 'card_index', -1)
        payment = list(getattr(action, 'payment_indices', []))
        if hand_cards and 0 <= idx < len(hand_cards):
            card = hand_cards[idx]
            base["description"] = f"打出「{card.name}」({_card_type_label_str(card.card_type)}, 费用{card.cost})"
            base["card_name"] = card.name
            base["card_index"] = idx
            base["card_cost"] = card.cost
            base["payment_indices"] = payment
            base["effect_summary"] = card_effect_summary(card.definition)
        else:
            base["description"] = "打出 (手牌)"
            base["card_index"] = idx
            base["payment_indices"] = payment

    elif atype == "court_action":
        cid = getattr(action, 'card_id', '')
        base["card_id"] = cid
        if court_cards:
            for card in court_cards:
                if card.definition.card_id == cid:
                    base["description"] = f"牌组行动: 「{card.name}」"
                    base["card_name"] = card.name
                    base["effect_summary"] = _summarize_strategy_effects(card.definition)
                    base["block_costs"] = _format_block_costs(card.definition)
                    break
        if "description" not in base:
            base["description"] = f"牌组行动 (id={cid})"

    elif atype == "play_public_card":
        cid = getattr(action, 'card_id', '')
        payment = list(getattr(action, 'payment_indices', []))
        base["card_id"] = cid
        base["payment_indices"] = payment
        if public_cards:
            for card in public_cards:
                if card.definition.card_id == cid:
                    base["description"] = f"公共行动: 「{card.name}」(费用{card.cost})"
                    base["card_name"] = card.name
                    base["effect_summary"] = _summarize_strategy_effects(card.definition)
                    base["block_costs"] = _format_block_costs(card.definition)
                    break
        if "description" not in base:
            base["description"] = f"公共行动 (id={cid})"

    # --- Special actions ---
    elif atype == "convert":
        target = getattr(action, 'target_location', '?')
        free = getattr(action, 'free', False)
        cost = "免费" if free else "4军力"
        base["description"] = f"转化 → {target} ({cost})"
        base["target"] = target
    elif atype == "archive":
        idx = getattr(action, 'card_index', -1)
        source = getattr(action, 'source', 'hand')
        base["description"] = f"存档 ({source})"
        base["card_index"] = idx
        base["source"] = source
    elif atype == "spread_culture":
        culture = getattr(action, 'culture_type', '?')
        region = getattr(action, 'target_region', '?')
        culture_label = {"confucianism": "儒学", "taoism": "玄学", "buddhism": "佛学"}.get(culture, culture)
        base["description"] = f"传播文化: {culture_label} → {region}"
    elif atype == "search":
        st = getattr(action, 'search_type', '?')
        cnt = getattr(action, 'search_count', 1)
        base["description"] = f"检索: {st} x{cnt}"
    elif atype == "levy":
        cid = getattr(action, 'card_id', '')
        base["description"] = f"征发 (id={cid})"
        base["card_id"] = cid
    elif atype == "raise_order":
        base["description"] = "提高行动顺位"
    elif atype == "lower_order":
        target = getattr(action, 'target_player_id', '?')
        base["description"] = f"降低 {target} 顺位"
    elif atype == "activate_effect":
        card_id = getattr(action, 'card_id', '')
        bi = getattr(action, 'block_index', 0)
        ci = getattr(action, 'choice_index', 0)
        base["card_id"] = card_id
        base["block_index"] = bi
        base["choice_index"] = ci
        # Try to find card name
        card_name = _find_card_name(card_id, player_staff, player_hero)
        base["description"] = f"激活「{card_name}」" if card_name else f"激活效果 (id={card_id})"

    else:
        base["description"] = str(atype)

    return base


def _find_card_name(card_id: str, staff: list = None, hero: Any = None) -> Optional[str]:
    """Look up a card name from staff area or hero."""
    if hero and hasattr(hero, 'definition') and hero.definition.card_id == card_id:
        return hero.name
    if staff:
        for c in staff:
            if hasattr(c, 'definition') and c.definition.card_id == card_id:
                return c.name
    return None


def _card_type_label_str(card_type) -> str:
    """Chinese label for card type (works with raw values or enum)."""
    if card_type is None:
        return "?"
    val = card_type.value if hasattr(card_type, 'value') else str(card_type)
    labels = {"friend": "幕僚", "strategy": "策略", "event": "事件",
              "hero": "英雄", "mechanism": "强制事件"}
    return labels.get(val, val)


# ================================================================
# Effect summarization helpers (extracted from HumanPlayer)
# ================================================================

def _summarize_steps(steps) -> str:
    """Summarize a list of effect steps into a concise string."""
    if not steps:
        return ""

    from cards.effect_ast import EffectType

    parts = []
    for step in steps:
        et = step.effect_type if hasattr(step, 'effect_type') else step.get('effect_type', '')
        params = step.params if hasattr(step, 'params') else step
        raw_amt = params.get("amount", params.get("count", 1)) if isinstance(params, dict) else 1
        try:
            amt = int(raw_amt)
        except (ValueError, TypeError):
            amt = 1

        labels = {
            EffectType.GAIN_MILITARY: f"+{amt}军力",
            EffectType.GAIN_VP: f"+{amt}VP",
            EffectType.DRAW_CARDS: f"摸{amt}张牌",
            EffectType.SPREAD_CULTURE: "传播文化",
            EffectType.CONVERT: f"转化x{amt}" if amt > 1 else "转化",
            EffectType.MARCH: f"进军x{amt}" if amt > 1 else "进军",
            EffectType.OCCUPY: f"占据x{amt}" if amt > 1 else "占据",
            EffectType.RAISE_ORDER: "提高顺位",
            EffectType.LOWER_ORDER: "降低顺位",
            EffectType.RAISE_PRESTIGE: f"+{amt}威望",
            EffectType.RAISE_CONTRIBUTION: f"+{amt}功绩",
            EffectType.ARCHIVE_CARD: "存档",
            EffectType.ARCHIVE_THIS: "存档此牌",
            EffectType.SEARCH: f"检索x{amt}" if amt > 1 else "检索",
            EffectType.GET_EXPEDITION: "远征标记",
            EffectType.FORTIFY: "加固",
            EffectType.DISCARD_CARDS: f"弃{amt}手牌",
            EffectType.LOSE_VP: f"-{amt}VP",
            EffectType.LOSE_MILITARY: f"-{amt}军力",
            EffectType.PAY_MILITARY: f"支付{amt}军力",
            EffectType.PAY_VP: f"支付{amt}VP",
            EffectType.CHOOSE: "选择效果",
        }
        label = labels.get(et)
        if label:
            parts.append(label)
        else:
            et_str = et.value if hasattr(et, 'value') else str(et)
            parts.append(et_str)

    return "，".join(parts) if parts else ""


def _summarize_card_effects(card_def: "CardDef") -> str:
    """Extract a one-line effect summary covering enter/active/passive blocks."""
    parsed = card_def.parsed_effect
    if not parsed:
        return ""

    from cards.effect_ast import AbilityType

    parts = []
    for block in parsed.blocks:
        if block.ability_type in (AbilityType.ENTER, AbilityType.ACTIVE,
                                   AbilityType.STRATEGY_ACTION):
            steps_summary = _summarize_steps(block.steps)
            if steps_summary:
                parts.append(steps_summary)
        elif block.ability_type == AbilityType.PASSIVE:
            trigger = block.trigger or ""
            if trigger:
                parts.append(f"被动:{_trigger_label(trigger)}")

    return "，".join(parts) if parts else ""


def _summarize_strategy_effects(card_def: "CardDef") -> str:
    """Extract effect summary from strategy_action blocks specifically."""
    parsed = card_def.parsed_effect
    if not parsed:
        return ""

    from cards.effect_ast import AbilityType

    parts = []
    for block in parsed.blocks:
        if block.ability_type == AbilityType.STRATEGY_ACTION:
            steps_summary = _summarize_steps(block.steps)
            if steps_summary:
                parts.append(steps_summary)
            if block.choice_options:
                for opt_steps in block.choice_options[:1]:
                    opt_summary = _summarize_steps(opt_steps)
                    if opt_summary:
                        parts.append(f"选项:{opt_summary}")

    return "，".join(parts) if parts else ""


def _format_block_costs(card_def: "CardDef") -> str:
    """Extract block-level costs from strategy_action blocks."""
    parsed = card_def.parsed_effect
    if not parsed:
        return ""

    from cards.effect_ast import AbilityType

    all_costs = []
    for block in parsed.blocks:
        if block.ability_type == AbilityType.STRATEGY_ACTION:
            for cost in block.costs:
                ct = cost.cost_type if hasattr(cost, 'cost_type') else cost.get('cost_type', '')
                params = cost.params if hasattr(cost, 'params') else cost
                if ct == "pay_military":
                    all_costs.append(f"支付{params.get('amount', 0)}军力")
                elif ct == "pay_vp":
                    all_costs.append(f"支付{params.get('amount', 0)}VP")
                elif ct == "discard_cards":
                    all_costs.append(f"弃{params.get('count', 1)}手牌")

    return "，".join(all_costs) if all_costs else ""


def _format_block_costs_from_blocks(blocks) -> str:
    """Format costs from a list of block objects (for activate effect)."""
    all_costs = []
    for block in blocks:
        for cost in block.costs:
            ct = cost.cost_type if hasattr(cost, 'cost_type') else cost.get('cost_type', '')
            params = cost.params if hasattr(cost, 'params') else cost
            if ct == "pay_military":
                all_costs.append(f"支付{params.get('amount', 0)}军力")
            elif ct == "pay_vp":
                all_costs.append(f"支付{params.get('amount', 0)}VP")
            elif ct == "discard_cards":
                all_costs.append(f"弃{params.get('count', 1)}手牌")
    return "，".join(all_costs) if all_costs else ""


def _trigger_label(trigger: str) -> str:
    """Chinese label for trigger types."""
    labels = {
        "on_turn_start": "回合开始",
        "on_turn_end": "回合结束",
        "on_march": "进军时",
        "on_occupy": "占据时",
        "on_fortify": "加固时",
        "on_convert": "转化时",
        "on_play_card": "出牌时",
        "on_court_action": "牌组行动时",
        "on_spread_culture": "传播文化时",
        "on_archive": "存档时",
        "on_draw": "摸牌时",
        "on_discard": "弃牌时",
        "on_recruit": "征募时",
        "on_gain_military": "获得军力时",
        "on_gain_vp": "获得VP时",
        "on_gain_prestige": "获得威望时",
        "on_gain_contribution": "获得功绩时",
        "on_military_change": "军力变化时",
        "on_vp_change": "VP变化时",
        "always": "始终",
    }
    return labels.get(trigger, trigger)


# ================================================================
# Deep freeze (for SnapshotViewport immutability)
# ================================================================

def deep_freeze(obj: Any) -> Any:
    """Recursively convert a nested structure to immutable primitives.

    - list → tuple
    - dict → frozendict-like (actually just a deeply-frozen dict; we use
      a regular dict but all nested values are frozen)
    - set → frozenset
    - Other types pass through unchanged.

    Since Python doesn't have a native frozen dict, we return a regular dict
    whose values have all been recursively frozen.  This is sufficient for
    the "don't accidentally mutate a snapshot" use case.
    """
    if isinstance(obj, dict):
        return {k: deep_freeze(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return tuple(deep_freeze(v) for v in obj)
    elif isinstance(obj, set):
        return frozenset(deep_freeze(v) for v in obj)
    elif isinstance(obj, bytes):
        return obj  # already immutable
    elif isinstance(obj, (int, float, str, bool, type(None))):
        return obj
    else:
        # Unknown type — return as-is (may be a custom object)
        return obj


def is_json_serializable(obj: Any) -> bool:
    """Check if an object can be serialized to JSON."""
    try:
        import json
        json.dumps(obj)
        return True
    except (TypeError, ValueError):
        # Try after deep_freeze
        try:
            json.dumps(deep_freeze(obj))
            return True
        except (TypeError, ValueError):
            return False
