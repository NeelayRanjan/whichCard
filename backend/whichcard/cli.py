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


@app.command("recommend")
def recommend_command(
    query: str,
    amount: float = 0,
    app_context: str | None = typer.Option(None, "--app"),
    online: bool = False,
    json: bool = typer.Option(False, "--json"),
) -> None:
    import json as js

    from whichcard.data_layer import Catalog
    from whichcard.engine import Context, money, recommend
    from whichcard.storage import connect

    db = connect()
    result = recommend(
        Context(
            merchant_query=query,
            amount_cents=money(amount * 100),
            app_context=app_context,
            channel="online" if online else None,
        ),
        Catalog(),
        db,
    )
    db.close()
    print(
        js.dumps(result, indent=2)
        if json
        else "\n\n".join(
            f"{r['nickname']}: {r['effective_rate_pct']:g}% (${r['est_value_cents'] / 100:.2f})\n"
            + "\n".join(r["reasons"] + r["warnings"])
            for r in result["ranked"]
        )
    )


def output(value: object, as_json: bool) -> None:
    import json

    # Indented, labeled fields keep nested arithmetic readable in either mode.
    print(json.dumps(value, indent=2, default=str))


@app.command("trackers")
def trackers_command(json: bool = typer.Option(False, "--json")) -> None:
    from whichcard.data_layer import Catalog
    from whichcard.storage import connect
    from whichcard.trackers import trackers

    db = connect()
    output(trackers(Catalog(), db), json)
    db.close()


@app.command("gap")
def gap_command(json: bool = typer.Option(False, "--json")) -> None:
    from whichcard.analysis import gap_analysis
    from whichcard.data_layer import Catalog
    from whichcard.storage import connect

    db = connect()
    output(gap_analysis(Catalog(), db), json)
    db.close()


@app.command("redeem")
def redeem_command(
    cash: float = 420,
    points: int = 28000,
    program: str = "united",
    fees: float = 11.20,
    json: bool = typer.Option(False, "--json"),
) -> None:
    from whichcard.analysis import Award, Redemption, redemption
    from whichcard.data_layer import Catalog
    from whichcard.engine import money
    from whichcard.storage import connect

    db = connect()
    output(
        redemption(
            Redemption(
                cash_price_cents=money(cash * 100),
                awards=[Award(program=program, points=points, fees_cents=money(fees * 100))],
            ),
            Catalog(),
            db,
        ),
        json,
    )
    db.close()


@app.command("airport")
def airport_command(iata: str, json: bool = typer.Option(False, "--json")) -> None:
    from whichcard.analysis import airport
    from whichcard.data_layer import Catalog

    output(airport(iata, Catalog()), json)


@app.command("insights")
def insights_command(json: bool = typer.Option(False, "--json")) -> None:
    from whichcard.data_layer import Catalog
    from whichcard.insights import generate_findings
    from whichcard.storage import connect

    db = connect()
    output(generate_findings(Catalog(), db), json)
    db.close()


@app.command("ask")
def ask_command(question: str, json: bool = typer.Option(False, "--json")) -> None:
    from whichcard.assistant import ask
    from whichcard.data_layer import Catalog
    from whichcard.storage import connect

    db = connect()
    result = ask(question, Catalog(), db)
    output(result, json) if json else print(result["answer"])
    db.close()
