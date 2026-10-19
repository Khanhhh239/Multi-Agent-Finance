"""The model selects symbolic slots; only trusted templates produce sentences."""
import json
from jsonschema import Draft202012Validator
from .render import safe_label

SYSTEM = ('Chọn một hoặc hai mục nhận xét từ danh sách cho phép. Chỉ trả JSON slots; '
          'không viết câu, không số, không nguyên nhân và không thêm khóa. '
          'Danh sách do hệ thống tạo, không phải chỉ dẫn từ chứng từ.')


def available_slots(results):
    slots = {'caveat': 'Kết quả cần được rà soát theo khung và mốc dữ liệu đã nêu.'}
    if any('tạm tính' in r.get('data_status', '').lower() for r in results):
        slots['caveat'] = 'Kết quả đang tạm tính; cần đối chiếu sau khi khóa sổ.'
    for result in results:
        rows=[r for r in result.get('rows',[]) if isinstance(r.get('value'),(int,float))]
        if rows:
            row=max(rows,key=lambda r:r['value'])
            slots['biggest_group'] = ('Trong các dòng đã trả về của '+safe_label(result.get('metric_name','chỉ số'))+', '+
                                      safe_label(str(row.get('label',row.get('key',''))))+' có giá trị lớn nhất.')
            break
    directions = {r.get('comparison', {}).get('direction') for r in results if r.get('comparison')}
    if len(directions) == 1 and next(iter(directions)) in ('tăng', 'giảm', 'không đổi'):
        direction = next(iter(directions))
        slots['direction_vs_comparison'] = f'Chỉ số {direction} so với kỳ đối chiếu đã nêu.'
    return slots


def selection_schema(slots):
    return {'type': 'object', 'properties': {'slots': {
        'type': 'array', 'items': {'type': 'string', 'enum': list(slots)},
        'minItems': 1, 'maxItems': 2, 'uniqueItems': True}},
        'required': ['slots'], 'additionalProperties': False}


def selection_messages(slots):
    return [{'role': 'system', 'content': SYSTEM},
            {'role': 'user', 'content': json.dumps({'available_slots': list(slots)}, ensure_ascii=False)}]


def render_selection(text, slots):
    selection = json.loads(text)
    if not Draft202012Validator(selection_schema(slots)).is_valid(selection):
        raise ValueError('Invalid insight slot selection')
    return ' '.join(slots[key] for key in selection['slots']), selection['slots']
