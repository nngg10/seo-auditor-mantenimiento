"""HU-M01: pruebas de extremo a extremo sobre la API.

Reproducen el defecto: el servidor no debe conectarse a destinos de la red local
aunque el usuario los ingrese como URL de una auditoría.
"""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

DESTINOS_LOCALES = [
    "http://localhost",
    "http://127.0.0.1",
    "http://192.168.1.1",
    "http://10.0.0.8",
    "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/",
]


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


@pytest.fixture
def tienda(cliente, sesion):
    r = cliente.post("/api/tiendas", json={"nombre": "Tienda", "url": "https://books.toscrape.com"}, headers=sesion)
    return r.json()["id"]


@pytest.mark.parametrize("url", DESTINOS_LOCALES)
def test_no_se_registra_tienda_con_destino_local(cliente, sesion, url):
    r = cliente.post("/api/tiendas", json={"nombre": "Interna", "url": url}, headers=sesion)
    assert r.status_code == 422, f"{url} fue aceptada como tienda"


def test_auditoria_no_se_conecta_a_un_servicio_interno(cliente, sesion, tienda, servicio_interno):
    url_interna, visitas = servicio_interno
    r = cliente.post("/api/auditorias", json={"tienda_id": tienda, "url": url_interna}, headers=sesion)
    assert visitas == [], f"el servidor se conectó al servicio interno: {visitas}"
    assert r.status_code == 422


def test_rechazo_no_interrumpe_la_sesion_ni_expone_detalles(cliente, sesion, tienda):
    r = cliente.post("/api/auditorias", json={"tienda_id": tienda, "url": "http://127.0.0.1:9/"}, headers=sesion)
    assert r.status_code == 422
    detalle = r.json()["detail"]
    for interno in ("Traceback", "Errno", "Error(", "httpx", "socket"):
        assert interno not in detalle
    assert cliente.get("/api/tiendas", headers=sesion).status_code == 200
