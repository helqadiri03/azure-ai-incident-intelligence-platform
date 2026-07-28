import json

def make_sql_stat(title, query, x, y, w, h, id):
    return {
        "id": id, "title": title, "type": "stat",
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "datasource": {"uid": "P8EDE85F80A37D6DB", "type": "mssql"},
        "targets": [{"refId": "A", "datasource": {"uid": "P8EDE85F80A37D6DB", "type": "mssql"}, "rawSql": query, "format": "table"}],
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"}
    }

def make_prom_stat(title, expr, x, y, w, h, id, unit=""):
    panel = {
        "id": id, "title": title, "type": "stat",
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "datasource": {"uid": "PBFA97CFB590B2093", "type": "prometheus"},
        "targets": [{"refId": "A", "expr": expr, "datasource": {"uid": "PBFA97CFB590B2093", "type": "prometheus"}}],
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"}
    }
    if unit:
        panel["fieldConfig"] = {"defaults": {"unit": unit}}
    return panel

def make_sql_barchart(title, query, x, y, w, h, id):
    return {
        "id": id, "title": title, "type": "barchart",
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "datasource": {"uid": "P8EDE85F80A37D6DB", "type": "mssql"},
        "targets": [{"refId": "A", "datasource": {"uid": "P8EDE85F80A37D6DB", "type": "mssql"}, "rawSql": query, "format": "table"}],
        "options": {"orientation": "horizontal"}
    }

panels = [
    # Row 1: Overview
    {"id": 100, "type": "row", "title": "────────────────────────────────────────── AI INCIDENT INTELLIGENCE PLATFORM ──────────────────────────────────────────", "gridPos": {"x": 0, "y": 0, "w": 24, "h": 1}},
    make_sql_stat("Total Incidents", "SELECT COUNT(*) FROM dbo_mart.mart_incident_summary", 0, 1, 6, 4, 1),
    make_sql_stat("Critical Incidents", "SELECT COUNT(*) FROM dbo_mart.mart_incident_summary WHERE severity = 'Critical'", 6, 1, 6, 4, 2),
    make_sql_stat("Open Incidents", "SELECT COUNT(*) FROM dbo_mart.fct_incidents WHERE duration_minutes IS NULL", 12, 1, 6, 4, 3),
    make_sql_stat("Average MTTR (min)", "SELECT AVG(duration_minutes) FROM dbo_mart.fct_incidents", 18, 1, 6, 4, 4),

    # Row 2: AI Assistant
    {"id": 101, "type": "row", "title": "────────────────────────────────────────── AI Assistant ──────────────────────────────────────────", "gridPos": {"x": 0, "y": 5, "w": 24, "h": 1}},
    make_prom_stat("Questions Answered", "rag_total_requests_total", 0, 6, 6, 4, 5),
    make_prom_stat("Confidence", "rag_avg_confidence_score", 6, 6, 6, 4, 6, unit="percent"),
    make_prom_stat("Response Time (ms)", "rag_avg_llm_latency_ms + rag_avg_search_latency_ms", 12, 6, 6, 4, 7),
    make_prom_stat("Helpful Feedback", "(rag_helpful_feedback_total / (rag_helpful_feedback_total + rag_unhelpful_feedback_total)) * 100", 18, 6, 6, 4, 8, unit="percent"),

    # Row 3: Details
    {"id": 102, "type": "row", "title": "────────────────────────────────────────── Insights ──────────────────────────────────────────", "gridPos": {"x": 0, "y": 10, "w": 24, "h": 1}},
    make_sql_barchart("Top Services", "SELECT service_name, COUNT(*) as count FROM dbo_mart.mart_incident_summary GROUP BY service_name ORDER BY count DESC", 0, 11, 8, 8, 9),
    make_sql_barchart("Root Causes", "SELECT primary_root_cause_category, COUNT(*) as count FROM dbo_mart.mart_incident_summary GROUP BY primary_root_cause_category ORDER BY count DESC", 8, 11, 8, 8, 10),
    
    # Platform Health stacked vertically
    make_prom_stat("API Uptime", "up{job='backend'} * 100", 16, 11, 8, 3, 11, unit="percent"),
    make_sql_stat("Embedding Index", "SELECT COUNT(*) FROM dbo.raw_events", 16, 14, 8, 2, 12),
    make_prom_stat("Last Sync", "time() - process_start_time_seconds{job='backend'}", 16, 16, 8, 3, 13, unit="s")
]

dashboard = {
    "title": "Incident Intelligence Overview",
    "uid": "e15967ee-e0fa-400c-b26a-b2f518e98629",
    "tags": [],
    "schemaVersion": 39,
    "version": 2,
    "panels": panels,
    "time": {"from": "now-6h", "to": "now"}
}

with open("/home/helqadiri/Desktop/AI-Incident-Intelligence-Platform/monitoring/grafana/dashboards/incident_intelligence.json", "w") as f:
    json.dump(dashboard, f, indent=2)
