    #!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
convert_prob_model.py

Convierte/limpia un "modelo de probabilidad" guardado como dict/tuple/objeto para
producir un estimador sklearn utilizable en inferencia (que exponga predict_proba o predict).

Uso:
  python scripts/convert_prob_model.py --in models/prob_win_calibrated.joblib --out models/prob_win_clean.joblib
"""

import argparse
from pathlib import Path
import numpy as np
import joblib

# ---- Wrappers ligeros ----

class SigmoidProbWrapper:
    """Envuelve un estimador con decision_function(x) para exponer predict_proba estilo binario."""
    def __init__(self, base):
        self.base = base
    def fit(self, X, y=None):  # noqa
        return self
    def predict_proba(self, X):
        z = self.base.decision_function(X)
        p = 1.0 / (1.0 + np.exp(-z))
        p = np.clip(p, 1e-6, 1-1e-6)
        # devolver forma (n,2) estilo sklearn binario
        return np.stack([1.0 - p, p], axis=1)
    def predict(self, X):
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)

class Clip01ProbWrapper:
    """Envuelve un estimador que solo tiene predict(x) continuo, interpretándolo como probabilidad [0,1] con clip."""
    def __init__(self, base):
        self.base = base
    def fit(self, X, y=None):  # noqa
        return self
    def predict_proba(self, X):
        y = self.base.predict(X)
        p = np.clip(y, 0.0, 1.0)
        return np.stack([1.0 - p, p], axis=1)
    def predict(self, X):
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)

# ---- helpers ----

def unwrap(obj):
    """Intenta extraer un estimador usable desde dict/tuple/obj."""
    if isinstance(obj, dict):
        for k in ("model","estimator","clf","pipeline"):
            if k in obj:
                return obj[k]
        return None
    if isinstance(obj, (list, tuple)) and len(obj) > 0:
        return unwrap(obj[0]) or obj[0]
    return obj

def make_prob_estimator(raw):
    est = unwrap(raw)
    if est is None:
        return None
    # si ya tiene predict_proba, úsalo tal cual
    if hasattr(est, "predict_proba"):
        return est
    # si tiene decision_function, envolver con sigmoide
    if hasattr(est, "decision_function"):
        return SigmoidProbWrapper(est)
    # si tiene predict (continuo), envolver con clip 0..1
    if hasattr(est, "predict"):
        return Clip01ProbWrapper(est)
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="outp", required=True)
    args = ap.parse_args()

    inp = Path(args.inp); outp = Path(args.outp)
    est_raw = joblib.load(inp)
    est = make_prob_estimator(est_raw)
    if est is None:
        raise RuntimeError(f"No se pudo crear un estimador de probabilidad a partir de: {type(est_raw)}")

    outp.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(est, outp)
    print(f"✅ Modelo de probabilidad limpio guardado en: {outp}")

if __name__ == "__main__":
    main()
