import argparse, json, os, copy, hashlib, datetime


def _load(path):
    # Use utf-8-sig to handle potential BOM from Windows PowerShell Set-Content -Encoding utf8
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def _deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if k == "month":
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def resolve_policy(month: str,
                   base_path: str = "policies/Policy_Base.json",
                   monthly_dir: str = "policies/monthly") -> dict:
    base = _load(base_path)
    month_file = os.path.join(monthly_dir, f"Policy_{month}.json")
    if os.path.exists(month_file):
        monthly = _load(month_file)
        merged = _deep_merge(base, monthly)
        src = {"base": base_path, "monthly": month_file}
    else:
        merged = base
        src = {"base": base_path, "monthly": None}

    payload = json.dumps(merged, sort_keys=True).encode("utf-8")
    sha = hashlib.sha1(payload).hexdigest()
    merged["_meta"] = {
        "_source": src,
        "_hash": sha,
        # Prefer timezone-aware UTC timestamps
        "_created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    return merged


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    pol = resolve_policy(args.month)
    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(pol, f, indent=2)
        print(f"[policy] Resuelta -> {args.out}")
    else:
        print(json.dumps(pol, indent=2))
