import json
import os

DATASET_FILE = os.path.join(os.path.dirname(__file__), "golden_dataset.json")

def generate_dataset():
    cases = []
    
    # --- Intent: PAYMENT_ISSUE ---
    # English
    cases.append({"id": "P1", "input": "I paid for the pro plan but money was deducted twice.", "context": {}, "expected": {"language": "en", "intent": "PAYMENT_ISSUE", "decision": "ASK_USER"}})
    cases.append({"id": "P2", "input": "Check my transaction TXN12345", "context": {}, "expected": {"language": "en", "intent": "PAYMENT_ISSUE", "decision": "USE_TOOL", "tool": "check_transaction", "grounding": True}})
    # Tamil
    cases.append({"id": "P3", "input": "என் பணம் ரெண்டு தடவை எடுக்கப்பட்டுவிட்டது", "context": {}, "expected": {"language": "ta", "intent": "PAYMENT_ISSUE", "decision": "ASK_USER"}})
    # Tanglish
    cases.append({"id": "P4", "input": "ennoda kaasu rendatti eduthutanga", "context": {}, "expected": {"language": "tanglish", "intent": "PAYMENT_ISSUE", "decision": "ASK_USER"}})
    # Hindi
    cases.append({"id": "P5", "input": "मेरा पैसा कट गया", "context": {}, "expected": {"language": "hi", "intent": "PAYMENT_ISSUE", "decision": "ASK_USER"}})
    # Hinglish
    cases.append({"id": "P6", "input": "mera paisa double deduct ho gaya", "context": {}, "expected": {"language": "hinglish", "intent": "PAYMENT_ISSUE", "decision": "ASK_USER"}})

    # --- Intent: SECURITY_ISSUE ---
    cases.append({"id": "S1", "input": "Someone hacked into my account from Russia!", "context": {}, "expected": {"language": "en", "intent": "SECURITY_ISSUE", "decision": "ESCALATE"}})
    cases.append({"id": "S2", "input": "My phone was stolen, block my account.", "context": {}, "expected": {"language": "en", "intent": "SECURITY_ISSUE", "decision": "ESCALATE"}})
    cases.append({"id": "S3", "input": "என் அக்கவுண்ட் ஹேக் ஆகிடுச்சு", "context": {}, "expected": {"language": "ta", "intent": "SECURITY_ISSUE", "decision": "ESCALATE"}})
    cases.append({"id": "S4", "input": "account hack aayiduchu bro", "context": {}, "expected": {"language": "tanglish", "intent": "SECURITY_ISSUE", "decision": "ESCALATE"}})
    cases.append({"id": "S5", "input": "kisi ne mera account hack kar liya", "context": {}, "expected": {"language": "hinglish", "intent": "SECURITY_ISSUE", "decision": "ESCALATE"}})

    # --- Intent: LOGIN_ISSUE ---
    cases.append({"id": "L1", "input": "I forgot my password.", "context": {}, "expected": {"language": "en", "intent": "LOGIN_ISSUE", "decision": "RESOLVE"}})
    cases.append({"id": "L2", "input": "My account is locked after too many attempts.", "context": {}, "expected": {"language": "en", "intent": "LOGIN_ISSUE", "decision": "RESOLVE"}})
    cases.append({"id": "L3", "input": "password maranthuten", "context": {}, "expected": {"language": "tanglish", "intent": "LOGIN_ISSUE", "decision": "RESOLVE"}})
    cases.append({"id": "L4", "input": "password yaad nahi", "context": {}, "expected": {"language": "hinglish", "intent": "LOGIN_ISSUE", "decision": "RESOLVE"}})
    
    # --- Intent: DELIVERY_ISSUE ---
    # wait! In decision.py there is NO tool for DELIVERY_ISSUE! Look at decision.py: it only has USE_TOOL for PAYMENT, REFUND, UPDATE. For DELIVERY, if order_id is present, it will fall through to RESOLVE (if knowledge) or ESCALATE (if no knowledge). 
    # Ah! Let me check decision.py. If we mock RAG, it returns knowledge, so decision is RESOLVE.
    cases.append({"id": "D1", "input": "When will order ORD55555 be delivered?", "context": {}, "expected": {"language": "en", "intent": "DELIVERY_ISSUE", "decision": "RESOLVE"}}) 
    cases.append({"id": "D2", "input": "order is late", "context": {}, "expected": {"language": "en", "intent": "DELIVERY_ISSUE", "decision": "ASK_USER"}})
    cases.append({"id": "D3", "input": "order deliver aagala", "context": {}, "expected": {"language": "tanglish", "intent": "DELIVERY_ISSUE", "decision": "ASK_USER"}})

    # --- Intent: REFUND_ISSUE ---
    cases.append({"id": "R1", "input": "I want a refund for TXN99999", "context": {}, "expected": {"language": "en", "intent": "REFUND_ISSUE", "decision": "USE_TOOL", "tool": "create_refund_request", "grounding": True}})
    cases.append({"id": "R2", "input": "check refund status for TXN11111", "context": {}, "expected": {"language": "en", "intent": "REFUND_ISSUE", "decision": "USE_TOOL", "tool": "create_refund_request", "grounding": True}}) # M4 logic only has create_refund_request for REFUND_ISSUE
    cases.append({"id": "R3", "input": "refund venum for TXN12345", "context": {}, "expected": {"language": "tanglish", "intent": "REFUND_ISSUE", "decision": "USE_TOOL", "tool": "create_refund_request", "grounding": True}})

    # --- Intent: UPDATE_ISSUE ---
    cases.append({"id": "U1", "input": "Can I update my phone number?", "context": {}, "expected": {"language": "en", "intent": "UPDATE_ISSUE", "decision": "USE_TOOL", "tool": "update_customer_details"}})
    cases.append({"id": "U2", "input": "phone number change pannanum", "context": {}, "expected": {"language": "tanglish", "intent": "UPDATE_ISSUE", "decision": "USE_TOOL", "tool": "update_customer_details"}})

    # --- Multi-turn Conversations ---
    cases.append({"id": "M1", "input": "What about my other transaction TXN88888?", "context": {"previous_analysis": {"intent": "PAYMENT_ISSUE"}}, "expected": {"language": "en", "intent": "PAYMENT_ISSUE", "decision": "USE_TOOL", "tool": "check_transaction", "grounding": True}})
    
    # --- RAG Retrieval / General ---
    cases.append({"id": "G1", "input": "What are your business hours?", "context": {}, "expected": {"language": "en", "intent": "GENERAL_QUERY", "decision": "RESOLVE"}})
    cases.append({"id": "G2", "input": "How do I upgrade to the enterprise plan?", "context": {}, "expected": {"language": "en", "intent": "GENERAL_QUERY", "decision": "RESOLVE"}})

    # Expand variations programmatically to reach ~60 cases
    variations = [
        ("I was charged twice.", "en", "PAYMENT_ISSUE", "ASK_USER"),
        ("My card was deducted wrongly.", "en", "PAYMENT_ISSUE", "ASK_USER"),
        ("Kaasu rendu thadava poiruchu", "tanglish", "PAYMENT_ISSUE", "ASK_USER"),
        ("paisa double kat gaya", "hinglish", "PAYMENT_ISSUE", "ASK_USER"),
        ("Someone is accessing my account!", "en", "SECURITY_ISSUE", "ESCALATE"),
        ("Account hack aagiduchu nu nenaikran", "tanglish", "SECURITY_ISSUE", "ESCALATE"),
        ("How to change password?", "en", "LOGIN_ISSUE", "RESOLVE"),
        ("password reset pannunga", "tanglish", "LOGIN_ISSUE", "RESOLVE"),
        ("Where is my delivery for ORD12345?", "en", "DELIVERY_ISSUE", "RESOLVE"),
        ("delivery late aaguthu", "tanglish", "DELIVERY_ISSUE", "ASK_USER"),
        ("I need my money back for TXN23456", "en", "REFUND_ISSUE", "USE_TOOL", "create_refund_request"),
        ("Update address details", "en", "UPDATE_ISSUE", "USE_TOOL", "update_customer_details"),
        ("How do I contact support?", "en", "GENERAL_QUERY", "RESOLVE"),
        ("Support number enna?", "tanglish", "GENERAL_QUERY", "RESOLVE"),
    ]
    
    for i, (text, lang, intent, decision, *rest) in enumerate(variations):
        case = {
            "id": f"V{i}",
            "input": text,
            "context": {},
            "expected": {
                "language": lang,
                "intent": intent,
                "decision": decision
            }
        }
        if rest:
            case["expected"]["tool"] = rest[0]
            case["expected"]["grounding"] = True if decision == "USE_TOOL" else False
            
        cases.append(case)

    # Adding more to hit exactly 50+ cases
    more_texts = [
        ("can't login to my account", "en", "LOGIN_ISSUE", "RESOLVE"),
        ("unauthorized transaction TXN98765", "en", "SECURITY_ISSUE", "ESCALATE"), 
        ("return my item ORD11111", "en", "REFUND_ISSUE", "RESOLVE"), 
        ("return my money for TXN11111", "en", "REFUND_ISSUE", "USE_TOOL", "create_refund_request"),
        ("update my email", "en", "UPDATE_ISSUE", "USE_TOOL", "update_customer_details"),
        ("change my phone number", "en", "UPDATE_ISSUE", "USE_TOOL", "update_customer_details"),
        ("delivery hasn't arrived", "en", "DELIVERY_ISSUE", "ASK_USER"),
        ("mera account locked hai", "hinglish", "LOGIN_ISSUE", "RESOLVE"),
        ("paisa wapas chahiye for TXN00000", "hinglish", "REFUND_ISSUE", "USE_TOOL", "create_refund_request"),
        ("panam thirumba venum for TXN00000", "tanglish", "REFUND_ISSUE", "USE_TOOL", "create_refund_request"),
        ("order track karo ORD00000", "hinglish", "DELIVERY_ISSUE", "RESOLVE"),
        ("hack kardiya mera account", "hinglish", "SECURITY_ISSUE", "ESCALATE"),
        ("password bhool gaya", "hinglish", "LOGIN_ISSUE", "RESOLVE"),
    ]

    for i, (text, lang, intent, decision, *rest) in enumerate(more_texts):
        case = {
            "id": f"X{i}",
            "input": text,
            "context": {},
            "expected": {
                "language": lang,
                "intent": intent,
                "decision": decision
            }
        }
        if rest:
            case["expected"]["tool"] = rest[0]
            case["expected"]["grounding"] = True if decision == "USE_TOOL" else False
            
        cases.append(case)
        
    with open(DATASET_FILE, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2, ensure_ascii=False)
        
    print(f"Generated {len(cases)} evaluation cases at {DATASET_FILE}")

if __name__ == "__main__":
    generate_dataset()
