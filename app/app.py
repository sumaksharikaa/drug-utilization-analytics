"""
app.py — Drug Utilization & Formulary Analytics Dashboard
Run: streamlit run app/app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import os

st.set_page_config(
    page_title="Drug Utilization & Formulary Analytics",
    page_icon="💉",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

@st.cache_data
def load_data():
    drugs    = pd.read_csv(f"{DATA_DIR}/drugs.csv")
    formulary= pd.read_csv(f"{DATA_DIR}/formulary.csv", parse_dates=["effective_date"])
    members  = pd.read_csv(f"{DATA_DIR}/members.csv",   parse_dates=["enrollment_date"])
    rx       = pd.read_csv(f"{DATA_DIR}/prescriptions.csv", parse_dates=["service_date"])
    pa       = pd.read_csv(f"{DATA_DIR}/prior_auth_requests.csv", parse_dates=["request_date","decision_date"])
    spend    = pd.read_csv(f"{DATA_DIR}/drug_spend_summary.csv")

    rx = rx.merge(drugs[["drug_id","brand_name","generic_name","manufacturer","is_specialty","unit_cost_usd"]], on="drug_id", how="left")
    rx = rx.merge(members[["member_id","age","gender","state","plan_type"]], on="member_id", how="left")
    rx["month"]   = rx["service_date"].dt.to_period("M").dt.to_timestamp()
    rx["quarter"] = rx["service_date"].dt.to_period("Q").dt.to_timestamp()
    rx["year"]    = rx["service_date"].dt.year

    pa = pa.merge(drugs[["drug_id","brand_name","therapy_area"]], on="drug_id", how="left")
    return rx, pa, drugs, formulary, spend

rx, pa, drugs, formulary, spend = load_data()

TIER_LABELS = {1:"T1 Pref Generic",2:"T2 Non-Pref Generic",3:"T3 Pref Brand",4:"T4 Non-Pref Brand",5:"T5 Specialty"}
COLORS = px.colors.qualitative.Bold

# ── sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.title("💉 Filters")
years         = sorted(rx["year"].unique())
sel_years     = st.sidebar.multiselect("Year", years, default=years)
therapy_areas = sorted(rx["therapy_area"].dropna().unique())
sel_therapy   = st.sidebar.multiselect("Therapy Area", therapy_areas, default=therapy_areas)
sel_pharmacy  = st.sidebar.multiselect("Pharmacy Type",
    ["Retail","Mail Order","Specialty"], default=["Retail","Mail Order","Specialty"])

mask = (rx["year"].isin(sel_years) & rx["therapy_area"].isin(sel_therapy) & rx["pharmacy_type"].isin(sel_pharmacy))
fdf  = rx[mask].copy()

# ── header ────────────────────────────────────────────────────────────────────
st.title("💉 Drug Utilization & Formulary Analytics")
st.caption("Plan spend, formulary tier analysis, prior authorization performance, generic substitution opportunities")
st.divider()

# ── KPIs ──────────────────────────────────────────────────────────────────────
k1,k2,k3,k4,k5,k6 = st.columns(6)
total_spend  = fdf["total_cost_usd"].sum()
plan_paid    = fdf["plan_paid_usd"].sum()
total_rx     = len(fdf)
generic_rate = fdf["is_generic"].mean()*100
avg_cost     = fdf["total_cost_usd"].mean()
unique_mbr   = fdf["member_id"].nunique()

k1.metric("Total Rx",         f"{total_rx:,}")
k2.metric("Unique Members",   f"{unique_mbr:,}")
k3.metric("Total Drug Spend", f"${total_spend/1e6:.2f}M")
k4.metric("Plan Paid",        f"${plan_paid/1e6:.2f}M")
k5.metric("Avg Cost / Rx",    f"${avg_cost:,.0f}")
k6.metric("Generic Rate",     f"{generic_rate:.1f}%")
st.divider()

tab1,tab2,tab3,tab4,tab5 = st.tabs([
    "📈 Spend Trends","💊 Formulary","🔐 Prior Auth","🔄 Generic Opportunities","🔎 Data Quality"
])

# ══ TAB 1 — SPEND TRENDS ═════════════════════════════════════════════════════
with tab1:
    c1,c2 = st.columns(2)
    with c1:
        st.subheader("Monthly Drug Spend by Therapy Area")
        m_spend = (fdf.groupby(["month","therapy_area"])["plan_paid_usd"].sum().reset_index())
        fig = px.area(m_spend, x="month", y="plan_paid_usd", color="therapy_area",
                      color_discrete_sequence=COLORS,
                      labels={"plan_paid_usd":"Plan Paid ($)","therapy_area":"Therapy","month":"Month"})
        fig.update_layout(xaxis_title=None, legend_title="Therapy Area")
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Spend by Formulary Tier")
        tier_spend = (fdf.groupby("formulary_tier")
                      .agg(total=("total_cost_usd","sum"), plan=("plan_paid_usd","sum"),
                           copay=("member_copay_usd","sum"), count=("rx_id","count"))
                      .reset_index())
        tier_spend["tier_label"] = tier_spend["formulary_tier"].map(TIER_LABELS)
        fig2 = px.bar(tier_spend, x="tier_label", y=["plan","copay"],
                      barmode="stack", color_discrete_sequence=["#2980b9","#e67e22"],
                      labels={"value":"Amount ($)","tier_label":"Formulary Tier","variable":"Payer"})
        fig2.update_layout(xaxis_title=None, legend_title="Payer")
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Top 10 Drugs by Plan Spend")
    top_drugs = (fdf.groupby(["brand_name","therapy_area"])
                 .agg(plan_paid=("plan_paid_usd","sum"), rx_count=("rx_id","count"))
                 .reset_index().sort_values("plan_paid",ascending=False).head(10))
    fig3 = px.bar(top_drugs, x="plan_paid", y="brand_name", color="therapy_area",
                  orientation="h", color_discrete_sequence=COLORS,
                  labels={"plan_paid":"Plan Paid ($)","brand_name":"Drug"})
    fig3.update_layout(yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig3, use_container_width=True)

# ══ TAB 2 — FORMULARY ════════════════════════════════════════════════════════
with tab2:
    st.subheader("📋 Current Formulary Explorer")
    current_form = formulary[formulary["end_date"].isna()].merge(
        drugs[["drug_id","brand_name","generic_name","therapy_area","manufacturer",
               "unit_cost_usd","requires_prior_auth","is_specialty"]], on="drug_id", how="left")

    col_filter = st.columns(3)
    sel_tier_f = col_filter[0].multiselect("Tier", sorted(current_form["formulary_tier"].unique()),
                                           default=sorted(current_form["formulary_tier"].unique()))
    sel_area_f = col_filter[1].multiselect("Therapy", sorted(current_form["therapy_area"].dropna().unique()),
                                           default=sorted(current_form["therapy_area"].dropna().unique()))
    sel_pa_f   = col_filter[2].selectbox("Requires PA", ["All","Yes","No"])

    fform = current_form[current_form["formulary_tier"].isin(sel_tier_f) &
                         current_form["therapy_area"].isin(sel_area_f)]
    if sel_pa_f == "Yes":   fform = fform[fform["requires_prior_auth"]==True]
    elif sel_pa_f == "No":  fform = fform[fform["requires_prior_auth"]==False]

    fform["tier_label"] = fform["formulary_tier"].map(TIER_LABELS)
    display_cols = ["brand_name","generic_name","therapy_area","manufacturer",
                    "tier_label","copay_pct","unit_cost_usd","requires_prior_auth","is_specialty"]
    st.dataframe(fform[display_cols].rename(columns={
        "brand_name":"Brand","generic_name":"Generic","therapy_area":"Therapy",
        "manufacturer":"Manufacturer","tier_label":"Tier","copay_pct":"Copay %",
        "unit_cost_usd":"Unit Cost ($)","requires_prior_auth":"PA Req","is_specialty":"Specialty"}),
        use_container_width=True, hide_index=True)

    st.divider()
    c1,c2 = st.columns(2)
    with c1:
        st.subheader("Formulary Tier Distribution")
        tier_dist = current_form["formulary_tier"].map(TIER_LABELS).value_counts().reset_index()
        tier_dist.columns = ["Tier","Drugs"]
        fig = px.pie(tier_dist, values="Drugs", names="Tier", hole=0.4,
                     color_discrete_sequence=COLORS)
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader("Avg Unit Cost by Tier")
        cost_tier = (current_form.groupby("formulary_tier")["unit_cost_usd"]
                     .mean().reset_index())
        cost_tier["tier_label"] = cost_tier["formulary_tier"].map(TIER_LABELS)
        fig2 = px.bar(cost_tier, x="tier_label", y="unit_cost_usd",
                      color="unit_cost_usd", color_continuous_scale=["#aed6f1","#1a3c5e"],
                      labels={"unit_cost_usd":"Avg Unit Cost ($)","tier_label":"Tier"})
        fig2.update_layout(coloraxis_showscale=False)
        st.plotly_chart(fig2, use_container_width=True)

# ══ TAB 3 — PRIOR AUTH ═══════════════════════════════════════════════════════
with tab3:
    c1,c2,c3,c4 = st.columns(4)
    total_pa    = len(pa)
    approved    = (pa["outcome"]=="Approved").sum()
    denied      = (pa["outcome"]=="Denied").sum()
    avg_days    = pa["days_to_decision"].mean()
    c1.metric("Total PA Requests", f"{total_pa:,}")
    c2.metric("Approved",          f"{approved:,}  ({approved/total_pa*100:.0f}%)")
    c3.metric("Denied",            f"{denied:,}  ({denied/total_pa*100:.0f}%)")
    c4.metric("Avg Days to Decision", f"{avg_days:.1f}")

    c1,c2 = st.columns(2)
    with c1:
        st.subheader("PA Outcome Distribution")
        outcomes = pa["outcome"].value_counts().reset_index()
        outcomes.columns = ["Outcome","Count"]
        color_map = {"Approved":"#2ecc71","Denied":"#e74c3c","Pending":"#f39c12","Appeal Approved":"#3498db"}
        fig = px.pie(outcomes, values="Count", names="Outcome", hole=0.4,
                     color="Outcome", color_discrete_map=color_map)
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Denial Reasons")
        denial_reasons = (pa[pa["outcome"]=="Denied"]["denial_reason"]
                          .value_counts().reset_index())
        denial_reasons.columns = ["Reason","Count"]
        fig2 = px.bar(denial_reasons, x="Count", y="Reason", orientation="h",
                      color_discrete_sequence=["#e74c3c"],
                      labels={"Count":"Denials","Reason":""})
        fig2.update_layout(yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("PA Performance by Drug — Approval Rate & Avg Days")
    pa_drug = (pa.groupby("brand_name")
               .agg(total=("pa_id","count"),
                    approved=("outcome",lambda x:(x=="Approved").sum()),
                    avg_days=("days_to_decision","mean"),
                    urgent=("is_urgent","sum"))
               .reset_index())
    pa_drug["approval_rate"] = pa_drug["approved"]/pa_drug["total"]*100
    pa_drug["avg_days"]      = pa_drug["avg_days"].round(1)
    fig3 = px.scatter(pa_drug, x="avg_days", y="approval_rate", size="total",
                      text="brand_name", color="approval_rate",
                      color_continuous_scale=["#e74c3c","#2ecc71"],
                      labels={"avg_days":"Avg Days to Decision","approval_rate":"Approval Rate (%)","total":"Volume"})
    fig3.update_traces(textposition="top center")
    st.plotly_chart(fig3, use_container_width=True)

# ══ TAB 4 — GENERIC OPPORTUNITIES ════════════════════════════════════════════
with tab4:
    st.subheader("🔄 Generic Substitution Opportunities")
    st.caption("Brand drugs where generic equivalents may reduce plan spend")

    brand_rx = (fdf[(fdf["is_generic"]==False) & (fdf["is_specialty"]==False)]
                .groupby(["brand_name","generic_name","therapy_area","formulary_tier"])
                .agg(rx_count=("rx_id","count"),
                     total_spend=("total_cost_usd","sum"),
                     plan_paid=("plan_paid_usd","sum"),
                     avg_cost=("total_cost_usd","mean"))
                .reset_index().sort_values("plan_paid",ascending=False))
    brand_rx["potential_savings"] = (brand_rx["plan_paid"]*0.88).round(2)
    brand_rx["tier_label"]        = brand_rx["formulary_tier"].map(TIER_LABELS)

    c1,c2 = st.columns(2)
    with c1:
        fig = px.bar(brand_rx.head(10), x="plan_paid", y="brand_name",
                     color="therapy_area", orientation="h",
                     color_discrete_sequence=COLORS,
                     labels={"plan_paid":"Plan Paid ($)","brand_name":"Drug"})
        fig.update_layout(title="Top Brand Drugs by Plan Spend", yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        fig2 = px.bar(brand_rx.head(10), x="potential_savings", y="brand_name",
                      color_discrete_sequence=["#27ae60"], orientation="h",
                      labels={"potential_savings":"Est. Savings if Generic ($)","brand_name":"Drug"})
        fig2.update_layout(title="Estimated Savings via Generic Switch", yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig2, use_container_width=True)

    total_savings = brand_rx["potential_savings"].sum()
    st.metric("💰 Total Estimated Generic Substitution Savings", f"${total_savings:,.0f}")

    st.dataframe(brand_rx[["brand_name","generic_name","therapy_area","tier_label",
                             "rx_count","plan_paid","potential_savings"]]
                 .rename(columns={"brand_name":"Brand","generic_name":"Generic",
                                  "therapy_area":"Therapy","tier_label":"Tier",
                                  "rx_count":"Rx Count","plan_paid":"Plan Paid ($)",
                                  "potential_savings":"Est. Savings ($)"}),
                 use_container_width=True, hide_index=True)

# ══ TAB 5 — DATA QUALITY ═════════════════════════════════════════════════════
with tab5:
    st.subheader("🔎 Data Quality Checks")
    checks = {
        "Prescriptions with negative cost":        (fdf["total_cost_usd"]<0).sum(),
        "Copay exceeds total cost":                (fdf["member_copay_usd"]>fdf["total_cost_usd"]).sum(),
        "Prescriptions missing therapy area":      fdf["therapy_area"].isna().sum(),
        "PA requests: denied without reason":      pa[(pa["outcome"]=="Denied")&pa["denial_reason"].isna()].shape[0],
        "Members missing state":                   rx["state"].isna().sum(),
        "Formulary records missing tier name":     formulary["tier_name"].isna().sum(),
    }
    dq = pd.DataFrame(list(checks.items()), columns=["Check","Issues"])
    dq["Status"] = dq["Issues"].apply(lambda x: "✅ Pass" if x==0 else "⚠️ Review")

    c1,c2 = st.columns([2,1])
    with c1:
        st.dataframe(dq.style.map(
            lambda v: "color:green" if "Pass" in str(v) else "color:orange", subset=["Status"]),
            use_container_width=True, hide_index=True)
    with c2:
        score = (dq["Issues"]==0).sum()/len(dq)*100
        fig = go.Figure(go.Indicator(
            mode="gauge+number", value=score,
            title={"text":"DQ Score"},
            gauge={"axis":{"range":[0,100]},
                   "bar":{"color":"#2ecc71" if score>80 else "#e74c3c"},
                   "steps":[{"range":[0,60],"color":"#fadbd8"},
                             {"range":[60,80],"color":"#fdebd0"},
                             {"range":[80,100],"color":"#d5f5e3"}]},
            number={"suffix":"%"}))
        fig.update_layout(height=260)
        st.plotly_chart(fig, use_container_width=True)

st.divider()
st.caption("Drug Utilization & Formulary Analytics · MySQL · Python ETL · Streamlit · Portfolio Project — sumaksharika.com")
