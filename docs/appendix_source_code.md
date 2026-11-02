# APPENDIX A — SOURCE CODE

This appendix contains verified source code excerpts extracted directly from the **ResolveAI V2** production codebase. ResolveAI V2 is an Agentic Multilingual Customer Support Platform engineered with FastAPI, SQLAlchemy (Asyncio), FAISS vector retrieval, and custom multi-agent intelligence controllers supporting English, Tamil, Tanglish, Hindi, and Hinglish.

---

## A.1 User Authentication and Authorization

### Source File
`backend/app/auth/deps.py` (Lines 25–60)

```python
async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> User:
    """Dependency: Extract and verify user from JWT access token."""
    try:
        payload = verify_token(token, expected_type="access")
        user_id = int(payload.get("sub"))
    except Exception as e:
        raise AuthenticationError(f"Could not validate credentials: {str(e)}")

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise AuthenticationError("User not found")
    if not user.is_active:
        raise AuthenticationError("Inactive user")

    return user


def require_role(allowed_roles: list[UserRole]):
    """Dependency factory: Enforce role-based access control."""
    async def role_checker(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role not in allowed_roles:
            raise ForbiddenError(f"Operation requires one of roles: {', '.join(allowed_roles)}")
        return current_user
    return role_checker


# Convenience dependencies
require_customer = require_role([UserRole.CUSTOMER, UserRole.ADMIN])
require_expert = require_role([UserRole.EXPERT, UserRole.ADMIN])
require_admin = require_role([UserRole.ADMIN])
```

### Explanation
This component implements token-based authentication and Role-Based Access Control (RBAC) across API endpoints. The `get_current_user` dependency decodes and cryptographically verifies incoming JWT access tokens, validates user activity in PostgreSQL, and yields the authenticated `User` model. The `require_role` higher-order function constructs reusable FastAPI guards ensuring strict endpoint authorization for customers, human support experts, and administrators.

### Related Test Case
`backend/tests/test_auth.py` (`test_jwt_access_token_generation_and_verification`, `test_role_based_access_control`)

---

## A.2 Customer Conversation and Message Processing

### Source File
`backend/app/conversations/service.py` (Lines 166–216)

```python
    async def process_customer_message(
        self, db: AsyncSession, conversation: Conversation, customer_id: int, message_content: str,
        tts_callback = None,
        reply_with_voice: bool = False,
    ):
        """Processes an incoming customer message on an existing conversation."""
        # 1. Add customer message
        customer_msg = await MessageService.create_message(
            db=db,
            conversation_id=conversation.id,
            sender_type=SenderType.CUSTOMER,
            content=message_content,
            sender_id=customer_id,
        )

        # 2. Broadcast customer message to any assigned expert
        handoff = await db.scalar(
            select(Handoff).where(
                Handoff.conversation_id == conversation.id,
            )
        )
        expert_user_id = None
        if handoff and handoff.assigned_expert_id:
            expert_rec = await db.scalar(select(Expert).where(Expert.id == handoff.assigned_expert_id))
            if expert_rec:
                expert_user_id = expert_rec.user_id

        await manager.send_to_conversation_participants(
            customer_id=customer_id,
            expert_id=expert_user_id,
            event=new_message_event(
                conversation_id=conversation.id,
                message_id=customer_msg.id,
                sender_type=customer_msg.sender_type.value if hasattr(customer_msg.sender_type, 'value') else str(customer_msg.sender_type),
                content=customer_msg.content,
                created_at=customer_msg.created_at.isoformat(),
                message_type=customer_msg.message_type.value if hasattr(customer_msg.message_type, 'value') else str(customer_msg.message_type),
                audio_url=customer_msg.audio_url,
            ),
        )

        # 3. Broadcast typing indicator
        await manager.send_to_user(
            customer_id,
            typing_event(conversation.id, "ai", is_start=True),
        )

        # 4. Trigger turn execution and AI response generation
        return await self._trigger_ai_response(
            db=db,
            conversation=conversation,
            latest_message=message_content,
            tts_callback=tts_callback,
            reply_with_voice=reply_with_voice,
        )
```

### Explanation
This method coordinates incoming customer support interactions across text and voice channels. It commits the incoming message using an asynchronous database transaction, notifies active websocket participants (including assigned human experts), and broadcasts typing status indicators. Finally, it invokes `_trigger_ai_response` to run intent classification, memory retrieval, policy-grounded RAG, and safety validation.

### Related Test Case
`backend/tests/test_conversations_api.py` (`test_customer_message_submission_and_ai_turn`)

---

## A.3 Multilingual and Code-Mixed Language Processing

### Source File
`backend/app/ai/intelligence/language.py` (Lines 516–570, 1006–1035)

```python
    def detect(self, text: str, contextual_preference: Optional[str] = None) -> LanguageDetectionResult:
        """
        Detect code-mixed languages and script types across pan-Indian languages.
        """
        result = LanguageDetectionResult()
        text_lower = text.lower()

        # Check for native scripts
        scripts = self._detect_scripts(text)
        result.script_types = scripts

        # Count markers for core languages
        tanglish_count = self._count_markers(text_lower, self.TANGLISH_MARKERS)
        hinglish_count = self._count_markers(text_lower, self.HINGLISH_MARKERS)
        telugu_count = self._count_markers(text_lower, self.TELUGU_MARKERS)
        kannada_count = self._count_markers(text_lower, self.KANNADA_MARKERS)
        english_word_count = self._count_english_words(text_lower)

        has_tamil_script = "tamil" in scripts
        has_devanagari = "devanagari" in scripts
        has_latin = "latin" in scripts

        # Script-aware classification
        if has_tamil_script:
            result.primary_language = "ta"
            if has_latin:
                result.mixed_with = ["en"]
                result.is_code_mixed = True
                result.code_mix_type = "tanglish"
                result.confidence = 0.96
            else:
                result.code_mix_type = "tamil"
                result.confidence = 0.98
        elif has_devanagari:
            result.primary_language = "hi"
            if has_latin:
                result.mixed_with = ["en"]
                result.is_code_mixed = True
                result.code_mix_type = "hinglish"
                result.confidence = 0.96
            else:
                result.code_mix_type = "hindi"
                result.confidence = 0.98
        elif tanglish_count > hinglish_count and tanglish_count > 0:
            result.primary_language = "ta"
            result.is_code_mixed = True
            result.code_mix_type = "tanglish"
            result.confidence = min(0.60 + 0.10 * tanglish_count, 0.98)
        elif hinglish_count > 0:
            result.primary_language = "hi"
            result.is_code_mixed = True
            result.code_mix_type = "hinglish"
            result.confidence = min(0.60 + 0.10 * hinglish_count, 0.98)

        return result


    def detect_negation(self, text: str) -> bool:
        """
        Accurately identifies negative statements across Tamil/Tanglish, Hindi/Hinglish, and English.
        Crucially prevents mistaking 'not working / not opening' for positive actions.
        """
        t = f" {text.lower()} "

        # Tamil / Tanglish negation markers
        tamil_negations = [
            r"\baagala\b", r"\baagave\s+illa\b", r"\billa\b", r"\billai\b",
            r"\bvarala\b", r"\bvarave\s+illa\b", r"\bmudiyala\b", r"\bpanna\s+mudiyala\b",
            r"\bkedakkala\b", r"\bkedaikala\b", r"\btheriyala\b", r"\bpuriyala\b",
            r"\bopen\s+aagala\b", r"\bwork\s+aagala\b", r"இல்லை", r"ஆகவில்லை", r"வரவில்லை"
        ]

        # Hindi / Hinglish negation markers
        hindi_negations = [
            r"\bnahi\b", r"\bnahi\s+hua\b", r"\bnahi\s+ho\s+raha\b", r"\bnahi\s+chal\s+raha\b",
            r"\bnahi\s+khul\s+raha\b", r"\bnahi\s+aaya\b", r"\bnahi\s+mila\b", r"नहीं", r"ना"
        ]

        for pattern in tamil_negations + hindi_negations:
            if re.search(pattern, t):
                return True
        return False
```

### Explanation
This intelligence module identifies colloquial and code-mixed Indian language input (such as Romanized Tanglish and Hinglish) alongside native Indic scripts (Tamil, Devanagari). It combines Unicode script boundary analysis with colloquial vocabulary dictionaries to prevent dialect misclassification. Furthermore, `detect_negation` ensures critical conversational polarity is maintained so that complaints like *"App open aagala"* are not misinterpreted as successful operations.

### Related Test Case
`backend/tests/test_intelligence.py` (`TestCodeMixedLanguageDetector.test_tanglish_romanized`, `TestCodeMixedLanguageDetector.test_hinglish_romanized`)

---

## A.4 Knowledge Retrieval and FAISS RAG

### Source File
`backend/app/rag/retriever.py` (Lines 179–230, 278–294)

```python
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
        # Semantic embedding and vector similarity search
        query_emb = await self.__class__._get_embeddings([query])
        query_matrix = np.array(query_emb).astype('float32')
        
        index = self.__class__._indexes[tenant_id]
        metadata = self.__class__._chunk_metadata_by_tenant[tenant_id]

        distances, indices = index.search(query_matrix, top_k)
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx != -1 and idx in metadata:
                results.append(metadata[idx])
                
        return {"status": "RAG_SUCCESS" if results else "RAG_EMPTY", "results": results}
```

### Explanation
This subsystem provides dense vector retrieval over support documentation using Facebook AI Similarity Search (FAISS). Knowledge articles are partitioned by `tenant_id` to guarantee cross-tenant data isolation, chunked with `tiktoken`, and indexed into dense 1536-dimensional L2 Euclidean distance spaces (`faiss.IndexFlatL2`). During live customer turns, semantic vector search retrieves the most pertinent policy chunks to ground the model's responses.

### Related Test Case
`backend/tests/test_rag_retrieval_and_isolation.py` (`test_schema_create_tenant_ownership`, `test_crud_isolation_read`)

---

## A.5 Adaptive Resolution Decision Engine

### Source File
`backend/app/ai/m4/decision.py` (Lines 4–46, 82–96)

```python
class DecisionEngine:
    def decide(
        self, 
        analysis: Dict[str, Any], 
        retrieved_articles: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Returns a structured decision: RESOLVE, ASK_USER, ESCALATE, USE_TOOL.
        """
        priority = str(analysis.get("priority", "LOW")).upper()
        intent = str(analysis.get("intent", "GENERAL_QUERY")).upper()
        entities = analysis.get("entities", {})
        orig_msg = str(analysis.get("original_message", "")).lower()
        from app.ai.intelligence.escalation_keywords import is_supervisor_demand, is_fraud_or_security

        # 0. Check for explicit human / expert escalation request (Highest Priority)
        if intent in ["ESCALATION_REQUEST"] or is_supervisor_demand(orig_msg):
            return {
                "decision": "ESCALATE",
                "reason": "Customer explicitly requested human expert"
            }
        
        # 1. Check for immediate escalation based on priority, fraud keywords, or security intent
        if priority in ["CRITICAL"] or intent in ["SECURITY_ISSUE", "FRAUD_SUSPICION"] or is_fraud_or_security(orig_msg):
            return {
                "decision": "ESCALATE",
                "reason": "Security-sensitive fraud or risk issue requires human intervention"
            }

        # 1.5 Conversational function handling (Acknowledgments & Emotional Reactions)
        conv_fn = analysis.get("conversational_function", "")
        if intent == "ACKNOWLEDGMENT" or conv_fn == "ACKNOWLEDGMENT":
            return {
                "decision": "RESOLVE",
                "reason": "Customer acknowledged previous answer",
                "action_type": "acknowledgment_closing"
            }

        # 1.6 Deterministic Tool Dispatch
        if "order_id" in entities and intent in ("ORDER_STATUS", "DELIVERY_ISSUE"):
            return {
                "decision": "USE_TOOL",
                "tool_name": "get_order_status",
                "tool_args": {"order_id": entities["order_id"]},
                "reason": "Customer provided Order ID for order status lookup"
            }

        # 2. Check for missing required information based on intent
        if intent in ("ORDER_STATUS", "DELIVERY_ISSUE") and "order_id" not in entities:
            return {
                "decision": "ASK_USER",
                "reason": "Order ID required for delivery tracking",
                "missing_entity": "order_id"
            }

        # Default resolution grounded in knowledge base
        return {
            "decision": "RESOLVE",
            "reason": "Answered query using grounded knowledge base article",
            "article": retrieved_articles[0] if retrieved_articles else None
        }
```

### Explanation
The decision engine evaluates the multi-dimensional analysis of a turn (intent, priority, entities, and security triggers) to govern agent workflow behavior. It enforces immediate escalation (`ESCALATE`) upon detecting security risks, fraud keywords, or supervisor requests, halts execution to request missing entities (`ASK_USER`), automatically routes verified IDs to database tools (`USE_TOOL`), and delivers factual answers grounded in retrieved knowledge articles (`RESOLVE`).

### Related Test Case
`backend/tests/test_autonomy_and_escalation.py` (`test_security_always_escalates`, `test_missing_entity_asks_user`)

---

## A.6 Expert Handoff and Ticket Management

### Source File
`backend/app/handoff/service.py` (Lines 87–134)

```python
    @classmethod
    async def create_or_update_handoff(
        cls,
        db: AsyncSession,
        conversation: Conversation,
        analysis: Dict[str, Any],
        ticket: Optional[Ticket] = None,
        reason: Optional[str] = None,
    ) -> Tuple[Handoff, bool]:
        """
        Creates or updates a Handoff record for an escalated conversation.
        Guarantees idempotency (never creates duplicate handoffs for the same conversation).
        Sets conversation state to WAITING_FOR_EXPERT and updates linked ticket.
        Returns: (handoff, is_new)
        """
        # 1. Update Conversation workflow state immediately
        conversation.workflow_state = WorkflowState.WAITING_FOR_EXPERT

        # 2. Update linked ticket if available, or fetch it
        if not ticket:
            ticket = await db.scalar(select(Ticket).where(Ticket.conversation_id == conversation.id))
        if ticket:
            ticket.status = TicketStatus.ESCALATED

        # 3. Derive classification and priority
        intent = str(analysis.get("intent", "GENERAL_QUERY")).upper()
        category = cls.INTENT_CATEGORY_MAPPING.get(intent, "General Support")
        priority = cls._normalize_priority(analysis.get("priority", Priority.MEDIUM))

        escalation_reason = (
            reason
            or analysis.get("decision_reason")
            or "Customer requested human expert or automated escalation threshold reached"
        )

        # 4. Check for existing Handoff on this conversation
        existing_handoff = await db.scalar(
            select(Handoff).where(Handoff.conversation_id == conversation.id)
        )

        if existing_handoff:
            existing_handoff.escalation_reason = escalation_reason
            existing_handoff.priority = priority
            existing_handoff.category = category
            existing_handoff.status = HandoffStatus.WAITING
            await db.commit()
            return existing_handoff, False

        # 5. Insert new Handoff record
        new_handoff = Handoff(
            conversation_id=conversation.id,
            priority=priority,
            category=category,
            escalation_reason=escalation_reason,
            status=HandoffStatus.WAITING,
            ai_analysis=analysis,
            collected_information=analysis.get("entities", {})
        )
        db.add(new_handoff)
        await db.commit()
        await db.refresh(new_handoff)
        return new_handoff, True
```

### Explanation
This service manages the transition lifecycle when moving conversations from automated AI processing to human support agents. It atomically synchronizes conversation workflow states to `WAITING_FOR_EXPERT`, updates linked support tickets to `ESCALATED`, and persists structured diagnostics (extracted entities, intent categorization, and root causes). Idempotent design safeguards against duplicate handoff records across rapid message bursts.

### Related Test Case
`backend/tests/test_expert_handoff.py` (`test_handoff_creation_and_expert_assignment`, `test_expert_chat_realtime_sync`)

---

## A.7 Cross-Ticket Incident Detection and Clustering

### Source File
`backend/app/ai/intelligence/incidents.py` (Lines 425–480, 502–540)

```python
    def detect_spike(
        self,
        tickets: List[TicketSnapshot],
        baseline_hours: float = 24.0,
        current_hours: float = 2.0,
        spike_ratio_threshold: float = 2.5,
    ) -> Dict[str, Any]:
        """
        Detect unusual complaint spikes using real timestamps against a defined baseline.
        """
        valid_tickets = [t for t in tickets if t.created_at is not None]
        if len(valid_tickets) < 5:
            return {"is_spike": False, "reason": "insufficient_data"}

        sorted_tickets = sorted(valid_tickets, key=lambda t: t.created_at)
        max_time = sorted_tickets[-1].created_at
        cutoff = max_time - timedelta(hours=current_hours)
        baseline_start = max_time - timedelta(hours=current_hours + baseline_hours)

        current_window = [t for t in valid_tickets if t.created_at >= cutoff]
        baseline_window = [t for t in valid_tickets if baseline_start <= t.created_at < cutoff]

        baseline_rate = len(baseline_window) / max(baseline_hours, 1.0)
        current_rate = len(current_window) / max(current_hours, 0.5)

        spike_ratio = current_rate / max(baseline_rate, 0.1)
        is_spike = bool(spike_ratio >= spike_ratio_threshold and len(current_window) >= 3)

        return {
            "is_spike": is_spike,
            "spike_ratio": round(spike_ratio, 2),
            "current_count": len(current_window),
            "baseline_count": len(baseline_window),
        }

    def detect_incidents(
        self,
        tickets: List[TicketSnapshot],
        tenant_id: str = "default",
    ) -> List[IncidentHypothesis]:
        """Analyze tickets using graph clustering to discover root-cause incident hypotheses."""
        tenant_tickets = [t for t in tickets if t.tenant_id == tenant_id]
        if len(tenant_tickets) < self.MIN_CLUSTER_SIZE:
            return []

        # Build similarity scores across tickets
        similarities = []
        for i, ticket_a in enumerate(tenant_tickets):
            for j, ticket_b in enumerate(tenant_tickets):
                if i >= j:
                    continue
                sim = self.analyzer.compute_similarity(ticket_a, ticket_b)
                if sim.overall >= self.SIMILARITY_THRESHOLD:
                    similarities.append(sim)

        # Graph connected-component clustering
        clusters = self._cluster_tickets(similarities, tenant_tickets)
        hypotheses = []
        for idx, cluster in enumerate(clusters):
            if len(cluster) >= self.MIN_CLUSTER_SIZE:
                hypotheses.append(self._generate_hypothesis(idx, cluster, tenant_tickets))

        return hypotheses
```

### Explanation
This analytical component discovers systemic operational outages (such as regional payment gateway downtime) by evaluating cross-ticket correlations. It monitors real-time complaint arrival rates against trailing baseline windows to identify statistically significant volume spikes. Connected-component graph clustering links tickets sharing high semantic similarity, temporal proximity, and categorical equivalence into cohesive incident hypotheses.

### Related Test Case
`backend/tests/test_incident_intelligence.py` (`test_incident_clustering_algorithm`, `test_complaint_spike_detection`)

---

## A.8 Voice Input and Speech Processing

### Source File
`backend/app/voice/livekit_service.py` (Lines 180–232)

```python
    @classmethod
    async def process_spoken_utterance(
        cls,
        db: AsyncSession,
        conversation_id: int,
        customer_id: int,
        utterance_id: str,
        transcript: str,
        tts_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Processes a spoken audio utterance with validation and database idempotency."""
        # 1. Validation and noise filtering
        val_result = validate_spoken_utterance(transcript)
        if not val_result.is_valid:
            return {
                "status": "ignored",
                "reason": val_result.reason,
                "utterance_id": utterance_id,
                "conversation_id": conversation_id,
                "message": f"Utterance ignored: {val_result.reason}",
            }
        clean_transcript = val_result.cleaned_text

        # 2. Database idempotency check (reject replay attacks and duplicate audio packets)
        existing = await db.scalar(
            select(ProcessedUtterance).where(
                ProcessedUtterance.utterance_id == utterance_id,
                ProcessedUtterance.customer_id == customer_id,
                ProcessedUtterance.conversation_id == conversation_id,
            )
        )
        if existing:
            return {
                "status": "duplicate",
                "utterance_id": utterance_id,
                "conversation_id": conversation_id,
                "message": "Duplicate utterance already processed",
            }

        # 3. Record utterance idempotency key
        record = ProcessedUtterance(
            utterance_id=utterance_id,
            customer_id=customer_id,
            conversation_id=conversation_id,
        )
        db.add(record)
        await db.commit()

        # 4. Dispatch turn to conversation pipeline
        svc = ConversationService()
        await svc.process_customer_message(
            db=db,
            conversation=convo,
            customer_id=customer_id,
            message_content=clean_transcript,
            tts_callback=tts_callback,
            reply_with_voice=True,
        )

        await db.refresh(convo)
        return {"status": "processed", "utterance_id": utterance_id, "conversation_id": conversation_id}
```

### Explanation
This module handles real-time voice sessions using LiveKit audio streaming protocols. Spoken utterances received from client audio tracks undergo hallucination and noise filtering (`validate_spoken_utterance`) before persisting in an idempotency table (`ProcessedUtterance`) to prevent duplicate execution during network retries. Cleaned transcripts are dispatched to the conversational core with bidirectional text-to-speech (TTS) streaming callbacks.

### Related Test Case
`backend/tests/test_livekit_voice_pipeline.py` (`test_livekit_utterance_flow`, `test_voice_idempotency_duplicate_rejection`)

---

## A.9 Error Handling and Security Guardrails

### Source File
`backend/app/ai/validation/service.py` (Lines 33–79, 97–117)

```python
class ValidationService:
    @classmethod
    async def validate_response(cls, ctx: ResponseValidationContext) -> ValidationResult:
        """Executes a 9-layer sequential validation pipeline on proposed AI responses."""
        final_result = ValidationResult(status=ValidationStatus.VALID)
        
        # Layer 1: Structural check (empty output, markdown breakage)
        struct_res = check_structural(ctx)
        cls._merge_result(final_result, struct_res)
        if final_result.status == ValidationStatus.ESCALATE: 
            return final_result
        
        # Layer 2: Security check (PII leaks, credential exposure)
        sec_res = check_security(ctx)
        cls._merge_result(final_result, sec_res)
        if final_result.status == ValidationStatus.ESCALATE: 
            return final_result
        
        # Layer 3: Tool truthfulness check (invented order/tracking numbers)
        tool_res = check_tool_truthfulness(ctx)
        cls._merge_result(final_result, tool_res)
        if final_result.status == ValidationStatus.ESCALATE: 
            return final_result
        
        # Layer 4: Action truthfulness (unconfirmed refund / cancellation promises)
        action_res = check_action_truthfulness(ctx)
        cls._merge_result(final_result, action_res)
        if final_result.status == ValidationStatus.ESCALATE: 
            return final_result
        
        # Layer 5: Fact contradiction check
        contra_res = check_contradiction(ctx)
        cls._merge_result(final_result, contra_res)
        if final_result.status == ValidationStatus.ESCALATE: 
            return final_result
        
        # Layer 6: Memory consistency check
        mem_res = check_memory_consistency(ctx)
        cls._merge_result(final_result, mem_res)
        if final_result.status == ValidationStatus.ESCALATE: 
            return final_result
        
        # Layer 7: Intent alignment check
        intent_res = check_intent_alignment(ctx)
        cls._merge_result(final_result, intent_res)
        if final_result.status == ValidationStatus.ESCALATE: 
            return final_result
        
        # Layer 8: Semantic grounding against RAG articles
        if final_result.status == ValidationStatus.VALID:
            ground_res = await check_semantic_grounding(ctx)
            cls._merge_result(final_result, ground_res)
            
        return final_result

    @staticmethod
    def _merge_result(final: ValidationResult, current: ValidationResult):
        """Merges validation check results, applying the most severe status."""
        final.violations.extend(current.violations)
        final.reasons.extend(current.reasons)
        status_priority = {
            ValidationStatus.ESCALATE: 4,
            ValidationStatus.REGENERATE: 3,
            ValidationStatus.ASK_CLARIFICATION: 2,
            ValidationStatus.VALID: 1,
        }
        if status_priority[current.status] > status_priority[final.status]:
            final.status = current.status
```

### Explanation
This multi-layer validation engine acts as a defensive perimeter over candidate responses before they reach the user or text-to-speech synthesizer. It systematically intercepts unauthorized PII leaks, fabricated refund commitments, ungrounded factual claims, and logical contradictions. If a critical safety constraint is violated, the service short-circuits the pipeline and routes the customer safely to human experts.

### Related Test Case
`backend/tests/test_response_validation.py` (`test_unconfirmed_refund_blocked_by_validation`, `test_pii_leak_blocked`)

---

## A.10 Relevant Automated Test Suites

### Source File
`backend/tests/test_voice_parity_and_safety.py` (Lines 74–108)

```python
@pytest.mark.asyncio
async def test_voice_turn_unconfirmed_refund_promise_blocked_by_validation(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """If a voice turn proposes a refund without confirmed tool execution, it must be blocked by validation."""
    convo_resp = await async_client.post(
        "/api/conversations",
        json={"subject": "Voice Call", "channel": "voice", "initial_message": None},
        headers=auth_headers_a,
    )
    assert convo_resp.status_code == 200
    convo_id = convo_resp.json()["id"]

    utt_id = f"utt_refund_val_{uuid.uuid4().hex[:8]}"
    resp = await async_client.post(
        "/api/audio/livekit/utterance",
        json={
            "conversation_id": convo_id,
            "utterance_id": utt_id,
            "transcript": "Please refund my money for order ORD-12345 right now.",
        },
        headers=auth_headers_a,
    )
    assert resp.status_code == 200
    data = resp.json()
    ai_reply = (data.get("ai_response") or "").lower()

    # The unvalidated statement must NEVER be spoken or returned without confirmed tool execution
    assert "i have processed your refund" not in ai_reply
    assert "refund has been processed" not in ai_reply
    assert "refunded your" not in ai_reply

    # System safely escalates to human expert team and informs the caller
    assert any(phrase in ai_reply for phrase in ["support team", "expert", "specialist", "connect"])
    assert data.get("workflow_state") in ("waiting_for_expert", "escalating", "with_expert")
```

### Explanation
This automated integration test verifies that the 9-layer response validation guardrail prevents unauthorized promises during conversational voice sessions. When a caller demands a refund without verified transactional execution, Layer 4 action truthfulness suppresses the draft and triggers safe, deterministic escalation to human experts without verbal hallucination.

---
*End of Appendix A — Source Code*

