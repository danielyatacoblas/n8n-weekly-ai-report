# docs

Material de apoyo del repositorio.

- `reporte_ejemplo.png`: el reporte que genera el workflow de n8n para la semana del 07/09 al 13/09, con un resumen de IA que pasó la verificación de cifras.

## Grabar el video de la demo

1. `docker compose up -d` e importa y activa `workflows/reporte_demo.json` (ver README).
2. Abre en el navegador <http://localhost:5678/webhook/reporte-demo?fecha=2026-09-14>
   y, a un lado, n8n en la pestaña *Executions*.
3. Recorre el reporte: el miércoles en rojo y los hallazgos.
4. Prueba el verificador cambiando la URL:
   - `&texto_ia=Las ventas bajaron 8.6 % y quedaron en S/ 8,078.10.` → aceptado.
   - `&texto_ia=Las ventas fueron S/ 9,999.` → descartado, con el motivo.
5. Guarda el archivo como `docs/video.mp4`. Luego, al editar el README en
   GitHub, arrastra el video donde dice `VIDEO` para que se reproduzca en la página.
