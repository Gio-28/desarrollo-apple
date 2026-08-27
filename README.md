# Creador de contratos - Apple Travel

Herramienta interna: pega los datos de la reserva (desde la hoja de seguimiento, o a mano),
revisa el contrato, y lo descarga en Word listo para firmar. Acceso restringido por cuenta
(usuario + contraseña + verificacion en dos pasos), administrado desde un panel interno.

## Como funciona

1. **Login**: usuario + contraseña + codigo de verificacion en dos pasos enviado por correo
   (6 digitos, valido 10 minutos). Solo entra quien tenga una cuenta creada por un
   administrador — no hay registro publico.
2. **Crear contrato** → se pega el texto con los datos del cliente y la reserva. Se aceptan
   dos formatos, detectados automaticamente:
   - **Hoja de calculo**: la fila de la hoja interna de seguimiento de reservas (copiada tal
     cual desde Excel/Sheets, con o sin la fila de encabezados), seguida de lineas sueltas
     para los pasajeros (`Nombre - CC 123...`), opcionalmente la habitacion
     (`Habitacion: Estandar`), el texto de incluye / no incluye del programa (la palabra
     "no incluye" sola en una linea marca donde empieza esa seccion), y opcionalmente el
     itinerario dia a dia (la palabra "Itinerario" sola en su linea marca donde empieza,
     y toma el resto del texto).
   - **Etiquetas**: una linea por dato, `Etiqueta: valor` (hay un boton "Usar plantilla" con
     el formato de ejemplo). El orden no importa; las etiquetas de lista (Pago, Pasajero,
     Adicional, Incluye, No incluye, Itinerario) se pueden repetir varias veces (excepto
     Itinerario, que toma todo el texto siguiente).
3. Un parser propio (sin IA, sin servicios externos, `app/documents/contrato_turismo/text_parser.py`)
   interpreta ese texto y lo ordena en los campos del contrato. Si falta algo obligatorio,
   no deja continuar.
4. Se muestra una **vista previa** de lo extraido. Se puede **editar** cualquier dato, incluida
   la imagen de los tiquetes aereos (se arrastra o se elige un archivo; va debajo de "No
   incluye" en el documento final) y el itinerario.
5. Al darle **Descargar contrato**, se rellena la plantilla Word original
   (`app/documents/contrato_turismo/template.docx`, sin tocar logos, tablas ni clausulas) y se
   descarga en `.docx`, listo para revisar y enviar a firma por el medio que prefieran.

> El envio automatico a firma por **Dropbox Sign** ya esta implementado en el codigo
> (`app/services/dropboxsign_client.py`) pero esta desactivado: requiere un plan de API de pago
> de Dropbox Sign (distinto del plan normal de la app web). Para reactivarlo, ver el comentario
> en `app/routes/documents_routes.py`.

La app esta pensada para crecer: hoy solo existe "Crear contrato", pero se pueden agregar
mas tipos de documento (ej. cotizaciones) sin tocar el resto del sistema — ver el
docstring en `app/documents/__init__.py`.

## Seguridad del acceso

Como se manejan datos sensibles de clientes, el login tiene varias capas:

- **Contraseñas** con hash bcrypt (nunca se guardan en texto plano), minimo 10 caracteres
  combinando mayusculas/minusculas/numeros/simbolos.
- **Verificacion en dos pasos por correo obligatoria** para todas las cuentas — cada login
  envia un codigo de 6 digitos (valido 10 minutos) al correo de esa persona. La primera vez,
  cada cuenta configura su propio correo antes de poder entrar.
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

Cuentas: **GitHub** y **Vercel** (ya las tienes). Ademas:

### 1. Base de datos

En Vercel, el proyecto ya tiene conectada una base de datos Postgres (Neon, plan gratuito)
que guarda los usuarios. La variable `DATABASE_URL` la inyecta Vercel automaticamente — no
hay que configurarla a mano en producción.

### 2. Correo para los codigos de verificacion (SMTP)

Se necesita una cuenta de correo que el sistema use para enviar los codigos de 2FA:

1. Genera una **contraseña de aplicacion** de esa cuenta (no la contraseña normal):
   - Gmail/Google Workspace: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) (requiere verificacion en dos pasos activada en esa cuenta).
   - Microsoft 365: [mysignins.microsoft.com/security-info](https://mysignins.microsoft.com/security-info) → Agregar metodo → Contraseña de aplicacion.
2. Guarda `SMTP_USER` (el correo), `SMTP_PASSWORD` (la contraseña de aplicacion), y ajusta
   `SMTP_HOST`/`SMTP_PORT` si no es Gmail (por defecto: `smtp.gmail.com:587`; Microsoft 365
   es `smtp.office365.com:587`).

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
   (la URL que te da Vercel, ej. `https://tu-proyecto.vercel.app`), `SMTP_USER`, `SMTP_PASSWORD`,
   y opcionalmente `ADMIN_USERNAME` / `ADMIN_PASSWORD` para el primer arranque (bootstrap
   del primer administrador). `DROPBOX_SIGN_API_KEY` solo hace falta si reactivas el envio
   automatico a firma (ver nota mas arriba).
5. Despliega.

## Estructura del proyecto

```
api/index.py                        entrypoint que usa Vercel
app/main.py                         arma la app FastAPI (sesiones, cabeceras de seguridad, rutas)
app/db.py                           conexion a Postgres + creacion de tabla de usuarios
app/security.py                     hash de contraseñas, codigos OTP, CSRF, bloqueo de cuenta
app/auth.py                         acceso a datos de usuarios + sesion
app/services/email_client.py        envia el codigo de verificacion por correo (SMTP)
app/routes/auth_routes.py           login, cambio de clave forzado, correo/codigo de verificacion
app/routes/admin_routes.py          panel de administracion de usuarios
app/documents/                      un modulo por cada tipo de documento
  contrato_turismo/
    schema.py                       campos del contrato + que es obligatorio
    text_parser.py                  interpreta el texto pegado (hoja de calculo o etiquetas), sin IA
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
   `/crear/<slug>`, `/api/<slug>/parse` y `/api/<slug>/descargar` — no hay que tocar login,
   diseño ni el flujo de pegar/revisar/descargar.

## Limitaciones conocidas

- La "vista previa" del paso 2 es un resumen ordenado de los datos (no una imagen exacta
  del Word). El documento `.docx` que se descarga si mantiene el diseño original completo.
- La descarga es en formato Word (`.docx`), no PDF: convertir a PDF en el servidor
  requeriria instalar LibreOffice (pesado para este tipo de hosting) o contratar un servicio
  externo de conversion. Pasar de Word a PDF a mano toma segundos (Word/Google Docs
  tienen "Guardar como PDF" integrado).
- El envio automatico a firma por Dropbox Sign esta implementado pero desactivado (requiere
  un plan de API de pago).
- No hay proteccion tipo CAPTCHA visible (Cloudflare Turnstile, etc.) — se uso honeypot +
  bloqueo por intentos en su lugar para no depender de otra cuenta/servicio externo. Si el
  trafico de bots se vuelve un problema, es facil agregarlo mas adelante.
