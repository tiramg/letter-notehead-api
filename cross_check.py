"""Cross-check two independent recognitions of the same score.

Compares pitches and timed musical events from two recognitions. Agreement
is a consistency check, not proof of accuracy: both passes can make the
same mistake. The primary score is never modified by this module.
"""
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from fractions import Fraction


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


def measure_event_map(mxl_path):
    """Compare musical timelines in quarter-note units, independent of divisions.

    Sorting events permits harmless XML chord/voice serialization changes.
    Staff, voice, rests, grace notes and ties remain part of the comparison.
    """
    result = {}
    for part in _score_root(mxl_path).findall('part'):
        divisions = 1
        for index, measure in enumerate(part.findall('measure')):
            divisions = int(measure.findtext('attributes/divisions') or divisions)
            cursor = Fraction(0)
            last_onset = cursor
            events = Counter()
            for child in measure:
                duration = Fraction(child.findtext('duration') or 0) / divisions
                if child.tag == 'backup':
                    cursor -= duration
                elif child.tag == 'forward':
                    cursor += duration
                elif child.tag == 'note':
                    chord = child.find('chord') is not None
                    grace = child.find('grace') is not None
                    onset = last_onset if chord else cursor
                    pitch = _pitch_of(child)
                    if pitch is None:
                        pitch = 'rest' if child.find('rest') is not None else 'unpitched'
                    ties = tuple(sorted(t.get('type', '') for t in child.findall('tie')))
                    events[(onset, duration, pitch, child.findtext('staff') or '1',
                            child.findtext('voice') or '1', grace, ties)] += 1
                    if not chord:
                        last_onset = onset
                        if not grace:
                            cursor += duration
            result[(part.get('id'), index)] = events
    return result


def compare_scores(primary_path, secondary_path):
    """Return per-measure musical disagreements between two MXL files.

    Measures present in only one score, or whose pitch multisets differ,
    are reported with the pitches unique to each pass.
    """
    primary = measure_pitch_map(primary_path)
    secondary = measure_pitch_map(secondary_path)
    primary_events = measure_event_map(primary_path)
    secondary_events = measure_event_map(secondary_path)
    differences = []
    for key in sorted(set(primary) | set(secondary), key=lambda k: (str(k[0]), k[1])):
        in_primary = primary.get(key, Counter())
        in_secondary = secondary.get(key, Counter())
        missing = key not in primary or key not in secondary
        events_differ = primary_events.get(key) != secondary_events.get(key)
        if not missing and in_primary == in_secondary and not events_differ:
            continue
        only_primary = sorted((in_primary - in_secondary).elements())
        only_secondary = sorted((in_secondary - in_primary).elements())
        differences.append({
            "part": key[0],
            "missingInPrimary": key not in primary,
            "missingInSecondary": key not in secondary,
            "timingOrStructureDiffers": events_differ,
            "measureIndex": key[1],
            "primaryNoteCount": sum(in_primary.values()),
            "secondaryNoteCount": sum(in_secondary.values()),
            "onlyInPrimary": only_primary,
            "onlyInSecondary": only_secondary,
        })
    total_primary = sum(sum(c.values()) for c in primary.values())
    total_secondary = sum(sum(c.values()) for c in secondary.values())
    agreed = len(set(primary) | set(secondary)) - len(differences)
    compared = len(set(primary) | set(secondary))
    return {
        "method": "dual-pass-musical-event-diff",
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
