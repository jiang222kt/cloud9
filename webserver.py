# webserver.py

import os
import re
import html
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── テンプレートエンジン ──
class TemplateEngine:
    def __init__(self, template_dir="templates"):
        self.template_dir = template_dir

    def __call__(self, tpl_name, context):
        return self.render(tpl_name, context)

    def render(self, tpl_name, context):
        path = os.path.join(self.template_dir, tpl_name)
        src  = open(path, encoding="utf-8").read()
        code = self._compile(src)
        namespace = dict(context, html=html)
        exec(code, namespace)
        return namespace["_render"]()

    def _compile(self, src):
        tokens = re.split(r'(<%=?|%>)', src)
        lines = [
            "def _render():",
            "    _buf = []",
            "    def write(s): _buf.append(str(s))",
        ]
        indent = 1
        mode = "text"

        for tok in tokens:
            if tok == "<%":
                mode = "code"
            elif tok == "<%=":
                mode = "expr"
            elif tok == "%>":
                mode = "text"
            else:
                if mode == "text":
                    for part in tok.splitlines(True):
                        if part:
                            lines.append("    " * indent + f"write({part!r})")
                elif mode == "expr":
                    expr = tok.strip()
                    lines.append(
                        "    " * indent +
                        f"write(html.escape(str({expr})))"
                    )
                elif mode == "code":
                    code_line = tok.strip()
                    if not code_line:
                        continue
                    if code_line == "endif":
                        indent -= 1
                    elif code_line.startswith(("else", "elif")):
                        indent -= 1
                        lines.append("    " * indent + code_line)
                        indent += 1
                    else:
                        lines.append("    " * indent + code_line)
                        if code_line.endswith(":"):
                            indent += 1

        lines.append("    return ''.join(_buf)")
        return "\n".join(lines)


# ── ルーティング ──
class Router:
    def __init__(self):
        self._routes = {}

    def add(self, method, path, handler):
        self._routes[(method.upper(), path)] = handler

    def match(self, method, path):
        return self._routes.get((method.upper(), path))


# ── 静的ファイル配信 ──
class StaticHandler:
    def __init__(self, directory):
        self.directory = directory

    def handle(self, req, url_prefix):
        rel = req.path[len(url_prefix):].lstrip("/")
        fs  = os.path.join(self.directory, rel)
        if not os.path.isfile(fs):
            return req.send_error(404)
        mime, _ = __import__("mimetypes").guess_type(fs)
        with open(fs, "rb") as f:
            data = f.read()
        req.send_response(200)
        req.send_header("Content-Type", mime or "application/octet-stream")
        req.send_header("Content-Length", str(len(data)))
        req.end_headers()
        req.wfile.write(data)


# ── ハンドラ定義 ──
def index_handler(req, params, tpl):
    body = tpl("index.html", {})
    data = body.encode("utf-8")
    req.send_response(200)
    req.send_header("Content-Type", "text/html; charset=utf-8")
    req.send_header("Content-Length", str(len(data)))
    req.end_headers()
    req.wfile.write(data)

def hello_handler(req, params, tpl):
    msg  = params.get("message", [""])[0]
    body = tpl("hello.html", {"message": msg})
    data = body.encode("utf-8")
    req.send_response(200)
    req.send_header("Content-Type", "text/html; charset=utf-8")
    req.send_header("Content-Length", str(len(data)))
    req.end_headers()
    req.wfile.write(data)

def whatsup_handler(req, params, tpl):
    info = params.get("info", [""])[0]
    body = tpl("whatsup.html", {"info": info})
    data = body.encode("utf-8")
    req.send_response(200)
    req.send_header("Content-Type", "text/html; charset=utf-8")
    req.send_header("Content-Length", str(len(data)))
    req.end_headers()
    req.wfile.write(data)


# ── WebServer 本体 ──
class WebServer:
    def __init__(self, root_dir, port, host="0.0.0.0"):
        self.root     = os.path.abspath(root_dir)
        self.host     = host
        self.port     = port
        self.router   = Router()
        self._statics = []
        self._orig    = None
        self._httpd   = None

        # デフォルト静的配信とルート設定
        self.static("/static/", os.path.join(self.root, "static"))
        self.router.add("GET",  "/",        index_handler)
        self.router.add("GET",  "/hello",   hello_handler)
        self.router.add("POST", "/whatsup", whatsup_handler)

    def static(self, url_prefix, directory):
        self._statics.append((url_prefix, directory))

    def __enter__(self):
        self._orig = os.getcwd()
        os.chdir(self.root)

        router  = self.router
        statics = self._statics
        engine  = TemplateEngine(template_dir="templates")

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                for prefix, d in statics:
                    if self.path.startswith(prefix):
                        return StaticHandler(d).handle(self, prefix)
                parsed = urllib.parse.urlparse(self.path)
                fn     = router.match("GET", parsed.path)
                if not fn:
                    return self.send_error(404)
                qs = urllib.parse.parse_qs(parsed.query)
                return fn(self, qs, engine)

            def do_POST(self):
                parsed = urllib.parse.urlparse(self.path)
                fn     = router.match("POST", parsed.path)
                if not fn:
                    return self.send_error(404)
                length = int(self.headers.get("Content-Length","0"))
                body   = self.rfile.read(length).decode()
                params = urllib.parse.parse_qs(body)
                return fn(self, params, engine)

        self._httpd = HTTPServer((self.host, self.port), _Handler)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._httpd:
            self._httpd.server_close()
        os.chdir(self._orig)

    def start(self):
        addr = f"http://{self.host}:{self.port}"
        print(f"Serving on {addr} (root: {self.root}) …")
        try:
            self._httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutdown requested")
        finally:
            self._httpd.server_close()
