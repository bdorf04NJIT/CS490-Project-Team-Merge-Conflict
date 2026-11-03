"""Source-specific parsing for *supplied* Google Maps review CSV exports.

The file is user-supplied evidence, not a claim that we fetched it from Google.
Normalization and persistence happen in their own application layers.
"""

import csv
import io
import re
from dataclasses import dataclass

MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_CSV_ROWS = 5000


class SourceFormatError(ValueError):
    """An uploaded document cannot be interpreted as a review CSV."""


@dataclass(frozen=True)
class RawReviewBatch:
    rows: list[dict]
    source_kind: str


def _column_name(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower().strip()).strip("_")


def parse_review_csv(data: bytes) -> RawReviewBatch:
    """Parse a bounded UTF-8 CSV; leave individual review validation for S1-021."""
    if not data or len(data) > MAX_CSV_BYTES:
        raise SourceFormatError("Select a nonempty UTF-8 CSV smaller than 2 MB.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise SourceFormatError("The CSV must use UTF-8 encoding.") from None
    if "\x00" in text:
        raise SourceFormatError("The supplied file is not a valid CSV.")
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        if not reader.fieldnames or any(not isinstance(x, str) for x in reader.fieldnames):
            raise SourceFormatError("The CSV needs column headers.")
        keys = [_column_name(x) for x in reader.fieldnames]
        if len(keys) != len(set(keys)) or not all(keys):
            raise SourceFormatError("The CSV contains duplicate or empty column names.")
        if not set(keys).intersection({"review_text", "text", "review", "snippet", "content"}):
            raise SourceFormatError("Include a review_text column.")
        if not set(keys).intersection({"rating", "stars", "review_rating"}):
            raise SourceFormatError("Include a rating column.")
        rows = []
        for row in reader:
            if len(rows) >= MAX_CSV_ROWS:
                raise SourceFormatError("Import at most 5,000 review rows at a time.")
            if None in row:
                raise SourceFormatError("The CSV includes a row with more values than columns.")
            rows.append({keys[i]: row.get(header) for i, header in enumerate(reader.fieldnames)})
    except csv.Error:
        raise SourceFormatError("The CSV contains malformed quoting or rows.") from None
    return RawReviewBatch(rows=rows, source_kind="google_maps_csv")
