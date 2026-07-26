{{
    config(
        materialized = 'view',
        description = 'Groups negative signals into discrete incidents using a 15-minute sliding window (sessionization).'
    )
}}

/*
    int_incidents.sql
    ─────────────────
    Groups consecutive negative signals for the same service into a single incident.
    If a service has a 15-minute gap without any negative signals, the next negative
    signal starts a new incident.
*/

WITH negative_signals AS (
    SELECT * FROM {{ ref('int_negative_signals') }}
),

-- 1. Order signals and get the timestamp of the previous signal for the same service
lagged AS (
    SELECT
        *,
        LAG(event_at) OVER (PARTITION BY service_name ORDER BY event_at ASC) AS prev_event_at
    FROM negative_signals
),

-- 2. Flag a signal as the start of a new incident if it's the first one, 
-- or if the gap from the previous one is > 15 minutes
session_flags AS (
    SELECT
        *,
        CASE 
            WHEN prev_event_at IS NULL THEN 1
            WHEN DATEDIFF(minute, prev_event_at, event_at) > 15 THEN 1
            ELSE 0 
        END AS is_new_incident
    FROM lagged
),

-- 3. Create a unique incident identifier using a cumulative sum of the flags
sessionized AS (
    SELECT
        *,
        -- Generate a unique hash for each incident session per service
        HASHBYTES('SHA2_256', 
            service_name + 
            CAST(SUM(is_new_incident) OVER (PARTITION BY service_name ORDER BY event_at ASC ROWS UNBOUNDED PRECEDING) AS VARCHAR)
        ) AS incident_hash
    FROM session_flags
),

-- 4. Aggregate the signals into incident rows
incidents AS (
    SELECT
        -- Convert varbinary hash to a hex string for easier joining downstream
        CONVERT(VARCHAR(64), incident_hash, 2) AS incident_id,
        service_name,
        MIN(event_at) AS incident_start_time,
        MAX(event_at) AS incident_end_time,
        COUNT(event_id) AS total_signals,
        
        -- Capture the first reason seen in this incident for context
        MIN(CASE WHEN is_new_incident = 1 THEN negative_reason END) AS initial_symptom
        
    FROM sessionized
    GROUP BY
        incident_hash,
        service_name
)

SELECT * FROM incidents
