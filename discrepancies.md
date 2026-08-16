# 六朝何事 — 规则书 vs 代码 不一致清单

> 对局驱动过程中逐条核对发现。每条标严重度（高/中/低）、位置、影响。持续补充。

---

## 1.【高】规则书 §3.2 区域列表过时，与代码严重不符

- **规则书** [rulebook.md:148](rulebook.md#L148)：「区域包括：关中，巴蜀，荆襄，**河南**，江南，河北，山东，山西。」——只列 8 个，且用「河南」。
- **代码/地图实际**（[map_adjacency.yaml](engine/config/map_adjacency.yaml#L5-L100) + [area_control.py](engine/rules/area_control.py#L24-L50)）：共 **12 区域**：西凉、关中、巴蜀、荆襄、江南、**中原**、山西、山东、淮南、河北、幽燕、塞外。
- **不一致点**：
  1. 规则书漏了 4 个区域（西凉、淮南、幽燕、塞外）。
  2. 「河南」应为「中原」。
- **影响**：读规则书的玩家/LLM 会对地图构成产生错误认知。需更新规则书。

---

## 2.【中】viewport/utils.py 弘农所属区域映射错误

- **代码** [viewport/utils.py:372](engine/viewport/utils.py#L372)：`"弘农": "关中"`。
- **真源** [map_adjacency.yaml](engine/config/map_adjacency.yaml#L46-L47) + [area_control.py](engine/rules/area_control.py#L36)：弘农属于**中原**（`中原: [弘农, 洛阳, 雍丘, 彭城, 谯, 东平]`）。
- **影响**：视窗里弘农地点显示的 `region` 字段错误显示为「关中」；heuristic_ai 的 `_score_convert` 按错误区域查文化标记。核心区控计分不受影响（走 REGION_CONFIG）。

---

## 3.【中】目标牌条件加载失效（数据双源 + 读错字段）

- **编译数据** [cards_compiled.json](versions/v1.0/cards/cards_compiled.json)：目标牌存的是 `simple_condition_ast` / `full_condition_ast`（AST 形式）。
- **加载器** [version.py:154-163](engine/config/version.py#L154-L163)：读的是 `simple_condition` / `full_condition`（**空字段**）→ `goal_simple_condition`、`goal_full_condition`、`effect_text` 全为**空字符串**。
- **后果**：初设时 SetupContext 的目标条件为空 → 玩家选目标牌时看不到「简单目标/完整目标」人话条件（实测 dump 里「简:」后面空白）。
- **但计分不受影响**：[goals.py](engine/rules/goals.py#L19-L55) 用**硬编码的 `GOAL_DEFINITIONS`** 列表做终局判定。即：条件数据存在两处（编译 AST + 硬编码），编译 AST 从未被读取（死数据），初设显示则空白。
- **影响**：选目标时的信息缺失，但不导致计分错误。需统一为单一来源。

---

## 4.【低】enums.py Region 注释过时

- **代码** [enums.py:86](engine/models/enums.py#L86)：`ZHONGYUAN = "中原"  # 弘农, 洛阳, 上洛, 雍丘, 彭城, 谯, 东平`——把「上洛」列进中原。
- **真源**：上洛属于**荆襄**（map_adjacency.yaml 荆襄 `[襄阳,南郡,巴东,武昌,宛城,上洛]`）。
- **影响**：仅注释，不影响运行。顺手更正。

---

## 5.【低】board_info.md 地名与代码不统一（设计文档过时）

board_info.md 是已翻译进 map_adjacency.yaml 的设计稿，代码内部一致，但文档残留旧名：

| board_info.md | 代码实际 | 位置 |
|---|---|---|
| 「关外」 | 「塞外」 | board_info 区域表 vs enums.py GUANWAI |
| 邻接表「邺」 | 「邺城」 | board_info §二 vs map_adjacency.yaml |
| 邻接表「成都」 | 「蜀郡」 | board_info §二（汉中邻接）vs map_adjacency.yaml |

**影响**：仅文档层面，代码不受影响。

---

## 待对局验证的候选点（先记录，实战中确认）

- 司马家军力分配（规则书 §3.4「军力>6 则分配」）与 [rules/sima.py](engine/rules/sima.py) 的阈值/流程是否一致。
- 文化传播「上限5vp」与 [rules/scoring.py](engine/rules/scoring.py) `CULTURE_SUPPLY_VP` 的关系。
- 终局平手判定（规则书 §4.4）与 [game.py `_determine_winner`](engine/engine/game.py#L1189-L1210) 的一致性。
- 强制事件牌「翻出3张重洗」与 [game.py](engine/engine/game.py#L844-L850) 的 `>= 3` 判定。

---

_本文件由对局驱动过程中持续维护。_
