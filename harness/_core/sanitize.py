from __future__ import annotations
import re

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TEMPLATE = re.compile(r"\{[^}]{1,40}\}")


def strip_control_chars(s: str) -> str:
    return _CTRL.sub("", s)


def assert_no_template_chars(s: str, context: str = "") -> None:
    m = _TEMPLATE.search(s)
    if m:
        loc = f" in {context}" if context else ""
        raise ValueError(
            f"Unrendered template placeholder{loc}: {s[:80]!r} (found {m.group()!r})"
        )


def scrub_pii_in_state(obj: object) -> object:
    """Wrap untrusted Airtable string values to prevent log injection.

    Idempotent — already-wrapped dicts pass through unchanged.
    Non-string values pass through unchanged.
    """
    if isinstance(obj, dict) and obj.get("_untrusted"):
        return obj
    if isinstance(obj, str):
        return {
            "_untrusted": True,
            "_source": "airtable",
            "value": strip_control_chars(obj),
        }
    return obj
