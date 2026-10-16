"""Data boundary used from the first facts pack, before model exposure."""
import html,re,unicodedata

def clean_text(text):
    return ''.join(c for c in unicodedata.normalize('NFC',str(text)) if unicodedata.category(c) not in ('Cf','Cc') or c=='\n')

def suspicious(text):
    from .guardrails import detect_injection
    return detect_injection(text)

def wrap_untrusted(text,source='tool',limit=160):
    value=clean_text(text)
    value='[nội dung nghi vấn đã ẩn]' if suspicious(value) else value[:limit]
    return '<du_lieu_khong_tin_cay nguon="'+html.escape(source,quote=True)+'">'+html.escape(value)+'</du_lieu_khong_tin_cay>'
