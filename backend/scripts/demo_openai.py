import asyncio
import os
import json
import httpx
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from dotenv import load_dotenv

from app.config import settings
from app.ai.openai_provider import OpenAIProvider

# Load environment from .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

async def demo():
    if not settings.openai_api_key:
        print("[-] OPENAI_API_KEY is not set. Please set it in .env to run this demo.")
        return

    print("[+] OPENAI_API_KEY detected. Initializing OpenAIProvider...")
    provider = OpenAIProvider()
    
    # We will simulate a sequence of messages
    conversation_history = []
    
    # Message 1
    print("\n--- Conversation Turn 1 ---")
    msg1 = "Hi there"
    print(f"Customer: {msg1}")
    
    analysis1 = await provider.analyze(msg1, {"history": conversation_history})
    print(f"[Analysis] Intent: {analysis1.get('intent')}, Entities: {analysis1.get('entities')}")
    
    resp1 = await provider.generate_response(analysis1, [], {"history": conversation_history})
    print(f"[Decision] {analysis1.get('decision_state')}")
    print(f"AI: {resp1}")
    
    conversation_history.append({"sender_type": "customer", "content": msg1})
    conversation_history.append({"sender_type": "ai", "content": resp1})
    
    # Message 2
    print("\n--- Conversation Turn 2 ---")
    msg2 = "My payment failed"
    print(f"Customer: {msg2}")
    
    analysis2 = await provider.analyze(msg2, {"history": conversation_history})
    print(f"[Analysis] Intent: {analysis2.get('intent')}, Entities: {analysis2.get('entities')}")
    
    resp2 = await provider.generate_response(analysis2, [], {"history": conversation_history})
    print(f"[Decision] {analysis2.get('decision_state')}")
    print(f"AI: {resp2}")
    
    conversation_history.append({"sender_type": "customer", "content": msg2})
    conversation_history.append({"sender_type": "ai", "content": resp2})
    
    # Message 3
    print("\n--- Conversation Turn 3 ---")
    msg3 = "TXN12345"
    print(f"Customer: {msg3}")
    
    # Pass previous analysis to preserve intent in context
    context3 = {"history": conversation_history, "previous_analysis": analysis2}
    analysis3 = await provider.analyze(msg3, context3)
    print(f"[Analysis] Intent: {analysis3.get('intent')}, Entities: {analysis3.get('entities')}")
    
    resp3 = await provider.generate_response(analysis3, [], context3)
    print(f"[Decision] {analysis3.get('decision_state')}")
    print(f"AI: {resp3}")
    if analysis3.get('decision_state') == "USE_TOOL":
        print(f"[*] Tool Requested: {analysis3.get('tool_name')} with args {analysis3.get('tool_args')}")
        
    conversation_history.append({"sender_type": "customer", "content": msg3})
    conversation_history.append({"sender_type": "ai", "content": resp3})
    
    # Message 4 (Escalation)
    print("\n--- Conversation Turn 4 ---")
    msg4 = "I want to speak to a human manager right now."
    print(f"Customer: {msg4}")
    
    context4 = {"history": conversation_history, "previous_analysis": analysis3}
    analysis4 = await provider.analyze(msg4, context4)
    print(f"[Analysis] Intent: {analysis4.get('intent')}, Entities: {analysis4.get('entities')}")
    
    resp4 = await provider.generate_response(analysis4, [], context4)
    print(f"[Decision] {analysis4.get('decision_state')}")
    print(f"AI: {resp4}")

if __name__ == "__main__":
    asyncio.run(demo())
