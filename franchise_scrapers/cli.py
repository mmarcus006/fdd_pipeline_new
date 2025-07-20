# franchise_scrapers/cli.py
import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from franchise_scrapers.mn.scraper import scrape_minnesota
from franchise_scrapers.wi.scraper import run_wisconsin_pipeline

app = typer.Typer(help="Franchise FDD Scrapers - Extract FDD documents from state portals")
console = Console()


@app.command("mn")
def minnesota(
    download: bool = typer.Option(False, "--download", help="Download PDF files"),
    max_pages: int = typer.Option(20, "--max-pages", help="Maximum number of pages to scrape"),
):
    """Scrape Minnesota CARDS portal for Clean FDD documents.
    
    Extracts franchise data from the Minnesota Department of Commerce CARDS portal
    and exports to mn_clean_fdd.csv. Optionally downloads PDF files.
    """
    console.print("[bold blue]Minnesota FDD Scraper[/bold blue]")
    console.print(f"Download PDFs: {'Yes' if download else 'No'}")
    console.print(f"Max pages: {max_pages}")
    console.print()
    
    try:
        # Run the async scraper
        rows = asyncio.run(scrape_minnesota(download_pdfs_flag=download, max_pages=max_pages))
        
        console.print(f"\n[green]✓ Scraping completed successfully![/green]")
        console.print(f"Total documents found: {len(rows)}")
        console.print(f"Output saved to: mn_clean_fdd.csv")
        
        if download:
            successful = sum(1 for row in rows if row.pdf_status == "ok")
            failed = sum(1 for row in rows if row.pdf_status == "failed")
            console.print(f"\nDownload statistics:")
            console.print(f"  Successful: {successful}")
            console.print(f"  Failed: {failed}")
            
    except KeyboardInterrupt:
        console.print("\n[yellow]Scraping interrupted by user[/yellow]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"\n[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


@app.command("wi")
def wisconsin(
    details: bool = typer.Option(False, "--details", help="Extract detailed filing information"),
    download: bool = typer.Option(False, "--download", help="Download PDF files"),
    max_workers: int = typer.Option(4, "--max-workers", help="Maximum concurrent search workers"),
    resume_from: Optional[str] = typer.Option(None, "--resume-from", help="Resume from step: 'search' or 'details'"),
):
    """Scrape Wisconsin DFI portal for franchise filings.
    
    Multi-step process:
    1. Extract active filings list
    2. Search for each franchise (can be parallelized)
    3. Extract details (if --details flag)
    4. Download PDFs (if --download flag)
    """
    console.print("[bold blue]Wisconsin FDD Scraper[/bold blue]")
    console.print(f"Extract details: {'Yes' if details else 'No'}")
    console.print(f"Download PDFs: {'Yes' if download else 'No'}")
    console.print(f"Max workers: {max_workers}")
    if resume_from:
        console.print(f"Resuming from: {resume_from}")
    console.print()
    
    try:
        # Run the async pipeline
        asyncio.run(run_wisconsin_pipeline(
            details_flag=details,
            download_flag=download,
            max_workers=max_workers,
            resume_from=resume_from
        ))
        
        console.print(f"\n[green]✓ Scraping completed successfully![/green]")
        
        # List output files
        console.print("\nOutput files created:")
        if Path("wi_active_filings.csv").exists():
            console.print("  - wi_active_filings.csv")
        if Path("wi_registered_filings.csv").exists():
            console.print("  - wi_registered_filings.csv")
        if details and Path("wi_details_filings.csv").exists():
            console.print("  - wi_details_filings.csv")
            
    except KeyboardInterrupt:
        console.print("\n[yellow]Scraping interrupted by user[/yellow]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"\n[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


@app.callback()
def main():
    """
    Franchise FDD Scrapers - Extract FDD documents from state regulatory portals.
    
    This tool provides scrapers for:
    - Minnesota Department of Commerce CARDS portal
    - Wisconsin Department of Financial Institutions portal
    
    Use 'franchise-scrapers mn --help' or 'franchise-scrapers wi --help' for more information.
    """
    pass


if __name__ == "__main__":
    app()