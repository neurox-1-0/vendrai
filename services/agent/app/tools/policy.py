from typing import List

def search_procurement_policies(vendor_name: str, risk_level: str) -> List[str]:
    """
    Mock function to simulate a semantic vector search against a Qdrant database containing
    corporate procurement policies. 
    In a real environment, the risk_level and vendor attributes would be converted to embeddings 
    and used to retrieve chunks of PDF policy documents.
    """
    retrieved_policies = []
    
    # Generic policies that always apply
    retrieved_policies.append(
        "PROC-101: All new vendors must provide a valid W-9 and verified bank details before approval."
    )
    
    # Conditional policies based on risk level
    if risk_level == "HIGH":
        retrieved_policies.append(
            "PROC-405 (High Risk): Any vendor flagged as HIGH risk by the OFAC/Sanctions checker "
            "requires explicit sign-off from the Chief Financial Officer (CFO) and Chief Compliance Officer (CCO)."
        )
        retrieved_policies.append(
            "PROC-406: High-risk vendors are not eligible for automated fast-track payments."
        )
    elif risk_level == "MEDIUM":
        retrieved_policies.append(
            "PROC-302 (Medium Risk): Vendors with MEDIUM risk indicators require a Level 2 Procurement Manager approval."
        )
    else:
        retrieved_policies.append(
            "PROC-201 (Standard): LOW risk vendors with standard documentation can be approved by a Level 1 Associate or automatically if all data matches."
        )
        
    return retrieved_policies
