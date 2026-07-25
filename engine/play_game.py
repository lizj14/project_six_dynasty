"""Interactive game: human player vs HeuristicAI opponents.

Usage:
    python play_game.py                    # Interactive faction selection
    python play_game.py north              # Play as 北方
    python play_game.py jin                # Play as 东晋 player 1
    python play_game.py jin_1              # Play as 东晋 player 1
    python play_game.py jin_2              # Play as 东晋 player 2
    python play_game.py jin_3              # Play as 东晋 player 3

    # Custom initial hand (for testing specific cards):
    python play_game.py jin --preset jin_1=慧远,尊奉江东
    python play_game.py north --preset north=司马道子,流民四起
    python play_game.py jin -p jin_1=慧远,还都洛阳 -p jin_2=道安
"""

import os
import sys
import time

# Force UTF-8 output on Windows (Git Bash may default to GBK)
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stdin.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(__file__))

from config.version import Version
from ai.heuristic_ai import HeuristicAI
from ai.human_player import HumanPlayer
from engine.game import GameEngine
from engine.game_logger import GameLogger, describe_action

# Valid faction choices
FACTION_CHOICES = {
    "north": "北方",
    "jin": "东晋",
}

# When human plays Jin, assign them to this slot
# (other Jin slots are filled by AI)
HUMAN_JIN_SLOT = "jin_1"

# Map each player slot to its AI seed
AI_SEEDS = {
    "north": 1,
    "jin_1": 2,
    "jin_2": 3,
    "jin_3": 4,
}


class LoggingAgentWrapper:
    """Wraps an AI agent to print each action it takes in real time."""

    _setup_buffer: list[str] = []
    _buffer_enabled: bool = False

    def __init__(self, agent):
        self._agent = agent

    @property
    def player_id(self):
        return self._agent.player_id

    def setup_decision(self, ctx):
        decision = self._agent.setup_decision(ctx)
        # Build setup summary line(s)
        lines = []
        hero_name = ctx.hero_choices[decision.hero_index]['name'] if ctx.hero_choices else '?'
        lines.append(f"  [{self.player_id}] 选择英雄: {hero_name}")
        if ctx.goal_choices:
            g_name = ctx.goal_choices[decision.public_goal_index]['name'] if ctx.goal_choices else '?'
            lines.append(f"  [{self.player_id}] 公开目标: {g_name}")
        if ctx.hand_cards and decision.face_down_card_index < len(ctx.hand_cards):
            fd_name = ctx.hand_cards[decision.face_down_card_index]
            pay_names = [ctx.hand_cards[i] for i in decision.payment_indices
                        if i < len(ctx.hand_cards)]
            pay_str = f"（支付: {' '.join(pay_names)}）" if pay_names else ""
            lines.append(f"  [{self.player_id}] 暗置打出: {fd_name} {pay_str}")

        if LoggingAgentWrapper._buffer_enabled:
            LoggingAgentWrapper._setup_buffer.extend(lines)
        else:
            for line in lines:
                print(line)
        return decision

    @classmethod
    def enable_setup_buffer(cls):
        """Buffer AI setup decisions instead of printing immediately.
        Flushed by HumanPlayer.setup_decision() so the human doesn't see
        AI choices before making their own (simultaneous selection)."""
        cls._setup_buffer.clear()
        cls._buffer_enabled = True

    @classmethod
    def flush_setup_buffer(cls):
        """Print all buffered AI setup decisions."""
        for line in cls._setup_buffer:
            print(line)
        cls._setup_buffer.clear()
        cls._buffer_enabled = False

    def decide_action(self, state, available_actions):
        action = self._agent.decide_action(state, available_actions)
        if action is not None:
            try:
                desc, _, costs, _ = describe_action(action, state)
                cost_str = ""
                if costs:
                    parts = []
                    for k, v in costs.items():
                        if v:
                            parts.append(f"{k}:{v}")
                    if parts:
                        cost_str = f" [{', '.join(parts)}]"
                print(f"  [{self.player_id}] {desc}{cost_str}")
            except Exception:
                print(f"  [{self.player_id}] {getattr(action, 'action_type', '?')}")
        return action

    def make_choice(self, state, prompt):
        return self._agent.make_choice(state, prompt)

    def choose_discards(self, state, hand_cards, count, reason="hand_limit"):
        return self._agent.choose_discards(state, hand_cards, count, reason=reason)

    def select_target(self, state, prompt):
        return self._agent.select_target(state, prompt)

    def request_card_play(self, state, eligible_indices, filter_spec=None, free=False):
        return self._agent.request_card_play(state, eligible_indices, filter_spec=filter_spec, free=free)

    def request_court_play(self, state, eligible_cards=None, filter_spec=None):
        return self._agent.request_court_play(state, eligible_cards=eligible_cards, filter_spec=filter_spec)


def parse_preset_hands(argv: list[str]) -> dict[str, list[str]]:
    """Parse --preset / -p arguments into preset_hands dict.

    Format: player_id=card1,card2,...
    Example: --preset jin_1=慧远,尊奉江东
    Supports multiple -p flags.
    """
    result: dict[str, list[str]] = {}
    for i, arg in enumerate(argv):
        if arg in ("--preset", "-p") and i + 1 < len(argv):
            val = argv[i + 1]
            if "=" in val:
                pid, names_str = val.split("=", 1)
                # Split by comma: supports 中文逗号 and 英文逗号
                names = [n.strip() for n in names_str.replace("，", ",").split(",") if n.strip()]
                if pid not in result:
                    result[pid] = []
                result[pid].extend(names)
            else:
                print(f"[!] --preset 格式错误: 应为 player_id=牌名1,牌名2")
                print(f"    例如: --preset jin_1=慧远,尊奉江东")
                sys.exit(1)
    return result


def select_faction(argv: list[str]) -> str:
    """Let the user choose which faction to play. Returns player_id.

    "north" → human plays 北方
    "jin"   → human plays 东晋 (assigned to jin_1 slot)
    """
    # Filter out --preset / -p flags and their values to find the faction arg
    cleaned = []
    skip_next = False
    for a in argv[1:]:
        if skip_next:
            skip_next = False
            continue
        if a in ("--preset", "-p"):
            skip_next = True
            continue
        cleaned.append(a)

    if cleaned:
        arg = cleaned[0].lower()
        if arg in FACTION_CHOICES:
            return arg
        # Backward compat: accept specific slot names
        if arg in ("jin_1", "jin_2", "jin_3"):
            return arg
        print(f"无效的阵营: {cleaned[0]}")
        print(f"可选: {', '.join(FACTION_CHOICES.keys())}")
        sys.exit(1)

    # Interactive selection
    print("\n" + "=" * 50)
    print("  六朝何事 — 交互式游戏测试")
    print("=" * 50)
    print("\n选择你的阵营:\n")
    for i, (fid, label) in enumerate(FACTION_CHOICES.items(), 1):
        print(f"  {i}. {label}")
    print()

    while True:
        try:
            raw = input("  选择 (1-2): ").strip()
            val = int(raw)
            if 1 <= val <= len(FACTION_CHOICES):
                return list(FACTION_CHOICES.keys())[val - 1]
            print(f"  [!] 请输入 1-{len(FACTION_CHOICES)} 之间的数字")
        except ValueError:
            print("  [!] 请输入有效数字")
        except (EOFError, KeyboardInterrupt):
            print("\n  已取消")
            sys.exit(0)


def _print_final_scoring_breakdown(state, scoring_result, winner: str, human_pid: str):
    """Print detailed final scoring breakdown per player.

    Shows each scoring step's contribution and hidden goal details.
    """
    faction_labels = {"north": "北方", "jin_1": "东晋1", "jin_2": "东晋2", "jin_3": "东晋3"}

    # Pre-scoring state: we need to estimate pre-scoring VP by subtracting
    # scoring gains. Use the scoring result detail to reconstruct.
    players = {p.player_id: p for p in state.get_all_players()}

    # Gather per-player scoring details from result steps
    player_details = {pid: {"culture": 0, "region": 0, "sima": 0, "goal": 0, "goals": {}}
                      for pid in players}

    for step in scoring_result.steps:
        detail = step.get("detail", {})
        if step["name"] == "文化分数":
            for culture_name, cd in detail.items():
                if isinstance(cd, dict):
                    for pid, vp in cd.get("vp_awarded", {}).items():
                        player_details[pid]["culture"] += vp

        elif step["name"] == "区控与部队储备":
            region_detail = detail.get("region_control", {})
            if isinstance(region_detail, dict):
                for region_name, rd in region_detail.items():
                    if isinstance(rd, dict):
                        for pid, vp in rd.get("vp_awarded", {}).items():
                            player_details[pid]["region"] += vp
            # Army reserve
            for pid in players:
                p = players[pid]
                reserve_vp = getattr(p, 'army_reserve_revealed_vp', 0)
                if reserve_vp:
                    player_details[pid]["region"] += reserve_vp

        elif step["name"] == "司马家分数分配":
            if isinstance(detail, dict):
                for pid, vp in detail.get("vp_awarded", {}).items():
                    player_details[pid]["sima"] += vp

        elif step["name"] == "目标牌":
            if isinstance(detail, dict):
                for pid, gd in detail.items():
                    if isinstance(gd, dict):
                        player_details[pid]["goal"] = gd.get("total", 0)
                        player_details[pid]["goals"] = gd.get("goals", {})

    # Print each player's breakdown
    for pid in ["north", "jin_1", "jin_2", "jin_3"]:
        if pid not in players:
            continue
        p = players[pid]
        pd = player_details[pid]
        label = faction_labels.get(pid, pid)
        marker = " ★胜者" if pid == winner else ""
        is_you = " (你)" if pid == human_pid else ""

        # Calculate pre-scoring VP (final VP minus scoring gains)
        scoring_gain = pd["culture"] + pd["region"] + pd["sima"] + pd["goal"]
        pre_vp = p.vp - scoring_gain

        print(f"\n  ┌─ {label}{is_you}{marker}")
        print(f"  │  终局VP: {p.vp}  (基础: {pre_vp} + 终局计分: {scoring_gain})")
        if pd["culture"]:
            print(f"  │  文化分数: +{pd['culture']}")
        if pd["region"]:
            print(f"  │  区控与部队储备: +{pd['region']}")
        if pd["sima"]:
            print(f"  │  司马家分配: +{pd['sima']}")
        if pd["goal"]:
            print(f"  │  目标牌: +{pd['goal']}")

        # Goal details
        if pd["goals"] and p.faction.value == "jin":
            for gname, ginfo in pd["goals"].items():
                level = ginfo.get("level", "?")
                earned = ginfo.get("earned_vp", 0)
                if level == "full":
                    status = f"✓完成(完全) +{earned}"
                elif level == "simple":
                    status = f"✓完成(简易) +{earned}"
                elif level == "none":
                    status = "✗未完成"
                else:
                    status = f"? +{earned}"
                print(f"  │    · {gname}: {status}")
        print(f"  └{'─'*45}")

    # Sima state
    sima = getattr(state, 'sima', None)
    if sima:
        print(f"\n  司马家: VP={sima.vp}, 军力={sima.military}, 威望={sima.prestige}")


def main():
    # Parse preset hands from CLI before faction selection
    preset_hands = parse_preset_hands(sys.argv)

    # Select faction
    chosen_faction = select_faction(sys.argv)
    faction_label = FACTION_CHOICES.get(chosen_faction, chosen_faction)

    # Determine human player_id
    if chosen_faction == "north":
        human_pid = "north"
    elif chosen_faction == "jin":
        human_pid = HUMAN_JIN_SLOT
    else:
        # Backward compat: specific slot name
        human_pid = chosen_faction

    print(f"\n  你选择了: {faction_label}")
    if chosen_faction == "jin":
        print(f"  你将扮演东晋玩家 ({human_pid})")
    print(f"  其他三位玩家由 HeuristicAI 控制")
    print(f"  输入 q 可随时退出并保存日志")
    print(f"  游戏开始...\n")

    # Load version
    v = Version.load('v1.0')

    # Create human player first so we can reference it in callbacks
    human_player = HumanPlayer(player_id=human_pid)

    # Create agents: 1 HumanPlayer + 3 HeuristicAI (wrapped for logging)
    agents = []
    for pid in ["north", "jin_1", "jin_2", "jin_3"]:
        if pid == human_pid:
            agents.append(human_player)
        else:
            ai = HeuristicAI(player_id=pid, seed=AI_SEEDS[pid])
            agents.append(LoggingAgentWrapper(ai))

    # Enable setup buffer: AI setup decisions are buffered during the
    # sequential _deal_and_select_cards loop so the human player doesn't
    # see opposing choices before making their own (simultaneous selection).
    # HumanPlayer.setup_decision() flushes the buffer AFTER the human finishes.
    LoggingAgentWrapper.enable_setup_buffer()
    human_player._on_setup_end = lambda: LoggingAgentWrapper.flush_setup_buffer()

    # Create logger and engine
    logger = GameLogger()
    game_seed = int(time.time() * 1000) % 999999

    # Wire callbacks for human player
    def on_action(state, pid, action, result):
        """Print action results to terminal — enforce viewport visibility rules."""
        HumanPlayer.print_action_result(state, pid, action, result, human_pid=human_pid)

    def check_quit():
        """Check if human player requested early quit."""
        return human_player.wants_early_quit

    if preset_hands:
        print(f"  🧪 测试模式 — 预设手牌: {preset_hands}")

    engine = GameEngine(
        agents=agents, version=v, seed=game_seed, logger=logger,
        on_action_executed=on_action,
        preset_hands=preset_hands if preset_hands else None,
    )
    engine.check_early_quit = check_quit

    # Run game
    t0 = time.time()
    final_state = engine.run()
    elapsed = time.time() - t0

    # Check if early quit
    if human_player.wants_early_quit:
        print(f"\n{'='*50}")
        print(f"  ⚠ 游戏提前终止（玩家请求）")
        print(f"  回合数: {final_state.round}")
        print(f"{'='*50}")

    # Print results
    winner = engine.get_winner()
    scores = engine.get_scores()
    if not human_player.wants_early_quit:
        print(f"\n{'='*50}")
        print(f"  游戏结束!")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  回合数: {final_state.round}")
        print(f"  结束原因: {final_state.game_end_reason or 'round_10'}")
        print(f"{'='*50}")

        # Detailed scoring breakdown
        scoring_result = getattr(final_state, '_final_scoring_result', None)
        if scoring_result:
            _print_final_scoring_breakdown(final_state, scoring_result, winner, human_pid)
        else:
            print()
            for pid, score in scores.items():
                marker = " ★胜者" if pid == winner else ""
                is_you = " (你)" if pid == human_pid else ""
                print(f"  {pid}{is_you}: {score} VP{marker}")

    # Save logs
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    early_tag = "_early_quit" if human_player.wants_early_quit else ""
    base_name = f"{timestamp}_human_play_{human_pid}{early_tag}"

    txt_path = os.path.join(log_dir, f"{base_name}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(logger.to_text())
    print(f"\n  文本日志: {txt_path}")

    json_path = os.path.join(log_dir, f"{base_name}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(logger.to_json())
    print(f"  JSON日志: {json_path}")


if __name__ == "__main__":
    main()
