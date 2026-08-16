"""All game enumerations for 六朝何事 (Six Dynasties)."""

from enum import Enum, auto


class FactionType(Enum):
    """Player faction affiliation."""
    NORTH = "north"          # 北方
    JIN = "jin"              # 东晋
    SIMA = "sima"            # 司马家 (non-player)
    NEUTRAL = "neutral"      # 中立


class CardType(Enum):
    """Top-level card classification."""
    HERO = "hero"                  # 角色牌
    EVENT = "event"                # 事件牌
    STRATEGY = "strategy"          # 策略牌
    FRIEND = "friend"              # 幕僚牌
    MECHANISM = "mechanism"        # 强制事件牌
    GOAL = "goal"                  # 目标牌
    EMPEROR = "emperor"            # 君主牌
    PUBLIC = "public"              # 公共行动牌
    REFUGEE = "refugee"            # 流民牌
    INITIAL = "initial"            # 初始牌 (pseudo-type for starting cards)


class CardCategory(Enum):
    """Card sub-category for organization and marker association."""
    # Hero categories
    HERO_JIN = "hero_jin"
    HERO_NORTH = "hero_north"

    # Friend categories
    FRIEND_MILITARY = "friend_military"      # 幕僚-名将
    FRIEND_ADVISOR = "friend_advisor"        # 幕僚-谋主
    FRIEND_SPECIAL = "friend_special"        # 幕僚-特殊
    FRIEND_CULTURE = "friend_culture"        # 幕僚-艺术文化

    # Strategy categories
    STRATEGY_MILITARY = "strategy_military"   # 策略-军备
    STRATEGY_CULTURE = "strategy_culture"     # 策略-文化
    STRATEGY_SPECIAL = "strategy_special"     # 策略-特殊

    # Event categories
    EVENT_ART = "event_art"                   # 事件-艺术
    EVENT_CULTURE = "event_culture"           # 事件-文化
    EVENT_MILITARY = "event_military"         # 事件-军事
    EVENT_VP = "event_vp"                     # 事件-VP
    EVENT_SEARCH = "event_search"             # 事件-检索
    EVENT_MECHANISM = "event_mechanism"       # 事件-机制
    EVENT_UTILITY = "event_utility"           # 事件-功能
    EVENT_POWER = "event_power"               # 事件-权谋

    # Other
    PUBLIC = "public"
    GOAL = "goal"
    EMPEROR = "emperor"
    REFUGEE = "refugee"
    INITIAL = "initial"


class PhaseType(Enum):
    """Game phase."""
    SETUP = "setup"
    PREPARATION = "preparation"
    ACTION = "action"
    SETTLEMENT = "settlement"
    GAME_OVER = "game_over"


class CultureType(Enum):
    """Three culture tracks."""
    CONFUCIANISM = "confucianism"  # 儒学
    TAOISM = "taoism"              # 玄学
    BUDDHISM = "buddhism"          # 佛学


class Region(Enum):
    """Map regions (12 regions)."""
    XILIANG = "西凉"        # 张掖, 姑臧, 金城
    GUANZHONG = "关中"      # 安定, 天水, 长安
    BASHU = "巴蜀"          # 汉中, 巴郡, 蜀郡
    JINGXIANG = "荆襄"      # 襄阳, 南郡, 巴东, 武昌, 宛城, 上洛
    JIANGNAN = "江南"       # 浔阳, 建康, 京口, 吴, 会稽
    ZHONGYUAN = "中原"      # 弘农, 洛阳, 雍丘, 彭城, 谯, 东平
    SHANXI = "山西"          # 平阳, 太原, 上党
    SHANDONG = "山东"        # 济南, 广固, 琅琊
    HUAINAN = "淮南"         # 寿春, 合肥, 广陵
    HEBEI = "河北"           # 中山, 襄国, 邺城, 信都
    YOUYAN = "幽燕"          # 蓟城, 龙城
    GUANWAI = "塞外"         # 盛乐, 平城


class MarkerType(Enum):
    """Card/action marker types."""
    MILITARY = "军事"
    CULTURE = "文化"
    AFFAIR = "内政"
    POWER = "权谋"


class TerrainType(Enum):
    """Connection terrain between locations."""
    SIMPLE = "simple"      # 实线 — normal cost
    DIFFICULT = "difficult"  # 虚线 — march cost +1


class ActionType(Enum):
    """All possible game actions."""
    # Quick actions
    OCCUPY = "occupy"          # 占据
    MARCH = "march"            # 进军
    DRAW = "draw"              # 摸牌
    RECRUIT = "recruit"        # 征募
    FORTIFY = "fortify"        # 加固
    # Hand/card actions
    PLAY_CARD = "play_card"    # 手牌行动
    COURT_ACTION = "court_action"  # 牌组行动
    # Special actions
    CONVERT = "convert"        # 转化
    ARCHIVE = "archive"        # 存档
    SPREAD_CULTURE = "spread_culture"  # 传播文化
    SEARCH = "search"          # 检索
    LEVY = "levy"            # 征发
    RAISE_ORDER = "raise_order"  # 提高行动顺位
    LOWER_ORDER = "lower_order"  # 降低行动顺位
    DISCARD = "discard"        # 弃牌
    # Meta
    END_TURN = "end_turn"      # 结束行动
    PASS = "pass"              # 跳过


class EmperorTaskType(Enum):
    """Types of tasks that appear on emperor dice."""
    EXPANSION = "expansion"    # 扩张
    FORTIFY = "fortify"        # 加固
    CULTURE = "culture"        # 文化
    REFORM = "reform"          # 改革
    ART = "art"                # 艺术


class QuickActionType(Enum):
    """The five quick action types."""
    OCCUPY = "occupy"
    MARCH = "march"
    DRAW = "draw"
    RECRUIT = "recruit"
    FORTIFY = "fortify"


class ControlState(Enum):
    """Who controls a location or region."""
    NORTH = "north"
    JIN_P1 = "jin_p1"
    JIN_P2 = "jin_p2"
    JIN_P3 = "jin_p3"
    SIMA = "sima"
    NEUTRAL = "neutral"      # 中立势力占据 (has neutral troops)
    EMPTY = "empty"          # 未被占据 (no troops, can be occupied directly)


class EventTrigger(Enum):
    """Trigger timing for passive/triggered abilities."""
    ON_MARCH = "on_march"              # 进军后
    ON_OCCUPY = "on_occupy"            # 占据后
    ON_CONVERT = "on_convert"          # 转化后
    ON_ARCHIVE = "on_archive"          # 存档后
    ON_FORTIFY = "on_fortify"          # 加固后
    ON_SPREAD_CULTURE = "on_spread_culture"  # 传播文化后
    ON_DRAW = "on_draw"                # 摸牌后
    ON_DISCARD = "on_discard"          # 弃牌后
    ON_PLAY_CARD = "on_play_card"      # 打出牌后
    ON_COURT_ACTION = "on_court_action"  # 执行牌组行动后
    ON_GAIN_PRESTIGE = "on_gain_prestige"  # 获得威望后
    ON_GAIN_CONTRIBUTION = "on_gain_contribution"  # 获得功绩后
    ON_GAIN_VP = "on_gain_vp"          # 获得VP后
    ON_ORDER_CHANGE = "on_order_change"  # 顺位变化后
    ON_TURN_START = "on_turn_start"    # 回合开始
    ON_TURN_END = "on_turn_end"        # 回合结束
    # ON_CARD_ENTER = "on_card_enter"  # 卡牌登场 — 预留，解析器及触发分发均未实现
    ON_CARD_LEAVE = "on_card_leave"    # 卡牌退场
    ON_CONDITION = "on_condition"      # 条件触发
