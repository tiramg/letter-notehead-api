"""Build original, hand-specified notation fixtures and assess direct overlays.

Requires PyMuPDF, Pillow and a supplied Bravura SMuFL font (--font).
The oracle contains explicit letter/octave/position triples, not direct_pdf's
pitch calculation. This is a controlled geometry benchmark, not a substitute
for independent real-score or camera-image recognition tests.
"""
import argparse
import hashlib
import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import fitz
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from direct_pdf import convert_pdf, inspect_pdf, UnsupportedPDF

# Letter, octave, vertical offset from the bottom staff line (5pt spacing).
TREBLE = [('C',4,5),('D',4,2.5),('E',4,0),('F',4,-2.5),('G',4,-5),
          ('A',4,-7.5),('B',4,-10),('C',5,-12.5),('D',5,-15),('E',5,-17.5)]
BASS = [('C',2,10),('E',2,5),('G',2,0),('B',2,-5),('C',3,-7.5),
        ('D',3,-10),('E',3,-12.5),('F',3,-15),('G',3,-17.5),('A',3,-20)]
HEAD = {'eighth':0xE0A4,'quarter':0xE0A4,'half':0xE0A3,'whole':0xE0A2}
DURATION = {'eighth':1,'quarter':2,'half':4,'whole':8}


def glyph(page, x, y, code):
    page.insert_text((x,y), chr(code), fontname='Music', fontsize=20)


def staff(page, bottom, clef='treble', start=35, end=560):
    for k in range(5):
        page.draw_line((start,bottom-k*5),(end,bottom-k*5),width=.45)
    glyph(page,start+5,bottom-(5 if clef=='treble' else 15),
          0xE050 if clef=='treble' else 0xE062)


def add_note(page, oracle, x, bottom, spec, kind='quarter', chord=False, alter=0, stem=True, **fields):
    letter, octave, offset = spec
    y = bottom+offset
    glyph(page,x,y,HEAD[kind])
    # Actual ledger strokes, rather than text labels claiming to be notation.
    for ledger in range(int(bottom+5),int(y+1),5) if y>bottom else []:
        page.draw_line((x-2,ledger),(x+8,ledger),width=.45)
    for ledger in range(int(bottom-25),int(y-1),-5) if y<bottom-20 else []:
        page.draw_line((x-2,ledger),(x+8,ledger),width=.45)
    if kind!='whole' and stem:
        page.draw_line((x+5.6,y),(x+5.6,y-24),width=.5)
    oracle.append(dict(page=1,x=x,y=y,letter=letter,writtenOctave=octave,
                       duration=DURATION[kind],type=kind,chord=chord,alter=alter,**fields))


def save_xml(path, notes, dense=False):
    root=ET.Element('score-partwise',version='4.0')
    listing=ET.SubElement(root,'part-list')
    scorepart=ET.SubElement(listing,'score-part',id='P1')
    ET.SubElement(scorepart,'part-name').text='Benchmark piano'
    part=ET.SubElement(root,'part',id='P1')
    measures=sorted(set(n['measure'] for n in notes))
    for number in measures:
        measure=ET.SubElement(part,'measure',number=str(number))
        if number==1:
            attributes=ET.SubElement(measure,'attributes')
            ET.SubElement(attributes,'divisions').text='2'
            key=ET.SubElement(attributes,'key'); ET.SubElement(key,'fifths').text='-3' if dense else '0'
            meter=ET.SubElement(attributes,'time')
            ET.SubElement(meter,'beats').text='4'; ET.SubElement(meter,'beat-type').text='4'
            ET.SubElement(attributes,'staves').text='2'
            for staffno, sign, line in [(1,'G',2),(2,'F',4)]:
                clef=ET.SubElement(attributes,'clef',number=str(staffno))
                ET.SubElement(clef,'sign').text=sign; ET.SubElement(clef,'line').text=str(line)
        for staffno in [1,2]:
            events=[n for n in notes if n['measure']==number and n['staff']==staffno]
            if staffno==2:
                backup=ET.SubElement(measure,'backup'); ET.SubElement(backup,'duration').text='8'
            for data in events:
                note=ET.SubElement(measure,'note')
                if data['chord']: ET.SubElement(note,'chord')
                pitch=ET.SubElement(note,'pitch'); ET.SubElement(pitch,'step').text=data['letter']
                if data['alter']: ET.SubElement(pitch,'alter').text=str(data['alter'])
                ET.SubElement(pitch,'octave').text=str(data['writtenOctave'])
                ET.SubElement(note,'duration').text=str(data['duration'])
                ET.SubElement(note,'voice').text=str(staffno)
                ET.SubElement(note,'type').text=data['type']
                ET.SubElement(note,'staff').text=str(staffno)
    ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)


def build(directory, font, dense):
    name='dense-piano' if dense else 'simple-piano'
    pdf=fitz.open(); page=pdf.new_page(width=595,height=842)
    page.insert_font(fontname='Music',fontfile=str(font))
    page.insert_text((35,38), 'LetterScore / '+name.replace('-',' ').title(), fontsize=16)
    page.insert_text((35,57),'Original benchmark study | 4/4 | Known note and rhythm reference',fontsize=9)
    oracle=[]
    systems=4 if dense else 3
    for system in range(systems):
        top=120+system*(175 if dense else 200); bottom=top+65
        staff(page,top);staff(page,bottom,'bass')
        page.draw_line((35,top-20),(35,bottom),width=.6)
        for line_bottom in [top,bottom]:
            for yy in [line_bottom-15,line_bottom-5]:
                glyph(page,85 if dense else 70,yy,0xE084)
        if dense:
            for line_bottom in [top,bottom]:
                for dx, yy in ([(65,10),(72,17.5),(79,7.5)] if line_bottom==top else [(65,5),(72,12.5),(79,2.5)]):
                    glyph(page,dx,line_bottom-yy,0xE260)
        for half in range(2):
            m=system*2+half+1; start=100+half*230
            if dense:
                for event in range(8):
                    x=start+event*26
                    for c in range(3):
                        spec=TREBLE[(event+2*c+system)%len(TREBLE)]
                        add_note(page,oracle,x,top,spec,'eighth',chord=c>0,
                                 alter=-1 if spec[0] in 'BEA' else 0,stem=False,measure=m,staff=1,event=event)
                    chord_ys=[top+TREBLE[(event+2*c+system)%len(TREBLE)][2] for c in range(3)]
                    page.draw_line((x+5.6,max(chord_ys)),(x+5.6,min(chord_ys)-24),width=.5)
                    # Beam pairs preserve the eight-eighth-note rhythm visually.
                    if event%2==0:
                        y0=min(top+TREBLE[(event+2*c+system)%len(TREBLE)][2] for c in range(3))-24
                        y1=min(top+TREBLE[(event+1+2*c+system)%len(TREBLE)][2] for c in range(3))-24
                        page.draw_line((x+5.6,y0),(x+31.6,y1),width=2)
                for event in range(4):
                    for c in range(3):
                        spec=BASS[(event+2*c+system)%len(BASS)]
                        add_note(page,oracle,start+event*52,bottom,spec,chord=c>0,
                                 alter=-1 if spec[0] in 'BEA' else 0,stem=False,measure=m,staff=2,event=event)
                    chord_ys=[bottom+BASS[(event+2*c+system)%len(BASS)][2] for c in range(3)]
                    page.draw_line((start+event*52+5.6,max(chord_ys)),(start+event*52+5.6,min(chord_ys)-24),width=.5)
            else:
                kinds=[['quarter']*4,['half']*2,['whole']][system]
                for event,kind in enumerate(kinds):
                    x=start+event*(208/len(kinds))
                    add_note(page,oracle,x,top,TREBLE[(m+event)%10],kind,measure=m,staff=1,event=event)
                    add_note(page,oracle,x,bottom,BASS[(m+event)%10],kind,measure=m,staff=2,event=event)
            page.draw_line((start+222,top-20),(start+222,bottom),width=.55)
    source=directory/f'{name}.pdf'; pdf.subset_fonts();pdf.save(source,deflate=True);pdf.close()
    (directory/f'{name}-oracle.json').write_text(json.dumps(oracle,indent=2))
    save_xml(directory/f'{name}.musicxml',oracle,dense)
    return source,oracle


def assess(source,oracle,destination):
    before=hashlib.sha256(source.read_bytes()).hexdigest(); started=time.perf_counter()
    mapped=convert_pdf(source,destination)
    expected={(n['page'],round(n['x'],2),round(n['y'],2)):(n['letter'],n['writtenOctave']) for n in oracle}
    actual={(n['page'],round(n['x'],2),round(n['y'],2)):(n['letter'],n['writtenOctave']) for n in mapped}
    correct=sum(actual.get(k)==value for k,value in expected.items())
    return {'expectedNotes':len(oracle),'mappedNotes':len(mapped),'correctLettersAndWrittenOctaves':correct,
            'missing':len(expected.keys()-actual.keys()),'extra':len(actual.keys()-expected.keys()),
            'sourceUnchanged':before==hashlib.sha256(source.read_bytes()).hexdigest(),
            'seconds':round(time.perf_counter()-started,3),
            'passed':actual==expected and len(mapped)==len(oracle)}


def run(output,font):
    output.mkdir(parents=True,exist_ok=True)
    results={}
    for dense in [False,True]:
        source,oracle=build(output,font,dense)
        results[source.stem]=assess(source,oracle,output/f'{source.stem}-alpha.pdf')
    with fitz.open(output/'dense-piano.pdf') as document:
        pix=document[0].get_pixmap(matrix=fitz.Matrix(2,2))
        image=Image.frombytes('RGB',[pix.width,pix.height],pix.samples)
        image.save(output/'dense-piano-raster.png')
        # Explicitly simulated camera degradation; this is not a phone photo.
        image=image.rotate(2.0,fillcolor='white',resample=Image.Resampling.BICUBIC)
        image=image.filter(ImageFilter.GaussianBlur(.5))
        image.save(output/'dense-piano-simulated-photo.jpg',quality=88)
    raster=fitz.open();page=raster.new_page(width=595,height=842)
    page.insert_image(page.rect,filename=str(output/'dense-piano-raster.png'))
    raster.save(output/'dense-piano-scan.pdf',deflate=True);raster.close()
    try:
        inspect_pdf(output/'dense-piano-scan.pdf'); rejected=False
    except UnsupportedPDF:
        rejected=True
    results['raster-safety-gate']={'passed':rejected,'expectedRoute':'OMR, not direct PDF'}
    results['photo-recognition']={'status':'not_run','reason':'Run run_omr_baseline.py separately. A real phone capture is still needed.'}
    (output/'results.json').write_text(json.dumps(results,indent=2))
    print(json.dumps(results,indent=2))
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--font',required=True,type=Path)
    parser.add_argument('--output',type=Path,default=Path('benchmark-output'))
    args=parser.parse_args();run(args.output,args.font)
