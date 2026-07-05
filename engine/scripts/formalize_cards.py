"""Formalize goal_cards and emperor_cards with structured AST."""
import json, sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

INPUT = os.path.join(os.path.dirname(__file__), '..', '..', 'versions', 'v1.0', 'cards', 'cards_compiled.json')

with open(INPUT, 'r', encoding='utf-8') as f:
    data = json.load(f)

# ========== Formalized goal cards ==========
goal_cards = [
    {
        'card_id': 'goal_天府之土_1', 'name': '天府之土',
        'simple_vp': 7, 'full_vp': 14,
        'simple_condition_ast': {'condition_type': 'friendly_control_region', 'params': {'region': '巴蜀'}},
        'full_condition_ast': {'condition_type': 'control_region', 'params': {'region': '巴蜀'}}
    },
    {
        'card_id': 'goal_河洛旧都_1', 'name': '河洛旧都',
        'simple_vp': 16, 'full_vp': 22,
        'simple_condition_ast': {'condition_type': 'friendly_control_region', 'params': {'region': '中原'}},
        'full_condition_ast': {'condition_type': 'control_region', 'params': {'region': '中原'}}
    },
    {
        'card_id': 'goal_关中故畿_1', 'name': '关中故畿',
        'simple_vp': 14, 'full_vp': 20,
        'simple_condition_ast': {'condition_type': 'friendly_control_region', 'params': {'region': '关中'}},
        'full_condition_ast': {'condition_type': 'control_region', 'params': {'region': '关中'}}
    },
    {
        'card_id': 'goal_海岱之地_1', 'name': '海岱之地',
        'simple_vp': 7, 'full_vp': 14,
        'simple_condition_ast': {'condition_type': 'friendly_control_region', 'params': {'region': '山东'}},
        'full_condition_ast': {'condition_type': 'control_region', 'params': {'region': '山东'}}
    },
    {
        'card_id': 'goal_赵魏雄藩_1', 'name': '赵魏雄藩',
        'simple_vp': 14, 'full_vp': 20,
        'simple_condition_ast': {'condition_type': 'friendly_control_region', 'params': {'region': '河北'}},
        'full_condition_ast': {'condition_type': 'control_region', 'params': {'region': '河北'}}
    },
    {
        'card_id': 'goal_表里山河_1', 'name': '表里山河',
        'simple_vp': 11, 'full_vp': 16,
        'simple_condition_ast': {'condition_type': 'friendly_control_region', 'params': {'region': '山西'}},
        'full_condition_ast': {'condition_type': 'control_region', 'params': {'region': '山西'}}
    },
    {
        'card_id': 'goal_配享太庙_1', 'name': '配享太庙',
        'simple_vp': 10, 'full_vp': 18,
        'simple_condition_ast': {'condition_type': 'compare', 'params': {'left': 'contribution', 'op': '>=', 'right': 7}},
        'full_condition_ast': {'condition_type': 'compare', 'params': {'left': 'contribution', 'op': '==', 'right': 9}}
    },
    {
        'card_id': 'goal_加九锡_1', 'name': '加九锡',
        'simple_vp': 8, 'full_vp': 30,
        'simple_condition_ast': {'condition_type': 'compare', 'params': {'left': 'prestige', 'op': '>', 'right': 6}},
        'full_condition_ast': {
            'condition_type': 'and',
            'params': {
                'conditions': [
                    {'condition_type': 'prestige_highest', 'params': {}},
                    {'condition_type': 'compare', 'params': {'left': 'prestige_lead', 'op': '>=', 'right': 3}}
                ]
            }
        }
    },
    {
        'card_id': 'goal_加九锡_2', 'name': '加九锡',
        'simple_vp': 8, 'full_vp': 30,
        'simple_condition_ast': {'condition_type': 'compare', 'params': {'left': 'prestige', 'op': '>', 'right': 6}},
        'full_condition_ast': {
            'condition_type': 'and',
            'params': {
                'conditions': [
                    {'condition_type': 'prestige_highest', 'params': {}},
                    {'condition_type': 'compare', 'params': {'left': 'prestige_lead', 'op': '>=', 'right': 3}}
                ]
            }
        }
    },
    {
        'card_id': 'goal_家财万贯_1', 'name': '家财万贯',
        'simple_vp': 6, 'full_vp': 12,
        'simple_condition_ast': {'condition_type': 'compare', 'params': {'left': 'hand_count', 'op': '>=', 'right': 6}},
        'full_condition_ast': {'condition_type': 'compare', 'params': {'left': 'hand_count', 'op': '>=', 'right': 9}}
    },
    {
        'card_id': 'goal_遗臭万年_1', 'name': '遗臭万年',
        'simple_vp': 7, 'full_vp': 14,
        'simple_condition_ast': {'condition_type': 'compare', 'params': {'left': 'power_marker_count', 'op': '>=', 'right': 3}},
        'full_condition_ast': {'condition_type': 'compare', 'params': {'left': 'power_marker_count', 'op': '>=', 'right': 5}}
    },
    {
        'card_id': 'goal_敦悦五经_1', 'name': '敦悦五经',
        'simple_vp': 6, 'full_vp': 16,
        'simple_condition_ast': {'condition_type': 'culture_contribution_gt', 'params': {'culture': 'confucianism', 'threshold': 3}},
        'full_condition_ast': {
            'condition_type': 'and',
            'params': {
                'conditions': [
                    {'condition_type': 'culture_contribution_gt', 'params': {'culture': 'confucianism', 'threshold': 5}},
                    {'condition_type': 'culture_most_empty', 'params': {'culture': 'confucianism'}}
                ]
            }
        }
    },
    {
        'card_id': 'goal_清言世业_1', 'name': '清言世业',
        'simple_vp': 6, 'full_vp': 16,
        'simple_condition_ast': {'condition_type': 'culture_contribution_gt', 'params': {'culture': 'taoism', 'threshold': 3}},
        'full_condition_ast': {
            'condition_type': 'and',
            'params': {
                'conditions': [
                    {'condition_type': 'culture_contribution_gt', 'params': {'culture': 'taoism', 'threshold': 5}},
                    {'condition_type': 'culture_most_empty', 'params': {'culture': 'taoism'}}
                ]
            }
        }
    },
    {
        'card_id': 'goal_崇奉三宝_1', 'name': '崇奉三宝',
        'simple_vp': 6, 'full_vp': 16,
        'simple_condition_ast': {'condition_type': 'culture_contribution_gt', 'params': {'culture': 'buddhism', 'threshold': 3}},
        'full_condition_ast': {
            'condition_type': 'and',
            'params': {
                'conditions': [
                    {'condition_type': 'culture_contribution_gt', 'params': {'culture': 'buddhism', 'threshold': 5}},
                    {'condition_type': 'culture_most_empty', 'params': {'culture': 'buddhism'}}
                ]
            }
        }
    },
    {
        'card_id': 'goal_配享武庙_1', 'name': '配享武庙',
        'simple_vp': 10, 'full_vp': 18,
        'simple_condition_ast': {
            'condition_type': 'and',
            'params': {
                'conditions': [
                    {'condition_type': 'compare', 'params': {'left': 'prestige', 'op': '>', 'right': 6}},
                    {'condition_type': 'not_completed_goal', 'params': {'goal': '加九锡'}}
                ]
            }
        },
        'full_condition_ast': {
            'condition_type': 'and',
            'params': {
                'conditions': [
                    {'condition_type': 'compare', 'params': {'left': 'prestige', 'op': '==', 'right': 9}},
                    {'condition_type': 'not_completed_goal', 'params': {'goal': '加九锡'}}
                ]
            }
        }
    },
    {
        'card_id': 'goal_世说新语_1', 'name': '世说新语',
        'simple_vp': 8, 'full_vp': 16,
        'simple_condition_ast': {'condition_type': 'compare', 'params': {'left': 'history_count', 'op': '>=', 'right': 5}},
        'full_condition_ast': {'condition_type': 'compare', 'params': {'left': 'history_count', 'op': '>=', 'right': 8}}
    },
]

# ========== Formalized emperor cards ==========
emperor_cards = [
    {
        'card_id': 'emperor_纯质_1', 'name': '纯质',
        'initial_prestige': 4,
        'emperor_tasks': [],
        'effect_ast': {'effect_type': 'skip_emperor_die', 'params': {}}
    },
    {
        'card_id': 'emperor_雅好_1', 'name': '雅好',
        'initial_prestige': 6,
        'emperor_tasks': ['march', 'march', 'reform', 'spread_culture', 'art', 'art'],
        'effect_ast': {}
    },
    {
        'card_id': 'emperor_守成_1', 'name': '守成',
        'initial_prestige': 5,
        'emperor_tasks': ['march', 'march', 'fortify', 'fortify', 'reform', 'spread_culture'],
        'effect_ast': {}
    },
    {
        'card_id': 'emperor_躬亲_1', 'name': '躬亲',
        'initial_prestige': 7,
        'emperor_tasks': ['march', 'march', 'march', 'reform', 'reform', 'spread_culture'],
        'effect_ast': {}
    },
    {
        'card_id': 'emperor_中庸_1', 'name': '中庸',
        'initial_prestige': 5,
        'emperor_tasks': ['march', 'march', 'fortify', 'art', 'spread_culture', 'spread_culture'],
        'effect_ast': {}
    },
]

data['goal_cards'] = goal_cards
data['emperor_cards'] = emperor_cards

with open(INPUT, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f'OK: {len(goal_cards)} goal_cards, {len(emperor_cards)} emperor_cards')
