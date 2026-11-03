"""Boundary to the external review source (Google Maps reviews).

The ingestion service hands a verified target to this adapter only after the
authentication, ownership, and source checks pass. Fetching reviews from the
source is implemented in S1-020; until then the adapter reports that ingestion
is unavailable instead of pretending to succeed or substituting sample data.
"""

from ..errors import IngestionUnavailable


class UnconfiguredReviewSource:
    def submit(self, *, target_id, source_url):
        raise IngestionUnavailable()
