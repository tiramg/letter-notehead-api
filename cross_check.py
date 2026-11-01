"""Cross-check two independent recognitions of the same score.

Audiveris is deterministic for identical input, but a PDF page recognized
directly (vector rendering at a fixed resolution) and the same page
recognized from a raster image go through different binarization and
glyph decisions. Where the two passes agree on a measure's pitches, the
result is very likely right. Where they disagree, the measure deserves a
visual check -- and the disagreement says exactly which pitches differ,
instead of asking the user to re-check the whole page.

Used by server.py when LETTER_NOTEHEAD_CROSSCHECK=1: the primary result
is still the PDF pass; the cross-check only annotates validation/issues.
"""
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter


def _score_root(mxl_path):
    with zipfile.ZipFile(mxl_path) as zf:
        name = next(n for n in zf.namelist()
                    if n.endswith('.xml') and not n.startswith('META-INF/'))
        return ET.fromstring(zf.read(name))


def _pitch_of(note):
    pitch = note.find('pitch')
    if pitch is None:
        return None
    step = pitch.findtext('step') or '?'
    alter = pitch.findtext('alter')
    accidental = {'1': '#', '-1': 'b', '2': '##', '-2': 'bb'}.get(alter, '') if alter else ''
    return step + accidental + (pitch.findtext('octave') or '')


def measure_pitch_map(mxl_path):
    """Map (part_id, measure_index) -> Counter of pitches, grace notes included."""
    root = _score_root(mxl_path)
    result = {}
    for part in root.findall('part'):
        part_id = part.attrib.get('id')
        for index, measure in enumerate(part.findall('measure')):
            pitches = Counter()
            for note in measure.findall('note'):
                pitch = _pitch_of(note)
                if pitch is not None:
                    pitches[pitch] += 1
            result[(part_id, index)] = pitches
    return result


def compare_scores(primary_path, secondary_path):
    """Return per-measure pitch disagreements between two MXL files.

    Measures present in only one score, or whose pitch multisets differ,
    are reported with the pitches unique to each pass.
    """
    primary = measure_pitch_map(primary_path)
    secondary = measure_pitch_map(secondary_path)
    differences = []
    for key in sorted(set(primary) | set(secondary), key=lambda k: (str(k[0]), k[1])):
        in_primary = primary.get(key, Counter())
        in_secondary = secondary.get(key, Counter())
        if in_primary == in_secondary:
            continue
        only_primary = sorted((in_primary - in_secondary).elements())
        only_secondary = sorted((in_secondary - in_primary).elements())
        differences.append({
            "part": key[0],
            "measureIndex": key[1],
            "primaryNoteCount": sum(in_primary.values()),
            "secondaryNoteCount": sum(in_secondary.values()),
            "onlyInPrimary": only_primary,
            "onlyInSecondary": only_secondary,
        })
    total_primary = sum(sum(c.values()) for c in primary.values())
    total_secondary = sum(sum(c.values()) for c in secondary.values())
    agreed = sum(1 for k in set(primary) | set(secondary)
                 if primary.get(k, Counter()) == secondary.get(k, Counter()))
    compared = len(set(primary) | set(secondary))
    return {
        "method": "dual-pass-pitch-diff",
        "primaryNotes": total_primary,
        "secondaryNotes": total_secondary,
        "measuresCompared": compared,
        "measuresAgreed": agreed,
        "differingMeasures": differences,
        "differingMeasureCount": len(differences),
    }


if __name__ == '__main__':
    import argparse, json
    parser = argparse.ArgumentParser(description='Compare two MXL recognitions measure by measure.')
    parser.add_argument('primary')
    parser.add_argument('secondary')
    args = parser.parse_args()
    print(json.dumps(compare_scores(args.primary, args.secondary), indent=2))
