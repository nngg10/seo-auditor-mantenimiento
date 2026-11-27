"""HU-M02: identificación del estado de los servicios externos (CA-01 a CA-05).

Se simulan respuestas satisfactorias, errores y tiempos de espera agotados de PageSpeed
y de la IA. El análisis HTML se simula con una página fija para no depender de Internet.
"""
import asyncio
import io
import json

import httpx
import pytest
from pypdf import PdfReader

from app.api import servicio_auditoria
from app.services.ai_agent import FUENTE_REGLAS, AgenteIA, ProveedorLLM
from app.services.pagespeed import ClientePageSpeed, PageSpeedError
from app.services.scraper import WebScraper

URL = "http://93.184.216.34/producto"      # IP pública literal: la política de HU-M01 no consulta DNS
HTML = ("<html lang='es'><head><title>Zapato de cuero artesanal para hombre</title></head>"
        "<body><h1>Zapato</h1><img src='a.jpg'></body></html>")
METRICAS_OK = {"rendimiento": 72, "seo_lighthouse": 90, "lcp_s": 2.9, "cls": 0.05, "tbt_ms": 150,
               "fcp_s": 1.2, "speed_index_s": 2.0, "inp_ms_campo": None, "oportunidades": []}


class LLMSimulado(ProveedorLLM):
    nombre = "IA simulada"

    def __init__(self, error: Exception | None = None):
        self.error = error

    async def generar(self, prompt: str) -> str:
        if self.error:
            raise self.error
        return json.dumps({"recomendaciones": [
            {"severidad": "Alta", "categoria": "SEO", "titulo": "Falta meta descripción", "accion": "Agregarla."}]})


@pytest.fixture
def escenario(cliente, sesion, monkeypatch):
    """Configura qué responde cada servicio y ejecuta una auditoría por la API."""
    async def scraper_simulado(url):
        return WebScraper()._extraer(HTML, url, 200, 120, False)

    monkeypatch.setattr(servicio_auditoria.scraper, "analizar", scraper_simulado)
    tienda = cliente.post("/api/tiendas", json={"nombre": "Tienda", "url": "https://books.toscrape.com"},
                          headers=sesion).json()["id"]

    def ejecutar(pagespeed=None, pagespeed_error: Exception | None = None, ia: ProveedorLLM | None = None):
        async def pagespeed_simulado(url, estrategia="mobile"):
            if pagespeed_error:
                raise pagespeed_error
            return pagespeed

        monkeypatch.setattr(servicio_auditoria.pagespeed, "consultar", pagespeed_simulado)
        monkeypatch.setattr(servicio_auditoria, "agente", AgenteIA(proveedor=ia))
        r = cliente.post("/api/auditorias", json={"tienda_id": tienda, "url": URL}, headers=sesion)
        assert r.status_code == 201, r.text
        return r.json()

    ejecutar.tienda = tienda
    return ejecutar


# ------------------------------------------------------------------- CA-01
def test_ca01_estado_por_separado_cuando_todo_responde(escenario):
    a = escenario(pagespeed=METRICAS_OK, ia=LLMSimulado())
    s = a["servicios"]
    assert [s["html"]["estado"], s["pagespeed"]["estado"], s["ia"]["estado"]] == ["ok", "ok", "ok"]
    assert a["parcial"] is False


# ------------------------------------------------------------------- CA-02
def test_ca02_pagespeed_con_error_no_se_muestra_como_cero(escenario):
    a = escenario(pagespeed_error=PageSpeedError("PageSpeed devolvió HTTP 500"), ia=LLMSimulado())
    assert a["servicios"]["pagespeed"]["estado"] == "fallo"
    assert "HTTP 500" in a["servicios"]["pagespeed"]["detalle"]
    assert a["rendimiento"] is None and a["lcp_s"] is None    # ausente, nunca 0
    assert a["parcial"] is True


def test_ca02_error_inesperado_de_pagespeed_no_rompe_la_auditoria(escenario):
    a = escenario(pagespeed_error=KeyError("lighthouseResult"), ia=LLMSimulado())
    assert a["servicios"]["pagespeed"]["estado"] == "fallo"
    assert "KeyError" not in a["servicios"]["pagespeed"]["detalle"]   # sin detalles internos


def test_ca02_pagespeed_sin_puntaje_se_marca_incompleto(escenario):
    a = escenario(pagespeed={**METRICAS_OK, "rendimiento": None}, ia=LLMSimulado())
    assert a["servicios"]["pagespeed"]["estado"] == "incompleto"
    assert a["parcial"] is True


# ------------------------------------------------------------------- CA-03
def test_ca03_ia_que_falla_se_identifica_como_respaldo_local(escenario):
    a = escenario(pagespeed=METRICAS_OK, ia=LLMSimulado(httpx.ReadTimeout("lento")))
    assert a["servicios"]["ia"]["estado"] == "respaldo"
    assert a["ia_fuente"] == FUENTE_REGLAS
    assert "tiempo de espera agotado" in a["servicios"]["ia"]["detalle"]
    assert a["parcial"] is True


def test_ca03_ia_sin_configurar_se_distingue_de_un_fallo(escenario):
    a = escenario(pagespeed=METRICAS_OK, ia=None)
    assert a["servicios"]["ia"]["estado"] == "sin_configurar"
    assert a["ia_fuente"] == FUENTE_REGLAS


def test_ca03_ia_que_responde_indica_el_proveedor(escenario):
    a = escenario(pagespeed=METRICAS_OK, ia=LLMSimulado())
    assert a["servicios"]["ia"]["estado"] == "ok"
    assert "IA simulada" in a["servicios"]["ia"]["detalle"]


# ------------------------------------------------------------------- CA-04
def test_ca04_pdf_conserva_las_advertencias_de_resultado_parcial(escenario, cliente, sesion):
    a = escenario(pagespeed_error=PageSpeedError("Google PageSpeed no respondió en 40 segundos."),
                  ia=LLMSimulado(httpx.ReadTimeout("lento")))
    r = cliente.get(f"/api/auditorias/{a['id']}/pdf", headers=sesion)
    texto = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    texto = " ".join(texto.split())
    assert "Resultado parcial" in texto
    assert "Google PageSpeed no respondió en 40 segundos" in texto
    assert "motor de reglas local" in texto
    assert "Estado de los servicios" in texto


def test_ca04_historial_marca_las_auditorias_parciales(escenario, cliente, sesion):
    escenario(pagespeed=METRICAS_OK, ia=LLMSimulado())
    escenario(pagespeed_error=PageSpeedError("cuota agotada"), ia=LLMSimulado())
    h = cliente.get(f"/api/tiendas/{escenario.tienda}/auditorias", headers=sesion).json()["auditorias"]
    assert [x["parcial"] for x in h] == [True, False]      # de la más reciente a la más antigua


# ------------------------------------------------------------------- CA-05
def test_ca05_pagespeed_tiempo_agotado():
    def servidor(request):
        raise httpx.ReadTimeout("sin respuesta", request=request)

    cliente_psi = ClientePageSpeed(api_key="", timeout=1, transporte=httpx.MockTransport(servidor))
    with pytest.raises(PageSpeedError) as e:
        asyncio.run(cliente_psi.consultar(URL))
    assert "no respondió" in str(e.value)


def test_ca05_pagespeed_cuota_agotada():
    cliente_psi = ClientePageSpeed(api_key="", transporte=httpx.MockTransport(
        lambda request: httpx.Response(429, json={"error": {"message": "Quota exceeded"}})))
    with pytest.raises(PageSpeedError) as e:
        asyncio.run(cliente_psi.consultar(URL))
    assert "cuota" in str(e.value).lower()
