"""
NEW_SCRIPT_TEMPLATE.PY - Plantilla para Nuevos Scripts
=======================================================

Copia este archivo y adapta para tus análisis.

✅ CHECKLIST INTEGRADO:
  1. Importar operable_mask ← Haz esto automáticamente
  2. Aplicar operability.py ← No re-implementar filtros
  3. Imprimir breakdown ← Siempre mostrar conteos
  4. Ejecutar validador ← Antes de usar resultados
  5. Reportar Global + Operable ← Nunca solo uno

Uso:
    cp new_script_template.py mi_analisis.py
    # Edita: nombre script, lógica específica
    # Mantén: imports, breakdown, validación
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys

# ============================================================================
# CHECKLIST ITEM 1: IMPORTAR DE operability.py (SINGLE SOURCE OF TRUTH)
# ============================================================================

from operability import (
    operable_mask,
    get_operability_breakdown,
    get_risk_distribution,
    CONF_THRESHOLD,
    WHITELIST_TICKERS,
    ALLOWED_RISKS,
    EXPECTED_OPERABLE_COUNT
)
from operability_config import output


# ============================================================================
# CONFIGURACIÓN ESPECÍFICA DEL SCRIPT
# ============================================================================

SCRIPT_NAME = "mi_analisis"  # Cambiar a tu nombre
CSV_PATH = Path("outputs/analysis/all_signals_with_confidence.csv")
OUTPUTS_DIR = Path("outputs/analysis")
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================================
# FUNCIONES HELPER
# ============================================================================

def load_and_prepare_data() -> pd.DataFrame:
    """Cargar y preparar datos."""
    if not CSV_PATH.exists():
        print(f"❌ No existe: {CSV_PATH}")
        sys.exit(1)
    
    df = pd.read_csv(CSV_PATH)
    df["date"] = pd.to_datetime(df["date"])
    
    # CALCULARTE RIESGO MACRO (adaptado de production_orchestrator.py)
    from datetime import datetime
    FOMC_DATES = pd.to_datetime([
        "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
        "2025-07-30", "2025-09-17", "2025-11-05", "2025-12-17"
    ])
    
    def calculate_macro_risk_level(date):
        fomc_proximity = ((FOMC_DATES - date).days).min()
        return "HIGH" if abs(fomc_proximity) <= 2 else "MEDIUM"
    
    df["macro_risk"] = df["date"].apply(calculate_macro_risk_level)
    
    return df


def validate_operables_count(operable_count: int, expected: int = EXPECTED_OPERABLE_COUNT) -> bool:
    """
    CHECKLIST ITEM 4: Validar conteo.
    
    Returns:
        True si OK, False si hay mismatch
    """
    if expected is None:
        return True
    
    delta = operable_count - expected
    delta_pct = abs(delta) / expected * 100 if expected > 0 else 0
    
    print(f"\n📋 VALIDACIÓN DE OPERABLES:")
    print(f"   Esperado: {expected:,}")
    print(f"   Obtenido: {operable_count:,}")
    print(f"   Delta: {delta:+d} ({delta_pct:.2f}%)")
    
    if delta == 0:
        print(f"   ✅ CONSISTENCIA TOTAL")
        return True
    elif abs(delta) <= 1:
        print(f"   ⚠️  Delta mínimo (probablemente NaN/parse)")
        return True
    elif delta_pct <= output.ABORT_THRESHOLD_PCT:
        print(f"   ⚠️  Dentro de umbral ({output.ABORT_THRESHOLD_PCT}%)")
        return True
    else:
        print(f"   ❌ MISMATCH SIGNIFICATIVO - Revisar filtros")
        if output.ABORT_ON_MISMATCH:
            print(f"   🛑 ABORT_ON_MISMATCH=True - Abortando")
            sys.exit(1)
        return False


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Función principal."""
    
    print("\n" + "="*70)
    print(f"SCRIPT: {SCRIPT_NAME}")
    print("="*70)
    
    # 1. Cargar datos
    print("\n📖 Cargando datos...")
    df = load_and_prepare_data()
    print(f"✓ {len(df):,} observaciones")
    
    # 2. CHECKLIST ITEM 2: Aplicar operability.py
    print("\n🔍 Aplicando operability.operable_mask()...")
    mask = operable_mask(df)
    operable = df[mask].copy()
    
    # 3. CHECKLIST ITEM 3: Imprimir breakdown
    print("\n📊 BREAKDOWN AUTOMÁTICO:")
    breakdown = get_operability_breakdown(df)
    print(f"   Global: {breakdown['global']:,}")
    print(f"   Conf>=4: {breakdown['conf_only']:,} ({breakdown['percentages']['conf_only']:.1f}%)")
    print(f"   +Risk: {breakdown['conf_risk']:,} ({breakdown['percentages']['conf_risk']:.1f}%)")
    print(f"   +Whitelist: {breakdown['operable']:,} ({breakdown['percentages']['operable']:.1f}%)")
    
    # 4. Distribución de riesgos
    print("\n🚨 DISTRIBUCIÓN DE RIESGOS MACRO:")
    risk_dist = get_risk_distribution(df)
    for risk, info in sorted(risk_dist.items()):
        print(f"   {risk}: {info['count']:5,} ({info['percentage']:5.1f}%)")
    
    # 5. CHECKLIST ITEM 4: Validar conteo
    validate_operables_count(len(operable))
    
    # 6. HACER ANÁLISIS AQUÍ
    print(f"\n{'='*70}")
    print("📈 TU ANÁLISIS ESPECÍFICO (reemplaza esta sección)")
    print(f"{'='*70}")
    
    # Ejemplo: comparar Global vs Operable
    print("\n📊 GLOBAL vs OPERABLE SLICE:")
    print(f"   Global accuracy: {(df['direction_correct'].mean()*100):.2f}%")
    print(f"   Operable accuracy: {(operable['direction_correct'].mean()*100):.2f}%")
    
    # 7. EXPORTAR
    print(f"\n{'='*70}")
    print("💾 EXPORTANDO RESULTADOS")
    print(f"{'='*70}")
    
    operable.to_csv(OUTPUTS_DIR / f"{SCRIPT_NAME}_operables.csv", index=False)
    print(f"✓ Exportado: {SCRIPT_NAME}_operables.csv")
    
    print(f"\n{'='*70}")
    print("✅ SCRIPT COMPLETADO")
    print(f"{'='*70}\n")
    
    # 8. RECORDATORIO DE VALIDACIÓN EXTERNA
    print("🔍 PRÓXIMO PASO: Validación externa")
    print(f"   python diff_operables.py --test={SCRIPT_NAME}_operables.csv")
    print()


if __name__ == "__main__":
    main()
