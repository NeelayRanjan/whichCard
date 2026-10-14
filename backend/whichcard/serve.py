import uvicorn

if __name__ == "__main__":
    uvicorn.run("whichcard.api:app", host="0.0.0.0", port=8787)
