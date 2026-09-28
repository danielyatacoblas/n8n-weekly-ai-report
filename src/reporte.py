"""Métricas, hallazgos y verificación del resumen del reporte semanal.

Es la misma lógica que corre en los nodos Code de n8n
(workflows/src/reporte.js); tests/test_paridad_js.py verifica que ambas copias
den el mismo resultado.

Todo se calcula con enteros (céntimos, décimas de porcentaje, centésimas de
ROAS). Así Python y JavaScript redondean igual y el verificador de cifras
compara exactamente los mismos textos.
"""
from __future__ import annotations

import math
import re
from datetime import date

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
SEMANAS_HISTORIA = 8        # semanas previas para saber qué es "normal" en cada día
UMBRAL_Z = 2                # desvíos estándar para marcar un día como fuera de lo normal
META_ROAS = 200             # 2.00 soles vendidos por sol invertido en publicidad
META_BOT = 700              # 70.0 % de consultas resueltas por el bot
CAMBIO_RELEVANTE = 100      # 10.0 % de variación en ventas
ALZA_GASTO = 200            # 20.0 % más de gasto en publicidad
NUMERO = r"\d[\d,]*(?:\.\d+)?"


# ── números ────────────────────────────────────────────────────────────────

def centimos(v) -> int:
    """'1,234.5' o 1234.5 → 123450. Lo que no es un monto vale 0."""
    t = str(v if v is not None else "").strip().replace(",", "")
    m = re.fullmatch(r"(-?)(\d+)(?:\.(\d{1,2}))?", t)
    if not m:
        return 0
    valor = int(m.group(2)) * 100 + int((m.group(3) or "").ljust(2, "0"))
    return -valor if m.group(1) else valor


def entero(v) -> int:
    t = str(v if v is not None else "").strip()
    return int(t) if re.fullmatch(r"-?\d+", t) else 0


def redondear(num: int, den: int) -> int:
    """num / den redondeado al entero más cercano, alejándose de cero en .5."""
    signo = -1 if (num < 0) != (den < 0) else 1
    return signo * ((2 * abs(num) + abs(den)) // (2 * abs(den)))


def miles(n: int) -> str:
    return f"{n:,}"


def soles(c: int) -> str:
    signo = "-" if c < 0 else ""
    c = abs(c)
    return f"{signo}S/ {miles(c // 100)}.{c % 100:02d}"


def decimas(d: int) -> str:
    """125 → '12.5'."""
    signo = "-" if d < 0 else ""
    return f"{signo}{abs(d) // 10}.{abs(d) % 10}"


def centesimas(c: int) -> str:
    return f"{c // 100}.{c % 100:02d}"


def variacion(actual: int, anterior: int):
    """Cambio en décimas de porcentaje, o None si antes era 0."""
    return None if anterior == 0 else redondear((actual - anterior) * 1000, anterior)


# ── fechas ─────────────────────────────────────────────────────────────────

def dia(iso: str) -> int:
    return date.fromisoformat(iso).toordinal()


def iso(ordinal: int) -> str:
    return date.fromordinal(ordinal).isoformat()


def semana_anterior(fecha_ref: str) -> tuple[str, str]:
    """Lunes a domingo de la semana anterior a la fecha de referencia."""
    d = dia(fecha_ref)
    lunes = d - date.fromordinal(d).weekday()
    return iso(lunes - 7), iso(lunes - 1)


def ddmm(fecha: str) -> str:
    return f"{fecha[8:10]}/{fecha[5:7]}"


# ── métricas ───────────────────────────────────────────────────────────────

def _en(fila: dict, ini: str, fin: str) -> bool:
    f = str(fila.get("fecha") or "")[:10]
    return ini <= f <= fin


def _ventas(filas, ini, fin):
    sel = [f for f in filas if _en(f, ini, fin)]
    ingresos = sum(centimos(f.get("subtotal")) for f in sel)
    pedidos = len({str(f.get("pedido_id")) for f in sel})
    return {"ingresos": ingresos, "pedidos": pedidos,
            "ticket": redondear(ingresos, pedidos) if pedidos else 0}


def _ingresos_por_dia(filas) -> dict:
    por_dia: dict = {}
    for f in filas:
        k = str(f.get("fecha") or "")[:10]
        por_dia[k] = por_dia.get(k, 0) + centimos(f.get("subtotal"))
    return por_dia


def calcular(datos: dict, fecha_ref: str) -> dict:
    ini, fin = semana_anterior(fecha_ref)
    ini_a, fin_a = iso(dia(ini) - 7), iso(dia(fin) - 7)
    ventas = datos.get("ventas") or []

    actual, anterior = _ventas(ventas, ini, fin), _ventas(ventas, ini_a, fin_a)
    por_dia = _ingresos_por_dia(ventas)
    dias = [{"fecha": iso(dia(ini) + i), "dia": DIAS[i],
             "ingresos": por_dia.get(iso(dia(ini) + i), 0)} for i in range(7)]

    productos: dict = {}
    for f in ventas:
        if _en(f, ini, fin):
            p = productos.setdefault(str(f.get("producto") or f.get("sku") or "?"),
                                     {"ingresos": 0, "unidades": 0})
            p["ingresos"] += centimos(f.get("subtotal"))
            p["unidades"] += entero(f.get("cantidad"))
    top = sorted(productos.items(), key=lambda kv: (-kv[1]["ingresos"], kv[0]))[:3]

    pub = [f for f in datos.get("publicidad") or [] if _en(f, ini, fin)]
    pub_a = [f for f in datos.get("publicidad") or [] if _en(f, ini_a, fin_a)]
    gasto = sum(centimos(f.get("gasto")) for f in pub)
    gasto_a = sum(centimos(f.get("gasto")) for f in pub_a)

    conv = [f for f in datos.get("conversaciones") or [] if _en(f, ini, fin)]
    conv_a = [f for f in datos.get("conversaciones") or [] if _en(f, ini_a, fin_a)]
    atendidas = [f for f in conv if f.get("accion") != "silencio"]
    resueltas = [f for f in atendidas
                 if f.get("accion") == "responder" and f.get("intencion") != "aclarar"]

    fac = [f for f in datos.get("facturas") or [] if _en(f, ini, fin)]
    registradas = [f for f in fac if f.get("estado") == "registrada"]

    return {
        "semana": {"inicio": ini, "fin": fin},
        "ventas": dict(actual, anterior=anterior,
                       cambio_ingresos=variacion(actual["ingresos"], anterior["ingresos"]),
                       cambio_pedidos=variacion(actual["pedidos"], anterior["pedidos"]),
                       cambio_ticket=variacion(actual["ticket"], anterior["ticket"]),
                       por_dia=dias,
                       top=[{"producto": k, **v} for k, v in top]),
        "publicidad": {
            "gasto": gasto, "cambio_gasto": variacion(gasto, gasto_a),
            "clics": sum(entero(f.get("clics")) for f in pub),
            "roas": redondear(actual["ingresos"] * 100, gasto) if gasto else None,
            "costo_por_pedido": redondear(gasto, actual["pedidos"]) if actual["pedidos"] else None,
        },
        "atencion": {
            "conversaciones": len(conv), "cambio": variacion(len(conv), len(conv_a)),
            "resueltas_bot": len(resueltas),
            "tasa_bot": redondear(len(resueltas) * 1000, len(atendidas)) if atendidas else None,
            "derivadas": sum(1 for f in conv if f.get("accion") == "derivar"),
            "sin_respuesta": sum(1 for f in conv if f.get("intencion") == "aclarar"),
        },
        "facturas": {"registradas": len(registradas),
                     "total": sum(centimos(f.get("total")) for f in registradas),
                     "revision": sum(1 for f in fac if f.get("estado") == "revision")},
        "anomalias": anomalias(por_dia, ini),
    }


def anomalias(por_dia: dict, ini: str) -> list[dict]:
    """Días de la semana que se salen de lo normal para ese día de la semana.

    Compara cada día con el mismo día de las 8 semanas anteriores (un martes
    con un martes) usando el puntaje z: cuántos desvíos estándar se aleja del
    promedio. Todo con sumas enteras; la raíz cuadrada es la única operación
    con decimales y da el mismo resultado en Python y en JavaScript.
    """
    salida = []
    for i in range(7):
        d = dia(ini) + i
        x = por_dia.get(iso(d), 0)
        hist = [por_dia.get(iso(d - 7 * k), 0) for k in range(1, SEMANAS_HISTORIA + 1)]
        n, suma = len(hist), sum(hist)
        dispersion = n * sum(h * h for h in hist) - suma * suma
        if dispersion <= 0:
            continue
        z = (x * n - suma) / math.sqrt(dispersion)
        if abs(z) >= UMBRAL_Z:
            salida.append({"fecha": iso(d), "dia": DIAS[i], "ingresos": x,
                           "promedio": redondear(suma, n),
                           "tipo": "baja" if z < 0 else "alta"})
    return salida


# ── hallazgos y texto ──────────────────────────────────────────────────────

def hallazgos(m: dict) -> list[str]:
    """Lo que el dueño debería saber, en orden de importancia. Reglas fijas."""
    v, pub, at, fac = m["ventas"], m["publicidad"], m["atencion"], m["facturas"]
    out = []
    c = v["cambio_ingresos"]
    if c is not None and abs(c) >= CAMBIO_RELEVANTE:
        out.append(f"Las ventas {'subieron' if c > 0 else 'bajaron'} {decimas(abs(c))} % "
                   f"frente a la semana anterior ({soles(v['ingresos'])} contra "
                   f"{soles(v['anterior']['ingresos'])}).")
    for a in m["anomalias"]:
        nivel = "por debajo" if a["tipo"] == "baja" else "por encima"
        extra = (" Conviene revisar si la web o los pagos tuvieron problemas ese día."
                 if a["tipo"] == "baja" else "")
        out.append(f"El {a['dia']} {ddmm(a['fecha'])} se vendió {soles(a['ingresos'])}, muy "
                   f"{nivel} de lo normal para un {a['dia']} (promedio {soles(a['promedio'])}).{extra}")
    cg = pub["cambio_gasto"]
    if cg is not None and cg >= ALZA_GASTO and (c is None or c <= 0):
        out.append(f"El gasto en publicidad subió {decimas(cg)} % ({soles(pub['gasto'])}), pero "
                   f"las ventas no acompañaron ({_cambio(c)}). Conviene revisar qué campaña cambió.")
    if pub["roas"] is not None and pub["roas"] < META_ROAS:
        out.append(f"La publicidad devolvió {centesimas(pub['roas'])} soles en ventas por cada "
                   f"sol invertido, por debajo de la meta de {centesimas(META_ROAS)}.")
    if at["tasa_bot"] is not None and at["tasa_bot"] < META_BOT:
        out.append(f"El bot resolvió el {decimas(at['tasa_bot'])} % de las consultas, por debajo "
                   f"de la meta de {decimas(META_BOT)} %.")
    if at["sin_respuesta"] >= 3:
        out.append(f"{at['sin_respuesta']} preguntas de clientes no encontraron respuesta en la "
                   "base del bot: conviene agregarlas a las preguntas frecuentes.")
    if fac["revision"]:
        out.append(f"{fac['revision']} factura{'s' if fac['revision'] > 1 else ''} de "
                   f"proveedores {'esperan' if fac['revision'] > 1 else 'espera'} revisión.")
    if v["top"]:
        t = v["top"][0]
        out.append(f"El producto que más vendió fue {t['producto']}: {soles(t['ingresos'])} "
                   f"en {t['unidades']} unidades.")
    return out


def _cambio(c) -> str:
    return "sin dato de la semana anterior" if c is None else \
        f"{'+' if c >= 0 else ''}{decimas(c)} % frente a la semana anterior"


def hechos(m: dict, lista: list[str]) -> str:
    """Los datos que recibe la IA. Es también la lista de cifras permitidas."""
    v, pub, at, fac = m["ventas"], m["publicidad"], m["atencion"], m["facturas"]
    lineas = [
        f"Semana: del {ddmm(m['semana']['inicio'])} al {ddmm(m['semana']['fin'])}",
        f"Ventas: {soles(v['ingresos'])} ({_cambio(v['cambio_ingresos'])})",
        f"Pedidos: {v['pedidos']} ({_cambio(v['cambio_pedidos'])})",
        f"Ticket promedio: {soles(v['ticket'])} ({_cambio(v['cambio_ticket'])})",
        f"Gasto en publicidad: {soles(pub['gasto'])} ({_cambio(pub['cambio_gasto'])})",
    ]
    if pub["roas"] is not None:
        lineas.append(f"Ventas por sol invertido en publicidad: {centesimas(pub['roas'])}")
    if pub["costo_por_pedido"] is not None:
        lineas.append(f"Costo de publicidad por pedido: {soles(pub['costo_por_pedido'])}")
    lineas.append(f"Conversaciones con clientes: {at['conversaciones']} ({_cambio(at['cambio'])})")
    if at["tasa_bot"] is not None:
        lineas.append(f"Resueltas por el bot: {at['resueltas_bot']} ({decimas(at['tasa_bot'])} %)")
    lineas.append(f"Derivadas a una persona: {at['derivadas']}")
    lineas.append(f"Facturas registradas: {fac['registradas']} por {soles(fac['total'])}; "
                  f"en revisión: {fac['revision']}")
    lineas.append("Hallazgos:")
    lineas += [f"- {h}" for h in lista]
    return "\n".join(lineas)


def plantilla(m: dict, lista: list[str]) -> str:
    """Resumen sin IA: se usa cuando la IA falla o menciona una cifra que no existe."""
    v = m["ventas"]
    inicio = (f"Semana del {ddmm(m['semana']['inicio'])} al {ddmm(m['semana']['fin'])}: "
              f"ventas de {soles(v['ingresos'])} en {v['pedidos']} pedidos.")
    return " ".join([inicio] + lista[:3])


# ── verificación del texto de la IA ────────────────────────────────────────

def normalizar_numero(n: str) -> str:
    """'1,234.50' → '1234.5'; '07' → '7'. Así se comparan cifras escritas distinto."""
    s = n.replace(",", "")
    entera, _, dec = s.partition(".")
    entera = entera.lstrip("0") or "0"
    dec = dec.rstrip("0")
    return f"{entera}.{dec}" if dec else entera


def verificar(texto: str, base: str) -> dict:
    """Toda cifra del texto de la IA debe aparecer en los datos que se le dieron.

    Se permiten además los números del 0 al 10, que aparecen al redactar
    ("los 7 días", "3 productos") sin ser datos del negocio.
    """
    permitidas = {normalizar_numero(n) for n in re.findall(NUMERO, base)}
    permitidas |= {str(i) for i in range(11)}
    ajenas = []
    for n in re.findall(NUMERO, texto or ""):
        k = normalizar_numero(n)
        if k not in permitidas and n not in ajenas:
            ajenas.append(n)
    return {"ok": bool((texto or "").strip()) and not ajenas, "cifras_ajenas": ajenas}


def resumen_final(texto_ia: str | None, m: dict, lista: list[str]) -> dict:
    base = hechos(m, lista)
    if texto_ia is None:
        return {"texto": plantilla(m, lista), "origen": "plantilla",
                "motivo": "la IA no respondió", "cifras_ajenas": []}
    v = verificar(texto_ia, base)
    if v["ok"]:
        return {"texto": texto_ia.strip(), "origen": "ia", "motivo": "", "cifras_ajenas": []}
    motivo = ("la IA devolvió un texto vacío" if not v["cifras_ajenas"] else
              "la IA mencionó cifras que no están en los datos: " + ", ".join(v["cifras_ajenas"]))
    return {"texto": plantilla(m, lista), "origen": "plantilla", "motivo": motivo,
            "cifras_ajenas": v["cifras_ajenas"]}
