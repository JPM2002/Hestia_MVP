#!/usr/bin/env python3
"""
Script para ejecutar migraciones SQL en la base de datos.

Uso:
    python run_migrations.py

Este script:
1. Lee todos los archivos .sql en el directorio migrations/
2. Los ejecuta en orden alfabético (001_, 002_, 003_, etc.)
3. Maneja tanto SQLite (dev) como PostgreSQL (producción)
"""

import os
import sys
from pathlib import Path

# Importar servicios de BD
sys.path.insert(0, str(Path(__file__).parent))
from hestia_app.services.db import execute, using_pg


def run_migrations():
    """Ejecuta todas las migraciones SQL en orden."""
    migrations_dir = Path(__file__).parent / "migrations"

    if not migrations_dir.exists():
        print(f"❌ Error: No existe el directorio {migrations_dir}")
        return False

    # Obtener todos los archivos .sql y ordenarlos
    sql_files = sorted(migrations_dir.glob("*.sql"))

    if not sql_files:
        print("⚠️ No se encontraron archivos de migración (.sql)")
        return True

    db_type = "PostgreSQL" if using_pg() else "SQLite"
    print(f"\n🔧 Ejecutando migraciones en {db_type}...")
    print(f"📁 Directorio: {migrations_dir}\n")

    success_count = 0
    error_count = 0

    for sql_file in sql_files:
        migration_name = sql_file.name
        print(f"⏳ Ejecutando: {migration_name}...", end=" ")

        try:
            # Leer contenido del archivo SQL
            sql_content = sql_file.read_text(encoding='utf-8')

            # Si es PostgreSQL, convertir AUTOINCREMENT a SERIAL
            if using_pg():
                # PostgreSQL no soporta AUTOINCREMENT, usar SERIAL
                sql_content = sql_content.replace(
                    'INTEGER PRIMARY KEY AUTOINCREMENT',
                    'SERIAL PRIMARY KEY'
                )

            # Dividir en statements individuales (separados por ;)
            statements = [s.strip() for s in sql_content.split(';') if s.strip() and not s.strip().startswith('--')]

            # Ejecutar cada statement
            for statement in statements:
                if statement:
                    execute(statement, commit=True)

            print("✅ OK")
            success_count += 1

        except Exception as e:
            print(f"❌ ERROR")
            print(f"   Detalle: {str(e)}")
            error_count += 1

    print(f"\n📊 Resumen:")
    print(f"   ✅ Exitosas: {success_count}")
    print(f"   ❌ Errores: {error_count}")
    print(f"   📝 Total: {len(sql_files)}")

    return error_count == 0


if __name__ == "__main__":
    print("=" * 60)
    print("🚀 HESTIA - Ejecutor de Migraciones SQL")
    print("=" * 60)

    try:
        success = run_migrations()

        if success:
            print("\n✅ Todas las migraciones se ejecutaron correctamente!")
            sys.exit(0)
        else:
            print("\n⚠️ Algunas migraciones fallaron. Revisa los errores arriba.")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
