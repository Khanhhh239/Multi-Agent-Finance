"""Schema-only provider double; no claim of prose or legal quality."""
import json
from src.explanation_v2.natural import request_data


def payload(context):
    content,_=request_data(context);sections=json.loads(content)['sections']
    texts={'summary':'Đây là bản nháp cho dữ liệu đã lưu; còn nội dung cần đối chiếu.',
           'reasons':'Bạn cần xem các thông tin và giới hạn trong nguồn.',
           'next_actions':'Bạn hãy đối chiếu chứng từ gốc và bổ sung phần còn thiếu.'}
    def paragraph(key):return {'text':texts[key],'fact_ids':sections[key]}
    return json.dumps({'summary':paragraph('summary'),'reasons':[paragraph('reasons')],'next_actions':[paragraph('next_actions')]},ensure_ascii=False)
