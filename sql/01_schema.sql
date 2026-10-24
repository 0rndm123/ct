-- Execute inside the dedicated "COT" database.
BEGIN;
-- Older PostgreSQL installations may still allow PUBLIC to CREATE in public.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
-- All schema objects must be owned by cot_loader, NOT by the admin account.
SET LOCAL ROLE cot_loader;
CREATE SCHEMA IF NOT EXISTS cot AUTHORIZATION cot_loader;

CREATE TABLE IF NOT EXISTS cot.datasets (
    dataset_id text PRIMARY KEY CHECK (dataset_id ~ '^[a-z0-9]{4}-[a-z0-9]{4}$'),
    report_code text NOT NULL UNIQUE,
    family text NOT NULL CHECK (family IN ('legacy','disaggregated','tff','supplemental')),
    universe text NOT NULL CHECK (universe IN ('futures_only','futures_options_combined')),
    first_year smallint NOT NULL,
    source_url text NOT NULL,
    enabled boolean NOT NULL DEFAULT true
);

INSERT INTO cot.datasets(dataset_id,report_code,family,universe,first_year,source_url) VALUES
('6dca-aqww','legacy_futures','legacy','futures_only',1986,'https://publicreporting.cftc.gov/resource/6dca-aqww.json'),
('jun7-fc8e','legacy_combined','legacy','futures_options_combined',1995,'https://publicreporting.cftc.gov/resource/jun7-fc8e.json'),
('72hh-3qpy','disaggregated_futures','disaggregated','futures_only',2006,'https://publicreporting.cftc.gov/resource/72hh-3qpy.json'),
('kh3c-gbw2','disaggregated_combined','disaggregated','futures_options_combined',2006,'https://publicreporting.cftc.gov/resource/kh3c-gbw2.json'),
('gpe5-46if','tff_futures','tff','futures_only',2006,'https://publicreporting.cftc.gov/resource/gpe5-46if.json'),
('yw9f-hn96','tff_combined','tff','futures_options_combined',2006,'https://publicreporting.cftc.gov/resource/yw9f-hn96.json'),
('4zgm-a668','supplemental_cit','supplemental','futures_options_combined',2006,'https://publicreporting.cftc.gov/resource/4zgm-a668.json')
ON CONFLICT (dataset_id) DO UPDATE SET
report_code=excluded.report_code,
family=excluded.family,
universe=excluded.universe,
first_year=excluded.first_year,
source_url=excluded.source_url;

CREATE TABLE IF NOT EXISTS cot.ingest_runs (
    run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mode text NOT NULL CHECK (mode IN ('history','weekly')),
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status text NOT NULL DEFAULT 'running' CHECK (status IN ('running','completed','failed')),
    error_message text
);

CREATE TABLE IF NOT EXISTS cot.ingest_windows (
    run_id bigint NOT NULL REFERENCES cot.ingest_runs(run_id),
    dataset_id text NOT NULL REFERENCES cot.datasets(dataset_id),
    from_date date NOT NULL,
    to_date date NOT NULL, -- upper bound exclusive
    expected_rows bigint,
    fetched_rows bigint NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'running' CHECK (status IN ('running','completed','failed')),
    error_message text,
    archive_manifest text,
    source_file text,
    PRIMARY KEY (run_id,dataset_id,from_date,to_date),
    CHECK(to_date > from_date)
);

-- Compatible with schema installations created before raw-file preservation.
ALTER TABLE cot.ingest_windows ADD COLUMN IF NOT EXISTS archive_manifest text;
ALTER TABLE cot.ingest_windows ADD COLUMN IF NOT EXISTS source_file text;

CREATE TABLE IF NOT EXISTS cot.reports (
    dataset_id text NOT NULL REFERENCES cot.datasets(dataset_id),
    report_date date NOT NULL,
    cftc_contract_market_code text NOT NULL CHECK (length(trim(cftc_contract_market_code)) > 0),
    market_and_exchange_names text NOT NULL CHECK (length(trim(market_and_exchange_names)) > 0),
    source_id text,
    cftc_market_code text,
    cftc_commodity_code text,
    commodity_name text,
    commodity_group_name text,
    commodity_subgroup_name text,
    contract_market_name text,
    open_interest numeric,
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    payload_sha256 char(64) NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_changed_at timestamptz NOT NULL DEFAULT now(),
    last_checked_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_id, report_date, cftc_contract_market_code, market_and_exchange_names)
);
CREATE INDEX IF NOT EXISTS idx_cot_reports_date ON cot.reports (report_date DESC);
CREATE INDEX IF NOT EXISTS idx_cot_reports_market_date ON cot.reports (cftc_contract_market_code,report_date DESC);
CREATE INDEX IF NOT EXISTS idx_cot_reports_dataset_date ON cot.reports (dataset_id,report_date DESC);
CREATE INDEX IF NOT EXISTS idx_cot_reports_commodity ON cot.reports (commodity_name);

-- Current successfully loaded source file per report family and CFTC position date.
-- Hash enables incremental runs without touching identical rows.
-- Source provenance by CFTC reporting date. Existing records remain immutable unless source changes.
CREATE TABLE IF NOT EXISTS cot.source_files (
    dataset_id text NOT NULL REFERENCES cot.datasets(dataset_id),
    report_date date NOT NULL,
    source_file text NOT NULL,
    file_sha256 char(64) NOT NULL
        CHECK (length(file_sha256) = 64 AND file_sha256 !~ '[^0-9a-f]'),
    row_count integer NOT NULL CHECK (row_count > 0),
    first_loaded_at timestamptz NOT NULL DEFAULT now(),
    last_loaded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_id, report_date)
);
CREATE INDEX IF NOT EXISTS idx_source_files_date ON cot.source_files (report_date DESC);

CREATE TABLE IF NOT EXISTS cot.report_revisions (
    revision_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_id text NOT NULL,
    report_date date NOT NULL,
    cftc_contract_market_code text NOT NULL,
    market_and_exchange_names text NOT NULL,
    previous_payload jsonb NOT NULL,
    previous_payload_sha256 char(64) NOT NULL,
    replaced_at timestamptz NOT NULL DEFAULT now()
);
CREATE OR REPLACE FUNCTION cot.audit_report_revision() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.payload_sha256 IS DISTINCT FROM NEW.payload_sha256 THEN
        INSERT INTO cot.report_revisions (
            dataset_id,report_date,cftc_contract_market_code,market_and_exchange_names,
            previous_payload,previous_payload_sha256
        ) VALUES (
            OLD.dataset_id,OLD.report_date,OLD.cftc_contract_market_code,OLD.market_and_exchange_names,
            OLD.payload,OLD.payload_sha256
        );
        NEW.last_changed_at := now();
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_cot_report_revision ON cot.reports;
CREATE TRIGGER trg_cot_report_revision BEFORE UPDATE ON cot.reports
FOR EACH ROW EXECUTE FUNCTION cot.audit_report_revision();

CREATE OR REPLACE VIEW cot.v_latest_reports AS
SELECT DISTINCT ON (r.dataset_id,r.cftc_contract_market_code)
    d.report_code,d.family,d.universe,r.*
FROM cot.reports r JOIN cot.datasets d USING (dataset_id)
ORDER BY r.dataset_id,r.cftc_contract_market_code,r.report_date DESC,r.market_and_exchange_names;

-- Query arbitrary numeric source fields without assuming common family-specific names.
CREATE OR REPLACE VIEW cot.v_numeric_metrics AS
SELECT d.report_code,d.family,d.universe,
       r.report_date,r.cftc_contract_market_code,r.market_and_exchange_names,
       kv.key AS metric_name,
       CASE WHEN kv.value ~ '^[+-]?[0-9]+([.][0-9]+)?$'
            THEN kv.value::numeric ELSE NULL END AS metric_value
FROM cot.reports r
JOIN cot.datasets d USING (dataset_id)
CROSS JOIN LATERAL jsonb_each_text(r.payload) AS kv(key,value)
WHERE kv.value ~ '^[+-]?[0-9]+([.][0-9]+)?$';

-- Coverage of all seven datasets by reporting date.
CREATE OR REPLACE VIEW cot.v_report_coverage AS
SELECT r.report_date, d.report_code, count(*)::bigint AS contract_rows,
       max(s.file_sha256) AS source_sha256,
       max(s.last_loaded_at) AS last_loaded_at
FROM cot.reports r
JOIN cot.datasets d USING (dataset_id)
LEFT JOIN cot.source_files s
       ON s.dataset_id = r.dataset_id AND s.report_date = r.report_date
GROUP BY r.report_date, d.report_code;

-- Applications have read-only access; ingestion exclusively uses cot_loader.
GRANT USAGE ON SCHEMA cot TO cot_app;
GRANT SELECT ON ALL TABLES IN SCHEMA cot TO cot_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA cot GRANT SELECT ON TABLES TO cot_app;

COMMIT;
