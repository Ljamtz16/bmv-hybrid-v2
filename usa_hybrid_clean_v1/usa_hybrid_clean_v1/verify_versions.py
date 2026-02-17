import joblib
import os
from pathlib import Path

print("=" * 60)
print("VERIFICACIÓN DE VERSIONES — MODELOS vs RUNTIME")
print("=" * 60)

# Runtime actual
import sklearn, numpy, pandas, xgboost, catboost
print("\n[RUNTIME ACTUAL]")
print(f"  scikit-learn: {sklearn.__version__}")
print(f"  joblib:       {joblib.__version__}")
print(f"  numpy:        {numpy.__version__}")
print(f"  pandas:       {pandas.__version__}")
print(f"  xgboost:      {xgboost.__version__}")
print(f"  catboost:     {catboost.__version__}")

# Modelos entrenados
model_dir = Path("models/direction/")
models = ["rf.joblib", "xgb.joblib", "cat.joblib", "meta.joblib"]

print("\n[MODELOS — VERSIONES DE ENTRENAMIENTO]")
for model_file in models:
    path = model_dir / model_file
    if path.exists():
        model = joblib.load(path)
        size_mb = os.path.getsize(path) / (1024 * 1024)
        
        # Extraer sklearn version desde múltiples fuentes
        sklearn_ver = None
        
        # 1) Atributo directo _sklearn_version
        if hasattr(model, '_sklearn_version'):
            sklearn_ver = model._sklearn_version
        
        # 2) Atributo __sklearn_version__ (alternativo)
        elif hasattr(model, '__sklearn_version__'):
            sklearn_ver = model.__sklearn_version__
        
        # 3) Si es dict (a veces guardan metadata wrapeada)
        elif isinstance(model, dict):
            sklearn_ver = model.get('sklearn_version') or model.get('_sklearn_version', 'N/A (dict)')
            print(f"  {model_file:15s} type=dict, keys={list(model.keys())}")
        
        # 4) Intentar desde __getstate__ (pickle state)
        elif hasattr(model, '__getstate__'):
            try:
                state = model.__getstate__()
                if isinstance(state, dict):
                    sklearn_ver = state.get('_sklearn_version') or state.get('sklearn_version')
            except:
                pass
        
        # 5) Para XGBoost/CatBoost nativos (no sklearn wrappers)
        if sklearn_ver is None:
            model_type = str(type(model).__name__)
            if 'xgboost' in model_type.lower() or 'XGB' in model_type:
                sklearn_ver = 'N/A (native XGB)'
            elif 'catboost' in model_type.lower() or 'CatBoost' in model_type:
                sklearn_ver = 'N/A (native CAT)'
            else:
                sklearn_ver = f'N/A (type={model_type})'
        
        print(f"  {model_file:15s} sklearn={str(sklearn_ver):20s} size={size_mb:.2f}MB")
    else:
        print(f"  {model_file:15s} NOT FOUND")

print("\n[VERIFICACIÓN]")
runtime_ver = sklearn.__version__
model_ver = getattr(joblib.load(model_dir / "rf.joblib"), '_sklearn_version', 'unknown')
if runtime_ver == model_ver:
    print(f"  OK MATCH: Runtime {runtime_ver} == Model {model_ver}")
else:
    print(f"  WARN MISMATCH: Runtime {runtime_ver} != Model {model_ver}")

print("\n" + "=" * 60)
