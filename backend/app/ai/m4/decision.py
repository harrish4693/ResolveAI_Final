from typing import Dict, Any, List

class DecisionEngine:
    def decide(
        self, 
        analysis: Dict[str, Any], 
        retrieved_articles: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Returns a structured decision: RESOLVE, ASK_USER, ESCALATE.
        """
        priority = str(analysis.get("priority", "LOW")).upper()
        intent = str(analysis.get("intent", "GENERAL_QUERY")).upper()
        entities = analysis.get("entities", {})
        orig_msg = str(analysis.get("original_message", "")).lower()
        from app.ai.intelligence.escalation_keywords import is_supervisor_demand, is_fraud_or_security

        # 0. Check for explicit human / expert escalation request (Highest Priority)
        if intent in ["ESCALATION_REQUEST"]:
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

        if intent == "EMOTIONAL_REACTION" or conv_fn == "EMOTIONAL_REACTION":
            return {
                "decision": "ASK_USER",
                "reason": "Customer expressed frustration, offering empathetic support",
                "missing_entity": "empathy_checkin"
            }

        # 1.6 Multilingual positive confirmations (Refund received & Payment completed)
        if intent == "REFUND_RECEIVED" or (
            intent == "REFUND_ISSUE"
            and not analysis.get("negation_detected", True)
            and any(w in orig_msg for w in ["vandhuduchu", "vandhuruchu", "received", "got it", "got my", "mil gaya", "வந்துவிட்டது", "கிடைத்துவிட்டது"])
        ):
            return {
                "decision": "RESOLVE",
                "reason": "Customer confirmed refund has been received",
                "action_type": "refund_received_acknowledgment"
            }

        if intent == "PAYMENT_CONFIRMATION" or (
            intent == "PAYMENT_ISSUE"
            and not analysis.get("negation_detected", True)
            and any(w in orig_msg for w in ["panniten", "pantaen", "paid", "completed", "done", "செலுத்திவிட்டேன்", "கட்டியாச்சு"])
        ):
            return {
                "decision": "RESOLVE",
                "reason": "Customer confirmed payment has been completed",
                "action_type": "payment_confirmation"
            }

        diag = analysis.get("diagnostic_details") or {}

        # RC-7: Request alternative solutions ("Idhukku vera edhavadhu vazhi irukka?", "Is there any other way?")
        if intent == "REQUEST_ALTERNATIVE" or diag.get("is_request_alternative") or analysis.get("is_request_alternative"):
            return {
                "decision": "RESOLVE",
                "reason": "Customer requested alternative options or resolution paths",
                "action_type": "alternative_options",
                "article": retrieved_articles[0] if retrieved_articles else None
            }

        # RC-7: Delivery delay continuation ("Innum varala ya, romba late aagudhu")
        if diag.get("is_delay_continuation") or analysis.get("is_delay_continuation"):
            if "order_id" in entities:
                return {
                    "decision": "USE_TOOL",
                    "tool_name": "get_order_status",
                    "tool_args": {"order_id": entities["order_id"]},
                    "reason": "Customer inquiring on delayed delivery with provided Order ID"
                }
            return {
                "decision": "ASK_USER",
                "reason": "Customer expressing delivery delay frustration, empathetic inquiry for Order ID",
                "missing_entity": "empathetic_delay_inquiry"
            }

        # RC-7 & RC-3: Causal explanation / Why request ("But why?", "Edhukku?", "Kyun?")
        if intent == "WHY_QUESTION" or diag.get("explain_why") or analysis.get("explain_why"):
            return {
                "decision": "RESOLVE",
                "reason": "Customer requested causal reason behind previous answer or requirement",
                "action_type": "causal_why_explanation",
                "article": retrieved_articles[0] if retrieved_articles else None
            }

        # RC-3: Misunderstanding correction / reconsideration ("Naa indha question kekave illaye", "Naan adha sollala")
        if intent == "CORRECTION_RECONSIDER" or diag.get("is_misunderstanding_correction") or analysis.get("is_misunderstanding_correction"):
            return {
                "decision": "ASK_USER",
                "reason": "Customer indicated misunderstanding; re-evaluating true request",
                "missing_entity": "reconsider_question"
            }

        # RC-3: Simplification request ("puriyala, simple ah sollu")
        if intent == "CLARIFICATION_SIMPLIFY" or diag.get("needs_simplification") or analysis.get("needs_simplification"):
            return {
                "decision": "RESOLVE",
                "reason": "Customer requested simpler explanation of previous response",
                "action_type": "simplified_explanation",
                "article": retrieved_articles[0] if retrieved_articles else None
            }

        # RC-3: Contextual next-steps continuation ("appo next enna pannanum?")
        if diag.get("is_next_step") or analysis.get("is_next_step"):
            if intent in ("POLICY_QUERY", "REFUND_ISSUE"):
                return {
                    "decision": "RESOLVE",
                    "reason": "Explaining next steps for policy or return request",
                    "action_type": "policy_next_steps",
                    "article": retrieved_articles[0] if retrieved_articles else None
                }
            if intent in ("ORDER_STATUS", "DELIVERY_ISSUE") and "order_id" not in entities:
                return {
                    "decision": "ASK_USER",
                    "reason": "Need Order ID to provide next steps for order/delivery",
                    "missing_entity": "order_id"
                }

        # 2. Check for greetings and unclear inputs
        if intent == "GREETING":
            return {
                "decision": "ASK_USER",
                "reason": "Greeting customer",
                "missing_entity": "greeting"
            }

        if intent == "UNCLEAR":
            return {
                "decision": "ASK_USER",
                "reason": "Input is unclear and needs clarification",
                "missing_entity": "unclear"
            }

        # 2.1 Check for missing required information based on intent
        if intent == "PAYMENT_ISSUE" and "transaction_id" not in entities:
            is_policy_q = any(w in orig_msg for w in ["policy", "rule", "terms", "how does", "what is", "kaise", "eppadi", "methods"])
            if not is_policy_q:
                return {
                    "decision": "ASK_USER",
                    "reason": "Transaction ID required for payment issues",
                    "missing_entity": "transaction_id"
                }
            
        if intent in ["DELIVERY_ISSUE", "ORDER_STATUS"] and "order_id" not in entities:
            is_informational_or_policy = any(w in orig_msg for w in [
                "policy", "rule", "terms", "charges", "where do you ship", "shipment time", "methods"
            ])
            if not is_informational_or_policy:
                return {
                    "decision": "ASK_USER",
                    "reason": "Order ID required for delivery tracking",
                    "missing_entity": "order_id"
                }
            
        # 2.5 Check if we should use a tool
        if intent == "PAYMENT_ISSUE" and "transaction_id" in entities:
            return {
                "decision": "USE_TOOL",
                "tool_name": "check_transaction",
                "tool_args": {"transaction_id": entities["transaction_id"]},
                "reason": "Using check_transaction to check payment status"
            }

        if intent in ["DELIVERY_ISSUE", "ORDER_STATUS"] and "order_id" in entities:
            return {
                "decision": "USE_TOOL",
                "tool_name": "get_order_status",
                "tool_args": {"order_id": entities["order_id"]},
                "reason": "Using get_order_status for delivery tracking"
            }

        if "ticket_id" in entities:
            return {
                "decision": "USE_TOOL",
                "tool_name": "get_ticket_status",
                "tool_args": {"ticket_id": entities["ticket_id"]},
                "reason": "Using get_ticket_status to check ticket progress"
            }

        # High-risk execution actions: financial refunds and account changes require human expert
        is_refund_execution = intent == "REFUND_ISSUE" and (
            "want a refund" in orig_msg
            or "give me a refund" in orig_msg
            or "refund my" in orig_msg
            or "need refund" in orig_msg
            or "refund pannunga" in orig_msg
            or "refund kripya" in orig_msg
            or bool(entities.get("transaction_id"))
        )
        if is_refund_execution or intent == "UPDATE_ISSUE":
            return {
                "decision": "ESCALATE",
                "reason": f"{intent} requires human expert review"
            }

        # Clarification on why Order ID is needed
        if intent == "CLARIFICATION_ORDER_ID_PURPOSE" or diag.get("clarification_target") == "order_id_reason":
            return {
                "decision": "ASK_USER",
                "reason": "Explaining why Order ID is required to lookup order status",
                "missing_entity": "order_id_reason"
            }

        # Policy Queries & Overview
        category = analysis.get("category", "")
        is_policy_query = (
            intent == "POLICY_QUERY"
            or category == "policy"
            or (analysis.get("diagnostic_details") or {}).get("is_policy_overview")
            or any(kw in orig_msg for kw in ["ena ena policy", "enna policy", "what policies", "policies available", "kya kya policy", "policy list", "available policies", "unga kitaa", "unga kitta"])
        )
        if is_policy_query:
            is_overview = (
                (analysis.get("diagnostic_details") or {}).get("is_policy_overview")
                or any(kw in orig_msg for kw in ["ena ena", "enna enna", "what policies", "all policies", "policy list", "available policies", "unga kitaa", "unga kitta", "kya kya"])
            )
            article = retrieved_articles[0] if retrieved_articles else {
                "title": "ResolveMart Company Policies Overview",
                "content": "Return Policy: 30 days return window. Cancellation Policy: Cancel before dispatch. Shipping: Standard 3-5 days delivery. Support: 24/7 customer support."
            }
            return {
                "decision": "RESOLVE",
                "reason": f"Providing company policy {'overview' if is_overview else 'information'}",
                "action_type": "policy_overview" if is_overview else "policy_info",
                "article": article
            }

        # 3. Check if we have reliable knowledge to resolve the inquiry
        if retrieved_articles:
            best_article = retrieved_articles[0]
            return {
                "decision": "RESOLVE",
                "reason": f"Reliable knowledge found: {best_article.get('title', 'Knowledge Article')}",
                "article": best_article
            }

        # 4. No reliable knowledge found: apply appropriate safety / clarification policy
        # High-risk actions without knowledge: financial refunds, account changes, or security
        if intent == "REFUND_ISSUE":
            return {
                "decision": "ESCALATE",
                "reason": "Refund requests require human expert review"
            }

        if intent == "UPDATE_ISSUE":
            return {
                "decision": "ESCALATE",
                "reason": "Account changes require human expert review"
            }
            
        if intent == "GENERAL_QUERY" and "support ticket" in analysis.get("original_message", "").lower():
            return {
                "decision": "USE_TOOL",
                "tool_name": "create_support_ticket",
                "tool_args": {"subject": analysis.get("original_message", "New ticket")},
                "reason": "Creating a support ticket as requested"
            }

        if intent in ["GREETING", "GENERAL_QUERY"]:
            return {
                "decision": "ASK_USER",
                "reason": f"No knowledge needed for {intent}, gathering more context",
                "missing_entity": "greeting" if intent == "GREETING" else "specific_issue"
            }
        elif intent in ["LOGIN_ISSUE"]:
            return {
                "decision": "ASK_USER",
                "reason": "Provide troubleshooting guidance or ask for error details",
                "missing_entity": "error_details"
            }
        elif intent in ["SECURITY_ISSUE"]:
            return {
                "decision": "ESCALATE",
                "reason": f"Security-sensitive issue requires mandatory human intervention"
            }
        else:
            return {
                "decision": "ESCALATE",
                "reason": f"No reliable knowledge found to safely resolve {intent}"
            }

class ResponseGenerator:
    def generate(self, decision_obj: Dict[str, Any], language: str = "english") -> str:
        """
        Generates grounded responses based on the decision and requested language.
        Never hallucinates.
        """
        decision = decision_obj.get("decision")
        item_term = decision_obj.get("customer_item_term") or decision_obj.get("diagnostic_details", {}).get("customer_item_term", "order")
        lang_lower = str(language or "english").lower()
        is_tanglish = "tanglish" in lang_lower
        is_tamil = ("tamil" in lang_lower or lang_lower in ("ta", "ta-in")) and not is_tanglish
        is_hinglish = "hinglish" in lang_lower
        is_hindi = ("hindi" in lang_lower or lang_lower in ("hi", "hi-in")) and not is_hinglish

        is_kanglish = "kanglish" in lang_lower
        is_kannada = ("kannada" in lang_lower or lang_lower in ("kn", "kn-in")) and not is_kanglish
        is_tenglish = "tenglish" in lang_lower
        is_telugu = ("telugu" in lang_lower or lang_lower in ("te", "te-in")) and not is_tenglish
        is_manglish = "manglish" in lang_lower
        is_malayalam = ("malayalam" in lang_lower or lang_lower in ("ml", "ml-in")) and not is_manglish

        is_benglish = "benglish" in lang_lower
        is_bengali = ("bengali" in lang_lower or "bangla" in lang_lower or lang_lower in ("bn", "bn-in")) and not is_benglish
        is_marathish = "marathish" in lang_lower
        is_marathi = ("marathi" in lang_lower or lang_lower in ("mr", "mr-in")) and not is_marathish
        is_gujlish = "gujlish" in lang_lower
        is_gujarati = ("gujarati" in lang_lower or lang_lower in ("gu", "gu-in")) and not is_gujlish
        is_punglish = "punglish" in lang_lower
        is_punjabi = ("punjabi" in lang_lower or lang_lower in ("pa", "pa-in")) and not is_punglish

        is_odia = "odia" in lang_lower or "oriya" in lang_lower or lang_lower in ("or", "or-in", "od", "od-in")
        is_assamese = "assamese" in lang_lower or lang_lower in ("as", "as-in")
        is_urdu = "urdu" in lang_lower or lang_lower in ("ur", "ur-in")
        
        if decision == "USE_TOOL":
            if "tool_result" in decision_obj:
                res = decision_obj["tool_result"]
                data = res.get("data", res) if isinstance(res, dict) else {}
                success = res.get("success", True) if isinstance(res, dict) else True
                if success is not False and ("order_id" in data or "transaction_id" in data or "ticket_id" in data or "full_name" in data or res.get("success") is True or res.get("status") == "success"):
                    if "status" in data and "order_id" in data:
                        deliv = f" Expected delivery: {data['expected_delivery']}." if data.get("expected_delivery") else ""
                        if is_tanglish:
                            return f"Unga order {data['order_id']} status {data['status']}.{deliv} Tracking number: {data.get('tracking_number', 'N/A')}."
                        elif is_tamil:
                            deliv_ta = f" எதிர்பார்க்கப்படும் டெலிவரி: {data['expected_delivery']}." if data.get("expected_delivery") else ""
                            return f"உங்கள் ஆர்டர் {data['order_id']} நிலை {data['status']}.{deliv_ta} கண்காணிப்பு எண்: {data.get('tracking_number', 'N/A')}."
                        elif is_hinglish:
                            return f"Aapka order {data['order_id']} status {data['status']} hai.{deliv} Tracking: {data.get('tracking_number', 'N/A')}."
                        elif is_hindi:
                            deliv_hi = f" अपेक्षित डिलीवरी: {data['expected_delivery']}." if data.get("expected_delivery") else ""
                            return f"आपका ऑर्डर {data['order_id']} स्थिति {data['status']} है।{deliv_hi} ट्रैकिंग नंबर: {data.get('tracking_number', 'N/A')}।"
                        elif is_kanglish:
                            return f"Nimma order {data['order_id']} status {data['status']}.{deliv} Tracking number: {data.get('tracking_number', 'N/A')}."
                        elif is_kannada:
                            deliv_kn = f" ಅಂದಾಜು ಡೆಲಿವರಿ ದಿನಾಂಕ: {data['expected_delivery']}." if data.get("expected_delivery") else ""
                            return f"ನಿಮ್ಮ ಆರ್ಡರ್ {data['order_id']} ಸ್ಥಿತಿ {data['status']}.{deliv_kn} ಟ್ರ್ಯಾಕಿಂಗ್ ಸಂಖ್ಯೆ: {data.get('tracking_number', 'N/A')}."
                        elif is_tenglish:
                            return f"Mee order {data['order_id']} status {data['status']}.{deliv} Tracking number: {data.get('tracking_number', 'N/A')}."
                        elif is_telugu:
                            deliv_te = f" అంచనా డెలివరీ తేదీ: {data['expected_delivery']}." if data.get("expected_delivery") else ""
                            return f"మీ ఆర్డర్ {data['order_id']} స్థితి {data['status']}.{deliv_te} ట్రాకింగ్ సంఖ్య: {data.get('tracking_number', 'N/A')}."
                        elif is_manglish:
                            return f"Ningalude order {data['order_id']} status {data['status']}.{deliv} Tracking number: {data.get('tracking_number', 'N/A')}."
                        elif is_malayalam:
                            deliv_ml = f" പ്രതീക്ഷിക്കുന്ന ഡെലിവറി തീയതി: {data['expected_delivery']}." if data.get("expected_delivery") else ""
                            return f"നിങ്ങളുടെ ഓർഡർ {data['order_id']} നില {data['status']}.{deliv_ml} ട്രാക്കിംഗ് നമ്പർ: {data.get('tracking_number', 'N/A')}."
                        elif is_benglish:
                            return f"Apanar order {data['order_id']} status {data['status']}.{deliv} Tracking number: {data.get('tracking_number', 'N/A')}."
                        elif is_bengali:
                            deliv_bn = f" সম্ভাব্য ডেলিভারি তারিখ: {data['expected_delivery']}।" if data.get("expected_delivery") else ""
                            return f"আপনার অর্ডার {data['order_id']} স্ট্যাটাস {data['status']}।{deliv_bn} ট্র্যাকিং নম্বর: {data.get('tracking_number', 'N/A')}।"
                        elif is_marathish:
                            return f"Tumcha order {data['order_id']} status {data['status']} ahe.{deliv} Tracking number: {data.get('tracking_number', 'N/A')}."
                        elif is_marathi:
                            deliv_mr = f" अपेक्षित डिलिव्हरी तारीख: {data['expected_delivery']}." if data.get("expected_delivery") else ""
                            return f"तुमचा ऑर्डर {data['order_id']} स्थिती {data['status']} आहे.{deliv_mr} ट्रॅकिंग नंबर: {data.get('tracking_number', 'N/A')}."
                        elif is_gujlish:
                            return f"Tamaro order {data['order_id']} status {data['status']} chhe.{deliv} Tracking number: {data.get('tracking_number', 'N/A')}."
                        elif is_gujarati:
                            deliv_gu = f" અપેક્ષિત ડિલિવરી તારીખ: {data['expected_delivery']}." if data.get("expected_delivery") else ""
                            return f"તમારો ઓર્ડર {data['order_id']} સ્થિતિ {data['status']} છે.{deliv_gu} ટ્રેકિંગ નંબર: {data.get('tracking_number', 'N/A')}."
                        elif is_punglish:
                            return f"Tuhada order {data['order_id']} status {data['status']} hai.{deliv} Tracking number: {data.get('tracking_number', 'N/A')}."
                        elif is_punjabi:
                            deliv_pa = f" ਸੰਭਾਵਿਤ ਡਿਲੀਵਰੀ ਮਿਤੀ: {data['expected_delivery']}।" if data.get("expected_delivery") else ""
                            return f"ਤੁਹਾਡਾ ਆਰਡਰ {data['order_id']} ਸਥਿਤੀ {data['status']} ਹੈ।{deliv_pa} ਟਰੈਕਿੰਗ ਨੰਬਰ: {data.get('tracking_number', 'N/A')}।"
                        elif is_odia:
                            deliv_od = f" ସମ୍ଭାବ୍ୟ ଡେଲିଭରୀ ତାରିଖ: {data['expected_delivery']}।" if data.get("expected_delivery") else ""
                            return f"ଆପଣଙ୍କ ଅର୍ଡର {data['order_id']} ସ୍ଥିତି {data['status']} ଅଟେ।{deliv_od} ଟ୍ରାକିଂ ନମ୍ବର: {data.get('tracking_number', 'N/A')}।"
                        elif is_urdu:
                            deliv_ur = f" متوقع ترسیل کی تاریخ: {data['expected_delivery']}۔" if data.get("expected_delivery") else ""
                            return f"آپ کا آرڈر {data['order_id']} کی حیثیت {data['status']} ہے۔{deliv_ur} ٹریکنگ نمبر: {data.get('tracking_number', 'N/A')}۔"
                        return f"Your order {data['order_id']} is currently {data['status']}. Expected delivery: {data.get('expected_delivery', 'N/A')}. Tracking: {data.get('tracking_number', 'N/A')}."
                    if "status" in data and "transaction_id" in data:
                        if is_tanglish:
                            return f"Unga transaction {data['transaction_id']} status {data['status']}. Amount: {data.get('amount', 'N/A')} {data.get('currency', 'INR')}."
                        elif is_tamil:
                            return f"உங்கள் பரிவர்த்தனை {data['transaction_id']} நிலை {data['status']}. தொகை: {data.get('amount', 'N/A')} {data.get('currency', 'INR')}."
                        elif is_hinglish:
                            return f"Aapka transaction {data['transaction_id']} status {data['status']} hai. Amount: {data.get('amount', 'N/A')} {data.get('currency', 'INR')}."
                        elif is_hindi:
                            return f"आपका लेनदेन {data['transaction_id']} स्थिति {data['status']} है। राशि: {data.get('amount', 'N/A')} {data.get('currency', 'INR')}।"
                        elif is_kanglish:
                            return f"Nimma transaction {data['transaction_id']} status {data['status']}. Amount: {data.get('amount', 'N/A')} {data.get('currency', 'INR')}."
                        elif is_kannada:
                            return f"ನಿಮ್ಮ ವಹಿವಾಟು {data['transaction_id']} ಸ್ಥಿತಿ {data['status']}. ಮೊತ್ತ: {data.get('amount', 'N/A')} {data.get('currency', 'INR')}."
                        elif is_tenglish:
                            return f"Mee transaction {data['transaction_id']} status {data['status']}. Amount: {data.get('amount', 'N/A')} {data.get('currency', 'INR')}."
                        elif is_telugu:
                            return f"మీ లావాదేవీ {data['transaction_id']} స్థితి {data['status']}. మొత్తం: {data.get('amount', 'N/A')} {data.get('currency', 'INR')}."
                        elif is_manglish:
                            return f"Ningalude transaction {data['transaction_id']} status {data['status']}. Amount: {data.get('amount', 'N/A')} {data.get('currency', 'INR')}."
                        elif is_malayalam:
                            return f"നിങ്ങളുടെ ഇടപാട് {data['transaction_id']} നില {data['status']}. തുക: {data.get('amount', 'N/A')} {data.get('currency', 'INR')}."
                        elif is_bengali or is_benglish:
                            return f"আপনার লেনদেন {data['transaction_id']} স্ট্যাটাস {data['status']}। পরিমাণ: {data.get('amount', 'N/A')} {data.get('currency', 'INR')}।"
                        elif is_marathi or is_marathish:
                            return f"तुमचा व्यवहार {data['transaction_id']} स्थिती {data['status']} आहे. रक्कम: {data.get('amount', 'N/A')} {data.get('currency', 'INR')}."
                        elif is_gujarati or is_gujlish:
                            return f"તમારો વ્યવહાર {data['transaction_id']} સ્થિતિ {data['status']} છે. રકમ: {data.get('amount', 'N/A')} {data.get('currency', 'INR')}."
                        elif is_punjabi or is_punglish:
                            return f"ਤੁਹਾਡਾ ਲੈਣ-ਦੇਣ {data['transaction_id']} ਸਥਿਤੀ {data['status']} ਹੈ। ਰਕਮ: {data.get('amount', 'N/A')} {data.get('currency', 'INR')}।"
                        elif is_odia:
                            return f"ଆପଣଙ୍କ ଟ୍ରାଞ୍ଜାକସନ {data['transaction_id']} ସ୍ଥିତି {data['status']} ଅଟେ। ରାଶି: {data.get('amount', 'N/A')} {data.get('currency', 'INR')}।"
                        elif is_urdu:
                            return f"آپ کی ٹرانزیکشن {data['transaction_id']} کی حیثیت {data['status']} ہے۔ رقم: {data.get('amount', 'N/A')} {data.get('currency', 'INR')}۔"
                        return f"Your transaction {data['transaction_id']} is currently {data['status']}. Amount: {data.get('amount', 'N/A')} {data.get('currency', 'INR')}."
                    if "ticket_id" in data:
                        return f"Ticket #{data['ticket_id']} — Status: {data.get('status', 'N/A')}, Priority: {data.get('priority', 'N/A')}."
                    if "full_name" in data:
                        return f"Account info — Name: {data['full_name']}, Email: {data.get('email', 'N/A')}."
                    if "message" in res:
                        return res["message"]
                    return f"Action completed successfully."
                elif res.get("success") is False:
                    err_code = res.get("error_code", "")
                    msg = str(res.get("message", ""))
                    if err_code == "ORDER_NOT_FOUND" or ("order" in msg.lower() and "not found" in msg.lower()):
                        if is_tanglish:
                            return "Andha Order ID-la entha details-um kedaikala. Kripya unga Order ID-ah check panni thirumba sollunga."
                        elif is_tamil:
                            return "அந்த ஆர்டர் எண்ணில் விவரங்கள் எதுவும் கிடைக்கவில்லை. உங்கள் ஆர்டர் ஐடியை சரிபார்த்து மீண்டும் கூறவும்."
                        elif is_hinglish:
                            return "Uss reference number ke saath order nahi mila. Kripya apna Order ID check karke dobara batayein."
                        elif is_hindi:
                            return "उस संदर्भ संख्या के साथ कोई ऑर्डर नहीं मिला। कृपया अपना ऑर्डर आईडी जांच कर दोबारा बताएं।"
                        elif is_kanglish:
                            return "Aa Order ID-nalli yavude details sigalilla. Dayavittu nimma Order ID check maadi mathomme thilisi."
                        elif is_kannada:
                            return "ಆ ಆರ್ಡರ್ ಸಂಖ್ಯೆಯೊಂದಿಗೆ ವಿವರಗಳು ಸಿಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ಆರ್ಡರ್ ಐಡಿ ಪರಿಶೀಲಿಸಿ ಮತ್ತೆ ತಿಳಿಸಿ."
                        elif is_tenglish:
                            return "Aa Order ID-lo emi details dorakaledu. Dayachesi mee Order ID check chesi malli cheppandi."
                        elif is_telugu:
                            return "ఆ ఆర్డర్ వివరాలు కనుగొనబడలేదు. దయచేసి మీ ఆర్డర్ ఐడిని సరిచూసి మళ్ళీ చెప్పండి."
                        elif is_manglish:
                            return "Aa Order ID-il details onnum kittiyilla. Dayavayi ningalude Order ID check cheythu veendum parayuka."
                        elif is_malayalam:
                            return "ആ ഓർഡർ വിവരങ്ങൾ കണ്ടെത്താനായില്ല. ദയവായി നിങ്ങളുടെ ഓർഡർ ഐഡി പരിശോധിച്ച് വീണ്ടും പറയുക."
                        elif is_bengali or is_benglish:
                            return "সেই অর্ডার নম্বর দিয়ে কোনো তথ্য পাওয়া যায়নি। অনুগ্রহ করে আপনার অর্ডার আইডি পুনরায় যাচাই করুন।"
                        elif is_marathi or is_marathish:
                            return "त्या संदर्भ क्रमांकाचा ऑर्डर सापडला नाही. कृपया तुमचा ऑर्डर आयडी तपासून पुन्हा सांगा."
                        elif is_gujarati or is_gujlish:
                            return "તે સંદર્ભ નંબર સાથેનો ઓર્ડર મળ્યો નથી. કૃપા કરીને તમારો ઓર્ડર આઈડી ચકાસીને ફરી જણાવો."
                        elif is_punjabi or is_punglish:
                            return "ਉਸ ਆਰਡਰ ਨੰਬਰ ਨਾਲ ਕੋਈ ਵੇਰਵਾ ਨਹੀਂ ਮਿਲਿਆ। ਕਿਰਪਾ ਕਰਕੇ ਆਪਣਾ ਆਰਡਰ ਆਈਡੀ ਚੈੱਕ ਕਰਕੇ ਦੁਬਾਰਾ ਦੱਸੋ।"
                        return "I couldn't find an order with that reference number. Could you please double-check your Order ID and provide it again?"
                    if err_code == "TRANSACTION_NOT_FOUND" or ("transaction" in msg.lower() and "not found" in msg.lower()):
                        if is_tanglish:
                            return "Andha transaction reference kedaikala. Unga transaction ID-ah check panni thirumba sollunga."
                        elif is_tamil:
                            return "அந்த பரிவர்த்தனை குறிப்பு கிடைக்கவில்லை. உங்கள் பரிவர்த்தனை ஐடியை சரிபார்த்து மீண்டும் கூறவும்."
                        elif is_hinglish:
                            return "Uss reference number ke saath transaction nahi mila. Kripya transaction ID check karke dobara batayein."
                        elif is_hindi:
                            return "उस संदर्भ संख्या के साथ लेनदेन नहीं मिला। कृपया ट्रांजैक्शन आईडी जांच कर दोबारा बताएं।"
                        elif is_kanglish:
                            return "Aa transaction details sigalilla. Dayavittu nimma transaction ID check maadi mathomme thilisi."
                        elif is_kannada:
                            return "ಆ ವಹಿವಾಟಿನ ವಿವರಗಳು ಸಿಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ಟ್ರಾನ್ಸಾಕ್ಷನ್ ಐಡಿ ಪರಿಶೀಲಿಸಿ ಮತ್ತೆ ತಿಳಿಸಿ."
                        elif is_tenglish:
                            return "Aa transaction details dorakaledu. Dayachesi mee transaction ID check chesi malli cheppandi."
                        elif is_telugu:
                            return "ఆ లావాదేవీ వివరాలు కనుగొనబడలేదు. దయచేసి మీ లావాదేవీ ఐడిని సరిచూసి మళ్ళీ చెప్పండి."
                        elif is_manglish:
                            return "Aa transaction details kittiyilla. Dayavayi ningalude transaction ID check cheythu veendum parayuka."
                        elif is_malayalam:
                            return "ആ ഇടപാട് വിവരങ്ങൾ കണ്ടെത്താനായില്ല. ദയവായി നിങ്ങളുടെ ട്രാൻസാക്ഷൻ ഐഡി പരിശോധിച്ച് വീണ്ടും പറയുക."
                        elif is_bengali or is_benglish:
                            return "সেই লেনদেনের বিবরণ পাওয়া যায়নি। অনুগ্রহ করে আপনার ট্রানজ্যাকশন আইডি যাচাই করে পুনরায় জানান।"
                        elif is_marathi or is_marathish:
                            return "त्या संदर्भ क्रमांकाचा व्यवहार सापडला नाही. कृपया तुमचा ट्रान्झॅक्शन आयडी तपासून पुन्हा सांगा."
                        elif is_gujarati or is_gujlish:
                            return "તે સંદર્ભ નંબર સાથેનો વ્યવહાર મળ્યો નથી. કૃપા કરીને ટ્રાન્ઝેક્શન આઈડી ચકાસીને ફરી જણાવો."
                        elif is_punjabi or is_punglish:
                            return "ਉਸ ਲੈਣ-ਦੇਣ ਦੇ ਵੇਰਵੇ ਨਹੀਂ ਮਿਲੇ। ਕਿਰਪਾ ਕਰਕੇ ਆਪਣਾ ਟ੍ਰਾਂਜੈਕਸ਼ਨ ਆਈਡੀ ਚੈੱਕ ਕਰਕੇ ਦੁਬਾਰਾ ਦੱਸੋ।"
                        return "I couldn't find a transaction with that reference number. Could you please double-check your transaction ID and provide it again?"
                    if err_code == "TICKET_NOT_FOUND" or ("ticket" in msg.lower() and "not found" in msg.lower()):
                        return "I couldn't find a support ticket with that ID number. Could you please verify the ticket number?"
                    if err_code == "ACCESS_DENIED" or "permission" in msg.lower():
                        return "I am unable to access details for that record with your current account. Could you please verify your account details?"
                    return f"I wasn't able to complete that: {msg or 'Unknown error'}."
                elif res.get("status") == "success":
                    if "message" in res:
                        return res["message"] + (f" Refund ID: {res.get('refund_id')}" if res.get("refund_id") else "")
                    return f"Your transaction is currently {res.get('transaction_status')}. Amount: {res.get('amount')} {res.get('currency')}."
                else:
                    return f"Action failed: {res.get('message', 'Unknown error')}."
            if is_tanglish:
                return "Oru nimisham, check panni solren..."
            elif is_tamil:
                return "ஒரு நிமிடம், சரிபார்த்து கூறுகிறேன்..."
            elif is_hinglish:
                return "Ek second, main check karke batata hoon..."
            elif is_hindi:
                return "एक मिनट, मैं जांच कर बताता हूँ..."
            elif is_kanglish:
                return "Ondu nimisha, check maadi helthini..."
            elif is_kannada:
                return "ಒಂದು ಕ್ಷಣ, ಪರಿಶೀಲಿಸಿ ತಿಳಿಸುತ್ತೇನೆ..."
            elif is_tenglish:
                return "Okka kshanam, check chesi chepthanu..."
            elif is_telugu:
                return "ఒక్క క్షణం, తనిఖీ చేసి చెబుతాను..."
            elif is_manglish:
                return "Oru nimesham, check cheythu parayam..."
            elif is_malayalam:
                return "ഒരു നിമിഷം, പരിശോധിച്ച് പറയാം..."
            elif is_bengali or is_benglish:
                return "এক মিনিট, আমি যাচাই করে জানাচ্ছি..."
            elif is_marathi or is_marathish:
                return "एक मिनिट, मी तपासून सांगतो..."
            elif is_gujarati or is_gujlish:
                return "એક મિનિટ, હું તપાસીને જણાવું છું..."
            elif is_punjabi or is_punglish:
                return "ਇੱਕ ਮਿੰਟ, ਮੈਂ ਚੈੱਕ ਕਰਕੇ ਦੱਸਦਾ ਹਾਂ..."
            elif is_odia:
                return "ଗୋଟିଏ ମିନିଟ୍, ମୁଁ ଯାଞ୍ଚ କରି ଜଣାଉଛି..."
            elif is_urdu:
                return "ایک لمحہ، میں چیک کر کے بتاتا ہوں۔"
            return "Let me check that for you..."

        if decision == "ESCALATE":
            if is_tanglish:
                return "Ungal request-ah namma support team-kku connect panni irukken. Oru human expert seekiram join pannuvaanga."
            elif is_tamil:
                return "உங்கள் கோரிக்கையை எங்கள் உதவி குழுவிற்கு இணைத்துள்ளேன். ஒரு மனித நிபுணர் விரைவில் இணைவார்."
            elif is_hinglish:
                return "Main aapki request support team ko transfer kar raha hoon. Ek expert jaldi hi join karega."
            elif is_hindi:
                return "मैंने आपके अनुरोध को सहायता टीम से जोड़ दिया है। एक विशेषज्ञ जल्द ही शामिल होंगे।"
            elif is_kanglish:
                return "Nimma request-na namma support team-ge connect madiddini. Obba expert thakshana join madthare."
            elif is_kannada:
                return "ನಿಮ್ಮ ವಿನಂತಿಯನ್ನು ನಮ್ಮ ಬೆಂಬಲ ತಂಡಕ್ಕೆ ವರ್ಗಾಯಿಸಲಾಗಿದೆ. ಒಬ್ಬ ಪರಿಣಿತರು ಶೀಘ್ರದಲ್ಲೇ ಸಂಪರ್ಕಿಸುತ್ತಾರೆ."
            elif is_tenglish:
                return "Mee request-ni maa support team-ki transfer chestunnanu. Oka expert twaralo join avutaru."
            elif is_telugu:
                return "మీ అభ్యర్థనను మా సపోర్ట్ బృందానికి బదిలీ చేస్తున్నాను. ఒక నిపుణుడు త్వరలోనే కనెక్ట్ అవుతారు."
            elif is_manglish:
                return "Ningalude request njangalude support team-lekku transfer cheythirikkunnu. Oru expert udane join cheyyum."
            elif is_malayalam:
                return "നിങ്ങളുടെ അഭ്യർത്ഥന ഞങ്ങളുടെ സപ്പോർട്ട് ടീമിന് കൈമാറി. ഒരു വിദഗ്ദ്ധൻ ഉടൻ തന്നെ ബന്ധപ്പെടും."
            elif is_bengali or is_benglish:
                return "আপনার অনুরোধটি আমাদের সাপোর্ট টিমে স্থানান্তর করা হয়েছে। একজন বিশেষজ্ঞ শীঘ্রই যুক্ত হবেন।"
            elif is_marathi or is_marathish:
                return "मी तुमची विनंती आमच्या सहाय्यक टीमकडे हस्तांतरित करत आहे. एक तज्ज्ञ लवकरच संपर्क करतील."
            elif is_gujarati or is_gujlish:
                return "હું તમારી વિનંતી સપોર્ટ ટીમને ટ્રાન્સફર કરી રહ્યો છું. એક નિષ્ણાત ટૂંક સમયમાં જોડાશે."
            elif is_punjabi or is_punglish:
                return "ਮੈਂ ਤੁਹਾਡੀ ਬੇਨਤੀ ਸਹਾਇਤਾ ਟੀਮ ਨੂੰ ਟਰਾਂਸਫਰ ਕਰ ਰਿਹਾ ਹਾਂ। ਇੱਕ ਮਾਹਰ ਜਲਦੀ ਹੀ ਸ਼ਾਮਲ ਹੋਵੇਗਾ।"
            elif is_odia:
                return "ଆପଣଙ୍କ ଅନୁରୋଧକୁ ଆମର ସହାୟତା ଟିମକୁ ପଠାଯାଇଛି। ଜଣେ ବିଶେଷଜ୍ଞ ଶୀଘ୍ର ଯୋଗଦେବେ।"
            elif is_urdu:
                return "میں نے آپ کی درخواست سپورٹ ٹیم کو منتقل کر دی ہے۔ ایک ماہر جلد ہی شامل ہوں گے۔"
            return "I've connected your request to our support team. An expert will join shortly."
            
        if decision == "ASK_USER":
            missing = decision_obj.get("missing_entity")
            item_term = decision_obj.get("customer_item_term") or decision_obj.get("diagnostic_details", {}).get("customer_item_term", "order")
            
            if missing == "empathy_checkin":
                if is_tanglish:
                    return "Ungal thagavalukku romba varuthapadugirom. Ungal issue-ah solve panna naan ready-aa irukken, illa oru human expert-kku connect panna vaa?"
                elif is_hinglish:
                    return "Humein khed hai ki aapko pareshani hui. Main is samasya ko solve karne ke liye poori koshish karunga, ya agar aap chahein toh expert se connect kar sakta hoon."
                elif is_tamil:
                    return "உங்களுக்கு ஏற்பட்ட சிரமத்திற்கு வருந்துகிறோம். உங்கள் பிரச்சினையை தீர்க்க நான் உதவுகிறேன், அல்லது ஒரு மனித நிபுணரிடம் இணைக்க வேண்டுமா?"
                elif is_hindi:
                    return "आपको हुई असुविधा के लिए हमें खेद है। मैं आपकी समस्या को हल करने में मदद करूँगा, या क्या आप किसी विशेषज्ञ से बात करना चाहते हैं?"
                elif is_kanglish:
                    return "Nimma problem-ge thumba kshame kelthivi. Nanu solve madla athava expert-ge connect madla?"
                elif is_kannada:
                    return "ನಿಮಗೆ ಉಂಟಾದ ಅನಾನುಕೂಲತೆಗೆ ನಾವು ಕ್ಷಮೆಯಾಚಿಸುತ್ತೇವೆ. ನಾನು ನಿಮಗೆ ಸಹಾಯ ಮಾಡಲೆ ಅಥವಾ ಮಾನವ ತಜ್ಞರೊಂದಿಗೆ ಸಂಪರ್ಕಿಸಬೇಕೆ?"
                elif is_tenglish:
                    return "Meeku kaligina asaukaryaniki kshaminchandi. Nenu solve cheyyana leda expert-tho matladathara?"
                elif is_telugu:
                    return "మీకు కలిగిన అసౌకర్యానికి చింతిస్తున్నాము. నేను మీకు సహాయం చేయనా లేదా ఒక నిపుణుడితో మాట్లాడతారా?"
                elif is_manglish:
                    return "Ningalkkundaaya vishamakkarathil kshama chodikkunnu. Njan help cheyyano atho expert-ne connect cheyyano?"
                elif is_malayalam:
                    return "നിങ്ങൾക്കുണ്ടായ ബുദ്ധിമുട്ടിൽ ഞങ്ങൾ ക്ഷമ ചോദിക്കുന്നു. ഞാൻ സഹായിക്കണോ അതോ വിദഗ്ദ്ധനുമായി ബന്ധിപ്പിക്കണമെന്നുണ്ടോ?"
                elif is_bengali or is_benglish:
                    return "আপনার অসুবিধার জন্য আমরা দুঃখিত। আমি কি সাহায্য করব নাকি বিশেষজ্ঞের সাথে কথা বলবেন?"
                elif is_marathi or is_marathish:
                    return "झालेल्या त्रासाबद्दल आम्ही दिलगीर आहोत. मी मदत करू की तज्ज्ञांशी संपर्क साधू?"
                elif is_gujarati or is_gujlish:
                    return "તમને થયેલી અસુવિધા માટે અમે દિલગીર છીએ. હું મદદ કરું કે નિષ્ણાત સાથે જોડું?"
                elif is_punjabi or is_punglish:
                    return "ਤੁਹਾਨੂੰ ਹੋਈ ਪਰੇਸ਼ਾਨੀ ਲਈ ਸਾਨੂੰ ਅਫ਼ਸੋਸ ਹੈ। ਕੀ ਮੈਂ ਮਦਦ ਕਰਾਂ ਜਾਂ ਮਾਹਰ ਨਾਲ ਗੱਲ ਕਰੋਗੇ?"
                return "I completely understand your frustration and apologize for the inconvenience. I'm here to help sort this out, or I can connect you directly with a human expert if you prefer."
            if missing == "empathetic_delay_inquiry":
                if is_tanglish:
                    return "Delivery delay aagardhuku romba varuthapadugirom bro. Unga order details-ah udane track panni enna aachu nu paarka, unga Order ID-ah share panna mudiyuma?"
                elif is_hinglish:
                    return "Delivery mein deri ke liye humein khed hai. Main turant courier status check karke batata hoon, kripya apna Order ID share kar sakte hain?"
                elif is_tamil:
                    return "டெலிவரி தாமதத்திற்கு வருந்துகிறோம். உங்கள் ஆர்டர் நிலையை உடனடியாக சரிபார்க்க, உங்கள் ஆர்டர் ஐடியைப் பகிர முடியுமா?"
                elif is_hindi:
                    return "डिलीवरी में देरी के लिए हमें खेद है। मैं तुरंत स्थिति की जांच करता हूँ, क्या आप अपना ऑर्डर आईडी बता सकते हैं?"
                elif is_kanglish:
                    return "Delivery delay aagiddakke thumba kshame kelthivi. Courier status check maadi thilisoke nimma Order ID share madthira?"
                elif is_kannada:
                    return "ಡೆಲಿವರಿ ವಿಳಂಬಕ್ಕೆ ಕ್ಷಮೆಯಿರಲಿ. ನಿಮ್ಮ ಆರ್ಡರ್ ಸ್ಥಿತಿಯನ್ನು ಪರಿಶೀಲಿಸಲು ನಿಮ್ಮ ಆರ್ಡರ್ ಐಡಿಯನ್ನು ಹಂಚಿಕೊಳ್ಳಬಹುದೇ?"
                elif is_tenglish:
                    return "Delivery late ainanduku kshaminchandi. Courier status check chesi cheppadaniki mee Order ID share chestara?"
                elif is_telugu:
                    return "డెలివరీ ఆలస్యమైనందుకు క్షమించండి. కొరియర్ స్థితిని తనిఖీ చేయడానికి మీ ఆర్డర్ ఐడిని షేర్ చేయగలరా?"
                elif is_manglish:
                    return "Delivery late aayathil kshama chodikkunnu. Courier status check cheyyan ningalude Order ID share cheyyamo?"
                elif is_malayalam:
                    return "ഡെലിവറി വൈകിയതിൽ ഞങ്ങൾ ക്ഷമ ചോദിക്കുന്നു. കൊറിയർ സ്റ്റാറ്റസ് പരിശോധിക്കാൻ നിങ്ങളുടെ ഓർഡർ ഐഡി പങ്കിടാമോ?"
                elif is_bengali or is_benglish:
                    return "ডেলিভারিতে বিলম্বের জন্য আমরা দুঃখিত। কুরিয়ার স্ট্যাটাস পরীক্ষা করতে আপনার অর্ডার আইডি জানাতে পারেন?"
                elif is_marathi or is_marathish:
                    return "डिलिव्हरी उशिरा झाल्याबद्दल आम्ही दिलगीर आहोत. त्वरित स्थिती तपासण्यासाठी तुमचा ऑर्डर आयडी सांगू शकाल का?"
                elif is_gujarati or is_gujlish:
                    return "ડિલિવરીમાં વિલંબ બદલ અમે દિલગીર છીએ. કુરિયર સ્થિતિ તપાસવા માટે તમારો ઓર્ડર આઈડી આપી શકો છો?"
                elif is_punjabi or is_punglish:
                    return "ਡਿਲਿਵਰੀ ਵਿੱਚ ਦੇਰੀ ਲਈ ਸਾਨੂੰ ਅਫ਼ਸੋਸ ਹੈ। ਸਥਿਤੀ ਚੈੱਕ ਕਰਨ ਲਈ ਕਿਰਪਾ ਕਰਕੇ ਆਪਣਾ ਆਰਡਰ ਆਈਡੀ ਸਾਂਝਾ ਕਰੋਗੇ?"
                return "I'm very sorry for the delay with your delivery. Let me check the courier status immediately—could you please share your Order ID so I can track it?"
            if missing == "handoff_confirmation":
                if is_tanglish:
                    return "Ungal issue-ah solve panna namma human expert kitta connect pannattuma? (Aama / Vendaam nu sollunga)"
                elif is_hinglish:
                    return "Kya main aapko hamare human expert se connect kar doon? (Haan ya Nahi batayein)"
                elif is_tamil:
                    return "உங்களுக்கு உதவ எங்கள் மனித நிபுணரிடம் இணைக்க வேண்டுமா? (ஆம் / வேண்டாம் என்று கூறவும்)"
                elif is_hindi:
                    return "क्या मैं आपको हमारे विशेषज्ञ से जोड़ दूँ? (हाँ या नहीं बताएं)"
                elif is_kanglish:
                    return "Nimma issue solve madoke human expert jothe connect madla? ('Haudu' athava 'Illa' antha heli)"
                elif is_kannada:
                    return "ನಿಮಗೆ ಸಹಾಯ ಮಾಡಲು ಮಾನವ ತಜ್ಞರೊಂದಿಗೆ ಸಂಪರ್ಕಿಸಬೇಕೆ? (ದಯವಿಟ್ಟು ಹೌದು ಅಥವಾ ಇಲ್ಲ ಎಂದು ತಿಳಿಸಿ)"
                elif is_tenglish:
                    return "Mee issue solve cheyadaniki human expert-to connect cheyyocha? ('Avunu' leda 'Kaadu' ani cheppandi)"
                elif is_telugu:
                    return "మీకు సహాయం చేయడానికి మానవ నిపుణుడితో కనెక్ట్ చేయమంటారా? (దయచేసి అవును లేదా కాదు అని చెప్పండి)"
                elif is_manglish:
                    return "Ningalude issue solve cheyyan human expert-umayi connect cheyyano? ('Athe' athava 'Alla' ennu parayuka)"
                elif is_malayalam:
                    return "നിങ്ങളെ സഹായിക്കാൻ ഒരു വിദഗ്ദ്ധനുമായി ബന്ധിപ്പിക്കണമെന്നുണ്ടോ? (ദയവായി അതെ അല്ലെങ്കിൽ അല്ല എന്ന് മറുപടി നൽകുക)"
                elif is_bengali or is_benglish:
                    return "আপনাকে সহায়তা করার জন্য আমি কি একজন মানব বিশেষজ্ঞের সাথে সংযুক্ত করব? (হ্যাঁ অথবা না বলুন)"
                elif is_marathi or is_marathish:
                    return "तुम्हाला मदत करण्यासाठी मानवी तज्ज्ञांशी संपर्क साधू का? (कृपया होय किंवा नाही सांगा)"
                elif is_gujarati or is_gujlish:
                    return "તમને મદદ કરવા માટે શું હું તમને નિષ્ણાત સાથે જોડી આપું? (કૃપા કરીને હા અથવા ના કહો)"
                elif is_punjabi or is_punglish:
                    return "ਕੀ ਮੈਂ ਤੁਹਾਡੀ ਮਦਦ ਲਈ ਮਾਹਰ ਨਾਲ ਸੰਪਰਕ ਕਰਾਵਾਂ? (ਕਿਰਪਾ ਕਰਕੇ ਹਾਂ ਜਾਂ ਨਹੀਂ ਦੱਸੋ)"
                return "Would you like me to connect you with a human expert to assist you? (Please reply Yes or No)"
            if missing == "handoff_unclear":
                if is_tanglish:
                    return "Puriyavillai. Human expert-kku connect panna venuma? 'Aama' illa 'Vendaam' nu sollunga."
                elif is_hinglish:
                    return "Samajh nahi paaya. Kya aap human expert se connect hona chahte hain? Kripya 'Haan' ya 'Nahi' batayein."
                elif is_tamil:
                    return "புரியவில்லை. மனித நிபுணரிடம் இணைக்க வேண்டுமா? 'ஆம்' அல்லது 'வேண்டாம்' என்று கூறவும்."
                elif is_hindi:
                    return "स्पष्ट नहीं हुआ। क्या आप विशेषज्ञ से जुड़ना चाहते हैं? कृपया 'हाँ' या 'नहीं' बताएं।"
                elif is_kanglish or is_kannada:
                    return "Thiliyavillilla. Namma expert-ge connect madla? 'Haudu' athava 'Illa' antha heli."
                elif is_tenglish or is_telugu:
                    return "Ardham kaledu. Human expert-to connect cheyyamantara? 'Avunu' leda 'Kaadu' ani cheppandi."
                elif is_manglish or is_malayalam:
                    return "Manasilayilla. Expert-umayi connect cheyyano? 'Athe' athava 'Alla' ennu parayuka."
                return "I didn't quite catch that. Would you like to be connected to a human expert? Please reply 'Yes' or 'No'."
            if missing == "transaction_id":
                if is_tanglish:
                    return "Kandippa, unga transaction ID sollunga, naan check panren."
                elif is_tamil:
                    return "நிச்சயமாக, உங்கள் பரிவர்த்தனை ஐடியைக் கூறுங்கள், நான் சரிபார்க்கிறேன்."
                elif is_hinglish:
                    return "Kripya apna transaction ID batayein, main check karta hoon."
                elif is_hindi:
                    return "कृपया अपना ट्रांजैक्शन आईडी बताएं, मैं जांच करता हूँ।"
                elif is_kanglish:
                    return "Kanditha, nimma transaction ID thilisi, nanu check madthini."
                elif is_kannada:
                    return "ದಯವಿಟ್ಟು ನಿಮ್ಮ ಟ್ರಾನ್ಸಾಕ್ಷನ್ ಐಡಿ ತಿಳಿಸಿ, ನಾನು ಪರಿಶೀಲಿಸುತ್ತೇನೆ."
                elif is_tenglish:
                    return "Kachithanga, mee transaction ID cheppandi, nenu check chestanu."
                elif is_telugu:
                    return "దయచేసి మీ లావాదేవీ (ట్రాన్సాక్షన్) ఐడిని చెప్పండి, నేను తనిఖీ చేస్తాను."
                elif is_manglish:
                    return "Theerchayayum, ningalude transaction ID parayamo, njan check cheyyam."
                elif is_malayalam:
                    return "ദയവായി നിങ്ങളുടെ ട്രാൻസാക്ഷൻ ഐഡി നൽകുക, ഞാൻ പരിശോധിക്കാം."
                elif is_bengali or is_benglish:
                    return "দয়া করে আপনার ট্রানজ্যাকশন আইডি প্রদান করুন, আমি যাচাই করে দেখছি।"
                elif is_marathi or is_marathish:
                    return "कृपया तुमचा ट्रान्झॅक्शन आयडी सांगा, मी तपासतो."
                elif is_gujarati or is_gujlish:
                    return "કૃપા કરીને તમારો ટ્રાન્ઝેક્શન આઈડી જણાવો, હું તપાસ કરું છું."
                elif is_punjabi or is_punglish:
                    return "ਕਿਰਪਾ ਕਰਕੇ ਆਪਣਾ ਟ੍ਰਾਂਜੈਕਸ਼ਨ ਆਈਡੀ ਦੱਸੋ, ਮੈਂ ਚੈੱਕ ਕਰਦਾ ਹਾਂ।"
                return "Could you provide your transaction ID?"
            if missing == "order_id":
                if is_tanglish:
                    if item_term and item_term != "order":
                        return f"Kandippa! Unga {item_term} delivery status check panna Order ID sollunga bro, naan udane check panni solren."
                    return "Kandippa! Unga Order ID sollunga, naan udane check panni solren."
                elif is_tamil:
                    if item_term and item_term != "order":
                        return f"நிச்சயமாக! உங்கள் {item_term} நிலையை அறிய ஆர்டர் ஐடியைக் கூறுங்கள்."
                    return "நிச்சயமாக! உங்கள் ஆர்டர் ஐடியைக் கூறுங்கள், நான் சரிபார்க்கிறேன்."
                elif is_hinglish:
                    if item_term and item_term != "order":
                        return f"Zaroor! Aapke {item_term} ka status check karne ke liye kripya apna Order ID batayein, main status check karta hoon."
                    return "Zaroor! Kripya apna Order ID batayein, main status check karta hoon."
                elif is_hindi:
                    if item_term and item_term != "order":
                        return f"ज़रूर! आपके {item_term} की स्थिति देखने के लिए कृपया अपना ऑर्डर आईडी बताएं।"
                    return "ज़रूर! कृपया अपना ऑर्डर आईडी बताएं, मैं जांच करता हूँ।"
                elif is_kanglish:
                    if item_term and item_term != "order":
                        return f"Kanditha! Nimma {item_term} status check madoke Order ID thilisi."
                    return "Kanditha! Nimma Order ID thilisi, nanu check madthini."
                elif is_kannada:
                    if item_term and item_term != "order":
                        return f"ಖಂಡಿತ! ನಿಮ್ಮ {item_term} ಸ್ಥಿತಿಯನ್ನು ಪರಿಶೀಲಿಸಲು ದಯವಿಟ್ಟು ನಿಮ್ಮ ಆರ್ಡರ್ ಐಡಿ ತಿಳಿಸಿ."
                    return "ಖಂಡಿತ! ನಿಮ್ಮ ಆರ್ಡರ್ ಸ್ಥಿತಿಯನ್ನು ಪರಿಶೀಲಿಸಲು ದಯವಿಟ್ಟು ನಿಮ್ಮ ಆರ್ಡರ್ ಐಡಿ ತಿಳಿಸಿ."
                elif is_tenglish:
                    if item_term and item_term != "order":
                        return f"Kachithanga! Mee {item_term} status check cheyadaniki Order ID cheppandi."
                    return "Kachithanga! Mee Order ID cheppandi, nenu check chestanu."
                elif is_telugu:
                    if item_term and item_term != "order":
                        return f"ఖచ్చితంగా! మీ {item_term} స్థితిని తనిఖీ చేయడానికి దయచేసి మీ ఆర్డర్ ఐడిని తెలియజేయండి."
                    return "ఖచ్చితంగా! మీ ఆర్ಡర్ స్థితిని తనిఖీ చేయడానికి దయచేసి మీ ఆర్ಡర్ ఐడిని తెలియజేయండి."
                elif is_manglish:
                    if item_term and item_term != "order":
                        return f"Theerchayayum! Ningalude {item_term} status check cheyyan Order ID parayamo?"
                    return "Theerchayayum! Ningalude Order ID parayamo, njan check cheyyam."
                elif is_malayalam:
                    if item_term and item_term != "order":
                        return f"തീർച്ചയായും! നിങ്ങളുടെ {item_term} നില പരിശോധിക്കാൻ ദയവായി ഓർഡർ ഐഡി നൽകുക."
                    return "തീർച്ചയായും! നിങ്ങളുടെ ഓർഡർ നില പരിശോധിക്കാൻ ദയവായി ഓർഡർ ഐഡി നൽകുക."
                elif is_bengali or is_benglish:
                    if item_term and item_term != "order":
                        return f"নিশ্চয়ই! আপনার {item_term} স্ট্যাটাস পরীক্ষা করতে অনুগ্রহ করে আপনার অর্ডার আইডি প্রদান করুন।"
                    return "নিশ্চয়ই! আপনার অর্ডার স্ট্যাটাস পরীক্ষা করতে অনুগ্রহ করে আপনার অর্ডার আইডি প্রদান করুন।"
                elif is_marathi or is_marathish:
                    if item_term and item_term != "order":
                        return f"नक्कीच! तुमच्या {item_term} ची स्थिती तपासण्यासाठी कृपया तुमचा ऑर्डर आयडी सांगा."
                    return "नक्कीच! तुमच्या ऑर्डरची स्थिती तपासण्यासाठी कृपया तुमचा ऑर्डर आयडी सांगा."
                elif is_gujarati or is_gujlish:
                    if item_term and item_term != "order":
                        return f"ચોક્કસ! તમારા {item_term} ની સ્થિતિ તપાસવા માટે કૃપા કરીને તમારો ઓર્ડર આઈડી જણાવો."
                    return "ચોક્કસ! તમારા ઓર્ડરની સ્થિતિ તપાસવા માટે કૃપા કરીને તમારો ઓર્ડર આઈડી જણાવો."
                elif is_punjabi or is_punglish:
                    if item_term and item_term != "order":
                        return f"ਬਿਲਕੁਲ! ਤੁਹਾਡੇ {item_term} ਦੀ ਸਥਿਤੀ ਚੈੱਕ ਕਰਨ ਲਈ ਕਿਰਪਾ ਕਰਕੇ ਆਪਣਾ ਆਰਡਰ ਆਈਡੀ ਦੱਸੋ।"
                    return "ਬਿਲਕੁਲ! ਤੁਹਾਡੇ ਆਰਡਰ ਦੀ ਸਥਿਤੀ ਚੈੱਕ ਕਰਨ ਲਈ ਕਿਰਪਾ ਕਰਕੇ ਆਪਣਾ ਆਰਡਰ ਆਈਡੀ ਦੱਸੋ।"
                if item_term and item_term != "order":
                    return f"Sure! Could you please provide your Order ID so I can check the status of your {item_term} for you?"
                return "Could you please provide your Order ID?"
            if missing == "order_id_reason":
                if is_tanglish:
                    return "Unga order details and live tracking status check panna Order ID theva padudhu bro. Ungalukku vandha SMS illa email-la ORD- number irukkum, adha share pannunga."
                elif is_tamil:
                    return "உங்கள் ஆர்டர் விவரங்கள் மற்றும் நேரடி டெலிவரி நிலையைச் சரிபார்க்க Order ID தேவைப்படுகிறது. உங்கள் SMS அல்லது மின்னஞ்சலில் உள்ள ORD- எண்ணைப் பகிருங்கள்."
                elif is_hinglish:
                    return "Aapke order details aur live tracking status check karne ke liye Order ID ki zaroorat hoti hai. SMS ya email mein mila ORD- number share karein."
                elif is_hindi:
                    return "आपके ऑर्डर विवरण और ट्रैकिंग स्थिति की जांच के लिए Order ID की आवश्यकता होती है। कृपया अपने SMS या ईमेल से ORD- नंबर साझा करें।"
                elif is_kanglish or is_kannada:
                    return "Nimma order details mathu live tracking status check madoke Order ID beku. SMS athava email-nalli iro ORD- number thilisi."
                elif is_tenglish or is_telugu:
                    return "Mee order details mariyu live tracking status check cheyadaniki Order ID avasaram. SMS leda email lo unna ORD- number cheppandi."
                elif is_manglish or is_malayalam:
                    return "Ningalude order details live tracking status check cheyyan Order ID aavashyamaanu. SMS allenkil email-il ulla ORD- number parayamo."
                elif is_bengali or is_benglish:
                    return "আপনার অর্ডারের বিবরণ এবং লাইভ ট্র্যাকিং স্ট্যাটাস যাচাই করতে Order ID প্রয়োজন। অনুগ্রহ করে আপনার SMS বা ইমেলে থাকা ORD- নম্বরটি জানান।"
                elif is_marathi or is_marathish:
                    return "तुमच्या ऑर्डरचे तपशील आणि लाईव्ह ट्रॅकिंग स्टेटस तपासण्यासाठी Order ID आवश्यक आहे. कृपया SMS किंवा ईमेलमध्ये आलेला ORD- क्रमांक सांगा."
                elif is_gujarati or is_gujlish:
                    return "તમારા ઓર્ડરની વિગતો અને લાઈવ ટ્રેકિંગ સ્ટેટસ તપાસવા માટે Order ID ની જરૂર છે. કૃપા કરીને SMS અથવા ઇમેઇલમાંથી ORD- નંબર જણાવો."
                elif is_punjabi or is_punglish:
                    return "ਤੁਹਾਡੇ ਆਰਡਰ ਦੇ ਵੇਰਵੇ ਅਤੇ ਲਾਈਵ ਟ੍ਰੈਕਿੰਗ ਸਥਿਤੀ ਚੈੱਕ ਕਰਨ ਲਈ Order ID ਦੀ ਲੋੜ ਹੈ। ਕਿਰਪਾ ਕਰਕੇ SMS ਜਾਂ ਈਮੇਲ ਵਿੱਚ ਆਇਆ ORD- ਨੰਬਰ ਦੱਸੋ।"
                return "An Order ID (e.g. ORD-12345) is needed to look up your order details, tracking status, and account in our system. You can find it in your confirmation SMS or email."
            if missing == "greeting":
                if is_tanglish:
                    return "Vanakkam! Ungaluku naan eppadi udhava mudiyum?"
                elif is_tamil:
                    return "வணக்கம்! நான் உங்களுக்கு எவ்வாறு உதவ முடியும்?"
                elif is_hinglish or is_hindi:
                    return "Namaste! Main aapki kya madad kar sakta hoon?"
                elif is_kanglish:
                    return "Namaskara! Naanu nimage hege sahayavagali?"
                elif is_kannada:
                    return "ನಮಸ್ಕಾರ! ಇಂದು ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?"
                elif is_tenglish:
                    return "Namaskaram! Nenu meeku ela sahayapadagalanu?"
                elif is_telugu:
                    return "నమస్కారం! నేను మీకు ఈరోజు ఎలా సహాయపడగలను?"
                elif is_manglish:
                    return "Namaskaram! Njan ningale engane sahayikkanam?"
                elif is_malayalam:
                    return "നമസ്കാരം! ഇന്ന് ഞാൻ നിങ്ങളെ എങ്ങനെ സഹായിക്കണം?"
                elif is_bengali or is_benglish:
                    return "নমস্কার! আজ আমি আপনাকে কীভাবে সাহায্য করতে পারি?"
                elif is_marathi or is_marathish:
                    return "नमस्कार! आज मी तुम्हाला कशी मदत करू शकतो?"
                elif is_gujarati or is_gujlish:
                    return "નમસ્તે! આજે હું તમને કેવી રીતે મદદ કરી શકું?"
                elif is_punjabi or is_punglish:
                    return "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ! ਅੱਜ ਮੈਂ ਤੁਹਾਡੀ ਕਿਵੇਂ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ?"
                elif is_odia:
                    return "ନମସ୍କାର! ଆଜି ମୁଁ ଆପଣଙ୍କୁ କିପରି ସାହାଯ୍ୟ କରିପାରିବି?"
                elif is_assamese:
                    return "নমস্কাৰ! আজি মই আপোনাক কেনেকৈ সহায় কৰিব পাৰোঁ?"
                elif is_urdu:
                    return "آداب! آج میں آپ کی کیا مدد کر سکتا ہوں؟"
                return "Hello! How can I help you today?"
            if missing == "reconsider_question":
                if is_tanglish:
                    return "Mannikkavum! Naan ungal kelviyai thappa purinjikitten. Ungalukku enna theva nu sollunga, naan kavanama check panren."
                elif is_hinglish:
                    return "Maaf kijiye! Lagta hai main aapka sawal galat samajh gaya. Kripya batayein aapko kya jankari chahiye, main madad karta hoon."
                elif is_tamil:
                    return "மன்னிக்கவும்! உங்கள் கேள்வியை தவறாக புரிந்து கொண்டேன். உங்களுக்கு என்ன உதவி தேவை என்று கூறுங்கள், நான் உதவுகிறேன்."
                elif is_hindi:
                    return "माफ़ कीजिए! शायद मैं आपका सवाल गलत समझ गया। कृपया बताएं कि आपको क्या मदद चाहिए।"
                return "I apologize for misunderstanding your question. Could you please tell me what you need assistance with, and I'll help you directly?"
            if missing in ("unclear", "clarification"):
                if is_tanglish:
                    return "Mannikkavum, ungal kelvi puriyavillai. Enna problem nu konjam vilakkamaaga solla mudiyuma?"
                elif is_hinglish:
                    return "Maaf kijiye, samajh nahi paaya. Kya aap apni samasya ke baare mein thoda aur bata sakte hain?"
                return "I'm sorry, I didn't quite understand that. Could you please clarify what you need assistance with?"
            if missing == "specific_issue":
                if is_tanglish:
                    return "Ungal issue pathi innum konjam details solla mudiyuma?"
                elif is_hinglish:
                    return "Kya aap apni samasya ke baare mein thoda aur bata sakte hain?"
                return "I don't have information on that. Could you provide more details about your support issue?"
            if is_tanglish:
                return "Ungal kelviyai konjam vilakkamaaga solla mudiyuma?"
            return "Could you provide more details so I can assist you better?"
            
        if decision == "RESOLVE":
            action_type = decision_obj.get("action_type")
            article = decision_obj.get("article", {})
            title = str(article.get("title", "")).lower() if isinstance(article, dict) else ""
            content = str(article.get("content", "")) if isinstance(article, dict) else ""

            if action_type == "policy_overview":
                policy_type = decision_obj.get("policy_type") or decision_obj.get("diagnostic_details", {}).get("policy_type", "")
                if policy_type == "return":
                    if is_tanglish:
                        return f"Namma return policy padi, {item_term} delivery aana date-la irundhu 30 days kulla neenga return panna mudiyum bro. Items original condition-la irundha full refund process panniduvom."
                    elif is_tamil:
                        return "நமது Return Policy-ன் படி, டெலிவரி செய்யப்பட்ட 30 நாட்களுக்குள் பொருட்களை திரும்ப அளிக்கலாம். அசல் நிலையில் இருந்தால் முழு கட்டணமும் திரும்பப் பெறலாம்."
                    elif is_hinglish:
                        return f"ResolveMart return policy ke anusaar, delivery ke 30 dinon ke andar aap apna {item_term} return kar sakte hain. Item original condition mein hona chahiye."
                    elif is_hindi:
                        return "ResolveMart रिटर्न पॉलिसी के अनुसार, डिलीवरी के 30 दिनों के भीतर आप रिटर्न कर सकते हैं।"
                    elif is_kanglish:
                        return f"Namma return policy prakara, {item_term} delivery aada 30 dinagala olage return madbahudu. Original condition-nalli idhre full refund siguthe."
                    elif is_kannada:
                        return "ನಮ್ಮ ರಿಟರ್ನ್ ಪಾಲಿಸಿಯ ಪ್ರಕಾರ, ಡೆಲಿವರಿ ಆದ 30 ದಿನಗಳೊಳಗೆ ನೀವು ವಸ್ತುಗಳನ್ನು ಹಿಂತಿರುಗಿಸಬಹುದು. ಮೂಲ ಸ್ಥಿತಿಯಲ್ಲಿದ್ದರೆ ಪೂರ್ಣ ಮರುಪಾವತಿ ದೊರೆಯುತ್ತದೆ."
                    elif is_tenglish:
                        return f"Maa return policy prakaram, {item_term} delivery aina 30 days lopu return cheyyochu. Original condition-lo unte full refund istamu."
                    elif is_telugu:
                        return "మా రిటర్న్ పాలసీ ప్రకారం, డెలివరీ అయిన 30 రోజులలోపు వస్తువులను తిరిగి ఇవ్వవచ్చు. అసలు స్థితిలో ఉంటే పూర్తి రీఫండ్ లభిస్తుంది."
                    elif is_manglish:
                        return f"Njangalude return policy anusarichu, {item_term} delivery aayi 30 days-kullil return cheyyam. Original condition-il aanenkil full refund labhikkum."
                    elif is_malayalam:
                        return "ഞങ്ങളുടെ റിട്ടേൺ പോളിസി പ്രകാരം, ഡെലിവറി കഴിഞ്ഞ് 30 ദിവസത്തിനുള്ളിൽ സാധനങ്ങൾ തിരികെ നൽകാം. ഒറിജിനൽ അവസ്ഥയിലാണെങ്കിൽ പൂർണ്ണ റീഫണ്ട് ലഭിക്കും."
                    elif is_bengali or is_benglish:
                        return "আমাদের রিটার্ন পলিসি অনুযায়ী, ডেলিভারির ৩০ দিনের মধ্যে আইটেম ফেরত দেওয়া যেতে পারে এবং সম্পূর্ণ রিফান্ড পাবেন।"
                    elif is_marathi or is_marathish:
                        return "आमच्या रिटर्न पॉलिसीनुसार, डिलिव्हरीच्या ३० दिवसांच्या आत तुम्ही वस्तू परत करू शकता आणि पूर्ण परतावा मिळेल."
                    elif is_gujarati or is_gujlish:
                        return "અમારી રીટર્ન પોલિસી મુજબ, ડિલિવરીના 30 દિવસમાં તમે વસ્તુ પરત કરી શકો છો અને સંપૂર્ણ રિફંડ મળશે."
                    elif is_punjabi or is_punglish:
                        return "ਸਾਡੀ ਰਿਟਰਨ ਨੀਤੀ ਅਨੁਸਾਰ, ਡਿਲੀਵਰੀ ਦੇ 30 ਦਿਨਾਂ ਦੇ ਅੰਦਰ ਤੁਸੀਂ ਆਈਟਮ ਵਾਪਸ ਕਰ ਸਕਦੇ ਹੋ ਅਤੇ ਪੂਰਾ ਰਿਫੰਡ ਮਿਲੇਗਾ।"
                    return f"Under our return policy, items can be returned within 30 days of delivery in original condition for a full refund."

                if is_tanglish:
                    return "Namma ResolveMart-la 3 mukkiyamana policies irukku: 1) Return Policy: Items delivery aana 30 days kulla original condition-la return panna mudiyum. 2) Cancellation Policy: Order dispatch aagardhukku munnadi cancel panna mudiyum. 3) Delivery: Standard delivery 3-5 business days kulla vandhudum. Ungalukku edha pathi detail-ah theriyanum?"
                elif is_tamil:
                    return "நமது ResolveMart-ல் முக்கிய கொள்கைகள்: 1) Return Policy: டெலிவரி செய்யப்பட்ட 30 நாட்களுக்குள் பொருட்களை திரும்ப அளிக்கலாம். 2) Cancellation Policy: அனுப்பப்படுவதற்கு முன் ஆர்டரை ரத்து செய்யலாம். 3) Shipping Policy: 3-5 வேலை நாட்களில் டெலிவரி செய்யப்படும். உங்களுக்கு எந்த கொள்கை பற்றி மேலும் விவரங்கள் வேண்டும்?"
                elif is_hinglish:
                    return "ResolveMart mein mukhya policies ye hain: 1) Return Policy: Delivery ke 30 dinon ke andar original condition mein return kar sakte hain. 2) Cancellation Policy: Dispatch se pehle order cancel kar sakte hain. 3) Delivery Policy: Standard delivery 3-5 business days mein hoti hai. Aapko kis policy ke baare mein aur jaankari chahiye?"
                elif is_hindi:
                    return "हमारे ResolveMart में मुख्य पॉलिसियां हैं: 1) Return Policy: डिलीवरी के 30 दिनों के भीतर आइटम रिटर्न किया जा सकता है। 2) Cancellation Policy: डिस्पैच से पहले ऑर्डर रद्द किया जा सकता है। 3) Delivery Policy: स्टैंडर्ड डिलीवरी 3-5 दिनों में होती है। आपको किस पॉलिसी के बारे में जानकारी चाहिए?"
                elif is_kanglish:
                    return "ResolveMart-nalli mukhyavada policies: 1) Return: Delivery aada 30 days olage return madbahudu. 2) Cancellation: Dispatch aagoku munche cancel madbahudu. 3) Shipping: 3-5 business days. Nimage yavudhu thilko beku?"
                elif is_kannada:
                    return "ರೆಸಾಲ್ವ್‌ಮಾರ್ಟ್‌ನಲ್ಲಿ ಮುಖ್ಯ ನಿಯಮಗಳು: 1) ರಿಟರ್ನ್ ಪಾಲಿಸಿ: ಡೆಲಿವರಿ ಆದ 30 ದಿನಗಳೊಳಗೆ ಹಿಂತಿರುಗಿಸಬಹುದು. 2) ರದ್ದತಿ: ರವಾನೆಗೆ ಮೊದಲು ರದ್ದುಗೊಳಿಸಬಹುದು. 3) ಡೆಲಿವರಿ: 3-5 ವ್ಯವಹಾರ ದಿನಗಳು. ನಿಮಗೆ ಯಾವ ವಿವರ ಬೇಕು?"
                elif is_tenglish:
                    return "ResolveMart-lo main policies: 1) Return Policy: Delivery aina 30 days lo return cheyyochu. 2) Cancellation: Dispatch mundu cancel cheyyochu. 3) Delivery: 3-5 business days. Meeku edi kavali?"
                elif is_telugu:
                    return "రిసాల్వ్‌మార్ట్‌లో ముఖ్య నిబంధనలు: 1) రిటర్న్ పాలసీ: డెలివరీ అయిన 30 రోజులలోపు తిరిగి ఇవ్వవచ్చు. 2) రద్దు: డిస్పాచ్‌కు ముందు రద్దు చేసుకోవచ్చు. 3) డెಲಿవరీ: 3-5 పనిదినాలు. మీకు ఏ వివరాలు కావాలి?"
                elif is_manglish:
                    return "ResolveMart-le main policies: 1) Return: Delivery aayi 30 days-kullil return cheyyam. 2) Cancellation: Dispatch-nu mumpu cancel cheyyam. 3) Delivery: 3-5 business days. Ningalkku ethaanu ariyendathu?"
                elif is_malayalam:
                    return "റിസോൾവ്മാർട്ടിൽ പ്രധാന പോളിസികൾ: 1) റിട്ടേൺ: ഡെലിവറി കഴിഞ്ഞ് 30 ദിവസത്തിനുള്ളിൽ തിരികെ നൽകാം. 2) ക്യാൻസലേഷൻ: അയയ്ക്കുന്നതിന് മുൻപ് റദ്ദാക്കാം. 3) ഡെലിവറി: 3-5 പ്രവൃത്തിദിനങ്ങൾ. ഏത് വിവരമാണ് വേണ്ടത്?"
                elif is_bengali or is_benglish:
                    return "ResolveMart-এর প্রধান নীতিগুলি: ১) রিটার্ন পলিসি: ডেলিভারির ৩০ দিনের মধ্যে ফেরত দেওয়া যাবে। ২) বাতিলকরণ: পাঠানোর আগে বাতিল করা যাবে। ৩) ডেলিভারি: ৩-৫ কার্যদিবস। আপনি কোনটি জানতে চান?"
                elif is_marathi or is_marathish:
                    return "ResolveMart च्या मुख्य पॉलिसी: 1) रिटर्न पॉलिसी: डिलिव्हरीच्या 30 दिवसांच्या आत परत करू शकता. 2) रद्दीकरण: डिस्पॅचपूर्वी रद्द करू शकता. 3) डिलिव्हरी: 3-5 दिवस. तुम्हाला कशाबद्दल माहिती हवी आहे?"
                elif is_gujarati or is_gujlish:
                    return "ResolveMart ની મુખ્ય નીતિઓ: 1) રીટર્ન પોલિસી: ડિલિવરીના 30 દિવસમાં પરત કરી શકો છો. 2) કેન્સલેશન: ડિસ્પેચ પહેલાં રદ કરી શકો છો. 3) ડિલિવરી: 3-5 દિવસ. તમને કઈ માહિતી જોઈએ છે?"
                elif is_punjabi or is_punglish:
                    return "ResolveMart ਦੀਆਂ ਮੁੱਖ ਨੀਤੀਆਂ: 1) ਰਿਟਰਨ ਨੀਤੀ: ਡਿਲੀਵਰੀ ਦੇ 30 ਦਿਨਾਂ ਦੇ ਅੰਦਰ ਵਾਪਸੀ। 2) ਰੱਦ ਕਰਨਾ: ਡਿਸਪੈਚ ਤੋਂ ਪਹਿਲਾਂ ਰੱਦ ਕੀਤਾ ਜਾ ਸਕਦਾ ਹੈ। 3) ਡਿਲਿਵਰੀ: 3-5 ਦਿਨ। ਤੁਹਾਨੂੰ ਕਿਸ ਬਾਰੇ ਜਾਣਕਾਰੀ ਚਾਹੀਦੀ ਹੈ?"
                return "At ResolveMart, our core policies are: 1) Return Policy: Returns accepted within 30 days of delivery in original condition. 2) Cancellation Policy: Orders can be cancelled anytime before dispatch. 3) Shipping & Delivery Policy: Standard delivery within 3-5 business days with tracking. Which policy would you like more details about?"

            if action_type == "simplified_explanation":
                if is_tanglish:
                    return "Simple-ah solren bro: Namma ResolveMart-la items delivery aana 30 days kulla neenga return panna mudiyum, full refund kedaikkum."
                elif is_hinglish:
                    return "Aasaan shabdon mein: ResolveMart par delivery ke 30 dinon ke andar aap return kar sakte hain aur pura refund milega."
                elif is_tamil:
                    return "எளிய முறையில் கூறினால்: டெலிவரி செய்யப்பட்ட 30 நாட்களுக்குள் பொருட்களை திரும்ப அளித்து முழு தொகையையும் திரும்பப் பெறலாம்."
                elif is_hindi:
                    return "आसान शब्दों में: डिलीवरी के 30 दिनों के भीतर आप सामान वापस कर सकते हैं और पूरा रिफंड मिलेगा।"
                return "Simply put: You can return items within 30 days of delivery in original condition for a full refund."

            if action_type == "policy_next_steps":
                if is_tanglish:
                    return "Adhukku apram, unga order details check panna unga Order ID share pannunga, return request initiate pannalam."
                elif is_hinglish:
                    return "Uske baad, aap apna Order ID share karein taaki hum return request initiate kar sakein."
                elif is_tamil:
                    return "அதற்குப் பிறகு, உங்கள் ஆர்டர் ஐடியைப் பகிர்ந்தால் ரிட்டர்ன் கோரிக்கையைத் தொடங்கலாம்."
                elif is_hindi:
                    return "इसके बाद, कृपया अपना ऑर्डर आईडी बताएं ताकि हम रिटर्न प्रक्रिया शुरू कर सकें।"
                return "After that, simply share your Order ID and we can initiate the return request for you."

            if action_type == "alternative_options":
                if is_tanglish:
                    return "Kandippa! Order ID illana, unga registered mobile number or email address vechu namma support team unga account-ah verify panna mudiyum. Illana ungalukku help panna oru human expert-kku connect pannattuma?"
                elif is_hinglish:
                    return "Haan bilkul! Agar Order ID nahi hai, toh aapke registered mobile number ya email ID se hum details check kar sakte hain, ya phir main aapko ek human expert se connect kar doon?"
                elif is_tamil:
                    return "நிச்சயமாக! ஆர்டர் ஐடி இல்லையென்றால், உங்கள் பதிவு செய்யப்பட்ட மொபைல் எண் அல்லது மின்னஞ்சல் மூலம் சரிபார்க்கலாம். அல்லது ஒரு மனித நிபுணரிடம் இணைக்க வேண்டுமா?"
                elif is_hindi:
                    return "ज़रूर! अगर ऑर्डर आईडी नहीं है, तो आपके रजिस्टर्ड मोबाइल या ईमेल से हम चेक कर सकते हैं, या क्या मैं आपको किसी विशेषज्ञ से जोड़ दूँ?"
                return "Certainly! If you don't have your Order ID handy, we can look up your order using your registered email address or phone number. Alternatively, I can connect you with a human expert who can assist you directly."

            if action_type == "causal_why_explanation":
                if is_tanglish:
                    return "Original payment method-la refund panna thaan bank security rules and fraud prevention policy allow pannum bro. Idhanaala thaan direct cash-a thara mudiyadhu / vera account-ku maatha mudiyadhu."
                elif is_hinglish:
                    return "Bank security rules aur fraud prevention policy ke anusaar, refund sirf original payment method mein hi transfer ho sakta hai."
                elif is_tamil:
                    return "வங்கி பாதுகாப்பு விதிகள் மற்றும் மோசடி தடுப்புக் கொள்கைகளின்படி, கட்டணம் செலுத்திய அதே முறைக்கு மட்டுமே பணத்தை திரும்ப அளிக்க முடியும்."
                elif is_hindi:
                    return "बैंक सुरक्षा नियमों और धोखाधड़ी रोकथाम नीतियों के अनुसार, रिफंड केवल मूल भुगतान विधि में ही किया जा सकता है।"
                return "Our refund policy requires returning funds directly to the original payment method in compliance with banking security regulations and anti-fraud guidelines."

            if action_type == "handoff_confirmed":
                if is_tanglish:
                    return "Nandri! Ungal request-ah namma human expert kitta connect panren. Konjam nerathula join pannuvaanga."
                elif is_hinglish:
                    return "Dhanyawaad! Main aapki request human expert ko transfer kar raha hoon. Wo jaldi hi aapse judenge."
                elif is_tamil:
                    return "நன்றி! உங்கள் கோரிக்கையை மனித நிபுணரிடம் இணைக்கிறேன். சிறிது நேரத்தில் இணைவார்."
                elif is_hindi:
                    return "धन्यवाद! मैं आपका अनुरोध विशेषज्ञ को ट्रांसफर कर रहा हूँ। वे जल्द ही आपसे जुड़ेंगे।"
                return "Thank you! I am transferring your request to a human expert. Someone will join shortly."

            if action_type == "handoff_rejected":
                if is_tanglish:
                    return "Seri bro, problem illa! Naane ungalukku continue panni help panren. Ungal kelviya sollunga."
                elif is_hinglish:
                    return "Theek hai, koi baat nahi! Main yahan aapki madad ke liye tayyar hoon. Batayein main kya kar sakta hoon."
                elif is_tamil:
                    return "சரி, பரவாயில்லை! நானே உங்களுக்கு தொடர்ந்து உதவுகிறேன். உங்கள் கேள்வியைக் கூறுங்கள்."
                elif is_hindi:
                    return "कोई बात नहीं! मैं यहीं आपकी सहायता करूँगा। बताइए मैं क्या मदद कर सकता हूँ।"
                return "No problem at all! I'll continue assisting you here. How can I help?"

            if action_type == "refund_received_acknowledgment":
                if is_tanglish:
                    return "Ketaadhum magizhchi bro! Unga refund vandhadhu romba nalladhu. Ungalukku vera edhavadhu help venuma?"
                elif is_tamil:
                    return "உங்கள் ரீஃபண்ட் கிடைத்ததில் மகிழ்ச்சி! உங்களுக்கு வேறு ஏதேனும் உதவி தேவையா?"
                elif is_hinglish:
                    return "Yeh sunkar accha laga ki aapka refund mil gaya! Kya aapko kisi aur cheez mein sahayata chahiye?"
                elif is_hindi:
                    return "यह जानकर अच्छा लगा कि आपका रिफंड मिल गया! क्या आपको किसी और सहायता की आवश्यकता है?"
                elif is_kanglish or is_kannada:
                    return "Nimma refund bandhidhukke thumba santhosha! Nimage bere enadru sahayavagbeka?" if is_kanglish else "ನಿಮ್ಮ ಮರುಪಾವತಿ ದೊರೆತಿದ್ದಕ್ಕೆ ಸಂತೋಷ! ನಿಮಗೆ ಬೇರೆ ಯಾವುದೇ ಸಹಾಯ ಬೇಕೇ?"
                elif is_tenglish or is_telugu:
                    return "Mee refund vachinanduku santhosham! Meeku inka edaina help kavalana?" if is_tenglish else "మీ రీఫండ్ అందినందుకు సంతోషం! మీకు మరేదైనా సహాయం కావాలా?"
                elif is_manglish or is_malayalam:
                    return "Ningalude refund kittiyathil santhosham! Ningalkku vere enthenkilum help venamo?" if is_manglish else "നിങ്ങളുടെ റീഫണ്ട് ലഭിച്ചതിൽ സന്തോഷം! നിങ്ങൾക്ക് മറ്റ് എന്തെങ്കിലും സഹായം ആവശ്യമുണ്ടോ?"
                elif is_bengali or is_benglish:
                    return "আপনার রিফান্ড পাওয়ার বিষয়টি জেনে ভালো লাগল! আপনার কি অন্য কোনো সহায়তার প্রয়োজন?"
                elif is_marathi or is_marathish:
                    return "तुमचा परतावा मिळाल्याचे ऐकून आनंद झाला! तुम्हाला इतर काही मदत हवी आहे का?"
                elif is_gujarati or is_gujlish:
                    return "તમારો રિફંડ મળી ગયો તે જાણીને આનંદ થયો! શું તમારે અન્ય કોઈ મદદની જરૂર છે?"
                elif is_punjabi or is_punglish:
                    return "ਇਹ ਸੁਣ ਕੇ ਖੁਸ਼ੀ ਹੋਈ ਕਿ ਤੁਹਾਡਾ ਰਿਫੰਡ ਮਿਲ ਗਿਆ ਹੈ! ਕੀ ਤੁਹਾਨੂੰ ਕਿਸੇ ਹੋਰ ਸਹਾਇਤਾ ਦੀ ਲੋੜ ਹੈ?"
                return "Glad to hear that your refund has been received! Please let us know if you need help with anything else."

            if action_type == "payment_confirmation":
                if is_tanglish:
                    return "Nandri! Unga payment complete aana details note pannitom bro. Ungal order process aagudhu. Vera edhavadhu check pannanuma?"
                elif is_tamil:
                    return "நன்றி! உங்கள் கட்டணம் வெற்றிகரமாக பெறப்பட்டது. வேறு ஏதேனும் விவரங்கள் அறிய வேண்டுமா?"
                elif is_hinglish:
                    return "Dhanyawaad! Aapka payment prapt ho gaya hai. Kya aapko aur kisi cheez mein madad chahiye?"
                elif is_hindi:
                    return "धन्यवाद! आपका भुगतान प्राप्त हो गया है। क्या आपको किसी अन्य सहायता की आवश्यकता है?"
                elif is_kanglish or is_kannada:
                    return "Dhanyavada! Nimma payment details note madiddini. Bere enadru check madbeka?" if is_kanglish else "ಧನ್ಯವಾದಗಳು! ನಿಮ್ಮ ಪಾವತಿ ಸ್ವೀಕರಿಸಲಾಗಿದೆ. ಬೇರೆ ಯಾವುದೇ ಸಹಾಯ ಬೇಕೇ?"
                elif is_tenglish or is_telugu:
                    return "Dhanyavadalu! Mee payment praptamaindi. Inka emaina check cheyala?" if is_tenglish else "ధన్యవాదాలు! మీ చెల్లింపు విజయవంతంగా పూర్తయింది. మీకు మరేదైనా సహాయం కావాలా?"
                elif is_manglish or is_malayalam:
                    return "Nanni! Ningalude payment labhichu. Vere enthenkilum check cheyyano?" if is_manglish else "നന്ദി! നിങ്ങളുടെ പേയ്‌മെന്റ് വിജയകരമായി ലഭിച്ചു. മറ്റ് എന്തെങ്കിലും അറിയേണ്ടതുണ്ടോ?"
                elif is_bengali or is_benglish:
                    return "ধন্যবাদ! আপনার পেমেন্ট সফলভাবে গৃহীত হয়েছে। আপনার কি অন্য কিছু জানা দরকার?"
                elif is_marathi or is_marathish:
                    return "धन्यवाद! तुमचे पेमेंट यशस्वीरित्या प्राप्त झाले आहे. तुम्हाला इतर काही माहिती हवी आहे का?"
                elif is_gujarati or is_gujlish:
                    return "ધન્યવાદ! તમારું ચુકવણું પ્રાપ્ત થઈ ગયું છે. શું તમારે અન્ય કોઈ મદદની જરૂર છે?"
                elif is_punjabi or is_punglish:
                    return "ਧੰਨਵਾਦ! ਤੁਹਾਡਾ ਭੁਗਤਾਨ ਪ੍ਰਾਪਤ ਹੋ ਗਿਆ ਹੈ। ਕੀ ਤੁਹਾਨੂੰ ਕਿਸੇ ਹੋਰ ਮਦਦ ਦੀ ਲੋੜ ਹੈ?"
                return "Thank you! We have noted that your payment is completed. Let us know if you need help with anything else."

            if action_type == "acknowledgment_closing" or not article:
                if is_tanglish:
                    return "Magizhchi! Ungalukku vera edhavadhu help venuma?"
                elif is_tamil:
                    return "மகிழ்ச்சி! உங்களுக்கு வேறு ஏதேனும் உதவி தேவையா?"
                elif is_hinglish:
                    return "Aapka swagat hai! Kya aapko aur kisi cheez mein madad chahiye?"
                elif is_hindi:
                    return "आपका स्वागत है! क्या आपको किसी और सहायता की आवश्यकता है?"
                elif is_kanglish or is_kannada:
                    return "Santhosha! Nimage bere enadru sahayavagbeka?" if is_kanglish else "ಸಂತೋಷ! ನಿಮಗೆ ಬೇರೆ ಯಾವುದೇ ಸಹಾಯ ಬೇಕೇ?"
                elif is_tenglish or is_telugu:
                    return "Santhosham! Meeku inka edaina help kavalana?" if is_tenglish else "సంతోషం! మీకు మరేదైనా సహాయం కావాలా?"
                elif is_manglish or is_malayalam:
                    return "Santhosham! Ningalkku vere enthenkilum help venamo?" if is_manglish else "സന്തോഷം! നിങ്ങൾക്ക് മറ്റ് എന്തെങ്കിലും സഹായം ആവശ്യമുണ്ടോ?"
                elif is_bengali or is_benglish:
                    return "আপনাকে স্বাগতম! আপনার কি অন্য কোনো সাহায্যের প্রয়োজন?"
                elif is_marathi or is_marathish:
                    return "आपले स्वागत आहे! तुम्हाला इतर काही मदत हवी आहे का?"
                elif is_gujarati or is_gujlish:
                    return "આપનું સ્વાગત છે! શું તમારે અન્ય કોઈ સહાયની જરૂર છે?"
                elif is_punjabi or is_punglish:
                    return "ਤੁਹਾਡਾ ਸਵਾਗਤ ਹੈ! ਕੀ ਤੁਹਾਨੂੰ ਕਿਸੇ ਹੋਰ ਮਦਦ ਦੀ ਲੋੜ ਹੈ?"
                return "You're welcome! Let me know if you need help with anything else."
            
            # Synthesize grounded language-specific response
            if is_tanglish:
                if any(w in title for w in ["return", "refund", "pol-005", "pol-006", "pol-007"]) or any(w in content.lower() for w in ["return", "refund"]):
                    if "refund" in title or ("refund" in content.lower() and "return" not in title):
                        return "Namma refund policy padi, refunds internally 24 hours kulla process aagidum, bank account-la reflect aaga 3–5 business days aagum. Original payment method-ku thaan refund panna mudiyum."
                    return "Namma return policy padi, items delivery aana 30 days kulla original condition-la neenga return panna mudiyum. Ungalukku vera edhavadhu help venuma?"
                elif any(w in title for w in ["cancel", "pol-004"]) or "cancellation" in content.lower():
                    return "Namma cancellation policy padi, order dispatch aagardhukku munnadi neenga cancel panna mudiyum. Shipped aana apram cancel panna mudiyadhu, delivery aana apram return thaan panna mudiyum."
                elif any(w in title for w in ["shipping", "delivery", "pol-003"]) or "shipping" in content.lower():
                    return "Namma standard delivery 3–5 business days kulla vandhudum. Order ship aana udane tracking number ungalukku SMS and email-la kedaikum."
                elif any(w in title for w in ["charter", "hours", "pol-001"]):
                    return "ResolveMart customer support 24/7 kedaikkum. Human experts Monday to Friday 9 AM to 6 PM irupaanga. Ungalukku eppo venumnaalum human support kedaikkum."
                else:
                    import re
                    clean_c = re.sub(r"\[(?:CORE|EXT)\]", "", content)
                    clean_c = re.sub(r"Decision guidance:[\s\S]*$", "", clean_c).strip()
                    lines = [l.strip() for l in clean_c.split("\n") if l.strip() and not l.strip().startswith("Never:") and not l.strip().startswith("Escalate when:")]
                    first_line = lines[0] if lines else clean_c[:150]
                    return f"Namma policy padi, {first_line}. Ungalukku vera edhavadhu help venuma?"
            elif is_tamil:
                if any(w in title for w in ["return", "pol-005"]) or "return" in content.lower():
                    return "நமது நிறுவனத்தின் கொள்கையின்படி, டெலிவரி செய்யப்பட்ட 30 நாட்களுக்குள் அசல் நிலையில் (original condition) உள்ள பொருட்களை நீங்கள் திரும்ப அளிக்கலாம். உங்களுக்கு வேறு ஏதேனும் உதவி தேவையா?"
                elif any(w in title for w in ["cancel", "pol-004"]):
                    return "பொருட்கள் அனுப்பப்படுவதற்கு (Shipment) முன்பு மட்டுமே நீங்கள் ஆர்டரை ரத்து செய்ய முடியும். அனுப்பப்பட்ட பிறகு ரத்து செய்ய இயலாது."
                else:
                    return "நமது நிறுவன விதிமுறைகளின்படி உங்கள் கோரிக்கை பரிசீலிக்கப்படும். மேலும் விவரங்களுக்கு எங்களை தொடர்பு கொள்ளவும்."
            elif is_hinglish:
                if any(w in title for w in ["return", "pol-005"]) or "return" in content.lower():
                    return "Hamari return policy ke hisaab se, delivery ke 30 dinon ke andar original condition mein aap product return kar sakte hain. Kya aapko iske baare mein aur jaankari chahiye?"
                elif any(w in title for w in ["cancel", "pol-004"]):
                    return "Hamari policy ke anusaar, order ship hone se pehle aap cancel kar sakte hain. Dispatch ke baad cancel nahi ho sakta, return karna hoga."
                elif any(w in title for w in ["shipping", "delivery", "pol-003"]):
                    return "Standard delivery mein 3–5 business days lagte hain. Order dispatch hone ke baad tracking details mil jayengi."
                else:
                    return f"Policy details: {content[:150]}. Kya aapko iske baare mein aur jaankari chahiye?"
            elif is_hindi:
                if any(w in title for w in ["return", "pol-005"]) or "return" in content.lower():
                    return "हमारी रिटर्न पॉलिसी के अनुसार, डिलीवरी के 30 दिनों के भीतर मूल स्थिति में आइटम रिटर्न किया जा सकता है। क्या आपको और जानकारी चाहिए?"
                elif any(w in title for w in ["cancel", "pol-004"]):
                    return "हमारी पॉलिसी के अनुसार, ऑर्डर शिप होने से पहले आप रद्द कर सकते हैं। डिस्पैच के बाद रद्द नहीं किया जा सकता।"
                else:
                    return f"कंपनी की नीति के अनुसार, हम आपकी सहायता के लिए तैयार हैं।"
            elif is_kannada or is_kanglish:
                if any(w in title for w in ["return", "pol-005"]) or "return" in content.lower():
                    return "ನಮ್ಮ ರಿಟರ್ನ್ ಪಾಲಿಸಿಯ ಪ್ರಕಾರ, ಡೆಲಿವರಿ ಆದ 30 ದಿನಗಳೊಳಗೆ ನೀವು ವಸ್ತುಗಳನ್ನು ಹಿಂತಿರುಗಿಸಬಹುದು." if is_kannada else "Namma return policy prakara, delivery aada 30 days olage return madbahudu."
                elif any(w in title for w in ["cancel", "pol-004"]):
                    return "ರವಾನೆಗೆ (Shipment) ಮೊದಲು ಮಾತ್ರ ನೀವು ಆರ್ಡರ್ ರದ್ದುಗೊಳಿಸಬಹುದು." if is_kannada else "Order dispatch aagoku munche cancel madbahudu."
                else:
                    return "ಕಂಪನಿಯ ನಿಯಮಗಳ ಪ್ರಕಾರ ನಾವು ನಿಮಗೆ ಸಹಾಯ ಮಾಡಲು ಸಿದ್ಧರಿದ್ದೇವೆ." if is_kannada else "Company rules prakara naavu nimage help madoke ready iddini."
            elif is_telugu or is_tenglish:
                if any(w in title for w in ["return", "pol-005"]) or "return" in content.lower():
                    return "మా రిటర్న్ పాలసీ ప్రకారం, డెలివరీ అయిన 30 రోజులలోపు వస్తువులను తిరిగి ఇవ్వవచ్చు." if is_telugu else "Maa return policy prakaram, delivery aina 30 days lopu return cheyyochu."
                elif any(w in title for w in ["cancel", "pol-004"]):
                    return "వస్తువులు పంపే ముందు (Shipment) మాత్రమే మీరు ఆర్డర్‌ను రద్దు చేయవచ్చు." if is_telugu else "Order dispatch mundu cancel cheyyochu."
                else:
                    return "సంస్థ నిబంధనల ప్రకారం మీకు సహాయం చేయడానికి మేము సిద్ధంగా ఉన్నాము." if is_telugu else "Company rules prakaram meeku help cheyadaniki memu ready unnamu."
            elif is_malayalam or is_manglish:
                if any(w in title for w in ["return", "pol-005"]) or "return" in content.lower():
                    return "ഞങ്ങളുടെ റിട്ടേൺ പോളിസി പ്രകാരം, ഡെലിവറി കഴിഞ്ഞ് 30 ദിവസത്തിനുള്ളിൽ സാധനങ്ങൾ തിരികെ നൽകാം." if is_malayalam else "Njangalude return policy anusarichu, delivery aayi 30 days-kullil return cheyyam."
                elif any(w in title for w in ["cancel", "pol-004"]):
                    return "സാധനങ്ങൾ അയയ്ക്കുന്നതിന് (Shipment) മുൻപ് മാത്രമേ ഓർഡർ റദ്ദാക്കാനാകൂ." if is_malayalam else "Order dispatch-nu mumpu cancel cheyyam."
                else:
                    return "കമ്പനി പോളിസി പ്രകാരം നിങ്ങളെ സഹായിക്കാൻ ഞങ്ങൾ തയ്യാറാണ്." if is_malayalam else "Company policy anusarichu ningale help cheyyan njangal ready aanu."
            elif is_bengali or is_benglish:
                if any(w in title for w in ["return", "pol-005"]) or "return" in content.lower():
                    return "আমাদের রিটার্ন পলিসি অনুযায়ী, ডেলিভারির ৩০ দিনের মধ্যে আইটেম ফেরত দেওয়া যাবে।"
                elif any(w in title for w in ["cancel", "pol-004"]):
                    return "অর্ডার পাঠানোর আগে আপনি বাতিল করতে পারবেন।"
                else:
                    return "কোম্পানির নীতি অনুসারে আমরা আপনাকে সহায়তা করতে প্রস্তুত।"
            elif is_marathi or is_marathish:
                if any(w in title for w in ["return", "pol-005"]) or "return" in content.lower():
                    return "आमच्या रिटर्न पॉलिसीनुसार, डिलिव्हरीच्या ३० दिवसांच्या आत तुम्ही वस्तू परत करू शकता."
                elif any(w in title for w in ["cancel", "pol-004"]):
                    return "ऑर्डर पाठवण्यापूर्वी तुम्ही रद्द करू शकता."
                else:
                    return "कंपनीच्या धोरणानुसार आम्ही आपल्याला मदत करण्यास तयार आहोत."
            elif is_gujarati or is_gujlish:
                if any(w in title for w in ["return", "pol-005"]) or "return" in content.lower():
                    return "અમારી રીટર્ન પોલિસી મુજબ, ડિલિવરીના 30 દિવસમાં તમે વસ્તુ પરત કરી શકો છો."
                elif any(w in title for w in ["cancel", "pol-004"]):
                    return "ઓર્ડર મોકલતા પહેલા તમે રદ કરી શકો છો."
                else:
                    return "કંપનીની નીતિ મુજબ અમે તમને મદદ કરવા તૈયાર છીએ."
            elif is_punjabi or is_punglish:
                if any(w in title for w in ["return", "pol-005"]) or "return" in content.lower():
                    return "ਸਾਡੀ ਰਿਟਰਨ ਨੀਤੀ ਅਨੁਸਾਰ, ਡਿਲੀਵਰੀ ਦੇ 30 ਦਿਨਾਂ ਦੇ ਅੰਦਰ ਤੁਸੀਂ ਆਈਟਮ ਵਾਪਸ ਕਰ ਸਕਦੇ ਹੋ।"
                elif any(w in title for w in ["cancel", "pol-004"]):
                    return "ਆਰਡਰ ਭੇਜਣ ਤੋਂ ਪਹਿਲਾਂ ਤੁਸੀਂ ਰੱਦ ਕਰ ਸਕਦੇ ਹੋ।"
                else:
                    return "ਕੰਪਨੀ ਦੀ ਨੀਤੀ ਅਨੁਸਾਰ ਅਸੀਂ ਤੁਹਾਡੀ ਮਦਦ ਕਰਨ ਲਈ ਤਿਆਰ ਹਾਂ।"
            else:
                # English: clean developer tags and provide clean grounded response
                import re
                clean_c = re.sub(r"\[(?:CORE|EXT)\]", "", content)
                clean_c = re.sub(r"Decision guidance:[\s\S]*$", "", clean_c).strip()
                lines = [l.strip() for l in clean_c.split("\n") if l.strip() and not l.strip().startswith("Never:") and not l.strip().startswith("Escalate when:") and not l.strip().startswith("Handoff notes:")]
                return "\n\n".join(lines[:8]) if lines else content
            
        return "I'm having trouble understanding. Let me connect you to a human expert."
