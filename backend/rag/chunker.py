import os
import json
from pathlib import Path

def parse_document(file_path):
    """Read a formatted incident text file and extract metadata and chunks."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    metadata = {}
    chunks = []
    
    # Split the document into sections based on double newlines
    blocks = content.split('\n\n')
    
    for block in blocks:
        block = block.strip()
        if not block:
            continue
            
        if block.startswith("Incident ID:"):
            metadata['incident_id'] = block.replace("Incident ID:", "").strip()
        elif block.startswith("Azure Service:"):
            # Extract the actual value which is on the next line
            metadata['service'] = block.split('\n')[1].strip()
        elif block.startswith("Severity:"):
            metadata['severity'] = block.split('\n')[1].strip()
        elif block.startswith("Duration:"):
            metadata['duration'] = block.split('\n')[1].strip()
        elif block.startswith("Symptoms:"):
            chunks.append({
                "chunk_type": "Symptoms",
                "text": block
            })
        elif block.startswith("Root Cause:"):
            chunks.append({
                "chunk_type": "Root Cause",
                "text": block
            })
        elif block.startswith("Resolution:"):
            chunks.append({
                "chunk_type": "Resolution",
                "text": block
            })
            
    return metadata, chunks

def process_documents(input_dir="documents", output_dir="chunks"):
    """Process all incident text files and save them as chunked JSON documents."""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    if not input_path.exists():
        print(f"Error: Input directory '{input_dir}' does not exist.")
        print("Please run exporter.py first to generate the documents.")
        return
        
    total_files = 0
    total_chunks = 0
    
    for file_path in input_path.glob("*.txt"):
        metadata, chunks = parse_document(file_path)
        
        incident_id = metadata.get('incident_id', 'unknown')
        incident_chunks = []
        
        # Create a searchable item for each chunk, injecting metadata
        for i, chunk in enumerate(chunks):
            chunk_doc = {
                "id": f"{incident_id}_chunk_{i+1}",
                "incident_id": incident_id,
                "service": metadata.get('service'),
                "severity": metadata.get('severity'),
                "chunk_type": chunk["chunk_type"],
                "content": chunk["text"]
            }
            incident_chunks.append(chunk_doc)
            total_chunks += 1
            
        # Save chunks for this specific incident
        output_file = output_path / f"chunks_{incident_id}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(incident_chunks, f, indent=2)
            
        total_files += 1
            
    print(f"Successfully processed {total_files} incident files.")
    print(f"Generated {total_chunks} total searchable chunks.")
    print(f"Chunks saved to {output_dir}/ directory.")

if __name__ == "__main__":
    print("Starting document chunking process...")
    process_documents()
