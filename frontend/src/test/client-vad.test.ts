import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  encodeWAV,
  encodeWAVBuffer,
  calculateRMS,
  ClientVADState,
  getConfirmationPrompt,
  transcribeUtterance,
} from "../lib/clientVAD";

describe("Client VAD and 16kHz WAV Encoding", () => {
  it("encodes Float32Array to valid 16-bit 16kHz mono WAV Blob", async () => {
    const sampleRate = 16000;
    const numSamples = 1600; // 100ms
    const samples = new Float32Array(numSamples);
    // Fill with simple sine wave
    for (let i = 0; i < numSamples; i++) {
      samples[i] = Math.sin((2 * Math.PI * 440 * i) / sampleRate);
    }

    const wavBlob = encodeWAV(samples, sampleRate);
    const arrayBuf = encodeWAVBuffer(samples, sampleRate);
    const view = new DataView(arrayBuf);

    // Verify RIFF header
    const riff = String.fromCharCode(view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3));
    expect(riff).toBe("RIFF");
    const wave = String.fromCharCode(view.getUint8(8), view.getUint8(9), view.getUint8(10), view.getUint8(11));
    expect(wave).toBe("WAVE");

    // Channels = 1 (mono)
    expect(view.getUint16(22, true)).toBe(1);
    // Sample rate = 16000
    expect(view.getUint32(24, true)).toBe(16000);
    // Bits per sample = 16
    expect(view.getUint16(34, true)).toBe(16);
  });

  describe("Confirmation Prompts for Low Confidence (< 0.60)", () => {
    it("returns Tanglish confirmation prompt", () => {
      const prompt = getConfirmationPrompt("refund eppo varum", "tanglish");
      expect(prompt).toBe('Neenga "refund eppo varum" nu sonneengala?');
    });

    it("returns Tamil confirmation prompt", () => {
      const prompt = getConfirmationPrompt("பணம் திருடப்பட்டது", "tamil");
      expect(prompt).toBe('நீங்கள் "பணம் திருடப்பட்டது" என்று சொன்னீர்களா?');
    });

    it("returns Hindi confirmation prompt", () => {
      const prompt = getConfirmationPrompt("पैसे कट गए", "hindi");
      expect(prompt).toBe('क्या आपने "पैसे कट गए" कहा?');
    });

    it("returns Hinglish confirmation prompt", () => {
      const prompt = getConfirmationPrompt("paisa cut ho gaya", "hinglish");
      expect(prompt).toBe('Aapne "paisa cut ho gaya" bola kya?');
    });

    it("returns English confirmation prompt", () => {
      const prompt = getConfirmationPrompt("track my order", "english");
      expect(prompt).toBe('Did you mean "track my order"?');
    });
  });

  describe("ClientVADState Voice Detection Lifecycle", () => {
    it("rejects transient noise bursts under minSpeechMs (250ms)", () => {
      const vad = new ClientVADState({
        minSpeechMs: 250,
        endSilenceMs: 700,
        speechEnergyThreshold: 0.05,
      });

      const loudFrame = new Float32Array(800).fill(0.2); // Loud frame (RMS 0.2)
      const silentFrame = new Float32Array(800).fill(0.0); // Silence

      // 100ms loud speech (2 chunks of 50ms)
      vad.processFrame(loudFrame, 50);
      vad.processFrame(loudFrame, 50);

      // Followed by 750ms silence (15 chunks of 50ms)
      let emitted: Blob | null = null;
      for (let i = 0; i < 15; i++) {
        const result = vad.processFrame(silentFrame, 50);
        if (result) emitted = result;
      }

      // Must be rejected because total speech was only 100ms (< 250ms)
      expect(emitted).toBeNull();
    });

    it("emits WAV blob when sustained speech (>= 250ms) followed by end silence (>= 700ms)", () => {
      const vad = new ClientVADState({
        minSpeechMs: 250,
        endSilenceMs: 700,
        speechEnergyThreshold: 0.05,
      });

      const loudFrame = new Float32Array(800).fill(0.2);
      const silentFrame = new Float32Array(800).fill(0.0);

      // 400ms sustained speech (8 chunks of 50ms)
      for (let i = 0; i < 8; i++) {
        vad.processFrame(loudFrame, 50);
      }

      // 700ms silence (14 chunks of 50ms)
      let emitted: Blob | null = null;
      for (let i = 0; i < 14; i++) {
        const res = vad.processFrame(silentFrame, 50);
        if (res) emitted = res;
      }

      expect(emitted).not.toBeNull();
      expect(emitted?.type).toBe("audio/wav");
    });
  });

  describe("transcribeUtterance API Integration", () => {
    beforeEach(() => {
      vi.restoreAllMocks();
    });

    it("triggers confirmation when confidence is < 0.60", async () => {
      const mockWav = new Blob(["dummy wav"], { type: "audio/wav" });
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          transcript: "pannanum",
          language_code: "ta-IN",
          confidence: 0.45,
          provider: "sarvam",
        }),
      });

      const res = await transcribeUtterance(mockWav, "tanglish");
      expect(res.transcript).toBe("pannanum");
      expect(res.needsConfirmation).toBe(true);
      expect(res.confirmationPrompt).toBe('Neenga "pannanum" nu sonneengala?');
    });

    it("does not trigger confirmation when confidence is high (>= 0.60)", async () => {
      const mockWav = new Blob(["dummy wav"], { type: "audio/wav" });
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          transcript: "enaku refund venum",
          language_code: "ta-IN",
          confidence: 0.92,
          provider: "sarvam",
        }),
      });

      const res = await transcribeUtterance(mockWav, "tanglish");
      expect(res.transcript).toBe("enaku refund venum");
      expect(res.needsConfirmation).toBeFalsy();
    });

    it("falls back gracefully to browser on network failure", async () => {
      const mockWav = new Blob(["dummy wav"], { type: "audio/wav" });
      global.fetch = vi.fn().mockRejectedValue(new Error("Network timeout"));

      const res = await transcribeUtterance(mockWav, "en-IN");
      expect(res.fallback).toBe("browser");
      expect(res.reason).toContain("Network timeout");
    });
  });
});
