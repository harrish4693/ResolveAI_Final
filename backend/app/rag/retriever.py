from abc import ABC, abstractmethod
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

import os
import json
import re
import faiss
import tiktoken
from openai import AsyncOpenAI, APIConnectionError, RateLimitError, APITimeoutError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.rag.models import KnowledgeArticle
from app.config import settings

class Retriever(ABC):
    @abstractmethod
    async def search(self, query: str, db: AsyncSession, top_k: int = 3, tenant_id: str = "default") -> Dict[str, Any]:
        pass

class TFIDFRetriever(Retriever):
    """
    Lightweight TF-IDF retriever for M4 prototype.
    Builds the index per tenant and caches it. Refreshed via refresh().
    """
    _vectorizers = {}
    _tfidf_matrices = {}
    _articles_by_tenant = {}
    _built_tenants = set()

    @classmethod
    def invalidate(cls, tenant_id: str):
        if tenant_id in cls._built_tenants:
            cls._built_tenants.remove(tenant_id)
        if tenant_id in cls._vectorizers:
            del cls._vectorizers[tenant_id]
        if tenant_id in cls._tfidf_matrices:
            del cls._tfidf_matrices[tenant_id]
        if tenant_id in cls._articles_by_tenant:
            del cls._articles_by_tenant[tenant_id]

    @classmethod
    async def refresh(cls, db: AsyncSession, tenant_id: str = "default"):
        """Rebuild the index from the database for a specific tenant."""
        result = await db.execute(select(KnowledgeArticle).where(
            KnowledgeArticle.is_active == True,
            KnowledgeArticle.tenant_id == tenant_id
        ))
        articles = result.scalars().all()
        
        cls._articles_by_tenant[tenant_id] = articles
        
        if not articles:
            if tenant_id in cls._built_tenants:
                cls._built_tenants.remove(tenant_id)
            return
            
        corpus = [f"{a.title} {a.content}" for a in articles]
        vectorizer = TfidfVectorizer(stop_words='english')
        try:
            matrix = vectorizer.fit_transform(corpus)
            cls._vectorizers[tenant_id] = vectorizer
            cls._tfidf_matrices[tenant_id] = matrix
            cls._built_tenants.add(tenant_id)
        except ValueError:
            if tenant_id in cls._built_tenants:
                cls._built_tenants.remove(tenant_id)

    async def search(self, query: str, db: AsyncSession, top_k: int = 3, tenant_id: str = "default") -> Dict[str, Any]:
        if not tenant_id:
            return {"status": "RAG_EMPTY", "results": []}

        # If not built yet for this tenant, build it once
        if tenant_id not in self.__class__._built_tenants:
            await self.__class__.refresh(db, tenant_id)
            
        if tenant_id not in self.__class__._built_tenants or not self.__class__._articles_by_tenant.get(tenant_id):
            return {"status": "RAG_EMPTY", "results": []}
            
        try:
            vectorizer = self.__class__._vectorizers[tenant_id]
            matrix = self.__class__._tfidf_matrices[tenant_id]
            articles = self.__class__._articles_by_tenant[tenant_id]

            effective_query = query
            has_indic = any(ord(c) >= 0x0600 and ord(c) <= 0x0D7F for c in query)
            words = set(re.findall(r'\b\w+\b', query.lower()))
            indic_markers = {
                "varala", "varave", "innum", "aagala", "reach", "panniten", "pannala", "vandhuduchu", "kedaikala", "illa", "seri",
                "raledu", "raaledu", "inka", "kaledu", "chesanu", "cheyaledu", "vachindi", "dabbu",
                "bandilla", "innu", "aagilla", "maadiddini", "madilla", "banthu", "duddu",
                "vannilla", "ithuvare", "aayilla", "cheythu", "cheythilla", "vannu", "paisa",
                "asheni", "ekhono", "hoyni", "korechi", "korini", "peyechi", "taka",
                "aala", "ajun", "zala", "kela", "milaala", "paise", "saanga",
                "aavyo", "haji", "thayu", "didhu", "malyo", "rupia", "nathi",
                "aaya", "aje", "hoya", "ditta", "kita", "dasso", "nahi"
            }
            if has_indic or bool(words & indic_markers):
                try:
                    from app.ai.intelligence.multilingual_engine import multilingual_service
                    understanding = multilingual_service.understand(query, tenant_id=tenant_id)
                    if understanding.normalized_search_query:
                        effective_query = f"{query} {understanding.normalized_meaning} {understanding.normalized_search_query}"
                except Exception:
                    pass

            query_vec = vectorizer.transform([effective_query])
            similarities = cosine_similarity(query_vec, matrix).flatten()
            
            # Sort by highest similarity
            top_indices = np.argsort(similarities)[::-1]
            
            results = []
            for idx in top_indices[:top_k]:
                score = similarities[idx]
                if score > 0.05: # Arbitrary threshold to ignore completely unrelated docs
                    article = articles[idx]
                    results.append({
                        "id": article.id,
                        "title": article.title,
                        "content": article.content,
                        "category": article.category,
                        "score": float(score)
                    })
            if results:
                return {"status": "RAG_SUCCESS", "results": results}
            return {"status": "RAG_EMPTY", "results": []}
        except ValueError:
            return {"status": "RAG_EMPTY", "results": []}

class FAISSRetriever(Retriever):
    """
    Production retriever using FAISS and OpenAI embeddings.
    Multi-tenant isolation via separate indexes per tenant.
    """
    _indexes = {}
    _chunk_metadata_by_tenant = {}
    _built_tenants = set()

    @classmethod
    def invalidate(cls, tenant_id: str):
        """Invalidate a tenant's index so it will be lazily rebuilt on next search."""
        if tenant_id in cls._built_tenants:
            cls._built_tenants.remove(tenant_id)
        if tenant_id in cls._indexes:
            del cls._indexes[tenant_id]
        if tenant_id in cls._chunk_metadata_by_tenant:
            del cls._chunk_metadata_by_tenant[tenant_id]

    @classmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((APIConnectionError, RateLimitError, APITimeoutError))
    )
    async def _get_embeddings(cls, texts: List[str]) -> List[List[float]]:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.embeddings.create(
            input=texts,
            model="text-embedding-3-small"
        )
        return [data.embedding for data in response.data]

    @classmethod
    def _chunk_text(cls, text: str, max_tokens: int = 500) -> List[str]:
        enc = tiktoken.get_encoding("cl100k_base")
        tokens = enc.encode(text)
        chunks = []
        for i in range(0, len(tokens), max_tokens):
            chunk = enc.decode(tokens[i:i+max_tokens])
            chunks.append(chunk)
        return chunks

    @classmethod
    async def refresh(cls, db: AsyncSession, tenant_id: str = "default"):
        """Rebuild the index from canonical KB data for a specific tenant."""
        if not settings.openai_api_key:
            return

        result = await db.execute(select(KnowledgeArticle).where(
            KnowledgeArticle.is_active == True,
            KnowledgeArticle.tenant_id == tenant_id
        ))
        articles = result.scalars().all()
        
        if not articles:
            if tenant_id in cls._built_tenants:
                cls._built_tenants.remove(tenant_id)
            return

        index = faiss.IndexFlatL2(1536)
        chunk_metadata = {}
        
        chunks = []
        metadata_list = []
        chunk_id = 0
        
        for article in articles:
            article_chunks = cls._chunk_text(article.content)
            for i, c in enumerate(article_chunks):
                chunks.append(f"{article.title}\n\n{c}")
                metadata_list.append({
                    "chunk_id": chunk_id,
                    "article_id": article.id,
                    "title": article.title,
                    "category": article.category,
                    "chunk_index": i,
                    "content": c
                })
                chunk_id += 1
                
        if not chunks:
            if tenant_id in cls._built_tenants:
                cls._built_tenants.remove(tenant_id)
            return
            
        # Batch get embeddings
        embeddings = []
        for i in range(0, len(chunks), 100):
            batch = chunks[i:i+100]
            emb = await cls._get_embeddings(batch)
            embeddings.extend(emb)
            
        emb_matrix = np.array(embeddings).astype('float32')
        index.add(emb_matrix)
        
        for i, meta in enumerate(metadata_list):
            chunk_metadata[i] = meta
            
        cls._indexes[tenant_id] = index
        cls._chunk_metadata_by_tenant[tenant_id] = chunk_metadata
        cls._built_tenants.add(tenant_id)

    async def search(self, query: str, db: AsyncSession, top_k: int = 3, tenant_id: str = "default") -> Dict[str, Any]:
        if not settings.openai_api_key:
            return {"status": "RAG_PROVIDER_FAILURE", "results": []}

        if not tenant_id:
            return {"status": "RAG_EMPTY", "results": []}
            
        if tenant_id not in self.__class__._built_tenants:
            try:
                await self.__class__.refresh(db, tenant_id)
            except Exception as e:
                print(f"Exception in refresh: {e}")
                return {"status": "RAG_PROVIDER_FAILURE", "results": []}
                
        if tenant_id not in self.__class__._built_tenants:
            return {"status": "RAG_EMPTY", "results": []}
            
        try:
            effective_query = query
            has_indic = any(ord(c) >= 0x0600 and ord(c) <= 0x0D7F for c in query)
            words = set(re.findall(r'\b\w+\b', query.lower()))
            indic_markers = {
                "varala", "varave", "innum", "aagala", "reach", "panniten", "pannala", "vandhuduchu", "kedaikala", "illa", "seri",
                "raledu", "raaledu", "inka", "kaledu", "chesanu", "cheyaledu", "vachindi", "dabbu",
                "bandilla", "innu", "aagilla", "maadiddini", "madilla", "banthu", "duddu",
                "vannilla", "ithuvare", "aayilla", "cheythu", "cheythilla", "vannu", "paisa",
                "asheni", "ekhono", "hoyni", "korechi", "korini", "peyechi", "taka",
                "aala", "ajun", "zala", "kela", "milaala", "paise", "saanga",
                "aavyo", "haji", "thayu", "didhu", "malyo", "rupia", "nathi",
                "aaya", "aje", "hoya", "ditta", "kita", "dasso", "nahi"
            }
            if has_indic or bool(words & indic_markers):
                try:
                    from app.ai.intelligence.multilingual_engine import multilingual_service
                    understanding = multilingual_service.understand(query, tenant_id=tenant_id)
                    if understanding.normalized_search_query:
                        effective_query = f"{query} {understanding.normalized_meaning} {understanding.normalized_search_query}"
                except Exception:
                    pass

            query_emb = await self.__class__._get_embeddings([effective_query])
            query_matrix = np.array(query_emb).astype('float32')
            
            index = self.__class__._indexes[tenant_id]
            metadata = self.__class__._chunk_metadata_by_tenant[tenant_id]

            distances, indices = index.search(query_matrix, top_k)
            
            results = []
            for i, idx in enumerate(indices[0]):
                if idx != -1 and idx in metadata:
                    results.append(metadata[idx])
                    
            if results:
                return {"status": "RAG_SUCCESS", "results": results}
            else:
                return {"status": "RAG_EMPTY", "results": []}
        except Exception as e:
            print(f"Exception in search: {e}")
            return {"status": "RAG_PROVIDER_FAILURE", "results": []}
