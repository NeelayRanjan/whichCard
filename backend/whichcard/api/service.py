from functools import lru_cache

from whichcard.data_layer import Catalog
from whichcard.storage import connect


@lru_cache(maxsize=1)
def catalog() -> Catalog:
    return Catalog()


def database():
    db = connect()
    try:
        yield db
    finally:
        db.close()
