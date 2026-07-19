"""视窗系统 CLI — 分层数字菜单，无需记忆关键字。

用法:
    python viewport_cli.py        交互模式（推荐）
    python viewport_cli.py -q     快速查询模式（兼容旧语法）

交互模式完全使用数字选择，层层递进：
    主菜单 → 选视角 → 选类别 → （可选子类） → 显示结果
"""

import os
import sys
import json
import random

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stdin.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(__file__))

from config.version import Version
from ai.heuristic_ai import HeuristicAI
from engine.game import GameEngine
from viewport import create_viewport, SnapshotViewport


# ═══════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════

FACTION_LABEL = {"north": "北方", "jin": "东晋"}
PLAYER_IDS = ["north", "jin_1", "jin_2", "jin_3"]


def _player_label(state, pid: str) -> str:
    """返回带阵营标签的玩家显示名。"""
    p = state.get_player(pid)
    if p is None:
        return pid
    f = FACTION_LABEL.get(p.faction.value if hasattr(p.faction, 'value') else str(p.faction), '?')
    return f"{pid}({f})"


def _input_choice(max_val: int, allow_back: bool = True) -> int:
    """获取用户数字输入。0 表示返回上级。"""
    while True:
        try:
            raw = input("  选择 > ").strip()
            if not raw:
                continue
            val = int(raw)
            if 0 <= val <= max_val:
                return val
            hint = f"请输入 0-{max_val} 之间的数字"
            print(f"    [!] {hint}")
        except ValueError:
            print(f"    [!] 请输入有效数字")
        except (EOFError, KeyboardInterrupt):
            print("\n  已退出")
            sys.exit(0)


def _any_key():
    """等待用户按回车。"""
    try:
        input("\n  按 Enter 返回...")
    except (EOFError, KeyboardInterrupt):
        pass


def _card_line(c: dict) -> str:
    """单行卡牌摘要。"""
    name = c.get("name", "?")
    cost = c.get("cost", 0)
    cat = c.get("card_type", "?")
    effect = c.get("effect_summary", "")
    cost_str = f"费{cost}" if cost > 0 else "费0"
    line = f"{name}({cat} {cost_str})"
    if effect:
        line += f" — {effect}"
    return line


# ═══════════════════════════════════════════════════════════════════════
# 游戏管理器
# ═══════════════════════════════════════════════════════════════════════

class GameRunner:
    """封装游戏初始化和步进逻辑。"""

    def __init__(self):
        self.engine: GameEngine = None

    def init_game(self):
        """初始化新游戏（setup + 准备阶段）。"""
        print("\n  ⏳ 正在初始化游戏...")
        version = Version.load('v1.0')
        agents = [
            HeuristicAI(player_id="north", seed=1),
            HeuristicAI(player_id="jin_1", seed=2),
            HeuristicAI(player_id="jin_2", seed=3),
            HeuristicAI(player_id="jin_3", seed=4),
        ]
        self.engine = GameEngine(
            agents=agents, version=version,
            seed=random.randint(0, 999999),
        )

        # 只执行 setup，不进入完整游戏循环
        from engine.phases import setup_game
        state = setup_game(
            self.engine.library, self.engine.agents,
            self.engine.rng.randint(0, 999999),
            version=version,
            map_adjacencies=self.engine.map_adjacencies,
            action_system=self.engine.action_system,
            logger=None,
        )
        self.engine.state = state
        self.engine._post_setup_init()
        print(f"  ✅ 初始化完成 — 第{state.round}回合 {state.phase.value}阶段\n")

    @property
    def state(self):
        return self.engine.state

    def step_one_player(self) -> bool:
        """推进1个玩家的完整回合。返回 False 表示游戏结束。"""
        state = self.engine.state
        if state.phase.name == 'GAME_OVER':
            return False

        from models.enums import PhaseType

        # 如果还在准备阶段，先执行准备阶段
        if state.phase == PhaseType.PREPARATION:
            from engine.phases import run_preparation_phase
            run_preparation_phase(state, self.engine.rng)
            state.phase = PhaseType.ACTION
            # 区控奖励
            from rules.scoring import award_region_control_phase
            award_region_control_phase(state, player_id=None)
            self._fix_turn_order()

        # 行动阶段：当前玩家执行完整回合
        if state.phase == PhaseType.ACTION:
            if state.active_player_index >= len(state.turn_order):
                # 所有玩家都行动完毕 → 结算阶段
                from engine.phases import run_settlement_phase
                run_settlement_phase(state, self.engine.rng)
                # run_settlement_phase 内部已处理: round+=1, phase=PREPARATION 或 GAME_OVER
                if state.phase == PhaseType.GAME_OVER:
                    return False
                return True

            pid = state.turn_order[state.active_player_index]
            self.engine._run_player_turn(state, pid)
            state.active_player_index += 1
            return True

        return True

    def step_one_round(self) -> bool:
        """推进1整轮。返回 False 表示游戏结束。"""
        state = self.engine.state
        if state.phase.name == 'GAME_OVER':
            return False
        self.engine._run_round()
        return state.phase.name != 'GAME_OVER'

    def make_viewport(self, player_id: str, mode: str = "live"):
        """创建某玩家的视窗。"""
        available = []
        try:
            available = self.engine._get_available_actions(
                self.engine.state, player_id)
        except Exception:
            pass
        return create_viewport(self.engine.state, player_id, available, mode=mode)

    def _fix_turn_order(self):
        """确保 turn_order 正确（setup 后可能未设置）。"""
        state = self.engine.state
        if not state.turn_order:
            state.turn_order = ["north", "jin_1", "jin_2", "jin_3"]



# ═══════════════════════════════════════════════════════════════════════
# 视图层 — 所有信息展示函数
# ═══════════════════════════════════════════════════════════════════════

class ViewDisplayer:
    """负责格式化输出各种视窗数据。"""

    @staticmethod
    def show_hand(vp, pid: str):
        cards = vp.get_my_hand()
        print(f"\n  ┌─ 我的手牌 ({len(cards)}张) ──────────────────────────────")
        if not cards:
            print("  │ (无)")
        else:
            for i, c in enumerate(cards):
                print(f"  │ {i+1:2d}. {_card_line(c)}")
        print(f"  └──────────────────────────────────────────────")

    @staticmethod
    def show_staff(vp, pid: str):
        cards = vp.get_my_staff()
        print(f"\n  ┌─ 我的幕僚区 ({len(cards)}人) ────────────────────────────")
        if not cards:
            print("  │ (无)")
        else:
            for i, c in enumerate(cards):
                markers = c.get("markers", {})
                m_parts = []
                for k, v in markers.items():
                    if v:
                        m_parts.append(f"{k}+{v}")
                m_str = " | ".join(m_parts) if m_parts else ""
                print(f"  │ {i+1:2d}. {_card_line(c)}")
                if m_str:
                    print(f"  │     标记: {m_str}")
        print(f"  └──────────────────────────────────────────────")

    @staticmethod
    def show_hero(vp, pid: str):
        hero = vp.get_my_hero()
        print(f"\n  ┌─ 我的英雄 ──────────────────────────────────────")
        if hero is None:
            print("  │ (无)")
        else:
            print(f"  │ 名称: {hero.get('name', '?')}")
            effect = hero.get("effect_text", "")
            if effect:
                print(f"  │ 效果: {effect}")
            markers = hero.get("markers", {})
            if markers:
                m_str = " | ".join(f"{k}+{v}" for k, v in markers.items() if v)
                if m_str:
                    print(f"  │ 标记: {m_str}")
        print(f"  └──────────────────────────────────────────────")

    @staticmethod
    def show_history(vp, pid: str):
        cards = vp.get_my_history()
        print(f"\n  ┌─ 我的史书区 ({len(cards)}张) ──────────────────────────")
        if not cards:
            print("  │ (无)")
        else:
            for i, c in enumerate(cards):
                hv = c.get("history_vp", 0)
                print(f"  │ {i+1:2d}. {_card_line(c)}  [史书VP: {hv}]")
        print(f"  └──────────────────────────────────────────────")

    @staticmethod
    def show_my_attrs(vp, pid: str):
        me = vp.get_my_player()
        print(f"\n  ┌─ 我的属性 ─────────────────────────────────────")
        print(f"  │ VP: {me.get('vp', 0)}")
        print(f"  │ 军力: {me.get('military', 0)}")
        print(f"  │ 手牌数: {me.get('hand_count', 0)}")
        print(f"  │ 部队(已放置): {me.get('army_placed_count', 0)}")
        print(f"  │ 部队(储备区): {me.get('army_reserve_count', 0)}")
        if me.get("faction") == "jin":
            print(f"  │ 威望: {me.get('prestige', 0)}")
            print(f"  │ 功绩: {me.get('contribution', 0)}")
            print(f"  │ 顺位: {me.get('order', 0)}")
        markers = {k: v for k, v in me.items() if k.startswith("marker_") and v}
        if markers:
            m_str = " | ".join(f"{k.replace('marker_','')}+{v}" for k, v in markers.items())
            print(f"  │ 标记: {m_str}")
        print(f"  └──────────────────────────────────────────────")

    @staticmethod
    def show_other_player(vp, pid: str, runner: GameRunner):
        """展示其他某个玩家的公开信息。"""
        other = vp.get_other_player(pid)
        if not other:
            print(f"\n  [!] 玩家 {pid} 不存在")
            _any_key()
            return
        print(f"\n  ┌─ 【{_player_label(runner.state, pid)}】公开信息 ─────")
        print(f"  │ VP: {other.get('vp', 0)}")
        print(f"  │ 军力: {other.get('military', 0)}")
        print(f"  │ 手牌数: {other.get('hand_count', 0)}")
        print(f"  │ 部队(已放): {other.get('army_placed_count', 0)}")
        print(f"  │ 幕僚数: {other.get('staff_count', 0)}")
        staff_names = other.get("staff_names", [])
        if staff_names:
            print(f"  │ 幕僚: {', '.join(staff_names)}")
        hero = other.get("hero")
        if hero:
            print(f"  │ 英雄: {hero.get('name', '?')}")
        if other.get("faction") == "jin":
            print(f"  │ 威望: {other.get('prestige', 0)}")
            print(f"  │ 功绩: {other.get('contribution', 0)}")
            print(f"  │ 顺位: {other.get('order', 0)}")
        print(f"  └──────────────────────────────────────────────")

    @staticmethod
    def show_all_locations(vp):
        locs = vp.get_all_locations()
        # 按控制者分组
        groups = {}
        for lid, loc in locs.items():
            c = loc.get("controller", "?")
            groups.setdefault(c, []).append(lid)
        print(f"\n  ┌─ 全部地点 ({len(locs)}个) ───────────────────────────")
        ctrl_labels = {
            "north": "北方控制", "jin_1": "东晋1", "jin_2": "东晋2", "jin_3": "东晋3",
            "sima": "司马家", "neutral": "中立", "empty": "空地",
        }
        for ctrl, lids in sorted(groups.items()):
            label = ctrl_labels.get(ctrl, ctrl)
            fortified = []
            normal = []
            for lid in lids:
                loc = locs[lid]
                if loc.get("is_fortified"):
                    fortified.append(lid)
                else:
                    normal.append(lid)
            parts = []
            if fortified:
                parts.append(" | ".join(f"🏰{l}" for l in fortified))
            if normal:
                parts.append(" | ".join(normal))
            print(f"  │ [{label}] {' | '.join(parts)}")
        print(f"  └──────────────────────────────────────────────")

    @staticmethod
    def show_friendly_locations(vp, pid: str):
        friendly = vp.get_friendly_locations()
        print(f"\n  ┌─ 友方地点 ─────────────────────────────────────")
        if not friendly:
            print("  │ (无)")
        else:
            locs = vp.get_all_locations()
            for lid in friendly:
                loc = locs.get(lid, {})
                fortified = "🏰" if loc.get("is_fortified") else "  "
                ctrl = loc.get("controller", "?")
                print(f"  │ {fortified} {lid}  [{ctrl}]")
        print(f"  └──────────────────────────────────────────────")

    @staticmethod
    def show_adjacent(vp, pid: str, runner: GameRunner):
        """交互式查询邻接地。"""
        locs = vp.get_all_locations()
        loc_names = sorted(locs.keys())
        print(f"\n  ┌─ 可用地点 ─────────────────────────────────────")
        for i, name in enumerate(loc_names[:20]):
            print(f"  │ {i+1:2d}. {name}")
        if len(loc_names) > 20:
            print(f"  │ ... （共{len(loc_names)}个）")
        print(f"  │  0. 返回")
        print(f"  └──────────────────────────────────────────────")

        choice = _input_choice(len(loc_names))
        if choice == 0:
            return
        src = loc_names[choice - 1]
        adj = vp.get_adjacent_locations(src)
        print(f"\n  ┌─ 与【{src}】邻接的地点 ──────────────────────")
        if not adj:
            print("  │ (无)")
        else:
            for lid in adj:
                loc = locs.get(lid, {})
                ctrl = loc.get("controller", "?")
                print(f"  │   {lid}  [{ctrl}]")
        print(f"  └──────────────────────────────────────────────")

    @staticmethod
    def show_court(vp, pid: str):
        """显示朝堂牌。"""
        print(f"\n  ┌─ 朝堂牌 ───────────────────────────────────────")
        for faction in ["north", "jin"]:
            label = "北方" if faction == "north" else "东晋"
            cards = vp.get_court_cards(faction)
            print(f"  │ [{label}朝堂] ({len(cards)}张)")
            for c in cards:
                print(f"  │   {_card_line(c)}")
        print(f"  └──────────────────────────────────────────────")

    @staticmethod
    def show_tracks(vp, pid: str):
        """显示轨道数据。"""
        vp_track = vp.get_vp_track()
        prestige = vp.get_prestige_track()
        contrib = vp.get_contribution_track()
        order_t = vp.get_order_track()
        culture = vp.get_culture_tracks()

        print(f"\n  ┌─ 轨道数据 ─────────────────────────────────────")

        print(f"  │ 【VP轨道】")
        for pid_key in PLAYER_IDS:
            v = vp_track.get(pid_key, 0)
            label = _player_label(_runner.state if hasattr(ViewDisplayer, '_runner') else None, pid_key)
            if hasattr(ViewDisplayer, '_runner') and ViewDisplayer._runner:
                label = _player_label(ViewDisplayer._runner.state, pid_key)
            print(f"  │   {pid_key}: {v}")
        sima_vp = vp_track.get("sima", 0)
        print(f"  │   sima(司马家): {sima_vp}")

        if prestige:
            print(f"  │ 【威望】")
            for pid_key in ["jin_1", "jin_2", "jin_3"]:
                if pid_key in prestige:
                    print(f"  │   {pid_key}: {prestige[pid_key]}")

        if contrib:
            print(f"  │ 【功绩】")
            for pid_key in ["jin_1", "jin_2", "jin_3"]:
                if pid_key in contrib:
                    print(f"  │   {pid_key}: {contrib[pid_key]}")

        if order_t:
            print(f"  │ 【顺位】")
            for pid_key in ["jin_1", "jin_2", "jin_3"]:
                if pid_key in order_t:
                    print(f"  │   {pid_key}: {order_t[pid_key]}")

        if culture:
            print(f"  │ 【文化】")
            for ctype, cdata in culture.items():
                levels = cdata.get("levels", {}) if isinstance(cdata, dict) else {}
                print(f"  │   {ctype}: {levels}")

        print(f"  └──────────────────────────────────────────────")

    @staticmethod
    def show_decks(vp, pid: str):
        """显示牌库信息。"""
        print(f"\n  ┌─ 牌库信息 ─────────────────────────────────────")
        print(f"  │ 主牌库: {vp.get_main_deck_count()} 张")
        md = vp.get_main_discard()
        if md:
            print(f"  │ 主弃牌堆 ({len(md)}张): {', '.join(md[:10])}")
            if len(md) > 10:
                print(f"  │   ... (+{len(md)-10}张)")
        else:
            print(f"  │ 主弃牌堆: (空)")

        print(f"  │ 北方牌库: {vp.get_national_deck_count('north')} 张")
        nd = vp.get_national_discard("north")
        if nd:
            print(f"  │ 北方弃牌堆 ({len(nd)}张): {', '.join(nd[:5])}")

        print(f"  │ 东晋牌库: {vp.get_national_deck_count('jin')} 张")
        jd = vp.get_national_discard("jin")
        if jd:
            print(f"  │ 东晋弃牌堆 ({len(jd)}张): {', '.join(jd[:5])}")

        print(f"  │ 强制事件堆: {vp.get_forced_event_pile_count()} 张")
        print(f"  │ 流民供应区: {vp.get_refugee_supply_count()} 张")
        print(f"  └──────────────────────────────────────────────")

    @staticmethod
    def show_actions(vp, pid: str):
        actions = vp.get_available_actions()
        print(f"\n  ┌─ 可用行动 ─────────────────────────────────────")
        if not actions:
            print("  │ (无可用行动)")
        else:
            for cat, acts in actions.items():
                if isinstance(acts, list):
                    print(f"  │ 【{cat}】({len(acts)}个)")
                    for a in acts[:5]:
                        label = a.get("description", str(a)) if isinstance(a, dict) else str(a)
                        if len(label) > 60:
                            label = label[:57] + "..."
                        print(f"  │   · {label}")
                    if len(acts) > 5:
                        print(f"  │   ... (+{len(acts)-5}个)")
        print(f"  └──────────────────────────────────────────────")

    @staticmethod
    def show_summary(vp, pid: str):
        summary = vp.query("summary")
        print(f"\n  ┌─ 玩家摘要 ─────────────────────────────────────")
        print(f"  │ {summary}")
        print(f"  └──────────────────────────────────────────────")

    @staticmethod
    def show_full(vp, pid: str):
        data = vp.to_dict()
        pub = data.get("public", {})
        priv = data.get("private", {})

        print(f"\n  ┌─ 完整视窗 ({pid}) ──────────────────────────────")
        print(f"  │ 回合: {data.get('round')}  阶段: {data.get('phase')}")

        # 私有信息概要
        hand = priv.get("hand", [])
        staff = priv.get("staff", [])
        history = priv.get("history", [])
        hero = priv.get("hero")
        print(f"  │ --- 私有信息 ---")
        print(f"  │ 手牌({len(hand)}张): {', '.join(c.get('name','?') for c in hand)}")
        if staff:
            print(f"  │ 幕僚({len(staff)}人): {', '.join(c.get('name','?') for c in staff)}")
        if history:
            print(f"  │ 史书({len(history)}张): {', '.join(c.get('name','?') for c in history)}")
        if hero:
            print(f"  │ 英雄: {hero.get('name', '?')}")

        # 公开信息概要
        players = pub.get("players", {})
        print(f"  │ --- 公开信息 ---")
        for pkey, pinfo in players.items():
            hc = pinfo.get("hand_count", 0)
            vp_val = pinfo.get("vp", 0)
            print(f"  │ {pkey}: VP={vp_val} 手牌={hc}张")

        # 地图概要
        locs = pub.get("map", {}).get("locations", {})
        ctrl_count = {}
        for lid, linfo in locs.items():
            c = linfo.get("controller", "?")
            ctrl_count[c] = ctrl_count.get(c, 0) + 1
        print(f"  │ 地图: {' | '.join(f'{k}:{v}' for k,v in sorted(ctrl_count.items()))}")

        print(f"  └──────────────────────────────────────────────")

        # 也输出 JSON 文件路径
        snap = SnapshotViewport.from_state(ViewDisplayer._runner.state, pid)
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(log_dir, exist_ok=True)
        json_path = os.path.join(log_dir, f"viewport_{pid}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(snap.to_json())
        print(f"  📁 完整JSON已保存: {json_path}")


# ═══════════════════════════════════════════════════════════════════════
# 菜单系统
# ═══════════════════════════════════════════════════════════════════════

class ViewportMenu:
    """分层菜单导航。"""

    def __init__(self, runner: GameRunner):
        self.runner = runner
        self.display = ViewDisplayer()
        ViewDisplayer._runner = runner  # 让 display 能访问 game state

    # ─── 主菜单 ────────────────────────────────────────────────────

    def run(self):
        """主循环。"""
        self.runner.init_game()
        self._print_welcome()

        while True:
            if self.runner.state.phase.name == 'GAME_OVER':
                self._print_game_over()
                break

            self._print_state_bar()
            print(f"  1. 视窗查询（选视角分层查看信息）")
            print(f"  2. 推进 1 步（1个玩家完整回合）")
            print(f"  3. 推进 1 整轮")
            print(f"  4. 游戏状态详情")
            print(f"  5. 导出全部玩家视窗 JSON")
            print(f"  0. 退出")
            print()

            choice = _input_choice(5)
            if choice == 0:
                print("  再见！")
                break
            elif choice == 1:
                self._menu_perspective()
            elif choice == 2:
                self._do_step()
            elif choice == 3:
                self._do_round()
            elif choice == 4:
                self._do_state_detail()
            elif choice == 5:
                self._do_export_all()

    def _print_welcome(self):
        print("═" * 58)
        print("  视窗系统 CLI — 分层菜单查询")
        print("  所有操作通过数字选择，无需记忆关键字")
        print("═" * 58)

    def _print_state_bar(self):
        """顶部状态栏。"""
        state = self.runner.state
        phase_cn = {"preparation": "准备", "action": "行动", "settlement": "结算",
                     "game_over": "结束"}.get(state.phase.value, state.phase.value)
        current = ""
        if state.turn_order and state.active_player_index < len(state.turn_order):
            current = state.turn_order[state.active_player_index]

        # 快速摘要行
        parts = []
        for pid in PLAYER_IDS:
            p = state.get_player(pid)
            if p:
                f = "北" if (p.faction.value if hasattr(p.faction, 'value') else str(p.faction)) == "north" else "晋"
                parts.append(f"{pid}({f}) VP:{p.vp} 军:{p.military} 牌:{len(p.hand)}")
        summary = " │ ".join(parts)

        print(f"\n{'─' * 58}")
        print(f"  第{state.round}回合 · {phase_cn}阶段 · 当前行动: {current}")
        print(f"  {summary}")
        print(f"{'─' * 58}\n")

    def _print_game_over(self):
        state = self.runner.state
        print(f"\n{'═' * 58}")
        print(f"  游戏结束 — {state.game_end_reason or '第10回合'}")
        print(f"{'═' * 58}")
        for p in state.get_all_players():
            print(f"  {_player_label(state, p.player_id)}: {p.vp} VP")

    # ─── 主菜单操作 ────────────────────────────────────────────────

    def _do_step(self):
        print("\n  ⏳ 执行 1 步...")
        ok = self.runner.step_one_player()
        if not ok:
            print("  ⚠ 游戏已结束")
        else:
            state = self.runner.state
            idx = state.active_player_index
            if idx < len(state.turn_order):
                print(f"  ✅ → 当前行动: {state.turn_order[idx]}")
            else:
                print(f"  ✅ → 阶段结束")

    def _do_round(self):
        state = self.runner.state
        old = state.round
        print(f"\n  ⏳ 执行第{old}回合...")
        ok = self.runner.step_one_round()
        if not ok:
            print("  ⚠ 游戏已结束")
        else:
            print(f"  ✅ 第{old}回合完成 → 第{self.runner.state.round}回合")

    def _do_state_detail(self):
        """显示详细游戏状态（类似 play_game.py 的回合公开信息）。"""
        state = self.runner.state
        phase_cn = {"preparation": "准备", "action": "行动", "settlement": "结算",
                     "game_over": "结束"}.get(state.phase.value, state.phase.value)
        print(f"\n{'─' * 58}")
        print(f"  第{state.round}回合 · {phase_cn}阶段 · 当前: {state.turn_order[state.active_player_index] if state.active_player_index < len(state.turn_order) else '?'}")
        print(f"{'─' * 58}")

        # 行动顺位
        print(f"\n  【行动顺位】")
        print(f"  {' → '.join(state.turn_order)}")

        # 玩家详情表
        print(f"\n  【玩家状态】")
        print(f"  {'玩家':<8} {'阵营':<6} {'VP':>4} {'军力':>4} {'功绩':>4} {'威望':>4} {'顺位':>4} {'手牌':>4} {'部队':>4}")
        print(f"  {'-' * 52}")
        for p in state.get_all_players():
            f = FACTION_LABEL.get(p.faction.value if hasattr(p.faction, 'value') else str(p.faction), '?')
            contrib = str(p.contribution) if (p.faction.value if hasattr(p.faction, 'value') else str(p.faction)) == "jin" else "-"
            prestige = str(p.prestige) if (p.faction.value if hasattr(p.faction, 'value') else str(p.faction)) == "jin" else "-"
            order = str(p.order) if (p.faction.value if hasattr(p.faction, 'value') else str(p.faction)) == "jin" else "-"
            army = f"{p.army_placed_count}/{p.army_reserve_count}"
            print(f"  {p.player_id:<8} {f:<6} {p.vp:>4} {p.military:>4} {contrib:>4} {prestige:>4} {order:>4} {len(p.hand):>4} {army:>4}")

        # 地图控制
        print(f"\n  【地图控制】")
        locs = state.locations
        groups = {}
        for lid, loc in locs.items():
            c = loc.controller.value if hasattr(loc.controller, 'value') else str(loc.controller)
            groups.setdefault(c, []).append(lid)
        for ctrl, lids in sorted(groups.items()):
            print(f"  {ctrl:<10} {' '.join(lids)}")

        # 牌库
        print(f"\n  【牌库】")
        for pid in PLAYER_IDS:
            deck = state.get_national_deck(pid)
            discard = state.get_national_discard(pid)
            court = state.get_court_cards(pid)
            print(f"  {pid}: 牌库{len(deck)}张  弃牌{len(discard)}张  朝堂{len(court)}张")
        print(f"  主牌库: {len(state.main_deck)}张  主弃牌: {len(state.main_discard)}张")

        # 朝堂牌详情
        for pid in PLAYER_IDS:
            court = state.get_court_cards(pid)
            if court:
                names = [f"{c.name}(费{c.cost})" for c in court]
                print(f"  {pid}朝堂: {', '.join(names)}")

        print()

    def _do_export_all(self):
        """导出全部4个玩家的完整视窗JSON。"""
        state = self.runner.state
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(log_dir, exist_ok=True)

        print(f"\n  ┌─ 导出所有玩家视窗 ────────────────────────────")
        for pid in PLAYER_IDS:
            snap = SnapshotViewport.from_state(state, pid)
            json_path = os.path.join(log_dir, f"viewport_{pid}.json")
            with open(json_path, "w", encoding="utf-8") as f:
                f.write(snap.to_json())

            # 简要预览
            data = snap.to_dict()
            hand = data.get("private", {}).get("hand", [])
            hand_names = [c['name'] for c in hand]
            pub_player = data.get("public", {}).get("players", {}).get(pid, {})
            print(f"  │ {pid}: VP={pub_player.get('vp','?')} "
                  f"手牌({len(hand)}张): {', '.join(hand_names[:4])}"
                  f"{'...' if len(hand_names) > 4 else ''}")
        print(f"  │ 📁 保存至: {log_dir}/")
        print(f"  └──────────────────────────────────────────────\n")

    # ─── 二级菜单：选择视角 ─────────────────────────────────────────

    def _menu_perspective(self):
        """选择从哪个玩家的视角查看。"""
        state = self.runner.state
        while True:
            print(f"\n  ┌─ 选择视角 ─────────────────────────────────────")
            idx = 1
            pid_map = {}
            for pid in PLAYER_IDS:
                p = state.get_player(pid)
                if p:
                    f = FACTION_LABEL.get(p.faction.value if hasattr(p.faction, 'value') else str(p.faction), '?')
                    vp_val = p.vp
                    hand_n = len(p.hand)
                    military = p.military
                    extra = ""
                    if (p.faction.value if hasattr(p.faction, 'value') else str(p.faction)) == "jin":
                        extra = f" 威望:{p.prestige}"
                    print(f"  │ {idx}. {pid} ({f}) — VP:{vp_val} 军力:{military} 手牌:{hand_n}{extra}")
                    pid_map[idx] = pid
                    idx += 1
            print(f"  │ 0. 返回主菜单")
            print(f"  └──────────────────────────────────────────────")

            choice = _input_choice(len(pid_map))
            if choice == 0:
                return
            pid = pid_map[choice]
            self._menu_category(pid)

    # ─── 三级菜单：选择信息类别 ─────────────────────────────────────

    def _menu_category(self, pid: str):
        """选择查看哪类信息。"""
        state = self.runner.state
        vp = self.runner.make_viewport(pid)
        me = vp.get_my_player()
        hand_n = me.get("hand_count", 0)
        staff_n = me.get("staff_count", 0)
        history_n = me.get("history_count", 0)

        p = state.get_player(pid)
        faction = p.faction.value if p and hasattr(p.faction, 'value') else (str(p.faction) if p else "?")
        f_label = FACTION_LABEL.get(faction, faction)

        while True:
            print(f"\n  ┌─ 【{pid} ({f_label})】选择查看内容 ──────────────")
            print(f"  │  1. 我的手牌 ({hand_n}张)")
            print(f"  │  2. 我的幕僚区 ({staff_n}人)")
            print(f"  │  3. 我的英雄")
            print(f"  │  4. 我的史书区 ({history_n}张)")
            print(f"  │  5. 我的属性 (VP/军力/部队等)")
            print(f"  │  6. 其他玩家公开信息 →")
            print(f"  │  7. 地图信息 →")
            print(f"  │  8. 朝堂牌")
            print(f"  │  9. 轨道数据")
            print(f"  │ 10. 牌库信息")
            print(f"  │ 11. 可用行动")
            print(f"  │ 12. 玩家摘要")
            print(f"  │ 13. 完整视窗 (含JSON导出)")
            print(f"  │  0. 返回上级")
            print(f"  └──────────────────────────────────────────────")

            choice = _input_choice(13)
            if choice == 0:
                return

            vp = self.runner.make_viewport(pid)  # 每次刷新

            if choice == 1:
                self.display.show_hand(vp, pid)
                _any_key()
            elif choice == 2:
                self.display.show_staff(vp, pid)
                _any_key()
            elif choice == 3:
                self.display.show_hero(vp, pid)
                _any_key()
            elif choice == 4:
                self.display.show_history(vp, pid)
                _any_key()
            elif choice == 5:
                self.display.show_my_attrs(vp, pid)
                _any_key()
            elif choice == 6:
                self._menu_other_players(vp, pid)
            elif choice == 7:
                self._menu_map(vp, pid)
            elif choice == 8:
                self.display.show_court(vp, pid)
                _any_key()
            elif choice == 9:
                self.display.show_tracks(vp, pid)
                _any_key()
            elif choice == 10:
                self.display.show_decks(vp, pid)
                _any_key()
            elif choice == 11:
                self.display.show_actions(vp, pid)
                _any_key()
            elif choice == 12:
                self.display.show_summary(vp, pid)
                _any_key()
            elif choice == 13:
                self.display.show_full(vp, pid)
                _any_key()

    # ─── 四级子菜单 ─────────────────────────────────────────────────

    def _menu_other_players(self, vp, viewer_pid: str):
        """选择查看哪个其他玩家。"""
        state = self.runner.state
        others = [p for p in PLAYER_IDS if p != viewer_pid]
        while True:
            print(f"\n  ┌─ 查看其他玩家公开信息 ────────────────────────")
            idx = 1
            pid_map = {}
            for pid in others:
                other = vp.get_other_player(pid)
                vp_val = other.get("vp", "?")
                hc = other.get("hand_count", "?")
                army = other.get("army_placed_count", "?")
                staff = other.get("staff_count", "?")
                hero_name = ""
                hero = other.get("hero")
                if hero:
                    hero_name = f" 英雄:{hero.get('name','?')}"
                print(f"  │ {idx}. {_player_label(state, pid)} — "
                      f"VP:{vp_val} 军力:{other.get('military','?')} 手牌:{hc} 部队:{army} 幕僚:{staff}{hero_name}")
                pid_map[idx] = pid
                idx += 1
            print(f"  │ 0. 返回")
            print(f"  └──────────────────────────────────────────────")

            choice = _input_choice(len(pid_map))
            if choice == 0:
                return
            target = pid_map[choice]
            vp_fresh = self.runner.make_viewport(viewer_pid)
            self.display.show_other_player(vp_fresh, target, self.runner)
            _any_key()

    def _menu_map(self, vp, pid: str):
        """地图子菜单。"""
        while True:
            locs = vp.get_all_locations()
            friendly = vp.get_friendly_locations()
            print(f"\n  ┌─ 地图信息 ─────────────────────────────────────")
            print(f"  │  1. 全部地点 ({len(locs)}个)")
            print(f"  │  2. 友方地点 ({len(friendly)}个)")
            print(f"  │  3. 特定地点（输入名称）")
            print(f"  │  4. 邻接地（输入名称）")
            print(f"  │  0. 返回")
            print(f"  └──────────────────────────────────────────────")

            choice = _input_choice(4)
            if choice == 0:
                return

            vp = self.runner.make_viewport(pid)
            if choice == 1:
                self.display.show_all_locations(vp)
                _any_key()
            elif choice == 2:
                self.display.show_friendly_locations(vp, pid)
                _any_key()
            elif choice == 3:
                self._query_location_by_name(vp)
            elif choice == 4:
                self.display.show_adjacent(vp, pid, self.runner)
                _any_key()

    def _query_location_by_name(self, vp):
        """让用户输入地名来查询。"""
        locs = vp.get_all_locations()
        loc_names = sorted(locs.keys())

        # 显示可选地点列表
        print(f"\n  ┌─ 可用地点 ─────────────────────────────────────")
        cols = 5
        for i in range(0, len(loc_names), cols):
            row = "  │ " + "  ".join(f"{loc_names[j]:<8}" for j in range(i, min(i+cols, len(loc_names))))
            print(row)
        print(f"  │  0. 返回")
        print(f"  └──────────────────────────────────────────────")

        print(f"\n  请输入地名（支持中文）:")
        try:
            name = input("  地名 > ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if not name or name == "0":
            return

        loc = vp.get_location(name)
        if loc is None:
            print(f"\n  [!] 未找到地点: {name}")
            _any_key()
            return

        print(f"\n  ┌─ 地点详情: {name} ─────────────────────────────")
        ctrl_labels = {
            "north": "北方", "jin_1": "东晋1", "jin_2": "东晋2",
            "jin_3": "东晋3", "sima": "司马家", "neutral": "中立", "empty": "空地",
        }
        ctrl = loc.get("controller", "?")
        print(f"  │ 控制者: {ctrl_labels.get(ctrl, ctrl)}")
        print(f"  │ 已加固: {'是 🏰' if loc.get('is_fortified') else '否'}")
        culture = loc.get("culture_marker")
        if culture:
            print(f"  │ 文化标记: {culture}")
        if loc.get("culture_locked"):
            print(f"  │ 文化锁定: 是")
        print(f"  └──────────────────────────────────────────────")
        _any_key()


# ═══════════════════════════════════════════════════════════════════════
# 兼容模式：一次性 CLI 查询
# ═══════════════════════════════════════════════════════════════════════

def one_shot_query(player_id: str, query_path: str):
    """兼容旧命令行的一次性查询。"""
    runner = GameRunner()
    runner.init_game()
    from viewport import QueryEngine

    if player_id not in PLAYER_IDS:
        print(f"未知玩家: {player_id}")
        print(f"可用: {', '.join(PLAYER_IDS)}")
        sys.exit(1)

    vp = runner.make_viewport(player_id)
    qe = QueryEngine(vp)
    result = qe.query(query_path)

    if isinstance(result, (dict, list)):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result)


# ═══════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════

def main():
    # 兼容旧的一次性查询模式
    if len(sys.argv) >= 3:
        one_shot_query(sys.argv[1], sys.argv[2])
        return

    # -q 快速查询模式
    if len(sys.argv) == 2 and sys.argv[1] == "-q":
        print("快速查询模式: python viewport_cli.py <玩家ID> <查询路径>")
        print(f"玩家ID: {', '.join(PLAYER_IDS)}")
        print("示例: python viewport_cli.py north my.hand")
        return

    # 默认：交互式分层菜单
    runner = GameRunner()
    menu = ViewportMenu(runner)
    menu.run()


if __name__ == "__main__":
    main()
