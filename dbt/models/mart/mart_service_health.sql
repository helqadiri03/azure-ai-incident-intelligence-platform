{{
    config(
        materialized = 'view',
        description = 'Daily health aggregation per service.'
    )
}}

WITH daily_incidents AS (
    SELECT
        service_name,
        CAST(incident_start_time AS DATE) AS date,
        COUNT(incident_id) AS total_incidents,
        SUM(total_signals) AS total_negative_signals
    FROM {{ ref('fct_incidents') }}
    GROUP BY service_name, CAST(incident_start_time AS DATE)
),

daily_deployments AS (
    SELECT
        service_name,
        CAST(event_at AS DATE) AS date,
        COUNT(event_id) AS total_deployments
    FROM {{ ref('stg_raw_events') }}
    WHERE event_type = 'deployment'
    GROUP BY service_name, CAST(event_at AS DATE)
),

all_dates_services AS (
    SELECT DISTINCT service_name, date FROM daily_incidents
    UNION
    SELECT DISTINCT service_name, date FROM daily_deployments
)

SELECT
    a.service_name,
    a.date,
    COALESCE(i.total_incidents, 0) AS total_incidents,
    COALESCE(i.total_negative_signals, 0) AS total_negative_signals,
    COALESCE(d.total_deployments, 0) AS total_deployments
    
FROM all_dates_services a
LEFT JOIN daily_incidents i ON a.service_name = i.service_name AND a.date = i.date
LEFT JOIN daily_deployments d ON a.service_name = d.service_name AND a.date = d.date
