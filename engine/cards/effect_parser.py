"""Card effect text parser — converts Chinese effect text into CardEffect AST.

Parses the templated tag language found in card_design.csv's 效果 column.
Uses regex-based pattern matching since the language is semi-structured.
"""

import re
from typing import Optional

from .effect_ast import (
    CardEffect, AbilityBlock, EffectStep, Condition,
    EffectType, AbilityType, TriggerType,
)
from .tags import tokenize_simple, extract_tag_name


class EffectParser:
    """Parser for card effect text. Converts raw Chinese text to CardEffect AST."""

    def parse(self, card_name: str, effect_text: str, **card_info) -> CardEffect:
        """Parse a card's effect text into a CardEffect AST.

        Args:
            card_name: Card name for debugging
            effect_text: Raw effect text from CSV
            **card_info: Additional card properties (markers, faction, etc.)
        """
        if not effect_text or effect_text.strip() in ('', '-'):
            return CardEffect(card_name=card_name, raw_text=effect_text)

        effect = CardEffect(
            card_name=card_name,
            raw_text=effect_text,
            is_usurp=card_info.get('is_usurp', False),
            faction_restriction=card_info.get('faction_restriction'),
        )

        text = effect_text.strip()

        # Detect play condition at start: "XXX，可以打出。" / "如果有XXX，可以打出"
        play_cond_match = re.match(r'(.+?)[，,]\s*可以打出[。\s]*(.*)', text)
        if play_cond_match and ('时' in play_cond_match.group(1) or '如果' in play_cond_match.group(1) or '控制' in play_cond_match.group(1) or '占据' in play_cond_match.group(1)):
            cond_text = play_cond_match.group(1).strip()
            rest_text = play_cond_match.group(2).strip()
            effect.play_condition = self._parse_condition(cond_text)
            text = rest_text  # Continue parsing the rest

        # Split into ability blocks based on timing keywords
        blocks = self._split_blocks(text)
        for block_text, ability_type in blocks:
            # Restriction blocks → card-level play_condition
            if ability_type == "restriction":
                cond = self._parse_restriction_condition(block_text)
                if cond:
                    effect.play_condition = cond
                continue

            ability = self._parse_ability_block(block_text, ability_type)
            if ability:
                # Expand sub-passives: "XXX时，A。YYY时，B。" → two blocks
                sub_passives = getattr(ability, '_sub_passives', None)
                if sub_passives:
                    _, _, shared_filter = self._detect_trigger(text)
                    for i, (trigger_text, effect_text) in enumerate(sub_passives):
                        sub_block = self._parse_ability_block(effect_text, AbilityType.PASSIVE)
                        if sub_block:
                            sub_block.trigger, sub_block.trigger_scope, _ = \
                                self._detect_trigger(trigger_text)
                            sub_block.trigger_filter = shared_filter
                            # Modifier goes to the last sub_block (which has the actual trigger)
                            if i == len(sub_passives) - 1 and ability.modifier:
                                sub_block.modifier = ability.modifier
                            if sub_block.trigger is None and sub_block.steps:
                                sub_block.trigger = self._infer_trigger_from_steps(
                                    sub_block.steps, trigger_text)
                            # Skip empty default-trigger blocks (static permissions filtered out)
                            if (sub_block.steps or sub_block.choice_options or
                                (sub_block.modifier and sub_block.trigger is not None)):
                                effect.blocks.append(sub_block)
                else:
                    # Propagate restrictions from blocks to card-level
                    block_restrictions = getattr(ability, '_restrictions', None)
                    if block_restrictions:
                        effect.restrictions.extend(block_restrictions)
                        delattr(ability, '_restrictions')
                    # Convert play_requirement steps to card-level play_condition
                    if ability.steps and all(
                        s.effect_type == "play_requirement" for s in ability.steps
                    ):
                        for s in ability.steps:
                            culture_map = {"儒学": "confucianism", "玄学": "taoism", "佛学": "buddhism"}
                            culture = culture_map.get(
                                s.params.get("culture", ""),
                                s.params.get("culture", ""),
                            )
                            threshold = s.params.get("threshold", 0)
                            effect.play_condition = Condition(
                                condition_type="culture_contribution_gt",
                                params={"culture": culture, "threshold": threshold},
                            )
                        continue  # Skip adding this block
                    # Skip empty blocks (e.g. restriction-only passives)
                    if ability.steps or ability.choice_options:
                        effect.blocks.append(ability)

        return effect

    def _split_blocks(self, text: str) -> list[tuple[str, str]]:
        """Split effect text into ability blocks by timing keywords.

        Returns list of (block_text, ability_type).
        """
        # Order matters — match longer patterns first
        patterns = [
            (r'主动[：:]', AbilityType.ACTIVE),
            (r'被动[：:]', AbilityType.PASSIVE),
            (r'登场[：:]', AbilityType.ENTER),
            (r'强制[：:]', AbilityType.FORCED),
            (r'行动[：:]', AbilityType.STRATEGY_ACTION),
            (r'限定[：:]', "restriction"),
        ]

        # Find all split points
        splits = []
        for pattern, atype in patterns:
            for m in re.finditer(pattern, text):
                splits.append((m.start(), m.end(), atype))

        if not splits:
            # No timing keyword found — treat entire text based on context
            return [(text, AbilityType.STRATEGY_ACTION)]

        splits.sort(key=lambda x: x[0])

        blocks = []
        for i, (start, end, atype) in enumerate(splits):
            next_start = splits[i + 1][0] if i + 1 < len(splits) else len(text)
            block_text = text[end:next_start].strip()
            blocks.append((block_text, atype))

        return blocks

    def _parse_ability_block(self, text: str, ability_type: str) -> Optional[AbilityBlock]:
        """Parse a single ability block's text into an AbilityBlock."""
        if not text:
            return None

        block = AbilityBlock(ability_type=ability_type, source_text=text)

        # Check for usurp block
        text, usurp_text = self._extract_usurp(text)

        # Check for if-else: 如果COND，THEN；否则，ELSE
        _if_else = re.match(r'如果(.+?)[，,](.+?)[；;]否则[，,]?(.+)', text)
        if _if_else:
            cond_text = _if_else.group(1).strip()
            then_text = _if_else.group(2).strip()
            else_text = _if_else.group(3).strip()
            cond = self._parse_condition(cond_text)
            # if-true branch: condition must be met
            if_true_steps = self._parse_steps(then_text)
            for s in if_true_steps:
                s.condition = cond
                block.steps.append(s)
            # if-false branch: condition must NOT be met (invert)
            neg_cond = Condition(condition_type="not", params={"condition": {
                "condition_type": cond.condition_type, "params": cond.params}})
            if_false_steps = self._parse_steps(else_text)
            for s in if_false_steps:
                s.condition = neg_cond
                block.steps.append(s)
        # Check for choice structure
        elif ('选择' in text and '项' in text) or '或者' in text or (
            '或' in text and '或者' not in text and re.search(r'(获得|失去|提高|降低).*或', text)):
            block.choice_options = self._parse_choices(text)
        else:
            block.steps = self._parse_steps(text)

        # Merge usurp effects into steps with can_usurp condition
        if usurp_text:
            u_steps = self._parse_steps(usurp_text)
            usurp_cond = Condition(condition_type="can_usurp", params={})
            for us in u_steps:
                us.condition = usurp_cond
                block.steps.append(us)

        # Extract block-level costs for all ability types
        if block.steps:
            self._extract_block_costs(block)

        # For passives, detect trigger/restrictions + handle multi-trigger
        if ability_type == AbilityType.PASSIVE:
            self._detect_restrictions(text, block)
            if re.search(r'并列最高.*僭越', text) or re.search(r'也可以执行.*僭越', text):
                block.modifier = {"usurp_with_tie": True}
            sub_blocks = self._split_passive_triggers(text)
            if len(sub_blocks) > 1:
                block._sub_passives = sub_blocks
            else:
                block.trigger, block.trigger_scope, block.trigger_filter = \
                    self._detect_trigger(text)
                if block.trigger is None and block.steps:
                    block.trigger = self._infer_trigger_from_steps(block.steps, text)

        # Convert "choice" steps to block-level choice_options
        keep_steps = []
        for step in block.steps:
            if step.effect_type == "choice" and "options" in step.params:
                if not block.choice_options:
                    block.choice_options = step.params["options"]
            else:
                keep_steps.append(step)
        block.steps = keep_steps

        return block

    def _parse_restriction_condition(self, text: str) -> Optional[Condition]:
        """Parse restriction text into a structured play_condition.

        Patterns:
          - "需要控制[幽燕]，才能打出、执行或征发"
          - "占据[京口]时，才能打出、执行或征发"
          - "控制[西凉]时，才能打出、执行或征发"
          - "XXX时，可以打出"
        """
        import re as _re
        clean = self._normalize_tags(text)

        # "占据[京口]" → occupy specific location
        occupy = _re.search(r'占据\[([^\]]+)\]', clean)
        if occupy:
            return Condition(
                condition_type="occupy_location",
                params={"location": occupy.group(1)},
            )
        # "控制[幽燕]" / "需要控制[西凉]" → control region
        region = _re.search(r'(?:需要\s*)?控制\[([^\]]+)\]', clean)
        if region:
            return Condition(
                condition_type="control_region",
                params={"region": region.group(1)},
            )

        # "XXX时，可以打出" (event play condition)
        if _re.search(r'可以打出', clean):
            # Extract the condition part before "时"
            cond_part = _re.match(r'(.+?)时[，,]?\s*可以打出', clean)
            if cond_part:
                return self._parse_condition(cond_part.group(1).strip())
            return Condition(condition_type="raw_text", params={"text": text})

        return Condition(condition_type="raw_text", params={"text": text})

    def _set_var_amount(self, step: "EffectStep", source: str, extra: dict = None) -> bool:
        """Set variable amount on a step, recursing into sub_effect. Returns True if applied."""
        # Check for targeted_effect with lose_vp/gain_vp sub_effect
        if step.effect_type == "targeted_effect" and "sub_effect" in step.params:
            se = step.params["sub_effect"]
            if isinstance(se, dict) and se.get("effect_type") in ("lose_vp", "gain_vp"):
                if se.get("params", {}).get("amount") in ("X", None):
                    se["params"] = se.get("params", {})
                    se["params"]["amount"] = source
                    if extra:
                        se["params"].update(extra)
                    return True
            return False
        # Regular step with variable amount ("X" only, not None or concrete)
        if step.params.get("amount") == "X":
            step.params["amount"] = source
            if extra:
                step.params.update(extra)
            return True
        return False

    def _target_type_for(self, name: str) -> str:
        """Map Chinese target name to target type."""
        if '司马家' in name:
            return "sima"
        if '宰辅' in name:
            return "chancellor"
        if '玩家' in name:
            return "player"
        return "unknown"

    def _infer_trigger_from_steps(self, steps: list, text: str) -> str:
        """Infer trigger timing from step effect types, and fix step types."""
        for step in steps:
            # cost_reduction + march context → march_cost_reduction
            if step.effect_type == "cost_reduction" and re.search(r'进军|march', text):
                step.effect_type = "march_cost_reduction"
                step.params["per_turn_limit"] = 2  # conservative default
                return TriggerType.ON_MARCH
            if step.effect_type == "march_cost_reduction":
                return TriggerType.ON_MARCH
            if step.effect_type == "region_reward_override":
                return "on_region_reward"
        # Check text for clues
        if re.search(r'进军', text):
            return TriggerType.ON_MARCH
        return None  # was TriggerType.ALWAYS

    def _split_passive_triggers(self, text: str) -> list[tuple[str, str]]:
        """Split passive text into (trigger_desc, effect_text) pairs.

        Also handles compound triggers like "存档或弃置[流民]时" →
        expanded to ("存档[流民]时", effect) and ("弃置[流民]时", effect).
        """
        import re as _re
        pairs = []

        # Check for compound triggers with 或/或者
        compound = _re.match(r'(.+?)(?:或|或者)(.+?)([时后])[，,](.+)', text)
        if compound:
            prefix = compound.group(1).strip()
            suffix = compound.group(2).strip() + compound.group(3)
            effect = compound.group(4).strip()
            pairs.append((prefix + compound.group(3), effect))
            pairs.append((suffix, effect))
            return pairs

        # Split by "。" first — each sentence may have its own trigger
        sentences = [s.strip() for s in text.split('。') if s.strip()]
        for sentence in sentences:
            m = _re.match(r'(.+?(?:[时后]|每.+?(?:[时后])))[，,](.+)', sentence)
            if m:
                trigger = m.group(1).strip()
                effect = m.group(2).strip()
                pairs.append((trigger, effect))
            else:
                # No explicit trigger — use full sentence as trigger+effect
                pairs.append((sentence, sentence))
        return pairs if pairs else [(text, text)]

    def _detect_restrictions(self, text: str, block: "AbilityBlock"):
        """Detect static card restrictions from passive text.

        Handles patterns like:
          - "不能被存档、征发或弃置"  (compound, shared "不能被")
          - "不能被存档"              (single)
        """
        restrictions = []
        # Find the "不能被" clause and extract all items
        m = re.search(r'不能\s*被?\s*(.+)', text)
        if m:
            items_text = m.group(1)
            # Split by 、or 或
            items = re.split(r'[、或]', items_text)
            for item in items:
                item = item.strip()
                if '存档' in item:
                    restrictions.append("cannot_be_archived")
                if '征发' in item:
                    restrictions.append("cannot_be_drafted")
                if '弃置' in item:
                    restrictions.append("cannot_be_discarded")

        if restrictions:
            block._restrictions = restrictions

        return block

    def _extract_block_costs(self, block: "AbilityBlock"):
        """Move payment steps from block.steps into block.costs.

        Patterns like "支付1张手牌，提高1级顺位，传播1次[玄学]" →
          costs: [discard_cards(1)]
          steps: [raise_order(1), spread_culture(...)]
        """
        from .effect_ast import Cost

        keep_steps = []
        for step in block.steps:
            # Discard from hand as cost
            if step.effect_type == EffectType.DISCARD_CARDS:
                if step.params.get("from_hand", True):
                    block.costs.append(Cost(
                        cost_type="discard_cards",
                        params={"count": step.params.get("count", 1), "from_hand": True},
                    ))
                    continue
            elif step.effect_type == EffectType.PAY_MILITARY:
                block.costs.append(Cost(
                    cost_type="pay_military",
                    params={"amount": step.params.get("amount", 0)},
                ))
            elif step.effect_type == EffectType.PAY_VP:
                block.costs.append(Cost(
                    cost_type="pay_vp",
                    params={"amount": step.params.get("amount", 0)},
                ))
            elif step.effect_type == "abandon_court_card":
                block.costs.append(Cost(
                    cost_type="abandon_court_card",
                    params={"count": step.params.get("count", 1)},
                ))
            else:
                keep_steps.append(step)

        block.steps = keep_steps

    def _extract_usurp(self, text: str) -> tuple[str, Optional[str]]:
        """Extract usurp [僭越] portion from text.

        Returns (base_text, usurp_text_or_None).
        """
        # Pattern: [僭越]... or {urusp}... (but NOT as part of trigger like "结算[僭越]效果时")
        if re.search(r'(?:结算|执行)\s*\[僭越\]', text):
            return text, None  # Part of trigger description, not usurp block
        match = re.search(r'(\[僭越\]|\{urusp\})\s*(.+)', text)
        if match:
            # The usurp text is everything after the marker
            usurp_text = match.group(2)
            base_text = text[:match.start()].strip()
            return base_text, usurp_text
        return text, None

    def _parse_choices(self, text: str) -> list[list[EffectStep]]:
        """Parse choice options: 选择1项：optionA；或者optionB / 获得X或Y"""
        options = []
        # Pattern 1: explicit choice marker "选择1项："
        if '选择' in text and '项' in text:
            parts = re.split(r'[；;]\s*或者\s*|[；;]', text)
            for part in parts:
                part = re.sub(r'^选择\d+项[：:]\s*', '', part).strip()
                if part:
                    options.append(self._parse_steps(part))
            return options

        # Pattern 2: "获得1军力或2vp" → split by 或
        if '或' in text and '或者' not in text:
            parts = text.split('或')
            for part in parts:
                part = part.strip()
                if part:
                    try:
                        steps = self._parse_steps(part)
                        if steps:
                            options.append(steps)
                    except ValueError:
                        pass
            if len(options) >= 2:
                return options

        # Fallback: split by 或者
        parts = re.split(r'[；;]\s*或者\s*|[；;]', text)
        for part in parts:
            part = re.sub(r'^选择\d+项[：:]\s*', '', part).strip()
            if part:
                options.append(self._parse_steps(part))
        return options if len(options) >= 2 else []

    def _parse_steps(self, text: str) -> list[EffectStep]:
        """Parse effect text into a list of EffectSteps.

        Uses a stateful approach: try to parse each segment. If a segment
        doesn't match, see if it's a modifier for the previous step
        (variable binding) or a context fragment that can be skipped.
        """
        if not text:
            return []

        steps = []
        pos = 0

        while pos < len(text):
            # Try optional-with-cost: 可以支付N军力/Nvp，EFFECT
            opt_cost = re.match(r'可以\s*支付\s*(\d+)\s*(?:军力|vp)[，,](.+)', text[pos:], re.IGNORECASE)
            if opt_cost:
                cost_amount = int(opt_cost.group(1))
                is_vp = 'vp' in opt_cost.group(0).lower()
                effect_text = opt_cost.group(2)
                pos += len(opt_cost.group(0))
                cost_type = "pay_vp" if is_vp else "pay_military"
                inner = self._parse_steps(effect_text)
                for s in inner:
                    s.params["may"] = True
                    s.params["cost"] = {"cost_type": cost_type, "params": {"amount": cost_amount}}
                    steps.extend(inner)
                continue

            # Try conditional: 如果 COND ， EFFECT / 本回合X时，EFFECT
            cond_match = re.match(r'(?:如果|本回合)\s*(.+?)[，,](.+?)(?:[。；]|$)', text[pos:])
            if cond_match:
                condition_text = cond_match.group(1).strip()
                effect_text = cond_match.group(2).strip()
                pos += len(cond_match.group(0))
                cond = self._parse_condition(condition_text)
                for seg in re.split(r'[，。；]', effect_text):
                    seg = seg.strip()
                    if seg:
                        try:
                            s = self._parse_single_step(seg)
                            s.condition = cond
                            # Merge "如果加固目标不是自己的地点，额外获得Nvp" into prev fortify
                            if (s.effect_type == EffectType.GAIN_VP and
                                s.condition and "加固" in str(s.condition.params.get("text", ""))):
                                for j in range(len(steps) - 1, -1, -1):
                                    if steps[j].effect_type == "fortify":
                                        steps[j].params["bonus_vp_if_not_own"] = s.params.get("amount", 1)
                                        break
                            else:
                                steps.append(s)
                        except ValueError:
                            pass
                if pos < len(text) and text[pos] in '。；':
                    pos += 1
                continue

            # Extract next segment + remember the separator
            m = re.match(r'[^，。；并]+', text[pos:])
            if not m:
                pos += 1
                continue
            segment = m.group(0).strip()
            pos += len(m.group(0))
            sep = text[pos] if pos < len(text) and text[pos] in '，。；并' else ''
            if sep:
                pos += 1

            # Variable binding: X=[军事]标记数 — applies to the previous step
            var_match = re.match(r'X\s*=\s*\[(.+?)\]\s*标记数\s*（?最多(\d+)）?', segment)
            if var_match:
                if steps:
                    steps[-1].params["variable"] = True
                    steps[-1].params["variable_source"] = var_match.group(1)
                    max_val = var_match.group(2)
                    if max_val:
                        steps[-1].params["max"] = int(max_val)
                continue
            # Simpler: X=[...]标记数 (no max)
            var_match2 = re.match(r'X\s*=\s*\[(.+?)\]\s*标记数', segment)
            if var_match2:
                if steps:
                    steps[-1].params["variable"] = True
                    steps[-1].params["variable_source"] = var_match2.group(1)
                continue
            # X=文化贡献等级之和 → sum of 3 culture contributions
            var_match3 = re.match(r'X\s*=\s*(文化贡献等级之和|文化贡献度之和)', segment)
            if var_match3:
                if steps:
                    steps[-1].params["amount"] = "sum"
                    steps[-1].params["sources"] = [
                        "confucianism_contribution",
                        "taoism_contribution",
                        "buddhism_contribution",
                    ]
                continue
            # X=你的[权谋]标记数 → power_marker_count
            var_power = re.match(r'X\s*=\s*你的?\[(权谋|军事|文化|内政)\]\s*标记数', segment)
            if var_power:
                marker_map = {'权谋': 'power', '军事': 'military', '文化': 'culture', '内政': 'affair'}
                if steps:
                    for s in steps:
                        self._set_var_amount(s, f"marker_count_{marker_map[var_power.group(1)]}")
                continue
            # X=东晋朝堂区的[流民]数 → jin_court_refugee_count
            var_court = re.match(r'X\s*=\s*东晋朝堂区的?\[流民\]数', segment)
            if var_court:
                if steps:
                    for s in steps:
                        self._set_var_amount(s, "jin_court_refugee_count")
                continue
            # X=[江南][荆襄][淮南]的中立地点数 → neutral_count(regions)
            var_neutral = re.match(r'X\s*=\s*\[(.+?)\][的]?\s*中立地点数', segment)
            if var_neutral:
                if steps:
                    regions = re.findall(r'\[([^\]]+)\]', segment)
                    for s in steps:
                        self._set_var_amount(s, "neutral_count_in_regions",
                                              {"regions": regions})
                continue
            # X=其他之和 (generic)
            var_match4 = re.match(r'X\s*=\s*(.+之和)', segment)
            if var_match4:
                if steps:
                    steps[-1].params["variable"] = True
                    steps[-1].params["variable_source"] = var_match4.group(1)
                continue

            # Split compound resources: "2军力2vp" → "2军力", "2vp"
            if re.search(r'\d+\s*军力\s*\d+\s*vp', segment, re.IGNORECASE):
                # Split before the second number: "2军力2vp" → ["2军力", "2vp"]
                sub_segs = re.split(r'(?<=\D)(?=\d+\s*vp)', segment, maxsplit=1)
                for sub in sub_segs:
                    sub = sub.strip()
                    if sub:
                        try:
                            step = self._parse_single_step(sub)
                            steps.append(step)
                        except ValueError:
                            raise ValueError(f"Cannot parse compound resource part: '{sub}'")
                continue

            # Skip context fragments that aren't standalone steps
            if self._is_context_fragment(segment):
                continue

            try:
                step = self._parse_single_step(segment)
                # Merge conditional "额外获得Nvp" into previous fortify step
                if (step.effect_type == EffectType.GAIN_VP and
                    step.condition and
                    step.condition.condition_type == "raw_text" and
                    "加固" in step.condition.params.get("text", "") and steps):
                    prev = steps[-1]
                    if prev.effect_type == "fortify":
                        prev.params["bonus_vp_if_not_own"] = step.params.get("amount", 1)
                        prev.condition = None  # Clear raw_text
                        continue
                # Unwrap "compound" steps (from multi-target place_refugee etc.)
                # If targeted_effect has sub_effects array, check if next raw segment
                # is a gain_vp/military/etc. that should be inside the targeted_effect
                # (handled by appending to sub_effects when the next step is parsed)

                if step.effect_type == "compound" and "steps" in step.params:
                    for sub in step.params["steps"]:
                        # Reconstitute EffectStep from dict
                        es = EffectStep(
                            effect_type=sub["effect_type"],
                            params=sub.get("params", {}),
                            source_text=step.source_text,
                        )
                        steps.append(es)
                    continue
                # Merge cost_reduction into previous march/fortify/occupy step
                if step.effect_type == "cost_reduction" and steps:
                    prev = steps[-1]
                    if prev.effect_type in ("march", "fortify", "occupy"):
                        prev.params["cost_reduction"] = step.params.get("amount", 1)
                        continue
                # Expand each_lose_vp into multiple targeted_effects
                if step.effect_type == "each_lose_vp":
                    targets = step.params.get("targets", [])
                    variable = step.params.get("variable", False)
                    for t in targets:
                        ttype = self._target_type_for(t)
                        tparams = {"type": ttype}
                        # sima/chancellor are auto-detected, no selection needed
                        if ttype not in ("sima", "chancellor"):
                            tparams["selection"] = "choose"
                        expanded = EffectStep(
                            effect_type="targeted_effect",
                            params={
                                "target": tparams,
                                "sub_effect": {
                                    "effect_type": EffectType.LOSE_VP,
                                    "params": {"amount": "X", "variable": variable},
                                },
                            },
                            source_text=step.source_text,
                        )
                        steps.append(expanded)
                else:
                    steps.append(step)
            except ValueError:
                # Try merging with next segment, preserving the separator
                if pos < len(text):
                    m2 = re.match(r'[^，。；并]+', text[pos:])
                    if m2:
                        next_seg = m2.group(0).strip()
                        merged = segment + sep + next_seg
                        try:
                            step = self._parse_single_step(merged)
                            steps.append(step)
                            pos += len(m2.group(0))
                            if pos < len(text) and text[pos] in '，。；':
                                pos += 1
                        except ValueError:
                            raise ValueError(
                                f"Cannot parse effect step: '{segment}{sep}{next_seg}'"
                            )
                    else:
                        raise ValueError(f"Cannot parse effect step: '{segment}'")
                else:
                    raise ValueError(f"Cannot parse effect step: '{segment}'")

        return steps

    def _is_context_fragment(self, text: str) -> bool:
        """Check if text is a context fragment, not a standalone effect step.

        Fragments include:
          - "先动值N" (hero start order, handled at enter block level)
          - "[X]不能被存档、征发或弃置" (passive restriction)
          - "才能打出、执行或征发" (faction/condition restriction)
          - "不获得vp" (no-VP clause)
          - "然后" (sequence connector)
          - "也可以执行" (additional capability)
          - "获得2vp" (this IS a step, not a fragment!)
        """
        # Hero enter metadata (stored on card, not as parsed steps)
        if re.match(r'^(先动值\d+|获得\d+顺位|获得\d+功绩|获得\d+威望|'
                      r'\d+功绩和\d+威望|获得\d+功绩和\d+威望)$', text):
            return True
        # Parenthetical notes like （不触发被动效果）
        if text.startswith('（') and text.endswith('）'):
            return True
        # Passive restrictions / static requirements
        if re.search(r'不能被存档', text):
            return True
        if re.search(r'才能打出', text):
            return True
        # "需要X才能打出/执行" — static requirement
        if re.search(r'需要.*才能', text):
            return True
        # "此牌离开幕僚区时" — trigger descriptor (handled by split)
        if re.search(r'离开幕僚区', text):
            return True
        # "当你的X是并列最高时" — static permission
        if re.search(r'并列最高', text) or re.search(r'也可以执行', text):
            return True
        # "当你的X是...时" — static permission descriptor
        if re.search(r'当你的', text):
            return True
        # "威望最高的X玩家" / "[功绩]最高的X玩家" — implicit target+effect, skip
        # "该玩家-N功绩并+Nvp" — compound effect (needs dedicated parser)
        # Standalone No-VP clause
        if text in ('（不获得vp）', '（不获得VP）', '不获得vp', '不获得VP',
                    '（不触发被动效果）', '（不触发被动）'):
            return True
        # Sequence connectors (bare only)
        if text == '然后':
            return True
        # Play capability keywords (bare only)
        if text in ('也可以执行', '可以执行', '也可以打出', '可以打出',
                    '可以打出或执行', '或执行', '可以打出或，执行'):
            return True
        if re.search(r'^(可以打出|可以执行|或执行)$', text):
            return True
        # Trigger descriptors (handled at block level)
        if re.search(r'(时|后)\s*$', text) and not re.search(r'\d+次', text):
            return True
        # "每回合前N次" triggers — keep as steps, don't filter
        # (handled by dedicated patterns)
        # 流民被动描述: "自动放置回供应堆" — handled by special logic
        if '放置回供应堆' in text or '自动放置' in text:
            return True
        # "并且" connector
        if text == '并且':
            return True
        # "终局" keyword
        if text == '终局':
            return True
        # "然后" standalone — but "然后摸1张牌" IS a valid step
        if text == '然后':
            return True
        # "结算" standalone
        if text == '结算':
            return True
        # "效果" standalone
        if text == '效果':
            return True
        # Bare play-conditions: "可以作为事件打出", "可以打出或执行"
        # NOT: "可以执行1个手牌行动" (that's a real effect)
        if re.search(r'^(?:可以打出或执行|可以作为事件打出|可以打出|可以执行)$', text):
            return True
        # Standalone conditions like "需要[X]等级>0"
        if re.search(r'需要\[', text) and '才能打出' in text:
            return True
        # "幕僚区空位总数为N" — descriptive, stored as card field
        if '幕僚区空位总数为' in text:
            return True
        # "X=..." complex variable bindings
        if re.match(r'X\s*=\s*', text):
            return True
        # Faction label ("北方", "东晋") already handled as step
        # Bare marker descriptions
        if re.search(r'^(军事|文化|内政|权谋|儒学|玄学|佛学)标记$', text):
            return True
        return False

    def _parse_condition(self, text: str) -> Optional[Condition]:
        """Parse a condition string like '[内政]标记数>2' into a Condition."""
        text = self._normalize_tags(text)

        # [内政]标记数>N
        m = re.search(r'\[?(内政|军事|文化|权谋)\]?\s*标记数\s*[>＞]\s*(\d+)', text)
        if m:
            from .tags import SEMANTIC_TAGS
            marker_name = m.group(1)
            return Condition(
                condition_type="marker_count_gt",
                params={"marker": marker_name, "threshold": int(m.group(2))},
            )

        # [儒学]等级>N
        m = re.search(r'\[?(儒学|玄学|佛学)\]?\s*等级\s*[>＞]\s*(\d+)', text)
        if m:
            return Condition(
                condition_type="culture_level_gt",
                params={"culture": m.group(1), "threshold": int(m.group(2))},
            )

        # [儒学]贡献度>N
        m = re.search(r'\[?(儒学|玄学|佛学)\]?\s*贡献度\s*[>＞]\s*(\d+)', text)
        if m:
            return Condition(
                condition_type="culture_contribution_gt",
                params={"culture": m.group(1), "threshold": int(m.group(2))},
            )

        # 本回合执行[进军]时 → duration-limited trigger
        m = re.search(r'(?:本回合\s*)?执行\s*\[?(进军|占据|加固|转化)\]?\s*时', text)
        if m:
            action_map = {'进军': 'march', '占据': 'occupy', '加固': 'fortify', '转化': 'convert'}
            return Condition(
                condition_type="on_action_this_turn",
                params={"action": action_map.get(m.group(1), m.group(1))},
            )

        # 拥有4种不同的标记各1个 → AND of 4 marker checks
        m = re.search(r'拥有\s*(\d+)\s*种\s*不同的?\s*标记\s*各?\s*(\d+)?\s*个?', text)
        if m:
            count = int(m.group(1))
            each = int(m.group(2)) if m.group(2) else 1
            all_markers = ["军事", "文化", "内政", "权谋"]
            marker_en = {"军事": "military", "文化": "culture", "内政": "affair", "权谋": "power"}
            sub_conds = []
            for mk in all_markers[:count]:
                sub_conds.append({
                    "condition_type": "marker_count",
                    "params": {"marker": marker_en[mk], "min": each},
                })
            return Condition(
                condition_type="and",
                params={"conditions": sub_conds},
            )

        # 控制[幽燕] / 占据[京口]
        m = re.search(r'(?:控制|占据|友方控制)\[([^\]]+)\]', text)
        if m:
            return Condition(
                condition_type="control_region",
                params={"region": m.group(1)},
            )

        # [儒学]区域数>=[玄学]区域数 → region count comparison
        rc = re.search(r'\[(儒学|玄学|佛学)\]\s*(?:区域数|等级)\s*([>=<]+)\s*\[(儒学|玄学|佛学)\]\s*(?:区域数|等级)', text)
        if rc:
            culture_map = {'儒学': 'confucianism', '玄学': 'taoism', '佛学': 'buddhism'}
            left_key = "region_count" if "区域数" in text else "culture_level"
            return Condition(
                condition_type="compare",
                params={"left": f"{left_key}_{culture_map[rc.group(1)]}",
                        "op": rc.group(2).strip(),
                        "right": f"{left_key}_{culture_map[rc.group(3)]}"},
            )

        # 幕僚区有空位 → friend_count < staff_limit
        if re.search(r'幕僚区有空位', text):
            return Condition(
                condition_type="compare",
                params={"left": "friend_count", "op": "<", "right": "staff_limit"},
            )

        # 有一条从[X]到[Y]的全部地点被东晋占据的线路 → has_route
        route_m = re.search(r'从\[([^\]]+)\]\s*到\s*\[([^\]]+)\].*线路', text)
        if route_m:
            return Condition(
                condition_type="has_route",
                params={"from": route_m.group(1), "to": route_m.group(2), "controller": "jin"},
            )

        # Generic: fallback — raw_text is a last resort for unrecognized conditions
        return Condition(condition_type="raw_text", params={"text": text})

    def _parse_single_step(self, text: str) -> Optional[EffectStep]:
        """Parse a single effect segment into an EffectStep."""
        # Normalize template tags to clean text
        clean = self._normalize_tags(text)

        # Try each pattern matcher
        for pattern_fn in _STEP_PATTERNS:
            result = pattern_fn(clean, text)
            if result:
                return result

        # Not matched — add a pattern matcher above
        raise ValueError(f"Cannot parse effect step: '{text}'")

    def _normalize_tags(self, text: str) -> str:
        """Strip template tags and brackets for cleaner pattern matching."""
        from .tags import SEMANTIC_TAGS

        def replace_tag(m):
            tag = m.group(1).strip()
            return SEMANTIC_TAGS.get(tag, tag)

        result = re.sub(r'\{([^}]+)\}', replace_tag, text)
        return result

    def _detect_trigger(self, text: str) -> tuple[Optional[str], str, Optional[dict]]:
        """Detect trigger event, scope, and filter from passive text.

        Returns (trigger_type, scope, filter_dict).
        """
        clean = self._normalize_tags(text)

        # Scope detection
        scope = "any" if re.search(r'任意玩家|其他玩家|友方', clean) else "self"

        # Filter detection — only from trigger portion (before 时/后)
        trigger_filter = None
        trigger_part = clean.split('时')[0] if '时' in clean else clean.split('后')[0] if '后' in clean else clean
        marker_match = re.search(r'\[(权谋|军事|文化|内政)\]', trigger_part)
        if marker_match:
            marker_map = {'权谋': 'power', '军事': 'military', '文化': 'culture', '内政': 'affair'}
            trigger_filter = {"marker": marker_map.get(marker_match.group(1), marker_match.group(1))}
        # Card-specific trigger: [流民]
        if re.search(r'\[流民\]', trigger_part):
            trigger_filter = {"card": "流民"}

        # Trigger type detection
        trigger_map = [
            (r'每次\s*(?:\[?进军\]?\s*)+后', TriggerType.ON_MARCH),
            (r'每次\s*占据\s*后', TriggerType.ON_OCCUPY),
            (r'每次\s*(?:结算\s*)?\[?转化\]?\s*后', TriggerType.ON_CONVERT),
            (r'每次\s*存档', TriggerType.ON_ARCHIVE),
            (r'(?:每次\s*)?弃置', TriggerType.ON_DISCARD),
            (r'(?:每次\s*)?执行.*策略', TriggerType.ON_COURT_ACTION),
            (r'(?:每次\s*)?打出.*(?:标记|牌)', TriggerType.ON_PLAY_CARD),
            (r'每次\s*获得\s*功绩', TriggerType.ON_GAIN_CONTRIBUTION),
            (r'每次\s*获得\s*威望', TriggerType.ON_GAIN_PRESTIGE),
            (r'每当\s*传播.*文化', TriggerType.ON_SPREAD_CULTURE),
            (r'每次\s*执行\s*僭越', TriggerType.ON_USURP),
            (r'提高行动顺位\s*时', TriggerType.ON_ORDER_CHANGE),
            (r'任意玩家.*顺位.*时', TriggerType.ON_ORDER_CHANGE),
            (r'离开幕僚区\s*时', TriggerType.ON_CARD_LEAVE),
            (r'友方.*传播.*文化', TriggerType.ON_SPREAD_CULTURE),
            # (r'标记\s*放置.*版图', TriggerType.ON_CARD_ENTER),  # on_card_enter 未实现触发分发，已注释
            (r'(?:每次|结算)?.*僭越.*?(?:时|后)', TriggerType.ON_USURP),
        ]
        trigger_type = None  # was TriggerType.ALWAYS
        for pattern, tt in trigger_map:
            if re.search(pattern, clean):
                trigger_type = tt
                break

        return trigger_type, scope, trigger_filter


# ============================================================
# Step Pattern Matchers
# ============================================================

# Each function takes (clean_text, original_text) and returns
# an EffectStep or None if it doesn't match.

def _parse_gain_military(text: str, orig: str) -> Optional[EffectStep]:
    """获得N军力 / N军力 (bare) / N军力Nvp (compound resource)"""
    # "获得N军力"
    m = re.search(r'获得\s*(\d+|X)\s*军力', text)
    if m:
        val = m.group(1)
        return EffectStep(
            effect_type=EffectType.GAIN_MILITARY,
            params={"amount": val if val == 'X' else int(val), "variable": val == 'X'},
            source_text=orig,
        )
    # Compound resource: "N军力Nvp" → gain_military(N) + gain_vp(N)
    # Handled in _parse_steps by splitting and creating two separate steps
    # (no compound step — each resource gets its own effect_type)
    # Bare "N军力"
    m = re.search(r'^(\d+)\s*军力$', text)
    if m:
        return EffectStep(
            effect_type=EffectType.GAIN_MILITARY,
            params={"amount": int(m.group(1)), "variable": False},
            source_text=orig,
        )
    return None


def _parse_gain_vp(text: str, orig: str) -> Optional[EffectStep]:
    """获得Nvp / Nvp (bare)"""
    m = re.search(r'获得\s*(\d+|X)\s*vp', text, re.IGNORECASE)
    if m:
        val = m.group(1)
        return EffectStep(
            effect_type=EffectType.GAIN_VP,
            params={"amount": val if val == 'X' else int(val), "variable": val == 'X'},
            source_text=orig,
        )
    # Bare "Nvp" or "+Nvp"
    m = re.search(r'^\+?(\d+)\s*vp$', text, re.IGNORECASE)
    if m:
        return EffectStep(
            effect_type=EffectType.GAIN_VP,
            params={"amount": int(m.group(1)), "variable": False},
            source_text=orig,
        )
    return None


def _parse_pay_military(text: str, orig: str) -> Optional[EffectStep]:
    """支付N军力"""
    m = re.search(r'支付\s*(\d+)\s*军力', text)
    if m:
        return EffectStep(
            effect_type=EffectType.PAY_MILITARY,
            params={"amount": int(m.group(1))},
            source_text=orig,
        )
    return None


def _parse_draw_cards(text: str, orig: str) -> Optional[EffectStep]:
    """摸N张牌 / 摸N张手牌"""
    m = re.search(r'摸\s*(\d+)\s*张(?:手)?牌', text)
    if m:
        return EffectStep(
            effect_type=EffectType.DRAW_CARDS,
            params={"count": int(m.group(1))},
            source_text=orig,
        )
    return None


def _parse_other_discard(text: str, orig: str) -> Optional[EffectStep]:
    """其他每个东晋玩家各弃N张手牌 → targeted_effect on each other Jin player"""
    m = re.search(r'其他每个东晋玩家各弃\s*(\d+)\s*张\s*(手)?牌', text)
    if m:
        return EffectStep(
            effect_type="targeted_effect",
            params={
                "target": {"type": "other_jin_player", "selection": "each"},
                "sub_effect": {
                    "effect_type": EffectType.DISCARD_CARDS,
                    "params": {"count": int(m.group(1)), "from_hand": True},
                },
            },
            source_text=orig,
        )
    return None


def _parse_discard_cards(text: str, orig: str) -> Optional[EffectStep]:
    """弃N张手牌"""
    m = re.search(r'弃\s*(\d+)\s*张\s*(手)?牌', text)
    if m:
        return EffectStep(
            effect_type=EffectType.DISCARD_CARDS,
            params={"count": int(m.group(1)), "from_hand": True},
            source_text=orig,
        )
    return None


def _parse_pay_hand_card(text: str, orig: str) -> Optional[EffectStep]:
    """支付N张手牌 (pay hand cards as cost)"""
    m = re.search(r'支付\s*(\d+)\s*张\s*(手)?牌', text)
    if m:
        return EffectStep(
            effect_type=EffectType.DISCARD_CARDS,
            params={"count": int(m.group(1)), "from_hand": True, "as_cost": True},
            source_text=orig,
        )
    return None


def _parse_archive_this(text: str, orig: str) -> Optional[EffectStep]:
    """存档此牌"""
    if re.search(r'存档\s*(此牌|该牌)', text):
        return EffectStep(
            effect_type=EffectType.ARCHIVE_THIS,
            params={},
            source_text=orig,
        )
    return None


def _parse_archive_card(text: str, orig: str) -> Optional[EffectStep]:
    """存档1张[幕僚] / 存档1张候选策略牌"""
    m = re.search(r'存档\s*(\d+)\s*张?\s*(幕僚|候选策略牌|候选|牌)', text)
    if m:
        card_type = m.group(2)
        type_map = {
            '幕僚': 'friend',
            '候选策略牌': 'court',
            '候选': 'court',
            '牌': 'any',
        }
        return EffectStep(
            effect_type=EffectType.ARCHIVE_CARD,
            params={"count": int(m.group(1)), "card_type": type_map.get(card_type, 'any')},
            source_text=orig,
        )
    return None


def _parse_convert_location(text: str, orig: str) -> Optional[EffectStep]:
    """转化[长安][弘农] / 转化1个相邻中立地点 / 转化N个[X]以外的Y地点"""
    NON_LOCATIONS = {'僭越', '儒学', '玄学', '佛学', '军事', '文化', '内政', '权谋',
                     '北伐', '流民', '幕僚', '策略', '进军', '加固', '功绩', '威望'}

    # Pattern: 转化N个[X]以外的Y地点 (convert with structured filter)
    m = re.search(r'转化\s*(\d+)\s*个\s*\[([^\]]+)\]\s*以外\s*的\s*(.+?)\s*地点', text)
    if m:
        f = {"exclude_locations": [m.group(2)]}
        desc = m.group(3).strip()
        if '司马家' in desc:
            f["controller"] = "sima"
        elif '东晋' in desc:
            f["controller"] = "jin"
        elif '北方' in desc:
            f["controller"] = "north"
        elif '中立' in desc:
            f["controller"] = "neutral"
        return EffectStep(
            effect_type=EffectType.CONVERT,
            params={"count": int(m.group(1)), "filter": f},
            source_text=orig,
        )

    # Multiple named locations
    locs = re.findall(r'\[([^\]]+)\]', text)
    convert_locs = []
    for loc in locs:
        if loc not in NON_LOCATIONS:
            from .tags import SEMANTIC_TAGS
            if loc not in SEMANTIC_TAGS and not loc.isascii():
                convert_locs.append(loc)

    # Pattern: 转化1个非[江南][荆襄]区域的中立地点 (exclude regions)
    m_excl = re.search(r'转化\s*(\d+)\s*个\s*非\s*(.+?)\s*区域\s*的?\s*中立地点', text)
    if m_excl:
        exclude_regions = re.findall(r'\[([^\]]+)\]', m_excl.group(2))
        return EffectStep(
            effect_type=EffectType.CONVERT,
            params={
                "count": int(m_excl.group(1)),
                "filter": {"controller": "neutral", "exclude_regions": exclude_regions},
            },
            source_text=orig,
        )

    # Pattern: 转化1个相邻中立地点 (structured filter)
    m = re.search(r'转化\s*(\d+)\s*个?\s*(相邻)?\s*(中立)?\s*(地点|区域)?', text)
    if m and not convert_locs:
        f = {}
        if m.group(2):
            f["adjacent"] = True
        if m.group(3):
            f["controller"] = "neutral"
        return EffectStep(
            effect_type=EffectType.CONVERT,
            params={"count": int(m.group(1)), "filter": f} if f else {"count": int(m.group(1))},
            source_text=orig,
        )

    if convert_locs:
        import re as _re
        clean_src = _re.sub(r'[（(][^）)]*[）)]', '', orig).strip()
        return EffectStep(
            effect_type=EffectType.CONVERT,
            params={"count": len(convert_locs), "specific_locations": convert_locs},
            source_text=clean_src or orig,
        )

    return None


def _parse_spread_culture(text: str, orig: str) -> Optional[EffectStep]:
    """传播1次[儒学] / 传播1次文化"""
    m = re.search(r'传播\s*(\d+)\s*次\s*\[?(文化|儒学|玄学|佛学)\]?', text)
    if m:
        culture = m.group(2)
        culture_map = {
            '儒学': 'confucianism',
            '玄学': 'taoism',
            '佛学': 'buddhism',
            '文化': None,  # Player chooses or generic
        }
        return EffectStep(
            effect_type=EffectType.SPREAD_CULTURE,
            params={
                "count": int(m.group(1)),
                "culture": culture_map.get(culture) if culture else None,
            },
            source_text=orig,
        )
    return None


def _parse_search(text: str, orig: str) -> Optional[EffectStep]:
    """检索2次[策略] / 检索2次[军事]"""
    m = re.search(r'检索\s*(\d+)\s*次\s*\[?([^\]]+)\]?', text)
    if m:
        search_type = m.group(2).strip()
        type_map = {
            '策略': 'strategy',
            '幕僚': 'friend',
            '军事': 'military',
            '文化': 'culture',
            '权谋': 'power',
            '内政': 'affair',
        }
        return EffectStep(
            effect_type=EffectType.SEARCH,
            params={
                "count": int(m.group(1)),
                "search_type": type_map.get(search_type, search_type),
            },
            source_text=orig,
        )
    return None


def _parse_march_free(text: str, orig: str) -> Optional[EffectStep]:
    """免费[进军]1次 / 免费进军1次"""
    m = re.search(r'免费\s*(进军|占据|加固)\s*(\d+)?\s*次', text)
    if m:
        action_map = {'进军': 'march', '占据': 'occupy', '加固': 'fortify'}
        action = action_map.get(m.group(1), m.group(1))
        count = int(m.group(2)) if m.group(2) else 1
        return EffectStep(
            effect_type=action,
            params={"free": True, "count": count},
            source_text=orig,
        )
    return None


def _parse_fortify(text: str, orig: str) -> Optional[EffectStep]:
    """免费加固1次 / 加固1次"""
    m = re.search(r'(免费)?\s*加固\s*(\d+)?\s*次', text)
    if m:
        return EffectStep(
            effect_type=EffectType.FORTIFY,
            params={"free": m.group(1) is not None, "count": int(m.group(2)) if m.group(2) else 1},
            source_text=orig,
        )
    return None


def _parse_raise_order(text: str, orig: str) -> Optional[EffectStep]:
    """提高1级顺位"""
    m = re.search(r'提高\s*(\d+)\s*级\s*顺位', text)
    if m:
        return EffectStep(
            effect_type=EffectType.RAISE_ORDER,
            params={"amount": int(m.group(1))},
            source_text=orig,
        )
    return None


def _parse_lower_order(text: str, orig: str) -> Optional[EffectStep]:
    """降低N级顺位 / 其他所有X玩家降低N级(顺位)"""
    m = re.search(r'(?:其他所有\S*玩家\s*)?降低\s*(\d+)\s*级\s*(?:顺位)?', text)
    if m:
        return EffectStep(
            effect_type=EffectType.LOWER_ORDER,
            params={"amount": int(m.group(1))},
            source_text=orig,
        )
    return None


def _parse_draft(text: str, orig: str) -> Optional[EffectStep]:
    """征发N张候选策略牌"""
    m = re.search(r'征发\s*(\d+)\s*张\s*候选策略牌', text)
    if m:
        return EffectStep(
            effect_type=EffectType.DRAFT,
            params={"count": int(m.group(1))},
            source_text=orig,
        )
    return None


def _parse_supply_court(text: str, orig: str) -> Optional[EffectStep]:
    """补充1张牌到朝堂区"""
    m = re.search(r'补充\s*(\d+)\s*张牌\s*到\s*朝堂区', text)
    if m:
        return EffectStep(
            effect_type=EffectType.SUPPLY_COURT,
            params={"count": int(m.group(1))},
            source_text=orig,
        )
    return None


def _parse_get_expedition(text: str, orig: str) -> Optional[EffectStep]:
    """获得[北伐]标记 / 从东晋面板获得[北伐]标记"""
    if re.search(r'北伐.*标记', text) and re.search(r'获得|获取', text):
        return EffectStep(
            effect_type=EffectType.GET_EXPEDITION,
            params={},
            source_text=orig,
        )
    return None


def _parse_add_refugee(text: str, orig: str) -> Optional[EffectStep]:
    """放置1张[流民]"""
    m = re.search(r'放置\s*(\d+)\s*张?\s*流民', text)
    if m:
        return EffectStep(
            effect_type=EffectType.ADD_REFUGEE,
            params={"count": int(m.group(1))},
            source_text=orig,
        )
    return None


def _parse_play_card(text: str, orig: str) -> Optional[EffectStep]:
    """可以打出1张幕僚牌 / 可以打出1张手牌"""
    m = re.search(r'(可以\s*)?打出\s*(\d+)\s*张\s*(幕僚|手)?牌', text)
    if m:
        card_type = m.group(3) or 'any'
        may = m.group(1) is not None
        type_map = {'幕僚': 'friend', '手': 'any', '': 'any'}
        return EffectStep(
            effect_type=EffectType.PLAY_CARD,
            params={"count": int(m.group(2)), "card_type": type_map.get(card_type, 'any'),
                    "may": may},
            source_text=orig,
        )
    return None


def _parse_raise_culture(text: str, orig: str) -> Optional[EffectStep]:
    """提高1级[佛学]贡献度"""
    m = re.search(r'提高\s*(\d+)\s*级\s*(儒学|玄学|佛学)\s*贡献度', text)
    if m:
        culture_map = {'儒学': 'confucianism', '玄学': 'taoism', '佛学': 'buddhism'}
        return EffectStep(
            effect_type=EffectType.RAISE_CULTURE_LEVEL,
            params={"amount": int(m.group(1)), "culture": culture_map.get(m.group(2))},
            source_text=orig,
        )
    return None


def _parse_remove_army(text: str, orig: str) -> Optional[EffectStep]:
    """将部队储备区的N个部队放回游戏盒中"""
    m = re.search(r'将.*部队储备区.*(\d+)\s*个\s*部队\s*放回.*游戏盒', text)
    if m:
        return EffectStep(
            effect_type=EffectType.REMOVE_FROM_GAME,
            params={"count": int(m.group(1)), "from_reserve": True},
            source_text=orig,
        )
    return None


def _parse_gain_contribution_and_prestige(text: str, orig: str) -> Optional[EffectStep]:
    """获得N功绩和N威望 / 获得N功绩（可能带括号注释）"""
    m = re.search(r'(?:获得\s*)?(\d+)\s*功绩\s*(?:和|、)\s*(\d+)\s*威望', text)
    if m:
        return EffectStep(
            effect_type="gain_contribution_and_prestige",
            params={"contribution": int(m.group(1)), "prestige": int(m.group(2))},
            source_text=orig,
        )
    # Standalone: 获得N功绩 or N功绩
    m = re.search(r'(?:获得\s*)?(\d+)\s*功绩', text)
    if m:
        return EffectStep(
            effect_type=EffectType.RAISE_CONTRIBUTION,
            params={"amount": int(m.group(1))},
            source_text=orig,
        )
    return None


def _parse_gain_prestige(text: str, orig: str) -> Optional[EffectStep]:
    """获得N威望 / 司马家威望+N / 威望+N"""
    m = re.search(r'获得(\d+)\[?威望\]?', text)
    if m:
        return EffectStep(
            effect_type=EffectType.RAISE_PRESTIGE,
            params={"amount": int(m.group(1))},
            source_text=orig,
        )
    # 司马家威望+N / 威望+N
    m = re.search(r'(?:司马家)?\s*威望\s*\+\s*(\d+)', text)
    if m:
        return EffectStep(
            effect_type=EffectType.RAISE_PRESTIGE,
            params={"amount": int(m.group(1))},
            source_text=orig,
        )
    # 司马家威望-N / 威望-N
    m = re.search(r'(?:司马家)?\s*威望\s*-\s*(\d+)', text)
    if m:
        return EffectStep(
            effect_type=EffectType.LOWER_PRESTIGE,
            params={"amount": int(m.group(1))},
            source_text=orig,
        )
    return None


def _parse_gain_order(text: str, orig: str) -> Optional[EffectStep]:
    """获得N顺位"""
    m = re.search(r'获得(\d+)顺位', text)
    if m:
        return EffectStep(
            effect_type=EffectType.RAISE_ORDER,
            params={"amount": int(m.group(1))},
            source_text=orig,
        )
    return None


def _parse_free_action(text: str, orig: str) -> Optional[EffectStep]:
    """免费[进军]N次 / 免费[加固]N次 / [进军]N次"""
    m = re.search(r'(免费\s*)?\[?(进军|加固|占据)\]?\s*(\d+)\s*次', text)
    if m:
        action_map = {'进军': 'march', '加固': 'fortify', '占据': 'occupy'}
        action = action_map.get(m.group(2), m.group(2))
        free = m.group(1) is not None
        count = int(m.group(3))
        return EffectStep(
            effect_type=action,
            params={"free": free, "count": count},
            source_text=orig,
        )
    return None


def _parse_play_or_draft_card(text: str, orig: str) -> Optional[EffectStep]:
    """打出1张[X]牌或征发1张[X]候选策略牌 → choice between two actions"""
    m = re.search(r'打出\s*(\d+)\s*张\s*\[?(军事|文化|内政|权谋)\]?\s*牌\s*或\s*征发\s*(\d+)\s*张\s*\[?(军事|文化|内政|权谋)\]?\s*候选策略牌', text)
    if m:
        play_count = int(m.group(1))
        play_tag = m.group(2)
        draft_count = int(m.group(3))
        draft_tag = m.group(4)
        marker_en = {'军事': 'military', '文化': 'culture', '内政': 'affair', '权谋': 'power'}
        return EffectStep(
            effect_type="choice",
            params={
                "options": [
                    [{"effect_type": EffectType.PLAY_CARD, "params": {"count": play_count},
                      "filter": {"marker": marker_en.get(play_tag, play_tag)}}],
                    [{"effect_type": EffectType.DRAFT, "params": {"count": draft_count},
                      "filter": {"marker": marker_en.get(draft_tag, draft_tag)}}],
                ]
            },
            source_text=orig,
        )
    return None


def _parse_convert_to_neutral(text: str, orig: str) -> Optional[EffectStep]:
    """将1个X区域的地点转为中立控制 → targeted_effect with location target"""
    m = re.search(r'将\s*(\d+)\s*个\s*(.+?)\s*区域\s*的?\s*(.+?)\s*转为\s*中立', text)
    if m:
        count = int(m.group(1))
        region_desc = m.group(2).strip()
        loc_desc = m.group(3).strip()
        # Build location target filter
        loc_filter = {}
        # Map region name to filter
        region_map = {'玄学': 'taoism', '儒学': 'confucianism', '佛学': 'buddhism'}
        if region_desc in region_map:
            loc_filter["culture_region"] = region_map[region_desc]
        else:
            loc_filter["region_name"] = region_desc
        if '未加固' in loc_desc:
            loc_filter["not_fortified"] = True
        return EffectStep(
            effect_type="targeted_effect",
            params={
                "target": {
                    "type": "location",
                    "count": count,
                    "selection": "choose",
                    "filters": [loc_filter],
                },
                "sub_effect": {
                    "effect_type": "convert_to_neutral",
                    "params": {},
                },
            },
            source_text=orig,
        )
    return None


def _parse_place_refugee(text: str, orig: str) -> Optional[EffectStep]:
    """在X弃牌区放置1张[流民] — resolve '本国' to own_faction"""
    m = re.search(r'在(.+?)弃牌区\s*(?:各)?\s*放置\s*(\d+)\s*张?\s*\[?流民\]?', text)
    if m:
        targets_raw = m.group(1).strip()
        count = int(m.group(2))
        # Split "东晋和北方" → ["东晋", "北方"]
        targets = re.split(r'[、和]', targets_raw)
        steps = []
        for t in targets:
            t = t.strip()
            if not t:
                continue
            if '本国' in t:
                t = "own_national_discard"
            elif '东晋' in t:
                t = "jin_discard"
            elif '北方' in t:
                t = "north_discard"
            steps.append(EffectStep(
                effect_type=EffectType.ADD_REFUGEE,
                params={"target": t, "count": count},
                source_text=orig,
            ))
        if len(steps) == 1:
            return steps[0]
        elif len(steps) > 1:
            return EffectStep(
                effect_type="compound",
                params={"steps": [{"effect_type": s.effect_type, "params": s.params} for s in steps]},
                source_text=orig,
            )
    return None
    return None


def _parse_conditional_playable(text: str, orig: str) -> Optional[EffectStep]:
    """X>1时，可以打出 / 拥有X时，可以打出 — play conditions handled by play_condition block"""
    return None


def _parse_reshuffle_emperor(text: str, orig: str) -> Optional[EffectStep]:
    """重洗当前君主牌"""
    if '重洗' in text and '君主牌' in text:
        return EffectStep(
            effect_type="reshuffle_emperor",
            params={},
            source_text=orig,
        )
    return None


def _parse_targeted_effect(text: str, orig: str) -> Optional[EffectStep]:
    """选择目标，效果 — formalized target + recursively parsed effect."""
    m = re.search(r'选择\s*(.+?)[，,]\s*(.+)', text)
    if m:
        target_desc = m.group(1).strip()
        effect_desc = m.group(2).strip()
        target = _parse_target(target_desc)
        # Split by 并/。 to get multiple sub-effects
        sub_effects = []
        for part in re.split(r'[并。]', effect_desc):
            part = part.strip()
            if part:
                se = _try_parse(part)
                if se:
                    sub_effects.append(_serialize_step(se))
        return EffectStep(
            effect_type="targeted_effect",
            params={
                "target": target,
                "sub_effects": sub_effects if sub_effects else None,
            },
            source_text=orig,
        )
    return None


def _parse_target(desc: str) -> dict:
    """Parse a target description into a structured target object.

    Examples:
      "1个玩家"           → {type: player, count: 1, selection: choose}
      "1个东晋玩家"        → {type: jin_player, count: 1, selection: choose}
      "1个友方玩家"        → {type: friendly_player, count: 1, selection: choose}
      "1个[幕僚]区空位最少的玩家" → {type: player, count: 1, selection: choose,
                                   filters: [{type: fewest_staff_slots}]}
      "1个费用最高的[幕僚]"  → {type: friend_card, count: 1, selection: choose,
                              filters: [{type: highest_cost}]}
      "1个[玄学]区域的未加固地点" → {type: location, count: 1, selection: choose,
                                  filters: [{type: region, value: 玄学},
                                            {type: not_fortified}]}
    """
    target = {"count": 1, "selection": "choose", "filters": []}

    # Count
    count_m = re.search(r'(\d+)\s*个', desc)
    if count_m:
        target["count"] = int(count_m.group(1))

    # Type detection
    if re.search(r'玩家', desc):
        if re.search(r'东晋', desc):
            target["type"] = "jin_player"
        elif re.search(r'友方', desc):
            target["type"] = "friendly_player"
        elif re.search(r'其他', desc):
            target["type"] = "other_jin_player"
        else:
            target["type"] = "player"
    elif re.search(r'幕僚', desc):
        target["type"] = "friend_card"
    elif re.search(r'候选策略牌', desc):
        target["type"] = "court_card"
    elif re.search(r'地点', desc):
        target["type"] = "location"
    elif re.search(r'手牌', desc):
        target["type"] = "hand_card"
    elif re.search(r'版图上.*文化标记', desc):
        target["type"] = "culture_marker_on_map"
    elif re.search(r'标记', desc) and re.search(r'文化|军事|内政|权谋', desc):
        target["type"] = "marker_type"
    elif re.search(r'威望|功绩|顺位', desc):
        target["type"] = "track"
    else:
        target["type"] = "unknown"

    # Selection method
    if re.search(r'随机', desc):
        target["selection"] = "random"
    elif re.search(r'所有', desc):
        target["selection"] = "all"

    # Filters
    if re.search(r'幕僚区空位最少', desc) or re.search(r'空位最少', desc):
        target["filters"].append({"type": "fewest_empty_staff_slots"})
    if re.search(r'费用最高', desc):
        target["filters"].append({"type": "highest_cost"})
    if re.search(r'费用最低', desc):
        target["filters"].append({"type": "lowest_cost"})
    if re.search(r'功绩最高', desc) or re.search(r'\[功绩\]\s*最高', desc):
        target["filters"].append({"type": "highest_contribution"})
    if re.search(r'威望最高', desc) or re.search(r'\[威望\]\s*最高', desc):
        target["filters"].append({"type": "highest_contribution"})
    if re.search(r'威望最高', desc):
        target["filters"].append({"type": "highest_prestige"})
    if re.search(r'未加固', desc):
        target["filters"].append({"type": "not_fortified"})
    if re.search(r'非东晋占据', desc):
        target["filters"].append({"type": "not_jin_controlled"})
    # Region filter
    region_m = re.search(r'\[?(玄学|儒学|佛学|江南|中原|关中|河北|山东|山西|淮南|荆襄|巴蜀|西凉|幽燕|塞外)\]?\s*区域', desc)
    if region_m:
        target["filters"].append({"type": "region", "value": region_m.group(1)})
    # Culture marker filter
    culture_m = re.search(r'\[?(玄学|儒学|佛学)\]?\s*标记', desc)
    if culture_m:
        target["filters"].append({"type": "culture", "value": culture_m.group(1)})

    return target


def _try_parse(segment: str) -> Optional[EffectStep]:
    """Try to parse a segment. If it contains '并', split into compound."""
    clean = _normalize_text(segment)
    # Handle "并" compounds: "该玩家-1[功绩]并+6vp"
    if '并' in segment and '并且' not in segment:
        parts = segment.split('并')
        # Return the first parsable part
        for part in parts:
            part = part.strip()
            if part:
                clean_p = _normalize_text(part)
                for pattern_fn in _STEP_PATTERNS:
                    result = pattern_fn(clean_p, part)
                    if result:
                        return result  # Return first match (caller handles the rest)
    for pattern_fn in _STEP_PATTERNS:
        result = pattern_fn(clean, segment)
        if result:
            return result
    return None


def _normalize_text(text: str) -> str:
    """Standalone text normalization (same as EffectParser._normalize_tags)."""
    from .tags import SEMANTIC_TAGS
    def replace_tag(m):
        tag = m.group(1).strip()
        return SEMANTIC_TAGS.get(tag, tag)
    return re.sub(r'\{([^}]+)\}', replace_tag, text)


def _serialize_step(step: Optional[EffectStep]) -> Optional[dict]:
    """Serialize an EffectStep to a dict (for nested storage)."""
    if step is None:
        return None
    return {
        "effect_type": step.effect_type,
        "params": step.params,
        "condition": _serialize_condition_dict(step.condition),
        "source_text": step.source_text,
    }


def _serialize_condition_dict(cond: Optional["Condition"]) -> Optional[dict]:
    if cond is None:
        return None
    return {"condition_type": cond.condition_type, "params": cond.params}


def _parse_lose_military(text: str, orig: str) -> Optional[EffectStep]:
    """该玩家失去N军力 / 失去N军力"""
    m = re.search(r'失去\s*(\d+)\s*军力', text)
    if m:
        return EffectStep(
            effect_type=EffectType.LOSE_MILITARY,
            params={"amount": int(m.group(1))},
            source_text=orig,
        )
    return None


def _parse_lose_contribution(text: str, orig: str) -> Optional[EffectStep]:
    """-N[功绩] / 失去N功绩"""
    m = re.search(r'[-−]\s*(\d+)\s*\[?功绩\]?', text)
    if m:
        return EffectStep(
            effect_type=EffectType.LOWER_CONTRIBUTION,
            params={"amount": int(m.group(1))},
            source_text=orig,
        )
    m = re.search(r'失去\s*(\d+)\s*功绩', text)
    if m:
        return EffectStep(
            effect_type=EffectType.LOWER_CONTRIBUTION,
            params={"amount": int(m.group(1))},
            source_text=orig,
        )
    return None


def _parse_lose_prestige(text: str, orig: str) -> Optional[EffectStep]:
    """失去N威望"""
    m = re.search(r'失去\s*(\d+)\s*\[?威望\]?', text)
    if m:
        return EffectStep(
            effect_type=EffectType.LOWER_PRESTIGE,
            params={"amount": int(m.group(1))},
            source_text=orig,
        )
    return None


def _parse_gain_vp_with_condition(text: str, orig: str) -> Optional[EffectStep]:
    """获得X vp，X=..."""
    m = re.search(r'获得\s*X\s*vp', text, re.IGNORECASE)
    if m:
        return EffectStep(
            effect_type=EffectType.GAIN_VP,
            params={"amount": "X", "variable": True},
            source_text=orig,
        )
    return None


def _parse_raise_culture_level(text: str, orig: str) -> Optional[EffectStep]:
    """提高1级[佛学]贡献度 / 提高1级文化贡献度"""
    m = re.search(r'提高\s*(\d+)\s*级\s*\[?(儒学|玄学|佛学|文化)\]?\s*贡献度', text)
    if m:
        culture_map = {'儒学': 'confucianism', '玄学': 'taoism', '佛学': 'buddhism', '文化': None}
        return EffectStep(
            effect_type=EffectType.RAISE_CULTURE_LEVEL,
            params={"amount": int(m.group(1)),
                    "culture": culture_map.get(m.group(2))},
            source_text=orig,
        )
    return None


def _parse_remove_culture_marker(text: str, orig: str) -> Optional[EffectStep]:
    """从供应轨移除N个[佛学]标记"""
    m = re.search(r'从供应轨移除\s*(\d+)\s*个\s*\[?(儒学|玄学|佛学)\]?\s*标记', text)
    if m:
        return EffectStep(
            effect_type="remove_culture_marker",
            params={"count": int(m.group(1)), "culture": m.group(2)},
            source_text=orig,
        )
    return None


def _parse_flip_culture_marker(text: str, orig: str) -> Optional[EffectStep]:
    """选择1个版图上的文化标记翻面"""
    if '文化标记翻面' in text:
        return EffectStep(
            effect_type="flip_culture_marker",
            params={},
            source_text=orig,
        )
    return None


def _parse_archive_friend(text: str, orig: str) -> Optional[EffectStep]:
    """存档1个幕僚"""
    m = re.search(r'存档\s*(\d+)\s*个\s*幕僚', text)
    if m:
        return EffectStep(
            effect_type="archive_card",
            params={"count": int(m.group(1)), "card_type": "friend", "from": "staff"},
            source_text=orig,
        )
    return None


def _parse_play_card_tag_filter(text: str, orig: str) -> Optional[EffectStep]:
    """打出1张不含[军事]标记的手牌"""
    m = re.search(r'打出\s*(\d+)\s*张\s*不含\s*\[?(军事|文化|内政|权谋)\]?\s*标记的\s*手牌', text)
    if m:
        marker_map = {'军事': 'military', '文化': 'culture', '内政': 'affair', '权谋': 'power'}
        return EffectStep(
            effect_type="play_card",
            params={"count": int(m.group(1)), "filter": {"exclude_marker": marker_map[m.group(2)]}},
            source_text=orig,
        )
    return None


def _parse_need_condition_to_play(text: str, orig: str) -> Optional[EffectStep]:
    """需要[X]等级>N，才能打出 — requirement for card playability"""
    m = re.search(r'需要\s*\[?(儒学|玄学|佛学)\]?\s*等级\s*[>＞]\s*(\d+)', text)
    if m:
        return EffectStep(
            effect_type="play_requirement",
            params={"culture": m.group(1), "threshold": int(m.group(2))},
            source_text=orig,
        )
    return None


def _parse_faction_label(text: str, orig: str) -> Optional[EffectStep]:
    """北方 / 东晋 — faction-specific action label"""
    if text.strip() in ('北方', '东晋'):
        return EffectStep(
            effect_type="faction_label",
            params={"faction": "north" if text.strip() == '北方' else 'jin'},
            source_text=orig,
        )
    return None


def _parse_convert_friendly_to_neutral(text: str, orig: str) -> Optional[EffectStep]:
    """将N个己方控制地点转化为中立地点（己方=自己控制，非友方）"""
    m = re.search(r'将\s*(\d+)\s*个\s*己方控制地点\s*转化\s*为\s*中立地点', text)
    if m:
        return EffectStep(
            effect_type="convert_own_to_neutral",
            params={"count": int(m.group(1))},
            source_text=orig,
        )
    return None


def _parse_both_lose_vp_with_variable(text: str, orig: str) -> Optional[EffectStep]:
    """司马家和宰辅各失去X vp → two targeted_effects"""
    m = re.search(r'(.+?)和(.+?)各失去\s*X\s*vp', text, re.IGNORECASE)
    if m:
        t1 = m.group(1).strip()  # e.g. "司马家"
        t2 = m.group(2).strip()  # e.g. "宰辅"
        return EffectStep(
            effect_type="each_lose_vp",
            params={
                "targets": [t1, t2],
                "variable": True,
            },
            source_text=orig,
        )
    return None


def _parse_change_to_player_control(text: str, orig: str) -> Optional[EffectStep]:
    """改为/转为 X 占据 → convert_to_neutral / convert_to_sima / convert"""
    m = re.search(r'(改为|转为)\s*(玩家|司马家|中立)\s*(占据|控制)?', text)
    if m:
        target = m.group(2)
        if target == '中立':
            return EffectStep(
                effect_type="convert_to_neutral",
                params={},
                source_text=orig,
            )
        if target == '司马家':
            return EffectStep(
                effect_type="convert_to_sima",
                params={},
                source_text=orig,
            )
        # "改为玩家占据" — generic convert (used in targeted_effect sub-effects)
        return EffectStep(
            effect_type="convert",
            params={},
            source_text=orig,
        )
    return None


def _parse_target_archive_friend(text: str, orig: str) -> Optional[EffectStep]:
    """该玩家存档被选择的幕僚 — handled by targeted_effect + archive_card"""
    return None


def _parse_free_fortify_friendly(text: str, orig: str) -> Optional[EffectStep]:
    """免费[加固]友方地点N次"""
    m = re.search(r'免费\s*\[?加固\]?\s*友方地点\s*(\d+)\s*次', text)
    if m:
        return EffectStep(
            effect_type="fortify",
            params={"free": True, "count": int(m.group(1)), "target": "friendly"},
            source_text=orig,
        )
    return None


def _parse_extra_action(text: str, orig: str) -> Optional[EffectStep]:
    """可以执行1个手牌行动 / 可以执行1个牌组行动 / 执行1个手牌行动"""
    m = re.search(r'(?:可以\s*)?(?:执行|获得)\s*(\d+)\s*个\s*(手牌|牌组|朝堂)\s*行动', text)
    if not m:
        # "获得1个朝堂行动" variant
        m = re.search(r'获得\s*(\d+)\s*个\s*朝堂行动', text)
    if m:
        is_hand = "手牌" in m.group(2)
        effect_type = "extra_hand_action" if is_hand else "extra_court_action"
        return EffectStep(
            effect_type=effect_type,
            params={"count": int(m.group(1)), "may": "可以" in text},
            source_text=orig,
        )
    return None


def _parse_steal_random_card(text: str, orig: str) -> Optional[EffectStep]:
    """随机抽取(他的)(1张)手牌"""
    m = re.search(r'随机抽取\s*(?:他的|其)?\s*(\d+)\s*张\s*手牌', text)
    if m:
        return EffectStep(
            effect_type="steal_random_card",
            params={"count": int(m.group(1))},
            source_text=orig,
        )
    return None


def _parse_give_card(text: str, orig: str) -> Optional[EffectStep]:
    """给予(其)(1张)(手)牌"""
    m = re.search(r'给予\s*(?:其|他)?\s*(\d+)\s*张\s*(手)?牌', text)
    if m:
        return EffectStep(
            effect_type="give_card",
            params={"count": int(m.group(1)), "from_hand": True},
            source_text=orig,
        )
    return None


def _parse_march_cost_modifier(text: str, orig: str) -> Optional[EffectStep]:
    """每回合前N次[进军]时，费用减1"""
    m = re.search(r'每回合前\s*(\d+)\s*次\s*\[?进军\]?\s*时\s*[,，]?\s*费用减\s*(\d+)', text)
    if m:
        return EffectStep(
            effect_type="march_cost_reduction",
            params={"per_turn_limit": int(m.group(1)), "amount": int(m.group(2))},
            source_text=orig,
        )
    return None


def _parse_region_reward_modifier(text: str, orig: str) -> Optional[EffectStep]:
    """区域奖励改为0/1vp"""
    m = re.search(r'区域奖励\s*改为\s*(\d+)\s*/\s*(\d+)\s*vp', text, re.IGNORECASE)
    if m:
        return EffectStep(
            effect_type="region_reward_override",
            params={"partial": int(m.group(1)), "full": int(m.group(2))},
            source_text=orig,
        )
    return None


def _parse_abandon_court_card(text: str, orig: str) -> Optional[EffectStep]:
    """弃置N张候选策略牌 — discard from court (not from hand)"""
    m = re.search(r'弃置\s*(\d+)\s*张\s*候选策略牌', text)
    if m:
        return EffectStep(
            effect_type="abandon_court_card",
            params={"count": int(m.group(1))},
            source_text=orig,
        )
    return None


def _parse_swap_troops(text: str, orig: str) -> Optional[EffectStep]:
    """交换X和Y的部队 — swap troops between two locations"""
    m = re.search(r'交换\s*(.+?)\s*和\s*(.+?)\s*的部队', text)
    if m:
        loc_a = m.group(1).strip()
        loc_b = m.group(2).strip()
        return EffectStep(
            effect_type="swap_troops",
            params={"location_a": loc_a, "location_b": loc_b},
            source_text=orig,
        )
    return None


def _parse_cost_reduction(text: str, orig: str) -> Optional[EffectStep]:
    """费用减N (standalone cost reduction)"""
    m = re.search(r'费用\s*减\s*(\d+)', text)
    if m:
        return EffectStep(
            effect_type="cost_reduction",
            params={"amount": int(m.group(1))},
            source_text=orig,
        )
    return None


# List of all pattern matchers in priority order
_STEP_PATTERNS = [
    _parse_gain_military,
    _parse_gain_vp,
    _parse_gain_vp_with_condition,
    _parse_gain_contribution_and_prestige,
    _parse_gain_prestige,
    _parse_gain_order,
    _parse_lose_military,
    _parse_lose_prestige,
    _parse_pay_military,
    _parse_pay_hand_card,
    _parse_draw_cards,
    _parse_other_discard,
    _parse_discard_cards,
    _parse_archive_this,
    _parse_archive_card,
    _parse_archive_friend,
    _parse_convert_location,
    _parse_convert_to_neutral,
    _parse_spread_culture,
    _parse_search,
    _parse_free_action,
    _parse_march_free,
    _parse_fortify,
    _parse_raise_order,
    _parse_lower_order,
    _parse_raise_culture_level,
    _parse_remove_culture_marker,
    _parse_flip_culture_marker,
    _parse_draft,
    _parse_supply_court,
    _parse_get_expedition,
    _parse_add_refugee,
    _parse_place_refugee,
    _parse_play_card,
    _parse_play_card_tag_filter,
    _parse_play_or_draft_card,
    _parse_raise_culture,
    _parse_remove_army,
    _parse_reshuffle_emperor,
    _parse_conditional_playable,
    _parse_need_condition_to_play,
    _parse_targeted_effect,
    _parse_faction_label,
    _parse_convert_friendly_to_neutral,
    _parse_both_lose_vp_with_variable,
    _parse_change_to_player_control,
    _parse_target_archive_friend,
    _parse_free_fortify_friendly,
    _parse_extra_action,
    _parse_steal_random_card,
    _parse_give_card,
    _parse_march_cost_modifier,
    _parse_region_reward_modifier,
    _parse_abandon_court_card,
    _parse_swap_troops,
    _parse_lose_contribution,
    _parse_cost_reduction,
]
