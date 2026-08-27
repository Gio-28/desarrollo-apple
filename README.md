# Creador de contratos - Apple Travel

Herramienta interna: pega los datos del cliente en cualquier orden, revisa el contrato,
y se envia automaticamente a firma por Dropbox Sign. Acceso restringido a correos
`@appletravel.com.co` (Google Login).

## Como funciona

1. **Login** con Google, restringido al dominio de la empresa.
2. **Crear contrato** → se pega un texto libre (WhatsApp, notas, lo que sea) con los datos
   del cliente y la reserva.
3. El texto se envia a **Claude (Anthropic)**, que extrae los datos y los ordena en los
   campos del contrato. Si falta algo obligatorio, no deja continuar.
4. Se muestra una **vista previa** de lo extraido. Se puede **editar** cualquier dato.
5. Al darle **Enviar a firma**, se rellena la plantilla Word original (`app/documents/contrato_turismo/template.docx`,
   sin tocar logos, tablas ni clausulas) y se manda a **Dropbox Sign** para que el cliente firme.

La app esta pensada para crecer: hoy solo existe "Crear contrato", pero se pueden agregar
mas tipos de documento (ej. cotizaciones) sin tocar el resto del sistema — ver el
docstring en `app/documents/__init__.py`.

## Que necesitas antes de arrancar

Cuentas: **GitHub** y **Vercel** (ya las tienes), y **Dropbox Sign** (ya la tienes).
Ademas necesitas crear/obtener:

### 1. Credenciales de Google (para el login restringido)

1. Ve a [Google Cloud Console](https://console.cloud.google.com/) → crea un proyecto (o usa uno existente).
2. **APIs & Services → OAuth consent screen**: tipo "External" (o "Internal" si tienen Google Workspace),
   nombre de la app "Apple Travel - Contratos", agrega tu correo como soporte.
3. **APIs & Services → Credentials → Create Credentials → OAuth client ID** → tipo "Web application".
4. En **Authorized redirect URIs** agrega:
   - `http://localhost:8000/auth/callback` (para probar en tu computador)
   - `https://<tu-dominio-de-vercel>/auth/callback` (lo agregas despues del primer deploy, cuando ya tengas el dominio)
5. Copia el **Client ID** y **Client Secret**.

### 2. API key de Anthropic (para leer el texto pegado)

1. Ve a [console.anthropic.com](https://console.anthropic.com/) → **API Keys** → crea una nueva.
2. Copia la key (empieza con `sk-ant-...`).

### 3. API key de Dropbox Sign

1. En tu cuenta de Dropbox Sign: **Settings → API → API Key**.
2. Copia la key.

## Configuracion local

```bash
cd "CREADOR DE CONTRATOS"
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # y completa los valores
```

Genera un `SESSION_SECRET` con:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Corre el servidor:

```bash
uvicorn app.main:app --reload --port 8000
```

Abre `http://localhost:8000`.

## Desplegar en Vercel

1. Sube este proyecto a un repo de GitHub (dentro de tu cuenta).
2. En Vercel: **Add New → Project** → importa ese repo.
3. En **Settings → Environment Variables** del proyecto en Vercel, agrega las mismas
   variables del `.env` (`SESSION_SECRET`, `ALLOWED_EMAIL_DOMAIN`, `GOOGLE_CLIENT_ID`,
   `GOOGLE_CLIENT_SECRET`, `BASE_URL`, `ANTHROPIC_API_KEY`, `DROPBOX_SIGN_API_KEY`).
   - `BASE_URL` debe ser la URL publica que te da Vercel, ej. `https://creador-contratos.vercel.app`.
4. Despliega. Copia el dominio final y agregalo como **Authorized redirect URI** en
   Google Cloud (`https://<dominio>/auth/callback`), como se explico arriba.
5. Vuelve a desplegar (o simplemente espera al siguiente push) para que tome el redirect URI nuevo.

## Estructura del proyecto

```
api/index.py                        entrypoint que usa Vercel
app/main.py                         arma la app FastAPI (sesiones, rutas, estaticos)
app/auth.py                         login con Google, restriccion de dominio
app/documents/                      un modulo por cada tipo de documento
  contrato_turismo/
    schema.py                       campos del contrato + que es obligatorio
    filler.py                       rellena template.docx con python-docx
    template.docx                   plantilla Word original (no tocar a mano)
app/services/
  claude_client.py                  llama a Anthropic para extraer los datos
  dropboxsign_client.py             envia el documento final a firma
templates/, static/                 la interfaz (HTML + CSS + JS simple, sin frameworks)
```

## Agregar un nuevo tipo de documento (ej. "Crear cotizacion")

1. Crea `app/documents/cotizacion/` con `schema.py`, `filler.py` y su `template.docx`.
2. Registra un `DocumentType` en `app/documents/__init__.py` (una linea, siguiendo el
   ejemplo de `contrato_turismo`).
3. Automaticamente aparece como tarjeta en la pagina principal, con sus propias rutas
   `/crear/<slug>`, `/api/<slug>/parse` y `/api/<slug>/generar` — no hay que tocar login,
   diseño ni el flujo de pegar/revisar/enviar.

## Limitaciones conocidas

- La "vista previa" del paso 2 es un resumen ordenado de los datos (no una imagen exacta
  del Word), porque convertir a PDF en el navegador requeriria instalar LibreOffice en el
  servidor. El documento Word final que se envia a firma si mantiene el diseño original completo.
- El campo de firma del cliente se marca en el documento con un "text tag" de Dropbox Sign
  (`[sig|req|signer1]`), oculto automaticamente por Dropbox Sign al procesar el envio.
