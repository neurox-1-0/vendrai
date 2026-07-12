from typing import TypedDict, Annotated, Sequence, Optional, Dict, Any
from langchain_core.messages import BaseMessage
import operator

class AgentState(TypedDict):
    # Core case context
    case_id: str
    tenant_id: str
    case_type: str
    
    # LangGraph message history
    messages: Annotated[Sequence[BaseMessage], operator.add]
    
    # Shared global state context for the agents
    current_vendor: Optional[Dict[str, Any]]
    risk_level: Optional[str]
    missing_information: Optional[list[str]]
    approval_status: Optional[str]
    
    # Next node routing
    next_node: str
