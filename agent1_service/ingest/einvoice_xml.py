"""Đọc XML có namespace; nhận diện phiên bản và chuỗi thay thế/điều chỉnh."""
from pathlib import Path
from xml.etree import ElementTree as ET
from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException
import io
import pandas as pd
from agent1.synth.einvoice import parse_xml
from agent1.data.schema import quality_gate


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
    row=parse_xml(io.BytesIO(ET.tostring(root)))
    row['firm_id']=firm_id
    row['invoice_id']=row.pop('invoice_key') or f"{row['seller_mst']}-{row['symbol']}-{row['invoice_no']}"
    row['customer_id']=str(row['buyer_mst'])
    row['document_version']=version
    row['adjustment_type']=root.findtext('.//TTHDLQuan/TCHDon')
    row['adjusts_invoice_id']=root.findtext('.//TTHDLQuan/SHDCLQuan')
    row['issue_date']=pd.Timestamp(row['issue_date'])
    row['due_date']=pd.Timestamp(row['due_date']) if row['due_date'] else pd.NaT
    row['term_days']=(row['due_date']-row['issue_date']).days if pd.notna(row['due_date']) else 0
    if validate:
        errors=quality_gate(pd.DataFrame([row]),today=pd.Timestamp.now(tz='Asia/Ho_Chi_Minh').tz_localize(None).normalize())
        if errors.any_error.iloc[0]:
            raise ValueError('Hoá đơn không đạt cổng chất lượng: '+','.join(errors.columns[errors.iloc[0]]))
    return row
