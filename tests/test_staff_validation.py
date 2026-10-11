import tempfile
import unittest
import zipfile
from pathlib import Path
from server import validate_musicxml


class StaffValidationTests(unittest.TestCase):
    def check(self, content, staves=2, beats='4'):
        score = f'''<score-partwise><part id="P1"><measure number="1">
        <attributes><divisions>4</divisions><staves>{staves}</staves><time><beats>{beats}</beats><beat-type>4</beat-type></time></attributes>
        </measure><measure number="2">{content}</measure></part></score-partwise>'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'score.mxl'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('score.xml', score)
            return validate_musicxml(path)

    def test_complete_bass_does_not_hide_empty_treble(self):
        result = self.check('<note><pitch><step>C</step><octave>3</octave></pitch><duration>16</duration><staff>2</staff></note>')
        self.assertEqual(result['suspectMeasureCount'], 1)
        self.assertEqual(result['suspectMeasures'][0]['staves'], [{'staff': '1', 'filled': 0.0}])

    def test_complete_rests_are_valid(self):
        notes = '<note><rest measure="yes"/><duration>16</duration><staff>1</staff></note><backup><duration>16</duration></backup><note><rest measure="yes"/><duration>16</duration><staff>2</staff></note>'
        self.assertEqual(self.check(notes)['suspectMeasureCount'], 0)

    def test_audiveris_consecutive_whole_measure_rests(self):
        content = '<note><rest measure="yes"/><duration>16</duration><staff>1</staff></note><note><rest measure="yes"/><duration>16</duration><staff>2</staff></note>'
        self.assertEqual(self.check(content)['suspectMeasureCount'], 0)

    def test_forward_does_not_hide_missing_music(self):
        content = '<forward><duration>8</duration></forward><note><rest/><duration>8</duration></note>'
        self.assertEqual(self.check(content, staves=1)['suspectMeasures'][0]['filled'], .5)

    def test_chord_duration_and_multiple_voices(self):
        content = '<note><rest/><duration>8</duration></note><note><chord/><rest/><duration>16</duration></note><backup><duration>8</duration></backup><note><rest/><duration>16</duration></note>'
        self.assertEqual(self.check(content, staves=1)['suspectMeasureCount'], 0)

    def test_additive_meter(self):
        content = '<note><rest/><duration>20</duration></note>'
        self.assertEqual(self.check(content, staves=1, beats='3+2')['suspectMeasureCount'], 0)


if __name__ == '__main__':
    unittest.main()
