"""CLI entry point for the OpenDataViz Pipeline."""

import sys
import logging
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .extract import extract_all, extract_country_metadata
from .transform import transform_records
from .load import load_all
from .imputation import DataImputer
from .projection import Projector
from .quality import run_quality_checks
from .export import export_all, export_quality_report

console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("opendataviz")


def run_pipeline() -> None:
    """Run the full ETL pipeline: extract → transform → load."""
    console.print(Panel("🌍 [bold green]OpenDataViz Pipeline[/] — Extracting African Economic Data", expand=False))
    
    start = time.time()
    
    # Extract
    console.print("\n[bold cyan]Step 1/3:[/] Extracting from World Bank API...")
    raw_records = extract_all()
    if not raw_records:
        console.print("[bold red]No records extracted! Aborting.[/]")
        sys.exit(1)
    
    import httpx
    with httpx.Client() as client:
        country_metadata = extract_country_metadata(client)
    
    # Transform
    console.print("\n[bold cyan]Step 2/3:[/] Transforming data...")
    data = transform_records(raw_records)
    
    # Load
    console.print("\n[bold cyan]Step 3/3:[/] Loading into DuckDB warehouse...")
    load_all(data, country_metadata)
    
    elapsed = time.time() - start
    console.print(f"\n[bold green]✅ Pipeline complete in {elapsed:.1f}s[/]")
    
    # Summary table
    table = Table(title="Pipeline Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Raw records", f"{len(raw_records):,}")
    table.add_row("Facts loaded", f"{len(data['facts']):,}")
    table.add_row("Countries", f"{len(data['dim_country'])}")
    table.add_row("Indicators", f"{len(data['dim_indicator'])}")
    table.add_row("Year range", f"{min(d['year'] for d in data['dim_date'])}-{max(d['year'] for d in data['dim_date'])}")
    console.print(table)


def run_imputation(method: str = "knn") -> None:
    """Fill missing values via ML imputation (KNN/Iterative), pole by pole."""
    console.print(Panel("🧩 [bold magenta]ML Imputation[/] — Filling Missing Values", expand=False))
    results = DataImputer().run_all(method=method)

    table = Table(title="Imputation Summary")
    table.add_column("Indicator", style="cyan")
    table.add_column("Missing", justify="right")
    table.add_column("Imputed", justify="right", style="green")
    table.add_column("Note", style="dim")
    for r in results:
        table.add_row(r.short_name, str(r.total_missing), str(r.imputed), r.skipped_reason or "")
    console.print(table)

    total_imputed = sum(r.imputed for r in results)
    total_missing = sum(r.total_missing for r in results)
    console.print(f"\n[bold green]✅ Imputed {total_imputed}/{total_missing} missing values[/]")


def run_projection() -> None:
    """Forecast the next 5 years per (country, indicator) with ElasticNet."""
    console.print(Panel("\U0001f52e [bold blue]Projections[/] — Forecasting 5 Years Ahead", expand=False))
    results = Projector().run_all()

    table = Table(title="Projection Summary")
    table.add_column("Indicator", style="cyan")
    table.add_column("Countries Projected", justify="right", style="green")
    table.add_column("Skipped (short history)", justify="right", style="dim")
    for r in results:
        table.add_row(r.short_name, str(r.countries_projected), str(r.countries_skipped))
    console.print(table)

    total_projected = sum(r.countries_projected for r in results)
    console.print(f"\n[bold green]✅ Generated projections for {total_projected} country/indicator pairs[/]")


def run_quality() -> dict:
    """Run data quality checks."""
    console.print(Panel("🔍 [bold yellow]Data Quality Checks[/]", expand=False))
    report = run_quality_checks()
    
    console.print(f"\n[bold]Overall Score: {report['overall_score']}/100[/]")
    for dim_name, dim_data in report["dimensions"].items():
        emoji = "✅" if dim_data["score"] >= 80 else "⚠️" if dim_data["score"] >= 50 else "❌"
        console.print(f"  {emoji} {dim_name.title()}: {dim_data['score']}/100")
    
    return report


def run_export(quality_report: dict | None = None) -> None:
    """Export data for dashboard."""
    console.print(Panel("📊 [bold blue]Exporting Dashboard Data[/]", expand=False))
    export_all()
    if quality_report:
        export_quality_report(quality_report)
    console.print("[bold green]✅ Dashboard data exported[/]")


def main() -> None:
    """Main entry point."""
    command = sys.argv[1] if len(sys.argv) > 1 else "all"
    
    if command == "extract":
        raw = extract_all()
        console.print(f"Extracted {len(raw)} records")
    elif command == "pipeline":
        run_pipeline()
    elif command == "impute":
        run_imputation()
    elif command == "project":
        run_projection()
    elif command == "quality":
        run_quality()
    elif command == "export":
        run_export()
    elif command == "all":
        run_pipeline()
        run_imputation()
        run_projection()
        report = run_quality()
        run_export(report)
    else:
        console.print(f"[red]Unknown command: {command}[/]")
        console.print("Usage: python -m pipeline.main [all|pipeline|impute|project|quality|export]")
        sys.exit(1)


if __name__ == "__main__":
    main()
