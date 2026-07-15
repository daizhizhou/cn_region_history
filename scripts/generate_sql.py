"""Generate MySQL dump for China administrative divisions up to township level.

This script downloads open-source datasets (modood and xiangyuecn), merges them, and emits a MySQL-compatible SQL dump (utf8mb4) containing CREATE TABLE and INSERT statements.

Notes:
- Run: python generate_sql.py
- Output: output/cn_regions_2024.sql
"""

import os
import csv
import subprocess
import sys
from pathlib import Path
from urllib.parse import urljoin

try:
    import requests
    import pandas as pd
    from tqdm import tqdm
except Exception:
    print('Missing dependencies. Please run: pip install -r ../requirements.txt')
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / 'scripts'
DATA_DIR = ROOT / 'data'
OUTPUT_DIR = ROOT / 'output'

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Source URLs (modood project)
MOOD_BASE = 'https://github.com/modood/Administrative-divisions-of-China/raw/master/dist/'
MOOD_FILES = {
    'provinces': 'provinces.csv',
    'cities': 'cities.csv',
    'areas': 'areas.csv',
    'streets': 'streets.csv',
    'villages': 'villages.csv'
}

XIANG_REPO = 'https://github.com/xiangyuecn/AreaCity-JsSpider-StatsGov.git'
XIANG_LOCAL = DATA_DIR / 'AreaCity-JsSpider-StatsGov'

def download_modood():
    local_paths = {}
    for k, fname in MOOD_FILES.items():
        url = urljoin(MOOD_BASE, fname)
        local = DATA_DIR / fname
        if not local.exists():
            print(f'Downloading {url} -> {local}')
            r = requests.get(url, stream=True, timeout=60)
            r.raise_for_status()
            with open(local, 'wb') as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
        else:
            print(f'Using cached {local}')
        local_paths[k] = str(local)
    return local_paths

def clone_xiangyuecn():
    # Clone if not exists
    if not XIANG_LOCAL.exists():
        print('Cloning xiangyuecn repo for postal codes and coordinates...')
        subprocess.check_call(['git', 'clone', '--depth', '1', XIANG_REPO, str(XIANG_LOCAL)])
    else:
        print('Using cached xiangyuecn repo')
    # Try to find ok_data_level4.csv
    candidates = list(XIANG_LOCAL.glob('**/ok_data_level4.csv'))
    if not candidates:
        # try other common filenames
        candidates = list(XIANG_LOCAL.glob('**/*level4*.csv'))
    if not candidates:
        print('Warning: cannot find ok_data_level4.csv in xiangyuecn repo. Postal code merging may be limited.')
        return None
    return str(candidates[0])

def load_modood(paths):
    # load streets (township) and higher levels
    print('Loading modood CSVs...')
    streets = pd.read_csv(paths['streets'], dtype=str, keep_default_na=False)
    areas = pd.read_csv(paths['areas'], dtype=str, keep_default_na=False)
    cities = pd.read_csv(paths['cities'], dtype=str, keep_default_na=False)
    provinces = pd.read_csv(paths['provinces'], dtype=str, keep_default_na=False)
    # Normalize column names
    for df in [streets, areas, cities, provinces]:
        df.columns = [c.strip() for c in df.columns]
    return provinces, cities, areas, streets


def load_xiang(path):
    if not path:
        return None
    print('Loading xiangyuecn CSV for postal codes/coords...')
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        return df
    except Exception as e:
        print('Failed to read xiang CSV:', e)
        return None


def build_master(provinces, cities, areas, streets, xiang):
    # We'll create a unified DataFrame with columns matching the target schema
    cols = ['code', 'name', 'level', 'parent_code', 'postal_code', 'lon', 'lat', 'year', 'source']
    rows = []
    # provinces
    for _, r in provinces.iterrows():
        rows.append({'code': r['code'], 'name': r['name'], 'level': 1, 'parent_code': None, 'postal_code': None, 'lon': None, 'lat': None, 'year': 2023, 'source': 'modood_provinces_2023'})
    # cities
    for _, r in cities.iterrows():
        rows.append({'code': r['code'], 'name': r['name'], 'level': 2, 'parent_code': r.get('provinceCode') or r.get('province_code') or None, 'postal_code': None, 'lon': None, 'lat': None, 'year': 2023, 'source': 'modood_cities_2023'})
    # areas
    for _, r in areas.iterrows():
        rows.append({'code': r['code'], 'name': r['name'], 'level': 3, 'parent_code': r.get('cityCode') or r.get('city_code') or None, 'postal_code': None, 'lon': None, 'lat': None, 'year': 2023, 'source': 'modood_areas_2023'})
    # streets (township)
    for _, r in streets.iterrows():
        parent = r.get('areaCode') or r.get('area_code') or None
        rows.append({'code': r['code'], 'name': r['name'], 'level': 4, 'parent_code': parent, 'postal_code': None, 'lon': None, 'lat': None, 'year': 2023, 'source': 'modood_streets_2023'})

    df = pd.DataFrame(rows, columns=cols)

    # Merge postal codes and coordinates from xiang by matching full code or name+parent fallback
    if xiang is not None:
        xiang = xiang.copy()
        # Normalize common columns
        # xiang may contain columns like 'code','zip','lng','lat' or 'postcode'
        cand_code_cols = [c for c in xiang.columns if c.lower() in ('code','adcode','area_code')]
        cand_zip_cols = [c for c in xiang.columns if 'zip' in c.lower() or 'postcode' in c.lower() or 'postal' in c.lower()]
        cand_lon_cols = [c for c in xiang.columns if c.lower() in ('lng','lon','longitude')]
        cand_lat_cols = [c for c in xiang.columns if c.lower() in ('lat','latitude')]

        code_col = cand_code_cols[0] if cand_code_cols else None
        zip_col = cand_zip_cols[0] if cand_zip_cols else None
        lon_col = cand_lon_cols[0] if cand_lon_cols else None
        lat_col = cand_lat_cols[0] if cand_lat_cols else None

        if code_col:
            xiang_index = xiang.set_index(code_col)
            def enrich(row):
                code = row['code']
                if code in xiang_index.index:
                    r = xiang_index.loc[code]
                    pc = r.get(zip_col, None) if zip_col else None
                    lon = r.get(lon_col, None) if lon_col else None
                    lat = r.get(lat_col, None) if lat_col else None
                    return pd.Series([pc, lon, lat])
                return pd.Series([None, None, None])
            df[['postal_code','lon','lat']] = df.apply(enrich, axis=1)
        else:
            print('No code column found in xiang data; skipping direct code merge')

    return df


def emit_mysql(df, outpath):
    print('Emitting MySQL dump to', outpath)
    with open(outpath, 'w', encoding='utf-8') as f:
        f.write('-- MySQL dump generated by scripts/generate_sql.py
')
        f.write('SET NAMES utf8mb4;\n')
        f.write('SET FOREIGN_KEY_CHECKS = 0;\n\n')
        f.write('DROP TABLE IF EXISTS `admin_divisions`;\n')
        f.write('CREATE TABLE `admin_divisions` (\n')
        f.write('  `id` BIGINT NOT NULL AUTO_INCREMENT,\n')
        f.write('  `code` VARCHAR(24) NOT NULL,\n')
        f.write('  `name` VARCHAR(200) NOT NULL,\n')
        f.write('  `level` TINYINT NOT NULL,\n')
        f.write('  `parent_code` VARCHAR(24) DEFAULT NULL,\n')
        f.write('  `postal_code` VARCHAR(12) DEFAULT NULL,\n')
        f.write('  `lon` DOUBLE DEFAULT NULL,\n')
        f.write('  `lat` DOUBLE DEFAULT NULL,\n')
        f.write('  `year` SMALLINT NOT NULL DEFAULT 2024,\n')
        f.write('  `source` VARCHAR(255) DEFAULT NULL,\n')
        f.write('  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n')
        f.write('  PRIMARY KEY (`id`),\n')
        f.write('  UNIQUE KEY `uk_code_year` (`code`,`year`)\n')
        f.write(') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n\n')

        # Batch insert
        f.write('LOCK TABLES `admin_divisions` WRITE;\n')
        cols = ['code','name','level','parent_code','postal_code','lon','lat','year','source']
        batch = []
        for i, row in df.iterrows():
            vals = []
            for c in cols:
                v = row.get(c, None)
                if pd.isna(v) or v is None:
                    vals.append('NULL')
                else:
                    s = str(v).replace("'","\\'")
                    vals.append(f"'{s}'")
            batch.append('(' + ','.join(vals) + ')')
            if len(batch) >= 500:
                f.write('INSERT INTO `admin_divisions` (' + ','.join(['`'+c+'`' for c in cols]) + ') VALUES\n')
                f.write(',\n'.join(batch) + ';\n')
                batch = []
        if batch:
            f.write('INSERT INTO `admin_divisions` (' + ','.join(['`'+c+'`' for c in cols]) + ') VALUES\n')
            f.write(',\n'.join(batch) + ';\n')
        f.write('UNLOCK TABLES;\n')
    print('Done')


def main():
    print('Step 1: download modood')
    mood_paths = download_modood()

    print('Step 2: clone xiang repo')
    xiang_path = clone_xiangyuecn()

    print('Step 3: load data')
    provinces, cities, areas, streets = load_modood(mood_paths)
    xiang_df = load_xiang(xiang_path)

    print('Step 4: build master table')
    master = build_master(provinces, cities, areas, streets, xiang_df)

    print('Records assembled:', len(master))

    out = OUTPUT_DIR / 'cn_regions_2024.sql'
    emit_mysql(master, str(out))
    print('Output sql at', out)

if __name__ == '__main__':
    main()
