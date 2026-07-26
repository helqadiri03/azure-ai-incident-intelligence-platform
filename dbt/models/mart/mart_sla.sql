{{
    config(
        materialized = 'view',
        description = 'Monthly SLA/uptime metrics per service.'
    )
}}

WITH monthly_downtime AS (
    SELECT
        service_name,
        -- Truncate to the start of the month
        DATEADD(month, DATEDIFF(month, 0, incident_start_time), 0) AS month_start,
        SUM(duration_minutes) AS total_downtime_minutes,
        COUNT(incident_id) AS total_incidents
    FROM {{ ref('fct_incidents') }}
    GROUP BY service_name, DATEADD(month, DATEDIFF(month, 0, incident_start_time), 0)
)

SELECT
    service_name,
    month_start,
    total_downtime_minutes,
    total_incidents,
    
    -- Assuming a 30-day month for simplicity in SLA calculation: 43200 total minutes
    -- (43200 - downtime) / 43200
    ROUND(((43200.0 - total_downtime_minutes) / 43200.0) * 100, 4) AS uptime_percentage,
    
    -- MTTR = total downtime / total incidents
    ROUND(total_downtime_minutes * 1.0 / NULLIF(total_incidents, 0), 2) AS mttr_minutes

FROM monthly_downtime
