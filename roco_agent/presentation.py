"""模型专用的数据视图；完整查询记录留在数据层。"""


def compact(value):
    if isinstance(value, dict):
        return {k: compact(v) for k, v in value.items()
                if k not in ('icon', 'small_icon', 'image_sources', 'image_url')}
    if isinstance(value, list):
        return [compact(v) for v in value]
    return value


def strip_metadata(value):
    if isinstance(value, dict):
        return {k: strip_metadata(v) for k, v in value.items()
                if k not in ('sources', 'source_url', 'updated_at', 'stale', 'warning',
                             'file', 'provenance', 'fetched_at', 'imported_at')}
    if isinstance(value, list):
        return [strip_metadata(v) for v in value]
    return value


def label(value):
    return value.get('name', value) if isinstance(value, dict) else value


def number(value):
    if isinstance(value, str):
        try:
            if value.strip().isdecimal():
                return int(value)
        except ValueError:
            pass
    return value


def skill_view(skill):
    fields = {'名称': skill.get('name'),
              '属性': label(skill.get('element_type') or skill.get('type') or skill.get('families')),
              '类型': label(skill.get('skill_type') or skill.get('damage_type')),
              '威力': number(skill.get('power')), '能耗': number(skill.get('cost')),
              '效果': skill.get('description', skill.get('desc'))}
    if not fields['名称']:
        fields['技能ID'] = skill.get('skill_id')
    damage_type = label(skill.get('damage_type'))
    if damage_type is not None and damage_type != fields['类型']:
        fields['伤害类型'] = damage_type
    known = {'name', 'element_type', 'type', 'families', 'skill_type', 'damage_type',
             'power', 'cost', 'description', 'desc', 'skill_id'}
    extra = {k: v for k, v in skill.items() if k not in known}
    if extra:
        fields['补充信息'] = extra
    return {k: v for k, v in fields.items() if v is not None}


def game_view(value):
    if isinstance(value, list):
        return [game_view(v) for v in value]
    if not isinstance(value, dict):
        return value
    if 'name' in value and set(value) <= {'id', 'type_id', 'name'}:
        return value['name']
    ignored = {'available_sections', 'display_order'}
    routes = value.get('sections')
    if isinstance(routes, dict) and routes and all(isinstance(v, str) and v.startswith('/api/') for v in routes.values()):
        ignored.add('sections')
    if 'name' in value:
        ignored.update(('id', 'type_id', 'item_id', 'skill_id'))
    for field in ('types', 'egg_groups'):
        if field in value:
            ignored.update((field[:-1] + '_ids', field[:-1] + '_names'))
    return {k: game_view(v) for k, v in value.items() if k not in ignored}


def family_view(family):
    if 'branches' in family:
        return game_view(family)
    members, features = [], {}
    names = {m.get('pet_id'): m.get('name') for m in family.get('members', [])}
    for member in family.get('members', []):
        row = {k: member[k] for k in ('pet_id', 'name', 'previous_pet_id', 'stage') if k in member}
        level = member.get('condition_level', member.get('level'))
        conditions = {'level': level, 'items': game_view(member.get('items')), 'cost': member.get('money')}
        texts = member.get('condition_texts') or [member.get('condition_summary') or member.get('evolution_description')]
        texts = [t for t in texts if t and t.replace(' ', '') != f'等级达到{level}']
        if texts:
            conditions['other'] = list(dict.fromkeys(texts))
        description = member.get('evolution_description')
        parent = names.get(member.get('previous_pet_id'))
        repeated = [f'{parent}升级到{level}级后进化为{member.get("name")}。',
                    f'{parent}首领化后成为{member.get("name")}。']
        if description and description not in [*texts, member.get('condition_summary'), *repeated]:
            conditions['description'] = description
        row['conditions'] = {k: v for k, v in conditions.items() if v is not None}
        feature = member.get('feature')
        if feature and feature.get('name'):
            name, effect = feature['name'], feature.get('desc')
            # 相同特性共用一份效果；效果出现差异时逐形态保留。
            if name not in features or features[name] == effect:
                features[name] = effect
                row['feature'] = name
            else:
                row['feature'] = {'name': name, 'effect': effect}
        known = {'pet_id', 'name', 'previous_pet_id', 'stage', 'condition_level', 'level', 'items',
                 'money', 'condition_texts', 'condition_summary', 'evolution_description', 'feature', 'display_order'}
        extra = {k: game_view(v) for k, v in member.items() if k not in known}
        if extra:
            row['extra'] = extra
        members.append(row)
    result = {'members': members}
    if features:
        result['features'] = features
    result.update({k: game_view(v) for k, v in family.items() if k not in ('family_id', 'name', 'members')})
    return result


def learning_condition(item):
    source = item.get('source')
    row = {'学习方式': {'level': '升级', 'machine': '技能石', 'blood': '血脉',
                         'legendary': '传说技能'}.get(source, source)}
    if item.get('requires'):
        row['学习条件'] = item['requires']
    if source in ('level', 'blood'):
        row['学习等级'] = item.get('level')
    if source == 'blood':
        if item.get('bloodline_name'):
            row['血脉'] = item['bloodline_name']
        elif item.get('bloodline_id') is not None:
            row['血脉ID'] = item['bloodline_id']
    return row


def skill_pets_view(data):
    pets = []
    for pet in data['items']:
        conditions = []
        for relation in pet['learning']:
            condition = learning_condition(relation)
            conditions.append(condition)
        pets.append({'名称': pet['name'], '学习条件': conditions})
    view = {'技能': data['name'], '精灵': pets, '总数': data['total'], 'has_more': data['has_more']}
    if data.get('has_more'):
        view['next_offset'] = data['next_offset']
    return view


def learning_view(data):
    items = []
    for item in data.get('items', []):
        detail = dict(item.get('detail') or {})
        detail.setdefault('name', item.get('name'))
        detail.setdefault('skill_id', item['skill_id'])
        row = skill_view(detail)
        row.update(learning_condition(item))
        detail_status = item.get('detail_status', 'ok' if item.get('detail') is not None else 'detail_missing')
        if detail_status != 'ok':
            row['详情状态'] = detail_status
        items.append(row)
    result = {'技能': items}
    if data.get('name'):
        result['精灵'] = data['name']
    if 'can_learn_in_selected_scope' in data:
        result['当前筛选条件下可学习'] = data['can_learn_in_selected_scope']
    return result


def model_result(name, answer):
    if name == 'search_pets' and answer['status'] == 'ok':
        data = answer['data']
        candidates = [{'pet_id': item['pet_id'], 'name': item['name']} for item in data['items']]
        if data.get('has_more'):
            return {'candidates': candidates, 'has_more': True}
        if not candidates:
            return '未找到'
        return candidates[0]['pet_id'] if len(candidates) == 1 else candidates
    answer = strip_metadata(compact(answer))
    data = answer.get('data')
    if not isinstance(data, dict):
        return answer
    if name == 'get_skill' and answer['status'] == 'ok':
        answer['data'] = skill_view(data)
    elif name == 'get_pet_skills' and answer['status'] in ('ok', 'partial'):
        answer['data'] = learning_view(data)
    elif name == 'get_skill_pets' and answer['status'] == 'ok':
        answer['data'] = skill_pets_view(data)
    elif name == 'get_pet' and answer['status'] == 'ok':
        if data.get('section') == 'family' and isinstance(data.get('value'), dict):
            answer['data'] = {k: v for k, v in data.items() if k != 'value'}
            answer['data']['value'] = family_view(data['value'])
        else:
            answer['data'] = game_view(data)
    return answer
