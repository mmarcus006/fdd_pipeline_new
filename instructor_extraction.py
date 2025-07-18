import instructor
import google.generativeai as genai
from google.ai.generativelanguage_v1beta.types.file import File
import time

# Import Franchisor models
from models.franchisor import FranchisorCreate


# Initialize the client
client = instructor.from_gemini(
    client=genai.GenerativeModel(
        model_name="models/gemini-2.5-pro-latest",
    )
)


async def extract_franchisor_from_pdf(pdf_path: str) -> FranchisorCreate:
    """
    Extract franchisor information from a PDF using structured extraction.
    
    Args:
        pdf_path: Path to the PDF file to process
        
    Returns:
        FranchisorCreate with structured franchisor data
    """
    # Upload the PDF
    file = genai.upload_file(pdf_path)

    # Wait for file to finish processing
    while file.state != File.State.ACTIVE:
        time.sleep(1)
        file = genai.get_file(file.name)
        print(f"File is still uploading, state: {file.state}")

    print(f"File is now active, state: {file.state}")

    # Extract structured franchisor information
    resp = await client.chat.completions.create(
        messages=[
            {
                "role": "user", 
                "content": [
                    """Extract franchisor information from this FDD document. 
                    Focus on identifying:
                    - Company name (canonical name)
                    - Parent company if mentioned
                    - Website, phone, email contact information  
                    - Business address
                    - Any DBA (doing business as) names""",
                    file
                ]
            }
        ],
        response_model=FranchisorCreate,
    )

    return resp


def extract_franchisor_from_text(text_content: str) -> FranchisorCreate:
    """
    Extract franchisor information from text content.
    
    Args:
        text_content: Text content to analyze
        
    Returns:
        FranchisorCreate with structured franchisor data
    """
    # Alternative client initialization method
    alt_client = instructor.from_provider("google/gemini-2.5-pro")
    
    resp = alt_client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": f"""Extract franchisor information from this text:

{text_content}

Focus on identifying:
- Company name (canonical name)
- Parent company if mentioned  
- Website, phone, email contact information
- Business address
- Any DBA (doing business as) names"""
            }
        ],
        response_model=FranchisorCreate,
    )
    
    return resp


# Example usage
if __name__ == "__main__":
    # Example with PDF file
    # result = extract_franchisor_from_pdf("path/to/your/fdd.pdf")
    # print(f"Extracted Franchisor: {result.canonical_name}")
    
    # Example with text content
    sample_text = """
    VALVOLINE INSTANT OIL CHANGE FRANCHISING, INC.
    A Delaware Corporation
    
    Business Address:
    100 Valvoline Way
    Lexington, KY 40509
    Phone: (859) 357-7777
    Website: www.valvoline.com
    
    Parent Company: Valvoline Inc.
    """
    
    result = extract_franchisor_from_text(sample_text)
    print(f"Extracted Franchisor: {result.canonical_name}")
    print(f"Address: {result.address}")