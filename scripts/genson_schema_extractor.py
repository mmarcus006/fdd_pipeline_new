import json
import sys
from pathlib import Path
from genson import SchemaBuilder


def generate_schema_with_genson(input_path, output_path):
    """
    Generates a JSON schema from a file using the genson library.

    Args:
        input_path (Path): The path to the input JSON file.
        output_path (Path): The path where the generated schema will be saved.
    """
    try:
        print(f"Reading input file: '{input_path}'...")
        with open(input_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)

        # Create a SchemaBuilder instance
        builder = SchemaBuilder()

        # Add the JSON object to the builder. It will analyze the structure.
        builder.add_object(json_data)

        # Generate the final schema
        generated_schema = builder.to_schema()

        print(f"Writing generated schema to: '{output_path}'...")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(generated_schema, f, indent=2)

        print("Schema generation successful!")

    except FileNotFoundError:
        print(f"Error: Input file not found at '{input_path}'")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: The file at '{input_path}' is not a valid JSON file.")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)


def main():
    """
    Main function to handle command-line arguments.
    """

    input_file = Path(
        r"C:\Users\Miller\projects\fdd_pipeline_new\examples\2025_VALVOLINE INSTANT OIL CHANGE FRANCHISING, INC_32722-202412-04.pdf-42b85dc3-4422-4724-abf7-344b6d910da3\layout.json"
    )

    # Create a name for the output file
    output_file = input_file.parent / f"{input_file.stem}_schema.json"

    generate_schema_with_genson(input_file, output_file)


if __name__ == "__main__":
    main()
