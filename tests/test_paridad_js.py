"""Paridad: los nodos Code de n8n (JS) y la lógica Python deben dar lo mismo.

Compara las métricas, los hallazgos, el texto que recibe la IA y la decisión
del verificador de cifras. Requiere Node.js; si no está instalado, se salta.
"""
from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.reporte import calcular, hallazgos, hechos, resumen_final  # noqa: E402

RUNNER = ROOT / "tests" / "correr_nodo_js.mjs"
DATOS = {h: list(csv.DictReader((ROOT / "data" / f"{h}.csv").open(encoding="utf-8")))
         for h in ("ventas", "publicidad", "conversaciones", "facturas")}
TEXTOS = [
    None, "", "   ",
    "Las ventas bajaron 8.6 % y quedaron en S/ 8,078.10.",
    "Las ventas bajaron 9 % hasta S/ 8,100.",
    "Vendimos 0060 pedidos, 7 días seguidos, con 0.50 de algo.",
    "El miércoles 09/09 se vendió S/ 65.80 frente a S/ 982.44.",
]

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="Node.js no está instalado")


def _js(datos, fecha, tmp_path):
    ruta = tmp_path / "pedido.json"
    ruta.write_text(json.dumps({"datos": datos, "fecha_ref": fecha, "textos_ia": TEXTOS},
                               ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(["node", str(RUNNER), str(ruta)],
                          capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        pytest.fail(f"el nodo JS falló:\n{proc.stderr}")
    return json.loads(proc.stdout)


@pytest.mark.parametrize("fecha", ["2026-09-14", "2026-09-17", "2026-08-03", "2026-07-13", "2026-12-01"])
def test_mismas_metricas_hallazgos_y_verificacion(fecha, tmp_path):
    m = calcular(DATOS, fecha)
    lista = hallazgos(m)
    js = _js(DATOS, fecha, tmp_path)
    assert js["metricas"] == m
    assert js["hallazgos"] == lista
    assert js["hechos"] == hechos(m, lista)
    assert js["resumenes"] == [resumen_final(t, m, lista) for t in TEXTOS]


def test_datos_vacios_o_raros(tmp_path):
    raros = {"ventas": [{"fecha": "2026-09-08", "pedido_id": "1", "subtotal": "abc",
                         "cantidad": "x"},
                        {"fecha": "2026-09-08T10:00:00", "subtotal": "1,234.5", "cantidad": "2"}],
             "publicidad": [], "conversaciones": [{"fecha": "2026-09-09"}], "facturas": None}
    m = calcular(raros, "2026-09-14")
    lista = hallazgos(m)
    js = _js(raros, "2026-09-14", tmp_path)
    assert (js["metricas"], js["hallazgos"]) == (m, lista)
