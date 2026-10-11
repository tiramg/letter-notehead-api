Ballade rendering reproduction, 2026-10-11

The first two pages were recognized independently with Audiveris 5.11.0,
350 DPI, OCR disabled, 128 MB heap and swap. The original page-1 export,
merged MusicXML and letter-notehead MusicXML all failed MuseScore Studio
4.7.5 strict PDF conversion with POSIX exit 40. MuseScore's internal log
reports incomplete measure 10, staff 2, found 21/8 versus expected 17/8.
Thus this failure precedes page merging and letter-notehead conversion.

The -f relaxed-import option produced a two-page PDF, visually inspected
on page 1. It exposes substantial recognition errors and is not a repair.
render_pdf retries converter exit 40 only when a warning list is provided;
success returns an explicit review warning and server confidence becomes low.
Other exit codes fail, unsuccessful retries fail, and strict callers retain
their existing behavior. The MusicXML is not rewritten by the fallback.

Four targeted fallback tests, six existing staff-validation tests, review
JavaScript checks and Python syntax checks passed. The actual render_pdf
fallback also produced a PDF and one warning with the recognized Ballade
score. The cloud reproduction uses TCP Xvfb due Unix-socket restrictions;
the production Docker xvfb-run command is unchanged. User Docker runtime
confirmation is still required. No recognition-accuracy improvement claimed.
