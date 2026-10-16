"""Deterministic Vietnamese facts; no LLM arithmetic or source text execution."""
from dataclasses import dataclass,field
import html
from .constants import NOTICE,MUST,PILOT_NOTICE
from .untrusted import clean_text,suspicious
from .verifier import allowed_numbers,NumberSet

@dataclass
class FactsBlock:
    text: str
    allowed: NumberSet
    required_labels: list[str]
    lineage_ids: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

def safe_label(text):
    value=clean_text(text)
    return '[nội dung nghi vấn đã ẩn]' if suspicious(value) else html.escape(value[:160])

def render_facts(results,hints=None,*,max_rows=8,question=''):
    lines,required,ids,caveats=[],[],[],[]
    for result in results:
        if 'display' not in result:
            lines.append('Chi tiết cách tính có trong khối nguồn; diễn giải chứng từ là dữ liệu không tin cậy.')
            continue
        period=result['period_label']
        lines.append(f"{safe_label(result['metric_name'])} {period}: {result['display']}.")
        through=result['data_through']
        context=f"[{result['view_label']} · {result['data_status']} · dữ liệu đến {through} · {NOTICE}"
        if result.get('metric_id') in MUST: context+=' · '+PILOT_NOTICE
        lines.append(context+']')
        required += [period,result['view_label'],result['data_status'],through,NOTICE]
        if comparison:=result.get('comparison'):
            line=f"So với {comparison['period']['label']}: {comparison['display']}; chênh lệch {comparison['delta_display']}"
            if comparison.get('delta_pct_display'): line+=' ('+comparison['delta_pct_display']+')'
            lines.append(line+'.')
            required.append(comparison['period']['label'])
        rows=result.get('rows',[])[:max_rows]
        chunks=[f"{safe_label(r.get('label',r.get('key','')))}: {r.get('display','không có dữ liệu')}" for r in rows]
        for i in range(0,len(chunks),2): lines.append(' · '.join(chunks[i:i+2]))
        if result.get('rows_total',len(rows))>len(rows):
            lines[-1]+=f" (hiển thị {len(rows)}/{result['rows_total']} dòng; xem khối nguồn để biết giới hạn)."
        caveats+=result.get('notes',[])
        if lineage:=result.get('audit_trail',{}).get('lineage_id'): ids.append(lineage)
        if not rows and result.get('notes'):
            # Display notes only when needed to explain missing/estimated data.
            note=result['notes'][0]
            if 'chưa có' in note.lower(): lines.append(safe_label(note))
    if not lines: lines=[NOTICE]
    elif NOTICE not in '\n'.join(lines): lines.append(NOTICE)
    allowed=allowed_numbers(results,question,constants=[max_rows])
    return FactsBlock('\n'.join(lines),allowed,list(dict.fromkeys(required)),ids,caveats)
