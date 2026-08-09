# 📰 Código Abierto — Página semanal automática

Briefing de tecnología, IA y marketing con mirada LATAM, publicado como
**página web** que se renueva sola cada **lunes 7:30 AM (Lima)**.
Las noticias de cada semana **reemplazan** a las anteriores: la página
siempre muestra solo la edición vigente, sin acumular historial.

**Costo total: S/ 0.00.**

---

## Instalación (una sola vez, ~10 minutos)

### 1. Sube estos archivos al repositorio
Crea un repo **público** llamado `codigo-abierto` y sube todo el contenido
de esta carpeta. Ojo: la ruta `.github/workflows/newsletter.yml` debe quedar
exactamente así. Si al arrastrar archivos la carpeta oculta no se sube, créala
manualmente con *Add file → Create new file* escribiendo
`.github/workflows/newsletter.yml` como nombre y pegando el contenido.

### 2. API key de Gemini (gratis, sin tarjeta)
- Entra a **https://aistudio.google.com** con tu cuenta Google.
- *Get API key → Create API key*. Copia la clave.

### 3. Guarda el secreto en el repo
**Settings → Secrets and variables → Actions → New repository secret**

| Nombre | Valor |
|---|---|
| `GEMINI_API_KEY` | tu clave de Gemini |

(Ya no se necesitan secretos de correo: esta versión no envía emails.)

### 4. Activa GitHub Pages
**Settings → Pages → Source: Deploy from a branch → Branch: `main` /docs → Save**

Tu página quedará en: `https://TU-USUARIO.github.io/codigo-abierto`

### 5. Primera edición
**Actions → Código Abierto Semanal → Run workflow → Run workflow**

En ~2 minutos la página mostrará la edición con noticias frescas.
A partir de ahí, se renueva sola todos los lunes.

---

## Cómo "actualizar" las noticias

- **Automático**: cada lunes 7:30 AM el robot reemplaza el contenido.
- **Manual (cuando tú quieras)**: pestaña *Actions → Run workflow* y en
  ~2 minutos la página tiene noticias del momento. Luego recarga la página
  (el botón ⟳ ACTUALIZAR dentro de la página hace la recarga por ti).

> Nota: el botón dentro de la página solo recarga lo publicado; quien
> regenera el contenido con noticias nuevas es el workflow de Actions.

## Personalización

- **Fuentes de noticias**: lista `FEEDS` en `generar.py`.
- **Tono y estructura editorial**: variable `PROMPT` en `generar.py`.
- **Horario**: el `cron` en `.github/workflows/newsletter.yml` (va en UTC;
  Lima = UTC-5).

## Solución de problemas

- **Falla el paso de Gemini** → verifica el secreto `GEMINI_API_KEY`; el
  free tier a veces limita por minuto, vuelve a ejecutar el workflow.
- **La página no cambia** → GitHub Pages tarda 1-2 min tras cada commit;
  luego recarga con Ctrl+F5.
- **El cron no corrió un lunes** → GitHub puede retrasar crons algunos
  minutos u omitirlos en repos sin actividad por 60 días; como la página
  hace un commit semanal, se mantiene activo.
