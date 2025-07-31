"""HTML generator for JSON preview using ``renderjson`` library."""

from __future__ import annotations

from json import dumps, loads


class JsonPreview:
    """Convert JSON data to collapsible HTML."""

    def __init__(self, collapse_lines: int = 50) -> None:
        self.collapse_lines = collapse_lines

    def to_html(self, text: str, tab_width: int = 2) -> str:
        """Return HTML representation of JSON ``text``."""
        obj = loads(text)
        pretty = dumps(
            obj,
            indent=tab_width,
            sort_keys=True,
            ensure_ascii=False,
        )
        line_count = pretty.count("\n") + 1
        show_level = 1 if line_count > self.collapse_lines else 99
        return (
            "<html><head><meta charset='utf-8'>"
            "<script src='https://cdn.jsdelivr.net/npm/renderjson@1.1.1/"
            "renderjson.js'></script>"
            "<style>body{font-family:monospace}</style>"
            "</head><body>"
            f"<script>renderjson.set_show_to_level({show_level});"
            f"document.body.appendChild(renderjson({pretty}));</script>"
            "</body></html>"
        )
