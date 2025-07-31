"""Webkit based renderer."""

from io import StringIO
from json import dumps, loads
from os.path import exists, splitext
from traceback import format_exc

from docutils import DataError
from docutils.core import publish_string
from docutils.parsers.rst import Parser as RstParser
from docutils.writers.html4css1 import Writer as Writer4css1
from docutils.writers.pep_html import Writer as WriterPep
from docutils.writers.s5_html import Writer as WriterS5
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


class HtmlPreview:
    """Dummy html preview class."""


class JSONPreview:
    """Dummy json preview class."""


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
        "class": JSONPreview,
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

# NOTE: json-formatter-js library is normally embedded here. The actual
# content could not be fetched in this environment.
JSON_FORMATTER_JS = """/* json-formatter-js library code should be here */"""

JSON_FORMATTER_CSS = """/* json-formatter-js CSS should be here */"""

JSON_VIEW_TEMPLATE = """<!DOCTYPE html>
<html>
  <head>
    <meta charset='utf-8'>
    <style>{css}</style>
  </head>
  <body>
    <div id='json-container'></div>
    <script>{js}</script>
    <script>
      const data = {json};
      const formatter = new JSONFormatter(data);
      document.getElementById('json-container').appendChild(formatter.render());
    </script>
  </body>
</html>"""


class Renderer(Overlay):
    """Renderer widget, mainly based on Webkit."""

    def __init__(self, win, parser="rst", writer="html4", style=""):
        super().__init__()

        self.textview = TextView()
        self.fgcolor = "#000"

        self.webview = WebView()
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

        self.set_writer(writer)
        self.set_parser(parser)
        self.style = style
        self.tab_width = 8
        self.__win = win

    def on_theme_changed(self, obj=None, pspec=None):
        """Change webkit background and default foreground color."""
        text_style = self.textview.get_style_context()
        background = text_style.get_background_color(StateFlags.NORMAL)
        foreground = text_style.get_color(StateFlags.NORMAL)
        self.webview.set_background_color(background)
        self.fgcolor = (
            f"#{int(foreground.red*255):x}"
            f"{int(foreground.green*255):x}"
            f"{int(foreground.blue*255):x}"
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
            # this call at this place do problem, when Gdk.threads_init
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
        return True  # disable context menu for now

    def on_button_release(self, webview, event):
        """Catch release-button only when try to follow link.

        Context menu is catch by webview before this callback.
        """
        if event.button == self.context_button:
            return True
        if self.link_uri:
            if self.link_uri.startswith("file://"):  # try to open source
                self.find_and_opendocument(self.link_uri[7:].split("#")[0])
            else:
                show_uri_on_window(None, self.link_uri, 0)
        return True

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
            elif issubclass(self.__parser["class"], JSONPreview):
                try:
                    json_data = loads(self.src)
                except ValueError as e:
                    return False, DATA_ERROR % ("JSON", str(e)), "text/html"
                else:
                    html = JSON_VIEW_TEMPLATE.format(
                        css=JSON_FORMATTER_CSS,
                        js=JSON_FORMATTER_JS,
                        json=dumps(json_data, ensure_ascii=False),
                    )
                    return False, html, "text/html"
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
                    kwargs.pop("parser")  # pep is allways rst
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
            # output to file or html preview
            return False, html, "text/html"

    def do_render(self):
        """Render the source, and show rendered output."""
        state, html, mime_type = self.render_output()
        if state:
            if self.pos > 1:  # vim
                a, b = len(self.src[:self.pos]), len(self.src[self.pos:])
                position = (float(a) / (a + b)) if a or b else 0
            else:
                position = self.pos

            html += SCROLL % position
        if html and self.__win.runing:
            file_name = self.file_name or get_home_dir()
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
        # FIXME: if dialog is used, application will lock :-(
        log_default_handler(
            "Application",
            LogLevelFlags.LEVEL_WARNING,
            error.message,
        )

    def on_load_changed(self, webview, load_event):
        """Set foreground color when object while object is loading."""
        self.webview.run_javascript(
            f"document.fgColor='{self.fgcolor}'",
            None,
            None,
            None,
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

        if self.pos > 1:  # vim
            a, b = len(self.src[:self.pos]), len(self.src[self.pos:])
            position = (float(a) / (a + b)) if a or b else 0
        else:
            position = self.pos

        self.webview.run_javascript(JS_SCROLL % position, None, None, None)
