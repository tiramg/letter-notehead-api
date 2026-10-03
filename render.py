"""Render converted MusicXML/MXL to PDF with MuseScore Studio."""
from pathlib import Path
import os, shutil, subprocess
from PIL import Image

def find_musescore():
    configured=os.environ.get('MUSESCORE_BIN')
    candidates=[configured,shutil.which('mscore4portable'),shutil.which('mscore4'),shutil.which('musescore4'),shutil.which('MuseScore4.exe')]
    if os.name=='nt':
        candidates += [r'C:\Program Files\MuseScore 4\bin\MuseScore4.exe',r'C:\Program Files\MuseScore Studio 4\bin\MuseScore4.exe']
    for item in candidates:
        if item and Path(item).exists(): return str(Path(item))
    return None

def render_pdf(source,destination,binary=None):
    binary=binary or find_musescore()
    if not binary: raise RuntimeError('MuseScore Studio is not installed or MUSESCORE_BIN is not configured.')
    destination=Path(destination); destination.parent.mkdir(parents=True,exist_ok=True)
    run=subprocess.run(['xvfb-run','-a','-s','-screen 0 1280x1024x24',binary,'-o',str(destination),str(source)],capture_output=True,text=True,timeout=180)
    if run.returncode or not destination.exists(): raise RuntimeError('MuseScore could not render this score to PDF.')
    return destination

def render_pages_and_lines(source,output_dir,dpi=90,line_dpi=180):
    """Render low-memory pages plus high-resolution musical systems one page at a time."""
    source=Path(source); output_dir=Path(output_dir); output_dir.mkdir(parents=True,exist_ok=True)
    binary=shutil.which('pdftoppm')
    if not binary: raise RuntimeError('pdftoppm is not installed.')
    prefix=output_dir/'page'
    run=subprocess.run([binary,'-png','-r',str(dpi),str(source),str(prefix)],capture_output=True,text=True,timeout=120)
    pages=sorted(output_dir.glob('page-*.png'),key=lambda p:int(p.stem.rsplit('-',1)[-1]))
    if run.returncode or not pages: raise RuntimeError('The score pages could not be rendered.')
    lines=[]
    ratio=line_dpi/dpi
    for page_number,page in enumerate(pages,1):
        # Render only this page at high resolution, then discard it after cropping.
        detail_root=output_dir/f'detail-{page_number:03d}'
        detail=detail_root.with_suffix('.png')
        detail_run=subprocess.run([binary,'-png','-f',str(page_number),'-l',str(page_number),'-singlefile','-r',str(line_dpi),str(source),str(detail_root)],capture_output=True,text=True,timeout=90)
        if detail_run.returncode or not detail.exists(): continue
        with Image.open(detail) as opened:
            image=opened.convert('RGB')
        gray=image.convert('L'); width,height=image.size
        active=[]; pixels=gray.load(); threshold=max(10,int(width*.012))
        for y in range(height):
            if sum(1 for x in range(0,width,2) if pixels[x,y] < 190) >= threshold//2: active.append(y)
        groups=[]
        merge_gap=max(58,int(58*ratio))
        for y in active:
            if not groups or y-groups[-1][-1] > merge_gap: groups.append([y])
            else: groups[-1].append(y)
        groups=[g for g in groups if g[-1]-g[0] >= int(55*ratio)]
        for line_number,g in enumerate(groups,1):
            padding=int(28*ratio); top=max(0,g[0]-padding); bottom=min(height,g[-1]+padding+1)
            crop=image.crop((0,top,width,bottom))
            target=output_dir/f'line-{page_number:03d}-{line_number:03d}.png'
            crop.save(target,optimize=True)
            crop.close(); lines.append(target)
        gray.close(); image.close(); detail.unlink(missing_ok=True)
    if not lines: lines=pages[:]
    return pages,lines

def render_preview(source,destination):
    """Render the first PDF page as a phone-friendly PNG preview."""
    destination=Path(destination); destination.parent.mkdir(parents=True,exist_ok=True)
    output_root=destination.with_suffix('')
    binary=shutil.which('pdftoppm')
    if not binary: raise RuntimeError('pdftoppm is not installed.')
    run=subprocess.run([binary,'-png','-f','1','-singlefile','-r','150',str(source),str(output_root)],capture_output=True,text=True,timeout=60)
    if run.returncode or not destination.exists(): raise RuntimeError('The score preview could not be rendered.')
    return destination

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('destination');args=p.parse_args()
    print(render_pdf(args.source,args.destination))
