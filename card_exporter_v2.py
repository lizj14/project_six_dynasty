import csv
import json
import os
from pathlib import Path

def load_variables(variables_path):
    """加载变量配置文件"""
    with open(variables_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return {v['code']: v['replacement'] for v in data['variables']}

def longest_match_replace(text, variables, card_type=''):
    """使用最长匹配原则进行变量替换"""
    sorted_vars = sorted(variables.items(), key=lambda x: len(x[1]), reverse=True)
    for code, replacement in sorted_vars:
        if replacement in text:
            text = text.replace(replacement, '{' + code + '}')
    
    # 处理"仅限xx玩家打出"开头的情况，单独做一行
    # 在第一个{action}、{passive}、{decision}或{enter}前添加换行
    if text.startswith('{only}'):
        for marker in ['{action}', '{passive}', '{decision}', '{enter}']:
            if marker in text:
                idx = text.index(marker)
                # 在marker前添加换行
                text = text[:idx] + '{newline}' + text[idx:]
                break
    
    # 在所有牌的主动、被动、资源效果之间添加换行
    # 在"{action}"、"{passive}"、"{enter}"、"{decision}"前添加换行（如果前面不是{newline}）
    text = text.replace('{action}', '{newline}{action}')
    text = text.replace('{passive}', '{newline}{passive}')
    text = text.replace('{enter}', '{newline}{enter}')
    text = text.replace('{decision}', '{newline}{decision}')
    
    # 移除连续的换行
    text = text.replace('{newline}{newline}', '{newline}')
    
    # 移除开头的换行（{newline}是9个字符）
    if text.startswith('{newline}'):
        text = text[9:]
    
    return text

def parse_card_design(csv_path):
    """解析card_design.csv，处理归属继承"""
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
                '艺术标记': get_int(row[10]) if len(row) > 10 else 0,
                '权谋标记': get_int(row[11]) if len(row) > 11 else 0,
                '内政标记': get_int(row[12]) if len(row) > 12 else 0,
                '限定东晋': get_int(row[13]) if len(row) > 13 else 0,
                '限定北方': get_int(row[14]) if len(row) > 14 else 0,
                '僭越': get_int(row[15]) if len(row) > 15 else 0,
                '公共': get_int(row[30]) if len(row) > 30 else 0,
                '儒学': get_int(row[33]) if len(row) > 33 else 0,
                '玄学': get_int(row[34]) if len(row) > 34 else 0,
                '佛学': get_int(row[35]) if len(row) > 35 else 0
            }
            cards.append(card)
    
    return cards

def parse_goal_cards(csv_path):
    """解析card_goal.csv"""
    goals = []
    
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            goals.append({
                'name': row['目标牌'],
                'score': row['分数'],
                'simple': row['简单目标'],
                'complete': row['完整目标']
            })
    
    return goals

def parse_emperor_cards(csv_path):
    """解析card_emperor.csv"""
    emperors = []
    
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 跳过空行、扩张骰子行和数量不是数字的行
            if not row['君主牌'] or row['君主牌'] == '扩张骰子':
                continue
            
            # 检查数量是否为有效数字
            amount = row['数量']
            if not amount or not amount.isdigit():
                continue
            
            emperors.append({
                'name': row['君主牌'],
                'amount': amount,
                'prestige': row['初始威望'],
                'effect': row['特效'] if row['特效'] else '',
                'options': [row[str(i)] for i in range(1, 7) if str(i) in row and row[str(i)] and row[str(i)] != '-']
            })
    
    return emperors

def write_refugee_csv(file_path):
    """写入流民牌CSV（16张补充流民牌）"""
    rows = []
    # 总共20张流民牌，北方和东晋初始牌库各2张，还需要16张
    for _ in range(16):
        rows.append([
            1,
            '2',          # vp数字（史书区vp）
            '0',          # 费用数字
            '流民',       # text_top
            '',           # text_top:color
            '流民',       # text_owner
            '',           # text_card_type
            '{passive}{refugee}被{save}时，自动放置回供应堆。{save}{refugee}的玩家获得2{vp}。',
            '',           # 牌面背景:color
            ''            # [Item Note]
        ])
    
    headers = [
        '[Item Amount]', 'vp数字', '费用数字', 'text_top', 'text_top:color', 
        'text_owner', 'text_card_type', 'text_bottom', '牌面背景:color', '[Item Note]'
    ]
    
    with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

def get_card_type_tag(card):
    """获取卡牌类型标签"""
    card_type = card['类型']
    card_category = card['卡牌分类']
    
    # 公共事件牌：卡牌分类包含"公共"
    if '公共' in card['卡牌分类']:
        return '{card_public}'
    
    # 角色牌特殊处理：添加北方/东晋标识
    if card_type == '角色牌':
        if '北方' in card_category:
            return '{card_hero}-{north}'
        else:
            return '{card_hero}-{jin}'
    
    # 确定类型前缀
    type_prefix = {
        '事件牌': '{card_event}',
        '幕僚牌': '{card_friend}',
        '策略牌': '{card_strategy}',
        '机制牌': '{card_mechanism}',
        '角色牌': '{card_hero}'
    }.get(card_type, '{card_event}')
    
    # 确定标记后缀
    tag_suffix = ''
    if card['文化标记']:
        tag_suffix = '-{culture}'
    elif card['军事标记']:
        tag_suffix = '-{military}'
    elif card['艺术标记']:
        tag_suffix = '-{art}'
    elif card['权谋标记']:
        tag_suffix = '-{power}'
    elif card['内政标记']:
        tag_suffix = '-{affair}'
    elif '事件-机制' in card_category:
        return '{card_mechanism}'
    
    return f"{type_prefix}{tag_suffix}"

def get_background_color(card):
    """获取背景颜色"""
    card_type = card['类型']
    card_category = card['卡牌分类']
    
    # 强制性事件牌优先（红色）
    if '事件-机制' in card_category:
        return '#882420FF'  # 红色
    elif card_type == '事件牌':
        return '#F5EDDAFF'  # 米色（普通事件牌）
    elif card_type == '幕僚牌':
        return '#3E5F91FF'  # 蓝色
    else:
        return ''  # 默认

def get_title_color(card):
    """获取标题字颜色"""
    card_type = card['类型']
    card_category = card['卡牌分类']
    
    # 强制性事件牌（事件-机制）没有标题字颜色
    if '事件-机制' in card_category:
        return ''  # 空
    elif card_type == '事件牌':
        return '#292929FF'  # 深灰色（普通事件牌标题）
    else:
        return ''  # 默认

def categorize_cards_new(cards):
    """按照新思路分类卡牌"""
    categories = {
        'common': [],           # 通用牌（不含初始牌和公共牌）
        'public': [],           # 公共事件牌
        'north_initial': [],    # 北方初始牌（用于生成）
        'jin_initial': [],      # 东晋初始牌（用于生成）
        'north_friend': [],     # 北方候选幕僚牌
        'hero_north': [],       # 北方角色牌
        'hero_jin': [],         # 东晋角色牌
    }
    
    # 角色专属牌组（每个角色3张）
    hero_groups = {}
    
    current_hero = None
    hero_cards = []
    
    for card in cards:
        if card['卡牌名称'] == '' or card['卡牌名称'] == '卡牌名称':
            continue
            
        # 如果归属变更（非空且不等于当前角色），重置角色组
        if card['归属'] and card['归属'] != current_hero and current_hero:
            # 保存上一个角色组
            if hero_cards:
                hero_groups[current_hero] = hero_cards
            current_hero = None
            hero_cards = []
            
        # 公共事件牌：卡牌分类包含"公共"
        if '公共' in card['卡牌分类']:
            categories['public'].append(card)
            continue
            
        # 角色牌：开始新的角色组
        if card['类型'] == '角色牌':
            # 保存上一个角色组
            if current_hero and hero_cards:
                hero_groups[current_hero] = hero_cards
            
            current_hero = card['归属']
            hero_cards = []
            
            # 角色牌单独分类
            if '北方' in card['卡牌分类']:
                categories['hero_north'].append(card)
            else:
                categories['hero_jin'].append(card)
            continue
            
        # 角色专属牌（跟随角色的3张牌）
        if current_hero and card['归属'] == current_hero:
            hero_cards.append(card)
            # 每个角色最多3张专属牌
            if len(hero_cards) >= 3:
                hero_groups[current_hero] = hero_cards
                current_hero = None
                hero_cards = []
            continue
            
        # 初始牌（归属为'初始'）- 不放入common
        if card['归属'] == '初始':
            # 判断是北方还是东晋初始牌
            if card['限定北方']:
                categories['north_initial'].append(card)
            elif card['限定东晋']:
                categories['jin_initial'].append(card)
            else:
                # 通用初始牌，加入两个阵营的初始牌列表
                categories['north_initial'].append(card)
                categories['jin_initial'].append(card)
        elif card['归属'] == '牌库':
            # 牌库牌放入通用牌
            categories['common'].append(card)
        elif card['归属'] == '北方':
            # 北方候选幕僚牌
            categories['north_friend'].append(card)
        else:
            categories['common'].append(card)
    
    # 添加剩余的角色组
    if current_hero and hero_cards:
        hero_groups[current_hero] = hero_cards
    
    return categories, hero_groups

def generate_initial_deck(cards, counts):
    """根据规则书数量生成起始牌库"""
    result = []
    
    for card_name, count in counts.items():
        # 找到对应的卡牌
        found_card = None
        for card in cards:
            if card['卡牌名称'] == card_name:
                found_card = card
                break
        
        if found_card:
            # 添加指定数量的卡牌
            for _ in range(count):
                result.append(found_card.copy())
    
    return result

def write_common_csv(file_path, cards, variables):
    """按照新模板写入CSV"""
    rows = []
    
    # 根据输出文件名称确定初始牌归属
    file_name = os.path.basename(file_path)
    is_north_initial = 'north_initial' in file_name
    is_jin_initial = 'jin_initial' in file_name
    
    for card in cards:
        effect = card['效果']
        effect = longest_match_replace(effect, variables, card['类型'])
        
        # 资源信息处理（资源栏为'-'表示为空，不添加）
        resource = card['资源']
        if resource and resource != '-':
            resource = longest_match_replace(resource, variables)
            effect += f"{{newline}}{{resource}}{resource}。"
        
        # 设置text_owner
        owner = '{common}'
        if is_north_initial:
            owner = '{north}'
        elif is_jin_initial:
            owner = '{jin}'
        
        rows.append([
            1,  # [Item Amount]
            card['史书vp'] if card['史书vp'] else '',
            card['费用'] if card['费用'] and card['费用'] != '-' else '',
            card['卡牌名称'],
            get_title_color(card),  # text_top:color
            owner,
            f"<align=\"center\">{get_card_type_tag(card)}</align>",
            effect,
            get_background_color(card),
            ''  # [Item Note]
        ])
    
    headers = [
        '[Item Amount]', 'vp数字', '费用数字', 'text_top', 'text_top:color', 
        'text_owner', 'text_card_type', 'text_bottom', '牌面背景:color', '[Item Note]'
    ]
    
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

def write_goal_csv(file_path, goals):
    """写入目标牌CSV（参考output格式）"""
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
            1,
            goal['name'],
            text_bottom,
            ''
        ])
    
    headers = [
        '[Item Amount]', 'text_top', 'text_bottom', '[Item Note]'
    ]
    
    with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

def write_emperor_csv(file_path, emperors):
    """写入君主牌CSV（参考output格式）"""
    # 中文到变量名的映射
    option_mapping = {
        '扩张': 'emp_expansion',
        '文化': 'emp_culture',
        '艺术': 'emp_art',
        '改革': 'emp_reform',
        '加固': 'emp_defense'
    }
    
    rows = []
    for emperor in emperors:
        # 生成text_bottom，参考格式：
        # 初始威望：6
        # 1：{emp_expansion}
        # 2-3：{emp_culture}
        # 4-6：{emp_art}
        effect_lines = [f"初始威望：{emperor['prestige']}"]
        
        # 处理选项，按照1-6的顺序分组（相邻相同的合并）
        options = emperor['options']
        if options:
            i = 0
            while i < len(options):
                current = options[i]
                start = i + 1  # 骰子从1开始
                # 找到连续相同的选项
                while i + 1 < len(options) and options[i + 1] == current:
                    i += 1
                end = i + 1
                var_name = option_mapping.get(current, f"emp_{current}")
                if start == end:
                    effect_lines.append(f"{start}：{{{var_name}}}")
                else:
                    effect_lines.append(f"{start}-{end}：{{{var_name}}}")
                i += 1
        
        # 添加特效
        if emperor['effect']:
            effect_lines.insert(1, emperor['effect'])
        
        text_bottom = '{newline}'.join(effect_lines)
        
        for _ in range(int(emperor['amount'])):
            rows.append([
                1,
                emperor['name'],
                text_bottom,
                ''
            ])
    
    headers = [
        '[Item Amount]', 'text_top', 'text_bottom', '[Item Note]'
    ]
    
    with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

def write_hero_group_csv(file_path, cards, hero_name, variables):
    """写入角色专属牌组CSV（支持统一文件格式）"""
    rows = []
    for item in cards:
        # 支持两种格式：(hero_name, card) 元组 或 直接是 card
        if isinstance(item, tuple):
            current_hero_name, card = item
        else:
            current_hero_name = hero_name
            card = item
            
        effect = card['效果']
        effect = longest_match_replace(effect, variables, card['类型'])
        
        # 资源信息处理（资源栏为'-'表示为空，不添加）
        resource = card['资源']
        if resource and resource != '-':
            resource = longest_match_replace(resource, variables)
            effect += f"{{newline}}{{resource}}{resource}。"
        
        rows.append([
            1,
            card['史书vp'] if card['史书vp'] else '',
            card['费用'] if card['费用'] and card['费用'] != '-' else '',
            card['卡牌名称'],
            get_title_color(card),  # text_top:color
            current_hero_name,
            f"<align=\"center\">{get_card_type_tag(card)}</align>",
            effect,
            get_background_color(card),
            ''
        ])
    
    headers = [
        '[Item Amount]', 'vp数字', '费用数字', 'text_top', 'text_top:color', 
        'text_owner', 'text_card_type', 'text_bottom', '牌面背景:color', '[Item Note]'
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
    categories, hero_groups = categorize_cards_new(cards)
    
    # 清空并创建输出目录
    import shutil
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 通用牌（不含初始牌和公共牌）
    write_common_csv(output_dir / 'card_common.csv', categories['common'], variables)
    
    # 公共事件牌
    write_common_csv(output_dir / 'card_public.csv', categories['public'], variables)
    
    # 北方候选幕僚牌
    write_common_csv(output_dir / 'card_north_friend.csv', categories['north_friend'], variables)
    
    # 规则书指定的起始牌数量
    north_counts = {
        '士卒': 5,
        '流民': 2,
        '宫廷': 1,
        '征辟人才': 1,
        '骑兵': 1
    }
    
    jin_counts = {
        '士卒': 4,
        '流民': 2,
        '宫廷': 1,
        '加官进爵': 1,
        '北伐': 1,
        '征辟人才': 1
    }
    
    # 生成北方初始牌组
    north_initial_deck = generate_initial_deck(categories['north_initial'], north_counts)
    write_common_csv(output_dir / 'card_north_initial.csv', north_initial_deck, variables)
    
    # 生成东晋初始牌组
    jin_initial_deck = generate_initial_deck(categories['jin_initial'], jin_counts)
    write_common_csv(output_dir / 'card_jin_initial.csv', jin_initial_deck, variables)
    
    # 北方角色牌
    write_common_csv(output_dir / 'card_hero_north.csv', categories['hero_north'], variables)
    
    # 东晋角色牌
    write_common_csv(output_dir / 'card_hero_jin.csv', categories['hero_jin'], variables)
    
    # 将所有角色的专属牌组统一保存到 card_hero_deck.csv
    all_hero_cards = []
    for hero_name, hero_cards in hero_groups.items():
        for card in hero_cards:
            all_hero_cards.append((hero_name, card))
    
    # 写入统一的文件
    write_hero_group_csv(output_dir / 'card_hero_deck.csv', all_hero_cards, None, variables)
    
    # 目标牌
    write_goal_csv(output_dir / 'card_goal.csv', goals)
    
    # 君主牌
    write_emperor_csv(output_dir / 'card_emperor.csv', emperors)
    
    # 流民牌（16张补充牌）
    write_refugee_csv(output_dir / 'card_refugee.csv')
    
    print(f"导出完成！文件已保存到 {output_dir}")

if __name__ == '__main__':
    main()