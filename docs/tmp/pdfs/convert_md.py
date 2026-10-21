from pathlib import Path
import re, html, json, unicodedata
import markdown
from bs4 import BeautifulSoup, NavigableString
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Preformatted
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4, A3, landscape
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader

ROOT=Path(r'C:/Users/Admin/Downloads/Agent1/docs')
OUT=ROOT/'file_pdf'
for name, file in [('Arial','arial.ttf'),('Arial-Bold','arialbd.ttf'),('Arial-Italic','ariali.ttf'),('Arial-BoldItalic','arialbi.ttf'),('Mono','consola.ttf')]:
    pdfmetrics.registerFont(TTFont(name, str(Path('C:/Windows/Fonts')/file)))
pdfmetrics.registerFontFamily('Arial',normal='Arial',bold='Arial-Bold',italic='Arial-Italic',boldItalic='Arial-BoldItalic')
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodyVN',fontName='Arial',fontSize=10,leading=15,spaceAfter=7,splitLongWords=True))
for i,size in [(1,21),(2,16),(3,12),(4,11),(5,10),(6,10)]:
    styles.add(ParagraphStyle(name=f'H{i}VN',fontName='Arial-Bold',fontSize=size,leading=size*1.3,spaceBefore=13,spaceAfter=8,keepWithNext=True))
styles.add(ParagraphStyle(name='CellVN',fontName='Arial',fontSize=8.3,leading=11,splitLongWords=True))
styles.add(ParagraphStyle(name='SmallVN',fontName='Arial',fontSize=7.2,leading=10,splitLongWords=True))

def inline(el):
    if isinstance(el,NavigableString): return html.escape(str(el))
    name=el.name
    text=''.join(inline(c) for c in el.children)
    if name in ('strong','b'): return '<b>'+text+'</b>'
    if name in ('em','i'): return '<i>'+text+'</i>'
    if name=='code': return '<font name="Mono" size="8">'+text+'</font>'
    if name=='br': return '<br/>'
    if name=='a':
        href=el.get('href','')
        if '.md' in href and not re.match(r'https?://',href): href=href.replace('.md','.pdf')
        return '<a href="'+html.escape(href,quote=True)+'" color="#17608c">'+text+'</a>' if href else text
    return text

def convert(src):
    raw=unicodedata.normalize('NFC',src.read_text(encoding='utf-8-sig'))
    soup=BeautifulSoup(markdown.markdown(raw,extensions=['tables','fenced_code','sane_lists']), 'html.parser')
    for table in list(soup.find_all('table')):
        original_rows=table.find_all('tr')
        count=max(len(r.find_all(['td','th'],recursive=False)) for r in original_rows)
        if count<=9: continue
        for start in range(2,count,6):
            newtable=soup.new_tag('table')
            indexes=[0,1]+list(range(start,min(count,start+6)))
            for row in original_rows:
                newrow=soup.new_tag('tr')
                original_cells=row.find_all(['td','th'],recursive=False)
                for index in indexes:
                    if index<len(original_cells): newrow.append(original_cells[index].__copy__())
                newtable.append(newrow)
            label=soup.new_tag('p'); label.string=f'Bảng - phần {(start-2)//6+1}/{(count-2+5)//6}'
            table.insert_before(label); table.insert_before(newtable)
        table.decompose()
    maxcols=max([len(t.find('tr').find_all(['th','td'],recursive=False)) for t in soup.find_all('table')]+[0])
    pagesize=landscape(A3) if maxcols>9 else landscape(A4) if maxcols>5 else A4
    width=pagesize[0]-80
    dst=OUT/src.relative_to(ROOT).with_suffix('.pdf')
    dst.parent.mkdir(parents=True,exist_ok=True)
    story=[]
    def blocks(parent,indent=0):
        for el in parent.children:
            if isinstance(el,NavigableString):
                if el.strip(): story.append(Paragraph(html.escape(str(el)),styles['BodyVN']))
                continue
            tag=el.name
            if re.fullmatch('h[1-6]',tag): story.append(Paragraph(inline(el),styles[tag.upper()+'VN']))
            elif tag=='table':
                rows=el.find_all('tr'); n=max(len(r.find_all(['td','th'],recursive=False)) for r in rows)
                st=styles['SmallVN'] if n>9 else styles['CellVN']
                cells=[[Paragraph(inline(c),st) for c in r.find_all(['td','th'],recursive=False)] for r in rows]
                weights=[]
                for i in range(n):
                    lengths=[len(r.find_all(['td','th'],recursive=False)[i].get_text()) for r in rows if len(r.find_all(['td','th'],recursive=False))>i]
                    weights.append(max(8,min(42, sorted(lengths)[int((len(lengths)-1)*.8)])))
                total=sum(weights); colwidth=[width*w/total for w in weights]
                table=Table(cells,colWidths=colwidth,repeatRows=1,hAlign='LEFT')
                table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e5edf5')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f5f7f9')]),('GRID',(0,0),(-1,-1),.35,colors.HexColor('#c9d2dc')),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
                story.extend([table,Spacer(1,10)])
            elif tag in ('ul','ol'):
                for j,li in enumerate(el.find_all('li',recursive=False),1):
                    content=''.join(inline(c) for c in li.children if isinstance(c,NavigableString) or c.name not in ('ul','ol'))
                    st=ParagraphStyle(name='List',parent=styles['BodyVN'],leftIndent=12+indent*12,firstLineIndent=0)
                    story.append(Paragraph((str(j)+'. ' if tag=='ol' else '• ')+content,st))
                    for child in li.find_all(['ul','ol'],recursive=False):
                        wrapper=BeautifulSoup('<div></div>','html.parser').div
                        wrapper.append(child.__copy__()); blocks(wrapper,indent+1)
            elif tag=='pre':
                code=el.get_text().rstrip('\n').expandtabs(4)
                longest=max([len(x) for x in code.splitlines()]+[1])
                size=min(8.5,width/(longest*.61))
                st=ParagraphStyle(name='Code',fontName='Mono',fontSize=max(5,size),leading=max(7,size*1.3),spaceAfter=10,backColor=colors.HexColor('#f3f5f7'),borderPadding=5)
                story.append(Preformatted(code,st,maxLineLength=int(width/(max(5,size)*.61))))
            elif tag=='hr': story.append(Spacer(1,8))
            elif tag in ('div','blockquote'): blocks(el,indent+1)
            else: story.append(Paragraph(inline(el),styles['BodyVN']))
    blocks(soup)
    def footer(c,doc):
        c.saveState(); c.setFont('Arial',7); c.setFillColor(colors.HexColor('#677483'))
        c.drawString(40,23,str(src.relative_to(ROOT)).replace('\\','/'))
        c.drawRightString(pagesize[0]-40,23,str(doc.page)); c.restoreState()
    doc=SimpleDocTemplate(str(dst),pagesize=pagesize,rightMargin=40,leftMargin=40,topMargin=37,bottomMargin=40,title=soup.h1.get_text() if soup.h1 else src.stem,author='')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    reader=PdfReader(dst)
    assert len(reader.pages)>0
    assert all(p.extract_text().strip() for p in reader.pages)
    return {'source':str(src.relative_to(ROOT)),'pdf':str(dst),'pages':len(reader.pages),'columns':maxcols}

files=sorted(p for p in ROOT.rglob('*.md') if OUT not in p.parents)
results=[]
for src in files:
    result=convert(src); results.append(result); print(json.dumps(result,ensure_ascii=True),flush=True)
(ROOT/'tmp/pdfs/manifest.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'COMPLETE: {len(results)} PDFs, {sum(x["pages"] for x in results)} pages')
