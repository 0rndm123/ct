-- Run with: psql -X -d COT -f sql/02_quality_checks.sql
\echo '== Database identity =='
SELECT current_database() AS connected_database;
\echo '== Coverage and recency by dataset =='
SELECT d.report_code,d.family,d.universe,d.first_year,
       count(r.report_date) AS rows,
       min(r.report_date) AS first_position_date,
       max(r.report_date) AS last_position_date
FROM cot.datasets d LEFT JOIN cot.reports r USING(dataset_id)
GROUP BY d.report_code,d.family,d.universe,d.first_year
ORDER BY d.report_code;
\echo '== Run status =='
SELECT run_id,mode,status,started_at,finished_at,left(error_message,120) AS error
FROM cot.ingest_runs
ORDER BY run_id DESC LIMIT 20;
\echo '== Failed/incomplete windows =='
SELECT run_id,dataset_id,from_date,to_date,expected_rows,fetched_rows,status,error_message
FROM cot.ingest_windows WHERE status <> 'completed'
ORDER BY run_id DESC,dataset_id LIMIT 50;
\echo '== Yearly history counts =='
SELECT d.report_code,EXTRACT(YEAR FROM r.report_date)::int AS report_year,
       count(*) AS rows
FROM cot.reports r JOIN cot.datasets d USING(dataset_id)
GROUP BY d.report_code,EXTRACT(YEAR FROM r.report_date)
ORDER BY d.report_code,report_year;
\echo '== Revisions recorded =='
SELECT dataset_id,count(*) AS revisions FROM cot.report_revisions
GROUP BY dataset_id ORDER BY dataset_id;
\echo '== Data quality outliers =='
SELECT dataset_id,count(*) FILTER (WHERE open_interest < 0) AS negative_oi,
       count(*) FILTER (WHERE open_interest IS NULL) AS missing_oi
FROM cot.reports GROUP BY dataset_id ORDER BY dataset_id;
