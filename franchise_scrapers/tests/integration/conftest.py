# franchise_scrapers/tests/integration/conftest.py
"""Shared fixtures for integration tests."""

import pytest
import asyncio
import csv
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, AsyncGenerator
from unittest.mock import MagicMock, AsyncMock, patch
from playwright.async_api import Page, Browser, BrowserContext

from franchise_scrapers.models import CleanFDDRow, WIActiveRow, WIRegisteredRow, WIDetailsRow


@pytest.fixture
def temp_dir(tmp_path):
    """Create temporary directory for test outputs."""
    test_dir = tmp_path / "test_output"
    test_dir.mkdir(exist_ok=True)
    return test_dir


@pytest.fixture
def sample_mn_table_data():
    """Sample Minnesota table data for testing."""
    return [
        {
            'legal_name': 'Test Franchise Inc.',
            'pdf_url': 'https://www.cards.commerce.state.mn.us/CARDS/security/search.do?method=showDocument&documentId=123456&documentTitle=Test%20FDD',
            'document_id': '123456',
            'scraped_at': datetime.utcnow()
        },
        {
            'legal_name': 'Another Franchise LLC',
            'pdf_url': 'https://www.cards.commerce.state.mn.us/CARDS/security/search.do?method=showDocument&documentId=789012&documentTitle=Another%20FDD',
            'document_id': '789012',
            'scraped_at': datetime.utcnow()
        }
    ]


@pytest.fixture
def sample_wi_active_data():
    """Sample Wisconsin active filings data."""
    return [
        WIActiveRow(legal_name="Wisconsin Franchise A", filing_number="12345"),
        WIActiveRow(legal_name="Wisconsin Franchise B", filing_number="67890"),
        WIActiveRow(legal_name="Wisconsin Franchise C", filing_number="11111")
    ]


@pytest.fixture
def sample_wi_registered_data():
    """Sample Wisconsin registered franchises data."""
    return [
        WIRegisteredRow(
            filing_number="12345",
            legal_name="Wisconsin Franchise A",
            details_url="https://apps.dfi.wi.gov/apps/FranchiseEFiling/Details.aspx?id=12345"
        ),
        WIRegisteredRow(
            filing_number="67890",
            legal_name="Wisconsin Franchise B",
            details_url="https://apps.dfi.wi.gov/apps/FranchiseEFiling/Details.aspx?id=67890"
        )
    ]


@pytest.fixture
def sample_wi_details_data():
    """Sample Wisconsin details page data."""
    return [
        WIDetailsRow(
            filing_number="12345",
            status="Registered",
            legal_name="Wisconsin Franchise A",
            trade_name="WF-A",
            contact_email="contact@wfa.com",
            pdf_path="wi_fdds/12345_Wisconsin_Franchise_A.pdf",
            pdf_status="ok",
            scraped_at=datetime.utcnow()
        ),
        WIDetailsRow(
            filing_number="67890",
            status="Registered",
            legal_name="Wisconsin Franchise B",
            trade_name=None,
            contact_email="info@wfb.com",
            pdf_path="wi_fdds/67890_Wisconsin_Franchise_B.pdf",
            pdf_status="ok",
            scraped_at=datetime.utcnow()
        )
    ]


@pytest.fixture
async def mock_browser():
    """Create a mock browser for testing."""
    browser = AsyncMock(spec=Browser)
    context = AsyncMock(spec=BrowserContext)
    page = AsyncMock(spec=Page)
    
    # Set up browser -> context -> page chain
    browser.new_context.return_value = context
    context.new_page.return_value = page
    
    # Common page methods
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.query_selector = AsyncMock()
    page.query_selector_all = AsyncMock()
    page.evaluate = AsyncMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.wait_for_download = AsyncMock()
    page.close = AsyncMock()
    
    context.close = AsyncMock()
    browser.close = AsyncMock()
    
    return browser, context, page


@pytest.fixture
def mock_csv_writer(temp_dir):
    """Create a mock CSV writer that actually writes to temp files."""
    def _make_writer(filename: str, fieldnames: List[str]):
        filepath = temp_dir / filename
        file_handle = open(filepath, 'w', newline='', encoding='utf-8')
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        return writer, file_handle, filepath
    
    return _make_writer


@pytest.fixture
def mock_download():
    """Create a mock download object."""
    download = AsyncMock()
    download.path = AsyncMock(return_value="/tmp/test_download.pdf")
    download.save_as = AsyncMock()
    download.failure = AsyncMock(return_value=None)
    return download


@pytest.fixture
def cleanup_downloads(temp_dir):
    """Cleanup downloaded files after test."""
    yield
    # Cleanup any PDFs downloaded during tests
    for pdf in temp_dir.glob("**/*.pdf"):
        pdf.unlink(missing_ok=True)


@pytest.fixture
def mock_html_responses():
    """Mock HTML responses for different portal pages."""
    return {
        'mn_search_page': '''
            <html>
                <body>
                    <div id="results">
                        <table>
                            <tbody>
                                <tr>
                                    <td>Test Franchise Inc.</td>
                                    <td><a href="/CARDS/security/search.do?method=showDocument&documentId=123456">View</a></td>
                                </tr>
                                <tr>
                                    <td>Another Franchise LLC</td>
                                    <td><a href="/CARDS/security/search.do?method=showDocument&documentId=789012">View</a></td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                    <a class="pagination" href="?page=2">Next</a>
                </body>
            </html>
        ''',
        'wi_active_page': '''
            <html>
                <body>
                    <table id="ctl00_contentPlaceholder_grdActiveFilings">
                        <tbody>
                            <tr>
                                <td>Wisconsin Franchise A</td>
                                <td>12345</td>
                            </tr>
                            <tr>
                                <td>Wisconsin Franchise B</td>
                                <td>67890</td>
                            </tr>
                        </tbody>
                    </table>
                </body>
            </html>
        ''',
        'wi_search_results': '''
            <html>
                <body>
                    <table id="ctl00_contentPlaceholder_grdSearchResults">
                        <tbody>
                            <tr>
                                <td>12345</td>
                                <td>Wisconsin Franchise A</td>
                                <td>Registered</td>
                                <td><a href="Details.aspx?id=12345">Details</a></td>
                            </tr>
                        </tbody>
                    </table>
                </body>
            </html>
        ''',
        'wi_details_page': '''
            <html>
                <body>
                    <span id="ctl00_contentPlaceholder_lblFilingNumber">12345</span>
                    <span id="ctl00_contentPlaceholder_lblStatus">Registered</span>
                    <span id="ctl00_contentPlaceholder_lblLegalName">Wisconsin Franchise A</span>
                    <span id="ctl00_contentPlaceholder_lblTradeName">WF-A</span>
                    <span id="ctl00_contentPlaceholder_lblEmail">contact@wfa.com</span>
                    <a id="ctl00_contentPlaceholder_hyperlinkDisclosureDocument" href="GetDocument.aspx?id=12345">Download FDD</a>
                </body>
            </html>
        '''
    }


@pytest.fixture
def assert_csv_contents():
    """Helper to assert CSV file contents."""
    def _assert(filepath: Path, expected_rows: int, required_fields: List[str]):
        assert filepath.exists(), f"CSV file {filepath} does not exist"
        
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
        assert len(rows) == expected_rows, f"Expected {expected_rows} rows, got {len(rows)}"
        
        if rows:
            for field in required_fields:
                assert field in rows[0], f"Required field '{field}' not found in CSV"
        
        return rows
    
    return _assert


# Markers for test categories
pytest.mark.live = pytest.mark.skipif(
    "not config.getoption('--live')",
    reason="Live tests require --live flag"
)

pytest.mark.mock = pytest.mark.skipif(
    "config.getoption('--live')",
    reason="Mock tests skipped when --live flag is used"
)


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Run live integration tests against actual portals"
    )