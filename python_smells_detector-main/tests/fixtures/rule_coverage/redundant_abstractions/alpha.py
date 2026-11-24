"""First half of a pair of modules with the same public surface."""


def normalize_text(value):
    return " ".join(value.split())


def validate_input(value):
    return bool(value)


def summarize_rows(rows):
    return {"rows": len(rows)}


def render_output(payload):
    return repr(payload)
