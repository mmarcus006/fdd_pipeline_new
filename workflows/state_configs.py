"""State-specific configurations for the scraping flows."""

from typing import Dict, List
from scrapers.states.minnesota import MinnesotaScraper
from scrapers.states.wisconsin import WisconsinScraper
from workflows.base_state_flow import StateConfig
from utils.logging import PipelineLogger


# Minnesota configuration
MINNESOTA_CONFIG = StateConfig(
    state_code="MN",
    state_name="Minnesota",
    scraper_class=MinnesotaScraper,
    folder_name="Minnesota FDDs",
    portal_name="CARDS",
)

# Wisconsin configuration
WISCONSIN_CONFIG = StateConfig(
    state_code="WI",
    state_name="Wisconsin",
    scraper_class=WisconsinScraper,
    folder_name="Wisconsin FDDs",
    portal_name="DFI",
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
    logger = PipelineLogger("state_configs")
    state_lower = state.lower()
    
    logger.debug(
        "getting_state_config",
        requested_state=state,
        normalized_state=state_lower,
        available_states=list(STATE_CONFIGS.keys()),
    )
    
    if state_lower not in STATE_CONFIGS:
        available_states = ", ".join(STATE_CONFIGS.keys())
        logger.error(
            "state_config_not_found",
            requested_state=state,
            available_states=available_states,
        )
        raise ValueError(
            f"Unknown state: {state}. Available states: {available_states}"
        )
    
    config = STATE_CONFIGS[state_lower]
    logger.debug(
        "state_config_retrieved",
        state_code=config.state_code,
        state_name=config.state_name,
        portal_name=config.portal_name,
        scraper_class=config.scraper_class.__name__,
    )
    
    return config


def get_all_state_configs() -> Dict[str, StateConfig]:
    """Get all available state configurations.
    
    Returns:
        Dictionary of state code to StateConfig mappings
    """
    logger = PipelineLogger("state_configs")
    
    # Get unique configs (skip aliases)
    unique_configs = {}
    for key, config in STATE_CONFIGS.items():
        if key == config.state_code.lower():
            unique_configs[config.state_code] = config
    
    logger.debug(
        "all_state_configs_retrieved",
        state_count=len(unique_configs),
        state_codes=list(unique_configs.keys()),
    )
    
    return unique_configs


def list_supported_states() -> List[str]:
    """Get list of supported state codes.
    
    Returns:
        List of state codes
    """
    return list(get_all_state_configs().keys())


if __name__ == "__main__":
    """Demonstrate state configuration functionality."""
    
    from utils.logging import configure_logging
    
    # Configure logging for demo
    configure_logging()
    
    def demonstrate_configurations():
        """Show all state configurations."""
        print("\n" + "="*80)
        print("FDD Pipeline - State Configurations")
        print("="*80)
        print("\nAvailable State Configurations:")
        
        for state_code, config in get_all_state_configs().items():
            print(f"\n{config.state_name} ({state_code}):")
            print(f"  Portal Name: {config.portal_name}")
            print(f"  Scraper Class: {config.scraper_class.__name__}")
            print(f"  Google Drive Folder: {config.folder_name}")
            print(f"  State Code: {config.state_code}")
    
    def demonstrate_config_access():
        """Show how to access configurations."""
        print("\n" + "="*80)
        print("Accessing State Configurations")
        print("="*80)
        
        print("\nSupported access patterns:")
        print("  - By state code: get_state_config('WI')")
        print("  - By lowercase: get_state_config('wi')")
        print("  - By full name: get_state_config('wisconsin')")
        
        print("\nExample usage:")
        for test_state in ["WI", "wi", "wisconsin", "MN", "minnesota"]:
            try:
                config = get_state_config(test_state)
                print(f"  get_state_config('{test_state}') → {config.state_name}")
            except ValueError as e:
                print(f"  get_state_config('{test_state}') → Error: {e}")
    
    def demonstrate_adding_states():
        """Show how to add new state configurations."""
        print("\n" + "="*80)
        print("Adding New State Configurations")
        print("="*80)
        
        print("\nTo add a new state (e.g., California):")
        print("\n1. Create scraper class:")
        print("   # scrapers/states/california.py")
        print("   class CaliforniaScraper(BaseScraper):")
        print("       # Implementation...")
        
        print("\n2. Add configuration:")
        print("   # workflows/state_configs.py")
        print("   CALIFORNIA_CONFIG = StateConfig(")
        print('       state_code="CA",')
        print('       state_name="California",')
        print("       scraper_class=CaliforniaScraper,")
        print('       folder_name="California FDDs",')
        print('       portal_name="CA DBO"')
        print("   )")
        
        print("\n3. Update STATE_CONFIGS dictionary:")
        print('   "california": CALIFORNIA_CONFIG,')
        print('   "ca": CALIFORNIA_CONFIG,')
        
        print("\n4. The state is now available everywhere!")
        print("   - In CLI: python main.py scrape --state CA")
        print("   - In flows: get_state_config('CA')")
    
    def demonstrate_state_flow_integration():
        """Show how configs integrate with flows."""
        print("\n" + "="*80)
        print("State Flow Integration")
        print("="*80)
        
        print("\nThe base_state_flow uses configurations to:")
        print("  1. Select the appropriate scraper class")
        print("  2. Configure Google Drive folder paths")
        print("  3. Set portal-specific parameters")
        print("  4. Track metrics by state")
        
        print("\nExample flow usage:")
        print("  from workflows.state_configs import WISCONSIN_CONFIG")
        print("  from workflows.base_state_flow import scrape_state_flow")
        print("")
        print("  results = await scrape_state_flow(")
        print("      state_config=WISCONSIN_CONFIG,")
        print("      download_documents=True,")
        print("      max_documents=10")
        print("  )")
    
    # Run demonstrations
    demonstrate_configurations()
    demonstrate_config_access()
    demonstrate_adding_states()
    demonstrate_state_flow_integration()
    
    print("\n" + "="*80)
    print("State configurations loaded and ready!")
    print("="*80 + "\n")
