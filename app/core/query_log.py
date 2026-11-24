"""Cleaning rules for the log of chat messages that matched no guide.

Pure functions, no database. The log keeps only the TEXT of a message that
found no guide, so that every miss can become a keyword or a new guide. It
never stores who wrote it, and it refuses text that looks like personal data.
"""
from __future__ import annotations

import re

MAX_QUERY_LENGTH = 200
MIN_QUERY_LENGTH = 3

# 7 or more digits in a row, allowing up to two spaces, dots, dashes or brackets
# between them: phone numbers and similar. A budget such as 60000 (5 digits) is
# fine. This errs on the side of privacy: a message that is mostly spec numbers
# (for example "ddr4 3200 16gb") may be skipped too, which only costs one log entry.
_LONG_NUMBER = re.compile(r"\d(?:[\s().-]{0,2}\d){6,}")


def clean_query(raw: str) -> tuple[str, str] | None:
    """Return (text, normalized) to store, or None if the message must not be logged.

    text        what the person typed, with spaces tidied and cut to 200 characters
    normalized  lower-case words only, used to group repeats of the same message
                ("PC wont turn on!!" and "pc wont turn on" are one entry)
    """
    text = re.sub(r"\s+", " ", raw or "").strip()
    if len(text) < MIN_QUERY_LENGTH:
        return None
    if "@" in text or _LONG_NUMBER.search(text):
        return None  # looks like an email address or phone number: do not keep it
    text = text[:MAX_QUERY_LENGTH].rstrip()
    normalized = re.sub(r"[\W_]+", " ", text.lower()).strip()
    if not any(ch.isalpha() for ch in normalized):
        return None  # only digits or symbols
    return text, normalized