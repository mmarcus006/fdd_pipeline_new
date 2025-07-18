"""State-specific configurations for the scraping flows."""

from tasks.minnesota_scraper import MinnesotaScraper
from tasks.wisconsin_scraper import WisconsinScraper
from flows.base_state_flow import StateConfig


# Minnesota configuration
MINNESOTA_CONFIG = StateConfig(
    state_code="MN",
    state_name="Minnesota",
    scraper_class=MinnesotaScraper,
    folder_name="Minnesota FDDs",
    portal_name="CARDS"
)

# Wisconsin configuration
WISCONSIN_CONFIG = StateConfig(
    state_code="WI",
    state_name="Wisconsin",
    scraper_class=WisconsinScraper,
    folder_name="Wisconsin FDDs",
    portal_name="DFI"
)

# All available state configurations
STATE_CONFIGS = {
    "minnesota": MINNESOTA_CONFIG,
    "mn": MINNESOTA_CONFIG,
    "wisconsin": WISCONSIN_CONFIG,
    "wi": WISCONSIN_CONFIG,
}


def get_state_config(state: str) -> StateConfig:
    """Get state configuration by name or code.
    
    Args:
        state: State name or code (case-insensitive)
        
    Returns:
        StateConfig for the requested state
        
    Raises:
        ValueError: If state is not found
    """
    state_lower = state.lower()
    if state_lower not in STATE_CONFIGS:
        available_states = ", ".join(STATE_CONFIGS.keys())
        raise ValueError(
            f"Unknown state: {state}. Available states: {available_states}"
        )
    return STATE_CONFIGS[state_lower]