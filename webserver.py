import os
import re
import html
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

# --- ノード定義 ---
class TextNode:
    def __init__(self, text): self.text = text
    def render(self, ctx, buf): buf.append(self.text)

class ExprNode:
    def __init__(self, expr): self.expr = expr.strip()
    def render(self, ctx, buf):
        val = eval(self.expr, {}, ctx)
        buf.append(str(html.escape(val)))

class CodeNode:
    def __init__(self, code): self.code = code
    def render(self, ctx, buf):
        exec(self.code, {}, ctx)

# --- Lexer & Parser ---
class Lexer:
    TOK = re.compile(r'(<%=?|%>)')
    def __init__(self, src): self.src = src
    def tokenize(self):
        parts = self.TOK.split(self.src)
        tokens, mode = [], 'TEXT'
        for p in parts:
            if p == '<%':    mode = 'CODE'
            elif p == '<%=': mode = 'EXPR'
            elif p == '%>':  mode = 'TEXT'
            else:            tokens.append((mode, p))
        return tokens

class Parser:
    def __init__(self, tokens): self.tokens = tokens
    def parse(self):
        nodes = []
        for typ, txt in self.tokens:
            if typ == 'TEXT': nodes.append(TextNode(txt))
            elif typ == 'EXPR': nodes.append(ExprNode(txt))
            elif typ == 'CODE': nodes.append(CodeNode(txt))
        return nodes

# --- テンプレートエンジン ---
class SimpleTemplate:
    def __init__(self, src):
        self.nodes = Parser(Lexer(src).tokenize()).parse()
    def render(self, **ctx):
        buf = []
        for n in self.nodes: n.render(ctx, buf)
        return ''.join(buf)

# --- ルーティング ---
class Router:
    def __init__(self): self._routes = {}
    def add(self, method, path, handler):
        self._routes[(method.upper(), path)] = handler
    def match(self, method, path):
        return self._routes.get((method.upper(), path))

# --- 静的ファイル配信 ---
class StaticHandler:
    def __init__(self, directory): self.directory = directory
    def handle(self, req, url_prefix):
        rel = req.path[len(url_prefix):].lstrip('/')
        fs  = os.path.join(self.directory, rel)
        if not os.path.isfile(fs):
            return req.send_error(404)
        mime, _ = __import__('mimetypes').guess_type(fs)
        with open(fs, 'rb') as f: data = f.read()
        req.send_response(200)
        req.send_header('Content-Type', mime or 'application/octet-stream')
        req.send_header('Content-Length', str(len(data)))
        req.end_headers()
        req.wfile.write(data)

# --- WebServer ---
class WebServer:
    def __init__(self, root_dir, port, host='0.0.0.0'):
        self.root    = os.path.abspath(root_dir)
        self.host    = host
        self.port    = port
        self.router  = Router()
        self._statics = []
        self._orig   = None
        self._httpd  = None

    def static(self, url_prefix, directory):
        self._statics.append((url_prefix, directory))

    def __enter__(self):
        self._orig = os.getcwd()
        os.chdir(self.root)

        router  = self.router
        statics = self._statics

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                # 静的配信
                for prefix, d in statics:
                    if self.path.startswith(prefix):
                        return StaticHandler(d).handle(self, prefix)
                # ルーティング
                parsed = urllib.parse.urlparse(self.path)
                fn     = router.match('GET', parsed.path)
                if not fn: return self.send_error(404)
                qs = urllib.parse.parse_qs(parsed.query)
                return fn(self, qs, SimpleTemplateLoader())

            def do_POST(self):
                parsed = urllib.parse.urlparse(self.path)
                fn     = router.match('POST', parsed.path)
                if not fn: return self.send_error(404)
                length = int(self.headers.get('Content-Length','0'))
                body   = self.rfile.read(length).decode()
                params = urllib.parse.parse_qs(body)
                return fn(self, params, SimpleTemplateLoader())

        self._httpd = HTTPServer((self.host, self.port), _Handler)
        return self

    def __exit__(self, *args):
        if self._httpd: self._httpd.server_close()
        os.chdir(self._orig)

    def start(self):
        addr = f"http://{self.host}:{self.port}"
        print(f"Serving on {addr} (root: {self.root}) …")
        try:
            self._httpd.serve_forever()
        except KeyboardInterrupt:
            print('\nShutdown requested')
        finally:
            self._httpd.server_close()

# --- テンプレート読み込みラッパー ---
class SimpleTemplateLoader:
    def __call__(self, tpl_name, ctx):
        path = os.path.join(os.getcwd(), 'templates', tpl_name)
        src  = open(path, encoding='utf-8').read()
        tpl  = SimpleTemplate(src)
        return tpl.render(**ctx)

# --- ハンドラ ---
def index_handler(req, params, tpl):
    html = tpl('index.html', {})
    b    = html.encode('utf-8')
    req.send_response(200)
    req.send_header('Content-Type','text/html; charset=utf-8')
    req.send_header('Content-Length',str(len(b)))
    req.end_headers()
    req.wfile.write(b)

def hello_handler(req, params, tpl):
    msg  = params.get('message',[''])[0]
    html = tpl('hello.html', {'message': msg})
    b    = html.encode('utf-8')
    req.send_response(200)
    req.send_header('Content-Type','text/html; charset=utf-8')
    req.send_header('Content-Length',str(len(b)))
    req.end_headers()
    req.wfile.write(b)

def whatsup_handler(req, params, tpl):
    msg  = params.get('message',[''])[0]
    html = tpl('whatsup.html', {'message': msg})
    b    = html.encode('utf-8')
    req.send_response(200)
    req.send_header('Content-Type','text/html; charset=utf-8')
    req.send_header('Content-Length',str(len(b)))
    req.end_headers()
    req.wfile.write(b)

# --- 実行 ---
if __name__ == '__main__':
    with WebServer('.', 8000) as app:
        app.static('/static/', './static')
        app.router.add('GET',  '/',       index_handler)
        app.router.add('GET',  '/hello',  hello_handler)
        app.router.add('POST', '/whatsup', whatsup_handler)
        app.start()