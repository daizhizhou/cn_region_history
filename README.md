# cn_region_history

This repository contains scripts to assemble China's administrative division data (up to 乡镇/街道) into a MySQL dump (utf8mb4). It uses open-source sources (modood and xiangyuecn) to build a consolidated SQL file covering data up to 2024 where available.

Contents:
- scripts/generate_sql.py : Download sources, merge them, and produce cn_regions_2024.sql (MySQL dump).
- data/sample_cn_regions_2024_sample.sql : small sample SQL with first ~200 rows to preview schema.
- README.md : instructions, data sources, license.
- requirements.txt : Python dependencies.

Notes:
- I cannot create the GitHub repo for you, but you created it and I committed these files to branch `data-import`.
- The generator script downloads the authoritative modood dataset (latest public, 2023) and the xiangyuecn AreaCity dataset (township-level postal codes and coordinates) and attempts to merge them by administrative code. Where 2024 official snapshots are unavailable, the script will mark source accordingly.

Run instructions (quick):
1. Clone your repo and switch to branch `data-import`.
2. Install dependencies: `pip install -r requirements.txt`.
3. Run: `python scripts/generate_sql.py`
4. Output: `output/cn_regions_2024.sql` (utf8mb4 MySQL dump). A sample output is included at data/sample_cn_regions_2024_sample.sql.
