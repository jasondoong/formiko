"""HTML generator for JSON preview with collapsible folding."""

from __future__ import annotations

from html import escape
from json import dumps, loads
from typing import Any


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
        collapse = line_count > self.collapse_lines
        body = self._value_to_html(obj, collapse, 0)
        return (
            "<html><head><meta charset='utf-8'>"
            "<link rel='stylesheet' "
            "href='resource:///org/formiko/jsonfold.css'>"
            "</head><body><pre>"
            + body
            + "</pre>"
            + "<script src='resource:///org/formiko/jsonfold.js'></script>"
            "</body></html>"
        )

    def _value_to_html(self, value: Any, collapse: bool, level: int) -> str:
        if isinstance(value, dict):
            cls = ["jblock"]
            if collapse and level > 0:
                cls.append("collapsed")
            items = []
            for _key, val in value.items():
                item = (
                    '<div class="jitem"><span class="jkey">'
                    f'"{escape(str(_key))}"'
                    '</span>: '
                    f"{self._value_to_html(val, collapse, level + 1)}</div>"
                )
                items.append(item)
            children = "".join(items)
            return (
                f"<div class='{ ' '.join(cls) }'>"
                f"<span class='jtoggler'></span>{{"
                f"<div class='children'>{children}</div>}}</div>"
            )
        if isinstance(value, list):
            cls = ["jblock"]
            if collapse and level > 0:
                cls.append("collapsed")
            items = [
                (
                    "<div class='jitem'>"
                    f"{self._value_to_html(v, collapse, level + 1)}</div>"
                )
                for v in value
            ]
            children = "".join(items)
            return (
                f"<div class='{ ' '.join(cls) }'>"
                '<span class="jtoggler"></span>['
                f'<div class="children">{children}</div>]</div>'
            )
        if isinstance(value, str):
            return f"<span class='jstr'>\"{escape(value)}\"</span>"
        if value is True or value is False:
            return f"<span class='jbool'>{str(value).lower()}</span>"
        if value is None:
            return "<span class='jnull'>null</span>"
        return f"<span class='jnum'>{value}</span>"
