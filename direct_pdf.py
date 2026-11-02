"""Experimental letter overlays for semantic SMuFL PDFs; never run OMR here.

Only upright PDFs with extractable standard noteheads, five-line staves,
and G/F clefs are accepted. Unsupported input raises UnsupportedPDF before
any output is written. Key signatures, accidentals and rhythms stay in the
original engraving; output letters denote written diatonic staff positions.
"""
from pathlib import Path
import json
import statistics
import tempfile

import fitz


class UnsupportedPDF(ValueError):
    pass


HEADS = {0xE0A4: 'filled', 0xE0A3: 'half', 0xE0A2: 'whole'}
CLEFS = {0xE050: 'treble', 0xE062: 'bass'}


def _characters(page):
    for block in page.get_text('rawdict')['blocks']:
        for line in block.get('lines', []):
            for span in line['spans']:
                for char in span['chars']:
                    yield char


def _staves(page):
    ys = set()
    for drawing in page.get_drawings():
        for item in drawing['items']:
            if item[0] == 'l':
                a, b = item[1:3]
                if abs(a.y-b.y) < .02 and abs(a.x-b.x) > 80:
                    ys.add(round(a.y, 2))
    ys = sorted(ys)
    staves = []
    index = 0
    while index <= len(ys)-5:
        candidate = ys[index:index+5]
        gaps = [b-a for a, b in zip(candidate, candidate[1:])]
        spacing = statistics.median(gaps)
        if 2 < spacing < 15 and max(abs(g-spacing) for g in gaps) < .05:
            staves.append({'bottom': candidate[-1], 'center': candidate[2],
                           'spacing': spacing, 'clefs': []})
            index += 5
        else:
            index += 1
    return staves


def inspect_pdf(source):
    """Return the complete overlay plan without changing the source file."""
    plan = []
    with fitz.open(source) as document:
        for page_index, page in enumerate(document):
            if page.rotation:
                raise UnsupportedPDF('Rotated PDF pages need recognition or normalization first.')
            chars = list(_characters(page))
            heads = [c for c in chars if ord(c['c']) in HEADS]
            if not heads:
                raise UnsupportedPDF(f'Page {page_index+1} has no readable SMuFL noteheads; use recognition.')
            if any(0xE0A0 <= ord(c['c']) <= 0xE0FF and ord(c['c']) not in HEADS
                   for c in chars):
                raise UnsupportedPDF('Unsupported notehead shape; use recognition.')
            if any(ord(c['c']) in {0xE05C, 0xE069, 0xE06A} for c in chars):
                raise UnsupportedPDF('C or percussion clef is not supported by the direct route.')
            staves = _staves(page)
            if not staves:
                raise UnsupportedPDF('Could not identify regular five-line staves.')
            for char in chars:
                if ord(char['c']) in CLEFS:
                    x, y = char['origin']
                    staff = min(staves, key=lambda s: abs(s['center']-y))
                    if abs(staff['center']-y) > 3*staff['spacing']:
                        raise UnsupportedPDF('Clef could not be assigned to a staff.')
                    staff['clefs'].append((x, CLEFS[ord(char['c'])]))
            for staff in staves:
                staff['clefs'].sort()
                if not staff['clefs']:
                    raise UnsupportedPDF('Every staff must have an explicit readable G or F clef.')
            for char in heads:
                x, y = char['origin']
                ranked = sorted(staves, key=lambda s: abs(s['center']-y))
                staff = ranked[0]
                if len(ranked)>1 and abs(abs(ranked[1]['center']-y)-abs(staff['center']-y)) < staff['spacing']*.3:
                    raise UnsupportedPDF('Note lies ambiguously between two staves.')
                if abs(y-staff['center']) > staff['spacing']*8:
                    raise UnsupportedPDF('Note is too far from its staff to map safely.')
                active = [c for c in staff['clefs'] if c[0] <= x+.1]
                if not active:
                    raise UnsupportedPDF('A note precedes its staff clef.')
                steps = (staff['bottom']-y)/(staff['spacing']/2)
                if abs(steps-round(steps)) > .04:
                    raise UnsupportedPDF('Notehead does not align with a staff line or space.')
                index = (30 if active[-1][1]=='treble' else 18)+round(steps)
                width = char['bbox'][2]-char['bbox'][0]
                if not 2 < width < 20:
                    raise UnsupportedPDF('Unusable notehead dimensions.')
                plan.append({'page': page_index+1, 'x': x, 'y': y,
                             'centerX': (char['bbox'][0]+char['bbox'][2])/2,
                             'width': width, 'letter': 'CDEFGAB'[index%7],
                             'writtenOctave': index//7, 'shape': HEADS[ord(char['c'])],
                             'clef': active[-1][1]})
    return sorted(plan, key=lambda n: (n['page'], n['x'], n['y']))


def convert_pdf(source, destination):
    """Validate all pages, then overlay letters without removing notation."""
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError('Choose a different output path to preserve the original PDF.')
    plan = inspect_pdf(source)
    with fitz.open(source) as document:
        for note in plan:
            page = document[note['page']-1]
            size = min(7, note['width']*.63)
            width = fitz.get_text_length(note['letter'], fontname='hebo', fontsize=size)
            x, y = note['centerX'], note['y']
            hollow = note['shape'] != 'filled'
            if hollow:
                page.draw_rect(fitz.Rect(x-width/2-.1, y-size*.37,
                                         x+width/2+.1, y+size*.37),
                               color=None, fill=(1,1,1), overlay=True)
            page.insert_text((x-width/2, y+size*.36), note['letter'],
                             fontname='hebo', fontsize=size,
                             color=(0,0,0) if hollow else (1,1,1), overlay=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.direct-pdf-', dir=destination.parent) as td:
            temporary = Path(td)/'output.pdf'
            document.save(temporary, garbage=4, deflate=True)
            with fitz.open(temporary) as check:
                if len(check) != len(document):
                    raise RuntimeError('Output PDF page count does not match the source.')
            temporary.replace(destination)
    return plan


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('destination')
    parser.add_argument('--audit')
    args = parser.parse_args()
    try:
        notes = convert_pdf(args.source, args.destination)
    except UnsupportedPDF as exc:
        parser.exit(2, f'Direct conversion unavailable: {exc}\n')
    if args.audit:
        Path(args.audit).write_text(json.dumps(notes, indent=2))
    print(f'Lettered {len(notes)} noteheads. Original key signatures and accidentals apply.')
