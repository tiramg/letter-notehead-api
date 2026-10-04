"""Low-memory sheet-music photo cleanup for Audiveris.

This deliberately uses Pillow instead of keeping OpenCV resident beside the JVM.
The Render service only has 512 MB, so preprocessing must release almost all of
its working memory before optical music recognition starts.
"""
from io import BytesIO
from pathlib import Path
import json

from PIL import Image, ImageChops, ImageFilter, ImageOps


PHOTO_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}


def _row_darkness(image):
    """Return dark-pixel coverage for each row of a small grayscale image."""
    width, height = image.size
    pixels = image.tobytes()
    left = max(0, width // 20)
    right = min(width, width - left)
    usable = max(1, right - left)
    values = []
    for y in range(height):
        row = pixels[y * width + left:y * width + right]
        values.append(sum(value < 145 for value in row) / usable)
    return values


def _line_centers(values):
    """Find long, dark horizontal strokes and merge their thickness."""
    ordered = sorted(values)
    baseline = ordered[int(len(ordered) * 0.90)] if ordered else 0
    threshold = max(0.18, baseline * 1.35)
    centers = []
    start = None
    for index, value in enumerate(values + [0]):
        if value >= threshold and start is None:
            start = index
        elif value < threshold and start is not None:
            if index - start <= 5:
                centers.append((start + index - 1) / 2)
            start = None
    return centers


def _staff_metrics(image):
    scale = min(1.0, 1200 / max(1, image.width))
    sample = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.BILINEAR)
    centers = _line_centers(_row_darkness(sample))
    differences = [b - a for a, b in zip(centers, centers[1:]) if 3 <= b - a <= 24]
    if not differences:
        return {"staffSpacing": 0.0, "staffLineCount": len(centers), "sampleScale": scale}
    differences.sort()
    spacing = differences[len(differences) // 2] / scale
    return {"staffSpacing": round(spacing, 2), "staffLineCount": len(centers), "sampleScale": scale}


def _deskew(image):
    """Correct small handheld-camera rotation using staff-line peak strength."""
    sample = image.copy()
    sample.thumbnail((1000, 1400), Image.Resampling.BILINEAR)
    best_angle = 0.0
    best_score = -1.0
    for step in range(-6, 7):
        angle = step * 0.5
        candidate = sample.rotate(angle, Image.Resampling.BICUBIC, expand=False, fillcolor=255)
        rows = _row_darkness(candidate)
        strongest = sorted(rows, reverse=True)[:max(10, len(rows) // 30)]
        score = sum(value * value for value in strongest)
        if score > best_score:
            best_angle, best_score = angle, score
    if abs(best_angle) < 0.24:
        return image, 0.0
    return image.rotate(best_angle, Image.Resampling.BICUBIC, expand=True, fillcolor=255), best_angle


def _normalize_lighting(image):
    """Remove broad phone-camera shadows while preserving fine music symbols."""
    radius = max(18, min(image.size) // 35)
    background = image.filter(ImageFilter.GaussianBlur(radius=radius))
    # image + (255 - background) - 17 == image - background + 238
    # This is a low-memory approximation of flat-field division that works on
    # the older Pillow packaged by Ubuntu as well as current releases.
    normalized = ImageChops.add(image, ImageOps.invert(background), scale=1, offset=-17)
    return ImageOps.autocontrast(normalized, cutoff=(0.4, 0.4))


def prepare_photo(source_bytes, suffix, directory, quality):
    """Create a 300-DPI, staff-sized grayscale input and return its metrics."""
    if suffix not in PHOTO_SUFFIXES:
        return source_bytes, suffix, {"kind": "document", "confidence": "high", "warnings": []}

    with Image.open(BytesIO(source_bytes)) as opened:
        image = ImageOps.exif_transpose(opened).convert("L")
    original_size = image.size
    image, angle = _deskew(image)
    before = _staff_metrics(image)
    image = _normalize_lighting(image)

    target_spacing = 13 if quality == "fast" else 16
    measured = before["staffSpacing"]
    scale = target_spacing / measured if measured else 1.0
    scale = max(1.0, min(scale, 2.8 if quality == "best" else 2.2))
    max_dimension = 5000 if quality == "best" else 4200
    if max(image.size) * scale > max_dimension:
        scale = max_dimension / max(image.size)
    if scale > 1.03:
        image = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)

    after = _staff_metrics(image)
    warnings = []
    confidence = "medium"
    if before["staffLineCount"] < 10 or before["staffSpacing"] < 4.5:
        confidence = "low"
        warnings.append("Staff lines are too small or unclear for reliable recognition.")
    if min(original_size) < 1000:
        confidence = "low"
        warnings.append("The original photo has limited detail; move closer for the next photo.")
    if before["staffSpacing"] and before["staffSpacing"] < 8:
        warnings.append("Fine note details were enlarged before recognition; verify chords and ledger-line notes.")
    warnings.append("Photo recognition can misread dense chords, ledger lines, ties, and curved pages. Compare the result with the original.")

    target = Path(directory) / f"prepared-{quality}.png"
    image.save(target, "PNG", optimize=True, dpi=(300, 300))
    metrics = {
        "kind": "photo",
        "confidence": confidence,
        "warnings": warnings,
        "originalWidth": original_size[0],
        "originalHeight": original_size[1],
        "preparedWidth": image.width,
        "preparedHeight": image.height,
        "deskewDegrees": round(angle, 2),
        "staffSpacingBefore": before["staffSpacing"],
        "staffSpacingAfter": after["staffSpacing"],
        "staffLineCount": before["staffLineCount"],
        "scaleApplied": round(scale, 2),
    }
    return target.read_bytes(), ".png", metrics


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("target")
    parser.add_argument("--quality", choices=("fast", "best"), default="best")
    args = parser.parse_args()
    source = Path(args.source)
    prepared, suffix, metrics = prepare_photo(source.read_bytes(), source.suffix.lower(), Path(args.target).parent, args.quality)
    Path(args.target).write_bytes(prepared)
    print(json.dumps(metrics, indent=2))
