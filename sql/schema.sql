-- =============================================================================
-- schema.sql
-- Drug Utilization & Formulary Analytics — MySQL Schema
-- ER Model: members → prescriptions ← drugs ← formulary
--           prescriptions → prior_auth_requests
--           drugs → drug_spend_summary
-- =============================================================================

DROP DATABASE IF EXISTS drug_utilization_db;
CREATE DATABASE drug_utilization_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE drug_utilization_db;

-- =============================================================================
-- DIMENSION TABLES
-- =============================================================================

CREATE TABLE drugs (
    drug_id                 VARCHAR(10)     NOT NULL PRIMARY KEY,
    brand_name              VARCHAR(100)    NOT NULL,
    generic_name            VARCHAR(100)    NOT NULL,
    therapy_area            VARCHAR(60)     NOT NULL,
    manufacturer            VARCHAR(100)    NOT NULL,
    dosage_form             VARCHAR(40)     NOT NULL,
    strength                VARCHAR(20)     NOT NULL,
    ndc                     VARCHAR(20),
    unit_cost_usd           DECIMAL(10,2)   NOT NULL CHECK (unit_cost_usd > 0),
    formulary_tier          TINYINT         NOT NULL CHECK (formulary_tier BETWEEN 1 AND 5),
    requires_prior_auth     BOOLEAN         NOT NULL DEFAULT FALSE,
    is_specialty            BOOLEAN         NOT NULL DEFAULT FALSE,
    is_cold_chain           BOOLEAN         NOT NULL DEFAULT FALSE,
    days_supply_limit       SMALLINT        DEFAULT 30,
    max_quantity_per_fill   SMALLINT        DEFAULT 3,
    created_at              TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_drugs_therapy   (therapy_area),
    INDEX idx_drugs_tier      (formulary_tier),
    INDEX idx_drugs_mfr       (manufacturer)
);

CREATE TABLE formulary (
    formulary_id    VARCHAR(10)     NOT NULL PRIMARY KEY,
    drug_id         VARCHAR(10)     NOT NULL,
    formulary_tier  TINYINT         NOT NULL CHECK (formulary_tier BETWEEN 1 AND 5),
    tier_name       VARCHAR(50)     NOT NULL,
    copay_pct       DECIMAL(5,2)    NOT NULL,
    effective_date  DATE            NOT NULL,
    end_date        DATE,
    change_reason   VARCHAR(100),
    plan_year       YEAR            NOT NULL,
    created_at      TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (drug_id) REFERENCES drugs(drug_id),
    INDEX idx_formulary_drug      (drug_id),
    INDEX idx_formulary_effective (effective_date),
    INDEX idx_formulary_year      (plan_year)
);

CREATE TABLE members (
    member_id       VARCHAR(12)     NOT NULL PRIMARY KEY,
    age             TINYINT         NOT NULL CHECK (age BETWEEN 0 AND 120),
    gender          CHAR(6)         CHECK (gender IN ('M','F','Other')),
    state           CHAR(2)         NOT NULL,
    plan_type       VARCHAR(30)     NOT NULL,
    enrollment_date DATE            NOT NULL,
    is_active       BOOLEAN         DEFAULT TRUE,
    created_at      TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_members_state  (state),
    INDEX idx_members_plan   (plan_type)
);

-- =============================================================================
-- FACT TABLES
-- =============================================================================

CREATE TABLE prescriptions (
    rx_id               VARCHAR(12)     NOT NULL PRIMARY KEY,
    member_id           VARCHAR(12)     NOT NULL,
    drug_id             VARCHAR(10)     NOT NULL,
    prescriber_npi      VARCHAR(12),
    service_date        DATE            NOT NULL,
    days_supply         SMALLINT        CHECK (days_supply IN (30,60,90)),
    quantity_dispensed  SMALLINT        NOT NULL CHECK (quantity_dispensed > 0),
    formulary_tier      TINYINT         NOT NULL,
    total_cost_usd      DECIMAL(10,2)   NOT NULL CHECK (total_cost_usd >= 0),
    member_copay_usd    DECIMAL(10,2)   NOT NULL DEFAULT 0,
    plan_paid_usd       DECIMAL(10,2)   NOT NULL DEFAULT 0,
    pharmacy_type       VARCHAR(20)     CHECK (pharmacy_type IN ('Retail','Mail Order','Specialty')),
    refill_number       TINYINT         DEFAULT 0,
    is_generic          BOOLEAN         DEFAULT FALSE,
    therapy_area        VARCHAR(60),
    created_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (member_id) REFERENCES members(member_id),
    FOREIGN KEY (drug_id)   REFERENCES drugs(drug_id),
    INDEX idx_rx_member     (member_id),
    INDEX idx_rx_drug       (drug_id),
    INDEX idx_rx_date       (service_date),
    INDEX idx_rx_therapy    (therapy_area),
    INDEX idx_rx_tier       (formulary_tier),
    INDEX idx_rx_pharmacy   (pharmacy_type)
);

CREATE TABLE prior_auth_requests (
    pa_id               VARCHAR(10)     NOT NULL PRIMARY KEY,
    rx_id               VARCHAR(12)     NOT NULL,
    drug_id             VARCHAR(10)     NOT NULL,
    member_id           VARCHAR(12)     NOT NULL,
    request_date        DATE            NOT NULL,
    decision_date       DATE,
    days_to_decision    SMALLINT,
    outcome             VARCHAR(20)     CHECK (outcome IN ('Approved','Denied','Pending','Appeal Approved')),
    denial_reason       VARCHAR(100),
    is_urgent           BOOLEAN         DEFAULT FALSE,
    appeal_filed        BOOLEAN         DEFAULT FALSE,
    created_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (rx_id)     REFERENCES prescriptions(rx_id),
    FOREIGN KEY (drug_id)   REFERENCES drugs(drug_id),
    FOREIGN KEY (member_id) REFERENCES members(member_id),
    INDEX idx_pa_drug     (drug_id),
    INDEX idx_pa_outcome  (outcome),
    INDEX idx_pa_date     (request_date),
    CONSTRAINT chk_decision_date CHECK (decision_date IS NULL OR decision_date >= request_date)
);

CREATE TABLE drug_spend_summary (
    summary_id      INT             NOT NULL AUTO_INCREMENT PRIMARY KEY,
    month           VARCHAR(7)      NOT NULL,
    drug_id         VARCHAR(10)     NOT NULL,
    therapy_area    VARCHAR(60),
    formulary_tier  TINYINT,
    pharmacy_type   VARCHAR(20),
    rx_count        INT             NOT NULL DEFAULT 0,
    total_cost      DECIMAL(12,2)   NOT NULL DEFAULT 0,
    member_copay    DECIMAL(12,2)   NOT NULL DEFAULT 0,
    plan_paid       DECIMAL(12,2)   NOT NULL DEFAULT 0,
    unique_members  INT             NOT NULL DEFAULT 0,
    created_at      TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (drug_id) REFERENCES drugs(drug_id),
    INDEX idx_spend_month    (month),
    INDEX idx_spend_drug     (drug_id),
    INDEX idx_spend_therapy  (therapy_area)
);

-- =============================================================================
-- AUDIT TABLE
-- =============================================================================

CREATE TABLE audit_log (
    log_id      BIGINT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    table_name  VARCHAR(50)     NOT NULL,
    record_id   VARCHAR(20)     NOT NULL,
    action      ENUM('INSERT','UPDATE','DELETE') NOT NULL,
    changed_by  VARCHAR(50)     DEFAULT (CURRENT_USER()),
    changed_at  TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    old_values  JSON,
    new_values  JSON,
    INDEX idx_audit_table  (table_name),
    INDEX idx_audit_time   (changed_at)
);

-- =============================================================================
-- STORED PROCEDURE: Formulary Tier Change Impact Analysis
-- =============================================================================

DELIMITER //
CREATE PROCEDURE sp_formulary_tier_impact(IN p_drug_id VARCHAR(10))
BEGIN
    SELECT
        d.brand_name,
        d.generic_name,
        f.plan_year,
        f.formulary_tier,
        f.tier_name,
        f.copay_pct,
        f.effective_date,
        f.change_reason,
        COUNT(p.rx_id)              AS rx_count_after_change,
        ROUND(SUM(p.total_cost_usd),2) AS total_spend_after_change,
        ROUND(AVG(p.member_copay_usd),2) AS avg_member_copay
    FROM formulary f
    JOIN drugs d ON f.drug_id = d.drug_id
    LEFT JOIN prescriptions p
        ON p.drug_id = f.drug_id
        AND p.service_date >= f.effective_date
        AND (p.service_date < f.end_date OR f.end_date IS NULL)
    WHERE f.drug_id = p_drug_id
    GROUP BY f.formulary_id, d.brand_name, d.generic_name,
             f.plan_year, f.formulary_tier, f.tier_name,
             f.copay_pct, f.effective_date, f.change_reason
    ORDER BY f.effective_date;
END //
DELIMITER ;

-- =============================================================================
-- VIEW: Current Active Formulary
-- =============================================================================

CREATE VIEW vw_current_formulary AS
SELECT
    d.drug_id,
    d.brand_name,
    d.generic_name,
    d.therapy_area,
    d.manufacturer,
    d.dosage_form,
    d.strength,
    d.unit_cost_usd,
    f.formulary_tier,
    f.tier_name,
    f.copay_pct,
    d.requires_prior_auth,
    d.is_specialty,
    d.is_cold_chain,
    f.effective_date AS tier_effective_date
FROM drugs d
JOIN formulary f ON d.drug_id = f.drug_id
WHERE f.end_date IS NULL
ORDER BY f.formulary_tier, d.therapy_area, d.brand_name;
