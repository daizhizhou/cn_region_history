#!/usr/bin/env python3
"""
Generate a normalized SQL dump of Chinese administrative regions
Combines modood/Administrative-divisions-of-China (dist/*.csv) and
xiangyuecn/AreaCity-JsSpider-StatsGov (ok_data_level4.csv) when available.

Usage:
  python scripts/generate_sql.py --data-year 2023 --output output/cn_regions_2026-07-15-2023.sql
"""
import argparse
import io
import os
import sys
import requests
import pandas as pd

# URLs (raw)
MOOD_BASE = "https://raw.githubusercontent.com/modood/Administrative-divisions-of-China/master/dist"
MOOD_FILES = {
    "provinces": f"{MOOD_BASE}/provinces.csv",
    "cities": f"{MOOD_BASE}/cities.csv",
    "areas": f"{MOOD_BASE}/areas.csv",
    "streets": f"{MOOD_BASE}/streets.csv",
    "villages": f"{MOOD_BASE}/villages.csv",
}
XIANG_OK4 = "https://raw.githubusercontent.com/xiangyuecn/AreaCity-JsSpider-StatsGov/master/src/%E9%87%87%E9%9B%86%E5%88%B0%E7%9A%84%E6%95%B0%E6%8D%AE/ok_data_level4.csv"

TIMEOUT = 30

def fetch_csv(url):
    try:
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        return pd.read_csv(io.StringIO(r.text), dtype=str)
    except Exception:
        return None

def normalize_modood(df, which):
    rows = []
    if df is None:
        return pd.DataFrame(rows)
    if which == "provinces":
        for _, r in df.iterrows():
            rows.append({
                "level":"province","code":str(r.get("code","")).strip(),
                "name":r.get("name",""), "parent_code":None,
                "pinyin":None,"ext_id":None,"source":"modood"
            })
    elif which == "cities":
        for _, r in df.iterrows():
            rows.append({
                "level":"city","code":str(r.get("code","")).strip(),
                "name":r.get("name",""), "parent_code":str(r.get("provinceCode","") or r.get("province","") or None),
                "pinyin":None,"ext_id":None,"source":"modood"
            })
    elif which == "areas":
        for _, r in df.iterrows():
            rows.append({
                "level":"area","code":str(r.get("code","")).strip(),
                "name":r.get("name",""), "parent_code":str(r.get("cityCode","") or r.get("areaCode","") or None),
                "pinyin":None,"ext_id":None,"source":"modood"
            })
    elif which == "streets":
        for _, r in df.iterrows():
            rows.append({
                "level":"street","code":str(r.get("code","")).strip(),
                "name":r.get("name",""), "parent_code":str(r.get("areaCode","") or None),
                "pinyin":None,"ext_id":None,"source":"modood"
            })
    elif which == "villages":
        for _, r in df.iterrows():
            rows.append({
                "level":"village","code":str(r.get("code","")).strip(),
                "name":r.get("name",""), "parent_code":str(r.get("townCode","") or None),
                "pinyin":None,"ext_id":None,"source":"modood"
            })
    return pd.DataFrame(rows)

def normalize_xiang(df):
    rows = []
    if df is None:
        return pd.DataFrame(rows)
    for _, r in df.iterrows():
        deep = r.get("deep")
        if pd.isna(deep):
            level = "unknown"
        else:
            try:
                d = int(str(deep))
            except:
                d = -1
            if d == 0: level="province"
            elif d == 1: level="city"
            elif d == 2: level="area"
            elif d == 3: level="street"
            else: level="other"
        rows.append({
            "level": level,
            "code": str(r.get("id","")).strip(),
            "name": r.get("name",""),
            "parent_code": str(r.get("pid","")) if not pd.isna(r.get("pid","")) else None,
            "pinyin": r.get("pinyin","") if "pinyin" in r else None,
            "ext_id": r.get("ext_id","") if "ext_id" in r else None,
            "source":"xiang"
        })
    return pd.DataFrame(rows)

def sql_escape(s):
    if s is None or (isinstance(s,float) and pd.isna(s)):
        return "NULL"
    t = str(s)
    t = t.replace("'", "''")
    return f"'{t}'"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-year", default="2023")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    # Attempt to load modood files
    dfs = {}
    for k, url in MOOD_FILES.items():
        print("Fetching", url, file=sys.stderr)
        df = fetch_csv(url)
        if df is None:
            print(f"Warning: failed to fetch {k} from {url}", file=sys.stderr)
        dfs[k] = df

    # Attempt xiang
    print("Fetching xiang ok_data_level4...", file=sys.stderr)
    xiang_df = fetch_csv(XIANG_OK4)
    if xiang_df is None:
        print("Warning: failed to fetch xiang ok_data_level4.csv", file=sys.stderr)

    parts = []
    parts.append(normalize_modood(dfs.get("provinces"), "provinces"))
    parts.append(normalize_modood(dfs.get("cities"), "cities"))
    parts.append(normalize_modood(dfs.get("areas"), "areas"))
    parts.append(normalize_modood(dfs.get("streets"), "streets"))
    parts.append(normalize_modood(dfs.get("villages"), "villages"))
    parts.append(normalize_xiang(xiang_df))

    df_all = pd.concat(parts, ignore_index=True, sort=False)
    # Drop empty codes
    df_all = df_all[df_all["code"].notna() & (df_all["code"].str.strip() != "")]
    # Deduplicate by code, prefer xiang (source == 'xiang') then modood
    df_all["priority"] = df_all["source"].map(lambda s: 0 if s=="xiang" else 1)
    df_all = df_all.sort_values(["code","priority"]).drop_duplicates(subset=["code"], keep="first")
    df_all = df_all.drop(columns=["priority"])

    # Prepare SQL file
    out_path = args.output
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("-- CN regions dump\n")
        f.write(f"-- data_year: {args.data_year}\n\n")
        f.write("CREATE TABLE IF NOT EXISTS cn_regions (\n")
        f.write("  level VARCHAR(16),\n")
        f.write("  code VARCHAR(64) PRIMARY KEY,\n")
        f.write("  name TEXT,\n")
        f.write("  parent_code VARCHAR(64),\n")
        f.write("  pinyin TEXT,\n")
        f.write("  ext_id VARCHAR(64),\n")
        f.write("  source VARCHAR(32),\n")
        f.write("  data_year VARCHAR(8)\n")
        f.write(") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n\n")

        # Write inserts in batches
        f.write("INSERT INTO cn_regions (level, code, name, parent_code, pinyin, ext_id, source, data_year) VALUES\n")
        values = []
        for _, r in df_all.iterrows():
            vals = [
                sql_escape(r.get("level")),
                sql_escape(r.get("code")),
                sql_escape(r.get("name")),
                sql_escape(r.get("parent_code")),
                sql_escape(r.get("pinyin")),
                sql_escape(r.get("ext_id")),
                sql_escape(r.get("source")),
                sql_escape(args.data_year),
            ]
            values.append("(" + ",".join(vals) + ")")
        if values:
            f.write(",\n".join(values) + ";\n")
        else:
            f.write(" -- no rows\n")

    print("Wrote SQL to", out_path, file=sys.stderr)

if __name__ == "__main__":
    main()
