"""
Simplified CRUD operations with essential functionality only.
"""

from typing import Any, Dict, List, Optional, Type, TypeVar
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from ..exceptions import DatabaseError, RecordNotFoundError, DuplicateRecordError
from ..logging_config import get_logger
from ..models.base import Base

ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)

logger = get_logger(__name__, "crud")


class SimpleCRUD:
    """Simplified CRUD operations with essential functionality"""
    
    def __init__(self, model: Type[ModelType]):
        self.model = model
        self.model_name = model.__name__
    
    async def create(self, session: AsyncSession, obj_in: Dict[str, Any]) -> ModelType:
        """Create a new record"""
        try:
            db_obj = self.model(**obj_in)
            session.add(db_obj)
            await session.commit()
            await session.refresh(db_obj)
            
            logger.info(f"Created {self.model_name}", extra_fields={"id": getattr(db_obj, 'id', None)})
            return db_obj
            
        except IntegrityError as e:
            await session.rollback()
            logger.error(f"Integrity error creating {self.model_name}: {e}")
            raise DuplicateRecordError(f"Record already exists: {str(e)}")
        except Exception as e:
            await session.rollback()
            logger.error(f"Error creating {self.model_name}: {e}")
            raise DatabaseError(str(e))
    
    async def get(self, session: AsyncSession, id: Any, load_relations: List[str] = None) -> Optional[ModelType]:
        """Get record by ID"""
        try:
            query = select(self.model).where(self.model.id == id)
            
            if load_relations:
                for relation in load_relations:
                    if hasattr(self.model, relation):
                        query = query.options(selectinload(getattr(self.model, relation)))
            
            result = await session.execute(query)
            return result.scalar_one_or_none()
            
        except Exception as e:
            logger.error(f"Error getting {self.model_name} by ID {id}: {e}")
            raise DatabaseError(str(e))
    
    async def get_multi(
        self, 
        session: AsyncSession, 
        skip: int = 0, 
        limit: int = 100,
        filters: Dict[str, Any] = None,
        load_relations: List[str] = None
    ) -> List[ModelType]:
        """Get multiple records with optional filtering"""
        try:
            query = select(self.model)
            
            # Apply filters
            if filters:
                conditions = []
                for field_name, field_value in filters.items():
                    if hasattr(self.model, field_name):
                        field = getattr(self.model, field_name)
                        conditions.append(field == field_value)
                
                if conditions:
                    query = query.where(and_(*conditions))
            
            # Add relationship loading
            if load_relations:
                for relation in load_relations:
                    if hasattr(self.model, relation):
                        query = query.options(selectinload(getattr(self.model, relation)))
            
            # Apply pagination
            query = query.offset(skip).limit(limit)
            
            result = await session.execute(query)
            return result.scalars().all()
            
        except Exception as e:
            logger.error(f"Error getting multiple {self.model_name}: {e}")
            raise DatabaseError(str(e))
    
    async def update(self, session: AsyncSession, id: Any, obj_in: Dict[str, Any]) -> Optional[ModelType]:
        """Update record by ID"""
        try:
            db_obj = await self.get(session, id)
            if not db_obj:
                raise RecordNotFoundError(f"{self.model_name} with id {id} not found")
            
            for field, value in obj_in.items():
                if hasattr(db_obj, field):
                    setattr(db_obj, field, value)
            
            await session.commit()
            await session.refresh(db_obj)
            
            logger.info(f"Updated {self.model_name}", extra_fields={"id": id})
            return db_obj
            
        except RecordNotFoundError:
            raise
        except Exception as e:
            await session.rollback()
            logger.error(f"Error updating {self.model_name} with id {id}: {e}")
            raise DatabaseError(str(e))
    
    async def delete(self, session: AsyncSession, id: Any) -> bool:
        """Delete record by ID"""
        try:
            db_obj = await self.get(session, id)
            if not db_obj:
                return False
            
            await session.delete(db_obj)
            await session.commit()
            
            logger.info(f"Deleted {self.model_name}", extra_fields={"id": id})
            return True
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Error deleting {self.model_name} with id {id}: {e}")
            raise DatabaseError(str(e))
    
    async def count(self, session: AsyncSession, filters: Dict[str, Any] = None) -> int:
        """Count records with optional filtering"""
        try:
            query = select(func.count(self.model.id))
            
            if filters:
                conditions = []
                for field_name, field_value in filters.items():
                    if hasattr(self.model, field_name):
                        field = getattr(self.model, field_name)
                        conditions.append(field == field_value)
                
                if conditions:
                    query = query.where(and_(*conditions))
            
            result = await session.execute(query)
            return result.scalar()
            
        except Exception as e:
            logger.error(f"Error counting {self.model_name}: {e}")
            raise DatabaseError(str(e))
