import csv
import json
import os
import re
from pathlib import Path


def load_variables(variables_path):
    with open(variables_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return {v['code']: v['replacement'] for v in data['variables']}


def longest_match_replace(text, variables):
    sorted_vars = sorted(variables.items(), key=lambda x: len(x[1]), reverse=True)
    for code, replacement in sorted_vars:
        if replacement in text:
            text = text.replace(replacement, '{' + code + '}')
    return text


def format_effect_markers(text):
    """Format action/passive/decision/enter markers with newlines."""
    # Handle {only} prefix first
    if text.startswith('{only}'):
        for marker in ['{action}', '{passive}', '{decision}', '{enter}']:
            if marker in text:
                idx = text.index(marker)
                text = text[:idx] + '{newline}' + text[idx:]
                break

    for marker in ['{action}', '{passive}', '{enter}', '{decision}']:
        text = text.replace(marker, '{newline}' + marker)
    text = text.replace('{newline}{newline}', '{newline}')
    if text.startswith('{newline}'):
        text = text[9:]
    return text


def parse_resource(resource_str):
    """Parse resource string into vp and military components.
    Returns (vp_value, mil_value) as strings."""
    vp = ''
    mil = ''
    if resource_str and resource_str != '-':
        vp_match = re.search(r'(-?\d+)vp', resource_str)
        mil_match = re.search(r'(-?\d+)军力', resource_str)
        if vp_match:
            vp = vp_match.group(1)
        if mil_match:
            mil = mil_match.group(1)
    return vp, mil


def extract_restriction(effect, card=None):
    """Extract usage restriction from card flags and effect text.
    Priority: CSV flags (限定东晋/限定北方) > text parsing.
    Returns (restriction, clean_effect) tuple."""
    restriction = ''

    # Priority 1: CSV structured flags
    if card:
        if card['限定东晋']:
            restriction = '{only}{jin}'
        elif card['限定北方']:
            restriction = '{only}{north}'

    # Strip matching text prefix if restriction came from CSV flags
    if restriction:
        m = re.match(r'仅限(东晋|北方)玩家打出[。.]?', effect)
        if m:
            effect = effect[m.end():].lstrip()

    # Pattern 2: 被动：需要控制[XX]，才能打出、执行或征发。
    m = re.search(r'被动：需要控制\[([^\]]+)\]，才能打出[、，执行或征发]*[。.]?', effect)
    if m:
        loc = m.group(1)
        if not restriction:
            restriction = '控制[' + loc + ']'
            effect = effect[:m.start()] + effect[m.end():]
            effect = effect.strip().rstrip('。').rstrip('.')

    # Pattern 3: 控制[XX]时，可以打出。 at start
    m = re.match(r'控制\[([^\]]+)\]时，可以打出[。.]?', effect)
    if m:
        if not restriction:
            restriction = '控制[' + m.group(1) + ']'
            effect = effect[m.end():].lstrip()

    # Pattern 4: 占据[XX]时，可以打出。 at start
    m = re.match(r'占据\[([^\]]+)\]时，可以打出[。.]?', effect)
    if m:
        if not restriction:
            restriction = '占据[' + m.group(1) + ']'
            effect = effect[m.end():].lstrip()

    # Clean up the effect
    effect = effect.strip()
    if effect.startswith('。'):
        effect = effect[1:].strip()

    return restriction, effect


def parse_card_design(csv_path):
    cards = []
    current_owner = None

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        headers = next(reader)

        for row in reader:
            if len(row) == 0:
                continue

            owner = row[0].strip()
            if owner:
                current_owner = owner
            else:
                owner = current_owner

            def get_int(val):
                try:
                    return int(val) if val else 0
                except:
                    return 0

            card = {
                '归属': owner,
                '卡牌名称': row[1] if len(row) > 1 else '',
                '费用': row[2] if len(row) > 2 else '',
                '类型': row[3] if len(row) > 3 else '',
                '卡牌分类': row[4] if len(row) > 4 else '',
                '效果': row[5] if len(row) > 5 else '',
                '资源': row[6] if len(row) > 6 else '',
                '史书vp': row[7] if len(row) > 7 else '',
                '文化标记': get_int(row[8]) if len(row) > 8 else 0,
                '军事标记': get_int(row[9]) if len(row) > 9 else 0,
                '权谋标记': get_int(row[10]) if len(row) > 10 else 0,
                '内政标记': get_int(row[11]) if len(row) > 11 else 0,
                '限定东晋': get_int(row[12]) if len(row) > 12 else 0,
                '限定北方': get_int(row[13]) if len(row) > 13 else 0,
                '僭越': get_int(row[14]) if len(row) > 14 else 0,
                '公共': get_int(row[30]) if len(row) > 30 else 0,
                '儒学': get_int(row[33]) if len(row) > 33 else 0,
                '玄学': get_int(row[34]) if len(row) > 34 else 0,
                '佛学': get_int(row[35]) if len(row) > 35 else 0,
            }
            cards.append(card)

    return cards


def parse_goal_cards(csv_path):
    goals = []
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            goals.append({
                'name': row['目标牌'],
                'score': row['分数'],
                'simple': row['简单目标'],
                'complete': row['完整目标'],
            })
    return goals


def parse_emperor_cards(csv_path):
    emperors = []
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row['君主牌'] or row['君主牌'] == '扩张骰子':
                continue
            amount = row['数量']
            if not amount or not amount.isdigit():
                continue
            emperors.append({
                'name': row['君主牌'],
                'amount': amount,
                'prestige': row['初始威望'],
                'effect': row['特效'] if row['特效'] else '',
                'options': [row[str(i)] for i in range(1, 7)
                           if str(i) in row and row[str(i)] and row[str(i)] != '-'],
            })
    return emperors


def get_card_type_tag(card):
    card_type = card['类型']
    card_category = card['卡牌分类']

    if '公共' in card_category:
        return '{card_public}'

    if card_type == '角色牌':
        base = '{card_hero}'
        if '北方' in card_category:
            base += '-{north}'
        else:
            base += '-{jin}'
        if card['文化标记']:
            base += '-{culture}'
        elif card['军事标记']:
            base += '-{military}'
        elif card['权谋标记']:
            base += '-{power}'
        elif card['内政标记']:
            base += '-{affair}'
        return base

    type_prefix = {
        '事件牌': '{card_event}',
        '幕僚牌': '{card_friend}',
        '策略牌': '{card_strategy}',
        '机制牌': '{card_mechanism}',
        '角色牌': '{card_hero}',
    }.get(card_type, '{card_event}')

    tag_suffix = ''
    if card['文化标记']:
        tag_suffix = '-{culture}'
    elif card['军事标记']:
        tag_suffix = '-{military}'
    elif card['权谋标记']:
        tag_suffix = '-{power}'
    elif card['内政标记']:
        tag_suffix = '-{affair}'
    elif '事件-机制' in card_category:
        return '{card_mechanism}'

    return f"{type_prefix}{tag_suffix}"


def get_background_color(card):
    card_category = card['卡牌分类']
    if '事件-机制' in card_category:
        return '#882420FF'
    elif card['类型'] == '事件牌':
        return '#F5EDDAFF'
    elif card['类型'] == '幕僚牌':
        return '#3E5F91FF'
    elif card['类型'] == '策略牌':
        return '#1a1a1aFF'
    else:
        return ''


def get_title_color(card):
    card_category = card['卡牌分类']
    if '事件-机制' in card_category:
        return ''
    elif card['类型'] == '事件牌':
        return '#292929FF'
    elif card['类型'] == '策略牌':
        return ''
    else:
        return ''


def categorize_cards(cards):
    categories = {
        'common': [],
        'public': [],
        'north_initial': [],
        'jin_initial': [],
        'north_friend': [],
        'hero_north': [],
        'hero_jin': [],
    }
    hero_groups = {}
    current_hero = None
    hero_cards = []

    for card in cards:
        if card['卡牌名称'] == '' or card['卡牌名称'] == '卡牌名称':
            continue

        if card['归属'] and card['归属'] != current_hero and current_hero:
            if hero_cards:
                hero_groups[current_hero] = hero_cards
            current_hero = None
            hero_cards = []

        if '公共' in card['卡牌分类']:
            categories['public'].append(card)
            continue

        if card['类型'] == '角色牌':
            if current_hero and hero_cards:
                hero_groups[current_hero] = hero_cards
            current_hero = card['归属']
            hero_cards = []
            if '北方' in card['卡牌分类']:
                categories['hero_north'].append(card)
            else:
                categories['hero_jin'].append(card)
            continue

        if current_hero and card['归属'] == current_hero:
            hero_cards.append(card)
            if len(hero_cards) >= 3:
                hero_groups[current_hero] = hero_cards
                current_hero = None
                hero_cards = []
            continue

        if card['归属'] == '初始':
            if card['限定北方']:
                categories['north_initial'].append(card)
            elif card['限定东晋']:
                categories['jin_initial'].append(card)
            else:
                categories['north_initial'].append(card)
                categories['jin_initial'].append(card)
        elif card['归属'] == '北方':
            categories['north_friend'].append(card)
        else:
            categories['common'].append(card)

    if current_hero and hero_cards:
        hero_groups[current_hero] = hero_cards

    return categories, hero_groups


def generate_initial_deck(cards, counts):
    result = []
    for card_name, count in counts.items():
        found_card = None
        for card in cards:
            if card['卡牌名称'] == card_name:
                found_card = card
                break
        if found_card:
            for _ in range(count):
                result.append(found_card.copy())
    return result


def vis(value):
    """Return visibility flag: empty (visible) if value is truthy, 'False' otherwise."""
    # Empty string or None values should show False
    if value is None or value == '' or value is False:
        return 'False'
    if isinstance(value, str) and value.strip() == '':
        return 'False'
    if value == 0:
        return 'False'
    return ''


def write_card_csv(file_path, cards, variables, file_type='common'):
    """Write cards in the new 23-column template format."""
    rows = []

    for card in cards:
        # Parse resource
        resource_str = card['资源'] if card['资源'] and card['资源'] != '-' else ''
        vp_prod, mil_prod = parse_resource(resource_str)

        # Parse effect for restriction (BEFORE variable substitution)
        raw_effect = card['效果']
        restriction, clean_effect = extract_restriction(raw_effect, card)
        # Apply variable substitution after extraction
        restriction = longest_match_replace(restriction, variables)
        clean_effect = longest_match_replace(clean_effect, variables)
        clean_effect = format_effect_markers(clean_effect)

        # Resource display (for text_bottom) — skip for strategy cards (shown via symbols)
        if resource_str and card['类型'] != '策略牌':
            resource_str_replaced = longest_match_replace(resource_str, variables)
            clean_effect += f"{{newline}}{{resource}}{resource_str_replaced}。"

        # Cost
        cost = card['费用'] if card['费用'] and card['费用'] != '-' else ''

        # 史书vp
        shishu_vp = card['史书vp'] if card['史书vp'] else ''

        # Owner text
        owner = card['归属']
        # Determine faction from file name for initial decks
        file_path_str = str(file_path)
        if 'north_initial' in file_path_str:
            owner_text = '{north}'
        elif 'jin_initial' in file_path_str:
            owner_text = '{jin}'
        elif owner == '北方':
            owner_text = '{north}'
        elif owner == '公共':
            owner_text = '{common}'
        elif owner in ('牌库', '通用', '初始'):
            owner_text = '{common}'
        else:
            owner_text = owner

        # Determine visibility
        is_forced = '事件-机制' in card['卡牌分类']
        is_public = '公共' in card['卡牌分类']

        if is_forced:
            # Forced events: hide all symbols, costs, and numbers
            vp_prod_vis = 'False'
            mil_vis = 'False'
            vp_sym_vis = 'False'
            mil_sym_vis = 'False'
            vp_num_vis = 'False'
            cost_vis = 'False'
            score_sym_vis = 'False'
            cost_token_vis = 'False'
        else:
            vp_prod_vis = vis(vp_prod)
            mil_vis = vis(mil_prod)
            vp_sym_vis = '' if vp_prod else 'False'
            mil_sym_vis = '' if mil_prod else 'False'
            vp_num_vis = vis(shishu_vp)
            cost_vis = vis(cost)
            score_sym_vis = '' if shishu_vp else 'False'
            cost_token_vis = '' if cost else 'False'

        # Public cards: hide存档vp
        if is_public:
            vp_num_vis = 'False'
            score_sym_vis = 'False'

        limit_vis = vis(restriction)
        bg_vis = '' if get_background_color(card) else 'False'

        is_refugee = card['卡牌名称'] == '流民'

        row = [
            1,
            vp_prod if not is_refugee else '',
            vp_prod_vis if not is_refugee else 'False',
            mil_prod if not is_refugee else '',
            mil_vis if not is_refugee else 'False',
            vp_sym_vis if not is_refugee else 'False',
            mil_sym_vis if not is_refugee else 'False',
            shishu_vp if not is_refugee else '',
            vp_num_vis if not is_refugee else 'False',
            cost if not is_refugee else '0',
            cost_vis if not is_refugee else '',
            card['卡牌名称'],
            get_title_color(card) if not is_refugee else '',
            restriction if not is_refugee else '',
            limit_vis if not is_refugee else 'False',
            owner_text if not is_refugee else '',
            f'<align="center">{get_card_type_tag(card)}</align>' if not is_refugee else '',
            clean_effect,
            score_sym_vis if not is_refugee else 'False',
            cost_token_vis if not is_refugee else '',
            bg_vis if not is_refugee else '',
            get_background_color(card) if not is_refugee else '',
            '',
        ]
        rows.append(row)

    headers = [
        '[Item Amount]', 'vp产能数字', 'vp产能数字:visible',
        '军力数字', '军力数字:visible', 'vp符号:visible', '军力符号:visible',
        'vp数字', 'vp数字:visible', '费用数字', '费用数字:visible',
        'text_top', 'text_top:color', 'text_limit', 'text_limit:visible',
        'text_owner', 'text_card_type', 'text_bottom',
        '分数符号:visible', '费用token:visible', '牌面背景:visible',
        '牌面背景:color', '[Item Note]',
    ]

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def write_goal_csv(file_path, goals):
    """Write goal cards using the new format."""
    rows = []
    for goal in goals:
        scores = goal['score'].split('/')
        simple_score = scores[0]
        complete_score = scores[1] if len(scores) > 1 else scores[0]

        simple = goal['simple']
        complete = goal['complete']

        if simple.startswith('东晋控制[') and complete.startswith('玩家控制['):
            simple_district = simple.replace('东晋控制[', '').replace(']区域', '')
            complete_district = complete.replace('玩家控制[', '').replace(']区域', '')
            text_bottom = f"{{jin}}{{control}}[{simple_district}]{{district}}：{simple_score}vp{{newline}}{{player}}{{control}}[{complete_district}]{{district}}：{complete_score}vp"
        else:
            text_bottom = f"{simple}：{simple_score}vp{{newline}}{complete}：{complete_score}vp"

        rows.append([
            1, goal['name'], text_bottom, '',
        ])

    headers = ['[Item Amount]', 'text_top', 'text_bottom', '[Item Note]']
    with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def write_emperor_csv(file_path, emperors):
    """Write emperor cards using the new format."""
    option_mapping = {
        '扩张': 'emp_expansion',
        '文化': 'emp_culture',
        '艺术': 'emp_art',
        '改革': 'emp_reform',
        '加固': 'emp_defense',
    }
    rows = []
    for emperor in emperors:
        effect_lines = [f"初始威望：{emperor['prestige']}"]
        options = emperor['options']
        if options:
            i = 0
            while i < len(options):
                current = options[i]
                start = i + 1
                while i + 1 < len(options) and options[i + 1] == current:
                    i += 1
                end = i + 1
                var_name = option_mapping.get(current, f"emp_{current}")
                if start == end:
                    effect_lines.append(f"{start}：{{{var_name}}}")
                else:
                    effect_lines.append(f"{start}-{end}：{{{var_name}}}")
                i += 1
        if emperor['effect']:
            effect_lines.insert(1, emperor['effect'])
        text_bottom = '{newline}'.join(effect_lines)
        for _ in range(int(emperor['amount'])):
            rows.append([1, emperor['name'], text_bottom, ''])

    headers = ['[Item Amount]', 'text_top', 'text_bottom', '[Item Note]']
    with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def write_refugee_csv(file_path):
    """Write refugee cards in the new format."""
    rows = []
    for _ in range(16):
        rows.append([
            1, '', 'False', '', 'False', 'False', 'False',
            '', 'False', '0', '',
            '流民', '', '', 'False',
            '流民', '',
            '{passive}{refugee}被{save}时，自动放置回供应堆。{save}{refugee}的{player}获得2{vp}。',
            'False', '', '', '', '',
        ])
    headers = [
        '[Item Amount]', 'vp产能数字', 'vp产能数字:visible',
        '军力数字', '军力数字:visible', 'vp符号:visible', '军力符号:visible',
        'vp数字', 'vp数字:visible', '费用数字', '费用数字:visible',
        'text_top', 'text_top:color', 'text_limit', 'text_limit:visible',
        'text_owner', 'text_card_type', 'text_bottom',
        '分数符号:visible', '费用token:visible', '牌面背景:visible',
        '牌面背景:color', '[Item Note]',
    ]
    with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def write_hero_group_csv(file_path, cards, variables):
    """Write hero deck cards in the new format."""
    rows = []
    for item in cards:
        if isinstance(item, tuple):
            hero_name, card = item
        else:
            hero_name = ''
            card = item

        resource_str = card['资源'] if card['资源'] and card['资源'] != '-' else ''
        vp_prod, mil_prod = parse_resource(resource_str)

        # Parse effect for restriction (BEFORE variable substitution)
        raw_effect = card['效果']
        restriction, clean_effect = extract_restriction(raw_effect, card)
        # Apply variable substitution after extraction
        restriction = longest_match_replace(restriction, variables)
        clean_effect = longest_match_replace(clean_effect, variables)
        clean_effect = format_effect_markers(clean_effect)

        if resource_str and card['类型'] != '策略牌':
            resource_str_replaced = longest_match_replace(resource_str, variables)
            clean_effect += f"{{newline}}{{resource}}{resource_str_replaced}。"

        cost = card['费用'] if card['费用'] and card['费用'] != '-' else ''
        shishu_vp = card['史书vp'] if card['史书vp'] else ''
        owner_text = hero_name if hero_name else card['归属']

        is_forced = '事件-机制' in card['卡牌分类']

        if is_forced:
            row = [
                1, vp_prod, 'False',
                mil_prod, 'False',
                'False', 'False',
                shishu_vp, 'False',
                cost, 'False',
                card['卡牌名称'],
                get_title_color(card),
                restriction, vis(restriction),
                owner_text,
                f'<align="center">{get_card_type_tag(card)}</align>',
                clean_effect,
                'False', 'False',
                '' if get_background_color(card) else 'False',
                get_background_color(card),
                '',
            ]
        else:
            row = [
                1, vp_prod, vis(vp_prod),
                mil_prod, vis(mil_prod),
                '' if vp_prod else 'False',
                '' if mil_prod else 'False',
                shishu_vp, vis(shishu_vp),
                cost, vis(cost),
                card['卡牌名称'],
                get_title_color(card),
                restriction, vis(restriction),
                owner_text,
                f'<align="center">{get_card_type_tag(card)}</align>',
                clean_effect,
                '' if shishu_vp else 'False',
                '' if cost else 'False',
                '' if get_background_color(card) else 'False',
                get_background_color(card),
                '',
            ]
        rows.append(row)

    headers = [
        '[Item Amount]', 'vp产能数字', 'vp产能数字:visible',
        '军力数字', '军力数字:visible', 'vp符号:visible', '军力符号:visible',
        'vp数字', 'vp数字:visible', '费用数字', '费用数字:visible',
        'text_top', 'text_top:color', 'text_limit', 'text_limit:visible',
        'text_owner', 'text_card_type', 'text_bottom',
        '分数符号:visible', '费用token:visible', '牌面背景:visible',
        '牌面背景:color', '[Item Note]',
    ]

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def main():
    base_dir = Path(r'd:\life\board_game\project_six_dynasty')
    card_design_path = base_dir / 'card_design.csv'
    goal_path = base_dir / 'card_goal.csv'
    emperor_path = base_dir / 'card_emperor.csv'
    variables_path = base_dir / 'project_siz_dynasty_table_creator' / 'data' / 'variables.json'
    output_dir = base_dir / 'export_sample_new'

    variables = load_variables(variables_path)
    cards = parse_card_design(card_design_path)
    goals = parse_goal_cards(goal_path)
    emperors = parse_emperor_cards(emperor_path)
    categories, hero_groups = categorize_cards(cards)

    import shutil
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Common cards
    write_card_csv(output_dir / 'card_common.csv', categories['common'], variables)

    # Public cards
    write_card_csv(output_dir / 'card_public.csv', categories['public'], variables)

    # North friend cards
    write_card_csv(output_dir / 'card_north_friend.csv', categories['north_friend'], variables)

    # Initial deck counts
    north_counts = {
        '士卒': 5, '流民': 2, '宫廷': 1, '征辟人才': 1, '轻骑兵': 1,
    }
    jin_counts = {
        '士卒': 3, '流民': 2, '宫廷': 1, '加官进爵': 1,
        '北伐': 1, '征辟人才': 1, '清谈': 1,
    }

    north_initial = generate_initial_deck(categories['north_initial'], north_counts)
    write_card_csv(output_dir / 'card_north_initial.csv', north_initial, variables)

    jin_initial = generate_initial_deck(categories['jin_initial'], jin_counts)
    write_card_csv(output_dir / 'card_jin_initial.csv', jin_initial, variables)

    # Hero cards
    write_card_csv(output_dir / 'card_hero_north.csv', categories['hero_north'], variables)
    write_card_csv(output_dir / 'card_hero_jin.csv', categories['hero_jin'], variables)

    # Hero decks
    all_hero_cards = []
    for hero_name, hero_cards in hero_groups.items():
        for card in hero_cards:
            all_hero_cards.append((hero_name, card))
    write_hero_group_csv(output_dir / 'card_hero_deck.csv', all_hero_cards, variables)

    # Goal, Emperor, Refugee
    write_goal_csv(output_dir / 'card_goal.csv', goals)
    write_emperor_csv(output_dir / 'card_emperor.csv', emperors)
    write_refugee_csv(output_dir / 'card_refugee.csv')

    print(f"v3 导出完成！文件已保存到 {output_dir}")


if __name__ == '__main__':
    main()
