"""Load products_seed.json (with search text + embeddings) and reviews_seed.json into Supabase.

Run after schema.sql, and again whenever product or review data changes:
    python seed_products.py
Safe to re-run: existing rows are updated, not duplicated.
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
REVIEWS_FILE = Path(__file__).parent / "reviews_seed.json"


def load_json(path: Path) -> list[dict] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Could not read %s: %s", path, exc)
        return None


def main() -> int:
    products = load_json(SEED_FILE)
    reviews = load_json(REVIEWS_FILE)
    if products is None or reviews is None:
        return 1

    product_ids = {p["id"] for p in products}
    unknown = {r["product_id"] for r in reviews} - product_ids
    if unknown:
        logger.error("reviews_seed.json refers to unknown product ids: %s", sorted(unknown))
        return 1

    for p in products:
        p["search_text"] = build_search_text(p)

    try:
        logger.info("Embedding %d products...", len(products))
        vectors = get_embeddings().embed_documents([p["search_text"] for p in products])
        for p, vector in zip(products, vectors):
            p["embedding"] = vector

        client = db.get_client()
        client.table("products").upsert(products).execute()
        logger.info("Seeded %d products", len(products))

        # Products first: reviews reference them.
        client.table("reviews").upsert(reviews, on_conflict="product_id,author_name").execute()
        logger.info("Seeded %d reviews", len(reviews))
    except Exception:
        logger.exception("Seeding failed")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
