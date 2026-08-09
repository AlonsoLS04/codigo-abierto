# -*- coding: utf-8 -*-
"""
CÓDIGO ABIERTO — Generador semanal
1) Lee titulares recientes desde feeds RSS
2) Pide a Gemini (free tier) que redacte la edición en JSON
3) Renderiza el HTML con un archivo de ediciones pasadas al pie
4) Publica:
   - docs/index.html          -> edición más reciente
   - docs/ediciones/NNN.html  -> respaldo permanente de cada edición
   - docs/ediciones/NNN.json  -> contenido completo (lo consume Lovable)
   - docs/index.json          -> historial ligero de todas las ediciones
"""

import os
import re
import time
import json
import html
import datetime
import requests
import feedparser
from pathlib import Path
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------- CONFIG ----

RAIZ = Path(__file__).parent
DIR_DOCS = RAIZ / "docs"
DIR_EDICIONES = DIR_DOCS / "ediciones"
ARCHIVO_INDEX = DIR_DOCS / "index.json"

URL_BASE = "https://alonsols04.github.io/codigo-abierto"

# Cuántas ediciones pasadas se listan al pie de la página
MAX_ARCHIVO_VISIBLE = 12

FEEDS = [
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://www.xataka.com/feedburner.xml",
    "https://hipertextual.com/feed",
    "https://www.marketingdirecto.com/feed",
    # --- Análisis de datos ---
    "https://www.kdnuggets.com/feed",
    "https://towardsdatascience.com/feed",
    "https://www.analyticsvidhya.com/feed/",
]

MAX_ITEMS_POR_FEED = 8
MODELOS = ["gemini-3.5-flash", "gemini-3-flash", "gemini-3.1-flash-lite"]
REINTENTOS = 3
ESPERA_SEG = 30

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

# ------------------------------------------------------------ 1. NOTICIAS ---

def recolectar_noticias():
    items = []
    for url in FEEDS:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:MAX_ITEMS_POR_FEED]:
                resumen = re.sub(r"<[^>]+>", "", e.get("summary", ""))[:300]
                items.append({
                    "titulo": e.get("title", "").strip(),
                    "resumen": resumen.strip(),
                    "enlace": e.get("link", ""),
                    "fuente": feed.feed.get("title", url),
                })
        except Exception as ex:
            print(f"[aviso] feed falló {url}: {ex}")
    print(f"Noticias recolectadas: {len(items)}")
    return items

# -------------------------------------------------------------- 2. GEMINI ---

PROMPT = """Eres el editor de CÓDIGO ABIERTO, un briefing semanal en español sobre
tecnología, inteligencia artificial y marketing, escrito para profesionales de
Latinoamérica. Tono: directo, inteligente, sin humo, con criterio editorial.

A partir de las noticias listadas abajo, redacta la edición de esta semana.
Selecciona solo lo más relevante. Cada historia debe incluir un "Ángulo LATAM":
qué significa esto para el mercado latinoamericano.

Responde ÚNICAMENTE con un JSON válido, sin markdown, sin ```, con esta forma:
{
  "portada": {"titulo": "...", "cuerpo": "2-3 párrafos", "angulo_latam": "...", "enlace": "url", "fuente": "..."},
  "ia": [{"titulo": "...", "cuerpo": "1-2 párrafos", "angulo_latam": "...", "enlace": "url", "fuente": "..."}],
  "marketing": [{"titulo": "...", "cuerpo": "...", "angulo_latam": "...", "enlace": "url", "fuente": "..."}],
  "datos": [{"titulo": "...", "cuerpo": "1-2 párrafos", "angulo_latam": "...", "enlace": "url", "fuente": "..."}],
  "tip_analista": {"titulo": "nombre corto del tip", "cuerpo": "explicación práctica en 2-4 frases", "herramienta": "SQL | Power BI | Python | Excel | DAX"},
  "dato": {"cifra": "ej: 73%", "contexto": "una frase que explica la cifra"},
  "para_llevar": "una reflexión final de 2-3 frases, accionable"
}
Reglas: "ia" con 2 historias, "marketing" con 2 historias, "datos" con 2 historias
sobre análisis de datos, ciencia de datos, BI o herramientas de datos (elígelas de
las fuentes tipo KDnuggets, Towards Data Science o Analytics Vidhya si están en la
lista). El "tip_analista" es un consejo práctico y accionable de análisis de datos
(un truco de SQL, DAX, Power BI, Python/pandas o Excel) que un analista pueda
aplicar hoy mismo; puede ser de tu conocimiento, no necesita venir de las noticias.
Usa los enlaces reales
de las noticias dadas. No inventes noticias que no estén en la lista.

NOTICIAS DE LA SEMANA:
"""

def generar_contenido(noticias):
    api_key = os.environ["GEMINI_API_KEY"]
    cuerpo_noticias = "\n".join(
        f"- [{n['fuente']}] {n['titulo']} :: {n['resumen']} :: {n['enlace']}"
        for n in noticias
    )
    payload = {
        "contents": [{"parts": [{"text": PROMPT + cuerpo_noticias}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 4000},
    }
    ultimo_error = None
    for modelo in MODELOS:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{modelo}:generateContent?key={api_key}")
        for intento in range(1, REINTENTOS + 1):
            try:
                print(f"Intentando con {modelo} (intento {intento}/{REINTENTOS})...")
                r = requests.post(url, json=payload, timeout=120)
                if r.status_code == 429:
                    print(f"  -> 429 (limite de cuota). Esperando {ESPERA_SEG}s...")
                    time.sleep(ESPERA_SEG)
                    continue
                r.raise_for_status()
                texto = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                texto = re.sub(r"^```(json)?|```$", "", texto.strip(),
                               flags=re.MULTILINE).strip()
                print(f"  -> OK con {modelo}")
                return json.loads(texto)
            except Exception as ex:
                ultimo_error = ex
                print(f"  -> fallo: {ex}")
                time.sleep(5)
        print(f"{modelo} agotado, probando siguiente modelo...")
    raise SystemExit(f"Ningun modelo de Gemini respondio. Ultimo error: {ultimo_error}")

# ------------------------------------------------------- 3. ARCHIVO / JSON ---

def cargar_indice():
    """Lee el historial existente. Devuelve lista vacía si aún no existe."""
    if ARCHIVO_INDEX.exists():
        try:
            return json.loads(ARCHIVO_INDEX.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("[aviso] index.json corrupto; se reinicia el historial.")
            return []
    return []

def siguiente_numero(indice):
    if not indice:
        return 1
    return max(int(e["numero"]) for e in indice) + 1

def resumen_corto(texto, limite=160):
    texto = (texto or "").strip()
    if len(texto) <= limite:
        return texto
    return texto[:limite].rsplit(" ", 1)[0] + "…"

def fecha_legible(fecha_iso):
    """'2026-08-09' -> '9 de agosto, 2026'"""
    try:
        d = datetime.date.fromisoformat(fecha_iso)
        return f"{d.day} de {MESES[d.month-1]}, {d.year}"
    except Exception:
        return fecha_iso

# ---------------------------------------------------------------- 4. HTML ---

def esc(t):
    return html.escape(t or "")

def tarjeta(historia, etiqueta):
    return f"""
    <div style="background:#141414;border:1px solid #262626;border-radius:12px;padding:24px;margin-bottom:18px;">
      <div style="color:#FF6B00;font-size:11px;letter-spacing:2px;font-weight:700;margin-bottom:8px;">{etiqueta}</div>
      <h2 style="color:#FFFFFF;font-size:20px;margin:0 0 12px;line-height:1.3;">{esc(historia['titulo'])}</h2>
      <p style="color:#B3B3B3;font-size:14px;line-height:1.7;margin:0 0 14px;">{esc(historia['cuerpo'])}</p>
      <div style="background:#0D0D0D;border-left:3px solid #FF6B00;padding:12px 16px;margin-bottom:14px;">
        <span style="color:#FF6B00;font-size:11px;font-weight:700;letter-spacing:1px;">ÁNGULO LATAM</span>
        <p style="color:#D9D9D9;font-size:13px;line-height:1.6;margin:6px 0 0;">{esc(historia['angulo_latam'])}</p>
      </div>
      <a href="{esc(historia.get('enlace',''))}" target="_blank" style="color:#FF6B00;font-size:12px;font-weight:700;text-decoration:none;letter-spacing:1px;">LEER MÁS → <span style="color:#666;">({esc(historia.get('fuente',''))})</span></a>
    </div>"""

def bloque_archivo(indice, numero_actual, ruta_relativa):
    """Lista de ediciones pasadas. `ruta_relativa` ajusta los links según
    si la página está en la raíz (docs/) o en docs/ediciones/."""
    pasadas = [e for e in indice if e["numero"] != numero_actual][:MAX_ARCHIVO_VISIBLE]
    if not pasadas:
        return ""
    filas = ""
    for e in pasadas:
        href = f"{ruta_relativa}{e['numero']}.html"
        filas += f"""
      <a href="{href}" style="display:block;text-decoration:none;padding:14px 0;border-bottom:1px solid #1F1F1F;">
        <span style="color:#FF6B00;font-family:monospace;font-size:12px;font-weight:700;">#{esc(e['numero'])}</span>
        <span style="color:#666;font-size:11px;margin-left:8px;">{esc(fecha_legible(e['fecha']))}</span>
        <div style="color:#DDDDDD;font-size:14px;line-height:1.4;margin-top:4px;">{esc(e['titulo'])}</div>
      </a>"""
    return f"""
  <div style="background:#141414;border:1px solid #262626;border-radius:12px;padding:24px;margin-top:28px;">
    <div style="color:#888;font-size:11px;letter-spacing:2px;font-weight:700;margin-bottom:6px;">🗂 EDICIONES ANTERIORES</div>
    <p style="color:#666;font-size:12px;margin:0 0 8px;">Cada lunes se suma una edición nueva. El archivo queda disponible siempre.</p>
    {filas}
  </div>"""

def render_html(c, ahora, numero_str, indice, es_archivo=False):
    """`es_archivo=True` cuando la página se guarda dentro de docs/ediciones/."""
    fecha_texto = f"{ahora.day} de {MESES[ahora.month-1]} de {ahora.year}"
    cuerpo_ia = "".join(tarjeta(h, "INTELIGENCIA ARTIFICIAL") for h in c["ia"])
    cuerpo_mkt = "".join(tarjeta(h, "MARKETING") for h in c["marketing"])
    cuerpo_datos = "".join(tarjeta(h, "ANÁLISIS DE DATOS") for h in c.get("datos", []))

    # Links del archivo: desde la raíz apuntan a ediciones/, desde una
    # edición archivada apuntan al mismo directorio.
    ruta_rel = "" if es_archivo else "ediciones/"
    archivo = bloque_archivo(indice, numero_str, ruta_rel)

    # Desde una edición archivada, ofrecer volver a la más reciente
    volver = ""
    if es_archivo:
        volver = f"""
  <div style="text-align:center;margin-bottom:24px;">
    <a href="{URL_BASE}/" style="color:#FF6B00;font-size:12px;font-weight:700;text-decoration:none;letter-spacing:1px;">← VER LA EDICIÓN MÁS RECIENTE</a>
  </div>"""

    tip = c.get("tip_analista", {})
    bloque_tip = ""
    if tip:
        bloque_tip = f"""
  <div style="background:#0F1A14;border:1px solid #2E7D5B;border-radius:12px;padding:24px;margin-bottom:18px;">
    <div style="color:#4ADE80;font-size:11px;letter-spacing:2px;font-weight:700;margin-bottom:8px;">💡 TIP DEL ANALISTA <span style="color:#888;">· {esc(tip.get('herramienta',''))}</span></div>
    <h2 style="color:#FFFFFF;font-size:18px;margin:0 0 10px;line-height:1.3;">{esc(tip.get('titulo',''))}</h2>
    <p style="color:#C8E6D5;font-size:14px;line-height:1.7;margin:0;">{esc(tip.get('cuerpo',''))}</p>
  </div>"""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Código Abierto #{numero_str} — {esc(c['portada']['titulo'])}</title>
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Space+Grotesk:wght@400;500;700&display=swap" rel="stylesheet">
</head>
<body style="margin:0;padding:0;background:#0A0A0A;font-family:'Space Grotesk',Arial,sans-serif;">
<div style="max-width:640px;margin:0 auto;padding:32px 20px;">

  <div style="text-align:center;padding-bottom:24px;border-bottom:2px solid #FF6B00;margin-bottom:12px;">
    <div style="font-family:'Bebas Neue',Impact,sans-serif;font-size:44px;color:#FFFFFF;letter-spacing:4px;">CÓDIGO <span style="color:#FF6B00;">ABIERTO</span></div>
    <div style="color:#888;font-size:12px;letter-spacing:3px;margin-top:4px;">TECH · IA · MARKETING · DATOS · MIRADA LATAM</div>
    <div style="color:#FF6B00;font-size:12px;margin-top:10px;font-weight:700;">EDICIÓN #{numero_str} — {fecha_texto.upper()}</div>
  </div>

  <div style="text-align:center;margin-bottom:28px;">
    <span style="color:#666;font-size:11px;letter-spacing:1px;">Publicado el {fecha_texto} · Nueva edición cada lunes</span>
  </div>
{volver}
  <div style="background:linear-gradient(135deg,#1A1208,#141414);border:1px solid #FF6B00;border-radius:12px;padding:28px;margin-bottom:28px;">
    <div style="color:#FF6B00;font-size:11px;letter-spacing:2px;font-weight:700;margin-bottom:10px;">★ PORTADA</div>
    <h1 style="color:#FFFFFF;font-size:26px;margin:0 0 14px;line-height:1.25;">{esc(c['portada']['titulo'])}</h1>
    <p style="color:#CCCCCC;font-size:15px;line-height:1.75;margin:0 0 14px;">{esc(c['portada']['cuerpo'])}</p>
    <div style="background:#0D0D0D;border-left:3px solid #FF6B00;padding:12px 16px;margin-bottom:14px;">
      <span style="color:#FF6B00;font-size:11px;font-weight:700;letter-spacing:1px;">ÁNGULO LATAM</span>
      <p style="color:#D9D9D9;font-size:13px;line-height:1.6;margin:6px 0 0;">{esc(c['portada']['angulo_latam'])}</p>
    </div>
    <a href="{esc(c['portada'].get('enlace',''))}" target="_blank" style="color:#FF6B00;font-size:12px;font-weight:700;text-decoration:none;letter-spacing:1px;">LEER MÁS →</a>
  </div>

  {cuerpo_ia}
  {cuerpo_mkt}
  {cuerpo_datos}
  {bloque_tip}

  <div style="text-align:center;background:#141414;border:1px solid #262626;border-radius:12px;padding:28px;margin-bottom:18px;">
    <div style="color:#888;font-size:11px;letter-spacing:2px;margin-bottom:8px;">EL DATO DE LA SEMANA</div>
    <div style="font-family:'Bebas Neue',Impact,sans-serif;font-size:56px;color:#FF6B00;line-height:1;">{esc(c['dato']['cifra'])}</div>
    <p style="color:#B3B3B3;font-size:13px;margin:10px 0 0;">{esc(c['dato']['contexto'])}</p>
  </div>

  <div style="background:#141414;border-radius:12px;padding:24px;border:1px dashed #FF6B00;">
    <div style="color:#FF6B00;font-size:11px;letter-spacing:2px;font-weight:700;margin-bottom:8px;">📌 PARA LLEVAR</div>
    <p style="color:#E6E6E6;font-size:14px;line-height:1.7;margin:0;font-style:italic;">{esc(c['para_llevar'])}</p>
  </div>
{archivo}
  <div style="text-align:center;color:#555;font-size:11px;margin-top:32px;letter-spacing:1px;">
    CÓDIGO ABIERTO — Curado desde Lima 🇵🇪 para toda LATAM
  </div>
</div>
</body>
</html>"""

# ----------------------------------------------------------------- MAIN -----

def main():
    ahora = datetime.datetime.now(ZoneInfo("America/Lima"))
    DIR_DOCS.mkdir(parents=True, exist_ok=True)
    DIR_EDICIONES.mkdir(parents=True, exist_ok=True)

    noticias = recolectar_noticias()
    if not noticias:
        raise SystemExit("No se pudieron recolectar noticias; se aborta.")

    contenido = generar_contenido(noticias)

    # --- Numeración e historial ---
    indice = cargar_indice()
    numero_str = f"{siguiente_numero(indice):03d}"
    fecha_iso = ahora.strftime("%Y-%m-%d")

    entrada_nueva = {
        "numero": numero_str,
        "fecha": fecha_iso,
        "titulo": contenido["portada"]["titulo"],
        "resumen": resumen_corto(contenido["portada"]["cuerpo"]),
        "url_json": f"{URL_BASE}/ediciones/{numero_str}.json",
        "url_html": f"{URL_BASE}/ediciones/{numero_str}.html",
    }
    indice_actualizado = [entrada_nueva] + indice  # más reciente primero

    # --- a) Página principal (raíz): edición más reciente ---
    (DIR_DOCS / "index.html").write_text(
        render_html(contenido, ahora, numero_str, indice_actualizado, es_archivo=False),
        encoding="utf-8",
    )
    print("Página actualizada: docs/index.html")

    # --- b) Respaldo archivado de esta edición ---
    (DIR_EDICIONES / f"{numero_str}.html").write_text(
        render_html(contenido, ahora, numero_str, indice_actualizado, es_archivo=True),
        encoding="utf-8",
    )

    # --- c) Contenido completo en JSON (lo consume Lovable) ---
    edicion_completa = {
        "numero": numero_str,
        "fecha": fecha_iso,
        "titulo": contenido["portada"]["titulo"],
        "portada": contenido["portada"],
        "ia": contenido.get("ia", []),
        "marketing": contenido.get("marketing", []),
        "datos": contenido.get("datos", []),
        "tip_analista": contenido.get("tip_analista", {}),
        "dato": contenido.get("dato", {}),
        "para_llevar": contenido.get("para_llevar", ""),
    }
    (DIR_EDICIONES / f"{numero_str}.json").write_text(
        json.dumps(edicion_completa, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # --- d) Historial ligero ---
    ARCHIVO_INDEX.write_text(
        json.dumps(indice_actualizado, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Edición #{numero_str} publicada · historial: {len(indice_actualizado)} ediciones")

if __name__ == "__main__":
    main()
