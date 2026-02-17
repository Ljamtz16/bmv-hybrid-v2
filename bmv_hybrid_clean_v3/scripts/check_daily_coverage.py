# scripts/check_daily_coverage.py
import argparse, os, csv, glob
from datetime import datetime, date

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data/daily", help="Carpeta con CSVs diarios por ticker")
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end",   required=True, help="YYYY-MM-DD (exclusivo o inclusivo; no importa para chequeo de presencia)")
    ap.add_argument("--date-col", default="date", help="Nombre de la columna de fecha (si aplica)")
    ap.add_argument("--sep", default=",", help="Separador del CSV")
    return ap.parse_args()

def detect_header_and_datecol(path, sep, date_col):
    with open(path, newline="", encoding="utf-8") as f:
        sn = f.readline().strip()
        hdr = sn.split(sep)
        # heurística: si primera fila parece encabezado
        if date_col in hdr:
            return True, hdr.index(date_col), hdr
        # si no hay encabezado, asumimos primera columna es la fecha
        return False, 0, None

def main():
    args = parse_args()
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end   = datetime.strptime(args.end,   "%Y-%m-%d").date()

    files = sorted(glob.glob(os.path.join(args.data_dir, "*.csv")))
    if not files:
        print(f"⚠️  No hay CSVs en {args.data_dir}")
        return

    total = 0
    with_window = 0
    examples_missing = []
    examples_ok = []

    for fp in files:
        total += 1
        try:
            has_hdr, date_idx, hdr = detect_header_and_datecol(fp, args.sep, args.date_col)
            found = False
            mind, maxd = None, None
            with open(fp, newline="", encoding="utf-8") as f:
                rdr = csv.reader(f, delimiter=args.sep)
                # salta header si lo detectamos
                if has_hdr:
                    next(rdr, None)
                for row in rdr:
                    if not row or len(row) <= date_idx:
                        continue
                    try:
                        d = datetime.strptime(row[date_idx][:10], "%Y-%m-%d").date()
                    except Exception:
                        continue
                    if mind is None or d < mind: mind = d
                    if maxd is None or d > maxd: maxd = d
                    if start <= d < end:
                        found = True
                if found:
                    with_window += 1
                    if len(examples_ok) < 5:
                        examples_ok.append((os.path.basename(fp), mind, maxd))
                else:
                    if len(examples_missing) < 5:
                        examples_missing.append((os.path.basename(fp), mind, maxd))
        except Exception as e:
            if len(examples_missing) < 5:
                examples_missing.append((os.path.basename(fp), None, None))

    print("==== Cobertura diaria ====")
    print(f"Carpeta: {args.data_dir}")
    print(f"Ventana: [{start} .. {end})")
    print(f"Archivos totales: {total}")
    print(f"Con datos en ventana: {with_window}  |  Sin datos: {total - with_window}")
    if examples_ok:
        print("\nEjemplos OK (min..max):")
        for n, mi, ma in examples_ok:
            print(f"  {n:32s}  {mi} .. {ma}")
    if examples_missing:
        print("\nEjemplos SIN 2025-09 (min..max detectado):")
        for n, mi, ma in examples_missing:
            print(f"  {n:32s}  {mi} .. {ma}")

if __name__ == "__main__":
    main()
