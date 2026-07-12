import os
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

from app.config import settings
from app.state import AgentState
from app.schemas import SupplierDocumentFields, DuplicateDecision
from app.tools.ocr import extract_text_from_document
from app.tools.duplicate import search_vendor_duplicates

# Setup Gemini Model
if not settings.GEMINI_API_KEY:
    # Dummy mock model if no API key is provided
    # In a real environment, you must provide GEMINI_API_KEY in .env
    pass

class Route(BaseModel):
    next_node: str = Field(description="The next agent to route to: 'document_extraction_agent', 'duplicate_detection_agent', 'risk_agent', or 'END'")
    reasoning: str = Field(description="Why this route was chosen based on the current case state")

def supervisor_node(state: AgentState) -> dict:
    print(f"--- SUPERVISOR NODE --- Case: {state.get('case_id')}")
    
    # If we don't have a Gemini API key yet, just route to END safely for testing
    if not settings.GEMINI_API_KEY:
        print("WARNING: No GEMINI_API_KEY found. Routing to END.")
        return {"next_node": "END"}
        
    llm = ChatGoogleGenerativeAI(
        model=settings.DEFAULT_MODEL,
        google_api_key=settings.GEMINI_API_KEY,
        temperature=0.1
    )
    
    # In LangGraph 0.1.5, we can use bind_tools or structured output.
    # We will use with_structured_output for strict routing.
    router_llm = llm.with_structured_output(Route)
    
    system_prompt = (
        "You are the Supervisor Agent for the Vendor-to-Pay Exception System. "
        "Your job is to route to the correct specialist agent based on the CURRENT STATE.\n\n"
        f"CURRENT STATE:\n"
        f"- Vendor Extracted: {'YES' if state.get('current_vendor') else 'NO'}\n"
        f"- Duplicate Checked: {'YES' if state.get('duplicate_status') else 'NO'}\n"
        f"- Risk Checked: {'YES' if state.get('risk_level') else 'NO'}\n\n"
        "ROUTING RULES:\n"
        "1. If Vendor Extracted is NO, route to 'document_extraction_agent'.\n"
        "2. If Vendor Extracted is YES but Duplicate Checked is NO, route to 'duplicate_detection_agent'.\n"
        "3. If Duplicate Checked is YES but Risk Checked is NO, route to 'risk_agent'.\n"
        "4. If all are YES, route to 'END'."
    )
    
    messages = [SystemMessage(content=system_prompt)] + list(state.get("messages", []))
    
    try:
        response = router_llm.invoke(messages)
        if isinstance(response, list):
            response = response[0]
            
        if isinstance(response, dict):
            next_node = response.get("next_node", "END")
            reasoning = response.get("reasoning", "No reasoning provided")
        else:
            next_node = getattr(response, "next_node", "END")
            reasoning = getattr(response, "reasoning", "No reasoning provided")
            
        print(f"Routing Decision: {next_node} - Reason: {reasoning}")
        return {"next_node": next_node}
    except Exception as e:
        print(f"Error in Supervisor: {e}")
        return {"next_node": "END"}

def document_extraction_node(state: AgentState) -> dict:
    print(f"--- DOCUMENT EXTRACTION AGENT --- Case: {state.get('case_id')}")
    
    if not settings.GEMINI_API_KEY:
        print("WARNING: No GEMINI_API_KEY found. Returning stub data.")
        return {
            "messages": [SystemMessage(content="Extracted data from documents successfully (STUB).")],
            "current_vendor": {"vendor_name": "Extracted Vendor Inc.", "tax_id": "12345"}
        }
        
    try:
        # Step 1: Call OCR tool
        ocr_text = extract_text_from_document() # Using simulation mode by default for MVP unless URL is passed
        print("OCR Text Extracted successfully.")
        
        # Step 2: Extract structured data using LLM
        llm = ChatGoogleGenerativeAI(
            model=settings.DEFAULT_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.0
        )
        extraction_llm = llm.with_structured_output(SupplierDocumentFields)
        
        prompt = (
            "Extract the following supplier details from the OCR text provided below. "
            "If a field is not present, leave it null/None.\n\n"
            f"OCR TEXT:\n{ocr_text}"
        )
        
        extracted_data = extraction_llm.invoke(prompt)
        
        # Handle response format
        if isinstance(extracted_data, list):
            extracted_data = extracted_data[0]
            
        if isinstance(extracted_data, BaseModel):
            vendor_dict = extracted_data.model_dump()
        elif isinstance(extracted_data, dict):
            vendor_dict = extracted_data
        else:
            vendor_dict = getattr(extracted_data, "dict", lambda: {})()
            
        print(f"Extracted Vendor Data: {vendor_dict}")
        
        return {
            "messages": [SystemMessage(content=f"Document Extraction Complete. Found vendor: {vendor_dict.get('vendor_name', 'Unknown')}")],
            "current_vendor": vendor_dict
        }
        
    except Exception as e:
        print(f"Error in Document Extraction: {e}")
        return {
            "messages": [SystemMessage(content=f"Document Extraction failed: {str(e)}")]
        }

def duplicate_detection_node(state: AgentState) -> dict:
    print(f"--- DUPLICATE DETECTION AGENT --- Case: {state.get('case_id')}")
    
    vendor = state.get("current_vendor")
    if not vendor:
        return {"duplicate_status": "SKIPPED", "messages": [SystemMessage(content="No vendor data to check duplicates for.")]}
        
    vendor_name = vendor.get("vendor_name", "")
    tax_id = vendor.get("tax_id")
    
    # Step 1: Query potential duplicates
    print(f"Searching ERP for duplicates for: {vendor_name}")
    potential_matches = search_vendor_duplicates(vendor_name, tax_id)
    
    if not potential_matches:
        print("No potential duplicates found.")
        return {
            "duplicate_status": "NO_DUPLICATES",
            "messages": [SystemMessage(content="Duplicate check complete. No matching ERP vendors found.")]
        }
        
    if not settings.GEMINI_API_KEY:
        print("WARNING: No GEMINI API Key, returning stub duplicate check.")
        return {"duplicate_status": "POTENTIAL_DUPLICATE_FOUND"}

    # Step 2: Use LLM to reason about the matches
    llm = ChatGoogleGenerativeAI(
        model=settings.DEFAULT_MODEL,
        google_api_key=settings.GEMINI_API_KEY,
        temperature=0.1
    )
    duplicate_llm = llm.with_structured_output(DuplicateDecision)
    
    prompt = (
        "You are a master data governance agent. We extracted a vendor from a document and searched our ERP system for similar vendors.\n"
        "Your job is to look at the newly extracted vendor and the potential ERP matches, and determine if this is likely a DUPLICATE.\n\n"
        f"EXTRACTED VENDOR:\nName: {vendor_name}\nTax ID: {tax_id}\n\n"
        f"POTENTIAL ERP MATCHES:\n{potential_matches}\n\n"
        "If a match is extremely likely (e.g. same tax id, or very similar name), mark it as a duplicate."
    )
    
    try:
        decision = duplicate_llm.invoke(prompt)
        
        if isinstance(decision, list):
            decision = decision[0]
            
        if isinstance(decision, BaseModel):
            decision_dict = decision.model_dump()
        elif isinstance(decision, dict):
            decision_dict = decision
        else:
            decision_dict = getattr(decision, "dict", lambda: {})()
            
        print(f"Duplicate Decision: {decision_dict}")
        
        is_dup = decision_dict.get("is_duplicate", False)
        status = "DUPLICATE_FOUND" if is_dup else "NO_DUPLICATES"
        
        return {
            "duplicate_status": status,
            "messages": [SystemMessage(content=f"Duplicate Check Complete. Decision: {status}. Reasoning: {decision_dict.get('reasoning')}")]
        }
        
    except Exception as e:
        print(f"Error in Duplicate Detection: {e}")
        return {"duplicate_status": "ERROR"}


def risk_agent_stub(state: AgentState) -> dict:
    print("--- RISK AGENT ---")
    return {
        "messages": [SystemMessage(content="Risk check completed. Level: LOW.")],
        "risk_level": "LOW"
    }

# Build Graph
builder = StateGraph(AgentState)

builder.add_node("supervisor", supervisor_node)
builder.add_node("document_extraction_agent", document_extraction_node)
builder.add_node("duplicate_detection_agent", duplicate_detection_node)
builder.add_node("risk_agent", risk_agent_stub)

# The supervisor determines the next step
builder.set_entry_point("supervisor")

# Define conditional edges from supervisor
builder.add_conditional_edges(
    "supervisor",
    lambda state: state["next_node"],
    {
        "document_extraction_agent": "document_extraction_agent",
        "duplicate_detection_agent": "duplicate_detection_agent",
        "risk_agent": "risk_agent",
        "END": END
    }
)

# Agents always route back to supervisor to decide what's next
builder.add_edge("document_extraction_agent", "supervisor")
builder.add_edge("duplicate_detection_agent", "supervisor")
builder.add_edge("risk_agent", "supervisor")

graph = builder.compile()

if __name__ == "__main__":
    print("Initializing Vendor-to-Pay Graph Test...")
    initial_state = {
        "case_id": "test-case-123",
        "tenant_id": "tenant-abc",
        "case_type": "VENDOR_ONBOARDING",
        "messages": [HumanMessage(content="A new vendor just submitted a W-9 form and bank details. Please process.")],
        "current_vendor": None,
        "duplicate_status": None,
        "risk_level": None
    }
    
    # Run the graph
    for step in graph.stream(initial_state):
        print(f"Step executed: {list(step.keys())[0]}")
