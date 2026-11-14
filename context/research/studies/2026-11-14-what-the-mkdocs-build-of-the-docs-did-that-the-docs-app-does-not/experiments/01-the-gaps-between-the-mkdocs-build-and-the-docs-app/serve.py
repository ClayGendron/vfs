import http.server, os, sys
root, port = sys.argv[1], int(sys.argv[2])
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=root, **k)
    def log_message(self, *a): pass
    def send_head(self):
        p = self.path.split('?')[0].split('#')[0]
        full = os.path.join(root, p.lstrip('/'))
        if not os.path.exists(full) and os.path.exists(full + '.html'):
            self.path = p + '.html'
        elif os.path.isdir(full) and not os.path.exists(os.path.join(full, 'index.html')) and os.path.exists(full.rstrip('/') + '.html'):
            self.path = p.rstrip('/') + '.html'
        elif not os.path.exists(full):
            self.send_response(404); self.send_header('Content-Type', 'text/html'); self.end_headers()
            self.wfile.write(open(os.path.join(root, '404.html'), 'rb').read()); return None
        return super().send_head()
http.server.ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()
