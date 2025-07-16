"""
Script to run the FDD Pipeline Internal API.

Usage:
    python -m src.api.run [--reload] [--port 8000] [--host 0.0.0.0]
"""

import uvicorn
import click


@click.command()
@click.option('--reload', is_flag=True, help='Enable auto-reload for development')
@click.option('--port', default=8000, help='Port to run the API on')
@click.option('--host', default='0.0.0.0', help='Host to bind the API to')
@click.option('--workers', default=1, help='Number of worker processes')
def main(reload: bool, port: int, host: str, workers: int):
    """Run the FDD Pipeline Internal API."""
    
    if reload:
        # Development mode with auto-reload
        uvicorn.run(
            "src.api.main:app",
            host=host,
            port=port,
            reload=True,
            log_level="info"
        )
    else:
        # Production mode
        uvicorn.run(
            "src.api.main:app",
            host=host,
            port=port,
            workers=workers,
            log_level="info"
        )


if __name__ == "__main__":
    main()