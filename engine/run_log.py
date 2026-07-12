"""Run a game with logging and write txt+json log files."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from config.version import Version
from ai.heuristic_ai import HeuristicAI
from engine.game import GameEngine
from engine.game_logger import GameLogger

v = Version.load('v1.0')
agents = [
    HeuristicAI(player_id="north", seed=1),
    HeuristicAI(player_id="jin_1", seed=2),
    HeuristicAI(player_id="jin_2", seed=3),
    HeuristicAI(player_id="jin_3", seed=4),
]

logger = GameLogger()
engine = GameEngine(agents=agents, version=v, seed=42, logger=logger)
final_state = engine.run()

# Write logs
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)

txt_path = os.path.join(log_dir, "heuristic_ai_test_log_v13.txt")
with open(txt_path, "w", encoding="utf-8") as f:
    f.write(logger.to_text())

json_path = os.path.join(log_dir, "heuristic_ai_test_log_v13.json")
with open(json_path, "w", encoding="utf-8") as f:
    f.write(logger.to_json())

print(f"Winner: {engine.get_winner()}")
print(f"Scores: {engine.get_scores()}")
print(f"Rounds: {final_state.round}")
print(f"Logs written to {txt_path} and {json_path}")
