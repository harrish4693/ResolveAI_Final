from typing import Any, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession

import time
import logging
import re

from app.ai.base import AIProvider
from app.ai.m4.analysis import LanguageDetector, IntentClassifier, SentimentAnalyzer, EntityExtractor
from app.ai.m4.priority import PriorityEngine
from app.ai.m4.decision import DecisionEngine, ResponseGenerator
from app.rag.retriever import TFIDFRetriever

logger = logging.getLogger(__name__)

class M4AIProvider(AIProvider):
    def __init__(self):
        self.language_detector = LanguageDetector()
        self.intent_classifier = IntentClassifier()
        self.sentiment_analyzer = SentimentAnalyzer()
        self.entity_extractor = EntityExtractor()
        
        self.priority_engine = PriorityEngine()
        self.retriever = TFIDFRetriever()
        
        self.decision_engine = DecisionEngine()
        self.response_generator = ResponseGenerator()

        # Intelligence Layer Capabilities
        from app.ai.intelligence.language import (
            CodeMixedLanguageDetector,
            IndianLanguageNormalizer,
            CodeMixedIntentExtractor,
            UniversalMeaningEngine,
        )
        self.cm_language_detector = CodeMixedLanguageDetector()
        self.cm_normalizer = IndianLanguageNormalizer()
        self.cm_intent_extractor = CodeMixedIntentExtractor()
        self.meaning_engine = UniversalMeaningEngine()

    async def generate_structured(self, messages: List[Dict[str, str]], response_format: Any) -> Any:
        raise NotImplementedError("M4AIProvider does not support structured generation.")
        
    async def analyze(self, message: str, context: Dict[str, Any], db: AsyncSession = None) -> Dict[str, Any]:
        """
        Analyzes the incoming message with multi-turn context support.
        """
        start_time = time.time()
        logger.info("M4 pipeline analysis started")
        
        # Multi-turn ASK_USER context preservation
        previous_analysis = context.get("previous_analysis", {})
        conversation_state = context.get("conversation_state")
        history = context.get("history", [])
        
        # 1. Deep Meaning Understanding (Universal Multilingual Engine)
        meaning = self.meaning_engine.understand_utterance(
            message,
            history=history,
            conversation_state=conversation_state
        )

        if conversation_state:
            from app.conversations.state import ConversationStateManager
            ConversationStateManager.update_before_turn(conversation_state, message, meaning)

        conv_fn = meaning.conversational_function
        style = meaning.communication_style
        message_for_analysis = meaning.normalized_meaning or message
        sentiment = self.sentiment_analyzer.analyze(message_for_analysis)

        if meaning.is_code_mixed and meaning.code_mix_type:
            language = meaning.code_mix_type
        elif meaning.primary_language in ("ta", "hi", "kn", "te", "bn", "ml", "mr", "gu", "pa", "or", "as", "ur"):
            language = meaning.primary_language
        else:
            language = self.language_detector.detect(message)

        intent = meaning.intent
        if not intent or intent in ("GENERAL_QUERY", ""):
            classified = self.intent_classifier.classify(message)
            intent = classified if classified and classified != "UNKNOWN" else (intent or "GENERAL_QUERY")

        extracted_entities = self.entity_extractor.extract(message)
        new_entities = {**meaning.entities, **extracted_entities}

        analysis_result_extras = {
            "is_code_mixed": meaning.is_code_mixed,
            "code_mix_type": meaning.code_mix_type,
            "normalized_message": meaning.normalized_meaning,
            "normalized_search_query": meaning.normalized_search_query,
            "negation_detected": meaning.negation_detected,
            "category": meaning.category,
            "clarification_needed": meaning.clarification_needed,
            "conversational_function": conv_fn,
            "communication_style": style,
            "understood_meaning": meaning.understood_meaning,
            "diagnostic_details": meaning.diagnostic_details,
        }
        
        # 2. Merge with previous context guards:
        words_in_msg = set(re.findall(r'\b\w+\b', message.lower()))
        greeting_words = {"hi", "hello", "hey", "vanakkam", "namaste", "good morning", "good afternoon"}
        substantive_words = {
            "policy", "return", "refund", "order", "delivery", "track", "cancel", "pay", "payment",
            "money", "problem", "issue", "crash", "error", "password", "login", "account", "help",
            "enna", "eppadi", "eppo", "enga", "how", "what", "where", "when", "why", "kya", "kaise"
        }
        has_substantive_word = bool(words_in_msg & substantive_words)
        is_greeting = (intent == "GREETING" or bool(words_in_msg & greeting_words) or conv_fn == "GREETING") and not has_substantive_word
        is_unclear = (
            intent == "UNCLEAR"
            or analysis_result_extras.get("clarification_needed", False)
        )
        has_new_order_id = bool(new_entities.get("order_id"))

        if conv_fn == "ACKNOWLEDGMENT" or intent == "ACKNOWLEDGMENT":
            intent = "ACKNOWLEDGMENT"
            # RC-2 Fix: Preserve entities when an unresolved request is still active.
            # Only clear entities when no task is in flight; "seri"/"ok" does not by itself
            # resolve the conversation — it is conversational glue.
            has_active_task = (
                (conversation_state and (
                    getattr(conversation_state, "unresolved_request", None)
                    or getattr(conversation_state, "pending_question", None)
                ))
                or previous_analysis.get("decision_state") in ("ASK_USER",)
            )
            if has_active_task:
                # Keep prior entities; the customer's underlying request is still open
                merged_entities = {**previous_analysis.get("entities", {}), **new_entities}
            else:
                merged_entities = {}
        elif conv_fn == "EMOTIONAL_REACTION" or intent == "EMOTIONAL_REACTION":
            intent = "EMOTIONAL_REACTION"
            merged_entities = {}
        elif is_greeting:
            intent = "GREETING"
            merged_entities = {}
        elif is_unclear:
            intent = "UNCLEAR"
            merged_entities = {}
        elif conv_fn == "ANSWER_TO_PENDING":
            if new_entities.get("order_id"):
                intent = "ORDER_STATUS"
            elif new_entities.get("transaction_id"):
                intent = "PAYMENT_ISSUE"
            merged_entities = {**previous_analysis.get("entities", {}), **new_entities}
        elif conv_fn == "CLARIFICATION_OR_CORRECTION":
            if meaning.diagnostic_details.get("is_misunderstanding_correction"):
                intent = "CORRECTION_RECONSIDER"
            elif meaning.diagnostic_details.get("needs_simplification"):
                prev_int = (conversation_state and conversation_state.active_intent) or previous_analysis.get("intent")
                intent = prev_int if prev_int and prev_int not in ("GREETING", "GENERAL_QUERY", "ACKNOWLEDGMENT") else "CLARIFICATION_SIMPLIFY"
            merged_entities = {**(getattr(conversation_state, "entities", {}) or {}), **previous_analysis.get("entities", {}), **new_entities}
        elif has_new_order_id and intent in ("GENERAL_QUERY", "UNCLEAR", "ORDER_STATUS", "DELIVERY_ISSUE"):
            intent = "ORDER_STATUS"
            merged_entities = new_entities
        elif has_new_order_id:
            merged_entities = new_entities
        elif intent == "LANGUAGE_SWITCH" or conv_fn == "LANGUAGE_SWITCH":
            # Preserve pending inquiry across language switch
            prev_intent = previous_analysis.get("intent") or (conversation_state and conversation_state.active_intent)
            if prev_intent and prev_intent not in ("GREETING", "UNCLEAR", "LANGUAGE_SWITCH", "ACKNOWLEDGMENT"):
                intent = prev_intent
                merged_entities = {**(getattr(conversation_state, "entities", {}) or {}), **previous_analysis.get("entities", {}), **new_entities}
                prev_msg = previous_analysis.get("original_message", "")
                if prev_msg:
                    message_for_analysis = f"{prev_msg} {message_for_analysis}"
            else:
                merged_entities = new_entities
        elif conv_fn == "FOLLOW_UP":
            active_state_intent = getattr(conversation_state, "active_intent", None) if conversation_state else None
            if intent in ("GENERAL_QUERY", "UNKNOWN"):
                if active_state_intent and active_state_intent not in ("GENERAL_QUERY", "UNKNOWN", "GREETING", "UNCLEAR", "LANGUAGE_SWITCH", "ACKNOWLEDGMENT"):
                    intent = active_state_intent
                elif previous_analysis.get("intent") and previous_analysis.get("intent") not in ("GENERAL_QUERY", "UNKNOWN", "GREETING", "UNCLEAR", "LANGUAGE_SWITCH", "ACKNOWLEDGMENT"):
                    intent = previous_analysis.get("intent")
            merged_entities = {**(getattr(conversation_state, "entities", {}) or {}), **previous_analysis.get("entities", {}), **new_entities}
            prev_msg = previous_analysis.get("original_message", "")
            if prev_msg and prev_msg not in message_for_analysis:
                message_for_analysis = f"{prev_msg} {message_for_analysis}"
        elif conv_fn in ("NEW_REQUEST", "TOPIC_CHANGE"):
            merged_entities = new_entities
        else:
            merged_entities = new_entities

        # Parity Row 4: Context-Aware Entity Preservation & Long-Term Memory Hydration
        # Only hydrate when relevant to current domain inquiry and not acknowledgment/greeting
        if conv_fn not in ("ACKNOWLEDGMENT", "EMOTIONAL_REACTION", "GREETING"):
            if intent in ("ORDER_STATUS", "DELIVERY_ISSUE") and "order_id" not in merged_entities:
                if conversation_state and conversation_state.entities.get("order_id"):
                    merged_entities["order_id"] = conversation_state.entities["order_id"]
                elif previous_analysis.get("entities", {}).get("order_id"):
                    merged_entities["order_id"] = previous_analysis["entities"]["order_id"]
                else:
                    for m in context.get("relevant_memories", []):
                        match = re.search(r"\b(ORD-?[A-Za-z0-9_-]{3,25})\b", str(m), re.IGNORECASE)
                        if match:
                            merged_entities["order_id"] = match.group(1).upper()
                            break
            if intent == "PAYMENT_ISSUE" and "transaction_id" not in merged_entities:
                if conversation_state and conversation_state.entities.get("transaction_id"):
                    merged_entities["transaction_id"] = conversation_state.entities["transaction_id"]
                elif previous_analysis.get("entities", {}).get("transaction_id"):
                    merged_entities["transaction_id"] = previous_analysis["entities"]["transaction_id"]
                else:
                    for m in context.get("relevant_memories", []):
                        match = re.search(r"\b(TXN-?[A-Za-z0-9_-]{3,25})\b", str(m), re.IGNORECASE)
                        if match:
                            merged_entities["transaction_id"] = match.group(1).upper()
                            break
        priority = self.priority_engine.determine_priority(intent, sentiment, message_for_analysis)
        
        analysis_result = {
            "original_message": message,
            "language": language,
            "intent": intent,
            "sentiment": sentiment,
            "entities": merged_entities,
            "priority": priority,
            **analysis_result_extras
        }
        
        latency = (time.time() - start_time) * 1000
        logger.info("M4 pipeline analysis completed", extra={
            "analysis": analysis_result,
            "latency_ms": round(latency, 2)
        })
        return analysis_result

    async def generate_response(
        self, analysis: Dict[str, Any], knowledge: List[Any], context: Dict[str, Any], db: AsyncSession = None
    ) -> str:
        """
        Retrieves knowledge, makes a decision, and generates response.
        Updates the analysis object with the decision so ConversationService can access it.
        """
        start_time = time.time()
        
        # 1. Retrieve knowledge if we have a DB session
        message = analysis.get("original_message", "")
        norm_msg = analysis.get("normalized_message", "")
        search_query = analysis.get("normalized_search_query", "")
        entities_str = ' '.join([str(v) for v in analysis.get('entities', {}).values()])
        query = f"{message} {norm_msg} {search_query} {analysis.get('intent', '')} {entities_str}".strip()
        retrieved_articles = []
        if db:
            tenant_id = context.get("tenant_id", "default") or "default"
            rag_result = await self.retriever.search(query, db, tenant_id=tenant_id)
            if isinstance(rag_result, dict):
                retrieved_articles = rag_result.get("results", [])
            else:
                retrieved_articles = rag_result
        elif knowledge:
            retrieved_articles = knowledge
            
        # 2. Intelligence: Advanced RAG Quality
        from app.ai.intelligence.rag_quality import RAGQualityVerifier
        verifier = RAGQualityVerifier()
        rag_quality = verifier.verify(query, retrieved_articles, analysis.get("intent", ""))
        
        # Keep only good articles or let the decision engine see all of them, but we record quality in analysis
        analysis["rag_quality"] = {
            "grade": rag_quality.quality_grade,
            "issues": rag_quality.issues
        }

        # 3. Decision Engine
        decision_obj = self.decision_engine.decide(analysis, retrieved_articles)
        
        # 4. Intelligence: Escalation Decision Engine (Overrides)
        from app.ai.intelligence.escalation import EscalationDecisionEngine
        from app.ai.intelligence.failure_prediction import FailurePredictor, global_attempt_tracker
        escalation_engine = EscalationDecisionEngine()
        esc_eval = escalation_engine.evaluate(
            analysis, 
            {
                "rag_results": retrieved_articles, 
                "attempt_count": context.get("attempt_count", 0)
            }
        )
        
        # 5. Intelligence: Resolution Failure Prediction
        failure_predictor = FailurePredictor()
        failure_pred_context = {
            **context,
            "rag_results": retrieved_articles,
            "attempt_count": context.get("attempt_count", 0),
        }
        convo_id = context.get("conversation_id", 0)
        failure_pred = failure_predictor.predict(
            analysis,
            failure_pred_context,
            attempt_tracker=global_attempt_tracker,
            conversation_id=convo_id,
        )

        failure_risk_data = {
            "likelihood": failure_pred.likelihood.value,
            "probability": failure_pred.probability,
            "should_escalate_early": failure_pred.should_escalate_early,
            "reasons": failure_pred.reasons,
            "frustration_level": failure_pred.frustration_level,
            "recommendation": failure_pred.recommendation,
            "predicted_difficulty": failure_pred.predicted_difficulty,
            "observed_failure_count": failure_pred.observed_failure_count,
            "has_prior_solution_failed": failure_pred.has_prior_solution_failed,
            "suggested_action": failure_pred.suggested_action,
        }
        analysis["failure_risk"] = failure_risk_data

        # Preliminary decision state on analysis for accurate autonomy factor scoring
        analysis["decision_state"] = decision_obj.get("decision")
        analysis["decision_reason"] = decision_obj.get("reason")
        analysis["tool_name"] = decision_obj.get("tool_name")
        analysis["tool_args"] = decision_obj.get("tool_args")

        # 6. Intelligence: Dynamic Autonomy Controls
        from app.ai.intelligence.autonomy import AutonomyLevelDeterminer, AutonomyConfigDTO, AutonomyLevel, AutonomyMode
        from app.ai.autonomy_service import AutonomyConfigService

        autonomy_cfg = context.get("autonomy_config")
        if not autonomy_cfg and context.get("autonomy_mode"):
            autonomy_cfg = AutonomyConfigDTO.for_mode(context.get("autonomy_mode"), tenant_id=context.get("tenant_id", "default"))
        elif not autonomy_cfg and db:
            autonomy_cfg = await AutonomyConfigService.get_effective_config(db, tenant_id=context.get("tenant_id", "default"))
        elif not autonomy_cfg:
            autonomy_cfg = AutonomyConfigDTO.default(context.get("tenant_id", "default"))

        autonomy_determiner = AutonomyLevelDeterminer(
            thresholds=autonomy_cfg.thresholds,
            mode=autonomy_cfg.mode,
        )
        autonomy_decision = autonomy_determiner.determine_level(
            analysis=analysis,
            context={
                **context,
                "rag_results": retrieved_articles,
                "confidence_score": esc_eval.confidence.overall,
            },
            mode=autonomy_cfg.mode,
        )

        # Proactive Escalation & Dynamic Autonomy Policy:
        # - Hard security and critical rules ALWAYS escalate regardless of failure prediction or autonomy mode.
        # - Restricted actions strictly require confirmation in all modes.
        # - If escalation engine dictates ESCALATE: preserve escalation.
        # - If failure risk is HIGH / VERY_HIGH with should_escalate_early: proactively recommend expert escalation.
        # - Conservative mode applies stricter review (clarifies or escalates on elevated uncertainty/risk).
        # - High automation mode allows low-risk routine inquiries to resolve with relaxed threshold (65%+).
        # - Balanced mode preserves existing behavior.
        priority_norm = str(analysis.get("priority", "")).upper()
        intent_norm = str(analysis.get("intent", "")).upper()
        orig_msg = str(analysis.get("original_message", "")).lower()
        attempt_count = context.get("attempt_count", 0)
        mode_val = autonomy_cfg.mode.value if hasattr(autonomy_cfg.mode, "value") else str(autonomy_cfg.mode)

        # Mandatory Safety Hard Escalations:
        from app.ai.intelligence.escalation_keywords import is_supervisor_demand, is_fraud_or_security
        # 1. Explicit supervisor / human demand (Top Priority - never overridden)
        has_supervisor_demand = is_supervisor_demand(orig_msg) or intent_norm in ("ESCALATION_REQUEST",)
        # 2. Fraud / Security keywords or critical priority
        has_security_keywords = is_fraud_or_security(orig_msg)
        # 3. Repeated attempts (>= 3)
        has_repeated_failures = attempt_count >= 3

        if has_supervisor_demand:
            decision_obj["decision"] = "ESCALATE"
            decision_obj["reason"] = "Customer explicitly requested human expert"
        elif intent_norm in ("SECURITY_ISSUE", "FRAUD_SUSPICION") or priority_norm == "CRITICAL" or has_security_keywords:
            decision_obj["decision"] = "ESCALATE"
            decision_obj["reason"] = "Security-sensitive or critical issue requires mandatory expert escalation"
        elif has_repeated_failures:
            decision_obj["decision"] = "ESCALATE"
            decision_obj["reason"] = f"Repeated failed resolution attempts ({attempt_count} attempts) requires expert escalation"
        elif esc_eval.decision.value == "ESCALATE" and decision_obj.get("decision") != "ASK_USER":
            decision_obj["decision"] = "ESCALATE"
            decision_obj["reason"] = esc_eval.context.reason
        elif failure_pred.should_escalate_early or failure_pred.likelihood.value in ("HIGH", "VERY_HIGH"):
            if decision_obj["decision"] == "RESOLVE" and analysis.get("intent") not in ("GREETING", "ACKNOWLEDGMENT") and analysis.get("conversational_function") != "ACKNOWLEDGMENT":
                decision_obj["decision"] = "ESCALATE"
                reason_detail = failure_pred.reasons[0] if failure_pred.reasons else "high resolution failure probability"
                decision_obj["reason"] = f"Proactive escalation recommendation: {reason_detail}"
        else:
            # Apply mode-aware autonomy decision
            if autonomy_decision.level == AutonomyLevel.ESCALATE:
                if decision_obj["decision"] in ("RESOLVE", "USE_TOOL") and analysis.get("intent") != "ACKNOWLEDGMENT" and analysis.get("conversational_function") != "ACKNOWLEDGMENT":
                    decision_obj["decision"] = "ESCALATE"
                    decision_obj["reason"] = f"Autonomy policy ({mode_val}): {autonomy_decision.reasoning}"
            elif autonomy_decision.level == AutonomyLevel.CONFIRMATION_REQUIRED:
                if decision_obj["decision"] == "RESOLVE":
                    # Informational policy inquiries with grounded articles or natural acknowledgments should resolve cleanly
                    is_policy_q = any(k in orig_msg for k in ["policy", "rule", "terms", "how does", "what is", "how to", "pathi", "enna", "eppadi", "evlo", "naatkal"]) or analysis.get("intent") == "ACKNOWLEDGMENT" or analysis.get("conversational_function") == "ACKNOWLEDGMENT"
                    if not is_policy_q:
                        decision_obj["decision"] = "ASK_USER"
                        decision_obj["reason"] = f"Autonomy policy ({mode_val}): {autonomy_decision.reasoning}"

        # Inject decision state and intelligence into analysis (by reference)
        analysis["decision_state"] = decision_obj.get("decision")
        analysis["decision_reason"] = decision_obj.get("reason")
        analysis["tool_name"] = decision_obj.get("tool_name")
        analysis["tool_args"] = decision_obj.get("tool_args")
        analysis["confidence_score"] = esc_eval.confidence.overall
        analysis["autonomy"] = {
            "mode": mode_val,
            "level": autonomy_decision.level.value,
            "confidence_score": autonomy_decision.confidence_score,
            "risk_score": autonomy_decision.risk_score,
            "reasoning": autonomy_decision.reasoning,
            "factors": autonomy_decision.factors,
        }
        
        # 3. Generate Grounded Response
        eff_lang = context.get("preferred_language") or analysis.get("language") or "english"
        response_text = self.response_generator.generate(decision_obj, language=eff_lang)
        
        # Inject memory for testing
        memories = context.get("relevant_memories", [])
        if memories:
            memory_text = "\n".join([f"- {m}" for m in memories])
            response_text += f"\n\n(Mock Memory Injected: {memory_text})"
            
        latency = (time.time() - start_time) * 1000
        logger.info("M4 pipeline response generation completed", extra={
            "decision": analysis["decision_state"],
            "tool_name": analysis.get("tool_name"),
            "latency_ms": round(latency, 2)
        })
        
        return response_text

    async def process_voice_turn(
        self, message: str, context: Dict[str, Any], db: AsyncSession = None
    ) -> Dict[str, Any]:
        """
        Fast voice turn processor for M4 mock provider with emotion estimation,
        universal multilingual meaning understanding, and natural spoken responses.
        """
        from app.ai.intelligence.emotion import ConversationalEmotionAnalyzer

        history = context.get("history", [])
        conversation_state = context.get("conversation_state")
        turn_number = len([m for m in history if m.get("sender_type") == "ai"]) + 1
        attempt_count = context.get("attempt_count", 0)

        # 1. Meaning understanding (Universal Multilingual Engine)
        meaning = self.meaning_engine.understand_utterance(text=message, history=history, conversation_state=conversation_state)

        # 2. Emotion analysis
        emotion_res = ConversationalEmotionAnalyzer.analyze(
            text=message,
            history=history,
            attempt_count=attempt_count,
        )

        # 3. Run analysis
        analysis = await self.analyze(message, context, db)
        analysis["emotion"] = emotion_res.primary_emotion
        analysis["emotion_confidence"] = emotion_res.confidence
        analysis["negation_detected"] = meaning.negation_detected
        analysis["understood_meaning"] = meaning.understood_meaning
        analysis["diagnostic_details"] = meaning.diagnostic_details

        # 4. Generate response
        response_text = await self.generate_response(analysis, [], context, db)

        # Strip formatting for voice naturalness
        cleaned = re.sub(r"```[\s\S]*?```", "", response_text)
        cleaned = re.sub(r"\[EXT\]", "", cleaned)
        cleaned = re.sub(r"[*#_`\[\]{}]", "", cleaned)
        cleaned = re.sub(r"\(Mock Memory Injected:[^)]*\)", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # Voice naturalness: limit to at most two conversational sentences
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]
        if len(sentences) > 2:
            cleaned = " ".join(sentences[:2])

        decision = analysis.get("decision_state", "RESOLVE")

        # Conversational handling for Universal Engine intents:
        if meaning.conversational_function == "ACKNOWLEDGMENT" or meaning.intent == "ACKNOWLEDGMENT":
            decision = "RESOLVE"
            target_lang = str(context.get("preferred_language", meaning.code_mix_type or "english")).lower()
            ACKNOWLEDGMENT_BY_LANG = {
                "tanglish": "Magizhchi! Vera edhavadhu help venuma?",
                "tamil": "மகிழ்ச்சி! உங்களுக்கு வேறு ஏதேனும் உதவி தேவையா?",
                "hinglish": "Aapka swagat hai! Kya aapko aur kisi cheez mein madad chahiye?",
                "hindi": "आपका स्वागत है! क्या आपको और किसी चीज़ में मदद चाहिए?",
                "kannada": "ತುಂಬಾ ಸಂತೋಷ! ನಿಮಗೆ ಬೇರೆ ಏನಾದರೂ ಸಹಾಯ ಬೇಕೇ?",
                "kanglish": "Santhosha! Innu bere sahayavagbeka?",
                "telugu": "చాలా సంతోషం! మీకు ఇంకా ఏదైనా సహాయం కావాలా?",
                "tenglish": "Santhosham! Inka emaina help kavala?",
                "malayalam": "വളരെ സന്തോഷം! നിങ്ങൾക്ക് വേറെ എന്തെങ്കിലും സഹായം വേണമോ?",
                "manglish": "Santhosham! Iniyum enthenkilum help veno?",
                "bengali": "অনেক ধন্যবাদ! আপনার কি আরও কোনো সাহায্য লাগবে?",
                "benglish": "Anondito! Aaro kono help lagbe ki?",
                "marathi": "आनंद झाला! अजून काही मदत हवी आहे का?",
                "marathish": "Anand jhala! Ajun kahi help havi ahe ka?",
                "gujarati": "આનંદ થયો! બીજી કોઈ મદદ જોઈએ છે?",
                "gujlish": "Aanand thayo! Biji koi help joiye chhe?",
                "punjabi": "ਖੁਸ਼ੀ ਹੋਈ! ਹੋਰ ਕੋਈ ਮਦਦ ਚਾਹੀਦੀ ਹੈ?",
                "punglish": "Khushi hoyi! Hor koi help chahidi hai?",
                "odia": "ଖୁସି ଲାଗିଲା! ଆପଣଙ୍କୁ ଆଉ କିଛି ସାହାଯ୍ୟ ଦରକାର କି?",
                "assamese": "ভাল লাগিল! আপোনাক আৰু কিবা সহায় লাগে নেকি?",
                "urdu": "بہت خوشی ہوئی! کیا آپ کو مزید کسی مدد کی ضرورت ہے؟",
                "english": "You're welcome! Let me know if you need help with anything else.",
            }
            matched_ack = None
            for k, msg in ACKNOWLEDGMENT_BY_LANG.items():
                if k in target_lang:
                    matched_ack = msg
                    break
            cleaned = matched_ack or ACKNOWLEDGMENT_BY_LANG["english"]
        elif meaning.conversational_function == "EMOTIONAL_REACTION" or meaning.intent == "EMOTIONAL_REACTION":
            decision = "ASK_USER"
            target_lang = str(context.get("preferred_language", meaning.code_mix_type or "english")).lower()
            EMOTIONAL_REACTION_BY_LANG = {
                "tanglish": "Ungal thagavalukku romba varuthapadugirom. Ungal issue-ah solve panna naan ready-aa irukken, illa oru human expert-kku connect panna vaa?",
                "tamil": "உங்கள் தகவலுக்கு மிகவும் வருந்துகிறோம். உங்கள் பிரச்சனையை தீர்க்க நான் தயாராக இருக்கிறேன், அல்லது மனித நிபுணருடன் இணைக்கவா?",
                "hinglish": "Humein khed hai ki aapko pareshani hui. Main is samasya ko solve karne ke liye poori koshish karunga, ya expert se baat karni hai?",
                "hindi": "हमें खेद है कि आपको परेशानी हुई। मैं इस समस्या को हल करने की पूरी कोशिश करूँगा, या विशेषज्ञ से बात करनी है?",
                "kannada": "ನಿಮಗೆ ಉಂಟಾದ ತೊಂದರೆಗೆ ವಿಷಾದಿಸುತ್ತೇವೆ. ನಿಮ್ಮ ಸಮಸ್ಯೆಯನ್ನು ಬಗೆಹರಿಸಲು ನಾನು ಸಿದ್ಧನಾಗಿದ್ದೇನೆ, ಅಥವಾ ತಜ್ಞರೊಂದಿಗೆ ಸಂಪರ್ಕಿಸಬೇಕೇ?",
                "kanglish": "Nimage aada thondarege khedavagide. Nimma problem solve madoke naan ready iddini, athva expert kitta connect madla?",
                "telugu": "మీకు కలిగిన అసౌకర్యానికి చింతిస్తున్నాము. మీ సమస్యను పరిష్కరించడానికి నేను సిద్ధంగా ఉన్నాను, లేదా నిపుణుడితో మాట్లాడతారా?",
                "tenglish": "Meeku jarigina asowkaryaaniki sorry andi. Mee issue solve cheyadaniki nenu ready, leda human expert tho connect cheyyala?",
                "malayalam": "നിങ്ങൾക്കുണ്ടായ ബുദ്ധിമുട്ടിൽ ഖേദിക്കുന്നു. ഈ പ്രശ്നം പരിഹരിക്കാൻ ഞാൻ തയ്യാറാണ്, അല്ലെങ്കിൽ ഒരു വിദഗ്ദ്ധനുമായി ബന്ധിപ്പിക്കണോ?",
                "manglish": "Ningalkkundaaya vishamathil khedikkunnu. Ee issue solve cheyyaan njan ready aanu, allel expert kitta connect cheyyano?",
                "bengali": "আপনার অসুবিধার জন্য আমরা আন্তরিকভাবে দুঃখিত। আমি সমস্যা সমাধানের চেষ্টা করছি, নাকি বিশেষজ্ঞের সাথে কথা বলবেন?",
                "benglish": "Apanar osubidhar jonno khoma chaichhi. Ami issue solve korte ready achhi, naki expert er sathe connect korbo?",
                "marathi": "तुम्हाला झालेल्या त्रासाबद्दल दिलगीर आहोत. मी तुमची अडचण सोडवण्यासाठी तयार आहे, की तज्ज्ञांशी बोलायचे आहे?",
                "marathish": "Tumhala jhalelya trasabaddal sorry. Me issue solve karayla ready ahe, ki expert shi bolaycha ahe?",
                "gujarati": "તમને થયેલી મુશ્કેલી બદલ દિલગીર છીએ. હું સમસ્યા ઉકેલવા તૈયાર છું, કે નિષ્ણાત સાથે વાત કરવી છે?",
                "gujlish": "Tamne thael tras badal sorry. Hu problem solve karva ready chhu, ke expert saathe connect karu?",
                "punjabi": "ਤੁਹਾਨੂੰ ਹੋਈ ਪਰੇਸ਼ਾਨੀ ਲਈ ਅਫ਼ਸੋਸ ਹੈ। ਮੈਂ ਇਹ ਮਸਲਾ ਹੱਲ ਕਰਨ ਲਈ ਤਿਆਰ ਹਾਂ, ਜਾਂ ਕਿਸੇ ਮਾਹਰ ਨਾਲ ਗੱਲ ਕਰਨੀ ਹੈ?",
                "punglish": "Tuhanu hoyi pareshani layi sorry. Main issue solve karan layi ready haan, ya expert naal connect karaan?",
                "odia": "ଆପଣଙ୍କ ଅସୁବିଧା ପାଇଁ ଆମେ ଦୁଃଖିତ। ମୁଁ ସମସ୍ୟାର ସମାଧାନ ପାଇଁ ପ୍ରସ୍ତୁତ, କିମ୍ବା ବିଶେଷଜ୍ଞଙ୍କ ସହ କଥା ହେବେ?",
                "assamese": "আপোনাৰ অসুবিধাৰ বাবে আমি দুখিত। মই সমস্যা সমাধান কৰিবলৈ সাজু, নে বিশেষজ্ঞৰ সৈতে কথা পাতিব?",
                "urdu": "ہمیں افسوس ہے کہ آپ کو پریشانی ہوئی۔ میں یہ مسئلہ حل کرنے کے لیے تیار ہوں، یا ماہر سے بات کرنی ہے؟",
                "english": "I understand your frustration and apologize for the inconvenience. Let me help sort this out.",
            }
            matched_emo = None
            for k, msg in EMOTIONAL_REACTION_BY_LANG.items():
                if k in target_lang:
                    matched_emo = msg
                    break
            cleaned = matched_emo or EMOTIONAL_REACTION_BY_LANG["english"]
        elif meaning.intent == "LANGUAGE_SWITCH" or (context.get("is_language_switch") and meaning.intent in ("LANGUAGE_SWITCH", "GREETING", "UNKNOWN", "UNCLEAR") and not context.get("pending_query") and len(cleaned) < 5):
            decision = "RESOLVE"
            target_lang = str(context.get("preferred_language", "tanglish")).lower()
            from app.conversations.service import ConversationService
            ack = ConversationService.LANGUAGE_SWITCH_ACKNOWLEDGMENTS.get(
                target_lang,
                f"Sure, let's continue in {target_lang.capitalize()}."
            )
            ack_pfx = ""
            for lang_k, pfx in ConversationService.LANGUAGE_SWITCH_PREFIXES.items():
                if lang_k in target_lang:
                    ack_pfx = pfx
                    break
            if context.get("pending_query") and cleaned and len(cleaned) > 10:
                pfx = ack_pfx or "Sure, let's continue! "
                cleaned = f"{pfx}{cleaned}"
            else:
                cleaned = ack
        elif meaning.intent == "OPENING_PROBLEM_STATEMENT":
            decision = "ASK_USER"
            cm_lang = (meaning.code_mix_type or meaning.primary_language or "english").lower()
            OPENING_PROBLEM_BY_LANG = {
                "tanglish": "Seri, enna problem? Sollunga.",
                "tamil": "சரி, என்ன பிரச்சனை? சொல்லுங்கள்.",
                "hinglish": "Bataiye, kya dikkat aa rahi hai?",
                "hindi": "बताइए, क्या समस्या आ रही है?",
                "telugu": "చెప్పండి, మీకు ఏమి సమస్య ఉంది?",
                "tenglish": "Cheppandi, meeku emi problem undi?",
                "kannada": "ಹೇಳಿ, ನಿಮಗೆ ಏನು ಸಮಸ್ಯೆ ಇದೆ?",
                "kanglish": "Heli, nimage en problem aagidhe?",
                "malayalam": "പറയൂ, എന്താണ് പ്രശ്നം?",
                "manglish": "Parayoo, enthaanu problem?",
                "bengali": "বলুন, আপনার কী সমস্যা হচ্ছে?",
                "benglish": "Bolun, apanar ki problem hochhe?",
                "marathi": "सांगा, काय अडचण येत आहे?",
                "marathish": "Sanga, kay problem yet ahe?",
                "gujarati": "કહો, તમને શું સમસ્યા આવી રહી છે?",
                "gujlish": "Kaho, tamne shu problem aavi rahi chhe?",
                "punjabi": "ਦੱਸੋ, ਤੁਹਾਨੂੰ ਕੀ ਸਮੱਸਿਆ ਆ ਰਹੀ ਹੈ?",
                "punglish": "Dasso, tuhanu ki problem aa rehi hai?",
                "odia": "କୁହନ୍ତୁ, ଆପଣଙ୍କର କ'ଣ ସମସ୍ୟା ହେଉଛି?",
                "assamese": "কওক, আপোনাৰ কি সমস্যা হৈছে?",
                "urdu": "بتائیے، آپ کو کیا مسئلہ درپیش ہے؟",
                "english": "Sure, what issue are you facing? Tell me.",
            }
            matched_msg = None
            for k, msg in OPENING_PROBLEM_BY_LANG.items():
                if k in cm_lang:
                    matched_msg = msg
                    break
            cleaned = matched_msg or OPENING_PROBLEM_BY_LANG["english"]
        elif meaning.intent == "TECHNICAL_ISSUE":
            symptom = meaning.diagnostic_details.get("symptom")
            decision = "ASK_USER"
            if symptom == "loading_freeze":
                if meaning.code_mix_type == "tanglish":
                    cleaned = "Seri, app restart panni paathengala? Cache clear panni try pannunga."
                elif meaning.code_mix_type in ("hinglish", "hindi"):
                    cleaned = "App restart karke dekha? Ek baar cache clear karke try kijiye."
                else:
                    cleaned = "Have you tried restarting the app and clearing its cache?"
            else:
                if meaning.code_mix_type == "tanglish":
                    cleaned = "Error message edhavadhu kaatutha, illa loading-laye nikkudha?"
                elif meaning.code_mix_type in ("hinglish", "hindi"):
                    cleaned = "Koi error message aa raha hai ya screen freeze ho rahi hai?"
                else:
                    cleaned = "Are you seeing an error message or does it freeze?"
        elif meaning.intent == "ESCALATION_REQUEST" or decision == "ESCALATE":
            decision = "ESCALATE"
            cleaned = "I am connecting you with an expert right now. Please hold on."
        elif emotion_res.primary_emotion == "frustrated":
            if "restart" in cleaned.lower() or "reinstall" in cleaned.lower() or len(cleaned) < 5:
                cleaned = "Let's check what happened with your transaction without repeating those steps."
            elif cleaned.lower().startswith("i understand"):
                cleaned = re.sub(r"^i understand[^.!?]*[.!?]\s*", "", cleaned, flags=re.IGNORECASE).strip()
                if not cleaned:
                    cleaned = "Let's check what happened with your transaction."
        elif not cleaned:
            cleaned = "Let me check the details for your request right now."

        # Keep word count strictly conversational (< 45 words)
        words = cleaned.split()
        if len(words) > 40:
            cleaned = " ".join(words[:40]) + "."

        final_intent = meaning.intent if meaning.intent not in ("GENERAL_QUERY",) else analysis.get("intent", "GENERAL_QUERY")
        final_lang = meaning.code_mix_type if meaning.is_code_mixed else analysis.get("language", "English")

        return {
            "intent": final_intent,
            "category": meaning.category,
            "sentiment": analysis.get("sentiment", "neutral"),
            "priority": analysis.get("priority", "LOW"),
            "language": final_lang,
            "emotion": emotion_res.primary_emotion,
            "emotion_confidence": emotion_res.confidence,
            "entities": {**analysis.get("entities", {}), **meaning.entities},
            "decision": decision,
            "spoken_response": cleaned,
            "response_text": cleaned,
            "tool_name": analysis.get("tool_name"),
            "tool_args": analysis.get("tool_args", {}),
            "reason": analysis.get("decision_reason", ""),
            "negation_detected": meaning.negation_detected,
            "understood_meaning": meaning.understood_meaning,
            "latency_ms": 15.0,
        }

