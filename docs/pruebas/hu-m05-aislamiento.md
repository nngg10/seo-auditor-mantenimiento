# Evidencia de pruebas — HU-M05 Aislamiento del acceso a auditorías

- Fecha de ejecución: 2026-11-27 09:09
- Commit base evaluado: `fcdb84c` (rama `feature/HU-M05-aislamiento-auditorias`; el código de la aplicación no cambia en esta historia)
- Configuración: entorno de pruebas con base SQLite temporal (`DB_PATH`), sin servicios externos
- Comando: `python -m pytest tests/test_hu_m05_aislamiento.py --junitxml=...`
- Resultado: **27 de 27 pruebas pasan**

Escenario: la cuenta A tiene una tienda y una auditoría; la cuenta B, independiente, intenta
llegar a esos datos cambiando identificadores. Además, se recorren automáticamente todas las
rutas protegidas con credenciales inválidas (sin token, mal formado, firmado con otra clave,
sin firma, vencido y de un usuario eliminado).

| Criterio | Caso | Resultado | Tiempo |
|---|---|---|---|
| CA-01, CA-02 | B no accede a datos de A — detalle de auditoría | Pasó | 0.43 s |
| CA-01, CA-02 | B no accede a datos de A — reintentar diagnóstico IA | Pasó | 0.41 s |
| CA-01, CA-02 | B no accede a datos de A — exportación PDF | Pasó | 0.41 s |
| CA-01, CA-02 | B no accede a datos de A — historial de la tienda | Pasó | 0.41 s |
| CA-01, CA-02 | B no accede a datos de A — historial filtrado | Pasó | 0.41 s |
| CA-01, CA-02 | B no accede a datos de A — exportación CSV de la tienda | Pasó | 0.42 s |
| CA-01, CA-02 | B no accede a datos de A — editar tienda | Pasó | 0.41 s |
| CA-01, CA-02 | B no accede a datos de A — eliminar tienda | Pasó | 0.41 s |
| CA-01, CA-02 | B no accede a datos de A — auditar tienda ajena | Pasó | 0.43 s |
| CA-02 | Los datos de A siguen intactos tras los intentos de B | Pasó | 0.44 s |
| CA-02 | Los listados y el CSV general de B no incluyen datos de A | Pasó | 0.42 s |
| CA-02 | La propietaria sí accede a todo (control positivo) | Pasó | 0.45 s |
| CA-04 | Auditoría ajena e inexistente son indistinguibles — detalle | Pasó | 0.41 s |
| CA-04 | Auditoría ajena e inexistente son indistinguibles — PDF | Pasó | 0.42 s |
| CA-04 | Tienda ajena e inexistente son indistinguibles | Pasó | 0.42 s |
| CA-03 | El inventario de rutas protegidas está revisado | Pasó | 0.00 s |
| CA-03 | Ruta protegida rechaza credenciales inválidas — `GET /api/auth/yo` | Pasó | 0.22 s |
| CA-03 | Ruta protegida rechaza credenciales inválidas — `GET /api/tiendas` | Pasó | 0.22 s |
| CA-03 | Ruta protegida rechaza credenciales inválidas — `POST /api/tiendas` | Pasó | 0.22 s |
| CA-03 | Ruta protegida rechaza credenciales inválidas — `PUT /api/tiendas/{tienda_id}` | Pasó | 0.22 s |
| CA-03 | Ruta protegida rechaza credenciales inválidas — `DELETE /api/tiendas/{tienda_id}` | Pasó | 0.22 s |
| CA-03 | Ruta protegida rechaza credenciales inválidas — `GET /api/tiendas/{tienda_id}/auditorias` | Pasó | 0.22 s |
| CA-03 | Ruta protegida rechaza credenciales inválidas — `POST /api/auditorias` | Pasó | 0.22 s |
| CA-03 | Ruta protegida rechaza credenciales inválidas — `GET /api/auditorias/{auditoria_id}` | Pasó | 0.22 s |
| CA-03 | Ruta protegida rechaza credenciales inválidas — `POST /api/auditorias/{auditoria_id}/diagnostico` | Pasó | 0.22 s |
| CA-03 | Ruta protegida rechaza credenciales inválidas — `GET /api/auditorias/{auditoria_id}/pdf` | Pasó | 0.22 s |
| CA-03 | Ruta protegida rechaza credenciales inválidas — `GET /api/exportar/auditorias.csv` | Pasó | 0.22 s |

## Pruebas de mutación (comprobación de que las pruebas detectan fallas)

| Falla introducida a propósito | Pruebas que fallaron |
|---|---|
| Detalle de auditoría sin filtrar por propietario | 6 (detalle, diagnóstico, PDF, integridad e indistinguibilidad) |
| Edición de tienda sin comprobar propietario | 2 (editar tienda e integridad de los datos de A) |

En ambos casos se restauró el código y todas las pruebas volvieron a pasar.

**Conclusión:** no se reprodujo ninguna falla de autorización en el código actual; la historia
se mantiene como mantenimiento **preventivo** y estas pruebas quedan como regresión.
