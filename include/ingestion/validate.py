"""Row-level data validation for the ingestion layer.

Each domain has a list of rules. A rule looks at a DataFrame chunk (all columns are
strings, lower-case names) and returns a boolean Series (True = row is BAD) plus a
short reason. validate() returns:
    ok_mask  - rows that passed every rule
    reasons  - for each bad row, all the reasons joined with '; '

Rules follow the project spec: price > 0, valid dates, non-null SKU/keys.
Columns that are legitimately empty (e.g. hospitalid on a retail sale) are NOT rules.
"""
import pandas as pd

DATE_MIN = pd.Timestamp("2020-01-01")
DATE_MAX = pd.Timestamp("2030-12-31")


class SchemaMismatch(Exception):
    """The file's columns differ from the expected source schema -> whole batch fails."""


# ----------------------------------------------------------------------------- rule builders
def required(*cols):
    def rule(df, seen):
        bad = pd.Series(False, index=df.index)
        for c in cols:
            bad |= df[c].isna() | (df[c].astype(str).str.strip() == "")
        return bad, "missing required value in: " + ",".join(cols)
    return rule


def greater_than(col, limit=0.0):
    def rule(df, seen):
        v = pd.to_numeric(df[col], errors="coerce")
        return ~(v > limit), f"{col} must be a number > {limit}"
    return rule


def non_negative(*cols):
    def rule(df, seen):
        bad = pd.Series(False, index=df.index)
        for c in cols:
            bad |= ~(pd.to_numeric(df[c], errors="coerce") >= 0)
        return bad, "negative or non-numeric value in: " + ",".join(cols)
    return rule


def valid_date(col):
    def rule(df, seen):
        d = pd.to_datetime(df[col], errors="coerce", utc=True).dt.tz_localize(None)
        return ~((d >= DATE_MIN) & (d <= DATE_MAX)), f"{col} is not a valid date in 2020-2030"
    return rule


def unique_key(*cols):
    """Reject a repeated key inside the file (including across chunks of the same file)."""
    def rule(df, seen):
        key = df[cols[0]].astype(str) if len(cols) == 1 else df[list(cols)].astype(str).agg("|".join, axis=1)
        dup_in_chunk = key.duplicated(keep="first")
        dup_before = key.isin(seen)
        seen.update(key[~(dup_in_chunk | dup_before)].tolist())
        return dup_in_chunk | dup_before, "duplicate key in file: " + ",".join(cols)
    return rule


RULES = {
    "master": [required("medicineid"), unique_key("medicineid"),
               greater_than("wholesalepriceusd"), greater_than("recommendedretailpriceusd"),
               valid_date("effectivefromdate")],
    "sales": [required("salestransactionid", "medicineid", "pharmacyid"), unique_key("salestransactionid"),
              greater_than("unitretailpriceusd"), greater_than("quantitysoldpacks"),
              valid_date("salesdate")],
    "hospital_demand": [required("hospitaldemandrecordid", "hospitalid", "medicineid"),
                        unique_key("hospitaldemandrecordid"), valid_date("demandmonth"),
                        non_negative("forecastdemandpacks", "requestedquantitypacks",
                                     "consumedquantitypacks", "closingstockpacks")],
    # Phase 2 / 3 domains (rules ready now so the loader already handles all 7 files)
    "manufacturing": [required("manufacturingorderid", "productionbatchid", "medicineid"),
                      unique_key("manufacturingorderid"), valid_date("orderdate"),
                      non_negative("actualquantitypacks")],
    "delivery": [required("shipmentid", "shipmentlinenumber", "medicineid"),
                 unique_key("shipmentid", "shipmentlinenumber"), valid_date("dispatchdate"),
                 non_negative("shippedquantitypacks")],
    "warehouse": [required("inventorysnapshotid", "warehouselotid", "medicineid"),
                  unique_key("inventorysnapshotid"), valid_date("snapshotdate")],
    "iot": [required("sensorreadingid", "deviceid"), unique_key("sensorreadingid"),
            valid_date("eventtimestamputc")],
}


def check_schema(domain, columns, expected):
    missing = [c for c in expected if c not in columns]
    extra = [c for c in columns if c not in expected]
    if missing or extra:
        raise SchemaMismatch(f"schema mismatch for '{domain}': missing={missing[:6]} unexpected={extra[:6]}")


def validate(domain, df, seen):
    """Return (ok_mask, reasons) where reasons is a Series aligned to df.index."""
    bad_any = pd.Series(False, index=df.index)
    reasons = pd.Series("", index=df.index, dtype=object)
    for rule in RULES[domain]:
        bad, msg = rule(df, seen)
        bad_any |= bad
        reasons[bad] = reasons[bad].where(reasons[bad] == "", reasons[bad] + "; ") + msg
    return ~bad_any, reasons
