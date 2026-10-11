# Ballade recognition investigation — 2026-10-11

The user's Docker test confirms the relaxed-import rendering fallback works:
two pages, 772 recognized notes, 43 merged measures, approximately 105 seconds.
The review is incomplete. The 35 flagged measures are review candidates, not
35 verified errors or a basis for an accuracy percentage.

Recognition defects precede merging, letter conversion, and MuseScore import.
The original first-page Audiveris export contains 340 pitched notes and no
MusicXML time-modification elements, although explicit triplets are visible
in the original. The second-page export contains 432 pitched notes and four
time-modification elements. This is not a complete manual transcription.

## Targeted first-page experiments

All fresh runs use Audiveris 5.11.0, a 128 MB Java heap, SerialGC, swap,
the same separated original PDF page, and otherwise unchanged defaults.
OCR language data was available for the OCR-enabled experiment.

| Setting | Pitched notes | Tuplet timing elements | Measure 8 treble matches / missing / extra |
| --- | ---: | ---: | --- |
| Existing 350 DPI, OCR off | 340 | 0 | 3 / 3 / 2 |
| OCR on, 350 DPI | 340 | 0 | 3 / 3 / 2 |
| 300 DPI, OCR off | 337 | 0 | 3 / 3 / 2 |
| Implicit tuplets enabled | 336 | 13 | 5 / 1 / 2 |
| Fingering recognition enabled | 340 | 0 | 3 / 3 / 2 |
| Adaptive mean coefficient 0.72 | 332 | 0 | 3 / 3 / 2 |

The measure-8 reference is manually read from the original first Moderato
measure: Bb4, D4, Eb4, F#4, Bb4, A4. Counts compare pitch/octave/alteration
multisets on the treble staff, excluding rests. They do not test ordering,
duration, ties, voice assignment, or the remainder of the score, and are
not an overall accuracy measurement. Original and trial note totals alone
do not establish whether either transcription is better.

OCR-on produced identical note elements to the original first-page export.
The 300 DPI and threshold trials did not repair the checked missing-note
passage. Fingering recognition did not repair it either.

Implicit tuplets recovered two pitches in measure 8, but still retained
wrong durations and extra notes. It also inserted 13 tuplet timing elements
in measure 19, a 6/4 passage without those tuplets in the original.
Thus fewer missing pitches in this subset is insufficient to accept it.
The original and implicit trials both flag 20 first-page measures in the
current staff-duration checker.

No candidate passed the checked pitch and rhythm criteria. No production
recognition setting or cache version was changed, and no new installation
is required. Do not describe the rendering fallback as a correction.

## Remaining work

The staff-duration checker can flag intentional empty staff intervals when
voices cross between staves, especially in the introduction. Review warnings
must continue to be distinguished from verified missing notes.

Further work needs to address note/stem/beam grouping and explicit tuplet
classification at the recognition stage. Generic OCR or resolution changes,
and forcing measures to fit by inserting rests or guessing tuplets, did not
provide a reliable repair in the experiments above.

Upstream configuration inspected at the version used:
https://github.com/Audiveris/audiveris/blob/5.11.0/app/src/main/java/org/audiveris/omr/sheet/ProcessingSwitches.java
Both fingerings and implicitTuplets default to false. Their trials above
changed each setting independently; explicit tuplets and implicit inference
are distinct mechanisms.
