"""Product embedding repository for semantic search data access."""

import asyncio
import logging
from typing import Optional, List, Dict
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository
from ..models.product_embedding import ProductEmbedding

logger = logging.getLogger(__name__)


class ProductEmbeddingRepository(BaseRepository[ProductEmbedding]):
    """Repository for ProductEmbedding operations with vector search."""

    def __init__(self, session: AsyncSession):
        super().__init__(ProductEmbedding, session)

    async def search_by_similarity(
        self,
        query_embedding: List[float],
        limit: int = 5,
        category_filter: Optional[str] = None,
        include_inactive: bool = False,
        similarity_threshold: float = 0.0,
    ) -> List[Dict]:
        """
        Search products using cosine similarity with pgvector.

        Args:
            query_embedding: Query vector (1536 dimensions)
            limit: Maximum number of results to return
            category_filter: Optional category to filter by
            include_inactive: Whether to include inactive products
            similarity_threshold: Minimum similarity score (0-1)

        Returns:
            List of dicts with product info and similarity scores
        """
        # Build the SQL query with pgvector's cosine distance operator (<=>)
        # Cosine distance = 1 - cosine_similarity
        # So similarity = 1 - distance
        sql_query = """
            SELECT
                id,
                title,
                description,
                category,
                price,
                tags,
                url,
                image_url,
                1 - (embedding <=> :query_embedding) as similarity
            FROM product_embeddings
            WHERE 1=1
        """

        # Add filters
        params = {"query_embedding": str(query_embedding), "limit": limit}

        if not include_inactive:
            sql_query += " AND is_active = true"

        if category_filter:
            sql_query += " AND category = :category"
            params["category"] = category_filter

        # Order by similarity (highest first) and limit
        sql_query += " ORDER BY embedding <=> :query_embedding LIMIT :limit"

        # Execute the query with retry logic for concurrency issues
        max_retries = 3
        retry_delay = 0.1  # 100ms

        for attempt in range(max_retries):
            try:
                result = await self.session.execute(text(sql_query), params)
                rows = result.fetchall()
                break  # Success, exit retry loop
            except Exception as e:
                if "another operation is in progress" in str(e) and attempt < max_retries - 1:
                    logger.warning(
                        f"Database concurrency issue, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                else:
                    # Re-raise if it's not a concurrency issue or we've exhausted retries
                    raise

        # Process results
        results = []
        for row in rows:
            similarity = float(row.similarity)

            # Skip results below threshold
            if similarity < similarity_threshold:
                continue

            result_dict = {
                "id": row.id,
                "title": row.title,
                "description": row.description,
                "category": row.category,
                "price": row.price,
                "tags": row.tags,
                "url": row.url,
                "image_url": row.image_url,
                "similarity": round(similarity, 4),
                "is_ood": similarity < similarity_threshold,
            }

            results.append(result_dict)

        logger.debug(f"Found {len(results)} similar products")
        return results

    async def get_by_category(self, category: str, include_inactive: bool = False) -> List[ProductEmbedding]:
        """
        Get all products in a category.

        Args:
            category: Category name
            include_inactive: Whether to include inactive products

        Returns:
            List of products in the category
        """
        stmt = select(ProductEmbedding).where(ProductEmbedding.category == category)

        if not include_inactive:
            stmt = stmt.where(ProductEmbedding.is_active == True)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_products(self, limit: int = 100) -> List[ProductEmbedding]:
        """
        Get all active products.

        Args:
            limit: Maximum number of products to return

        Returns:
            List of active products
        """
        result = await self.session.execute(
            select(ProductEmbedding)
            .where(ProductEmbedding.is_active == True)
            .order_by(ProductEmbedding.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def deactivate(self, product: ProductEmbedding) -> None:
        """Mark product as inactive."""
        product.is_active = False
        await self.session.flush()

    async def activate(self, product: ProductEmbedding) -> None:
        """Mark product as active."""
        product.is_active = True
        await self.session.flush()

    async def update_embedding(self, product: ProductEmbedding, embedding: List[float]) -> None:
        """
        Update product embedding vector.

        Args:
            product: Product to update
            embedding: New embedding vector
        """
        product.embedding = embedding
        await self.session.flush()
