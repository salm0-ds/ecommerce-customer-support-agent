"""Load products_seed.json into Supabase with search text + embeddings.

Run after schema.sql, and again whenever product data changes:
    python seed_products.py
"""

import json
import logging
import sys
from pathlib import Path

import db
from product_search import build_search_text, get_embeddings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("seed")

SEED_FILE = Path(__file__).parent / "products_seed.json"


def main() -> int:
    try:
        products = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Could not read %s: %s", SEED_FILE, exc)
        return 1

    for p in products:
        p["search_text"] = build_search_text(p)

    try:
        logger.info("Embedding %d products...", len(products))
        vectors = get_embeddings().embed_documents([p["search_text"] for p in products])
        for p, vector in zip(products, vectors):
            p["embedding"] = vector

        db.get_client().table("products").upsert(products).execute()
    except Exception:
        logger.exception("Seeding failed")
        return 1

    logger.info("Seeded %d products", len(products))
    return 0


if __name__ == "__main__":
    sys.exit(main())
