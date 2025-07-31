"""Previewer classes for different content types."""

from json import dumps, loads

class HtmlPreview:
    """Dummy html preview class that returns the original text."""
    def __call__(self, text, **_kwargs):
        """Return the original text."""
        return text, "text/html"

class JSONPreview:
    """JSON preview class that pretty-prints JSON content."""
    def __call__(self, text, tab_width=4, **_kwargs):
        """Pretty-print JSON text."""
        try:
            json_obj = loads(text)
            pretty_json = dumps(
                json_obj,
                sort_keys=True,
                ensure_ascii=False,
                indent=tab_width,
                separators=(",", ": "),
            )
            return pretty_json, "application/json"
        except ValueError as e:
            error_html = f"<h1>JSON Error!</h1><p style='color:red; text-width:weight;'>{e}</p>"
            return error_html, "text/html"
