"""Utility for extracting text from PDF files."""

import PyPDF2
from pathlib import Path
from typing import Union

def extract_text_from_pdf(pdf_path: Union[str, Path]) -> str:
    """
    Extracts text from all pages of a PDF file.

    Args:
        pdf_path: The path to the PDF file.

    Returns:
        The extracted text as a single string.
    """
    text = ""
    try:
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"Error extracting text from {pdf_path}: {e}")
    return text 