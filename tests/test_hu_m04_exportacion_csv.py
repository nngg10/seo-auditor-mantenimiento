"""HU-M04: exportación de resultados en CSV (CA-01 a CA-05).

El CSV usa UTF-8 con BOM y punto y coma como separador para que Excel en español
lo abra directamente en columnas y con las tildes correctas.
"""
import csv
import io
import uuid

import pytest

from app.api import auditorias as repo_auditorias
from app.database import db

ENCABEZADOS = ["Tienda", "URL", "Fecha", "Puntaje SEO", "Puntaje de rendimiento", "Resultado"]
RUTA = "/api/exportar/auditorias.csv"


def crear_auditoria(tienda_id, fecha, seo=80, rendimiento=70, pagespeed_error=None, url="https://books.toscrape.com"):
    datos = {"url": url, "duracion_s": 1.0, "http_status": 200, "rendimiento": rendimiento, "seo": seo,
             "lcp_s": None, "cls": None, "tbt_ms": None, "pagespeed_error": pagespeed_error, "pagespeed": {},
             "scraper": {}, "hallazgos": [], "recomendaciones": [], "ia_fuente": "Motor de reglas local",
             "ia_aviso": None, "ia_fallo": False}
    a = repo_auditorias.guardar(tienda_id, datos)
    with db.sesion() as c:
        c.execute("UPDATE auditorias SET fecha = ? WHERE id = ?", (fecha, a.id))
    return a.id


def cuenta(cliente):
    email = f"m04-{uuid.uuid4().hex[:8]}@test.com"
    cliente.post("/api/auth/registro", json={"nombre": "Cuenta CSV", "email": email,
                                             "password": "Segura123", "confirmacion": "Segura123"})
    token = cliente.post("/api/auth/login", json={"email": email, "password": "Segura123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def tienda(cliente, headers, nombre, url):
    r = cliente.post("/api/tiendas", json={"nombre": nombre, "url": url}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def leer_csv(r):
    assert r.status_code == 200, r.text
    assert r.content.startswith(b"\xef\xbb\xbf"), "debe incluir BOM UTF-8 para Excel"
    return list(csv.reader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))


# ------------------------------------------------------------------- CA-01
def test_ca01_encabezados_y_campos(cliente):
    h = cuenta(cliente)
    t = tienda(cliente, h, "Librería Cuero Fino", "https://books.toscrape.com")
    crear_auditoria(t, "2026-11-19 11:20:00", seo=87, rendimiento=74)
    r = cliente.get(RUTA, headers=h)
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"] and ".csv" in r.headers["content-disposition"]
    filas = leer_csv(r)
    assert filas[0] == ENCABEZADOS
    assert filas[1] == ["Librería Cuero Fino", "https://books.toscrape.com", "2026-11-19 11:20", "87", "74", "Completo"]


def test_ca01_orden_de_la_mas_reciente_a_la_mas_antigua(cliente):
    h = cuenta(cliente)
    t = tienda(cliente, h, "Tienda", "https://books.toscrape.com")
    for f in ("2026-11-01 08:00:00", "2026-11-20 08:00:00", "2026-11-10 08:00:00"):
        crear_auditoria(t, f)
    assert [f[2][:10] for f in leer_csv(cliente.get(RUTA, headers=h))[1:]] == ["2026-11-20", "2026-11-10", "2026-11-01"]


# ------------------------------------------------------------------- CA-02
def test_ca02_valores_ausentes_no_se_convierten_en_cero(cliente):
    h = cuenta(cliente)
    t = tienda(cliente, h, "Tienda", "https://books.toscrape.com")
    crear_auditoria(t, "2026-11-19 11:20:00", rendimiento=None, pagespeed_error="cuota agotada")
    fila = leer_csv(cliente.get(RUTA, headers=h))[1]
    assert fila[4] == ""                   # celda vacía: las hojas de cálculo no la promedian como 0
    assert fila[5] == "Parcial"


# ------------------------------------------------------------------- CA-03
def test_ca03_solo_auditorias_del_usuario_autenticado(cliente):
    a, b = cuenta(cliente), cuenta(cliente)
    crear_auditoria(tienda(cliente, a, "Tienda de A", "https://books.toscrape.com"), "2026-11-19 10:00:00")
    crear_auditoria(tienda(cliente, b, "Tienda de B", "https://webscraper.io"), "2026-11-19 10:00:00")
    filas = leer_csv(cliente.get(RUTA, headers=a))
    assert [f[0] for f in filas[1:]] == ["Tienda de A"]


def test_ca03_no_se_puede_exportar_una_tienda_ajena(cliente):
    a, b = cuenta(cliente), cuenta(cliente)
    ajena = tienda(cliente, b, "Tienda de B", "https://webscraper.io")
    crear_auditoria(ajena, "2026-11-19 10:00:00")
    r = cliente.get(RUTA, params={"tienda_id": ajena}, headers=a)
    assert r.status_code == 404
    assert "Tienda de B" not in r.text


def test_ca03_exportar_requiere_sesion(cliente):
    assert cliente.get(RUTA).status_code == 401


def test_ca03_filtro_por_tienda_y_fechas(cliente):
    h = cuenta(cliente)
    t1 = tienda(cliente, h, "Uno", "https://books.toscrape.com")
    t2 = tienda(cliente, h, "Dos", "https://webscraper.io")
    crear_auditoria(t1, "2026-11-05 10:00:00")
    crear_auditoria(t1, "2026-11-25 10:00:00")
    crear_auditoria(t2, "2026-11-10 10:00:00")
    filas = leer_csv(cliente.get(RUTA, params={"tienda_id": t1, "desde": "2026-11-20"}, headers=h))
    assert [(f[0], f[2][:10]) for f in filas[1:]] == [("Uno", "2026-11-25")]
    assert cliente.get(RUTA, params={"desde": "2026-11-20", "hasta": "2026-11-01"}, headers=h).status_code == 422


# ------------------------------------------------------------------- CA-04
def test_ca04_comas_comillas_punto_y_coma_tildes_y_saltos_de_linea(cliente):
    h = cuenta(cliente)
    nombre = 'Zapatería "El Ñandú", calzado; señoras\ny niños'
    t = tienda(cliente, h, nombre, "https://books.toscrape.com")
    crear_auditoria(t, "2026-11-19 11:20:00", url="https://books.toscrape.com/catalogue/página?a=1,2;3")
    fila = leer_csv(cliente.get(RUTA, headers=h))[1]
    assert fila[0] == nombre
    assert fila[1] == "https://books.toscrape.com/catalogue/página?a=1,2;3"


# ------------------------------------------------------------------- CA-05
@pytest.mark.parametrize("peligroso", ['=HYPERLINK("http://x.com","clic")', "+57 300", "-1+1", "@SUMA(A1)",
                                       "\t=1+1", "\r=1+1"])
def test_ca05_texto_que_parece_formula_se_neutraliza(cliente, peligroso):
    h = cuenta(cliente)
    t = tienda(cliente, h, "Tienda segura", "https://books.toscrape.com")
    with db.sesion() as c:                  # el nombre llega a la base sin pasar por la interfaz
        c.execute("UPDATE tiendas SET nombre = ? WHERE id = ?", (peligroso, t))
    crear_auditoria(t, "2026-11-19 11:20:00")
    celda = leer_csv(cliente.get(RUTA, headers=h))[1][0]
    assert celda == "'" + peligroso
    assert celda[0] not in "=+-@\t\r"


def test_ca05_los_puntajes_numericos_no_se_alteran(cliente):
    h = cuenta(cliente)
    t = tienda(cliente, h, "Tienda", "https://books.toscrape.com")
    crear_auditoria(t, "2026-11-19 11:20:00", seo=0, rendimiento=100)
    assert leer_csv(cliente.get(RUTA, headers=h))[1][3:5] == ["0", "100"]


def test_sin_auditorias_devuelve_solo_encabezados(cliente):
    assert leer_csv(cliente.get(RUTA, headers=cuenta(cliente))) == [ENCABEZADOS]
