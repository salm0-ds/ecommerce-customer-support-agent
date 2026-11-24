"""The SuggestProducts tool: filter the catalog in the database, let the LLM pick.

The catalog is small, so the LLM sees every product that passes the hard filters
(in stock, category, price, not already shown) and chooses the best fit itself.
"""

import logging
from typing import Literal

from pydantic import BaseModel, Field, model_validator

import db

logger = logging.getLogger(__name__)

Category = Literal["sleep", "gut-health", "focus", "energy", "stress", "hydration"]


class SuggestProducts(BaseModel):
    """Look up products that could match what the customer wants.
    Call this as soon as you have any idea what they want, even if it is vague.
    Products already shown in this conversation are excluded automatically.
    Returns the matching products for you to choose from, or an empty list."""

    query: str = Field(
        description="What the customer is looking for, combining everything they have said, "
        "e.g. 'non-drowsy stress relief for work anxiety'."
    )
    category: Category | None = Field(
        default=None, description="Only set if the customer's goal clearly maps to one category."
    )
    min_price: float | None = Field(
        default=None, ge=0, description="Only set if the customer stated an exact minimum price."
    )
    max_price: float | None = Field(
        default=None, ge=0, description="Only set if the customer stated an exact maximum price."
    )

    @model_validator(mode="after")
    def check_prices(self):
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("min_price cannot be greater than max_price")
        return self


def suggest_products(args: SuggestProducts, exclude_ids: list[str]) -> dict:
    """Return compact candidates for the LLM to choose from."""
    products = db.find_products(args.category, args.min_price, args.max_price, exclude_ids)
    logger.info(
        "suggest_products query=%r filters=%s -> %d products",
        args.query, args.model_dump(exclude={"query"}, exclude_none=True), len(products),
    )

    if not products:
        return {"results": [], "note": "Nothing matches these filters. Ask the customer one clarifying question."}

    return {
        "results": [
            {
                "id": p["id"],
                "name": p["name"],
                "category": p["category"],
                "price": float(p["price"]),
                "short_description": p["short_description"],
                "description": p["description"],
                "benefits": p["benefits"],
                "rating": float(p["rating"]),
            }
            for p in products
        ]
    }
