# Controlled conversion benchmark

This suite separates direct PDF lettering from optical recognition. The original
studies have explicit note/position oracles and MusicXML references. They are
controlled fixtures, not a representative production accuracy dataset.

## Reproduce

Install `python3 -m pip install -r requirements-benchmark.txt`.
Download Bravura.otf from the checksum-pinned URL in `.github/workflows/tests.yml`
and set `LETTERSCORE_BENCHMARK_FONT` to its absolute path for regression tests.

```
python3 benchmarks/build_benchmark.py --font /path/Bravura.otf --output benchmark-output
python3 benchmarks/run_omr_baseline.py benchmark-output --audiveris /path/Audiveris
python3 direct_pdf.py input.pdf output-alpha.pdf --audit audit.json
```

The OMR command requires Audiveris 5.11.0 and Poppler support in that installation;
it uses the production 128 MB heap and 350 DPI/no-OCR PDF profile. Photo input
uses the existing best preprocessing profile. It runs recognition only, not
MuseScore engraving or the Android/API workflow. Benchmarks are regenerated
from source: do not compare outputs from different fixture versions.

## What is measured

- Direct PDFs: exact letter and written-octave matches at each expected notehead
  position. 28 simple notes; 288 dense chord notes. Existing engraving is retained.
- OMR: per-measure multisets of pitch, accidental, octave and duration against
  the oracle, pooled over parts/staves. Precision and recall are reported separately.
  Onset, voice/staff assignment, rest accuracy and engraving layout are NOT scored.
- Safety: scans and unsupported notation must be rejected by the direct route.
- Tests: clef changes, source preservation, rotated/C-clef inputs, and validation
  of every page before writing the output.

The JPG is a rotated/blurred simulation of the dense study, not a real phone
photo. Actual phone photos and independently prepared real-score references
remain necessary before claiming production accuracy.

## Direct PDF limitations

`direct_pdf.py` is an experimental CLI, not yet wired into the Android/API
response contract. It needs semantic SMuFL noteheads, straight five-line staves,
and explicit G/F clefs on every staff. Scans, outlined fonts, C/percussion clefs,
rotated pages, unusual notehead shapes, and uncertain staff assignments need a
recognition fallback. It does not create MusicXML, MIDI or playback timing.

Letters describe written A-G names; the original key signature, accidentals,
clefs and octave marks still apply. Agreement between passes is not accuracy.
No known-note benchmark yet certifies every note in the supplied Mrs Magic PDF.

The font is Bravura by Steinberg, licensed under SIL OFL 1.1. Generated benchmark
packages include that license. No user score or user score-derived fixture is
committed to this repository.

## Real-photo comparison with a supplied digital reference

```
python3 benchmarks/compare_photo_reference.py reference.pdf recognized.mxl --page 1
```

This diagnostic compares letter, written octave, measure index and staff against
the semantic PDF. It requires paired piano staves with connected measure barlines
and a single recognized piano part. Unsupported part grouping is reported rather
than silently pooled. The reference's measure/staff assignment is tested against
both original fixture oracles. Swapped measures/staves and duplicate extras have
regression tests. Accidentals, rhythm, onset, voice and tie correctness are not
included in this metric.

A real photographed page was tested against its supplied digital reference:
529 expected noteheads. Clean digital raster: 529 matching written pitches.
Current Fast photo preprocessing: 211 matching notes out of 529 expected (279
recognized). Current Best photo preprocessing: 369 matching notes out of 529
expected (504 recognized). Matches require the correct measure and staff. Best
still differed in every measure. OCR on/off did not change the Best result on
this page. Enlarging toward 20/24px staff spacing did not improve it: 20px caused
unsupported extra-part grouping; 24px matched 270 expected written pitches.
These are diagnostics from one supplied screen photograph, not general accuracy
figures. No preprocessing default is changed based on these unsuccessful trials.
No user image, score-derived fixture or private recognition output is committed.
