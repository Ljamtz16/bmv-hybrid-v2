# scripts/01_download_data.py
from __future__ import annotations
import argparse, sys, subprocess
from pathlib import Path

def ensure_src_on_syspath():
    """
    Inserta en sys.path el directorio raíz que contiene /src.
    Sube desde /scripts hasta encontrar 'src'.
    """
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "src").is_dir():
            if str(parent) not in sys.path:
                sys.path.insert(0, str(parent))
            return parent
    # Si no encontró /src, deja como está
    return here.parent

def load_downloader():
    """
    Devuelve una función callable para bajar datos si existe en src.io.download.
    Prueba varios nombres comunes. Si no encuentra, devuelve None.
    """
    try:
        import src.io.download as mod  # type: ignore
    except Exception as e:
        print(f"⚠️ No pude importar src.io.download directamente: {e}")
        return None

    for name in ("download", "download_all", "main", "run", "cli", "fetch"):
        fn = getattr(mod, name, None)
        if callable(fn):
            print(f"✅ Usando función '{name}' de src.io.download")
            return fn
    print("⚠️ src.io.download se importó, pero no encontré ninguna función conocida (download / download_all / main / run / cli / fetch).")
    return None

def run_module_as_script(py_exe: str):
    """Fallback: ejecutar el módulo como script: python -m src.io.download"""
    cmd = [py_exe, "-m", "src.io.download"]
    print("\n▶ Fallback: ejecutando módulo como script:", " ".join(cmd))
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        raise SystemExit(f"❌ Falló: python -m src.io.download (code {proc.returncode})")

def main():
    ap = argparse.ArgumentParser(description="Descarga/actualiza datos crudos (wrapper robusto).")
    ap.add_argument("--python", default=str((Path(".venv") / "Scripts" / "python.exe").resolve()),
                    help="Ruta a python.exe (default .venv/Scripts/python.exe)")
    args, unknown = ap.parse_known_args()  # deja pasar flags adicionales al downloader si existen

    project_root = ensure_src_on_syspath()
    print(f"• Project root: {project_root}")

    # Intenta función directa
    fn = load_downloader()
    if fn is not None:
        # Llama la función, pasando args desconocidos si acepta
        try:
            # Intenta con (args) si la función acepta argumentos; si no, sin args
            try:
                return fn(*unknown)
            except TypeError:
                return fn()
        except SystemExit as e:
            # Propaga código de salida de funciones que llaman sys.exit
            if e.code and e.code != 0:
                raise
            return

    # Fallback: ejecutar como módulo (permite que el módulo maneje sus propios flags)
    run_module_as_script(args.python)

if __name__ == "__main__":
    main()
