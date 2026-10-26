import http.server
import socketserver
import threading
import os

# Render ke liye ek chota dummy web server
PORT = int(os.environ.get("PORT", 10000))

class SimpleHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")

def run_web_server():
    with socketserver.TCPServer(("", PORT), Handler := SimpleHandler) as httpd:
        print(f"Web server running on port {PORT}")
        httpd.serve_forever()

# Web server ko background thread me start kar rahe hain taaki Render khush rahe
threading.Thread(target=run_web_server, daemon=True).start()
      
