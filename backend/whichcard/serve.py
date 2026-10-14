import uvicorn

from whichcard.data_layer import Catalog

if __name__ == "__main__":
    config = Catalog().preferences.server
    uvicorn.run("whichcard.api:app", host=config.bind, port=config.port)
