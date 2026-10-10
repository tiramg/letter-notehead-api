Photo recognition investigation, 2026-10-10

The supplied Alone in the Ring phone photo reproduces the production Best
Accuracy result: 117 pitched notes over 15 measures. The exported score omits
the lower-staff bass-clef change at the end of measure 4 and loses substantial
upper-staff content in measures 4, 8, and 11.

Changing lighting, image size, music font templates, thresholding, or staff
geometry produced 56–127 recognized notes, but no variant reliably preserved
all inspected passages. Note counts alone cannot identify the best result.
The initial diagnostics change adopted no experimental settings. Subsequent
Best Accuracy testing of a narrowly adjusted adaptive threshold is described
below.

The prior part-wide duration check flagged measure 8 only. The per-staff check
flags measures 2, 4, 6, 8, 9, 10, 11, and 12 on the same exported score.
These are review flags, not a count of incorrect notes. Cross-staff notation
may legitimately trigger a flag, and complete but incorrect pitches can pass.

Reports now distinguish complete manual review from incomplete annotation.
The percentage remains a rough marked-note-error estimate, not ground-truth
OMR accuracy. A rigorous benchmark still needs a reference MusicXML score
and note-event alignment that accounts for insertions, deletions, pitch,
duration, and clef state.

Experimental Best Accuracy photo profile

A mean coefficient of 0.72 (instead of the engine default 0.7) reproduced
128 pitched notes under the service's 128 MB Java heap and swap settings.
It recovered the lower-staff bass-clef change at the end of measure 4 and the
two upper-staff whole notes in measure 8.

A manually checked subset of 42 letter/octave entries across selected staff
passages was compared as multisets. The default matched 19 entries, left 23
reference entries unmatched, and produced 10 unmatched recognized entries.
The experimental profile matched 37 entries, left 5 unmatched reference
entries, and produced 1 unmatched recognized entry in that same subset.

This is development evidence on one image, not a held-out accuracy benchmark.
The subset ignores accidentals, duration, timing and order; it does not cover
all measures. The new profile still flags eight suspect measures and introduces
extra notes in measure 1 while losing some notes elsewhere. No full-score
accuracy percentage is claimed. The change applies only to Best Accuracy
photos; PDF and Fast recognition settings remain the same.
