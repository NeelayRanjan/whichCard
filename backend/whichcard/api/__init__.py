import sqlite3

from fastapi import Depends, FastAPI, HTTPException

from whichcard.analysis import Redemption
from whichcard.api.service import catalog, database
from whichcard.data_layer.models import Place
from whichcard.engine import Context, recommend

app = FastAPI(title="whichcard", version="0.1.0")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


@app.post("/api/recommend")
def recommend_api(context: Context, db: sqlite3.Connection = Depends(database)):
    if context.category and context.category not in catalog().categories:
        raise HTTPException(422, "unknown category")
    return recommend(context, catalog(), db)


@app.get("/api/trackers")
def trackers_api(db: sqlite3.Connection = Depends(database)):
    from whichcard.trackers import trackers

    return trackers(catalog(), db)


@app.post("/api/credits/{card}/{credit_id}")
def credit_api(
    card: str, credit_id: str, payload: dict[str, int], db: sqlite3.Connection = Depends(database)
):
    from whichcard.engine import today
    from whichcard.trackers import mark_credit

    try:
        mark_credit(db, catalog(), card, credit_id, payload.get("amount_cents", -1), today())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"status": "saved"}


@app.get("/api/spend")
def spend_api(db: sqlite3.Connection = Depends(database)):
    from whichcard.analysis import spend_profile

    return spend_profile(catalog(), db)


@app.get("/api/gap")
def gap_api(db: sqlite3.Connection = Depends(database)):
    from whichcard.analysis import gap_analysis

    return gap_analysis(catalog(), db)


@app.post("/api/redeem/evaluate")
def redeem_api(payload: Redemption, db: sqlite3.Connection = Depends(database)):
    from whichcard.analysis import redemption

    try:
        return redemption(payload, catalog(), db)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/airport/{iata}")
def airport_api(iata: str):
    from whichcard.analysis import airport

    return airport(iata, catalog())


@app.get("/api/now")
def now_api(
    app: str | None = None,
    merchant: str | None = None,
    category: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    db: sqlite3.Connection = Depends(database),
):
    from whichcard.analysis import now

    try:
        return now(
            Context(app_context=app, merchant_query=merchant, category=category, lat=lat, lon=lon),
            catalog(),
            db,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/places")
def place_api(place: Place):
    from whichcard.data_layer import write_yaml

    c = catalog()
    places = [p for p in c.places if p.name != place.name] + [place]
    write_yaml(c.root / "config/places.local.yaml", [p.model_dump() for p in places])
    c.places = places
    return {"status": "saved"}


@app.get("/api/findings")
def findings_api(db: sqlite3.Connection = Depends(database)):
    from whichcard.insights import generate_findings

    return generate_findings(catalog(), db)


@app.post("/api/findings/{fingerprint}/dismiss")
def dismiss_api(fingerprint: str, db: sqlite3.Connection = Depends(database)):
    from whichcard.insights import dismiss

    try:
        dismiss(db, fingerprint)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"status": "dismissed"}


@app.post("/api/ask")
def ask_api(payload: dict[str, str], db: sqlite3.Connection = Depends(database)):
    import httpx

    from whichcard.assistant import ask

    try:
        return ask(payload.get("question", ""), catalog(), db, payload.get("session_id", "local"))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (httpx.HTTPError, KeyError, IndexError) as exc:
        raise HTTPException(
            502, "Local assistant is unavailable or returned an invalid response. Check endpoint and model."
        ) from exc
