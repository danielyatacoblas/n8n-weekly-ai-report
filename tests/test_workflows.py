"""Revisa los workflows generados: que se puedan importar y no filtren secretos."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = {p.name: json.loads(p.read_text(encoding="utf-8"))
             for p in (ROOT / "workflows").glob("*.json")}


def _conexiones(wf):
    for origen, salidas in wf["connections"].items():
        for ramas in salidas.values():
            for i, rama in enumerate(ramas):
                for destino in rama:
                    yield origen, i, destino["node"]


def _nodo(wf, nombre):
    return next(n for n in wf["nodes"] if n["name"] == nombre)


def test_existen_los_dos_workflows():
    assert set(WORKFLOWS) == {"reporte_demo.json", "reporte_produccion.json"}


@pytest.mark.parametrize("nombre", sorted(WORKFLOWS))
def test_conexiones_validas_y_sin_nodos_sueltos(nombre):
    wf = WORKFLOWS[nombre]
    nodos = {n["name"] for n in wf["nodes"]}
    tocados = set()
    for origen, _, destino in _conexiones(wf):
        assert origen in nodos and destino in nodos
        tocados.update((origen, destino))
    assert tocados == nodos


@pytest.mark.parametrize("nombre", sorted(WORKFLOWS))
def test_no_hay_credenciales(nombre):
    texto = json.dumps(WORKFLOWS[nombre])
    assert "credentials" not in texto
    assert not re.search(r"sk-[A-Za-z0-9]{20,}", texto)


def test_los_datos_ficticios_solo_viajan_en_la_demo():
    prod = json.dumps(WORKFLOWS["reporte_produccion.json"], ensure_ascii=False)
    assert "Café Chanchamayo" not in prod
    assert "Café Chanchamayo" in json.dumps(WORKFLOWS["reporte_demo.json"], ensure_ascii=False)


def test_sale_los_lunes_a_las_8():
    cron = _nodo(WORKFLOWS["reporte_produccion.json"], "Lunes 8:00")
    assert cron["parameters"]["rule"]["interval"][0]["expression"] == "0 8 * * 1"


def test_todo_texto_de_la_ia_pasa_por_el_verificador():
    wf = WORKFLOWS["reporte_produccion.json"]
    ia = _nodo(wf, "IA · Redactar resumen")
    assert ia["onError"] == "continueErrorOutput"
    salidas = {(o, i): d for o, i, d in _conexiones(wf) if o == "IA · Redactar resumen"}
    assert salidas == {("IA · Redactar resumen", 0): "Verificar y armar el reporte",
                       ("IA · Redactar resumen", 1): "Verificar y armar el reporte"}
    assert "se descarta" in ia["parameters"]["messages"]["messageValues"][0]["message"]


def test_el_correo_sale_en_html():
    gm = _nodo(WORKFLOWS["reporte_produccion.json"], "Gmail · Enviar reporte")
    assert gm["parameters"]["emailType"] == "html"
