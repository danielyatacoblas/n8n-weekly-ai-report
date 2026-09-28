"""Tests de métricas, hallazgos y verificación de cifras."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.reporte import (calcular, centimos, hallazgos, hechos,  # noqa: E402
                         normalizar_numero, redondear, resumen_final,
                         semana_anterior, soles, variacion, verificar)

DATOS = {h: list(csv.DictReader((ROOT / "data" / f"{h}.csv").open(encoding="utf-8")))
         for h in ("ventas", "publicidad", "conversaciones", "facturas")}


def venta(fecha, pedido, subtotal, producto="Café", cantidad=1):
    return {"fecha": fecha, "pedido_id": pedido, "producto": producto,
            "cantidad": str(cantidad), "subtotal": subtotal}


# ── números ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("num,den,esperado", [
    (5, 2, 3), (-5, 2, -3), (4, 3, 1), (-4, 3, -1), (1, 3, 0), (7, 7, 1)])
def test_redondeo_alejandose_de_cero(num, den, esperado):
    assert redondear(num, den) == esperado


@pytest.mark.parametrize("valor,c", [("1,234.5", 123450), ("12", 1200), (12.3, 1230),
                                     ("-5.00", -500), ("", 0), (None, 0), ("abc", 0)])
def test_centimos(valor, c):
    assert centimos(valor) == c


def test_formato_en_soles():
    assert soles(123456789) == "S/ 1,234,567.89"
    assert soles(-500) == "-S/ 5.00"


def test_variacion_en_decimas_de_porcentaje():
    assert variacion(110, 100) == 100          # +10.0 %
    assert variacion(90, 100) == -100
    assert variacion(5, 0) is None


# ── semana ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ref", ["2026-09-14", "2026-09-16", "2026-09-20"])
def test_la_semana_reportada_es_la_anterior_de_lunes_a_domingo(ref):
    assert semana_anterior(ref) == ("2026-09-07", "2026-09-13")


# ── métricas ───────────────────────────────────────────────────────────────

def test_ventas_pedidos_y_ticket():
    d = {"ventas": [venta("2026-09-08", 1, "100.00"), venta("2026-09-08", 1, "50.00"),
                    venta("2026-09-09", 2, "30.00"), venta("2026-09-01", 3, "999.00")]}
    v = calcular(d, "2026-09-14")["ventas"]
    assert (v["ingresos"], v["pedidos"], v["ticket"]) == (18000, 2, 9000)
    assert v["anterior"]["ingresos"] == 99900


def test_semana_sin_ventas_no_divide_por_cero():
    m = calcular({}, "2026-09-14")
    assert m["ventas"]["ticket"] == 0
    assert m["publicidad"]["roas"] is None
    assert m["atencion"]["tasa_bot"] is None


def test_la_tasa_del_bot_no_cuenta_los_chats_en_manos_de_un_asesor():
    conv = ([{"fecha": "2026-09-08", "accion": "responder", "intencion": "pago"}] * 3 +
            [{"fecha": "2026-09-08", "accion": "responder", "intencion": "aclarar"}] +
            [{"fecha": "2026-09-08", "accion": "silencio", "intencion": "x"}] * 10)
    at = calcular({"conversaciones": conv}, "2026-09-14")["atencion"]
    assert at["tasa_bot"] == 750                # 3 de 4, no 3 de 14


def test_detecta_el_miercoles_caido_y_nada_mas():
    anomalias = calcular(DATOS, "2026-09-14")["anomalias"]
    assert [(a["fecha"], a["tipo"]) for a in anomalias] == [("2026-09-09", "baja")]


def test_un_dia_normal_no_es_anomalia():
    # 8 martes con ventas parecidas y uno igual: nada fuera de lo normal
    ventas = [venta(f"2026-{m}", i, "100.00") for i, m in enumerate(
        ["07-14", "07-21", "07-28", "08-04", "08-11", "08-18", "08-25", "09-01", "09-08"])]
    ventas.append(venta("2026-08-25", 99, "5.00"))
    assert calcular({"ventas": ventas}, "2026-09-14")["anomalias"] == []


# ── hallazgos ──────────────────────────────────────────────────────────────

def test_hallazgos_de_la_semana_de_ejemplo():
    lista = hallazgos(calcular(DATOS, "2026-09-14"))
    assert lista[0].startswith("El miércoles 09/09 se vendió S/ 65.80")
    assert lista[1].startswith("El gasto en publicidad subió 60.9 %")
    assert any("preguntas de clientes no encontraron respuesta" in h for h in lista)


def test_si_gasto_y_ventas_suben_juntos_no_hay_alarma_de_publicidad():
    d = {"ventas": [venta("2026-09-08", 1, "200.00"), venta("2026-09-01", 2, "100.00")],
         "publicidad": [{"fecha": "2026-09-08", "gasto": "50.00"},
                        {"fecha": "2026-09-01", "gasto": "20.00"}]}
    assert not any("publicidad subió" in h for h in hallazgos(calcular(d, "2026-09-14")))


# ── verificación de cifras ─────────────────────────────────────────────────

@pytest.mark.parametrize("n,k", [("1,234.50", "1234.5"), ("007", "7"), ("0.50", "0.5"),
                                 ("12.0", "12"), ("0", "0")])
def test_normalizar_numero(n, k):
    assert normalizar_numero(n) == k


def test_acepta_cifras_escritas_como_en_los_datos():
    assert verificar("Vendimos S/ 1,234.50 en 12 pedidos.", "Ventas: S/ 1,234.50\nPedidos: 12")["ok"]


def test_rechaza_una_cifra_inventada_o_redondeada():
    v = verificar("Vendimos S/ 1,235 en 12 pedidos.", "Ventas: S/ 1,234.50\nPedidos: 12")
    assert v == {"ok": False, "cifras_ajenas": ["1,235"]}


def test_numeros_chicos_se_permiten():
    assert verificar("En los 7 días hubo 3 problemas.", "nada")["ok"]


def test_texto_vacio_no_es_valido():
    assert not verificar("  ", "Ventas: 5")["ok"]


def test_si_la_ia_inventa_se_usa_el_resumen_automatico():
    m = calcular(DATOS, "2026-09-14")
    lista = hallazgos(m)
    r = resumen_final("Las ventas fueron S/ 9,999.99.", m, lista)
    assert r["origen"] == "plantilla"
    assert r["cifras_ajenas"] == ["9,999.99"]
    assert "S/ 8,078.10" in r["texto"]


def test_el_resumen_automatico_pasa_su_propia_verificacion():
    m = calcular(DATOS, "2026-09-14")
    lista = hallazgos(m)
    plantilla = resumen_final(None, m, lista)["texto"]
    assert verificar(plantilla, hechos(m, lista))["ok"]
