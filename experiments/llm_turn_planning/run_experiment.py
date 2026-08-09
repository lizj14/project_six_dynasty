"""
LLM 回合规划能力实验

目的：在写任何代码之前，先验证 LLM 能否基于规则书+卡表+游戏视图，
产出有质量的回合战略分析和行动计划。

隔离原则：
- 只提供给 LLM：规则书摘要、卡表、地图连接、当前玩家游戏视图
- 不提供：测试日志、历史分析、代码上下文、其他玩家的手牌

用法：
    cd d:/life/board_game/project_six_dynasty
    python experiments/llm_turn_planning/run_experiment.py

配置：
    设置环境变量 OPENAI_API_KEY（或修改脚本中的 API 配置）
"""

import json
import os
import sys
import textwrap
from datetime import datetime
from pathlib import Path

# ── 项目路径设置 ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "engine"))

# ── API 配置 ──────────────────────────────────────────────────
LLM_CONFIG = {
    "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/v1"),
    "api_key": os.environ.get("OPENAI_API_KEY", "sk-ae7688570fe042b78a8f9b250ea6775a"),
    "model": os.environ.get("LLM_MODEL", "deepseek-v4-pro"),
    "temperature": 0.3,
    "max_tokens": 8192,
}

# ── 输出目录 ──────────────────────────────────────────────────
OUTPUT_DIR = PROJECT_ROOT / "experiments" / "llm_turn_planning" / "outputs"


# ================================================================
# 第一步：构建实验用游戏状态
# ================================================================

def build_experiment_state():
    """使用真实游戏引擎初始化一局，用 DummyAI 跑完前2回合，
    然后执行第3回合的准备阶段，在第3回合行动阶段开始前返回状态。

    返回 (GameState, viewer_id)，其中 viewer_id 为即将行动的玩家。
    """
    from config.version import Version
    from ai.dummy_ai import DummyAI
    from engine.game import GameEngine
    from engine.action_system import ActionSystem
    from engine.phases import run_preparation_phase, setup_game
    from models.enums import PhaseType

    seed = int(os.environ.get("EXPERIMENT_SEED", "43"))

    # 加载游戏版本
    version = Version.load("v1.0")

    # 创建4个 DummyAI agent（不同 seed 确保行为不同）
    agents = [
        DummyAI(player_id="north", seed=seed),
        DummyAI(player_id="jin_1", seed=seed + 100),
        DummyAI(player_id="jin_2", seed=seed + 200),
        DummyAI(player_id="jin_3", seed=seed + 300),
    ]

    # 创建引擎
    action_system = ActionSystem()
    engine = GameEngine(
        agents=agents,
        version=version,
        seed=seed,
        action_system=action_system,
    )

    # 初始化游戏
    state = engine.state = setup_game(
        version.card_library, agents,
        seed, version=version,
        map_adjacencies=version.map,
        action_system=action_system,
    )
    engine._post_setup_init()

    # 手动跑前2回合（setup 后 round=1, phase=PREPARATION）
    rng = engine.rng
    for _ in range(2):  # 第1和第2回合
        engine._run_round()
        if state.phase == PhaseType.GAME_OVER:
            break

    # 现在 state.round=3, phase=PREPARATION
    # 执行第3回合的准备阶段
    run_preparation_phase(state, rng)

    from rules.scoring import award_region_control_phase
    award_region_control_phase(state, player_id=None)

    # 现在进入行动阶段
    state.phase = PhaseType.ACTION

    # 重置所有玩家的回合行动标记（模拟 _run_player_turn 开头的 reset_action_flags）
    for p in state.get_all_players():
        p.reset_action_flags()

    # 重置活跃玩家索引（本轮尚未有人行动）
    state.active_player_index = 0

    # 选择一个东晋玩家作为"主角"（排在第一位的 jin 玩家）
    viewer_id = state.turn_order[1]  # turn_order[0] 是 north
    print(f"  第3回合行动顺序: {state.turn_order}")
    print(f"  选中的玩家: {viewer_id}")

    return state, viewer_id


# ================================================================
# 第二步：构建 Prompt
# ================================================================

def build_rulebook_text() -> str:
    """读取完整规则书（优先从版本目录读取，与版本强绑定）。"""
    # 优先从 v1.0 版本目录读取
    version_rulebook = PROJECT_ROOT / "versions" / "v1.0" / "rulebook.md"
    if version_rulebook.exists():
        with open(version_rulebook, "r", encoding="utf-8") as f:
            return f.read()
    # 回退到项目根目录
    with open(PROJECT_ROOT / "rulebook.md", "r", encoding="utf-8") as f:
        return f.read()


def build_card_table() -> str:
    """从 CSV 卡表提取所有卡牌，整理为 LLM 友好格式。"""
    import csv

    csv_path = PROJECT_ROOT / "card_design.csv"
    cards_by_type = {}

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            card_type = row.get("类型", "")
            name = row.get("卡牌名称", "")
            cat_detail = row.get("卡牌分类", "")
            cost = row.get("费用", "")
            effect = row.get("效果", "")
            faction = row.get("归属", "")
            markers = []
            if row.get("军事标记", "") == "1":
                markers.append("军事")
            if row.get("文化标记", "") == "1":
                markers.append("文化")
            if row.get("内政标记", "") == "1":
                markers.append("内政")
            if row.get("权谋标记", "") == "1":
                markers.append("权谋")

            if not name or name == "统计":
                continue

            marker_str = ("[" + ",".join(markers) + "]") if markers else ""
            entry = {
                "name": name,
                "type": card_type,
                "cost": cost,
                "faction": faction,
                "markers": marker_str,
                "effect": effect,
                "sub_category": cat_detail,
            }
            cards_by_type.setdefault(card_type, []).append(entry)

    # 格式化输出
    lines = ["# 卡牌总表\n"]

    type_order = [
        ("角色牌", "角色牌（英雄，选择后整局生效）"),
        ("幕僚牌", "幕僚牌（持续增益，放入幕僚区）"),
        ("策略牌", "策略牌（放入国家牌库顶，随后出现在朝堂区供牌组行动选择；含初始牌）"),
        ("事件牌", "事件牌（一次性强力效果，含强制事件/公共行动牌）"),
    ]

    for type_key, type_label in type_order:
        entries = cards_by_type.get(type_key, [])
        if not entries:
            continue
        lines.append(f"## {type_label} ({len(entries)}张)\n")
        for e in entries:
            faction_tag = f"[{e['faction']}]" if e['faction'] not in ("统计", "", "初始", "通用") else ""
            marker = f" {e['markers']}" if e['markers'] else ""
            sub = f" | {e['sub_category']}" if e['sub_category'] else ""
            lines.append(f"- **{e['name']}** {faction_tag} | 费用{e['cost']}{sub}{marker}")
            if e['effect'] and e['effect'] != '-':
                effect_clean = e['effect'].replace('\n', ' ').strip()
                if len(effect_clean) > 120:
                    effect_clean = effect_clean[:117] + "..."
                lines.append(f"  {effect_clean}")
        lines.append("")

    return "\n".join(lines)


def build_map_connections() -> str:
    """构建地图连接关系文本。"""
    import yaml

    map_yaml = PROJECT_ROOT / "versions" / "v1.0" / "map" / "map_adjacency.yaml"
    with open(map_yaml, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    lines = ["# 地图连接关系\n"]

    # 区域信息
    lines.append("## 区域\n")
    for region_name, region_data in data["regions"].items():
        locs = "、".join(region_data["locations"])
        cp = region_data.get("control_vp_partial", 0)
        cf = region_data.get("control_vp_full", 0)
        cs = region_data.get("culture_slots", 0)
        ic = region_data.get("initial_culture", "")
        culture_labels = {"confucianism": "儒学", "taoism": "玄学", "buddhism": "佛学"}
        ic_label = culture_labels.get(ic, "")
        bonus = region_data.get("placement_bonus", "")
        lines.append(f"- **{region_name}**：{locs}")
        lines.append(f"  控制VP(部分={cp}/完全={cf})，文化槽={cs}，初始文化={ic_label or '无'}，放置奖励={bonus or '无'}")
    lines.append("")

    # 连接关系
    lines.append("## 连接关系（实线=简单地形，虚线=困难地形）\n")
    connections_by_region: dict[str, list] = {}
    for entry in data.get("adjacencies", []):
        loc_a, loc_b, terrain = entry[0], entry[1], entry[2]
        terrain_label = "· ·" if terrain == "difficult" else "—"
        conn = f"{loc_a} {terrain_label} {loc_b}"
        # 按第一个地点的区域分组
        region_a = _get_location_region(loc_a)
        connections_by_region.setdefault(region_a, []).append(conn)

    for region, conns in connections_by_region.items():
        lines.append(f"### {region}")
        for c in conns:
            lines.append(f"  {c}")

    return "\n".join(lines)


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
    return region_map.get(location_id, "未知")


def build_game_view_text(state, viewer_id: str) -> str:
    """从 SnapshotViewport 构建人类可读的游戏视图文本。"""
    from viewport.snapshot import SnapshotViewport

    vp = SnapshotViewport.from_state(state, viewer_id)

    lines = [f"# 当前游戏状态（第{vp.round}回合，{vp.phase}阶段）\n"]

    # ── 你的信息 ──
    me = vp.get_my_player()
    lines.append("## 你的信息")
    lines.append(f"- 玩家ID：{viewer_id}")
    lines.append(f"- 阵营：{'北方' if me.get('faction') == 'north' else '东晋'}")
    lines.append(f"- VP：{me.get('vp', 0)}")
    lines.append(f"- 军力：{me.get('military', 0)}")
    lines.append(f"- 部队已放置：{me.get('army_placed_count', 0)} / 储备：{me.get('army_reserve_count', 0)}")
    if me.get('faction') == 'jin':
        lines.append(f"- 威望：{me.get('prestige', 0)}")
        lines.append(f"- 功绩：{me.get('contribution', 0)}")
        lines.append(f"- 行动顺位：{me.get('order', 0)}")
    lines.append(f"- 标记：军事{me.get('marker_military',0)} 文化{me.get('marker_culture',0)} 内政{me.get('marker_affair',0)} 权谋{me.get('marker_power',0)}")

    # 英雄
    hero = vp.get_my_hero()
    if hero:
        lines.append(f"- 英雄：{hero['name']} — {hero.get('effect_text', '')}")

    # 手牌
    lines.append("\n### 你的手牌")
    hand = vp.get_my_hand()
    for i, card in enumerate(hand):
        markers = ",".join(k for k, v in card.get('markers', {}).items() if v)
        marker_str = f" [{markers}]" if markers else ""
        cost_str = f"费用{card['cost']}" if card['cost'] >= 0 else ""
        card_type = card.get('card_type', '?')
        lines.append(f"  [{i}] {card['name']} ({card_type}, {cost_str}){marker_str}")
        if card.get('effect_text'):
            lines.append(f"      效果: {card['effect_text']}")
        elif card.get('effect_summary'):
            lines.append(f"      效果: {card['effect_summary']}")

    # 幕僚
    staff = vp.get_my_staff()
    if staff:
        lines.append("\n### 你的幕僚区")
        for card in staff:
            lines.append(f"  - {card['name']}: {card.get('effect_text', card.get('effect_summary', ''))}")

    # ── 朝堂区 ──
    faction = "jin" if me.get('faction') == 'jin' else "north"
    lines.append(f"\n## 朝堂区（候选策略牌，{faction}）")
    court_cards = vp.get_court_cards(faction)
    for i, card in enumerate(court_cards):
        cost_str = f"费用{card['cost']}" if card.get('cost', -1) >= 0 else ""
        resource = ""
        if card.get('resource_option_army', 0):
            resource += f"+{card['resource_option_army']}军力"
        if card.get('resource_option_vp', 0):
            resource += f" +{card['resource_option_vp']}VP" if resource else f"+{card['resource_option_vp']}VP"
        resource_str = f" [资源: {resource}]" if resource else ""
        lines.append(f"  [{i}] {card['name']} ({card.get('card_type','')}, {cost_str}){resource_str}")
        if card.get('effect_text'):
            lines.append(f"      效果: {card['effect_text']}")
        elif card.get('effect_summary'):
            lines.append(f"      效果: {card['effect_summary']}")

    # ── 公共行动牌 ──
    public_actions = vp.get_public_actions()
    if public_actions:
        lines.append("\n## 公共行动牌")
        for card in public_actions:
            lines.append(f"  - {card['name']} (费用{card.get('cost',0)}): {card.get('effect_text', '')}")

    # ── 地图 ──
    lines.append("\n## 地图状态\n")
    all_locs = vp.get_all_locations()
    # 按区域分组
    regions = vp.get_regions()
    for region_name in sorted(regions.keys()):
        rd = regions[region_name]
        loc_ids = rd.get("locations", [])
        control = rd.get("control_marker", "无")
        cultures = rd.get("culture_markers", [])
        culture_strs = []
        for cm in cultures:
            ct = cm.get("type", "?")
            lock = "🔒" if cm.get("locked") else ""
            culture_strs.append(f"{ct}{lock}")
        culture_str = (" [" + ",".join(culture_strs) + "]") if culture_strs else ""

        ctrl_cn = {"north": "北方", "jin_p1": "晋1", "jin_p2": "晋2", "jin_p3": "晋3",
                   "sima": "司马", "neutral": "中立", "empty": "空"}
        loc_strs = []
        for lid in loc_ids:
            loc = all_locs.get(lid, {})
            ctrl = loc.get("controller", "?")
            ctrl_label = ctrl_cn.get(ctrl, ctrl)
            fort = "★" if loc.get("is_fortified") else ""
            cap = "🏛" if loc.get("is_capital") else ""
            loc_strs.append(f"{lid}({ctrl_label}){fort}{cap}")
        lines.append(f"  **{region_name}** [控制:{control or '无'}]{culture_str}")
        lines.append(f"    {'  '.join(loc_strs)}")

    # ── 轨道 ──
    lines.append(f"\n## 数据轨道")
    vp_track = vp.get_vp_track()
    lines.append(f"- VP：north={vp_track.get('north',0)} jin_1={vp_track.get('jin_1',0)} jin_2={vp_track.get('jin_2',0)} jin_3={vp_track.get('jin_3',0)} sima={vp_track.get('sima',0)}")

    prestige = vp.get_prestige_track()
    lines.append(f"- 威望：jin_1={prestige.get('jin_1',0)} jin_2={prestige.get('jin_2',0)} jin_3={prestige.get('jin_3',0)} sima={prestige.get('sima',0)}")

    contrib = vp.get_contribution_track()
    lines.append(f"- 功绩：jin_1={contrib.get('jin_1',0)} jin_2={contrib.get('jin_2',0)} jin_3={contrib.get('jin_3',0)}")

    order = vp.get_order_track()
    lines.append(f"- 顺位：jin_1={order.get('jin_1',0)} jin_2={order.get('jin_2',0)} jin_3={order.get('jin_3',0)}")

    # ── 其他玩家公开信息 ──
    lines.append("\n## 其他玩家（公开信息）")
    for pid in [p for p in ["north", "jin_2", "jin_3"] if p != viewer_id]:
        p = vp.get_other_player(pid)
        if not p:
            continue
        faction_label = "北方" if p.get('faction') == 'north' else "东晋"
        hero_name = p.get('hero', {}).get('name', '无') if p.get('hero') else '无'
        staff = "、".join(p.get('staff_names', [])) if p.get('staff_names') else "无"
        lines.append(f"- **{pid}** [{faction_label}] VP:{p.get('vp',0)} 军力:{p.get('military',0)} 手牌:{p.get('hand_count',0)} 部队:{p.get('army_placed_count',0)}")
        lines.append(f"  英雄:{hero_name} 幕僚:[{staff}]")
        if p.get('faction') == 'jin':
            lines.append(f"  威望:{p.get('prestige',0)} 功绩:{p.get('contribution',0)} 顺位:{p.get('order',0)}")

    # ── 皇帝/司马家 ──
    lines.append("\n## 皇帝与司马家")
    emp = vp.get_emperor()
    sima = vp.get_sima()
    task_strs = []
    for t in emp.get("tasks", []):
        mark = "✓" if t.get("completed") else "○"
        ttype = t.get("type", "?")
        target = f"({t.get('target_region', '')})" if t.get("target_region") else ""
        task_strs.append(f"{mark}{ttype}{target}")
    tasks = " ".join(task_strs) if task_strs else "无"
    lines.append(f"- 皇帝：{emp.get('emperor_name','?')} 年龄{emp.get('age',0)} 威望{emp.get('prestige',0)}")
    lines.append(f"- 任务：{tasks}")
    lines.append(f"- 司马家：VP{sima.get('vp',0)} 军力{sima.get('military',0)} 威望{sima.get('prestige',0)} 首都{sima.get('capital_location','建康')}")

    # ── 牌库 ──
    lines.append(f"\n## 牌库计数")
    lines.append(f"- 主牌库剩余：{vp.get_main_deck_count()} | 主弃牌区：{len(vp.get_main_discard())}张")
    lines.append(f"- 东晋牌库：{vp.get_national_deck_count('jin')} | 东晋弃牌区：{len(vp.get_national_discard('jin'))}张")
    lines.append(f"- 北方牌库：{vp.get_national_deck_count('north')} | 北方弃牌区：{len(vp.get_national_discard('north'))}张")

    # ── 可执行行动 ──
    lines.append(f"\n## 回合进度")
    lines.append(f"- 手牌行动：{'已执行' if me.get('has_taken_hand_action') else '未执行'}")
    lines.append(f"- 牌组行动：{'已执行' if me.get('has_taken_court_action') else '未执行'}")
    lines.append(f"- 快速摸牌：{'已使用' if me.get('has_drawn_quick') else '未使用'}")
    lines.append(f"- 快速加固：{'已使用' if me.get('has_fortified_quick') else '未使用'}")

    return "\n".join(lines)


def build_prompt(viewer_id: str, game_view_text: str) -> tuple[str, list[dict]]:
    """构建完整 prompt，返回 (system_prompt, messages)。"""

    rulebook = build_rulebook_text()
    card_table = build_card_table()
    map_text = build_map_connections()

    # ── System Prompt ──
    system = textwrap.dedent("""\
    你是一个桌游AI助手，正在玩一款名为《六朝何事》的4人历史策略桌游。
    你扮演一位东晋家族，目标是获得最高的VP（胜利点数）。

    你的任务：基于当前的游戏状态，分析局势并规划本回合的行动方案。

    请按以下格式输出（JSON）：

    {
      "战略分析": {
        "局势评估": "一句话总结当前局势",
        "本回合目标": "本回合希望达成的具体目标",
        "威胁与机会": "需要注意的威胁和可以把握的机会"
      },
      "手牌行动": {
        "选择的牌": "牌名",
        "理由": "为什么选这张牌"
      },
      "牌组行动": {
        "选择的牌": "牌名（或'跳过'）",
        "理由": "为什么选这张牌"
      },
      "快速行动序列": [
        {"行动": "xxx", "目标": "xxx（如适用）", "理由": "xxx"}
      ],
      "整体思路": "解释你的整体规划和各行动之间的配合逻辑"
    }

    注意事项：
    - 东晋玩家和司马家是友方，目标是一起对抗北方玩家，但东晋之间也要竞争VP
    - 手牌行动只能执行1次
    - 牌组行动只能执行1次（从朝堂区选牌）
    - 快速行动不限次数，但受军力限制
    - 注意军力管理：行动结束时军力清0，所以要在本回合内花完
    - 注意手牌上限：行动结束时最多保留8张
    """)

    # ── User Message ──
    user = f"""以下是《六朝何事》的规则书摘要、卡牌总表、地图连接关系和当前游戏状态。
请基于这些信息，分析当前局势并规划本回合的操作方案。

---

{rulebook}

---

{card_table}

---

{map_text}

---

{game_view_text}

---

请基于以上信息，输出你的回合分析（JSON格式）。"""

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    return system, messages


# ================================================================
# 第三步：调用 LLM API
# ================================================================

def call_llm(system_prompt: str, messages: list[dict]) -> dict:
    """调用 LLM API，返回响应。"""
    try:
        from openai import OpenAI
    except ImportError:
        print("[ERROR] 请安装 openai 库: pip install openai")
        sys.exit(1)

    client = OpenAI(
        base_url=LLM_CONFIG["base_url"],
        api_key=LLM_CONFIG["api_key"],
    )

    print(f"[API] 调用 {LLM_CONFIG['model']}...")
    print(f"[API] base_url: {LLM_CONFIG['base_url']}")
    print(f"[API] prompt 长度: system={len(system_prompt)} chars, user={len(messages[-1]['content'])} chars")

    response = client.chat.completions.create(
        model=LLM_CONFIG["model"],
        messages=messages,
        temperature=LLM_CONFIG["temperature"],
        max_tokens=LLM_CONFIG["max_tokens"],
    )

    return {
        "model": response.model,
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        },
        "content": response.choices[0].message.content,
        "finish_reason": response.choices[0].finish_reason,
    }


# ================================================================
# 第四步：保存结果
# ================================================================

def save_results(
    system_prompt: str,
    messages: list[dict],
    response: dict,
    timestamp: str,
):
    """保存实验输入输出。"""
    run_dir = OUTPUT_DIR / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    # 保存完整 prompt
    prompt_file = run_dir / "prompt.txt"
    with open(prompt_file, "w", encoding="utf-8") as f:
        for msg in messages:
            f.write(f"=== {msg['role'].upper()} ===\n{msg['content']}\n\n")

    # 保存 LLM 响应
    response_file = run_dir / "response.json"
    with open(response_file, "w", encoding="utf-8") as f:
        json.dump(response, f, ensure_ascii=False, indent=2)

    # 保存 LLM 文本输出（方便阅读）
    text_file = run_dir / "response.txt"
    with open(text_file, "w", encoding="utf-8") as f:
        f.write(response["content"])

    # 保存实验配置
    config_file = run_dir / "config.json"
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": timestamp,
            "model": LLM_CONFIG["model"],
            "temperature": LLM_CONFIG["temperature"],
            "max_tokens": LLM_CONFIG["max_tokens"],
            "token_usage": response.get("usage", {}),
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] 结果已保存到 {run_dir}")
    print(f"  prompt.txt    — 完整 prompt")
    print(f"  response.json — API 响应（含 token 统计）")
    print(f"  response.txt  — LLM 输出文本")
    print(f"  config.json   — 实验配置")


# ================================================================
# Main
# ================================================================

def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"=== LLM 回合规划实验 [{timestamp}] ===\n")

    # Step 1: 构建游戏状态
    print("[1/5] 构建实验游戏状态...")
    state, viewer_id = build_experiment_state()
    print(f"  active player: {viewer_id}")
    print(f"  round: {state.round}, phase: {state.phase.value}")
    print(f"  locations: {len(state.locations)}")
    print(f"  hand cards: {len(state.get_player(viewer_id).hand)}")
    print(f"  court cards (jin): {len(state.jin_court)}, (north): {len(state.north_court)}")

    # Step 2: 构建游戏视图文本
    print("\n[2/5] 构建游戏视图文本...")
    game_view_text = build_game_view_text(state, viewer_id)
    print(f"  game view: {len(game_view_text)} chars")

    # Step 3: 构建 Prompt
    print("\n[3/5] 构建 Prompt...")
    system_prompt, messages = build_prompt(viewer_id, game_view_text)
    total_chars = sum(len(m["content"]) for m in messages) + len(system_prompt)
    print(f"  total prompt size: {total_chars} chars (~{total_chars // 4} tokens estimated)")

    # Step 4: 调用 LLM
    print("\n[4/5] 调用 LLM API...")
    try:
        response = call_llm(system_prompt, messages)
        print(f"  model: {response['model']}")
        usage = response.get("usage", {})
        print(f"  tokens: {usage.get('prompt_tokens', '?')} prompt + "
              f"{usage.get('completion_tokens', '?')} completion = "
              f"{usage.get('total_tokens', '?')} total")
        print(f"  finish: {response['finish_reason']}")

        # 打印 LLM 输出
        print("\n" + "=" * 60)
        print("LLM 输出:")
        print("=" * 60)
        print(response["content"])
        print("=" * 60)

    except Exception as e:
        print(f"\n[ERROR] LLM 调用失败: {e}")
        print("请检查 API 配置（OPENAI_API_KEY, OPENAI_BASE_URL, LLM_MODEL）")
        # 即使 LLM 失败，也保存 prompt 供手动测试
        response = {"error": str(e), "content": "", "usage": {}}

    # Step 5: 保存结果
    print("\n[5/5] 保存结果...")
    save_results(system_prompt, messages, response, timestamp)

    print("\n=== 实验完成 ===")


if __name__ == "__main__":
    main()
