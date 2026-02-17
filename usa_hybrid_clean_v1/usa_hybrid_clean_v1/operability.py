"""
OPERABILITY.PY - Single Source of Truth para Definición de "Operable"
======================================================================

Define GLOBALMENTE qué es una señal "operable".
Todos los scripts importan de aquí. Nunca re-implementar filtros.

Uso:
    from operability import operable_mask, CONF_THRESHOLD, WHITELIST_TICKERS
    
    df["macro_risk"] = df["date"].apply(calculate_macro_risk_level)
    mask = operable_mask(df)
    operable = df[mask]
"""

import pandas as pd
import numpy as np
from typing import Callable, Optional
from operability_config import gate_config

# ============================================================================
# CONSTANTES GLOBALES - NUNCA CAMBIAR SIN DOCUMENTAR
# ============================================================================

CONF_THRESHOLD = 4  # Confidence score >= 4 (de 5)

ALLOWED_RISKS = ["LOW", "MEDIUM"]  # Riesgos permitidos. No operar si HIGH/CRITICAL

WHITELIST_TICKERS = ["CVX", "XOM", "WMT", "MSFT", "SPY"]  # Tickers probados

# ============================================================================
# FUNCIONES PREPARACION
# ============================================================================

def prepare_operability_columns(df: pd.DataFrame, warn_on_fallback: bool = True) -> pd.DataFrame:
    """
    PREPROCESAMIENTO UNIFICADO - Llama antes de operable_mask().
    
    Prepara todas las columnas requeridas por operable_mask():
    1. Normaliza confidence_score -> confidence (alias)
    2. Crea macro_risk si falta (fallback a "MEDIUM" con warning)
    3. Normaliza tickers (uppercase, strip)
    4. Valida tipos (date como datetime, confidence como float)
    5. Valida fechas
    
    Args:
        df: DataFrame con datos
        warn_on_fallback: Si True, alerta cuando se usa macro_risk fallback
        
    Returns:
        DataFrame preparado y listo para operable_mask()
        
    Raises:
        ValueError: Si falta columna crítica (ticker, confianza, date)
    """
    df = df.copy()
    
    print("[PREP] Iniciando prepare_operability_columns()...")
    
    # 1. Normalizar confidence (puede ser confidence_score, confidence_level, o confidence)
    if "confidence" not in df.columns:
        if "confidence_score" in df.columns:
            df["confidence"] = df["confidence_score"]
            print(f"[PREP]  Usando confidence_score como confidence")
        elif "confidence_level" in df.columns:
            # Convertir texto a número
            level_map = {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
                         "Baja": 2, "Media": 3, "Alta": 4, "Muy Alta": 5}
            df["confidence"] = df["confidence_level"].map(level_map).fillna(3).astype(float)
            print(f"[PREP]  Convertido confidence_level a confidence")
        else:
            raise ValueError("[PREP] No se encontró columna de confianza (confidence, confidence_score, confidence_level)")
    
    # 2. Validar columnas críticas
    required = ["ticker", "confidence", "date"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"[PREP] Faltan columnas críticas: {missing}")
    
    # 3. Normalizar tipo de date
    if df["date"].dtype != "datetime64[ns]":
        print(f"[PREP]  Convirtiendo date a datetime64[ns]...")
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        invalid_dates = df["date"].isna().sum()
        if invalid_dates > 0:
            print(f"[PREP]  WARN: {invalid_dates} fechas inválidas (NaT)")
    
    # 4. Normalizar confidence a float
    if df["confidence"].dtype != "float64":
        print(f"[PREP]  Convirtiendo confidence a float64...")
        df["confidence"] = pd.to_numeric(df["confidence"], errors="coerce")
        invalid_conf = df["confidence"].isna().sum()
        if invalid_conf > 0:
            print(f"[PREP]  WARN: {invalid_conf} confidence inválidas (NaN)")
    
    # 5. Normalizar tickers
    print(f"[PREP]  Normalizando tickers...")
    df["ticker"] = df["ticker"].str.strip().str.upper()
    
    # 5b. Calcular gap_pct si overlay habilitado y hay OHLCV
    overlay_active = gate_config.is_gap_overlay_active()
    if overlay_active:
        if "open" in df.columns and "close" in df.columns:
            print(f"[PREP]  Calculando gap_pct desde OHLCV...")
            # Obtener prev_close por ticker
            if "prev_close" not in df.columns:
                df["prev_close"] = df.groupby("ticker")["close"].shift(1)
            # Disponibilidad: prev_close no NaN y > 0
            avail_mask = (~df["prev_close"].isna()) & (df["prev_close"] > 0)
            df["gap_pct"] = 0.0
            df.loc[avail_mask, "gap_pct"] = ((df.loc[avail_mask, "open"] - df.loc[avail_mask, "prev_close"]) / df.loc[avail_mask, "prev_close"] * 100)
            # Marcar disponibilidad para auditoría
            df["gap_pct_available"] = avail_mask.astype(int)
            # Limpiar prev_close para no contaminar downstream
            df.drop("prev_close", axis=1, inplace=True)
        else:
            print(f"[PREP]  GAP overlay activo pero falta open/prev_close → gap_pct unavailable (set a 0, availability=0)")
            df["gap_pct"] = 0.0
            df["gap_pct_available"] = 0
    else:
        if gate_config.MODE.upper() == "PROD" and not gate_config.OHLCV_READY:
            print(f"[PREP]  GAP overlay solicitado pero desactivado en PROD (OHLCV_READY=False) → gap_pct=0")
        else:
            print(f"[PREP]  GAP_OVERLAY_DISABLED por configuración - gap_pct=0")
        df["gap_pct"] = 0.0
        df["gap_pct_available"] = 0
    
    # 6. Crear macro_risk si falta - CALCULAR REAL (no fallback)
    if "macro_risk" not in df.columns:
        print(f"[PREP] {'!'*60}")
        print(f"[PREP] CALCULANDO macro_risk desde FOMC dates...")
        print(f"[PREP] {'!'*60}")
        
        # Importar función de cálculo real
        from backtest_confidence_rules import calculate_macro_risk_level
        
        # Calcular para cada fila (date, gap_pct real)
        df["macro_risk"] = df.apply(
            lambda row: calculate_macro_risk_level(row["date"], gap_pct=row.get("gap_pct", 0)),
            axis=1
        )
        
        # Diagnóstico
        risk_counts = df["macro_risk"].value_counts()
        print(f"[PREP] Distribución macro_risk calculado:")
        for risk, count in risk_counts.items():
            pct = 100 * count / len(df)
            print(f"[PREP]   {risk}: {count} ({pct:.1f}%)")
        print(f"[PREP] OK: macro_risk calculado para {len(df)} filas")
    else:
        # Asegurarse que sea string
        df["macro_risk"] = df["macro_risk"].fillna("MEDIUM").astype(str)
        invalid_risk = (~df["macro_risk"].isin(ALLOWED_RISKS + ["UNKNOWN", "MEDIUM", "HIGH", "CRITICAL"])).sum()
        if invalid_risk > 0:
            print(f"[PREP]  WARN: {invalid_risk} valores de macro_risk inválidos (normalizando a MEDIUM)")
            df.loc[~df["macro_risk"].isin(ALLOWED_RISKS), "macro_risk"] = "MEDIUM"
    
    print(f"[PREP] OK: {len(df)} filas listas para operable_mask()")
    return df


# ============================================================================
# FUNCIONES
# ============================================================================

def normalize_tickers(df: pd.DataFrame, column: str = "ticker") -> pd.DataFrame:
    """
    Normalizar tickers: uppercase + strip espacios.
    
    Args:
        df: DataFrame
        column: Nombre de la columna de tickers
        
    Returns:
        DataFrame con tickers normalizados
        
    Side effect:
        Loggea cuántos tickers se normalizaron
    """
    df = df.copy()
    
    if column not in df.columns:
        return df
    
    original = df[column].copy()
    df[column] = df[column].str.strip().str.upper()
    
    # Detectar cambios
    changed = (original != df[column]).sum()
    if changed > 0:
        print(f"⚠️  Normalizados {changed} tickers (espacios/minúsculas)")
    
    return df


def validate_required_columns(df: pd.DataFrame) -> bool:
    """
    Validar que DataFrame tiene columnas requeridas.
    
    Requeridas:
        - confidence_score
        - macro_risk (o risk_level para adaptar)
        - ticker
        
    Returns:
        True si OK, False si falta algo
    """
    required = ["confidence_score", "ticker"]
    risk_col = "macro_risk" if "macro_risk" in df.columns else "risk_level"
    
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"❌ ERROR: Faltan columnas: {missing}")
        return False
    
    if risk_col not in df.columns:
        print(f"❌ ERROR: Falta columna de riesgo (macro_risk o risk_level)")
        return False
    
    return True


def adapt_risk_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adapter: si existe risk_level, renombrar a macro_risk.
    
    Evita confusiones con nombres diferentes.
    
    Args:
        df: DataFrame
        
    Returns:
        DataFrame con columna estandarizada como macro_risk
    """
    df = df.copy()
    
    if "risk_level" in df.columns and "macro_risk" not in df.columns:
        df = df.rename(columns={"risk_level": "macro_risk"})
        print("✓ Adaptado: risk_level → macro_risk")
    
    return df


def operable_mask(
    df: pd.DataFrame,
    conf_threshold: int = CONF_THRESHOLD,
    allowed_risks: list = ALLOWED_RISKS,
    whitelist: list = WHITELIST_TICKERS,
    ticker_column: str = "ticker",
    risk_column: str = "macro_risk"
) -> pd.Series:
    """
    FUNCIÓN CENTRAL: Máscara booleana para señales operables.
    
    Una señal es OPERABLE si:
        1. confidence_score >= conf_threshold
        2. macro_risk IN allowed_risks
        3. ticker IN whitelist
        
    Args:
        df: DataFrame con datos
        conf_threshold: Mínimo confidence (default: 4)
        allowed_risks: Lista de riesgos permitidos (default: ["LOW", "MEDIUM"])
        whitelist: Lista de tickers permitidos (default: WHITELIST_TICKERS)
        ticker_column: Nombre columna tickers (default: "ticker")
        risk_column: Nombre columna riesgo (default: "macro_risk")
        
    Returns:
        pd.Series booleana (True = operable)
        
    Raises:
        ValueError: Si falta columna requerida
    """
    
    # Validar que existan columnas
    if not validate_required_columns(df):
        raise ValueError("DataFrame incompleto para operable_mask")
    
    # Adaptar nombres si es necesario
    df = adapt_risk_column(df)
    
    # Normalizar tickers
    df = normalize_tickers(df, ticker_column)
    
    # Aplicar 3 filtros
    conf_ok = df["confidence_score"] >= conf_threshold
    risk_ok = df[risk_column].isin(allowed_risks)
    ticker_ok = df[ticker_column].isin(whitelist)
    
    return conf_ok & risk_ok & ticker_ok


def get_operability_breakdown(
    df: pd.DataFrame,
    conf_threshold: int = CONF_THRESHOLD,
    allowed_risks: list = ALLOWED_RISKS,
    whitelist: list = WHITELIST_TICKERS
) -> dict:
    """
    Desglose paso a paso de cómo se reducen las observaciones.
    
    Útil para diagnóstico y auditoría.
    
    Returns:
        {
            "global": 26637,
            "conf_ok": 10384,
            "conf_risk": 10364,
            "operable": 3881,
            "percentages": {...}
        }
    """
    df = adapt_risk_column(df)
    df = normalize_tickers(df)
    
    total = len(df)
    
    conf_ok_count = (df["confidence_score"] >= conf_threshold).sum()
    conf_risk_count = (
        (df["confidence_score"] >= conf_threshold) &
        (df["macro_risk"].isin(allowed_risks))
    ).sum()
    operable_count = len(df[operable_mask(df, conf_threshold, allowed_risks, whitelist)])
    
    return {
        "global": total,
        "conf_only": conf_ok_count,
        "conf_risk": conf_risk_count,
        "operable": operable_count,
        "percentages": {
            "conf_only": conf_ok_count / total * 100 if total > 0 else 0,
            "conf_risk": conf_risk_count / total * 100 if total > 0 else 0,
            "operable": operable_count / total * 100 if total > 0 else 0,
        }
    }


def get_risk_distribution(df: pd.DataFrame) -> dict:
    """
    Distribución de riesgos macro.
    
    Útil para verificar que el gate discrimina.
    
    Returns:
        {
            "LOW": 0,
            "MEDIUM": 3881,
            "HIGH": 500,
            "CRITICAL": 200,
            "NaN": 50
        }
    """
    df = adapt_risk_column(df)
    
    risk_counts = df["macro_risk"].value_counts(dropna=False).to_dict()
    total = len(df)
    
    # Agregar percentajes
    distribution = {}
    for risk, count in risk_counts.items():
        pct = count / total * 100 if total > 0 else 0
        risk_name = risk if pd.notna(risk) else "NaN"
        distribution[str(risk_name)] = {
            "count": count,
            "percentage": round(pct, 2)
        }
    
    return distribution


# ============================================================================
# CONSTANTES DE REFERENCIA (para validación)
# ============================================================================

EXPECTED_OPERABLE_COUNT = 3881  # Número oficial en dataset de referencia

if __name__ == "__main__":
    # Test rápido
    print("✓ operability.py cargado")
    print(f"  CONF_THRESHOLD: {CONF_THRESHOLD}")
    print(f"  ALLOWED_RISKS: {ALLOWED_RISKS}")
    print(f"  WHITELIST_TICKERS: {WHITELIST_TICKERS}")
    print(f"  EXPECTED_OPERABLE_COUNT: {EXPECTED_OPERABLE_COUNT}")
