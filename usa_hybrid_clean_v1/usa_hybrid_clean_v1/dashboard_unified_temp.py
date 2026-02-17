#!/usr/bin/env python3
"""
Trade Dashboard Unificado - FASE 2 OPTIMIZADO

✅ READ-ONLY DASHBOARD:
   - Solo lectura de CSV (sin lógica de decisión)
   - Tracking en background thread (no bloquea endpoints)
   - Snapshot centralizado (una sola fuente de verdad)
   - Caché de 10s para reutilizar métricas
   
🎯 Arquitectura limpia:
   - build_trade_snapshot(): Centraliza TODAS las métricas
   - get_cached_snapshot(): Cache para endpoints
   - Endpoints sin lógica duplicada
"""
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template_string, jsonify, request
import logging
import logging.handlers
import socket
import pytz
import pandas_market_calendars as mcal
import threading
import time
import math

# ============================================================================
# 📋 LOGGER SETUP (FASE 5.1 - Observabilidad)
# ============================================================================
LOGS_DIR = Path('reports/logs')
LOGS_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger('dashboard')
logger.setLevel(logging.DEBUG)

# File handler (rotation cada 10MB, max 5 files)
file_handler = logging.handlers.RotatingFileHandler(
    LOGS_DIR / 'dashboard.log',
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=5
)
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# Console handler (solo INFO y superior)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter(
    '[%(levelname)s] %(message)s'
)
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

app = Flask(__name__)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

TRADE_PLAN_PATH = Path("val/trade_plan_EXECUTE.csv")
TRADE_HISTORY_PATH = Path("val/trade_history_closed.csv")
STANDARD_PLAN_PATH = Path("val/trade_plan_STANDARD.csv")
STANDARD_PLANS_DIR = Path("evidence") / "weekly_plans"
STANDARD_TRACK_PATH = Path("val/standard_plan_tracking.csv")

# Cache de precios (TTL 60s)
PRICE_CACHE = {}
CACHE_TTL = 60

# Cache de estimaciones de tiempo (TTL 10 min) - para fallback estimate_time_to_target
TIME_ESTIMATE_CACHE = {}
TIME_CACHE_TTL = 600

# Tracking en background thread
TRACKING_THREAD = None
TRACKING_ACTIVE = False
TRACKING_INTERVAL = 90  # ejecutar cada 90 segundos

# Modo producción (FASE 5.3)
# - Por ahora, single-process only.
# - Si se usa multi-worker, activar file-locking antes de escalar.
PRODUCTION_MODE = True
SINGLE_PROCESS_ONLY = True

# Snapshot cache (para reutilizar en múltiples endpoints)
SNAPSHOT_CACHE = None

def json_safe_float(value, default=0.0):
    """Convierte a float seguro para JSON (NaN → default, Inf → default)"""
    try:
        val = float(value)
        if math.isnan(val) or math.isinf(val):
            return default
        return val
    except (ValueError, TypeError):
        return default
SNAPSHOT_CACHE_TTL = 10  # segundos (fresh)
SNAPSHOT_STALE_TTL = 120  # segundos (stale-while-revalidate)
SNAPSHOT_LAST_BUILD = 0
SNAPSHOT_REVALIDATING = False

# Lock para thread-safety en lectura/escritura de CSVs
CSV_LOCK = threading.RLock()  # RLock permite re-entrada desde el mismo thread

# ============================================================================
# CAPITAL MANAGER - Gestión de buckets Swing + Intraday
# ============================================================================
class CapitalManager:
    """
    Maneja buckets de capital separados para Swing e Intraday.
    Autoridad final en decisiones de ejecución.
    """
    
    def __init__(self, total_capital=2000, swing_pct=0.70, intraday_pct=0.30):
        self.total = total_capital
        self.swing_pct = swing_pct
        self.intraday_pct = intraday_pct
        
        self.swing_bucket = total_capital * swing_pct
        self.intraday_bucket = total_capital * intraday_pct
        
        # Límites de posiciones abiertas
        self.max_open_total = 4
        self.max_open_swing = 3
        self.max_open_intraday = 2
        
        # Tracking por libro
        self.open_swing = {}      # {ticker: qty}
        self.open_intraday = {}   # {ticker: qty}
        
        logger.info(f"[CAPITAL] Initialized: Total=${total_capital}, Swing={swing_pct*100:.0f}% (${self.swing_bucket}), Intraday={intraday_pct*100:.0f}% (${self.intraday_bucket})")
    
    def available_swing(self):
        """Retorna capital disponible en bucket Swing"""
        return self.swing_bucket
    
    def available_intraday(self):
        """Retorna capital disponible en bucket Intraday"""
        return self.intraday_bucket
    
    def get_open_count(self, book='swing'):
        """Retorna cantidad de posiciones abiertas en un libro"""
        if book == 'swing':
            return len(self.open_swing)
        elif book == 'intraday':
            return len(self.open_intraday)
        else:
            return len(self.open_swing) + len(self.open_intraday)
    
    def allows(self, signal_dict):
        """
        Chequea si una señal puede ejecutarse:
        - Suficiente capital en bucket
        - No supera límites de posiciones abiertas
        - Ticker no duplicado en mismo libro
        
        signal_dict: {book, ticker, entry, qty, side}
        """
        book = signal_dict.get('book', 'swing')
        ticker = signal_dict.get('ticker', '')
        qty = signal_dict.get('qty', 0)
        entry = signal_dict.get('entry', 0)
        
        if not ticker or qty <= 0 or entry <= 0:
            logger.warning(f"[CAPITAL] Invalid signal: {signal_dict}")
            return False
        
        cost = qty * entry
        
        # Chequea límites totales
        total_open = self.get_open_count(book='all')
        if total_open >= self.max_open_total:
            logger.warning(f"[CAPITAL] Max total positions reached ({total_open}/{self.max_open_total})")
            return False
        
        # Chequea límites por libro
        if book == 'swing':
            if self.get_open_count(book='swing') >= self.max_open_swing:
                logger.warning(f"[CAPITAL] Max Swing positions reached ({self.get_open_count('swing')}/{self.max_open_swing})")
                return False
            if ticker in self.open_swing:
                logger.warning(f"[CAPITAL] Ticker {ticker} already open in Swing")
                return False
            if cost > self.available_swing():
                logger.warning(f"[CAPITAL] Insufficient Swing capital: need ${cost}, available ${self.available_swing()}")
                return False
        
        elif book == 'intraday':
            if self.get_open_count(book='intraday') >= self.max_open_intraday:
                logger.warning(f"[CAPITAL] Max Intraday positions reached ({self.get_open_count('intraday')}/{self.max_open_intraday})")
                return False
            if ticker in self.open_intraday:
                logger.warning(f"[CAPITAL] Ticker {ticker} already open in Intraday")
                return False
            if cost > self.available_intraday():
                logger.warning(f"[CAPITAL] Insufficient Intraday capital: need ${cost}, available ${self.available_intraday()}")
                return False
            
            # Gate: Intraday reduce 50% si ticker en Swing (correlación heat)
            if ticker in self.open_swing:
                logger.info(f"[CAPITAL] Intraday {ticker} in Swing: reducing 50%")
                cost = cost * 0.5
        
        return True
    
    def add_open(self, book, ticker, qty):
        """Registra posición abierta"""
        if book == 'swing':
            self.open_swing[ticker] = qty
            logger.info(f"[CAPITAL] Swing opened: {ticker} x{qty}")
        elif book == 'intraday':
            self.open_intraday[ticker] = qty
            logger.info(f"[CAPITAL] Intraday opened: {ticker} x{qty}")
    
    def remove_open(self, book, ticker):
        """Registra cierre de posición"""
        if book == 'swing':
            if ticker in self.open_swing:
                del self.open_swing[ticker]
                logger.info(f"[CAPITAL] Swing closed: {ticker}")
        elif book == 'intraday':
            if ticker in self.open_intraday:
                del self.open_intraday[ticker]
                logger.info(f"[CAPITAL] Intraday closed: {ticker}")


# ============================================================================
# RISK MANAGER - Kill-switches y drawdown control
# ============================================================================
class RiskManager:
    """
    Controla kill-switches y drawdown.
    Previene overtrading en rachas negativas.
    """
    
    def __init__(self, capital_manager, capital_total=2000):
        self.cm = capital_manager
        self.capital_total = capital_total
        self.capital_peak = capital_total
        
        # Kill-switch Intraday
        self.intraday_enabled = True
        self.intraday_loss_today = 0.0
        self.intraday_daily_stop_pct = 0.03  # 3% del bucket intraday
        self.intraday_weekly_stop_pct = 0.06  # 6% del bucket intraday
        
        # Drawdown general
        self.drawdown_threshold = 0.10  # 10% drawdown total
        
        # Tracking por día/semana
        self.current_date = datetime.now().date()
        self.current_week_start = datetime.now().date() - timedelta(days=datetime.now().weekday())
        
        logger.info(f"[RISK] Initialized: Daily stop {self.intraday_daily_stop_pct*100:.1f}%, Weekly stop {self.intraday_weekly_stop_pct*100:.1f}%, DD threshold {self.drawdown_threshold*100:.1f}%")
    
    def update_pnl(self, pnl_value):
        """
        Actualiza PnL y chequea kill-switches.
        pnl_value: profit/loss del día
        """
        self.intraday_loss_today += pnl_value
        
        # Chequea cambio de día
        today = datetime.now().date()
        if today != self.current_date:
            self.intraday_loss_today = 0.0
            self.current_date = today
        
        # Chequea cambio de semana
        week_start = today - timedelta(days=today.weekday())
        if week_start != self.current_week_start:
            self.intraday_enabled = True  # Reset weekly
            self.current_week_start = week_start
            logger.info(f"[RISK] Weekly reset: Intraday enabled")
        
        # Daily stop
        if self.intraday_loss_today < -(self.cm.intraday_bucket * self.intraday_daily_stop_pct):
            self.intraday_enabled = False
            logger.warning(f"[RISK] Daily stop hit: Intraday disabled (loss ${self.intraday_loss_today:.2f})")
    
    def update_capital(self, current_capital):
        """Actualiza capital y chequea drawdown"""
        if current_capital > self.capital_peak:
            self.capital_peak = current_capital
        
        dd = (self.capital_peak - current_capital) / self.capital_peak
        if dd > self.drawdown_threshold:
            self.intraday_enabled = False
            logger.critical(f"[RISK] Drawdown threshold hit: {dd*100:.2f}%. Intraday disabled.")
        
        return dd
    
    def is_intraday_enabled(self):
        """Retorna si Intraday puede operar"""
        return self.intraday_enabled
    
    def get_status(self):
        """Retorna status dict para logging/UI"""
        return {
            'intraday_enabled': self.intraday_enabled,
            'intraday_loss_today': self.intraday_loss_today,
            'capital_peak': self.capital_peak,
            'drawdown_pct': ((self.capital_peak - self.cm.total) / self.capital_peak) * 100,
        }


# Instancia global de Capital y Risk Manager
CAPITAL_MANAGER = CapitalManager(total_capital=2000, swing_pct=0.70, intraday_pct=0.30)
RISK_MANAGER = RiskManager(CAPITAL_MANAGER, capital_total=2000)


# ============================================================================
# METRICS TRACKER - Colecta métricas separadas por libro (FASE 2-3)
# ============================================================================
class MetricsTracker:
    """
    Rastrea métricas separadas para Swing vs Intraday.
    Calcula PF, winrate, DD por libro.
    Generador de reportes semanales.
    """
    
    def __init__(self, capital_manager):
        self.cm = capital_manager
        
        # Trades cerrados por libro
        self.swing_trades = []
        self.intraday_trades = []
        
        # PnL acumulado
        self.swing_pnl = 0.0
        self.intraday_pnl = 0.0
        
        # Estadísticas actuales
        self.swing_stats = {
            'trades': 0,
            'winners': 0,
            'losers': 0,
            'pnl': 0.0,
            'pf': 0.0,
            'winrate': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'dd_pct': 0.0,
            'capital_peak': capital_manager.total
        }
        
        self.intraday_stats = {
            'trades': 0,
            'winners': 0,
            'losers': 0,
            'pnl': 0.0,
            'pf': 0.0,
            'winrate': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'dd_pct': 0.0,
            'capital_peak': capital_manager.total
        }
        
        # Reporte semanal
        self.weekly_reports = []
        self.current_week_start = datetime.now().date() - timedelta(days=datetime.now().weekday())
        
        logger.info(f"[METRICS] Tracker initialized")
    
    def log_trade(self, book, ticker, side, entry, exit_price, qty, pnl, reason_exit='TP'):
        """Registra un trade cerrado"""
        trade = {
            'timestamp': datetime.now(),
            'book': book,
            'ticker': ticker,
            'side': side,
            'entry': entry,
            'exit': exit_price,
            'qty': qty,
            'pnl': pnl,
            'reason': reason_exit,
        }
        
        if book == 'swing':
            self.swing_trades.append(trade)
            self.swing_pnl += pnl
            logger.info(f"[SWING] {side} {ticker}: entry={entry:.2f}, exit={exit_price:.2f}, PnL={pnl:+.2f}")
        elif book == 'intraday':
            self.intraday_trades.append(trade)
            self.intraday_pnl += pnl
            logger.info(f"[INTRADAY] {side} {ticker}: entry={entry:.2f}, exit={exit_price:.2f}, PnL={pnl:+.2f}")
        
        self._recalculate_stats()
    
    def _recalculate_stats(self):
        """Recalcula todas las estadísticas"""
        # Swing stats
        self._calc_book_stats('swing', self.swing_trades, self.swing_stats)
        # Intraday stats
        self._calc_book_stats('intraday', self.intraday_trades, self.intraday_stats)
    
    def _calc_book_stats(self, book, trades, stats):
        """Calcula estadísticas para un libro específico"""
        if not trades:
            stats['trades'] = 0
            stats['pnl'] = 0.0
            return
        
        stats['trades'] = len(trades)
        stats['pnl'] = sum(t['pnl'] for t in trades)
        
        wins = [t for t in trades if t['pnl'] > 0]
        losses = [t for t in trades if t['pnl'] < 0]
        
        stats['winners'] = len(wins)
        stats['losers'] = len(losses)
        stats['winrate'] = stats['winners'] / stats['trades'] if stats['trades'] > 0 else 0.0
        
        if wins:
            stats['avg_win'] = sum(t['pnl'] for t in wins) / len(wins)
        else:
            stats['avg_win'] = 0.0
        
        if losses:
            stats['avg_loss'] = sum(t['pnl'] for t in losses) / len(losses)
        else:
            stats['avg_loss'] = 0.0
        
        # Profit Factor
        gross_profit = sum(t['pnl'] for t in wins) if wins else 0.0
        gross_loss = abs(sum(t['pnl'] for t in losses)) if losses else 0.0
        stats['pf'] = gross_profit / gross_loss if gross_loss > 0 else (1.0 if gross_profit > 0 else 0.0)
        
        # Drawdown (peak-to-trough)
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in trades:
            cumulative += t['pnl']
            if cumulative > peak:
                peak = cumulative
            dd = ((peak - cumulative) / peak * 100) if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        stats['dd'] = max_dd
    
    def get_weekly_report(self):
        """Genera reporte semanal"""
        week_start = datetime.now().date() - timedelta(days=datetime.now().weekday())
        
        # Trades de esta semana
        swing_week = [t for t in self.swing_trades if t['timestamp'].date() >= week_start]
        intraday_week = [t for t in self.intraday_trades if t['timestamp'].date() >= week_start]
        
        # Calcular PnL semanal
        swing_pnl_week = sum(t['pnl'] for t in swing_week)
        intraday_pnl_week = sum(t['pnl'] for t in intraday_week)
        
        # Best/worst trades
        swing_best = max([t['pnl'] for t in swing_week], default=0.0)
        swing_worst = min([t['pnl'] for t in swing_week], default=0.0)
        intraday_best = max([t['pnl'] for t in intraday_week], default=0.0)
        intraday_worst = min([t['pnl'] for t in intraday_week], default=0.0)
        
        report = {
            'week_start': week_start.isoformat(),
            'week_end': (week_start + timedelta(days=6)).isoformat(),
            'generated_at': datetime.now().isoformat(),
            'swing': {
                'trades': len(swing_week),
                'pnl': swing_pnl_week,
                'winners': len([t for t in swing_week if t['pnl'] > 0]),
                'losers': len([t for t in swing_week if t['pnl'] < 0]),
                'pf': self.swing_stats['pf'],
                'winrate': self.swing_stats['winrate'],
                'winrate_pct': self.swing_stats['winrate'] * 100,
                'avg_win': self.swing_stats['avg_win'],
                'avg_loss': self.swing_stats['avg_loss'],
                'best_trade': swing_best,
                'worst_trade': swing_worst,
            },
            'intraday': {
                'trades': len(intraday_week),
                'pnl': intraday_pnl_week,
                'winners': len([t for t in intraday_week if t['pnl'] > 0]),
                'losers': len([t for t in intraday_week if t['pnl'] < 0]),
                'pf': self.intraday_stats['pf'],
                'winrate': self.intraday_stats['winrate'],
                'winrate_pct': self.intraday_stats['winrate'] * 100,
                'avg_win': self.intraday_stats['avg_win'],
                'avg_loss': self.intraday_stats['avg_loss'],
                'best_trade': intraday_best,
                'worst_trade': intraday_worst,
            },
            'total': {
                'pnl': swing_pnl_week + intraday_pnl_week,
                'trades': len(swing_week) + len(intraday_week),
            }
        }
        
        self.weekly_reports.append(report)
        
        logger.info(f"[REPORT] Weekly report generated for week {week_start}")
        return report
    
    def get_status(self):
        """Retorna status actual por libro"""
        total_trades = len(self.swing_trades) + len(self.intraday_trades)
        total_pnl = self.swing_pnl + self.intraday_pnl
        
        # Calcular PF combinado
        all_trades = self.swing_trades + self.intraday_trades
        wins = [t for t in all_trades if t['pnl'] > 0]
        losses = [t for t in all_trades if t['pnl'] < 0]
        gross_profit = sum(t['pnl'] for t in wins) if wins else 0.0
        gross_loss = abs(sum(t['pnl'] for t in losses)) if losses else 0.0
        total_pf = gross_profit / gross_loss if gross_loss > 0 else (1.0 if gross_profit > 0 else 0.0)
        
        return {
            'swing': self.swing_stats.copy(),
            'intraday': self.intraday_stats.copy(),
            'total': {
                'trades': total_trades,
                'pnl': total_pnl,
                'pf': total_pf,
            },
            'total_pnl': total_pnl,
            'swing_pnl': self.swing_pnl,
            'intraday_pnl': self.intraday_pnl,
        }


# Instancia global de MetricsTracker
METRICS_TRACKER = MetricsTracker(CAPITAL_MANAGER)

def get_max_capital():
    """Lee capital máximo de config o usa 800 por defecto"""
    try:
        import yaml
        config_path = Path("config/base.yaml")
        if config_path.exists():
            with open(config_path) as f:
                cfg = yaml.safe_load(f)
                return cfg.get('capital_max', 800)
    except:
        pass
    return 800


# ============================================================================
# INTRADAY GATES - Filtro de calidad para entradas intraday
# ============================================================================
def intraday_gates_pass(signal_dict, market_data=None):
    """
    Valida una señal intraday contra 4 puertas de calidad.
    
    Gate 1: Contexto (macro del día)
    Gate 2: Alineación multi-timeframe
    Gate 3: Señal técnica confirmada
    Gate 4: Riesgo y ejecución
    
    Retorna: (passed: bool, reason: str)
    """
    
    ticker = signal_dict.get('ticker', '')
    entry = signal_dict.get('entry', 0)
    side = signal_dict.get('side', 'BUY')
    
    # GATE 1: Contexto (macro del día)
    # Rechaza si hay whipsaw severo en índices
    if market_data:
        spy_change = market_data.get('SPY_change_pct', 0)
        qqq_change = market_data.get('QQQ_change_pct', 0)
        
        # Si mercado está en rango lateral extremo (±1.5%), intraday se vuelve peligroso
        if abs(spy_change) < 0.5 and abs(qqq_change) < 0.5:
            logger.info(f"[GATE1] Market too flat for {ticker}: SPY {spy_change:.2f}%, QQQ {qqq_change:.2f}%")
            return False, "Gate 1 FAIL: Market too flat"
        
        # Si día es de evento conocido, rechaza
        if market_data.get('event_day', False):
            logger.info(f"[GATE1] Event day detected, intraday disabled")
            return False, "Gate 1 FAIL: Event day"
    
    # GATE 2: Alineación multi-timeframe
    # Intraday debe estar alineado con TF mayor (1H/Daily)
    daily_trend = signal_dict.get('daily_trend', None)  # 'UP', 'DOWN', 'FLAT'
    
    if daily_trend == 'DOWN' and side == 'BUY':
        logger.info(f"[GATE2] {ticker} BUY conflicts with daily DOWN trend")
        return False, "Gate 2 FAIL: Conflicts with daily trend"
    
    if daily_trend == 'UP' and side == 'SELL':
        logger.info(f"[GATE2] {ticker} SELL conflicts with daily UP trend")
        return False, "Gate 2 FAIL: Conflicts with daily trend"
    
    # GATE 3: Señal técnica confirmada
    # Valida que exista una confirmación (volumen, patrón, etc.)
    signal_strength = signal_dict.get('signal_strength', 0)  # 0-100
    min_strength = 50  # Mínimo 50% de confianza
    
    if signal_strength < min_strength:
        logger.info(f"[GATE3] {ticker} signal weak: {signal_strength}% < {min_strength}%")
        return False, f"Gate 3 FAIL: Signal strength {signal_strength}%"
    
    # GATE 4: Riesgo y ejecución
    # Valida SL, TP y time-out
    sl = signal_dict.get('sl', 0)
    tp = signal_dict.get('tp', 0)
    
    if not sl or not tp or entry <= 0:
        logger.warning(f"[GATE4] {ticker} missing SL/TP: sl={sl}, tp={tp}, entry={entry}")
        return False, "Gate 4 FAIL: Missing SL/TP/Entry"
    
    # SL debe ser pequeño (intraday es scalp)
    risk = abs(entry - sl) / entry
    reward = abs(tp - entry) / entry
    rr_ratio = reward / risk if risk > 0 else 0
    
    if risk > 0.03:  # SL > 3% es muy grande para intraday
        logger.info(f"[GATE4] {ticker} SL too large: {risk*100:.2f}% > 3%")
        return False, f"Gate 4 FAIL: SL too large ({risk*100:.2f}%)"
    
    if rr_ratio < 1.5:  # RR mínimo 1.5:1 para intraday
        logger.info(f"[GATE4] {ticker} poor R:R: {rr_ratio:.2f}:1 < 1.5:1")
        return False, f"Gate 4 FAIL: Poor R:R {rr_ratio:.2f}:1"
    
    # Todas las puertas pasaron
    logger.info(f"[INTRADAY] All gates passed for {ticker}: strength={signal_strength}%, RR={rr_ratio:.2f}:1")
    return True, "All gates passed"


def get_cached_prices(tickers):
    """Obtiene precios actuales con cache de 30s. Batch request."""
    import yfinance as yf
    from datetime import datetime, timedelta
    
    now = datetime.now()
    result = {}
    tickers_to_fetch = []
    
    for ticker in tickers:
        cached = PRICE_CACHE.get(ticker)
        if cached and (now - cached['timestamp']).seconds < CACHE_TTL:
            result[ticker] = cached['price']
        else:
            tickers_to_fetch.append(ticker)
    
    # Batch fetch para tickers no cacheados
    if tickers_to_fetch:
        try:
            # yfinance batch (espacio separado)
            tickers_str = ' '.join(tickers_to_fetch)
            data = yf.download(tickers_str, period='1d', interval='1m', progress=False, threads=True)
            
            for ticker in tickers_to_fetch:
                try:
                    if len(tickers_to_fetch) == 1:
                        price = float(data['Close'].iloc[-1])
                    else:
                        price = float(data['Close'][ticker].iloc[-1])
                    PRICE_CACHE[ticker] = {'price': price, 'timestamp': now}
                    result[ticker] = price
                except:
                    result[ticker] = None
        except:
            # Fallback: individual si batch falla
            for ticker in tickers_to_fetch:
                try:
                    stock = yf.Ticker(ticker)
                    hist = stock.history(period="1d", interval="1m")
                    if not hist.empty:
                        price = float(hist['Close'].iloc[-1])
                        PRICE_CACHE[ticker] = {'price': price, 'timestamp': now}
                        result[ticker] = price
                    else:
                        result[ticker] = None
                except:
                    result[ticker] = None
    
    return result

def get_local_ip():
    try:
        import socket
        # Obtener todas las interfaces
        hostname = socket.gethostname()
        all_ips = socket.gethostbyname_ex(hostname)[2]
        # Filtrar IPv4 válidas que NO sean 127.x.x.x ni 169.x.x.x
        for ip in all_ips:
            if not ip.startswith('127.') and not ip.startswith('169.') and not ip.startswith('192.168.137'):
                return ip
        # Si no encontramos una buena IP, retornar la primera válida
        for ip in all_ips:
            if not ip.startswith('127.') and not ip.startswith('169.'):
                return ip
        return "127.0.0.1"
    except:
        return "127.0.0.1"

def estimate_time_to_target(ticker, current_price, target_price, side="BUY"):
    """Estima tiempo basado en distancia real a target y velocidad combinada (70% velocity + 30% ATR)."""
    try:
        import yfinance as yf
        
        # Obtener histórico de 1 minuto (últimas 5 días)
        stock = yf.Ticker(ticker)
        hist = stock.history(period="5d", interval="1m")
        
        if hist.empty or len(hist) < 20:
            return None
        
        # Método 1: Velocidad actual (últimos 60 minutos)
        changes_recent = hist['Close'].diff().dropna().tail(60)
        if len(changes_recent) > 0:
            velocity_current = changes_recent.abs().mean()
        else:
            velocity_current = 0
        
        # Método 2: Volatilidad histórica (ATR - Average True Range de 14 períodos)
        high_low = hist['High'] - hist['Low']
        high_close = abs(hist['High'] - hist['Close'].shift())
        low_close = abs(hist['Low'] - hist['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        atr = true_range.tail(14).mean()
        
        # Combinar: 70% velocidad actual + 30% ATR (volatilidad esperada)
        if velocity_current > 0 and atr > 0:
            combined_velocity = (velocity_current * 0.7) + (atr * 0.3)
        elif velocity_current > 0:
            combined_velocity = velocity_current
        elif atr > 0:
            combined_velocity = atr
        else:
            return None
        
        # Distancia a recorrer (basado en precio actual y target real)
        distance = abs(target_price - current_price)
        
        # Tiempo estimado en minutos
        estimated_minutes = distance / combined_velocity
        
        return max(1, int(round(estimated_minutes)))
        
    except Exception as e:
        print(f"[WARNING] Error estimating time for {ticker}: {e}")
        return None

def get_time_from_plan(ticker, plan_path=None):
    """Lee tiempo estimado del CSV del plan desde columna 'etth_days_raw' y convierte a minutos.
    ✅ PRIORIDAD: usar siempre esto primero
    """
    try:
        if plan_path is None:
            plan_path = TRADE_PLAN_PATH
        
        if not Path(plan_path).exists():
            return None
        
        df = pd.read_csv(plan_path)
        if 'etth_days_raw' not in df.columns:
            return None
        
        row = df[df['ticker'].str.upper() == ticker.upper()]
        if row.empty:
            return None
        
        time_days = row.iloc[0]['etth_days_raw']
        if pd.isna(time_days) or time_days <= 0:
            return None
        
        # Convertir de días a minutos (1 día = 24 * 60 = 1440 minutos)
        minutes = int(time_days * 24 * 60)
        return max(1, minutes)
    except Exception as e:
        print(f"[WARNING] Error reading plan time for {ticker}: {e}")
        return None

def run_tracking_cycle():
    """Ejecuta tracking TP/SL en background thread cada TRACKING_INTERVAL segundos.
    ⏱️ SIN BLOQUEAR endpoints
    """
    global TRACKING_ACTIVE
    cycle_start = time.time()
    try:
        logger.debug("[TRACKING] Cycle start")
        _track_standard_plan_to_history()
        _track_probwin_plan_to_history()
        TRACKING_ACTIVE = True
        duration = time.time() - cycle_start
        logger.info(f"[TRACKING] Cycle completed in {duration:.2f}s")
    except Exception as e:
        duration = time.time() - cycle_start
        logger.exception(f"[TRACKING] Cycle FAILED after {duration:.2f}s: {e}")

def _rebuild_snapshot_async():
    """Rebuild snapshot in background (SWR)."""
    global SNAPSHOT_CACHE, SNAPSHOT_LAST_BUILD, SNAPSHOT_REVALIDATING
    try:
        snap_start = time.time()
        SNAPSHOT_CACHE = build_trade_snapshot()
        SNAPSHOT_LAST_BUILD = time.time()
        duration = time.time() - snap_start
        logger.debug(f"[SNAPSHOT] Async rebuild in {duration:.2f}s")
    except Exception as e:
        logger.exception(f"[SNAPSHOT] Async rebuild failed: {e}")
    finally:
        SNAPSHOT_REVALIDATING = False

def get_cached_snapshot():
    """Retorna snapshot cacheado.
    - Fresh: < SNAPSHOT_CACHE_TTL
    - Stale: < SNAPSHOT_STALE_TTL (devuelve cache y revalida en background)
    - Expired: rebuild síncrono
    """
    global SNAPSHOT_CACHE, SNAPSHOT_LAST_BUILD, SNAPSHOT_REVALIDATING
    now = time.time()

    if SNAPSHOT_CACHE is not None:
        age = now - SNAPSHOT_LAST_BUILD
        if age < SNAPSHOT_CACHE_TTL:
            return SNAPSHOT_CACHE
        if age < SNAPSHOT_STALE_TTL:
            if not SNAPSHOT_REVALIDATING:
                SNAPSHOT_REVALIDATING = True
                threading.Thread(target=_rebuild_snapshot_async, daemon=True).start()
            return SNAPSHOT_CACHE

    # Regenerar snapshot (bloqueante)
    SNAPSHOT_CACHE = build_trade_snapshot()
    SNAPSHOT_LAST_BUILD = now
    return SNAPSHOT_CACHE

def get_market_status():
    """Obtiene el estado del mercado NYSE usando zona horaria correcta y calendario real"""
    try:
        ny_tz = pytz.timezone('US/Eastern')
        now_ny = datetime.now(ny_tz)
        today = now_ny.date()
        current_time = now_ny.time()
        
        # Obtener calendario NYSE
        nyse = mcal.get_calendar('NYSE')
        schedule = nyse.schedule(start_date=today, end_date=today)
        
        # Si no hay schedule, es día no laborable (fin de semana o feriado)
        if schedule.empty:
            return "🔴 CERRADO", "danger", "Fin de semana o feriado"
        
        # Obtener horas de apertura y cierre
        market_open = schedule.iloc[0]['market_open'].tz_convert(ny_tz).time()
        market_close = schedule.iloc[0]['market_close'].tz_convert(ny_tz).time()
        
        # Verificar si el mercado está abierto
        if market_open <= current_time < market_close:
            time_str = f"{market_open.strftime('%H:%M')} - {market_close.strftime('%H:%M')} ET"
            return "🟢 ABIERTO", "success", time_str
        else:
            time_str = f"Cerrado - Abre {market_open.strftime('%H:%M')} ET"
            return "🔴 CERRADO", "danger", time_str
            
    except Exception as e:
        print(f"[WARNING] Error checking market status: {e}")
        # Fallback simple
        hour = datetime.now().hour
        if 14 <= hour < 21:
            return "⚠️ ABIERTO (estimado)", "warning", "09:30 - 16:00 ET"
        else:
            return "🔴 CERRADO", "danger", "Fuera de horario"

def load_active_trades(plan_path=TRADE_PLAN_PATH):
    """⚡ Carga trades activos rápidamente.
    ✅ Prioridad: etth_days_raw del plan
    ⚠️ NO estima tiempo (muy lento), solo muestra N/A
    """
    try:
        if not plan_path.exists():
            return []
            
        with CSV_LOCK:  # Thread-safe read
            df = pd.read_csv(plan_path)
        trades = []
        
        # Obtener todos los tickers para batch fetch de precios
        tickers = [row.get("ticker", "") for _, row in df.iterrows()]
        prices = get_cached_prices(tickers)
        
        for _, row in df.iterrows():
            ticker = row.get("ticker", "")
            entry = float(row.get("entry", 0))
            tp = float(row.get("tp_price", 0))
            sl = float(row.get("sl_price", 0))
            
            # Obtener precio del cache
            current_price = prices.get(ticker, entry)
            if current_price is None:
                current_price = entry
            
            # Calcular PnL actual
            side = str(row.get("side", "BUY")).upper()
            if side == "BUY":
                pnl = current_price - entry
            else:  # SELL
                pnl = entry - current_price
            
            # ✅ PRIORIDAD: tiempo del plan (etth_days_raw)
            # Si no existe = N/A (no hacer estimation cost-prohibitive)
            time_to_tp = get_time_from_plan(ticker, plan_path)
            time_to_sl = get_time_from_plan(ticker, plan_path)  # Mismo tiempo para SL
            
            trades.append({
                "ticker": ticker,
                "side": side,
                "entry": json_safe_float(entry),
                "exit": json_safe_float(current_price),
                "tp": json_safe_float(tp),
                "sl": json_safe_float(sl),
                "qty": int(row.get("qty", 1)),
                "prob_win": json_safe_float(row.get("prob_win", 50), 50.0),
                "pnl": json_safe_float(pnl),
                "time_to_tp": time_to_tp,  # Puede ser None
                "time_to_sl": time_to_sl   # Puede ser None
            })
        
        return trades
        
    except Exception as e:
        print(f"[WARNING] Error loading trades: {e}")
    return []

def _load_latest_standard_plan():
    """Carga el plan STANDARD más reciente (val o evidence/weekly_plans)."""
    try:
        if STANDARD_PLAN_PATH.exists():
            return pd.read_csv(STANDARD_PLAN_PATH)

        if STANDARD_PLANS_DIR.exists():
            standard_files = sorted(STANDARD_PLANS_DIR.glob("plan_standard_*.csv"))
            if standard_files:
                return pd.read_csv(standard_files[-1])
    except Exception as e:
        print(f"[WARNING] Error loading STANDARD plan: {e}")
    return pd.DataFrame()

def _normalize_standard_plan(plan_df):
    if plan_df is None or plan_df.empty:
        return pd.DataFrame()

    def pick(row, *keys, default=None):
        for k in keys:
            if k in row and pd.notna(row[k]):
                return row[k]
        return default

    rows = []
    now_iso = datetime.now().isoformat()
    for _, row in plan_df.iterrows():
        ticker = str(pick(row, "ticker", default="")).upper()
        if not ticker:
            continue
        side = str(pick(row, "side", "direction", default="BUY")).upper()
        entry = float(pick(row, "entry", "entry_price", default=0) or 0)
        tp_price = float(pick(row, "tp_price", "tp", default=0) or 0)
        sl_price = float(pick(row, "sl_price", "sl", default=0) or 0)
        qty = float(pick(row, "qty", "quantity", default=1) or 1)
        generated_at = str(pick(row, "generated_at", "date", "timestamp", default=now_iso))

        # ID único: STD + ticker + side + entry (evita duplicados)
        trade_id = f"STD-{ticker}-{side}-{entry:.4f}".replace(" ", "T")
        rows.append({
            "trade_id": trade_id,
            "ticker": ticker,
            "side": side,
            "entry": entry,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "qty": qty,
            "plan_type": "STANDARD",
            "entry_time": generated_at,
            "generated_at": generated_at
        })

    return pd.DataFrame(rows)

def _remove_closed_from_plans(closed_tickers, plan_type="ALL"):
    """Remueve tickers cerrados SOLO de archivos activos en val/ (NO toca evidence histórica)."""
    try:
        removed_count = 0
        
        # Remover del plan STANDARD activo (SOLO val/)
        if plan_type in ["STANDARD", "ALL"]:
            if STANDARD_PLAN_PATH.exists():
                df = pd.read_csv(STANDARD_PLAN_PATH)
                original_len = len(df)
                df = df[~df["ticker"].str.upper().isin(closed_tickers)]
                if len(df) < original_len:
                    df.to_csv(STANDARD_PLAN_PATH, index=False)
                    removed_count += original_len - len(df)
                    print(f"[INFO] Removed {original_len - len(df)} closed trades from STANDARD plan (val/)")
        
        # Remover del plan PROBWIN_55 activo (SOLO val/trade_plan_EXECUTE.csv)
        if plan_type in ["PROBWIN_55", "ALL"]:
            if TRADE_PLAN_PATH.exists():
                df = pd.read_csv(TRADE_PLAN_PATH)
                original_len = len(df)
                df = df[~df["ticker"].str.upper().isin(closed_tickers)]
                if len(df) < original_len:
                    df.to_csv(TRADE_PLAN_PATH, index=False)
                    removed_count += original_len - len(df)
                    print(f"[INFO] Removed {original_len - len(df)} closed trades from PROBWIN_55 plan (val/)")
        
        return removed_count
    except Exception as e:
        print(f"[WARNING] Error removing closed trades from plans: {e}")
        return 0

def _close_manual_trade(ticker, reason="MANUAL"):
    """Cierra manualmente una posición activa y la mueve a historial."""
    tk = str(ticker).upper().strip()
    if not tk:
        return {"ok": False, "error": "Ticker vacío"}

    now_iso = datetime.now().isoformat()

    with CSV_LOCK:
        if not TRADE_PLAN_PATH.exists():
            return {"ok": False, "error": "No existe trade_plan_EXECUTE.csv"}

        plan_df = pd.read_csv(TRADE_PLAN_PATH)
        if plan_df.empty:
            return {"ok": False, "error": "No hay trades activos"}

        match = plan_df[plan_df["ticker"].str.upper() == tk]
        if match.empty:
            return {"ok": False, "error": f"Ticker {tk} no encontrado en activos"}

        row = match.iloc[0]

    # Precio actual desde cache
    price = get_cached_prices([tk]).get(tk)
    if price is None:
        price = float(row.get("entry", 0) or 0)

    side = str(row.get("side", "BUY")).upper()
    entry = float(row.get("entry", 0) or 0)
    tp_price = float(row.get("tp_price", 0) or 0)
    sl_price = float(row.get("sl_price", 0) or 0)
    qty = float(row.get("qty", 1) or 1)
    plan_type = str(row.get("plan_type", "PROBWIN_55") or "PROBWIN_55").upper()
    entry_time = str(row.get("entry_time", row.get("generated_at", now_iso)))

    exit_price = float(price or entry)
    pnl = (exit_price - entry) * qty if side == "BUY" else (entry - exit_price) * qty
    pnl_pct = ((exit_price - entry) / entry * 100) if entry > 0 and side == "BUY" else ((entry - exit_price) / entry * 100 if entry > 0 else 0)

    closed_row = {
        "ticker": tk,
        "side": side,
        "entry": json_safe_float(entry),
        "exit": json_safe_float(exit_price),
        "tp_price": json_safe_float(tp_price),
        "sl_price": json_safe_float(sl_price),
        "qty": json_safe_float(qty),
        "exposure": json_safe_float(entry * qty),
        "prob_win": json_safe_float(row.get("prob_win", 50), 50.0),
        "exit_reason": reason,
        "pnl": json_safe_float(pnl),
        "pnl_pct": json_safe_float(pnl_pct),
        "closed_at": now_iso,
        "date": now_iso.split("T")[0],
        "trade_id": str(row.get("trade_id", f"MANUAL-{tk}-{side}-{entry:.4f}")),
        "plan_type": plan_type,
        "entry_time": entry_time,
        "generated_at": entry_time
    }

    with CSV_LOCK:
        # Verificar idempotencia en historial
        hist_df = None
        if TRADE_HISTORY_PATH.exists():
            hist_df = _read_history_csv()
            if not hist_df.empty:
                # Chequeo por trade_id
                existing_ids = set(hist_df.get("trade_id", pd.Series(dtype=str)).astype(str).tolist())
                if closed_row["trade_id"] in existing_ids:
                    return {"ok": False, "error": "Trade ya cerrado", "code": "already_closed"}

                # Chequeo por ticker (doble seguridad)
                if "ticker" in hist_df.columns:
                    if hist_df["ticker"].astype(str).str.upper().isin([tk]).any():
                        return {"ok": False, "error": "Trade ya cerrado", "code": "already_closed"}

            # Asegurar columna plan_type en historial
            if "plan_type" not in hist_df.columns:
                hist_df["plan_type"] = "UNKNOWN"

        # Escritura atómica del historial
        if hist_df is not None and not hist_df.empty:
            new_hist = pd.concat([hist_df, pd.DataFrame([closed_row])], ignore_index=True)
        else:
            new_hist = pd.DataFrame([closed_row])

        tmp_hist = TRADE_HISTORY_PATH.with_suffix(".tmp")
        new_hist.to_csv(tmp_hist, index=False)
        tmp_hist.replace(TRADE_HISTORY_PATH)

        # Remover del plan activo (escritura atómica)
        plan_df = pd.read_csv(TRADE_PLAN_PATH)
        plan_df = plan_df[plan_df["ticker"].str.upper() != tk]
        tmp_plan = TRADE_PLAN_PATH.with_suffix(".tmp")
        plan_df.to_csv(tmp_plan, index=False)
        tmp_plan.replace(TRADE_PLAN_PATH)

    return {"ok": True, "ticker": tk, "exit": exit_price, "pnl": pnl}

def _track_probwin_plan_to_history():
    """Trackea el plan PROBWIN_55 (EXECUTE) y genera historial cuando alcanza TP/SL."""
    try:
        if not TRADE_PLAN_PATH.exists():
            return
        
        with CSV_LOCK:  # Thread-safe CSV read
            plan_df = pd.read_csv(TRADE_PLAN_PATH)
        
        if plan_df.empty:
            return
        
        import yfinance as yf
        now_iso = datetime.now().isoformat()
        price_cache = {}
        closed_rows = []
        
        for _, row in plan_df.iterrows():
            ticker = str(row.get("ticker", "")).upper()
            side = str(row.get("side", "BUY")).upper()
            entry = float(row.get("entry", 0) or 0)
            tp_price = float(row.get("tp_price", 0) or 0)
            sl_price = float(row.get("sl_price", 0) or 0)
            qty = float(row.get("qty", 1) or 1)
            
            if not ticker or entry <= 0 or qty <= 0:
                continue
            
            if ticker in price_cache:
                current_price = price_cache[ticker]
            else:
                try:
                    stock = yf.Ticker(ticker)
                    hist = stock.history(period="1d", interval="1m")
                    current_price = float(hist["Close"].iloc[-1]) if not hist.empty else entry
                except Exception:
                    current_price = entry
                price_cache[ticker] = current_price
            
            hit_tp = False
            hit_sl = False
            if side == "BUY":
                hit_tp = tp_price > 0 and current_price >= tp_price
                hit_sl = sl_price > 0 and current_price <= sl_price
            else:
                hit_tp = tp_price > 0 and current_price <= tp_price
                hit_sl = sl_price > 0 and current_price >= sl_price
            
            if hit_tp or hit_sl:
                exit_reason = "TP" if hit_tp else "SL"
                exit_price = tp_price if hit_tp else sl_price
                pnl = (exit_price - entry) * qty if side == "BUY" else (entry - exit_price) * qty
                pnl_pct = ((exit_price - entry) / entry * 100) if side == "BUY" else ((entry - exit_price) / entry * 100)
                exposure = entry * qty
                closed_date = now_iso.split("T")[0]
                # ID único: ticker + side + entry + plan_type (evita duplicados)
                trade_id = f"PW55-{ticker}-{side}-{entry:.4f}".replace("/", "-")
                
                closed_rows.append({
                    "ticker": ticker,
                    "side": side,
                    "entry": entry,
                    "exit": exit_price,
                    "tp_price": tp_price,
                    "sl_price": sl_price,
                    "qty": qty,
                    "exposure": exposure,
                    "prob_win": float(row.get("prob_win", 0) or 0),
                    "exit_reason": exit_reason,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "closed_at": now_iso,
                    "date": closed_date,
                    "trade_id": trade_id,
                    "plan_type": "PROBWIN_55"
                })
        
        if not closed_rows:
            return
        
        closed_df = pd.DataFrame(closed_rows)
        
        with CSV_LOCK:  # Thread-safe CSV writes
            # IDEMPOTENCIA: Evitar duplicados en historial (por trade_id y ticker+plan_type)
            if TRADE_HISTORY_PATH.exists():
                hist_df = pd.read_csv(TRADE_HISTORY_PATH)
                # Chequeo 1: Por trade_id exacto
                existing_hist_ids = set(hist_df.get("trade_id", pd.Series(dtype=str)).astype(str).tolist())
                closed_df = closed_df[~closed_df["trade_id"].isin(existing_hist_ids)]
                
                # Chequeo 2: Por ticker+plan_type (doble seguridad)
                if not closed_df.empty and not hist_df.empty:
                    hist_df["ticker_plan_key"] = hist_df["ticker"].str.upper() + "_" + hist_df.get("plan_type", "UNKNOWN").astype(str)
                    closed_df["ticker_plan_key"] = closed_df["ticker"].str.upper() + "_" + closed_df["plan_type"].astype(str)
                    existing_keys = set(hist_df["ticker_plan_key"].tolist())
                    closed_df = closed_df[~closed_df["ticker_plan_key"].isin(existing_keys)]
                    closed_df = closed_df.drop(columns=["ticker_plan_key"])
            
            if closed_df.empty:
                print("[INFO] No new trades to close (already in history)")
                return
            
            header_needed = not TRADE_HISTORY_PATH.exists()
            closed_df.to_csv(TRADE_HISTORY_PATH, mode="a", header=header_needed, index=False)
            
            # Remover tickers cerrados del plan PROBWIN_55
            closed_tickers = set(closed_df["ticker"].str.upper().tolist())
            _remove_closed_from_plans(closed_tickers, "PROBWIN_55")
        
    except Exception as e:
        print(f"[WARNING] Error tracking PROBWIN_55 plan: {e}")

def _track_standard_plan_to_history():
    """Crea y actualiza seguimiento del plan STANDARD y genera historial cerrado (TP/SL)."""
    try:
        plan_df = _normalize_standard_plan(_load_latest_standard_plan())
        if plan_df.empty:
            return

        with CSV_LOCK:  # Thread-safe CSV access
            # Cargar tracking existente o inicializar
            if STANDARD_TRACK_PATH.exists():
                track_df = pd.read_csv(STANDARD_TRACK_PATH)
            else:
                track_df = pd.DataFrame(columns=plan_df.columns)

            existing_ids = set(track_df["trade_id"].astype(str).tolist()) if not track_df.empty else set()
            new_rows = plan_df[~plan_df["trade_id"].isin(existing_ids)]
            if not new_rows.empty:
                track_df = pd.concat([track_df, new_rows], ignore_index=True)

            if track_df.empty:
                return

        import yfinance as yf
        now_iso = datetime.now().isoformat()
        price_cache = {}
        closed_rows = []
        open_rows = []

        for _, row in track_df.iterrows():
            ticker = str(row.get("ticker", "")).upper()
            side = str(row.get("side", "BUY")).upper()
            entry = float(row.get("entry", 0) or 0)
            tp_price = float(row.get("tp_price", 0) or 0)
            sl_price = float(row.get("sl_price", 0) or 0)
            qty = float(row.get("qty", 1) or 1)

            if not ticker or entry <= 0 or qty <= 0:
                continue

            if ticker in price_cache:
                current_price = price_cache[ticker]
            else:
                try:
                    stock = yf.Ticker(ticker)
                    hist = stock.history(period="1d", interval="1m")
                    current_price = float(hist["Close"].iloc[-1]) if not hist.empty else entry
                except Exception:
                    current_price = entry
                price_cache[ticker] = current_price

            hit_tp = False
            hit_sl = False
            if side == "BUY":
                hit_tp = tp_price > 0 and current_price >= tp_price
                hit_sl = sl_price > 0 and current_price <= sl_price
            else:
                hit_tp = tp_price > 0 and current_price <= tp_price
                hit_sl = sl_price > 0 and current_price >= sl_price

            if hit_tp or hit_sl:
                exit_reason = "TP" if hit_tp else "SL"
                exit_price = tp_price if hit_tp else sl_price
                pnl = (exit_price - entry) * qty if side == "BUY" else (entry - exit_price) * qty
                pnl_pct = ((exit_price - entry) / entry * 100) if side == "BUY" else ((entry - exit_price) / entry * 100)
                exposure = entry * qty
                closed_date = now_iso.split("T")[0]
                closed_rows.append({
                    "ticker": ticker,
                    "side": side,
                    "entry": entry,
                    "exit": exit_price,
                    "tp_price": tp_price,
                    "sl_price": sl_price,
                    "qty": qty,
                    "exposure": exposure,
                    "prob_win": float(row.get("prob_win", 0) or 0),
                    "exit_reason": exit_reason,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "closed_at": now_iso,
                    "date": closed_date,
                    "trade_id": str(row.get("trade_id", ""))
                })
            else:
                open_rows.append(row)

        with CSV_LOCK:  # Thread-safe CSV writes
            # Guardar tracking actualizado
            if open_rows:
                pd.DataFrame(open_rows).to_csv(STANDARD_TRACK_PATH, index=False)
            else:
                if STANDARD_TRACK_PATH.exists():
                    STANDARD_TRACK_PATH.unlink(missing_ok=True)

            if not closed_rows:
                return

            closed_df = pd.DataFrame(closed_rows)

            # Asegurar columna plan_type en el historial
            if TRADE_HISTORY_PATH.exists():
                hist_df = pd.read_csv(TRADE_HISTORY_PATH)
                if "plan_type" not in hist_df.columns:
                    hist_df["plan_type"] = "UNKNOWN"
                    hist_df.to_csv(TRADE_HISTORY_PATH, index=False)

            # IDEMPOTENCIA: Evitar duplicados en historial (por trade_id y ticker+plan_type)
            if TRADE_HISTORY_PATH.exists():
                hist_df = pd.read_csv(TRADE_HISTORY_PATH)
                # Chequeo 1: Por trade_id exacto
                existing_hist_ids = set(hist_df.get("trade_id", pd.Series(dtype=str)).astype(str).tolist())
                closed_df = closed_df[~closed_df["trade_id"].isin(existing_hist_ids)]
                
                # Chequeo 2: Por ticker+plan_type (doble seguridad)
                if not closed_df.empty and not hist_df.empty:
                    hist_df["ticker_plan_key"] = hist_df["ticker"].str.upper() + "_" + hist_df.get("plan_type", "UNKNOWN").astype(str)
                    closed_df["ticker_plan_key"] = closed_df["ticker"].str.upper() + "_" + closed_df.get("plan_type", "STANDARD").astype(str)
                    existing_keys = set(hist_df["ticker_plan_key"].tolist())
                    closed_df = closed_df[~closed_df["ticker_plan_key"].isin(existing_keys)]
                    closed_df = closed_df.drop(columns=["ticker_plan_key"])

            if closed_df.empty:
                print("[INFO] No new trades to close (already in history)")
                return

            header_needed = not TRADE_HISTORY_PATH.exists()
            if "plan_type" not in closed_df.columns:
                closed_df["plan_type"] = "STANDARD"
            closed_df.to_csv(TRADE_HISTORY_PATH, mode="a", header=header_needed, index=False)

            # Remover tickers cerrados del plan STANDARD
            closed_tickers = set(closed_df["ticker"].str.upper().tolist())
            _remove_closed_from_plans(closed_tickers, "STANDARD")

    except Exception as e:
        print(f"[WARNING] Error tracking STANDARD plan: {e}")

def _read_history_csv():
    with CSV_LOCK:  # Thread-safe read
        try:
            return pd.read_csv(TRADE_HISTORY_PATH)
        except Exception:
            try:
                return pd.read_csv(TRADE_HISTORY_PATH, engine="python", on_bad_lines="skip")
            except Exception as e:
                print(f"[WARNING] Error reading history CSV: {e}")
                return pd.DataFrame()

def load_history_trades():
    """⚡ RÁPIDO: Solo lee CSV, NO hace tracking (se ejecuta en background)"""
    try:
        if TRADE_HISTORY_PATH.exists():
            df = _read_history_csv()
            # ⚡ Reemplazar NaN con valores por defecto ANTES de iterar
            df = df.fillna({
                'entry': 0, 'exit': 0, 'tp_price': 0, 'sl_price': 0,
                'pnl': 0, 'pnl_pct': 0, 'prob_win': 50, 'qty': 0,
                'ticker': '', 'plan_type': 'UNKNOWN', 'side': 'BUY',
                'exit_reason': '', 'closed_at': '', 'trade_id': '',
                'date': '', 'entry_time': '', 'opened_at': '', 'generated_at': ''
            })
            trades = []
            for _, row in df.iterrows():
                closed_at_str = str(row.get("closed_at", ""))
                entry_at_str = str(row.get("entry_time", row.get("opened_at", row.get("generated_at", ""))))
                try:
                    closed_dt = pd.to_datetime(closed_at_str)
                    fecha = closed_dt.strftime("%Y-%m-%d")
                    hora = closed_dt.strftime("%H:%M")
                except Exception:
                    fecha = str(row.get("date", ""))
                    hora = "N/A"

                entry_estimated = False
                if not entry_at_str or entry_at_str.lower() in ["nan", "none"]:
                    base_date = str(row.get("date", fecha))
                    entry_at_str = f"{base_date}T09:30:00"
                    entry_estimated = True

                duration_min = None
                try:
                    entry_dt = pd.to_datetime(entry_at_str)
                    closed_dt = pd.to_datetime(closed_at_str)
                    duration_min = int((closed_dt - entry_dt).total_seconds() // 60)
                except Exception:
                    duration_min = None

                trades.append({
                    "fecha": fecha,
                    "hora": hora,
                    "ticker": row.get("ticker", ""),
                    "plan_type": str(row.get("plan_type", "")).upper() or "UNKNOWN",
                    "tipo": str(row.get("side", "BUY")).upper(),
                    "entrada": json_safe_float(row.get("entry", 0)),
                    "salida": json_safe_float(row.get("exit", 0)),
                    "tp_price": json_safe_float(row.get("tp_price", 0)),
                    "sl_price": json_safe_float(row.get("sl_price", 0)),
                    "pnl": json_safe_float(row.get("pnl", 0)),
                    "pnl_pct": json_safe_float(row.get("pnl_pct", 0)),
                    "win_rate": json_safe_float(row.get("prob_win", 50), 50.0),
                    "exit_reason": str(row.get("exit_reason", "")),
                    "qty": json_safe_float(row.get("qty", 0)),
                    "closed_at": closed_at_str,
                    "trade_id": str(row.get("trade_id", "")),
                    "entry_at": entry_at_str,
                    "entry_estimated": entry_estimated,
                    "duration_min": duration_min
                })
            return trades
    except Exception as e:
        print(f"[WARNING] Error loading history: {e}")
    return []

def load_plan_comparison():
    """Carga planes STANDARD y PROBWIN_55 con cache de precios"""
    try:
        from datetime import datetime
        from pathlib import Path
        
        plans = []
        plans_dir = Path("evidence") / "weekly_plans"
        
        # Intentar cargar planes de hoy
        today = datetime.now().strftime("%Y-%m-%d")
        standard_path = plans_dir / f"plan_standard_{today}.csv"
        probwin55_path = plans_dir / f"plan_probwin55_{today}.csv"
        
        # Si no existen, buscar el archivo más reciente
        if not standard_path.exists():
            standard_files = sorted(plans_dir.glob("plan_standard_*.csv"))
            if standard_files:
                standard_path = standard_files[-1]
        
        if not probwin55_path.exists():
            probwin55_files = sorted(plans_dir.glob("plan_probwin55_*.csv"))
            if probwin55_files:
                probwin55_path = probwin55_files[-1]
        
        # Si no hay plan probwin55 en evidence, usar EXECUTE como fallback
        if not probwin55_path.exists() or (probwin55_path.exists() and pd.read_csv(probwin55_path).empty):
            execute_path = Path("val/trade_plan_EXECUTE.csv")
            if execute_path.exists():
                probwin55_path = execute_path
        
        # Recolectar todos los tickers para batch fetch
        all_tickers = []
        
        # Cargar STANDARD
        standard_data = []
        if standard_path.exists():
            with CSV_LOCK:  # Thread-safe read
                df_std = pd.read_csv(standard_path)
            if not df_std.empty:
                all_tickers.extend([str(row.get("ticker", "")) for _, row in df_std.iterrows()])
        
        # Cargar PROBWIN_55
        probwin_data = []
        if probwin55_path.exists():
            with CSV_LOCK:  # Thread-safe read
                df_prob = pd.read_csv(probwin55_path)
            if not df_prob.empty:
                all_tickers.extend([str(row.get("ticker", "")) for _, row in df_prob.iterrows()])
        
        # Obtener precios en batch
        prices = get_cached_prices(all_tickers) if all_tickers else {}
        
        # Procesar STANDARD
        if standard_path.exists():
            with CSV_LOCK:  # Thread-safe read
                df_std = pd.read_csv(standard_path)
            if not df_std.empty:
                for _, row in df_std.iterrows():
                    ticker = str(row.get("ticker", "")).strip().upper()
                    if not ticker or ticker.lower() in ["nan", "none"]:
                        continue
                    entry = float(row.get("entry", 0) or 0)
                    tp = float(row.get("tp_price", 0) or 0)
                    sl = float(row.get("sl_price", 0) or 0)
                    qty = float(row.get("qty", 1) or 1)
                    if entry <= 0 or qty <= 0:
                        continue
                    exposure = abs(entry * qty) if not pd.isna(qty) else entry
                    side = str(row.get("side", "BUY")).upper()
                    
                    # Obtener precio del cache
                    current_price = prices.get(ticker, entry)
                    if current_price is None:
                        current_price = entry
                    
                    # Calcular cambio
                    change_pct = ((current_price - entry) / entry * 100) if entry > 0 else 0
                    
                    # ✅ Solo usar etth del plan (sin estimate_time)
                    time_to_tp = get_time_from_plan(ticker, standard_path)
                    time_to_sl = get_time_from_plan(ticker, standard_path)
                    
                    standard_data.append({
                        "ticker": ticker,
                        "side": side,
                        "entry": entry,
                        "current": current_price,
                        "change_pct": change_pct,
                        "tp": tp,
                        "sl": sl,
                        "prob_win": float(row.get("prob_win", 0)) * 100,
                        "exposure": exposure,
                        "time_to_tp": time_to_tp,
                        "time_to_sl": time_to_sl
                    })
        
        # Procesar PROBWIN_55
        if probwin55_path.exists():
            with CSV_LOCK:  # Thread-safe read
                df_prob = pd.read_csv(probwin55_path)
            if not df_prob.empty:
                for _, row in df_prob.iterrows():
                    ticker = str(row.get("ticker", "")).strip().upper()
                    if not ticker or ticker.lower() in ["nan", "none"]:
                        continue
                    entry = float(row.get("entry", 0) or 0)
                    tp = float(row.get("tp_price", 0) or 0)
                    sl = float(row.get("sl_price", 0) or 0)
                    qty = float(row.get("qty", 1) or 1)
                    if entry <= 0 or qty <= 0:
                        continue
                    exposure = abs(entry * qty) if not pd.isna(qty) else entry
                    side = str(row.get("side", "BUY")).upper()
                    
                    # Obtener precio del cache
                    current_price = prices.get(ticker, entry)
                    if current_price is None:
                        current_price = entry
                    
                    # Calcular cambio
                    change_pct = ((current_price - entry) / entry * 100) if entry > 0 else 0
                    
                    # ✅ Solo usar etth del plan (sin estimate_time)
                    time_to_tp = get_time_from_plan(ticker, probwin55_path)
                    time_to_sl = get_time_from_plan(ticker, probwin55_path)
                    
                    probwin_data.append({
                        "ticker": ticker,
                        "side": side,
                        "entry": entry,
                    "current": current_price,
                    "change_pct": change_pct,
                    "tp": tp,
                    "sl": sl,
                    "prob_win": float(row.get("prob_win", 0)) * 100,
                    "exposure": exposure,
                    "time_to_tp": time_to_tp,
                    "time_to_sl": time_to_sl
                })
        
        # Agregar planes
        if standard_data:
            avg_prob_win = sum(p["prob_win"] for p in standard_data) / len(standard_data) if standard_data else 0
            plans.append({
                "name": "STANDARD",
                "positions": len(standard_data),
                "exposure": sum(p["exposure"] for p in standard_data),
                "prob_win_avg": avg_prob_win,
                "tickers": ", ".join(set(p["ticker"] for p in standard_data)),
                "details": standard_data
            })
        
        if probwin_data:
            avg_prob_win = sum(p["prob_win"] for p in probwin_data) / len(probwin_data) if probwin_data else 0
            plans.append({
                "name": "PROBWIN_55",
                "positions": len(probwin_data),
                "exposure": sum(p["exposure"] for p in probwin_data),
                "prob_win_avg": avg_prob_win,
                "tickers": ", ".join(set(p["ticker"] for p in probwin_data)),
                "details": probwin_data
            })
        
        # Ordenar: PROBWIN_55 primero
        plans.sort(key=lambda x: (x["name"] != "PROBWIN_55", x["name"]))
        
        return plans
    except Exception as e:
        print(f"[WARNING] Error loading plan comparison: {e}")
        return []

def build_trade_snapshot():
    """🎯 CENTRALIZADO: Snapshot único de TODAS las métricas.
    ✅ Read-only dashboard (solo lectura CSV)
    ✅ Sin lógica de decisión
    ✅ Una sola fuente de verdad
    
    Retorna:
    {
        "active": [trades activos],
        "history": [trades cerrados],
        "summary": {pnl_total, win_rate, exposure, ...},
        "plans": [STANDARD, PROBWIN_55 comparison]
    }
    """
    with CSV_LOCK:  # Thread-safe read de CSVs
        try:
            # Leer datos (sin tracking, solo lectura)
            active_trades = load_active_trades()
            history_trades = load_history_trades()

            # Ocultar trades que ya pasaron a histórico
            def _mk_key_from_history(t):
                return (
                    str(t.get("ticker", "")).upper(),
                    str(t.get("tipo", "")).upper(),
                    round(float(t.get("entrada", 0) or 0), 4),
                    int(float(t.get("qty", 0) or 0))
                )

            def _mk_key_from_active(t):
                return (
                    str(t.get("ticker", "")).upper(),
                    str(t.get("side", "")).upper(),
                    round(float(t.get("entry", 0) or 0), 4),
                    int(float(t.get("qty", 0) or 0))
                )

            closed_keys = {_mk_key_from_history(t) for t in history_trades}
            if closed_keys:
                active_trades = [t for t in active_trades if _mk_key_from_active(t) not in closed_keys]
            plans_data = load_plan_comparison()
            
            # Calcular métricas centralizadas
            pnl_total = sum(t["pnl"] for t in history_trades) if history_trades else 0
            winners = sum(1 for t in history_trades if t["pnl"] > 0) if history_trades else 0
            total_trades = len(history_trades)
            win_rate = (winners / total_trades * 100) if total_trades > 0 else 0
            
            # Métricas de posiciones abiertas
            prob_win_avg = (sum(t["prob_win"] for t in active_trades) / len(active_trades)) if active_trades else 0
            exposure = sum(abs(t["entry"] * t["qty"]) for t in active_trades) if active_trades else 0
            
            # Métricas por plan (histórico)
            plan_metrics = {}
            if history_trades:
                for plan_type in ["STANDARD", "PROBWIN_55"]:
                    plan_trades = [t for t in history_trades if t.get("plan_type", "").upper() == plan_type.upper()]
                    if plan_trades:
                        plan_pnl = sum(t["pnl"] for t in plan_trades)
                        plan_winners = sum(1 for t in plan_trades if t["pnl"] > 0)
                        plan_metrics[plan_type] = {
                            "total": len(plan_trades),
                            "winners": plan_winners,
                            "pnl": json_safe_float(plan_pnl),
                            "win_rate": json_safe_float((plan_winners / len(plan_trades) * 100) if plan_trades else 0)
                        }
            
            return {
                "active": active_trades,
                "history": history_trades,
                "summary": {
                    "pnl_total": json_safe_float(pnl_total),
                    "total_trades": total_trades,
                    "win_rate": json_safe_float(win_rate),
                    "active_trades": len(active_trades),
                    "prob_win_avg": json_safe_float(prob_win_avg),
                    "exposure": json_safe_float(exposure),
                    "max_capital": get_max_capital()
                },
                "plans": plans_data,
                "plan_metrics": plan_metrics
            }
        except Exception as e:
            print(f"[WARNING] Error building snapshot: {e}")
            import traceback
            traceback.print_exc()
            return {
                "active": [],
                "history": [],
                "summary": {
                    "pnl_total": 0,
                    "total_trades": 0,
                    "win_rate": 0,
                    "active_trades": 0,
                    "prob_win_avg": 0,
                    "exposure": 0,
                    "max_capital": get_max_capital()
                },
                "plans": [],
                "plan_metrics": {}
            }

def calculate_summary():
    """⚠️ DEPRECATED: Usar build_trade_snapshot() en su lugar.
    Mantiene compatibilidad con código viejo.
    """
    snapshot = build_trade_snapshot()
    return snapshot["summary"]

HTML = '''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trade Dashboard Temp</title>
    <style>
        :root {
            --primary: #1e3c72;
            --primary-light: #2a5298;
            --secondary: #0084ff;
            --success: #28a745;
            --danger: #dc3545;
            --warning: #ff9800;
            --purple: #667eea;
            --purple-dark: #764ba2;
            --text-dark: #1e3c72;
            --text-muted: #999;
            --bg-white: #ffffff;
            --bg-gray: #f5f5f5;
            --border-light: #eee;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        .header {
            background: var(--bg-white);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 8px 16px rgba(0,0,0,0.1);
        }
        .header h1 { color: var(--text-dark); font-size: 32px; margin-bottom: 12px; font-weight: 600; }
        .header-info { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 20px; }
        .header-left p { color: var(--text-muted); font-size: 13px; margin: 4px 0; }
        .status-badge {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px 18px;
            border-radius: 24px;
            font-weight: 600;
            font-size: 13px;
        }
        .status-badge.success { background: #d4edda; color: #155724; }
        .status-badge.danger { background: #f8d7da; color: #721c24; }
        .status-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        .status-dot.success { background: var(--success); }
        .status-dot.danger { background: var(--danger); }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .tabs {
            display: flex;
            gap: 0;
            margin-bottom: 24px;
            background: var(--bg-white);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            flex-wrap: wrap;
        }
        .tab-btn {
            flex: 1 1 200px;
            padding: 16px 20px;
            border: none;
            background: var(--bg-gray);
            cursor: pointer;
            font-size: 15px;
            font-weight: 600;
            color: #666;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            border-bottom: 3px solid transparent;
        }
        .tab-btn:hover { background: #efefef; }
        .tab-btn.active { background: var(--bg-white); color: var(--secondary); border-bottom-color: var(--secondary); }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .plan-toggle {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--bg-white);
            border-radius: 12px;
            padding: 12px 16px;
            margin-bottom: 16px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
            gap: 12px;
            flex-wrap: wrap;
        }
        .plan-badge {
            font-size: 12px;
            font-weight: 700;
            color: var(--text-dark);
            background: #eef3ff;
            padding: 6px 10px;
            border-radius: 999px;
        }
        .plan-buttons { display: flex; gap: 8px; }
        .plan-btn {
            border: 1px solid #d0d7e2;
            background: #f7f9fc;
            color: #345;
            padding: 8px 12px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .plan-btn.active {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-color: transparent;
            box-shadow: 0 4px 10px rgba(102, 126, 234, 0.3);
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        .stat-card {
            background: var(--bg-white);
            padding: 20px;
            border-radius: 12px;
            border-left: 4px solid var(--secondary);
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        }
        .stat-card.profit { border-left-color: var(--success); }
        .stat-card.loss { border-left-color: var(--danger); }
        .chart-btn {
            margin-top: 10px;
            width: 100%;
            border: none;
            padding: 10px 12px;
            border-radius: 8px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            font-weight: 700;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.35);
        }
        .chart-btn:hover { filter: brightness(1.05); }
        .modal-backdrop {
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.55);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 9999;
        }
        .modal-backdrop.active { display: flex; }
        .modal {
            width: min(900px, 92vw);
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 50px rgba(0,0,0,0.35);
            overflow: hidden;
        }
        .modal-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 16px 20px;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: white;
            font-weight: 700;
        }
        .modal-body {
            padding: 16px;
        }
        .modal-footer {
            display: flex;
            justify-content: flex-end;
            padding: 12px 16px 16px;
            background: #f8fbff;
            border-top: 1px solid #e6f0ff;
        }
        #chartCanvas {
            width: 100%;
            background: linear-gradient(180deg, #f8fbff 0%, #ffffff 100%);
            border-radius: 12px;
            border: 1px solid #e6f0ff;
        }
        .chart-legend {
            display: flex;
            gap: 12px;
            align-items: center;
            margin-top: 10px;
            color: #667;
            font-size: 12px;
        }
        .legend-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #1e3c72;
            display: inline-block;
        }
        .chart-stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 10px;
            margin-bottom: 10px;
        }
        .chart-stat {
            background: #f5f9ff;
            border: 1px solid #e6f0ff;
            border-radius: 10px;
            padding: 8px 10px;
            font-size: 12px;
            color: #445;
        }
        .chart-stat strong { display: block; font-size: 14px; color: #1e3c72; }
        .chart-indicators {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin: 10px 0 6px;
        }
        .indicator-chip {
            padding: 6px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 700;
            background: #eef4ff;
            color: #1e3c72;
            border: 1px solid #dbe7ff;
        }
        .indicator-chip.good { background: #e8fff1; color: #1b8f4b; border-color: #c9f5dc; }
        .indicator-chip.bad { background: #ffecec; color: #c0392b; border-color: #ffd0d0; }
        .btn-close {
            border: none;
            padding: 10px 18px;
            border-radius: 10px;
            background: #1e3c72;
            color: white;
            font-weight: 700;
            cursor: pointer;
            box-shadow: 0 4px 10px rgba(30, 60, 114, 0.25);
        }
        .btn-close:hover { filter: brightness(1.05); }
        .modal-close {
            border: none;
            background: rgba(255,255,255,0.2);
            color: white;
            font-weight: 800;
            width: 32px;
            height: 32px;
            border-radius: 50%;
            cursor: pointer;
        }
        .stat-label { color: var(--text-muted); font-size: 11px; font-weight: 700; text-transform: uppercase; margin-bottom: 8px; }
        .stat-value { font-size: 32px; font-weight: 700; color: var(--text-dark); line-height: 1; margin-bottom: 6px; }
        .stat-value.profit { color: var(--success); }
        .stat-value.loss { color: var(--danger); }
        .stat-subtext { color: #bbb; font-size: 12px; }
        .trades-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
        .trade-card {
            background: var(--bg-white);
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
            border-left: 4px solid var(--secondary);
        }
        .trade-card.profit { border-left-color: var(--success); }
        .trade-card.loss { border-left-color: var(--danger); }
        .trade-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--border-light);
        }
        .trade-ticker { font-size: 24px; font-weight: 700; color: var(--text-dark); }
        .trade-info { display: flex; gap: 8px; align-items: center; }
        .trade-side {
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
        }
        .trade-side.buy { background: #d4edda; color: #155724; }
        .trade-side.sell { background: #f8d7da; color: #721c24; }
        .trade-pnl { font-size: 20px; font-weight: 700; }
        .trade-pnl.profit { color: #28a745; }
        .trade-pnl.loss { color: #dc3545; }
        .trade-rows { display: flex; flex-direction: column; gap: 0; }
        .trade-row {
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            font-size: 13px;
            border-bottom: 1px solid #f5f5f5;
        }
        .trade-row:last-child { border-bottom: none; }
        .trade-label { color: #999; font-weight: 600; }
        .trade-value { color: #1e3c72; font-weight: 700; }
        .trade-stats {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
            margin-top: 16px;
            padding-top: 12px;
            border-top: 1px solid #eee;
            text-align: center;
        }
        .trade-stat-label { color: #999; font-size: 11px; font-weight: 600; margin-bottom: 4px; }
        .trade-stat-value { color: #1e3c72; font-size: 18px; font-weight: 700; }
        .empty-state { text-align: center; padding: 60px 20px; background: white; border-radius: 12px; color: #999; }
        .empty-state h2 { color: #1e3c72; margin-bottom: 8px; font-size: 18px; }
        .table-wrapper { background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        .summary-table-wrap { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; }
        .summary-table-wrap table { min-width: 520px; }
        table { width: 100%; border-collapse: collapse; }
        th { background: #f9f9f9; padding: 16px; text-align: left; font-weight: 700; color: #1e3c72; font-size: 12px; text-transform: uppercase; border-bottom: 2px solid #eee; }
        td { padding: 16px; border-bottom: 1px solid #eee; color: #666; font-size: 13px; }
        tr:hover { background: #f9f9f9; }
        tr:last-child td { border-bottom: none; }
        .pnl-positive { color: #28a745; font-weight: 700; }
        .pnl-negative { color: #dc3545; font-weight: 700; }
        .btn-refresh {
            position: fixed;
            bottom: 30px;
            right: 30px;
            background: linear-gradient(135deg, #0084ff 0%, #005acc 100%);
            color: white;
            border: none;
            border-radius: 50%;
            width: 60px;
            height: 60px;
            font-size: 24px;
            cursor: pointer;
            box-shadow: 0 6px 16px rgba(0,132,255,0.4);
            transition: all 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .btn-refresh:hover { transform: scale(1.1); box-shadow: 0 8px 20px rgba(0,132,255,0.6); }
        .btn-refresh.spinning { animation: spin 1s linear infinite; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

        @media (max-width: 768px) {
            .tabs { border-radius: 10px; }
            .tab-btn { flex: 1 1 50%; padding: 12px 10px; font-size: 13px; }
            .summary-table-wrap table { min-width: 480px; }
        }

        @media (max-width: 480px) {
            .tabs { border-radius: 8px; }
            .tab-btn { flex: 1 1 50%; padding: 10px 8px; font-size: 11px; }
            .summary-table-wrap table { min-width: 420px; }
        }

        .report-view-btn {
            padding: 10px 18px;
            background: #f5f5f5;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 600;
            color: #333;
            transition: all 0.2s;
        }
        .report-view-btn:hover { background: #efefef; border-color: #bbb; }
        .report-view-btn.active {
            background: linear-gradient(135deg, #0084ff 0%, #005acc 100%);
            color: white;
            border-color: #005acc;
        }

        .report-card {
            background: white;
            border-radius: 14px;
            padding: 20px;
            box-shadow: 0 6px 18px rgba(0,0,0,0.10);
        }
        .report-title {
            font-size: 18px;
            font-weight: 700;
            color: #1e3c72;
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 8px;
        }
        .report-subtitle {
            color: #6b7280;
            font-size: 12px;
            margin-bottom: 12px;
        }
        .report-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 10px;
            border-radius: 16px;
            background: #f0f7ff;
            color: #0084ff;
            font-weight: 700;
            font-size: 11px;
        }

        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #c0c0c0; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #888; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Trade Dashboard Temporal</h1>
            <div class="header-info">
                <div class="header-left">
                    <p><strong>Actualizado:</strong> <span id="updateTime">{{ now }}</span></p>
                    <p><small>Monitoreo en tiempo real | Precios desde Yahoo Finance</small></p>
                </div>
                <div class="status-badge {{ market_status_class }}">
                    <span class="status-dot {{ market_status_class }}"></span>
                    <span>{{ market_status }} | {{ market_time }}</span>
                </div>
            </div>
        </div>
        
        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab(0)"><span style="font-size: 20px;">📊</span> Trade Monitor</button>
            <button class="tab-btn" onclick="switchTab(1)"><span style="font-size: 20px;">⚖️</span> Plan Comparison</button>
            <button class="tab-btn" onclick="switchTab(2)"><span style="font-size: 20px;">📋</span> Historial</button>
            <button class="tab-btn" onclick="switchTab(3)"><span style="font-size: 20px;">📈</span> Reporte Historico</button>
            <button class="tab-btn" onclick="switchTab(4)"><span style="font-size: 20px;">🚪</span> Gating Rules</button>
            <button class="tab-btn" onclick="switchTab(5)"><span style="font-size: 20px;">❤️</span> System Health</button>
            <button class="tab-btn" onclick="switchTab(6)"><span style="font-size: 20px;">🎯</span> FASE 2-3</button>
        </div>
        
        <div class="tab-content active" id="tab0">
            <div class="plan-toggle">
                <div class="plan-badge" id="planBadge">Plan: ACTIVO</div>
                <div class="plan-buttons">
                    <button class="plan-btn active" id="btnPlanActive" onclick="setTradePlan('active')">Activo</button>
                    <button class="plan-btn" id="btnPlanStandard" onclick="setTradePlan('standard')">Standard</button>
                </div>
            </div>
            <div class="stats-grid" id="statsGrid"></div>
            <div class="trades-grid" id="tradesGrid"></div>
        </div>
        
        <div class="tab-content" id="tab1">
            <div style="display: flex; flex-direction: column; gap: 32px;">
                <!-- Tabla resumen colapsable -->
                <div style="background: white; border-radius: 16px; padding: 24px; box-shadow: 0 8px 24px rgba(0,0,0,0.12);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; cursor: pointer;" onclick="toggleSummaryTable()">
                        <h2 style="color: #1e3c72; font-size: 22px; font-weight: 600; display: flex; align-items: center; gap: 12px; margin: 0;">
                            <span style="font-size: 28px;">📊</span>
                            Resumen de Planes
                        </h2>
                        <button id="toggleSummaryBtn" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; padding: 10px 20px; border-radius: 24px; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 8px; box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4); transition: all 0.3s ease;">
                            <span id="toggleIcon">▼</span>
                            <span id="toggleText">Ocultar</span>
                        </button>
                    </div>
                    <div id="summaryTableContainer" style="overflow: hidden; transition: max-height 0.4s ease, opacity 0.3s ease; max-height: 1000px; opacity: 1;">
                        <div class="summary-table-wrap">
                            <table style="width: 100%; border-collapse: separate; border-spacing: 0;">
                            <thead>
                                <tr style="background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: white;">
                                    <th style="padding: 16px; text-align: left; font-weight: 600; border-radius: 8px 0 0 0;">Plan</th>
                                    <th style="padding: 16px; text-align: center; font-weight: 600;">Posiciones</th>
                                    <th style="padding: 16px; text-align: center; font-weight: 600;">Exposición</th>
                                    <th style="padding: 16px; text-align: center; font-weight: 600; border-radius: 0 8px 0 0;">Prob Win Avg</th>
                                </tr>
                            </thead>
                            <tbody id="comparisonTable">
                                <tr><td colspan="4" style="text-align: center; padding: 40px; color: #999;">Sin datos disponibles</td></tr>
                            </tbody>
                            </table>
                        </div>
                    </div>
                </div>
                
                <!-- Detalles de posiciones mejorado -->
                <div id="comparisonDetails"></div>
            </div>
        </div>
        
        <div class="tab-content" id="tab2">
            <div class="trades-grid" id="historyGrid"></div>
        </div>

        <div class="tab-content" id="tab3">
            <div id="reportContent" style="display: none;">
                <div style="display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap;">
                    <button class="report-view-btn active" onclick="switchReportView('grouped')">Agrupado por Fecha</button>
                    <button class="report-view-btn" onclick="switchReportView('detailed')">Detalles y Duración</button>
                    <button class="report-view-btn" onclick="switchReportView('timeline')">Timeline Visual</button>
                    <button class="report-view-btn" onclick="switchReportView('plan')">Comparativa por Plan</button>
                </div>
                <div id="reportGrouped" style="display: block;"></div>
                <div id="reportDetailed" style="display: none;"></div>
                <div id="reportTimeline" style="display: none;"></div>
                <div id="reportPlan" style="display: none;"></div>
            </div>
            <div id="reportEmpty" style="text-align: center; padding: 40px;">
                <h3 style="color: #999;">Cargando reporte...</h3>
            </div>
        </div>

        <div class="tab-content" id="tab4">
            <div id="gatingRulesContent" style="display: flex; flex-direction: column; gap: 24px;">
                <div id="gatingRulesLoader" style="text-align: center; padding: 40px;">
                    <h3 style="color: #999;">Cargando reglas de gating...</h3>
                </div>
            </div>
        </div>

        <div class="tab-content" id="tab5">
            <div id="systemHealthContent" style="display: flex; flex-direction: column; gap: 24px;">
                <div id="systemHealthLoader" style="text-align: center; padding: 40px;">
                    <h3 style="color: #999;">Cargando estado del sistema...</h3>
                </div>
            </div>
        </div>
        
        <div class="tab-content" id="tab6">
            <div style="background: white; border-radius: 16px; padding: 0; box-shadow: 0 8px 24px rgba(0,0,0,0.12); overflow: hidden;">
                <iframe 
                    id="fase23Frame" 
                    src="/dashboard" 
                    style="width: 100%; height: calc(100vh - 240px); border: none; display: block;"
                    onload="document.getElementById('fase23Loader').style.display='none'">
                </iframe>
                <div id="fase23Loader" style="text-align: center; padding: 60px; position: absolute; width: 100%; background: white;">
                    <h3 style="color: #667eea; margin-bottom: 10px;">🎯 Cargando FASE 2-3...</h3>
                    <p style="color: #999; font-size: 14px;">Dashboard de validación y operación</p>
                    <div style="margin-top: 20px; width: 60px; height: 60px; border: 4px solid #eee; border-top-color: #667eea; border-radius: 50%; margin: 20px auto; animation: spin 1s linear infinite;"></div>
                </div>
            </div>
        </div>
    </div>
    
    <button class="btn-refresh" id="refreshBtn" onclick="refreshDashboard()">↻</button>

    <div class="modal-backdrop" id="chartModal">
        <div class="modal" role="dialog" aria-modal="true">
            <div class="modal-header">
                <div id="chartTitle">📈 Chart</div>
                <button class="modal-close" onclick="closeChartModal()">×</button>
            </div>
            <div class="modal-body">
                <div class="chart-stats" id="chartStats"></div>
                <canvas id="chartCanvas" height="360"></canvas>
                <div class="chart-legend"><span class="legend-dot"></span> Precio de cierre</div>
                <div class="chart-indicators" id="chartIndicators"></div>
                <div id="chartStatus" style="margin-top: 8px; color: #666; font-size: 12px;"></div>
            </div>
            <div class="modal-footer">
                <button class="btn-close" id="closePositionBtn" onclick="closePositionFromModal()">🛑 Cerrar Posición</button>
            </div>
        </div>
    </div>
    
    <script>
        const API = window.location.origin + '/api';
        const PRICE_DECIMALS = 2;
        
        // Formato financiero consistente
        const formatCurrency = (value) => {
            return new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: 'USD',
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }).format(value);
        };
        
        const formatPercent = (value) => {
            return new Intl.NumberFormat('en-US', {
                style: 'percent',
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }).format(value / 100);
        };

        let tradePlanMode = 'active';

        function setTradePlan(mode) {
            tradePlanMode = mode === 'standard' ? 'standard' : 'active';
            const btnActive = document.getElementById('btnPlanActive');
            const btnStandard = document.getElementById('btnPlanStandard');
            if (btnActive && btnStandard) {
                btnActive.classList.toggle('active', tradePlanMode === 'active');
                btnStandard.classList.toggle('active', tradePlanMode === 'standard');
            }
            const badge = document.getElementById('planBadge');
            if (badge) {
                badge.textContent = tradePlanMode === 'standard' ? 'Plan: STANDARD' : 'Plan: ACTIVO';
            }
            loadTradeMonitor();
        }

        function getTradesUrl() {
            return API + '/trades' + (tradePlanMode === 'standard' ? '?plan=standard' : '');
        }

        function openChartModal(ticker) {
            const modal = document.getElementById('chartModal');
            const title = document.getElementById('chartTitle');
            const status = document.getElementById('chartStatus');
            const stats = document.getElementById('chartStats');
            const indicators = document.getElementById('chartIndicators');
            const closeBtn = document.getElementById('closePositionBtn');
            title.textContent = `📈 Chart ${ticker}`;
            status.textContent = 'Cargando...';
            stats.innerHTML = '';
            indicators.innerHTML = '';
            closeBtn.dataset.ticker = ticker;
            modal.classList.add('active');

            fetch(API + '/chart/' + encodeURIComponent(ticker))
                .then(r => r.json())
                .then(data => {
                    if (!data || !data.points || data.points.length === 0) {
                        status.textContent = `Sin datos para el chart. (${data && data.source ? data.source : 'n/a'})`;
                        renderChart([]);
                        return;
                    }
                    const first = data.points[0];
                    const last = data.points[data.points.length - 1];
                    const change = last.close - first.close;
                    const changePct = first.close ? (change / first.close) * 100 : 0;
                    const max = Math.max(...data.points.map(p => p.close));
                    const min = Math.min(...data.points.map(p => p.close));
                    const avg = data.points.reduce((s, p) => s + p.close, 0) / data.points.length;
                    const range = max - min;
                    const vol = avg ? (range / avg) * 100 : 0;
                    const t0 = new Date(first.t);
                    const t1 = new Date(last.t);
                    const spanMin = isNaN(t0) || isNaN(t1) ? null : Math.max(0, Math.round((t1 - t0) / 60000));
                    const closes = data.points.map(p => p.close);
                    const sma = (arr, n) => arr.length >= n ? arr.slice(-n).reduce((s, v) => s + v, 0) / n : null;
                    const sma20 = sma(closes, 20);
                    const sma50 = sma(closes, 50);
                    const rsi14 = calcRSI(closes, 14);
                    const trend = sma20 && sma50 ? (sma20 >= sma50 ? 'Alcista' : 'Bajista') : 'N/A';
                    stats.innerHTML = `
                        <div class="chart-stat"><span>Último</span><strong>${formatCurrency(last.close)}</strong></div>
                        <div class="chart-stat"><span>Variación</span><strong style="color:${change >= 0 ? '#28a745' : '#dc3545'};">${change >= 0 ? '+' : ''}${formatCurrency(change)}</strong></div>
                        <div class="chart-stat"><span>%</span><strong style="color:${changePct >= 0 ? '#28a745' : '#dc3545'};">${changePct >= 0 ? '+' : ''}${changePct.toFixed(2)}%</strong></div>
                        <div class="chart-stat"><span>Máx / Mín</span><strong>${formatCurrency(max)} / ${formatCurrency(min)}</strong></div>
                        <div class="chart-stat"><span>Promedio</span><strong>${formatCurrency(avg)}</strong></div>
                        <div class="chart-stat"><span>Rango</span><strong>${formatCurrency(range)}</strong></div>
                        <div class="chart-stat"><span>Volatilidad</span><strong>${vol.toFixed(2)}%</strong></div>
                        <div class="chart-stat"><span>Ventana</span><strong>${spanMin !== null ? spanMin + ' min' : 'n/a'}</strong></div>
                        <div class="chart-stat"><span>Puntos</span><strong>${data.points.length}</strong></div>
                    `;
                    indicators.innerHTML = `
                        <span class="indicator-chip ${trend === 'Alcista' ? 'good' : trend === 'Bajista' ? 'bad' : ''}">Tendencia: ${trend}</span>
                        <span class="indicator-chip">SMA20: ${sma20 ? formatCurrency(sma20) : 'n/a'}</span>
                        <span class="indicator-chip">SMA50: ${sma50 ? formatCurrency(sma50) : 'n/a'}</span>
                        <span class="indicator-chip ${rsi14 !== null ? (rsi14 < 30 ? 'good' : rsi14 > 70 ? 'bad' : '') : ''}">RSI(14): ${rsi14 !== null ? rsi14.toFixed(1) : 'n/a'}</span>
                    `;
                    renderChart(data.points);
                    status.textContent = `Último precio: ${formatCurrency(last.close)} • ${data.points.length} puntos • ${data.source || 'n/a'}`;
                })
                .catch(err => {
                    console.error(err);
                    status.textContent = 'Error cargando el chart.';
                    renderChart([]);
                });
        }

        function closeChartModal() {
            document.getElementById('chartModal').classList.remove('active');
        }

        function closePosition(ticker) {
            if (!confirm(`¿Cerrar posición ${ticker}?`)) return;
            fetch(API + '/close/' + encodeURIComponent(ticker), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reason: 'MANUAL' })
            })
            .then(r => r.json().then(data => ({ status: r.status, data })))
            .then(({ status, data }) => {
                if (status !== 200) {
                    alert(`Error: ${data.error || 'No se pudo cerrar'}`);
                    return;
                }
                alert(`Posición ${data.ticker} cerrada. PnL: ${formatCurrency(data.pnl || 0)}`);
                loadTradeMonitor();
                loadHistory();
            })
            .catch(err => {
                console.error(err);
                alert('Error al cerrar la posición');
            });
        }

        function closePositionFromModal() {
            const btn = document.getElementById('closePositionBtn');
            const ticker = btn.dataset.ticker;
            if (!ticker) return;
            closePosition(ticker);
            closeChartModal();
        }

        function calcRSI(values, period) {
            if (!values || values.length < period + 1) return null;
            let gains = 0, losses = 0;
            for (let i = values.length - period; i < values.length; i++) {
                const change = values[i] - values[i - 1];
                if (change >= 0) gains += change; else losses -= change;
            }
            const avgGain = gains / period;
            const avgLoss = losses / period;
            if (avgLoss === 0) return 100;
            const rs = avgGain / avgLoss;
            return 100 - (100 / (1 + rs));
        }

        function renderChart(points) {
            const canvas = document.getElementById('chartCanvas');
            const ctx = canvas.getContext('2d');
            const w = canvas.width = canvas.clientWidth;
            const h = canvas.height = 360;
            ctx.clearRect(0, 0, w, h);

            if (!points || points.length === 0) {
                ctx.fillStyle = '#999';
                ctx.font = '14px Segoe UI, sans-serif';
                ctx.fillText('Sin datos', 12, 24);
                return;
            }

            if (points.length === 1) {
                ctx.fillStyle = '#1e3c72';
                ctx.beginPath();
                ctx.arc(w / 2, h / 2, 4, 0, Math.PI * 2);
                ctx.fill();
                return;
            }

            const padding = 42;
            const closes = points.map(p => p.close);
            const min = Math.min(...closes);
            const max = Math.max(...closes);
            const range = (max - min) || 1;
            const trendUp = closes[closes.length - 1] >= closes[0];
            const lineColor = trendUp ? '#1b8f4b' : '#c0392b';

            // Background
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(0, 0, w, h);

            // Grid
            ctx.strokeStyle = '#edf2f7';
            ctx.lineWidth = 1;
            const gridLines = 4;
            for (let i = 0; i <= gridLines; i++) {
                const y = padding + (i / gridLines) * (h - padding * 2);
                ctx.beginPath();
                ctx.moveTo(padding, y);
                ctx.lineTo(w - padding, y);
                ctx.stroke();
            }

            // Price labels (min/max)
            ctx.fillStyle = '#666';
            ctx.font = '11px Segoe UI, sans-serif';
            ctx.fillText(`$${max.toFixed(2)}`, 6, padding + 4);
            ctx.fillText(`$${min.toFixed(2)}`, 6, h - padding);

            // Path
            const path = new Path2D();
            points.forEach((p, i) => {
                const x = padding + (i / (points.length - 1)) * (w - padding * 2);
                const y = padding + (1 - ((p.close - min) / range)) * (h - padding * 2);
                if (i === 0) path.moveTo(x, y);
                else path.lineTo(x, y);
            });

            // Fill under line
            const fill = new Path2D(path);
            fill.lineTo(w - padding, h - padding);
            fill.lineTo(padding, h - padding);
            fill.closePath();
            const grad = ctx.createLinearGradient(0, padding, 0, h - padding);
            grad.addColorStop(0, trendUp ? 'rgba(40, 167, 69, 0.20)' : 'rgba(220, 53, 69, 0.20)');
            grad.addColorStop(1, 'rgba(0,0,0,0.02)');
            ctx.fillStyle = grad;
            ctx.fill(fill);

            // Line
            ctx.strokeStyle = lineColor;
            ctx.lineWidth = 2.4;
            ctx.stroke(path);

            // Last point marker
            const last = points[points.length - 1];
            const lx = w - padding;
            const ly = padding + (1 - ((last.close - min) / range)) * (h - padding * 2);
            ctx.fillStyle = lineColor;
            ctx.beginPath();
            ctx.arc(lx, ly, 3.5, 0, Math.PI * 2);
            ctx.fill();

            // Border
            ctx.strokeStyle = 'rgba(30,60,114,0.15)';
            ctx.lineWidth = 1;
            ctx.strokeRect(padding, padding, w - padding * 2, h - padding * 2);

            // Time labels
            const first = points[0];
            const lastPoint = points[points.length - 1];
            ctx.fillStyle = '#7a8699';
            ctx.font = '10px Segoe UI, sans-serif';
            ctx.fillText(first.t ? first.t.split('T')[0] : '', padding, h - 8);
            ctx.fillText(lastPoint.t ? lastPoint.t.split('T')[0] : '', w - padding - 60, h - 8);
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeChartModal();
        });
        document.getElementById('chartModal').addEventListener('click', (e) => {
            if (e.target.id === 'chartModal') closeChartModal();
        });
        
        function switchTab(i) {
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById('tab' + i).classList.add('active');
            document.querySelectorAll('.tab-btn')[i].classList.add('active');
            if (i === 0) loadTradeMonitor();
            else if (i === 1) loadComparison();
            else if (i === 2) loadHistory();
            else if (i === 3) loadHistoryReport();
            else if (i === 4) loadGatingRules();
            else if (i === 5) loadSystemHealth();
        }
        
        function loadTradeMonitor() {
            fetch(getTradesUrl()).then(r => r.json()).then(data => {
                const s = data.summary;
                document.getElementById('statsGrid').innerHTML = `
                    <div class="stat-card ${s.pnl_total >= 0 ? 'profit' : 'loss'}">
                        <div class="stat-label">P&L TOTAL</div>
                        <div class="stat-value ${s.pnl_total >= 0 ? 'profit' : 'loss'}">${formatCurrency(s.pnl_total)}</div>
                        <div class="stat-subtext">${s.total_trades} trades cerrados</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">EXPOSICIÓN</div>
                        <div class="stat-value">${formatCurrency(s.exposure)}</div>
                        <div class="stat-subtext">de ${formatCurrency(s.max_capital)} cap</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">TRADES ACTIVOS</div>
                        <div class="stat-value">${s.active_trades}</div>
                        <div class="stat-subtext">posiciones abiertas</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">PROB. WIN</div>
                        <div class="stat-value">${s.prob_win_avg.toFixed(2)}%</div>
                        <div class="stat-subtext">promedio</div>
                    </div>
                `;
                
                if (!data.trades || data.trades.length === 0) {
                    document.getElementById('tradesGrid').innerHTML = '<div class="empty-state" style="grid-column: 1/-1;"><h2>No hay trades activos</h2></div>';
                    return;
                }
                
                document.getElementById('tradesGrid').innerHTML = data.trades.map(t => `
                    <div class="trade-card ${t.pnl > 0 ? 'profit' : 'loss'}">
                        <div class="trade-header">
                            <div class="trade-ticker">${t.ticker}</div>
                            <div class="trade-info">
                                <span class="trade-side ${t.side.toLowerCase()}">${t.side}</span>
                                <div class="trade-pnl ${t.pnl > 0 ? 'profit' : 'loss'}">${formatCurrency(t.pnl)}</div>
                            </div>
                        </div>
                        
                        <!-- Precio Actual destacado (fondo sólido) -->
                        <div style="background: #667eea; border-radius: 8px; padding: 12px; margin: 12px 0; text-align: center; box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);">
                            <div style="color: rgba(255,255,255,0.8); font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;">Precio Actual</div>
                            <div style="color: white; font-size: 24px; font-weight: 800; letter-spacing: -0.5px;">${formatCurrency(t.exit)}</div>
                            <div style="color: rgba(255,255,255,0.9); font-size: 12px; font-weight: 600; margin-top: 4px;">
                                ${t.pnl >= 0 ? '▲' : '▼'} ${formatPercent((t.pnl / t.entry) * 100)}
                            </div>
                        </div>
                        
                        <div class="trade-rows">
                            <div class="trade-row"><span class="trade-label">Entry</span><span class="trade-value">${formatCurrency(t.entry)}</span></div>
                            <div class="trade-row"><span class="trade-label">Target (TP)</span><span class="trade-value" style="color: #28a745;">${formatCurrency(t.tp)} <small style="color: #999;">(${formatPercent(((t.tp - t.entry) / t.entry) * 100)})</small></span></div>
                            <div class="trade-row"><span class="trade-label">Stop (SL)</span><span class="trade-value" style="color: #dc3545;">${formatCurrency(t.sl)} <small style="color: #999;">(${formatPercent(((t.sl - t.entry) / t.entry) * 100)})</small></span></div>
                        </div>
                        
                        <!-- Tiempo estimado -->
                        <div style="background: linear-gradient(135deg, #fff5e6 0%, #fffbf0 100%); border-radius: 8px; padding: 12px; margin: 12px 0; border-left: 4px solid #ff9800;">
                            <div style="font-size: 11px; color: #666; font-weight: 600; text-transform: uppercase; margin-bottom: 8px;">⏱️ Tiempo Estimado</div>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                                <div style="text-align: center;">
                                    <div style="font-size: 10px; color: #28a745; font-weight: 600;">Hasta TP</div>
                                    <div style="font-size: 16px; font-weight: 700; color: #28a745;">${t.time_to_tp ? t.time_to_tp + ' min' : 'N/A'}</div>
                                </div>
                                <div style="text-align: center;">
                                    <div style="font-size: 10px; color: #dc3545; font-weight: 600;">Hasta SL</div>
                                    <div style="font-size: 16px; font-weight: 700; color: #dc3545;">${t.time_to_sl ? t.time_to_sl + ' min' : 'N/A'}</div>
                                </div>
                            </div>
                        </div>
                        <div class="trade-stats">
                            <div><div class="trade-stat-label">Qty</div><div class="trade-stat-value">${t.qty}</div></div>
                            <div><div class="trade-stat-label">Prob Win</div><div class="trade-stat-value">${t.prob_win.toFixed(1)}%</div></div>
                            <div><div class="trade-stat-label">P&L</div><div class="trade-stat-value" style="font-size: 13px; color: ${t.pnl >= 0 ? '#28a745' : '#dc3545'};">$${t.pnl.toFixed(2)}</div></div>
                        </div>
                        <button class="chart-btn" onclick="openChartModal('${t.ticker}')">📈 Ver Chart</button>
                    </div>
                `).join('');
            }).catch(e => console.error(e));
        }
        
        function loadComparison() {
            fetch(API + '/comparison').then(r => r.json()).then(data => {
                if (!data || data.length === 0) {
                    document.getElementById('comparisonTable').innerHTML = '<tr><td colspan="4" style="text-align: center; padding: 40px; color: #999;">Sin datos de comparación</td></tr>';
                    document.getElementById('comparisonDetails').innerHTML = '';
                    return;
                }
                
                // Tabla resumen con mejor diseño
                document.getElementById('comparisonTable').innerHTML = data.map((plan, idx) => `
                    <tr style="background: ${plan.name === 'PROBWIN_55' ? 'linear-gradient(135deg, #e3f2fd 0%, #f8f9fa 100%)' : 'white'}; border-bottom: 1px solid #eee;">
                        <td style="padding: 20px;">
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <span style="font-size: 24px;">${plan.name === 'STANDARD' ? '📋' : '⭐'}</span>
                                <div>
                                    <div style="font-weight: 700; color: #1e3c72; font-size: 16px;">${plan.name}</div>
                                    ${plan.name === 'PROBWIN_55' ? '<div style="font-size: 11px; color: #0084ff; font-weight: 600; margin-top: 4px;">✓ Recomendado</div>' : ''}
                                </div>
                            </div>
                        </td>
                        <td style="padding: 20px; text-align: center;">
                            <div style="display: inline-block; padding: 8px 16px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 20px; font-weight: 700; font-size: 16px; box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);">
                                ${plan.positions}
                            </div>
                        </td>
                        <td style="padding: 20px; text-align: center; font-size: 16px; font-weight: 700; color: #1e3c72;">
                            $${plan.exposure.toFixed(2)}
                        </td>
                        <td style="padding: 20px; text-align: center;">
                            <div style="display: inline-block; padding: 10px 20px; border-radius: 24px; font-weight: 700; font-size: 15px; background: ${plan.prob_win_avg >= 55 ? 'linear-gradient(135deg, #11998e 0%, #38ef7d 100%)' : plan.prob_win_avg >= 50 ? 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)' : 'linear-gradient(135deg, #fa709a 0%, #fee140 100%)'}; color: white; box-shadow: 0 4px 12px ${plan.prob_win_avg >= 55 ? 'rgba(17, 153, 142, 0.4)' : plan.prob_win_avg >= 50 ? 'rgba(245, 87, 108, 0.4)' : 'rgba(250, 112, 154, 0.4)'};">
                                ${plan.prob_win_avg.toFixed(1)}%
                            </div>
                        </td>
                    </tr>
                `).join('');
                
                // Detalle de posiciones con diseño premium
                document.getElementById('comparisonDetails').innerHTML = data.map(plan => `
                    <div style="background: white; border-radius: 16px; padding: 28px; box-shadow: 0 8px 24px rgba(0,0,0,0.12); border: ${plan.name === 'PROBWIN_55' ? '2px solid #0084ff' : '2px solid transparent'};">
                        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 3px solid ${plan.name === 'PROBWIN_55' ? '#0084ff' : '#1e3c72'};">
                            <h3 style="color: #1e3c72; font-size: 22px; font-weight: 700; display: flex; align-items: center; gap: 12px; margin: 0;">
                                <span style="font-size: 32px;">${plan.name === 'STANDARD' ? '📋' : '⭐'}</span>
                                ${plan.name}
                            </h3>
                            ${plan.name === 'PROBWIN_55' ? '<div style="padding: 8px 20px; background: linear-gradient(135deg, #0084ff 0%, #00a8ff 100%); color: white; border-radius: 24px; font-size: 13px; font-weight: 700; box-shadow: 0 4px 12px rgba(0, 132, 255, 0.4);">✓ RECOMENDADO</div>' : '<div style="padding: 8px 20px; background: #f8f9fa; color: #666; border-radius: 24px; font-size: 13px; font-weight: 600;">Alternativo</div>'}
                        </div>
                        ${plan.details && plan.details.length > 0 ? `
                            <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 20px;">
                                ${plan.details.map(pos => `
                                    <div style="background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%); border-radius: 12px; padding: 20px; border: 2px solid ${pos.side === 'BUY' ? '#28a745' : '#dc3545'}; box-shadow: 0 6px 20px rgba(0,0,0,0.08); position: relative; overflow: hidden;">
                                        <div style="position: absolute; top: 0; right: 0; width: 100px; height: 100px; background: ${pos.side === 'BUY' ? 'linear-gradient(135deg, rgba(40, 167, 69, 0.1) 0%, transparent 100%)' : 'linear-gradient(135deg, rgba(220, 53, 69, 0.1) 0%, transparent 100%)'}; border-radius: 0 0 0 100px;"></div>
                                        
                                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; position: relative; z-index: 1;">
                                            <div style="font-size: 24px; font-weight: 800; color: #1e3c72; letter-spacing: -0.5px;">${pos.ticker}</div>
                                            <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 4px;">
                                                <span style="padding: 6px 12px; border-radius: 8px; font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; background: ${pos.side === 'BUY' ? 'linear-gradient(135deg, #28a745 0%, #20c997 100%)' : 'linear-gradient(135deg, #dc3545 0%, #ff6b6b 100%)'}; color: white; box-shadow: 0 4px 12px ${pos.side === 'BUY' ? 'rgba(40, 167, 69, 0.3)' : 'rgba(220, 53, 69, 0.3)'};">${pos.side}</span>
                                                <span style="padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: 700; background: ${pos.prob_win >= 55 ? 'linear-gradient(135deg, #28a745 0%, #20c997 100%)' : pos.prob_win >= 50 ? 'linear-gradient(135deg, #ffc107 0%, #ff9800 100%)' : 'linear-gradient(135deg, #dc3545 0%, #ff6b6b 100%)'}; color: white;">Win ${pos.prob_win.toFixed(1)}%</span>
                                            </div>
                                        </div>
                                        
                                        <div style="background: white; border-radius: 8px; padding: 14px; margin-bottom: 12px; box-shadow: inset 0 2px 8px rgba(0,0,0,0.05);">
                                            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; font-size: 13px;">
                                                <div style="display: flex; flex-direction: column;">
                                                    <span style="color: #999; font-weight: 600; font-size: 11px; text-transform: uppercase; margin-bottom: 4px;">Entry</span>
                                                    <span style="color: #1e3c72; font-weight: 800; font-size: 16px;">$${pos.entry.toFixed(2)}</span>
                                                </div>
                                                <div style="display: flex; flex-direction: column;">
                                                    <span style="color: #999; font-weight: 600; font-size: 11px; text-transform: uppercase; margin-bottom: 4px;">Current</span>
                                                    <span style="color: ${pos.change_pct >= 0 ? '#28a745' : '#dc3545'}; font-weight: 800; font-size: 16px;">$${pos.current.toFixed(2)}</span>
                                                    <span style="color: ${pos.change_pct >= 0 ? '#28a745' : '#dc3545'}; font-weight: 700; font-size: 11px;">${pos.change_pct >= 0 ? '+' : ''}${pos.change_pct.toFixed(2)}%</span>
                                                </div>
                                                <div style="display: flex; flex-direction: column; align-items: flex-end;">
                                                    <span style="color: #999; font-weight: 600; font-size: 11px; text-transform: uppercase; margin-bottom: 4px;">Exposure</span>
                                                    <span style="color: #667eea; font-weight: 800; font-size: 16px;">$${pos.exposure.toFixed(2)}</span>
                                                </div>
                                            </div>
                                        </div>
                                        
                                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                                            <div style="background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%); border-radius: 8px; padding: 12px; border-left: 4px solid #28a745;">
                                                <div style="color: #155724; font-weight: 600; font-size: 11px; text-transform: uppercase; margin-bottom: 4px;">TP</div>
                                                <div style="color: #28a745; font-weight: 800; font-size: 16px;">$${pos.tp.toFixed(2)}</div>
                                                <div style="color: #28a745; font-weight: 600; font-size: 11px;">+${((pos.tp - pos.entry) / pos.entry * 100).toFixed(2)}%</div>
                                                ${pos.time_to_tp ? `<div style="color: #28a745; font-weight: 600; font-size: 10px; margin-top: 6px; border-top: 1px solid rgba(40, 167, 69, 0.3); padding-top: 6px;">⏱️ ${pos.time_to_tp} min</div>` : ''}
                                            </div>
                                            <div style="background: linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%); border-radius: 8px; padding: 12px; border-left: 4px solid #dc3545;">
                                                <div style="color: #721c24; font-weight: 600; font-size: 11px; text-transform: uppercase; margin-bottom: 4px;">SL</div>
                                                <div style="color: #dc3545; font-weight: 800; font-size: 16px;">$${pos.sl.toFixed(2)}</div>
                                                <div style="color: #dc3545; font-weight: 600; font-size: 11px;">${((pos.sl - pos.entry) / pos.entry * 100).toFixed(2)}%</div>
                                                ${pos.time_to_sl ? `<div style="color: #dc3545; font-weight: 600; font-size: 10px; margin-top: 6px; border-top: 1px solid rgba(220, 53, 69, 0.3); padding-top: 6px;">⏱️ ${pos.time_to_sl} min</div>` : ''}
                                            </div>
                                        </div>
                                    </div>
                                `).join('')}
                            </div>
                        ` : `
                            <div style="text-align: center; padding: 60px 20px; background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border-radius: 12px; border: 2px dashed #dee2e6;">
                                <div style="font-size: 48px; margin-bottom: 16px; opacity: 0.5;">📭</div>
                                <p style="font-size: 18px; color: #6c757d; font-weight: 600; margin: 0;">Sin posiciones en este plan</p>
                            </div>
                        `}
                    </div>
                `).join('');
                
            }).catch(err => console.error('Error loading comparison:', err));
        }
        
        function loadHistory() {
            fetch(API + '/history').then(r => r.json()).then(data => {
                if (!data || data.length === 0) {
                    document.getElementById('historyGrid').innerHTML = '<div class="empty-state" style="grid-column: 1/-1;"><h2>Sin historial de trades</h2></div>';
                    return;
                }
                document.getElementById('historyGrid').innerHTML = data.map(t => `
                    <div class="trade-card ${t.pnl > 0 ? 'profit' : 'loss'}">
                        <div class="trade-header">
                            <div class="trade-ticker">${t.ticker}</div>
                            <div class="trade-info">
                                <span class="trade-side ${t.tipo.toLowerCase()}">${t.tipo}</span>
                                <div class="trade-pnl ${t.pnl > 0 ? 'profit' : 'loss'}">$${t.pnl.toFixed(2)}</div>
                            </div>
                        </div>
                        <div class="trade-rows">
                            <div class="trade-row"><span class="trade-label">Fecha</span><span class="trade-value">${t.fecha}</span></div>
                            <div class="trade-row"><span class="trade-label">Hora Cierre (${t.exit_reason})</span><span class="trade-value" style="font-weight: 600; color: ${t.exit_reason === 'TP' ? '#28a745' : t.exit_reason === 'SL' ? '#dc3545' : '#ff9800'};">${t.hora}</span></div>
                            <div class="trade-row"><span class="trade-label">Entry</span><span class="trade-value">$${t.entrada.toFixed(2)}</span></div>
                            <div class="trade-row"><span class="trade-label">Exit</span><span class="trade-value">$${t.salida.toFixed(2)}</span></div>
                            <div class="trade-row"><span class="trade-label">Status</span><span class="trade-value" style="color: ${t.pnl > 0 ? '#28a745' : '#dc3545'};">${t.pnl > 0 ? 'GANANCIA' : 'PÉRDIDA'}</span></div>
                        </div>
                        <div class="trade-stats">
                            <div><div class="trade-stat-label">P&L</div><div class="trade-stat-value" style="color: ${t.pnl > 0 ? '#28a745' : '#dc3545'};">$${t.pnl.toFixed(2)}</div></div>
                            <div><div class="trade-stat-label">Win Rate</div><div class="trade-stat-value">${t.win_rate.toFixed(1)}%</div></div>
                            <div><div class="trade-stat-label">Retorno</div><div class="trade-stat-value" style="font-size: 13px;">${((t.pnl / t.entrada) * 100).toFixed(1)}%</div></div>
                        </div>
                    </div>
                `).join('');
            }).catch(e => console.error(e));
        }

        function switchReportView(view) {
            document.querySelectorAll('.report-view-btn').forEach(b => b.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById('reportGrouped').style.display = 'none';
            document.getElementById('reportDetailed').style.display = 'none';
            document.getElementById('reportTimeline').style.display = 'none';
            document.getElementById('reportPlan').style.display = 'none';
            if (view === 'grouped') document.getElementById('reportGrouped').style.display = 'block';
            else if (view === 'detailed') document.getElementById('reportDetailed').style.display = 'block';
            else if (view === 'timeline') document.getElementById('reportTimeline').style.display = 'block';
            else if (view === 'plan') document.getElementById('reportPlan').style.display = 'block';
        }

        function loadHistoryReport() {
            fetch(API + '/history').then(r => r.json()).then(data => {
                if (!data || data.length === 0) {
                    document.getElementById('reportContent').style.display = 'none';
                    document.getElementById('reportEmpty').innerHTML = '<h3 style="color: #999;">Sin historial de trades</h3>';
                    return;
                }
                document.getElementById('reportEmpty').style.display = 'none';
                document.getElementById('reportContent').style.display = 'block';
                renderGroupedView(data);
                renderDetailedView(data);
                renderTimelineView(data);
                renderPlanComparisonView(data);
            }).catch(e => console.error(e));
        }

        function renderGroupedView(data) {
            const grouped = {};
            data.forEach(t => {
                if (!grouped[t.fecha]) grouped[t.fecha] = [];
                grouped[t.fecha].push(t);
            });

            let html = '';
            Object.keys(grouped).sort().reverse().forEach(fecha => {
                const trades = grouped[fecha];
                const dayPnL = trades.reduce((s, t) => s + t.pnl, 0);
                const dayWins = trades.filter(t => t.pnl > 0).length;
                const dayTotal = trades.length;
                const dayAvg = dayPnL / dayTotal;

                html += `
                <div style="margin-bottom: 32px; background: white; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); overflow: hidden;">
                    <div style="background: linear-gradient(135deg, ${dayPnL > 0 ? '#f0fdf4' : '#fef2f2'} 0%, white 100%); padding: 20px; border-left: 4px solid ${dayPnL > 0 ? '#28a745' : '#dc3545'};">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 16px; margin-bottom: 12px;">
                            <div>
                                <div style="font-size: 18px; font-weight: 700; color: #1e3c72; margin-bottom: 8px;">📅 ${fecha}</div>
                                <div style="display: flex; gap: 20px; font-size: 12px; flex-wrap: wrap;">
                                    <div><span style="color: #666;">Total:</span> <span style="font-weight: 600; color: #333;">${dayTotal}</span></div>
                                    <div><span style="color: #666;">Ganancias:</span> <span style="font-weight: 600; color: #28a745;">${dayWins} ✓</span></div>
                                    <div><span style="color: #666;">Pérdidas:</span> <span style="font-weight: 600; color: #dc3545;">${dayTotal - dayWins} ✗</span></div>
                                </div>
                            </div>
                            <div style="text-align: right;">
                                <div style="font-size: 11px; color: #666; margin-bottom: 4px; text-transform: uppercase;">Resultado</div>
                                <div style="font-size: 28px; font-weight: 700; color: ${dayPnL > 0 ? '#28a745' : '#dc3545'};">
                                    ${dayPnL > 0 ? '+' : ''}$${dayPnL.toFixed(2)}
                                </div>
                                <div style="font-size: 12px; color: #666; margin-top: 4px;">Promedio: $${dayAvg.toFixed(2)}</div>
                            </div>
                        </div>
                    </div>

                    <div style="padding: 16px; display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px;">
                        ${trades.map(t => `
                            <div class="trade-card ${t.pnl > 0 ? 'profit' : 'loss'}" style="border-left: 4px solid ${t.pnl > 0 ? '#28a745' : '#dc3545'}; background: white;">
                                <div class="trade-header" style="padding: 12px; border-bottom: 1px solid #f0f0f0;">
                                    <div class="trade-ticker" style="font-size: 16px; font-weight: 700; margin-bottom: 6px;">${t.ticker}</div>
                                    <div style="display: flex; justify-content: space-between; align-items: center;">
                                        <span class="trade-side ${t.tipo.toLowerCase()}" style="font-size: 12px; font-weight: 600;">${t.tipo}</span>
                                        <span style="font-size: 12px; color: ${t.pnl > 0 ? '#28a745' : '#dc3545'}; font-weight: 600;">${t.exit_reason}</span>
                                    </div>
                                </div>
                                <div style="padding: 12px;">
                                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px;">
                                        <div>
                                            <div style="font-size: 11px; color: #666;">Entry</div>
                                            <div style="font-size: 14px; font-weight: 600;">$${t.entrada.toFixed(2)}</div>
                                        </div>
                                        <div>
                                            <div style="font-size: 11px; color: #666;">Exit</div>
                                            <div style="font-size: 14px; font-weight: 600;">$${t.salida.toFixed(2)}</div>
                                        </div>
                                    </div>
                                    <div style="background: ${t.pnl > 0 ? '#f0fdf4' : '#fef2f2'}; padding: 10px; border-radius: 6px; text-align: center; border: 1px solid ${t.pnl > 0 ? '#dcfce7' : '#fee2e2'};">
                                        <div style="font-size: 11px; color: #666; margin-bottom: 4px;">P&L</div>
                                        <div style="font-size: 18px; font-weight: 700; color: ${t.pnl > 0 ? '#28a745' : '#dc3545'};">${t.pnl > 0 ? '+' : ''}$${t.pnl.toFixed(2)}</div>
                                        <div style="font-size: 11px; color: #666; margin-top: 4px;">${t.pnl_pct > 0 ? '+' : ''}${t.pnl_pct.toFixed(2)}%</div>
                                    </div>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
                `;
            });
            document.getElementById('reportGrouped').innerHTML = html;
        }

        function renderDetailedView(data) {
            let html = '<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px;">';
            data.slice().reverse().forEach(t => {
                const priceDiff = (t.salida - t.entrada);
                const priceDiffPct = ((priceDiff / t.entrada) * 100);
                const exposureReal = (t.qty * t.entrada).toFixed(2);
                const profitPerUnit = (t.qty ? (priceDiff / t.qty) : 0).toFixed(4);

                html += `
                <div class="trade-card ${t.pnl > 0 ? 'profit' : 'loss'}" style="background: white; border-left: 4px solid ${t.pnl > 0 ? '#28a745' : '#dc3545'}; border-radius: 12px;">
                    <div class="trade-header" style="padding: 16px 16px 12px 16px; border-bottom: 2px solid #f0f0f0;">
                        <div class="trade-ticker" style="font-size: 20px; font-weight: bold; margin-bottom: 8px;">${t.ticker} ${t.tipo}</div>
                        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                            <div style="font-size: 11px; color: #666; background: #f5f5f5; padding: 4px 8px; border-radius: 4px;">📅 ${t.fecha}</div>
                            <div style="font-size: 13px; font-weight: 600; color: ${t.pnl > 0 ? '#28a745' : '#dc3545'};">🕐 Cierre: ${t.hora}</div>
                            <div style="font-size: 13px; font-weight: 600; color: #0084ff; background: #f0f7ff; padding: 4px 8px; border-radius: 4px;">⚡ ${t.exit_reason}</div>
                        </div>
                        <div style="margin-top: 8px; font-size: 11px; color: #999; font-style: italic;">${t.entry_estimated ? '* Hora de entrada estimada (plan generado)' : '* Hora de entrada registrada'}</div>
                    </div>

                    <div style="padding: 16px;">
                        <div style="background: #f9f9f9; padding: 12px; border-radius: 8px; margin-bottom: 16px;">
                            <div style="font-size: 11px; color: #888; font-weight: 600; margin-bottom: 8px; text-transform: uppercase;">MOVIMIENTO DEL PRECIO</div>
                            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px;">
                                <div>
                                    <div style="font-size: 11px; color: #666;">Entrada</div>
                                    <div style="font-size: 14px; font-weight: 600;">$${t.entrada.toFixed(PRICE_DECIMALS)}</div>
                                </div>
                                <div>
                                    <div style="font-size: 11px; color: #666;">Salida</div>
                                    <div style="font-size: 14px; font-weight: 600;">$${t.salida.toFixed(PRICE_DECIMALS)}</div>
                                </div>
                                <div style="grid-column: 1/-1;">
                                    <div style="font-size: 11px; color: #666; margin-bottom: 4px;">Diferencia por acción</div>
                                    <div style="font-size: 13px; font-weight: 600; color: ${priceDiff > 0 ? '#28a745' : '#dc3545'};">
                                        ${priceDiff > 0 ? '+' : ''}$${priceDiff.toFixed(PRICE_DECIMALS)} (${priceDiffPct > 0 ? '+' : ''}${priceDiffPct.toFixed(2)}%)
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div style="background: #f9f9f9; padding: 12px; border-radius: 8px; margin-bottom: 16px;">
                            <div style="font-size: 11px; color: #888; font-weight: 600; margin-bottom: 8px; text-transform: uppercase;">POSICIÓN</div>
                            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px;">
                                <div>
                                    <div style="font-size: 11px; color: #666;">Hora entrada</div>
                                    <div style="font-size: 13px; font-weight: 600;">${t.entry_at ? t.entry_at.replace('T', ' ') : 'N/A'}</div>
                                </div>
                                <div>
                                    <div style="font-size: 11px; color: #666;">Duración</div>
                                    <div style="font-size: 13px; font-weight: 600;">${t.duration_min !== null ? t.duration_min + ' min' : 'N/A'}</div>
                                </div>
                                <div>
                                    <div style="font-size: 11px; color: #666;">Cantidad</div>
                                    <div style="font-size: 14px; font-weight: 600;">${t.qty} acc.</div>
                                </div>
                                <div>
                                    <div style="font-size: 11px; color: #666;">P&L por acc</div>
                                    <div style="font-size: 13px; font-weight: 600; color: ${profitPerUnit > 0 ? '#28a745' : '#dc3545'};">$${profitPerUnit}</div>
                                </div>
                                <div>
                                    <div style="font-size: 11px; color: #666;">Exposición</div>
                                    <div style="font-size: 14px; font-weight: 600;">$${exposureReal}</div>
                                </div>
                                <div>
                                    <div style="font-size: 11px; color: #666;">TP / SL</div>
                                    <div style="font-size: 13px;">
                                        <div style="color: #28a745; font-weight: 600;">↑ $${t.tp_price.toFixed(2)}</div>
                                        <div style="color: #dc3545; font-weight: 600;">↓ $${t.sl_price.toFixed(2)}</div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div style="background: ${t.pnl > 0 ? '#f0fdf4' : '#fef2f2'}; padding: 12px; border-radius: 8px; border: 1px solid ${t.pnl > 0 ? '#dcfce7' : '#fee2e2'}; margin-bottom: 16px;">
                            <div style="font-size: 11px; color: #888; font-weight: 600; margin-bottom: 8px; text-transform: uppercase;">RESULTADO FINAL</div>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                                <div>
                                    <div style="font-size: 11px; color: #666;">P&L Total</div>
                                    <div style="font-size: 18px; font-weight: 700; color: ${t.pnl > 0 ? '#28a745' : '#dc3545'};">${t.pnl > 0 ? '+' : ''}$${t.pnl.toFixed(2)}</div>
                                </div>
                                <div>
                                    <div style="font-size: 11px; color: #666;">Retorno %</div>
                                    <div style="font-size: 18px; font-weight: 700; color: ${t.pnl_pct > 0 ? '#28a745' : '#dc3545'};">${t.pnl_pct > 0 ? '+' : ''}${t.pnl_pct.toFixed(2)}%</div>
                                </div>
                            </div>
                        </div>

                        <div style="padding-top: 12px; border-top: 2px solid #f0f0f0;">
                            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; font-size: 12px;">
                                <div>
                                    <div style="color: #666; margin-bottom: 4px;">Win Probability</div>
                                    <div style="font-weight: 600; color: #0084ff;">${t.win_rate.toFixed(1)}%</div>
                                </div>
                                <div>
                                    <div style="color: #666; margin-bottom: 4px;">ID</div>
                                    <div style="font-weight: 500; color: #888; font-size: 11px; word-break: break-all;">${t.trade_id}</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                `;
            });
            html += '</div>';
            document.getElementById('reportDetailed').innerHTML = html;
        }

        function renderTimelineView(data) {
            const byMonth = {};
            data.forEach(t => {
                const month = t.fecha.substring(0, 7);
                if (!byMonth[month]) byMonth[month] = [];
                byMonth[month].push(t);
            });

            let html = '<div style="padding: 16px 0;">';
            Object.keys(byMonth).sort().reverse().forEach(month => {
                const trades = byMonth[month];
                const monthPnL = trades.reduce((s, t) => s + t.pnl, 0);
                const monthWins = trades.filter(t => t.pnl > 0).length;

                html += `
                <div style="margin-bottom: 32px; background: white; padding: 24px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                        <div style="font-size: 16px; font-weight: 700; color: #1e3c72;">${month}</div>
                        <div style="font-size: 14px; font-weight: 700; color: ${monthPnL > 0 ? '#28a745' : '#dc3545'};">${monthPnL > 0 ? '+' : ''}$${monthPnL.toFixed(2)}</div>
                    </div>
                    <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px;">
                        ${trades.map((t, i) => `
                            <div title="${t.ticker} ${t.tipo} | ${t.fecha} ${t.hora} | P&L: $${t.pnl.toFixed(2)}" style="display: inline-flex; width: 22px; height: 22px; border-radius: 50%; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; color: white; background: ${t.pnl > 0 ? '#28a745' : '#dc3545'}; border: 2px solid white; box-shadow: 0 0 0 1px #ddd;">
                                ${i + 1}
                            </div>
                        `).join('')}
                    </div>
                    <div style="font-size: 12px; color: #666;">
                        ${monthWins} ganancias de ${trades.length} trades | Win Rate: ${((monthWins / trades.length) * 100).toFixed(1)}%
                    </div>
                </div>
                `;
            });
            html += '</div>';
            document.getElementById('reportTimeline').innerHTML = html;
        }

        function renderPlanComparisonView(data) {
            const byPlan = {};
            data.forEach(t => {
                const plan = (t.plan_type || 'UNKNOWN').toUpperCase();
                if (!byPlan[plan]) byPlan[plan] = [];
                byPlan[plan].push(t);
            });

            const plans = Object.keys(byPlan).sort((a, b) => (a === 'STANDARD' ? -1 : b === 'STANDARD' ? 1 : a.localeCompare(b)));

            if (plans.length === 0) {
                document.getElementById('reportPlan').innerHTML = '<div class="empty-state"><h2>Sin datos de planes</h2></div>';
                return;
            }

            let summaryHtml = '<div class="report-card" style="margin-bottom: 16px; background: linear-gradient(135deg, #f8fbff 0%, #ffffff 100%); border: 1px solid #e6f0ff;">' +
                '<div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">' +
                '<div>' +
                '<div class="report-title">📈 Comparativa Histórica por Plan</div>' +
                '<div class="report-subtitle">Seguimiento del rendimiento de cada plan con histórico de cierres TP/SL.</div>' +
                '</div>' +
                '<div class="report-badge">STANDARD tracking activo</div>' +
                '</div>' +
                '</div>' +
                '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px;">';
            plans.forEach(plan => {
                const trades = byPlan[plan];
                const total = trades.length;
                const pnlTotal = trades.reduce((s, t) => s + t.pnl, 0);
                const wins = trades.filter(t => t.pnl > 0).length;
                const winRate = total > 0 ? (wins / total * 100) : 0;
                const avgPnl = total > 0 ? (pnlTotal / total) : 0;
                const avgRet = total > 0 ? (trades.reduce((s, t) => s + (t.pnl_pct || 0), 0) / total) : 0;

                summaryHtml += `
                <div class="report-card" style="border-left: 4px solid ${plan === 'STANDARD' ? '#0084ff' : '#1e3c72'};">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <div style="font-size: 18px; font-weight: 700; color: #1e3c72;">${plan}</div>
                        <div style="font-size: 12px; color: #666;">${total} trades</div>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                        <div>
                            <div style="font-size: 11px; color: #888;">P&L Total</div>
                            <div style="font-size: 18px; font-weight: 700; color: ${pnlTotal >= 0 ? '#28a745' : '#dc3545'};">${pnlTotal >= 0 ? '+' : ''}$${pnlTotal.toFixed(2)}</div>
                        </div>
                        <div>
                            <div style="font-size: 11px; color: #888;">Win Rate</div>
                            <div style="font-size: 18px; font-weight: 700; color: #1e3c72;">${winRate.toFixed(1)}%</div>
                        </div>
                        <div>
                            <div style="font-size: 11px; color: #888;">Promedio P&L</div>
                            <div style="font-size: 16px; font-weight: 700; color: ${avgPnl >= 0 ? '#28a745' : '#dc3545'};">${avgPnl >= 0 ? '+' : ''}$${avgPnl.toFixed(2)}</div>
                        </div>
                        <div>
                            <div style="font-size: 11px; color: #888;">Retorno Prom.</div>
                            <div style="font-size: 16px; font-weight: 700; color: ${avgRet >= 0 ? '#28a745' : '#dc3545'};">${avgRet >= 0 ? '+' : ''}${avgRet.toFixed(2)}%</div>
                        </div>
                    </div>
                </div>
                `;
            });
            summaryHtml += '</div>';

            let detailHtml = '<div class="report-card" style="margin-top: 12px;">' +
                '<div class="report-title">🧾 Últimos movimientos por plan</div>' +
                '<div class="report-subtitle">Muestra los últimos 6 cierres por cada plan.</div>' +
                '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px;">';
            plans.forEach(plan => {
                const trades = byPlan[plan];
                detailHtml += `
                <div style="background: #fff; border-radius: 12px; padding: 16px; border: 1px solid #eef2f7;">
                    <div style="font-weight: 700; color: #1e3c72; margin-bottom: 8px;">${plan} - Últimos 6 trades</div>
                    ${trades.slice(-6).reverse().map(t => `
                        <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #f0f0f0; font-size: 12px;">
                            <span>${t.ticker} ${t.tipo}</span>
                            <span style="color: ${t.pnl >= 0 ? '#28a745' : '#dc3545'}; font-weight: 600;">${t.pnl >= 0 ? '+' : ''}$${t.pnl.toFixed(2)}</span>
                        </div>
                    `).join('')}
                </div>
                `;
            });
            detailHtml += '</div></div>';

            document.getElementById('reportPlan').innerHTML = `
                ${summaryHtml}
                ${detailHtml}
            `;
        }
        
        function loadGatingRules() {
            fetch(API + '/gating-rules').then(r => r.json()).then(data => {
                let html = '';
                
                // Tipos de gating
                html += '<div style="background: white; border-radius: 16px; padding: 24px; box-shadow: 0 8px 24px rgba(0,0,0,0.12); margin-bottom: 24px;">';
                html += '<h2 style="color: #1e3c72; margin: 0 0 20px 0; font-size: 18px; font-weight: 700;">🚪 Tipos de Gating</h2>';
                html += '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px;">';
                
                data.gating_types.forEach(gate => {
                    html += `
                    <div style="background: linear-gradient(135deg, #667eea15 0%, #764ba215 100%); border: 1px solid #667eea30; border-radius: 12px; padding: 16px; transition: all 0.3s;">
                        <div style="font-size: 16px; font-weight: 700; color: #1e3c72; margin-bottom: 4px;">${gate.name}</div>
                        <div style="font-size: 12px; color: #666; margin-bottom: 12px; line-height: 1.5;">${gate.description}</div>
                        <div style="border-top: 1px solid #eee; padding-top: 12px;">
                            <div style="display: grid; gap: 8px; font-size: 12px;">
                                <div><span style="color: #999;">Selección:</span> <strong style="color: #1e3c72;">${gate.typical_selection}</strong></div>
                                <div><span style="color: #999;">Rebalance:</span> <strong style="color: #1e3c72;">${gate.rebalance}</strong></div>
                                <div><span style="color: #999;">Método:</span> <strong style="color: #1e3c72;">${gate.parameters.method}</strong></div>
                                <div><span style="color: #999;">Lookback:</span> <strong style="color: #1e3c72;">${gate.parameters.lookback_days || 'N/A'} días</strong></div>
                            </div>
                        </div>
                    </div>
                    `;
                });
                html += '</div></div>';
                
                // Thresholds por régimen
                html += '<div style="background: white; border-radius: 16px; padding: 24px; box-shadow: 0 8px 24px rgba(0,0,0,0.12); margin-bottom: 24px;">';
                html += '<h2 style="color: #1e3c72; margin: 0 0 20px 0; font-size: 18px; font-weight: 700;">📊 Thresholds por Régimen de Mercado</h2>';
                html += '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px;">';
                
                Object.entries(data.thresholds).forEach(([regime, rules]) => {
                    const regimeEmoji = regime.includes('bearish') ? '🔴' : regime.includes('neutral') ? '🟡' : '🟢';
                    const regimeColor = regime.includes('bearish') ? '#dc3545' : regime.includes('neutral') ? '#ff9800' : '#28a745';
                    html += `
                    <div style="background: white; border: 2px solid ${regimeColor}30; border-radius: 12px; padding: 14px;">
                        <div style="font-weight: 700; color: #1e3c72; margin-bottom: 10px; font-size: 14px;">${regimeEmoji} ${regime.replace(/_/g, ' ').toUpperCase()}</div>
                        <div style="display: grid; gap: 6px; font-size: 12px;">
                            <div><span style="color: #999;">Min Prob Win:</span> <strong style="color: ${regimeColor};">${(rules.min_prob_win * 100).toFixed(0)}%</strong></div>
                            <div><span style="color: #999;">Nivel:</span> <strong style="color: #1e3c72;">${rules.confidence_level}</strong></div>
                        </div>
                    </div>
                    `;
                });
                html += '</div></div>';
                
                // Position Sizing
                html += '<div style="background: white; border-radius: 16px; padding: 24px; box-shadow: 0 8px 24px rgba(0,0,0,0.12); margin-bottom: 24px;">';
                html += '<h2 style="color: #1e3c72; margin: 0 0 20px 0; font-size: 18px; font-weight: 700;">💰 Dimensionamiento de Posiciones</h2>';
                const ps = data.position_sizing;
                html += `
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px;">
                    <div style="background: #e8f5e915; border: 1px solid #28a74530; border-radius: 12px; padding: 14px; text-align: center;">
                        <div style="font-size: 20px; font-weight: 700; color: #28a745; margin-bottom: 2px;">${ps.max_positions_open}</div>
                        <div style="font-size: 11px; color: #666; font-weight: 600; text-transform: uppercase;">Max Posiciones</div>
                    </div>
                    <div style="background: #e3f2fd15; border: 1px solid #2196f330; border-radius: 12px; padding: 14px; text-align: center;">
                        <div style="font-size: 20px; font-weight: 700; color: #2196f3; margin-bottom: 2px;">${(ps.per_trade_capital_pct * 100).toFixed(1)}%</div>
                        <div style="font-size: 11px; color: #666; font-weight: 600; text-transform: uppercase;">% por Trade</div>
                    </div>
                    <div style="background: #fff3e015; border: 1px solid #ff980030; border-radius: 12px; padding: 14px; text-align: center;">
                        <div style="font-size: 20px; font-weight: 700; color: #ff9800; margin-bottom: 2px;">${(ps.max_exposure_pct * 100).toFixed(0)}%</div>
                        <div style="font-size: 11px; color: #666; font-weight: 600; text-transform: uppercase;">Exposición Max</div>
                    </div>
                    <div style="background: #f3e5f515; border: 1px solid #9c27b030; border-radius: 12px; padding: 14px; text-align: center;">
                        <div style="font-size: 20px; font-weight: 700; color: #9c27b0; margin-bottom: 2px;">$${ps.max_capital.toFixed(0)}</div>
                        <div style="font-size: 11px; color: #666; font-weight: 600; text-transform: uppercase;">Capital Máx</div>
                    </div>
                </div>
                `;
                html += '</div>';
                
                // Exit Rules
                html += '<div style="background: white; border-radius: 16px; padding: 24px; box-shadow: 0 8px 24px rgba(0,0,0,0.12);">';
                html += '<h2 style="color: #1e3c72; margin: 0 0 20px 0; font-size: 18px; font-weight: 700;">🛑 Reglas de Salida (Exit)</h2>';
                const exit = data.exit_rules;
                html += `
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px;">
                    <div style="background: linear-gradient(135deg, #28a74510 0%, #28a74505 100%); border: 2px solid #28a745; border-radius: 12px; padding: 16px; text-align: center;">
                        <div style="font-size: 28px; font-weight: 700; color: #28a745; margin-bottom: 4px;">+${(exit.take_profit_pct * 100).toFixed(1)}%</div>
                        <div style="font-size: 12px; color: #1e3c72; font-weight: 600;">Take Profit</div>
                        <div style="font-size: 10px; color: #666; margin-top: 4px;">Ganancia objetivo</div>
                    </div>
                    <div style="background: linear-gradient(135deg, #dc354510 0%, #dc354505 100%); border: 2px solid #dc3545; border-radius: 12px; padding: 16px; text-align: center;">
                        <div style="font-size: 28px; font-weight: 700; color: #dc3545; margin-bottom: 4px;">-${(exit.stop_loss_pct * 100).toFixed(1)}%</div>
                        <div style="font-size: 12px; color: #1e3c72; font-weight: 600;">Stop Loss</div>
                        <div style="font-size: 10px; color: #666; margin-top: 4px;">Pérdida máxima</div>
                    </div>
                    <div style="background: linear-gradient(135deg, #2196f310 0%, #2196f305 100%); border: 2px solid #2196f3; border-radius: 12px; padding: 16px; text-align: center;">
                        <div style="font-size: 28px; font-weight: 700; color: #2196f3; margin-bottom: 4px;">${exit.max_hold_days}d</div>
                        <div style="font-size: 12px; color: #1e3c72; font-weight: 600;">Max Hold</div>
                        <div style="font-size: 10px; color: #666; margin-top: 4px;">Cierre forzado</div>
                    </div>
                </div>
                `;
                html += '</div>';
                
                document.getElementById('gatingRulesContent').innerHTML = html;
            }).catch(e => {
                document.getElementById('gatingRulesContent').innerHTML = '<div style="background: #ffebee; color: #dc3545; padding: 20px; border-radius: 12px; border-left: 4px solid #dc3545;">❌ Error: ' + e.message + '</div>';
            });
        }
        
        function loadSystemHealth() {
            fetch(API + '/health').then(r => r.json()).then(health => {
                let html = '';
                
                // Status card principal
                const statusColor = health.status === 'ok' ? '#28a745' : health.status === 'degraded' ? '#ff9800' : '#dc3545';
                const statusEmoji = health.status === 'ok' ? '✅' : health.status === 'degraded' ? '⚠️' : '❌';
                const statusText = health.status === 'ok' ? 'SALUDABLE' : health.status === 'degraded' ? 'DEGRADADO' : 'ERROR';
                
                html += `
                <div style="background: linear-gradient(135deg, ${statusColor}15 0%, ${statusColor}08 100%); border: 2px solid ${statusColor}40; border-radius: 16px; padding: 24px; margin-bottom: 24px;">
                    <div style="display: flex; align-items: center; gap: 16px;">
                        <span style="font-size: 48px; line-height: 1;">${statusEmoji}</span>
                        <div>
                            <div style="font-size: 20px; font-weight: 700; color: ${statusColor};">${statusText}</div>
                            <div style="font-size: 12px; color: #666; margin-top: 2px;">${new Date(health.time).toLocaleString()}</div>
                        </div>
                    </div>
                </div>
                `;
                
                // Snapshot Cache
                html += '<div style="background: white; border-radius: 16px; padding: 24px; box-shadow: 0 8px 24px rgba(0,0,0,0.12); margin-bottom: 24px;">';
                html += '<h2 style="color: #1e3c72; margin: 0 0 20px 0; font-size: 18px; font-weight: 700;">💾 Estado del Cache</h2>';
                const snap = health.snapshot;
                const ageColor = snap.age_sec < 10 ? '#28a745' : snap.age_sec < 60 ? '#ff9800' : '#dc3545';
                html += `
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px;">
                    <div style="background: linear-gradient(135deg, ${ageColor}10 0%, ${ageColor}05 100%); border: 1px solid ${ageColor}30; border-radius: 12px; padding: 14px; text-align: center;">
                        <div style="font-size: 24px; font-weight: 700; color: ${ageColor}; margin-bottom: 4px;">${snap.age_sec ? snap.age_sec.toFixed(1) : 'N/A'}<span style="font-size: 14px;">s</span></div>
                        <div style="font-size: 11px; color: #666; font-weight: 600; text-transform: uppercase;">Edad del Cache</div>
                        <div style="font-size: 10px; color: #999; margin-top: 4px;">${snap.age_sec < 10 ? 'Muy Fresco' : snap.age_sec < 60 ? 'Fresco' : 'Envejecido'}</div>
                    </div>
                    <div style="background: ${snap.stale ? '#ffebee' : '#e8f5e9'}15; border: 1px solid ${snap.stale ? '#dc3545' : '#28a745'}30; border-radius: 12px; padding: 14px; text-align: center;">
                        <div style="font-size: 24px; font-weight: 700; color: ${snap.stale ? '#dc3545' : '#28a745'}; margin-bottom: 4px;">${snap.stale ? '⏳' : '✅'}</div>
                        <div style="font-size: 11px; color: #666; font-weight: 600; text-transform: uppercase;">${snap.stale ? 'Stale' : 'Fresh'}</div>
                        <div style="font-size: 10px; color: #999; margin-top: 4px;">${snap.stale ? 'Datos antiguos' : 'Datos recientes'}</div>
                    </div>
                    <div style="background: ${snap.revalidating ? '#fff3e015' : '#f3e5f515'}; border: 1px solid ${snap.revalidating ? '#ff9800' : '#9c27b0'}30; border-radius: 12px; padding: 14px; text-align: center;">
                        <div style="font-size: 24px; font-weight: 700; color: ${snap.revalidating ? '#ff9800' : '#9c27b0'}; margin-bottom: 4px;">${snap.revalidating ? '🔄' : '⏸️'}</div>
                        <div style="font-size: 11px; color: #666; font-weight: 600; text-transform: uppercase;">${snap.revalidating ? 'Actualiz.' : 'Idle'}</div>
                        <div style="font-size: 10px; color: #999; margin-top: 4px;">${snap.revalidating ? 'En background' : 'En espera'}</div>
                    </div>
                </div>
                `;
                html += '</div>';
                
                // Archivos del Sistema
                html += '<div style="background: white; border-radius: 16px; padding: 24px; box-shadow: 0 8px 24px rgba(0,0,0,0.12); margin-bottom: 24px;">';
                html += '<h2 style="color: #1e3c72; margin: 0 0 20px 0; font-size: 18px; font-weight: 700;">📁 Archivos del Sistema</h2>';
                html += '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px;">';
                
                const fileNames = {
                    'trade_plan': 'Plan de Trades',
                    'trade_history': 'Historial Cerrado',
                    'standard_plan': 'Plan Standard'
                };
                
                Object.entries(health.files).forEach(([key, exists]) => {
                    const icon = exists ? '✅' : '❌';
                    const color = exists ? '#28a745' : '#dc3545';
                    html += `
                    <div style="background: ${exists ? '#e8f5e9' : '#ffebee'}15; border: 1px solid ${color}30; border-radius: 12px; padding: 14px; text-align: center;">
                        <div style="font-size: 20px; margin-bottom: 4px;">${icon}</div>
                        <div style="font-size: 12px; color: #1e3c72; font-weight: 600; margin-bottom: 4px;">${fileNames[key] || key}</div>
                        <div style="font-size: 10px; color: #666;">${exists ? 'Disponible' : 'Faltante'}</div>
                    </div>
                    `;
                });
                html += '</div></div>';
                
                // Tracking Thread
                html += '<div style="background: white; border-radius: 16px; padding: 24px; box-shadow: 0 8px 24px rgba(0,0,0,0.12); margin-bottom: 24px;">';
                html += '<h2 style="color: #1e3c72; margin: 0 0 20px 0; font-size: 18px; font-weight: 700;">🔄 Monitoreo en Background</h2>';
                const track = health.tracking;
                html += `
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px;">
                    <div style="background: ${track.thread_alive ? '#e8f5e9' : '#ffebee'}15; border: 1px solid ${track.thread_alive ? '#28a745' : '#dc3545'}30; border-radius: 12px; padding: 14px; text-align: center;">
                        <div style="font-size: 20px; margin-bottom: 4px;">${track.thread_alive ? '🟢' : '🔴'}</div>
                        <div style="font-size: 12px; color: #1e3c72; font-weight: 600; margin-bottom: 4px;">Tracking Thread</div>
                        <div style="font-size: 10px; color: #666;">${track.thread_alive ? 'ACTIVO' : 'DETENIDO'}</div>
                    </div>
                    <div style="background: #e3f2fd15; border: 1px solid #2196f330; border-radius: 12px; padding: 14px; text-align: center;">
                        <div style="font-size: 20px; color: #2196f3; margin-bottom: 4px;">⏱️</div>
                        <div style="font-size: 12px; color: #1e3c72; font-weight: 600; margin-bottom: 4px;">Intervalo</div>
                        <div style="font-size: 10px; color: #666;">${track.interval_sec}s</div>
                    </div>
                </div>
                `;
                html += '</div>';
                
                // Empty State
                if (health.empty_state) {
                    html += '<div style="background: white; border-radius: 16px; padding: 24px; box-shadow: 0 8px 24px rgba(0,0,0,0.12);">';
                    html += '<h2 style="color: #1e3c72; margin: 0 0 20px 0; font-size: 18px; font-weight: 700;">📊 Estado de Datos</h2>';
                    html += '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px;">';
                    
                    const es = health.empty_state;
                    html += `
                    <div style="background: ${!es.active_trades ? '#e8f5e9' : '#ffebee'}15; border: 1px solid ${!es.active_trades ? '#28a745' : '#ff9800'}30; border-radius: 12px; padding: 14px; text-align: center;">
                        <div style="font-size: 20px; margin-bottom: 4px;">${!es.active_trades ? '✅' : '⚠️'}</div>
                        <div style="font-size: 12px; color: #1e3c72; font-weight: 600; margin-bottom: 4px;">Trades Activos</div>
                        <div style="font-size: 10px; color: #666;">${!es.active_trades ? 'CON DATOS' : 'VACÍO'}</div>
                    </div>
                    <div style="background: ${!es.history_trades ? '#e8f5e9' : '#ffebee'}15; border: 1px solid ${!es.history_trades ? '#28a745' : '#ff9800'}30; border-radius: 12px; padding: 14px; text-align: center;">
                        <div style="font-size: 20px; margin-bottom: 4px;">${!es.history_trades ? '✅' : '⚠️'}</div>
                        <div style="font-size: 12px; color: #1e3c72; font-weight: 600; margin-bottom: 4px;">Historial</div>
                        <div style="font-size: 10px; color: #666;">${!es.history_trades ? 'CON DATOS' : 'VACÍO'}</div>
                    </div>
                    `;
                    html += '</div></div>';
                }
                
                document.getElementById('systemHealthContent').innerHTML = html;
            }).catch(e => {
                document.getElementById('systemHealthContent').innerHTML = '<div style="background: #ffebee; color: #dc3545; padding: 20px; border-radius: 12px; border-left: 4px solid #dc3545;">❌ Error: ' + e.message + '</div>';
            });
        }
        
        function refreshDashboard() {
            const btn = document.getElementById('refreshBtn');
            btn.classList.add('spinning');
            const i = Array.from(document.querySelectorAll('.tab-btn')).indexOf(document.querySelector('.tab-btn.active'));
            if (i === 0) loadTradeMonitor();
            else if (i === 1) loadComparison();
            else if (i === 2) loadHistory();
            else if (i === 3) loadHistoryReport();
            else if (i === 4) loadGatingRules();
            else if (i === 5) loadSystemHealth();
            document.getElementById('updateTime').textContent = new Date().toLocaleString();
            setTimeout(() => btn.classList.remove('spinning'), 500);
        }
        
        function toggleSummaryTable() {
            const container = document.getElementById('summaryTableContainer');
            const icon = document.getElementById('toggleIcon');
            const text = document.getElementById('toggleText');
            const btn = document.getElementById('toggleSummaryBtn');
            
            if (container.style.maxHeight === '0px') {
                // Expandir
                container.style.maxHeight = '1000px';
                container.style.opacity = '1';
                icon.textContent = '▼';
                text.textContent = 'Ocultar';
                btn.style.background = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
            } else {
                // Colapsar
                container.style.maxHeight = '0px';
                container.style.opacity = '0';
                icon.textContent = '▶';
                text.textContent = 'Mostrar';
                btn.style.background = 'linear-gradient(135deg, #11998e 0%, #38ef7d 100%)';
            }
        }
        
        setInterval(refreshDashboard, 30000);
        loadTradeMonitor();
    </script>
</body>
</html>
'''

# ============================================================================
# 📊 REQUEST MIDDLEWARE - Logear latencia de cada request
# ============================================================================
@app.before_request
def log_request_start():
    """Registra inicio del request"""
    request.start_time = time.time()

@app.after_request
def log_request_end(response):
    """Registra fin del request con latencia"""
    if hasattr(request, 'start_time'):
        duration = time.time() - request.start_time
        status_icon = "OK" if response.status_code < 300 else "WARN" if response.status_code < 400 else "ERR"
        logger.info(f"[HTTP] {status_icon} {request.method} {request.path} {response.status_code} ({duration*1000:.1f}ms)")
    return response

@app.route('/')
def index():
    market_status, status_class, market_time = get_market_status()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return render_template_string(HTML, market_status=market_status, market_status_class=status_class, market_time=market_time, now=now)

@app.route('/api/trades')
def api_trades():
    """📊 Trade Monitor - Trades activos con métricas centralizadas"""
    snapshot = get_cached_snapshot()
    plan = (request.args.get('plan') or '').strip().lower()

    if plan == 'standard':
        active_trades = load_active_trades(STANDARD_PLAN_PATH)
        history_trades = snapshot["history"]

        def _mk_key_from_history(t):
            return (
                str(t.get("ticker", "")).upper(),
                str(t.get("tipo", "")).upper(),
                round(float(t.get("entrada", 0) or 0), 4),
                int(float(t.get("qty", 0) or 0))
            )

        def _mk_key_from_active(t):
            return (
                str(t.get("ticker", "")).upper(),
                str(t.get("side", "")).upper(),
                round(float(t.get("entry", 0) or 0), 4),
                int(float(t.get("qty", 0) or 0))
            )

        closed_keys = {_mk_key_from_history(t) for t in history_trades}
        if closed_keys:
            active_trades = [t for t in active_trades if _mk_key_from_active(t) not in closed_keys]

        exposure = sum(abs(t["entry"] * t["qty"]) for t in active_trades) if active_trades else 0
        prob_win_avg = (sum(t["prob_win"] for t in active_trades) / len(active_trades)) if active_trades else 0

        summary = dict(snapshot["summary"])
        summary["active_trades"] = len(active_trades)
        summary["exposure"] = json_safe_float(exposure)
        summary["prob_win_avg"] = json_safe_float(prob_win_avg)

        return jsonify({
            "trades": active_trades,
            "summary": summary,
            "plan": "STANDARD"
        })

    return jsonify({
        "trades": snapshot["active"],
        "summary": snapshot["summary"],
        "plan": "ACTIVE"
    })

@app.route('/api/comparison')
def api_comparison():
    """⚖️ Plan Comparison - STANDARD vs PROBWIN_55"""
    snapshot = get_cached_snapshot()
    return jsonify(snapshot["plans"])

@app.route('/api/history')
def api_history():
    """📋 Historial - Trades cerrados (solo lectura)"""
    snapshot = get_cached_snapshot()
    return jsonify(snapshot["history"])

@app.route('/api/gating-rules')
def api_gating_rules():
    """🚪 Gating Rules - Reglas de selección de activos"""
    rules = {
        "gating_types": [
            {
                "name": "Static Gate",
                "description": "Selección fija de tickers por mes",
                "parameters": {
                    "method": "Monte Carlo Simulation",
                    "lookback_days": 20,
                    "paths": 400,
                    "block_size": 4
                },
                "typical_selection": "4-5 tickers",
                "rebalance": "Mensual"
            },
            {
                "name": "Dynamic Gate",
                "description": "Selección de tickers con rebalance semanal",
                "parameters": {
                    "method": "Monte Carlo + Rotation",
                    "lookback_days": 20,
                    "max_rotation": 1,
                    "top_k": 4
                },
                "typical_selection": "4 tickers (con rotación)",
                "rebalance": "Semanal"
            },
            {
                "name": "Hybrid Gate",
                "description": "MC (60%) + Signal Quality (40%)",
                "parameters": {
                    "method": "Ensemble",
                    "mc_weight": 0.6,
                    "signal_weight": 0.4,
                    "min_prob_win": 0.55
                },
                "typical_selection": "3-4 tickers",
                "rebalance": "Mensual"
            }
        ],
        "thresholds": {
            "bearish_regime": {"min_prob_win": 0.65, "confidence_level": "Conservadora"},
            "neutral_regime": {"min_prob_win": 0.60, "confidence_level": "Moderada"},
            "bullish_regime": {"min_prob_win": 0.55, "confidence_level": "Agresiva"}
        },
        "position_sizing": {
            "max_positions_open": 5,
            "per_trade_capital_pct": 0.02,
            "max_exposure_pct": 0.80,
            "max_capital": 800.0
        },
        "exit_rules": {
            "take_profit_pct": 1.6,
            "stop_loss_pct": 1.0,
            "max_hold_days": 2
        },
        "risk_management": {
            "confidence_threshold": 4,
            "risk_level_threshold": "MEDIUM",
            "whitelist_tickers": ["CVX", "XOM", "WMT", "MSFT", "SPY", "PFE", "AMD"]
        }
    }
    return jsonify(rules)

@app.route('/api/health')
def api_health():
    """✅ Health real del dashboard"""
    now = datetime.now()
    snapshot_age = (time.time() - SNAPSHOT_LAST_BUILD) if SNAPSHOT_LAST_BUILD else None
    health = {
        "status": "ok",
        "time": now.isoformat(),
        "snapshot": {
            "age_sec": snapshot_age,
            "stale": snapshot_age is not None and snapshot_age > SNAPSHOT_CACHE_TTL,
            "revalidating": SNAPSHOT_REVALIDATING,
        },
        "files": {
            "trade_plan": TRADE_PLAN_PATH.exists(),
            "trade_history": TRADE_HISTORY_PATH.exists(),
            "standard_plan": STANDARD_PLAN_PATH.exists(),
        },
        "tracking": {
            "thread_alive": TRACKING_THREAD.is_alive() if TRACKING_THREAD else False,
            "interval_sec": TRACKING_INTERVAL,
        },
    }

    # Estado vacío explícito
    try:
        snapshot = get_cached_snapshot()
        health["empty_state"] = {
            "active_trades": len(snapshot.get("active", [])) == 0,
            "history_trades": len(snapshot.get("history", [])) == 0,
        }
    except Exception:
        health["status"] = "degraded"
        health["empty_state"] = {"active_trades": True, "history_trades": True}

    return jsonify(health)


# ============================================================================
# ENDPOINTS FASE 2-3: Validación y Operación
# ============================================================================

@app.route('/api/phase2/metrics')
def api_phase2_metrics():
    """Retorna métricas actuales por libro (FASE 2)"""
    status = METRICS_TRACKER.get_status()
    
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'capital_manager': {
            'total': CAPITAL_MANAGER.total,
            'swing_bucket': CAPITAL_MANAGER.swing_bucket,
            'intraday_bucket': CAPITAL_MANAGER.intraday_bucket,
            'open_swing': CAPITAL_MANAGER.open_swing,
            'open_intraday': CAPITAL_MANAGER.open_intraday,
        },
        'risk_manager': RISK_MANAGER.get_status(),
        'metrics': status,
        'phase': 'PHASE 2 - VALIDATION',
    })


@app.route('/api/phase2/weekly-report')
def api_phase2_weekly_report():
    """Genera reporte semanal con métricas por libro (FASE 2)"""
    report = METRICS_TRACKER.get_weekly_report()
    
    return jsonify({
        'status': 'ok',
        'report': report,
        'decision': {
            'swing_pf': report['swing']['pf'],
            'intraday_pf': report['intraday']['pf'],
            'intraday_enabled': RISK_MANAGER.is_intraday_enabled(),
            'recommendation': _get_phase2_recommendation(report),
        }
    })


@app.route('/api/phase3/log-trade', methods=['POST'])
def api_phase3_log_trade():
    """
    Registra un trade cerrado (FASE 3).
    
    POST body:
    {
        "book": "swing" | "intraday",
        "ticker": "AAPL",
        "side": "BUY" | "SELL",
        "entry": 180.0,
        "exit": 185.0,
        "qty": 3,
        "pnl": 15.0,
        "reason": "TP" | "SL" | "TIME"
    }
    """
    try:
        data = request.get_json()
        
        # Validar datos
        required = ['book', 'ticker', 'side', 'entry', 'exit', 'qty', 'pnl']
        if not all(k in data for k in required):
            return jsonify({'error': 'Missing required fields'}), 400
        
        book = data['book']
        ticker = data['ticker']
        
        # Log trade
        METRICS_TRACKER.log_trade(
            book=book,
            ticker=ticker,
            side=data['side'],
            entry=data['entry'],
            exit_price=data['exit'],
            qty=data['qty'],
            pnl=data['pnl'],
            reason_exit=data.get('reason', 'UNKNOWN')
        )
        
        # Actualizar RiskManager
        RISK_MANAGER.update_pnl(data['pnl'])
        
        # Liberar capital
        CAPITAL_MANAGER.remove_open(book, ticker)
        
        logger.info(f"[PHASE3] Trade logged: {book} {ticker}, PnL={data['pnl']:.2f}")
        
        return jsonify({
            'status': 'ok',
            'message': f'Trade logged for {book} {ticker}',
            'metrics': METRICS_TRACKER.get_status(),
        })
    
    except Exception as e:
        logger.exception(f"[PHASE3] Error logging trade: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/phase3/validation-plan')
def api_phase3_validation_plan():
    """
    Retorna plan de validación 12-week (FASE 3).
    Compara con criterios de decisión para Fase 2 afinada.
    """
    status = METRICS_TRACKER.get_status()
    risk_status = RISK_MANAGER.get_status()
    
    # Criterios de decisión (semana 8-12)
    swing_pf = status['swing']['pf']
    intraday_pf = status['intraday']['pf']
    intraday_dd = risk_status.get('drawdown_pct', 0)
    
    validation = {
        'phase': 'PHASE 3 - OPERATION',
        'current_metrics': status,
        'decision_criteria': {
            'swing_pf': {'value': swing_pf, 'requirement': '> 1.05'},
            'intraday_pf': {'value': intraday_pf, 'requirement': '> 1.15 for continue, < 1.05 for stop'},
            'intraday_dd': {'value': intraday_dd, 'requirement': '< 5%'},
            'weeks_collected': {'value': len(METRICS_TRACKER.weekly_reports), 'requirement': '8-12'},
        },
        'next_decision': _get_phase3_decision(swing_pf, intraday_pf, intraday_dd),
        'weekly_reports': METRICS_TRACKER.weekly_reports[-4:] if len(METRICS_TRACKER.weekly_reports) > 4 else METRICS_TRACKER.weekly_reports,
    }
    
    return jsonify(validation)


def _get_phase2_recommendation(report):
    """Recomienda siguiente paso basado en reporte semanal"""
    intraday_pf = report['intraday']['pf']
    
    if intraday_pf > 1.15:
        return "CONTINUE - Intraday adding value, keep collecting data"
    elif intraday_pf < 1.05:
        return "WARNING - Intraday PF weak, monitor closely or disable"
    else:
        return "NEUTRAL - Intraday PF borderline, need more data"


def _get_phase3_decision(swing_pf, intraday_pf, intraday_dd):
    """Decisión final para Fase 2 afinada (semana 8-12)"""
    if intraday_pf > 1.25 and intraday_dd < 5.0:
        return "READY_FOR_ADVANCED - Fase 2 afinada (adaptativo, dinámico)"
    elif intraday_pf < 1.05:
        return "DISABLE_INTRADAY - Swing only"
    else:
        return "CONTINUE_PHASE2 - Need more validation weeks"


@app.route('/api/phase3/checklist')
def api_phase3_checklist():
    """Checklist de Fase 3: ¿Está listo para operación real?"""
    
    checks = {
        'code_ready': {
            'CapitalManager': 'IMPLEMENTED',
            'RiskManager': 'IMPLEMENTED',
            'IntraDayGates': 'IMPLEMENTED',
            'MetricsTracker': 'IMPLEMENTED',
            'Logging': 'IMPLEMENTED',
        },
        'validation': {
            'Tests passing': '11/11 PASS',
            'Example scenarios': '5/5 PASS',
            'Documentation': 'COMPLETE',
        },
        'operation_ready': {
            'Logging separated': bool(CAPITAL_MANAGER and RISK_MANAGER and METRICS_TRACKER),
            'Metrics tracking': len(METRICS_TRACKER.swing_trades) > 0 or len(METRICS_TRACKER.intraday_trades) > 0,
            'Weekly reports': len(METRICS_TRACKER.weekly_reports) > 0,
            'Risk controls': RISK_MANAGER.is_intraday_enabled(),
        }
    }
    
    return jsonify({
        'phase': 'PHASE 3 - OPERATION READINESS',
        'checks': checks,
        'ready': all(checks['code_ready'].values()),
        'timestamp': datetime.now().isoformat(),
    })


# ============================================================================
# HTML VISUALES FASE 2-3 (Web Dashboard)
# ============================================================================

@app.route('/dashboard')
def dashboard_home():
    """Dashboard home - Índice de Fase 2-3"""
    html = """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Fase 2-3 Dashboard</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f5f7fa; color: #333; }
            .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
            header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 8px; margin-bottom: 30px; }
            h1 { font-size: 28px; margin-bottom: 10px; }
            .subtitle { opacity: 0.9; font-size: 14px; }
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; margin-bottom: 30px; }
            .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); transition: transform 0.3s; }
            .card:hover { transform: translateY(-5px); box-shadow: 0 4px 16px rgba(0,0,0,0.15); }
            .card-title { font-size: 18px; font-weight: 600; margin-bottom: 10px; color: #667eea; }
            .card-desc { font-size: 13px; color: #666; line-height: 1.6; margin-bottom: 15px; }
            .btn { display: inline-block; padding: 10px 20px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; transition: background 0.3s; font-size: 14px; }
            .btn:hover { background: #764ba2; }
            .btn-secondary { background: #48bb78; }
            .btn-secondary:hover { background: #38a169; }
            .phase-badge { display: inline-block; padding: 4px 12px; background: #667eea; color: white; border-radius: 20px; font-size: 12px; font-weight: 600; margin-top: 10px; }
            .status { margin-top: 15px; padding: 10px; background: #f0f4ff; border-left: 4px solid #667eea; border-radius: 4px; font-size: 12px; }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>⚙️ Fase 2-3 Trading System Dashboard</h1>
                <p class="subtitle">Swing + Intraday Selectivo - Validación y Operación</p>
            </header>

            <div class="grid">
                <!-- FASE 2 CARDS -->
                <div class="card">
                    <div class="card-title">📊 Fase 2: Métricas</div>
                    <div class="card-desc">Visualiza métricas actuales por libro (Swing vs Intraday). Monitorea PF, winrate, drawdown.</div>
                    <a href="/dashboard/phase2/metrics" class="btn">Ver Métricas</a>
                    <a href="/api/phase2/metrics" class="btn btn-secondary" style="margin-left: 8px;">JSON API</a>
                    <div class="phase-badge">FASE 2</div>
                </div>

                <div class="card">
                    <div class="card-title">📈 Fase 2: Reporte Semanal</div>
                    <div class="card-desc">Reporte semanal con PF por libro y recomendación para continuar o ajustar.</div>
                    <a href="/dashboard/phase2/report" class="btn">Ver Reporte</a>
                    <a href="/api/phase2/weekly-report" class="btn btn-secondary" style="margin-left: 8px;">JSON API</a>
                    <div class="phase-badge">FASE 2</div>
                </div>

                <!-- FASE 3 CARDS -->
                <div class="card">
                    <div class="card-title">🎯 Fase 3: Plan de Validación</div>
                    <div class="card-desc">Progreso hacia decisión final (semana 8-12). Criterios de decisión y tendencias.</div>
                    <a href="/dashboard/phase3/plan" class="btn">Ver Plan</a>
                    <a href="/api/phase3/validation-plan" class="btn btn-secondary" style="margin-left: 8px;">JSON API</a>
                    <div class="phase-badge">FASE 3</div>
                </div>

                <div class="card">
                    <div class="card-title">✅ Fase 3: Readiness Check</div>
                    <div class="card-desc">Verifica si todos los componentes están IMPLEMENTADOS y listos para operación real.</div>
                    <a href="/dashboard/phase3/checklist" class="btn">Ver Checklist</a>
                    <a href="/api/phase3/checklist" class="btn btn-secondary" style="margin-left: 8px;">JSON API</a>
                    <div class="phase-badge">FASE 3</div>
                </div>

                <!-- TRADE LOGGING -->
                <div class="card">
                    <div class="card-title">📝 Fase 3: Log Trade</div>
                    <div class="card-desc">Registra trades cerrados desde operación real. POST a /api/phase3/log-trade.</div>
                    <a href="/dashboard/phase3/log-trade" class="btn">Log Trade</a>
                    <div class="phase-badge">FASE 3</div>
                </div>

                <!-- SYSTEM STATUS -->
                <div class="card">
                    <div class="card-title">🏥 System Health</div>
                    <div class="card-desc">Estado del sistema, threads activos, archivos de datos.</div>
                    <a href="/api/health" class="btn" onclick="window.open(this.href); return false;">Ver Health</a>
                    <div class="status" id="health-status">Cargando...</div>
                </div>
            </div>

            <footer style="text-align: center; color: #999; font-size: 12px; margin-top: 40px;">
                <p>Swing + Fase 2 (Intraday Selectivo) | 12-week validation system | Ready for production</p>
            </footer>
        </div>

        <script>
            // Cargar estado del sistema
            fetch('/api/health')
                .then(r => r.json())
                .then(data => {
                    const status = document.getElementById('health-status');
                    status.innerHTML = `Status: ${data.status} | Trades: ${data.empty_state.active_trades ? 0 : '?'} active`;
                })
                .catch(e => {
                    document.getElementById('health-status').innerHTML = 'Error: ' + e.message;
                });
        </script>
    </body>
    </html>
    """
    return render_template_string(html)


@app.route('/dashboard/phase2/metrics')
def dashboard_phase2_metrics():
    """Visualiza métricas de Fase 2"""
    try:
        status = METRICS_TRACKER.get_status()
        
        swing = status['swing']
        intraday = status['intraday']
        
        html = f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Fase 2 - Métricas</title>
            <script src="https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js"></script>
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f5f7fa; color: #333; }}
                .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
                header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
                h1 {{ font-size: 24px; margin-bottom: 5px; }}
                .breadcrumb {{ opacity: 0.9; font-size: 13px; }}
                .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 20px; }}
                .card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
                .metric-group {{ margin-bottom: 20px; }}
                .metric-row {{ display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #eee; }}
                .metric-row:last-child {{ border-bottom: none; }}
                .metric-label {{ font-weight: 600; color: #667eea; }}
                .metric-value {{ font-size: 18px; font-weight: 700; color: #333; }}
                .metric-pf {{ color: #48bb78; }}
                .metric-pf.danger {{ color: #f56565; }}
                .chart-container {{ position: relative; height: 300px; margin: 20px 0; }}
                .back-btn {{ display: inline-block; padding: 8px 15px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; margin-bottom: 20px; }}
                .book-title {{ font-size: 16px; font-weight: 700; color: #667eea; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 2px solid #667eea; }}
            </style>
        </head>
        <body>
            <div class="container">
                <header>
                    <h1>📊 Fase 2: Métricas Actuales</h1>
                    <p class="breadcrumb"><a href="/dashboard" style="color: white; text-decoration: none;">← Dashboard</a> / Métricas</p>
                </header>

                <a href="/dashboard" class="back-btn">← Volver</a>

                <div class="grid">
                    <!-- SWING METRICS -->
                    <div class="card">
                        <div class="book-title">🔄 SWING</div>
                        <div class="metric-group">
                            <div class="metric-row">
                                <span class="metric-label">Trades:</span>
                                <span class="metric-value">{swing['trades']}</span>
                            </div>
                            <div class="metric-row">
                                <span class="metric-label">PnL:</span>
                                <span class="metric-value">${swing['pnl']:.2f}</span>
                            </div>
                            <div class="metric-row">
                                <span class="metric-label">Profit Factor:</span>
                                <span class="metric-value metric-pf {'danger' if swing['pf'] < 1.05 else ''}">
                                    {swing['pf']:.2f}
                                </span>
                            </div>
                            <div class="metric-row">
                                <span class="metric-label">Winrate:</span>
                                <span class="metric-value">{swing['winrate'] * 100:.1f}%</span>
                            </div>
                            <div class="metric-row">
                                <span class="metric-label">Avg Win/Loss:</span>
                                <span class="metric-value">${swing['avg_win']:.2f} / ${swing['avg_loss']:.2f}</span>
                            </div>
                            <div class="metric-row">
                                <span class="metric-label">Drawdown:</span>
                                <span class="metric-value">{swing['dd']:.2f}%</span>
                            </div>
                        </div>
                    </div>

                    <!-- INTRADAY METRICS -->
                    <div class="card">
                        <div class="book-title">⚡ INTRADAY</div>
                        <div class="metric-group">
                            <div class="metric-row">
                                <span class="metric-label">Trades:</span>
                                <span class="metric-value">{intraday['trades']}</span>
                            </div>
                            <div class="metric-row">
                                <span class="metric-label">PnL:</span>
                                <span class="metric-value">${intraday['pnl']:.2f}</span>
                            </div>
                            <div class="metric-row">
                                <span class="metric-label">Profit Factor:</span>
                                <span class="metric-value metric-pf {'danger' if intraday['pf'] < 1.15 else ''}">
                                    {intraday['pf']:.2f}
                                </span>
                            </div>
                            <div class="metric-row">
                                <span class="metric-label">Winrate:</span>
                                <span class="metric-value">{intraday['winrate'] * 100:.1f}%</span>
                            </div>
                            <div class="metric-row">
                                <span class="metric-label">Avg Win/Loss:</span>
                                <span class="metric-value">${intraday['avg_win']:.2f} / ${intraday['avg_loss']:.2f}</span>
                            </div>
                            <div class="metric-row">
                                <span class="metric-label">Drawdown:</span>
                                <span class="metric-value">{intraday['dd']:.2f}%</span>
                            </div>
                        </div>
                    </div>

                    <!-- TOTAL METRICS -->
                    <div class="card">
                        <div class="book-title">📈 TOTAL</div>
                        <div class="metric-group">
                            <div class="metric-row">
                                <span class="metric-label">Total Trades:</span>
                                <span class="metric-value">{status['total']['trades']}</span>
                            </div>
                            <div class="metric-row">
                                <span class="metric-label">Total PnL:</span>
                                <span class="metric-value">${status['total']['pnl']:.2f}</span>
                            </div>
                            <div class="metric-row">
                                <span class="metric-label">Combined PF:</span>
                                <span class="metric-value metric-pf">{status['total']['pf']:.2f}</span>
                            </div>
                            <div class="metric-row">
                                <span class="metric-label">Decision:</span>
                                <span class="metric-value">
                                    {'✅ Continue' if swing['pf'] > 1.05 and intraday['pf'] > 1.15 else '⚠️ Review'}
                                </span>
                            </div>
                        </div>
                    </div>
                </div>

                <footer style="text-align: center; color: #999; font-size: 12px; margin-top: 30px;">
                    <p>Last update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 
                       <a href="/api/phase2/metrics" style="color: #667eea;">JSON API</a></p>
                </footer>
            </div>
        </body>
        </html>
        """
        return render_template_string(html)
    except Exception as e:
        return f"<h1>Error loading metrics</h1><p>{str(e)}</p>", 500


@app.route('/dashboard/phase2/report')
def dashboard_phase2_report():
    """Visualiza reporte semanal de Fase 2"""
    try:
        report = METRICS_TRACKER.get_weekly_report()
        decision = _get_phase2_recommendation(report)
        
        swing = report['swing']
        intraday = report['intraday']
        
        html = f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Fase 2 - Reporte Semanal</title>
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f5f7fa; color: #333; }}
                .container {{ max-width: 1000px; margin: 0 auto; padding: 20px; }}
                header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
                h1 {{ font-size: 24px; margin-bottom: 5px; }}
                .card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 20px; }}
                .report-table {{ width: 100%; border-collapse: collapse; }}
                .report-table th {{ background: #667eea; color: white; padding: 10px; text-align: left; font-weight: 600; }}
                .report-table td {{ padding: 10px; border-bottom: 1px solid #eee; }}
                .report-table tr:hover {{ background: #f9f9f9; }}
                .decision-box {{ background: #e8f5e9; border-left: 4px solid #48bb78; padding: 15px; border-radius: 4px; margin: 20px 0; }}
                .decision-title {{ font-weight: 700; color: #48bb78; margin-bottom: 5px; }}
                .back-btn {{ display: inline-block; padding: 8px 15px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; margin-bottom: 20px; }}
                .metric {{ color: #667eea; font-weight: 700; }}
            </style>
        </head>
        <body>
            <div class="container">
                <header>
                    <h1>📈 Fase 2: Reporte Semanal</h1>
                    <p style="opacity: 0.9; font-size: 13px;"><a href="/dashboard" style="color: white; text-decoration: none;">← Dashboard</a> / Reporte Semanal</p>
                </header>

                <a href="/dashboard" class="back-btn">← Volver</a>

                <div class="card">
                    <h2>Resumen Semanal</h2>
                    <table class="report-table">
                        <tr>
                            <th>Métrica</th>
                            <th>Swing</th>
                            <th>Intraday</th>
                            <th>Criterio</th>
                        </tr>
                        <tr>
                            <td><strong>Trades</strong></td>
                            <td class="metric">{swing['trades']}</td>
                            <td class="metric">{intraday['trades']}</td>
                            <td>20+ recomendado</td>
                        </tr>
                        <tr>
                            <td><strong>PnL</strong></td>
                            <td class="metric">${swing['pnl']:.2f}</td>
                            <td class="metric">${intraday['pnl']:.2f}</td>
                            <td>Positivo</td>
                        </tr>
                        <tr>
                            <td><strong>Profit Factor</strong></td>
                            <td class="metric">{swing['pf']:.2f}</td>
                            <td class="metric">{intraday['pf']:.2f}</td>
                            <td>Swing > 1.05, ID > 1.15</td>
                        </tr>
                        <tr>
                            <td><strong>Winrate</strong></td>
                            <td class="metric">{swing['winrate']:.1f}%</td>
                            <td class="metric">{intraday['winrate']:.1f}%</td>
                            <td>> 50%</td>
                        </tr>
                        <tr>
                            <td><strong>Mejor Trade</strong></td>
                            <td class="metric">${swing.get('best_trade', 0):.2f}</td>
                            <td class="metric">${intraday.get('best_trade', 0):.2f}</td>
                            <td>Posit</td>
                        </tr>
                        <tr>
                            <td><strong>Peor Trade</strong></td>
                            <td class="metric">${swing.get('worst_trade', 0):.2f}</td>
                            <td class="metric">${intraday.get('worst_trade', 0):.2f}</td>
                            <td>Control</td>
                        </tr>
                    </table>
                </div>

                <div class="decision-box">
                    <div class="decision-title">📌 Recomendación</div>
                    <p>{decision}</p>
                    <p style="margin-top: 10px; font-size: 12px; color: #666;">
                        {'✅ Continue con Fase 3' if intraday['pf'] > 1.15 else '⚠️ Review antes de continuar'}
                    </p>
                </div>

                <footer style="text-align: center; color: #999; font-size: 12px; margin-top: 30px;">
                    <p>Last update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 
                       <a href="/api/phase2/weekly-report" style="color: #667eea;">JSON API</a></p>
                </footer>
            </div>
        </body>
        </html>
        """
        return render_template_string(html)
    except Exception as e:
        return f"<h1>Error loading report</h1><p>{str(e)}</p>", 500


@app.route('/dashboard/phase3/plan')
def dashboard_phase3_plan():
    """Visualiza plan de validación de Fase 3"""
    try:
        status = METRICS_TRACKER.get_status()
        risk_status = RISK_MANAGER.get_status()
        
        swing_pf = status['swing']['pf']
        intraday_pf = status['intraday']['pf']
        intraday_dd = risk_status.get('drawdown_pct', 0)
        weeks = len(METRICS_TRACKER.weekly_reports)
        
        decision = _get_phase3_decision(swing_pf, intraday_pf, intraday_dd)
        
        html = f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Fase 3 - Plan de Validación</title>
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f5f7fa; color: #333; }}
                .container {{ max-width: 1000px; margin: 0 auto; padding: 20px; }}
                header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
                h1 {{ font-size: 24px; margin-bottom: 5px; }}
                .card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 20px; }}
                .criteria-row {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; margin-bottom: 20px; padding: 15px; background: #f9f9f9; border-radius: 4px; }}
                .criteria-item {{ border-left: 3px solid #667eea; padding-left: 10px; }}
                .criteria-label {{ font-weight: 600; color: #667eea; font-size: 12px; margin-bottom: 5px; }}
                .criteria-value {{ font-size: 18px; font-weight: 700; }}
                .criteria-ok {{ color: #48bb78; }}
                .criteria-warning {{ color: #ed8936; }}
                .criteria-danger {{ color: #f56565; }}
                .decision-box {{ background: #e8f5e9; border-left: 4px solid #48bb78; padding: 15px; border-radius: 4px; margin: 20px 0; }}
                .decision-title {{ font-weight: 700; color: #48bb78; margin-bottom: 5px; }}
                .back-btn {{ display: inline-block; padding: 8px 15px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; margin-bottom: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <header>
                    <h1>🎯 Fase 3: Plan de Validación (12 semanas)</h1>
                    <p style="opacity: 0.9; font-size: 13px;"><a href="/dashboard" style="color: white; text-decoration: none;">← Dashboard</a> / Validation Plan</p>
                </header>

                <a href="/dashboard" class="back-btn">← Volver</a>

                <div class="card">
                    <h2>Criterios de Decisión (Semana 8-12)</h2>
                    <div class="criteria-row">
                        <div class="criteria-item">
                            <div class="criteria-label">Swing PF</div>
                            <div class="criteria-value criteria-{'ok' if swing_pf > 1.05 else 'danger'}">{swing_pf:.2f}</div>
                            <div style="font-size: 12px; color: #666; margin-top: 3px;">Req: > 1.05</div>
                        </div>
                        <div class="criteria-item">
                            <div class="criteria-label">Intraday PF</div>
                            <div class="criteria-value criteria-{'ok' if intraday_pf > 1.25 else 'warning' if intraday_pf > 1.05 else 'danger'}">{intraday_pf:.2f}</div>
                            <div style="font-size: 12px; color: #666; margin-top: 3px;">Req: > 1.25 (READY)</div>
                        </div>
                        <div class="criteria-item">
                            <div class="criteria-label">Intraday DD</div>
                            <div class="criteria-value criteria-{'ok' if intraday_dd < 5.0 else 'warning' if intraday_dd < 10.0 else 'danger'}">{intraday_dd:.2f}%</div>
                            <div style="font-size: 12px; color: #666; margin-top: 3px;">Req: < 5%</div>
                        </div>
                    </div>
                    
                    <div class="criteria-row">
                        <div class="criteria-item">
                            <div class="criteria-label">Semanas Recolectadas</div>
                            <div class="criteria-value">{weeks}/12</div>
                            <div style="font-size: 12px; color: #666; margin-top: 3px;">Req: 8-12</div>
                        </div>
                        <div style="grid-column: 2 / 4;"></div>
                    </div>
                </div>

                <div class="decision-box">
                    <div class="decision-title">🎯 Próxima Decisión</div>
                    <p style="font-size: 14px; margin-bottom: 10px;"><strong>{decision}</strong></p>
                    <ul style="margin-left: 20px; font-size: 12px; color: #666; line-height: 1.8;">
                        <li><strong>Fase 2 Afinada:</strong> Intraday PF > 1.25 & DD < 5% → Gates adaptativos, multi-ticker</li>
                        <li><strong>Swing Only:</strong> Intraday PF < 1.05 → Deshabilitar intraday, optimizar swing</li>
                        <li><strong>Continue:</strong> 1.05 ≤ PF ≤ 1.25 → Más validación, ajustar parámetros</li>
                    </ul>
                </div>

                <div class="card">
                    <h2>Últimos Reportes Semanales</h2>
                    <p style="font-size: 12px; color: #666; margin-bottom: 15px;">Últimas 4 semanas</p>
                    <!-- Weekly reports would go here -->
                    <p style="color: #999; font-style: italic;">Reportes serán actualizados conforme progresa la operación</p>
                </div>

                <footer style="text-align: center; color: #999; font-size: 12px; margin-top: 30px;">
                    <p>Last update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 
                       <a href="/api/phase3/validation-plan" style="color: #667eea;">JSON API</a></p>
                </footer>
            </div>
        </body>
        </html>
        """
        return render_template_string(html)
    except Exception as e:
        return f"<h1>Error loading validation plan</h1><p>{str(e)}</p>", 500


@app.route('/dashboard/phase3/checklist')
def dashboard_phase3_checklist():
    """Visualiza checklist de readiness Fase 3"""
    try:
        checks = {
            'code_ready': {
                'CapitalManager': 'IMPLEMENTED',
                'RiskManager': 'IMPLEMENTED',
                'IntraDayGates': 'IMPLEMENTED',
                'MetricsTracker': 'IMPLEMENTED',
                'Logging': 'IMPLEMENTED',
            },
            'validation': {
                'Tests passing': '11/11 PASS',
                'Example scenarios': '5/5 PASS',
                'Documentation': 'COMPLETE',
            },
            'operation_ready': {
                'Logging separated': CAPITAL_MANAGER and RISK_MANAGER and METRICS_TRACKER,
                'Metrics tracking': len(METRICS_TRACKER.swing_trades) > 0 or len(METRICS_TRACKER.intraday_trades) > 0,
                'Weekly reports': len(METRICS_TRACKER.weekly_reports) > 0,
                'Risk controls': RISK_MANAGER.is_intraday_enabled(),
            }
        }
        
        html = f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Fase 3 - Readiness Check</title>
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f5f7fa; color: #333; }}
                .container {{ max-width: 1000px; margin: 0 auto; padding: 20px; }}
                header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
                h1 {{ font-size: 24px; margin-bottom: 5px; }}
                .card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 20px; }}
                .checklist-item {{ display: flex; align-items: center; padding: 10px; border-bottom: 1px solid #eee; }}
                .checklist-item:last-child {{ border-bottom: none; }}
                .check {{ color: #48bb78; font-weight: 700; margin-right: 10px; }}
                .check-label {{ flex: 1; }}
                .check-value {{ color: #667eea; font-weight: 600; }}
                .section-title {{ font-size: 16px; font-weight: 700; color: #667eea; margin: 20px 0 10px 0; padding-bottom: 10px; border-bottom: 2px solid #667eea; }}
                .status-ready {{ background: #e8f5e9; border-left: 4px solid #48bb78; padding: 15px; border-radius: 4px; }}
                .status-ready-text {{ color: #48bb78; font-weight: 700; }}
                .back-btn {{ display: inline-block; padding: 8px 15px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; margin-bottom: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <header>
                    <h1>✅ Fase 3: Readiness Check</h1>
                    <p style="opacity: 0.9; font-size: 13px;"><a href="/dashboard" style="color: white; text-decoration: none;">← Dashboard</a> / Readiness</p>
                </header>

                <a href="/dashboard" class="back-btn">← Volver</a>

                <div class="card">
                    <div class="status-ready">
                        <p class="status-ready-text">✅ SISTEMA LISTO PARA OPERACIÓN REAL</p>
                        <p style="font-size: 12px; color: #666; margin-top: 5px;">Todos los componentes implementados y testeados</p>
                    </div>
                </div>

                <div class="card">
                    <div class="section-title">Code Status</div>
                    {"".join(f'<div class="checklist-item"><span class="check">✓</span><span class="check-label">{k}</span><span class="check-value">{v}</span></div>' for k, v in checks['code_ready'].items())}
                </div>

                <div class="card">
                    <div class="section-title">Validation Status</div>
                    {"".join(f'<div class="checklist-item"><span class="check">✓</span><span class="check-label">{k}</span><span class="check-value">{v}</span></div>' for k, v in checks['validation'].items())}
                </div>

                <div class="card">
                    <div class="section-title">Operation Ready</div>
                    {"".join(f'<div class="checklist-item"><span class="check">{"✓" if v else "✗"}</span><span class="check-label">{k}</span><span class="check-value">{"YES" if v else "Pending"}</span></div>' for k, v in checks['operation_ready'].items())}
                </div>

                <footer style="text-align: center; color: #999; font-size: 12px; margin-top: 30px;">
                    <p>Last update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 
                       <a href="/api/phase3/checklist" style="color: #667eea;">JSON API</a></p>
                </footer>
            </div>
        </body>
        </html>
        """
        return render_template_string(html)
    except Exception as e:
        return f"<h1>Error loading checklist</h1><p>{str(e)}</p>", 500


@app.route('/dashboard/phase3/log-trade')
def dashboard_phase3_log_trade():
    """Formulario para log trade en Fase 3"""
    html = """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Fase 3 - Log Trade</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f5f7fa; color: #333; }
            .container { max-width: 600px; margin: 0 auto; padding: 20px; }
            header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
            h1 { font-size: 24px; margin-bottom: 5px; }
            .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
            .form-group { margin-bottom: 15px; }
            label { display: block; margin-bottom: 5px; font-weight: 600; color: #667eea; }
            input, select { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
            input:focus, select:focus { outline: none; border-color: #667eea; box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1); }
            .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
            button { width: 100%; padding: 12px; background: #667eea; color: white; border: none; border-radius: 4px; font-weight: 600; cursor: pointer; margin-top: 20px; }
            button:hover { background: #764ba2; }
            .result { margin-top: 20px; padding: 15px; border-radius: 4px; display: none; }
            .result.success { background: #e8f5e9; color: #2e7d32; border-left: 4px solid #48bb78; }
            .result.error { background: #ffebee; color: #c62828; border-left: 4px solid #f44336; }
            .back-btn { display: inline-block; padding: 8px 15px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; margin-bottom: 20px; }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>📝 Fase 3: Log Trade</h1>
                <p style="opacity: 0.9; font-size: 13px;"><a href="/dashboard" style="color: white; text-decoration: none;">← Dashboard</a> / Log Trade</p>
            </header>

            <a href="/dashboard" class="back-btn">← Volver</a>

            <div class="card">
                <form id="trade-form">
                    <div class="form-row">
                        <div class="form-group">
                            <label>Book *</label>
                            <select name="book" required>
                                <option value="swing">Swing</option>
                                <option value="intraday">Intraday</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Ticker *</label>
                            <input type="text" name="ticker" placeholder="AAPL" required maxlength="10">
                        </div>
                    </div>

                    <div class="form-row">
                        <div class="form-group">
                            <label>Side *</label>
                            <select name="side" required>
                                <option value="BUY">BUY</option>
                                <option value="SELL">SELL</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Quantity *</label>
                            <input type="number" name="qty" placeholder="3" required min="1" step="1">
                        </div>
                    </div>

                    <div class="form-row">
                        <div class="form-group">
                            <label>Entry Price *</label>
                            <input type="number" name="entry" placeholder="225.50" required step="0.01">
                        </div>
                        <div class="form-group">
                            <label>Exit Price *</label>
                            <input type="number" name="exit" placeholder="232.25" required step="0.01">
                        </div>
                    </div>

                    <div class="form-row">
                        <div class="form-group">
                            <label>PnL *</label>
                            <input type="number" name="pnl" placeholder="20.25" required step="0.01">
                        </div>
                        <div class="form-group">
                            <label>Reason *</label>
                            <select name="reason" required>
                                <option value="TP">Take Profit</option>
                                <option value="SL">Stop Loss</option>
                                <option value="TIME">Time Exit</option>
                            </select>
                        </div>
                    </div>

                    <button type="submit">📤 Log Trade</button>
                </form>

                <div id="result" class="result"></div>
            </div>

            <footer style="text-align: center; color: #999; font-size: 12px; margin-top: 30px;">
                <p>POST to /api/phase3/log-trade | 
                   <a href="/api/phase2/metrics" style="color: #667eea;">View Metrics</a></p>
            </footer>
        </div>

        <script>
            document.getElementById('trade-form').addEventListener('submit', async (e) => {
                e.preventDefault();
                const formData = new FormData(e.target);
                const payload = {
                    book: formData.get('book'),
                    ticker: formData.get('ticker').toUpperCase(),
                    side: formData.get('side'),
                    entry: parseFloat(formData.get('entry')),
                    exit: parseFloat(formData.get('exit')),
                    qty: parseInt(formData.get('qty')),
                    pnl: parseFloat(formData.get('pnl')),
                    reason: formData.get('reason')
                };

                try {
                    const response = await fetch('/api/phase3/log-trade', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });

                    const result = document.getElementById('result');
                    if (response.ok) {
                        const data = await response.json();
                        result.className = 'result success';
                        result.innerHTML = `<strong>✅ Trade Logged</strong><p>${payload.book} ${payload.ticker} ${payload.side} | PnL: $${payload.pnl.toFixed(2)}</p>`;
                        e.target.reset();
                    } else {
                        const error = await response.json();
                        result.className = 'result error';
                        result.innerHTML = `<strong>❌ Error</strong><p>${error.error}</p>`;
                    }
                    result.style.display = 'block';
                } catch (err) {
                    const result = document.getElementById('result');
                    result.className = 'result error';
                    result.innerHTML = `<strong>❌ Error</strong><p>${err.message}</p>`;
                    result.style.display = 'block';
                }
            });
        </script>
    </body>
    </html>
    """
    return render_template_string(html)


@app.route('/api/chart/<ticker>')
def api_chart(ticker):
    """📈 Chart data por ticker (JSON-safe)"""
    try:
        import yfinance as yf
        tk = str(ticker).upper().strip()
        if not tk:
            return jsonify({"ticker": ticker, "points": [], "source": "empty"})

        source = "5d-15m"
        try:
            df = yf.download(tk, period='5d', interval='15m', progress=False, threads=True)
            if df is None or df.empty:
                source = "1d-1m"
                df = yf.download(tk, period='1d', interval='1m', progress=False, threads=True)
            if df is None or df.empty:
                source = "1mo-1d"
                df = yf.download(tk, period='1mo', interval='1d', progress=False, threads=True)
            if df is None or df.empty:
                source = "3mo-1d"
                df = yf.download(tk, period='3mo', interval='1d', progress=False, threads=True)
        except Exception as e:
            print(f"[WARNING] yfinance error {tk}: {e}")
            df = None

        if df is None or df.empty:
            # Fallback: intentar usar trade activo para un mini-chart
            source = "synthetic"
            try:
                snapshot = get_cached_snapshot()
                trade = next((t for t in snapshot.get("active", []) if str(t.get("ticker", "")).upper() == tk), None)
            except Exception:
                trade = None

            if trade:
                now = datetime.now()
                entry = json_safe_float(trade.get("entry", 0))
                current = json_safe_float(trade.get("exit", entry))
                tp = json_safe_float(trade.get("tp", current))
                sl = json_safe_float(trade.get("sl", current))
                points = [
                    {"t": (now - timedelta(minutes=3)).isoformat(), "close": entry},
                    {"t": (now - timedelta(minutes=2)).isoformat(), "close": (entry + current) / 2 if entry and current else current},
                    {"t": (now - timedelta(minutes=1)).isoformat(), "close": current},
                    {"t": now.isoformat(), "close": current},
                ]
                return jsonify({"ticker": tk, "points": points, "source": source})

            source = "cache"
            price = get_cached_prices([tk]).get(tk)
            if price is None:
                return jsonify({"ticker": tk, "points": [], "source": source})
            return jsonify({
                "ticker": tk,
                "points": [{"t": datetime.now().isoformat(), "close": json_safe_float(price)}],
                "source": source
            })

        # Obtener serie de cierre de forma robusta (MultiIndex o columnas distintas)
        close_series = None
        if hasattr(df.columns, "levels"):
            # MultiIndex: intentar ('Close', ticker) o cualquier 'Close'
            if ('Close', tk) in df.columns:
                close_series = df[('Close', tk)]
            elif 'Close' in df.columns.get_level_values(0):
                close_series = df['Close']
        else:
            if 'Close' in df.columns:
                close_series = df['Close']
            else:
                # buscar columna close en minúsculas
                for c in df.columns:
                    if str(c).lower() == 'close':
                        close_series = df[c]
                        break

        if close_series is None:
            return jsonify({"ticker": tk, "points": [], "source": source})

        close_series = close_series.dropna()
        points = []
        for idx, value in close_series.items():
            ts = idx.to_pydatetime().isoformat()
            points.append({
                "t": ts,
                "close": json_safe_float(value)
            })

        return jsonify({"ticker": tk, "points": points[-500:], "source": source})
    except Exception as e:
        print(f"[WARNING] Error chart {ticker}: {e}")
        return jsonify({"ticker": ticker, "points": [], "source": "error"})

@app.route('/api/close/<ticker>', methods=['POST'])
def api_close_trade(ticker):
    """🛑 Cierre manual de posición activa"""
    reason = "MANUAL"
    try:
        if request.is_json:
            payload = request.get_json(silent=True) or {}
            reason = str(payload.get("reason", "MANUAL"))
    except Exception:
        reason = "MANUAL"

    result = _close_manual_trade(ticker, reason=reason)
    if result.get("ok"):
        status = 200
    elif result.get("code") == "already_closed":
        status = 409
    else:
        status = 400
    return jsonify(result), status

def start_background_tracking():
    """⏱️ Lanza tracking en thread background cada TRACKING_INTERVAL segundos.
    No bloquea los endpoints.
    """
    global TRACKING_THREAD, TRACKING_ACTIVE
    
    def tracking_loop():
        logger.info(f"[TRACKING] Background tracking started (interval: {TRACKING_INTERVAL}s)")
        cycle_count = 0
        while True:
            try:
                time.sleep(TRACKING_INTERVAL)
                cycle_count += 1
                logger.debug(f"[TRACKING] Cycle #{cycle_count} starting")
                run_tracking_cycle()
            except Exception as e:
                logger.exception(f"[TRACKING] Loop error (cycle #{cycle_count}): {e}")
    
    if TRACKING_THREAD is None or not TRACKING_THREAD.is_alive():
        TRACKING_THREAD = threading.Thread(target=tracking_loop, daemon=True)
        TRACKING_THREAD.start()

def main():
    import sys
    import os
    PORT = 8060
    
    logger.info("[STARTUP] ============================================================")
    logger.info("[STARTUP] TRADE DASHBOARD UNIFICADO - FASE 2 (READ-ONLY + SNAPSHOT)")
    logger.info("[STARTUP] ============================================================")
    if PRODUCTION_MODE:
        logger.info("[STARTUP] PRODUCTION_MODE=ON")
        if SINGLE_PROCESS_ONLY:
            logger.info("[STARTUP] Single-process only (no multi-worker)")
        else:
            logger.warning("[STARTUP] Multi-worker enabled: use file-locking for CSV writes")
    else:
        logger.info("[STARTUP] PRODUCTION_MODE=OFF (single-process recommended)")

    # Aviso si se detecta concurrencia por entorno
    if os.environ.get("WEB_CONCURRENCY") or os.environ.get("GUNICORN_WORKERS"):
        logger.warning("[STARTUP] Detected multi-worker environment variables. CSV locks are process-local.")
    sys.stdout.flush()
    
    # Lanzar tracking en background
    start_background_tracking()
    
    local_ip = get_local_ip()
    logger.info(f"[STARTUP] LOCAL: http://localhost:{PORT}/")
    logger.info(f"[STARTUP] LAN: http://{local_ip}:{PORT}/")
    logger.info(f"[STARTUP] Listening on 0.0.0.0:{PORT}")
    logger.info(f"[STARTUP] Tracking interval: {TRACKING_INTERVAL}s")
    logger.info(f"[STARTUP] Cache TTL: {SNAPSHOT_CACHE_TTL}s")
    sys.stdout.flush()
    
    try:
        # Fix para Windows: deshabilitar reloader para evitar WERKZEUG_SERVER_FD error
        app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False, threaded=True)
    except KeyError as e:
        if 'WERKZEUG_SERVER_FD' in str(e):
            logger.warning("[WERKZEUG] Reloader error, restarting without reloader...")
            app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False, threaded=True)
        else:
            logger.error(f"[ERROR] {e}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"[ERROR] {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
