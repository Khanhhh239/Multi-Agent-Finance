"""Đọc XML có namespace; nhận diện phiên bản và chuỗi thay thế/điều chỉnh."""
from pathlib import Path
from xml.etree import ElementTree as ET
from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException
import pandas as pd
from .invoices import validate_invoices


def read_invoice_xml(content, firm_id, *, validate=True):
    content=content if isinstance(content,bytes) else Path(content).read_bytes()
    if len(content)>10_000_000 or b'<!DOCTYPE' in content.upper() or b'<!ENTITY' in content.upper():
        raise ValueError('XML có khai báo thực thể hoặc vượt giới hạn')
    try:
        root=SafeET.fromstring(content, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (DefusedXmlException, ET.ParseError) as error:
        raise ValueError('XML không hợp lệ hoặc chứa DTD/thực thể bị cấm') from error
    for element in root.iter():
        element.tag=element.tag.split('}')[-1]
    version=root.findtext('.//TTChung/PBan')
    if version not in {'2.0.0','2.0.1','2.1.0'}:
        raise ValueError(f'Chưa hỗ trợ PBan={version}')
    def get(path):
        return root.findtext(path)
    due=None
    for field in root.findall('.//TTin'):
        if field.findtext('TTruong')=='HanThanhToan':
            due=field.findtext('DLieu')
    row=dict(invoice_key=root.find('DLHDon').get('Id') if root.find('DLHDon') is not None else None,
             symbol=get('DLHDon/TTChung/KHHDon'),invoice_no=get('DLHDon/TTChung/SHDon'),
             issue_date=get('DLHDon/TTChung/NLap'),currency=get('DLHDon/TTChung/DVTTe'),
             seller_mst=get('DLHDon/NDHDon/NBan/MST'),buyer_mst=get('DLHDon/NDHDon/NMua/MST'),
             buyer_name=get('DLHDon/NDHDon/NMua/Ten'),
             amount_net=get('DLHDon/NDHDon/TToan/TgTCThue'),
             vat=get('DLHDon/NDHDon/TToan/TgTThue'),
             amount_gross=get('DLHDon/NDHDon/TToan/TgTTTBSo'),due_date=due)
    row['firm_id']=firm_id
    row['invoice_id']=row.pop('invoice_key') or f"{row['seller_mst']}-{row['symbol']}-{row['invoice_no']}"
    row['customer_id']=str(row['buyer_mst'])
    row['document_version']=version
    related=root.find('.//TTChung/TTHDLQuan')
    nature=related.findtext('TCHDon') if related is not None else None
    if nature not in (None,'1','2'):
        raise ValueError(f'Chưa hỗ trợ tính chất hóa đơn TCHDon={nature}')
    row['adjustment_type']={'1':'replacement','2':'adjustment'}.get(nature)
    if nature:
        row['adjusts_symbol']=related.findtext('KHHDCLQuan')
        row['adjusts_invoice_no']=related.findtext('SHDCLQuan')
        row['adjusts_issue_date']=related.findtext('NLHDCLQuan')
        if not row['adjusts_symbol'] or not row['adjusts_invoice_no'] or not row['adjusts_issue_date']:
            raise ValueError('Hóa đơn liên quan thiếu ký hiệu, số hoặc ngày lập')
    row['issue_date']=pd.Timestamp(row['issue_date'])
    row['due_date']=pd.Timestamp(row['due_date']) if row['due_date'] else pd.NaT
    row['term_days']=(row['due_date']-row['issue_date']).days if pd.notna(row['due_date']) else 0
    if validate:
        row['available_on']=pd.Timestamp.now(tz='Asia/Ho_Chi_Minh').date().isoformat()
        validate_invoices([row],source='xml',today=pd.Timestamp.now(tz='Asia/Ho_Chi_Minh').tz_localize(None).normalize())
    return row
