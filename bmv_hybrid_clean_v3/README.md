    # BMV Hybrid V2 - Clean Zero (v3)

    ![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
    ![CITATION.cff](https://img.shields.io/badge/Cite-CITATION.cff-orange.svg)

   Hybrid Quantitative Trading Architecture with Supervised Machine Learning
    Independent Research Project - Quantitative Finance and Machine Learning

    ---

    ## Abstract

    This repository presents a hybrid quantitative trading system applied to the Mexican Stock Exchange (BMV). The architecture integrates supervised machine learning models for daily signal generation and a structured intraday execution layer with dynamic risk management.

    The methodological framework includes feature engineering, probabilistic threshold calibration based on PnL optimization, walk-forward validation, and Monte Carlo robustness testing. Performance evaluation is conducted using Sharpe ratio, maximum drawdown, and win-rate stability across market regimes.

    This project is structured as an independent research initiative in quantitative machine learning, systematic trading, and applied statistical modeling.

    ---

    ## Research Objectives

    - Develop a reproducible ML-driven trading architecture.
    - Implement probabilistic gating to improve signal quality.
    - Apply walk-forward validation to reduce overfitting risk.
    - Quantify robustness using Monte Carlo simulation.
    - Design an adaptive risk management framework.

    ---

    ## System Architecture

    The system is structured in two main layers:

    ### 1. Daily Signal Layer
    - Feature engineering from OHLCV data.
    - Technical indicators and volatility metrics.
    - Random Forest-based probability estimation.
    - Threshold calibration using historical PnL optimization.

    ### 2. Intraday Execution Layer
    - Adaptive Take-Profit / Stop-Loss logic.
    - Position sizing based on probabilistic confidence.
    - Risk filtering under lateral market regimes.
    - Continuous monitoring deployment (Desktop + Raspberry Pi).

    For detailed architecture, see:
    - [ARCHITECTURE.md](ARCHITECTURE.md)
    - [docs/STRUCTURE.md](docs/STRUCTURE.md)

    ---

    ## Methodology

    1. Data acquisition and preprocessing (daily and intraday bars)
    2. Feature engineering (technical indicators, volatility filters, regime detection)
    3. Model training (Random Forest + probabilistic gating)
    4. Threshold calibration via historical PnL optimization
    5. Walk-forward validation across rolling windows
    6. Risk management integration
    7. Performance evaluation using:

    - Sharpe Ratio
    - Maximum Drawdown
    - Win Rate
    - Monte Carlo Simulation

    ---

    ## Performance Snapshot (Research Simulation)

    - Average simulated monthly return (walk-forward validation): 13-15%
    - Estimated Sharpe ratio: ~1.6
    - Maximum drawdown: <15%
    - Win rate: ~58%
    - Walk-forward validation across multi-year data

    Note: Metrics are reported from historical simulations and are sensitive to data coverage, assumptions, and regime selection. They are not indicative of future performance.

    ---

    ## Reproducibility

    To reproduce results:

    ### Install dependencies
    ```
    python -m venv .venv
    .venv\Scripts\python -m pip install -r requirements.txt
    ```

    ### Run core pipeline
    ```
    python scripts/01_download_data.py
    python scripts/02_build_features.py
    python scripts/04_generate_signals.py
    python scripts/05_calibrate_thresholds.py
    python scripts/06_backtest_eval.py
    ```

    Data and trained models are excluded from version control for size and security reasons.

    For reproducibility details, see:
    - [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md)

    ---

    ## Project Structure

    ```
    data/
    raw/
        1d/
        1h/
    models/
    reports/
    config/
    scripts/
    docs/
    ```

    ---

    ## Deployment

    The system is designed for:

    - Research simulation environment
    - Desktop execution
    - Raspberry Pi monitoring node

    Operational details available in:
    - [ARCHITECTURE.md](ARCHITECTURE.md)
    - [INDEX.md](INDEX.md)

    ---

    ## Ethical and Research Disclaimer

    This repository is intended for research and educational purposes only. It does not constitute financial advice. All simulations are based on historical data and involve assumptions that may not hold under live market conditions.

    ---

    ## Author

    Luis Jesus Aleman Martinez
    Tecnologico de Monterrey
    2025
    Independent Research Project - Quantitative Machine Learning
