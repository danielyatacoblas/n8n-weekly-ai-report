"""El correo HTML lo arma el nodo de n8n: se prueba ejecutándolo con Node."""
from __future__ import annotations

import csv
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "tests" / "correr_nodo_js.mjs"
DATOS = {h: list(csv.DictReader((ROOT / "data" / f"{h}.csv").open(encoding="utf-8")))
         for h in ("ventas", "publicidad", "conversaciones", "facturas")}

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="Node.js no está instalado")


def _html(datos, texto, tmp_path):
    ruta = tmp_path / "p.json"
    ruta.write_text(json.dumps({"datos": datos, "fecha_ref": "2026-09-14", "textos_ia": [texto]},
                               ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(["node", str(RUNNER), str(ruta)], capture_output=True, text=True,
                          encoding="utf-8", check=True)
    return json.loads(proc.stdout)["html"]


def test_el_correo_trae_las_cifras_y_marca_el_dia_anormal(tmp_path):
    html = _html(DATOS, None, tmp_path)
    assert "S/ 8,078.10" in html and "Semana del 07/09 al 13/09" in html
    assert html.count("#b3261e;height:14px") == 1          # solo el miércoles en rojo
    assert "Resumen automático (la IA no respondió)" in html


def test_el_texto_de_la_ia_se_escapa(tmp_path):
    """Un texto con HTML no debe poder romper ni inyectar nada en el correo."""
    html = _html(DATOS, "<script>alert(1)</script> Semana normal.", tmp_path)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_nombres_de_productos_con_caracteres_especiales(tmp_path):
    datos = dict(DATOS, ventas=[{"fecha": "2026-09-08", "pedido_id": "1",
                                 "producto": 'Café "Tom & Jerry" <edición>', "cantidad": "1",
                                 "subtotal": "10.00"}])
    html = _html(datos, None, tmp_path)
    assert "Café &quot;Tom &amp; Jerry&quot; &lt;edición&gt;" in html
