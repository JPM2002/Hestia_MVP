# Migraciones de Base de Datos - Hestia

## 📁 Estructura

Este directorio contiene las migraciones SQL para la base de datos de Hestia.

```
migrations/
├── README.md                           # Este archivo
├── 002_create_conversation_logs.sql    # Tablas para conversaciones y encuestas FAQ
└── 003_create_csat_surveys.sql         # Tabla para encuestas CSAT de tickets
```

## 🚀 Cómo ejecutar las migraciones

### Opción 1: Script automatizado (Recomendado)

```bash
# Desde el directorio raíz de Hestia_Production/
python run_migrations.py
```

Este script:
- ✅ Detecta automáticamente si usas SQLite (dev) o PostgreSQL (producción)
- ✅ Ejecuta todas las migraciones en orden
- ✅ Maneja errores y muestra un resumen
- ✅ Es idempotente (usa `CREATE TABLE IF NOT EXISTS`)

### Opción 2: Manual (PostgreSQL)

Si prefieres ejecutar manualmente en PostgreSQL:

```bash
# Conectarse a la base de datos
psql -h aws-1-us-east-1.pooler.supabase.com -p 6543 -U postgres -d postgres

# Ejecutar cada migración
\i migrations/002_create_conversation_logs.sql
\i migrations/003_create_csat_surveys.sql
```

### Opción 3: Manual (SQLite)

Para desarrollo local con SQLite:

```bash
# Conectarse a la base de datos
sqlite3 hestia_V2.db

# Ejecutar cada migración
.read migrations/002_create_conversation_logs.sql
.read migrations/003_create_csat_surveys.sql
```

## 📋 Migraciones disponibles

### 002_create_conversation_logs.sql
**Propósito**: Almacenar conversaciones FAQ y programar encuestas

**Tablas creadas**:
- `conversation_logs`: Metadata de sesiones conversacionales
- `conversation_messages`: Mensajes individuales de cada conversación

**Características**:
- Trackeo de conversaciones FAQ
- Programación de encuestas con APScheduler
- Cooldown para evitar spam
- Métricas de calidad de respuestas FAQ

### 003_create_csat_surveys.sql
**Propósito**: Almacenar encuestas CSAT de tickets resueltos

**Tablas creadas**:
- `csat_surveys`: Encuestas de satisfacción de tickets

**Características**:
- Encuestas de 3 preguntas (CSAT score, comentario, utilidad WhatsApp)
- Estados de encuesta (pending, q1_sent, q2_sent, q3_sent, completed, expired)
- Prevención de duplicados (un ticket = una encuesta)
- Reportes de satisfacción por org/hotel
- Expiración de encuestas no completadas

## ✅ Verificar que las migraciones se ejecutaron

### PostgreSQL:
```sql
-- Listar todas las tablas
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

-- Verificar estructura de csat_surveys
\d csat_surveys
```

### SQLite:
```sql
-- Listar todas las tablas
.tables

-- Verificar estructura de csat_surveys
.schema csat_surveys
```

## ⚠️ Notas importantes

1. **Idempotencia**: Todas las migraciones usan `CREATE TABLE IF NOT EXISTS`, por lo que son seguras de ejecutar múltiples veces.

2. **Orden**: Los archivos están numerados (002_, 003_) para garantizar que se ejecuten en el orden correcto.

3. **No modificar migraciones existentes**: Una vez ejecutada una migración en producción, NO la modifiques. Crea una nueva migración para cambios adicionales.

4. **Backup**: Siempre haz un backup de la base de datos antes de ejecutar migraciones en producción.

## 🐛 Troubleshooting

### Error: "no such table: csat_surveys"
**Solución**: Ejecuta la migración `003_create_csat_surveys.sql`
```bash
python run_migrations.py
```

### Error: "table csat_surveys already exists"
**Causa**: La migración ya fue ejecutada (esto es normal)
**Solución**: No hacer nada, la tabla ya existe

### Error: "psycopg2 not installed"
**Solución**: Instala las dependencias de PostgreSQL
```bash
pip install psycopg2-binary
```

## 📚 Crear una nueva migración

1. Crea un nuevo archivo con el siguiente número en secuencia:
   ```
   004_descripcion_de_la_migracion.sql
   ```

2. Usa `CREATE TABLE IF NOT EXISTS` para idempotencia

3. Agrega comentarios descriptivos al inicio del archivo

4. Actualiza este README con la descripción de la nueva migración

5. Ejecuta `python run_migrations.py` para verificar que funciona
