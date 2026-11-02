import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  VoiceTurnCoordinator,
  isEchoOfAgentText,
  normalizeForEcho,
  getGreetingForLanguage,
} from "../lib/voiceEchoFilter";

describe("VoiceEchoFilter & Turn Coordinator (Milestone P2.5)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe("Acoustic Echo Matching", () => {
    const agentGreeting = "Hello! I am ResolveAI. How can I help you today?";

    it("identifies exact and normalized matches as echo", () => {
      expect(isEchoOfAgentText("Hello! I am ResolveAI. How can I help you today?", agentGreeting)).toBe(true);
      expect(isEchoOfAgentText("hello i am resolveai how can i help you today", agentGreeting)).toBe(true);
    });

    it("identifies sub-phrases and token overlap as echo", () => {
      // Partial acoustic fragments picked up by mic
      expect(isEchoOfAgentText("I am ResolveAI", agentGreeting)).toBe(true);
      expect(isEchoOfAgentText("how can I help you", agentGreeting)).toBe(true);
      expect(isEchoOfAgentText("resolveai help you today", agentGreeting)).toBe(true);
    });

    it("does NOT classify distinct customer responses as echo", () => {
      expect(isEchoOfAgentText("Where is my order ORD-12345?", agentGreeting)).toBe(false);
      expect(isEchoOfAgentText("I want a refund for my shoes", agentGreeting)).toBe(false);
      expect(isEchoOfAgentText("Tanglish-la pesalam", agentGreeting)).toBe(false);
      expect(isEchoOfAgentText("pannanum", agentGreeting)).toBe(false);
    });
  });

  describe("VoiceTurnCoordinator Turn Control & Fake Timers", () => {
    let coordinator: VoiceTurnCoordinator;
    const greeting = "Hello! I am ResolveAI. How can I help you today?";

    beforeEach(() => {
      coordinator = new VoiceTurnCoordinator({ tailDurationMs: 300, sustainedBargeInThresholdMs: 400 });
    });

    it("blocks customer turns while agent audio is playing", () => {
      coordinator.onAgentAudioStart(greeting);
      expect(coordinator.isAgentAudioActive()).toBe(true);

      const canDispatch = coordinator.canDispatchTurn("Where is my order?");
      expect(canDispatch.canDispatch).toBe(false);
      expect(canDispatch.reason).toBe("agent_is_currently_speaking");
    });

    it("ignores greeting echo while agent audio is playing", () => {
      coordinator.onAgentAudioStart(greeting);

      const evalResult = coordinator.evaluateRecognitionResult("I am ResolveAI");
      expect(evalResult.allowTurn).toBe(false);
      expect(evalResult.isEcho).toBe(true);
      expect(evalResult.agentAudioWasPlaying).toBe(true);
      expect(evalResult.echoFilterDropped).toBe(true);
      expect(evalResult.dropReason).toBe("echo_of_agent_audio");
    });

    it("respects the 300 ms acoustic tail after agent audio finishes", () => {
      coordinator.onAgentAudioStart(greeting);

      // Audio finishes at t = 0
      coordinator.onAgentAudioAllFinished();

      // At t = 100 ms (within 300 ms tail), turn dispatch must be blocked
      vi.advanceTimersByTime(100);
      expect(coordinator.isAgentAudioActive()).toBe(true);
      const blockedTurn = coordinator.canDispatchTurn("Where is my order?");
      expect(blockedTurn.canDispatch).toBe(false);
      expect(blockedTurn.reason).toContain("within_300ms_acoustic_tail");

      // At t = 350 ms (past the 300 ms tail), active audio is cleared
      vi.advanceTimersByTime(250);
      expect(coordinator.isAgentAudioActive()).toBe(false);
      const allowedTurn = coordinator.canDispatchTurn("Where is my order?");
      expect(allowedTurn.canDispatch).toBe(true);
    });

    it("drops echo arriving during the acoustic tail", () => {
      coordinator.onAgentAudioStart(greeting);
      coordinator.onAgentAudioAllFinished();

      // Reverberation echo arrives at t = 150 ms
      vi.advanceTimersByTime(150);
      const evalResult = coordinator.evaluateRecognitionResult("how can I help you today");
      expect(evalResult.allowTurn).toBe(false);
      expect(evalResult.isEcho).toBe(true);
      expect(evalResult.echoFilterDropped).toBe(true);
    });

    it("triggers real barge-in only on sustained speech (>= 400 ms)", () => {
      coordinator.onAgentAudioStart(greeting);
      const customerSpeech = "Stop, I need urgent help with my payment";

      // First detection at t = 0 (0 ms sustained)
      const firstChunk = coordinator.evaluateRecognitionResult(customerSpeech);
      expect(firstChunk.allowTurn).toBe(false);
      expect(firstChunk.isBargeIn).toBe(false);
      expect(firstChunk.echoFilterDropped).toBe(true);
      expect(firstChunk.dropReason).toContain("held_for_sustained_barge_in");

      // Speech continues at t = 200 ms (200 ms sustained, still < 400 ms)
      vi.advanceTimersByTime(200);
      const secondChunk = coordinator.evaluateRecognitionResult(customerSpeech);
      expect(secondChunk.allowTurn).toBe(false);
      expect(secondChunk.isBargeIn).toBe(false);

      // Speech continues at t = 450 ms (450 ms sustained, >= 400 ms) -> BARGE-IN!
      vi.advanceTimersByTime(250);
      const thirdChunk = coordinator.evaluateRecognitionResult(customerSpeech);
      expect(thirdChunk.allowTurn).toBe(true);
      expect(thirdChunk.isBargeIn).toBe(true);
      expect(thirdChunk.echoFilterDropped).toBe(false);
      expect(coordinator.isAgentAudioActive()).toBe(false); // Playback cancelled
    });

    it("does not trigger barge-in if speech stops before 400 ms (transient acoustic noise)", () => {
      coordinator.onAgentAudioStart(greeting);

      // Brief noise at t = 0
      const noise = coordinator.evaluateRecognitionResult("cough");
      expect(noise.allowTurn).toBe(false);
      expect(noise.isBargeIn).toBe(false);

      // Agent continues speaking; at t = 500 ms agent audio ends
      vi.advanceTimersByTime(500);
      coordinator.onAgentAudioAllFinished();

      // At t = 900 ms (past tail), real customer speech arrives
      vi.advanceTimersByTime(400);
      const validTurn = coordinator.evaluateRecognitionResult("My delivery is delayed");
      expect(validTurn.allowTurn).toBe(true);
      expect(validTurn.isBargeIn).toBe(false);
      expect(validTurn.echoFilterDropped).toBe(false);
    });
  });

  describe("Greeting by Language", () => {
    it("returns appropriate greeting per supported language", () => {
      expect(getGreetingForLanguage("en-IN")).toBe("Hello! I am ResolveAI. How can I help you today?");
      expect(getGreetingForLanguage("tanglish")).toContain("Vanakkam");
      expect(getGreetingForLanguage("tamil")).toContain("வணக்கம்");
      expect(getGreetingForLanguage("hindi")).toContain("नमस्ते");
      expect(getGreetingForLanguage("hinglish")).toContain("Namaste");
    });
  });
});
