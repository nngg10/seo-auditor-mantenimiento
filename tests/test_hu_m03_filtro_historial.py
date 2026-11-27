"""HU-M03: filtrado del historial de auditorías por intervalo de fechas (CA-01 a CA-05)."""
import uuid

import pytest

from app.api import auditorias as repo_auditorias
from app.database import db

FECHAS = ["2026-11-01 09:00:00", "2026-11-10 08:00:00", "2026-11-20 23:59:59", "2026-11-25 10:30:00"]


def crear_auditoria(tienda_id: int, fecha: str, seo: int) -> int:
    datos = {"url": "https://books.toscrape.com", "duracion_s": 1.0, "http_status": 200, "rendimiento": 80,
             "seo": seo, "lcp_s": 2.0, "cls": 0.0, "tbt_ms": 0, "pagespeed_error": None, "pagespeed": {},
             "scraper": {}, "hallazgos": [], "recomendaciones": [], "ia_fuente": "Motor de reglas local",
             "ia_aviso": None, "ia_fallo": False}
    a = repo_auditorias.guardar(tienda_id, datos)
    with db.sesion() as c:
        c.execute("UPDATE auditorias SET fecha = ? WHERE id = ?", (fecha, a.id))
    return a.id


def nueva_cuenta(cliente):
    email = f"m03-{uuid.uuid4().hex[:8]}@test.com"
    cliente.post("/api/auth/registro", json={"nombre": "Otra Cuenta", "email": email,
                                             "password": "Segura123", "confirmacion": "Segura123"})
    token = cliente.post("/api/auth/login", json={"email": email, "password": "Segura123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def historial(cliente, sesion):
    """Tienda con cuatro auditorías en fechas conocidas; devuelve una función de consulta."""
    tienda = cliente.post("/api/tiendas", json={"nombre": "Tienda", "url": "https://books.toscrape.com"},
                          headers=sesion).json()["id"]
    ids = {f[:10]: crear_auditoria(tienda, f, seo=60 + i * 10) for i, f in enumerate(FECHAS)}

    def consultar(headers=sesion, tienda_id=tienda, **filtro):
        return cliente.get(f"/api/tiendas/{tienda_id}/auditorias", params=filtro, headers=headers)

    consultar.tienda, consultar.ids = tienda, ids
    return consultar


def fechas_de(r):
    return [a["fecha"][:10] for a in r.json()["auditorias"]]


# ------------------------------------------------------------------- CA-01
def test_ca01_intervalo_con_limites_incluidos(historial):
    r = historial(desde="2026-11-10", hasta="2026-11-20")
    assert r.status_code == 200
    assert fechas_de(r) == ["2026-11-20", "2026-11-10"]   # incluye 23:59:59 del día final


def test_ca01_solo_fecha_inicial(historial):
    assert fechas_de(historial(desde="2026-11-20")) == ["2026-11-25", "2026-11-20"]


def test_ca01_solo_fecha_final(historial):
    assert fechas_de(historial(hasta="2026-11-10")) == ["2026-11-10", "2026-11-01"]


def test_ca01_la_respuesta_informa_el_filtro_y_el_total(historial):
    d = historial(desde="2026-11-10", hasta="2026-11-20").json()
    assert d["filtro"] == {"desde": "2026-11-10", "hasta": "2026-11-20"}
    assert d["total"] == 4


# ------------------------------------------------------------------- CA-02
def test_ca02_rechaza_fecha_inicial_posterior_a_la_final(historial):
    r = historial(desde="2026-11-20", hasta="2026-11-10")
    assert r.status_code == 422
    assert "posterior" in r.json()["detail"]


@pytest.mark.parametrize("valor", ["2026-13-01", "20-11-2026", "ayer", "2026-11-31"])
def test_ca02_rechaza_fechas_con_formato_invalido(historial, valor):
    r = historial(desde=valor)
    assert r.status_code == 422
    assert "AAAA-MM-DD" in r.json()["detail"]


# ------------------------------------------------------------------- CA-03
def test_ca03_otra_cuenta_no_puede_filtrar_una_tienda_ajena(historial, cliente):
    assert historial(headers=nueva_cuenta(cliente), desde="2026-11-01").status_code == 404


def test_ca03_el_filtro_no_mezcla_auditorias_de_otra_cuenta(historial, cliente):
    otra = nueva_cuenta(cliente)
    tienda_ajena = cliente.post("/api/tiendas", json={"nombre": "Ajena", "url": "https://webscraper.io"},
                                headers=otra).json()["id"]
    crear_auditoria(tienda_ajena, "2026-11-15 12:00:00", seo=10)
    r = historial(desde="2026-11-01", hasta="2026-11-30")
    assert len(r.json()["auditorias"]) == 4
    assert all(a["seo"] != 10 for a in r.json()["auditorias"])


# ------------------------------------------------------------------- CA-04
def test_ca04_orden_de_la_mas_reciente_a_la_mas_antigua(historial):
    assert fechas_de(historial(desde="2026-11-01", hasta="2026-11-30")) == [
        "2026-11-25", "2026-11-20", "2026-11-10", "2026-11-01"]


def test_ca04_la_variacion_se_calcula_contra_la_auditoria_realmente_anterior(historial):
    """Aunque la anterior quede fuera del filtro, la variación no cambia."""
    a = historial(desde="2026-11-20", hasta="2026-11-20").json()["auditorias"][0]
    assert a["variacion"]["seo"] == 10                     # 80 (20/nov) - 70 (10/nov)


# ------------------------------------------------------------------- CA-05
def test_ca05_intervalo_sin_coincidencias(historial):
    d = historial(desde="2026-10-01", hasta="2026-10-31").json()
    assert d["auditorias"] == []
    assert d["total"] == 4                                  # la interfaz ofrece limpiar el filtro


# ----------------------------------------------------------------- Regresión
def test_regresion_sin_filtro_devuelve_todo(historial):
    d = historial().json()
    assert len(d["auditorias"]) == 4
    assert d["filtro"] == {"desde": None, "hasta": None}
