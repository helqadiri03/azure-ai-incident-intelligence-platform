{{
    config(
        materialized = 'view',
        description = 'Candidate root cause for each incident, including correlated deployments.'
    )
}}

/*
    mart_root_cause.sql
    ───────────────────
    Combines incidents with their correlated deployments to establish root cause candidates.
*/

WITH incidents AS (
    SELECT * FROM {{ ref('fct_incidents') }}
),

deployments AS (
    SELECT * FROM {{ ref('int_deployment_correlation') }}
)

SELECT
    i.incident_id,
    i.service_name,
    i.severity,
    i.initial_symptom,
    
    -- Root cause candidates
    CASE
        WHEN d.deployment_id IS NOT NULL THEN 'Recent Deployment (' + d.deployment_conclusion + ')'
        ELSE 'Unknown / Environmental'
    END AS primary_root_cause_category,
    
    d.deployment_id AS suspected_deployment_id,
    d.minutes_since_deployment

FROM incidents i
LEFT JOIN deployments d ON i.incident_id = d.incident_id
