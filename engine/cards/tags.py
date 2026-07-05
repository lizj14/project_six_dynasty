"""Card effect tag definitions and mappings.

The card effect text uses a template tag language like:
    {action}获得X军力，X=[军事]标记数
    {passive}每次{occupy_action}后，获得1{vp}

This module maps all tags to their meanings and provides the lexer.
"""

# === Semantic Tags (map to game actions/effects) ===

SEMANTIC_TAGS: dict[str, str] = {
    # Timing / ability type
    "action": "主动能力",           # Active ability (once per turn)
    "passive": "被动能力",          # Passive/continuous ability
    "enter": "登场效果",            # On-enter-play effect
    "decision": "牌组行动",         # Strategy action (court)
    "force": "强制效果",            # Forced/mandatory effect
    "choose": "选择",               # Player choice
    "other": "或者",                # "Or" branch in choices

    # Actions
    "play": "打出",                 # Play a card
    "save": "存档",                 # Archive a card
    "discard": "弃置",              # Discard
    "abandon": "弃置候选",          # Abandon a candidate card (弃置候选策略牌)
    "supple": "补充",               # Replenish card to court (补充牌到朝堂区)
    "supplant": "转化",             # Convert/supplant location
    "march": "进军",                # March
    "occupy_action": "占据",        # Occupy (action)
    "occupy": "占据",               # Occupy (state)
    "emp_defense": "加固",          # Fortify
    "emp_expansion": "扩张",        # Expansion task
    "emp_culture": "文化",          # Culture task
    "emp_reform": "改革",           # Reform task
    "emp_art": "艺术",              # Art task
    "free": "免费",                 # Free (no cost)

    # Payment
    "pay": "支付",                  # Pay cost
    "fee": "费用",                  # Cost amount

    # Card operations
    "search": "检索",               # Search deck
    "card_friend": "幕僚牌",        # Friend card type
    "card_strategy": "策略牌",      # Strategy card type
    "card_event": "事件牌",         # Event card type
    "card_mechanism": "强制事件牌",  # Mechanism card type
    "card_public": "公共牌",        # Public card type
    "card_hero": "角色牌",          # Hero card type

    # Resources
    "vp": "VP",                     # Victory points
    "battle": "军力",               # Military/battle power
    "hand": "手牌",                 # Hand cards
    "army": "部队",                 # Army unit
    "reserve": "部队储备区",        # Army reserve

    # Tracks
    "prestige": "威望",             # Prestige
    "contribution": "功绩",         # Contribution (note: CSV has typo "contirbution")
    "order": "行动顺位",            # Turn order

    # Markers / Tags
    "power": "权谋标记",            # Power marker
    "culture": "文化标记",          # Culture marker
    "military": "军事标记",         # Military marker
    "affair": "内政标记",           # Internal affairs marker

    # Cultures
    "Confusion": "儒学",            # Confucianism (typo in source)
    "NeoTaosim": "玄学",            # Neo-Taoism (typo in source)
    "Buddhist": "佛学",             # Buddhism

    # Factions
    "jin": "东晋",                  # Eastern Jin
    "north": "北方",                # Northern dynasty
    "sima": "司马家",               # Sima clan
    "common": "通用",              # Common/generic
    "neutral": "中立",              # Neutral

    # Game objects
    "player": "玩家",               # Player
    "friend_player": "友方玩家",     # Friendly player
    "this": "此牌",                 # This card (self-reference)
    "candidate": "候选策略牌",      # Candidate strategy card
    "court": "朝堂区",              # Court area
    "display": "展示区",            # Display area
    "friend_area": "幕僚区",        # Staff area
    "jin_panel": "东晋面板",        # Jin national board

    # Faction restrictions
    "only": "仅限",                 # Only (used with faction: {only}{jin})

    # Special
    "urusp": "僭越",                # Usurp (僭越)
    "expedition": "北伐标记",       # Northern expedition marker
    "refugee": "流民",              # Refugee
    "start_order": "先动值",        # Start order (hero)

    # Conditional
    "control": "控制",              # Control (a region)
    "neighbor": "相邻",             # Adjacent
    "district": "区域",             # Region
    "location": "地点",             # Location
    "capital": "首都",              # Capital

    # End
    "end": "终局",                  # End of game

    # Choice separator
    "newline": "换行",              # Line break

    # Task types (on emperor dice)
    "task_expansion": "扩张任务",
    "task_fortify": "加固任务",
    "task_culture": "文化任务",
    "task_reform": "改革任务",
    "task_art": "艺术任务",
}

# Reverse mapping: Chinese → tag
CHINESE_TO_TAG: dict[str, str] = {v: k for k, v in SEMANTIC_TAGS.items()}


def lex_effect_text(text: str) -> list[dict]:
    """Lex the effect text into a list of tokens.

    Each token is either:
      - {"type": "tag", "value": "action"}  (template tag like {action})
      - {"type": "text", "value": "获得"}     (plain Chinese text)
      - {"type": "number", "value": 3}        (number like 3 or X)
      - {"type": "bracket", "value": "[军事]"} (bracket reference like [军事])
      - {"type": "colon", "value": "："}       (Chinese colon separator)
      - {"type": "semicolon", "value": "；"}   (Chinese semicolon)
    """
    import re

    tokens = []
    pos = 0

    while pos < len(text):
        # Match template tags {xxx}
        tag_match = re.match(r'\{([^}]+)\}', text[pos:])
        if tag_match:
            tag_name = tag_match.group(1)
            tokens.append({"type": "tag", "value": tag_name})
            pos += len(tag_match.group(0))
            continue

        # Match bracket references [xxx]
        bracket_match = re.match(r'\[([^\]]+)\]', text[pos:])
        if bracket_match:
            tokens.append({"type": "bracket", "value": bracket_match.group(1)})
            pos += len(bracket_match.group(0))
            continue

        # Match numbers (including X as variable)
        num_match = re.match(r'(\d+|X)', text[pos:])
        if num_match:
            val = num_match.group(1)
            if val == 'X':
                tokens.append({"type": "variable", "value": "X"})
            else:
                tokens.append({"type": "number", "value": int(val)})
            pos += len(num_match.group(0))
            continue

        # Match punctuation
        if text[pos] in '：':
            tokens.append({"type": "colon", "value": text[pos]})
            pos += 1
            continue
        if text[pos] in '；':
            tokens.append({"type": "semicolon", "value": text[pos]})
            pos += 1
            continue
        if text[pos] in '，':
            tokens.append({"type": "comma", "value": text[pos]})
            pos += 1
            continue
        if text[pos] in '。':
            tokens.append({"type": "period", "value": text[pos]})
            pos += 1
            continue
        if text[pos] in '、':
            tokens.append({"type": "list_sep", "value": text[pos]})
            pos += 1
            continue
        if text[pos] in '>':
            tokens.append({"type": "gt", "value": text[pos]})
            pos += 1
            continue
        if text[pos] in '<':
            tokens.append({"type": "lt", "value": text[pos]})
            pos += 1
            continue
        if text[pos] in '=':
            tokens.append({"type": "equals", "value": text[pos]})
            pos += 1
            continue
        if text[pos] in '+':
            tokens.append({"type": "plus", "value": text[pos]})
            pos += 1
            continue
        if text[pos] in '-':
            tokens.append({"type": "minus", "value": text[pos]})
            pos += 1
            continue
        if text[pos] in '/':
            tokens.append({"type": "slash", "value": text[pos]})
            pos += 1
            continue

        # Collect Chinese text until next tag or bracket
        chinese_end = pos
        while (chinese_end < len(text) and
               text[chinese_end] not in '{}[]：；，。、<>=-+/' and
               not text[chinese_end].isdigit()):
            chinese_end += 1

        if chinese_end > pos:
            chinese_text = text[pos:chinese_end]
            tokens.append({"type": "text", "value": chinese_text})
            pos = chinese_end
        else:
            # Skip unknown character
            pos += 1

    return tokens


def tokenize_simple(text: str) -> list[str]:
    """Simplified tokenization — split into semantic chunks.

    Returns a list of segments alternating between tags and text.
    e.g. "{action}获得X军力" → ["{action}", "获得X军力"]
    """
    import re
    # Split on tag boundaries but keep the tags
    parts = re.split(r'(\{[^}]+\})', text)
    return [p for p in parts if p]


def extract_tag_name(tag_str: str) -> str:
    """Extract the tag name from {tagname}."""
    if tag_str.startswith('{') and tag_str.endswith('}'):
        return tag_str[1:-1]
    return tag_str
