import os
import json
import pyodbc
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

from openai import AzureOpenAI
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

from pipeline import (
    fetch_incidents,
    fetch_all_incident_ids,
    chunk_incident,
    embed_chunks,
    upsert_to_search,
    delete_from_search,
    get_indexed_incident_ids
)

load_dotenv()

AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY  = os.environ.get("AZURE_OPENAI_API_KEY")

SEARCH_ENDPOINT   = os.environ.get("AZURE_SEARCH_ENDPOINT")
SEARCH_API_KEY    = os.environ.get("AZURE_SEARCH_KEY")
SEARCH_INDEX_NAME = os.environ.get("AZURE_SEARCH_INDEX_NAME", "incident-chunks-index")

SERVER   = os.environ.get("SYNAPSE_SQL_HOST", "syn-aiip-dev-frc-001-ondemand.sql.azuresynapse.net")
PORT     = os.environ.get("SYNAPSE_SQL_PORT", "1433")
DATABASE = os.environ.get("SYNAPSE_SQL_DATABASE", "aiip_raw")
USER     = os.environ.get("SYNAPSE_SQL_USER", "sqladmin")
PASSWORD = os.environ.get("SYNAPSE_SQL_PASSWORD")

STATE_FILE = Path("backend/rag/.last_run_state.json")

def load_last_run() -> str:
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            return json.load(f).get("last_run", "1970-01-01 00:00:00")
    return "1970-01-01 00:00:00"

def save_last_run(timestamp: str):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump({"last_run": timestamp}, f, indent=2)
    print(f"State saved: {timestamp}")

def get_connection():
    conn_str = (
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server=tcp:{SERVER},{PORT};"
        f"Database={DATABASE};"
        f"Uid={USER};"
        f"Pwd={PASSWORD};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=30;"
    )
    return pyodbc.connect(conn_str)

def run():
    print("=" * 60)
    print("  RAG Incremental Updater & Deletion Sync")
    print(f"  Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    last_run = load_last_run()
    print(f"\n[1] Last successful run: {last_run}")

    conn = None
    try:
        conn = get_connection()
    except Exception as e:
        print(f"Synapse connection failed: {e}")
        return

    # --- UPSERT FLOW ---
    print(f"\n[2] Fetching updated incidents...")
    new_incidents = fetch_incidents(conn, last_run)
    
    if new_incidents:
        print(f"  -> Found {len(new_incidents)} incident(s) to process.")
        
        all_chunks = []
        for incident in new_incidents:
            all_chunks.extend(chunk_incident(incident))
        print(f"  -> Formatted {len(all_chunks)} chunks.")

        print(f"\n[3] Generating embeddings...")
        openai_client = AzureOpenAI(
            api_key=AZURE_OPENAI_API_KEY,
            api_version="2023-05-15",
            azure_endpoint=AZURE_OPENAI_ENDPOINT
        )
        all_chunks = embed_chunks(all_chunks, openai_client)

        print(f"\n[4] Upserting to Azure AI Search...")
        if SEARCH_API_KEY:
            search_client = SearchClient(
                endpoint=SEARCH_ENDPOINT,
                index_name=SEARCH_INDEX_NAME,
                credential=AzureKeyCredential(SEARCH_API_KEY)
            )
            upserted = upsert_to_search(all_chunks, search_client)
            print(f"  -> Upserted {upserted} chunks.")
        else:
            print("  -> Skipped upsert (SEARCH_API_KEY missing).")
    else:
        print("  -> No new or updated incidents.")

    # --- DELETION SYNC FLOW ---
    print(f"\n[5] Checking for deleted incidents...")
    if SEARCH_API_KEY:
        search_client = SearchClient(
            endpoint=SEARCH_ENDPOINT,
            index_name=SEARCH_INDEX_NAME,
            credential=AzureKeyCredential(SEARCH_API_KEY)
        )
        synapse_ids = fetch_all_incident_ids(conn)
        search_ids = get_indexed_incident_ids(search_client)
        
        orphaned_ids = list(search_ids - synapse_ids)
        if orphaned_ids:
            print(f"  -> Found {len(orphaned_ids)} orphaned incident(s). Deleting chunks...")
            deleted = delete_from_search(orphaned_ids, search_client)
            print(f"  -> Deleted {deleted} chunks.")
        else:
            print("  -> No orphaned chunks to delete.")

    conn.close()
    
    current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    save_last_run(current_time)
    print("\nUpdate complete.\n")

if __name__ == "__main__":
    run()
