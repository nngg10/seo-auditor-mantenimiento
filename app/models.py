"""Entidades del dominio (POO) y repositorios que las persisten en SQLite."""
import json
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Optional

from .database import BaseDeDatos
from .services.ai_agent import FUENTE_REGLAS


# ----------------------------------------------------------------- Entidades
@dataclass
class Usuario:
    id: int
    nombre: str
    email: str
    password_hash: str = field(repr=False)

    def a_dict(self) -> dict:
        return {"id": self.id, "nombre": self.nombre, "email": self.email}


@dataclass
class Tienda:
    id: int
    usuario_id: int
    nombre: str
    url: str
    creado: str

    def a_dict(self) -> dict:
        return asdict(self)


@dataclass
class Auditoria:
    id: int
    tienda_id: int
    codigo: str
    url: str
    fecha: str
    duracion_s: Optional[float]
    http_status: Optional[int]
    rendimiento: Optional[int]
    seo: Optional[int]
    lcp_s: Optional[float]
    cls: Optional[float]
    tbt_ms: Optional[float]
    pagespeed_error: Optional[str]
    pagespeed: dict
    scraper: dict
    hallazgos: list
    recomendaciones: list
    ia_fuente: str
    ia_aviso: Optional[str]
    ia_fallo: bool

    @classmethod
    def desde_fila(cls, f) -> "Auditoria":
        return cls(
            id=f["id"], tienda_id=f["tienda_id"], codigo=f["codigo"], url=f["url"],
            fecha=f["fecha"], duracion_s=f["duracion_s"], http_status=f["http_status"],
            rendimiento=f["rendimiento"], seo=f["seo"], lcp_s=f["lcp_s"], cls=f["cls"],
            tbt_ms=f["tbt_ms"], pagespeed_error=f["pagespeed_error"],
            pagespeed=json.loads(f["pagespeed_json"] or "{}"),
            scraper=json.loads(f["scraper_json"] or "{}"),
            hallazgos=json.loads(f["hallazgos_json"] or "[]"),
            recomendaciones=json.loads(f["recomendaciones_json"] or "[]"),
            ia_fuente=f["ia_fuente"] or "", ia_aviso=f["ia_aviso"], ia_fallo=bool(f["ia_fallo"]),
        )

    # ------------------------------------------------- HU-M02: estado de servicios
    def estado_servicios(self) -> dict:
        """Estado de cada servicio, derivado de los datos ya guardados (sirve también
        para auditorías anteriores a HU-M02, sin migrar la base de datos).

        Estados: ok | fallo | incompleto (PageSpeed) y ok | respaldo | sin_configurar (IA).
        """
        tiempo = self.scraper.get("tiempo_respuesta_ms")
        html = {"estado": "ok", "detalle": f"HTTP {self.http_status}" + (f" en {tiempo} ms" if tiempo is not None else "")}

        if self.pagespeed_error:
            pagespeed = {"estado": "fallo", "detalle": self.pagespeed_error}
        elif self.rendimiento is None:
            pagespeed = {"estado": "incompleto", "detalle": "Google respondió sin puntaje de rendimiento."}
        else:
            pagespeed = {"estado": "ok", "detalle": f"Rendimiento móvil {self.rendimiento}/100"}

        if self.ia_fallo:
            ia = {"estado": "respaldo", "detalle": self.ia_aviso or "El servicio de IA no respondió; se usó el motor de reglas local."}
        elif self.ia_fuente == FUENTE_REGLAS:
            ia = {"estado": "sin_configurar",
                  "detalle": "No hay una API key de IA configurada; el plan se generó con el motor de reglas local."}
        else:
            ia = {"estado": "ok", "detalle": f"Plan generado por {self.ia_fuente}"}
        return {"html": html, "pagespeed": pagespeed, "ia": ia}

    @property
    def parcial(self) -> bool:
        """True si algún servicio configurado falló o respondió incompleto.
        La IA sin configurar es un modo de funcionamiento elegido, no un fallo."""
        s = self.estado_servicios()
        return s["pagespeed"]["estado"] != "ok" or s["ia"]["estado"] == "respaldo"

    def resumen(self) -> dict:
        return {
            "id": self.id, "codigo": self.codigo, "url": self.url, "fecha": self.fecha,
            "rendimiento": self.rendimiento, "seo": self.seo, "lcp_s": self.lcp_s,
            "parcial": self.parcial,
        }

    def a_dict(self) -> dict:
        d = asdict(self)
        d["servicios"] = self.estado_servicios()
        d["parcial"] = self.parcial
        return d


# -------------------------------------------------------------- Repositorios
class UsuarioRepositorio:
    def __init__(self, db: BaseDeDatos):
        self.db = db

    def _fila_a_usuario(self, f) -> Optional[Usuario]:
        return Usuario(f["id"], f["nombre"], f["email"], f["password_hash"]) if f else None

    def por_email(self, email: str) -> Optional[Usuario]:
        with self.db.sesion() as c:
            f = c.execute("SELECT * FROM usuarios WHERE email = ?", (email.lower(),)).fetchone()
        return self._fila_a_usuario(f)

    def por_id(self, usuario_id: int) -> Optional[Usuario]:
        with self.db.sesion() as c:
            f = c.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
        return self._fila_a_usuario(f)

    def crear(self, nombre: str, email: str, password_hash: str) -> Usuario:
        with self.db.sesion() as c:
            cur = c.execute(
                "INSERT INTO usuarios (nombre, email, password_hash) VALUES (?, ?, ?)",
                (nombre, email.lower(), password_hash),
            )
            nuevo_id = cur.lastrowid
        return Usuario(nuevo_id, nombre, email.lower(), password_hash)


class TiendaRepositorio:
    def __init__(self, db: BaseDeDatos):
        self.db = db

    def listar(self, usuario_id: int) -> list[Tienda]:
        with self.db.sesion() as c:
            filas = c.execute(
                "SELECT * FROM tiendas WHERE usuario_id = ? ORDER BY creado DESC, id DESC", (usuario_id,)
            ).fetchall()
        return [Tienda(f["id"], f["usuario_id"], f["nombre"], f["url"], f["creado"]) for f in filas]

    def obtener(self, usuario_id: int, tienda_id: int) -> Optional[Tienda]:
        with self.db.sesion() as c:
            f = c.execute(
                "SELECT * FROM tiendas WHERE id = ? AND usuario_id = ?", (tienda_id, usuario_id)
            ).fetchone()
        return Tienda(f["id"], f["usuario_id"], f["nombre"], f["url"], f["creado"]) if f else None

    def existe_url(self, usuario_id: int, url: str, excluir_id: Optional[int] = None) -> bool:
        with self.db.sesion() as c:
            f = c.execute(
                "SELECT id FROM tiendas WHERE usuario_id = ? AND url = ? AND id != ?",
                (usuario_id, url, excluir_id or -1),
            ).fetchone()
        return f is not None

    def crear(self, usuario_id: int, nombre: str, url: str) -> Tienda:
        with self.db.sesion() as c:
            cur = c.execute(
                "INSERT INTO tiendas (usuario_id, nombre, url) VALUES (?, ?, ?)", (usuario_id, nombre, url)
            )
            nuevo_id = cur.lastrowid
        return self.obtener(usuario_id, nuevo_id)

    def actualizar(self, usuario_id: int, tienda_id: int, nombre: str, url: str) -> Optional[Tienda]:
        with self.db.sesion() as c:
            c.execute(
                "UPDATE tiendas SET nombre = ?, url = ? WHERE id = ? AND usuario_id = ?",
                (nombre, url, tienda_id, usuario_id),
            )
        return self.obtener(usuario_id, tienda_id)

    def eliminar(self, usuario_id: int, tienda_id: int) -> bool:
        with self.db.sesion() as c:
            cur = c.execute("DELETE FROM tiendas WHERE id = ? AND usuario_id = ?", (tienda_id, usuario_id))
        return cur.rowcount > 0


class AuditoriaRepositorio:
    def __init__(self, db: BaseDeDatos):
        self.db = db

    def guardar(self, tienda_id: int, datos: dict) -> Auditoria:
        with self.db.sesion() as c:
            cur = c.execute(
                """INSERT INTO auditorias (tienda_id, url, duracion_s, http_status, rendimiento, seo,
                       lcp_s, cls, tbt_ms, pagespeed_error, pagespeed_json, scraper_json, hallazgos_json,
                       recomendaciones_json, ia_fuente, ia_aviso, ia_fallo)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    tienda_id, datos["url"], datos["duracion_s"], datos["http_status"],
                    datos["rendimiento"], datos["seo"], datos["lcp_s"], datos["cls"], datos["tbt_ms"],
                    datos["pagespeed_error"], json.dumps(datos["pagespeed"], ensure_ascii=False),
                    json.dumps(datos["scraper"], ensure_ascii=False),
                    json.dumps(datos["hallazgos"], ensure_ascii=False),
                    json.dumps(datos["recomendaciones"], ensure_ascii=False),
                    datos["ia_fuente"], datos["ia_aviso"], int(datos["ia_fallo"]),
                ),
            )
            nuevo_id = cur.lastrowid
            anio = c.execute("SELECT strftime('%Y', fecha) FROM auditorias WHERE id = ?", (nuevo_id,)).fetchone()[0]
            c.execute("UPDATE auditorias SET codigo = ? WHERE id = ?", (f"AUD-{anio}-{nuevo_id:03d}", nuevo_id))
        return self.obtener_por_id(nuevo_id)

    def actualizar_diagnostico(self, auditoria_id: int, recomendaciones: list, fuente: str,
                               aviso: Optional[str], fallo: bool) -> None:
        with self.db.sesion() as c:
            c.execute(
                "UPDATE auditorias SET recomendaciones_json = ?, ia_fuente = ?, ia_aviso = ?, ia_fallo = ? WHERE id = ?",
                (json.dumps(recomendaciones, ensure_ascii=False), fuente, aviso, int(fallo), auditoria_id),
            )

    def obtener_por_id(self, auditoria_id: int) -> Optional[Auditoria]:
        with self.db.sesion() as c:
            f = c.execute("SELECT * FROM auditorias WHERE id = ?", (auditoria_id,)).fetchone()
        return Auditoria.desde_fila(f) if f else None

    def obtener(self, usuario_id: int, auditoria_id: int) -> Optional[Auditoria]:
        """Solo devuelve la auditoría si pertenece a una tienda del usuario."""
        with self.db.sesion() as c:
            f = c.execute(
                """SELECT a.* FROM auditorias a JOIN tiendas t ON t.id = a.tienda_id
                   WHERE a.id = ? AND t.usuario_id = ?""",
                (auditoria_id, usuario_id),
            ).fetchone()
        return Auditoria.desde_fila(f) if f else None

    def listar_por_usuario(self, usuario_id: int, tienda_id: Optional[int] = None,
                           desde: Optional[date] = None, hasta: Optional[date] = None) -> list[tuple[Auditoria, str]]:
        """HU-M04: auditorías de TODAS las tiendas del usuario (o de una), con el nombre de la tienda.
        La unión con `tiendas.usuario_id` garantiza que nunca se incluyan datos de otra cuenta."""
        sql = ("SELECT a.*, t.nombre AS tienda_nombre FROM auditorias a JOIN tiendas t ON t.id = a.tienda_id "
               "WHERE t.usuario_id = ?")
        params: list = [usuario_id]
        if tienda_id is not None:
            sql += " AND t.id = ?"
            params.append(tienda_id)
        if desde is not None:
            sql += " AND date(a.fecha) >= ?"
            params.append(desde.isoformat())
        if hasta is not None:
            sql += " AND date(a.fecha) <= ?"
            params.append(hasta.isoformat())
        with self.db.sesion() as c:
            filas = c.execute(sql + " ORDER BY a.fecha DESC, a.id DESC", params).fetchall()
        return [(Auditoria.desde_fila(f), f["tienda_nombre"]) for f in filas]

    def listar_por_tienda(self, tienda_id: int, desde: Optional[date] = None,
                          hasta: Optional[date] = None) -> list[Auditoria]:
        """Auditorías de la tienda, de la más reciente a la más antigua.
        HU-M03: `desde` y `hasta` son opcionales e incluyen el día completo."""
        sql, params = "SELECT * FROM auditorias WHERE tienda_id = ?", [tienda_id]
        if desde is not None:
            sql += " AND date(fecha) >= ?"
            params.append(desde.isoformat())
        if hasta is not None:
            sql += " AND date(fecha) <= ?"
            params.append(hasta.isoformat())
        with self.db.sesion() as c:
            filas = c.execute(sql + " ORDER BY fecha DESC, id DESC", params).fetchall()
        return [Auditoria.desde_fila(f) for f in filas]

    def anterior(self, auditoria: Auditoria) -> Optional[Auditoria]:
        with self.db.sesion() as c:
            f = c.execute(
                """SELECT * FROM auditorias WHERE tienda_id = ? AND id < ?
                   ORDER BY id DESC LIMIT 1""",
                (auditoria.tienda_id, auditoria.id),
            ).fetchone()
        return Auditoria.desde_fila(f) if f else None
