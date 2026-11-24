"""Second half of a pair of modules with the same public surface.

The four functions below mirror ``alpha.py`` name for name, which is exactly
what the architectural detector reports as a redundant abstraction once the
Jaccard similarity of the two name sets reaches the configured threshold.
"""


def normalize_text(value):
    cleaned = value.strip()
    return cleaned.lower()


def validate_input(value):
    if value is None:
        return False
    return len(str(value)) > 0


def summarize_rows(rows):
    total = 0
    for row in rows:
        total += len(row)
    return {"rows": len(rows), "cells": total}


def render_output(payload):
    parts = []
    for key in sorted(payload):
        parts.append("%s=%r" % (key, payload[key]))
    return ", ".join(parts)
