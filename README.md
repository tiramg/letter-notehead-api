# Letter Notehead Recognition Service

Cloud backend for the Letter Notehead Android app. It accepts a PDF or score image, runs Audiveris OMR, creates three MusicXML learning levels, and renders print-ready PDFs with MuseScore.

## API

- `GET /health` — verifies that Audiveris and MuseScore are available.
- `POST /api/recognize` — multipart form upload with field name `score`.
- Optional bearer authentication uses `LETTER_NOTEHEAD_API_TOKEN`.

The response includes score metadata and a `learningModes` object containing `all`, `guide`, and `none` variants. Each variant contains a label count and base64-encoded MXL and PDF files.

Uploads are processed inside a temporary directory and deleted immediately after the response is assembled. No score files are retained by the service.

## Render deployment

The included `render.yaml` creates a Docker web service with a health check and generated API token. Use at least the Starter instance because optical music recognition and engraving are CPU- and memory-intensive.
