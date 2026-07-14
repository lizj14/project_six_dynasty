"""HumanPlayer — interactive command-line agent for human play testing.

Implements the GameAgent interface so a human can play the game
via terminal input while other players are controlled by AI.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from typing import Optional

from .interface import GameAgent, SetupContext, SetupDecision
from models.enums import FactionType, CardType, CultureType
from cards.effect_ast import AbilityType, EffectType


class HumanPlayer(GameAgent):
    """Interactive human player via command-line input.

    On each decision point, prints the current game state and available
    options, then waits for numeric input from the user.
    """

    def __init__(self, player_id: str = ""):
        self.player_id = player_id
        self._action_count = 0  # Track how many actions taken this turn
        self._request_early_quit = False  # Set to True by 'q' command

    @property
    def wants_early_quit(self) -> bool:
        """Check if the player requested early game termination."""
        return self._request_early_quit

    # ================================================================
    # Setup
    # ================================================================

    def setup_decision(self, ctx: SetupContext) -> SetupDecision:
        """Interactive hero, goal, and face-down card selection.

        Order: show hand → show hero options → pick hero → pick goals → pick face-down card + payment.
        """
        d = SetupDecision()
        faction_label = "北方" if ctx.faction == "north" else "东晋"

        print(f"\n{'='*60}")
        print(f"  {faction_label} — {ctx.player_id} 初设")
        print(f"{'='*60}")

        # ---- Step 1: Show hand cards first ----
        self._print_hand_for_setup(ctx)

        # ---- Step 2: Show goal options (before hero — goals influence hero choice) ----
        if ctx.goal_choices:
            print(f"\n可选目标:")
            for i, goal in enumerate(ctx.goal_choices):
                simple_cond = goal.get('simple_condition', '')
                full_cond = goal.get('full_condition', '')
                if len(simple_cond) > 50:
                    simple_cond = simple_cond[:47] + "..."
                print(f"  {i+1}. {goal['name']} (简单:{goal.get('simple_vp','?')}vp"
                      f" / 完整:{goal.get('full_vp','?')}vp)")
                if simple_cond:
                    print(f"     简单: {simple_cond}")
                if full_cond and len(full_cond) < 60:
                    print(f"     完整: {full_cond}")

        # ---- Step 3: Show hero options ----
        print(f"\n可选英雄:")
        for i, hero in enumerate(ctx.hero_choices):
            prestige = hero.get("initial_prestige", 0)
            contrib = hero.get("initial_contribution", 0)
            effect = hero.get("effect_text", "")
            so = hero.get("start_order", 0)
            if len(effect) > 60:
                effect = effect[:57] + "..."
            print(f"  {i+1}. {hero['name']} (先动:{so}  初始威望:{prestige}  功绩:{contrib})")
            if effect:
                print(f"     {effect}")
        d.hero_index = self._input_index("选择英雄", len(ctx.hero_choices))
        chosen_hero = ctx.hero_choices[d.hero_index]['name']
        print(f"     → 选择了「{chosen_hero}」")

        # ---- Step 4: Goals selection (Jin only) ----
        if ctx.goal_choices:
            d.public_goal_index = self._input_index("选择公开目标", len(ctx.goal_choices))
            print(f"     → 公开目标: 「{ctx.goal_choices[d.public_goal_index]['name']}」")

            if len(ctx.goal_choices) >= 2:
                d.secret_goal_index = self._input_index(
                    "选择秘密目标", len(ctx.goal_choices),
                    default=d.public_goal_index)
                if d.secret_goal_index != d.public_goal_index:
                    print(f"     → 秘密目标: 「{ctx.goal_choices[d.secret_goal_index]['name']}」")
                else:
                    print(f"     → 秘密目标与公开目标相同")
            else:
                d.secret_goal_index = d.public_goal_index

        # ---- Step 5: Face-down card with cost-aware payment ----
        if ctx.hand_cards:
            self._pick_face_down_card(ctx, d)
        else:
            d.face_down_card_index = 0
            d.payment_indices = []

        print(f"\n  初设完成。等待其他玩家...\n")
        return d

    def _print_hand_for_setup(self, ctx: SetupContext):
        """Print the player's hand cards with costs at setup time."""
        print(f"\n当前手牌 ({len(ctx.hand_cards)} 张):")
        costs = ctx.hand_card_costs if hasattr(ctx, 'hand_card_costs') and ctx.hand_card_costs else []
        for i, name in enumerate(ctx.hand_cards):
            cost = costs[i] if i < len(costs) else "?"
            print(f"  {i+1}. {name} (费用: {cost})")

    def _pick_face_down_card(self, ctx: SetupContext, d: SetupDecision):
        """Let the player pick which card to play face-down and which cards to use as payment."""
        costs = ctx.hand_card_costs if hasattr(ctx, 'hand_card_costs') and ctx.hand_card_costs else []
        n = len(ctx.hand_cards)

        print(f"\n暗置打出 — 选择1张牌暗置打出，其余手牌中选N张作为费用:")

        # Choose the face-down card
        d.face_down_card_index = self._input_index("选择暗置打出的牌", n)
        chosen_cost = costs[d.face_down_card_index] if d.face_down_card_index < len(costs) else 0
        chosen_name = ctx.hand_cards[d.face_down_card_index]
        print(f"     → 暗置打出「{chosen_name}」(费用: {chosen_cost})")

        # Choose payment cards from remaining hand
        remaining = [i for i in range(n) if i != d.face_down_card_index]
        if chosen_cost > 0 and remaining:
            print(f"\n  需要支付 {chosen_cost} 张手牌作为费用。")
            print(f"  可选支付牌:")
            for i in remaining:
                c = costs[i] if i < len(costs) else "?"
                print(f"    {i+1}. {ctx.hand_cards[i]} (费用: {c})")

            d.payment_indices = []
            pay_i = 0
            max_retries = 5  # After 5 failed attempts, auto-fill
            retries = 0
            print(f"    (输入 0 跳过支付选择，由系统自动填充)")
            while pay_i < chosen_cost and retries < max_retries:
                if not remaining:
                    break
                idx = self._input_index(
                    f"选择支付的牌 ({pay_i+1}/{chosen_cost})",
                    n, allow_zero=True)
                if idx == -2:  # Special: skip (see _input_index modification)
                    break
                if idx in remaining and idx not in d.payment_indices:
                    d.payment_indices.append(idx)
                    remaining.remove(idx)
                    pay_i += 1
                elif idx in d.payment_indices:
                    print(f"    [!] 已选过该牌，请重新选择")
                    retries += 1
                else:
                    print(f"    [!] 不能选择暗置打出的牌本身，请重新选择")
                    retries += 1
            if d.payment_indices:
                payment_names = [ctx.hand_cards[i] for i in d.payment_indices if i < n]
                print(f"     → 已选支付: {' '.join(payment_names)} ({len(d.payment_indices)}/{chosen_cost})")
                if len(d.payment_indices) < chosen_cost:
                    print(f"     (剩余 {chosen_cost - len(d.payment_indices)} 张由系统自动填充)")
            elif not d.payment_indices:
                print(f"     → 支付: (由系统自动填充)")
        elif chosen_cost == 0:
            print(f"     → 该牌费用为0，无需支付")
            d.payment_indices = []
        else:
            d.payment_indices = []

    # ================================================================
    # Turn — iterative action decision (two-level menu)
    # ================================================================

    def decide_action(self, state: "GameState",
                      available_actions: list) -> Optional["GameAction"]:
        """Display available actions in a two-level menu.

        Level 1: Choose action category (court/quick/hand/activate)
        Level 2: Choose specific action within category
        Then choose payment/location details if needed.

        Special commands:
          q/Q = quit game early and save logs
          empty input = re-display
        """
        self._action_count += 1

        # Print state summary
        self._print_state_summary(state)

        if not available_actions:
            print("  无可用行动。按 Enter 结束回合...")
            input()
            self._action_count = 0
            return None

        # Group actions by category
        groups = self._group_actions(available_actions, state)

        while True:
            # === Level 1: Choose category ===
            category_names = list(groups.keys())
            print(f"\n  ┌─ 选择行动类别 ──────────────────────────────")
            cat_idx = 1
            cat_map = {}  # number → category_name
            for name in category_names:
                count = len(groups[name])
                print(f"  │ {cat_idx}. {name} ({count}个可选)")
                cat_map[cat_idx] = name
                cat_idx += 1
            print(f"  │ 0. 结束行动（空过）")
            print(f"  │ q. 提前终止游戏（保存日志）")
            print(f"  └──────────────────────────────────────────────")

            raw_choice = self._input_choice_raw(len(cat_map))
            if raw_choice is None:
                self._action_count = 0
                return None  # 0 = pass
            if raw_choice == -1:
                # q = quit game early
                self._request_early_quit = True
                self._action_count = 0
                return None

            cat_name = cat_map[raw_choice]
            cat_actions = groups[cat_name]

            # === Level 2: Choose specific action ===
            while True:
                print(f"\n  ┌─ 【{cat_name}】─────────────────────")
                action_list = []
                for i, action in enumerate(cat_actions):
                    preview = self._describe_action_preview(action, state)
                    cost = action.cost_description(state)
                    cost_str = f" — 费用: {cost}" if cost and cost not in ("?", "", None) else ""
                    print(f"  │ {i+1:2d}. {preview}{cost_str}")
                    action_list.append(action)
                print(f"  │  0. 返回上级")
                print(f"  └──────────────────────────────────────────────")

                action_choice = self._input_choice(len(action_list))
                if action_choice == 0:
                    break  # Back to category menu

                selected_action = action_list[action_choice - 1]

                # === Level 3: Adjust payment/location if needed ===
                final_action = self._adjust_action_details(selected_action, state)
                if final_action is None:
                    continue  # User cancelled, stay at level 2
                return final_action

    # ================================================================
    # Choice methods
    # ================================================================

    def make_choice(self, state: "GameState", prompt: dict) -> int:
        """Choose from effect options."""
        options = prompt.get("options", [])
        title = prompt.get("title", "选择一个选项")
        print(f"\n  {title}:")
        for i, opt in enumerate(options):
            label = opt.get("label", str(opt)) if isinstance(opt, dict) else str(opt)
            print(f"    {i+1}. {label}")
        return self._input_index("选择", len(options))

    def choose_discards(self, state: "GameState", hand_cards: list[str],
                        count: int) -> list[int]:
        """Choose cards to discard for hand limit.

        Shows hand cards, accepts numbered selections. Enter 0 to auto-select
        (discards from end of hand).
        """
        print(f"\n  手牌超出上限，需要弃 {count} 张:")
        for i, name in enumerate(hand_cards):
            print(f"    {i+1}. {name}")
        print(f"    (输入 0 自动选择末尾 {count} 张丢弃)")

        chosen = []
        for discard_i in range(count):
            idx = self._input_index(
                f"选择要弃的第{discard_i+1}张牌 (剩余{count - discard_i}张)",
                len(hand_cards), allow_zero=True)
            if idx == -2:  # Skip / auto-select
                break
            if idx not in chosen:
                chosen.append(idx)
            else:
                print(f"    [!] 已选过该牌，请重新选择")

        # If not enough chosen, auto-fill from end
        if len(chosen) < count:
            remaining = [i for i in range(len(hand_cards)) if i not in chosen]
            auto = remaining[-(count - len(chosen)):] if remaining else []
            chosen.extend(auto)
            if auto:
                auto_names = [hand_cards[i] for i in auto]
                print(f"    自动丢弃: {' '.join(auto_names)}")

        return chosen

    def select_target(self, state: "GameState", prompt: dict) -> Optional[str]:
        """Select a target from options."""
        options = prompt.get("options", [])
        title = prompt.get("title", prompt.get("message", "选择一个目标"))
        prompt_type = prompt.get("type", "")
        # Add context about what kind of selection this is
        type_labels = {
            "spread_culture_requested": "传播文化",
            "convert_requested": "转化地点",
            "march_requested": "进军",
            "occupy_requested": "占据",
            "fortify_requested": "加固",
            "archive_card": "存档",
            "draft_card": "征发",
            "player": "选择玩家",
            "location": "选择地点",
            "choose_effect": "效果选择",
        }
        context = type_labels.get(prompt_type, "")
        if context:
            print(f"\n  [{context}] {title}:")
        else:
            print(f"\n  {title}:")
        for i, opt in enumerate(options):
            if isinstance(opt, dict):
                print(f"    {i+1}. {opt.get('label', opt.get('id', str(opt)))}")
            else:
                print(f"    {i+1}. {opt}")
        if not options:
            print("    (无可用目标)")
            return None
        idx = self._input_index("选择目标", len(options))
        opt = options[idx]
        if isinstance(opt, dict):
            return opt.get("id", str(opt))
        return str(opt)

    # ================================================================
    # State summary display
    # ================================================================

    def _print_state_summary(self, state: "GameState"):
        """Print a summary of the player's current state before each action.

        Shows hand cards indexed (with cost/type/effect), military, VP,
        prestige/contribution/order (Jin), controlled locations, and staff.
        """
        player = state.get_player(self.player_id)
        if not player:
            return

        faction_label = "北方" if player.faction == FactionType.NORTH else "东晋"

        # ===== Top-line stats =====
        print(f"\n{'━'*60}")
        print(f"  第{state.round}回合 | [{faction_label}] {self.player_id}")
        print(f"  VP: {player.vp}  |  军力: {player.military}  |  "
              f"手牌: {len(player.hand)}张", end="")
        if player.faction == FactionType.JIN:
            print(f"  |  威望: {player.prestige}  |  功绩: {player.contribution}  |  顺位: {player.order}")
        else:
            print()
        print(f"  部队: {player.army_placed_count}放置 / {player.army_reserve_count}储备", end="")
        # Own controlled locations
        own_locs = state.get_own_locations(self.player_id)
        loc_str = " ".join(own_locs) if own_locs else "(无)"
        print(f"  |  占据: {loc_str}")
        # Staff area
        if player.staff_area:
            staff_str = "  ".join(f"[{c.name}]" for c in player.staff_area)
            print(f"  幕僚: {staff_str}")
        if player.history_area:
            history_str = " ".join(c.name for c in player.history_area)
            print(f"  史书: {history_str}")

        # ===== Hand cards detail =====
        if player.hand:
            print(f"  ┌─ 手牌详情 ({len(player.hand)}张) ──────────────────────────────")
            for i, card in enumerate(player.hand):
                d = card.definition
                cost_str = f"费用{d.cost}" if d.cost > 0 else "0费"
                # Card type tag
                if card.is_friend:
                    type_tag = "幕僚"
                elif card.card_type == CardType.EVENT:
                    type_tag = "事件"
                elif card.card_type == CardType.STRATEGY:
                    type_tag = "策略"
                else:
                    type_tag = d.card_type.value if hasattr(d.card_type, 'value') else str(d.card_type)
                # Brief effect description from parsed effect
                effect_brief = self._brief_effect(d)
                line = f"  │ {i+1}. [{cost_str} {type_tag}] {card.name}"
                if effect_brief:
                    line += f" — {effect_brief}"
                print(line)
            print(f"  └──────────────────────────────────────────────────")
        else:
            print(f"  手牌: (空)")

        print(f"{'━'*60}")

    @staticmethod
    def _brief_effect(definition) -> str:
        """Extract a one-line summary from a card's parsed effect."""
        parsed = definition.parsed_effect
        if not parsed:
            return ""
        parts = []
        for block in parsed.blocks:
            ab = block.ability_type or ""
            et = block.effect_type or ""
            if et == "gain":
                for step in block.steps:
                    p = step.params
                    res_type = p.get("resource", "")
                    amount = p.get("amount", "?")
                    if res_type == "military":
                        parts.append(f"+{amount}军力")
                    elif res_type == "vp":
                        parts.append(f"+{amount}VP")
                    elif res_type == "order":
                        parts.append(f"+{amount}顺位")
                    elif res_type:
                        parts.append(f"+{amount}{res_type}")
            elif et == "draw":
                parts.append("摸牌")
            elif et == "spread_culture":
                culture = ""
                for step in block.steps:
                    c = step.params.get("culture", "")
                    if c:
                        culture_map = {"confucianism": "儒学", "taoism": "玄学", "buddhism": "佛学"}
                        culture = culture_map.get(c, c)
                parts.append(f"传播{culture}" if culture else "传播文化")
            elif et == "march":
                parts.append("进军")
            elif et == "fortify":
                parts.append("加固")
            elif et == "convert":
                parts.append("转化")
            elif et == "occupy":
                parts.append("占据")
            elif et == "draft":
                parts.append("征发")
            elif et == "levy":
                parts.append("征发")
            elif et == "archive":
                parts.append("存档")
            elif et == "search":
                parts.append("检索")
            elif et == "activate_effect":
                parts.append("激活效果")
            elif ab == "active":
                parts.append("[主动技能]")
            elif ab == "passive":
                parts.append("[被动技能]")
            if len(parts) >= 3:
                break
        return " | ".join(parts[:3])

    # ================================================================
    # Action result display (called via engine callback)
    # ================================================================

    @staticmethod
    def print_action_result(state: "GameState", player_id: str,
                            action: "GameAction",
                            result: "ActionResult"):
        """Print the result of an executed action to the terminal.

        Designed to be used as the engine's on_action_executed callback.
        Shows what happened after each action: VP changes, military changes,
        card draws, etc.
        """
        atype = getattr(action, 'action_type', '?')
        player = state.get_player(player_id)
        if not result or not result.events:
            return

        for evt in result.events:
            t = evt.get("type", "")
            # Resource changes
            if t == "gain_vp":
                print(f"     ↳ +{evt.get('amount', '?')} VP")
            elif t == "lose_vp":
                print(f"     ↳ -{evt.get('amount', '?')} VP")
            elif t == "gain_military":
                print(f"     ↳ +{evt.get('amount', '?')} 军力")
            elif t == "pay_military":
                print(f"     ↳ 支付 {evt.get('amount', '?')} 军力")
            elif t == "recruit":
                card_name = evt.get("discarded", "?")
                print(f"     ↳ 弃「{card_name}」→ +1 军力")
            elif t == "draw":
                print(f"     ↳ 摸牌: 「{evt.get('card', '?')}」")
            elif t == "friend_played":
                print(f"     ↳ 幕僚入场: 「{evt.get('card', '?')}」")
            elif t == "strategy_played":
                print(f"     ↳ 策略牌进入国家牌库")
            elif t == "event_played":
                print(f"     ↳ 事件结算")
            elif t == "staff_replaced":
                print(f"     ↳ 替换幕僚: 「{evt.get('card', '?')}」"
                      f" → 「{evt.get('replaced_by', '?')}」")
            elif t == "archive_card":
                print(f"     ↳ 存档: 「{evt.get('card', '?')}」")
            elif t == "raise_order":
                new_order = evt.get("new_order", "?")
                print(f"     ↳ 顺位提升至 {new_order}")
            elif t == "spread_culture_vp":
                print(f"     ↳ 传播文化 +{evt.get('vp', '?')} VP")
            elif t == "activate_effect":
                print(f"     ↳ 激活「{evt.get('card', '?')}」")
            elif t == "raise_prestige":
                print(f"     ↳ +{evt.get('amount', '?')} 威望")
            elif t == "raise_contribution":
                print(f"     ↳ +{evt.get('amount', '?')} 功绩")
            elif t == "fortify_requested":
                target = evt.get("target", "?")
                if evt.get("skipped"):
                    print(f"     ↳ 加固→{target} (跳过: {evt.get('reason', '')})")
                else:
                    print(f"     ↳ 加固→{target}")
            elif t == "convert_requested":
                target = evt.get("target", "?")
                if not evt.get("skipped"):
                    print(f"     ↳ 转化→{target}")
            elif t == "march_requested":
                if evt.get("skipped"):
                    print(f"     ↳ 进军 (跳过: {evt.get('reason', '')})")
            elif t == "occupy_requested":
                if evt.get("skipped"):
                    print(f"     ↳ 占据 (跳过: {evt.get('reason', '')})")
            elif t == "spread_culture_requested":
                if evt.get("skipped"):
                    print(f"     ↳ 传播文化 (跳过: {evt.get('reason', '')})")
            elif t == "choose":
                print(f"     ↳ 选择了选项 {evt.get('chosen_label', '?')}")
            elif t == "extra_action_granted":
                action_type = evt.get("action_type", "?")
                print(f"     ↳ 获得额外行动: {action_type}")
            elif t == "game_end_trigger":
                print(f"     ↳ ⚠ 游戏结束触发: {evt.get('reason', '')}")

    # ================================================================
    # Action grouping and display
    # ================================================================

    def _group_actions(self, available_actions: list,
                       state: "GameState") -> dict[str, list]:
        """Group actions by category for organized display."""
        groups = {
            "快速行动": [],
            "手牌行动": [],
            "牌组行动": [],
            "公共行动": [],
            "激活效果": [],
            "其他行动": [],
        }

        quick_types = {"march", "occupy", "fortify", "draw", "recruit"}

        for action in available_actions:
            atype = getattr(action, 'action_type', '')
            if atype in quick_types:
                groups["快速行动"].append(action)
            elif atype == "play_card":
                groups["手牌行动"].append(action)
            elif atype == "court_action":
                groups["牌组行动"].append(action)
            elif atype == "play_public_card":
                groups["公共行动"].append(action)
            elif atype == "activate_effect":
                groups["激活效果"].append(action)
            else:
                groups["其他行动"].append(action)

        # Remove empty groups
        return {k: v for k, v in groups.items() if v}

    def _describe_action_preview(self, action,
                                  state: "GameState") -> str:
        """Generate a human-readable preview description of an action.

        Similar to game_logger.describe_action() but designed for pre-execution
        preview (doesn't require ActionResult).
        """
        atype = getattr(action, 'action_type', '?')
        player = state.get_player(self.player_id)

        # --- Quick actions ---
        if atype == "march":
            target = getattr(action, 'target_location', '?')
            cost = 3
            if hasattr(action, '_calculate_cost'):
                try:
                    cost = action._calculate_cost(state)
                except Exception:
                    pass
            return f"进军 → {target}"

        elif atype == "occupy":
            target = getattr(action, 'target_location', '?')
            return f"占据 → {target}"

        elif atype == "fortify":
            target = getattr(action, 'target_location', '?')
            return f"加固 → {target}"

        elif atype == "draw":
            return "摸牌 (快速行动)"

        elif atype == "recruit":
            idx = getattr(action, 'card_to_discard_index', -1)
            card_name = "?"
            if player and 0 <= idx < len(player.hand):
                card_name = player.hand[idx].name
            return f"征募: 弃「{card_name}」换1军力"

        # --- Card actions ---
        elif atype == "play_card":
            idx = getattr(action, 'card_index', -1)
            payment_indices = getattr(action, 'payment_indices', [])
            if player and 0 <= idx < len(player.hand):
                card = player.hand[idx]
                card_name = card.name
                cost = card.cost
                ctype = card.card_type
                type_label = _card_type_label(ctype)
                effect_summary = _summarize_card_effects(card.definition)

                # Payment card names
                payment_names = []
                for pi in payment_indices:
                    if 0 <= pi < len(player.hand) and pi != idx:
                        payment_names.append(player.hand[pi].name)

                desc = f"打出「{card_name}」({type_label}, 费用{cost})"
                if effect_summary:
                    desc += f" [{effect_summary}]"
                if payment_names:
                    desc += f"\n       支付: {' '.join(payment_names)}"
                if card.is_friend and not player.can_play_friend():
                    ri = getattr(action, 'replace_staff_index', 0)
                    if 0 <= ri < len(player.staff_area):
                        desc += f"\n       替换: {player.staff_area[ri].name}"
                return desc
            return f"打出 (手牌)"

        elif atype == "court_action":
            cid = getattr(action, 'card_id', '')
            court = state.get_court_cards(self.player_id)
            for card in court:
                if card.definition.card_id == cid:
                    defn = card.definition
                    effect_summary = _summarize_strategy_effects(defn)
                    desc = f"牌组行动: 「{card.name}」"
                    if effect_summary:
                        desc += f" [{effect_summary}]"
                    # Show block-level costs
                    costs_desc = _format_block_costs(defn)
                    if costs_desc:
                        desc += f"\n       费用: {costs_desc}"
                    return desc
            return f"牌组行动 (id={cid})"

        elif atype == "play_public_card":
            cid = getattr(action, 'card_id', '')
            payment_indices = getattr(action, 'payment_indices', [])
            for card in state.public_action_pool:
                if card.definition.card_id == cid:
                    defn = card.definition
                    effect_summary = _summarize_strategy_effects(defn)
                    cost = defn.cost or 0
                    desc = f"公共行动: 「{card.name}」(费用{cost})"
                    if effect_summary:
                        desc += f" [{effect_summary}]"
                    payment_names = []
                    if player:
                        for pi in payment_indices:
                            if 0 <= pi < len(player.hand):
                                payment_names.append(player.hand[pi].name)
                    if payment_names:
                        desc += f"\n       支付: {' '.join(payment_names)}"
                    costs_desc = _format_block_costs(defn)
                    if costs_desc:
                        desc += f"\n       额外费用: {costs_desc}"
                    return desc
            return f"公共行动 (id={cid})"

        # --- Special actions ---
        elif atype == "convert":
            target = getattr(action, 'target_location', '?')
            free = getattr(action, 'free', False)
            cost_label = "免费" if free else "4军力"
            return f"转化 → {target} ({cost_label})"

        elif atype == "archive":
            idx = getattr(action, 'card_index', -1)
            source = getattr(action, 'source', 'hand')
            if source == "hand" and player and 0 <= idx < len(player.hand):
                return f"存档: 「{player.hand[idx].name}」"
            cid = getattr(action, 'card_id', '')
            return f"存档 ({source}, id={cid})"

        elif atype == "spread_culture":
            culture = getattr(action, 'culture_type', '?')
            region = getattr(action, 'target_region', '?')
            culture_label = {"confucianism": "儒学", "taoism": "玄学",
                            "buddhism": "佛学"}.get(culture, culture)
            return f"传播文化: {culture_label} → {region}"

        elif atype == "search":
            st = getattr(action, 'search_type', '?')
            cnt = getattr(action, 'search_count', 1)
            return f"检索: {st} x{cnt}"

        elif atype == "levy":
            cid = getattr(action, 'card_id', '')
            court = state.get_court_cards(self.player_id)
            for card in court:
                if card.definition.card_id == cid:
                    defn = card.definition
                    return (f"征发: 「{card.name}」 "
                            f"(+{defn.resource_option_army}军/"
                            f"+{defn.resource_option_vp}vp)")
            return f"征发 (id={cid})"

        elif atype == "raise_order":
            return "提高行动顺位"

        elif atype == "lower_order":
            target = getattr(action, 'target_player_id', '?')
            return f"降低 {target} 顺位"

        elif atype == "activate_effect":
            card_id = getattr(action, 'card_id', '')
            bi = getattr(action, 'block_index', 0)
            ci = getattr(action, 'choice_index', 0)

            # Find the card
            card = None
            if player:
                if player.hero and player.hero.definition.card_id == card_id:
                    card = player.hero
                else:
                    for c in player.staff_area:
                        if c.definition.card_id == card_id:
                            card = c
                            break

            if card:
                defn = card.definition
                parsed = defn.parsed_effect
                active_blocks = [b for b in parsed.blocks
                               if b.ability_type == AbilityType.ACTIVE] if parsed else []
                effect_desc = ""
                costs_desc = ""
                if active_blocks and bi < len(active_blocks):
                    block = active_blocks[bi]
                    costs_desc = _format_block_costs_from_blocks([block])
                    steps = (block.choice_options[ci]
                            if block.choice_options and ci < len(block.choice_options)
                            else block.steps)
                    effect_desc = _summarize_steps(steps)

                desc = f"激活「{card.name}」"
                if effect_desc:
                    desc += f" [{effect_desc}]"
                if costs_desc:
                    desc += f"\n       费用: {costs_desc}"
                return desc
            return f"激活效果 (id={card_id})"

        # Fallback
        return f"{atype}"

    # ================================================================
    # Action detail adjustment (payment/march target, etc.)
    # ================================================================

    def _adjust_action_details(self, action,
                                state: "GameState") -> Optional["GameAction"]:
        """Let player adjust payment/location details of a chosen action.

        For card play actions with cost > 0, let player choose which specific
        cards to use as payment. For march/occupy/fortify, confirm target.

        Returns the (possibly modified) action, or None if cancelled.
        """
        atype = getattr(action, 'action_type', '')
        player = state.get_player(self.player_id)
        if not player:
            return action

        # --- Card play actions: let player choose payment cards ---
        if atype in ("play_card", "play_public_card"):
            card_index = getattr(action, 'card_index', -1)
            payment_indices = list(getattr(action, 'payment_indices', []))

            if atype == "play_card":
                if card_index < 0 or card_index >= len(player.hand):
                    return action
                card = player.hand[card_index]
                card_name = card.name
                cost = card.cost
            else:  # play_public_card
                card = None
                for c in state.public_action_pool:
                    if c.definition.card_id == getattr(action, 'card_id', ''):
                        card = c
                        break
                if card is None:
                    return action
                card_name = card.name
                cost = card.cost

            if cost == 0:
                return action  # No payment needed

            # Show current auto-filled payment (exclude the card being played)
            payment_names = []
            for pi in payment_indices:
                if 0 <= pi < len(player.hand) and pi != card_index:
                    payment_names.append(player.hand[pi].name)
            print(f"\n  ┌─ 调整支付 ───────────────────────────────────")
            print(f"  │ 要打出「{card_name}」(费用: {cost})")
            print(f"  │ 自动选择的支付牌: {' '.join(payment_names) if payment_names else '(无)'}")
            print(f"  │")
            print(f"  │ 当前手牌 (不可选择要打出的牌本身):")
            for i, c in enumerate(player.hand):
                if i == card_index:
                    print(f"  │   {i+1}. {c.name} (费用:{c.cost}) ← 要打出的牌")
                else:
                    marker = " ←自动选" if i in (payment_indices or []) else ""
                    print(f"  │   {i+1}. {c.name} (费用:{c.cost}){marker}")
            print(f"  │")
            print(f"  │ 请输入 {cost} 张牌作为支付 (输入编号，空格分隔)")
            print(f"  │ 直接回车 = 使用自动选择, 0 = 返回")

            while True:
                try:
                    raw = input(f"  │ 支付牌 > ").strip()
                    if not raw:
                        # Accept auto-filled payment
                        return action
                    if raw == "0":
                        return None  # Cancel

                    parts = raw.split()
                    new_payment = []
                    seen = set()
                    valid = True
                    for p in parts:
                        try:
                            val = int(p)
                            if 1 <= val <= len(player.hand):
                                idx = val - 1
                                if idx == card_index and atype == "play_card":
                                    print(f"  │ [!] 不能选择要打出的牌本身 (编号{val})")
                                    valid = False
                                    break
                                if idx in seen:
                                    print(f"  │ [!] 重复选择编号{val}")
                                    valid = False
                                    break
                                new_payment.append(idx)
                                seen.add(idx)
                            else:
                                print(f"  │ [!] 编号 {p} 超出范围 (1-{len(player.hand)})")
                                valid = False
                                break
                        except ValueError:
                            print(f"  │ [!] '{p}' 不是有效数字")
                            valid = False
                            break

                    if not valid:
                        continue

                    if len(new_payment) != cost:
                        print(f"  │ [!] 需要 {cost} 张支付牌，你选了 {len(new_payment)} 张")
                        continue

                    # Belt-and-suspenders: ensure card being played is NOT in payment
                    if atype == "play_card" and card_index in new_payment:
                        print(f"  │ [!] 不能选择要打出的牌本身作为支付 (编号{card_index+1})")
                        continue

                    # Create new action with updated payment
                    if atype == "play_card":
                        from engine.actions.card_actions import PlayCardAction
                        new_action = PlayCardAction(
                            player_id=self.player_id,
                            card_index=card_index,
                            payment_indices=new_payment,
                        )
                        if hasattr(action, 'replace_staff_index'):
                            new_action.replace_staff_index = action.replace_staff_index
                        new_payment_names = [player.hand[i].name for i in new_payment]
                        print(f"  │ → 支付: {' '.join(new_payment_names)}")
                        return new_action
                    else:
                        from engine.actions.card_actions import PublicCardAction
                        new_action = PublicCardAction(
                            player_id=self.player_id,
                            card_id=getattr(action, 'card_id', ''),
                            payment_indices=new_payment,
                        )
                        new_payment_names = [player.hand[i].name for i in new_payment]
                        print(f"  │ → 支付: {' '.join(new_payment_names)}")
                        return new_action

                except (EOFError, KeyboardInterrupt):
                    print("\n  输入中断，退出")
                    sys.exit(0)

        # --- March/Occupy/Fortify: confirm target ---
        elif atype in ("march", "occupy", "fortify"):
            target = getattr(action, 'target_location', '?')
            print(f"\n  ┌─ 确认目标 ───────────────────────────────────")
            cost = action.cost_description(state)
            cost_str = f" — 费用: {cost}" if cost and cost not in ("?", "") else ""
            action_label = {"march": "进军", "occupy": "占据", "fortify": "加固"}.get(atype, atype)
            print(f"  │ {action_label} → {target}{cost_str}")
            while True:
                try:
                    raw = input(f"  │ 确认? (y/n, 默认y): ").strip().lower()
                    if raw in ("", "y", "yes"):
                        return action
                    elif raw in ("n", "no"):
                        return None
                    else:
                        print(f"  │ 请输入 y 或 n")
                except (EOFError, KeyboardInterrupt):
                    print("\n  输入中断，退出")
                    sys.exit(0)

        return action

    # ================================================================
    # Input helpers
    # ================================================================

    @staticmethod
    def _input_index(prompt: str, max_val: int, default: int = -1,
                     allow_zero: bool = False) -> int:
        """Get a 0-based index from the user (displayed as 1-based).

        If allow_zero=True, input 0 returns -2 (caller interprets as "skip").
        """
        default_hint = f" [{default+1}]" if default >= 0 else ""
        zero_hint = ", 0=跳过" if allow_zero else ""
        while True:
            try:
                raw = input(f"  {prompt} (1-{max_val}{zero_hint}){default_hint}: ").strip()
                if not raw and default >= 0:
                    return default
                if not raw:
                    continue
                val = int(raw)
                if allow_zero and val == 0:
                    return -2
                if 1 <= val <= max_val:
                    return val - 1
                print(f"    [!] 请输入 1-{max_val} 之间的数字")
            except ValueError:
                print(f"    [!] 请输入有效数字")
            except (EOFError, KeyboardInterrupt):
                print("\n  输入中断，退出")
                sys.exit(0)

    @staticmethod
    def _input_choice(max_val: int) -> int:
        """Get a choice number from the user. 0 means pass."""
        while True:
            try:
                raw = input(f"\n  选择 > ").strip()
                if not raw:
                    continue
                val = int(raw)
                if 0 <= val <= max_val:
                    return val
                print(f"    [!] 请输入 0-{max_val} 之间的数字")
            except ValueError:
                print(f"    [!] 请输入有效数字")
            except (EOFError, KeyboardInterrupt):
                print("\n  输入中断，退出")
                sys.exit(0)

    @staticmethod
    def _input_choice_raw(max_val: int) -> Optional[int]:
        """Get a choice from user. Returns int for valid choice, None for 0, -1 for 'q'."""
        while True:
            try:
                raw = input(f"\n  选择 > ").strip()
                if not raw:
                    continue
                if raw.lower() == 'q':
                    return -1
                val = int(raw)
                if val == 0:
                    return None  # 0 = pass/back
                if 1 <= val <= max_val:
                    return val
                print(f"    [!] 请输入 0-{max_val} 之间的数字，或 q 退出")
            except ValueError:
                print(f"    [!] 请输入有效数字，或 q 退出")
            except (EOFError, KeyboardInterrupt):
                print("\n  输入中断，退出")
                sys.exit(0)


# ================================================================
# Helper functions for card effect summaries
# ================================================================

def _card_type_label(card_type) -> str:
    """Chinese label for card type."""
    if card_type is None:
        return "?"
    labels = {
        "friend": "幕僚",
        "strategy": "策略",
        "event": "事件",
        "hero": "英雄",
        "mechanism": "强制事件",
    }
    return labels.get(card_type.value if hasattr(card_type, 'value') else str(card_type),
                      str(card_type))


def _summarize_card_effects(card_def) -> str:
    """Extract a one-line effect summary from a card definition.

    Covers enter/active/passive blocks for play_card preview.
    """
    parsed = card_def.parsed_effect
    if not parsed:
        return ""

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


def _summarize_strategy_effects(card_def) -> str:
    """Extract effect summary specifically from strategy_action blocks."""
    parsed = card_def.parsed_effect
    if not parsed:
        return ""

    parts = []
    for block in parsed.blocks:
        if block.ability_type == AbilityType.STRATEGY_ACTION:
            steps_summary = _summarize_steps(block.steps)
            if steps_summary:
                parts.append(steps_summary)
            # Also check choice_options
            if block.choice_options:
                # Show first option as example
                for opt_steps in block.choice_options[:1]:
                    opt_summary = _summarize_steps(opt_steps)
                    if opt_summary:
                        parts.append(f"选项:{opt_summary}")

    return "，".join(parts) if parts else ""


def _summarize_steps(steps) -> str:
    """Summarize a list of effect steps into a concise string."""
    if not steps:
        return ""

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
            # Generic: use effect type name
            et_str = et.value if hasattr(et, 'value') else str(et)
            parts.append(et_str)

    return "，".join(parts) if parts else ""


def _format_block_costs(card_def) -> str:
    """Extract block-level costs from strategy_action blocks."""
    parsed = card_def.parsed_effect
    if not parsed:
        return ""

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
        "on_order_change": "顺位变化时",
        "on_end_game": "游戏结束时",
        "on_region_reward": "区控奖励时",
    }
    return labels.get(trigger, trigger)
