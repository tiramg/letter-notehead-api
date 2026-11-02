"""Measure recognition against original fixture oracles; no engraving required."""
import argparse
from collections import Counter
from fractions import Fraction
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from photo_prep import prepare_photo


def expected_events(oracle):
    return Counter((n['measure'],n['letter'],n['writtenOctave'],Fraction(n['alter']),
                    Fraction(n['duration'],2)) for n in oracle)


def recognized_events(path):
    with zipfile.ZipFile(path) as archive:
        name=next(n for n in archive.namelist() if n.endswith('.xml') and not n.startswith('META-INF/'))
        root=ET.fromstring(archive.read(name))
    events=Counter()
    for part in root.findall('part'):
        divisions=1
        for index,measure in enumerate(part.findall('measure'),1):
            divisions=int(measure.findtext('attributes/divisions') or divisions)
            for note in measure.findall('note'):
                p=note.find('pitch')
                if p is None: continue
                events[(index,p.findtext('step'),int(p.findtext('octave')),Fraction(p.findtext('alter') or '0'),
                        Fraction(note.findtext('duration') or '0')/divisions)]+=1
    return events


def run(directory,binary,timeout=240):
    directory=directory.resolve(); binary=binary.resolve()
    results={}
    for case, filename, oracle_name in [('simple-pdf','simple-piano.pdf','simple-piano'),
                                        ('dense-pdf','dense-piano.pdf','dense-piano'),
                                        ('simulated-photo','dense-piano-simulated-photo.jpg','dense-piano')]:
        case_dir=directory/'omr'/case/str(time.time_ns());case_dir.mkdir(parents=True,exist_ok=True)
        source=directory/filename
        if source.suffix=='.jpg':
            data,suffix,metrics=prepare_photo(source.read_bytes(),'.jpg',case_dir,'best')
            source=case_dir/('prepared'+suffix);source.write_bytes(data)
            (case_dir/'preprocessing.json').write_text(json.dumps(metrics,indent=2))
        command=[str(binary),'-batch','-swap']
        if source.suffix=='.pdf':
            command+=['-constant','org.audiveris.omr.image.ImageLoading.pdfResolution=350',
                      '-constant','org.audiveris.omr.text.tesseract.TesseractOCR.useOCR=false']
        command+=['-transcribe','-export','-output',str(case_dir),'--',str(source)]
        env=os.environ.copy();env['JAVA_TOOL_OPTIONS']='-Xmx128m -XX:+UseSerialGC -Djava.awt.headless=true'
        env['TESSDATA_PREFIX']='/usr/share/tesseract-ocr/5/tessdata'
        started=time.perf_counter()
        try:
            process=subprocess.run(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                   text=True,timeout=timeout)
            (case_dir/'engine.log').write_text(process.stdout)
            mxls=list(case_dir.rglob('*.mxl'))
            if process.returncode or not mxls:
                results[case]={'status':'engine_failed','exitCode':process.returncode}
            else:
                expected=expected_events(json.loads((directory/f'{oracle_name}-oracle.json').read_text()))
                actual=recognized_events(mxls[0]);matched=sum((actual & expected).values())
                results[case]={'status':'completed','expectedNotes':sum(expected.values()),
                               'recognizedNotes':sum(actual.values()),'matchedPitchAndDuration':matched,
                               'missingOrWrong':sum((expected-actual).values()),
                               'extraOrWrong':sum((actual-expected).values()),
                               'precision':matched/sum(actual.values()) if actual else 0,
                               'recall':matched/sum(expected.values())}
        except subprocess.TimeoutExpired:
            results[case]={'status':'timeout','timeoutSeconds':timeout}
        results[case]['seconds']=round(time.perf_counter()-started,3)
        results[case]['metric']='Per-measure pitch, accidental, octave and duration multiset; excludes onset, voice and staff accuracy.'
        (directory/'omr-results.json').write_text(json.dumps(results,indent=2))
        print(case,json.dumps(results[case]),flush=True)
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);parser.add_argument('--audiveris',required=True,type=Path)
    args=parser.parse_args();run(args.directory,args.audiveris)
