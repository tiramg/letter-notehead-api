Photo recognition investigation, 2026-10-10

The supplied Alone in the Ring phone photo reproduces the production Best
Accuracy result: 117 pitched notes over 15 measures. The exported score omits
the lower-staff bass-clef change at the end of measure 4 and loses substantial
upper-staff content in measures 4, 8, and 11.

Changing lighting, image size, music font templates, thresholding, or staff
geometry produced 56–127 recognized notes, but no variant reliably preserved
all inspected passages. Note counts alone cannot identify the best result.
No experimental recognition settings were adopted in this change.

The prior part-wide duration check flagged measure 8 only. The per-staff check
flags measures 2, 4, 6, 8, 9, 10, 11, and 12 on the same exported score.
These are review flags, not a count of incorrect notes. Cross-staff notation
may legitimately trigger a flag, and complete but incorrect pitches can pass.

Reports now distinguish complete manual review from incomplete annotation.
The percentage remains a rough marked-note-error estimate, not ground-truth
OMR accuracy. A rigorous benchmark still needs a reference MusicXML score
and note-event alignment that accounts for insertions, deletions, pitch,
duration, and clef state.
