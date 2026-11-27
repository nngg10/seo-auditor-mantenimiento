"""Pruebas de regresión: comportamiento existente que el mantenimiento no debe romper."""


def test_registro_y_login(cliente, sesion):
    r = cliente.get("/api/auth/yo", headers=sesion)
    assert r.status_code == 200
    assert r.json()["nombre"] == "Usuario Prueba"


def test_credenciales_incorrectas(cliente):
    r = cliente.post("/api/auth/login", json={"email": "nadie@test.com", "password": "mala12345"})
    assert r.status_code == 401


def test_ruta_protegida_sin_token(cliente):
    assert cliente.get("/api/tiendas").status_code == 401


def test_crear_tienda_publica(cliente, sesion):
    r = cliente.post("/api/tiendas", json={"nombre": "Librería", "url": "https://books.toscrape.com"}, headers=sesion)
    assert r.status_code == 201
    assert r.json()["url"] == "https://books.toscrape.com"
