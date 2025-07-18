"""Document fixtures for testing."""

from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from uuid import uuid4

from tasks.web_scraping import DocumentMetadata
from models.scrape_metadata import ScrapeMetadata
from models.fdd import FDD
from models.franchisor import Franchisor


class DocumentFixtures:
    """Common document fixtures for testing."""

    @staticmethod
    def create_sample_pdf_content() -> bytes:
        """Create sample PDF content for testing."""
        return b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Arial >> >> >> /MediaBox [0 0 612 792] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT /F1 12 Tf 100 700 Td (Sample FDD Document) Tj ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000315 00000 n
trailer
<< /Size 5 /Root 1 0 R >>
startxref
405
%%EOF"""

    @staticmethod
    def create_document_metadata(
        franchise_name: str = "Test Franchise", state_code: str = "MN", **kwargs
    ) -> DocumentMetadata:
        """Create a document metadata fixture."""
        return DocumentMetadata(
            franchise_name=franchise_name,
            filing_date=kwargs.get("filing_date", datetime.now().strftime("%Y-%m-%d")),
            document_type=kwargs.get("document_type", "FDD"),
            filing_number=kwargs.get(
                "filing_number", f"{state_code}-{datetime.now().year}-001"
            ),
            source_url=kwargs.get(
                "source_url", f"https://test.{state_code.lower()}.gov/doc/test"
            ),
            download_url=kwargs.get(
                "download_url",
                f"https://test.{state_code.lower()}.gov/download/test.pdf",
            ),
            file_size=kwargs.get("file_size", 1024000),
            additional_metadata={
                "source": state_code,
                "year": str(datetime.now().year),
                **kwargs.get("additional_metadata", {}),
            },
        )

    @staticmethod
    def create_franchisor(
        name: str = "Test Franchisor Corp", state: str = "MN", **kwargs
    ) -> Franchisor:
        """Create a franchisor fixture."""
        return Franchisor(
            id=kwargs.get("id", uuid4()),
            legal_name=name,
            dba_names=kwargs.get("dba_names", [f"{name} DBA"]),
            headquarters_state=state,
            headquarters_address=kwargs.get(
                "headquarters_address",
                {
                    "street": "123 Test St",
                    "city": "Test City",
                    "state": state,
                    "zip": "12345",
                },
            ),
            contact_info=kwargs.get(
                "contact_info",
                {
                    "phone": "555-0123",
                    "email": f"contact@{name.lower().replace(' ', '')}.com",
                },
            ),
            created_at=kwargs.get("created_at", datetime.utcnow()),
            updated_at=kwargs.get("updated_at", datetime.utcnow()),
        )

    @staticmethod
    def create_fdd(
        franchisor_id: str = None, filing_state: str = "MN", **kwargs
    ) -> FDD:
        """Create an FDD fixture."""
        return FDD(
            id=kwargs.get("id", uuid4()),
            franchisor_id=franchisor_id or uuid4(),
            filing_state=filing_state,
            filing_year=kwargs.get("filing_year", datetime.now().year),
            filing_date=kwargs.get("filing_date", datetime.now().date()),
            filing_number=kwargs.get(
                "filing_number", f"{filing_state}-{datetime.now().year}-001"
            ),
            document_type=kwargs.get("document_type", "FDD"),
            original_filename=kwargs.get("original_filename", "test_fdd.pdf"),
            drive_file_id=kwargs.get("drive_file_id", f"drive-file-{uuid4()}"),
            document_hash=kwargs.get("document_hash", "a" * 64),
            processing_status=kwargs.get("processing_status", "pending"),
            metadata=kwargs.get(
                "metadata", {"pages": 100, "file_size": 1024000, "source": filing_state}
            ),
            created_at=kwargs.get("created_at", datetime.utcnow()),
            updated_at=kwargs.get("updated_at", datetime.utcnow()),
        )

    @staticmethod
    def create_scrape_metadata(
        fdd_id: str = None, source_name: str = "MN", **kwargs
    ) -> ScrapeMetadata:
        """Create scrape metadata fixture."""
        return ScrapeMetadata(
            id=kwargs.get("id", uuid4()),
            fdd_id=fdd_id or uuid4(),
            source_name=source_name,
            source_url=kwargs.get(
                "source_url", f"https://test.{source_name.lower()}.gov/doc/test"
            ),
            filing_metadata=kwargs.get(
                "filing_metadata",
                {
                    "franchise_name": "Test Franchise",
                    "filing_date": datetime.now().strftime("%Y-%m-%d"),
                    "document_type": "FDD",
                    "filing_number": f"{source_name}-{datetime.now().year}-001",
                },
            ),
            prefect_run_id=kwargs.get("prefect_run_id", uuid4()),
            scraped_at=kwargs.get("scraped_at", datetime.utcnow()),
        )


class StateSpecificFixtures:
    """State-specific document fixtures."""

    @staticmethod
    def minnesota_documents(count: int = 2) -> List[DocumentMetadata]:
        """Create Minnesota-specific document fixtures."""
        docs = []
        for i in range(count):
            docs.append(
                DocumentFixtures.create_document_metadata(
                    franchise_name=f"Minnesota Franchise {i+1}",
                    state_code="MN",
                    filing_number=f"F-2024-{i+1:03d}",
                    additional_metadata={
                        "franchisor": f"MN Corp {i+1}",
                        "year": "2024",
                        "received_date": f"2024-{i+1:02d}-01",
                        "added_on": f"2024-{i+1:02d}-05",
                        "notes": "Clean FDD" if i == 0 else "",
                        "document_id": f"mn-doc-{i+1}",
                    },
                )
            )
        return docs

    @staticmethod
    def wisconsin_documents(count: int = 2) -> List[DocumentMetadata]:
        """Create Wisconsin-specific document fixtures."""
        docs = []
        for i in range(count):
            docs.append(
                DocumentFixtures.create_document_metadata(
                    franchise_name=f"Wisconsin Franchise {i+1}",
                    state_code="WI",
                    filing_number=f"WI-2024-{i+1:03d}",
                    additional_metadata={
                        "franchisor_info": {
                            "legal_name": f"WI Legal Corp {i+1}",
                            "trade_name": f"WI Trade Name {i+1}",
                            "business_address": f"{100+i} Wisconsin Ave, Madison, WI 53703",
                            "filing_status": "Registered",
                        },
                        "filing_info": {
                            "type": "Initial" if i == 0 else "Renewal",
                            "effective": f"2024-{i+1:02d}-01",
                        },
                        "states_filed": ["WI", "IL", "MN"] if i == 0 else ["WI"],
                    },
                )
            )
        return docs


class MockResponses:
    """Mock HTTP responses for testing."""

    @staticmethod
    def minnesota_search_page() -> str:
        """Mock Minnesota CARDS search results page."""
        return """
        <html>
        <body>
            <div id="results">
                <table>
                    <tr>
                        <th>#</th><th>Document</th><th>Franchisor</th><th>Franchise names</th>
                        <th>Document types</th><th>Year</th><th>File number</th><th>Notes</th><th>Received date</th>
                    </tr>
                    <tr>
                        <th>1</th>
                        <td><a href="/download?documentId=%7B123-456%7D">Test FDD 2024.pdf</a></td>
                        <td>Test Franchisor Corp</td>
                        <td>Test Franchise</td>
                        <td>Clean FDD</td>
                        <td>2024</td>
                        <td>F-2024-001</td>
                        <td>Initial filing</td>
                        <td>01/15/2024</td>
                    </tr>
                </table>
                <button id="load-more">Load more</button>
            </div>
        </body>
        </html>
        """

    @staticmethod
    def wisconsin_active_filings_page() -> str:
        """Mock Wisconsin active filings page."""
        return """
        <html>
        <body>
            <table id="ctl00_contentPlaceholder_grdActiveFilings">
                <tr>
                    <th>Franchise Name</th><th>Filing Number</th><th>Status</th>
                </tr>
                <tr>
                    <td>Test Wisconsin Franchise</td>
                    <td>WI-2024-001</td>
                    <td>Registered</td>
                </tr>
            </table>
        </body>
        </html>
        """

    @staticmethod
    def wisconsin_detail_page() -> str:
        """Mock Wisconsin franchise detail page."""
        return """
        <html>
        <body>
            <div>
                <h2>Franchisor Name and Address</h2>
                <p>Filing Number: WI-2024-001</p>
                <p>Filing Status: Registered</p>
                <p>Legal Name: Test Legal Corp</p>
                <p>Trade Name (DBA): Test Trade Name</p>
                <p>Business Address: 123 Wisconsin Ave, Madison, WI 53703</p>
                
                <h2>Filings for this Registration</h2>
                <table>
                    <tr><td>Type: Initial</td><td>Effective: 01/20/2024</td></tr>
                </table>
                
                <h2>States Application Filed</h2>
                <p>States Filed: WI, IL, MN</p>
                
                <button>Download</button>
            </div>
        </body>
        </html>
        """


class ProcessingFixtures:
    """Fixtures for document processing tests."""

    @staticmethod
    def sample_extracted_sections() -> Dict[str, Any]:
        """Sample extracted FDD sections."""
        return {
            "cover_page": {
                "franchisor_name": "Test Franchisor Corp",
                "franchise_name": "Test Franchise",
                "effective_date": "2024-01-15",
                "state": "Minnesota",
            },
            "item_1": {
                "franchisor_legal_name": "Test Franchisor Corporation",
                "dba_names": ["Test Franchise", "Test Brand"],
                "principal_address": "123 Test Street, Minneapolis, MN 55401",
                "formation_state": "Delaware",
                "formation_date": "2010-01-01",
            },
            "item_5": {
                "initial_franchise_fee": {
                    "amount": 45000,
                    "payment_terms": "Due upon signing",
                },
                "additional_fees": [
                    {"name": "Technology Fee", "amount": 299, "frequency": "monthly"}
                ],
            },
            "item_7": {
                "total_investment_range": {"low": 150000, "high": 350000},
                "investment_items": [
                    {"item": "Initial Franchise Fee", "low": 45000, "high": 45000},
                    {"item": "Equipment", "low": 50000, "high": 100000},
                ],
            },
        }

    @staticmethod
    def sample_validation_results() -> Dict[str, Any]:
        """Sample validation results."""
        return {
            "is_valid": True,
            "errors": [],
            "warnings": [
                {
                    "field": "item_5.technology_fee",
                    "message": "Technology fee seems high compared to industry average",
                }
            ],
            "metrics": {
                "completeness_score": 0.95,
                "fields_validated": 50,
                "fields_with_errors": 0,
                "fields_with_warnings": 1,
            },
        }


# Export all fixture classes
__all__ = [
    "DocumentFixtures",
    "StateSpecificFixtures",
    "MockResponses",
    "ProcessingFixtures",
]
