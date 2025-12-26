# Expected System Responses - Routing Test Cases

Este documento muestra las respuestas exactas que el bot debe dar para cada caso de prueba según el Mega Issue.

---

## ✅ CASO 1: Rules Hit - HOUSEKEEPING

**Usuario:** `Necesito toallas limpias`

**Sistema debe responder:**

```
Para poder ayudarte mejor, necesito confirmar algunos datos:

📝 ¿Cuál es tu nombre completo?
🏨 ¿En qué número de habitación te encuentras?
```

**Después de que el usuario proporcione identidad (ej: "Juan Pérez, habitación 205"):**

```
Perfecto, Juan Pérez. Voy a notificar al equipo de Housekeeping sobre:

📝 Necesito toallas limpias
🏨 Habitación 205

¿Confirmas? (Sí/No)
```

**Después de "Sí":**

```
¡Listo! Ya notifiqué al equipo de Housekeeping sobre tu solicitud en la habitación 205. Te avisaré cuando esté resuelto. ✅
```

**✅ Verificación en DB:**

- `area` = `HOUSEKEEPING`
- `routing_source` = `rules`
- `routing_confidence` >= `0.85`
- `routing_reason` = `Keyword-based: X matches`

---

## ✅ CASO 2: Rules Hit - MANTENCION

**Usuario:** `No funciona el aire acondicionado`

**Sistema debe responder:**

```
Para poder ayudarte mejor, necesito confirmar algunos datos:

📝 ¿Cuál es tu nombre completo?
🏨 ¿En qué número de habitación te encuentras?
```

**Después de identidad:**

```
Perfecto, [nombre]. Voy a notificar al equipo de Mantenimiento sobre:

📝 No funciona el aire acondicionado
🏨 Habitación [XXX]

¿Confirmas? (Sí/No)
```

**✅ Verificación en DB:**

- `area` = `MANTENCION`
- `routing_source` = `rules`
- `routing_confidence` >= `0.85`

---

## ✅ CASO 3: Rules Hit - RECEPCION

**Usuario:** `Quiero hacer late checkout`

**Sistema debe responder:**

```
Para poder ayudarte mejor, necesito confirmar algunos datos:

📝 ¿Cuál es tu nombre completo?
🏨 ¿En qué número de habitación te encuentras?
```

**Después de identidad:**

```
Perfecto, [nombre]. Voy a notificar al equipo de Recepción sobre:

📝 Quiero hacer late checkout
🏨 Habitación [XXX]

¿Confirmas? (Sí/No)
```

**✅ Verificación en DB:**

- `area` = `RECEPCION`
- `routing_source` = `rules`

---

## ✅ CASO 4: Rules Hit - GERENCIA

**Usuario:** `Quiero presentar una queja formal, esto es inaceptable`

**Sistema debe responder:**

```
Para poder ayudarte mejor, necesito confirmar algunos datos:

📝 ¿Cuál es tu nombre completo?
🏨 ¿En qué número de habitación te encuentras?
```

**Después de identidad:**

```
Perfecto, [nombre]. Voy a notificar al equipo de Gerencia sobre:

📝 Quiero presentar una queja formal, esto es inaceptable
🏨 Habitación [XXX]

¿Confirmas? (Sí/No)
```

**✅ Verificación en DB:**

- `area` = `GERENCIA`
- `routing_source` = `rules`

---

## ✅ CASO 5: LLM High Confidence

**Usuario:** `Pueden traerme almohadas extra por favor`

**Sistema debe responder:**

```
Para poder ayudarte mejor, necesito confirmar algunos datos:

📝 ¿Cuál es tu nombre completo?
🏨 ¿En qué número de habitación te encuentras?
```

**Después de identidad:**

```
Perfecto, [nombre]. Voy a notificar al equipo de Housekeeping sobre:

📝 Pueden traerme almohadas extra por favor
🏨 Habitación [XXX]

¿Confirmas? (Sí/No)
```

**✅ Verificación en DB:**

- `area` = `HOUSEKEEPING`
- `routing_source` = `llm`
- `routing_confidence` >= `0.75`
- `routing_reason` = `LLM classification`

**⚠️ Nota:** Rules NO detecta "almohadas" (gap en keywords), por lo que LLM debe clasificarlo.

---

## 🔍 CASO 6: LLM Low Confidence → Clarification

**Usuario:** `Tengo un problema en mi habitación`

**Sistema debe responder (SIN pedir identidad primero):**

```
Entiendo que necesitas ayuda con: *Tengo un problema en mi habitación*

Para asignarlo correctamente, ¿es sobre:

1️⃣ *Mantenimiento* (técnico/AC/agua/luz)
2️⃣ *Housekeeping* (limpieza/toallas/amenities)
3️⃣ *Recepción* (pagos/reservas/info)
4️⃣ *Otro* (queja/gerencia)

Responde con el número (1-4).
```

**⚠️ CRÍTICO:** El sistema detecta confidence < 0.65 y DEBE preguntar al usuario ANTES de pedir identidad.

**✅ Verificación de logs:**

```
[ROUTING] ⚠️ Low confidence (0.XX) or missing area → Request clarification
[ROUTING] 📋 Requesting area clarification from user
```

**Estado de sesión:**

- `session["state"]` = `GH_AREA_CLARIFICATION`
- `session["pending_detail"]` = `Tengo un problema en mi habitación`

---

## 🔍 CASO 7: Clarification → User Choice

**Conversación completa:**

**Usuario (msg 1):** `Necesito ayuda urgente`

**Sistema:**

```
Entiendo que necesitas ayuda con: *Necesito ayuda urgente*

Para asignarlo correctamente, ¿es sobre:

1️⃣ *Mantenimiento* (técnico/AC/agua/luz)
2️⃣ *Housekeeping* (limpieza/toallas/amenities)
3️⃣ *Recepción* (pagos/reservas/info)
4️⃣ *Otro* (queja/gerencia)

Responde con el número (1-4).
```

**Usuario (msg 2):** `2`

**Sistema:**

```
Para poder ayudarte mejor, necesito confirmar algunos datos:

📝 ¿Cuál es tu nombre completo?
🏨 ¿En qué número de habitación te encuentras?
```

**Usuario:** `María González, habitación 312`

**Sistema:**

```
Perfecto, María González. Voy a notificar al equipo de Housekeeping sobre:

📝 Necesito ayuda urgente
🏨 Habitación 312

¿Confirmas? (Sí/No)
```

**Usuario:** `Sí`

**Sistema:**

```
¡Listo! Ya notifiqué al equipo de Housekeeping sobre tu solicitud en la habitación 312. Te avisaré cuando esté resuelto. ✅
```

**✅ Verificación en DB:**

- `area` = `HOUSEKEEPING`
- `routing_source` = `clarification` ⭐ (NO "llm", sino "clarification")
- `routing_confidence` = `1.0` ⭐ (100% porque usuario confirmó)
- `routing_reason` = `User chose option 2: HOUSEKEEPING`

---

## 🔍 CASO 8: Multi-Department → Clarification

**Usuario:** `Necesito toallas y el aire no funciona`

**Sistema debe responder:**

```
Entiendo que necesitas ayuda con: *Necesito toallas y el aire no funciona*

Para asignarlo correctamente, ¿es sobre:

1️⃣ *Mantenimiento* (técnico/AC/agua/luz)
2️⃣ *Housekeeping* (limpieza/toallas/amenities)
3️⃣ *Recepción* (pagos/reservas/info)
4️⃣ *Otro* (queja/gerencia)

Responde con el número (1-4).
```

**⚠️ Razón:** Mensaje tiene keywords de 2 áreas. LLM clasifica como SUPERVISION con confidence ~0.50 (< 0.65).

**✅ Verificación de logs:**

```
[NLU] ⚠️ Rules missed → LLM fallback
[NLU] ✅ LLM result: intent=ticket_request, area=SUPERVISION, conf=0.50
[ROUTING] ⚠️ Low confidence (0.50) or missing area → Request clarification
```

---

## ℹ️ CASO 9: FAQ (No Ticket)

**Usuario:** `¿A qué hora es el desayuno?`

**Sistema debe responder (FAQ fallback):**

```
[Respuesta del FAQ module sobre horarios de desayuno]
```

**⚠️ CRÍTICO:** NO se debe crear ticket. El intent es `not_understood` y el orchestrator lo pasa al FAQ handler.

**✅ Verificación:**

- NO debe aparecer ticket en DB
- Logs deben mostrar: `[FLOW] ✅ DECISION: Intent=NOT_UNDERSTOOD → FAQ fallback`

---

## ✅ CASO 10: Edge Case - Mixed Greeting + Ticket

**Usuario:** `Hola, no tengo agua caliente en mi habitación 305`

**Sistema debe responder:**

```
Para poder ayudarte mejor, necesito confirmar algunos datos:

📝 ¿Cuál es tu nombre completo?
🏨 ¿En qué número de habitación te encuentras?
```

**⚠️ Nota:** El sistema ya extrajo `room=305` del mensaje, pero SIEMPRE pregunta para confirmar.

**Usuario:** `Pedro Martínez`

**Sistema:**

```
Perfecto, Pedro Martínez. Voy a notificar al equipo de Mantenimiento sobre:

📝 no tengo agua caliente en mi habitación 305
🏨 Habitación 305

¿Confirmas? (Sí/No)
```

**✅ Verificación en DB:**

- `area` = `MANTENCION`
- `routing_source` = `rules` (keywords: "agua caliente" + "no tengo")
- `huesped_nombre` = `Pedro Martínez`
- `ubicacion` = `305`

---

## 📊 Resumen de Comportamientos Esperados

| Caso | Mensaje                    | Routing Layer | Área         | Clarificación | Confidence | Source              |
| ---- | -------------------------- | ------------- | ------------ | ------------- | ---------- | ------------------- |
| 1    | "Necesito toallas limpias" | Rules         | HOUSEKEEPING | ❌ No         | ≥0.85      | rules               |
| 2    | "No funciona el aire"      | Rules         | MANTENCION   | ❌ No         | ≥0.85      | rules               |
| 3    | "Late checkout"            | Rules         | RECEPCION    | ❌ No         | ≥0.85      | rules               |
| 4    | "Queja formal"             | Rules         | GERENCIA     | ❌ No         | ≥0.85      | rules               |
| 5    | "Almohadas extra"          | LLM           | HOUSEKEEPING | ❌ No         | ≥0.75      | llm                 |
| 6    | "Problema en habitación"   | LLM           | SUPERVISION  | ✅ Sí         | <0.65      | llm → clarification |
| 7    | "Ayuda urgente" → "2"      | Clarification | HOUSEKEEPING | ✅ Sí         | 1.0        | clarification       |
| 8    | "Toallas y aire roto"      | LLM           | SUPERVISION  | ✅ Sí         | ~0.50      | llm → clarification |
| 9    | "¿Hora desayuno?"          | LLM           | N/A          | ❌ No         | 0.0        | FAQ (no ticket)     |
| 10   | "Hola, no hay agua 305"    | Rules         | MANTENCION   | ❌ No         | ≥0.85      | rules               |

---

## 🔬 Criterios de Éxito (Success Criteria)

### 1. Rules Efficiency (Casos 1-4, 10)

- ✅ Deben resolverse sin llamar al LLM
- ✅ Logs deben mostrar: `[NLU] ✅ RULES HIT → [AREA] - LLM SKIPPED`
- ✅ Latencia < 100ms (sin espera de API)

### 2. Confidence Threshold (Casos 6, 7, 8)

- ✅ Mensajes ambiguos deben activar clarificación
- ✅ Threshold = 0.65 debe funcionar correctamente
- ✅ Usuario SIEMPRE recibe menú 1-4 cuando confidence < 0.65

### 3. Metadata Persistence (Todos los casos)

- ✅ 100% de tickets deben tener los 4 campos de metadata en DB:
  - `routing_source` (rules/llm/clarification/fallback)
  - `routing_reason` (descripción textual)
  - `routing_confidence` (float 0.0-1.0)
  - `routing_version` (v1)

### 4. Area Correctness (Todos los casos)

- ✅ 100% de tickets deben rutear al área correcta
- ✅ NO debe haber tickets de toallas en RECEPCION
- ✅ NO debe haber tickets de AC en HOUSEKEEPING

### 5. Clarification Flow (Casos 6, 7, 8)

- ✅ Cuando usuario elige opción 1-4, `routing_source` = `clarification`
- ✅ Cuando usuario elige opción 1-4, `routing_confidence` = `1.0`
- ✅ Sistema acepta tanto número ("2") como keyword ("housekeeping")

---

## 🧪 Instrucciones de Testing

### Paso 1: Preparación

1. Asegúrate de que la BD tenga las 4 columnas de metadata
2. Limpia tickets de prueba anteriores
3. Activa logging en modo DEBUG

### Paso 2: Ejecución

1. Envía cada mensaje por WhatsApp (en orden)
2. Captura las respuestas del bot
3. Verifica que coincidan con las respuestas esperadas arriba

### Paso 3: Validación DB

```sql
SELECT
    id,
    area,
    detalle,
    routing_source,
    routing_reason,
    routing_confidence,
    routing_version
FROM tickets
ORDER BY created_at DESC
LIMIT 10;
```

### Paso 4: Validación Logs

Busca estos patrones en los logs:

```
✅ "[NLU] ✅ RULES HIT" → Casos 1-4, 10
✅ "[NLU] ⚠️ Rules missed → LLM fallback" → Casos 5-9
✅ "[ROUTING] ⚠️ Low confidence" → Casos 6, 7, 8
✅ "[ROUTING] 📋 Requesting area clarification" → Casos 6, 7, 8
✅ "[ROUTING] ✅ User clarified → [AREA]" → Caso 7
```

---

## ⚠️ Common Issues y Troubleshooting

### Issue 1: Rules no detecta keywords

**Síntoma:** Caso 1 cae al LLM en lugar de Rules
**Causa:** Typo en HOUSEKEEPING_PATTERNS o normalización Unicode fallida
**Fix:** Verificar que `routing_rules.py` tenga los patterns correctos

### Issue 2: Clarification nunca se activa

**Síntoma:** Caso 6 va directo a confirmación sin preguntar 1-4
**Causa:** Threshold está muy bajo o LLM retorna confidence muy alta
**Fix:** Verificar que `CONFIDENCE_THRESHOLD = 0.65` en `identity_handler.py:265`

### Issue 3: Metadata no se guarda en DB

**Síntoma:** Columnas routing\_\* están NULL o vacías
**Causa:** SQL INSERT no incluye las columnas o params no coinciden
**Fix:** Verificar `tickets.py:57-60` (columnas) y `tickets.py:86-90` (valores)

### Issue 4: Usuario elige "2" pero queda en SUPERVISION

**Síntoma:** Caso 7 no actualiza área después de elegir opción
**Causa:** `handle_area_clarification_response()` no se ejecuta o tiene bug
**Fix:** Verificar que orchestrator.py:163-175 capture el estado GH_AREA_CLARIFICATION

---

## 📈 Métricas de Éxito

Después de ejecutar los 10 casos:

| Métrica               | Target | Cómo medir                                            |
| --------------------- | ------ | ----------------------------------------------------- |
| Rules Hit Rate        | ≥50%   | Casos 1-4, 10 = 5/10 = 50%                            |
| LLM Calls Saved       | ≥5     | Count de logs "LLM SKIPPED"                           |
| Clarification Rate    | 30%    | Casos 6, 7, 8 = 3/10 = 30%                            |
| Metadata Completeness | 100%   | 9 tickets (todos excepto caso 9) deben tener metadata |
| Area Correctness      | 100%   | 9/9 tickets deben estar en área correcta              |

---

**Versión:** v1
**Fecha:** 2025-12-25
**Autor:** Claude Code
**Propósito:** Validación del Mega Issue - Routing Guardrails
