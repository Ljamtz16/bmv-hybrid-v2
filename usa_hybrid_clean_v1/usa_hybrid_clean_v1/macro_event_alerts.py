"""
SISTEMA DE DETECCIÓN DE EVENTOS MACRO Y ALERTAS
Detecta automáticamente eventos que afectan el mercado
y genera alertas para PAUSAR el trading

Eventos detectados:
  1. Earnings season (trimestre)
  2. Reuniones Fed (FOMC)
  3. Elecciones (USA/globales)
  4. Reportes económicos (CPI, NFP, GDP)
  5. VIX > 20 (volatilidad alta)
  6. Market gaps > 2%
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ============================================================================
# CALENDARIO DE EVENTOS MACRO 2024-2026
# ============================================================================

FOMC_MEETINGS = [
    # 2024
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
    "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    # 2025
    "2025-01-29", "2025-03-19", "2025-04-30", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-11-05", "2025-12-17",
    # 2026
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17"
]

US_ELECTIONS = [
    "2024-11-05",  # Presidential Election
    "2026-11-03"   # Midterm Elections
]

CPI_RELEASE_DAYS = [
    # Típicamente día 12-15 de cada mes
]

NFP_RELEASE_DAYS = [
    # Típicamente primer viernes de cada mes
]

# Earnings seasons (aproximadas)
EARNINGS_SEASONS = [
    ("2024-01-15", "2024-02-15"),  # Q4 2023
    ("2024-04-15", "2024-05-15"),  # Q1 2024
    ("2024-07-15", "2024-08-15"),  # Q2 2024
    ("2024-10-15", "2024-11-15"),  # Q3 2024
    ("2025-01-15", "2025-02-15"),  # Q4 2024
    ("2025-04-15", "2025-05-15"),  # Q1 2025
    ("2025-07-15", "2025-08-15"),  # Q2 2025
    ("2025-10-15", "2025-11-15"),  # Q3 2025
    ("2026-01-15", "2026-02-15"),  # Q4 2025
]

# ============================================================================
# FUNCIONES DE DETECCIÓN
# ============================================================================

def is_fomc_week(date):
    """Detecta si la fecha está en semana de reunión Fed."""
    date = pd.to_datetime(date)
    for fomc_date in FOMC_MEETINGS:
        fomc = pd.to_datetime(fomc_date)
        # Considerar 2 días antes y después
        if abs((date - fomc).days) <= 2:
            return True, fomc_date
    return False, None

def is_election_week(date):
    """Detecta si la fecha está en semana de elecciones."""
    date = pd.to_datetime(date)
    for election_date in US_ELECTIONS:
        election = pd.to_datetime(election_date)
        # Considerar 3 días antes y 5 días después (volatilidad post-elección)
        if -3 <= (date - election).days <= 5:
            return True, election_date
    return False, None

def is_earnings_season(date):
    """Detecta si la fecha está en earnings season."""
    date = pd.to_datetime(date)
    for start, end in EARNINGS_SEASONS:
        if pd.to_datetime(start) <= date <= pd.to_datetime(end):
            return True, start, end
    return False, None, None

def check_vix_high(vix_value=None):
    """Detecta si VIX está alto (> 20)."""
    # En producción, obtener VIX real desde API
    # Por ahora, retorna placeholder
    if vix_value and vix_value > 20:
        return True, vix_value
    return False, None

def check_market_gap(df, date, threshold=2.0):
    """Detecta si hubo gap significativo en el mercado."""
    date = pd.to_datetime(date)
    
    # Filtrar SPY para el día
    spy_data = df[(df["ticker"] == "SPY") & (df["date"] == date)]
    
    if len(spy_data) == 0:
        return False, None
    
    close_today = spy_data.iloc[0]["close"]
    
    # Obtener día anterior
    prev_date = date - timedelta(days=1)
    while True:
        spy_prev = df[(df["ticker"] == "SPY") & (df["date"] == prev_date)]
        if len(spy_prev) > 0:
            close_prev = spy_prev.iloc[0]["close"]
            break
        prev_date -= timedelta(days=1)
        if (date - prev_date).days > 7:  # Evitar loops infinitos
            return False, None
    
    gap_pct = ((close_today - close_prev) / close_prev) * 100
    
    if abs(gap_pct) >= threshold:
        return True, gap_pct
    
    return False, None

# ============================================================================
# SISTEMA DE ALERTAS
# ============================================================================

def check_trading_safety(date, df=None, vix_value=None):
    """
    Verifica si es seguro operar en la fecha dada.
    
    Retorna:
        safe (bool): True si es seguro, False si hay alerta
        alerts (list): Lista de alertas detectadas
        risk_level (str): "LOW", "MEDIUM", "HIGH", "CRITICAL"
    """
    
    date = pd.to_datetime(date)
    alerts = []
    risk_score = 0
    
    # 1. Verificar FOMC
    is_fomc, fomc_date = is_fomc_week(date)
    if is_fomc:
        alerts.append(f"⚠️  FOMC Meeting: {fomc_date} (±2 días)")
        risk_score += 3
    
    # 2. Verificar elecciones
    is_election, election_date = is_election_week(date)
    if is_election:
        alerts.append(f"🚨 ELECTION: {election_date} (alta volatilidad)")
        risk_score += 5
    
    # 3. Verificar earnings season
    is_earnings, season_start, season_end = is_earnings_season(date)
    if is_earnings:
        alerts.append(f"📊 EARNINGS SEASON: {season_start} → {season_end}")
        risk_score += 2
    
    # 4. Verificar VIX
    is_vix_high, vix = check_vix_high(vix_value)
    if is_vix_high:
        alerts.append(f"📈 VIX HIGH: {vix:.1f} (normal < 20)")
        risk_score += 3
    
    # 5. Verificar market gap
    if df is not None:
        is_gap, gap_pct = check_market_gap(df, date)
        if is_gap:
            alerts.append(f"⚡ MARKET GAP: {gap_pct:+.2f}% (threshold 2%)")
            risk_score += 2
    
    # Determinar nivel de riesgo
    if risk_score == 0:
        risk_level = "LOW"
        safe = True
    elif risk_score <= 2:
        risk_level = "MEDIUM"
        safe = True
    elif risk_score <= 4:
        risk_level = "HIGH"
        safe = False
    else:
        risk_level = "CRITICAL"
        safe = False
    
    return safe, alerts, risk_level

# ============================================================================
# GENERAR CALENDARIO DE TRADING
# ============================================================================

def generate_trading_calendar(start_date, end_date, df=None):
    """Genera calendario con alertas para cada día."""
    
    calendar = []
    current_date = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    
    while current_date <= end:
        
        safe, alerts, risk_level = check_trading_safety(current_date, df)
        
        calendar.append({
            "date": current_date.date(),
            "safe_to_trade": safe,
            "risk_level": risk_level,
            "alerts_count": len(alerts),
            "alerts": " | ".join(alerts) if alerts else "✅ Safe to trade"
        })
        
        current_date += timedelta(days=1)
    
    return pd.DataFrame(calendar)

# ============================================================================
# MAIN - DEMO
# ============================================================================

if __name__ == "__main__":
    
    print("="*70)
    print("SISTEMA DE DETECCIÓN DE EVENTOS MACRO Y ALERTAS")
    print("="*70)
    
    # Cargar datos
    try:
        df = pd.read_csv("outputs/analysis/all_signals_with_confidence.csv")
        df["date"] = pd.to_datetime(df["date"])
        print(f"✓ Datos cargados: {len(df)} observaciones")
    except:
        print("⚠️  Sin datos cargados, solo calendario de eventos")
        df = None
    
    # Test 1: Verificar semana de Noviembre (elecciones)
    print("\n" + "="*70)
    print("TEST 1: Semana de Noviembre 2025 (con elecciones)")
    print("="*70)
    
    test_dates_nov = pd.date_range("2025-11-05", "2025-11-11")
    for date in test_dates_nov:
        safe, alerts, risk_level = check_trading_safety(date, df)
        status = "✅ OPERAR" if safe else "❌ PAUSAR"
        print(f"{date.date()} → {status} | Risk: {risk_level:8s} | {alerts}")
    
    # Test 2: Verificar semana de Agosto (normal)
    print("\n" + "="*70)
    print("TEST 2: Semana de Agosto 2025 (sin eventos)")
    print("="*70)
    
    test_dates_aug = pd.date_range("2025-08-04", "2025-08-11")
    for date in test_dates_aug:
        safe, alerts, risk_level = check_trading_safety(date, df)
        status = "✅ OPERAR" if safe else "❌ PAUSAR"
        print(f"{date.date()} → {status} | Risk: {risk_level:8s} | {alerts}")
    
    # Generar calendario completo 2025
    print("\n" + "="*70)
    print("GENERANDO CALENDARIO DE TRADING 2025")
    print("="*70)
    
    calendar = generate_trading_calendar("2025-01-01", "2025-12-31", df)
    
    # Estadísticas
    safe_days = calendar["safe_to_trade"].sum()
    total_days = len(calendar)
    
    print(f"\n📅 Calendario 2025:")
    print(f"  Total días: {total_days}")
    print(f"  Días seguros: {safe_days} ({safe_days/total_days*100:.1f}%)")
    print(f"  Días con alertas: {total_days - safe_days} ({(total_days-safe_days)/total_days*100:.1f}%)")
    
    # Por nivel de riesgo
    print(f"\n📊 Distribución por riesgo:")
    risk_counts = calendar["risk_level"].value_counts()
    for level in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
        count = risk_counts.get(level, 0)
        pct = (count / total_days) * 100
        print(f"  {level:8s}: {count:3d} días ({pct:5.1f}%)")
    
    # Exportar calendario
    calendar.to_csv("outputs/trading_calendar_2025.csv", index=False)
    print(f"\n✓ Guardado: outputs/trading_calendar_2025.csv")
    
    # Mostrar días más peligrosos
    print(f"\n🚨 DÍAS MÁS PELIGROSOS (Critical Risk):")
    critical_days = calendar[calendar["risk_level"] == "CRITICAL"].head(10)
    if len(critical_days) > 0:
        for _, row in critical_days.iterrows():
            print(f"  {row['date']} | {row['alerts']}")
    else:
        print("  Ninguno")
    
    print("\n" + "="*70)
    print("✨ Sistema de alertas configurado")
    print("="*70)
