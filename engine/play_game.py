"""Interactive game: human player vs HeuristicAI opponents.

Usage:
    python play_game.py              # Interactive faction selection
    python play_game.py north        # Play as 北方
    python play_game.py jin_1        # Play as 东晋 player 1
    python play_game.py jin_2        # Play as 东晋 player 2
    python play_game.py jin_3        # Play as 东晋 player 3
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

    def __init__(self, agent):
        self._agent = agent

    @property
    def player_id(self):
        return self._agent.player_id

    def setup_decision(self, ctx):
        decision = self._agent.setup_decision(ctx)
        # Print AI's setup choices so human can see what happened
        hero_name = ctx.hero_choices[decision.hero_index]['name'] if ctx.hero_choices else '?'
        print(f"  [{self.player_id}] 选择英雄: {hero_name}")
        if ctx.goal_choices:
            g_name = ctx.goal_choices[decision.public_goal_index]['name'] if ctx.goal_choices else '?'
            print(f"  [{self.player_id}] 公开目标: {g_name}")
        if ctx.hand_cards and decision.face_down_card_index < len(ctx.hand_cards):
            fd_name = ctx.hand_cards[decision.face_down_card_index]
            pay_names = [ctx.hand_cards[i] for i in decision.payment_indices
                        if i < len(ctx.hand_cards)]
            pay_str = f"（支付: {' '.join(pay_names)}）" if pay_names else ""
            print(f"  [{self.player_id}] 暗置打出: {fd_name} {pay_str}")
        return decision

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

    def choose_discards(self, state, hand_cards, count):
        return self._agent.choose_discards(state, hand_cards, count)

    def select_target(self, state, prompt):
        return self._agent.select_target(state, prompt)


def select_faction() -> str:
    """Let the user choose which faction to play. Returns player_id.

    "north" → human plays 北方
    "jin"   → human plays 东晋 (assigned to jin_1 slot)
    """
    # Check command-line argument
    if len(sys.argv) >= 2:
        arg = sys.argv[1].lower()
        if arg in FACTION_CHOICES:
            return arg
        # Backward compat: accept specific slot names
        if arg in ("jin_1", "jin_2", "jin_3"):
            return arg
        print(f"无效的阵营: {sys.argv[1]}")
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


def main():
    # Select faction
    chosen_faction = select_faction()
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

    # Create logger and engine
    logger = GameLogger()
    game_seed = int(time.time() * 1000) % 999999

    # Wire callbacks for human player
    def on_action(state, pid, action, result):
        """Print action results to terminal when it's the human player's action."""
        HumanPlayer.print_action_result(state, pid, action, result)

    def check_quit():
        """Check if human player requested early quit."""
        return human_player.wants_early_quit

    engine = GameEngine(
        agents=agents, version=v, seed=game_seed, logger=logger,
        on_action_executed=on_action,
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
