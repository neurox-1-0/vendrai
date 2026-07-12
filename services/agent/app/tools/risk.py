from typing import Dict, Any, List

def check_vendor_risk(vendor_name: str, address: str = None) -> Dict[str, Any]:
    """
    Mock function to simulate an API call to an OFAC/Sanctions and Country-Risk database.
    In production, this would call external compliance APIs.
    """
    risk_factors: List[str] = []
    
    normalized_name = vendor_name.lower()
    
    # Simulate a hit on a sanctions list
    if "sanction" in normalized_name or "scam" in normalized_name:
        risk_factors.append(f"Vendor name '{vendor_name}' triggered a direct match on the Global Sanctions Watchlist.")
        
    # Simulate country risk (if address is present)
    if address:
        normalized_address = address.lower()
        high_risk_regions = ["syria", "iran", "north korea", "cuba", "russia"]
        
        for region in high_risk_regions:
            if region in normalized_address:
                risk_factors.append(f"Address contains a high-risk sanctioned region: {region.upper()}.")
                
    # Simulate a medium risk (e.g. politically exposed person or weird banking)
    if "shell" in normalized_name:
        risk_factors.append("Vendor name indicates potential shell company structure.")
        
    return {
        "vendor_name": vendor_name,
        "address_checked": address,
        "identified_risk_factors": risk_factors,
        "raw_hit_count": len(risk_factors)
    }
