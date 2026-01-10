# Hestia Dashboard (React + TypeScript)

Frontend del dashboard operativo de Hestia (MVP). Proyecto creado con Vite + React + TypeScript.

## Requisitos

- Node.js 18+ (ideal 20)
- npm

## Correr local

```bash
npm install
npm run dev
```

Abrir: http://localhost:5173

## Scripts

```bash
npm run lint          # ESLint (0 warnings allowed)
npm run format        # Prettier (reescribe formato)
npm run format:check  # Prettier (solo valida)
npm run build         # Build de producción (dist/)
npm run preview       # Preview del build
```

## Estructura

- `src/` código React
- `eslint.config.js` configuración ESLint (flat config)
- `.prettierrc` / `.prettierignore` configuración Prettier

## Notas

- Se ajustó `src/index.css` para remover estilos por defecto del template de Vite que limitaban el ancho del layout.
