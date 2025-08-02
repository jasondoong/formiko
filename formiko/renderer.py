"""Webkit based renderer."""

from concurrent.futures import ThreadPoolExecutor
from html import escape
from io import StringIO
from json import dumps, loads
from os.path import exists, splitext
from traceback import format_exc
from typing import Any

from docutils import DataError
from docutils.core import publish_string
from docutils.parsers.rst import Parser as RstParser
from docutils.writers.html4css1 import Writer as Writer4css1
from docutils.writers.pep_html import Writer as WriterPep
from docutils.writers.s5_html import Writer as WriterS5
from gi.repository import GLib, Gtk
from gi.repository.GLib import (
    MAXUINT,
    Bytes,
    Error,
    LogLevelFlags,
    get_home_dir,
    idle_add,
    log_default_handler,
)
from gi.repository.Gtk import (
    Align,
    Label,
    MessageDialog,
    MessageType,
    Overlay,
    Settings,
    StateFlags,
    TextView,
    main_iteration,
    show_uri_on_window,
)
from gi.repository.WebKit2 import (
    FindOptions,
    LoadEvent,
    PrintOperation,
    WebView,
)
from importlib.resources import files
from jsonpath_ng.exceptions import JsonPathParserError
from jsonpath_ng.ext import parse
from jsonpath_ng.jsonpath import Index

from formiko.dialogs import FileNotFoundDialog
from formiko.sourceview import LANGS

try:
    from docutils_tinyhtml import Writer as TinyWriter
except ImportError:
    TinyWriter = None

try:
    from docutils_html5 import Writer as Html5Writer
except ImportError:
    Html5Writer = None

try:
    from m2r import convert as m2r_convert

    class Mark2Resturctured(RstParser):
        """Converting from MarkDown to reStructuredText before parse."""

        def parse(self, inputstring, document):
            """Create RST from MD first and call than parse."""
            return super().parse(m2r_convert(inputstring), document)

except ImportError:
    Mark2Resturctured = None


_EXECUTOR = ThreadPoolExecutor(max_workers=2)


class JsonPreview:
    """
    Manages parsing, filtering, and rendering of JSON data into a
    collapsible and highlighted HTML preview.
    """

    def __init__(self, collapse_lines: int = 50) -> None:
        self.collapse_lines = collapse_lines
        self._css: str | None = None
        self._js: str | None = None
        self._json_data: Any = None
        self.webview: WebView | None = None
        self._win: Gtk.Window | None = None
        self._tab_width = 2
        self.filter_callback = None

    def to_html(self, text: str, tab_width: int = 2) -> str:
        """
        Parses JSON text and returns the initial full HTML representation.
        The parsed data is stored for later filtering.
        """
        self._json_data = loads(text)
        self._tab_width = tab_width
        return self._generate_html(self._json_data)

    def _generate_html(self, data: Any) -> str:
        """Generates the full HTML document for the given JSON data."""
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
                items.append(
                    '<div class="jitem">'
                    '<span class="jkey">'
                    f'"{escape(str(_key))}"'
                    "</span>: "
                    f"{self._value_to_html(val, collapse, level + 1, new_path)}"
                    "</div>"
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
                # jsonpath-ng uses brackets for lists, and a dot separator if not at root
                new_path = f"{path}.[{i}]" if path else f"[{i}]"
                items.append(
                    '<div class="jitem">'
                    f"{self._value_to_html(v, collapse, level + 1, new_path)}"
                    "</div>"
                )
            children = "".join(items)
            return (
                f'<div class="{ " ".join(cls) }" data-jpath="{path}">'
                '<span class="jtoggler"></span>['
                f'<div class="children">{children}</div>]</div>'
            )

        # For primitive values, wrap them in a span with the path
        if isinstance(value, str):
            return f'<span class="jstr" data-jpath="{path}">"{escape(value)}"</span>'
        if value is True or value is False:
            val_str = str(value).lower()
            return f'<span class="jbool" data-jpath="{path}">{val_str}</span>'
        if value is None:
            return f'<span class="jnull" data-jpath="{path}">null</span>'
        return f'<span class="jnum" data-jpath="{path}">{value}</span>'

    def apply_path_filter(self, expression: str) -> None:
        """
        Asynchronously prune self._json_data by JSONPath and re-render.
        A callback is fired with (expression, match_count) when done.
        """
        def _task():
            if not expression.strip():
                return self._json_data, [], expression.strip()

            try:
                expr = parse(expression)
                matches = expr.find(self._json_data)
                pruned = self._build_pruned_tree(matches)
                highlight_paths = [str(m.full_path) for m in matches]
                return pruned, highlight_paths, expression
            except JsonPathParserError as e:
                raise e
            except Exception as e:
                raise JsonPathParserError(f"Filter error: {e}") from e

        def _done(fut):
            try:
                pruned, highlights, expr = fut.result()
            except JsonPathParserError as e:
                GLib.idle_add(self._show_error_dialog, str(e))
                pruned, highlights, expr = self._json_data, [], ""

            GLib.idle_add(
                self._render,
                pruned,
                highlights,
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
        expr: str,
        count: int,
    ) -> bool:
        """Generates and loads HTML, then runs JS to highlight matches."""
        html = self._generate_html(data)

        if not self.webview:
            return False

        if hasattr(self.webview, "highlight_handler_id"):
            self.webview.disconnect(self.webview.highlight_handler_id)

        def on_load_finished(webview, load_event):
            if load_event == LoadEvent.FINISHED:
                js = (
                    f"const paths = {highlights!r};\n"
                    "paths.forEach(p => {\n"
                    '  const el = document.querySelector(`[data-jpath="${p}"]`);\n'
                    "  if (el) el.classList.add('jhighlight');\n"
                    "});"
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

    def _build_pruned_tree(self, matches: list) -> Any:
        """Return new dict/list containing matches and their ancestors."""
        if not matches:
            return {}

        keeper_paths = set()
        def get_path_tuple(m):
            path = []
            current = m
            while current and current.path is not None:
                path.insert(0, current.path)
                current = current.context
            return tuple(
                p.index if isinstance(p, Index) else str(p)
                for p in path
            )

        for m in matches:
            path_tuple = get_path_tuple(m)
            for i in range(len(path_tuple) + 1):
                keeper_paths.add(path_tuple[:i])

        if not keeper_paths or tuple() in keeper_paths:
            return self._json_data

        def recurse(data, path):
            if not isinstance(data, (dict, list)):
                return data

            if isinstance(data, dict):
                return {
                    key: recurse(value, path + (str(key),))
                    for key, value in data.items()
                    if path + (str(key),) in keeper_paths
                }

            # Must be a list
            return [
                recurse(value, path + (i,))
                for i, value in enumerate(data)
                if path + (i,) in keeper_paths
            ]

        return recurse(self._json_data, tuple())


class HtmlPreview:
    """Dummy html preview class."""


class Env:
    """Empty class for env overriding."""

    srcdir = ""


PARSERS = {
    "rst": {
        "key": "rst",
        "title": "Docutils reStructuredText parser",
        "class": RstParser,
        "package": "docutils",
        "url": "http://docutils.sourceforge.net",
    },
    "m2r": {
        "key": "m2r",
        "title": "MarkDown to reStructuredText",
        "class": Mark2Resturctured,
        "url": "https://github.com/miyakogi/m2r",
    },
    "html": {
        "key": "html",
        "title": "HTML preview",
        "class": HtmlPreview,
    },
    "json": {
        "key": "json",
        "title": "JSON preview",
        "class": JsonPreview,
    },
}

EXTS = {
    ".rst": "rst",
    ".html": "html",
    ".htm": "html",
    ".json": "json",
}

if Mark2Resturctured:
    EXTS[".md"] = "m2r"

WRITERS = {
    "html4": {
        "key": "html4",
        "title": "Docutils HTML4 writer",
        "class": Writer4css1,
        "package": "docutils",
        "url": "http://docutils.sourceforge.net",
    },
    "s5": {
        "key": "s5",
        "title": "Docutils S5/HTML slide show writer",
        "class": WriterS5,
        "package": "docutils",
        "url": "http://docutils.sourceforge.net",
    },
    "pep": {
        "key": "pep",
        "title": "Docutils PEP HTML writer",
        "class": WriterPep,
        "package": "docutils",
        "url": "http://docutils.sourceforge.net",
    },
    "tiny": {
        "key": "tiny",
        "title": "Tiny HTML writer",
        "class": TinyWriter,
        "package": "docutils-tinyhtmlwriter",
        "url": "https://github.com/ondratu/docutils-tinyhtmlwriter",
    },
    "html5": {
        "key": "html5",
        "title": "HTML 5 writer",
        "class": Html5Writer,
        "package": "docutils-html5-writer",
        "url": "https://github.com/Kozea/docutils-html5-writer",
    },
}

NOT_FOUND = """
<html>
  <head></head>
  <body>
    <h1>Commponent {title} Not Found!</h1>
    <p>Component <b>{title}</b> which you want to use is not found.
       See <a href="{url}">{url}</a> for mor details and install it
       to system.
    </p>
  </body>
</html>
"""

DATA_ERROR = """
<html>
  <head></head>
  <body>
    <h1>%s Error!</h1>
    <p style="color:red; text-width:weight;">%s</p>
  </body>
</html>
"""

NOT_IMPLEMENTED_ERROR = """
<html>
  <head></head>
  <body>
    <h1>Library Error</h1>
    <p>Sorry about that. This seems to be not supported functionality in
       dependent library Reader or Writer</p>
    <pre style="color:red; text-width:weight;">%s</pre>
  </body>
</html>
"""

EXCEPTION_ERROR = """
<html>
  <head></head>
  <body>
    <h1>Exception Error!</h1>
    <pre style="color:red; text-width:weight;">%s</pre>
  </body>
</html>
"""

SCROLL = """
<script>
    window.scrollTo(
        0,
        (document.documentElement.scrollHeight-window.innerHeight)*%f)
</script>
"""

JS_SCROLL = """
    window.scrollTo(
        0,
        (document.documentElement.scrollHeight-window.innerHeight)*%f);
"""

JS_POSITION = """
window.scrollY/(document.documentElement.scrollHeight-window.innerHeight)
"""

MARKUP = """<span background="#ddd"> %s </span>"""


class Renderer(Overlay):
    """Renderer widget, mainly based on Webkit."""

    def __init__(self, win, parser="rst", writer="html4", style=""):
        super().__init__()

        self.textview = TextView()
        self.fgcolor = "#000"

        self.webview = WebView()
        self.webview.get_settings().set_enable_developer_extras(True)
        self.webview.connect("mouse-target-changed", self.on_mouse)
        self.webview.connect("context-menu", self.on_context_menu)
        self.webview.connect("button-release-event", self.on_button_release)
        self.webview.connect("load-changed", self.on_load_changed)

        settings = Settings.get_default()
        settings.connect("notify::gtk-theme-name", self.on_theme_changed)
        self.on_theme_changed()

        self.add(self.webview)

        controller = self.webview.get_find_controller()
        self.search_done = None
        controller.connect("found-text", self.on_found_text)
        controller.connect("failed-to-find-text", self.on_faild_to_find_text)

        self.label = Label()
        self.label.set_halign(Align.START)
        self.label.set_valign(Align.END)
        self.add_overlay(self.label)
        self.link_uri = None
        self.context_button = 3  # will be rewrite by real value

        # Window reference must be available before parser initialization
        self.__win = win
        self.parser_instance = None

        self.set_writer(writer)
        self.set_parser(parser)

        self.style = style
        self.tab_width = 8


    def on_theme_changed(self, obj=None, pspec=None):
        """Change webkit background and default foreground color."""
        text_style = self.textview.get_style_context()
        background = text_style.get_background_color(StateFlags.NORMAL)
        foreground = text_style.get_color(StateFlags.NORMAL)
        self.webview.set_background_color(background)
        self.fgcolor = (
            f"#{int(foreground.red*255):02x}"
            f"{int(foreground.green*255):02x}"
            f"{int(foreground.blue*255):02x}"
        )
        self.on_load_changed(self.webview, LoadEvent.FINISHED)

    @property
    def position(self):
        """Return cursor position."""
        self.__position = -1
        self.webview.run_javascript(
            JS_POSITION,
            None,
            self.on_position_callback,
            None,
        )
        while self.__position < 0:
            main_iteration()
        return self.__position

    def on_position_callback(self, webview, result, data):
        """Set cursor position value."""
        try:
            js_res = webview.run_javascript_finish(result)
            self.__position = js_res.get_js_value().to_double()
        except Error:
            self.__position = 0

    def on_mouse(self, webview, hit_test_result, modifiers):
        """Show url links on mouse over."""
        self.link_uri = None
        if hit_test_result.context_is_link():
            self.link_uri = hit_test_result.get_link_uri()
            text = "link: " + self.link_uri
        elif hit_test_result.context_is_image():
            text = "image:" + hit_test_result.get_image_uri()
        elif hit_test_result.context_is_media():
            text = "media: " + hit_test_result.get_media_uri()
        else:
            if self.label.is_visible():
                self.label.hide()
            return
        self.label.set_markup(MARKUP % text.replace("&", "&amp;"))
        self.label.show()

    def on_context_menu(self, webview, menu, event, hit_test_result):
        """No action on webkit context menu."""
        self.context_button = event.button.button
        return True

    def on_button_release(self, webview, event):
        """Open links and let other clicks propagate."""
        if event.button != self.context_button and self.link_uri:
            if self.link_uri.startswith("file://"):
                self.find_and_opendocument(self.link_uri[7:].split("#")[0])
            else:
                show_uri_on_window(None, self.link_uri, 0)
            return True
        return False

    def find_and_opendocument(self, file_path):
        """Find file on disk and open it."""
        ext = splitext(file_path)[1]
        if not ext:
            for ext in LANGS:
                tmp = file_path + ext
                if exists(tmp):
                    file_path = tmp
                    break
        if ext in LANGS:
            self.__win.open_document(file_path)
        elif exists(file_path):
            show_uri_on_window(None, "file://" + file_path, 0)
        else:
            dialog = FileNotFoundDialog(self.__win, file_path)
            dialog.run()
            dialog.destroy()

    def set_writer(self, writer):
        """Set renderer writer."""
        assert writer in WRITERS
        self.__writer = WRITERS[writer]
        klass = self.__writer["class"]
        self.writer_instance = klass() if klass is not None else None
        idle_add(self.do_render)

    def get_writer(self):
        """Return renderer writer."""
        return self.__writer["key"]

    def set_parser(self, parser):
        """Set renderer parser."""
        assert parser in PARSERS
        self.__parser = PARSERS[parser]
        klass = self.__parser["class"]
        self.parser_instance = klass() if klass is not None else None
        if isinstance(self.parser_instance, JsonPreview):
            self.parser_instance.webview = self.webview
            self.parser_instance._win = self.__win
        idle_add(self.do_render)

    def get_parser(self):
        """Return renderer parser."""
        return self.__parser["key"]

    def set_style(self, style):
        """Set style for webview."""
        self.style = style
        idle_add(self.do_render)

    def get_style(self):
        """Return selected style."""
        return self.style

    def set_tab_width(self, width):
        """Set tab width."""
        self.tab_width = width
        idle_add(self.do_render)

    def render_output(self):  # noqa: C901, PLR0911, PLR0912
        """Render source and return output."""
        if getattr(self, "src", None) is None:
            return False, "", "text/plain"
        try:
            if self.__parser["class"] is None:
                html = NOT_FOUND.format(**self.__parser)
            elif self.__writer["class"] is None:
                html = NOT_FOUND.format(**self.__writer)
            elif issubclass(self.__parser["class"], JsonPreview):
                try:
                    parser = self.parser_instance
                    html = parser.to_html(self.src, self.tab_width)
                except (ValueError, TypeError) as e:
                    return False, DATA_ERROR % ("JSON", str(e)), "text/html"
                return True, html, "text/html"
            elif not issubclass(self.__parser["class"], HtmlPreview):
                settings = {
                    "warning_stream": StringIO(),
                    "embed_stylesheet": True,
                    "tab_width": self.tab_width,
                    "file_name": self.file_name,
                }
                if self.style:
                    settings["stylesheet"] = self.style
                    settings["stylesheet_path"] = []
                kwargs = {
                    "source": self.src,
                    "parser": self.parser_instance,
                    "writer": self.writer_instance,
                    "writer_name": "html",
                    "settings_overrides": settings,
                }
                if self.__writer["key"] == "pep":
                    kwargs["reader_name"] = "pep"
                    kwargs.pop("parser")
                html = publish_string(**kwargs).decode("utf-8")
                return True, html, "text/html"
            else:
                html = self.src

        except DataError as e:
            return False, DATA_ERROR % ("Data", e), "text/html"
        except NotImplementedError:
            exc_str = format_exc()
            return False, NOT_IMPLEMENTED_ERROR % exc_str, "text/html"
        except BaseException:
            exc_str = format_exc()
            return False, EXCEPTION_ERROR % exc_str, "text/html"
        else:
            return False, html, "text/html"

    def do_render(self):
        """Render the source, and show rendered output."""
        state, html, mime_type = self.render_output()
        if state:
            if self.pos > 1:
                a, b = len(self.src[:self.pos]), len(self.src[self.pos:])
                position = (float(a) / (a + b)) if a or b else 0
            else:
                position = self.pos
            html += SCROLL % position
        if html and getattr(self.__win, "runing", False):
            file_name = getattr(self, "file_name", get_home_dir())
            self.webview.load_bytes(
                Bytes(html.encode("utf-8")),
                mime_type,
                "UTF-8",
                "file://" + file_name,
            )

    def render(self, src, file_name, pos=0):
        """Add render task to ui queue."""
        self.src = src
        self.pos = pos
        self.file_name = file_name
        idle_add(self.do_render)

    def print_page(self):
        """Print the rendered page."""
        po = PrintOperation.new(self.webview)
        po.connect("failed", self.on_print_failed)
        po.run_dialog(self.__win)

    def on_print_failed(self, po, error):
        """Log error when print failed."""
        log_default_handler(
            "Application",
            LogLevelFlags.LEVEL_WARNING,
            error.message,
        )

    def on_load_changed(self, webview, load_event):
        """Set foreground color when object while object is loading."""
        self.webview.run_javascript(
            f"document.body.style.color='{self.fgcolor}'", None, None, None
        )

    def do_next_match(self, text):
        """Find next metch."""
        controller = self.webview.get_find_controller()
        if controller.get_search_text() != text:
            self.search_done = None
            controller.search(text, FindOptions.WRAP_AROUND, MAXUINT)
            while self.search_done is None:
                main_iteration()
        elif self.search_done:
            controller.search_next()
        return self.search_done

    def do_previous_match(self, text):
        """Find previous match."""
        controller = self.webview.get_find_controller()
        if controller.get_search_text() != text:
            self.search_done = None
            controller.search(
                text,
                FindOptions.WRAP_AROUND | FindOptions.BACKWARDS,
                MAXUINT,
            )
            while self.search_done is None:
                main_iteration()
        elif self.search_done:
            controller.search_previous()
        return self.search_done

    def stop_search(self):
        """Stop searching."""
        controller = self.webview.get_find_controller()
        controller.search_finish()

    def on_found_text(self, controller, count):
        """Mark search as done."""
        self.search_done = True

    def on_faild_to_find_text(self, controller):
        """Mark search as not done."""
        self.search_done = False

    def scroll_to_position(self, position):
        """Scroll to right cursor position."""
        if position is not None:
            self.pos = position

        if self.pos > 1:
            a, b = len(self.src[:self.pos]), len(self.src[self.pos:])
            position = (float(a) / (a + b)) if a or b else 0
        else:
            position = self.pos
        self.webview.run_javascript(JS_SCROLL % position, None, None, None)
