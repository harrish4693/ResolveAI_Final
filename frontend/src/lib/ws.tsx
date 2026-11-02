import { createContext, useContext, useEffect, useRef, useState, useCallback } from "react";
import type { ReactNode } from "react";
import { useAuth } from "./auth";

export interface WebSocketEvent {
  type: string;
  event_id: string;
  timestamp: string;
  conversation_id: number | null;
  data: Record<string, unknown>;
}

export type EventHandler = (event: WebSocketEvent) => void;

interface WebSocketContextType {
  isConnected: boolean;
  subscribe: (eventType: string, handler: EventHandler) => () => void;
  sendTyping: (conversationId: number, isStart: boolean) => void;
  sendVoiceCommand: (command: Record<string, any>) => void;
  sendVoiceChunk: (chunk: Blob | ArrayBuffer) => void;
  sendTranscriptUpdate: (conversationId: number, turnId: string, text: string, isFinal: boolean) => void;
}

const WebSocketContext = createContext<WebSocketContextType | undefined>(undefined);

const MIN_RECONNECT_MS = 1000;
const MAX_RECONNECT_MS = 30000;

export function WebSocketProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const handlersRef = useRef<Map<string, Set<EventHandler>>>(new Map());
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const reconnectDelayRef = useRef(MIN_RECONNECT_MS);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (typeof window === "undefined") return;
    const token = localStorage.getItem("access_token");
    if (!token || !mountedRef.current) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const url = `${protocol}//${host}/api/ws?token=${token}`;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setIsConnected(true);
        reconnectDelayRef.current = MIN_RECONNECT_MS;
      };

      ws.onmessage = (event) => {
        if (!mountedRef.current) return;
        if (event.data instanceof Blob || event.data instanceof ArrayBuffer) {
          const parsed: WebSocketEvent = {
            type: "AUDIO_CHUNK",
            event_id: "",
            timestamp: new Date().toISOString(),
            conversation_id: null,
            data: { chunk: event.data },
          };
          const handlers = handlersRef.current.get("AUDIO_CHUNK");
          if (handlers) {
            handlers.forEach((handler) => handler(parsed));
          }
          return;
        }

        try {
          const parsed: WebSocketEvent = JSON.parse(event.data);
          const eventType = parsed.type;

          const handlers = handlersRef.current.get(eventType);
          if (handlers) {
            handlers.forEach((handler) => handler(parsed));
          }

          const wildcardHandlers = handlersRef.current.get("*");
          if (wildcardHandlers) {
            wildcardHandlers.forEach((handler) => handler(parsed));
          }
        } catch {
          // Ignore non-json frames
        }
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        setIsConnected(false);
        wsRef.current = null;

        // Reconnect with exponential backoff
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = setTimeout(() => {
          reconnectDelayRef.current = Math.min(reconnectDelayRef.current * 2, MAX_RECONNECT_MS);
          connect();
        }, reconnectDelayRef.current);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch (e) {
      console.warn("WebSocket connection failed:", e);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    if (user) {
      connect();
    } else {
      if (wsRef.current) {
        wsRef.current.close();
      }
      setIsConnected(false);
    }

    return () => {
      mountedRef.current = false;
      clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [user, connect]);

  const subscribe = useCallback((eventType: string, handler: EventHandler) => {
    if (!handlersRef.current.has(eventType)) {
      handlersRef.current.set(eventType, new Set());
    }
    handlersRef.current.get(eventType)!.add(handler);

    return () => {
      const handlers = handlersRef.current.get(eventType);
      if (handlers) {
        handlers.delete(handler);
        if (handlers.size === 0) {
          handlersRef.current.delete(eventType);
        }
      }
    };
  }, []);

  const sendTyping = useCallback((conversationId: number, isStart: boolean) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: isStart ? "TYPING_START" : "TYPING_END",
          conversation_id: conversationId,
        }),
      );
    }
  }, []);

  const sendVoiceCommand = useCallback((command: Record<string, any>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(command));
    }
  }, []);

  const sendVoiceChunk = useCallback((chunk: Blob | ArrayBuffer) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(chunk);
    }
  }, []);

  const sendTranscriptUpdate = useCallback((conversationId: number, turnId: string, text: string, isFinal: boolean) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: "TRANSCRIPT_UPDATE",
          conversation_id: conversationId,
          turn_id: turnId,
          text,
          is_final: isFinal,
        })
      );
    }
  }, []);

  return (
    <WebSocketContext.Provider
      value={{ isConnected, subscribe, sendTyping, sendVoiceCommand, sendVoiceChunk, sendTranscriptUpdate }}
    >
      {children}
    </WebSocketContext.Provider>
  );
}

export function useWebSocket() {
  const context = useContext(WebSocketContext);
  if (context === undefined) {
    throw new Error("useWebSocket must be used within a WebSocketProvider");
  }
  return context;
}
