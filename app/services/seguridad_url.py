"""HU-M01: política de URL segura para las auditorías.

Impide que el servidor se use para llegar a destinos de la red local o privada
(ataque SSRF). La comprobación se hace en tres niveles:

1. Formato: esquema http/https, host presente y sin credenciales en la URL.
2. Destino: el nombre se resuelve por DNS y TODAS sus direcciones deben ser públicas.
3. Conexión: el transporte HTTP valida cada salto, incluidas las redirecciones, y se
   conecta exactamente a la IP que validó. Así, un cambio de DNS entre la validación
   y la conexión (DNS rebinding) no permite llegar a la red interna.

Los mensajes de URLNoPermitida están pensados para mostrarse al usuario: no incluyen
direcciones IP resueltas ni detalles internos (CA-04).
"""
import asyncio
import ipaddress
import socket
from typing import Awaitable, Callable, Optional, Union
from urllib.parse import urlsplit

import httpcore
import httpx

MENSAJE_FORMATO = "La URL no es válida. Debe empezar por http:// o https:// (ej. https://mitienda.com)."
MENSAJE_CREDENCIALES = "La URL no debe incluir usuario ni contraseña."
MENSAJE_DESTINO = ("La dirección apunta a un destino no permitido (red local, privada o reservada). "
                   "Solo se pueden auditar sitios públicos.")
MENSAJE_DNS = "No se encontró el dominio. Revisa que la URL esté bien escrita."

NOMBRES_LOCALES = {"localhost"}
SUFIJOS_LOCALES = (".localhost", ".local", ".internal", ".lan", ".home.arpa")

IP = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]
Resolver = Callable[[str, int], Awaitable[list]]


class URLNoPermitida(ValueError):
    """La URL no cumple la política. El mensaje se puede mostrar al usuario."""


async def resolver_dns(host: str, puerto: int) -> list:
    """Resolución DNS real (todas las direcciones IPv4 e IPv6 del nombre)."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, puerto, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})


def ip_es_publica(ip: IP) -> bool:
    """True solo para direcciones enrutables en Internet."""
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped:               # ::ffff:127.0.0.1
            return ip_es_publica(ip.ipv4_mapped)
        if ip.sixtofour:                 # 2002::/16 encapsula una IPv4
            return ip_es_publica(ip.sixtofour)
        if ip.teredo:                    # túnel que puede apuntar a redes internas
            return False
    # is_global excluye privadas, loopback, enlace local, compartidas (100.64/10),
    # reservadas y no especificadas; multicast se excluye aparte porque Python la
    # considera "global".
    return ip.is_global and not ip.is_multicast


def _como_ip(texto: str) -> Optional[IP]:
    try:
        return ipaddress.ip_address(texto.split("%", 1)[0])   # quita el "%zona" de IPv6
    except ValueError:
        return None


class PoliticaURL:
    """Reglas que debe cumplir una URL antes de que el servidor se conecte a ella."""

    def __init__(self, resolver: Resolver = resolver_dns):
        self.resolver = resolver

    def validar_formato(self, url: str) -> str:
        """Comprobaciones sin red: esquema, estructura, credenciales y nombres locales."""
        url = (url or "").strip()
        try:
            partes = urlsplit(url)
            host, _ = partes.hostname, partes.port      # .port lanza ValueError si es inválido
        except ValueError:
            raise URLNoPermitida(MENSAJE_FORMATO)
        if partes.scheme not in ("http", "https") or not host:
            raise URLNoPermitida(MENSAJE_FORMATO)
        if partes.username is not None or partes.password is not None:
            raise URLNoPermitida(MENSAJE_CREDENCIALES)
        self._validar_host(host)
        return url

    async def ips_permitidas(self, host: str, puerto: int) -> list:
        """Resuelve el host y devuelve sus IP solo si TODAS son públicas."""
        ip_literal = self._validar_host(host)
        if ip_literal is not None:
            return [str(ip_literal)]
        try:
            ips = await self.resolver(host, puerto)
        except (OSError, UnicodeError):
            raise URLNoPermitida(MENSAJE_DNS)
        if not ips:
            raise URLNoPermitida(MENSAJE_DNS)
        for texto in ips:
            ip = _como_ip(texto)
            if ip is None or not ip_es_publica(ip):
                raise URLNoPermitida(MENSAJE_DESTINO)
        return list(ips)

    async def validar(self, url: str) -> str:
        """Validación completa: formato y destino resuelto por DNS."""
        url = self.validar_formato(url)
        partes = urlsplit(url)
        await self.ips_permitidas(partes.hostname, partes.port or (443 if partes.scheme == "https" else 80))
        return url

    @staticmethod
    def _validar_host(host: str) -> Optional[IP]:
        """Rechaza nombres e IP literales no públicos. Devuelve la IP si el host es una IP."""
        nombre = host.lower().rstrip(".")
        ip = _como_ip(nombre)
        if ip is not None:
            if not ip_es_publica(ip):
                raise URLNoPermitida(MENSAJE_DESTINO)
            return ip
        # Nombres de una sola etiqueta ("intranet") o reservados para redes locales.
        if nombre in NOMBRES_LOCALES or nombre.endswith(SUFIJOS_LOCALES) or "." not in nombre:
            raise URLNoPermitida(MENSAJE_DESTINO)
        return None


class BackendRedSeguro(httpcore.AsyncNetworkBackend):
    """Backend de red que valida el destino en el momento de conectar y fija la IP validada."""

    def __init__(self, politica: PoliticaURL, interno: Optional[httpcore.AsyncNetworkBackend] = None):
        self.politica = politica
        self.interno = interno or httpcore.AnyIOBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        ips = await self.politica.ips_permitidas(host, port)
        return await self.interno.connect_tcp(ips[0], port, timeout=timeout,
                                              local_address=local_address, socket_options=socket_options)

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise URLNoPermitida(MENSAJE_DESTINO)

    async def sleep(self, seconds: float) -> None:
        await self.interno.sleep(seconds)


def _transporte_con_ip_fijada(politica: PoliticaURL) -> httpx.AsyncHTTPTransport:
    transporte = httpx.AsyncHTTPTransport()
    # httpx no expone un parámetro para el backend de red; se reemplaza el pool interno
    # (verificado con httpx 0.29 / httpcore 1.0). La prueba de DNS rebinding de
    # tests/test_hu_m01_politica.py detecta si una actualización rompe este reemplazo.
    transporte._pool = httpcore.AsyncConnectionPool(
        ssl_context=httpx.create_ssl_context(), network_backend=BackendRedSeguro(politica))
    return transporte


class TransporteSeguro(httpx.AsyncBaseTransport):
    """Valida cada solicitud (también cada redirección) antes de enviarla."""

    def __init__(self, politica: PoliticaURL, interno: Optional[httpx.AsyncBaseTransport] = None):
        self.politica = politica
        self.interno = interno or _transporte_con_ip_fijada(politica)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await self.politica.validar(str(request.url))
        return await self.interno.handle_async_request(request)

    async def aclose(self) -> None:
        await self.interno.aclose()


politica_por_defecto = PoliticaURL()
