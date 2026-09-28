// Carga las funciones del nodo Code de n8n fuera de n8n y las ejecuta.
// Uso:  node tests/correr_nodo_js.mjs <pedido.json>
// pedido = { datos, fecha_ref, textos_ia: [...] }
// Salida: { metricas, hallazgos, hechos, resumenes: [...], html }

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const fuente = readFileSync(join(ROOT, 'workflows', 'src', 'reporte.js'), 'utf8')
  .replace("'__MODO__'", "'metricas'").replace("'__FUENTE__'", "'demo'").replace('__DATOS__', '{}');
// Solo las funciones: la parte de ejecución usa globals de n8n
const biblioteca = fuente.split('// ── Ejecución en n8n ──')[0] +
  'return { calcular, hallazgos, hechos, verificar, resumenFinal, armarHtml };';
const f = new Function(biblioteca)();

const { datos, fecha_ref: fechaRef, textos_ia: textos } = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const metricas = f.calcular(datos, fechaRef);
const lista = f.hallazgos(metricas);
const resumenes = textos.map((t) => f.resumenFinal(t, metricas, lista));
process.stdout.write(JSON.stringify({
  metricas, hallazgos: lista, hechos: f.hechos(metricas, lista), resumenes,
  html: f.armarHtml(metricas, lista, resumenes[0]),
}));
