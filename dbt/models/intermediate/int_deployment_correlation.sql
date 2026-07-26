{{
    config(
        materialized = 'view',
        description = 'Correlates incidents with deployments that occurred shortly before the incident started.'
    )
}}

/*
    int_deployment_correlation.sql
    ──────────────────────────────
    Identifies potential root causes by finding GitHub deployments that
    completed within 60 minutes prior to an incident starting.
*/

WITH incidents AS (
    SELECT * FROM {{ ref('int_incidents') }}
),

deployments AS (
    SELECT
        event_id AS deployment_id,
        service_name,
        event_at AS deployment_time,
        deployment_conclusion
    FROM {{ ref('stg_raw_events') }}
    WHERE event_type = 'deployment'
),

correlated AS (
    SELECT
        i.incident_id,
        d.deployment_id,
        d.deployment_time,
        d.deployment_conclusion,
        DATEDIFF(minute, d.deployment_time, i.incident_start_time) AS minutes_since_deployment,
        
        -- Rank deployments just in case multiple happened within the window
        ROW_NUMBER() OVER (PARTITION BY i.incident_id ORDER BY d.deployment_time DESC) AS deployment_rank
        
    FROM incidents i
    JOIN deployments d 
      ON i.service_name = d.service_name
    WHERE 
        -- Deployment happened before the incident
        d.deployment_time <= i.incident_start_time
        -- And within 60 minutes
        AND DATEDIFF(minute, d.deployment_time, i.incident_start_time) <= 60
)

-- Only keep the most recent deployment prior to the incident
SELECT * FROM correlated WHERE deployment_rank = 1
