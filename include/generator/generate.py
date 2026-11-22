"""Data oversampling layer: synthesises NEW monthly batches for source files 01, 05 and 06
(the Phase 1 sources) and drops them into data/landing/ as .xlsx so the watcher ingests them.

Why these volumes:
  * 05 sales   : annual volume grew 155k -> 165k -> 180k (+9.1% last year). We project 2026 as
                 180k x 1.091 = 196k, spread by calendar days -> ~16.7k rows for Jan, ~15.1k for Feb.
                 (Monthly volume in the real history is very spiky around Dec/Jan; we deliberately
                 smooth it so each refresh file stays small enough for a live demo.)
  * 06 hospital: exactly 12 hospitals x 63 medicines = 756 rows per month (the file's own grain).
  * 01 master  : 4 medicines get a price/cost change per refresh -> creates SCD Type 2 history.

Realism rules: every new sale re-uses a real (pharmacy, warehouse lot, batch, medicine) combination
from the last 180 days whose batch is still >= 30 days from expiry; prices come from the CURRENT
master data; discount/tax/COGS formulas are the ones found in the history; IDs continue the
existing sequences; a fixed seed makes every demo run reproducible.
"""
import calendar
import json
import os
import re
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd

from common.config import GENERATED, LANDING, RAW, TMP
from common.db import pg_conn

SEED_BASE = 20260000
FILES = {"master": "01_master_data", "sales": "05_pharmacy_sales_data", "hospital": "06_hospital_demand_data"}
SALES_INT = ["DeliveryQuantityPacks", "QuantitySoldPacks", "DaysToExpiryAtSale", "ReturnedQuantityPacks"]
SALES_FLOAT = ["UnitRetailPriceUSD", "GrossSalesAmountUSD", "DiscountAmountUSD", "NetSalesAmountUSD",
               "SalesTaxUSD", "CostOfGoodsSoldUSD", "GrossMarginUSD"]
NA = dict(keep_default_na=False, na_values=[""])


# --------------------------------------------------------------------------- planning
def month_start_for(refresh_no):
    """Refresh 1 -> 2026-01-01, refresh 2 -> 2026-02-01, ..."""
    k = refresh_no - 1
    return date(2026 + k // 12, k % 12 + 1, 1)


def _shift(d, months):
    y, m = d.year + (d.month - 1 + months) // 12, (d.month - 1 + months) % 12 + 1
    return date(y, m, 1)


def plan(refresh_no):
    ms = month_start_for(refresh_no)
    last = calendar.monthrange(ms.year, ms.month)[1]
    return {"refresh_no": refresh_no, "month_start": ms.isoformat(),
            "month_end": date(ms.year, ms.month, last).isoformat(),
            "seed": SEED_BASE + refresh_no}


def _generated_files(key, below_refresh):
    """CSV copies of earlier generated files (refresh < below_refresh) for this source."""
    out = []
    for f in sorted(GENERATED.glob(f"{FILES[key]}_refresh*.csv")):
        n = int(re.search(r"_refresh(\d+)_", f.name).group(1))
        if n < below_refresh:
            out.append(f)
    return out


def _out_name(key, refresh_no, ms):
    return f"{FILES[key]}_refresh{refresh_no}_{ms.strftime('%Y-%m')}"


def _write(df, key, refresh_no, ms):
    """Save a CSV copy (generator memory) and an .xlsx into landing via atomic rename."""
    GENERATED.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    LANDING.mkdir(parents=True, exist_ok=True)
    name = _out_name(key, refresh_no, ms)
    df.to_csv(GENERATED / f"{name}.csv", index=False)
    tmp = TMP / f"{name}.xlsx.part"
    df.to_excel(tmp, index=False, engine="xlsxwriter")
    os.replace(tmp, LANDING / f"{name}.xlsx")       # appears in landing fully written
    return LANDING / f"{name}.xlsx", name


def _current_master(refresh_no):
    """Latest version of each medicine, from the raw file + earlier generated deltas."""
    frames = [pd.read_csv(RAW / "01_master_data.csv")] + [pd.read_csv(f) for f in _generated_files("master", refresh_no + 1)]
    m = pd.concat(frames, ignore_index=True).sort_values(["MedicineID", "EffectiveFromDate"])
    return m.groupby("MedicineID", as_index=False).tail(1).reset_index(drop=True)


# --------------------------------------------------------------------------- 01 master
def generate_master(refresh_no):
    p = plan(refresh_no)
    ms = date.fromisoformat(p["month_start"])
    rng = np.random.default_rng(p["seed"])
    cur = _current_master(refresh_no - 1) if refresh_no > 1 else pd.read_csv(RAW / "01_master_data.csv")
    idx = np.sort(rng.choice(len(cur), size=4, replace=False))
    new = cur.iloc[idx].copy()
    ratio = new.RecommendedRetailPriceUSD / new.WholesalePriceUSD
    new["WholesalePriceUSD"] = (new.WholesalePriceUSD * (1 + rng.uniform(0.04, 0.10, len(new)))).round(2)
    new["RecommendedRetailPriceUSD"] = (new.WholesalePriceUSD * ratio).round(2)
    new["UnitManufacturingCostUSD"] = (new.UnitManufacturingCostUSD * (1 + rng.uniform(0.02, 0.05, len(new)))).round(2)
    new["EffectiveFromDate"] = ms.isoformat()
    path, name = _write(new.reset_index(drop=True), "master", refresh_no, ms)
    return {"file": path.name, "domain": "master", "rows": len(new), "period_start": p["month_start"],
            "period_end": p["month_end"],
            "details": {"changed_medicines": new.MedicineID.tolist(),
                        "new_wholesale": new.WholesalePriceUSD.tolist(),
                        "note": "price/cost change rows -> new SCD2 versions in dim_medicine"}}


# --------------------------------------------------------------------------- 05 sales
def _scan_sales_history(refresh_no, ms):
    pool_start = (ms - timedelta(days=180)).isoformat()
    counts, max_id, max_rx, pools = {}, 0, 0, []
    files = [RAW / "05_pharmacy_sales_data.csv"] + _generated_files("sales", refresh_no)
    for f in files:
        for ch in pd.read_csv(f, dtype=str, chunksize=200_000, low_memory=False, **NA):
            for ym, n in ch.SalesDate.str[:4].value_counts().items():
                counts[ym] = counts.get(ym, 0) + int(n)
            max_id = max(max_id, int(ch.SalesTransactionID.str[5:].astype(int).max()))
            rx = ch.PrescriptionID.dropna()
            if len(rx):
                max_rx = max(max_rx, int(rx.str[3:].astype(int).max()))
            pools.append(ch[ch.SalesDate >= pool_start])
    return counts, max_id, max_rx, pd.concat(pools, ignore_index=True)


def generate_sales(refresh_no):
    p = plan(refresh_no)
    ms = date.fromisoformat(p["month_start"])
    me = date.fromisoformat(p["month_end"])
    rng = np.random.default_rng(p["seed"] + 100)
    master = _current_master(refresh_no).set_index("MedicineID")
    year_counts, max_id, max_rx, pool = _scan_sales_history(refresh_no, ms)

    last_year = ms.year - 1
    yoy = year_counts[str(last_year)] / year_counts[str(last_year - 1)] - 1
    annual = year_counts[str(last_year)] * (1 + yoy)
    n_rows = int(round(annual / 365 * calendar.monthrange(ms.year, ms.month)[1]))

    pool = pool[pool.BatchExpiryDate >= (ms + timedelta(days=30)).isoformat()].reset_index(drop=True)
    t = pool.iloc[rng.integers(0, len(pool), n_rows)].reset_index(drop=True)

    # dates: uniform over the days of the month, time-of-day inherited from the template row
    days = rng.integers(0, (me - ms).days + 1, n_rows)
    sale_date = pd.Series([(ms + timedelta(days=int(d))).isoformat() for d in days])
    order = np.argsort(sale_date.values, kind="stable")
    t, sale_date = t.iloc[order].reset_index(drop=True), sale_date.iloc[order].reset_index(drop=True)

    # money: formulas learned from history (price = master retail, COGS/pack = wholesale price)
    hist_pct = ((pd.to_numeric(pool.DiscountAmountUSD) / pd.to_numeric(pool.GrossSalesAmountUSD))
                .groupby(pool.PromotionCode.fillna("NONE")).median().round(2))
    tax_rate = float((pd.to_numeric(pool.SalesTaxUSD) / pd.to_numeric(pool.NetSalesAmountUSD)).median().round(2))
    qty = pd.to_numeric(t.QuantitySoldPacks).astype(int)
    price = t.MedicineID.map(master.RecommendedRetailPriceUSD)
    whole = t.MedicineID.map(master.WholesalePriceUSD)
    gross = (qty * price).round(2)
    disc = (gross * t.PromotionCode.fillna("NONE").map(hist_pct).fillna(0.0)).round(2)
    net = (gross - disc).round(2)
    cogs = (qty * whole).round(2)

    out = t.copy()
    out["SalesTransactionID"] = [f"SALE-{max_id + 1 + i:09d}" for i in range(n_rows)]
    out["SalesDate"] = sale_date
    out["SalesTimestampUTC"] = sale_date + "T" + t.SalesTimestampUTC.str[11:]
    out["DaysToExpiryAtSale"] = (pd.to_datetime(t.BatchExpiryDate) - pd.to_datetime(sale_date)).dt.days
    out["UnitRetailPriceUSD"], out["GrossSalesAmountUSD"], out["DiscountAmountUSD"] = price, gross, disc
    out["NetSalesAmountUSD"], out["SalesTaxUSD"] = net, (net * tax_rate).round(2)
    out["CostOfGoodsSoldUSD"], out["GrossMarginUSD"] = cogs, (net - cogs).round(2)
    has_rx = t.PrescriptionID.notna().to_numpy()
    out["PrescriptionID"] = np.where(has_rx, [f"RX-{max_rx + k:09d}" for k in np.cumsum(has_rx)], None)

    cols = list(pd.read_csv(RAW / "05_pharmacy_sales_data.csv", nrows=0).columns)
    out = out[cols]
    for c in SALES_INT:
        out[c] = pd.to_numeric(out[c]).astype(int)
    for c in SALES_FLOAT:
        out[c] = pd.to_numeric(out[c]).astype(float)
    path, name = _write(out, "sales", refresh_no, ms)

    changed_meds = pd.read_csv(GENERATED / f"{_out_name('master', refresh_no, ms)}.csv").MedicineID.tolist() \
        if (GENERATED / f"{_out_name('master', refresh_no, ms)}.csv").exists() else []
    return {"file": path.name, "domain": "sales", "rows": len(out), "period_start": p["month_start"],
            "period_end": p["month_end"],
            "details": {"projected_annual_rows": round(annual), "yoy_growth_used": round(yoy, 4),
                        "template_pool_rows": int(len(pool)), "channel_mix": out.SalesChannel.value_counts().to_dict(),
                        "pharmacy_type_mix": out.PharmacyType.value_counts().to_dict(),
                        "net_sales_usd": round(float(out.NetSalesAmountUSD.sum()), 2),
                        "gross_margin_usd": round(float(out.GrossMarginUSD.sum()), 2),
                        "return_rate_pct": round(100 * float((out.ReturnFlag == "Y").mean()), 2),
                        "rows_on_repriced_medicines": int(out.MedicineID.isin(changed_meds).sum()),
                        "first_id": out.SalesTransactionID.iloc[0], "last_id": out.SalesTransactionID.iloc[-1]}}


# --------------------------------------------------------------------------- 06 hospital demand
def generate_hospital(refresh_no):
    p = plan(refresh_no)
    ms = date.fromisoformat(p["month_start"])
    rng = np.random.default_rng(p["seed"] + 200)
    hist = pd.concat([pd.read_csv(RAW / "06_hospital_demand_data.csv")] +
                     [pd.read_csv(f) for f in _generated_files("hospital", refresh_no)], ignore_index=True)
    key = ["HospitalID", "MedicineID"]
    at = lambda m: hist[hist.DemandMonth == m.isoformat()].set_index(key)   # noqa: E731
    py, py2, prev = at(_shift(ms, -12)), at(_shift(ms, -24)), at(_shift(ms, -1))
    py = py.sort_index()
    growth = (py.ForecastDemandPacks / py2.ForecastDemandPacks.reindex(py.index)).clip(0.95, 1.12).fillna(1.04)
    n = len(py)
    noise = lambda s: rng.normal(1.0, s, n)                                     # noqa: E731

    forecast = (py.ForecastDemandPacks * growth * noise(0.03)).round().clip(lower=1)
    requested = (forecast * (py.RequestedQuantityPacks / py.ForecastDemandPacks) * noise(0.02)).round()
    requested = np.maximum(requested, forecast)
    approved = np.minimum(requested, (requested * (py.ApprovedQuantityPacks / py.RequestedQuantityPacks) * noise(0.01)).round())
    received = np.minimum(approved, (approved * (py.ReceivedQuantityPacks / py.ApprovedQuantityPacks) * noise(0.02)).round())
    consumed = (forecast * (py.ConsumedQuantityPacks / py.ForecastDemandPacks) * noise(0.03)).round()
    dispensed = (consumed * (py.DispensedQuantityPacks / py.ConsumedQuantityPacks) * noise(0.01)).round()
    wastage = np.where(rng.random(n) < 0.01, rng.integers(1, 4, n), 0)
    emergency = (py.EmergencyRequestQuantityPacks * noise(0.2)).round().clip(lower=0)
    opening = prev.ClosingStockPacks.reindex(py.index)
    shortfall = np.maximum(0, dispensed + wastage - (opening + received))      # cannot dispense stock we don't have
    dispensed = dispensed - shortfall
    closing = opening + received - dispensed - wastage                          # identity found in the history
    stockout_days = np.where(shortfall > 0, np.minimum(10, np.ceil(shortfall / np.maximum(dispensed / 30, 1))), 0)

    # disease-level epidemiology: one factor per (hospital, disease) so all its medicines agree
    disease_factor = pd.Series(rng.normal(1.02, 0.03, len(py)), index=py.index)
    dkey = py.reset_index().set_index(["HospitalID", "DiseaseCategory"]).index
    fac = pd.Series(disease_factor.values, index=dkey)
    fac = fac.groupby(level=[0, 1]).transform("first").values

    out = py.copy().reset_index()
    out["DemandMonth"] = ms.isoformat()
    for col, val in [("EstimatedDiseaseCases", py.EstimatedDiseaseCases.values * fac),
                     ("DiseaseRelatedAdmissions", py.DiseaseRelatedAdmissions.values * fac),
                     ("OutpatientEncounters", py.OutpatientEncounters.values * fac),
                     ("ForecastDemandPacks", forecast.values), ("RequestedQuantityPacks", requested.values),
                     ("ApprovedQuantityPacks", approved.values), ("ReceivedQuantityPacks", received.values),
                     ("EmergencyRequestQuantityPacks", emergency.values), ("OpeningStockPacks", opening.values),
                     ("DispensedQuantityPacks", dispensed.values), ("ConsumedQuantityPacks", consumed.values),
                     ("WastageQuantityPacks", wastage), ("ClosingStockPacks", closing.values),
                     ("UnfulfilledDemandPacks", shortfall.values), ("StockoutDays", stockout_days),
                     ("AverageLeadTimeDays", np.maximum(1, py.AverageLeadTimeDays.values + rng.integers(-1, 2, n)))]:
        out[col] = np.round(val).astype(int)
    out["ServiceLevelPct"] = np.where(out.RequestedQuantityPacks > 0,
                                      100 * (1 - out.UnfulfilledDemandPacks / out.RequestedQuantityPacks), 100.0).round(2)
    out["MedicationRequestStatus"] = np.where(out.UnfulfilledDemandPacks > 0, "Partially fulfilled", "Completed")
    out["DemandTrendIndex"] = (py.DemandTrendIndex.values * noise(0.01)).round(3)
    max_id = int(hist.HospitalDemandRecordID.str[5:].astype(int).max())
    out = out.sort_values(key).reset_index(drop=True)
    out["HospitalDemandRecordID"] = [f"HDEM-{max_id + 1 + i:08d}" for i in range(len(out))]
    out = out[list(pd.read_csv(RAW / "06_hospital_demand_data.csv", nrows=0).columns)]
    path, name = _write(out, "hospital", refresh_no, ms)
    return {"file": path.name, "domain": "hospital_demand", "rows": len(out), "period_start": p["month_start"],
            "period_end": p["month_start"],
            "details": {"hospitals": int(out.HospitalID.nunique()), "medicines": int(out.MedicineID.nunique()),
                        "forecast_packs": int(out.ForecastDemandPacks.sum()),
                        "consumed_packs": int(out.ConsumedQuantityPacks.sum()),
                        "unfulfilled_packs": int(out.UnfulfilledDemandPacks.sum()),
                        "rows_with_stockout": int((out.StockoutDays > 0).sum()),
                        "opening_stock_chained_from": _shift(ms, -1).isoformat()}}


# --------------------------------------------------------------------------- logging
def log_generation(run_id, refresh_no, results):
    """Write rows to ops.generation_log and a JSON stats file (for the methodology report)."""
    conn = pg_conn()
    with conn, conn.cursor() as cur:
        for r in results:
            size = round((LANDING / r["file"]).stat().st_size / 1048576, 3) if (LANDING / r["file"]).exists() else \
                round((GENERATED / r["file"].replace(".xlsx", ".csv")).stat().st_size / 1048576, 3)
            cur.execute("""INSERT INTO ops.generation_log (run_id, refresh_no, file_name, source_domain,
                           rows_generated, period_start, period_end, file_size_mb, details)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (run_id, refresh_no, r["file"], r["domain"], r["rows"], r["period_start"],
                         r["period_end"], size, json.dumps(r["details"])))
    conn.close()
    GENERATED.mkdir(parents=True, exist_ok=True)
    (GENERATED / f"refresh{refresh_no}_stats.json").write_text(
        json.dumps({"run_id": run_id, "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "files": results}, indent=2))
    return sum(r["rows"] for r in results)
