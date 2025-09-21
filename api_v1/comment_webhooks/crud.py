# from sqlalchemy import select
# from sqlalchemy.engine import Result
# from sqlalchemy.ext.asyncio import AsyncSession

# from core.models import Product

# from .schemas import 

# async def create_comment(session: AsyncSession, product_in: ProductCreate) -> Product:
#     product = Product(**product_in.model_dump())
#     session.add(product)
#     await session.commit()
#     # await session.refresh(product)
#     return product