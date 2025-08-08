"""JSON preview helper."""

from concurrent.futures import ThreadPoolExecutor
from html import escape
from importlib.resources import files
from json import dumps, loads
from typing import Any

from gi.repository import GLib, Gtk
from gi.repository.Gtk import MessageDialog, MessageType
from gi.repository.WebKit2 import LoadEvent, WebView
from jsonpath_ng.exceptions import JsonPathParserError
from jsonpath_ng.ext import parse

_EXECUTOR = ThreadPoolExecutor(max_workers=2)


class JSONPreview:
    """Manage JSON parsing, filtering, and rendering.

    Provides a collapsible and highlighted HTML preview.
    """

    def __init__(self, collapse_lines: int = 100) -> None:
        self.collapse_lines = collapse_lines
        self._css: str | None = None
        self._js: str | None = None
        self._json_data: Any = None
        self.webview: WebView | None = None
        self._win: Gtk.Window | None = None
        self._tab_width = 2
        self.filter_callback = None

    def to_html(self, text: str, tab_width: int = 2) -> str:
        """Parse JSON text and return the initial full HTML representation.

        The parsed data is stored for later filtering.
        """
        self._json_data = loads(text)
        self._tab_width = tab_width
        return self._generate_html(self._json_data)

    def _generate_html(self, data: Any) -> str:
        """Generate the full HTML document for the given JSON data."""
        pretty = dumps(
            data,
            indent=self._tab_width,
            sort_keys=True,
            ensure_ascii=False,
        )
        line_count = pretty.count("\n") + 1
        collapse = line_count > self.collapse_lines
        body = self._value_to_html(data, collapse, 0, "")
        css, js = self._resources()
        return (
            "<html><head><meta charset='utf-8'>"
            f"<style>{css}</style>"
            "</head><body><pre>"
            + body
            + "</pre>"
            f"<script>{js}</script>"
            "</body></html>"
        )

    def _resources(self) -> tuple[str, str]:
        if self._css is None or self._js is None:
            data_dir = files("formiko.data")
            self._css = (data_dir / "jsonfold.css").read_text(encoding="utf-8")
            self._js = (data_dir / "jsonfold.js").read_text(encoding="utf-8")
        return self._css, self._js

    def _value_to_html(
        self,
        value: Any,
        collapse: bool,
        level: int,
        path: str,
    ) -> str:
        # Generate string path that matches jsonpath-ng's str(full_path)
        if isinstance(value, dict):
            cls = ["jblock"]
            if collapse and level > 0:
                cls.append("collapsed")
            items = []
            for _key, val in value.items():
                # jsonpath-ng uses dot for fields
                new_path = f"{path}.{_key}" if path else _key
                child_html = self._value_to_html(
                    val, collapse, level + 1, new_path,
                )
                items.append(
                    '<div class="jitem">'
                    '<span class="jkey">'
                    f'"{escape(str(_key))}"'
                    "</span>: "
                    f"{child_html}"
                    "</div>",
                )
            children = "".join(items)
            return (
                f'<div class="{ " ".join(cls) }" data-jpath="{path}">'
                "<span class='jtoggler'></span>{"
                f"<div class='children'>{children}</div>}}</div>"
            )
        if isinstance(value, list):
            cls = ["jblock"]
            if collapse and level > 0:
                cls.append("collapsed")
            items = []
            for i, v in enumerate(value):
                # jsonpath-ng uses brackets for lists,
                # and a dot separator if not at root
                new_path = f"{path}.[{i}]" if path else f"[{i}]"
                child_html = self._value_to_html(
                    v, collapse, level + 1, new_path,
                )
                items.append(
                    '<div class="jitem">'
                    f"{child_html}"
                    "</div>",
                )
            children = "".join(items)
            return (
                f'<div class="{ " ".join(cls) }" data-jpath="{path}">'
                '<span class="jtoggler"></span>['
                f'<div class="children">{children}</div>]</div>'
            )

        # For primitive values, wrap them in a span with the path
        if isinstance(value, str):
            esc = escape(value)
            return (
                f'<span class="jstr" data-jpath="{path}">"{esc}"</span>'
            )
        if value is True or value is False:
            val_str = str(value).lower()
            return f'<span class="jbool" data-jpath="{path}">{val_str}</span>'
        if value is None:
            return f'<span class="jnull" data-jpath="{path}">null</span>'
        return f'<span class="jnum" data-jpath="{path}">{value}</span>'

    def apply_path_filter(self, expression: str | None) -> None:  # noqa: C901
        """Filter JSON by JSONPath and update the preview.

        A callback is fired with ``(expression, match_count)`` when done.

        ``expression`` may be ``None`` or empty to clear any existing filter
        and fully expand the JSON tree.
        """
        def _task():  # noqa: C901
            def collect_paths(val, path=""):
                paths = {path}
                if isinstance(val, dict):
                    for k, v in val.items():
                        new_path = f"{path}.{k}" if path else k
                        paths |= collect_paths(v, new_path)
                elif isinstance(val, list):
                    for i, v in enumerate(val):
                        new_path = f"{path}.[{i}]" if path else f"[{i}]"
                        paths |= collect_paths(v, new_path)
                return paths

            if not expression or not expression.strip():
                expands = collect_paths(self._json_data)
                return self._json_data, [], expands, ""

            try:
                expr = parse(expression)
                matches = expr.find(self._json_data)
            except JsonPathParserError:
                raise
            except Exception as e:
                msg = "Filter error"
                raise JsonPathParserError(msg) from e
            else:
                highlights = []
                expands = {""}
                for m in matches:
                    current = m
                    while current:
                        path_str = str(current.full_path)
                        if path_str == "$":
                            path_str = ""
                        expands.add(path_str)
                        current = current.context
                    path_str = str(m.full_path)
                    highlights.append("" if path_str == "$" else path_str)
                return self._json_data, highlights, expands, expression

        def _done(fut):
            try:
                data, highlights, expands, expr = fut.result()
            except JsonPathParserError as e:
                GLib.idle_add(self._show_error_dialog, str(e))
                data, highlights, expands, expr = self._json_data, [], {""}, ""

            GLib.idle_add(
                self._render,
                data,
                highlights,
                expands,
                expr,
                len(highlights),
            )
        _EXECUTOR.submit(_task).add_done_callback(_done)

    def _show_error_dialog(self, message: str) -> bool:
        dialog = MessageDialog(
            transient_for=self._win,
            modal=True,
            message_type=MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text="Invalid JSONPath Expression",
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()
        return False

    def _render(
        self,
        data,
        highlights: list[str],
        expands: set[str],
        expr: str,
        count: int,
    ) -> bool:
        """Generate and load HTML, then run JS to fold and highlight."""
        html = self._generate_html(data)

        if not self.webview:
            return False

        if hasattr(self.webview, "highlight_handler_id"):
            self.webview.disconnect(self.webview.highlight_handler_id)

        def on_load_finished(webview, load_event):
            if load_event == LoadEvent.FINISHED:
                if expr:
                    js = (
                        f"const highlights = {highlights!r};\n"
                        f"const expands = {list(expands)!r};\n"
                        """
document.querySelectorAll('.jblock').forEach(
  el => el.classList.add('collapsed')
);
expands.forEach(p => {
  const el = document.querySelector(`[data-jpath="${p}"]`);
  if (el) el.classList.remove('collapsed');
});
highlights.forEach(p => {
  const el = document.querySelector(`[data-jpath="${p}"]`);
  if (el) el.classList.add('jhighlight');
});
"""
                    )
                    webview.run_javascript(js)
                else:
                    js = (
                        "document.querySelectorAll('.jblock').forEach("
                        "el => el.classList.remove('collapsed'));"
                    )
                    webview.run_javascript(js)
                if hasattr(webview, "highlight_handler_id"):
                    webview.disconnect(webview.highlight_handler_id)
                    del webview.highlight_handler_id

        handler_id = self.webview.connect("load-changed", on_load_finished)
        self.webview.highlight_handler_id = handler_id
        self.webview.load_html(html, "file:///")

        if self.filter_callback:
            self.filter_callback(expr, count)

        return False
