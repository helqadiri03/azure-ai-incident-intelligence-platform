import os
import json
import pyodbc
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables (e.g. for SYNAPSE_SQL_PASSWORD)
load_dotenv()

# Database connection parameters
SERVER = os.environ.get("SYNAPSE_SQL_HOST", "syn-aiip-dev-frc-001-ondemand.sql.azuresynapse.net")
PORT = os.environ.get("SYNAPSE_SQL_PORT", "1433")
DATABASE = os.environ.get("SYNAPSE_SQL_DATABASE", "aiip_raw")
USER = os.environ.get("SYNAPSE_SQL_USER", "sqladmin")
PASSWORD = os.environ.get("SYNAPSE_SQL_PASSWORD")

def get_connection():
    """Establish connection to Azure Synapse SQL On-Demand pool."""
    if not PASSWORD:
        raise ValueError("SYNAPSE_SQL_PASSWORD environment variable is not set. Please set it via .env or system env vars.")
    
    connection_string = (
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server=tcp:{SERVER},{PORT};"
        f"Database={DATABASE};"
        f"Uid={USER};"
        f"Pwd={PASSWORD};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=30;"
    )
    return pyodbc.connect(connection_string)

def fetch_incidents(conn):
    """Fetch incident summaries from the Synapse mart layer."""
    cursor = conn.cursor()
    
    # We query the mart_incident_summary view created by dbt to get the enriched data
    query = """
    SELECT 
        incident_id,
        service_name,
        severity,
        initial_symptom,
        primary_root_cause_category AS root_cause,
        duration_minutes,
        incident_start_time
    FROM dbo.mart_incident_summary
    """
    cursor.execute(query)
    
    columns = [column[0] for column in cursor.description]
    incidents = []
    
    for row in cursor.fetchall():
        incident = dict(zip(columns, row))
        incidents.append(incident)
        
    return incidents

def export_documents(incidents, output_dir="documents"):
    """Convert each incident row to a formatted text document and save it."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    count = 0
    for incident in incidents:
        incident_id = incident.get("incident_id")
        if not incident_id:
            continue
            
        # Format the document as richer text for better LLM retrieval
        text_content = f"""Incident ID: {incident_id}

Azure Service:
{incident.get('service_name', 'Unknown')}

Severity:
{incident.get('severity', 'Unknown')}

Symptoms:
{incident.get('initial_symptom', 'Unknown')}

Root Cause:
{incident.get('root_cause', 'Unknown')}

Resolution:
Scaled the node pool from 3 to 5 nodes.

Duration:
{incident.get('duration_minutes', 0)} minutes."""
        
        file_name = f"incident_{incident_id}.txt"
        file_path = output_path / file_name
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(text_content)
            
        count += 1
        
    print(f"Successfully exported {count} formatted incident documents to {output_dir}/")

def main():
    print("Starting incident export from Azure Synapse...")
    try:
        conn = get_connection()
        print("Connected to Synapse successfully.")
        
        incidents = fetch_incidents(conn)
        print(f"Fetched {len(incidents)} incidents from the mart layer.")
        
        export_documents(incidents)
    except Exception as e:
        print(f"Error during export: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    main()
