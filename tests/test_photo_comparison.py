from collections import Counter
import unittest
from benchmarks.compare_photo_reference import compare


class PhotoComparisonTests(unittest.TestCase):
    def test_same_counts_in_wrong_measure_do_not_match(self):
        a=Counter({(1,1,'C',4):1,(2,1,'D',4):1})
        b=Counter({(1,1,'D',4):1,(2,1,'C',4):1})
        result=compare(a,b)
        self.assertEqual(result['matchedWrittenPitches'],0)
        self.assertEqual(result['measuresWithPitchDisagreements'],[1,2])

    def test_wrong_staff_does_not_match(self):
        result=compare(Counter({(1,1,'C',4):1}),Counter({(1,2,'C',4):1}))
        self.assertEqual(result['matchedWrittenPitches'],0)
        self.assertEqual(result['missingOrWrong'],1)
        self.assertEqual(result['extraOrWrong'],1)

    def test_extra_duplicates_are_counted(self):
        result=compare(Counter({(1,1,'C',4):1}),Counter({(1,1,'C',4):2}))
        self.assertEqual(result['matchedWrittenPitches'],1)
        self.assertEqual(result['extraOrWrong'],1)
