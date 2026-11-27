"""HU-M01: pruebas unitarias de la política de URL segura (CA-01 a CA-05).

El DNS se simula para que las pruebas no dependan de Internet y sean repetibles.
"""
import asyncio

import httpx
import pytest

from app.services.scraper import ScraperError, WebScraper
from app.services.seguridad_url import (MENSAJE_CREDENCIALES, MENSAJE_DESTINO, MENSAJE_DNS, MENSAJE_FORMATO,
                                        BackendRedSeguro, PoliticaURL, TransporteSeguro, URLNoPermitida)

IP_PUBLICA = "93.184.216.34"


def dns_simulado(tabla: dict, llamadas: list | None = None):
    async def resolver(host, puerto):
        if llamadas is not None:
            llamadas.append(host)
        if host not in tabla:
            raise OSError("nombre no encontrado")
        valor = tabla[host]
        return valor(len(llamadas or [])) if callable(valor) else valor
    return resolver


def validar(politica, url):
    return asyncio.run(politica.validar(url))


# ------------------------------------------------------------------- CA-01
@pytest.mark.parametrize("url", [
    "", "mitienda.com", "ftp://mitienda.com", "javascript:alert(1)", "http://", "https://mitienda.com:99999",
])
def test_ca01_formatos_incorrectos(url):
    with pytest.raises(URLNoPermitida) as e:
        PoliticaURL().validar_formato(url)
    assert str(e.value) == MENSAJE_FORMATO


def test_ca01_rechaza_credenciales_en_la_url():
    with pytest.raises(URLNoPermitida) as e:
        PoliticaURL().validar_formato("https://usuario:clave@mitienda.com")
    assert str(e.value) == MENSAJE_CREDENCIALES


def test_ca01_url_publica_valida():
    politica = PoliticaURL(dns_simulado({"mitienda.com": [IP_PUBLICA]}))
    assert validar(politica, "https://mitienda.com/producto?id=1") == "https://mitienda.com/producto?id=1"


# ------------------------------------------------------------------- CA-02
@pytest.mark.parametrize("url", [
    "http://localhost/", "http://LOCALHOST:8000/", "http://127.0.0.1/", "http://127.1.2.3/", "http://0.0.0.0/",
    "http://10.0.0.8/", "http://172.16.5.4/", "http://192.168.1.1/", "http://169.254.169.254/latest/meta-data/",
    "http://100.64.0.1/", "http://224.0.0.1/", "http://240.0.0.1/", "http://[::1]/", "http://[fe80::1]/",
    "http://[fd00::1]/", "http://[::ffff:127.0.0.1]/", "http://intranet/", "http://servidor.local/",
    "http://api.internal/", "http://app.localhost/",
])
def test_ca02_destinos_no_publicos_rechazados_sin_dns(url):
    llamadas = []
    politica = PoliticaURL(dns_simulado({}, llamadas))
    with pytest.raises(URLNoPermitida) as e:
        validar(politica, url)
    assert str(e.value) == MENSAJE_DESTINO
    assert llamadas == [], "un destino reconocible como local no debe ni consultar el DNS"


def test_ca02_dominio_que_resuelve_a_ip_privada():
    politica = PoliticaURL(dns_simulado({"tienda-trampa.com": ["10.1.2.3"]}))
    with pytest.raises(URLNoPermitida) as e:
        validar(politica, "https://tienda-trampa.com/")
    assert str(e.value) == MENSAJE_DESTINO
    assert "10.1.2.3" not in str(e.value)        # CA-04: no revela la IP resuelta


def test_ca02_dominio_con_una_ip_publica_y_otra_privada():
    politica = PoliticaURL(dns_simulado({"mixto.com": [IP_PUBLICA, "192.168.0.10"]}))
    with pytest.raises(URLNoPermitida):
        validar(politica, "https://mixto.com/")


def test_ca02_dominio_inexistente():
    with pytest.raises(URLNoPermitida) as e:
        validar(PoliticaURL(dns_simulado({})), "https://no-existe-xyz.com/")
    assert str(e.value) == MENSAJE_DNS


# ------------------------------------------------------------------- CA-03
HTML = b"<html><head><title>Producto</title></head><body><h1>Zapato</h1></body></html>"


def _scraper_con_redireccion(destino: str, tabla: dict, visitas: list) -> WebScraper:
    def servidor(request: httpx.Request) -> httpx.Response:
        visitas.append(str(request.url))
        if request.url.host == "tienda.com":
            return httpx.Response(302, headers={"Location": destino})
        return httpx.Response(200, headers={"Content-Type": "text/html"}, content=HTML)

    politica = PoliticaURL(dns_simulado(tabla))
    return WebScraper(politica=politica, transporte=TransporteSeguro(politica, interno=httpx.MockTransport(servidor)))


@pytest.mark.parametrize("destino,tabla_extra", [
    ("http://169.254.169.254/latest/meta-data/", {}),
    ("http://127.0.0.1:8080/admin", {}),
    ("http://panel.tienda-trampa.com/", {"panel.tienda-trampa.com": ["10.0.0.5"]}),
])
def test_ca03_redireccion_hacia_destino_restringido(destino, tabla_extra):
    visitas = []
    scraper = _scraper_con_redireccion(destino, {"tienda.com": [IP_PUBLICA], **tabla_extra}, visitas)
    with pytest.raises(ScraperError) as e:
        asyncio.run(scraper.analizar("https://tienda.com/producto"))
    assert str(e.value) == MENSAJE_DESTINO
    assert visitas == ["https://tienda.com/producto"], "no debe conectarse al destino de la redirección"


def test_ca03_redireccion_hacia_destino_publico_permitida():
    visitas = []
    scraper = _scraper_con_redireccion("https://www.tienda.com/producto",
                                       {"tienda.com": [IP_PUBLICA], "www.tienda.com": [IP_PUBLICA]}, visitas)
    resultado = asyncio.run(scraper.analizar("https://tienda.com/producto"))
    assert resultado["title"] == "Producto"
    assert resultado["redirigida"] is True
    assert len(visitas) == 2


# ------------------------------------------- Conexión: IP fijada y DNS rebinding
class BackendEspia:
    def __init__(self):
        self.conexiones = []

    async def connect_tcp(self, host, port, **kwargs):
        self.conexiones.append((host, port))
        raise httpx.ConnectError("conexión simulada")


def test_backend_se_conecta_a_la_ip_validada_y_no_al_nombre():
    espia = BackendEspia()
    backend = BackendRedSeguro(PoliticaURL(dns_simulado({"tienda.com": [IP_PUBLICA]})), interno=espia)
    with pytest.raises(httpx.ConnectError):
        asyncio.run(backend.connect_tcp("tienda.com", 443))
    assert espia.conexiones == [(IP_PUBLICA, 443)]


def test_dns_rebinding_bloqueado_al_conectar(servicio_interno):
    """El DNS responde una IP pública al validar y 127.0.0.1 al conectar: no debe llegar al servicio interno."""
    url_interna, visitas = servicio_interno
    puerto = url_interna.rsplit(":", 1)[1].strip("/")
    llamadas = []
    tabla = {"rebind.example": lambda n: [IP_PUBLICA] if n == 1 else ["127.0.0.1"]}
    politica = PoliticaURL(dns_simulado(tabla, llamadas))

    async def descargar():
        async with httpx.AsyncClient(transport=TransporteSeguro(politica)) as c:
            await c.get(f"http://rebind.example:{puerto}/")

    with pytest.raises(URLNoPermitida):
        asyncio.run(descargar())
    assert visitas == []
    assert len(llamadas) == 2, "la validación al conectar debe usar el backend seguro (segunda resolución)"
