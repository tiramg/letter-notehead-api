import tempfile
import unittest
import zipfile
from pathlib import Path

from cross_check import compare_scores
from server import parse_musicxml


def note(pitch='C', duration=1, extra='', octave=4):
    return (f'<note>{extra}<pitch><step>{pitch}</step><octave>{octave}</octave></pitch>'
            f'<duration>{duration}</duration></note>')


def measure(notes, divisions=None):
    attributes = f'<attributes><divisions>{divisions}</divisions></attributes>' if divisions else ''
    return f'<measure>{attributes}{notes}</measure>'


class CrossCheckTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def score(self, name, measures):
        path = Path(self.directory.name) / name
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('score.xml', f'<score-partwise><part id="P1">{measures}</part></score-partwise>')
        return path

    def compare(self, primary, secondary):
        return compare_scores(self.score('primary.mxl', primary), self.score('secondary.mxl', secondary))

    def test_identical_scores_agree(self):
        score = measure(note() + note('D'))
        self.assertEqual(self.compare(score, score)['differingMeasureCount'], 0)

    def test_changed_pitch_is_reported(self):
        difference = self.compare(measure(note()), measure(note('D')))['differingMeasures'][0]
        self.assertEqual(difference['onlyInPrimary'], ['C4'])
        self.assertEqual(difference['onlyInSecondary'], ['D4'])

    def test_swapped_note_order_does_not_agree(self):
        result = self.compare(measure(note() + note('D')), measure(note('D') + note()))
        self.assertEqual(result['differingMeasureCount'], 1)
        self.assertEqual(result['differingMeasures'][0]['onlyInPrimary'], [])

    def test_changed_rhythm_does_not_agree(self):
        result = self.compare(measure(note(duration=1) + note('D', 3)),
                              measure(note(duration=2) + note('D', 2)))
        self.assertEqual(result['differingMeasureCount'], 1)

    def test_missing_rest_only_measure_is_reported(self):
        rest = '<note><rest/><duration>4</duration></note>'
        result = self.compare(measure(note()) + measure(rest), measure(note()))
        self.assertEqual(result['measuresAgreed'], 1)
        self.assertTrue(result['differingMeasures'][0]['missingInSecondary'])

    def test_rest_duration_change_is_reported(self):
        self.assertEqual(self.compare(measure('<note><rest/><duration>1</duration></note>'),
                                      measure('<note><rest/><duration>2</duration></note>'))['differingMeasureCount'], 1)

    def test_equivalent_divisions_agree(self):
        self.assertEqual(self.compare(measure(note(duration=2), 2),
                                      measure(note(duration=4), 4))['differingMeasureCount'], 0)

    def test_divisions_carry_to_next_measure(self):
        a = measure(note(duration=2), 2) + measure(note('D', 2))
        b = measure(note(duration=4), 4) + measure(note('D', 4))
        self.assertEqual(self.compare(a, b)['differingMeasureCount'], 0)
        parsed = parse_musicxml(self.score('parse.mxl', a))
        self.assertEqual(parsed['parts'][0]['measures'][1]['notes'][0]['duration'], 1)

    def test_chord_serialization_order_agrees(self):
        chord = '<chord/>'
        a = measure(note() + note('E', extra=chord))
        b = measure(note('E') + note(extra=chord))
        self.assertEqual(self.compare(a, b)['differingMeasureCount'], 0)

    def test_staff_change_is_reported(self):
        result = self.compare(measure(note(extra='<staff>1</staff>')),
                              measure(note(extra='<staff>2</staff>')))
        self.assertEqual(result['differingMeasureCount'], 1)

    def test_tie_change_is_reported(self):
        result = self.compare(measure(note()), measure(note(extra='<tie type="start"/>')))
        self.assertEqual(result['differingMeasureCount'], 1)

    def test_backup_voice_order_agrees(self):
        a = measure(note() + '<backup><duration>1</duration></backup>' + note('E', extra='<voice>2</voice>'))
        b = measure(note('E', extra='<voice>2</voice>') + '<backup><duration>1</duration></backup>' + note())
        self.assertEqual(self.compare(a, b)['differingMeasureCount'], 0)


if __name__ == '__main__':
    unittest.main()
