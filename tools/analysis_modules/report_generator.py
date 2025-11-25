"""
Report Generator
----------------
Generates beautiful, formatted reports using rich library.
"""
from typing import Dict, List, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
import json
import csv
from .signal_analyzer import PerformanceMetrics, SignalOutcome
from .symbol_analyzer import SymbolPerformance
from .direction_analyzer import DirectionPerformance
from .confidence_analyzer import ConfidenceBand, FalsePositivePattern
from .entry_analyzer import EntryPattern


class ReportGenerator:
    """Generates formatted reports for analysis results."""
    
    def __init__(self):
        """Initialize report generator."""
        self.console = Console()
    
    def print_overview_report(self, metrics: PerformanceMetrics) -> None:
        """Prints overall performance overview."""
        self.console.print("\n")
        self.console.print(Panel.fit(
            "[bold cyan]📊 SIGNAL PERFORMANCE OVERVIEW[/bold cyan]",
            border_style="cyan"
        ))
        
        # Main metrics table
        table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
        table.add_column("Metric", style="cyan", width=30)
        table.add_column("Value", justify="right", style="yellow")
        
        table.add_row("Total Signals", str(metrics.total_signals))
        table.add_row("Open Signals", str(metrics.open_count))
        table.add_row("Closed Signals", str(metrics.total_signals - metrics.open_count))
        
        # Win rate with color
        win_color = "green" if metrics.win_rate >= 50 else "red"
        table.add_row("Win Rate", f"[{win_color}]{metrics.win_rate}%[/{win_color}]")
        
        # Outcomes
        table.add_row("", "")
        table.add_row("[bold]TP Outcomes[/bold]", "")
        table.add_row("  TP1 Hit", f"[green]{metrics.tp1_count}[/green] ({metrics.tp1_hit_rate}%)")
        table.add_row("  TP2 Hit", f"[green]{metrics.tp2_count}[/green] ({metrics.tp2_hit_rate}%)")
        
        table.add_row("", "")
        table.add_row("[bold]SL Outcomes[/bold]", "")
        table.add_row("  SL Hit", f"[red]{metrics.sl_count}[/red]")
        table.add_row("  Total SL Rate", f"[red]{metrics.sl_hit_rate}%[/red]")
        
        # R-multiples
        table.add_row("", "")
        table.add_row("[bold]R-Multiples[/bold]", "")
        r_color = "green" if metrics.avg_r_multiple > 0 else "red"
        table.add_row("  Average R", f"[{r_color}]{metrics.avg_r_multiple}R[/{r_color}]")
        table.add_row("  Average Win", f"[green]{metrics.avg_win_r}R[/green]")
        table.add_row("  Average Loss", f"[red]{metrics.avg_loss_r}R[/red]")
        table.add_row("  Expectancy", f"[{r_color}]{metrics.expectancy}R[/{r_color}]")
        
        # Time metrics
        table.add_row("", "")
        table.add_row("[bold]Time Metrics[/bold]", "")
        table.add_row("  Avg Hold Time", f"{metrics.avg_hold_time_hours}h")
        table.add_row("  Avg Time to TP", f"{metrics.avg_time_to_tp_hours}h")
        table.add_row("  Avg Time to SL", f"{metrics.avg_time_to_sl_hours}h")
        
        # MFE/MAE
        if metrics.avg_mfe_percent != 0 or metrics.avg_mae_percent != 0:
            table.add_row("", "")
            table.add_row("[bold]MFE/MAE[/bold]", "")
            table.add_row("  Avg MFE", f"{metrics.avg_mfe_percent}%")
            table.add_row("  Avg MAE", f"{metrics.avg_mae_percent}%")
        
        self.console.print(table)
    
    def print_symbol_report(
        self, 
        top_performers: List[SymbolPerformance],
        worst_performers: List[SymbolPerformance]
    ) -> None:
        """Prints symbol performance report."""
        self.console.print("\n")
        self.console.print(Panel.fit(
            "[bold green]🏆 TOP PERFORMING SYMBOLS[/bold green]",
            border_style="green"
        ))
        
        table = Table(show_header=True, header_style="bold green", box=box.ROUNDED)
        table.add_column("Symbol", style="cyan")
        table.add_column("Signals", justify="right")
        table.add_column("Win Rate", justify="right")
        table.add_column("Avg R", justify="right")
        table.add_column("TP1 Rate", justify="right")
        
        for perf in top_performers:
            r_color = "green" if perf.avg_r_multiple > 0 else "red"
            table.add_row(
                perf.symbol,
                str(perf.signal_count),
                f"{perf.win_rate}%",
                f"[{r_color}]{perf.avg_r_multiple}R[/{r_color}]",
                f"{perf.tp1_rate}%"
            )
        
        self.console.print(table)
        
        self.console.print("\n")
        self.console.print(Panel.fit(
            "[bold red]⚠️  WORST PERFORMING SYMBOLS[/bold red]",
            border_style="red"
        ))
        
        table = Table(show_header=True, header_style="bold red", box=box.ROUNDED)
        table.add_column("Symbol", style="cyan")
        table.add_column("Signals", justify="right")
        table.add_column("Win Rate", justify="right")
        table.add_column("Avg R", justify="right")
        table.add_column("SL Rate", justify="right")
        
        for perf in worst_performers:
            table.add_row(
                perf.symbol,
                str(perf.signal_count),
                f"[red]{perf.win_rate}%[/red]",
                f"[red]{perf.avg_r_multiple}R[/red]",
                f"[red]{perf.sl_rate}%[/red]"
            )
        
        self.console.print(table)
    
    def print_direction_report(self, long_perf: DirectionPerformance, short_perf: DirectionPerformance, bias: Dict) -> None:
        """Prints LONG vs SHORT comparison."""
        self.console.print("\n")
        self.console.print(Panel.fit(
            f"[bold yellow]🎯 DIRECTION ANALYSIS - Bias: {bias['bias']}[/bold yellow]",
            border_style="yellow"
        ))
        
        table = Table(show_header=True, header_style="bold yellow", box=box.ROUNDED)
        table.add_column("Direction")
        table.add_column("Signals", justify="right")
        table.add_column("Win Rate", justify="right")
        table.add_column("Avg R", justify="right")
        table.add_column("TP1 Rate", justify="right")
        table.add_column("SL Rate", justify="right")
        
        for perf in [long_perf, short_perf]:
            r_color = "green" if perf.avg_r_multiple > 0 else "red"
            table.add_row(
                f"[bold]{perf.direction}[/bold]",
                str(perf.signal_count),
                f"{perf.win_rate}%",
                f"[{r_color}]{perf.avg_r_multiple}R[/{r_color}]",
                f"{perf.tp1_rate}%",
                f"[red]{perf.sl_rate}%[/red]"
            )
        
        self.console.print(table)
        self.console.print(f"\n[dim]Distribution: {bias['ratio']} (LONG:SHORT) - {bias['long_percentage']}% LONG, {bias['short_percentage']}% SHORT[/dim]")
    
    def print_confidence_report(
        self, 
        bands: List[ConfidenceBand],
        correlation: float,
        optimal: Dict
    ) -> None:
        """Prints confidence analysis report."""
        self.console.print("\n")
        self.console.print(Panel.fit(
            f"[bold magenta]🎯 CONFIDENCE ANALYSIS - Correlation: {correlation}[/bold magenta]",
            border_style="magenta"
        ))
        
        table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
        table.add_column("Confidence Range")
        table.add_column("Signals", justify="right")
        table.add_column("Win Rate", justify="right")
        table.add_column("Avg R", justify="right")
        table.add_column("False Positives", justify="right")
        
        for band in bands:
            r_color = "green" if band.avg_r_multiple > 0 else "red"
            fp_color = "red" if band.false_positive_count > 0 else "green"
            table.add_row(
                f"{band.min_confidence:.2f} - {band.max_confidence:.2f}",
                str(band.signal_count),
                f"{band.win_rate}%",
                f"[{r_color}]{band.avg_r_multiple}R[/{r_color}]",
                f"[{fp_color}]{band.false_positive_count}[/{fp_color}]"
            )
        
        self.console.print(table)
        
        self.console.print(f"\n[bold green]Optimal Threshold: {optimal['optimal_threshold']}[/bold green]")
        self.console.print(f"Expected Win Rate: {optimal['expected_win_rate']}% | Expected R: {optimal['expected_r_multiple']}R")
    
    def print_false_positive_patterns(self, patterns: List[FalsePositivePattern]) -> None:
        """Prints false positive pattern detection."""
        if not patterns:
            self.console.print("\n[green]✅ No significant false positive patterns detected![/green]")
            return
        
        self.console.print("\n")
        self.console.print(Panel.fit(
            "[bold red]🚨 FALSE POSITIVE PATTERNS DETECTED[/bold red]",
            border_style="red"
        ))
        
        for pattern in patterns:
            self.console.print(f"\n[bold red]⚠️  {pattern.pattern_name}[/bold red]")
            self.console.print(f"   {pattern.description}")
            self.console.print(f"   Affected: {pattern.affected_signals} signals | SL Rate: {pattern.sl_hit_rate}%")
            if pattern.common_symbols:
                self.console.print(f"   Common symbols: {', '.join(pattern.common_symbols[:5])}")
            self.console.print(f"   [yellow]💡 Suggestion:[/yellow] {pattern.suggestion}")
    
    def print_entry_patterns(self, patterns: List[EntryPattern], recommendations: List[Dict]) -> None:
        """Prints entry analysis and filtering recommendations."""
        self.console.print("\n")
        self.console.print(Panel.fit(
            "[bold red]🎯 ENTRY ANALYSIS & FILTER RECOMMENDATIONS[/bold red]",
            border_style="red"
        ))
        
        if patterns:
            self.console.print("\n[bold]Risk Patterns Detected:[/bold]")
            for pattern in patterns:
                self.console.print(f"\n[red]⚠️  {pattern.pattern_name}[/red]")
                self.console.print(f"   {pattern.description}")
                self.console.print(f"   SL Hit Rate: {pattern.sl_hit_rate}%")
                self.console.print(f"   [yellow]Filter:[/yellow] {pattern.suggested_filter}")
        
        if recommendations:
            self.console.print("\n[bold yellow]📋 ACTION ITEMS:[/bold yellow]")
            for i, rec in enumerate(recommendations, 1):
                priority_color = "red" if rec['priority'] == 'HIGH' else "yellow"
                self.console.print(f"\n{i}. [{priority_color}]{rec['priority']}[/{priority_color}] {rec['title']}")
                self.console.print(f"   {rec['details']}")
                self.console.print(f"   [green]→[/green] {rec['action']}")
    
    def export_to_json(self, data: Dict, filename: str) -> None:
        """Exports analysis results to JSON."""
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        self.console.print(f"\n[green]✅ Exported to {filename}[/green]")
    
    def export_to_csv(self, data: List[Dict], filename: str) -> None:
        """Exports data to CSV."""
        if not data:
            return
        
        with open(filename, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        
        self.console.print(f"\n[green]✅ Exported to {filename}[/green]")
