import typer

app = typer.Typer(no_args_is_help=True)

@app.command()
def version() -> None:
    print("whichcard 0.1.0")
