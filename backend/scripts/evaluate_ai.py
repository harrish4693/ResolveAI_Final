import asyncio
import json
import os
import sys

# Add the project root to sys.path so we can import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ai.m4.provider import M4AIProvider

DATASET_FILE = os.path.join(os.path.dirname(__file__), "golden_dataset.json")

def load_dataset():
    with open(DATASET_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

async def evaluate():
    dataset = load_dataset()
    provider = M4AIProvider()
    
    # We will mock the retriever to simulate RAG being successful when needed
    class MockRetriever:
        async def search(self, query: str, db=None):
            return [{"title": "Mock Article", "content": "This is a mock resolved article."}]
    
    provider.retriever = MockRetriever()
    
    metrics = {
        "intent": {"total": 0, "correct": 0},
        "language": {"total": 0, "correct": 0},
        "decision": {"total": 0, "correct": 0},
        "tool": {"total": 0, "correct": 0},
        "grounding": {"total": 0, "correct": 0},
        "multiturn": {"total": 0, "correct": 0},
    }
    
    results = []

    for item in dataset:
        case_id = item["id"]
        input_text = item["input"]
        context = item.get("context", {})
        expected = item["expected"]
        
        # 1. Analyze
        analysis = await provider.analyze(input_text, context)
        
        # 2. Generate response (pass a dummy string for db to trigger retrieval logic if it checks for Truthy db)
        response_text = await provider.generate_response(analysis, [], context, db="dummy_db")
        
        # Check actuals
        actual_lang = analysis.get("language")
        actual_intent = analysis.get("intent")
        actual_decision = analysis.get("decision_state")
        actual_tool = analysis.get("tool_name")
        
        # Track metrics
        metrics["intent"]["total"] += 1
        if actual_intent == expected.get("intent"):
            metrics["intent"]["correct"] += 1
            
        metrics["language"]["total"] += 1
        if actual_lang == expected.get("language"):
            metrics["language"]["correct"] += 1
            
        metrics["decision"]["total"] += 1
        if actual_decision == expected.get("decision"):
            metrics["decision"]["correct"] += 1
            
        if "tool" in expected:
            metrics["tool"]["total"] += 1
            if actual_tool == expected["tool"]:
                metrics["tool"]["correct"] += 1
                
        if expected.get("grounding") is not None:
            metrics["grounding"]["total"] += 1
            # In M4AIProvider mock, it doesn't execute the tool inside generate_response during normal flow (ToolRuntime executes it).
            # But the decision should be USE_TOOL and tool_name should be correct for a grounding step.
            # If expected grounding is True, we check if the response indicates tool execution start.
            if actual_decision == "USE_TOOL" and actual_tool == expected.get("tool"):
                metrics["grounding"]["correct"] += 1
                
        if context.get("previous_analysis"):
            metrics["multiturn"]["total"] += 1
            if actual_intent == expected.get("intent") and actual_tool == expected.get("tool"):
                metrics["multiturn"]["correct"] += 1
                
        results.append({
            "id": case_id,
            "passed": actual_intent == expected.get("intent") and actual_decision == expected.get("decision"),
            "details": f"Expected {expected.get('language')}/{expected.get('intent')}/{expected.get('decision')}/{expected.get('tool')} | Got {actual_lang}/{actual_intent}/{actual_decision}/{actual_tool}"
        })
        if not (actual_intent == expected.get("intent") and actual_decision == expected.get("decision")):
            safe_input = input_text.encode('ascii', 'replace').decode('ascii')
            print(f"FAILED {case_id}: '{safe_input}' -> Expected {expected.get('intent')}/{expected.get('decision')} | Got {actual_intent}/{actual_decision}")
            
        if actual_lang != expected.get("language"):
            safe_input = input_text.encode('ascii', 'replace').decode('ascii')
            print(f"LANGUAGE FAILED {case_id}: '{safe_input}' -> Expected {expected.get('language')} | Got {actual_lang}")
        
    # Calculate percentages
    thresholds = {
        "intent": 90.0,
        "language": 90.0,
        "decision": 90.0,
        "tool": 95.0,
        "grounding": 95.0,
        "multiturn": 90.0,
    }
    
    print("\n" + "="*50)
    print(" ResolveAIV2 AI Evaluation Report")
    print("="*50 + "\n")
    
    passed_all = True
    
    for metric_name, data in metrics.items():
        if data["total"] == 0:
            continue
        accuracy = (data["correct"] / data["total"]) * 100
        threshold = thresholds[metric_name]
        
        status = "[PASS]" if accuracy >= threshold else "[FAIL]"
        if accuracy < threshold:
            passed_all = False
            
        print(f"{metric_name.capitalize():<12} Accuracy: {accuracy:>6.2f}% (Threshold: {threshold}%) {status}")
        
    print("\n" + "="*50)
    
    with open("evaluation_report.md", "w", encoding="utf-8") as f:
        f.write("# M10.4 AI Evaluation Report\n\n")
        f.write("| Metric | Accuracy | Threshold | Status |\n")
        f.write("|---|---|---|---|\n")
        for metric_name, data in metrics.items():
            if data["total"] == 0: continue
            acc = (data["correct"] / data["total"]) * 100
            status = "[PASS]" if acc >= thresholds[metric_name] else "[FAIL]"
            f.write(f"| {metric_name.capitalize()} | {acc:.2f}% | {thresholds[metric_name]}% | {status} |\n")
            
    if passed_all:
        print("\nAll thresholds met. Exiting 0.")
        sys.exit(0)
    else:
        print("\nEvaluation failed due to unmet thresholds. Exiting 1.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(evaluate())
