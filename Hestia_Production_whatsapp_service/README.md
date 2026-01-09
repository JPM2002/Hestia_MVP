# 🏨 Hestia Production WhatsApp Service

Sistema de gestión de WhatsApp para hoteles con soporte de tickets, FAQs y notificaciones automáticas.

## 📋 Características

### WhatsApp Gateway
- ✅ Integración con WhatsApp Cloud API
- ✅ Gestión de conversaciones y sesiones
- ✅ Pipeline de procesamiento de mensajes
- ✅ Clasificación inteligente con NLU
- ✅ Sistema de intents y routing

### Sistema de Tickets
- ✅ Creación y gestión de tickets
- ✅ Asignación a agentes
- ✅ Estados y seguimiento
- ✅ Integración con panel administrativo

### FAQs
- ✅ Respuestas automáticas a preguntas frecuentes
- ✅ Clasificación semántica
- ✅ Contexto hotelero

### 🔔 Notification Service (NUEVO)
- ✅ Notificaciones automáticas por WhatsApp
- ✅ Tickets asignados → Notifica al huésped
- ✅ Tickets resueltos → Notifica + Encuesta CSAT
- ✅ FAQs respondidas → Encuesta de satisfacción
- ✅ Worker independiente con polling

---

## 🏗️ Arquitectura

```
Hestia_Production_whatsapp_service/
├── gateway_app/                     # Aplicación principal
│   ├── blueprints/                  # Flask blueprints
│   │   └── webhook/                 # Webhook de WhatsApp
│   │
│   ├── core/                        # Lógica core
│   │   └── conversation/            # Sistema de conversación
│   │       ├── orchestrator.py      # Orquestador principal
│   │       ├── pipeline/            # Pipeline de procesamiento
│   │       └── session.py           # Gestión de sesiones
│   │
│   ├── services/                    # Servicios
│   │   ├── db.py                    # Acceso a base de datos
│   │   ├── whatsapp_api.py          # Cliente WhatsApp
│   │   └── notifications/           # 🆕 Servicio de notificaciones
│   │       ├── handlers.py          # Lógica de notificaciones
│   │       ├── notification_db.py   # DB para notificaciones
│   │       ├── notification_whatsapp.py  # Cliente WhatsApp
│   │       └── notification_config.py    # Configuración
│   │
│   ├── workers/                     # 🆕 Workers en background
│   │   └── notification_worker.py   # Worker de notificaciones
│   │
│   └── migrations/                  # Migraciones SQL
│       ├── 001_add_notification_fields.sql
│       └── 002_minimal_notification_fields.sql
│
├── run.py                           # Entry point principal (Flask)
├── run_notification_worker.py       # 🆕 Entry point del worker
├── requirements.txt                 # Dependencias
├── .env                             # Variables de entorno
└── docs/                            # Documentación
    └── NOTIFICATION_SERVICE.md      # 🆕 Docs de notificaciones

```

---

## 🚀 Instalación

### 1. Clonar el repositorio

```bash
cd Hestia_Production_whatsapp_service
```

### 2. Crear entorno virtual

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

Edita el archivo `.env` con tus credenciales:

```env
DATABASE_URL="postgresql://..."
WHATSAPP_CLOUD_TOKEN="..."
WHATSAPP_CLOUD_PHONE_ID="..."
OPENAI_API_KEY="..."

# Notification Service
POLLING_INTERVAL_SECONDS=10
ENABLE_ASSIGNMENT_NOTIFICATIONS=true
ENABLE_RESOLUTION_NOTIFICATIONS=true
ENABLE_CSAT_SURVEYS=true
ENABLE_FAQ_SURVEYS=true
```

### 5. Aplicar migraciones

**PostgreSQL:**
```bash
psql -h host -U user -d database -f gateway_app/migrations/002_minimal_notification_fields.sql
```

**SQLite:**
```bash
sqlite3 hestia_V2.db < gateway_app/migrations/001_add_notification_fields.sql
```

---

## ▶️ Uso

### Servidor principal (Flask)

```bash
python run.py
```

El servidor estará disponible en `http://localhost:5000`

### Worker de notificaciones (Background)

```bash
python run_notification_worker.py
```

El worker monitoreará la base de datos y enviará notificaciones automáticamente.

**Logs del worker:**
```
[2026-01-08 10:30:00] INFO [worker] 🚀 NOTIFICATION SERVICE - INICIANDO
[2026-01-08 10:30:10] INFO [handlers] [ASSIGNMENTS] Notificación enviada para ticket 123
```

---

## 📚 Documentación

- **[Notification Service](docs/NOTIFICATION_SERVICE.md)** - Documentación completa del servicio de notificaciones
- **API Endpoints** - Ver código en `gateway_app/blueprints/webhook/routes.py`

---

## 🔧 Configuración

### Ajustar notificaciones

```env
# Intervalo de polling (segundos)
POLLING_INTERVAL_SECONDS=10

# Habilitar/deshabilitar tipos de notificaciones
ENABLE_ASSIGNMENT_NOTIFICATIONS=true
ENABLE_RESOLUTION_NOTIFICATIONS=true
ENABLE_CSAT_SURVEYS=true
ENABLE_FAQ_SURVEYS=true

# Delay antes de enviar encuesta FAQ (segundos)
FAQ_SURVEY_DELAY_SECONDS=30
```

### Nivel de logging

```env
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
```

---

## 🚀 Deployment en Producción

### Con Systemd (Linux)

Crea dos servicios:

1. **Flask app** (`/etc/systemd/system/hestia-gateway.service`):
```ini
[Unit]
Description=Hestia WhatsApp Gateway
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/hestia/Hestia_Production_whatsapp_service
ExecStart=/opt/hestia/venv/bin/gunicorn -c gunicorn.conf.py wsgi:app
Restart=always

[Install]
WantedBy=multi-user.target
```

2. **Notification worker** (`/etc/systemd/system/hestia-notifications.service`):
```ini
[Unit]
Description=Hestia Notification Worker
After=network.target postgresql.service

[Service]
Type=simple
WorkingDirectory=/opt/hestia/Hestia_Production_whatsapp_service
ExecStart=/opt/hestia/venv/bin/python run_notification_worker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Activar:
```bash
sudo systemctl enable hestia-gateway hestia-notifications
sudo systemctl start hestia-gateway hestia-notifications
```

### Con Docker Compose

```yaml
version: '3.8'
services:
  gateway:
    build: .
    command: gunicorn -c gunicorn.conf.py wsgi:app
    ports:
      - "5000:5000"
    env_file:
      - .env
    restart: always

  notification-worker:
    build: .
    command: python run_notification_worker.py
    env_file:
      - .env
    restart: always
    depends_on:
      - gateway
```

---

## 📊 Monitoreo

### Ver logs del worker

```bash
# Systemd
sudo journalctl -u hestia-notifications -f

# Docker
docker logs -f hestia-notification-worker
```

### Verificar estado

```bash
# Systemd
sudo systemctl status hestia-notifications

# Docker
docker ps | grep notification
```

---

## 🔒 Seguridad

- ✅ Todas las credenciales en variables de entorno
- ✅ `.env` en `.gitignore`
- ✅ Conexiones HTTPS a WhatsApp API
- ✅ PostgreSQL con SSL
- ✅ No SQL injection (prepared statements)

---

## 🤝 Contribuir

1. Crea una rama: `git checkout -b feature/nueva-feature`
2. Commit: `git commit -m "feat: agregar nueva feature"`
3. Push: `git push origin feature/nueva-feature`
4. Abre un Pull Request

---

## 📝 Changelog

### v2.0.0 (2026-01-08)
- 🆕 Integrado Notification Service
- 🆕 Worker de notificaciones automáticas
- 🆕 Encuestas CSAT para tickets resueltos
- 🆕 Encuestas para FAQs
- 🆕 Notificaciones de asignación de tickets

### v1.0.0 (2025-12-31)
- ✅ WhatsApp Gateway inicial
- ✅ Sistema de tickets
- ✅ FAQs automáticas
- ✅ Pipeline de conversación

---

## 📄 Licencia

Propiedad de Hestia Team - 2026

---

## 🆘 Soporte

Para reportar bugs o solicitar features, contacta al equipo de desarrollo.

**Desarrollado con ❤️ por el equipo de Hestia**
