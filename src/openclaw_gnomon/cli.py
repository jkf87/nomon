import typer
from pathlib import Path
import sys
from openclaw_gnomon.paths import (
    openclaw_skills_dir,
    openclaw_mcp_config_path,
    gnomon_config_path,
)
from openclaw_gnomon.installer import (
    stage_skill_files,
    merge_mcp_entry,
    write_gnomon_config,
    remove_mcp_entry,
)
from rich.console import Console

console = Console()
app = typer.Typer(help="Gnomon — eval-first workflow harness for OpenClaw")
rubric_app = typer.Typer(help="Rubric management commands")
app.add_typer(rubric_app, name="rubric")


@app.command()
def install(verbose: bool = typer.Option(False, "--verbose", "-v")):
    """Install Gnomon skill and MCP into OpenClaw. Idempotent."""
    try:
        skills_dir = openclaw_skills_dir()
        mcp_config_path = openclaw_mcp_config_path()
        config_path = gnomon_config_path()

        console.print("[bold]Installing Gnomon for OpenClaw...[/bold]")

        if verbose:
            console.print(f"  Staging skill files to {skills_dir}/gnomon/")
        stage_skill_files(skills_dir)
        console.print("[green]✓[/green] Skill staged")

        if verbose:
            console.print(f"  Merging MCP entry in {mcp_config_path}")
        merge_mcp_entry(mcp_config_path)
        console.print("[green]✓[/green] MCP entry registered")

        if verbose:
            console.print(f"  Writing config to {config_path}")
        write_gnomon_config(config_path)
        console.print("[green]✓[/green] Config written")

        console.print("\n[bold green]Installation complete![/bold green]")
        console.print("Run: /gnomon:setup")

    except Exception as e:
        console.print(f"[red]✗ Installation failed: {e}[/red]")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@app.command()
def uninstall(verbose: bool = typer.Option(False, "--verbose", "-v")):
    """Uninstall Gnomon from OpenClaw."""
    try:
        mcp_config_path = openclaw_mcp_config_path()
        console.print("[bold]Uninstalling Gnomon from OpenClaw...[/bold]")

        if verbose:
            console.print(f"  Removing MCP entry from {mcp_config_path}")
        remove_mcp_entry(mcp_config_path)
        console.print("[green]✓[/green] MCP entry removed")

        console.print("[yellow]Note:[/yellow] ~/.openclaw/skills/gnomon/ not deleted")
        console.print("\n[bold green]Uninstall complete![/bold green]")

    except Exception as e:
        console.print(f"[red]✗ Uninstall failed: {e}[/red]")
        sys.exit(1)


@app.command()
def doctor(verbose: bool = typer.Option(False, "--verbose", "-v")):
    """Diagnose Gnomon installation."""
    try:
        console.print("[bold]Diagnosing Gnomon installation...[/bold]")

        skills_dir = openclaw_skills_dir()
        mcp_config_path = openclaw_mcp_config_path()
        config_path = gnomon_config_path()

        checks = []

        skill_file = skills_dir / "gnomon" / "SKILL.md"
        skill_ok = skill_file.exists()
        checks.append(("Skill file", skill_ok, str(skill_file)))

        import json
        mcp_ok = False
        if mcp_config_path.exists():
            try:
                with open(mcp_config_path) as f:
                    config = json.load(f)
                mcp_ok = "gnomon" in config.get("mcpServers", {})
            except Exception:
                pass
        checks.append(("MCP entry", mcp_ok, str(mcp_config_path)))

        config_ok = config_path.exists()
        checks.append(("Gnomon config", config_ok, str(config_path)))

        import subprocess
        try:
            subprocess.run(["uvx", "--version"], capture_output=True, check=True, timeout=5)
            uvx_ok = True
        except Exception:
            uvx_ok = False
        checks.append(("uvx available", uvx_ok, "uvx on PATH"))

        console.print()
        for name, ok, path in checks:
            icon = "[green]✓[/green]" if ok else "[red]✗[/red]"
            console.print(f"{icon} {name}: {path}")

        all_ok = all(ok for _, ok, _ in checks)
        if all_ok:
            console.print("\n[bold green]All checks passed![/bold green]")
            sys.exit(0)
        else:
            console.print("\n[bold yellow]Some checks failed. Run: openclaw-gnomon install[/bold yellow]")
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]Doctor check failed: {e}[/red]")
        sys.exit(1)


@app.command(name="run")
def run_workflow(
    rubric: Path = typer.Option(None, "--rubric", "-r", help="Path to rubric.yaml"),
):
    """Run a Gnomon workflow. Requires a rubric.yaml (eval-first)."""
    if rubric is None:
        rubric = Path("rubric.yaml")

    if not rubric.exists():
        console.print(
            "[red]✗ No rubric.yaml found.[/red]\n"
            "Gnomon requires eval criteria before execution.\n"
            "Create one with:\n\n"
            "  [bold]openclaw-gnomon rubric new[/bold]\n\n"
            "Then review it with:\n\n"
            "  [bold]openclaw-gnomon rubric check rubric.yaml[/bold]"
        )
        sys.exit(1)

    from openclaw_gnomon.rubric import load_rubric, validate_rubric
    rubric_obj = load_rubric(rubric)
    warnings = validate_rubric(rubric_obj)
    for w in warnings:
        console.print(f"[yellow]⚠ {w}[/yellow]")

    console.print(f"[green]✓[/green] Rubric loaded: {len(rubric_obj.items)} items")
    console.print("[bold]Gnomon workflow ready. (wire your workflow execution here)[/bold]")


@rubric_app.command(name="new")
def rubric_new(
    output: Path = typer.Option(Path("rubric.yaml"), "--output", "-o", help="Output path"),
):
    """Generate a rubric.yaml scaffold in the current directory."""
    import importlib.resources
    pkg_dir = Path(__file__).parent / "skill_template"
    template_path = pkg_dir / "rubric_template.yaml"
    content = template_path.read_text()

    output.write_text(content)
    console.print(f"[green]✓[/green] Rubric template created: {output}")
    console.print(f"Edit it, then validate with: [bold]openclaw-gnomon rubric check {output}[/bold]")


@rubric_app.command(name="check")
def rubric_check(rubric_path: Path = typer.Argument(..., help="Path to rubric.yaml")):
    """Validate a rubric.yaml and show item label statistics."""
    if not rubric_path.exists():
        console.print(f"[red]✗ File not found: {rubric_path}[/red]")
        sys.exit(1)

    from openclaw_gnomon.rubric import load_rubric, validate_rubric
    rubric_obj = load_rubric(rubric_path)
    warnings = validate_rubric(rubric_obj)

    total = len(rubric_obj.items)
    counts: dict[str, int] = {}
    for item in rubric_obj.items:
        counts[item.method] = counts.get(item.method, 0) + 1

    console.print(f"\n[bold]Rubric:[/bold] {rubric_obj.task}")
    console.print(f"[bold]Persona:[/bold] {rubric_obj.persona}")
    console.print(f"[bold]Items:[/bold] {total}\n")

    for method, count in sorted(counts.items()):
        pct = count / total * 100 if total else 0
        console.print(f"  {method:20s}  {count:3d}  ({pct:.0f}%)")

    if warnings:
        console.print()
        for w in warnings:
            console.print(f"[yellow]⚠ {w}[/yellow]")
        sys.exit(1)
    else:
        console.print("\n[green]✓ Rubric is valid.[/green]")


if __name__ == "__main__":
    app()
