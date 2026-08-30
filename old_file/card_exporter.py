import csv
import json
import os
from pathlib import Path

def load_variables(variables_path):
    """加载变量配置文件"""
    with open(variables_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return {v['code']: v['replacement'] for v in data['variables']}

def longest_match_replace(text, variables):
    """使用最长匹配原则进行变量替换"""
    # 按替换文本长度降序排序，确保最长匹配优先
    sorted_vars = sorted(variables.items(), key=lambda x: len(x[1]), reverse=True)
    
    for code, replacement in sorted_vars:
        if replacement in text:
            text = text.replace(replacement, '{' + code + '}')
    return text

def parse_card_design(csv_path):
    """解析card_design.csv，处理归属继承"""
    cards = []
    current_owner = None
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        headers = next(reader)  # 读取表头
        
        for row in reader:
            if len(row) == 0:
                continue
                
            owner = row[0].strip()
            
            # 处理归属继承
            if owner:
                current_owner = owner
            else:
                owner = current_owner
            
            # 处理空字符串
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
                '公共': get_int(row[30]) if len(row) > 30 else 0
            }
            cards.append(card)
    
    return cards

def categorize_cards(cards):
    """将卡牌分类到不同输出文件"""
    categories = {
        'card_hero': [],           # 角色牌
        'card_event_hero': [],     # 角色专属事件牌
        'card_friend_hero': [],    # 角色专属幕僚牌
        'card_strategy_hero': [],  # 角色专属策略牌
        'card_event': [],          # 通用事件牌
        'card_friend': [],         # 通用幕僚牌
        'card_strategy': [],       # 通用策略牌
        'card_mechanism': [],      # 强制性事件牌
        'card_public': [],         # 公共行动牌
        'card_north': []           # 北方专属牌
    }
    
    for card in cards:
        # 跳过统计行和标题行
        if card['卡牌名称'] == '' or card['卡牌名称'] == '卡牌名称':
            continue
            
        # 强制性事件牌优先
        if '事件-机制' in card['卡牌分类']:
            categories['card_mechanism'].append(card)
            continue
            
        # 公共行动牌
        if card['公共'] == 1:
            categories['card_public'].append(card)
            continue
            
        # 北方专属牌
        if card['归属'] == '北方':
            categories['card_north'].append(card)
            continue
            
        # 通用牌（归属为'初始'或'牌库'）
        if card['归属'] in ['初始', '牌库']:
            if card['类型'] == '事件牌':
                categories['card_event'].append(card)
            elif card['类型'] == '幕僚牌':
                categories['card_friend'].append(card)
            elif card['类型'] == '策略牌':
                categories['card_strategy'].append(card)
            continue
            
        # 角色专属牌
        if card['归属'] not in ['初始', '牌库', '北方', None, '']:
            if card['类型'] == '角色牌':
                categories['card_hero'].append(card)
            elif card['类型'] == '事件牌':
                categories['card_event_hero'].append(card)
            elif card['类型'] == '幕僚牌':
                categories['card_friend_hero'].append(card)
            elif card['类型'] == '策略牌':
                categories['card_strategy_hero'].append(card)
            continue
    
    return categories

def format_card(card, variables):
    """格式化卡牌效果，替换变量"""
    effect = card['效果']
    effect = longest_match_replace(effect, variables)
    return effect

def write_csv(file_path, rows, headers):
    """写入CSV文件"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

def export_cards(categories, variables, output_dir):
    """导出所有卡牌文件"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # card_hero.csv
    rows = []
    for card in categories['card_hero']:
        effect = format_card(card, variables)
        # 判断是北方还是东晋角色
        hero_type = 'north' if '北方' in card['卡牌分类'] else 'jin'
        rows.append([
            1,  # [Item Amount]
            card['卡牌名称'],
            f"<align=\"center\">{{card_hero}}-{{{hero_type}}}</align>",
            effect,
            True,  # text_bottom:text_wrapping
            f"ai/p00_{card['卡牌名称']}.png",
            "#FFFFFFFF"  # logo:color
        ])
    write_csv(output_path / 'card_hero.csv', rows, 
              ['[Item Amount]', 'text_top', 'text_card_type', 'text_bottom', 
               'text_bottom:text_wrapping', 'logo', 'logo:color', '[Item Note]'])
    
    # card_event_hero.csv
    rows = []
    for card in categories['card_event_hero']:
        effect = format_card(card, variables)
        rows.append([
            1,  # [Item Amount]
            card['史书vp'] if card['史书vp'] else 0,
            card['卡牌名称'],
            card['归属'],
            'center',
            f"<align=\"center\">{{card_event}}-{{military}}</align>",
            effect
        ])
    write_csv(output_path / 'card_event_hero.csv', rows,
              ['[Item Amount]', 'vp数字', 'text_top', 'text_owner', 
               'text_owner:text_alignment_h', 'text_card_type', 'text_bottom', '[Item Note]'])
    
    # card_friend_hero.csv
    rows = []
    for card in categories['card_friend_hero']:
        effect = format_card(card, variables)
        rows.append([
            1,  # [Item Amount]
            card['费用'],
            card['卡牌名称'],
            card['归属'],
            effect,
            card['史书vp'] if card['史书vp'] else 0
        ])
    write_csv(output_path / 'card_friend_hero.csv', rows,
              ['[Item Amount]', '费用数字', 'text_top', 'text_owner', 
               'text_bottom', '史书vp', '[Item Note]'])
    
    # card_strategy_hero.csv
    rows = []
    for card in categories['card_strategy_hero']:
        effect = format_card(card, variables)
        rows.append([
            1,  # [Item Amount]
            card['费用'],
            card['卡牌名称'],
            card['归属'],
            effect,
            card['资源']
        ])
    write_csv(output_path / 'card_strategy_hero.csv', rows,
              ['[Item Amount]', '费用数字', 'text_top', 'text_owner', 
               'text_bottom', '资源', '[Item Note]'])
    
    # card_event.csv
    rows = []
    for card in categories['card_event']:
        effect = format_card(card, variables)
        rows.append([
            1,  # [Item Amount]
            card['史书vp'] if card['史书vp'] else 0,
            card['卡牌名称'],
            '通用',
            effect
        ])
    write_csv(output_path / 'card_event.csv', rows,
              ['[Item Amount]', 'vp数字', 'text_top', 'text_owner', 'text_bottom', '[Item Note]'])
    
    # card_friend.csv
    rows = []
    for card in categories['card_friend']:
        effect = format_card(card, variables)
        rows.append([
            1,  # [Item Amount]
            card['费用'],
            card['卡牌名称'],
            '通用',
            effect,
            card['史书vp'] if card['史书vp'] else 0
        ])
    write_csv(output_path / 'card_friend.csv', rows,
              ['[Item Amount]', '费用数字', 'text_top', 'text_owner', 
               'text_bottom', '史书vp', '[Item Note]'])
    
    # card_strategy.csv
    rows = []
    for card in categories['card_strategy']:
        effect = format_card(card, variables)
        rows.append([
            1,  # [Item Amount]
            card['费用'],
            card['卡牌名称'],
            '通用',
            effect,
            card['资源']
        ])
    write_csv(output_path / 'card_strategy.csv', rows,
              ['[Item Amount]', '费用数字', 'text_top', 'text_owner', 
               'text_bottom', '资源', '[Item Note]'])
    
    # card_mechanism.csv
    rows = []
    for card in categories['card_mechanism']:
        effect = format_card(card, variables)
        rows.append([
            1,  # [Item Amount]
            card['卡牌名称'],
            effect
        ])
    write_csv(output_path / 'card_mechanism.csv', rows,
              ['[Item Amount]', 'text_top', 'text_bottom', '[Item Note]'])
    
    # card_public.csv
    rows = []
    for card in categories['card_public']:
        effect = format_card(card, variables)
        rows.append([
            1,  # [Item Amount]
            card['费用'],
            card['卡牌名称'],
            effect,
            2.5,  # text_bottom:text_size_min
            2.5   # text_bottom:text_size_max
        ])
    write_csv(output_path / 'card_public.csv', rows,
              ['[Item Amount]', '费用数字', 'text_top', 'text_bottom', 
               'text_bottom:text_size_min', 'text_bottom:text_size_max', '[Item Note]'])
    
    # card_north.csv
    rows = []
    for card in categories['card_north']:
        effect = format_card(card, variables)
        rows.append([
            1,  # [Item Amount]
            card['费用'],
            card['卡牌名称'],
            '北方',
            effect,
            card['史书vp'] if card['史书vp'] else 0
        ])
    write_csv(output_path / 'card_north.csv', rows,
              ['[Item Amount]', '费用数字', 'text_top', 'text_owner', 
               'text_bottom', '史书vp', '[Item Note]'])

def copy_external_files(source_dir, output_dir):
    """复制外部文件（card_goal.csv, card_emperor.csv）"""
    source_path = Path(source_dir)
    output_path = Path(output_dir)
    
    for filename in ['card_goal.csv', 'card_emperor.csv']:
        src = source_path / filename
        if src.exists():
            with open(src, 'r', encoding='utf-8') as f:
                content = f.read()
            with open(output_path / filename, 'w', encoding='utf-8') as f:
                f.write(content)

def main():
    # 路径配置
    base_dir = Path(r'd:\life\board_game\project_six_dynasty')
    card_design_path = base_dir / 'card_design.csv'
    variables_path = base_dir / 'project_siz_dynasty_table_creator' / 'data' / 'variables.json'
    output_dir = base_dir / 'export_sample'
    
    # 加载变量
    variables = load_variables(variables_path)
    
    # 解析卡牌
    cards = parse_card_design(card_design_path)
    
    # 分类卡牌
    categories = categorize_cards(cards)
    
    # 导出卡牌
    export_cards(categories, variables, output_dir)
    
    # 复制外部文件
    copy_external_files(base_dir, output_dir)
    
    print(f"导出完成！文件已保存到 {output_dir}")

if __name__ == '__main__':
    main()