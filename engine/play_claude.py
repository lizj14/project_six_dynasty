"""play_claude.py — 文件驱动的对局驱动器，让 coding agent（Claude）直接操控六朝何事。

参考领土(llm_coding_agent_test)的「状态 = f(seed, moves) 纯函数 + 文件驱动」做法：

    python play_claude.py new [--seed N] [--human north|jin_1|jin_2|jin_3]
    python play_claude.py step          # 从 seed+moves 回放，跑到下一个决策点，dump 到 claude_state.json
    python play_claude.py move '<json>' # 记录一步决策（追加到 moves.jsonl）
    python play_claude.py show          # 紧凑打印 claude_state.json
    python play_claude.py status        # 看已记录步数 + 当前决策点

隐藏信息纪律：`step` 只 dump「当前座位」的 SnapshotViewport —— 给某家决策时，
prompt 里根本没有别家的手牌 / 秘密目标。驱动层结构性保证。

决策记录格式（moves.jsonl 每行一个 JSON）：
    setup     {"player":"jin_1","type":"setup","hero":0,"public_goal":1,"secret_goal":0,"face_down":2,"payment":[]}
    action    {"player":"jin_1","type":"action","index":3}             # index 为 available_actions 下标；-1=结束行动
    choice    {"player":"jin_1","type":"choice","index":2}             # make_choice 选项下标
    target    {"player":"jin_1","type":"target","index":1}             # select_target 选项下标；-1=取消
    discard   {"player":"jin_1","type":"discard","indices":[0,3]}      # choose_discards 手牌下标
    card_play {"player":"jin_1","type":"card_play","index":0}          # request_card_play 的 eligible 下标；-1=拒绝
    court_play{"player":"jin_1","type":"court_play","index":-1}        # request_court_play 的 eligible 下标；-1=拒绝
"""

import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Windows Git Bash 默认 GBK，强制 UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from config.version import Version
from ai.interface import GameAgent, SetupContext, SetupDecision
from engine.game import GameEngine
from viewport.snapshot import SnapshotViewport
from viewport.utils import action_to_summary

STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude_run")

FACTION_LABEL = {"north": "北方", "jin_1": "东晋1", "jin_2": "东晋2", "jin_3": "东晋3"}


# ================================================================
# 文件工具
# ================================================================

def _path(name):
    return os.path.join(STATE_DIR, name)


def _load_json(path, default=None):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def _save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _append_jsonl(path, obj):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


# ================================================================
# 决策回放核心
# ================================================================

class NeedsDecision(Exception):
    """引擎在某决策点缺一步已记录的决策 —— 携带 dump 上下文，驱动层捕获后落盘。"""

    def __init__(self, dump):
        self.dump = dump
        super().__init__("needs decision")


class ReplayController:
    """全局决策队列 + 游标，4 个 ReplayAgent 共享。"""

    def __init__(self, decisions):
        self.decisions = decisions
        self.cursor = 0

    def next(self):
        if self.cursor < len(self.decisions):
            d = self.decisions[self.cursor]
            self.cursor += 1
            return d
        return None


def _build_viewport(state, viewer_id):
    try:
        return SnapshotViewport.from_state(state, viewer_id).to_dict()
    except Exception as e:
        return {"error": str(e)}


def _build_action_menu(state, player_id, available_actions):
    player = state.get_player(player_id)
    hand = player.hand if player else []
    court = state.get_court_cards(player_id)
    staff = player.staff_area if player else []
    hero = player.hero if player else None
    public = state.public_action_pool
    menu = []
    for i, a in enumerate(available_actions):
        s = action_to_summary(a, player_id, hand_cards=hand, court_cards=court,
                              public_cards=public, player_staff=staff, player_hero=hero)
        s["index"] = i
        menu.append(s)
    return menu


class ReplayAgent(GameAgent):
    """每个座位一个实例；决策要么从队列回放，要么 dump 后抛 NeedsDecision。"""

    def __init__(self, player_id, controller, human_seat):
        self.player_id = player_id
        self.controller = controller
        self.human_seat = human_seat

    # ---- 内部：缺决策时构造 dump 并抛出 ----

    def _needs(self, dtype, state=None, extra=None):
        dump = {
            "player": self.player_id,
            "type": dtype,
            "human": (self.player_id == self.human_seat),
        }
        if state is not None:
            dump["round"] = getattr(state, "round", 0)
            dump["phase"] = state.phase.value if hasattr(state.phase, "value") else str(state.phase)
            dump["viewport"] = _build_viewport(state, self.player_id)
        if extra:
            dump.update(extra)
        raise NeedsDecision(dump)

    # ---- GameAgent 接口 ----

    def setup_decision(self, ctx: SetupContext) -> SetupDecision:
        d = self.controller.next()
        if d is None:
            self._needs("setup", extra={
                "hero_choices": ctx.hero_choices,
                "goal_choices": ctx.goal_choices,
                "hand_cards": ctx.hand_cards,
                "hand_card_costs": ctx.hand_card_costs,
            })
        return SetupDecision(
            hero_index=d.get("hero", 0),
            public_goal_index=d.get("public_goal", 0),
            secret_goal_index=d.get("secret_goal", -1),
            face_down_card_index=d.get("face_down", 0),
            payment_indices=d.get("payment", []),
        )

    def decide_action(self, state, available_actions):
        d = self.controller.next()
        if d is None:
            menu = _build_action_menu(state, self.player_id, available_actions)
            self._needs("action", state=state, extra={
                "actions": menu,
                "pass_hint": "index = -1 表示结束行动/空过",
            })
        idx = d.get("index", -1)
        if idx is None or idx == -1:
            return None
        action = available_actions[idx]
        if d.get("payment") is not None:
            action.payment_indices = list(d["payment"])
        return action

    def make_choice(self, state, prompt):
        d = self.controller.next()
        if d is None:
            self._needs("choice", state=state, extra={
                "title": prompt.get("title", ""),
                "options": prompt.get("options", []),
            })
        return d.get("index", 0)

    def choose_discards(self, state, hand_cards, count, reason="hand_limit"):
        d = self.controller.next()
        if d is None:
            self._needs("discard", state=state, extra={
                "hand_cards": hand_cards, "count": count, "reason": reason,
            })
        return d.get("indices", [])

    def select_target(self, state, prompt):
        d = self.controller.next()
        if d is None:
            self._needs("target", state=state, extra={
                "title": prompt.get("title", ""),
                "prompt_type": prompt.get("type", ""),
                "options": prompt.get("options", []),
            })
        idx = d.get("index", -1)
        if idx is None or idx == -1:
            return None
        options = prompt.get("options", [])
        if idx < 0 or idx >= len(options):
            return None
        opt = options[idx]
        if isinstance(opt, dict):
            return opt.get("id", str(opt))
        return str(opt)

    def request_card_play(self, state, eligible_indices, filter_spec=None, free=False):
        d = self.controller.next()
        if d is None:
            player = state.get_player(self.player_id)
            names = [player.hand[i].name if player and 0 <= i < len(player.hand) else "?"
                     for i in eligible_indices]
            self._needs("card_play", state=state, extra={
                "eligible": names, "free": free, "filter": filter_spec,
            })
        idx = d.get("index", -1)
        if idx is None or idx == -1:
            return None
        from engine.actions.card_actions import PlayCardAction
        card_index = eligible_indices[idx]
        player = state.get_player(self.player_id)
        if free:
            payment = []
        else:
            cost = player.hand[card_index].cost if player and 0 <= card_index < len(player.hand) else 0
            payment = d.get("payment")
            if payment is None:
                payment = [j for j in range(len(player.hand)) if j != card_index][:cost]
        return PlayCardAction(player_id=self.player_id, card_index=card_index,
                              payment_indices=payment, free=free)

    def request_court_play(self, state, eligible_cards=None, filter_spec=None):
        d = self.controller.next()
        if d is None:
            court = eligible_cards if eligible_cards is not None else state.get_court_cards(self.player_id)
            names = [c.name for c in court]
            self._needs("court_play", state=state, extra={"eligible": names})
        idx = d.get("index", -1)
        if idx is None or idx == -1:
            return None
        from engine.actions.card_actions import CourtAction
        court = eligible_cards if eligible_cards is not None else state.get_court_cards(self.player_id)
        return CourtAction(player_id=self.player_id, card_id=court[idx].definition.card_id)


# ================================================================
# 紧凑打印（给驱动者快速看，完整详情读 claude_state.json）
# ================================================================

def _compact_my_state(dump):
    vp = dump.get("viewport", {})
    priv = vp.get("private", {})
    pub = vp.get("public", {})
    players = pub.get("players", {})
    me = players.get(dump["player"], {})
    lines = []
    lines.append(f"  回合{dump.get('round','?')} [{dump['player']}] VP={me.get('vp','?')} "
                 f"军力={me.get('military','?')} 手牌{me.get('hand_count','?')}张")
    if me.get("faction") == "jin":
        lines.append(f"  威望={me.get('prestige','?')} 功绩={me.get('contribution','?')} "
                     f"顺位={me.get('order','?')}")
    if priv.get("hand"):
        hand_names = [c.get("name", "?") for c in priv["hand"]]
        lines.append(f"  手牌: {' '.join(hand_names)}")
    if me.get("staff_names"):
        lines.append(f"  幕僚: {' '.join(me['staff_names'])}")
    # 地盘
    locs = vp.get("public", {}).get("map", {}).get("locations", {})
    own = [lid for lid, l in locs.items()
           if l.get("controller") in (dump["player"].replace("_", "_p").replace("north", "north"),
                                      ) or l.get("controller") == dump["player"]]
    if own:
        lines.append(f"  占据: {' '.join(own)}")
    return lines


def _print_dump(dump):
    who = "你" if dump.get("human") else "我"
    print(f"\n{'='*60}")
    print(f"  需要决策 [{dump['player']} {FACTION_LABEL.get(dump['player'],'')}] 类型={dump['type']} — 轮到 {who}")
    if dump.get("round"):
        print(f"  第 {dump['round']} 回合")
    print(f"{'='*60}")

    t = dump["type"]
    if t == "setup":
        print(f"\n【可选英雄】")
        for i, h in enumerate(dump.get("hero_choices", [])):
            print(f"  {i}. {h.get('name')} (先动{h.get('start_order')}) — {h.get('effect_text','')[:60]}")
        if dump.get("goal_choices"):
            print(f"\n【可选目标】")
            for i, g in enumerate(dump.get("goal_choices", [])):
                print(f"  {i}. {g.get('name')} 简{g.get('simple_vp')}/完{g.get('full_vp')}vp "
                      f"简:{g.get('simple_condition','')[:30]}")
        print(f"\n【手牌】")
        costs = dump.get("hand_card_costs", [])
        for i, name in enumerate(dump.get("hand_cards", [])):
            c = costs[i] if i < len(costs) else "?"
            print(f"  {i}. {name} (费用{c})")

    elif t == "action":
        for line in _compact_my_state(dump):
            print(line)
        print(f"\n【可选行动】(index 下标)")
        for a in dump.get("actions", []):
            print(f"  {a['index']:>2}. [{a.get('action_type')}] {a.get('description','?')}")
        print(f"\n  -1. 结束行动/空过")

    elif t in ("choice", "target"):
        print(f"  {dump.get('title','')}")
        for i, o in enumerate(dump.get("options", [])):
            label = o.get("label", o) if isinstance(o, dict) else o
            print(f"  {i}. {label}")

    elif t == "discard":
        print(f"  需弃 {dump.get('count')} 张 ({dump.get('reason')})")
        for i, name in enumerate(dump.get("hand_cards", [])):
            print(f"  {i}. {name}")

    elif t in ("card_play", "court_play"):
        print(f"  可选打出:")
        for i, name in enumerate(dump.get("eligible", [])):
            print(f"  {i}. {name}")
        print(f"  -1. 拒绝")

    print(f"\n(完整局面已写 claude_state.json，含地图/朝堂/轨道等细节)")
    print(f"记录决策: python play_claude.py move '<json>'")
    print(f"{'='*60}\n")


# ================================================================
# 命令
# ================================================================

def cmd_new(args):
    os.makedirs(STATE_DIR, exist_ok=True)
    seed = args.seed if args.seed is not None else 42
    human = args.human or "north"
    _save_json(_path("claude_game.json"), {"seed": seed, "human": human})
    with open(_path("moves.jsonl"), "w", encoding="utf-8"):
        pass
    if os.path.exists(_path("claude_state.json")):
        os.remove(_path("claude_state.json"))
    print(f"新局: seed={seed}, 你控 {human} ({FACTION_LABEL.get(human,'')})")
    print("下一步: python play_claude.py step")


def cmd_step(args):
    cfg = _load_json(_path("claude_game.json"))
    if cfg is None:
        print("先运行: python play_claude.py new")
        return
    seed = cfg["seed"]
    human = cfg.get("human", "north")
    moves = _load_jsonl(_path("moves.jsonl"))

    v = Version.load("v1.0")
    controller = ReplayController(moves)
    agents = [ReplayAgent(pid, controller, human)
              for pid in ["north", "jin_1", "jin_2", "jin_3"]]
    engine = GameEngine(agents=agents, version=v, seed=seed)

    try:
        final = engine.run()
    except NeedsDecision as e:
        _save_json(_path("claude_state.json"), e.dump)
        _print_dump(e.dump)
        return

    # 游戏结束（所有决策已记录）
    scores = engine.get_scores()
    winner = engine.get_winner()
    print("\n" + "=" * 60)
    print("  游戏结束!")
    print(f"  回合数: {final.round}  原因: {final.game_end_reason}")
    print("=" * 60)
    for pid, sc in scores.items():
        mark = " ★胜者" if pid == winner else ""
        print(f"  {pid} ({FACTION_LABEL.get(pid,'')}): {sc} VP{mark}")


def cmd_move(args):
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            d = json.load(f)
    else:
        d = json.loads(args.json)
    moves = _load_jsonl(_path("moves.jsonl"))
    d["seq"] = len(moves) + 1
    _append_jsonl(_path("moves.jsonl"), d)
    print(f"已记录第 {len(moves)+1} 步: {d.get('player')} {d.get('type')} "
          f"index={d.get('index', d.get('hero', '?'))}")


def cmd_show(args):
    dump = _load_json(_path("claude_state.json"))
    if dump is None:
        print("没有 claude_state.json，先运行 step")
        return
    if args.full:
        print(json.dumps(dump, ensure_ascii=False, indent=2))
    else:
        _print_dump(dump)


def cmd_status(args):
    cfg = _load_json(_path("claude_game.json"))
    moves = _load_jsonl(_path("moves.jsonl"))
    dump = _load_json(_path("claude_state.json"))
    if cfg is None:
        print("尚未开局 (先 new)")
        return
    print(f"seed={cfg['seed']} 你控={cfg.get('human','north')}")
    print(f"已记录 {len(moves)} 步")
    if dump:
        print(f"当前决策点: [{dump['player']}] {dump['type']} 第{dump.get('round','?')}回合")
    else:
        print("当前无待决策 (可能已结束，或还没 step)")


def main():
    p = argparse.ArgumentParser(description="文件驱动的六朝何事对局驱动器")
    sub = p.add_subparsers(dest="cmd", required=True)

    pn = sub.add_parser("new")
    pn.add_argument("--seed", type=int, default=None)
    pn.add_argument("--human", type=str, default="north")
    pn.set_defaults(func=cmd_new)

    ps = sub.add_parser("step")
    ps.set_defaults(func=cmd_step)

    pm = sub.add_parser("move")
    pm.add_argument("json", nargs="?", default=None)
    pm.add_argument("--file", type=str, default=None)
    pm.set_defaults(func=cmd_move)

    pw = sub.add_parser("show")
    pw.add_argument("--full", action="store_true")
    pw.set_defaults(func=cmd_show)

    pt = sub.add_parser("status")
    pt.set_defaults(func=cmd_status)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
