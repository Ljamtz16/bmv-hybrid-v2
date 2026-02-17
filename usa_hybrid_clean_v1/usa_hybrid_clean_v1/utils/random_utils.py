import os
import random
import numpy as np

DEFAULT_SEED = 42

def get_global_seed(default: int = DEFAULT_SEED) -> int:
    """
    Devuelve la semilla global:
    - Prioriza variable de entorno SEED.
    - Si no existe, usa el valor por defecto (42).
    """
    env_seed = os.environ.get("SEED")
    if env_seed is not None:
        try:
            return int(env_seed)
        except ValueError:
            pass
    return default

def set_global_seed(seed: int | None = None) -> int:
    """
    Fija la semilla en random y numpy y la devuelve.
    """
    if seed is None:
        seed = get_global_seed()
    np.random.seed(seed)
    random.seed(seed)
    return seed
