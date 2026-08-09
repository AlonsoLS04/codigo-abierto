# -*- coding: utf-8 -*-
"""
CÓDIGO ABIERTO — Generador semanal (sitio estático completo)

Publica en docs/ un sitio autónomo en GitHub Pages:
  docs/index.html            -> LANDING (hero, temas, tips, ediciones, sobre mí)
  docs/ediciones/NNN.html    -> cada edición, archivada para siempre
  docs/ediciones/NNN.json    -> contenido completo en JSON
  docs/index.json            -> historial ligero de todas las ediciones

Sin frameworks, sin build, sin dependencias de terceros para servir.
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

# Servicio de captura de correos. Déjalo vacío ("") mientras no lo tengas.
# Ejemplos: "https://buttondown.email/api/emails/embed-subscribe/TU-USUARIO"
#           "https://formspree.io/f/TU-CODIGO"
URL_SUSCRIPCION = ""

# Tus redes (deja "#" en las que aún no quieras enlazar)
REDES = [
    ("LinkedIn", "#"),
    ("GitHub", "https://github.com/alonsols04"),
    ("X / Twitter", "#"),
    ("YouTube", "#"),
]

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
  "tip_analista": {"titulo": "nombre corto del tip", "codigo": "el snippet de codigo real, con saltos de linea reales, max 8 lineas", "cuerpo": "explicación práctica en 1-2 frases", "herramienta": "Oracle SQL | DAX | Python | Power Query | Excel"},
  "dato": {"cifra": "ej: 73%", "contexto": "una frase que explica la cifra"},
  "para_llevar": "una reflexión final de 2-3 frases, accionable"
}
Reglas: "ia" con 2 historias, "marketing" con 2 historias, "datos" con 2 historias
sobre análisis de datos, ciencia de datos, BI o herramientas de datos (elígelas de
las fuentes tipo KDnuggets, Towards Data Science o Analytics Vidhya si están en la
lista).

El "tip_analista" es un truco práctico de análisis de datos que un analista pueda
aplicar hoy mismo; puede ser de tu conocimiento, no necesita venir de las noticias.
Es OBLIGATORIO que traiga un snippet de código real y funcional en el campo
"codigo": entre 3 y 8 líneas, con saltos de línea reales (\\n en el JSON), sin
markdown y sin backticks. Puede incluir un comentario corto explicativo dentro del
código. El campo "herramienta" debe coincidir con el lenguaje del snippet. El campo
"cuerpo" es una nota breve (1-2 frases) sobre cuándo o por qué usarlo, no repite el
código. Varía la herramienta entre semanas: no uses siempre la misma.

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

# ------------------------------------------------------------- 3. UTILES ----

def esc(t):
    return html.escape(str(t) if t is not None else "")

def parrafos(texto):
    """Convierte saltos de linea en <p> separados."""
    bloques = [b.strip() for b in re.split(r"\n\s*\n|\n", str(texto or "")) if b.strip()]
    return "".join(f'<p class="prosa">{esc(b)}</p>' for b in bloques)

def fecha_legible(fecha_iso):
    try:
        d = datetime.date.fromisoformat(fecha_iso)
        return f"{d.day} de {MESES[d.month-1]}, {d.year}"
    except Exception:
        return fecha_iso

def resumen_corto(texto, limite=170):
    texto = re.sub(r"\s+", " ", str(texto or "")).strip()
    if len(texto) <= limite:
        return texto
    return texto[:limite].rsplit(" ", 1)[0] + "…"

def cargar_indice():
    if ARCHIVO_INDEX.exists():
        try:
            return json.loads(ARCHIVO_INDEX.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("[aviso] index.json ilegible; se reinicia el historial.")
    return []

def siguiente_numero(indice):
    if not indice:
        return 1
    return max(int(e["numero"]) for e in indice) + 1

# ------------------------------------------------- RESALTADO DE SINTAXIS ----

KW_SQL = {
    "select","from","where","group","by","order","having","join","left","right",
    "inner","outer","on","as","and","or","not","in","is","null","case","when",
    "then","else","end","over","partition","asc","desc","with","union","all",
    "distinct","between","exists","insert","update","delete","create","table",
    "view","limit","fetch","first","rows","only","ignore","nulls","respect",
}
KW_DAX = {
    "var","return","not","in","true","false","and","or",
}
KW_PY = {
    "import","from","as","def","return","if","elif","else","for","while","in",
    "not","and","or","none","true","false","lambda","with","try","except",
    "class","yield","pass","break","continue","is","del","global","assert",
}

def _keywords(lenguaje):
    l = (lenguaje or "").lower()
    if "python" in l or "pandas" in l:
        return KW_PY, "#"
    if "dax" in l:
        return KW_DAX | KW_SQL, "//"
    if "power query" in l or "m " == l[:2]:
        return KW_DAX, "//"
    if "sql" in l:
        return KW_SQL, "--"
    return KW_SQL | KW_PY, "#"

def resaltar(codigo, lenguaje=""):
    """Colorea un snippet corto. Tokeniza en una sola pasada para no
    inyectar spans dentro de spans."""
    codigo = str(codigo or "").replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not codigo:
        return ""
    kws, marca = _keywords(lenguaje)

    patron = re.compile(
        r"(?P<com>--[^\n]*|//[^\n]*|\#[^\n]*)"
        r"|(?P<txt>\"[^\"\n]*\"|'[^'\n]*')"
        r"|(?P<num>\b\d+(?:\.\d+)?\b)"
        r"|(?P<fun>[A-Za-z_][A-Za-z_0-9\.]*)(?=\s*\()"
        r"|(?P<cor>\[[^\]\n]*\])"
        r"|(?P<pal>[A-Za-z_][A-Za-z_0-9]*)"
    )

    salida, pos = [], 0
    for m in patron.finditer(codigo):
        if m.start() > pos:
            salida.append(esc(codigo[pos:m.start()]))
        tipo = m.lastgroup
        bruto = m.group()
        if tipo == "com":
            salida.append(f'<span class="cm">{esc(bruto)}</span>')
        elif tipo == "txt":
            salida.append(f'<span class="str">{esc(bruto)}</span>')
        elif tipo == "num":
            salida.append(f'<span class="nm">{esc(bruto)}</span>')
        elif tipo == "fun":
            # "df.isna" -> "df." en texto normal, "isna" en color
            if "." in bruto:
                prefijo, base = bruto.rsplit(".", 1)
                salida.append(esc(prefijo + "."))
            else:
                base = bruto
            clase = "kw" if base.lower() in kws else "fn"
            salida.append(f'<span class="{clase}">{esc(base)}</span>')
        elif tipo == "cor":
            salida.append(f'<span class="str">{esc(bruto)}</span>')
        else:
            if bruto.lower() in kws:
                salida.append(f'<span class="kw">{esc(bruto)}</span>')
            else:
                salida.append(esc(bruto))
        pos = m.end()
    if pos < len(codigo):
        salida.append(esc(codigo[pos:]))
    return "".join(salida)

# ------------------------------------------------------------------ CSS -----

CSS = """
:root{
  --bg:#12111c; --fg:#f3f2f7; --card:#1d1b2b; --card2:#262338;
  --muted:#a9a5be; --line:#332f47; --terminal:#0e0d16;
  --violeta:#9b6cf5; --azul:#4f9dfb;
  --kw:#c39cf8; --str:#7fe0a8; --fn:#8ec2fb; --cm:#8d88a5;
  --grad:linear-gradient(120deg,#9b6cf5,#4f9dfb);
}
*{box-sizing:border-box;border-color:var(--line);}
html{scroll-behavior:smooth;}
body{margin:0;background:var(--bg);color:var(--fg);
  font-family:'DM Sans',system-ui,-apple-system,Arial,sans-serif;
  -webkit-font-smoothing:antialiased;line-height:1.6;
  overflow-x:hidden;max-width:100%;}
/* Evita que un hijo ancho (codigo largo) estire toda la pagina:
   los items de grid traen min-width:auto por defecto. */
.rejilla-2>*,.rejilla-3>*,.rejilla-tip>*,.dos-col>*,.pie-grid>*{min-width:0;}
h1,h2,h3,p,a,span{overflow-wrap:break-word;}
h1,h2,h3{font-family:'Space Grotesk',system-ui,sans-serif;letter-spacing:-.03em;
  line-height:1.12;margin:0;}
a{color:inherit;}
.mono{font-family:'JetBrains Mono',ui-monospace,monospace;}
.wrap{max-width:1120px;margin:0 auto;padding:0 20px;}
.wrap-sm{max-width:760px;margin:0 auto;padding:0 20px;}
.grad{background-image:var(--grad);-webkit-background-clip:text;background-clip:text;color:transparent;}
.muted{color:var(--muted);}

/* Encabezado */
.top{display:flex;align-items:center;justify-content:space-between;
  max-width:1120px;margin:0 auto;padding:22px 20px;}
.marca{font-family:'Space Grotesk',sans-serif;font-size:19px;font-weight:700;
  letter-spacing:-.02em;text-decoration:none;}
.btn-borde{display:inline-block;border:1px solid var(--line);border-radius:999px;
  padding:9px 18px;font-size:14px;font-weight:500;color:var(--muted);
  text-decoration:none;transition:.25s;}
.btn-borde:hover{border-color:var(--violeta);color:var(--fg);}

/* Hero */
.hero{position:relative;overflow:hidden;border-bottom:1px solid var(--line);
  background-image:linear-gradient(rgba(255,255,255,.035) 1px,transparent 1px),
    linear-gradient(90deg,rgba(255,255,255,.035) 1px,transparent 1px);
  background-size:56px 56px;}
.hero .halo{position:absolute;top:-160px;left:50%;transform:translateX(-50%);
  width:380px;height:380px;border-radius:50%;background:rgba(155,108,245,.28);
  filter:blur(120px);pointer-events:none;}
.hero-in{position:relative;max-width:760px;margin:0 auto;padding:88px 20px;text-align:center;}
.kicker{font-family:'JetBrains Mono',monospace;font-size:11.5px;text-transform:uppercase;
  letter-spacing:.3em;color:var(--azul);margin:0;}
.hero h1{font-size:clamp(42px,9vw,74px);font-weight:700;margin:24px 0 0;}
.lede{font-size:clamp(17px,2.4vw,20px);color:var(--muted);margin:22px auto 0;max-width:34rem;}

/* Secciones */
section{scroll-margin-top:24px;}
.bloque{padding:88px 0;}
.bloque-alt{border-top:1px solid var(--line);border-bottom:1px solid var(--line);
  background:rgba(38,35,56,.35);}
.h2{font-size:clamp(27px,4.4vw,38px);font-weight:700;}
.sub{color:var(--muted);margin:14px 0 0;max-width:34rem;}

/* Tarjetas de temas */
.rejilla-2{display:grid;gap:18px;margin-top:44px;}
@media(min-width:640px){.rejilla-2{grid-template-columns:1fr 1fr;}}
.tarjeta{height:100%;border:1px solid var(--line);background:var(--card);
  border-radius:18px;padding:26px;transition:border-color .3s;}
.tarjeta:hover{border-color:rgba(155,108,245,.6);}
.num{font-family:'JetBrains Mono',monospace;font-size:13px;color:var(--violeta);}
.tarjeta h3{font-size:20px;font-weight:600;margin:16px 0 0;}
.tarjeta p{font-size:14.5px;color:var(--muted);margin:12px 0 0;}

/* Snippets */
.rejilla-3{display:grid;gap:18px;margin-top:44px;}
@media(min-width:1000px){.rejilla-3{grid-template-columns:repeat(3,1fr);}}
.snip{display:flex;flex-direction:column;height:100%;overflow:hidden;
  min-width:0;max-width:100%;
  border:1px solid var(--line);background:var(--card);border-radius:18px;}
.snip-top{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;
  align-items:center;padding:15px 18px;border-bottom:1px solid var(--line);}
.snip-lbl{font-size:11px;font-weight:600;text-transform:uppercase;
  letter-spacing:.18em;color:var(--violeta);margin:0;}
.snip-top h3{font-size:16px;font-weight:600;margin:5px 0 0;}
.chip{flex-shrink:0;border:1px solid var(--line);border-radius:999px;padding:4px 12px;
  font-family:'JetBrains Mono',monospace;font-size:10.5px;text-transform:uppercase;
  letter-spacing:.05em;color:var(--muted);white-space:nowrap;}
.snip pre{flex:1;margin:0;padding:18px;background:var(--terminal);
  overflow-x:auto;-webkit-overflow-scrolling:touch;
  max-width:100%;min-width:0;
  font-family:'JetBrains Mono',monospace;font-size:12.5px;line-height:1.75;}
.snip pre code{display:block;min-width:0;}
.snip-pie{border-top:1px solid var(--line);padding:15px 18px;font-size:13.5px;color:var(--muted);margin:0;}
.kw{color:var(--kw);} .str{color:var(--str);} .fn{color:var(--fn);}
.cm{color:var(--cm);font-style:italic;} .nm{color:var(--azul);}

/* Listado de ediciones */
.lista{list-style:none;margin:44px 0 0;padding:0;border-top:1px solid var(--line);}
.lista li{border-bottom:1px solid var(--line);}
.lista a{display:grid;gap:10px;padding:26px 10px;text-decoration:none;transition:background .3s;}
@media(min-width:640px){.lista a{grid-template-columns:9.5rem minmax(0,1fr);gap:32px;}}
.lista a:hover{background:rgba(38,35,56,.5);}
.meta{font-family:'JetBrains Mono',monospace;font-size:13px;color:var(--muted);}
.meta .n{color:var(--violeta);}
@media(min-width:640px){.meta .f{display:block;margin-top:4px;}}
.lista h3{font-size:20px;font-weight:600;}
.lista p{font-size:14.5px;color:var(--muted);margin:9px 0 0;}
.flecha{display:inline-block;margin-top:12px;font-size:14px;font-weight:500;color:var(--azul);}
.vacio{margin-top:40px;border:1px solid var(--line);background:var(--card);
  border-radius:18px;padding:30px;text-align:center;color:var(--muted);}

/* Sobre mí */
.dos-col{display:grid;gap:36px;}
@media(min-width:1000px){.dos-col{grid-template-columns:minmax(0,1fr) minmax(0,1.4fr);}}
.dos-col .prosa{font-size:17.5px;color:var(--muted);margin:0 0 18px;}
.dos-col .prosa strong{color:var(--fg);font-weight:500;}

/* Formulario */
.form{width:100%;}
.form-fila{display:grid;gap:12px;}
@media(min-width:520px){.form-fila{grid-template-columns:minmax(0,1fr) auto;}}
.form input{height:50px;width:100%;min-width:0;border:1px solid var(--line);
  background:var(--card);border-radius:13px;padding:0 16px;font-size:16px;
  color:var(--fg);font-family:inherit;}
.form input::placeholder{color:var(--muted);}
.form input:focus{outline:none;border-color:var(--violeta);
  box-shadow:0 0 0 3px rgba(155,108,245,.25);}
.form button{height:50px;flex-shrink:0;border:0;border-radius:13px;padding:0 26px;
  background-image:var(--grad);color:#fff;font-size:16px;font-weight:600;
  font-family:inherit;cursor:pointer;transition:.2s;}
.form button:hover{transform:translateY(-2px);
  box-shadow:0 24px 60px -28px rgba(155,108,245,.7);}
.form-nota{margin:12px 0 0;font-size:13.5px;color:var(--muted);}
.form-nota.err{color:#f87171;} .form-nota.ok{color:var(--azul);}

/* Pie */
footer{border-top:1px solid var(--line);}
.pie-grid{display:grid;gap:44px;padding:72px 0;}
@media(min-width:1000px){.pie-grid{grid-template-columns:1fr 1fr;}}
.redes{list-style:none;margin:18px 0 0;padding:0;}
.redes li{margin-bottom:11px;}
.redes a{font-size:17px;font-weight:500;text-decoration:none;transition:color .25s;}
.redes a:hover{color:var(--violeta);}
.copy{border-top:1px solid var(--line);}
.copy p{max-width:1120px;margin:0 auto;padding:22px 20px;font-size:13.5px;color:var(--muted);}

/* Edición: portada y historias */
.destacada{border:1px solid rgba(155,108,245,.45);background:var(--card);
  border-radius:18px;padding:32px;box-shadow:0 0 60px -30px var(--violeta);}
.et{font-family:'JetBrains Mono',monospace;font-size:11.5px;text-transform:uppercase;
  letter-spacing:.18em;color:var(--violeta);}
.destacada h2{font-size:clamp(23px,3.6vw,30px);font-weight:700;margin:12px 0 0;}
.destacada .prosa{color:var(--muted);margin:16px 0 0;}
.latam{margin-top:22px;border-left:2px solid var(--azul);
  background:rgba(38,35,56,.55);border-radius:12px;padding:16px 18px;}
.latam .t{font-family:'JetBrains Mono',monospace;font-size:10.5px;text-transform:uppercase;
  letter-spacing:.2em;color:var(--azul);margin:0;}
.latam p{margin:8px 0 0;font-size:14.5px;color:rgba(243,242,247,.88);line-height:1.65;}
.leer{display:inline-block;margin-top:22px;font-size:14px;font-weight:500;
  color:var(--azul);text-decoration:none;}
.leer:hover{color:var(--violeta);}
.historia{display:flex;flex-direction:column;height:100%;border:1px solid var(--line);
  background:var(--card);border-radius:18px;padding:26px;}
.historia h3{font-size:20px;font-weight:600;margin:12px 0 0;}
.historia .prosa{font-size:14.5px;color:var(--muted);margin:12px 0 0;}
.cifra{display:flex;flex-direction:column;justify-content:center;height:100%;
  border:1px solid var(--line);background:var(--card);border-radius:18px;
  padding:34px;text-align:center;}
.cifra .n{font-family:'Space Grotesk',sans-serif;font-size:clamp(44px,8vw,60px);font-weight:700;}
.cifra p{font-size:14.5px;color:var(--muted);margin:16px 0 0;}
.llevar{font-size:clamp(19px,3vw,25px);font-style:italic;line-height:1.55;
  color:rgba(243,242,247,.92);margin:20px 0 0;}
.rejilla-tip{display:grid;gap:18px;}
@media(min-width:1000px){.rejilla-tip{grid-template-columns:minmax(0,1.4fr) minmax(0,1fr);}}

/* Animación de entrada */
/* Movil: codigo mas compacto y menos padding lateral */
@media(max-width:520px){
  .snip pre{font-size:11.5px;padding:14px;line-height:1.7;}
  .wrap,.wrap-sm{padding:0 16px;}
  .tarjeta,.historia,.snip-top,.snip-pie{padding-left:20px;padding-right:20px;}
  .destacada{padding:24px 20px;}
  .cifra{padding:28px 20px;}
  .bloque{padding:64px 0;}
  .hero-in{padding:64px 16px;}
  .lista a{padding:22px 4px;}
}
.rev{opacity:0;transform:translateY(24px);
  transition:opacity .7s cubic-bezier(.22,1,.36,1),transform .7s cubic-bezier(.22,1,.36,1);}
.rev.vis{opacity:1;transform:none;}
@media(prefers-reduced-motion:reduce){.rev{opacity:1;transform:none;transition:none;}}
"""

JS_REVEAL = """
(function(){
  var els=document.querySelectorAll('.rev');
  if(!('IntersectionObserver' in window)){
    els.forEach(function(e){e.classList.add('vis');});return;
  }
  var io=new IntersectionObserver(function(en){
    en.forEach(function(x){
      if(x.isIntersecting){x.target.classList.add('vis');io.unobserve(x.target);}
    });
  },{threshold:.12,rootMargin:'0px 0px -60px 0px'});
  els.forEach(function(e){io.observe(e);});
})();
"""

JS_FORM = """
(function(){
  var RE=/^[^\\s@]+@[^\\s@]+\\.[a-zA-Z]{2,}$/;
  document.querySelectorAll('form.form').forEach(function(f){
    var input=f.querySelector('input'), nota=f.querySelector('.form-nota');
    var base=nota.textContent, activo=f.getAttribute('data-activo')==='1';
    f.addEventListener('submit',function(ev){
      if(!RE.test((input.value||'').trim())){
        ev.preventDefault();
        nota.className='form-nota err';
        nota.textContent='Ingresa un correo válido, por ejemplo: nombre@dominio.com';
        return;
      }
      if(!activo){
        ev.preventDefault();
        nota.className='form-nota ok';
        nota.textContent='Las suscripciones por correo abren pronto. Por ahora, guarda esta página: cada lunes hay edición nueva.';
        input.value='';
        return;
      }
      nota.className='form-nota ok';
      nota.textContent='Enviando...';
    });
    input.addEventListener('input',function(){
      nota.className='form-nota'; nota.textContent=base;
    });
  });
})();
"""

FUENTES_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    'family=Space+Grotesk:wght@500;700&family=DM+Sans:wght@400;500;600&'
    'family=JetBrains+Mono:wght@400;500&display=swap">'
)

def cabeza(titulo, descripcion, url_canonica):
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(titulo)}</title>
<meta name="description" content="{esc(descripcion)}">
<meta name="author" content="Código Abierto">
<link rel="canonical" href="{esc(url_canonica)}">
<meta property="og:title" content="{esc(titulo)}">
<meta property="og:description" content="{esc(descripcion)}">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
{FUENTES_LINK}
<style>{CSS}</style>
</head>
<body>"""

def pie_scripts():
    return f"<script>{JS_REVEAL}{JS_FORM}</script>\n</body>\n</html>"

def formulario(idc, compacto=False):
    activo = "1" if URL_SUSCRIPCION else "0"
    accion = f' action="{esc(URL_SUSCRIPCION)}" method="post"' if URL_SUSCRIPCION else ""
    nota = ("Sin spam. Cancela cuando quieras." if compacto
            else "Un correo cada lunes. Sin spam, cancela cuando quieras.")
    return f"""
<form class="form" data-activo="{activo}"{accion} novalidate>
  <div class="form-fila">
    <label for="{idc}" style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);">Correo electrónico</label>
    <input id="{idc}" name="email" type="email" inputmode="email" autocomplete="email" placeholder="tu@correo.com">
    <button type="submit">Suscribirme</button>
  </div>
  <p class="form-nota">{nota}</p>
</form>"""

# --------------------------------------------------------- 4. LANDING HTML --

TEMAS = [
    ("01", "IA aplicada y herramientas",
     "Casos reales, prompts que funcionan y las herramientas que sí vale la pena probar esta semana."),
    ("02", "Análisis de datos y tips prácticos",
     "SQL, Power BI y Python: consultas, modelos y trucos que puedes usar el mismo lunes."),
    ("03", "Automatización y productividad",
     "Flujos que eliminan trabajo repetitivo: scripts, integraciones y pequeños hacks de rutina."),
    ("04", "Marketing digital y tendencias LATAM",
     "Qué está funcionando en la región, con datos y sin humo de gurús."),
]

# Tips de respaldo: solo se usan mientras el historial no tenga suficientes
# tips reales (las primeras semanas). Se van reemplazando solos.
SNIPPETS_RESPALDO = [
    {
        "titulo": "Ventas del año anterior en DAX",
        "herramienta": "DAX",
        "codigo": "// Compara periodos sin crear tablas extra\n"
                  "Ventas LY = CALCULATE(\n"
                  "    [Ventas], SAMEPERIODLASTYEAR(Calendario[Fecha])\n"
                  ")",
        "cuerpo": "Úsalo con una tabla de fechas marcada como calendario para evitar contextos raros.",
    },
    {
        "titulo": "Top 3 por categoría en SQL",
        "herramienta": "Oracle SQL",
        "codigo": "SELECT categoria, producto, total\n"
                  "FROM (SELECT c.*,\n"
                  "             ROW_NUMBER() OVER (PARTITION BY categoria\n"
                  "                                ORDER BY total DESC) rn\n"
                  "      FROM ventas c)\n"
                  "WHERE rn <= 3;",
        "cuerpo": "Window functions vencen a las subconsultas correlacionadas: menos lecturas, mismo resultado.",
    },
    {
        "titulo": "Perfilado rápido en Python",
        "herramienta": "Python",
        "codigo": "import pandas as pd\n\n"
                  "# % de nulos por columna, ordenado\n"
                  "nulos = df.isna().mean().sort_values(ascending=False)\n"
                  "print((nulos * 100).round(1))",
        "cuerpo": "Antes de modelar, revisa nulos: ahí empieza la mayoría de los errores.",
    },
]

def tips_para_landing(indice, cantidad=3):
    """Toma los tips reales de las ediciones más recientes. Si aún no hay
    suficientes, completa con los de respaldo."""
    tips = []
    for e in indice:
        t = e.get("tip") or {}
        if t.get("codigo") and t.get("titulo"):
            tips.append({
                "titulo": t["titulo"],
                "herramienta": t.get("herramienta", ""),
                "codigo": t["codigo"],
                "cuerpo": t.get("cuerpo", ""),
                "numero": e["numero"],
            })
        if len(tips) >= cantidad:
            break
    if len(tips) < cantidad:
        tips += SNIPPETS_RESPALDO[: cantidad - len(tips)]
    return tips[:cantidad]

def html_snippets(indice):
    salida = ""
    for i, s in enumerate(tips_para_landing(indice)):
        # Si el tip viene de una edición real, se enlaza a ella
        num = s.get("numero")
        etiqueta = f"Tip · edición #{esc(num)}" if num else "Tip de la semana"
        pie = esc(s.get("cuerpo", ""))
        if num:
            pie += (f' <a href="ediciones/{esc(num)}.html" '
                    f'style="color:var(--azul);text-decoration:none">Ver edición →</a>')
        salida += f"""
      <article class="snip rev" style="transition-delay:{i*100}ms">
        <header class="snip-top">
          <div style="min-width:0">
            <p class="snip-lbl">{etiqueta}</p>
            <h3>{esc(s['titulo'])}</h3>
          </div>
          <span class="chip">{esc(s.get('herramienta',''))}</span>
        </header>
        <pre><code>{resaltar(s['codigo'], s.get('herramienta',''))}</code></pre>
        <p class="snip-pie">{pie}</p>
      </article>"""
    return salida

def html_lista_ediciones(indice):
    if not indice:
        return ('<div class="vacio rev">La primera edición se publica el próximo lunes. '
                'Suscríbete para no perdértela.</div>')
    filas = ""
    for i, e in enumerate(indice):
        filas += f"""
      <li class="rev" style="transition-delay:{min(i,6)*70}ms">
        <a href="ediciones/{esc(e['numero'])}.html">
          <div class="meta"><span class="n">#{esc(e['numero'])}</span><span class="f">{esc(fecha_legible(e['fecha']))}</span></div>
          <div style="min-width:0">
            <h3>{esc(e['titulo'])}</h3>
            <p>{esc(e['resumen'])}</p>
            <span class="flecha">Leer edición →</span>
          </div>
        </a>
      </li>"""
    return f'<ul class="lista">{filas}</ul>'

def render_landing(indice):
    redes = "".join(
        f'<li><a href="{esc(h)}"{" target=_blank rel=noopener" if h.startswith("http") else ""}>{esc(l)}</a></li>'
        for l, h in REDES
    )
    temas = "".join(
        f"""
      <div class="rev" style="transition-delay:{i*90}ms">
        <div class="tarjeta">
          <span class="num">{n}</span>
          <h3>{esc(t)}</h3>
          <p>{esc(b)}</p>
        </div>
      </div>"""
        for i, (n, t, b) in enumerate(TEMAS)
    )
    return (
        cabeza(
            "Código Abierto — Newsletter de IA, datos y marketing",
            "Newsletter semanal en español para LATAM: IA aplicada, análisis de datos, "
            "automatización y marketing digital. Cada lunes, sin filtro.",
            f"{URL_BASE}/",
        )
        + f"""
<header class="top">
  <a class="marca" href="./">Código<span class="grad"> Abierto</span></a>
  <a class="btn-borde" href="#suscribirse">Suscribirme</a>
</header>

<main>
  <section class="hero">
    <div class="halo"></div>
    <div class="hero-in">
      <div class="rev">
        <p class="kicker">Newsletter semanal · LATAM</p>
        <h1>Código <span class="grad">Abierto</span></h1>
        <p class="lede">IA, datos y marketing, sin filtro, cada lunes.</p>
      </div>
      <div class="rev" style="transition-delay:120ms;max-width:28rem;margin:40px auto 0;text-align:left">
        {formulario("email-hero")}
      </div>
    </div>
  </section>

  <section class="bloque">
    <div class="wrap">
      <div class="rev">
        <h2 class="h2">Qué encontrarás</h2>
        <p class="sub">Cuatro frentes, un solo correo. Corto, aplicable y en español.</p>
      </div>
      <div class="rejilla-2">{temas}</div>
    </div>
  </section>

  <section class="bloque bloque-alt">
    <div class="wrap">
      <div class="rev">
        <h2 class="h2">Tips rápidos</h2>
        <p class="sub">Los últimos snippets publicados. Cópialos y úsalos hoy mismo.</p>
      </div>
      <div class="rejilla-3">{html_snippets(indice)}</div>
    </div>
  </section>

  <section class="bloque" id="ediciones">
    <div class="wrap">
      <div class="rev">
        <h2 class="h2">Ediciones recientes</h2>
        <p class="sub">Las últimas entregas publicadas cada lunes. El archivo queda disponible siempre.</p>
      </div>
      {html_lista_ediciones(indice)}
    </div>
  </section>

  <section class="bloque bloque-alt">
    <div class="wrap dos-col">
      <div class="rev"><h2 class="h2">Sobre mí</h2></div>
      <div class="rev" style="transition-delay:100ms">
        <p class="prosa">Soy analista de datos y producto en el sector seguros. Trabajo todos los días con
          <strong>Oracle SQL</strong>, <strong>Power BI</strong> y <strong>Python</strong>,
          y me obsesiona automatizar lo que no debería hacerse a mano.</p>
        <p class="prosa">Escribo <strong>Código Abierto</strong> para compartir lo que aprendo aplicando
          IA y datos a problemas de negocio reales en LATAM: sin teoría inflada, con ejemplos
          que puedes reutilizar.</p>
      </div>
    </div>
  </section>
</main>

<footer id="suscribirse">
  <div class="wrap pie-grid">
    <div class="rev">
      <h2 class="h2" style="font-size:clamp(23px,3.6vw,30px)">Únete a <span class="grad">Código Abierto</span></h2>
      <p class="sub">IA, datos y marketing en tu correo cada lunes por la mañana.</p>
      <div style="max-width:28rem;margin-top:24px">{formulario("email-pie", compacto=True)}</div>
    </div>
    <div class="rev" style="transition-delay:120ms">
      <p class="mono" style="font-size:11.5px;text-transform:uppercase;letter-spacing:.2em;color:var(--muted);margin:0">Sígueme</p>
      <ul class="redes">{redes}</ul>
    </div>
  </div>
  <div class="copy"><p>© {datetime.date.today().year} Código Abierto. Hecho desde LATAM.</p></div>
</footer>
"""
        + pie_scripts()
    )

# --------------------------------------------------------- 5. EDICION HTML --

def html_historia(h, etiqueta, delay):
    return f"""
      <div class="rev" style="transition-delay:{delay}ms">
        <article class="historia">
          <span class="et">{esc(etiqueta)}</span>
          <h3>{esc(h.get('titulo'))}</h3>
          {parrafos(h.get('cuerpo'))}
          <div class="latam">
            <p class="t">Ángulo LATAM</p>
            <p>{esc(h.get('angulo_latam'))}</p>
          </div>
          <a class="leer" href="{esc(h.get('enlace',''))}" target="_blank" rel="noopener">
            Leer más en {esc(h.get('fuente',''))} →</a>
        </article>
      </div>"""

def html_seccion_historias(titulo, etiqueta, historias, alt=False):
    if not historias:
        return ""
    tarjetas = "".join(
        html_historia(h, etiqueta, i * 90) for i, h in enumerate(historias)
    )
    clase = "bloque bloque-alt" if alt else "bloque"
    return f"""
  <section class="{clase}" style="padding:64px 0">
    <div class="wrap">
      <div class="rev"><h2 class="h2" style="font-size:clamp(23px,3.6vw,30px)">{esc(titulo)}</h2></div>
      <div class="rejilla-2" style="margin-top:32px">{tarjetas}</div>
    </div>
  </section>"""

def render_edicion(c, numero_str, fecha_iso, indice):
    portada = c["portada"]
    tip = c.get("tip_analista", {}) or {}
    dato = c.get("dato", {}) or {}

    # Otras ediciones (para navegar sin volver a la landing)
    otras = [e for e in indice if e["numero"] != numero_str][:6]
    bloque_otras = ""
    if otras:
        filas = "".join(
            f"""
        <li class="rev">
          <a href="{esc(e['numero'])}.html">
            <div class="meta"><span class="n">#{esc(e['numero'])}</span><span class="f">{esc(fecha_legible(e['fecha']))}</span></div>
            <div style="min-width:0"><h3>{esc(e['titulo'])}</h3></div>
          </a>
        </li>"""
            for e in otras
        )
        bloque_otras = f"""
  <section class="bloque" style="padding:64px 0">
    <div class="wrap">
      <div class="rev"><h2 class="h2" style="font-size:clamp(21px,3.2vw,27px)">Otras ediciones</h2></div>
      <ul class="lista" style="margin-top:28px">{filas}</ul>
    </div>
  </section>"""

    bloque_tip = ""
    if tip.get("titulo") or tip.get("cuerpo") or tip.get("codigo"):
        if tip.get("codigo"):
            cuerpo_pre = resaltar(tip["codigo"], tip.get("herramienta", ""))
            pie_tip = (f'<p class="snip-pie">{esc(tip.get("cuerpo",""))}</p>'
                       if tip.get("cuerpo") else "")
        else:
            # Ediciones antiguas sin campo "codigo": el cuerpo va como texto
            cuerpo_pre = f'<span style="white-space:pre-wrap">{esc(tip.get("cuerpo"))}</span>'
            pie_tip = ""
        bloque_tip = f"""
        <div class="rev">
          <article class="snip">
            <header class="snip-top">
              <div style="min-width:0">
                <p class="snip-lbl">Tip del analista</p>
                <h3>{esc(tip.get('titulo'))}</h3>
              </div>
              <span class="chip">{esc(tip.get('herramienta',''))}</span>
            </header>
            <pre><code>{cuerpo_pre}</code></pre>
            {pie_tip}
          </article>
        </div>"""

    bloque_dato = ""
    if dato.get("cifra"):
        bloque_dato = f"""
        <div class="rev" style="transition-delay:100ms">
          <div class="cifra">
            <p class="n grad">{esc(dato.get('cifra'))}</p>
            <p>{esc(dato.get('contexto'))}</p>
          </div>
        </div>"""

    fila_tip = ""
    if bloque_tip or bloque_dato:
        fila_tip = f"""
  <section class="bloque" style="padding:64px 0">
    <div class="wrap rejilla-tip">{bloque_tip}{bloque_dato}</div>
  </section>"""

    bloque_llevar = ""
    if c.get("para_llevar"):
        bloque_llevar = f"""
  <section class="bloque bloque-alt" style="padding:72px 0">
    <div class="wrap-sm" style="text-align:center">
      <div class="rev">
        <p class="kicker">Para llevar</p>
        <p class="llevar">{esc(c['para_llevar'])}</p>
        <p style="margin-top:36px"><a class="btn-borde" href="../#ediciones">← Volver al listado</a></p>
      </div>
    </div>
  </section>"""

    titulo_pagina = f"Edición #{numero_str} — {portada.get('titulo','')} | Código Abierto"
    descripcion = resumen_corto(portada.get("cuerpo"), 150)

    return (
        cabeza(titulo_pagina, descripcion, f"{URL_BASE}/ediciones/{numero_str}.html")
        + f"""
<header class="top">
  <a class="marca" href="../">Código<span class="grad"> Abierto</span></a>
  <a class="btn-borde" href="../#ediciones">← Volver al listado</a>
</header>

<main>
  <section class="hero">
    <div class="halo"></div>
    <div class="hero-in" style="max-width:860px;padding:68px 20px;text-align:left">
      <div class="rev">
        <p class="kicker">Edición #{esc(numero_str)} · {esc(fecha_legible(fecha_iso))}</p>
        <h1 style="font-size:clamp(32px,6vw,52px);margin-top:20px">{esc(portada.get('titulo'))}</h1>
      </div>
    </div>
  </section>

  <section class="bloque" style="padding:64px 0">
    <div class="wrap-sm" style="max-width:860px">
      <div class="rev">
        <article class="destacada">
          <span class="et">Portada</span>
          <h2>{esc(portada.get('titulo'))}</h2>
          {parrafos(portada.get('cuerpo'))}
          <div class="latam">
            <p class="t">Ángulo LATAM</p>
            <p>{esc(portada.get('angulo_latam'))}</p>
          </div>
          <a class="leer" href="{esc(portada.get('enlace',''))}" target="_blank" rel="noopener">
            Leer más en {esc(portada.get('fuente',''))} →</a>
        </article>
      </div>
    </div>
  </section>
{html_seccion_historias("Inteligencia artificial", "IA", c.get("ia", []), alt=True)}
{html_seccion_historias("Marketing", "Marketing", c.get("marketing", []))}
{html_seccion_historias("Datos", "Datos", c.get("datos", []), alt=True)}
{fila_tip}
{bloque_llevar}
{bloque_otras}
</main>

<footer>
  <div class="wrap pie-grid" style="padding:56px 0">
    <div class="rev">
      <h2 class="h2" style="font-size:clamp(21px,3.2vw,27px)">Únete a <span class="grad">Código Abierto</span></h2>
      <p class="sub">IA, datos y marketing en tu correo cada lunes por la mañana.</p>
      <div style="max-width:28rem;margin-top:24px">{formulario("email-edicion", compacto=True)}</div>
    </div>
  </div>
  <div class="copy"><p>© {datetime.date.today().year} Código Abierto. Hecho desde LATAM.</p></div>
</footer>
"""
        + pie_scripts()
    )

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

    tip = contenido.get("tip_analista", {}) or {}
    indice_actualizado = [{
        "numero": numero_str,
        "fecha": fecha_iso,
        "titulo": contenido["portada"]["titulo"],
        "resumen": resumen_corto(contenido["portada"]["cuerpo"]),
        "tip": {
            "titulo": tip.get("titulo", ""),
            "herramienta": tip.get("herramienta", ""),
            "codigo": tip.get("codigo", ""),
            "cuerpo": tip.get("cuerpo", ""),
        },
        "url_json": f"{URL_BASE}/ediciones/{numero_str}.json",
        "url_html": f"{URL_BASE}/ediciones/{numero_str}.html",
    }] + indice

    # --- a) Landing (raíz del sitio) ---
    (DIR_DOCS / "index.html").write_text(
        render_landing(indice_actualizado), encoding="utf-8")
    print("Landing publicada: docs/index.html")

    # --- b) Página de esta edición ---
    (DIR_EDICIONES / f"{numero_str}.html").write_text(
        render_edicion(contenido, numero_str, fecha_iso, indice_actualizado),
        encoding="utf-8")

    # --- c) JSON completo de la edición ---
    (DIR_EDICIONES / f"{numero_str}.json").write_text(
        json.dumps({
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
        }, ensure_ascii=False, indent=2),
        encoding="utf-8")

    # --- d) Historial ---
    ARCHIVO_INDEX.write_text(
        json.dumps(indice_actualizado, ensure_ascii=False, indent=2),
        encoding="utf-8")

    # --- e) Reescribe las páginas anteriores para que su listado
    #        "Otras ediciones" incluya la nueva ---
    for e in indice:
        ruta_json = DIR_EDICIONES / f"{e['numero']}.json"
        if not ruta_json.exists():
            continue
        try:
            viejo = json.loads(ruta_json.read_text(encoding="utf-8"))
            (DIR_EDICIONES / f"{e['numero']}.html").write_text(
                render_edicion(viejo, e["numero"], e["fecha"], indice_actualizado),
                encoding="utf-8")
        except Exception as ex:
            print(f"[aviso] no se pudo regenerar #{e['numero']}: {ex}")

    print(f"Edición #{numero_str} publicada · historial: {len(indice_actualizado)} ediciones")

if __name__ == "__main__":
    main()
