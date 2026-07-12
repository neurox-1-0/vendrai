from typing import List, Dict, Any

def search_vendor_duplicates(vendor_name: str, tax_id: str = None) -> List[Dict[str, Any]]:
    """
    Mock function to simulate a pg_trgm fuzzy search against an ERP database.
    In production, this would execute an async SQLAlchemy query against the `vendors` table.
    """
    # Mock ERP Database
    mock_db = [
        {
            "erp_vendor_id": "ERP-1001",
            "vendor_name": "Vendrai Tech",
            "tax_id": "98-7654321",
            "status": "ACTIVE"
        },
        {
            "erp_vendor_id": "ERP-1002",
            "vendor_name": "TechCorp Global",
            "tax_id": "11-2233445",
            "status": "INACTIVE"
        },
        {
            "erp_vendor_id": "ERP-1003",
            "vendor_name": "Vendrai Supplies",
            "tax_id": "99-1122334",
            "status": "ACTIVE"
        }
    ]
    
    results = []
    normalized_query = vendor_name.lower().replace("llc", "").replace("inc", "").strip()
    
    for record in mock_db:
        normalized_record_name = record["vendor_name"].lower()
        
        # Simple simulated fuzzy match
        if normalized_query in normalized_record_name or normalized_record_name in normalized_query:
            # Simulate a pg_trgm similarity score
            score = 0.85 
            if record["tax_id"] == tax_id and tax_id is not None:
                score = 0.99
                
            results.append({
                "record": record,
                "similarity_score": score
            })
            
    # Sort by highest score first
    results.sort(key=lambda x: x["similarity_score"], reverse=True)
    return results
