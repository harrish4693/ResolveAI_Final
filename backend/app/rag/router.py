from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.database import get_db
from app.auth.deps import get_current_user
from app.users.models import User
from app.rag.models import KnowledgeArticle
from app.rag.schemas import KnowledgeArticleCreate, KnowledgeArticleUpdate, KnowledgeArticleOut
from app.rag.retriever import TFIDFRetriever, FAISSRetriever

router = APIRouter(tags=["Knowledge"])

@router.get("", response_model=List[KnowledgeArticleOut])
async def list_articles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all active knowledge articles for the current tenant.
    Internal knowledge articles are restricted to admins and experts.
    Customers receive an empty list to prevent exposure of internal SOPs and playbooks.
    """
    user_role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role).lower()
    if user_role not in ("admin", "expert"):
        return []

    result = await db.execute(select(KnowledgeArticle).where(
        KnowledgeArticle.is_active == True,
        KnowledgeArticle.tenant_id == current_user.tenant_id
    ))
    return result.scalars().all()

@router.post("", response_model=KnowledgeArticleOut)
async def create_article(
    data: KnowledgeArticleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new knowledge article."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can manage knowledge")
        
    if data.tenant_id and data.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Cannot create article for different tenant")
        
    create_data = data.model_dump()
    create_data["tenant_id"] = current_user.tenant_id
    
    article = KnowledgeArticle(**create_data)
    db.add(article)
    await db.commit()
    await db.refresh(article)
    
    # Invalidate RAG index so it lazily rebuilds on next search
    TFIDFRetriever.invalidate(article.tenant_id)
    FAISSRetriever.invalidate(article.tenant_id)
    
    return article

@router.put("/{article_id}", response_model=KnowledgeArticleOut)
async def update_article(
    article_id: int,
    data: KnowledgeArticleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a knowledge article."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can manage knowledge")
        
    result = await db.execute(select(KnowledgeArticle).where(
        KnowledgeArticle.id == article_id,
        KnowledgeArticle.tenant_id == current_user.tenant_id
    ))
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
        
    update_data = data.model_dump(exclude_unset=True)
    if "tenant_id" in update_data:
        del update_data["tenant_id"] # Immutable tenant_id
        
    for key, value in update_data.items():
        setattr(article, key, value)
        
    await db.commit()
    await db.refresh(article)
    
    # Invalidate RAG index so it lazily rebuilds on next search
    TFIDFRetriever.invalidate(article.tenant_id)
    FAISSRetriever.invalidate(article.tenant_id)
    
    return article
