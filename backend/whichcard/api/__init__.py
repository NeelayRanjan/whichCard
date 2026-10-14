import sqlite3

from fastapi import Depends, FastAPI, HTTPException

from whichcard.api.service import catalog, database
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
