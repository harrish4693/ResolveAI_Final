import sys
import asyncio
import time
sys.path.insert(0, ".")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.voice.sarvam_tts import synthesize_sarvam
from app.voice.sarvam_stt import transcribe_sarvam

async def main():
    test_cases = [
        ("ta-IN", "enakku refund pannanum kaasu account ku varala"),
        ("hi-IN", "mera refund abhi tak nahi aaya paise bhejo"),
        ("en-IN", "I need help tracking my ResolveAI package right now"),
    ]
    for lang, text in test_cases:
        print(f"\nTesting {lang}: \"{text}\"")
        t0 = time.time()
        audio = await synthesize_sarvam(text, language_code=lang)
        tts_lat = int((time.time() - t0) * 1000)
        print(f"  TTS generated {len(audio)} bytes in {tts_lat}ms")
        
        # Test translit
        t1 = time.time()
        res_tr = await transcribe_sarvam(audio, language_code="unknown", mode="translit")
        stt_lat_tr = int((time.time() - t1) * 1000)
        print(f"  STT (translit, {stt_lat_tr}ms): \"{res_tr['transcript']}\" [lang: {res_tr['language_code']}, conf: {res_tr['confidence']}]")
        
        # Test codemix
        t2 = time.time()
        res_cm = await transcribe_sarvam(audio, language_code="unknown", mode="codemix")
        stt_lat_cm = int((time.time() - t2) * 1000)
        print(f"  STT (codemix,  {stt_lat_cm}ms): \"{res_cm['transcript']}\" [lang: {res_cm['language_code']}, conf: {res_cm['confidence']}]")

if __name__ == "__main__":
    asyncio.run(main())
