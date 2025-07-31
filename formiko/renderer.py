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

JSON_FORMATTER_JS = r'''!function(t,e){"object"==typeof exports&&"undefined"!=typeof module?module.exports=e():"function"==typeof define&&define.amd?define(e):(t=t||self).JSONFormatter=e()}(this,(function(){"use strict";function t(t){return null===t?"null":typeof t}function e(t){return!!t&&"object"==typeof t}function r(t){if(void 0===t)return"";if(null===t)return"Object";if("object"==typeof t&&!t.constructor)return"Object";var e=/function ([^(]*)/.exec(t.constructor.toString());return e&&e.length>1?e[1]:""}function n(t,e,r){return"null"===t||"undefined"===t?t:("string"!==t&&"stringifiable"!==t||(r='"'+r.replace(/"/g,'\\"')+'"'),"function"===t?e.toString().replace(/[\r\n]/g,"").replace(/\{.*\}/,"")+"{…}":r)}function o(o){var i="";return e(o)?(i=r(o),Array.isArray(o)&&(i+="["+o.length+"]")):i=n(t(o),o,o),i}function i(t){return"json-formatter-"+t}function s(t,e,r){var n=document.createElement(t);return e&&n.classList.add(i(e)),void 0!==r&&(r instanceof Node?n.appendChild(r):n.appendChild(document.createTextNode(String(r)))),n}!function(t){if(t&&"undefined"!=typeof window){var e=document.createElement("style");e.setAttribute("media","screen"),e.innerHTML=t,document.head.appendChild(e)}}('.json-formatter-row {\n  font-family: monospace;\n}\n.json-formatter-row,\n.json-formatter-row a,\n.json-formatter-row a:hover {\n  color: black;\n  text-decoration: none;\n}\n.json-formatter-row .json-formatter-row {\n  margin-left: 1rem;\n}\n.json-formatter-row .json-formatter-children.json-formatter-empty {\n  opacity: 0.5;\n  margin-left: 1rem;\n}\n.json-formatter-row .json-formatter-children.json-formatter-empty:after {\n  display: none;\n}\n.json-formatter-row .json-formatter-children.json-formatter-empty.json-formatter-object:after {\n  content: "No properties";\n}\n.json-formatter-row .json-formatter-children.json-formatter-empty.json-formatter-array:after {\n  content: "[]";\n}\n.json-formatter-row .json-formatter-string,\n.json-formatter-row .json-formatter-stringifiable {\n  color: green;\n  white-space: pre;\n  word-wrap: break-word;\n}\n.json-formatter-row .json-formatter-number {\n  color: blue;\n}\n.json-formatter-row .json-formatter-boolean {\n  color: red;\n}\n.json-formatter-row .json-formatter-null {\n  color: #855A00;\n}\n.json-formatter-row .json-formatter-undefined {\n  color: #ca0b69;\n}\n.json-formatter-row .json-formatter-function {\n  color: #FF20ED;\n}\n.json-formatter-row .json-formatter-date {\n  background-color: rgba(0, 0, 0, 0.05);\n}\n.json-formatter-row .json-formatter-url {\n  text-decoration: underline;\n  color: blue;\n  cursor: pointer;\n}\n.json-formatter-row .json-formatter-bracket {\n  color: blue;\n}\n.json-formatter-row .json-formatter-key {\n  color: #00008B;\n  padding-right: 0.2rem;\n}\n.json-formatter-row .json-formatter-toggler-link {\n  cursor: pointer;\n}\n.json-formatter-row .json-formatter-toggler {\n  line-height: 1.2rem;\n  font-size: 0.7rem;\n  vertical-align: middle;\n  opacity: 0.6;\n  cursor: pointer;\n  padding-right: 0.2rem;\n}\n.json-formatter-row .json-formatter-toggler:after {\n  display: inline-block;\n  transition: transform 100ms ease-in;\n  content: "►";\n}\n.json-formatter-row > a > .json-formatter-preview-text {\n  opacity: 0;\n  transition: opacity 0.15s ease-in;\n  font-style: italic;\n}\n.json-formatter-row:hover > a > .json-formatter-preview-text {\n  opacity: 0.6;\n}\n.json-formatter-row.json-formatter-open > .json-formatter-toggler-link .json-formatter-toggler:after {\n  transform: rotate(90deg);\n}\n.json-formatter-row.json-formatter-open > .json-formatter-children:after {\n  display: inline-block;\n}\n.json-formatter-row.json-formatter-open > a > .json-formatter-preview-text {\n  display: none;\n}\n.json-formatter-row.json-formatter-open.json-formatter-empty:after {\n  display: block;\n}\n.json-formatter-dark.json-formatter-row {\n  font-family: monospace;\n}\n.json-formatter-dark.json-formatter-row,\n.json-formatter-dark.json-formatter-row a,\n.json-formatter-dark.json-formatter-row a:hover {\n  color: white;\n  text-decoration: none;\n}\n.json-formatter-dark.json-formatter-row .json-formatter-row {\n  margin-left: 1rem;\n}\n.json-formatter-dark.json-formatter-row .json-formatter-children.json-formatter-empty {\n  opacity: 0.5;\n  margin-left: 1rem;\n}\n.json-formatter-dark.json-formatter-row .json-formatter-children.json-formatter-empty:after {\n  display: none;\n}\n.json-formatter-dark.json-formatter-row .json-formatter-children.json-formatter-empty.json-formatter-object:after {\n  content: "No properties";\n}\n.json-formatter-dark.json-formatter-row .json-formatter-children.json-formatter-empty.json-formatter-array:after {\n  content: "[]";\n}\n.json-formatter-dark.json-formatter-row .json-formatter-string,\n.json-formatter-dark.json-formatter-row .json-formatter-stringifiable {\n  color: #31F031;\n  white-space: pre;\n  word-wrap: break-word;\n}\n.json-formatter-dark.json-formatter-row .json-formatter-number {\n  color: #66C2FF;\n}\n.json-formatter-dark.json-formatter-row .json-formatter-boolean {\n  color: #EC4242;\n}\n.json-formatter-dark.json-formatter-row .json-formatter-null {\n  color: #EEC97D;\n}\n.json-formatter-dark.json-formatter-row .json-formatter-undefined {\n  color: #ef8fbe;\n}\n.json-formatter-dark.json-formatter-row .json-formatter-function {\n  color: #FD48CB;\n}\n.json-formatter-dark.json-formatter-row .json-formatter-date {\n  background-color: rgba(255, 255, 255, 0.05);\n}\n.json-formatter-dark.json-formatter-row .json-formatter-url {\n  text-decoration: underline;\n  color: #027BFF;\n  cursor: pointer;\n}\n.json-formatter-dark.json-formatter-row .json-formatter-bracket {\n  color: #9494FF;\n}\n.json-formatter-dark.json-formatter-row .json-formatter-key {\n  color: #23A0DB;\n  padding-right: 0.2rem;\n}\n.json-formatter-dark.json-formatter-row .json-formatter-toggler-link {\n  cursor: pointer;\n}\n.json-formatter-dark.json-formatter-row .json-formatter-toggler {\n  line-height: 1.2rem;\n  font-size: 0.7rem;\n  vertical-align: middle;\n  opacity: 0.6;\n  cursor: pointer;\n  padding-right: 0.2rem;\n}\n.json-formatter-dark.json-formatter-row .json-formatter-toggler:after {\n  display: inline-block;\n  transition: transform 100ms ease-in;\n  content: "►";\n}\n.json-formatter-dark.json-formatter-row > a > .json-formatter-preview-text {\n  opacity: 0;\n  transition: opacity 0.15s ease-in;\n  font-style: italic;\n}\n.json-formatter-dark.json-formatter-row:hover > a > .json-formatter-preview-text {\n  opacity: 0.6;\n}\n.json-formatter-dark.json-formatter-row.json-formatter-open > .json-formatter-toggler-link .json-formatter-toggler:after {\n  transform: rotate(90deg);\n}\n.json-formatter-dark.json-formatter-row.json-formatter-open > .json-formatter-children:after {\n  display: inline-block;\n}\n.json-formatter-dark.json-formatter-row.json-formatter-open > a > .json-formatter-preview-text {\n  display: none;\n}\n.json-formatter-dark.json-formatter-row.json-formatter-open.json-formatter-empty:after {\n  display: block;\n}\n');var a=/(^\d{1,4}[\.|\\/|-]\d{1,2}[\.|\\/|-]\d{1,4})(\s*(?:0?[1-9]:[0-5]|1(?=[012])\d:[0-5])\d\s*[ap]m)?$/,f=/\d{2}:\d{2}:\d{2} GMT-\d{4}/,m=/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.\d{3}Z/,l=window.requestAnimationFrame||function(t){return t(),0},d={hoverPreviewEnabled:!1,hoverPreviewArrayCount:100,hoverPreviewFieldCount:5,animateOpen:!0,animateClose:!0,theme:null,useToJSON:!0,sortPropertiesBy:null};return function(){function c(t,e,r,n){void 0===e&&(e=1),void 0===r&&(r=d),this.json=t,this.open=e,this.config=r,this.key=n,this._isOpen=null,void 0===this.config.hoverPreviewEnabled&&(this.config.hoverPreviewEnabled=d.hoverPreviewEnabled),void 0===this.config.hoverPreviewArrayCount&&(this.config.hoverPreviewArrayCount=d.hoverPreviewArrayCount),void 0===this.config.hoverPreviewFieldCount&&(this.config.hoverPreviewFieldCount=d.hoverPreviewFieldCount),void 0===this.config.useToJSON&&(this.config.useToJSON=d.useToJSON),""===this.key&&(this.key='""')}return Object.defineProperty(c.prototype,"isOpen",{get:function(){return null!==this._isOpen?this._isOpen:this.open>0},set:function(t){this._isOpen=t},enumerable:!0,configurable:!0}),Object.defineProperty(c.prototype,"isDate",{get:function(){return this.json instanceof Date||"string"===this.type&&(a.test(this.json)||m.test(this.json)||f.test(this.json))},enumerable:!0,configurable:!0}),Object.defineProperty(c.prototype,"isUrl",{get:function(){return"string"===this.type&&0===this.json.indexOf("http")},enumerable:!0,configurable:!0}),Object.defineProperty(c.prototype,"isArray",{get:function(){return Array.isArray(this.json)},enumerable:!0,configurable:!0}),Object.defineProperty(c.prototype,"isObject",{get:function(){return e(this.json)},enumerable:!0,configurable:!0}),Object.defineProperty(c.prototype,"isEmptyObject",{get:function(){return!this.keys.length&&!this.isArray},enumerable:!0,configurable:!0}),Object.defineProperty(c.prototype,"isEmpty",{get:function(){return this.isEmptyObject||this.keys&&!this.keys.length&&this.isArray},enumerable:!0,configurable:!0}),Object.defineProperty(c.prototype,"useToJSON",{get:function(){return this.config.useToJSON&&"stringifiable"===this.type},enumerable:!0,configurable:!0}),Object.defineProperty(c.prototype,"hasKey",{get:function(){return void 0!==this.key},enumerable:!0,configurable:!0}),Object.defineProperty(c.prototype,"constructorName",{get:function(){return r(this.json)},enumerable:!0,configurable:!0}),Object.defineProperty(c.prototype,"type",{get:function(){return this.config.useToJSON&&this.json&&this.json.toJSON?"stringifiable":t(this.json)},enumerable:!0,configurable:!0}),Object.defineProperty(c.prototype,"keys",{get:function(){if(this.isObject){var t=Object.keys(this.json);return!this.isArray&&this.config.sortPropertiesBy?t.sort(this.config.sortPropertiesBy):t}return[]},enumerable:!0,configurable:!0}),c.prototype.toggleOpen=function(){this.isOpen=!this.isOpen,this.element&&(this.isOpen?this.appendChildren(this.config.animateOpen):this.removeChildren(this.config.animateClose),this.element.classList.toggle(i("open")))},c.prototype.openAtDepth=function(t){void 0===t&&(t=1),t<0||(this.open=t,this.isOpen=0!==t,this.element&&(this.removeChildren(!1),0===t?this.element.classList.remove(i("open")):(this.appendChildren(this.config.animateOpen),this.element.classList.add(i("open")))))},c.prototype.getInlinepreview=function(){var t=this;if(this.isArray)return this.json.length>this.config.hoverPreviewArrayCount?"Array["+this.json.length+"]":"["+this.json.map(o).join(", ")+"]";var e=this.keys,r=e.slice(0,this.config.hoverPreviewFieldCount).map((function(e){return e+":"+o(t.json[e])})),n=e.length>=this.config.hoverPreviewFieldCount?"…":"";return"{"+r.join(", ")+n+"}"},c.prototype.render=function(){this.element=s("div","row");var t=this.isObject?s("a","toggler-link"):s("span");if(this.isObject&&!this.useToJSON&&t.appendChild(s("span","toggler")),this.hasKey&&t.appendChild(s("span","key",this.key+":")),this.isObject&&!this.useToJSON){var e=s("span","value"),r=s("span"),o=s("span","constructor-name",this.constructorName);if(r.appendChild(o),this.isArray){var a=s("span");a.appendChild(s("span","bracket","[")),a.appendChild(s("span","number",this.json.length)),a.appendChild(s("span","bracket","]")),r.appendChild(a)}e.appendChild(r),t.appendChild(e)}else{(e=this.isUrl?s("a"):s("span")).classList.add(i(this.type)),this.isDate&&e.classList.add(i("date")),this.isUrl&&(e.classList.add(i("url")),e.setAttribute("href",this.json));var f=n(this.type,this.json,this.useToJSON?this.json.toJSON():this.json);e.appendChild(document.createTextNode(f)),t.appendChild(e)}if(this.isObject&&this.config.hoverPreviewEnabled){var m=s("span","preview-text");m.appendChild(document.createTextNode(this.getInlinepreview())),t.appendChild(m)}var l=s("div","children");return this.isObject&&l.classList.add(i("object")),this.isArray&&l.classList.add(i("array")),this.isEmpty&&l.classList.add(i("empty")),this.config&&this.config.theme&&this.element.classList.add(i(this.config.theme)),this.isOpen&&this.element.classList.add(i("open")),this.element.appendChild(t),this.element.appendChild(l),this.isObject&&this.isOpen&&this.appendChildren(),this.isObject&&!this.useToJSON&&t.addEventListener("click",this.toggleOpen.bind(this)),this.element},c.prototype.appendChildren=function(t){var e=this;void 0===t&&(t=!1);var r=this.element.querySelector("div."+i("children"));if(r&&!this.isEmpty)if(t){var n=0,o=function(){var t=e.keys[n],i=new c(e.json[t],e.open-1,e.config,t);r.appendChild(i.render()),(n+=1)<e.keys.length&&(n>10?o():l(o))};l(o)}else this.keys.forEach((function(t){var n=new c(e.json[t],e.open-1,e.config,t);r.appendChild(n.render())}))},c.prototype.removeChildren=function(t){void 0===t&&(t=!1);var e=this.element.querySelector("div."+i("children"));if(t){var r=0,n=function(){e&&e.children.length&&(e.removeChild(e.children[0]),(r+=1)>10?n():l(n))};l(n)}else e&&(e.innerHTML="")},c}()}));
'''

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
                    html = f'''
<html>
<head>
<script>
{JSON_FORMATTER_JS}
</script>
</head>
<body>
<script>
const data = {dumps(json_data)};
const formatter = new JSONFormatter(data, 2);
document.body.appendChild(formatter.render());
</script>
</body>
</html>
'''
                    return False, html, "text/html"
                except ValueError as e:
                    return False, DATA_ERROR % ("JSON", str(e)), "text/html"
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
