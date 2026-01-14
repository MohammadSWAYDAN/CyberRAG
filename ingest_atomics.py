import os
import yaml
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document

# --- CONFIGURATION ---
# The folder where your "atomics" folder is located
DATASET_ROOT = os.path.join(os.getcwd(), "atomics")
# Where to save the FAISS index
INDEX_NAME = "faiss_index"

def main():
    print("STARTING CYBERRAG INGESTION (Propelled by LangChain)")
    
    # --- CPU CHECK & IMPORT VALIDATION ---
    try:
        import faiss # for embedding
        print(f"FAISS (CPU) successfully imported. Version: {faiss.__version__}")
        print("ℹ  Running in CPU mode as requested.")
    except ImportError:
        print("CRITICAL ERROR: 'faiss' module not found!")
        print("Please run: pip install faiss-cpu")
        print("Make sure you are in the correct Conda environment (agentic-ai).")
        return
    
    documents = []
    
    print(f"Scanning dataset at: {DATASET_ROOT}")
    count = 0
    
    # 1. Walk through the folder
    for root, dirs, files in os.walk(DATASET_ROOT):
        for file in files:
            if file.endswith(".yaml") and file.startswith("T"):
                file_path = os.path.join(root, file)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f)
                        
                    # Basic validation
                    if not data or 'atomic_tests' not in data:
                        continue
                        
                    technique_id = data.get('attack_technique', 'Unknown')
                    technique_name = data.get('display_name', 'Unknown')
                    
                    # 2. Process each Atomic Test
                    for test in data.get('atomic_tests', []):
                        test_name = test.get('name', 'Unnamed Test')
                        description = test.get('description', '').strip()
                        
                        # Get supported platforms (e.g., Windows, Linux)
                        platforms = test.get('supported_platforms', [])
                        platform_str = ", ".join(platforms) if platforms else "unknown"
                        
                        # Get the execution command
                        executor = test.get('executor', {})
                        command = executor.get('command', '')
                        executor_name = executor.get('name', 'unknown')
                        
                        # --- THE SPECIAL SAUCE: What goes into the Embedding? ---
                        # We combine Intent (Description) + Context (Technique)
                        page_content = f"""
                        Technique: {technique_id}: {technique_name}
                        Test Name: {test_name}
                        Platform: {platform_str}
                        Description: {description}
                        Command: {command}
                        """
                        
                        # --- METADATA ---
                        # In LangChain, metadata is a simple dictionary.
                        metadata = {
                            "technique_id": technique_id,
                            "technique_name": technique_name,
                            "test_name": test_name,
                            "platform": platform_str,
                            "executor": executor_name,
                            "command": command[:1000],  # Truncate if extreme
                            "source": file_path
                        }
                        
                        # Create LangChain Document
                        doc = Document(page_content=page_content, metadata=metadata)
                        documents.append(doc)
                        count += 1
                        
                        if count % 100 == 0:
                            print(f"Collected {count} tests...", end='\r')

                except Exception as e:
                    print(f" Error processing {file}: {e}")
    
    print(f"\n Data collected. Total documents: {len(documents)}")
    print("Initializing Embeddings (HuggingFace: all-MiniLM-L6-v2)...")
    
    # 3. Create Embeddings
    # This uses the local HuggingFace model (CPU friendly, free, no API key needed)
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    
    print("Building FAISS Vector Store (This may take a moment)...")
    
    # 4. Create Vector Store
    vectorstore = FAISS.from_documents(documents, embeddings)
    
    # 5. Save Locally
    print(f" Saving FAISS index to folder: ./{INDEX_NAME}")
    vectorstore.save_local(INDEX_NAME)

    print("\n SUCCESS! Index build complete.")
    

if __name__ == "__main__":
    main()
