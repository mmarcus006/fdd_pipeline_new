import json
from prefect import flow, task
from src.processing.section_identifier import FDDSectionIdentifier


@task
def load_json_data(file_path: str) -> dict:
    """Loads JSON data from a file."""
    with open(file_path, "r") as f:
        return json.load(f)


@task
def identify_fdd_sections_task(pdf_info: dict) -> list:
    """Identifies FDD sections from the parsed PDF data."""
    identifier = FDDSectionIdentifier()
    section_map = identifier.identify_sections(pdf_info)
    return section_map


@flow
def identify_fdd_sections_flow(file_path: str):
    """A Prefect flow to identify FDD sections from a JSON file."""
    pdf_info = load_json_data(file_path)
    section_map = identify_fdd_sections_task(pdf_info)
    print(section_map)


if __name__ == "__main__":
    # Example usage:
    file_path = "C:\\Users\\Miller\\projects\\fdd_pipeline_new\\examples\\2025_VALVOLINE INSTANT OIL CHANGE FRANCHISING, INC_32722-202412-04.pdf-42b85dc3-4422-4724-abf7-344b6d910da3\\layout.json"
    identify_fdd_sections_flow(file_path)
