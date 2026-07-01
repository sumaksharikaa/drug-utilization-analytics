"""
etl_pipeline.py
Drug Utilization & Formulary Analytics — ETL Pipeline (MySQL)
Extract → Validate → Transform → Load with reconciliation checks
"""

import pandas as pd
import numpy as np
import logging, os, sys
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("etl.log")],
)
log = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# ── try MySQL; fallback to SQLite for portability ────────────────────────────
try:
    import mysql.connector
    USE_MYSQL = True
except ImportError:
    import sqlite3
    USE_MYSQL = False
    log.warning("mysql-connector not found — using SQLite (run: pip install mysql-connector-python)")

DB_CONFIG = {
    "host":     os.getenv("DB_HOST",     "localhost"),
    "port":     int(os.getenv("DB_PORT", "3306")),
    "database": os.getenv("DB_NAME",     "drug_utilization_db"),
    "user":     os.getenv("DB_USER",     "root"),
    "password": os.getenv("DB_PASSWORD", ""),
}

VALID_PHARMACY_TYPES = {"Retail","Mail Order","Specialty"}
VALID_GENDERS        = {"M","F","Other"}
VALID_PA_OUTCOMES    = {"Approved","Denied","Pending","Appeal Approved"}
VALID_DAYS_SUPPLY    = {30,60,90}


class DrugUtilizationETL:
    def __init__(self):
        self.conn   = None
        self.cursor = None
        self.errors = []
        self.stats  = {}

    # ── connection ────────────────────────────────────────────────────────────
    def connect(self):
        if USE_MYSQL:
            log.info("Connecting to MySQL...")
            self.conn   = mysql.connector.connect(**DB_CONFIG)
            self.cursor = self.conn.cursor()
        else:
            log.info("Connecting to SQLite (fallback)...")
            db_path = os.path.join(os.path.dirname(__file__), "drug_utilization.db")
            self.conn   = sqlite3.connect(db_path)
            self.cursor = self.conn.cursor()
        log.info("Connected ✓")

    def disconnect(self):
        if self.cursor: self.cursor.close()
        if self.conn:   self.conn.close()

    # ── extract ───────────────────────────────────────────────────────────────
    def extract(self, filename):
        path = os.path.join(DATA_DIR, filename)
        log.info(f"Extracting {filename}...")
        df = pd.read_csv(path, low_memory=False)
        log.info(f"  → {len(df):,} rows")
        return df

    # ── validate helpers ──────────────────────────────────────────────────────
    def _flag(self, df, pk, cond, label):
        n = cond.sum()
        if n:
            log.warning(f"  ⚠ {label}: {n} rows")
            self.errors.append({"check": label, "count": int(n)})
        return df[~cond].copy()

    # ── transform ─────────────────────────────────────────────────────────────
    def transform_drugs(self, df):
        log.info("Transforming drugs...")
        df = df.drop_duplicates("drug_id")
        df["unit_cost_usd"] = pd.to_numeric(df["unit_cost_usd"], errors="coerce").fillna(0)
        df = self._flag(df,"drug_id", df["unit_cost_usd"]<=0,          "drugs: zero/negative cost")
        df = self._flag(df,"drug_id", df["formulary_tier"].isna(),      "drugs: missing tier")
        df["requires_prior_auth"] = df["requires_prior_auth"].astype(bool)
        df["is_specialty"]        = df["is_specialty"].astype(bool)
        df["is_cold_chain"]       = df["is_cold_chain"].astype(bool)
        df["ndc"]                 = df["ndc"].astype(str).str.strip()
        return df

    def transform_formulary(self, df):
        log.info("Transforming formulary...")
        df = df.drop_duplicates("formulary_id")
        df["effective_date"] = pd.to_datetime(df["effective_date"]).dt.date
        df["end_date"]       = pd.to_datetime(df["end_date"], errors="coerce").dt.date
        df["copay_pct"]      = pd.to_numeric(df["copay_pct"], errors="coerce").fillna(0)
        df["change_reason"]  = df["change_reason"].where(pd.notna(df["change_reason"]), None)
        return df

    def transform_members(self, df):
        log.info("Transforming members...")
        df = df.drop_duplicates("member_id")
        df["enrollment_date"] = pd.to_datetime(df["enrollment_date"]).dt.date
        df["is_active"]       = df["is_active"].astype(bool)
        df["age"]             = pd.to_numeric(df["age"], errors="coerce").fillna(0).astype(int)
        df = self._flag(df,"member_id", ~df["gender"].isin(VALID_GENDERS),   "members: invalid gender")
        df = self._flag(df,"member_id", (df["age"]<0)|(df["age"]>120),       "members: invalid age")
        return df

    def transform_prescriptions(self, df):
        log.info("Transforming prescriptions...")
        df = df.drop_duplicates("rx_id")
        df["service_date"]      = pd.to_datetime(df["service_date"]).dt.date
        df["total_cost_usd"]    = pd.to_numeric(df["total_cost_usd"],   errors="coerce").fillna(0)
        df["member_copay_usd"]  = pd.to_numeric(df["member_copay_usd"], errors="coerce").fillna(0)
        df["plan_paid_usd"]     = pd.to_numeric(df["plan_paid_usd"],    errors="coerce").fillna(0)
        df["quantity_dispensed"]= pd.to_numeric(df["quantity_dispensed"],errors="coerce").fillna(1).astype(int)
        df["refill_number"]     = pd.to_numeric(df["refill_number"],     errors="coerce").fillna(0).astype(int)
        df["is_generic"]        = df["is_generic"].astype(bool)
        df["days_supply"]       = pd.to_numeric(df["days_supply"], errors="coerce").fillna(30).astype(int)
        df.loc[~df["days_supply"].isin(VALID_DAYS_SUPPLY), "days_supply"] = 30
        df = self._flag(df,"rx_id", df["total_cost_usd"]<0,                  "rx: negative cost")
        df = self._flag(df,"rx_id", df["member_copay_usd"]>df["total_cost_usd"], "rx: copay > cost")

        # Reconciliation check
        calc_plan = (df["total_cost_usd"] - df["member_copay_usd"]).round(2)
        mismatch  = (abs(calc_plan - df["plan_paid_usd"]) > 0.02).sum()
        if mismatch:
            log.warning(f"  ⚠ Reconciliation: {mismatch} rows where plan_paid ≠ cost−copay — correcting")
            df["plan_paid_usd"] = calc_plan
        log.info(f"  Rx by pharmacy: {df['pharmacy_type'].value_counts().to_dict()}")
        return df

    def transform_prior_auth(self, df):
        log.info("Transforming prior auth requests...")
        df = df.drop_duplicates("pa_id")
        df["request_date"]  = pd.to_datetime(df["request_date"]).dt.date
        df["decision_date"] = pd.to_datetime(df["decision_date"], errors="coerce").dt.date
        df["days_to_decision"] = pd.to_numeric(df["days_to_decision"], errors="coerce")
        df["is_urgent"]     = df["is_urgent"].astype(bool)
        df["appeal_filed"]  = df["appeal_filed"].astype(bool)
        df["denial_reason"] = df["denial_reason"].where(pd.notna(df["denial_reason"]), None)
        df.loc[(df["outcome"]=="Denied") & df["denial_reason"].isna(), "denial_reason"] = "Unspecified"
        return df

    def transform_spend_summary(self, df):
        log.info("Transforming spend summary...")
        for col in ["total_cost","member_copay","plan_paid"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).round(2)
        df["rx_count"]       = pd.to_numeric(df["rx_count"],      errors="coerce").fillna(0).astype(int)
        df["unique_members"] = pd.to_numeric(df["unique_members"],errors="coerce").fillna(0).astype(int)
        return df

    # ── load ──────────────────────────────────────────────────────────────────
    def _load(self, table, df, cols, pk):
        if df.empty:
            log.warning(f"  No rows for {table}")
            return 0
        rows = [tuple(None if pd.isna(v) else v for v in row)
                for row in df[cols].itertuples(index=False)]
        ph   = ",".join(["%s"]*len(cols)) if USE_MYSQL else ",".join(["?"]*len(cols))
        col_str = ",".join(cols)
        if USE_MYSQL:
            sql = f"INSERT INTO {table} ({col_str}) VALUES ({ph}) ON DUPLICATE KEY UPDATE {', '.join(f'{c}=VALUES({c})' for c in cols if c!=pk)}"
        else:
            sql = f"INSERT OR REPLACE INTO {table} ({col_str}) VALUES ({ph})"
        self.cursor.executemany(sql, rows)
        self.conn.commit()
        log.info(f"  ✓ {table}: {len(rows):,} rows loaded")
        self.stats[table] = len(rows)
        return len(rows)

    # ── run ───────────────────────────────────────────────────────────────────
    def run(self):
        start = datetime.now()
        log.info("="*60)
        log.info("DRUG UTILIZATION ETL — STARTING")
        log.info("="*60)
        try:
            self.connect()
            self._load("drugs", self.transform_drugs(self.extract("drugs.csv")),
                ["drug_id","brand_name","generic_name","therapy_area","manufacturer",
                 "dosage_form","strength","ndc","unit_cost_usd","formulary_tier",
                 "requires_prior_auth","is_specialty","is_cold_chain",
                 "days_supply_limit","max_quantity_per_fill"], "drug_id")

            self._load("formulary", self.transform_formulary(self.extract("formulary.csv")),
                ["formulary_id","drug_id","formulary_tier","tier_name","copay_pct",
                 "effective_date","end_date","change_reason","plan_year"], "formulary_id")

            self._load("members", self.transform_members(self.extract("members.csv")),
                ["member_id","age","gender","state","plan_type",
                 "enrollment_date","is_active"], "member_id")

            self._load("prescriptions", self.transform_prescriptions(self.extract("prescriptions.csv")),
                ["rx_id","member_id","drug_id","prescriber_npi","service_date",
                 "days_supply","quantity_dispensed","formulary_tier","total_cost_usd",
                 "member_copay_usd","plan_paid_usd","pharmacy_type","refill_number",
                 "is_generic","therapy_area"], "rx_id")

            self._load("prior_auth_requests", self.transform_prior_auth(self.extract("prior_auth_requests.csv")),
                ["pa_id","rx_id","drug_id","member_id","request_date","decision_date",
                 "days_to_decision","outcome","denial_reason","is_urgent","appeal_filed"], "pa_id")

            self._load("drug_spend_summary", self.transform_spend_summary(self.extract("drug_spend_summary.csv")),
                ["month","drug_id","therapy_area","formulary_tier","pharmacy_type",
                 "rx_count","total_cost","member_copay","plan_paid","unique_members"], "summary_id" if USE_MYSQL else "month")

        except Exception as e:
            log.error(f"ETL failed: {e}")
            if self.conn: self.conn.rollback()
            raise
        finally:
            self.disconnect()

        elapsed = (datetime.now()-start).seconds
        log.info("="*60)
        log.info(f"ETL COMPLETE in {elapsed}s | Rows: {self.stats}")
        if self.errors:
            log.warning(f"DQ issues: {self.errors}")
        log.info("="*60)


if __name__ == "__main__":
    DrugUtilizationETL().run()
