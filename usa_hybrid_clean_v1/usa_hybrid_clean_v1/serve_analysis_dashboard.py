#!/usr/bin/env python
"""
Servidor HTTP simple para visualizar el dashboard de análisis
Uso: python serve_analysis_dashboard.py
Luego abre: http://localhost:8765
"""

import http.server
import socketserver
import os
from pathlib import Path

PORT = 8765
REPO_ROOT = Path(__file__).resolve().parent

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(REPO_ROOT), **kwargs)

os.chdir(REPO_ROOT)

with socketserver.TCPServer(("", PORT), MyHTTPRequestHandler) as httpd:
    print(f"")
    print(f"=" * 80)
    print(f"📊 DASHBOARD DE ANÁLISIS DISPONIBLE")
    print(f"=" * 80)
    print(f"")
    print(f"🌐 Abre tu navegador en:  http://localhost:{PORT}/analysis_dashboard.html")
    print(f"")
    print(f"📁 Directorio servido:    {REPO_ROOT}")
    print(f"")
    print(f"Presiona Ctrl+C para detener el servidor")
    print(f"")
    print(f"=" * 80)
    print(f"")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print(f"\n✓ Servidor detenido")
