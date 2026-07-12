import requests
from typing import Optional
from app.config import settings

def extract_text_from_document(file_url: Optional[str] = None, file_path: Optional[str] = None) -> str:
    """
    Extracts text from a document using OCR.space Free API.
    If no file_url or file_path is provided, it returns a simulated W-9 form text 
    for testing the LLM extraction logic without hitting API limits.
    """
    if not file_url and not file_path:
        # Simulation Mode
        return """
        W-9 Request for Taxpayer Identification Number and Certification
        Name: Vendrai Technologies LLC
        Business name/disregarded entity name: Vendrai Tech
        Address: 123 Innovation Drive, Suite 400, San Francisco, CA 94105
        Taxpayer Identification Number (TIN): 98-7654321
        
        Bank Details:
        Bank Name: Silicon Valley Bank
        Account Number: 100200300400
        SWIFT Code: SVBKS33
        """
        
    api_key = settings.OCR_API_KEY
    if not api_key:
        raise ValueError("OCR_API_KEY is not configured in .env")

    # Call OCR.space API
    # OCR.space allows URL or base64 or file upload. 
    # For MVP, we will use URL or just simulated mode mostly.
    
    payload = {
        'apikey': api_key,
        'language': 'eng',
        'isOverlayRequired': False
    }
    
    if file_url:
        payload['url'] = file_url
        response = requests.post(settings.OCR_API_URL, data=payload)
    elif file_path:
        with open(file_path, 'rb') as f:
            response = requests.post(settings.OCR_API_URL, files={'file': f}, data=payload)
    
    if response.status_code == 200:
        result = response.json()
        if result.get("IsErroredOnProcessing"):
            return f"OCR Error: {result.get('ErrorMessage', 'Unknown error')}"
            
        parsed_text = ""
        for item in result.get("ParsedResults", []):
            parsed_text += item.get("ParsedText", "") + "\n"
        return parsed_text
    
    return f"Failed to call OCR API. Status Code: {response.status_code}"
