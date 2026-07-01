"""
generate_data.py
Generates synthetic Drug Utilization & Formulary Analytics data.
Tables: drugs, formulary, members, prescriptions, prior_auth_requests, drug_spend_summary
"""

import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta
import os

random.seed(99)
np.random.seed(99)

OUT = os.path.dirname(__file__)

DRUGS = [
    ("DRG001","Humira",       "Adalimumab",        "Immunology",      "AbbVie",      "Injection","40mg",  6500,4,True, True),
    ("DRG002","Enbrel",       "Etanercept",         "Immunology",      "Pfizer",      "Injection","50mg",  5800,4,True, True),
    ("DRG003","Lipitor",      "Atorvastatin",       "Cardiology",      "Pfizer",      "Tablet",   "20mg",    12,1,False,False),
    ("DRG004","Crestor",      "Rosuvastatin",       "Cardiology",      "AstraZeneca", "Tablet",   "10mg",    18,2,False,False),
    ("DRG005","Metformin",    "Metformin HCl",      "Diabetes",        "Generic",     "Tablet",   "500mg",    4,1,False,False),
    ("DRG006","Januvia",      "Sitagliptin",        "Diabetes",        "Merck",       "Tablet",   "100mg",   85,3,False,False),
    ("DRG007","Ozempic",      "Semaglutide",        "Diabetes",        "Novo Nordisk","Injection","1mg",   850,3,True, False),
    ("DRG008","Keytruda",     "Pembrolizumab",      "Oncology",        "Merck",       "Injection","200mg",22000,5,True, True),
    ("DRG009","Eliquis",      "Apixaban",           "Cardiology",      "BMS/Pfizer",  "Tablet",   "5mg",   145,2,False,False),
    ("DRG010","Xarelto",      "Rivaroxaban",        "Cardiology",      "J&J",         "Tablet",   "20mg",  140,2,False,False),
    ("DRG011","Advair",       "Fluticasone/Salm",   "Pulmonology",     "GSK",         "Inhaler",  "250mcg", 95,2,False,False),
    ("DRG012","Symbicort",    "Budesonide/Form",    "Pulmonology",     "AstraZeneca", "Inhaler",  "160mcg", 90,2,False,False),
    ("DRG013","Stelara",      "Ustekinumab",        "Dermatology",     "Janssen",     "Injection","45mg", 18000,4,True, True),
    ("DRG014","Dupixent",     "Dupilumab",          "Dermatology",     "Sanofi",      "Injection","300mg", 3200,4,True, True),
    ("DRG015","Tecfidera",    "Dimethyl Fumarate",  "Neurology",       "Biogen",      "Capsule",  "240mg", 8100,4,True, True),
    ("DRG016","Lisinopril",   "Lisinopril",         "Cardiology",      "Generic",     "Tablet",   "10mg",     3,1,False,False),
    ("DRG017","Amlodipine",   "Amlodipine",         "Cardiology",      "Generic",     "Tablet",   "5mg",      4,1,False,False),
    ("DRG018","Omeprazole",   "Omeprazole",         "Gastroenterology","Generic",     "Capsule",  "20mg",     6,1,False,False),
    ("DRG019","Nexium",       "Esomeprazole",       "Gastroenterology","AstraZeneca", "Capsule",  "40mg",    45,2,False,False),
    ("DRG020","Revlimid",     "Lenalidomide",       "Oncology",        "BMS",         "Capsule",  "25mg", 19000,5,True, True),
]

FORMULARY_TIERS = {
    1:("Preferred Generic",    0.10),
    2:("Non-Preferred Generic",0.20),
    3:("Preferred Brand",      0.30),
    4:("Non-Preferred Brand",  0.45),
    5:("Specialty",            0.60),
}

STATES  = ["NC","TX","CA","FL","NY","GA","OH","PA","IL","AZ","WA","CO","MA","TN","VA"]
PLANS   = ["Gold Plan","Silver Plan","Bronze Plan","Platinum Plan","Medicare Advantage"]
PA_OUTCOMES = ["Approved","Denied","Pending","Appeal Approved"]
PA_W        = [0.65,0.18,0.08,0.09]
DENY_REASONS= ["Not medically necessary","Step therapy required",
                "Formulary exclusion","Duplicate therapy","Incomplete documentation"]

START = datetime(2022,1,1)
END   = datetime(2024,12,31)
def rdate(s=START,e=END): return s+timedelta(days=random.randint(0,(e-s).days))
def fmt(d): return d.strftime("%Y-%m-%d")

# drugs
dcols = ["drug_id","brand_name","generic_name","therapy_area","manufacturer",
         "dosage_form","strength","unit_cost_usd","formulary_tier","requires_prior_auth","is_specialty"]
drugs_df = pd.DataFrame(DRUGS, columns=dcols)
drugs_df["is_cold_chain"]        = drugs_df["is_specialty"]
drugs_df["ndc"]                  = [f"{random.randint(10000,99999)}-{random.randint(100,999)}-{random.randint(10,99)}" for _ in range(len(drugs_df))]
drugs_df["days_supply_limit"]    = 30
drugs_df["max_quantity_per_fill"]= np.where(drugs_df["is_specialty"],1,3)
drugs_df.to_csv(f"{OUT}/drugs.csv", index=False)

# formulary history
form_records = []
for _, row in drugs_df.iterrows():
    form_records.append({"formulary_id":f"FORM{len(form_records)+1:05d}","drug_id":row["drug_id"],
        "formulary_tier":row["formulary_tier"],"tier_name":FORMULARY_TIERS[row["formulary_tier"]][0],
        "copay_pct":FORMULARY_TIERS[row["formulary_tier"]][1],"effective_date":"2022-01-01",
        "end_date":None,"change_reason":"Initial formulary placement","plan_year":2022})
    if random.random()<0.30:
        new_tier = max(1,min(5,row["formulary_tier"]+random.choice([-1,1])))
        cd = rdate(datetime(2023,1,1),datetime(2023,12,31))
        form_records.append({"formulary_id":f"FORM{len(form_records)+1:05d}","drug_id":row["drug_id"],
            "formulary_tier":new_tier,"tier_name":FORMULARY_TIERS[new_tier][0],
            "copay_pct":FORMULARY_TIERS[new_tier][1],"effective_date":fmt(cd),"end_date":None,
            "change_reason":random.choice(["Annual formulary review","Generic available","Contract renegotiation","Clinical review"]),
            "plan_year":2023})
pd.DataFrame(form_records).to_csv(f"{OUT}/formulary.csv", index=False)

# members
n_mem = 1000
member_ids = [f"MBR{i:06d}" for i in range(1,n_mem+1)]
pd.DataFrame({"member_id":member_ids,"age":np.random.randint(18,85,n_mem),
    "gender":np.random.choice(["M","F","Other"],n_mem,p=[0.48,0.49,0.03]),
    "state":np.random.choice(STATES,n_mem),"plan_type":np.random.choice(PLANS,n_mem,p=[0.25,0.30,0.20,0.15,0.10]),
    "enrollment_date":[fmt(rdate(START,START+timedelta(days=180))) for _ in range(n_mem)],
    "is_active":np.random.choice([True,False],n_mem,p=[0.92,0.08])
}).to_csv(f"{OUT}/members.csv", index=False)

# prescriptions — balanced drug selection (equal weights)
n_rx = 5000
rx_records = []
drug_list = drugs_df.to_dict("records")
for i in range(1,n_rx+1):
    drug   = random.choice(drug_list)
    member = random.choice(member_ids)
    svc_d  = rdate()
    tier   = drug["formulary_tier"]
    copay_pct = FORMULARY_TIERS[tier][1]
    qty    = random.randint(1, int(drug["max_quantity_per_fill"]))
    cost   = round(drug["unit_cost_usd"]*qty*random.uniform(0.95,1.05),2)
    copay  = round(cost*copay_pct,2)
    rx_records.append({"rx_id":f"RX{i:07d}","member_id":member,"drug_id":drug["drug_id"],
        "prescriber_npi":str(random.randint(1000000000,9999999999)),
        "service_date":fmt(svc_d),"days_supply":random.choice([30,60,90]),
        "quantity_dispensed":qty,"formulary_tier":tier,"total_cost_usd":cost,
        "member_copay_usd":copay,"plan_paid_usd":round(cost-copay,2),
        "pharmacy_type":random.choice(["Retail","Mail Order","Specialty"]),
        "refill_number":random.randint(0,5),
        "is_generic":"Generic" in drug["manufacturer"],
        "therapy_area":drug["therapy_area"]})
rx_df = pd.DataFrame(rx_records)
rx_df.to_csv(f"{OUT}/prescriptions.csv", index=False)

# prior auth requests
pa_drugs = drugs_df[drugs_df["requires_prior_auth"]==True]["drug_id"].tolist()
pa_rx    = rx_df[rx_df["drug_id"].isin(pa_drugs)]
pa_records = []
for i,(_, row) in enumerate(pa_rx.iterrows(),1):
    req_d   = datetime.strptime(row["service_date"],"%Y-%m-%d")-timedelta(days=random.randint(3,14))
    outcome = np.random.choice(PA_OUTCOMES,p=PA_W)
    dec_days= random.randint(1,10) if outcome!="Pending" else None
    dec_d   = req_d+timedelta(days=dec_days) if dec_days else None
    pa_records.append({"pa_id":f"PA{i:06d}","rx_id":row["rx_id"],"drug_id":row["drug_id"],
        "member_id":row["member_id"],"request_date":fmt(req_d),
        "decision_date":fmt(dec_d) if dec_d else None,"days_to_decision":dec_days,
        "outcome":outcome,"denial_reason":random.choice(DENY_REASONS) if outcome=="Denied" else None,
        "is_urgent":random.random()<0.15,"appeal_filed":outcome=="Denied" and random.random()<0.40})
pd.DataFrame(pa_records).to_csv(f"{OUT}/prior_auth_requests.csv", index=False)

# monthly spend summary
rx_df["month"] = pd.to_datetime(rx_df["service_date"]).dt.to_period("M").astype(str)
spend_df = (rx_df.groupby(["month","drug_id","therapy_area","formulary_tier","pharmacy_type"])
    .agg(rx_count=("rx_id","count"),total_cost=("total_cost_usd","sum"),
         member_copay=("member_copay_usd","sum"),plan_paid=("plan_paid_usd","sum"),
         unique_members=("member_id","nunique")).reset_index().round(2))
spend_df.to_csv(f"{OUT}/drug_spend_summary.csv", index=False)

print("✅ Generated:")
for name,df in [("drugs",drugs_df),("formulary",pd.read_csv(f"{OUT}/formulary.csv")),
                ("members",pd.read_csv(f"{OUT}/members.csv")),("prescriptions",rx_df),
                ("prior_auth_requests",pd.read_csv(f"{OUT}/prior_auth_requests.csv")),
                ("drug_spend_summary",spend_df)]:
    print(f"   {name+'.csv':<30} → {len(df)} rows")
