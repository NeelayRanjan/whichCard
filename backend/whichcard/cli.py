import typer

app = typer.Typer(no_args_is_help=True)


@app.command()
def version() -> None:
    print("whichcard 0.1.0")


cards = typer.Typer()
app.add_typer(cards, name="cards")


@cards.command("list")
def cards_list(json: bool = typer.Option(False, "--json")) -> None:
    import json as js

    from whichcard.data_layer import Catalog

    result = [{"id": c.id, "name": c.name, "confidence": c.confidence} for c in Catalog().cards.values()]
    print(
        js.dumps(result, indent=2)
        if json
        else "\n".join(f"{c['id']}: {c['name']} [{c['confidence']}]" for c in result)
    )


@cards.command("review")
def cards_review() -> None:
    from whichcard.data_layer import Catalog

    catalog = Catalog()
    path = catalog.root / "REVIEW_CARDS.md"
    path.write_text(catalog.review())
    print(path)
