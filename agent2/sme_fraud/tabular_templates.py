"""Downloadable synthetic contract samples; no user source or local file paths."""
import csv
import io
import json
from .imports import DEFINITIONS


def flatten(row,prefix=''):
    out={}
    for name,value in row.items():
        field=prefix+name
        if isinstance(value,dict) and (name=='source' or name.endswith('_ref')):out.update(flatten(value,field+'.'))
        elif isinstance(value,(dict,list)):out[field]=json.dumps(value,ensure_ascii=False,separators=(',',':'))
        elif name.endswith('_vnd'):out[field]=str(value)
        else:out[field]=value
    return out


def sample(source,kind):
    tables={'metadata':[dict(contract_version=source['contract_version'],tenant_id=source['tenant_id'])],
            **{name:[flatten(row) for row in source.get(name,[])] for name in DEFINITIONS}}
    if kind=='csv':
        names=sorted({key for rows in tables.values() for row in rows for key in row})
        output=io.StringIO(newline='');writer=csv.writer(output);writer.writerow(['table',*names])
        for table,rows in tables.items():
            for row in rows:writer.writerow([table,*[row.get(name,'') for name in names]])
        return ('\ufeff'+output.getvalue()).encode('utf-8')
    from openpyxl import Workbook
    book=Workbook();book.remove(book.active)
    for table,rows in tables.items():
        if not rows:continue
        sheet=book.create_sheet(table);names=sorted({key for row in rows for key in row});sheet.append(names)
        for row in rows:sheet.append([row.get(name) for name in names])
        sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width=min(45,max(16,len(str(column[0].value))+2))
            for cell in column:
                if isinstance(cell.value,str):cell.number_format='@'
    output=io.BytesIO();book.save(output);return output.getvalue()
