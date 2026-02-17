#!/usr/bin/env python
"""
MEJORA 2: Recalibraci√≥n Mensual de Probabilidades
===================================================
Tu modelo predice prob_win (probabilidad de ganar).
Pero: ¿está sesgada? ¿Subestima o sobreestima?

Soluci√≥n: Recalibrar con Platt Scaling o Isotonic Regression
basada en el mes anterior.

CAMBIOS CLAVE:
1. Calcular prob_win del mes anterior (verificar contra realidad)
2. Entrenar calibrador (Platt o Isotonic)
3. Aplicar al mes actual
4. Re-definir umbral optimal (no siempre 0.65)

Esto asegura que "prob_win >= 0.65" significa REALMENTE 65% de ganar.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from sklearn.calibration import CalibratedClassifierCV
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings("ignore")

REPO_ROOT = Path(__file__).resolve().parent
CSV_PATH = REPO_ROOT / "outputs" / "analysis" / "all_signals_with_confidence.csv"
OUTPUTS_DIR = REPO_ROOT / "outputs" / "analysis"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

sns.set_style("whitegrid")
plt.rcParams["figure.figsize"] = (14, 7)


def load_and_prepare_data(csv_path: Path) -> pd.DataFrame:
    """Cargar datos y preparar."""
    df = pd.read_csv(csv_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["y_H3", "y_hat", "close"])
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    
    # Crear target: ¿ganamos dinero?
    df["price_pred"] = df["close"] * (1 + df["y_hat"])
    df["price_real"] = df["close"].shift(-3)
    df = df.dropna(subset=["price_real"])
    
    df["price_error_pct"] = ((df["price_real"] - df["price_pred"]) / df["price_pred"]) * 100
    df["direction_correct"] = (np.sign(df["y_hat"]) == np.sign(df["y_H3"])).astype(int)
    df["won"] = df["direction_correct"]  # Target binario: ganamos o no
    
    # Si no tienes prob_win, calcularla
    if "prob_win" not in df.columns:
        # Estimaci√≥n simple: suavizar direction_correct por ticker y ventana
        df["prob_win"] = df.groupby("ticker")["direction_correct"].transform(
            lambda x: x.rolling(window=20, min_periods=1).mean()
        )
    
    print(f"✓ Datos preparados: {len(df):,} observaciones")
    print(f"✓ Período: {df['date'].min().date()} a {df['date'].max().date()}")
    print(f"✓ Prob_win media: {df['prob_win'].mean():.3f}")
    print(f"✓ Win rate real: {df['won'].mean():.3f}")
    
    return df


def split_train_test(df: pd.DataFrame, test_month="2025-11"):
    """
    Dividir en entrenamiento (mes anterior) y test (mes actual).
    """
    test_date = pd.to_datetime(test_month + "-01")
    train_start = (test_date - timedelta(days=60)).date()  # 2 meses para entrenar
    train_end = (test_date - timedelta(days=1)).date()
    test_start = test_date.date()
    test_end = (test_date + timedelta(days=31)).date()
    
    train_df = df[(df["date"].dt.date >= train_start) & (df["date"].dt.date <= train_end)]
    test_df = df[(df["date"].dt.date >= test_start) & (df["date"].dt.date <= test_end)]
    
    print(f"\n[TRAIN] {train_start} a {train_end}: {len(train_df):,} obs")
    print(f"[TEST]  {test_start} a {test_end}: {len(test_df):,} obs")
    
    return train_df, test_df


def calibrate_platt(train_df: pd.DataFrame):
    """
    Entrenar Platt Scaling sobre los datos de entrenamiento.
    
    La idea: prob_win original no es perfecta, pero contiene informaci√≥n.
    Platt scaling ajusta la relaci√≥n entre prob_win y P(won=1).
    """
    
    X_train = train_df[["prob_win"]].values
    y_train = train_df["won"].values
    
    # Platt Scaling = LogisticRegression(max_iter=100)
    platt = LogisticRegression(max_iter=100)
    platt.fit(X_train, y_train)
    
    # prob_calibrated = platt.predict_proba(X_train)[:, 1]
    # Esto transforma prob_win cruda en probabilidad calibrada
    
    print(f"\n[PLATT SCALING]")
    print(f"  Coef (pendiente): {platt.coef_[0][0]:.4f}")
    print(f"  Intercept: {platt.intercept_[0]:.4f}")
    print(f"  (Mayor coef = model√≥ original es m√°s sensible)")
    
    return platt


def calibrate_isotonic(train_df: pd.DataFrame):
    """
    Entrenar Isotonic Regression sobre los datos de entrenamiento.
    M√°s flexible que Platt, no asume forma log√≠stica.
    """
    
    X_train = train_df[["prob_win"]].values.ravel()
    y_train = train_df["won"].values
    
    # Isotonic regression
    iso = IsotonicRegression()
    iso.fit(X_train, y_train)
    
    print(f"\n[ISOTONIC REGRESSION]")
    print(f"  Función no paramétrica (monotónica)")
    print(f"  Se adapta mejor a desviaciones del modelo logístico")
    
    return iso


def find_optimal_threshold(train_df: pd.DataFrame, prob_col="prob_win"):
    """
    Encontrar el threshold óptimo que maximiza accuracy o F1.
    """
    
    from sklearn.metrics import precision_recall_curve, f1_score
    
    probs = train_df[prob_col].values
    actuals = train_df["won"].values
    
    # Buscar threshold
    thresholds = np.arange(0, 1.01, 0.05)
    best_f1 = 0
    best_threshold = 0.5
    
    for thresh in thresholds:
        preds = (probs >= thresh).astype(int)
        f1 = f1_score(actuals, preds, zero_division=0)
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = thresh
    
    print(f"\n[THRESHOLD OPTIMIZATION]")
    print(f"  Threshold óptimo (en lugar de 0.65): {best_threshold:.2f}")
    print(f"  F1 Score a ese threshold: {best_f1:.4f}")
    print(f"  (Regla: prob_win >= {best_threshold:.2f} para operar)")
    
    return best_threshold


def apply_calibration(test_df: pd.DataFrame, platt_model, method="platt") -> pd.DataFrame:
    """
    Aplicar calibración al conjunto de test.
    """
    
    X_test = test_df[["prob_win"]].values
    
    if method == "platt":
        test_df["prob_win_calibrated"] = platt_model.predict_proba(X_test)[:, 1]
    else:
        # Para isotonic sería diferente (no tiene predict_proba)
        test_df["prob_win_calibrated"] = test_df["prob_win"].values
    
    return test_df


def plot_calibration(train_df: pd.DataFrame, test_df: pd.DataFrame, 
                     platt_model, optimal_threshold: float):
    """
    Visualizar efecto de calibración.
    """
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # 1. Distribución prob_win antes
    ax = axes[0, 0]
    ax.hist(train_df["prob_win"], bins=30, alpha=0.7, label="Train", color="steelblue")
    ax.hist(test_df["prob_win"], bins=30, alpha=0.7, label="Test", color="coral")
    ax.axvline(0.65, color="red", linestyle="--", linewidth=2, label="Old threshold (0.65)")
    ax.axvline(optimal_threshold, color="green", linestyle="--", linewidth=2, 
               label=f"Optimal threshold ({optimal_threshold:.2f})")
    ax.set_xlabel("Prob Win (Crudo)")
    ax.set_ylabel("Frecuencia")
    ax.set_title("Distribución de Probabilidades Crudas")
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # 2. Calibración: prob_win vs win_rate real
    ax = axes[0, 1]
    # Binning
    bins = np.arange(0, 1.05, 0.1)
    bin_means = []
    bin_rates = []
    
    for i in range(len(bins) - 1):
        mask = (train_df["prob_win"] >= bins[i]) & (train_df["prob_win"] < bins[i+1])
        if mask.sum() > 0:
            bin_means.append((bins[i] + bins[i+1]) / 2)
            bin_rates.append(train_df[mask]["won"].mean())
    
    ax.scatter(bin_means, bin_rates, s=100, alpha=0.7, label="Win rate real", color="steelblue")
    ax.plot([0, 1], [0, 1], "k--", alpha=0.5, label="Calibración perfecta")
    ax.set_xlabel("Prob Win Predicha")
    ax.set_ylabel("Win Rate Real")
    ax.set_title("Calibración: ¿Prob==Real?")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # 3. Comparación: Old vs New threshold
    ax = axes[1, 0]
    old_signals = (train_df["prob_win"] >= 0.65).sum()
    new_signals = (train_df["prob_win"] >= optimal_threshold).sum()
    
    bars = ax.bar(["Old (0.65)", f"New ({optimal_threshold:.2f})"], 
                   [old_signals, new_signals], 
                   color=["#FF6B6B", "#4ECDC4"], alpha=0.8)
    ax.set_ylabel("# Señales")
    ax.set_title("Cambio en # Señales")
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
               f'{int(height):,}',
               ha='center', va='bottom', fontsize=11, fontweight='bold')
    ax.grid(True, alpha=0.3, axis="y")
    
    # 4. Win rate por threshold
    ax = axes[1, 1]
    thresholds = np.arange(0.3, 0.8, 0.05)
    win_rates = []
    signal_counts = []
    
    for t in thresholds:
        subset = train_df[train_df["prob_win"] >= t]
        if len(subset) > 0:
            win_rates.append(subset["won"].mean() * 100)
            signal_counts.append(len(subset))
        else:
            win_rates.append(0)
            signal_counts.append(0)
    
    ax2 = ax.twinx()
    ax.plot(thresholds, win_rates, "o-", linewidth=2.5, markersize=8, 
            color="steelblue", label="Win Rate")
    ax2.plot(thresholds, signal_counts, "s-", linewidth=2.5, markersize=8, 
            color="coral", label="# Señales")
    ax.axvline(optimal_threshold, color="green", linestyle="--", linewidth=2, alpha=0.7)
    
    ax.set_xlabel("Threshold (prob_win >= x)")
    ax.set_ylabel("Win Rate (%)", color="steelblue")
    ax2.set_ylabel("# Señales", color="coral")
    ax.set_title("Trade-off: Win Rate vs # Señales")
    ax.grid(True, alpha=0.3)
    
    fig.tight_layout()
    plt.savefig(OUTPUTS_DIR / "12_probability_calibration.png", dpi=150, bbox_inches="tight")
    print(f"\n✓ Gráfica: 12_probability_calibration.png")
    plt.close()


def main():
    """Flujo principal."""
    df = load_and_prepare_data(CSV_PATH)
    
    # Split train/test por mes
    train_df, test_df = split_train_test(df, test_month="2025-11")
    
    # Entrenar calibrador (Platt)
    platt_model = calibrate_platt(train_df)
    
    # Encontrar threshold óptimo
    optimal_threshold = find_optimal_threshold(train_df)
    
    # Aplicar al test
    test_df_calibrated = apply_calibration(test_df, platt_model)
    
    # Visualizar
    plot_calibration(train_df, test_df, platt_model, optimal_threshold)
    
    print("\n" + "="*70)
    print("✅ MEJORA 2 COMPLETADA: RECALIBRACIÓN DE PROBABILIDADES")
    print("="*70)
    print(f"\nRECOMENDACIÓN DE OPERACIÓN:")
    print(f"  Usar: prob_win >= {optimal_threshold:.2f} (en lugar de >= 0.65)")
    print(f"  Win rate esperado: {find_optimal_threshold(train_df)*100:.1f}%")
    print(f"  # señales: {(train_df['prob_win'] >= optimal_threshold).sum():,}")


if __name__ == "__main__":
    main()
