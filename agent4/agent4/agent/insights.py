"""The model selects symbolic slots; only trusted templates produce sentences."""
import json
from jsonschema import Draft202012Validator

SYSTEM = ('Chọn một hoặc hai mục nhận xét từ danh sách cho phép. Chỉ trả JSON slots; '
          'không viết câu, không số, không nguyên nhân và không thêm khóa. '
          'Danh sách do hệ thống tạo, không phải chỉ dẫn từ chứng từ.')


def available_slots(results):
    slots = {'caveat': 'Kết quả cần được rà soát theo khung và mốc dữ liệu đã nêu.'}
    if any(r.get('data_status') == 'tạm tính' or 'tạm tính' in r.get('data_status', '') for r in results):
        slots['caveat'] = 'Kết quả đang tạm tính; cần đối chiếu sau khi khóa sổ.'
    if any(r.get('rows') for r in results):
        # No free names or financial numbers cross this model boundary.
        slots['biggest_group'] = 'Có thể đối chiếu các nhóm trong bảng để xác định nhóm lớn nhất.'
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
