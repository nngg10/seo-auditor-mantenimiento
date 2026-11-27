"""Configuración común de las pruebas.

El entorno de pruebas usa una base SQLite temporal y no llama a servicios externos
(PageSpeed ni IA), para que los resultados sean repetibles y no gasten cuotas.
"""
import os
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Debe definirse ANTES de importar la aplicación: config.py lee estas variables al cargarse.
_TMP = Path(tempfile.mkdtemp(prefix="auditor-pruebas-"))
os.environ["DB_PATH"] = str(_TMP / "pruebas.db")
os.environ["JWT_SECRET"] = "secreto-solo-para-pruebas-de-32-caracteres-o-mas"
for clave in ("OPENAI_API_KEY", "GEMINI_API_KEY", "PAGESPEED_API_KEY"):
    os.environ[clave] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import app, servicio_auditoria  # noqa: E402
from app.services.pagespeed import PageSpeedError  # noqa: E402


@pytest.fixture
def cliente(monkeypatch):
    async def pagespeed_simulado(url, estrategia="mobile"):
        raise PageSpeedError("PageSpeed desactivado en el entorno de pruebas.")

    monkeypatch.setattr(servicio_auditoria.pagespeed, "consultar", pagespeed_simulado)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sesion(cliente):
    """Registra un usuario nuevo y devuelve las cabeceras con su token JWT."""
    email = f"prueba-{uuid.uuid4().hex[:8]}@test.com"
    datos = {"nombre": "Usuario Prueba", "email": email, "password": "Segura123", "confirmacion": "Segura123"}
    assert cliente.post("/api/auth/registro", json=datos).status_code == 201
    token = cliente.post("/api/auth/login", json={"email": email, "password": "Segura123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def servicio_interno():
    """Servidor HTTP en 127.0.0.1 que simula un servicio interno y cuenta las visitas."""
    visitas = []

    class Manejador(BaseHTTPRequestHandler):
        def do_GET(self):
            visitas.append(self.path)
            cuerpo = b"<html><head><title>Panel interno confidencial</title></head><body>secreto</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def log_message(self, *args):
            pass

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{servidor.server_address[1]}/", visitas
    servidor.shutdown()
