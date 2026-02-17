# Project Overview

## Resumen (ES)
Este repositorio presenta un sistema hibrido de trading cuantitativo con dos capas:
- Senales diarias basadas en modelos (RF/SVM/LSTM) para direccion y probabilidad.
- Ejecucion intradia con control de riesgo (SL-first, trailing ATR, break-even, holding).

Contribuciones clave:
- Pipeline reproducible para generar features, calibrar umbrales y validar por PnL.
- Monitoreo operativo con dashboard y utilidades para despliegue en RPi.
- Artefactos de evaluacion (backtests, reportes y validaciones mensuales).

## Summary (EN)
This repository presents a hybrid quantitative trading system with two layers:
- Daily signals from ML models (RF/SVM/LSTM) for direction and probability.
- Intraday execution with risk controls (SL-first, trailing ATR, break-even, holding).

Key contributions:
- Reproducible pipeline to build features, calibrate thresholds, and validate by PnL.
- Operational monitoring with a dashboard and RPi deployment utilities.
- Evaluation artifacts (backtests, reports, and monthly validations).

## System Components
- Data ingestion and feature engineering
- Model training and calibration
- Signal generation and risk gating
- Execution logic and monitoring
- Reporting and validation

## Ethics and Risk Note
This project is for research and paper-trading contexts. It is not financial advice.
