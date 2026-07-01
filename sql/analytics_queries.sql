-- =============================================================================
-- analytics_queries.sql
-- Drug Utilization & Formulary Analytics — MySQL KPI Queries
-- =============================================================================

USE drug_utilization_db;

-- =============================================================================
-- 1. EXECUTIVE SUMMARY — Total Spend, Rx Volume, Generic Rate
-- =============================================================================

SELECT
    COUNT(*)                                        AS total_prescriptions,
    COUNT(DISTINCT member_id)                       AS unique_members,
    COUNT(DISTINCT drug_id)                         AS unique_drugs,
    ROUND(SUM(total_cost_usd), 2)                   AS total_drug_spend_usd,
    ROUND(SUM(plan_paid_usd), 2)                    AS total_plan_paid_usd,
    ROUND(SUM(member_copay_usd), 2)                 AS total_member_copay_usd,
    ROUND(AVG(total_cost_usd), 2)                   AS avg_cost_per_rx,
    ROUND(SUM(CASE WHEN is_generic THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2)
                                                    AS generic_dispensing_rate_pct,
    ROUND(SUM(plan_paid_usd) / SUM(total_cost_usd) * 100, 2)
                                                    AS plan_liability_pct
FROM prescriptions;


-- =============================================================================
-- 2. DRUG SPEND BY THERAPY AREA — Monthly Trend
-- =============================================================================

SELECT
    LEFT(service_date, 7)                           AS month,
    therapy_area,
    COUNT(*)                                        AS rx_count,
    COUNT(DISTINCT member_id)                       AS unique_members,
    ROUND(SUM(total_cost_usd), 2)                   AS total_spend,
    ROUND(SUM(plan_paid_usd), 2)                    AS plan_paid,
    ROUND(AVG(total_cost_usd), 2)                   AS avg_cost_per_rx
FROM prescriptions
GROUP BY LEFT(service_date, 7), therapy_area
ORDER BY month, therapy_area;


-- =============================================================================
-- 3. FORMULARY TIER UTILIZATION — Spend & Volume by Tier
-- =============================================================================

SELECT
    p.formulary_tier,
    f.tier_name,
    f.copay_pct,
    COUNT(p.rx_id)                                  AS rx_count,
    ROUND(SUM(p.total_cost_usd), 2)                 AS total_spend,
    ROUND(SUM(p.plan_paid_usd), 2)                  AS plan_paid,
    ROUND(SUM(p.member_copay_usd), 2)               AS member_copay,
    ROUND(AVG(p.total_cost_usd), 2)                 AS avg_cost_per_rx,
    ROUND(SUM(p.total_cost_usd) * 100.0
        / SUM(SUM(p.total_cost_usd)) OVER (), 2)    AS pct_of_total_spend
FROM prescriptions p
JOIN formulary f ON p.drug_id = f.drug_id AND f.end_date IS NULL
GROUP BY p.formulary_tier, f.tier_name, f.copay_pct
ORDER BY p.formulary_tier;


-- =============================================================================
-- 4. TOP 10 DRUGS BY PLAN SPEND
-- =============================================================================

SELECT
    d.brand_name,
    d.generic_name,
    d.therapy_area,
    d.manufacturer,
    d.formulary_tier,
    COUNT(p.rx_id)                                  AS total_rx,
    COUNT(DISTINCT p.member_id)                     AS unique_members,
    ROUND(SUM(p.total_cost_usd), 2)                 AS total_spend,
    ROUND(SUM(p.plan_paid_usd), 2)                  AS plan_paid,
    ROUND(AVG(p.total_cost_usd), 2)                 AS avg_cost_per_rx,
    ROUND(SUM(p.plan_paid_usd) * 100.0
        / (SELECT SUM(plan_paid_usd) FROM prescriptions), 2)
                                                    AS pct_of_total_plan_spend
FROM prescriptions p
JOIN drugs d ON p.drug_id = d.drug_id
GROUP BY d.drug_id, d.brand_name, d.generic_name,
         d.therapy_area, d.manufacturer, d.formulary_tier
ORDER BY plan_paid DESC
LIMIT 10;


-- =============================================================================
-- 5. PRIOR AUTHORIZATION PERFORMANCE
-- =============================================================================

SELECT
    d.brand_name,
    d.therapy_area,
    COUNT(pa.pa_id)                                 AS total_pa_requests,
    SUM(CASE WHEN pa.outcome = 'Approved' THEN 1 ELSE 0 END)        AS approved,
    SUM(CASE WHEN pa.outcome = 'Denied' THEN 1 ELSE 0 END)          AS denied,
    SUM(CASE WHEN pa.outcome = 'Appeal Approved' THEN 1 ELSE 0 END) AS appeal_approved,
    SUM(CASE WHEN pa.outcome = 'Pending' THEN 1 ELSE 0 END)         AS pending,
    ROUND(AVG(pa.days_to_decision), 1)              AS avg_days_to_decision,
    ROUND(SUM(CASE WHEN pa.is_urgent THEN 1 ELSE 0 END)
        * 100.0 / COUNT(*), 1)                      AS urgent_pct,
    ROUND(SUM(CASE WHEN pa.appeal_filed THEN 1 ELSE 0 END)
        * 100.0 / NULLIF(SUM(CASE WHEN pa.outcome='Denied' THEN 1 ELSE 0 END),0), 1)
                                                    AS appeal_rate_on_denials_pct
FROM prior_auth_requests pa
JOIN drugs d ON pa.drug_id = d.drug_id
GROUP BY d.drug_id, d.brand_name, d.therapy_area
ORDER BY total_pa_requests DESC;


-- =============================================================================
-- 6. PRIOR AUTH DENIAL REASONS
-- =============================================================================

SELECT
    pa.denial_reason,
    COUNT(*)                                        AS denial_count,
    ROUND(COUNT(*) * 100.0
        / SUM(COUNT(*)) OVER (), 2)                 AS pct_of_all_denials,
    ROUND(AVG(pa.days_to_decision), 1)              AS avg_days_to_deny
FROM prior_auth_requests pa
WHERE pa.outcome = 'Denied'
  AND pa.denial_reason IS NOT NULL
GROUP BY pa.denial_reason
ORDER BY denial_count DESC;


-- =============================================================================
-- 7. GENERIC SUBSTITUTION OPPORTUNITY ANALYSIS
-- =============================================================================

SELECT
    d.brand_name,
    d.generic_name,
    d.therapy_area,
    d.formulary_tier,
    d.unit_cost_usd                                 AS brand_cost,
    COUNT(p.rx_id)                                  AS brand_rx_count,
    ROUND(SUM(p.total_cost_usd), 2)                 AS brand_total_spend,
    -- Estimate potential savings at Tier-1 generic pricing (~$4-12/unit)
    ROUND(SUM(p.total_cost_usd) * 0.90, 2)         AS potential_savings_if_generic
FROM prescriptions p
JOIN drugs d ON p.drug_id = d.drug_id
WHERE d.is_specialty = FALSE
  AND p.is_generic   = FALSE
  AND d.formulary_tier > 1
GROUP BY d.drug_id, d.brand_name, d.generic_name,
         d.therapy_area, d.formulary_tier, d.unit_cost_usd
ORDER BY brand_total_spend DESC
LIMIT 15;


-- =============================================================================
-- 8. MEMBER DRUG UTILIZATION — High Utilizers
-- =============================================================================

WITH member_spend AS (
    SELECT
        p.member_id,
        m.age,
        m.gender,
        m.state,
        m.plan_type,
        COUNT(p.rx_id)                              AS total_rx,
        COUNT(DISTINCT p.drug_id)                   AS unique_drugs,
        ROUND(SUM(p.total_cost_usd), 2)             AS total_spend,
        ROUND(SUM(p.plan_paid_usd), 2)              AS plan_paid,
        ROUND(AVG(p.total_cost_usd), 2)             AS avg_rx_cost
    FROM prescriptions p
    JOIN members m ON p.member_id = m.member_id
    GROUP BY p.member_id, m.age, m.gender, m.state, m.plan_type
),
pct_ranks AS (
    SELECT *,
        NTILE(10) OVER (ORDER BY total_spend DESC)  AS spend_decile
    FROM member_spend
)
SELECT *
FROM pct_ranks
WHERE spend_decile = 1
ORDER BY total_spend DESC
LIMIT 20;


-- =============================================================================
-- 9. FORMULARY TIER CHANGE IMPACT — Before vs After
-- =============================================================================

WITH tier_changes AS (
    SELECT f1.drug_id, f1.formulary_tier AS old_tier, f2.formulary_tier AS new_tier,
           f1.copay_pct AS old_copay, f2.copay_pct AS new_copay,
           f2.effective_date AS change_date, f2.change_reason
    FROM formulary f1
    JOIN formulary f2 ON f1.drug_id = f2.drug_id
        AND f2.plan_year > f1.plan_year
),
before_after AS (
    SELECT tc.drug_id, tc.old_tier, tc.new_tier, tc.change_date, tc.change_reason,
           SUM(CASE WHEN p.service_date < tc.change_date THEN p.total_cost_usd ELSE 0 END)
               AS spend_before,
           SUM(CASE WHEN p.service_date >= tc.change_date THEN p.total_cost_usd ELSE 0 END)
               AS spend_after,
           COUNT(CASE WHEN p.service_date < tc.change_date THEN 1 END)   AS rx_before,
           COUNT(CASE WHEN p.service_date >= tc.change_date THEN 1 END)  AS rx_after
    FROM tier_changes tc
    JOIN prescriptions p ON p.drug_id = tc.drug_id
    GROUP BY tc.drug_id, tc.old_tier, tc.new_tier, tc.change_date, tc.change_reason
)
SELECT d.brand_name, d.therapy_area, ba.*,
    ROUND(spend_after - spend_before, 2) AS spend_delta,
    ROUND((spend_after - spend_before) / NULLIF(spend_before,0) * 100, 1) AS spend_change_pct
FROM before_after ba
JOIN drugs d ON ba.drug_id = d.drug_id
ORDER BY ABS(spend_after - spend_before) DESC;


-- =============================================================================
-- 10. PHARMACY TYPE MIX — Cost & Volume
-- =============================================================================

SELECT
    pharmacy_type,
    COUNT(*)                                        AS rx_count,
    COUNT(DISTINCT member_id)                       AS unique_members,
    ROUND(SUM(total_cost_usd), 2)                   AS total_spend,
    ROUND(AVG(total_cost_usd), 2)                   AS avg_cost_per_rx,
    ROUND(AVG(member_copay_usd), 2)                 AS avg_copay,
    ROUND(SUM(CASE WHEN is_generic THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1)
                                                    AS generic_rate_pct
FROM prescriptions
GROUP BY pharmacy_type
ORDER BY total_spend DESC;


-- =============================================================================
-- 11. DATA QUALITY CHECKS
-- =============================================================================

SELECT 'prescriptions_negative_cost'    AS check_name, COUNT(*) AS issues
FROM prescriptions WHERE total_cost_usd < 0
UNION ALL
SELECT 'prescriptions_copay_exceeds_cost', COUNT(*)
FROM prescriptions WHERE member_copay_usd > total_cost_usd
UNION ALL
SELECT 'pa_decision_before_request', COUNT(*)
FROM prior_auth_requests WHERE decision_date < request_date
UNION ALL
SELECT 'pa_denied_without_reason', COUNT(*)
FROM prior_auth_requests WHERE outcome='Denied' AND denial_reason IS NULL
UNION ALL
SELECT 'members_invalid_age', COUNT(*)
FROM members WHERE age < 0 OR age > 120
UNION ALL
SELECT 'formulary_missing_tier_name', COUNT(*)
FROM formulary WHERE tier_name IS NULL OR tier_name = '';
