"""Scan all unique effect/condition/cost/trigger/ability/filter types."""
import json

def _collect(step, ets, cts, fts):
    if not isinstance(step, dict):
        return
    ets.add(step.get('effect_type', ''))
    cond = step.get('condition')
    if cond and isinstance(cond, dict):
        cts.add(cond.get('condition_type', ''))
        _collect_cond(cond, cts)
    params = step.get('params', {})
    if not isinstance(params, dict):
        return
    se = params.get('sub_effect')
    if se and isinstance(se, dict):
        ets.add(se.get('effect_type', ''))
        sc = se.get('condition')
        if sc and isinstance(sc, dict):
            cts.add(sc.get('condition_type', ''))
            _collect_cond(sc, cts)
    ses = params.get('sub_effects')
    if ses and isinstance(ses, list):
        for s in ses:
            if isinstance(s, dict):
                ets.add(s.get('effect_type', ''))
                sc = s.get('condition')
                if sc and isinstance(sc, dict):
                    cts.add(sc.get('condition_type', ''))
                    _collect_cond(sc, cts)
    target = params.get('target', {})
    if isinstance(target, dict):
        for f in target.get('filters', []):
            if isinstance(f, dict):
                if 'type' in f:
                    fts.add(f['type'])
                for k in f:
                    if k not in ('type',):
                        fts.add(k)

def _collect_cond(cond, cts):
    if not isinstance(cond, dict):
        return
    params = cond.get('params', {})
    if not isinstance(params, dict):
        return
    sub = params.get('condition')
    if sub and isinstance(sub, dict):
        cts.add(sub.get('condition_type', ''))
        _collect_cond(sub, cts)
    conds = params.get('conditions', [])
    if isinstance(conds, list):
        for c in conds:
            if isinstance(c, dict):
                cts.add(c.get('condition_type', ''))
                _collect_cond(c, cts)

# Load JSON
with open('versions/v1.0/cards/cards_compiled.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

all_cards = data.get('hero_cards', []) + data.get('action_cards', []) + data.get('goal_cards', []) + data.get('emperor_cards', [])

effect_types = set()
condition_types = set()
cost_types = set()
trigger_types = set()
ability_types = set()
filter_types = set()

for c in all_cards:
    pe = c.get('parsed_effect', {})
    if not pe:
        continue
    for b in pe.get('blocks', []):
        ability_types.add(b.get('ability_type', ''))
        if b.get('trigger'):
            trigger_types.add(b['trigger'])
        for cost in b.get('costs', []):
            if isinstance(cost, dict):
                cost_types.add(cost.get('cost_type', ''))
        for s in b.get('steps', []):
            _collect(s, effect_types, condition_types, filter_types)
        for s in b.get('usurp_steps', []):
            _collect(s, effect_types, condition_types, filter_types)
        for opt in b.get('choice_options', []):
            if isinstance(opt, dict):
                for s in opt.get('steps', []):
                    _collect(s, effect_types, condition_types, filter_types)
                for cost in opt.get('costs', []):
                    if isinstance(cost, dict):
                        cost_types.add(cost.get('cost_type', ''))
            elif isinstance(opt, list):
                for s in opt:
                    _collect(s, effect_types, condition_types, filter_types)
    pc = pe.get('play_condition')
    if pc and isinstance(pc, dict):
        condition_types.add(pc.get('condition_type', ''))
        _collect_cond(pc, condition_types)

for g in data.get('goal_cards', []):
    for key in ['simple_condition_ast', 'full_condition_ast']:
        ast = g.get(key)
        if ast and isinstance(ast, dict):
            condition_types.add(ast.get('condition_type', ''))
            _collect_cond(ast, condition_types)

for e in data.get('emperor_cards', []):
    ea = e.get('effect_ast', {})
    if isinstance(ea, dict) and ea.get('effect_type'):
        effect_types.add(ea['effect_type'])

print('=== EFFECT TYPES ===')
for x in sorted(effect_types):
    if x: print(f'  {x}')

print('\n=== CONDITION TYPES ===')
for x in sorted(condition_types):
    if x: print(f'  {x}')

print('\n=== COST TYPES ===')
for x in sorted(cost_types):
    if x: print(f'  {x}')

print('\n=== TRIGGER TYPES ===')
for x in sorted(trigger_types):
    if x: print(f'  {x}')

print('\n=== ABILITY TYPES ===')
for x in sorted(ability_types):
    if x: print(f'  {x}')

print('\n=== FILTER TYPES/KEYS ===')
for x in sorted(filter_types):
    if x: print(f'  {x}')
