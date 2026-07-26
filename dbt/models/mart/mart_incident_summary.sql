{{
    config(
        materialized = 'view',
        description = 'Human-readable rollup of incident details for RAG context.'
    )
}}

/*
    mart_incident_summary.sql
    ─────────────────────────
    A flattened table combining the fact table and root cause.
    This is the ideal view to feed into the AI / RAG system.
*/

WITH incidents AS (
    SELECT * FROM {{ ref('fct_incidents') }}
),

root_causes AS (
    SELECT * FROM {{ ref('mart_root_cause') }}
)

SELECT
    i.incident_id,
    i.service_name,
    i.severity,
    i.incident_start_time,
    i.duration_minutes,
    i.total_signals,
    i.initial_symptom,
    r.primary_root_cause_category,
    r.suspected_deployment_id,
    r.minutes_since_deployment,
    
    -- Construct a narrative string for the LLM
    'Incident ' + i.incident_id + 
    ' on service ' + i.service_name + 
    ' started at ' + CAST(i.incident_start_time AS VARCHAR) +
    '. It lasted ' + CAST(i.duration_minutes AS VARCHAR) + ' minutes ' +
    'with ' + CAST(i.total_signals AS VARCHAR) + ' failure signals detected. ' +
    'Initial symptom: ' + COALESCE(i.initial_symptom, 'Unknown') + '. ' +
    'Root cause analysis points to: ' + r.primary_root_cause_category + '.'
    AS incident_narrative

FROM incidents i
JOIN root_causes r ON i.incident_id = r.incident_id
