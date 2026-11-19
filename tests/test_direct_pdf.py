import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from collections import Counter

import fitz
from direct_pdf import convert_pdf, inspect_pdf, UnsupportedPDF
from benchmarks.compare_photo_reference import reference_notes
from benchmarks.build_benchmark import build, staff, glyph

FONT = Path(os.environ.get('LETTERSCORE_BENCHMARK_FONT', '/nonexistent'))


@unittest.skipUnless(FONT.is_file(), 'Set LETTERSCORE_BENCHMARK_FONT to Bravura.otf')
class DirectPDFTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        cls.simple, cls.simple_oracle = build(cls.directory, FONT, False)
        cls.dense, cls.dense_oracle = build(cls.directory, FONT, True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def assert_oracle(self, source, expected):
        actual = inspect_pdf(source)
        key = lambda n: (n['page'], round(n['x'], 2), round(n['y'], 2), n['letter'], n['writtenOctave'])
        self.assertEqual(Counter(map(key, actual)), Counter(map(key, expected)))

    def test_28_known_simple_notes(self):
        self.assert_oracle(self.simple, self.simple_oracle)

    def test_288_known_dense_chord_notes(self):
        self.assert_oracle(self.dense, self.dense_oracle)

    def test_reference_measure_and_staff_mapping(self):
        for source, oracle in [(self.simple,self.simple_oracle),(self.dense,self.dense_oracle)]:
            expected=Counter((n['measure'],n['staff'],n['letter'],n['writtenOctave']) for n in oracle)
            self.assertEqual(reference_notes(source),expected)

    def test_original_symbols_and_file_are_preserved(self):
        before = hashlib.sha256(self.simple.read_bytes()).digest()
        output = self.directory/'preserved.pdf'
        plan = convert_pdf(self.simple, output)
        def chars(page):
            return Counter((c['c'], tuple(round(p, 3) for p in c['origin']))
                           for b in page.get_text('rawdict')['blocks']
                           for l in b.get('lines',[]) for s in l['spans'] for c in s['chars'])
        with fitz.open(self.simple) as original, fitz.open(output) as converted:
            self.assertFalse(chars(original[0])-chars(converted[0]))
            self.assertEqual(sum((chars(converted[0])-chars(original[0])).values()),len(plan))
        self.assertEqual(before,hashlib.sha256(self.simple.read_bytes()).digest())

    def test_same_path_cannot_overwrite_source(self):
        with self.assertRaises(ValueError):
            convert_pdf(self.simple,self.simple)

    def test_scanned_pdf_is_rejected(self):
        output=self.directory/'scan.pdf'
        with fitz.open(self.simple) as original, fitz.open() as raster:
            p=raster.new_page(width=595,height=842)
            p.insert_image(p.rect,pixmap=original[0].get_pixmap())
            raster.save(output)
        with self.assertRaises(UnsupportedPDF): inspect_pdf(output)

    def test_rotated_page_is_rejected(self):
        output=self.directory/'rotated.pdf'
        with fitz.open(self.simple) as document:
            document[0].set_rotation(90);document.save(output)
        with self.assertRaises(UnsupportedPDF): inspect_pdf(output)

    def test_unsupported_later_page_writes_no_output(self):
        source=self.directory/'partial.pdf';output=self.directory/'should-not-exist.pdf'
        with fitz.open(self.simple) as document:
            document.new_page();document.save(source)
        with self.assertRaises(UnsupportedPDF): convert_pdf(source,output)
        self.assertFalse(output.exists())

    def test_midstaff_clef_change(self):
        source=self.directory/'clef-change.pdf'
        with fitz.open() as document:
            page=document.new_page();page.insert_font(fontname='Music',fontfile=str(FONT))
            staff(page,150);glyph(page,110,150,0xE0A4)
            glyph(page,300,135,0xE062);glyph(page,350,150,0xE0A4)
            document.save(source)
        notes=inspect_pdf(source)
        self.assertEqual([(n['letter'],n['writtenOctave']) for n in notes],[('E',4),('G',2)])

    def test_c_clef_is_rejected(self):
        source=self.directory/'c-clef.pdf'
        with fitz.open() as document:
            page=document.new_page();page.insert_font(fontname='Music',fontfile=str(FONT))
            staff(page,150);glyph(page,200,140,0xE05C);glyph(page,350,150,0xE0A4)
            document.save(source)
        with self.assertRaises(UnsupportedPDF): inspect_pdf(source)
