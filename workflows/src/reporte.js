// Nodos Code de n8n: "Calcular métricas" y "Verificar y armar el reporte".
// Espejo en JavaScript de src/reporte.py (misma lógica, misma salida).
// La paridad entre ambos la verifica tests/test_paridad_js.py.
//
// scripts/build_workflow.py fija los marcadores:
//   MODO    'metricas' → lee las hojas y calcula;  'resumen' → verifica el texto
//           de la IA y arma el correo
//   FUENTE  'demo' (datos incluidos en el nodo) o 'sheets' (producción)
//   DATOS_DEMO  data/*.csv comprimidos (solo en la demo)

const MODO = '__MODO__';
const FUENTE = '__FUENTE__';
const DATOS_DEMO = __DATOS__;

const NEGOCIO = 'Tostaduría Selva Alta';
const DIAS = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];
const SEMANAS_HISTORIA = 8;
const UMBRAL_Z = 2;
const META_ROAS = 200;
const META_BOT = 700;
const CAMBIO_RELEVANTE = 100;
const ALZA_GASTO = 200;
const NUMERO = /\d[\d,]*(?:\.\d+)?/g;

// ── números ──

function centimos(v) {
  const t = String(v === null || v === undefined ? '' : v).trim().replace(/,/g, '');
  const m = t.match(/^(-?)(\d+)(?:\.(\d{1,2}))?$/);
  if (!m) return 0;
  const valor = parseInt(m[2], 10) * 100 + parseInt((m[3] || '').padEnd(2, '0'), 10);
  return m[1] ? -valor : valor;
}

function entero(v) {
  const t = String(v === null || v === undefined ? '' : v).trim();
  return /^-?\d+$/.test(t) ? parseInt(t, 10) : 0;
}

function redondear(num, den) {
  const signo = (num < 0) !== (den < 0) ? -1 : 1;
  return signo * Math.floor((2 * Math.abs(num) + Math.abs(den)) / (2 * Math.abs(den)));
}

const miles = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');

function soles(c) {
  const signo = c < 0 ? '-' : '';
  const a = Math.abs(c);
  return `${signo}S/ ${miles(Math.floor(a / 100))}.${String(a % 100).padStart(2, '0')}`;
}

function decimas(d) {
  const signo = d < 0 ? '-' : '';
  return `${signo}${Math.floor(Math.abs(d) / 10)}.${Math.abs(d) % 10}`;
}

const centesimas = (c) => `${Math.floor(c / 100)}.${String(c % 100).padStart(2, '0')}`;

const variacion = (actual, anterior) =>
  anterior === 0 ? null : redondear((actual - anterior) * 1000, anterior);

// ── fechas ──

const dia = (s) => Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10)) / 86400000;
const iso = (n) => new Date(n * 86400000).toISOString().slice(0, 10);

function semanaAnterior(fechaRef) {
  const d = dia(fechaRef);
  const lunes = d - (new Date(d * 86400000).getUTCDay() + 6) % 7;
  return [iso(lunes - 7), iso(lunes - 1)];
}

const ddmm = (f) => `${f.slice(8, 10)}/${f.slice(5, 7)}`;

// ── métricas ──

function en(fila, ini, fin) {
  const f = String(fila.fecha || '').slice(0, 10);
  return ini <= f && f <= fin;
}

function resumenVentas(filas, ini, fin) {
  const sel = filas.filter((f) => en(f, ini, fin));
  const ingresos = sel.reduce((s, f) => s + centimos(f.subtotal), 0);
  const pedidos = new Set(sel.map((f) => String(f.pedido_id))).size;
  return { ingresos, pedidos, ticket: pedidos ? redondear(ingresos, pedidos) : 0 };
}

function ingresosPorDia(filas) {
  const porDia = {};
  for (const f of filas) {
    const k = String(f.fecha || '').slice(0, 10);
    porDia[k] = (porDia[k] || 0) + centimos(f.subtotal);
  }
  return porDia;
}

function calcular(datos, fechaRef) {
  const [ini, fin] = semanaAnterior(fechaRef);
  const [iniA, finA] = [iso(dia(ini) - 7), iso(dia(fin) - 7)];
  const ventas = datos.ventas || [];

  const actual = resumenVentas(ventas, ini, fin);
  const anterior = resumenVentas(ventas, iniA, finA);
  const porDia = ingresosPorDia(ventas);
  const dias = DIAS.map((nombre, i) => ({
    fecha: iso(dia(ini) + i), dia: nombre, ingresos: porDia[iso(dia(ini) + i)] || 0,
  }));

  const productos = {};
  for (const f of ventas) {
    if (!en(f, ini, fin)) continue;
    const k = String(f.producto || f.sku || '?');
    productos[k] = productos[k] || { ingresos: 0, unidades: 0 };
    productos[k].ingresos += centimos(f.subtotal);
    productos[k].unidades += entero(f.cantidad);
  }
  const top = Object.entries(productos)
    .sort((a, b) => (b[1].ingresos - a[1].ingresos) || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))
    .slice(0, 3)
    .map(([producto, v]) => ({ producto, ingresos: v.ingresos, unidades: v.unidades }));

  const pub = (datos.publicidad || []).filter((f) => en(f, ini, fin));
  const pubA = (datos.publicidad || []).filter((f) => en(f, iniA, finA));
  const gasto = pub.reduce((s, f) => s + centimos(f.gasto), 0);
  const gastoA = pubA.reduce((s, f) => s + centimos(f.gasto), 0);

  const conv = (datos.conversaciones || []).filter((f) => en(f, ini, fin));
  const convA = (datos.conversaciones || []).filter((f) => en(f, iniA, finA));
  const atendidas = conv.filter((f) => f.accion !== 'silencio');
  const resueltas = atendidas.filter((f) => f.accion === 'responder' && f.intencion !== 'aclarar');

  const fac = (datos.facturas || []).filter((f) => en(f, ini, fin));
  const registradas = fac.filter((f) => f.estado === 'registrada');

  return {
    semana: { inicio: ini, fin },
    ventas: Object.assign({}, actual, {
      anterior,
      cambio_ingresos: variacion(actual.ingresos, anterior.ingresos),
      cambio_pedidos: variacion(actual.pedidos, anterior.pedidos),
      cambio_ticket: variacion(actual.ticket, anterior.ticket),
      por_dia: dias,
      top,
    }),
    publicidad: {
      gasto, cambio_gasto: variacion(gasto, gastoA),
      clics: pub.reduce((s, f) => s + entero(f.clics), 0),
      roas: gasto ? redondear(actual.ingresos * 100, gasto) : null,
      costo_por_pedido: actual.pedidos ? redondear(gasto, actual.pedidos) : null,
    },
    atencion: {
      conversaciones: conv.length, cambio: variacion(conv.length, convA.length),
      resueltas_bot: resueltas.length,
      tasa_bot: atendidas.length ? redondear(resueltas.length * 1000, atendidas.length) : null,
      derivadas: conv.filter((f) => f.accion === 'derivar').length,
      sin_respuesta: conv.filter((f) => f.intencion === 'aclarar').length,
    },
    facturas: {
      registradas: registradas.length,
      total: registradas.reduce((s, f) => s + centimos(f.total), 0),
      revision: fac.filter((f) => f.estado === 'revision').length,
    },
    anomalias: anomalias(porDia, ini),
  };
}

function anomalias(porDia, ini) {
  const salida = [];
  for (let i = 0; i < 7; i++) {
    const d = dia(ini) + i;
    const x = porDia[iso(d)] || 0;
    const hist = [];
    for (let k = 1; k <= SEMANAS_HISTORIA; k++) hist.push(porDia[iso(d - 7 * k)] || 0);
    const n = hist.length;
    const suma = hist.reduce((s, h) => s + h, 0);
    const dispersion = n * hist.reduce((s, h) => s + h * h, 0) - suma * suma;
    if (dispersion <= 0) continue;
    const z = (x * n - suma) / Math.sqrt(dispersion);
    if (Math.abs(z) >= UMBRAL_Z) {
      salida.push({ fecha: iso(d), dia: DIAS[i], ingresos: x,
                    promedio: redondear(suma, n), tipo: z < 0 ? 'baja' : 'alta' });
    }
  }
  return salida;
}

// ── hallazgos y texto ──

function cambioTexto(c) {
  return c === null ? 'sin dato de la semana anterior'
    : `${c >= 0 ? '+' : ''}${decimas(c)} % frente a la semana anterior`;
}

function hallazgos(m) {
  const { ventas: v, publicidad: pub, atencion: at, facturas: fac } = m;
  const out = [];
  const c = v.cambio_ingresos;
  if (c !== null && Math.abs(c) >= CAMBIO_RELEVANTE) {
    out.push(`Las ventas ${c > 0 ? 'subieron' : 'bajaron'} ${decimas(Math.abs(c))} % ` +
      `frente a la semana anterior (${soles(v.ingresos)} contra ${soles(v.anterior.ingresos)}).`);
  }
  for (const a of m.anomalias) {
    const nivel = a.tipo === 'baja' ? 'por debajo' : 'por encima';
    const extra = a.tipo === 'baja'
      ? ' Conviene revisar si la web o los pagos tuvieron problemas ese día.' : '';
    out.push(`El ${a.dia} ${ddmm(a.fecha)} se vendió ${soles(a.ingresos)}, muy ` +
      `${nivel} de lo normal para un ${a.dia} (promedio ${soles(a.promedio)}).${extra}`);
  }
  const cg = pub.cambio_gasto;
  if (cg !== null && cg >= ALZA_GASTO && (c === null || c <= 0)) {
    out.push(`El gasto en publicidad subió ${decimas(cg)} % (${soles(pub.gasto)}), pero ` +
      `las ventas no acompañaron (${cambioTexto(c)}). Conviene revisar qué campaña cambió.`);
  }
  if (pub.roas !== null && pub.roas < META_ROAS) {
    out.push(`La publicidad devolvió ${centesimas(pub.roas)} soles en ventas por cada ` +
      `sol invertido, por debajo de la meta de ${centesimas(META_ROAS)}.`);
  }
  if (at.tasa_bot !== null && at.tasa_bot < META_BOT) {
    out.push(`El bot resolvió el ${decimas(at.tasa_bot)} % de las consultas, por debajo ` +
      `de la meta de ${decimas(META_BOT)} %.`);
  }
  if (at.sin_respuesta >= 3) {
    out.push(`${at.sin_respuesta} preguntas de clientes no encontraron respuesta en la ` +
      'base del bot: conviene agregarlas a las preguntas frecuentes.');
  }
  if (fac.revision) {
    const varias = fac.revision > 1;
    out.push(`${fac.revision} factura${varias ? 's' : ''} de proveedores ` +
      `${varias ? 'esperan' : 'espera'} revisión.`);
  }
  if (v.top.length) {
    const t = v.top[0];
    out.push(`El producto que más vendió fue ${t.producto}: ${soles(t.ingresos)} ` +
      `en ${t.unidades} unidades.`);
  }
  return out;
}

function hechos(m, lista) {
  const { ventas: v, publicidad: pub, atencion: at, facturas: fac } = m;
  const lineas = [
    `Semana: del ${ddmm(m.semana.inicio)} al ${ddmm(m.semana.fin)}`,
    `Ventas: ${soles(v.ingresos)} (${cambioTexto(v.cambio_ingresos)})`,
    `Pedidos: ${v.pedidos} (${cambioTexto(v.cambio_pedidos)})`,
    `Ticket promedio: ${soles(v.ticket)} (${cambioTexto(v.cambio_ticket)})`,
    `Gasto en publicidad: ${soles(pub.gasto)} (${cambioTexto(pub.cambio_gasto)})`,
  ];
  if (pub.roas !== null) lineas.push(`Ventas por sol invertido en publicidad: ${centesimas(pub.roas)}`);
  if (pub.costo_por_pedido !== null) lineas.push(`Costo de publicidad por pedido: ${soles(pub.costo_por_pedido)}`);
  lineas.push(`Conversaciones con clientes: ${at.conversaciones} (${cambioTexto(at.cambio)})`);
  if (at.tasa_bot !== null) lineas.push(`Resueltas por el bot: ${at.resueltas_bot} (${decimas(at.tasa_bot)} %)`);
  lineas.push(`Derivadas a una persona: ${at.derivadas}`);
  lineas.push(`Facturas registradas: ${fac.registradas} por ${soles(fac.total)}; ` +
    `en revisión: ${fac.revision}`);
  lineas.push('Hallazgos:');
  for (const h of lista) lineas.push(`- ${h}`);
  return lineas.join('\n');
}

function plantilla(m, lista) {
  const v = m.ventas;
  const inicio = `Semana del ${ddmm(m.semana.inicio)} al ${ddmm(m.semana.fin)}: ` +
    `ventas de ${soles(v.ingresos)} en ${v.pedidos} pedidos.`;
  return [inicio].concat(lista.slice(0, 3)).join(' ');
}

// ── verificación del texto de la IA ──

function normalizarNumero(n) {
  const s = n.replace(/,/g, '');
  const punto = s.indexOf('.');
  let entera = punto === -1 ? s : s.slice(0, punto);
  let dec = punto === -1 ? '' : s.slice(punto + 1);
  entera = entera.replace(/^0+/, '') || '0';
  dec = dec.replace(/0+$/, '');
  return dec ? `${entera}.${dec}` : entera;
}

function verificar(texto, base) {
  const permitidas = new Set((base.match(NUMERO) || []).map(normalizarNumero));
  for (let i = 0; i <= 10; i++) permitidas.add(String(i));
  const ajenas = [];
  for (const n of ((texto || '').match(NUMERO) || [])) {
    if (!permitidas.has(normalizarNumero(n)) && !ajenas.includes(n)) ajenas.push(n);
  }
  return { ok: Boolean((texto || '').trim()) && !ajenas.length, cifras_ajenas: ajenas };
}

function resumenFinal(textoIa, m, lista) {
  const base = hechos(m, lista);
  if (textoIa === null || textoIa === undefined) {
    return { texto: plantilla(m, lista), origen: 'plantilla',
             motivo: 'la IA no respondió', cifras_ajenas: [] };
  }
  const v = verificar(textoIa, base);
  if (v.ok) return { texto: textoIa.trim(), origen: 'ia', motivo: '', cifras_ajenas: [] };
  const motivo = !v.cifras_ajenas.length ? 'la IA devolvió un texto vacío'
    : 'la IA mencionó cifras que no están en los datos: ' + v.cifras_ajenas.join(', ');
  return { texto: plantilla(m, lista), origen: 'plantilla', motivo, cifras_ajenas: v.cifras_ajenas };
}

// ── correo HTML (tablas y estilos en línea: es lo que entienden los clientes de correo) ──

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
  .replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function armarHtml(m, lista, resumen) {
  const { ventas: v, publicidad: pub, atencion: at } = m;
  // invertir: en publicidad, gastar más es la mala noticia
  const color = (c, invertir) => c === null || c === 0 ? '#6b7480'
    : (c > 0) !== invertir ? '#1f8a4c' : '#b3261e';
  const kpi = (titulo, valor, c, invertir = false) => `
    <td style="padding:12px;border:1px solid #e3e6ea;border-radius:8px;width:20%;vertical-align:top">
      <div style="font-size:12px;color:#6b7480">${esc(titulo)}</div>
      <div style="font-size:20px;font-weight:700;margin:4px 0">${esc(valor)}</div>
      <div style="font-size:12px;color:${color(c, invertir)}">${c === null ? 'sin dato previo'
        : esc((c >= 0 ? '+' : '') + decimas(c) + ' %')}</div>
    </td>`;
  const maximo = Math.max(1, ...v.por_dia.map((d) => d.ingresos));
  const raros = new Set(m.anomalias.map((a) => a.fecha));
  const barras = v.por_dia.map((d) => {
    const ancho = Math.max(1, Math.round((d.ingresos / maximo) * 100));
    const fondo = raros.has(d.fecha) ? '#b3261e' : '#7a4b2a';
    return `<tr>
      <td style="padding:3px 8px 3px 0;font-size:13px;width:90px">${esc(d.dia)} ${esc(ddmm(d.fecha))}</td>
      <td style="padding:3px 0"><div style="background:${fondo};height:14px;width:${ancho}%;border-radius:3px"></div></td>
      <td style="padding:3px 0 3px 8px;font-size:13px;text-align:right;width:110px">${esc(soles(d.ingresos))}</td>
    </tr>`;
  }).join('');
  const nota = resumen.origen === 'ia'
    ? 'Redactado por IA y verificado: todas las cifras coinciden con los datos.'
    : `Resumen automático (${esc(resumen.motivo)}).`;
  const top = v.top.map((t) => `<tr>
      <td style="padding:4px 0;font-size:13px">${esc(t.producto)}</td>
      <td style="padding:4px 0;font-size:13px;text-align:right">${t.unidades} u.</td>
      <td style="padding:4px 0;font-size:13px;text-align:right">${esc(soles(t.ingresos))}</td></tr>`).join('');

  return `<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Reporte semanal</title></head>
<body style="margin:0;background:#f3f4f6;font-family:Arial,Helvetica,sans-serif;color:#1c2530">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:20px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:680px;background:#ffffff;border-radius:12px;padding:24px">
<tr><td>
  <div style="font-size:12px;color:#6b7480;text-transform:uppercase;letter-spacing:.05em">Reporte semanal · ${esc(NEGOCIO)}</div>
  <h1 style="font-size:22px;margin:4px 0 16px">Semana del ${esc(ddmm(m.semana.inicio))} al ${esc(ddmm(m.semana.fin))}</h1>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="6"><tr>
    ${kpi('Ventas', soles(v.ingresos), v.cambio_ingresos)}
    ${kpi('Pedidos', String(v.pedidos), v.cambio_pedidos)}
    ${kpi('Ticket promedio', soles(v.ticket), v.cambio_ticket)}
    ${kpi('Publicidad', soles(pub.gasto), pub.cambio_gasto, true)}
    ${kpi('Conversaciones', String(at.conversaciones), at.cambio)}
  </tr></table>
  <p style="font-size:11px;color:#6b7480;margin:4px 6px 18px">En publicidad, el rojo indica que se gastó más que la semana anterior.</p>
  <h2 style="font-size:15px;margin:0 0 8px">Resumen</h2>
  <p style="font-size:14px;line-height:1.5;margin:0 0 4px">${esc(resumen.texto)}</p>
  <p style="font-size:11px;color:#6b7480;margin:0 0 18px">${nota}</p>
  <h2 style="font-size:15px;margin:0 0 8px">Lo que hay que saber</h2>
  <ul style="font-size:14px;line-height:1.5;margin:0 0 18px;padding-left:20px">
    ${lista.map((h) => `<li style="margin-bottom:6px">${esc(h)}</li>`).join('')}
  </ul>
  <h2 style="font-size:15px;margin:0 0 8px">Ventas por día</h2>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:18px">${barras}</table>
  <h2 style="font-size:15px;margin:0 0 8px">Productos más vendidos</h2>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:18px">${top}</table>
  <p style="font-size:11px;color:#6b7480;margin:0">Generado automáticamente con n8n a partir de la tienda,
  el bot de atención, las facturas y la publicidad. Semana del lunes al domingo.</p>
</td></tr></table></td></tr></table></body></html>`;
}

function textoCorto(m, resumen) {
  return `Reporte semanal ${ddmm(m.semana.inicio)}–${ddmm(m.semana.fin)} · ${NEGOCIO}\n\n` +
    resumen.texto + '\n\nEl detalle completo llegó por correo.';
}

// ── Ejecución en n8n ──

function desdeTabla(t) {
  return t.filas.map((f) => Object.fromEntries(t.columnas.map((c, i) => [c, f[i]])));
}

function leerDatos() {
  if (FUENTE === 'demo') {
    return Object.fromEntries(Object.entries(DATOS_DEMO).map(([k, t]) => [k, desdeTabla(t)]));
  }
  const hoja = (nombre) => $(nombre).all().map((i) => i.json);
  return {
    ventas: hoja('Sheets · Ventas'),
    publicidad: hoja('Sheets · Publicidad'),
    conversaciones: hoja('Sheets · Conversaciones'),
    facturas: hoja('Sheets · Facturas'),
  };
}

if (MODO === 'metricas') {
  // En la demo la fecha se puede pedir por la URL (?fecha=2026-09-14)
  const query = FUENTE === 'demo' ? ($input.first().json.query || {}) : {};
  const fechaRef = /^\d{4}-\d{2}-\d{2}$/.test(query.fecha || '') ? query.fecha : $now.toISODate();
  const m = calcular(leerDatos(), fechaRef);
  const lista = hallazgos(m);
  return [{ json: { metricas: m, hallazgos: lista, hechos: hechos(m, lista),
                    texto_ia_demo: FUENTE === 'demo' ? (query.texto_ia ?? null) : null } }];
}

// MODO 'resumen': llega la salida de la IA (o su error) y se verifica
const base = $('Calcular métricas').first().json;
const entrada = $input.first().json;
const textoIa = FUENTE === 'demo' ? base.texto_ia_demo
  : (typeof entrada.text === 'string' ? entrada.text : null);
const resumen = resumenFinal(textoIa, base.metricas, base.hallazgos);
return [{ json: {
  semana: base.metricas.semana,
  resumen,
  html: armarHtml(base.metricas, base.hallazgos, resumen),
  telegram: textoCorto(base.metricas, resumen),
  asunto: `Reporte semanal ${ddmm(base.metricas.semana.inicio)}–${ddmm(base.metricas.semana.fin)}: ` +
    `${soles(base.metricas.ventas.ingresos)} en ventas`,
  fila: {
    semana: base.metricas.semana.inicio,
    ventas: centesimas(base.metricas.ventas.ingresos),
    pedidos: base.metricas.ventas.pedidos,
    gasto_publicidad: centesimas(base.metricas.publicidad.gasto),
    hallazgos: base.hallazgos.length,
    resumen_por: resumen.origen,
    motivo: resumen.motivo,
  },
} }];
