"""Goal card scoring — check conditions against final game state.

Parses goal card conditions from card_goal.csv format.
Each goal has a simple condition (lower VP) and a full condition (higher VP).
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import re
from typing import Optional

from models.enums import Region, CultureType, FactionType
from rules.area_control import check_region_control


# Pre-loaded goal definitions (from card_goal.csv)
# Each entry: {name, simple_vp, full_vp, simple_cond, full_cond}
GOAL_DEFINITIONS = [
    {"name": "天府之土", "simple_vp": 7, "full_vp": 14,
     "simple": "友方控制[巴蜀]区域", "full": "玩家控制[巴蜀]区域"},
    {"name": "河洛旧都", "simple_vp": 16, "full_vp": 22,
     "simple": "友方控制[中原]区域", "full": "玩家控制[中原]区域"},
    {"name": "关中故畿", "simple_vp": 14, "full_vp": 20,
     "simple": "友方控制[关中]区域", "full": "玩家控制[关中]区域"},
    {"name": "海岱之地", "simple_vp": 7, "full_vp": 14,
     "simple": "友方控制[山东]区域", "full": "玩家控制[山东]区域"},
    {"name": "赵魏雄藩", "simple_vp": 14, "full_vp": 20,
     "simple": "友方控制[河北]区域", "full": "玩家控制[河北]区域"},
    {"name": "表里山河", "simple_vp": 11, "full_vp": 16,
     "simple": "友方控制[山西]区域", "full": "玩家控制[山西]区域"},
    {"name": "配享太庙", "simple_vp": 10, "full_vp": 18,
     "simple": "功绩大于等于7", "full": "功绩等于9"},
    {"name": "加九锡", "simple_vp": 8, "full_vp": 30,
     "simple": "威望超过6",
     "full": "威望最高，且超过第二名至少3点"},
    {"name": "家财万贯", "simple_vp": 6, "full_vp": 12,
     "simple": "手牌超过5张", "full": "手牌超过8张"},
    {"name": "遗臭万年", "simple_vp": 7, "full_vp": 14,
     "simple": "拥有3个权谋标记", "full": "拥有5个权谋标记"},
    {"name": "敦悦五经", "simple_vp": 6, "full_vp": 16,
     "simple": "儒学贡献超过3",
     "full": "儒学贡献超过5，且儒学贡献最高"},
    {"name": "清言世业", "simple_vp": 6, "full_vp": 16,
     "simple": "玄学贡献超过3",
     "full": "玄学贡献超过5，且玄学贡献最高"},
    {"name": "崇奉三宝", "simple_vp": 6, "full_vp": 16,
     "simple": "佛学贡献超过3",
     "full": "佛学贡献超过5，且佛学贡献最高"},
    {"name": "配享武庙", "simple_vp": 10, "full_vp": 18,
     "simple": "威望超过6，且没有完成加九锡",
     "full": "威望等于9，且没有完成加九锡"},
    {"name": "世说新语", "simple_vp": 8, "full_vp": 16,
     "simple": "史书区有5张牌", "full": "史书区有8张牌"},
]


def evaluate_goal(state: "GameState", player_id: str,
                  goal: dict) -> Optional[int]:
    """Evaluate a single goal card for a player.

    Returns VP earned (0 if not met, simple_vp or full_vp).
    Checks full condition first, then simple.
    """
    player = state.get_player(player_id)
    if not player:
        return None

    # Check full condition first (higher reward)
    if _check_condition(state, player, goal["full"]):
        return goal["full_vp"]

    # Check simple condition
    if _check_condition(state, player, goal["simple"]):
        return goal["simple_vp"]

    return 0


def _check_condition(state: "GameState", player: "PlayerState",
                     condition: str) -> bool:
    """Check if a goal condition is met. Supports these patterns:

    - 友方控制[X]区域 / 玩家控制[X]区域
    - 功绩大于等于N / 功绩等于N
    - 威望超过N / 威望等于N
    - 威望最高，且超过第二名至少N点
    - 手牌超过N张
    - 拥有N个权谋标记
    - 儒学/玄学/佛学贡献超过N，且贡献最高
    - 史书区有N张牌
    - 且没有完成[加九锡]
    """
    # Region control
    m = re.search(r'(友方|玩家)控制\[(.+?)\]区域', condition)
    if m:
        who = m.group(1)
        region_name = m.group(2)
        region = _find_region(region_name)
        if not region:
            return False
        cr = check_region_control(state, region)
        if who == "玩家":
            return cr.full_controller == player.player_id
        else:  # 友方
            if player.faction == FactionType.NORTH:
                return cr.partial_controller == "north"
            else:
                return cr.partial_controller in ("sima", player.player_id)

    # 功绩 >= N
    m = re.search(r'功绩大于等于(\d+)', condition)
    if m:
        return player.contribution >= int(m.group(1))

    # 功绩 == N
    m = re.search(r'功绩等于(\d+)', condition)
    if m:
        return player.contribution == int(m.group(1))

    # 威望 > N
    m = re.search(r'威望超过(\d+)', condition)
    if m:
        return player.prestige > int(m.group(1))

    # 威望 == N
    m = re.search(r'威望等于(\d+)', condition)
    if m:
        return player.prestige == int(m.group(1))

    # 威望最高，且超过第二名至少N点
    if "威望最高" in condition:
        if player.faction != FactionType.JIN:
            return False
        jin_players = state.get_jin_players()
        sorted_by_pres = sorted(jin_players, key=lambda p: -p.prestige)
        if sorted_by_pres[0].player_id != player.player_id:
            return False
        m = re.search(r'超过第二名至少(\d+)点', condition)
        if m:
            gap = int(m.group(1))
            if len(sorted_by_pres) < 2:
                return True
            return (sorted_by_pres[0].prestige - sorted_by_pres[1].prestige) >= gap
        return True

    # 手牌超过N张
    m = re.search(r'手牌超过(\d+)张', condition)
    if m:
        return len(player.hand) > int(m.group(1))

    # 拥有N个权谋标记
    m = re.search(r'拥有(\d+)个权谋标记', condition)
    if m:
        return player.marker_power >= int(m.group(1))

    # 儒学/玄学/佛学贡献超过N
    for culture_name, culture_enum in [
        ("儒学", CultureType.CONFUCIANISM),
        ("玄学", CultureType.TAOISM),
        ("佛学", CultureType.BUDDHISM),
    ]:
        pattern = f'{culture_name}贡献超过(\\d+)'
        m = re.search(pattern, condition)
        if m:
            contrib = player.culture_contributions.get(culture_enum, 0)
            if contrib <= int(m.group(1)):
                return False
            # Optional: "且贡献最高"
            if "贡献最高" in condition or "轨道露出" in condition:
                all_players = state.get_all_players()
                my_contrib = contrib
                for p in all_players:
                    if p.player_id != player.player_id:
                        if p.culture_contributions.get(culture_enum, 0) >= my_contrib:
                            return False
            return True

    # 史书区有N张牌
    m = re.search(r'史书区有(\d+)张牌', condition)
    if m:
        return len(player.history_area) >= int(m.group(1))

    # 没有完成[加九锡]
    if "没有完成加九锡" in condition or "没有完成[加九锡]" in condition:
        # Check if player has the 加九锡 goal completed
        # This requires tracking which goals a player has, which we don't yet
        # For now, just check if prestige condition for 加九锡 is met
        jjx_met = _check_jiajiuxi_completed(state, player)
        return not jjx_met

    return False


def _find_region(name: str) -> Optional[Region]:
    """Find a Region enum by Chinese name."""
    region_map = {
        "西凉": Region.XILIANG, "关中": Region.GUANZHONG,
        "巴蜀": Region.BASHU, "荆襄": Region.JINGXIANG,
        "江南": Region.JIANGNAN, "中原": Region.ZHONGYUAN,
        "山西": Region.SHANXI, "山东": Region.SHANDONG,
        "淮南": Region.HUAINAN, "河北": Region.HEBEI,
        "幽燕": Region.YOUYAN, "塞外": Region.GUANWAI,
    }
    return region_map.get(name)


def _check_jiajiuxi_completed(state: "GameState", player: "PlayerState") -> bool:
    """Check if a player has met the 加九锡 full condition."""
    if player.prestige <= 6:
        return False
    jin_players = state.get_jin_players()
    sorted_by_pres = sorted(jin_players, key=lambda p: -p.prestige)
    if sorted_by_pres[0].player_id != player.player_id:
        return False
    if len(sorted_by_pres) >= 2:
        return (sorted_by_pres[0].prestige - sorted_by_pres[1].prestige) >= 3
    return True


def score_player_goals(state: "GameState", player_id: str,
                       goal_names: list[str]) -> int:
    """Score all of a player's goal cards. Returns total VP from goals.

    goal_names: list of goal card names the player has.
    """
    total_vp = 0
    for name in goal_names:
        goal = next((g for g in GOAL_DEFINITIONS if g["name"] == name), None)
        if goal:
            vp = evaluate_goal(state, player_id, goal)
            if vp:
                total_vp += vp
    return total_vp
