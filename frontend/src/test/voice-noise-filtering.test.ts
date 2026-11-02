/**
 * ResolveAIV2 — Call Agent Background Voice and Noise Filtering Regression Tests
 *
 * Verifies:
 * 1. Customer speaks clearly in a quiet environment.
 * 2. Background TV or nearby conversation occurs while the customer is silent.
 * 3. Customer speaks while another person speaks nearby (adequate SNR).
 * 4. Background noise occurs during a legitimate customer utterance.
 * 5. Customer pauses naturally in the middle of a sentence.
 * 6. Customer gives a short answer such as "yes", "no", "seri", "haan", "cancel".
 * 7. Customer speaks in Tamil, Hindi, Tanglish, Hinglish, and English.
 * 8. Empty audio and silence do not trigger an agent response.
 * 9. The same audio segment does not create duplicate turns.
 * 10. Five consecutive Call Agent turns work without stale transcripts.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  calculateRMS,
  calculateZCR,
  isProbableSpeech,
  ClientVADState,
  validateCustomerUtterance,
} from "../lib/clientVAD";
import { WHITELISTED_SHORT_UTTERANCES } from "../lib/noiseFilter";
import { VoiceTurnCoordinator } from "../lib/voiceEchoFilter";

describe("Voice Noise Filtering & VAD Regression Suite", () => {
  describe("Scenario 1: Customer speaks clearly in a quiet environment", () => {
    it("detects speech onset, accumulates frames, and finalizes WAV blob after pause", () => {
      const vad = new ClientVADState({
        speechEnergyThreshold: 0.015,
        snrFactor: 2.2,
        speechOnsetConfirmationFrames: 2,
        minSpeechMs: 200,
        endSilenceMs: 300,
      });

      // Frame: 800 samples = 50ms at 16kHz
      // Clear vocal sine wave (440Hz, RMS ~0.15)
      const speechFrame = new Float32Array(800);
      for (let i = 0; i < 800; i++) {
        speechFrame[i] = 0.2 * Math.sin((2 * Math.PI * 440 * i) / 16000);
      }
      const silenceFrame = new Float32Array(800).fill(0.001);

      // Frame 1: Onset candidate 1 (not yet confirmed)
      let res1 = vad.processFrame(speechFrame, 50);
      expect(res1).toBeNull();
      expect(vad.isCurrentlySpeaking()).toBe(false);

      // Frame 2: Onset candidate 2 (speech onset confirmed!)
      let res2 = vad.processFrame(speechFrame, 50);
      expect(res2).toBeNull();
      expect(vad.isCurrentlySpeaking()).toBe(true);

      // Additional 200ms speech (4 frames)
      for (let i = 0; i < 4; i++) {
        vad.processFrame(speechFrame, 50);
      }

      // End silence: 300ms (6 frames of 50ms)
      let emitted: Blob | null = null;
      for (let i = 0; i < 6; i++) {
        const out = vad.processFrame(silenceFrame, 50);
        if (out) emitted = out;
      }

      expect(emitted).not.toBeNull();
      expect(emitted?.type).toBe("audio/wav");
    });
  });

  describe("Scenario 2: Background TV or nearby conversation occurs while customer is silent", () => {
    it("adaptive noise floor raises dynamic threshold so ambient room audio does not trigger speech", () => {
      const vad = new ClientVADState({
        speechEnergyThreshold: 0.015,
        snrFactor: 2.2,
        speechOnsetConfirmationFrames: 2,
        minSpeechMs: 250,
        endSilenceMs: 500,
      });

      // Moderate background noise (RMS ~0.008)
      const ambientTVFrame = new Float32Array(800);
      for (let i = 0; i < 800; i++) {
        ambientTVFrame[i] = (Math.random() - 0.5) * 0.02; // RMS ~0.0057
      }

      // Feed 20 frames (1 second) of ambient TV audio
      for (let i = 0; i < 20; i++) {
        vad.processFrame(ambientTVFrame, 50);
      }

      // Since ambient energy is below dynamic threshold, vad should never declare isSpeaking
      expect(vad.isCurrentlySpeaking()).toBe(false);

      // Even after 500ms, no WAV is emitted
      let emitted: Blob | null = null;
      for (let i = 0; i < 10; i++) {
        const res = vad.processFrame(ambientTVFrame, 50);
        if (res) emitted = res;
      }
      expect(emitted).toBeNull();
    });

    it("STT noise tags from background TV ([music], [applause], [cough]) are rejected by noise filter", () => {
      expect(validateCustomerUtterance("[music]").isValid).toBe(false);
      expect(validateCustomerUtterance("[applause]").isValid).toBe(false);
      expect(validateCustomerUtterance("[laughter]").isValid).toBe(false);
      expect(validateCustomerUtterance("[cough]").isValid).toBe(false);
      expect(validateCustomerUtterance("(music)").isValid).toBe(false);
      expect(validateCustomerUtterance("[chatter]").isValid).toBe(false);
      expect(validateCustomerUtterance("thank you for watching").isValid).toBe(false);
    });

    it("transient non-speech clicks and keyboard clatter are rejected by ZCR and onset confirmation", () => {
      const vad = new ClientVADState({
        speechEnergyThreshold: 0.015,
        snrFactor: 2.2,
        speechOnsetConfirmationFrames: 2,
        minSpeechMs: 250,
        endSilenceMs: 500,
      });

      // Sharp transient click: high frequency alternating pulse (ZCR ~ 0.9)
      const clickFrame = new Float32Array(800);
      for (let i = 0; i < 800; i++) {
        clickFrame[i] = i % 2 === 0 ? 0.3 : -0.3;
      }
      const silence = new Float32Array(800).fill(0.001);

      expect(calculateZCR(clickFrame)).toBeGreaterThan(0.52);
      expect(isProbableSpeech(clickFrame)).toBe(false);

      // Feed transient click for 1 frame
      vad.processFrame(clickFrame, 50);
      expect(vad.isCurrentlySpeaking()).toBe(false);

      // Followed by silence
      let emitted: Blob | null = null;
      for (let i = 0; i < 10; i++) {
        const res = vad.processFrame(silence, 50);
        if (res) emitted = res;
      }
      expect(emitted).toBeNull();
    });
  });

  describe("Scenario 3: Customer speaks with high SNR over background sound", () => {
    it("customer vocal energy easily crosses dynamic threshold and finalizes turn", () => {
      const vad = new ClientVADState({
        speechEnergyThreshold: 0.015,
        snrFactor: 2.0,
        speechOnsetConfirmationFrames: 2,
        minSpeechMs: 200,
        endSilenceMs: 300,
      });

      // Background ambient sound (RMS ~ 0.01)
      const ambient = new Float32Array(800);
      for (let i = 0; i < 800; i++) {
        ambient[i] = (Math.random() - 0.5) * 0.035;
      }
      // Adapt noise floor
      for (let i = 0; i < 10; i++) {
        vad.processFrame(ambient, 50);
      }

      // Customer speaks directly into mic (RMS ~ 0.18)
      const directSpeech = new Float32Array(800);
      for (let i = 0; i < 800; i++) {
        directSpeech[i] = 0.25 * Math.sin((2 * Math.PI * 300 * i) / 16000) + ambient[i];
      }

      // 6 frames of speech (300ms)
      for (let i = 0; i < 6; i++) {
        vad.processFrame(directSpeech, 50);
      }
      expect(vad.isCurrentlySpeaking()).toBe(true);

      // Followed by silence (300ms)
      let emitted: Blob | null = null;
      for (let i = 0; i < 6; i++) {
        const res = vad.processFrame(ambient, 50);
        if (res) emitted = res;
      }
      expect(emitted).not.toBeNull();
    });
  });

  describe("Scenario 4: Background noise occurs during a legitimate customer utterance", () => {
    it("preserves continuous speech tracking during utterance", () => {
      const vad = new ClientVADState({
        speechEnergyThreshold: 0.015,
        snrFactor: 2.2,
        speechOnsetConfirmationFrames: 2,
        minSpeechMs: 200,
        endSilenceMs: 400,
      });

      const speech = new Float32Array(800);
      for (let i = 0; i < 800; i++) {
        speech[i] = 0.2 * Math.sin((2 * Math.PI * 400 * i) / 16000);
      }

      // Start speaking (2 frames)
      vad.processFrame(speech, 50);
      vad.processFrame(speech, 50);
      expect(vad.isCurrentlySpeaking()).toBe(true);

      // Brief noise burst while customer speaks
      const noiseWithSpeech = new Float32Array(800);
      for (let i = 0; i < 800; i++) {
        noiseWithSpeech[i] = speech[i] + (Math.random() - 0.5) * 0.05;
      }
      vad.processFrame(noiseWithSpeech, 50);
      vad.processFrame(speech, 50);
      expect(vad.isCurrentlySpeaking()).toBe(true);
    });
  });

  describe("Scenario 5: Customer pauses naturally in the middle of a sentence", () => {
    it("does not prematurely cut off customer during natural pause (< endSilenceMs)", () => {
      const vad = new ClientVADState({
        speechEnergyThreshold: 0.015,
        snrFactor: 2.2,
        speechOnsetConfirmationFrames: 2,
        minSpeechMs: 250,
        endSilenceMs: 700, // 700ms end silence threshold
      });

      const speech = new Float32Array(800);
      for (let i = 0; i < 800; i++) {
        speech[i] = 0.2 * Math.sin((2 * Math.PI * 400 * i) / 16000);
      }
      const pauseSilence = new Float32Array(800).fill(0.001);

      // First part of sentence (200ms)
      for (let i = 0; i < 4; i++) {
        vad.processFrame(speech, 50);
      }
      expect(vad.isCurrentlySpeaking()).toBe(true);

      // Natural pause of 350ms (7 frames) - shorter than 700ms end silence
      for (let i = 0; i < 7; i++) {
        const res = vad.processFrame(pauseSilence, 50);
        expect(res).toBeNull(); // Must NOT prematurely emit!
      }
      expect(vad.isCurrentlySpeaking()).toBe(true);

      // Customer resumes speaking for another 200ms
      for (let i = 0; i < 4; i++) {
        vad.processFrame(speech, 50);
      }
      expect(vad.isCurrentlySpeaking()).toBe(true);

      // Now customer finishes speaking: 700ms silence (14 frames)
      let emitted: Blob | null = null;
      for (let i = 0; i < 14; i++) {
        const res = vad.processFrame(pauseSilence, 50);
        if (res) emitted = res;
      }
      expect(emitted).not.toBeNull();
    });
  });

  describe("Scenario 6: Customer gives a short answer", () => {
    it("preserves English short answers ('yes', 'no', 'stop', 'help', 'cancel', 'ok')", () => {
      const shortAnswers = ["yes", "no", "stop", "help", "cancel", "ok", "okay", "sure", "wait"];
      for (const ans of shortAnswers) {
        const val = validateCustomerUtterance(ans);
        expect(val.isValid).toBe(true);
        expect(val.isShortAnswer).toBe(true);
      }
    });

    it("rejects isolated filler murmurs while preserving short answers", () => {
      // Fillers must be rejected
      expect(validateCustomerUtterance("uh").isValid).toBe(false);
      expect(validateCustomerUtterance("um").isValid).toBe(false);
      expect(validateCustomerUtterance("hmm").isValid).toBe(false);
      expect(validateCustomerUtterance("ahh").isValid).toBe(false);

      // But whitelisted answers with identical shortness MUST be valid
      expect(validateCustomerUtterance("yes").isValid).toBe(true);
      expect(validateCustomerUtterance("no").isValid).toBe(true);
      expect(validateCustomerUtterance("ha").isValid).toBe(true);
      expect(validateCustomerUtterance("na").isValid).toBe(true);
    });
  });

  describe("Scenario 7: Multilingual Speech Preservation", () => {
    it("preserves Tamil, Tanglish, Hindi, and Hinglish short words in both scripts", () => {
      // Tamil & Tanglish
      expect(validateCustomerUtterance("seri").isValid).toBe(true);
      expect(validateCustomerUtterance("sari").isValid).toBe(true);
      expect(validateCustomerUtterance("aama").isValid).toBe(true);
      expect(validateCustomerUtterance("illai").isValid).toBe(true);
      expect(validateCustomerUtterance("சரி").isValid).toBe(true);
      expect(validateCustomerUtterance("இல்லை").isValid).toBe(true);
      expect(validateCustomerUtterance("ஆம்").isValid).toBe(true);

      // Hindi & Hinglish
      expect(validateCustomerUtterance("haan").isValid).toBe(true);
      expect(validateCustomerUtterance("nahi").isValid).toBe(true);
      expect(validateCustomerUtterance("theek hai").isValid).toBe(true);
      expect(validateCustomerUtterance("ruko").isValid).toBe(true);
      expect(validateCustomerUtterance("हाँ").isValid).toBe(true);
      expect(validateCustomerUtterance("नहीं").isValid).toBe(true);
      expect(validateCustomerUtterance("ठीक है").isValid).toBe(true);

      // Kannada, Telugu, Malayalam
      expect(validateCustomerUtterance("houdu").isValid).toBe(true);
      expect(validateCustomerUtterance("avunu").isValid).toBe(true);
      expect(validateCustomerUtterance("athe").isValid).toBe(true);
      expect(validateCustomerUtterance("ಹೌದು").isValid).toBe(true);
      expect(validateCustomerUtterance("అవును").isValid).toBe(true);
      expect(validateCustomerUtterance("അതെ").isValid).toBe(true);
    });

    it("preserves complete code-mixed and native script customer queries", () => {
      const queries = [
        "Enaku delivery eppo varum nu solla mudiyuma?",
        "Mera refund kab tak credit hoga account mein?",
        "Please cancel my order 4567.",
        "பணம் எப்போது திருப்பி வரும்?",
        "मुझे मेरा आर्डर ट्रैक करना है।",
        "ನನ್ನ ಪ್ರಾಡಕ್ಟ್ ಇನ್ನು ಡೆಲಿವರಿ ಆಗಿಲ್ಲ.",
      ];
      for (const q of queries) {
        const val = validateCustomerUtterance(q);
        expect(val.isValid).toBe(true);
        expect(val.isShortAnswer).toBe(false);
      }
    });
  });

  describe("Scenario 8: Empty audio and silence do not trigger an agent response", () => {
    it("rejects empty, whitespace, and punctuation-only transcripts", () => {
      expect(validateCustomerUtterance("").isValid).toBe(false);
      expect(validateCustomerUtterance("   ").isValid).toBe(false);
      expect(validateCustomerUtterance("...").isValid).toBe(false);
      expect(validateCustomerUtterance("???").isValid).toBe(false);
      expect(validateCustomerUtterance(".").isValid).toBe(false);
    });

    it("VAD never triggers turn on pure silence", () => {
      const vad = new ClientVADState({
        speechEnergyThreshold: 0.015,
        minSpeechMs: 250,
        endSilenceMs: 500,
      });
      const silentFrame = new Float32Array(800).fill(0.0001);

      for (let i = 0; i < 30; i++) {
        const res = vad.processFrame(silentFrame, 50);
        expect(res).toBeNull();
      }
      expect(vad.isCurrentlySpeaking()).toBe(false);
      expect(vad.forceFinalize()).toBeNull();
    });
  });

  describe("Scenario 9: Utterance Deduplication & Echo Guard", () => {
    it("VoiceTurnCoordinator rejects duplicate turns and echoes of agent speech", () => {
      const coordinator = new VoiceTurnCoordinator();
      coordinator.onAgentAudioStarted("Your order has been shipped.");

      // While agent is speaking, customer mic picking up agent speaker echo is dropped
      const echoCheck = coordinator.evaluateRecognitionResult("Your order has been shipped.");
      expect(echoCheck.allowTurn).toBe(false);
      expect(echoCheck.isEcho).toBe(true);
      expect(echoCheck.echoFilterDropped).toBe(true);

      // Agent finishes speaking
      coordinator.onAgentAudioAllFinished();

      // Fresh customer utterance after reverberation tail (300ms tail)
      const afterTail = Date.now() + 400;
      const validTurn = coordinator.canDispatchTurn("Where is my package?", afterTail);
      expect(validTurn.canDispatch).toBe(true);
      coordinator.onTurnDispatched("Where is my package?");

      // Rapid duplicate dispatch of the same turn
      const dupTurn = coordinator.canDispatchTurn("Where is my package?", afterTail + 50);
      expect(dupTurn.canDispatch).toBe(false);
      expect(dupTurn.reason).toBe("duplicate_turn");
    });
  });

  describe("Scenario 10: Five consecutive Call Agent turns work without stale transcripts", () => {
    it("supports 5 successive customer turns with clean state resets", () => {
      const coordinator = new VoiceTurnCoordinator();
      const turns = [
        "Hello, I need help with my recent order.",
        "Order number is 98765.",
        "Yes.",
        "I want to change the delivery address to Chennai.",
        "Thank you, that is all.",
      ];

      let simulatedTime = Date.now();

      for (let i = 0; i < turns.length; i++) {
        const text = turns[i];

        // 1. Validate customer utterance against noise filter
        const val = validateCustomerUtterance(text);
        expect(val.isValid).toBe(true);

        // 2. Coordinate turn dispatch after past agent tail
        simulatedTime += 400;
        const dispatchCheck = coordinator.canDispatchTurn(text, simulatedTime);
        expect(dispatchCheck.canDispatch).toBe(true);
        coordinator.onTurnDispatched(text);

        // 3. Agent speaks reply
        coordinator.onAgentAudioStarted(`Agent response for turn ${i + 1}`);
        coordinator.onAgentAudioAllFinished();
      }

      // Verify all 5 turns processed cleanly
      expect(coordinator.getDispatchedTurnCount()).toBe(5);
    });
  });
});
