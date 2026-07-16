#!/usr/bin/env python3
"""
Playwright-based scraper for KFC China official site.

Behaviour:
- Launch headless Chromium
- Navigate to KFC store locator / store list page
- Listen to all network responses; if responses include JSON with store lists, save them
- If no network JSON found, wait page render and extract store info from DOM elements
- Normalize fields and write a MySQL dump (similar schema to earlier)

Requirements:
- pip install playwright pandas
- playwright install
Usage:
  python scripts/fetch_kfc_playwright.py --output output/kfc_playwright_2026-07-15.sql
"""
import argparse, os, json, time, datetime
from playwright.sync_api import sync_playwright
import pandas as pd

# Adjust target page (store locator). If different, update this URL after you confirm with DevTools.
START_URL = "http://www.kfc.com.cn/kfccda/Discover/Default.aspx"  # or storelist URL

def try_extract_from_response_body(body_text):
    try:
        j = json.loads(body_text)
    except Exception:
        return None
    # heuristic: look for a list of store objects, e.g., presence of keys like 'storeName' or 'Table1'
    if isinstance(j, dict):
        if "Table1" in j and isinstance(j["Table1"], list):
            return j["Table1"]
        # sometimes API returns list directly
        for k in ("data","stores","list","result","rows"):
            if k in j and isinstance(j[k], list):
                return j[k]
    elif isinstance(j, list):
        # array of objects
        return j
    return None

def normalize_raw_item(it):
    # similar to earlier mapping; tolerant to many key names
    def pick(d, keys):
        for k in keys:
            if k in d and d[k] not in (None, ""):
                return d[k]
        return None
    POSS_ID = ["storeId","StoreId","id","ID","storeID"]
    POSS_NO = ["storeNo","StoreNo","serialNo","store_number"]
    POSS_NAME = ["storeName","StoreName","name"]
    POSS_PHONE = ["telephone","tel","phone","contact"]
    POSS_PROV = ["provinceName","province"]
    POSS_CITY = ["cityName","city"]
    POSS_ADDR = ["addressDetail","address","addr"]
    POSS_TAG = ["pro","service","tag","facility"]
    POSS_LON = ["lng","lon","longitude","pointY"]
    POSS_LAT = ["lat","latitude","pointX"]
    def first(keys): return pick(it, keys)
    # build normalized dict
    store_id = first(POSS_ID)
    store_no = first(POSS_NO)
    name = first(POSS_NAME)
    phone = first(POSS_PHONE)
    province = first(POSS_PROV)
    city = first(POSS_CITY)
    address = first(POSS_ADDR)
    tag_raw = first(POSS_TAG)
    # coords
    lon = first(POSS_LON)
    lat = first(POSS_LAT)
    location = None
    try:
        if lon is not None and lat is not None:
            location = f"{float(lon):.6f},{float(lat):.6f}"
    except Exception:
        location = None
    tags = None
    if tag_raw:
        if isinstance(tag_raw, list):
            tags = ",".join(map(str, tag_raw))
        else:
            tags = str(tag_raw).replace("，",",")
    return {
        "store_id": store_id,
        "store_no": store_no,
        "location": location,
        "name": name,
        "phone": phone,
        "province": province,
        "city": city,
        "address": address,
        "tag": tags,
        "raw": json.dumps(it, ensure_ascii=False)
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--headful", action="store_true", help="run with browser visible for debugging")
    args = parser.parse_args()

    collected = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headful)
        context = browser.new_context()
        page = context.new_page()

        # collect candidate JSON responses
        json_candidates = []

        def on_response(response):
            try:
                url = response.url
                # filter for likely endpoints; we capture everything and heuristically analyze
                ct = response.headers.get("content-type","")
                if "application/json" in ct or url.lower().endswith(".ashx") or "/ashx/" in url.lower():
                    try:
                        body = response.text()
                        stores = try_extract_from_response_body(body)
                        if stores:
                            print("Captured candidate JSON response from", url)
                            json_candidates.append((url, stores))
                    except Exception:
                        pass
            except Exception:
                pass

        page.on("response", on_response)

        print("Navigating to", START_URL)
        page.goto(START_URL, wait_until="domcontentloaded", timeout=60000)

        # let page load and fire any XHRs
        time.sleep(3)

        # If JSON candidates were captured, normalize them
        if json_candidates:
            for url, stores in json_candidates:
                for it in stores:
                    try:
                        norm = normalize_raw_item(it)
                        collected.append(norm)
                    except Exception:
                        continue
        else:
            # DOM fallback: try to locate store list elements
            # Generic heuristics: look for elements that look like store cards
            print("No JSON XHR captured; attempting DOM extraction fallback.")
            # Wait for some typical list container selectors
            time.sleep(2)
            # Try a few selectors commonly used
            selectors = [
                ".storelist .item", ".store-list .store", ".storeList li", ".list-box .list-item",
                ".search-results .result", ".stores-list .stores-item"
            ]
            nodes = None
            for sel in selectors:
                nodes = page.query_selector_all(sel)
                if nodes and len(nodes) > 0:
                    print("Found DOM nodes with selector", sel, "count", len(nodes))
                    break
            if not nodes:
                # fallback to any element with storeName text
                nodes = page.query_selector_all("li,div")
            # extract text heuristics
            for node in nodes:
                try:
                    text = node.inner_text().strip()
                    if not text or len(text.splitlines()) < 1:
                        continue
                    # crude parse: get lines and try map lines to fields
                    lines = [l.strip() for l in text.splitlines() if l.strip()]
                    # heuristic mapping
                    name = lines[0] if lines else None
                    addr = lines[1] if len(lines) > 1 else None
                    phone = None
                    for ln in lines:
                        if any(ch.isdigit() for ch in ln) and ("电话" in ln or "：" in ln or "-" in ln):
                            phone = ln
                    norm = {
                        "store_id": None,
                        "store_no": None,
                        "location": None,
                        "name": name,
                        "phone": phone,
                        "province": None,
                        "city": None,
                        "address": addr,
                        "tag": None,
                        "raw": json.dumps({"dom_text": text}, ensure_ascii=False)
                    }
                    collected.append(norm)
                except Exception:
                    continue

        browser.close()

    # dedupe by store_no or name+address
    seen = set(); rows=[]
    for r in collected:
        key = r.get("store_no") or (r.get("name") or "") + "|" + (r.get("address") or "")
        if not key:
            key = r.get("raw")
        if key in seen: continue
        seen.add(key); rows.append(r)

    df = pd.DataFrame(rows)
    if df.empty:
        print("No stores extracted. Consider running with --headful and inspecting network in the interactive browser.", flush=True)
        return

    # write MySQL dump
    out = args.output
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with open(out, "w", encoding="utf-8") as f:
        f.write("-- KFC China stores (Playwright)\n-- generated_at: %s\n\n" % now)
        f.write("""CREATE TABLE IF NOT EXISTS kfc_stores (
  store_id VARCHAR(64),
  store_no VARCHAR(64),
  location VARCHAR(64),
  name TEXT,
  phone VARCHAR(64),
  province VARCHAR(64),
  city VARCHAR(64),
  address TEXT,
  tag TEXT,
  raw JSON,
  fetched_at DATETIME,
  PRIMARY KEY (store_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n\n""")
        f.write("INSERT INTO kfc_stores (store_id, store_no, location, name, phone, province, city, address, tag, raw, fetched_at) VALUES\n")
        vals=[]
        for _,r in df.iterrows():
            def esc(x):
                if x is None or (isinstance(x,float) and pd.isna(x)): return "NULL"
                s=str(x).replace("'", "''")
                return f"'{s}'"
            row = [
                esc(r.get("store_id")),
                esc(r.get("store_no")),
                esc(r.get("location")),
                esc(r.get("name")),
                esc(r.get("phone")),
                esc(r.get("province")),
                esc(r.get("city")),
                esc(r.get("address")),
                esc(r.get("tag")),
                esc(r.get("raw")),
                f"'{now}'"
            ]
            vals.append("(" + ",".join(row) + ")")
        if vals:
            f.write(",\n".join(vals) + ";\n")
        else:
            f.write("-- no rows\n")
    print("Wrote SQL to", out)
