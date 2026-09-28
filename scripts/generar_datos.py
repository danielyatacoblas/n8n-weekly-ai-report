#!/usr/bin/env python3
"""Genera 10 semanas de datos ficticios de la tostaduría, como los dejan los
otros flujos en Google Sheets.

    python scripts/generar_datos.py

Salidas (una hoja por archivo, todo como texto, igual que lo entrega Sheets):
  data/ventas.csv           líneas de pedidos de la tienda online
  data/publicidad.csv       gasto diario por canal
  data/conversaciones.csv   registro del bot de atención
  data/facturas.csv         facturas de proveedores leídas por el flujo de facturas

La última semana (07/09 al 13/09) esconde dos problemas que el reporte debe
encontrar: el miércoles casi no hubo ventas (la pasarela de pago falló) y una
campaña nueva de publicidad gastó el doble sin vender más.
Semilla fija: siempre genera exactamente lo mismo.
"""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
INICIO = date(2026, 7, 6)          # lunes
SEMANAS = 10
MIERCOLES_CAIDO = date(2026, 9, 9)
CAMPANA_NUEVA = date(2026, 9, 7)

PRODUCTOS = [
    ("CAF-VRS-250", "Café Villa Rica tostado 250 g", 2890, 30),
    ("CAF-VRS-1K", "Café Villa Rica tostado 1 kg", 9900, 8),
    ("CAF-CHA-250", "Café Chanchamayo orgánico 250 g", 3290, 18),
    ("CAF-CUS-250", "Café Cusco geisha 250 g", 5990, 6),
    ("CAF-DES-250", "Café descafeinado 250 g", 3190, 6),
    ("PRE-V60", "Gotero V60 de cerámica", 7900, 3),
    ("PRE-PRENSA", "Prensa francesa 600 ml", 8900, 3),
    ("ACC-FILTROS", "Filtros de papel x100", 1990, 12),
    ("ACC-TAZA", "Taza de cerámica artesanal", 4500, 5),
    ("KIT-REGALO", "Kit regalo café + taza", 11900, 4),
]
PEDIDOS_POR_DIA = [9, 8, 8, 9, 11, 14, 12]            # lunes a domingo
INTENCIONES = ["precio_lentes", "horario", "pago", "delivery", "promociones", "cita"]


def soles(c: int) -> str:
    return f"{c // 100}.{c % 100:02d}"


def escribir(nombre: str, columnas: list[str], filas: list[list]) -> None:
    with (DATA / nombre).open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(columnas)
        w.writerows(filas)


def main():
    rng = random.Random(7)
    DATA.mkdir(exist_ok=True)
    ventas, publicidad, conversaciones, facturas = [], [], [], []
    pedido = 20000
    pesos = [p[3] for p in PRODUCTOS]

    for d in range(SEMANAS * 7):
        hoy = INICIO + timedelta(days=d)
        f = hoy.isoformat()
        n = PEDIDOS_POR_DIA[hoy.weekday()] + rng.randint(-2, 2)
        if hoy == MIERCOLES_CAIDO:
            n = 1
        for _ in range(n):
            pedido += 1
            for sku, nombre, precio, _ in {p[0]: p for p in rng.choices(PRODUCTOS, pesos, k=rng.randint(1, 3))}.values():
                cant = rng.choice([1, 1, 1, 2, 2, 3])
                ventas.append([f, pedido, sku, nombre, cant, soles(precio * cant)])

        for canal, base in (("Meta Ads", 4500), ("Google Ads", 3500)):
            gasto = base + rng.randint(-600, 600)
            if canal == "Meta Ads" and hoy >= CAMPANA_NUEVA:
                gasto *= 2                                  # campaña nueva, mismo resultado
            publicidad.append([f, canal, soles(gasto), rng.randint(40, 90)])

        for _ in range(rng.randint(14, 24)):
            r = rng.random()
            if r < 0.72:
                accion, intencion = "responder", rng.choice(INTENCIONES)
            elif r < 0.82:
                accion, intencion = "responder", "aclarar"
            elif r < 0.93:
                accion, intencion = "derivar", rng.choice(["pide_persona", "reclamo", "sin_respuesta"])
            else:
                accion, intencion = "silencio", "en_manos_de_asesor"
            conversaciones.append([f, accion, intencion])

        if hoy.weekday() in (0, 3):
            for _ in range(rng.randint(1, 2)):
                total = rng.randint(30000, 250000)
                estado = "revision" if rng.random() < 0.12 else "registrada"
                facturas.append([f, estado, soles(total)])

    escribir("ventas.csv", ["fecha", "pedido_id", "sku", "producto", "cantidad", "subtotal"], ventas)
    escribir("publicidad.csv", ["fecha", "canal", "gasto", "clics"], publicidad)
    escribir("conversaciones.csv", ["fecha", "accion", "intencion"], conversaciones)
    escribir("facturas.csv", ["fecha", "estado", "total"], facturas)
    print(f"{len(ventas)} líneas de venta, {len(publicidad)} días de publicidad, "
          f"{len(conversaciones)} conversaciones, {len(facturas)} facturas")


if __name__ == "__main__":
    main()
