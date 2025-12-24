import os
import sys
import json
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_groq import ChatGroq
from langchain.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(override=True)

# --- CONFIGURATION ---
INDEX_FOLDER = "faiss_index"
GROQ_MODEL_NAME = "llama-3.3-70b-versatile"

def main():
    print("---  CYBERRAG INTELLIGENCE TERMINAL (Dual-LLM Architecture) ---")
    
    # 1. Check API Key
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("  Error: GROQ_API_KEY environment variable not set.")
        return
    
    api_key = api_key.strip()
    print(f" Loaded API Key: {api_key[:4]}{'*' * 10}{api_key[-4:]}")

    # 2. Load FAISS Index
    print(" Loading Knowledge Base (FAISS)...")
    try:
        embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        print("ℹ  Running Embeddings in CPU mode.")
        vectorstore = FAISS.load_local(INDEX_FOLDER, embeddings, allow_dangerous_deserialization=True)
        print(" Index loaded successfully.")
    except Exception as e:
        print(f" Failed to load index: {e}")
        return

    # 3. Initialize LLM
    print(f" Connecting to Groq Cloud ({GROQ_MODEL_NAME})...")
    try:
        llm = ChatGroq(temperature=0, model_name=GROQ_MODEL_NAME, groq_api_key=api_key)
    except Exception as e:
        print(f" Failed to initialize Groq LLM: {e}")
        return

    # 4. LLM Chain 1: Query Rewriter
    rewriter_prompt_template = """You are a MITRE ATT&CK expert query optimizer.

Your job: Convert raw security alerts into optimal search queries for a MITRE ATT&CK knowledge base.

INPUT: Raw alert (may contain IPs, timestamps, priorities)
OUTPUT: JSON with two fields:
1. "enhanced_query": Clean attack description for vector search
2. "iocs": Extracted indicators (source_ip, dest_ip, protocol)

EXAMPLES:
Input: "ET SCAN SSH Brute Force Attempt 192.168.1.1 → 192.168.1.5 TCP"
Output: {{"enhanced_query": "SSH brute force password guessing attack", "iocs": {{"source_ip": "192.168.1.1", "dest_ip": "192.168.1.5", "protocol": "TCP"}}}}

Input: "RECON ICMP Scan Detected 10.0.0.1"
Output: {{"enhanced_query": "ICMP ping sweep network reconnaissance", "iocs": {{"source_ip": "10.0.0.1", "protocol": "ICMP"}}}}

Input: "How do attackers dump lsass?"
Output: {{"enhanced_query": "LSASS memory credential dumping technique", "iocs": {{}}}}

RAW ALERT:
{raw_alert}

OUTPUT (JSON only, no explanation):"""

    rewriter_prompt = PromptTemplate(template=rewriter_prompt_template, input_variables=["raw_alert"])
    rewriter_chain = rewriter_prompt | llm | StrOutputParser()

    # 5. LLM Chain 2: Analysis Generator
    analyst_prompt_template = """You are CyberRAG, an expert SOC Analyst trained on MITRE ATT&CK.

CRITICAL RULES:
- ONLY map to techniques explicitly mentioned in the CONTEXT
- If alert mentions "brute force", cite T1110 techniques
- If alert mentions "credential dump", cite T1003 techniques
- Always include extracted IOCs in your analysis

RETRIEVED ATOMIC RED TEAM CONTEXT:
{context}

ORIGINAL SECURITY ALERT:
{original_alert}

EXTRACTED IOCs:
{iocs}

FORMAT YOUR RESPONSE:
### 🛡 MITRE ATT&CK MAPPING
- Technique ID: [from context]
- Technique Name: [from context]
- Confidence: [0.0-1.0]

###  ALERT DETAILS
{ioc_details}

### ANALYSIS
[Explain how alert matches retrieved technique, cite specific commands from context]

###  MITIGATION
[Actionable steps for THIS specific alert]

ANALYSIS:"""

    analyst_prompt = PromptTemplate(
        template=analyst_prompt_template,
        input_variables=["context", "original_alert", "iocs", "ioc_details"]
    )

    print("\n SYSTEM READY. Type 'exit' to quit.\n")

    # 6. Interactive Loop
    while True:
        query = input("\n🔎 Enter Security Alert or Question: ").strip()
        if query.lower() in ["exit", "quit", "q"]:
            print("Shutting down.")
            break
        if not query:
            continue

        try:
            # STEP 1: LLM Query Rewriter
            print(" Step 1/3: Rewriting query with LLM...")
            rewriter_output = rewriter_chain.invoke({"raw_alert": query})
            
            # Parse JSON output
            try:
                rewriter_data = json.loads(rewriter_output)
                enhanced_query = rewriter_data.get("enhanced_query", query)
                iocs = rewriter_data.get("iocs", {})
            except json.JSONDecodeError:
                # Fallback if LLM doesn't return valid JSON
                enhanced_query = query
                iocs = {}
            
            print(f" Enhanced Query: {enhanced_query}")
            if iocs:
                print(f"  Extracted IOCs: {iocs}")

            # STEP 2: RAG Vector Search
            print("🔄 Step 2/3: Searching knowledge base...")
            retrieved_docs = vectorstore.similarity_search(enhanced_query, k=4)
            
            # Build context string
            context_parts = []
            for i, doc in enumerate(retrieved_docs, 1):
                context_parts.append(f"[Source {i}] {doc.page_content}")
            context_str = "\n\n".join(context_parts)

            # STEP 3: LLM Analysis Generator
            print("� Step 3/3: Generating analysis...")
            
            # Format IOC details for display
            ioc_details = ""
            if iocs.get("source_ip"):
                ioc_details += f"- Source IP: {iocs['source_ip']}\n"
            if iocs.get("dest_ip"):
                ioc_details += f"- Destination IP: {iocs['dest_ip']}\n"
            if iocs.get("protocol"):
                ioc_details += f"- Protocol: {iocs['protocol']}\n"
            if not ioc_details:
                ioc_details = "- No IOCs extracted (clean query)\n"
            
            analysis = llm.invoke(
                analyst_prompt.format(
                    context=context_str,
                    original_alert=query,
                    iocs=json.dumps(iocs, indent=2),
                    ioc_details=ioc_details
                )
            ).content

            # Print Results
            print("\n" + "="*60)
            print("📝 ANALYSIS RESULT:")
            print("="*60)
            print(analysis)
            print("-" * 60)
            
            # Show sources
            print("\n SOURCES USED:")
            for i, doc in enumerate(retrieved_docs, 1):
                technique = doc.metadata.get('technique_name', 'Unknown')
                platform = doc.metadata.get('platform', 'Unknown')
                print(f"[{i}] {technique} ({platform})")
            print("="*60)
            
        except Exception as e:
            print(f" Error during analysis: {e}")

if __name__ == "__main__":
    main()
