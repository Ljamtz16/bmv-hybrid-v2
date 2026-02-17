"""
OPERABILITY_CONFIG.PY - Configuración Centralizada
===================================================

Todos los parámetros del sistema en un único lugar.
Cambiar aquí = cambiar globalmente.

Secciones:
  - Data Sources (CSV Authority)
  - Kill Switch
  - Model Health
  - Risk Macro
  - Output
  - Delta Tolerance
"""

from typing import Literal
from pathlib import Path

# ============================================================================
# DATA SOURCES - CSV AUTHORITY
# ============================================================================

class DataSourceConfig:
    """
    Fuente única de verdad para datos.
    
    Define QUÉ CSV es el authoritative dataset y dónde está.
    """
    
    # CSV Authority: dataset maestro para validaciones
    CSV_AUTHORITY: Path = Path("outputs/analysis/all_signals_with_confidence.csv")
    
    # Logging
    LOG_FILE_METADATA: bool = True  # Loguear path, hash, size al cargar
    VALIDATE_FILE_EXISTS: bool = True  # Fallar si no existe
    
    def __repr__(self):
        return (
            f"DataSourceConfig(\n"
            f"  authority={self.CSV_AUTHORITY},\n"
            f"  log_metadata={self.LOG_FILE_METADATA})\n"
        )


# ============================================================================
# KILL SWITCH - CONFIGURACIÓN
# ============================================================================

class KillSwitchConfig:
    """Parámetros del kill switch (automático al detectar degradación)."""
    
    # Ventana de evaluación
    WINDOW_DAYS: int = 5  # Últimos N días operativos
    
    # Bandas de accuracy (no binario: PAUSE/WARN/TRADE)
    ACCURACY_CRITICAL: float = 0.45  # < 45% = PAUSE automático
    ACCURACY_WARNING: float = 0.50  # < 50% = WARNING (no pausa)
    ACCURACY_OPTIMAL: float = 0.55  # >= 55% = TRADE (verde)
    
    # Acción al dispararse
    PAUSE_DAYS: int = 5  # Pausar por N días
    
    # Logging
    LOG_ONLY_ON_CHANGE: bool = True  # Solo escribir si cambia de estado
    
    # Auditoría
    SAVE_DAILY_ACC_WINDOW: bool = True  # Guardar últimos N días
    SAVE_OPERABLE_FILTER_SUMMARY: bool = True  # Guardar breakdown
    
    def __repr__(self):
        return (
            f"KillSwitchConfig(\n"
            f"  window={self.WINDOW_DAYS}d,\n"
            f"  critical={int(self.ACCURACY_CRITICAL*100)}% (PAUSE),\n"
            f"  warning={int(self.ACCURACY_WARNING*100)}% (WARN),\n"
            f"  optimal={int(self.ACCURACY_OPTIMAL*100)}% (TRADE),\n"
            f"  pause_days={self.PAUSE_DAYS})\n"
        )


# ============================================================================
# MODEL HEALTH - CONFIGURACIÓN (separado del Kill Switch)
# ============================================================================

class ModelHealthConfig:
    """
    Indicador de salud del modelo (NO bloqueante).
    
    Emite warnings pero NO pausa el sistema.
    Sirve para detectar degradación antes de que dispare kill switch.
    """
    
    # Umbrales de warning (por debajo = aviso)
    GLOBAL_ACCURACY_WARNING: float = 0.45  # Global < 45% = ⚠️
    OPERABLE_ACCURACY_WARNING: float = 0.50  # Operable < 50% = ⚠️
    
    # Ventana de evaluación
    WINDOW_DAYS: int = 10  # Últimos N días (más que kill switch para tendencia)
    
    # Logging
    LOG_DAILY: bool = True  # Reportar cada día
    
    def __repr__(self):
        return (
            f"ModelHealthConfig(\n"
            f"  global_warning={int(self.GLOBAL_ACCURACY_WARNING*100)}%,\n"
            f"  operable_warning={int(self.OPERABLE_ACCURACY_WARNING*100)}%,\n"
            f"  window={self.WINDOW_DAYS}d)\n"
        )


# ============================================================================
# RISK MACRO - CONFIGURACIÓN
# ============================================================================

class RiskMacroConfig:
    """Cálculo y clasificación de riesgo macro.
    
    IMPORTANTE: macro_risk debe venir del pipeline o calcularse explícitamente.
    NO usar FALLBACK_RISK como solución permanente. Si falta macro_risk → WARNING.
    """
    
    # Eventos que aumentan riesgo
    FOMC_PROXIMITY_DAYS: int = 2  # FOMC ±N días = HIGH risk
    EARNINGS_PROXIMITY_DAYS: int = 1  # Earnings ±N días = MEDIUM
    ELECTION_PROXIMITY_DAYS: int = 3  # Elecciones ±N días = HIGH
    VIX_THRESHOLD: float = 20.0  # VIX > 20 = MEDIUM (si se usa)
    GAP_THRESHOLD_PCT: float = 2.0  # Gap > 2% = MEDIUM
    
    # Fallback SOLO si falta macro_risk en datos
    FALLBACK_RISK: str = "MEDIUM"  # Fallback con warning, NO default
    WARN_ON_FALLBACK: bool = True  # Siempre alertar si se usa fallback
    
    # Nota: LOW solo si explícitamente en datos, no por fallback
    
    def __repr__(self):
        return (
            f"RiskMacroConfig(\n"
            f"  fomc_proximity={self.FOMC_PROXIMITY_DAYS}d,\n"
            f"  earnings_proximity={self.EARNINGS_PROXIMITY_DAYS}d,\n"
            f"  fallback_risk={self.FALLBACK_RISK})\n"
        )


# ============================================================================
# OUTPUT - CONFIGURACIÓN
# ============================================================================

class OutputConfig:
    """Cómo se exportan los resultados."""
    
    # Reportes diarios
    DAILY_RISK_REPORT: bool = True  # %LOW/%MEDIUM/%HIGH/%CRITICAL
    DAILY_OPERABILITY_REPORT: bool = True  # Breakdown de filtros
    DAILY_AUDIT: bool = True  # run_audit.json
    
    # Validación
    VALIDATE_OPERABLES_COUNT: bool = True  # Chequear count vs expected
    ABORT_ON_MISMATCH: bool = False  # ¿Abortar si count difiere? (True = estricto)
    ABORT_THRESHOLD_PCT: float = 0.5  # Delta % permitida (0.5% = ~19 filas en 3881)
    
    # Preprocesamiento unificado
    UNIFIED_PREPROCESSING: bool = True  # Usar load_data() centralizado
    WARN_ON_TYPE_MISMATCH: bool = True  # Alertar si tipos inconsistentes
    
    # Logging
    VERBOSE: bool = True  # Imprimir detalles
    SAVE_RUN_AUDIT: bool = True  # Guardar run_audit.json
    
    def __repr__(self):
        return (
            f"OutputConfig(\n"
            f"  validate_operables={self.VALIDATE_OPERABLES_COUNT},\n"
            f"  abort_on_mismatch={self.ABORT_ON_MISMATCH},\n"
            f"  abort_threshold={self.ABORT_THRESHOLD_PCT}%,\n"
            f"  unified_preprocessing={self.UNIFIED_PREPROCESSING})\n"
        )


# ============================================================================
# GATE/OVERLAY - CONFIGURACIÓN
# ============================================================================

class GateConfig:
    """
    Configuración de overlays y modo de ejecución.
    Política recomendada:
      - PROD: GAP_OVERLAY_ENABLED=False hasta que OHLCV_READY=True
      - DEV: overlay ON, soft-fail (nunca aborta)
    """
    MODE: str = "DEV"
    STRICT_MODE: bool = False

    GAP_OVERLAY_ENABLED: bool = True  # Solicitado; puede ser deshabilitado efectivamente si OHLCV_READY=False en PROD
    GAP_UNAVAILABLE_PCT_HARDFAIL: float = 5.0  # porcentaje (%)
    OHLCV_READY: bool = False  # Si False en PROD, se desactiva overlay automáticamente

    MIN_HIGH_DAYS_FOR_SEPARATION: int = 10

    def is_gap_overlay_active(self) -> bool:
        """Determina si el overlay gap se aplica efectivamente."""
        if not self.GAP_OVERLAY_ENABLED:
            return False
        if self.MODE.upper() == "PROD" and not self.OHLCV_READY:
            return False
        return True

    def snapshot(self) -> dict:
        return {
            "MODE": self.MODE,
            "STRICT_MODE": self.STRICT_MODE,
            "GAP_OVERLAY_ENABLED_REQUESTED": self.GAP_OVERLAY_ENABLED,
            "GAP_OVERLAY_ACTIVE": self.is_gap_overlay_active(),
            "OHLCV_READY": self.OHLCV_READY,
            "GAP_UNAVAILABLE_PCT_HARDFAIL": self.GAP_UNAVAILABLE_PCT_HARDFAIL,
            "MIN_HIGH_DAYS_FOR_SEPARATION": self.MIN_HIGH_DAYS_FOR_SEPARATION,
        }

    def __repr__(self):
        return (
            f"GateConfig(MODE={self.MODE}, STRICT={self.STRICT_MODE}, "
            f"GAP_ENABLED={self.GAP_OVERLAY_ENABLED}, GAP_ACTIVE={self.is_gap_overlay_active()}, "
            f"OHLCV_READY={self.OHLCV_READY}, GAP_HARDFAIL={self.GAP_UNAVAILABLE_PCT_HARDFAIL}%, "
            f"MIN_HIGH_DAYS={self.MIN_HIGH_DAYS_FOR_SEPARATION})"
        )


# ============================================================================
# INSTANCIAS GLOBALES (importar de aquí)
# ============================================================================

data_source = DataSourceConfig()
kill_switch = KillSwitchConfig()
model_health = ModelHealthConfig()
risk_macro = RiskMacroConfig()
output = OutputConfig()
gate_config = GateConfig()


# ============================================================================
# DELTA TOLERANCE & AUDIT
# ============================================================================

class DeltaToleranceConfig:
    """
    Configuración de tolerancia para deltas en conteos de operables.
    
    Si hay diferencia entre datasets, debe estar documentada.
    """
    
    # Umbral de tolerancia
    DELTA_TOLERANCE_PCT: float = 0.5  # Aceptar si < 0.5%
    DELTA_TOLERANCE_ABSOLUTE: int = 2  # O < 2 filas
    
    # Auditoría obligatoria
    AUDIT_ON_DELTA: bool = True  # Generar CSV si hay delta
    REQUIRE_RCA_ON_DELTA: bool = True  # RCA (Root Cause Analysis) obligatorio
    
    # Logging
    DELTA_LOG_PATH: str = "outputs/analysis/DELTA_AUDIT.json"
    
    def __repr__(self):
        return (
            f"DeltaToleranceConfig(\n"
            f"  tolerance={self.DELTA_TOLERANCE_PCT}% or {self.DELTA_TOLERANCE_ABSOLUTE} rows,\n"
            f"  audit_enabled={self.AUDIT_ON_DELTA},\n"
            f"  rca_required={self.REQUIRE_RCA_ON_DELTA})\n"
        )


# ============================================================================
# INSTANCIAS GLOBALES (Segunda declaración - actualizar con delta_tolerance)
# ============================================================================

delta_tolerance = DeltaToleranceConfig()


# ============================================================================
# FUNCIONES ÚTILES
# ============================================================================

def print_config():
    """Imprimir toda la configuración."""
    print("\n" + "="*70)
    print("OPERABILITY CONFIG")
    print("="*70)
    print(data_source)
    print(kill_switch)
    print(model_health)
    print(risk_macro)
    print(output)
    print(gate_config)
    print(delta_tolerance)
    print("="*70)


if __name__ == "__main__":
    print_config()
