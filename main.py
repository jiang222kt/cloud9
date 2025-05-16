# main.py

from webserver import WebServer

PORT = 8000
with WebServer("./", PORT) as httpd:
    httpd.start()
