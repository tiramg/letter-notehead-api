"""Render converted MusicXML/MXL to PDF with MuseScore Studio."""
from pathlib import Path
import os, shutil, subprocess

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
    run=subprocess.run([binary,'-o',str(destination),str(source)],capture_output=True,text=True,timeout=180)
    if run.returncode or not destination.exists(): raise RuntimeError('MuseScore could not render this score to PDF.')
    return destination

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
