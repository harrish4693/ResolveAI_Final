import asyncio
import re
import os
import sys

from app.database import engine, async_session_factory, Base
from app.rag.models import KnowledgeArticle
from sqlalchemy import select

def parse_knowledge_library(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    articles = []
    parts = re.split(r'^###\s+', content, flags=re.MULTILINE)
    
    for part in parts[1:]:
        lines = part.strip().split('\n')
        if not lines:
            continue
            
        title_line = lines[0].strip()
        title = title_line
        
        category = "UNCATEGORIZED"
        tags = []
        
        content_lines = []
        for line in lines[1:]:
            category_match = re.search(r'\*\*Category:\*\*\s*([^|]+)', line, re.IGNORECASE)
            tags_match = re.search(r'\*\*Tags:\*\*\s*(.+)', line, re.IGNORECASE)
            
            if category_match or tags_match:
                if category_match:
                    category = category_match.group(1).strip().upper().replace(' ', '_')
                if tags_match:
                    tags = [t.strip() for t in tags_match.group(1).split(',')]
            else:
                content_lines.append(line)
                
        article_content = '\n'.join(content_lines).strip()
        
        articles.append({
            "title": title,
            "content": article_content,
            "category": category,
            "tags": tags,
            "is_active": True,
            "tenant_id": "default"
        })
        
    return articles

async def seed_knowledge():
    print("Seeding knowledge base...")
    
    docs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs", "KNOWLEDGE_LIBRARY.md"))
    articles_data = parse_knowledge_library(docs_path)
    
    # Implementing tenant_b mock articles as requested by Rule 7
    tenant_b_articles = [
        {
            "title": "POL-B01 — Tenant B Custom Policy",
            "content": "This is a custom policy for tenant B. Standard return window is 90 days. [CORE]",
            "category": "SERVICE_STANDARDS",
            "tags": ["tenant_b", "returns"],
            "is_active": True,
            "tenant_id": "tenant_b"
        },
        {
            "title": "TS-B01 — Tenant B Troubleshooting",
            "content": "If the tenant B device fails, hit it with a small hammer. [EXT]",
            "category": "TROUBLESHOOTING",
            "tags": ["tenant_b", "troubleshooting", "hammer"],
            "is_active": True,
            "tenant_id": "tenant_b"
        }
    ]
    articles_data.extend(tenant_b_articles)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async with async_session_factory() as session:
        for article_data in articles_data:
            stmt = select(KnowledgeArticle).where(
                KnowledgeArticle.title == article_data["title"],
                KnowledgeArticle.tenant_id == article_data["tenant_id"]
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                print(f"Article already exists: {article_data['title']} (Tenant: {article_data['tenant_id']})")
                existing.content = article_data["content"]
                existing.category = article_data["category"]
                existing.tags = article_data["tags"]
            else:
                print(f"Creating article: {article_data['title']} (Tenant: {article_data['tenant_id']})")
                article = KnowledgeArticle(**article_data)
                session.add(article)
                
        await session.commit()
        
    print(f"Knowledge base seeding complete. Total articles processed: {len(articles_data)}")

if __name__ == "__main__":
    asyncio.run(seed_knowledge())
