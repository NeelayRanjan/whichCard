import sqlite3
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile

from whichcard.analysis import Redemption
from whichcard.api.service import catalog, database
from whichcard.data_layer.models import Offer, Place, Preferences, StatementInput, Wallet
from whichcard.engine import Context, recommend


@asynccontextmanager
async def lifespan(app: FastAPI):
    from whichcard.storage import connect

    catalog()
    db = connect()
    db.close()
    yield


app = FastAPI(title="whichcard", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def same_origin(request, call_next):
    from urllib.parse import urlparse

    from fastapi.responses import JSONResponse

    origin = request.headers.get("origin")
    if (
        request.method not in {"GET", "HEAD", "OPTIONS"}
        and origin
        and urlparse(origin).netloc != request.url.netloc
    ):
        return JSONResponse({"detail": "Cross-origin writes are not allowed"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


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
    amount_cents: int = 0,
    db: sqlite3.Connection = Depends(database),
):
    from whichcard.analysis import now

    try:
        return now(
            Context(
                app_context=app,
                merchant_query=merchant,
                category=category,
                lat=lat,
                lon=lon,
                amount_cents=amount_cents,
            ),
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


@app.get("/api/config")
def config_api():
    from whichcard.assistant import SUGGESTIONS

    c = catalog()
    return {
        "wallet": c.wallet.model_dump(mode="json"),
        "preferences": c.preferences.model_dump(mode="json"),
        "cards": {k: v.model_dump(mode="json") for k, v in c.cards.items()},
        "categories": list(c.categories),
        "valuations": {k: c.valuation(k).model_dump() for k in c.valuations},
        "places": [p.model_dump() for p in c.places],
        "offers": [p.model_dump(mode="json") for p in c.offers],
        "apps": list(c.apps),
        "suggestions": SUGGESTIONS,
    }


@app.put("/api/settings")
def settings_api(preferences: Preferences):
    from whichcard.data_layer import write_yaml

    c = catalog()
    unknown = set(preferences.valuations) - set(c.valuations)
    if unknown:
        raise HTTPException(422, "unknown valuation currencies: " + ", ".join(sorted(unknown)))
    write_yaml(c.root / "config/preferences.local.yaml", preferences.model_dump(mode="json"))
    c.preferences = preferences
    return {"status": "saved"}


@app.put("/api/wallet")
def wallet_api(wallet: Wallet):
    from whichcard.data_layer import write_yaml

    c = catalog()
    if any(card.card not in c.cards for card in wallet.cards):
        raise HTTPException(422, "unknown card id")
    write_yaml(c.root / "config/wallet.yaml", wallet.model_dump(mode="json"))
    c.wallet = wallet
    return {"status": "saved"}


@app.put("/api/offers")
def offers_api(offers: list[Offer]):
    from whichcard.data_layer import write_yaml

    c = catalog()
    if any(o.wallet_card not in {card.card for card in c.wallet.cards} for o in offers):
        raise HTTPException(422, "offer must reference a wallet card")
    write_yaml(c.root / "config/offers.local.yaml", [o.model_dump(mode="json") for o in offers])
    c.offers = offers
    return {"status": "saved"}


@app.get("/api/transactions")
def transactions_api(
    category: str | None = None,
    card: str | None = None,
    review: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: sqlite3.Connection = Depends(database),
):
    from whichcard.storage import transactions

    rows = [
        r
        for r in transactions(db, card)
        if (not category or r["category"] == category)
        and (not review or r["confidence"] < 0.7 and not r["is_fee"] and not r["is_payment"])
    ]
    rows.reverse()
    return {"total": len(rows), "rows": rows[offset : offset + limit]}


@app.post("/api/transactions/{transaction_id}/override")
def override_api(transaction_id: int, payload: dict[str, str], db: sqlite3.Connection = Depends(database)):
    from whichcard.inference import override

    try:
        return override(db, catalog(), transaction_id, payload.get("field", ""), payload.get("value", ""))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/import")
async def import_api(
    file: UploadFile = File(...),
    card: str = Form(...),
    adapter: str | None = Form(None),
    db: sqlite3.Connection = Depends(database),
):
    import tempfile
    from pathlib import Path

    from whichcard.importers import import_file
    from whichcard.inference import enrich

    c = catalog()
    if card not in {i.card for i in c.wallet.cards}:
        raise HTTPException(422, "unknown wallet card")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".csv", ".ofx", ".qfx"}:
        raise HTTPException(422, "upload CSV, OFX or QFX")
    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "file exceeds 10 MB")
    folder = c.root / "imports"
    folder.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=folder, suffix=suffix, delete=False) as temp:
        temp.write(content)
        path = Path(temp.name)
    try:
        result = import_file(db, path, card, adapter or None)
        enrich(db, c)
        return result
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        path.unlink(missing_ok=True)


@app.post("/api/statements")
def statement_api(payload: StatementInput, db: sqlite3.Connection = Depends(database)):
    if payload.wallet_card_id not in {c.card for c in catalog().wallet.cards}:
        raise HTTPException(422, "unknown wallet card")
    with db:
        db.execute(
            'INSERT INTO statement(wallet_card_id,close_date,statement_balance,source) VALUES(?,?,?,"manual") '
            'ON CONFLICT(wallet_card_id,close_date) DO UPDATE SET statement_balance=excluded.statement_balance,source="manual"',
            (payload.wallet_card_id, payload.close_date.isoformat(), payload.statement_balance),
        )
    return {"status": "saved"}


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    from fastapi.responses import FileResponse

    from whichcard.data_layer import ROOT

    root = (ROOT / "frontend/dist").resolve()
    candidate = (root / path).resolve()
    if path.startswith("api/") or not candidate.is_relative_to(root):
        raise HTTPException(404, "not found")
    if candidate.is_file():
        return FileResponse(candidate)
    if (root / "index.html").exists():
        return FileResponse(root / "index.html")
    raise HTTPException(503, "Build frontend first: cd frontend && npm run build")
