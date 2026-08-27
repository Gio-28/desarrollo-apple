# Creador de contratos - Apple Travel

Herramienta interna: pega los datos del cliente (una linea por dato, con etiquetas), revisa
el contrato, y se envia automaticamente a firma por Dropbox Sign. Acceso restringido por
cuenta (usuario + contraseña + verificacion en dos pasos), administrado desde un panel interno.

## Como funciona

1. **Login**: usuario + contraseña + codigo de verificacion en dos pasos (TOTP, compatible
   con Google Authenticator / Authy). Solo entra quien tenga una cuenta creada por un
   administrador — no hay registro publico.
2. **Crear contrato** → se pega el texto con los datos del cliente y la reserva, una linea
   por dato con el formato `Etiqueta: valor` (hay un boton "Usar plantilla" que llena el
   formato de ejemplo). El orden de las lineas no importa; las etiquetas de lista (Pago,
   Pasajero, Adicional, Incluye, No incluye) se pueden repetir varias veces.
3. Un parser propio (sin IA, sin servicios externos, `app/documents/contrato_turismo/text_parser.py`)
   interpreta esas lineas y las ordena en los campos del contrato. Si falta algo obligatorio,
   no deja continuar.
4. Se muestra una **vista previa** de lo extraido. Se puede **editar** cualquier dato.
5. Al darle **Enviar a firma**, se rellena la plantilla Word original (`app/documents/contrato_turismo/template.docx`,
   sin tocar logos, tablas ni clausulas) y se manda a **Dropbox Sign** para que el cliente firme.

La app esta pensada para crecer: hoy solo existe "Crear contrato", pero se pueden agregar
mas tipos de documento (ej. cotizaciones) sin tocar el resto del sistema — ver el
docstring en `app/documents/__init__.py`.

## Seguridad del acceso

Como se manejan datos sensibles de clientes, el login tiene varias capas:

- **Contraseñas** con hash bcrypt (nunca se guardan en texto plano), minimo 10 caracteres
  combinando mayusculas/minusculas/numeros/simbolos.
- **Verificacion en dos pasos (2FA/TOTP) obligatoria** para todas las cuentas — se activa
  la primera vez que cada persona inicia sesion, escaneando un codigo QR con su celular.
- **Bloqueo automatico de cuenta** tras 5 intentos fallidos (15 minutos), tanto en la
  contraseña como en el codigo de 2FA.
- **Cambio de contraseña obligatorio** en el primer ingreso (las cuentas nuevas y los
  reinicios de clave usan una contraseña temporal de un solo uso).
- **Proteccion anti-bot** en el formulario de login (campo honeypot invisible) y **CSRF**
  en todos los formularios que cambian datos.
- **Cookies de sesion** `httponly`, `secure` (en producción) y `SameSite=Strict`, con
  expiracion a las 8 horas.
- **Cabeceras de seguridad** (CSP, HSTS, X-Frame-Options, etc.) en todas las respuestas.
- Ningun endpoint de creacion/envio de contratos es accesible sin sesion valida.

Las cuentas se administran desde `/admin/usuarios` (solo visible para administradores):
crear usuarios, reiniciar contraseñas, eliminar cuentas. No se puede eliminar al ultimo
administrador ni la propia cuenta desde ahi (para evitar quedar sin acceso).

## Que necesitas antes de arrancar

Cuentas: **GitHub**, **Vercel** y **Dropbox Sign** (ya las tienes). Ademas:

### 1. API key de Dropbox Sign

1. En tu cuenta de Dropbox Sign: **Settings → API → API Key**.
2. Copia la key.

### 2. Base de datos

En Vercel, el proyecto ya tiene conectada una base de datos Postgres (Neon, plan gratuito)
que guarda los usuarios y sus claves TOTP. La variable `DATABASE_URL` la inyecta Vercel
automaticamente — no hay que configurarla a mano en producción.

## Configuracion local

```bash
cd "CREADOR DE CONTRATOS"
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # y completa los valores (incluida una DATABASE_URL de prueba)
```

Genera un `SESSION_SECRET` con:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Corre el servidor:

```bash
uvicorn app.main:app --reload --port 8000
```

Abre `http://localhost:8000`. Si es la primera vez y configuraste `ADMIN_USERNAME` /
`ADMIN_PASSWORD` en el `.env`, esa cuenta se crea automaticamente al arrancar (solo si la
tabla de usuarios esta vacia).

## Desplegar en Vercel

1. Sube este proyecto a un repo de GitHub (dentro de tu cuenta).
2. En Vercel: **Add New → Project** → importa ese repo → Root Directory: el que corresponda
   segun donde quede el repo (si el repo tiene el contenido en su raiz, dejalo vacio).
3. Conecta una base de datos Postgres (recomendado: Neon, desde el tab **Storage** del
   proyecto en Vercel) — esto crea `DATABASE_URL` automaticamente.
4. En **Settings → Environment Variables**, agrega: `SESSION_SECRET`, `BASE_URL`
   (la URL que te da Vercel, ej. `https://tu-proyecto.vercel.app`), `DROPBOX_SIGN_API_KEY`,
   y opcionalmente `ADMIN_USERNAME` / `ADMIN_PASSWORD` para el primer arranque (bootstrap
   del primer administrador).
5. Despliega.

## Estructura del proyecto

```
api/index.py                        entrypoint que usa Vercel
app/main.py                         arma la app FastAPI (sesiones, cabeceras de seguridad, rutas)
app/db.py                           conexion a Postgres + creacion de tabla de usuarios
app/security.py                     hash de contraseñas, TOTP, CSRF, bloqueo de cuenta
app/auth.py                         acceso a datos de usuarios + sesion
app/routes/auth_routes.py           login, cambio de clave forzado, configuracion/verificacion 2FA
app/routes/admin_routes.py          panel de administracion de usuarios
app/documents/                      un modulo por cada tipo de documento
  contrato_turismo/
    schema.py                       campos del contrato + que es obligatorio
    text_parser.py                  interpreta el texto pegado (etiqueta: valor), sin IA
    filler.py                       rellena template.docx con python-docx
    template.docx                   plantilla Word original (no tocar a mano)
app/services/
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
- No hay proteccion tipo CAPTCHA visible (Cloudflare Turnstile, etc.) — se uso honeypot +
  bloqueo por intentos en su lugar para no depender de otra cuenta/servicio externo. Si el
  trafico de bots se vuelve un problema, es facil agregarlo mas adelante.
