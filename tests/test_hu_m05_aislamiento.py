"""HU-M05: aislamiento del acceso a auditorías entre cuentas (CA-01 a CA-05).

Dos cuentas independientes: A es la propietaria y B intenta llegar a los datos de A
cambiando identificadores en todas las rutas. También se recorren automáticamente todas
las rutas protegidas de la API para comprobar que exigen una sesión válida.
"""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.routing import APIRoute

from app.api import app
from app.api import auditorias as repo_auditorias
from app.config import JWT_SECRET
from app.database import db

RUTAS_PUBLICAS = {"/api/auth/registro", "/api/auth/login", "/api/salud"}
ID_INEXISTENTE = 999_999


def crear_cuenta(cliente, nombre):
    email = f"m05-{uuid.uuid4().hex[:8]}@test.com"
    r = cliente.post("/api/auth/registro", json={"nombre": nombre, "email": email,
                                                 "password": "Segura123", "confirmacion": "Segura123"})
    token = cliente.post("/api/auth/login", json={"email": email, "password": "Segura123"}).json()["access_token"]
    return {"headers": {"Authorization": f"Bearer {token}"}, "email": email, "id": r.json()["usuario"]["id"]}


def crear_auditoria(tienda_id):
    datos = {"url": "https://tienda-secreta-de-a.com/producto", "duracion_s": 1.0, "http_status": 200,
             "rendimiento": 55, "seo": 91, "lcp_s": 2.0, "cls": 0.0, "tbt_ms": 0, "pagespeed_error": None,
             "pagespeed": {}, "scraper": {"title": "Producto confidencial de A"}, "hallazgos": [],
             "recomendaciones": [], "ia_fuente": "Motor de reglas local", "ia_aviso": None, "ia_fallo": False}
    return repo_auditorias.guardar(tienda_id, datos).id


@pytest.fixture
def cuentas(cliente):
    a, b = crear_cuenta(cliente, "Propietaria A"), crear_cuenta(cliente, "Intrusa B")
    r = cliente.post("/api/tiendas", json={"nombre": "Tienda Secreta de A", "url": "https://tienda-secreta-de-a.com"},
                     headers=a["headers"])
    a["tienda"] = r.json()["id"]
    a["auditoria"] = crear_auditoria(a["tienda"])
    return a, b


def sin_datos_de(cuenta_a, respuesta):
    """CA-04: la respuesta no menciona nada de la cuenta A."""
    texto = respuesta.text
    return not any(x in texto for x in ("Tienda Secreta de A", "tienda-secreta-de-a.com", "Producto confidencial",
                                        "Propietaria A", cuenta_a["email"]))


# ---------------------------------------------- CA-01 / CA-02 (una prueba por ruta)
def peticiones_de_b(a):
    aud, tienda = a["auditoria"], a["tienda"]
    return {
        "detalle de auditoría": ("GET", f"/api/auditorias/{aud}", None, None),
        "reintentar diagnóstico IA": ("POST", f"/api/auditorias/{aud}/diagnostico", None, None),
        "exportación PDF": ("GET", f"/api/auditorias/{aud}/pdf", None, None),
        "historial de la tienda": ("GET", f"/api/tiendas/{tienda}/auditorias", None, None),
        "historial filtrado": ("GET", f"/api/tiendas/{tienda}/auditorias", {"desde": "2000-01-01"}, None),
        "exportación CSV de la tienda": ("GET", "/api/exportar/auditorias.csv", {"tienda_id": tienda}, None),
        "editar tienda": ("PUT", f"/api/tiendas/{tienda}", None, {"nombre": "Robada", "url": "https://robada.com"}),
        "eliminar tienda": ("DELETE", f"/api/tiendas/{tienda}", None, None),
        "auditar tienda ajena": ("POST", "/api/auditorias", None, {"tienda_id": tienda}),
    }


ACCIONES = list(peticiones_de_b({"auditoria": 0, "tienda": 0}))


@pytest.mark.parametrize("accion", ACCIONES)
def test_ca01_ca02_b_no_accede_a_datos_de_a(cliente, cuentas, accion):
    a, b = cuentas
    metodo, ruta, params, cuerpo = peticiones_de_b(a)[accion]
    r = cliente.request(metodo, ruta, params=params, json=cuerpo, headers=b["headers"])
    assert r.status_code == 404, f"{accion}: {r.status_code} {r.text}"
    assert sin_datos_de(a, r)


def test_ca02_los_datos_de_a_siguen_intactos_tras_los_intentos_de_b(cliente, cuentas):
    a, b = cuentas
    for metodo, ruta, params, cuerpo in peticiones_de_b(a).values():
        cliente.request(metodo, ruta, params=params, json=cuerpo, headers=b["headers"])
    tiendas_a = cliente.get("/api/tiendas", headers=a["headers"]).json()
    assert [(t["nombre"], t["url"]) for t in tiendas_a] == [("Tienda Secreta de A", "https://tienda-secreta-de-a.com")]
    assert cliente.get(f"/api/auditorias/{a['auditoria']}", headers=a["headers"]).status_code == 200


def test_ca02_listados_y_csv_general_de_b_no_incluyen_datos_de_a(cliente, cuentas):
    a, b = cuentas
    r = cliente.get("/api/tiendas", headers=b["headers"])
    assert r.json() == [] and sin_datos_de(a, r)
    csv_b = cliente.get("/api/exportar/auditorias.csv", headers=b["headers"])
    assert csv_b.status_code == 200 and sin_datos_de(a, csv_b)


def test_ca02_la_propietaria_si_accede_a_todo(cliente, cuentas):
    """Control positivo: las mismas rutas funcionan para A (las restricciones no bloquean al dueño)."""
    a, _ = cuentas
    h, aud, tienda = a["headers"], a["auditoria"], a["tienda"]
    assert cliente.get(f"/api/auditorias/{aud}", headers=h).status_code == 200
    assert cliente.get(f"/api/auditorias/{aud}/pdf", headers=h).status_code == 200
    assert cliente.get(f"/api/tiendas/{tienda}/auditorias", headers=h).json()["total"] == 1
    assert "Tienda Secreta de A" in cliente.get("/api/exportar/auditorias.csv", params={"tienda_id": tienda}, headers=h).text


# ------------------------------------------------------------------- CA-04
@pytest.mark.parametrize("ruta", ["/api/auditorias/{id}", "/api/auditorias/{id}/pdf"])
def test_ca04_ajena_e_inexistente_son_indistinguibles(cliente, cuentas, ruta):
    a, b = cuentas
    ajena = cliente.get(ruta.format(id=a["auditoria"]), headers=b["headers"])
    inexistente = cliente.get(ruta.format(id=ID_INEXISTENTE), headers=b["headers"])
    assert (ajena.status_code, ajena.json()) == (inexistente.status_code, inexistente.json())


def test_ca04_tienda_ajena_e_inexistente_son_indistinguibles(cliente, cuentas):
    a, b = cuentas
    ajena = cliente.get(f"/api/tiendas/{a['tienda']}/auditorias", headers=b["headers"])
    inexistente = cliente.get(f"/api/tiendas/{ID_INEXISTENTE}/auditorias", headers=b["headers"])
    assert (ajena.status_code, ajena.json()) == (inexistente.status_code, inexistente.json())


# ------------------------------------------------------------------- CA-03
def rutas_protegidas():
    rutas = []
    for r in app.routes:
        if isinstance(r, APIRoute) and r.path.startswith("/api/") and r.path not in RUTAS_PUBLICAS:
            for metodo in sorted(r.methods - {"HEAD", "OPTIONS"}):
                rutas.append((metodo, r.path))
    return rutas


INVENTARIO_REVISADO = {
    ("GET", "/api/auth/yo"),
    ("GET", "/api/tiendas"), ("POST", "/api/tiendas"),
    ("PUT", "/api/tiendas/{tienda_id}"), ("DELETE", "/api/tiendas/{tienda_id}"),
    ("GET", "/api/tiendas/{tienda_id}/auditorias"),
    ("POST", "/api/auditorias"), ("GET", "/api/auditorias/{auditoria_id}"),
    ("POST", "/api/auditorias/{auditoria_id}/diagnostico"), ("GET", "/api/auditorias/{auditoria_id}/pdf"),
    ("GET", "/api/exportar/auditorias.csv"),
}


def test_ca03_el_inventario_de_rutas_protegidas_esta_revisado():
    """Una ruta nueva hace fallar esta prueba hasta que alguien revise su control de acceso
    (si filtra por propietario) y la agregue al inventario."""
    assert set(rutas_protegidas()) == INVENTARIO_REVISADO


def token(sub, secreto=JWT_SECRET, minutos=60, alg="HS256"):
    exp = datetime.now(timezone.utc) + timedelta(minutes=minutos)
    return jwt.encode({"sub": str(sub), "exp": exp}, secreto, algorithm=alg)


@pytest.fixture
def credenciales_invalidas(cliente):
    eliminado = crear_cuenta(cliente, "Usuario eliminado")
    with db.sesion() as c:
        c.execute("DELETE FROM usuarios WHERE id = ?", (eliminado["id"],))
    sin_firma = jwt.encode({"sub": "1", "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, None, algorithm="none")
    return {
        "sin token": {},
        "token mal formado": {"Authorization": "Bearer abc.def.ghi"},
        "token firmado con otra clave": {"Authorization": f"Bearer {token(1, secreto='otra-clave-de-32-caracteres-xxxxxx')}"},
        "token sin firma (alg none)": {"Authorization": f"Bearer {sin_firma}"},
        "token vencido": {"Authorization": f"Bearer {token(1, minutos=-1)}"},
        "token de usuario eliminado": eliminado["headers"],
    }


@pytest.mark.parametrize("metodo,ruta", rutas_protegidas())
def test_ca03_toda_ruta_protegida_rechaza_credenciales_invalidas(cliente, credenciales_invalidas, metodo, ruta):
    ruta_real = ruta.replace("{tienda_id}", "1").replace("{auditoria_id}", "1")
    cuerpo = {"tienda_id": 1, "nombre": "x", "url": "https://x.com"} if metodo in ("POST", "PUT") else None
    for caso, headers in credenciales_invalidas.items():
        r = cliente.request(metodo, ruta_real, json=cuerpo, headers=headers)
        assert r.status_code == 401, f"{metodo} {ruta} con {caso}: {r.status_code}"
