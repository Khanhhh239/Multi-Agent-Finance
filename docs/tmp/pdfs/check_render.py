from pathlib import Path
import subprocess, concurrent.futures
from PIL import Image, ImageDraw
root=Path(r'C:/Users/Admin/Downloads/Agent1/docs')
tmp=root/'tmp/pdfs'
poppler=r'C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe'
pdfs=sorted((root/'file_pdf').rglob('*.pdf'))
def render(pair):
    i,p=pair
    target=tmp/f'preview_{i:02}'
    subprocess.run([poppler,'-f','1','-singlefile','-scale-to','700','-png',str(p),str(target)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    return target.with_suffix('.png')
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool: images=list(pool.map(render,enumerate(pdfs)))
for group in range(0,len(images),12):
    sheet=Image.new('RGB',(1400,1120),'#cccccc'); draw=ImageDraw.Draw(sheet)
    for j,path in enumerate(images[group:group+12]):
        im=Image.open(path); im.thumbnail((340,335)); x=(j%4)*350; y=(j//4)*370
        sheet.paste(im,(x,y+25)); draw.text((x+5,y+5),f'{group+j:02} '+pdfs[group+j].stem[:36],fill='black')
    sheet.save(tmp/f'contact_{group//12}.png')
print('Rendered',len(images),'PDF previews')
