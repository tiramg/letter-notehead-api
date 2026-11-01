# Letter Notehead Recognition Service

Cloud backend for the Letter Notehead Android app. It accepts a PDF or score image, runs Audiveris OMR, creates three MusicXML learning levels, and renders print-ready PDFs with MuseScore.

## API

- `GET /health` — verifies that Audiveris and MuseScore are available.
- `POST /api/recognize` — multipart form upload with field name `score`.
- Optional bearer authentication uses `LETTER_NOTEHEAD_API_TOKEN`.

The response includes score metadata and a `learningModes` object containing `all`, `guide`, and `none` variants. Each variant contains a label count and base64-encoded MXL and PDF files.

Uploads are processed inside a temporary directory and deleted immediately after the response is assembled. No score files are retained by the service.

## Optional dual-pass cross-check (PDF uploads)

Set `LETTER_NOTEHEAD_CROSSCHECK=1` to run a second, independent recognition
pass over a 300-DPI raster rendering of each PDF page and compare it with the
primary vector-PDF pass measure by measure (`cross_check.py`). The primary
result is unchanged; disagreements are reported in `validation.crossCheck`
and as specific entries in `issues` naming the measure and the pitches only
one pass found, so the user verifies a handful of measures instead of the
whole score. It roughly doubles recognition time, so it is off by default on
the memory-constrained cloud instance and best enabled for local/desktop
runs or a larger instance.

## Render deployment

The included `render.yaml` creates a Docker web service with a health check and generated API token. Use at least the Starter instance because optical music recognition and engraving are CPU- and memory-intensive.
