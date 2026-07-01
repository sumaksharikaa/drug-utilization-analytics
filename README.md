# 💉 Drug Utilization & Formulary Analytics

[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)](https://python.org)
[![MySQL](https://img.shields.io/badge/MySQL-8.0-orange?logo=mysql)](https://mysql.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.35-red?logo=streamlit)](https://streamlit.io)
[![Plotly](https://img.shields.io/badge/Plotly-5.22-purple?logo=plotly)](https://plotly.com)

An end-to-end **Drug Utilization Management (DUM)** and **Formulary Analytics** pipeline covering plan spend analysis, formulary tier management, prior authorization tracking, and generic substitution opportunity identification. Built on MySQL with a full Python ETL pipeline and an interactive Streamlit dashboard.

---

## 🗂️ Project Structure

```
drug-utilization-analytics/
├── data/
│   └── generate_data.py            # Synthetic drug utilization data generator
├── sql/
│   ├── schema.sql                  # MySQL schema, stored procedure, view
│   └── analytics_queries.sql       # 11 KPI queries with CTEs & window functions
├── etl/
│   └── etl_pipeline.py             # ETL: Extract → Validate → Reconcile → Load
├── app/
│   └── app.py                      # Streamlit dashboard (5 tabs)
├── requirements.txt
└── README.md
```

---

## 🏗️ ER Model

```
    ┌──────────┐        ┌──────────────┐
    │  members │        │   formulary  │
    └────┬─────┘        └──────┬───────┘
         │ 1                   │ M
         │                     │
    ┌────▼─────────────────────▼───┐
    │          prescriptions       │◄──── drugs
    └────────────────┬─────────────┘
                     │ 1
              ┌──────▼────────────────┐
              │  prior_auth_requests  │
              └───────────────────────┘

                drug_spend_summary (aggregated monthly fact)
```

---

## 📊 Dashboard Features

| Tab | What it shows |
|---|---|
| **📈 Spend Trends** | Monthly plan spend by therapy area, tier utilization, top 10 drugs by spend |
| **💊 Formulary** | Interactive formulary explorer with tier/PA/therapy filters, cost by tier |
| **🔐 Prior Auth** | Outcome distribution, denial reasons, drug-level approval rates & turnaround |
| **🔄 Generic Opportunities** | Brand drugs eligible for generic switch, estimated plan savings |
| **🔎 Data Quality** | 6 automated DQ checks with pass/fail gauge |

---

## ⚙️ Setup & Run

### 1. Clone & install
```bash
git clone https://github.com/sumaksharikaa/drug-utilization-analytics.git
cd drug-utilization-analytics
pip install -r requirements.txt
```

### 2. Generate data
```bash
python data/generate_data.py
```

### 3. MySQL setup (optional — dashboard runs on CSV)
```bash
mysql -u root -p < sql/schema.sql

export DB_HOST=localhost
export DB_USER=root
export DB_PASSWORD=your_password
export DB_NAME=drug_utilization_db

python etl/etl_pipeline.py
```

### 4. Launch dashboard
```bash
streamlit run app/app.py
```

---

## 🔑 Key Technical Concepts

| Concept | Implementation |
|---|---|
| **MySQL Schema** | 6 tables with FK constraints, multi-column indexes, CHECK constraints |
| **Stored Procedure** | `sp_formulary_tier_impact()` — before/after tier change spend analysis |
| **Database View** | `vw_current_formulary` — active formulary with drug and tier details |
| **ETL Reconciliation** | Plan paid auto-corrected where `plan_paid ≠ total_cost − copay` |
| **Window Functions** | `NTILE()` for member spend deciles, `SUM() OVER()` for spend share |
| **Formulary Management** | Tier change history tracking with effective/end dates |
| **PA Tracking** | Approval rate, days to decision, denial reason analysis, appeal rate |
| **Generic Analysis** | Brand drug identification + estimated savings at generic pricing |

---

## 📈 Sample KPIs Tracked

- **Total Drug Spend & Plan Liability** — billed, plan paid, member copay
- **Generic Dispensing Rate** — % of Rx filled with generic
- **Formulary Tier Utilization** — volume and spend by tier 1–5
- **PA Approval Rate & Turnaround** — avg days to decision by drug
- **Generic Substitution Savings** — estimated plan savings if switched
- **High Utilizer Identification** — top 10% members by total drug spend

---

## 🗃️ Dataset

- **20** specialty & non-specialty drugs across 7 therapy areas
- **28** formulary records including tier change history
- **1,000** plan members across 15 states
- **5,000** prescriptions (2022–2024)
- **2,047** prior authorization requests
- **1,939** monthly spend summary records

---

## 🔗 Related Projects

- [Specialty Pharmacy Claims Analytics](https://github.com/sumaksharikaa/sp-claims-analytics)
- [Healthcare Data Quality & Governance Pipeline](https://github.com/sumaksharikaa/healthcare-dq-governance)
- [Pharmacy Readmission Risk Predictor](https://github.com/sumaksharikaa/pharmacy-readmission-risk)

---

*Built by [Sumaksharika Nainavarapu](https://sumaksharika.com) · B.S. Pharmacy · M.S. Health Informatics & Analytics*
