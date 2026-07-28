import os
from dotenv import load_dotenv

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    SemanticConfiguration,
    SemanticPrioritizedFields,
    SemanticField,
    SemanticSearch
)

load_dotenv()

SEARCH_ENDPOINT   = os.environ.get("SEARCH_ENDPOINT") or os.environ.get("AZURE_SEARCH_ENDPOINT")
SEARCH_API_KEY    = os.environ.get("SEARCH_API_KEY") or os.environ.get("AZURE_SEARCH_KEY")
SEARCH_INDEX_NAME = os.environ.get("AZURE_SEARCH_INDEX_NAME", "incident-chunks-index")
EMBEDDING_DIMS    = 1536  # Both ada-002 and text-embedding-3-small use 1536 dimensions
HAS_OPENAI        = bool(os.environ.get("AZURE_OPENAI_API_KEY"))

def setup_search_index():
    """
    Create or update the Azure AI Search index schema.
    Includes rich metadata fields, vector search configuration, 
    and semantic search configuration for hybrid reranking.
    """
    if not SEARCH_API_KEY or not SEARCH_ENDPOINT:
        print("Skipping index setup: AZURE_SEARCH_KEY or AZURE_SEARCH_ENDPOINT not set.")
        return

    credential = AzureKeyCredential(SEARCH_API_KEY)
    index_client = SearchIndexClient(endpoint=SEARCH_ENDPOINT, credential=credential)
    
    # 1. Vector Search Configuration
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="myHnsw")],
        profiles=[
            VectorSearchProfile(
                name="myHnswProfile",
                algorithm_configuration_name="myHnsw",
            )
        ]
    )
    
    # 2. Semantic Search Configuration (for Hybrid Reranking)
    semantic_config = SemanticConfiguration(
        name="mySemanticConfig",
        prioritized_fields=SemanticPrioritizedFields(
            title_field=SemanticField(field_name="incident_id"),
            content_fields=[SemanticField(field_name="content")],
            keywords_fields=[SemanticField(field_name="service"), SemanticField(field_name="chunk_type")]
        )
    )
    semantic_search = SemanticSearch(configurations=[semantic_config])
    
    # 3. Schema Fields (Rich Metadata)
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="content", type=SearchFieldDataType.String),

        # Rich metadata for citations and filtering
        SimpleField(name="incident_id", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="service", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="severity", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="chunk_type", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="date", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="environment", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="resource_group", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="region", type=SearchFieldDataType.String, filterable=True),
    ]

    # Only add vector field if Azure OpenAI is configured
    if HAS_OPENAI:
        fields.append(
            SearchField(
                name="embedding",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=EMBEDDING_DIMS,
                vector_search_profile_name="myHnswProfile",
            )
        )

    index = SearchIndex(
        name=SEARCH_INDEX_NAME, 
        fields=fields, 
        vector_search=vector_search,
        semantic_search=semantic_search
    )
    
    try:
        index_client.create_or_update_index(index)
        print(f"Azure AI Search index '{SEARCH_INDEX_NAME}' configured successfully (Hybrid + Semantic).")
    except Exception as e:
        print(f"Error creating search index: {e}")

if __name__ == "__main__":
    print("--- Setting up Azure AI Search Index ---")
    setup_search_index()
