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


@app.command("import")
def import_command(
    file: str,
    card: str = typer.Option("CSP"),
    adapter: str | None = None,
    json: bool = typer.Option(False, "--json"),
) -> None:
    import json as js
    from pathlib import Path

    from whichcard.data_layer import Catalog
    from whichcard.importers import import_file
    from whichcard.storage import connect

    catalog = Catalog()
    instance = next((c for c in catalog.wallet.cards if card in {c.card, c.nickname}), None)
    if instance is None:
        raise typer.BadParameter(f"unknown wallet card {card}")
    db = connect()
    try:
        result = import_file(db, Path(file), instance.card, adapter)
        from whichcard.inference import enrich

        enrich(db, catalog)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    finally:
        db.close()
    print(js.dumps(result, indent=2) if json else f"Imported {result['added']} new transactions.")


@app.command()
def review(json: bool = typer.Option(False, "--json")) -> None:
    import json as js

    from whichcard.inference import review_queue
    from whichcard.storage import connect

    db = connect()
    rows = review_queue(db)
    db.close()
    print(
        js.dumps(rows, indent=2)
        if json
        else "\n".join(
            f"{r['id']}: {r['raw_description']} — {r['category']} ({r['confidence']:.0%})" for r in rows
        )
        or "No transactions need review."
    )
