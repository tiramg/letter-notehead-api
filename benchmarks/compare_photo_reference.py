"""Compare piano-page written pitches with a semantic-PDF reference.

This diagnostic checks letter, written octave, measure index and staff. It
excludes accidentals, rhythm, onset and voice, and is not full-score accuracy.
The reference must use paired five-line piano staves and connected barlines.
"""
from collections import Counter
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile
import fitz

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from direct_pdf import inspect_pdf, _staves


def reference_notes(path, page_number=1):
    notes=[n for n in inspect_pdf(path) if n['page']==page_number]
    result=Counter()
    with fitz.open(path) as pdf:
        page=pdf[page_number-1]
        staves=_staves(page)
        if len(staves)%2:raise ValueError('Expected paired piano staves.')
        systems=[];offset=0
        for i in range(0,len(staves),2):
            upper,lower=staves[i:i+2]
            top=upper['bottom']-4*upper['spacing']
            lower_top=lower['bottom']-4*lower['spacing']
            candidates=[]
            for drawing in page.get_drawings():
                for item in drawing['items']:
                    if item[0]!='l':continue
                    a,b=item[1:3]
                    if (abs(a.x-b.x)<.02 and 35<a.x<page.rect.width-10
                        and abs(min(a.y,b.y)-top)<.4
                        and max(a.y,b.y)>=lower_top-.4):
                        candidates.append(a.x)
            boundaries=[]
            for x in sorted(set(candidates)):
                if not boundaries or x-boundaries[-1]>4:
                    boundaries.append(x)
                else:boundaries[-1]=x
            if not boundaries:raise ValueError('No connected measure barlines found.')
            systems.append((upper,lower,boundaries,offset))
            offset+=len(boundaries)
        for note in notes:
            upper,lower,bounds,offset=min(systems,key=lambda row:min(abs(note['y']-row[0]['center']),abs(note['y']-row[1]['center'])))
            staff=1 if abs(note['y']-upper['center'])<abs(note['y']-lower['center']) else 2
            measure=offset+sum(note['x']>x for x in bounds)+1
            if measure>offset+len(bounds):raise ValueError('Reference note outside final barline.')
            result[(measure,staff,note['letter'],note['writtenOctave'])]+=1
    return result


def recognized_notes(path):
    with zipfile.ZipFile(path) as z:
        score=ET.fromstring(z.read(next(n for n in z.namelist() if n.endswith('.xml') and not n.startswith('META-INF/'))))
    parts=score.findall('part')
    if len(parts)!=1:raise ValueError('Measure/staff comparison currently requires a single piano part.')
    result=Counter()
    for index,measure in enumerate(parts[0].findall('measure'),1):
        for note in measure.findall('note'):
            pitch=note.find('pitch')
            if pitch is None:continue
            result[(index,int(note.findtext('staff') or 1),pitch.findtext('step'),int(pitch.findtext('octave')))]+=1
    return result


def compare(reference,actual):
    by_measure=[]
    for measure in sorted({key[0] for key in reference}|{key[0] for key in actual}):
        expected=Counter({k:v for k,v in reference.items() if k[0]==measure})
        found=Counter({k:v for k,v in actual.items() if k[0]==measure})
        missing=sum((expected-found).values());extra=sum((found-expected).values())
        by_measure.append({'measure':measure,'expectedNotes':sum(expected.values()),
                           'recognizedNotes':sum(found.values()),'matchedWrittenPitches':sum((expected&found).values()),
                           'missingOrWrong':missing,'extraOrWrong':extra})
    return {'expectedNotes':sum(reference.values()),'recognizedNotes':sum(actual.values()),
            'matchedWrittenPitches':sum((reference&actual).values()),
            'missingOrWrong':sum((reference-actual).values()),'extraOrWrong':sum((actual-reference).values()),
            'measuresWithPitchDisagreements':[m['measure'] for m in by_measure if m['missingOrWrong'] or m['extraOrWrong']],
            'measures':by_measure}


if __name__=='__main__':
    import argparse,json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference_pdf');parser.add_argument('recognized_mxl');parser.add_argument('--page',type=int,default=1)
    args=parser.parse_args()
    print(json.dumps(compare(reference_notes(args.reference_pdf,args.page),recognized_notes(args.recognized_mxl)),indent=2))
