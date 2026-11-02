# Letter Notehead Recognition Service

Cloud backend for the Letter Notehead Android app. It accepts a PDF or score image, runs Audiveris OMR, creates three MusicXML learning levels, and renders print-ready PDFs with MuseScore.

## API

- `GET /health` — verifies that Audiveris and MuseScore are available.
- `POST /api/recognize` — multipart form upload with field name `score`.
- Optional bearer authentication uses `LETTER_NOTEHEAD_API_TOKEN`.

The response includes score metadata and a `learningModes` object containing `all`, `guide`, and `none` variants. Each variant contains a label count and base64-encoded MXL and PDF files.

Uploads are processed inside a temporary directory and deleted immediately after the response is assembled. No score files are retained by the service.

## Optional dual-pass cross-check

Set `LETTER_NOTEHEAD_CROSSCHECK=1` to run a second, independent recognition
pass and compare it with the primary result measure by measure
(`cross_check.py`). The primary result is unchanged; disagreements are
reported in `validation.crossCheck` and as specific entries in `issues`
naming the measure and the pitches only one pass found. The comparison
also checks note order, duration, rests, staff/voice placement, grace notes,
and ties. Both passes can make the same mistake, so agreement is not an
accuracy measurement and all pages still need review.

- For PDF uploads, the second pass recognizes a 300-DPI raster rendering
  of each page instead of the vector document.
- For photo uploads, the second pass runs the other preprocessing profile
  (`fast` targets 13px staff spacing, `best` targets 16px). On a real
  phone photo the two profiles returned 116 vs 117 notes but agreed on
  only 4 of 15 measures, so per-measure flags matter more than totals.

It roughly doubles recognition time, so it is off by default on the
memory-constrained cloud instance and best enabled for local/desktop
runs or a larger instance.

## Render deployment

The included `render.yaml` creates a Docker web service with a health check and generated API token. Use at least the Starter instance because optical music recognition and engraving are CPU- and memory-intensive.

## Automated checks

Run `python3 -m unittest discover -s tests -v` `node --check review.js`, and `node tests/test_review.cjs`.
The tests use small MusicXML fixtures and do not require the recognition engines.
Full image-to-PDF testing additionally requires Audiveris, MuseScore, Xvfb,
and Poppler (provided by the Docker image).

The Test Lab reports a marked-error estimate only after every page has been
reviewed. That estimate counts manually marked issues against recognized
notes; it is not a measured pitch-accuracy benchmark.
