"""
Example usage of the MinerU Web API with Chrome
"""
import asyncio
from mineru_web_api import MinerUWebAPI

async def main():
    # Initialize the API client
    api = MinerUWebAPI(download_path="./downloads")
    
    # Example 1: Process a PDF from URL
    pdf_url = "https://smologfkmyahtgbzhkqu.supabase.co/storage/v1/object/public/fdds//480234_New%20York_Initial_10-15-2024.pdf"
    
    try:
        # Authenticate - will use your existing Chrome session
        print("Authenticating with Chrome...")
        await api.authenticate_with_browser(use_saved_auth=True)
        
        # Process the PDF
        print(f"Processing PDF: {pdf_url}")
        results = await api.process_pdf(pdf_url)
        
        print("✅ Success! Downloaded files:")
        print(f"  - Markdown: {results.get('markdown')}")
        print(f"  - JSON: {results.get('json')}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

    # Example 2: Process a local PDF file
    # local_pdf = "path/to/your/document.pdf"
    # results = await api.process_pdf(local_pdf)
    
    # Example 3: Process PDF from bytes
    # with open("document.pdf", "rb") as f:
    #     pdf_bytes = f.read()
    #     results = await api.process_pdf(pdf_bytes, filename="custom_name.pdf")

if __name__ == "__main__":
    # First run test_chrome.py to verify Chrome installation
    print("Make sure to run test_chrome.py first to verify Chrome installation!\n")
    
    asyncio.run(main())