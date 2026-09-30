#!/usr/bin/env python3
"""Construye los workflows de n8n a partir del código fuente.

    python scripts/build_workflow.py

Genera:
  workflows/reporte_demo.json        GET al webhook → el reporte en HTML, SIN credenciales
  workflows/reporte_produccion.json  lunes 8:00 → hojas → IA → verificación → correo + Telegram

Los dos nodos Code salen de workflows/src/reporte.js; cambian los marcadores
MODO, FUENTE y DATOS.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from diseno_canvas import acomodar  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "workflows" / "src" / "reporte.js"
DATA = ROOT / "data"
OUT = ROOT / "workflows"
HOJAS = ["ventas", "publicidad", "conversaciones", "facturas"]
ID_HOJA = {"__rl": True, "value": "REEMPLAZAR_ID_HOJA", "mode": "id"}

PROMPT_SISTEMA = (
    "Eres el analista de un negocio pequeño. Escribe para el dueño un resumen de 3 a 5 "
    "oraciones, en español claro y sin tecnicismos.\n"
    "Reglas:\n"
    "1. Usa SOLO las cifras de los DATOS, escritas exactamente igual (con S/, comas y %).\n"
    "2. No calcules cifras nuevas ni redondees. Si una cifra no está en los datos, no la escribas.\n"
    "3. Empieza por lo más importante y termina con una acción concreta para esta semana.\n"
    "Un sistema revisa cada número de tu texto: si alguno no está en los datos, tu texto se descarta.")


def datos_demo() -> str:
    """Las hojas como {columnas, filas}: la mitad de tamaño que una lista de objetos."""
    tablas = {}
    for hoja in HOJAS:
        filas = list(csv.reader((DATA / f"{hoja}.csv").open(encoding="utf-8")))
        tablas[hoja] = {"columnas": filas[0], "filas": filas[1:]}
    return json.dumps(tablas, ensure_ascii=False, separators=(",", ":"))


def codigo(modo: str, fuente: str) -> str:
    js = JS.read_text(encoding="utf-8")
    reemplazos = {"'__MODO__'": f"'{modo}'", "'__FUENTE__'": f"'{fuente}'",
                  "__DATOS__": datos_demo() if fuente == "demo" and modo == "metricas" else "{}"}
    for marca, valor in reemplazos.items():
        if js.count(marca) != 1:
            raise SystemExit(f"se esperaba una sola vez {marca} en {JS}")
        js = js.replace(marca, valor)
    return js


def _node(nid, name, ntype, tv, pos, params, extra=None):
    n = {"parameters": params, "id": nid, "name": name, "type": ntype,
         "typeVersion": tv, "position": pos}
    if extra:
        n.update(extra)
    return n


def _link(*destinos, tipo="main"):
    return [{"node": d, "type": tipo, "index": 0} for d in destinos]


@acomodar
def build_demo() -> dict:
    nodes = [
        _node("wh-1", "Webhook · Ver reporte", "n8n-nodes-base.webhook", 2, [0, 0],
              {"httpMethod": "GET", "path": "reporte-demo", "responseMode": "responseNode",
               "options": {}},
              {"webhookId": "reporte-demo",
               "notes": "Parámetros opcionales: ?fecha=2026-09-14 y ?texto_ia=... para "
                        "probar el verificador de cifras sin conectar un modelo."}),
        _node("code-1", "Calcular métricas", "n8n-nodes-base.code", 2, [240, 0],
              {"jsCode": codigo("metricas", "demo")},
              {"notes": "Trae incluidas 10 semanas de datos ficticios."}),
        _node("code-2", "Verificar y armar el reporte", "n8n-nodes-base.code", 2, [480, 0],
              {"jsCode": codigo("resumen", "demo")}),
        _node("resp-1", "Mostrar el reporte", "n8n-nodes-base.respondToWebhook", 1.1, [720, 0],
              {"respondWith": "text", "responseBody": "={{ $json.html }}",
               "options": {"responseHeaders": {"entries": [
                   {"name": "Content-Type", "value": "text/html; charset=utf-8"}]}}}),
    ]
    connections = {
        "Webhook · Ver reporte": {"main": [_link("Calcular métricas")]},
        "Calcular métricas": {"main": [_link("Verificar y armar el reporte")]},
        "Verificar y armar el reporte": {"main": [_link("Mostrar el reporte")]},
    }
    return {"id": "reportedemo", "name": "Reporte semanal · DEMO sin credenciales",
            "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1"}, "pinData": {},
            "meta": {"instanceId": "reporte-demo"}, "tags": []}


def _hoja(nid, nombre, pestana, pos):
    return _node(nid, nombre, "n8n-nodes-base.googleSheets", 4.5, pos,
                 {"documentId": ID_HOJA,
                  "sheetName": {"__rl": True, "value": pestana, "mode": "name"},
                  "options": {}},
                 {"executeOnce": True, "alwaysOutputData": True})


@acomodar
def build_prod() -> dict:
    nodes = [
        _node("cron-1", "Lunes 8:00", "n8n-nodes-base.scheduleTrigger", 1.2, [0, 300],
              {"rule": {"interval": [{"field": "cronExpression", "expression": "0 8 * * 1"}]}},
              {"notes": "Usa la zona horaria de n8n (GENERIC_TIMEZONE=America/Lima)."}),
        _hoja("gs-v", "Sheets · Ventas", "Ventas", [220, 300]),
        _hoja("gs-p", "Sheets · Publicidad", "Publicidad", [440, 300]),
        _hoja("gs-c", "Sheets · Conversaciones", "Conversaciones", [660, 300]),
        _hoja("gs-f", "Sheets · Facturas", "Facturas", [880, 300]),
        _node("code-1", "Calcular métricas", "n8n-nodes-base.code", 2, [1100, 300],
              {"jsCode": codigo("metricas", "sheets")}),
        _node("llm-1", "IA · Redactar resumen", "@n8n/n8n-nodes-langchain.chainLlm", 1.7,
              [1320, 300],
              {"promptType": "define", "text": "=DATOS:\n{{ $json.hechos }}",
               "messages": {"messageValues": [{"message": PROMPT_SISTEMA}]}},
              {"onError": "continueErrorOutput",
               "notes": "Si la IA falla o inventa una cifra, el reporte sale igual con "
                        "un resumen automático."}),
        _node("llm-m", "Modelo de IA", "@n8n/n8n-nodes-langchain.lmChatOpenAi", 1.2, [1320, 500],
              {"model": {"__rl": True, "value": "gpt-4o-mini", "mode": "list"},
               "options": {"temperature": 0.3, "maxTokens": 400}}),
        _node("code-2", "Verificar y armar el reporte", "n8n-nodes-base.code", 2, [1540, 300],
              {"jsCode": codigo("resumen", "sheets")},
              {"notes": "Cada número del texto de la IA debe existir en los datos."}),
        _node("gm-1", "Gmail · Enviar reporte", "n8n-nodes-base.gmail", 2.1, [1780, 140],
              {"sendTo": "REEMPLAZAR_CORREO_DUENO", "subject": "={{ $json.asunto }}",
               "emailType": "html", "message": "={{ $json.html }}",
               "options": {"appendAttribution": False}}),
        _node("tg-1", "Telegram · Resumen corto", "n8n-nodes-base.telegram", 1.2, [1780, 300],
              {"chatId": "REEMPLAZAR_CHAT_EQUIPO", "text": "={{ $json.telegram }}",
               "additionalFields": {"appendAttribution": False}}),
        _node("set-h", "Fila de historial", "n8n-nodes-base.set", 3.4, [1780, 460],
              {"mode": "raw", "jsonOutput": "={{ JSON.stringify($json.fila) }}", "options": {}}),
        _node("gs-h", "Sheets · Historial de reportes", "n8n-nodes-base.googleSheets", 4.5,
              [2000, 460],
              {"operation": "append", "documentId": ID_HOJA,
               "sheetName": {"__rl": True, "value": "Historial", "mode": "name"},
               "columns": {"mappingMode": "autoMapInputData", "value": {}},
               "options": {}}),
    ]
    connections = {
        "Lunes 8:00": {"main": [_link("Sheets · Ventas")]},
        "Sheets · Ventas": {"main": [_link("Sheets · Publicidad")]},
        "Sheets · Publicidad": {"main": [_link("Sheets · Conversaciones")]},
        "Sheets · Conversaciones": {"main": [_link("Sheets · Facturas")]},
        "Sheets · Facturas": {"main": [_link("Calcular métricas")]},
        "Calcular métricas": {"main": [_link("IA · Redactar resumen")]},
        "Modelo de IA": {"ai_languageModel": [_link("IA · Redactar resumen", tipo="ai_languageModel")]},
        "IA · Redactar resumen": {"main": [_link("Verificar y armar el reporte"),
                                           _link("Verificar y armar el reporte")]},
        "Verificar y armar el reporte": {"main": [_link("Gmail · Enviar reporte",
                                                        "Telegram · Resumen corto",
                                                        "Fila de historial")]},
        "Fila de historial": {"main": [_link("Sheets · Historial de reportes")]},
    }
    return {"id": "reporteprod", "name": "Reporte semanal · producción",
            "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1"}, "pinData": {},
            "meta": {"instanceId": "reporte-prod"}, "tags": []}


def main():
    for nombre, wf in (("reporte_demo.json", build_demo()),
                       ("reporte_produccion.json", build_prod())):
        ruta = OUT / nombre
        ruta.write_text(json.dumps(wf, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8", newline="\n")
        print(f"ok  {ruta.relative_to(ROOT)} — {len(wf['nodes'])} nodos, "
              f"{ruta.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
