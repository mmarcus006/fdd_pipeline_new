"""Shared test fixtures for franchise_scrapers unit tests."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock


@pytest.fixture
def sample_mn_table_html():
    """Sample HTML for Minnesota CARDS table."""
    return """
    <table>
        <tr>
            <th>#</th>
            <th>Document</th>
            <th>Franchisor</th>
            <th>Franchise names</th>
            <th>Document types</th>
            <th>Year</th>
            <th>File number</th>
            <th>Notes</th>
            <th>Received date</th>
        </tr>
        <tr>
            <td>1</td>
            <td><a href="https://cards.commerce.state.mn.us/download?documentId=%7B550e8400-e29b-41d4-a716-446655440000%7D">2024 FDD</a></td>
            <td>Test Franchise LLC</td>
            <td>Test Brand</td>
            <td>Clean FDD</td>
            <td>2024</td>
            <td>FN-12345</td>
            <td>Initial filing</td>
            <td>01/15/2024</td>
        </tr>
        <tr>
            <td>2</td>
            <td><a href="https://cards.commerce.state.mn.us/download?documentId=%7B660e8400-e29b-41d4-a716-446655440001%7D">2024 Amendment</a></td>
            <td>Another Franchise Inc</td>
            <td>Another Brand</td>
            <td>Amendment</td>
            <td>2024</td>
            <td>FN-67890</td>
            <td>Amendment to Item 7</td>
            <td>02/01/2024</td>
        </tr>
    </table>
    """


@pytest.fixture
def sample_wi_details_html():
    """Sample HTML for Wisconsin details page."""
    return """
    <html>
        <head><title>Test Franchise LLC Details</title></head>
        <body>
            <div class="details-container">
                <div class="field">
                    <label>Filing Number:</label>
                    <span class="value generic">12345</span>
                </div>
                <div class="field">
                    <label>Filing Status:</label>
                    <span class="value generic">Registered</span>
                </div>
                <div class="field">
                    <label>Franchise Legal Name:</label>
                    <span class="value generic">"Test Franchise LLC"</span>
                </div>
                <div class="field">
                    <label>Franchise Trade Name (DBA):</label>
                    <span class="value generic">"Test Brand"</span>
                </div>
                <div class="field">
                    <label>Franchise Business Address:</label>
                    <span class="value generic">"123 Main St, Madison, WI 53703"</span>
                </div>
                <div class="field">
                    <label>Email:</label>
                    <span class="value generic">"info@testfranchise.com"</span>
                </div>
                <div class="field">
                    <label>Effective Date:</label>
                    <span class="value cell">"01/15/2024"</span>
                </div>
                <div class="field">
                    <label>Type:</label>
                    <span class="value cell">"Initial"</span>
                </div>
                <div class="field">
                    <label>States Application Filed:</label>
                    <div class="states-list">
                        <span class="state text">"WI"</span>
                        <span class="state text">"IL"</span>
                        <span class="state text">"MN"</span>
                    </div>
                </div>
                <button class="download-btn">Download PDF</button>
            </div>
        </body>
    </html>
    """


@pytest.fixture
def sample_wi_active_csv_content():
    """Sample CSV content for Wisconsin active filings."""
    return """legal_name,filing_number
"Test Franchise LLC","12345"
"Another Franchise Inc","67890"
"Third Franchise Corp","11111"
"""


@pytest.fixture
def sample_wi_registered_csv_content():
    """Sample CSV content for Wisconsin registered filings."""
    return """filing_number,legal_name,details_url
"12345","Test Franchise LLC","https://apps.dfi.wi.gov/apps/FranchiseSearch/Details.aspx?id=12345"
"67890","Another Franchise Inc","https://apps.dfi.wi.gov/apps/FranchiseSearch/Details.aspx?id=67890"
"""


@pytest.fixture
def mock_playwright_page():
    """Create a mock Playwright page object."""
    page = AsyncMock()
    page.goto = AsyncMock()
    page.content = AsyncMock()
    page.query_selector = AsyncMock()
    page.query_selector_all = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.press = AsyncMock()
    page.wait_for_navigation = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.title = AsyncMock(return_value="Test Page")
    page.url = "https://example.com"
    page.expect_download = AsyncMock()
    page.screenshot = AsyncMock()
    page.evaluate = AsyncMock()
    return page


@pytest.fixture
def mock_playwright_browser():
    """Create a mock Playwright browser object."""
    browser = AsyncMock()
    browser.new_context = AsyncMock()
    browser.close = AsyncMock()
    browser.is_connected = AsyncMock(return_value=True)
    return browser


@pytest.fixture
def mock_playwright_context():
    """Create a mock Playwright browser context."""
    context = AsyncMock()
    context.new_page = AsyncMock()
    context.close = AsyncMock()
    context.set_default_timeout = AsyncMock()
    context.set_default_navigation_timeout = AsyncMock()
    context.add_cookies = AsyncMock()
    context.clear_cookies = AsyncMock()
    return context


@pytest.fixture
def sample_fdd_metadata():
    """Sample FDD metadata for testing."""
    return {
        'document_id': '550e8400-e29b-41d4-a716-446655440000',
        'legal_name': 'Test Franchise LLC',
        'pdf_url': 'https://example.com/download?documentId=%7B550e8400-e29b-41d4-a716-446655440000%7D',
        'franchisor': 'Test Franchise LLC',
        'franchise_names': 'Test Brand',
        'document_types': 'Clean FDD',
        'year': '2024',
        'file_number': 'FN-12345',
        'notes': 'Initial filing',
        'received_date': '01/15/2024',
        'scraped_at': datetime(2024, 1, 20, 10, 30, 0)
    }


@pytest.fixture
def sample_wi_details_metadata():
    """Sample Wisconsin details metadata for testing."""
    return {
        'filing_number': '12345',
        'status': 'Registered',
        'legal_name': 'Test Franchise LLC',
        'trade_name': 'Test Brand',
        'business_address': '123 Main St, Madison, WI 53703',
        'contact_email': 'info@testfranchise.com',
        'effective_date': '01/15/2024',
        'filing_type': 'Initial',
        'states_filed': ['WI', 'IL', 'MN']
    }


@pytest.fixture
def temp_download_dir(tmp_path):
    """Create a temporary download directory."""
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    return download_dir


class MockElementHandle:
    """Mock ElementHandle for Playwright testing."""
    
    def __init__(self, inner_text="", attributes=None):
        self.inner_text_value = inner_text
        self.attributes = attributes or {}
        self.inner_text = AsyncMock(return_value=self.inner_text_value)
        self.get_attribute = AsyncMock(side_effect=self._get_attribute)
        self.query_selector = AsyncMock(return_value=None)
        self.query_selector_all = AsyncMock(return_value=[])
        self.click = AsyncMock()
        self.fill = AsyncMock()
        self.press = AsyncMock()
        self.is_visible = AsyncMock(return_value=True)
        self.is_enabled = AsyncMock(return_value=True)
    
    async def _get_attribute(self, name):
        return self.attributes.get(name)


@pytest.fixture
def create_mock_element():
    """Factory fixture for creating mock elements."""
    def _create(inner_text="", attributes=None):
        return MockElementHandle(inner_text, attributes)
    return _create