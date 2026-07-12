import os
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

from app.config import settings
from app.state import AgentState

# Setup Gemini Model
if not settings.GEMINI_API_KEY:
    # Dummy mock model if no API key is provided
    # In a real environment, you must provide GEMINI_API_KEY in .env
    pass

class Route(BaseModel):
    next_node: str = Field(description="The next agent to route to: 'document_extraction_agent', 'risk_agent', or 'END'")
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
        "Your job is to read the case context and route to the correct specialist agent.\n"
        "- If documents need to be read, route to 'document_extraction_agent'.\n"
        "- If vendor data exists but risk hasn't been checked, route to 'risk_agent'.\n"
        "- If all tasks are done, route to 'END'."
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

def document_extraction_stub(state: AgentState) -> dict:
    print("--- DOCUMENT EXTRACTION AGENT ---")
    return {
        "messages": [SystemMessage(content="Extracted data from documents successfully.")],
        "current_vendor": {"name": "Extracted Vendor Inc.", "tax_id": "12345"}
    }

def risk_agent_stub(state: AgentState) -> dict:
    print("--- RISK AGENT ---")
    return {
        "messages": [SystemMessage(content="Risk check completed. Level: LOW.")],
        "risk_level": "LOW"
    }

# Build Graph
builder = StateGraph(AgentState)

builder.add_node("supervisor", supervisor_node)
builder.add_node("document_extraction_agent", document_extraction_stub)
builder.add_node("risk_agent", risk_agent_stub)

# The supervisor determines the next step
builder.set_entry_point("supervisor")

# Define conditional edges from supervisor
builder.add_conditional_edges(
    "supervisor",
    lambda state: state["next_node"],
    {
        "document_extraction_agent": "document_extraction_agent",
        "risk_agent": "risk_agent",
        "END": END
    }
)

# Agents always route back to supervisor to decide what's next
builder.add_edge("document_extraction_agent", "supervisor")
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
        "risk_level": None
    }
    
    # Run the graph
    for step in graph.stream(initial_state):
        print(f"Step executed: {list(step.keys())[0]}")
