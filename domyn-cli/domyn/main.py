import subprocess
import typer
import yaml
from pathlib import Path
from typing import Optional

__version__ = "0.1.0"

app = typer.Typer(
    name="domyn",
    help="Domyn CLI — manage and interact with the Domyn platform.",
    no_args_is_help=True,
)


def version_callback(value: bool):
    if value:
        typer.echo(f"domyn version {__version__}")
        raise typer.Exit()


def load_config(config_file: Path) -> dict:
    if not config_file.exists():
        typer.echo(f"Not found: {config_file}")
        raise typer.Exit(1)
    with config_file.open() as f:
        return yaml.safe_load(f)


@app.callback()
def main(
    ctx: typer.Context,
    config_file: Path = typer.Option(
        Path("config.domyn.yaml"), "--config-file", help="Path to the configuration file."
    ),
    _: Optional[bool] = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True, help="Show version and exit."
    ),
):
    ctx.ensure_object(dict)
    ctx.obj["config_file"] = config_file


@app.command()
def config(ctx: typer.Context):
    """Read the config.domyn.yaml file from the current directory."""
    path = ctx.obj["config_file"]
    if path.exists():
        typer.echo(f"Using configuration file: {path}")
    else:
        typer.echo("Configurations not found, using defaults.")


@app.command()
def services(ctx: typer.Context):
    """List services that have a Dockerfile, from the path defined in config.domyn.yaml."""
    cfg = load_config(ctx.obj["config_file"])

    services_path = Path.cwd() / cfg["services"]["path"]
    if not services_path.is_dir():
        typer.echo(f"Not found: {services_path}")
        raise typer.Exit(1)

    found = [d for d in services_path.iterdir() if d.is_dir() and (d / "Dockerfile").exists()]

    if not found:
        typer.echo("No services found.")
    else:
        for svc in sorted(found):
            typer.echo(svc.name)


@app.command()
def build(
    ctx: typer.Context,
    service: str = typer.Argument(..., help="Name of the service folder to build."),
    tag: str = typer.Option("latest", "--tag", "-t", help="Docker image tag."),
):
    """Build the Docker image for a service defined in config.domyn.yaml."""
    cfg = load_config(ctx.obj["config_file"])

    service_dir = Path.cwd() / cfg["services"]["path"] / service
    dockerfile = service_dir / "Dockerfile"

    if not dockerfile.exists():
        typer.echo(f"Not found: {dockerfile}")
        raise typer.Exit(1)

    platform = cfg.get("containers", {}).get("platform")
    cmd = ["docker", "build", "-t", f"{service}:{tag}", "-f", str(dockerfile), str(service_dir)]
    if platform:
        cmd += ["--platform", platform]
    subprocess.run(cmd, check=True)


@app.command()
def push(
    ctx: typer.Context,
    service: str = typer.Argument(..., help="Name of the service image to push."),
    tag: str = typer.Option("latest", "--tag", "-t", help="Docker image tag."),
):
    """Tag and push a service image to every registry defined in config.domyn.yaml."""
    cfg = load_config(ctx.obj["config_file"])

    registries = cfg.get("registries") or []
    if not registries:
        typer.echo("No registries defined in config.domyn.yaml")
        raise typer.Exit(1)

    source = f"{service}:{tag}"
    for registry in registries:
        remote_tag = f"{registry}/{source}"
        typer.echo(f"Tagging {source} → {remote_tag}")
        subprocess.run(["docker", "tag", source, remote_tag], check=True)
        typer.echo(f"Pushing {remote_tag}")
        subprocess.run(["docker", "push", remote_tag], check=True)


@app.command()
def deploy(
    ctx: typer.Context,
    service: str = typer.Argument(..., help="Name of the service to deploy (used as Helm release name)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
):
    """Deploy via Helm using kubernetes and helm settings from config.domyn.yaml."""
    cfg = load_config(ctx.obj["config_file"])

    kube_context = cfg["kubernetes"]["context"]
    chart = cfg["helm"]["chart"]
    values_files = cfg["helm"].get("values_files") or []
    namespace = cfg["helm"]["namespace"]

    service_values = Path.cwd() / cfg["services"]["path"] / service / "values.yaml"
    if not service_values.exists():
        typer.echo(f"Not found: {service_values}")
        raise typer.Exit(1)

    all_values = [str(service_values)] + list(values_files)
    values_args = [arg for f in all_values for arg in ("--values", f)]

    if not yes:
        typer.confirm(
            f"Deploy '{service}' to context '{kube_context}', namespace '{namespace}'?",
            abort=True,
        )

    dns_postfix = cfg.get("dns", {}).get("postfix")
    set_args = ["--set", f"dns.postfix={dns_postfix}"] if dns_postfix else []

    subprocess.run(
        [
            "helm", "upgrade", "--install", service, chart,
            *values_args,
            *set_args,
            "--namespace", namespace,
            "--create-namespace",
            "--kube-context", kube_context,
        ],
        check=True,
    )


@app.command()
def remove(
    ctx: typer.Context,
    service: str = typer.Argument(..., help="Name of the Helm release to remove."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
):
    """Remove a deployed Helm release from the cluster."""
    cfg = load_config(ctx.obj["config_file"])

    kube_context = cfg["kubernetes"]["context"]
    namespace = cfg["helm"]["namespace"]

    if not yes:
        typer.confirm(
            f"Remove '{service}' from context '{kube_context}', namespace '{namespace}'?",
            abort=True,
        )

    subprocess.run(
        [
            "helm", "uninstall", service,
            "--namespace", namespace,
            "--kube-context", kube_context,
        ],
        check=True,
    )


@app.command()
def kenoby():
    """General Kenoby"""
    print("Hello there!")


if __name__ == "__main__":
    app()
