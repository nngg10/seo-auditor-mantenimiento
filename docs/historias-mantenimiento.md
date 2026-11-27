# Historias de usuario de mantenimiento

Registro de las cinco intervenciones de mantenimiento sobre el auditor SEO y PageSpeed con IA.
Línea base: commit `7be7c41` (proyecto original `nngg10/seo-pagespeed-ai-auditor`).
Cada historia tiene su issue en GitHub, donde se actualiza su estado.

| Historia | Issue | Tipo | Rama | Estado |
|---|---|---|---|---|
| HU-M01 Validación segura de direcciones de auditoría | [#1](https://github.com/nngg10/seo-auditor-mantenimiento/issues/1) | preventivo, correctivo | `feature/HU-M01-validacion-url` | Pendiente |
| HU-M02 Identificación del estado de los servicios externos | [#2](https://github.com/nngg10/seo-auditor-mantenimiento/issues/2) | perfectivo | `feature/HU-M02-estado-servicios` | Pendiente |
| HU-M03 Filtrado del historial de auditorías | [#3](https://github.com/nngg10/seo-auditor-mantenimiento/issues/3) | perfectivo | `feature/HU-M03-filtro-historial` | Pendiente |
| HU-M04 Exportación de resultados en CSV | [#4](https://github.com/nngg10/seo-auditor-mantenimiento/issues/4) | perfectivo | `feature/HU-M04-exportacion-csv` | Pendiente |
| HU-M05 Aislamiento del acceso a auditorías | [#5](https://github.com/nngg10/seo-auditor-mantenimiento/issues/5) | preventivo | `feature/HU-M05-aislamiento-auditorias` | Pendiente |

## HU-M01. Validación segura de direcciones de auditoría

**Historia.** Como usuario del auditor, quiero recibir una validación segura de la dirección ingresada para evitar análisis de destinos no permitidos y obtener mensajes comprensibles cuando una URL sea rechazada.

**Clasificación.** Mantenimiento preventivo. La inspección inicial confirmó un comportamiento defectuoso (ver abajo), por lo que también se registra su componente correctivo.

### Criterios de aceptación
- [ ] **CA-01.** Las solicitudes de auditoría admiten únicamente direcciones con esquema HTTP o HTTPS y estructura válida.
- [ ] **CA-02.** Se rechazan destinos locales, privados, de enlace local y otros destinos no públicos según la política definida.
- [ ] **CA-03.** Las redirecciones se someten a la misma validación antes de realizar una nueva conexión.
- [ ] **CA-04.** El rechazo no interrumpe la sesión ni expone detalles internos de la aplicación.
- [ ] **CA-05.** Se incluyen pruebas de direcciones válidas, formatos incorrectos, destinos restringidos y redirecciones hacia destinos restringidos.

### Comportamiento actual (inspección inicial sobre el commit `7be7c41`)
- `normalizar_url` (`app/api.py`) solo comprueba el esquema `http/https` y que el dominio tenga un punto o sea `localhost`; acepta `http://localhost`, `http://127.0.0.1` y direcciones privadas como `http://192.168.1.1`.
- `WebScraper.analizar` (`app/services/scraper.py`) usa `follow_redirects=True`: las redirecciones se siguen sin validar el nuevo destino.
- No hay resolución DNS ni comprobación de la IP de destino antes de conectar.

### Componentes afectados
- `app/api.py` (normalizar_url)
- `app/services/scraper.py` (WebScraper)
- Nuevo módulo de política de URL
- `tests/`

### Pruebas previstas
- [ ] URL pública válida → se audita
- [ ] `ftp://`, texto sin esquema → rechazo 422
- [ ] `localhost`, `127.0.0.1`, `10.x`, `192.168.x`, `169.254.169.254`, IPv6 local → rechazo
- [ ] Dominio que resuelve a IP privada → rechazo
- [ ] Redirección hacia IP privada → rechazo sin conectar
- [ ] El mensaje de error no incluye trazas ni IP internas

### Trazabilidad
- Rama: `feature/HU-M01-validacion-url` (se crea desde `develop`)
- Responsable: _por asignar_
- Revisor: _por asignar_
- Estado: **pendiente**


## HU-M02. Identificación del estado de los servicios externos

**Historia.** Como analista de comercio electrónico, quiero distinguir qué servicios respondieron y cuáles fallaron para interpretar correctamente una auditoría parcial.

**Clasificación.** Mantenimiento perfectivo de la información presentada al usuario.

### Criterios de aceptación
- [ ] **CA-01.** El resultado muestra por separado el estado del análisis HTML, PageSpeed y el diagnóstico de IA.
- [ ] **CA-02.** Un servicio fallido no se representa como un resultado satisfactorio ni como un puntaje real de cero.
- [ ] **CA-03.** La interfaz diferencia un diagnóstico generado por IA de uno obtenido mediante reglas locales.
- [ ] **CA-04.** El informe PDF conserva las advertencias sobre resultados parciales.
- [ ] **CA-05.** Las pruebas simulan respuestas satisfactorias, errores y tiempos de espera agotados.

### Comportamiento actual (inspección inicial sobre el commit `7be7c41`)
- Ya existe parcialmente: si PageSpeed falla se guarda `pagespeed_error` y las tarjetas muestran «N/D»; si la IA falla se usa el motor de reglas local con `ia_aviso` y botón de reintento.
- No hay un bloque que muestre el estado de los tres servicios por separado.
- El PDF incluye el error de PageSpeed y la fuente del plan, pero no el aviso de la IA (`ia_aviso`).
- No existen pruebas automatizadas que simulen fallos de los servicios.

### Componentes afectados
- `app/services/auditor.py`
- `app/api.py`
- `app/static/app.js`
- `app/services/pdf_report.py`
- `tests/`

### Pruebas previstas
- [ ] Los tres servicios responden → tres estados «OK»
- [ ] PageSpeed con error 429 → estado «falló» y tarjetas N/D, nunca 0
- [ ] Tiempo agotado en PageSpeed → estado «falló»
- [ ] IA con error → estado «respaldo local» y aviso
- [ ] PDF de auditoría parcial contiene las advertencias

### Trazabilidad
- Rama: `feature/HU-M02-estado-servicios` (se crea desde `develop`)
- Responsable: _por asignar_
- Revisor: _por asignar_
- Estado: **pendiente**


## HU-M03. Filtrado del historial de auditorías

**Historia.** Como analista, quiero filtrar las auditorías de una tienda por intervalo de fechas para localizar resultados relevantes sin recorrer todo el historial.

**Clasificación.** Mantenimiento perfectivo.

### Criterios de aceptación
- [ ] **CA-01.** El usuario puede establecer fecha inicial y fecha final.
- [ ] **CA-02.** El sistema rechaza intervalos cuya fecha inicial sea posterior a la final.
- [ ] **CA-03.** Los resultados incluyen únicamente auditorías de tiendas autorizadas para el usuario.
- [ ] **CA-04.** El resultado conserva el orden de la más reciente a la más antigua.
- [ ] **CA-05.** Cuando no existen coincidencias, se presenta un mensaje de estado vacío y una opción para limpiar el filtro.

### Comportamiento actual (inspección inicial sobre el commit `7be7c41`)
- No existe. `GET /api/tiendas/{id}/auditorias` devuelve siempre el historial completo y la vista de historial no tiene controles de filtro.

### Componentes afectados
- `app/api.py` (historial)
- `app/models.py` (AuditoriaRepositorio)
- `app/static/app.js` (vista historial)
- `tests/`

### Pruebas previstas
- [ ] Intervalo con auditorías → solo las del rango, ordenadas de reciente a antigua
- [ ] Fecha inicial > final → rechazo 422
- [ ] Intervalo sin coincidencias → estado vacío + «Limpiar filtro»
- [ ] Tienda de otro usuario → 404
- [ ] Sin filtro → historial completo (regresión)

### Trazabilidad
- Rama: `feature/HU-M03-filtro-historial` (se crea desde `develop`)
- Responsable: _por asignar_
- Revisor: _por asignar_
- Estado: **pendiente**


## HU-M04. Exportación de resultados en CSV

**Historia.** Como responsable de una tienda, quiero descargar los resultados de mis auditorías en un archivo CSV para analizarlos en una hoja de cálculo.

**Clasificación.** Mantenimiento perfectivo de interoperabilidad.

### Criterios de aceptación
- [ ] **CA-01.** El archivo contiene encabezados y campos definidos: tienda, URL, fecha, puntaje SEO y puntaje de rendimiento.
- [ ] **CA-02.** Los valores no disponibles permanecen identificados como ausentes y no se convierten en puntajes inventados.
- [ ] **CA-03.** La descarga contiene únicamente auditorías autorizadas para el usuario autenticado.
- [ ] **CA-04.** Las comas, comillas y caracteres acentuados se exportan correctamente.
- [ ] **CA-05.** Los campos de texto potencialmente interpretables como fórmulas reciben un tratamiento seguro para su apertura en hojas de cálculo.

### Comportamiento actual (inspección inicial sobre el commit `7be7c41`)
- No existe. La única exportación disponible es el PDF de una auditoría individual.

### Componentes afectados
- `app/api.py` (nueva ruta de descarga)
- Nuevo servicio de exportación CSV
- `app/static/app.js` (botón de descarga)
- `tests/`

### Pruebas previstas
- [ ] CSV con encabezados correctos
- [ ] Rendimiento no disponible → celda vacía, no 0
- [ ] Nombre de tienda con comas, comillas y tildes → se abre bien en Excel
- [ ] Nombre que empieza por `=`, `+`, `-` o `@` → neutralizado
- [ ] Usuario sin permiso → no recibe auditorías ajenas

### Trazabilidad
- Rama: `feature/HU-M04-exportacion-csv` (se crea desde `develop`)
- Responsable: _por asignar_
- Revisor: _por asignar_
- Estado: **pendiente**


## HU-M05. Aislamiento del acceso a auditorías

**Historia.** Como propietario de una tienda, quiero que mis auditorías y archivos exportados sean accesibles únicamente desde mi cuenta para proteger la información de mi negocio.

**Clasificación.** Mantenimiento preventivo y fortalecimiento de pruebas. Solo se clasificará como correctivo si se reproduce una falla de autorización.

### Criterios de aceptación
- [ ] **CA-01.** Un usuario no puede consultar auditorías de otra cuenta modificando identificadores.
- [ ] **CA-02.** La restricción se aplica al detalle, historial, exportación PDF y nueva exportación CSV.
- [ ] **CA-03.** Las rutas protegidas rechazan solicitudes sin autenticación válida.
- [ ] **CA-04.** Las respuestas no revelan información de la cuenta ajena.
- [ ] **CA-05.** Se automatizan pruebas con dos cuentas independientes y se conserva evidencia del resultado.

### Comportamiento actual (inspección inicial sobre el commit `7be7c41`)
- La inspección inicial indica que las consultas ya filtran por usuario: `AuditoriaRepositorio.obtener` une con `tiendas.usuario_id` y `TiendaRepositorio.obtener` filtra por `usuario_id`; las rutas devuelven 404 para recursos ajenos.
- No existen pruebas automatizadas que lo demuestren; debe verificarse con dos cuentas antes de cerrar la historia.

### Componentes afectados
- `app/models.py` (repositorios)
- `app/api.py` (rutas protegidas)
- `app/security.py`
- `tests/`

### Pruebas previstas
- [ ] Usuario B pide detalle, historial y PDF de auditoría de A → 404
- [ ] Usuario B exporta CSV → solo sus datos
- [ ] Sin token, token inválido y token vencido → 401
- [ ] El cuerpo del 404 no menciona datos de A

### Trazabilidad
- Rama: `feature/HU-M05-aislamiento-auditorias` (se crea desde `develop`)
- Responsable: _por asignar_
- Revisor: _por asignar_
- Estado: **pendiente**
