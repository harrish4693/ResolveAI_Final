from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime

class KnowledgeArticleBase(BaseModel):
    title: str
    content: str
    category: str
    tags: Optional[List[str]] = None
    is_active: bool = True

class KnowledgeArticleCreate(KnowledgeArticleBase):
    tenant_id: Optional[str] = None

class KnowledgeArticleUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None

class KnowledgeArticleOut(KnowledgeArticleBase):
    id: int
    tenant_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
