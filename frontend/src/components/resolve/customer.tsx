import { useState, useEffect, useRef } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import {
  Plus,
  ArrowRight,
  MessageSquare,
  CircleCheck,
  Clock3,
  BookOpen,
  CreditCard,
  UserRound,
  ShieldCheck,
  Globe2,
  ChevronRight,
  Send,
  LockKeyhole,
  WifiOff,
  Bot,
  User,
  Headphones,
  Loader2,
  Sparkles,
  Mic,
  Square,
  Star,
  CheckCircle2,
  Sliders,
  AlertTriangle,
  ShieldAlert,
  RotateCcw,
  Check,
  Phone,
  PhoneOff,
  PhoneCall,
} from "lucide-react";
import { CallWithAgent } from "./CallWithAgent";
import { VoiceCallPage } from "./VoiceCallPage";
export { VoiceCallPage };
import {
  transcribeUtterance,
  downsampleTo16k,
  encodeWAV,
  AudioCaptureSession,
  logVoiceDiagnostic,
  validateCustomerUtterance,
} from "@/lib/clientVAD";
import { logSTTDiagnostic } from "@/lib/voiceDiagnostics";
import { resolveBcp47 } from "@/lib/voiceEchoFilter";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { AudioPlayer } from "@/components/ui/AudioPlayer";
import { ConfirmationModal } from "@/components/ui/ConfirmationModal";
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  PromptInput,
  PromptInputTextarea,
  PromptInputFooter,
  PromptInputSubmit,
} from "@/components/ai-elements/prompt-input";
import { Workspace } from "./workspace";
import { Empty, Heading, Metric, SearchField, Segments, StatusBadge, MetricSkeleton, TableSkeleton, InlineAlert } from "./common";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useWebSocket } from "@/lib/ws";
import conversationArt from "@/assets/conversation-art.jpg";

const topics = [
  {
    title: "Account & security",
    description: "Your profile, sign-in, and keeping your account safe.",
    icon: ShieldCheck,
  },
  {
    title: "Billing & payments",
    description: "Subscriptions, invoices, and payment questions.",
    icon: CreditCard,
  },
  {
    title: "Getting started",
    description: "A little guidance for your first steps.",
    icon: BookOpen,
  },
];

interface ConversationItem {
  id: number;
  subject?: string;
  status: string;
  workflow_state?: string;
  channel?: string;
  created_at: string;
  updated_at?: string;
  customer_id?: number;
}

interface TicketSummary {
  open: number;
  ai_processing: number;
  waiting_for_user: number;
  escalated: number;
  assigned: number;
  human_handling: number;
  resolved: number;
}

function getFriendlyWorkflowState(state?: string) {
  switch (state) {
    case "understanding":
      return "Understanding request…";
    case "searching_knowledge":
    case "deciding":
      return "Checking knowledge base…";
    case "asking_user":
      return "Waiting for your response";
    case "resolving":
      return "Resolving issue…";
    case "escalating":
    case "waiting_for_expert":
      return "Connecting to human expert…";
    case "with_expert":
      return "Connected to support expert";
    case "resolved":
      return "Resolved";
    default:
      return state || "Active";
  }
}

export function CustomerDashboard() {
  const [summary, setSummary] = useState<TicketSummary | null>(null);
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    async function loadData() {
      try {
        const [sumRes, convRes] = await Promise.allSettled([
          api.get("/tickets/summary"),
          api.get("/conversations"),
        ]);
        if (mounted) {
          if (sumRes.status === "fulfilled") {
            setSummary(sumRes.value.data);
          }
          if (convRes.status === "fulfilled") {
            setConversations(convRes.value.data || []);
          }
        }
      } catch (err) {
        console.error("Failed to load dashboard data", err);
      } finally {
        if (mounted) setLoading(false);
      }
    }
    loadData();
    return () => {
      mounted = false;
    };
  }, []);

  const openCount = summary
    ? summary.open +
      summary.ai_processing +
      summary.waiting_for_user +
      (summary.escalated || 0) +
      (summary.assigned || 0) +
      (summary.human_handling || 0)
    : conversations.filter((c) => c.status !== "resolved").length;

  const resolvedCount = summary
    ? summary.resolved
    : conversations.filter((c) => c.status === "resolved").length;
  const waitingCount = summary ? summary.waiting_for_user : 0;

  return (
    <Workspace title="Dashboard" active="Dashboard">
      <Heading
        title="Welcome to your support space"
        description="A little clarity. A quick answer. We’re here to help."
        action={
          <div className="flex items-center gap-2">
            <Button variant="outline" asChild className="gap-1.5 border-primary/30 hover:bg-primary/10">
              <Link to="/call">
                <PhoneCall className="size-4 text-primary" />
                Start Voice Call
              </Link>
            </Button>
            <Button asChild>
              <Link to="/chat/$id" params={{ id: "new" }}>
                <Plus className="mr-1.5 size-4" />
                New conversation
              </Link>
            </Button>
          </div>
        }
      />
      <section className="welcome-band">
        <div className="welcome-copy">
          <span className="eyebrow">Support that gets you</span>
          <h2>Let’s get it resolved.</h2>
          <p>
            Questions, roadblocks, or something not quite right?
            <br className="hidden lg:block" />
            Talk to ResolveAI in the language you’re comfortable with.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <Button asChild>
              <Link to="/chat/$id" params={{ id: "new" }}>
                <MessageSquare className="mr-2 size-4" />
                Start a conversation
                <ArrowRight className="ml-3 size-4" />
              </Link>
            </Button>
            <Button variant="outline" asChild className="gap-2 border-primary/30 hover:bg-primary/10">
              <Link to="/call">
                <PhoneCall className="size-4 text-primary" />
                Start Voice Call
              </Link>
            </Button>
          </div>
          <div className="language-line">
            <Globe2 className="size-3" />
            English<span>·</span>All Indian Languages<span>·</span>Code-Mixed
          </div>
        </div>
        <img
          className="welcome-art"
          src={conversationArt}
          alt="Blue and glass conversation bubbles"
          width={1024}
          height={1024}
        />
      </section>
      <div className="metric-grid">
        {loading ? (
          <>
            <MetricSkeleton />
            <MetricSkeleton />
            <MetricSkeleton />
          </>
        ) : (
          <>
            <Metric
              label="Open conversations"
              value={openCount}
              icon={MessageSquare}
              foot="Active & in progress"
            />
            <Metric
              label="Resolved conversations"
              value={resolvedCount}
              icon={CircleCheck}
              tone="success"
              foot="Successfully solved"
            />
            <Metric
              label="Awaiting response"
              value={waitingCount}
              icon={Clock3}
              tone="warning"
              foot="Requires follow-up"
            />
          </>
        )}
      </div>
      <div className="dashboard-grid">
        <section>
          <div className="section-title">
            <h2>Recent conversations</h2>
            <Button variant="link" size="sm" asChild>
              <Link to="/conversations">
                View all
                <ArrowRight className="ml-1 size-3.5" />
              </Link>
            </Button>
          </div>
          <div className="panel">
            {loading ? (
              <TableSkeleton rows={3} cols={3} />
            ) : conversations.length > 0 ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Conversation</th>
                      <th>Status</th>
                      <th>Last updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {conversations.slice(0, 5).map((c) => (
                      <tr key={c.id}>
                        <td>
                          <Link
                            to="/chat/$id"
                            params={{ id: String(c.id) }}
                            className="font-medium text-foreground hover:underline flex items-center gap-2"
                          >
                            <MessageSquare className="size-3.5 text-muted-foreground shrink-0" />
                            <span className="truncate max-w-[280px]">{c.subject || `Conversation #${c.id}`}</span>
                          </Link>
                        </td>
                        <td>
                          <StatusBadge status={c.status} size="sm" />
                        </td>
                        <td className="text-xs text-muted-foreground">
                          {c.updated_at
                            ? new Date(c.updated_at).toLocaleDateString()
                            : new Date(c.created_at).toLocaleDateString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty
                title="Your conversations start here"
                description="Start a conversation when you need a hand. You’ll find all your updates here."
                icon={MessageSquare}
                action={
                  <Button asChild variant="link" size="sm">
                    <Link to="/chat/$id" params={{ id: "new" }}>
                      Let’s talk
                      <ArrowRight className="ml-1 size-3.5" />
                    </Link>
                  </Button>
                }
              />
            )}
          </div>
        </section>
        <section>
          <div className="section-title">
            <h2>A shortcut to your answer</h2>
          </div>
          <Link to="/call" className="quick-link">
            <span className="small-icon">
              <PhoneCall />
            </span>
            <div className="flex-1">
              <h3>Live Voice Call</h3>
              <p>Speak directly with ResolveAI without typing</p>
            </div>
            <ChevronRight className="size-4 text-muted-foreground" />
          </Link>
          <Link to="/help" className="quick-link">
            <span className="small-icon">
              <Headphones />
            </span>
            <div className="flex-1">
              <h3>Support & Guidance Hub</h3>
              <p>24/7 Voice & Chat assistance from ResolveAI</p>
            </div>
            <ChevronRight className="size-4 text-muted-foreground" />
          </Link>
          <Link to="/conversations" className="quick-link">
            <span className="small-icon">
              <Clock3 />
            </span>
            <div className="flex-1">
              <h3>Check a conversation</h3>
              <p>Pick up where you left off</p>
            </div>
            <ChevronRight className="size-4 text-muted-foreground" />
          </Link>
          <Link to="/settings" className="quick-link">
            <span className="small-icon">
              <UserRound />
            </span>
            <div className="flex-1">
              <h3>Your account, your way</h3>
              <p>Profile and preferences</p>
            </div>
            <ChevronRight className="size-4 text-muted-foreground" />
          </Link>
        </section>
      </div>
      <section className="help-section">
        <div className="section-title">
          <h2>A good place to start</h2>
          <Button asChild variant="link" size="sm">
            <Link to="/help">
              Browse Help Center
              <ArrowRight className="ml-1 size-3.5" />
            </Link>
          </Button>
        </div>
        <div className="topic-grid">
          {topics.map((t) => (
            <Link key={t.title} to="/help" search={{ category: t.title }} className="topic-card">
              <div className="flex justify-between">
                <t.icon className="size-5" />
                <ArrowRight className="size-3.5" />
              </div>
              <h3>{t.title}</h3>
              <p>{t.description}</p>
            </Link>
          ))}
        </div>
      </section>
    </Workspace>
  );
}

export function ConversationsPage() {
  const [query, setQuery] = useState("");
  const [channelFilter, setChannelFilter] = useState("All");
  const [status, setStatus] = useState("All");
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    async function loadConversations() {
      try {
        const res = await api.get("/conversations");
        if (mounted) setConversations(res.data || []);
      } catch (err) {
        console.error("Failed to fetch conversations", err);
      } finally {
        if (mounted) setLoading(false);
      }
    }
    loadConversations();
    return () => {
      mounted = false;
    };
  }, []);

  const isVoiceCall = (c: ConversationItem) => {
    const ch = (c.channel || "").toLowerCase();
    const subj = (c.subject || "").toLowerCase();
    return ch === "voice" || subj.includes("voice call") || subj.includes("call with resolveai");
  };

  const filtered = conversations.filter((c) => {
    const isVoice = isVoiceCall(c);

    const matchesQuery =
      !query.trim() ||
      String(c.id).includes(query) ||
      (c.subject && c.subject.toLowerCase().includes(query.toLowerCase())) ||
      (isVoice && query.toLowerCase().includes("voice"));

    const matchesChannel =
      channelFilter === "All" ||
      channelFilter === "All Channels" ||
      ((channelFilter === "Voice Calls" || channelFilter === "Voice Call") && isVoice) ||
      ((channelFilter === "Chat" || channelFilter === "Text") && !isVoice);

    const matchesStatus =
      status === "All" ||
      status === "All Status" ||
      (status === "Open" && c.status === "open") ||
      (status === "Resolved" && c.status === "resolved") ||
      (status === "Pending" && (c.status === "waiting_for_user" || c.status === "ai_processing")) ||
      ((status === "Voice Call" || status === "Voice Calls") && isVoice);

    return matchesQuery && matchesChannel && matchesStatus;
  });

  return (
    <Workspace title="My Conversations" active="My Conversations">
      <Heading
        title="My conversations"
        description="Every question, voice call, and ticket update in one place."
        action={
          <div className="flex items-center gap-2">
            <Button variant="outline" asChild className="gap-1.5 border-primary/30 hover:bg-primary/10">
              <Link to="/call">
                <PhoneCall className="size-4 text-primary" />
                Start Voice Call
              </Link>
            </Button>
            <Button asChild>
              <Link to="/chat/$id" params={{ id: "new" }}>
                <Plus className="mr-1.5 size-4" />
                New conversation
              </Link>
            </Button>
          </div>
        }
      />
      <div className="filter-bar">
        <SearchField
          value={query}
          onChange={setQuery}
          placeholder="Search conversations, voice calls, or ticket ID…"
        />
        <Segments
          options={["All", "Voice Calls", "Chat"]}
          value={channelFilter}
          onChange={setChannelFilter}
        />
        <Segments
          options={["All", "Open", "Pending", "Resolved"]}
          value={status}
          onChange={setStatus}
        />
      </div>
      <div className="panel">
        {loading ? (
          <TableSkeleton rows={5} cols={6} />
        ) : filtered.length > 0 ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Ticket ID</th>
                  <th>Conversation</th>
                  <th>Channel</th>
                  <th>Status</th>
                  <th>Updated</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((c) => {
                  const isVoice = isVoiceCall(c);
                  return (
                    <tr key={c.id}>
                      <td className="font-mono text-xs text-muted-foreground">#{c.id}</td>
                      <td>
                        <Link
                          to="/chat/$id"
                          params={{ id: String(c.id) }}
                          className="font-medium text-foreground hover:underline flex items-center gap-2 max-w-[320px]"
                        >
                          {isVoice ? (
                            <span className="size-5 rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center shrink-0">
                              <PhoneCall className="size-3" />
                            </span>
                          ) : (
                            <span className="size-5 rounded-md bg-primary/10 text-primary flex items-center justify-center shrink-0">
                              <MessageSquare className="size-3" />
                            </span>
                          )}
                          <span className="truncate">{c.subject || `Conversation #${c.id}`}</span>
                        </Link>
                      </td>
                      <td>
                        {isVoice ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                            <PhoneCall className="size-3" />
                            Voice Call
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-muted text-muted-foreground border border-border">
                            <MessageSquare className="size-3" />
                            Chat
                          </span>
                        )}
                      </td>
                      <td>
                        <StatusBadge status={c.status} size="sm" />
                      </td>
                      <td className="text-xs text-muted-foreground">
                        {c.updated_at
                          ? new Date(c.updated_at).toLocaleDateString()
                          : new Date(c.created_at).toLocaleDateString()}
                      </td>
                      <td>
                        <Button asChild size="sm" variant="ghost">
                          <Link to="/chat/$id" params={{ id: String(c.id) }}>
                            {isVoice ? "Transcript" : "Open Chat"}
                            <ArrowRight className="ml-1 size-3.5" />
                          </Link>
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title={
              query
                ? "No matching conversations"
                : channelFilter === "Voice Calls"
                  ? "No voice calls found"
                  : "No conversations found"
            }
            description={
              query
                ? `No results for “${query}”. Try another search keyword.`
                : channelFilter === "Voice Calls"
                  ? "You haven't initiated any voice calls yet. Speak with ResolveAI anytime via Live Voice Call."
                  : "You don't have any conversations yet. Click 'New conversation' or 'Start Voice Call' to begin."
            }
            icon={channelFilter === "Voice Calls" ? PhoneCall : MessagesSquare}
            action={
              channelFilter === "Voice Calls" ? (
                <Button asChild size="sm" className="gap-2">
                  <Link to="/call">
                    <PhoneCall className="size-3.5" />
                    Start Voice Call
                  </Link>
                </Button>
              ) : (
                <Button asChild variant="outline" size="sm">
                  <Link to="/chat/$id" params={{ id: "new" }}>
                    <Plus className="mr-1.5 size-3.5" />
                    Start new conversation
                  </Link>
                </Button>
              )
            }
          />
        )}
      </div>
    </Workspace>
  );
}

export function ConversationDetails({ id }: { id: string }) {
  const [conversation, setConversation] = useState<any>(null);
  const [messages, setMessages] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    async function loadData() {
      try {
        const [cRes, mRes] = await Promise.all([
          api.get(`/conversations/${id}`),
          api.get(`/conversations/${id}/messages`),
        ]);
        if (mounted) {
          setConversation(cRes.data);
          setMessages(mRes.data || []);
        }
      } catch (err) {
        console.error("Failed to load conversation details", err);
      } finally {
        if (mounted) setLoading(false);
      }
    }
    loadData();
    return () => {
      mounted = false;
    };
  }, [id]);

  return (
    <Workspace title="Conversation details" active="My Conversations">
      <Button variant="link" asChild className="mb-5 !px-0">
        <Link to="/conversations">← Back to conversations</Link>
      </Button>
      <Heading
        title={conversation?.subject || `Conversation #${id}`}
        description={`Status: ${conversation?.status || "Loading..."} · Workflow: ${conversation?.workflow_state || "normal"}`}
        action={
          <Button asChild>
            <Link to="/chat/$id" params={{ id }}>
              <MessageSquare className="mr-1.5 size-4" />
              Open in Live Chat
            </Link>
          </Button>
        }
      />
      <div className="panel space-y-4">
        {loading ? (
          <TableSkeleton rows={4} cols={4} />
        ) : conversation ? (
          <div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pb-4 border-b">
              <div>
                <span className="text-xs text-muted-foreground block">Ticket ID</span>
                <span className="font-semibold text-sm">#{conversation.id}</span>
              </div>
              <div>
                <span className="text-xs text-muted-foreground block mb-1">Status</span>
                <StatusBadge status={conversation.status} />
              </div>
              <div>
                <span className="text-xs text-muted-foreground block">Created</span>
                <span className="font-semibold text-sm">
                  {new Date(conversation.created_at).toLocaleString()}
                </span>
              </div>
              <div>
                <span className="text-xs text-muted-foreground block">Messages</span>
                <span className="font-semibold text-sm">{messages.length} messages</span>
              </div>
            </div>
            <div className="mt-6 space-y-3">
              <h3 className="text-sm font-semibold">Message History</h3>
              {messages.map((m) => {
                const sType = (m.sender_type || "").toLowerCase();
                const isClient = sType === "customer" || sType === "user";
                return (
                  <div
                    key={m.id}
                    className={`flex flex-col max-w-[80%] ${
                      isClient ? "ml-auto items-end" : "mr-auto items-start"
                    }`}
                  >
                    <div
                      className={`flex items-center gap-1.5 mb-1 text-xs text-muted-foreground ${
                        isClient ? "self-end" : "self-start"
                      }`}
                    >
                      {isClient ? (
                        <>
                          <span>
                            {new Date(m.created_at).toLocaleTimeString([], {
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </span>
                          <span>·</span>
                          <span className="font-medium text-foreground">You</span>
                          <User className="size-3" />
                        </>
                      ) : (
                        <>
                          <Bot className="size-3 text-primary" />
                          <span className="font-medium text-foreground">ResolveAI</span>
                          <span>·</span>
                          <span>
                            {new Date(m.created_at).toLocaleTimeString([], {
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </span>
                        </>
                      )}
                    </div>
                    <div
                      className={`p-3 rounded-2xl text-sm leading-relaxed ${
                        isClient
                          ? "bg-primary text-primary-foreground rounded-tr-none shadow-sm"
                          : "bg-muted text-foreground rounded-tl-none border border-border shadow-xs"
                      }`}
                    >
                      {m.message_type === "voice" && m.audio_url && (
                        <div className="mb-2">
                          <AudioPlayer url={m.audio_url} />
                        </div>
                      )}
                      <p className="whitespace-pre-wrap">{m.content}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <Empty title="Conversation not found" description="We couldn't load this conversation." />
        )}
      </div>
    </Workspace>
  );
}

export interface MessageItem {
  id: number;
  sender_type: string;
  content: string;
  created_at: string;
  message_type?: string;
  audio_url?: string;
  metadata_?: { is_internal?: boolean; requires_handoff_confirmation?: boolean; [key: string]: any };
}

export const MACROS = [
  { trigger: "/hello", label: "Greeting", text: "Hello, I am a support expert. How can I assist you today?" },
  { trigger: "/security", label: "Security", text: "Hello, I am a security support expert. I will help you with this issue." },
  { trigger: "/payment", label: "Billing", text: "I can help you review your recent payments. Give me just a moment." },
  { trigger: "/resolve", label: "Wrap-up", text: "I'm glad we could resolve this. Let me know if you need anything else!" },
  { trigger: "/close", label: "Closing", text: "I will go ahead and close this ticket now. Have a great day!" },
];

export const DICTATION_LANGUAGES = [
  { code: "unknown", label: "Auto", title: "Auto-Detect (All Indian Languages & English)" },
  { code: "en-IN", label: "EN (IN)", title: "English (India)" },
  { code: "ta-IN", label: "Tamil", title: "Tamil (தமிழ் / Tanglish)" },
  { code: "hi-IN", label: "Hindi", title: "Hindi (हिन्दी / Hinglish)" },
  { code: "kn-IN", label: "Kannada", title: "Kannada (ಕನ್ನಡ / Kanglish)" },
  { code: "te-IN", label: "Telugu", title: "Telugu (తెలుగు / Tenglish)" },
  { code: "ml-IN", label: "Malayalam", title: "Malayalam (മലയാളം / Manglish)" },
  { code: "bn-IN", label: "Bengali", title: "Bengali (বাংলা / Benglish)" },
  { code: "mr-IN", label: "Marathi", title: "Marathi (मराठी / Marathish)" },
  { code: "gu-IN", label: "Gujarati", title: "Gujarati (ગુજરાતી / Gujlish)" },
  { code: "pa-IN", label: "Punjabi", title: "Punjabi (ਪੰਜਾਬੀ / Punglish)" },
  { code: "od-IN", label: "Odia", title: "Odia (ଓଡ଼ିଆ / Odlish)" },
  { code: "as-IN", label: "Assamese", title: "Assamese (অসমীয়া)" },
  { code: "ur-IN", label: "Urdu", title: "Urdu (اردو / Roman Urdu)" },
  { code: "en-US", label: "EN (US)", title: "English (United States)" },
] as const;

export const DICTATION_MODES = [
  { mode: "translit", label: "Romanized", title: "Romanized Latin script (Tanglish, Hinglish, Kanglish, etc.)" },
  { mode: "codemix", label: "Code-Mixed", title: "Indic native script + English technical terms" },
  { mode: "transcribe", label: "Native Script", title: "Full transcription in native Indian script" },
] as const;

export function ChatSurface({
  conversationId = "new",
  expert = false,
}: {
  conversationId?: string;
  expert?: boolean;
}) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { isConnected, subscribe, sendTyping, sendVoiceCommand, sendVoiceChunk } = useWebSocket();

  const isNew = conversationId === "new";
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [conversation, setConversation] = useState<any>(null);
  const [draft, setDraft] = useState("");
  const [mode, setMode] = useState("Reply");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState("");
  const [otherTyping, setOtherTyping] = useState(false);
  const [toolActivity, setToolActivity] = useState<{ toolName: string; status: string } | null>(
    null,
  );

  // Agentic Tool Confirmation State
  const [pendingConfirmation, setPendingConfirmation] = useState<{
    executionId: number;
    toolName: string;
  } | null>(null);
  const [isConfirming, setIsConfirming] = useState(false);

  // CSAT Feedback State
  const [rating, setRating] = useState<number>(0);
  const [feedbackComment, setFeedbackComment] = useState("");
  const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);

  // Voice Dictation State (Universal Multilingual Saaras v4 STT & Web Speech Fallback)
  const [dictationState, setDictationState] = useState<
    "idle" | "requesting_permission" | "listening" | "finalizing" | "uploading" | "transcribing" | "draft_updated"
  >("idle");
  const [dictationLang, setDictationLang] = useState<string>("en-IN");
  const dictationLangRef = useRef<string>("en-IN");
  dictationLangRef.current = dictationLang;
  const [dictationMode, setDictationMode] = useState<string>("translit");
  const dictationModeRef = useRef<string>("translit");
  dictationModeRef.current = dictationMode;
  const [dictationEngine, setDictationEngine] = useState<"auto" | "neural" | "browser">("auto");
  const dictationEngineRef = useRef<"auto" | "neural" | "browser">("auto");
  dictationEngineRef.current = dictationEngine;
  const [interimTranscript, setInterimTranscript] = useState<string>("");
  const committedSpokenRef = useRef<string>("");
  const currentSessionFinalsRef = useRef<string>("");
  const interimSpokenRef = useRef<string>("");
  const recognitionRef = useRef<any>(null);
  const baseDraftRef = useRef<string>("");
  const userRequestedStopRef = useRef<boolean>(false);
  const restartTimerRef = useRef<any>(null);
  const restartCountRef = useRef<number>(0);
  const lastRestartTimeRef = useRef<number>(0);
  const micStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorNodeRef = useRef<ScriptProcessorNode | null>(null);
  const audioChunksRef = useRef<Float32Array[]>([]);
  const captureSessionRef = useRef<AudioCaptureSession | null>(null);
  const activeUtteranceIdRef = useRef<string>("");
  const isSendingRef = useRef<boolean>(false);
  const lastSubmittedTextRef = useRef<string>("");

  // LiveKit Call with Agent State
  const [isInCall, setIsInCall] = useState(false);

  const seenIds = useRef<Set<number>>(new Set());
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, otherTyping, toolActivity, pendingConfirmation]);

  useEffect(() => {
    if (isNew) {
      setMessages([]);
      setConversation(null);
      seenIds.current.clear();
      setRating(0);
      setFeedbackSubmitted(false);
      return;
    }

    let mounted = true;
    async function loadConvo() {
      try {
        setError("");
        const [cRes, mRes] = await Promise.all([
          api.get(`/conversations/${conversationId}`),
          api.get(`/conversations/${conversationId}/messages`),
        ]);
        if (mounted) {
          setConversation(cRes.data);
          const msgs: MessageItem[] = mRes.data || [];
          setMessages(msgs);
          msgs.forEach((m) => seenIds.current.add(m.id));

          if (cRes.data?.preferred_language) {
            const resolved = resolveBcp47(undefined, cRes.data.preferred_language);
            setDictationLang(resolved);
            dictationLangRef.current = resolved;
          }
        }
      } catch (err: any) {
        if (mounted) {
          console.error("Failed to load conversation", err);
          setError("Failed to load conversation. Please try again.");
        }
      }
    }
    loadConvo();

    // Fallback polling for live synchronization (e.g. if WebSocket is briefly reconnecting)
    const pollInterval = setInterval(async () => {
      if (!mounted) return;
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return;
      try {
        const mRes = await api.get(`/conversations/${conversationId}/messages`);
        if (mounted && Array.isArray(mRes.data)) {
          const fetchedMsgs: MessageItem[] = mRes.data;
          let hasNew = false;
          for (const m of fetchedMsgs) {
            if (!seenIds.current.has(m.id)) {
              hasNew = true;
              break;
            }
          }
          if (hasNew) {
            fetchedMsgs.forEach((m) => seenIds.current.add(m.id));
            setMessages(fetchedMsgs);
          }
        }
      } catch {
        // Silently ignore background poll errors
      }
    }, 3500);

    return () => {
      mounted = false;
      clearInterval(pollInterval);
    };
  }, [conversationId, isNew]);

  useEffect(() => {
    if (isNew || !conversationId) return;
    const cid = parseInt(conversationId);
    if (isNaN(cid)) return;

    const unsubMsg = subscribe("NEW_MESSAGE", (event) => {
      if (event.conversation_id !== cid) return;
      const data = event.data as any;
      if (seenIds.current.has(data.message_id)) return;
      seenIds.current.add(data.message_id);

      const newMsg: MessageItem = {
        id: data.message_id,
        sender_type: (data.sender_type || "ASSISTANT").toUpperCase(),
        content: data.content,
        created_at: data.created_at || new Date().toISOString(),
        message_type: data.message_type,
        audio_url: data.audio_url,
        metadata_: data.metadata_ || (data.is_internal ? { is_internal: true } : undefined),
      };
      setMessages((prev) => {
        const filtered = prev.filter(
          (m) =>
            !(
              m.id < 0 &&
              m.content === newMsg.content &&
              m.sender_type === newMsg.sender_type
            ),
        );
        return [...filtered, newMsg];
      });
      setOtherTyping(false);
      setToolActivity(null);
    });

    const unsubTyping = subscribe("TYPING_START", (event) => {
      if (event.conversation_id !== cid) return;
      if (event.data?.sender_type === user?.role) return;
      setOtherTyping(true);
      setTimeout(() => setOtherTyping(false), 4000);
    });

    const unsubUpdated = subscribe("CONVERSATION_UPDATED", (event) => {
      if (event.conversation_id !== cid) return;
      setConversation((prev: any) => (prev ? { ...prev, ...event.data } : prev));
    });

    const unsubTool = subscribe("AGENTIC_TOOL_ACTIVITY", (event) => {
      if (event.conversation_id !== cid) return;
      setToolActivity(event.data as any);
    });

    const unsubConfirm = subscribe("TOOL_CONFIRMATION_REQUIRED", (event) => {
      if (event.conversation_id !== cid) return;
      const data = event.data as any;
      if (data.execution_id && data.tool_name) {
        setPendingConfirmation({
          executionId: data.execution_id,
          toolName: data.tool_name,
        });
      }
    });

    const unsubCallEnded = subscribe("VOICE_CALL_ENDED", (event) => {
      if (event.conversation_id === cid) {
        setIsInCall(false);
      }
    });

    return () => {
      unsubMsg();
      unsubTyping();
      unsubUpdated();
      unsubTool();
      unsubConfirm();
      unsubCallEnded();
    };
  }, [conversationId, isNew, subscribe, user?.role]);

  // Cleanup speech recognition and microphone audio on unmount or conversation change
  useEffect(() => {
    return () => {
      userRequestedStopRef.current = true;
      if (restartTimerRef.current) {
        clearTimeout(restartTimerRef.current);
        restartTimerRef.current = null;
      }
      activeUtteranceIdRef.current = "";
      if (captureSessionRef.current) {
        try {
          captureSessionRef.current.abort();
        } catch {}
        captureSessionRef.current = null;
      }
      if (recognitionRef.current) {
        try {
          recognitionRef.current.onstart = null;
          recognitionRef.current.onresult = null;
          recognitionRef.current.onerror = null;
          recognitionRef.current.onend = null;
          recognitionRef.current.abort();
        } catch {}
        recognitionRef.current = null;
      }
      if (micStreamRef.current) {
        try {
          micStreamRef.current.getTracks().forEach((t) => t.stop());
        } catch {}
        micStreamRef.current = null;
      }
      if (audioContextRef.current) {
        try {
          audioContextRef.current.close();
        } catch {}
        audioContextRef.current = null;
      }
    };
  }, [conversationId]);

  // Universal Multilingual Voice Dictation controls
  const startDictation = async (overrideLang?: string | unknown) => {
    const explicitLang = typeof overrideLang === "string" ? overrideLang : undefined;
    if (typeof window === "undefined") return;

    // Idempotency: Ignore rapid re-triggers while already transitioning
    if (
      dictationState === "requesting_permission" ||
      dictationState === "finalizing" ||
      dictationState === "uploading" ||
      dictationState === "transcribing"
    ) {
      return;
    }

    // Stop any existing session first
    if (captureSessionRef.current || recognitionRef.current || audioContextRef.current) {
      await stopDictation();
    }

    userRequestedStopRef.current = false;
    restartCountRef.current = 0;
    lastRestartTimeRef.current = Date.now();
    if (restartTimerRef.current) {
      clearTimeout(restartTimerRef.current);
      restartTimerRef.current = null;
    }

    const currentDraft = draft.trim();
    if (currentDraft && currentDraft === lastSubmittedTextRef.current) {
      setDraft("");
      baseDraftRef.current = "";
    } else {
      baseDraftRef.current = currentDraft;
    }
    committedSpokenRef.current = "";
    currentSessionFinalsRef.current = "";
    interimSpokenRef.current = "";
    setInterimTranscript("");
    setError("");

    const utteranceId = `dict_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
    activeUtteranceIdRef.current = utteranceId;

    logVoiceDiagnostic({
      feature: "chat_dictation",
      sessionId: conversationId || "new",
      utteranceId,
      state: "requesting_permission",
      transitionReason: "user_started_dictation",
    });

    setDictationState("requesting_permission");

    // 1. Primary path: Browser Web Speech API for real-time streaming incremental transcription
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    const startBrowserSession = (targetLang: string, retryAttempt: number = 0) => {
      if (typeof window === "undefined") return;
      const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (!SR) return;

      logSTTDiagnostic({
        sessionId: conversationId || "new",
        feature: "chat_dictation",
        event: "START_ATTEMPT",
        selectedLang: targetLang,
        details: { retryAttempt },
      });

      if (recognitionRef.current) {
        try {
          recognitionRef.current.onstart = null;
          recognitionRef.current.onresult = null;
          recognitionRef.current.onerror = null;
          recognitionRef.current.onend = null;
          recognitionRef.current.abort();
        } catch {}
        recognitionRef.current = null;
      }

      try {
        const recognition = new SR();
        recognition.lang = targetLang;
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.maxAlternatives = 1;

        recognition.onstart = () => {
          if (activeUtteranceIdRef.current !== utteranceId) return;
          setDictationState("listening");
          logVoiceDiagnostic({
            feature: "chat_dictation",
            sessionId: conversationId || "new",
            utteranceId,
            state: "listening",
            transitionReason: "speech_recognition_started",
          });
          logSTTDiagnostic({
            sessionId: conversationId || "new",
            feature: "chat_dictation",
            event: "ONSTART",
            selectedLang: targetLang,
            micLive: true,
          });
        };

        recognition.onresult = (event: any) => {
          if (activeUtteranceIdRef.current !== utteranceId || recognitionRef.current !== recognition) {
            return;
          }

          let sessionFinals = "";
          let sessionInterim = "";

          for (let i = 0; i < event.results.length; i++) {
            const res = event.results[i];
            const text = (res[0]?.transcript || "").trim();
            if (!text) continue;
            if (res.isFinal) {
              sessionFinals += (sessionFinals ? " " : "") + text;
            } else {
              sessionInterim += (sessionInterim ? " " : "") + text;
            }
          }

          currentSessionFinalsRef.current = sessionFinals;
          interimSpokenRef.current = sessionInterim;
          setInterimTranscript(sessionInterim);

          const base = baseDraftRef.current.trim();
          const totalCommitted = [committedSpokenRef.current, sessionFinals].filter(Boolean).join(" ").trim();
          const spoken = [totalCommitted, sessionInterim].filter(Boolean).join(" ").trim();
          const combined = base ? (spoken ? `${base} ${spoken}` : base) : spoken;
          setDraft(combined);

          const lastResult = event.results[event.results.length - 1];
          logSTTDiagnostic({
            sessionId: conversationId || "new",
            feature: "chat_dictation",
            event: "ONRESULT",
            selectedLang: targetLang,
            resultIndex: event.resultIndex,
            resultsLength: event.results?.length,
            resultChunk: lastResult?.[0]?.transcript,
            isFinal: lastResult?.isFinal,
            committedLength: totalCommitted.length,
            committedText: totalCommitted,
            interimText: sessionInterim,
          });
        };

        recognition.onerror = (event: any) => {
          if (activeUtteranceIdRef.current !== utteranceId || recognitionRef.current !== recognition) {
            return;
          }

          const err = event.error;
          logSTTDiagnostic({
            sessionId: conversationId || "new",
            feature: "chat_dictation",
            event: "ONERROR",
            selectedLang: targetLang,
            error: err,
          });

          if (err === "aborted") {
            if (userRequestedStopRef.current) {
              setDictationState("idle");
              setInterimTranscript("");
              recognitionRef.current = null;
            } else {
              // Transient abort by Chrome: restart recognition safely with small backoff
              if (restartTimerRef.current) clearTimeout(restartTimerRef.current);
              restartTimerRef.current = setTimeout(() => {
                if (!userRequestedStopRef.current && activeUtteranceIdRef.current === utteranceId) {
                  startBrowserSession(dictationLangRef.current);
                }
              }, 250);
            }
            return;
          }

          if (err === "not-allowed" || err === "permission-denied") {
            userRequestedStopRef.current = true;
            setError("Microphone permission denied. Please allow microphone access in your browser settings.");
            setDictationState("idle");
            setInterimTranscript("");
            recognitionRef.current = null;
          } else if (err === "no-speech") {
            // If user has already spoken in this session, treat as a recoverable pause between sentences
            if (committedSpokenRef.current || currentSessionFinalsRef.current || interimSpokenRef.current) {
              return;
            }
            // If nothing was spoken at all, inform the user and transition to idle
            userRequestedStopRef.current = true;
            setError("No speech was detected. Please try speaking again.");
            setDictationState("idle");
            setInterimTranscript("");
            recognitionRef.current = null;
          } else if (err === "audio-capture") {
            userRequestedStopRef.current = true;
            setError("Microphone is unavailable or already in use by another application.");
            setDictationState("idle");
            setInterimTranscript("");
            recognitionRef.current = null;
          } else if (err === "network") {
            userRequestedStopRef.current = true;
            setError("Speech recognition network error. Please check your connection.");
            setDictationState("idle");
            setInterimTranscript("");
            recognitionRef.current = null;
          } else if (err === "service-not-allowed") {
            userRequestedStopRef.current = true;
            setError("Speech recognition service is not permitted or available.");
            setDictationState("idle");
            setInterimTranscript("");
            recognitionRef.current = null;
          } else {
            userRequestedStopRef.current = true;
            setError(`Speech recognition error: ${err}`);
            setDictationState("idle");
            setInterimTranscript("");
            recognitionRef.current = null;
          }
        };

        recognition.onend = () => {
          if (activeUtteranceIdRef.current !== utteranceId || recognitionRef.current !== recognition) {
            return;
          }

          // Fold BOTH current session finals AND uncommitted interim into committedSpokenRef without losing words!
          // Chrome frequently fires onend during natural pauses before marking the last interim as isFinal.
          const sessionSpoken = [
            currentSessionFinalsRef.current,
            interimSpokenRef.current,
          ].filter(Boolean).join(" ").trim();

          if (sessionSpoken) {
            committedSpokenRef.current = [
              committedSpokenRef.current,
              sessionSpoken,
            ].filter(Boolean).join(" ").trim();
            currentSessionFinalsRef.current = "";
            interimSpokenRef.current = "";
          }
          setInterimTranscript("");

          const base = baseDraftRef.current.trim();
          const spoken = committedSpokenRef.current.trim();
          const combined = base ? (spoken ? `${base} ${spoken}` : base) : spoken;
          setDraft(combined);

          logSTTDiagnostic({
            sessionId: conversationId || "new",
            feature: "chat_dictation",
            event: "ONEND",
            selectedLang: targetLang,
            committedText: committedSpokenRef.current,
          });

          if (!userRequestedStopRef.current) {
            // Continuous speech: automatically restart with a fresh SpeechRecognition instance
            const now = Date.now();
            if (now - lastRestartTimeRef.current < 15000) {
              restartCountRef.current += 1;
            } else {
              restartCountRef.current = 1;
              lastRestartTimeRef.current = now;
            }

            // Rate-limit restarts (max 25 consecutive restarts without user speech) to prevent tight loops
            if (restartCountRef.current <= 25) {
              if (restartTimerRef.current) clearTimeout(restartTimerRef.current);
              logSTTDiagnostic({
                sessionId: conversationId || "new",
                feature: "chat_dictation",
                event: "RESTART_SCHEDULED",
                selectedLang: targetLang,
                details: { restartCount: restartCountRef.current },
              });
              restartTimerRef.current = setTimeout(() => {
                if (!userRequestedStopRef.current && activeUtteranceIdRef.current === utteranceId) {
                  logSTTDiagnostic({
                    sessionId: conversationId || "new",
                    feature: "chat_dictation",
                    event: "RESTART_TRIGGERED",
                    selectedLang: dictationLangRef.current,
                  });
                  startBrowserSession(dictationLangRef.current);
                }
              }, 220); // 220ms allows Chrome audio hardware enough time to release
              return;
            }
          }

          // User explicitly stopped or restart budget exceeded
          baseDraftRef.current = combined;
          committedSpokenRef.current = "";
          currentSessionFinalsRef.current = "";
          interimSpokenRef.current = "";
          setDictationState("idle");
          recognitionRef.current = null;
        };

        try {
          recognition.start();
          recognitionRef.current = recognition;
          setDictationState("listening");
          logSTTDiagnostic({
            sessionId: conversationId || "new",
            feature: "chat_dictation",
            event: "START_SUCCESS",
            selectedLang: targetLang,
          });
        } catch (startErr: any) {
          logSTTDiagnostic({
            sessionId: conversationId || "new",
            feature: "chat_dictation",
            event: "START_EXCEPTION",
            selectedLang: targetLang,
            error: startErr?.message || String(startErr),
          });
          // Retry with backoff if Chrome mic hardware was not yet freed
          if (!userRequestedStopRef.current && activeUtteranceIdRef.current === utteranceId && retryAttempt < 3) {
            const delay = 250 * Math.pow(2, retryAttempt);
            logSTTDiagnostic({
              sessionId: conversationId || "new",
              feature: "chat_dictation",
              event: "RESTART_SCHEDULED",
              selectedLang: targetLang,
              details: { retryAttempt: retryAttempt + 1, delay },
            });
            setTimeout(() => {
              if (!userRequestedStopRef.current && activeUtteranceIdRef.current === utteranceId) {
                startBrowserSession(targetLang, retryAttempt + 1);
              }
            }, delay);
          }
        }
      } catch (err: any) {
        console.warn("SpeechRecognition startup failed, checking fallback:", err);
      }
    };

    if (SpeechRecognition && dictationEngineRef.current !== "neural") {
      startBrowserSession(explicitLang || dictationLangRef.current || dictationLang);
      if (recognitionRef.current) {
        return;
      }
    }

    // 2. High-accuracy Neural STT path (Sarvam Saaras v4) / AudioCaptureSession fallback
    const hasMedia =
      typeof navigator !== "undefined" &&
      navigator.mediaDevices &&
      typeof navigator.mediaDevices.getUserMedia === "function" &&
      (window.AudioContext || (window as any).webkitAudioContext);

    if (hasMedia) {
      try {
        const session = new AudioCaptureSession();
        captureSessionRef.current = session;

        await session.start(utteranceId, {
          onTrackEnded: () => {
            if (activeUtteranceIdRef.current === utteranceId) {
              stopDictation();
            }
          },
        });

        setDictationState("listening");

        logVoiceDiagnostic({
          feature: "chat_dictation",
          sessionId: conversationId || "new",
          utteranceId,
          state: "listening",
          micTrackState: "live",
          audioContextState: "running",
          transitionReason: "mic_capture_started",
        });
        return;
      } catch (micErr: any) {
        captureSessionRef.current = null;
        console.warn("Microphone access error in chat dictation:", micErr);

        logVoiceDiagnostic({
          feature: "chat_dictation",
          sessionId: conversationId || "new",
          utteranceId,
          state: "idle",
          failureCategory: "mic_never_started",
          errorReason: micErr?.message || "getUserMedia_failed",
        });

        if (
          micErr?.name === "NotAllowedError" ||
          micErr?.name === "PermissionDeniedError" ||
          micErr?.message?.includes("denied") ||
          micErr?.message?.includes("Permission denied")
        ) {
          setError("Microphone permission denied. Please allow microphone access in your browser settings.");
          setDictationState("idle");
          return;
        }
        if (micErr?.name === "NotFoundError" || micErr?.name === "DevicesNotFoundError") {
          setError("Microphone is unavailable or already in use by another application.");
          setDictationState("idle");
          return;
        }
      }
    }

    // 3. Fallback: Neither Web Speech API nor MediaDevices supported
    logVoiceDiagnostic({
      feature: "chat_dictation",
      sessionId: conversationId || "new",
      utteranceId,
      state: "idle",
      failureCategory: "mic_never_started",
      errorReason: "Speech recognition not supported in browser",
    });
    setError("Speech recognition is not supported in this browser. Please type your message.");
    setDictationState("idle");
  };

  const stopDictation = async () => {
    userRequestedStopRef.current = true;
    if (restartTimerRef.current) {
      clearTimeout(restartTimerRef.current);
      restartTimerRef.current = null;
    }

    // 1. If AudioCaptureSession was active
    if (captureSessionRef.current) {
      const session = captureSessionRef.current;
      captureSessionRef.current = null;
      const currentUtteranceId = activeUtteranceIdRef.current;

      setDictationState("finalizing");
      logVoiceDiagnostic({
        feature: "chat_dictation",
        sessionId: conversationId || "new",
        utteranceId: currentUtteranceId,
        state: "finalizing",
        transitionReason: "user_stopped_dictation",
      });

      const finalized = await session.stop();

      // Check if session had valid audio
      if (!finalized || finalized.sampleCount < 400 || finalized.isSilent) {
        logVoiceDiagnostic({
          feature: "chat_dictation",
          sessionId: conversationId || "new",
          utteranceId: currentUtteranceId,
          state: "idle",
          failureCategory: !finalized || finalized.sampleCount === 0 ? "no_frames_received" : "audio_silent",
          frameCount: finalized?.sampleCount,
          rms: finalized?.rms,
          peak: finalized?.peak,
        });
        setError("No speech was detected. Please try speaking closer to the microphone.");
        setDictationState("idle");
        return;
      }

      setDictationState("uploading");
      const uploadStartTime = Date.now();

      logVoiceDiagnostic({
        feature: "chat_dictation",
        sessionId: conversationId || "new",
        utteranceId: currentUtteranceId,
        state: "uploading",
        payloadBytes: finalized.wavBlob.size,
        audioDurationSeconds: finalized.durationSeconds,
        rms: finalized.rms,
        peak: finalized.peak,
        frameCount: finalized.sampleCount,
        sampleRate: finalized.sampleRate,
      });

      setDictationState("transcribing");

      try {
        const langCode = dictationLangRef.current === "unknown" ? "unknown" : dictationLangRef.current;
        const res = await transcribeUtterance(finalized.wavBlob, langCode, dictationModeRef.current);

        const uploadDuration = Date.now() - uploadStartTime;

        // Verify this response is for the active utterance (reject stale responses)
        if (activeUtteranceIdRef.current !== currentUtteranceId) {
          console.warn("Discarding stale transcription response for utterance", currentUtteranceId);
          return;
        }

        const recognizedText = (res.transcript || "").trim();
        const validation = validateCustomerUtterance(recognizedText, res.confidence);

        if (recognizedText && validation.isValid) {
          logVoiceDiagnostic({
            feature: "chat_dictation",
            sessionId: conversationId || "new",
            utteranceId: currentUtteranceId,
            state: "draft_updated",
            uploadDurationMs: uploadDuration,
            sttProvider: res.provider || "sarvam",
            sttStatus: "success",
            transcriptCharCount: recognizedText.length,
          });

          // Insert transcript into draft preserving user's typing without auto-sending
          setDraft((prevDraft) => {
            const base = prevDraft.trim();
            const combined = base ? `${base} ${recognizedText}` : recognizedText;
            baseDraftRef.current = combined;
            return combined;
          });

          setDictationState("draft_updated");
          setTimeout(() => {
            setDictationState((curr) => (curr === "draft_updated" ? "idle" : curr));
          }, 800);
        } else if (recognizedText && !validation.isValid) {
          logVoiceDiagnostic({
            feature: "chat_dictation",
            sessionId: conversationId || "new",
            utteranceId: currentUtteranceId,
            state: "idle",
            failureCategory: "stt_empty_transcript",
            errorReason: `blocked_by_noise_filter: ${validation.reason}`,
          });
          setDictationState("idle");
        } else if (res.fallback === "browser") {
          logVoiceDiagnostic({
            feature: "chat_dictation",
            sessionId: conversationId || "new",
            utteranceId: currentUtteranceId,
            state: "idle",
            sttStatus: "fallback",
            failureCategory: "stt_empty_transcript",
            errorReason: res.reason,
          });
          setError("No speech was detected in your recording. Please try speaking again.");
          setDictationState("idle");
        } else {
          logVoiceDiagnostic({
            feature: "chat_dictation",
            sessionId: conversationId || "new",
            utteranceId: currentUtteranceId,
            state: "idle",
            sttStatus: "empty",
            failureCategory: "stt_empty_transcript",
          });
          setError("No speech was detected. Please try speaking again or type your message.");
          setDictationState("idle");
        }
      } catch (err: any) {
        logVoiceDiagnostic({
          feature: "chat_dictation",
          sessionId: conversationId || "new",
          utteranceId: currentUtteranceId,
          state: "idle",
          failureCategory: "upload_failed",
          errorReason: err?.message,
        });
        setError("Failed to transcribe audio. Please check your connection and try again.");
        setDictationState("idle");
      }
      return;
    }

    // 2. Legacy AudioContext fallback (if started without session ref)
    if (audioContextRef.current && micStreamRef.current) {
      setDictationState("finalizing");
      const audioCtx = audioContextRef.current;
      const stream = micStreamRef.current;
      const processor = processorNodeRef.current;

      try {
        processor?.disconnect();
        audioCtx?.close();
        stream.getTracks().forEach((t) => t.stop());
      } catch {}

      audioContextRef.current = null;
      processorNodeRef.current = null;
      micStreamRef.current = null;

      const chunks = audioChunksRef.current;
      audioChunksRef.current = [];

      if (!chunks || chunks.length === 0) {
        setError("No speech was detected. Please try speaking closer to the microphone.");
        setDictationState("idle");
        return;
      }

      let totalSamples = 0;
      for (const c of chunks) totalSamples += c.length;
      const merged = new Float32Array(totalSamples);
      let offset = 0;
      for (const c of chunks) {
        merged.set(c, offset);
        offset += c.length;
      }

      const inputRate = audioCtx.sampleRate || 44100;
      const samples16k = downsampleTo16k(merged, inputRate);
      if (samples16k.length < 400) {
        setError("No speech was detected. Please try speaking closer to the microphone.");
        setDictationState("idle");
        return;
      }

      const wavBlob = encodeWAV(samples16k, 16000);
      setDictationState("uploading");
      setDictationState("transcribing");

      try {
        const langCode = dictationLang === "en-IN" ? "unknown" : dictationLang;
        const res = await transcribeUtterance(wavBlob, langCode, "translit");

        if (res.transcript && res.transcript.trim()) {
          const spoken = res.transcript.trim();
          setDraft((prev) => {
            const base = prev.trim();
            const combined = base ? `${base} ${spoken}` : spoken;
            baseDraftRef.current = combined;
            return combined;
          });
          setDictationState("draft_updated");
          setTimeout(() => setDictationState("idle"), 800);
        } else {
          setError("No speech was detected in your recording. Please try speaking again.");
          setDictationState("idle");
        }
      } catch (err: any) {
        console.error("STT transcription error:", err);
        setError("Failed to transcribe audio. Please try again or type your message.");
        setDictationState("idle");
      }
      return;
    }

    // 3. Browser SpeechRecognition stop
    if (recognitionRef.current) {
      setDictationState("finalizing");
      const currentRec = recognitionRef.current;
      recognitionRef.current = null;
      try {
        currentRec.stop();
      } catch {
        try {
          currentRec.abort();
        } catch {}
        setDictationState("idle");
      }

      const sessionSpoken = [
        currentSessionFinalsRef.current,
        interimSpokenRef.current,
      ].filter(Boolean).join(" ").trim();

      if (sessionSpoken) {
        committedSpokenRef.current = [
          committedSpokenRef.current,
          sessionSpoken,
        ].filter(Boolean).join(" ").trim();
        currentSessionFinalsRef.current = "";
        interimSpokenRef.current = "";
      }

      const base = baseDraftRef.current.trim();
      const spoken = committedSpokenRef.current.trim();
      const validation = validateCustomerUtterance(spoken);
      const validSpoken = validation.isValid ? spoken : "";
      const combined = base ? (validSpoken ? `${base} ${validSpoken}` : base) : validSpoken;
      setDraft(combined);
      baseDraftRef.current = combined;
      committedSpokenRef.current = "";
      interimSpokenRef.current = "";
      setInterimTranscript("");
      setDictationState(validSpoken ? "draft_updated" : "idle");
      if (validSpoken) {
        setTimeout(() => {
          setDictationState((curr) => (curr === "draft_updated" ? "idle" : curr));
        }, 800);
      }
    } else {
      setDictationState("idle");
      setInterimTranscript("");
    }
  };

  // Text input typing debouncer
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setDraft(e.target.value);
    baseDraftRef.current = e.target.value;
    if (isNew || !conversationId) return;

    const cid = parseInt(conversationId);
    if (isNaN(cid)) return;

    if (typingTimerRef.current) {
      clearTimeout(typingTimerRef.current);
    } else {
      sendTyping(cid, true);
    }

    typingTimerRef.current = setTimeout(() => {
      sendTyping(cid, false);
      typingTimerRef.current = null;
    }, 2000);
  };

  const handleSend = async () => {
    if (!draft.trim() || isSending || isSendingRef.current) return;
    isSendingRef.current = true;
    setIsSending(true);
    const content = draft.trim();
    lastSubmittedTextRef.current = content;

    // 1. Immediately invalidate any in-flight dictation/STT utterance
    activeUtteranceIdRef.current = "";
    userRequestedStopRef.current = true;

    // 2. Clear any pending dictation restart timer
    if (restartTimerRef.current) {
      clearTimeout(restartTimerRef.current);
      restartTimerRef.current = null;
    }

    // 3. Immediately stop and detach any active SpeechRecognition instance
    if (recognitionRef.current) {
      const rec = recognitionRef.current;
      recognitionRef.current = null;
      try {
        rec.onstart = null;
        rec.onresult = null;
        rec.onerror = null;
        rec.onend = null;
        rec.abort();
      } catch {}
    }

    // 4. Immediately stop any active AudioCaptureSession or legacy audio context
    if (captureSessionRef.current) {
      try {
        captureSessionRef.current.stop();
      } catch {}
      captureSessionRef.current = null;
    }
    if (audioContextRef.current) {
      try {
        processorNodeRef.current?.disconnect();
        audioContextRef.current.close();
        micStreamRef.current?.getTracks().forEach((t) => t.stop());
      } catch {}
      audioContextRef.current = null;
      processorNodeRef.current = null;
      micStreamRef.current = null;
      audioChunksRef.current = [];
    }

    // 5. Completely clear composer draft and all speech transcript buffers
    setDraft("");
    baseDraftRef.current = "";
    committedSpokenRef.current = "";
    currentSessionFinalsRef.current = "";
    interimSpokenRef.current = "";
    setInterimTranscript("");
    setDictationState("idle");
    setError("");

    if (!isNew && conversationId) {
      const cid = parseInt(conversationId);
      if (!isNaN(cid)) {
        if (typingTimerRef.current) {
          clearTimeout(typingTimerRef.current);
          typingTimerRef.current = null;
        }
        sendTyping(cid, false);
      }
    }

    try {
      if (isNew) {
        const res = await api.post("/conversations", {
          initial_message: content,
          subject: content.substring(0, 50),
        });
        const newConvo = res.data;
        navigate({ to: "/chat/$id", params: { id: String(newConvo.id) } });
      } else {
        const isNote = expert && mode === "Internal note";
        const tempId = -Date.now();
        const optimisticMsg: MessageItem = {
          id: tempId,
          sender_type: isNote ? "NOTE" : (expert ? "EXPERT" : "CUSTOMER"),
          content,
          created_at: new Date().toISOString(),
          metadata_: isNote ? { is_internal: true } : undefined,
        };
        setMessages((prev) => [...prev, optimisticMsg]);

        const res = await api.post(`/conversations/${conversationId}/messages`, {
          content,
          is_internal: isNote,
        });

        if (Array.isArray(res.data)) {
          setMessages(res.data);
          res.data.forEach((m: any) => seenIds.current.add(m.id));
        }
      }
    } catch (err: any) {
      console.error("Failed to send message", err);
      setError(err.response?.data?.detail || "Failed to send message. Please retry.");
    } finally {
      isSendingRef.current = false;
      setIsSending(false);
    }
  };

  const handleToolConfirm = async (action: "accept" | "reject") => {
    if (!pendingConfirmation || !conversationId || isConfirming) return;
    setIsConfirming(true);
    try {
      await api.post(
        `/conversations/${conversationId}/tools/${pendingConfirmation.executionId}/confirm`,
        { action },
      );
      setPendingConfirmation(null);
    } catch (err: any) {
      console.error("Failed to confirm action", err);
      setError("Failed to process tool confirmation: " + (err.response?.data?.detail || err.message));
    } finally {
      setIsConfirming(false);
    }
  };

  const handleHandoffConfirm = async (confirmed: boolean) => {
    if (isSending || !conversationId) return;
    const text = confirmed ? "Aama, connect pannunga" : "Vendaam, continue with AI";
    setIsSending(true);
    setError("");
    try {
      const tempId = -Date.now();
      const optimisticMsg: MessageItem = {
        id: tempId,
        sender_type: "CUSTOMER",
        content: text,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, optimisticMsg]);

      const res = await api.post(`/conversations/${conversationId}/messages`, {
        content: text,
        is_internal: false,
      });

      if (Array.isArray(res.data)) {
        setMessages(res.data);
        res.data.forEach((m: any) => seenIds.current.add(m.id));
      }
    } catch (err: any) {
      console.error("Failed to confirm expert handoff", err);
      setError(err.response?.data?.detail || "Failed to send response. Please retry.");
    } finally {
      setIsSending(false);
    }
  };

  const submitFeedback = async () => {
    if (rating === 0 || !conversationId || isSubmittingFeedback) return;
    setIsSubmittingFeedback(true);
    try {
      await api.post(`/conversations/${conversationId}/feedback`, {
        rating,
        comment: feedbackComment,
      });
      setFeedbackSubmitted(true);
    } catch (err: any) {
      if (err.response?.status === 409) {
        setFeedbackSubmitted(true);
      } else {
        setError("Failed to submit feedback. Please try again.");
      }
    } finally {
      setIsSubmittingFeedback(false);
    }
  };

  const isResolved =
    conversation?.status === "resolved" || conversation?.status === "RESOLVED";

  const isVoice =
    (conversation?.channel || "").toLowerCase() === "voice" ||
    (conversation?.channel || "").toLowerCase() === "call" ||
    ((conversation?.subject || "").toLowerCase().startsWith("voice call"));

  return (
    <div className="chat-layout">
      <div className="chat-header">
        <div className="flex items-center gap-3">
          <span
            data-testid="chat-header-metric-icon"
            className={`metric-icon ${
              isVoice ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" : ""
            }`}
          >
            {isVoice ? <PhoneCall className="size-4" /> : <MessageSquare className="size-4" />}
          </span>
          <div>
            <h2>{expert ? "Customer conversation" : "ResolveAI Support"}</h2>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground mt-0.5">
              <span>
                {conversation?.subject
                  ? conversation.subject
                  : isNew
                    ? "New support conversation"
                    : `Ticket #${conversationId}`}
              </span>
              {!isNew && (
                <>
                  <span>·</span>
                  {isVoice ? (
                    <span
                      data-testid="chat-header-channel-badge"
                      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                    >
                      <PhoneCall className="size-3" />
                      Voice Call
                    </span>
                  ) : (
                    <span
                      data-testid="chat-header-channel-badge"
                      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-muted text-muted-foreground border border-border"
                    >
                      <MessageSquare className="size-3" />
                      Chat
                    </span>
                  )}
                  <span>·</span>
                  <span className="inline-flex items-center gap-1 font-medium text-foreground">
                    <span
                      className={`size-1.5 rounded-full ${
                        isResolved ? "bg-emerald-500" : "bg-primary animate-pulse"
                      }`}
                    />
                    {getFriendlyWorkflowState(conversation?.workflow_state)}
                  </span>
                </>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {!isNew && !isResolved && (
            <>
              <Button
                variant="outline"
                size="sm"
                asChild
                className="h-8 gap-1.5 text-xs font-medium border-primary/30 hover:bg-primary/10 hover:text-primary"
                title="Open dedicated voice call interface"
              >
                <Link to="/call/$id" params={{ id: conversationId }}>
                  <PhoneCall className="size-3.5 text-primary" />
                  <span className="hidden sm:inline">Voice Interface</span>
                </Link>
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsInCall((prev) => !prev)}
                className={`h-8 gap-1.5 text-xs font-medium transition-all ${
                  isInCall
                    ? "bg-destructive text-destructive-foreground hover:bg-destructive/90 border-transparent shadow-xs"
                    : "border-primary/30 hover:bg-primary/10 hover:text-primary"
                }`}
                title={isInCall ? "End voice call" : (expert ? "Join live voice call with customer" : "Start real-time voice call with agent")}
                aria-label={isInCall ? "End voice call" : (expert ? "Join Voice Call" : "Call with Agent")}
              >
                {isInCall ? (
                  <>
                    <PhoneOff className="size-3.5" />
                    <span>{expert ? "In Live Call" : "In Call"}</span>
                  </>
                ) : (
                  <>
                    <Phone className="size-3.5 text-primary" />
                    <span>{expert ? "Join Voice Call" : "Call with Agent"}</span>
                  </>
                )}
              </Button>
            </>
          )}
          {isConnected ? (
            <span className="flex items-center gap-1.5 text-[11px] text-emerald-600 dark:text-emerald-400 font-medium bg-emerald-50 dark:bg-emerald-950/40 px-2.5 py-1 rounded-full">
              <span className="size-2 rounded-full bg-emerald-500 animate-pulse" />
              Live Online
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground bg-muted px-2.5 py-1 rounded-full">
              <WifiOff className="size-3" />
              Connecting…
            </span>
          )}
        </div>
      </div>

      {/* Real-time Call with Agent Surface */}
      {isInCall && conversationId && !isNew && (
        <div className="px-4 pt-2">
          <CallWithAgent
            conversationId={conversationId}
            onEndCall={() => setIsInCall(false)}
            customerName={user?.full_name || "Customer"}
            isExpert={expert}
            initialLanguage={dictationLang}
            preferredLanguage={conversation?.preferred_language}
          />
        </div>
      )}
      <Conversation>
        <ConversationContent>
          {messages.length === 0 ? (
            <div className="chat-empty">
              <span className="logo-mark !size-12">
                <Sparkles className="size-6 text-primary-foreground" />
              </span>
              <h2>{expert ? "Select a case to get started" : "What can we help you with?"}</h2>
              <p>
                {expert
                  ? "Your customer’s conversation, notes, and handoff context will appear here."
                  : "Describe what’s on your mind in any Indian language or English. ResolveAI will handle it right away."}
              </p>
              {!expert && (
                <div className="flex gap-2 mt-6 flex-wrap justify-center">
                  {[
                    "What is your refund policy?",
                    "How do I update my profile?",
                    "I need help with billing",
                    "Something else",
                  ].map((t) => (
                    <Button
                      variant="outline"
                      size="sm"
                      key={t}
                      onClick={() =>
                        setDraft(t === "Something else" ? "I need assistance with " : t)
                      }
                    >
                      {t}
                      <ArrowRight className="!size-3 ml-1" />
                    </Button>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-4 py-4 px-2">
              {messages.map((m) => {
                const sType = (m.sender_type || "").toLowerCase();
                const isInternalNote = Boolean(m.metadata_?.is_internal) || sType === "note";
                const isClient = !isInternalNote && (sType === "customer" || sType === "user");
                const isExpert = !isInternalNote && (sType === "expert" || sType === "human");
                const isNote = isInternalNote;
                const isSelf = expert ? isExpert : isClient;

                if (isNote) {
                  return (
                    <div key={m.id} className="mx-auto max-w-[85%] w-full my-2">
                      <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-600 dark:text-amber-400 text-xs">
                        <div className="flex items-center gap-1.5 font-semibold mb-1">
                          <LockKeyhole className="size-3" />
                          <span>Internal Staff Note</span>
                          <span>·</span>
                          <span className="font-normal opacity-80">
                            {new Date(m.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                          </span>
                        </div>
                        <p className="whitespace-pre-wrap text-foreground font-normal text-sm">{m.content}</p>
                      </div>
                    </div>
                  );
                }

                return (
                  <div
                    key={m.id}
                    className={`flex flex-col max-w-[80%] ${
                      isSelf ? "ml-auto items-end" : "mr-auto items-start"
                    }`}
                  >
                    <div
                      className={`flex items-center gap-1.5 mb-1.5 text-[11px] text-muted-foreground ${
                        isSelf ? "self-end" : "self-start"
                      }`}
                    >
                      {isSelf ? (
                        <>
                          <span>
                            {new Date(m.created_at).toLocaleTimeString([], {
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </span>
                          <span>·</span>
                          <span className="font-medium text-foreground">{expert ? "You (Expert)" : "You"}</span>
                          <div className={`size-4.5 rounded-full flex items-center justify-center ${
                            expert ? "bg-emerald-500/10 text-emerald-600" : "bg-primary/10 text-primary"
                          }`}>
                            {expert ? <Headphones className="size-2.5" /> : <User className="size-2.5" />}
                          </div>
                        </>
                      ) : isClient ? (
                        <>
                          <div className="size-4.5 rounded-full bg-primary/10 flex items-center justify-center text-primary">
                            <User className="size-2.5" />
                          </div>
                          <span className="font-semibold text-foreground">Customer</span>
                          <span>·</span>
                          <span>
                            {new Date(m.created_at).toLocaleTimeString([], {
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </span>
                        </>
                      ) : isExpert ? (
                        <>
                          <div className="size-4.5 rounded-full bg-emerald-500/10 flex items-center justify-center text-emerald-500">
                            <Headphones className="size-2.5" />
                          </div>
                          <span className="font-semibold text-foreground">Support Expert</span>
                          <span>·</span>
                          <span>
                            {new Date(m.created_at).toLocaleTimeString([], {
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </span>
                        </>
                      ) : (
                        <>
                          <div className="size-4.5 rounded-full bg-primary/10 flex items-center justify-center text-primary">
                            <Bot className="size-2.5" />
                          </div>
                          <span className="font-semibold text-foreground">ResolveAI</span>
                          <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-primary/10 text-primary font-medium">
                            AI Agent
                          </span>
                          <span>·</span>
                          <span>
                            {new Date(m.created_at).toLocaleTimeString([], {
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </span>
                        </>
                      )}
                    </div>
                    <div
                      className={`p-3.5 rounded-2xl text-sm leading-relaxed ${
                        isSelf
                          ? expert
                            ? "bg-emerald-600 text-white rounded-tr-none shadow-sm dark:bg-emerald-700"
                            : "bg-primary text-primary-foreground rounded-tr-none shadow-sm"
                          : isClient
                            ? "bg-muted/80 text-foreground rounded-tl-none border border-border shadow-xs"
                            : isExpert
                              ? "bg-card text-foreground rounded-tl-none border border-emerald-500/30 shadow-xs"
                              : "bg-muted text-foreground rounded-tl-none border border-border shadow-xs"
                      }`}
                    >
                      {m.message_type === "voice" && m.audio_url && (
                        <div className="mb-2">
                          <AudioPlayer url={m.audio_url} />
                        </div>
                      )}
                      <p className="whitespace-pre-wrap">{m.content}</p>

                      {/* User Confirmation Before Expert Handoff Action Buttons */}
                      {Boolean(m.metadata_?.requires_handoff_confirmation) && !isClient && (
                        <div className="mt-3 pt-2.5 border-t border-border/50 flex flex-wrap gap-2">
                          <Button
                            type="button"
                            size="sm"
                            disabled={isSending}
                            onClick={() => handleHandoffConfirm(true)}
                            className="text-xs h-7.5 px-3 gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white font-medium shadow-xs"
                          >
                            <Headphones className="size-3" />
                            Yes, connect to expert
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={isSending}
                            onClick={() => handleHandoffConfirm(false)}
                            className="text-xs h-7.5 px-3 gap-1.5 border-border/80 hover:bg-background text-foreground font-medium"
                          >
                            <Bot className="size-3" />
                            No, keep helping here
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}

              {toolActivity && (
                <div className="flex items-center gap-2 p-2.5 rounded-xl bg-primary/5 text-primary text-xs w-fit border border-primary/10">
                  <Loader2 className="size-3.5 animate-spin" />
                  <span>Agent running: {(toolActivity.toolName || "tool").replace(/_/g, " ")}…</span>
                </div>
              )}

              {otherTyping && (
                <div className="flex items-center gap-2 text-xs text-muted-foreground p-2">
                  <Bot className="size-3.5 text-primary" />
                  <span className="flex gap-1">
                    <span className="size-1.5 rounded-full bg-primary animate-bounce" />
                    <span className="size-1.5 rounded-full bg-primary animate-bounce delay-150" />
                    <span className="size-1.5 rounded-full bg-primary animate-bounce delay-300" />
                  </span>
                  <span>Typing a response…</span>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      {/* CSAT Customer Feedback Section for resolved tickets */}
      {isResolved && user?.role === "customer" && (
        <div className="border-t border-border bg-card/60 p-4 shrink-0">
          {!feedbackSubmitted ? (
            <div className="max-w-md mx-auto space-y-3 text-center">
              <p className="text-xs font-semibold text-foreground">How was your support experience?</p>
              <div className="flex justify-center gap-2">
                {[1, 2, 3, 4, 5].map((star) => (
                  <button
                    key={star}
                    type="button"
                    onClick={() => setRating(star)}
                    className="p-1 hover:scale-110 transition-transform"
                    aria-label={`${star} star rating`}
                  >
                    <Star
                      className={`size-6 ${
                        rating >= star
                          ? "text-amber-400 fill-amber-400"
                          : "text-muted-foreground/30 hover:text-amber-300"
                      }`}
                    />
                  </button>
                ))}
              </div>
              {rating > 0 && (
                <div className="space-y-2 animate-in fade-in duration-200">
                  <Textarea
                    placeholder="Optional feedback about the resolution…"
                    value={feedbackComment}
                    onChange={(e) => setFeedbackComment(e.target.value)}
                    className="text-xs h-16 resize-none"
                  />
                  <Button
                    size="sm"
                    className="w-full"
                    onClick={submitFeedback}
                    disabled={isSubmittingFeedback}
                  >
                    {isSubmittingFeedback ? (
                      <Loader2 className="size-3.5 animate-spin mr-1.5" />
                    ) : null}
                    Submit Feedback
                  </Button>
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center justify-center gap-2 text-xs font-medium text-emerald-600 dark:text-emerald-400 py-1">
              <CheckCircle2 className="size-4" />
              Thank you for your feedback! Your review helps us improve.
            </div>
          )}
        </div>
      )}

      {/* Composer Area */}
      <div className="chat-composer">
        {expert && (
          <div className="mb-3 space-y-2">
            <Segments options={["Reply", "Internal note"]} value={mode} onChange={setMode} />
            {mode === "Internal note" ? (
              <p className="text-warning text-[11px] flex gap-2 items-center">
                <LockKeyhole className="size-3" />
                Only visible to your support team. Not sent to customers.
              </p>
            ) : !isResolved && (
              <div className="flex items-center gap-1.5 flex-wrap pt-1">
                <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Macros:</span>
                {MACROS.map((macro) => (
                  <button
                    key={macro.trigger}
                    type="button"
                    onClick={() => setDraft(macro.text)}
                    className="text-[11px] px-2 py-0.5 rounded-md bg-secondary hover:bg-primary/10 hover:text-primary transition-colors border border-border"
                    title={macro.label}
                  >
                    {macro.trigger}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        {error && (
          <div className="mb-3">
            <InlineAlert
              type="error"
              message={error}
              onDismiss={() => setError("")}
            />
          </div>
        )}
        {/* Visual Live Interim Dictation Feedback */}
        {interimTranscript && dictationState === "listening" && (
          <div
            data-testid="interim-dictation-preview"
            className="px-3 py-1.5 mb-2 rounded-lg bg-amber-500/10 border border-amber-500/25 text-xs text-amber-700 dark:text-amber-300 flex items-center justify-between animate-in fade-in slide-in-from-top-1"
          >
            <div className="flex items-center gap-2 truncate">
              <span className="size-2 rounded-full bg-amber-500 animate-pulse shrink-0" />
              <span className="font-semibold text-[11px] text-amber-800 dark:text-amber-200 shrink-0">
                Live Speech:
              </span>
              <span className="italic truncate font-medium">"{interimTranscript}"</span>
            </div>
            <span className="text-[10px] text-amber-600/80 dark:text-amber-400/80 uppercase font-mono tracking-wider shrink-0 ml-2">
              Provisional
            </span>
          </div>
        )}
        <PromptInput onSubmit={handleSend}>
          <PromptInputTextarea
            aria-label={mode === "Internal note" ? "Write an internal note" : "Your message"}
            placeholder={
              isResolved
                ? "This ticket has been resolved."
                : mode === "Internal note"
                  ? "Write an internal note…"
                  : "Ask anything in any Indian language or English…"
            }
            disabled={isResolved}
            value={draft}
            onChange={handleInputChange}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
          />
          <PromptInputFooter>
            <div className="flex items-center gap-3">
              <span className="text-[10px] text-muted-foreground flex items-center gap-1.5">
                <Globe2 className="size-3" />
                {mode === "Internal note"
                  ? "Private note"
                  : "Multilingual: All 22 Indian Languages & Code-Mixed"}
              </span>

              {/* Voice dictation button and language selector for customer */}
              {user?.role === "customer" && !isResolved && (
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={dictationState === "listening" ? stopDictation : startDictation}
                    disabled={
                      isSending ||
                      dictationState === "requesting_permission" ||
                      dictationState === "finalizing" ||
                      dictationState === "uploading" ||
                      dictationState === "transcribing"
                    }
                    className={`p-1.5 rounded-lg border transition-all flex items-center gap-1.5 text-xs ${
                      dictationState === "listening"
                        ? "bg-destructive/10 text-destructive border-destructive/30 animate-pulse font-medium"
                        : dictationState === "draft_updated"
                          ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30 font-medium"
                          : dictationState === "finalizing" ||
                            dictationState === "uploading" ||
                            dictationState === "transcribing" ||
                            dictationState === "requesting_permission"
                            ? "bg-primary/10 text-primary border-primary/30 font-medium"
                            : "text-muted-foreground hover:text-foreground hover:bg-muted border-border"
                    }`}
                    title={
                      dictationState === "listening"
                        ? "Stop listening and insert transcript into draft"
                        : "Dictate message with voice"
                    }
                    aria-label={dictationState === "listening" ? "Stop dictation" : "Start voice dictation"}
                  >
                    {dictationState === "listening" ? (
                      <>
                        <Square className="size-3 fill-destructive" />
                        <span>Listening ({dictationLang.split("-")[0].toUpperCase()})…</span>
                      </>
                    ) : dictationState === "requesting_permission" ? (
                      <>
                        <Loader2 className="size-3.5 animate-spin" />
                        <span>Connecting mic…</span>
                      </>
                    ) : dictationState === "finalizing" ? (
                      <>
                        <Loader2 className="size-3.5 animate-spin" />
                        <span>Finalizing…</span>
                      </>
                    ) : dictationState === "uploading" ? (
                      <>
                        <Loader2 className="size-3.5 animate-spin" />
                        <span>Uploading…</span>
                      </>
                    ) : dictationState === "transcribing" ? (
                      <>
                        <Loader2 className="size-3.5 animate-spin" />
                        <span>Transcribing…</span>
                      </>
                    ) : dictationState === "draft_updated" ? (
                      <>
                        <Check className="size-3.5 text-emerald-600 dark:text-emerald-400" />
                        <span>Added to draft</span>
                      </>
                    ) : (
                      <>
                        <Mic className="size-3.5" />
                        <span>Voice</span>
                      </>
                    )}
                  </button>

                  <select
                    aria-label="Recognition language"
                    value={dictationLang}
                    onChange={(e) => {
                      const newLang = e.target.value;
                      setDictationLang(newLang);
                      dictationLangRef.current = newLang;
                      if (dictationState === "listening" && recognitionRef.current) {
                        try {
                          recognitionRef.current.onstart = null;
                          recognitionRef.current.onresult = null;
                          recognitionRef.current.onerror = null;
                          recognitionRef.current.onend = null;
                          recognitionRef.current.abort();
                        } catch {}
                        recognitionRef.current = null;
                        setTimeout(() => {
                          if (!userRequestedStopRef.current) {
                            startDictation(newLang);
                          }
                        }, 50);
                      }
                    }}
                    disabled={isSending || isResolved}
                    className="h-7 text-[11px] px-1.5 py-0.5 rounded-md border border-border bg-background text-foreground hover:bg-muted focus:outline-hidden cursor-pointer"
                    title="Dictation language (Select language or Auto-detect)"
                  >
                    {DICTATION_LANGUAGES.map((l) => (
                      <option key={l.code} value={l.code} title={l.title}>
                        {l.label}
                      </option>
                    ))}
                  </select>

                  <select
                    aria-label="Recognition mode"
                    value={dictationMode}
                    onChange={(e) => {
                      const newMode = e.target.value;
                      setDictationMode(newMode);
                      dictationModeRef.current = newMode;
                    }}
                    disabled={isSending || isResolved || dictationState !== "idle"}
                    className="h-7 text-[11px] px-1.5 py-0.5 rounded-md border border-border bg-background text-foreground hover:bg-muted focus:outline-hidden cursor-pointer"
                    title="Output format: Romanized, Code-Mixed, or Native Script"
                  >
                    {DICTATION_MODES.map((m) => (
                      <option key={m.mode} value={m.mode} title={m.title}>
                        {m.label}
                      </option>
                    ))}
                  </select>

                  <button
                    type="button"
                    onClick={() => {
                      const next = dictationEngine === "neural" ? "browser" : "neural";
                      setDictationEngine(next);
                      dictationEngineRef.current = next;
                    }}
                    disabled={isSending || isResolved || dictationState !== "idle"}
                    className={`h-7 px-1.5 py-0.5 text-[11px] rounded-md border transition-colors cursor-pointer ${
                      dictationEngine === "neural"
                        ? "bg-primary/10 text-primary border-primary/30 font-medium"
                        : "bg-background text-muted-foreground border-border hover:bg-muted"
                    }`}
                    title={
                      dictationEngine === "neural"
                        ? "Using Neural STT (Sarvam Saaras v4). Click for browser Web Speech."
                        : "Using Browser Web Speech. Click for Neural STT."
                    }
                    aria-label="Dictation engine"
                  >
                    {dictationEngine === "neural" ? "Neural" : "Browser"}
                  </button>
                </div>
              )}
            </div>
            <PromptInputSubmit
              disabled={!draft.trim() || isSending || isResolved}
              aria-label="Send message"
            >
              {isSending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Send className="size-4" />
              )}
            </PromptInputSubmit>
          </PromptInputFooter>
        </PromptInput>
      </div>

      {/* Tool Confirmation Modal */}
      {pendingConfirmation && (
        <ConfirmationModal
          toolName={pendingConfirmation.toolName}
          isConfirming={isConfirming}
          onAccept={() => handleToolConfirm("accept")}
          onReject={() => handleToolConfirm("reject")}
        />
      )}
    </div>
  );
}

export function CustomerChat({ conversationId }: { conversationId?: string }) {
  return (
    <Workspace title="AI Support Chat" active="AI Support Chat">
      <ChatSurface conversationId={conversationId} />
    </Workspace>
  );
}

export function HelpPage({ initialCategory = "All topics" }: { initialCategory?: string }) {
  const { user } = useAuth();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState(initialCategory);
  const [articles, setArticles] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedArticle, setSelectedArticle] = useState<any | null>(null);

  const isStaff = user?.role === "admin" || user?.role === "expert";

  useEffect(() => {
    let mounted = true;
    async function fetchKnowledge() {
      // Customers do NOT receive or view any knowledge articles
      if (!isStaff) {
        if (mounted) {
          setArticles([]);
          setLoading(false);
        }
        return;
      }

      try {
        const res = await api.get("/knowledge");
        if (mounted) setArticles(res.data || []);
      } catch (err) {
        console.error("Failed to load knowledge articles", err);
      } finally {
        if (mounted) setLoading(false);
      }
    }
    fetchKnowledge();
    return () => {
      mounted = false;
    };
  }, [isStaff]);

  const filteredArticles = articles.filter((a) => {
    const matchesQuery =
      !query.trim() ||
      a.title?.toLowerCase().includes(query.toLowerCase()) ||
      a.content?.toLowerCase().includes(query.toLowerCase());

    const matchesCat =
      category === "All topics" || a.category?.toLowerCase() === category.toLowerCase();

    return matchesQuery && matchesCat;
  });

  // Dedicated Customer Support Hub - Absolutely NO knowledge articles or FAQs shown to customers
  if (!isStaff) {
    return (
      <Workspace title="Help Center" active="Help Center">
        <Heading
          title="How can we help you today?"
          description="ResolveAI is your 24/7 AI-powered support companion. Get instant resolutions via voice or chat, or track your ongoing tickets."
        />

        {/* 3 Interactive Support Action Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
          <div className="p-6 rounded-2xl border border-border bg-card/70 hover:border-emerald-500/50 hover:shadow-md transition-all flex flex-col justify-between shadow-sm">
            <div>
              <div className="w-12 h-12 rounded-xl bg-emerald-500/10 text-emerald-500 flex items-center justify-center mb-4">
                <PhoneCall className="size-6" />
              </div>
              <div className="flex items-center gap-2 mb-2">
                <h3 className="font-semibold text-foreground text-base">Instant Voice Call</h3>
                <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
                  Live 24/7
                </span>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed mb-6">
                Speak directly with ResolveAI without typing. Natural conversational voice in all supported Indian languages and English.
              </p>
            </div>
            <Button asChild className="w-full gap-2 bg-emerald-600 hover:bg-emerald-700 text-white">
              <Link to="/call">
                <PhoneCall className="size-4" />
                Start Voice Call
              </Link>
            </Button>
          </div>

          <div className="p-6 rounded-2xl border border-border bg-card/70 hover:border-primary/50 hover:shadow-md transition-all flex flex-col justify-between shadow-sm">
            <div>
              <div className="w-12 h-12 rounded-xl bg-primary/10 text-primary flex items-center justify-center mb-4">
                <MessageSquare className="size-6" />
              </div>
              <div className="flex items-center gap-2 mb-2">
                <h3 className="font-semibold text-foreground text-base">AI Support Chat</h3>
                <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-primary/15 text-primary">
                  Instant
                </span>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed mb-6">
                Chat 24/7 with our autonomous assistant. Ask questions, resolve billing, track shipments, or request instant refunds.
              </p>
            </div>
            <Button asChild className="w-full gap-2">
              <Link to="/chat/$id" params={{ id: "new" }}>
                <MessageSquare className="size-4" />
                Start AI Chat
              </Link>
            </Button>
          </div>

          <div className="p-6 rounded-2xl border border-border bg-card/70 hover:border-purple-500/50 hover:shadow-md transition-all flex flex-col justify-between shadow-sm">
            <div>
              <div className="w-12 h-12 rounded-xl bg-purple-500/10 text-purple-500 flex items-center justify-center mb-4">
                <Clock3 className="size-6" />
              </div>
              <div className="flex items-center gap-2 mb-2">
                <h3 className="font-semibold text-foreground text-base">My Support Tickets</h3>
                <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-purple-500/15 text-purple-600 dark:text-purple-400">
                  Tracking
                </span>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed mb-6">
                Check status updates for your open inquiries, review past solutions, or continue follow-ups with our team.
              </p>
            </div>
            <Button variant="outline" asChild className="w-full gap-2">
              <Link to="/conversations">
                <Clock3 className="size-4" />
                View My Tickets
              </Link>
            </Button>
          </div>
        </div>

        {/* Feature Highlights */}
        <div className="section-title">
          <h2>How ResolveAI Delivers Instant Support</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          <div className="p-4 rounded-xl border border-border/80 bg-background/50">
            <div className="flex items-center gap-2.5 mb-2">
              <Sparkles className="size-4 text-primary shrink-0" />
              <h4 className="text-sm font-semibold text-foreground">Autonomous Resolutions</h4>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              ResolveAI connects directly to services to track shipments, process eligible refunds, and make account changes instantly.
            </p>
          </div>
          <div className="p-4 rounded-xl border border-border/80 bg-background/50">
            <div className="flex items-center gap-2.5 mb-2">
              <Globe2 className="size-4 text-primary shrink-0" />
              <h4 className="text-sm font-semibold text-foreground">Multilingual Understanding</h4>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Express yourself naturally in all supported Indian languages and English without robotic delays.
            </p>
          </div>
          <div className="p-4 rounded-xl border border-border/80 bg-background/50">
            <div className="flex items-center gap-2.5 mb-2">
              <ShieldCheck className="size-4 text-primary shrink-0" />
              <h4 className="text-sm font-semibold text-foreground">Human Specialist Escalation</h4>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Complex or sensitive issues are seamlessly handed off to human support experts along with complete history.
            </p>
          </div>
        </div>

        {/* Bottom Banner */}
        <div className="rounded-2xl border border-primary/20 bg-gradient-to-r from-primary/10 via-primary/5 to-transparent p-6 flex flex-col md:flex-row items-center justify-between gap-4">
          <div>
            <h3 className="text-base font-semibold text-foreground">Need help right now?</h3>
            <p className="text-xs text-muted-foreground mt-1">
              Our AI is ready 24/7. Connect via voice or text with zero waiting time.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Button variant="outline" asChild className="gap-2">
              <Link to="/call">
                <PhoneCall className="size-4" />
                Voice Call
              </Link>
            </Button>
            <Button asChild className="gap-2">
              <Link to="/chat/$id" params={{ id: "new" }}>
                <MessageSquare className="size-4" />
                Start Chat
              </Link>
            </Button>
          </div>
        </div>
      </Workspace>
    );
  }

  // Staff View (Admin / Expert only)
  return (
    <Workspace title="Help Center" active="Help Center">
      <Heading
        title="Internal Knowledge Base & SOPs"
        description="Staff view: Review internal RAG playbooks, policies, and operating documents. Customers cannot access these documents."
      />
      <div className="filter-bar">
        <SearchField value={query} onChange={setQuery} placeholder="Search internal knowledge base…" />
      </div>
      <div className="topic-grid mb-7">
        {topics.map((t) => (
          <Button
            variant="outline"
            key={t.title}
            onClick={() => setCategory(t.title)}
            className={`topic-card !h-auto !whitespace-normal ${category === t.title ? "border-primary bg-brand-soft" : ""}`}
          >
            <t.icon className="!size-5" />
            <h3>{t.title}</h3>
            <p>{t.description}</p>
          </Button>
        ))}
      </div>
      <div className="section-title">
        <h2>
          {category === "All topics" ? "All Internal Knowledge Articles" : category}
        </h2>
        {category !== "All topics" && (
          <Button variant="link" size="sm" onClick={() => setCategory("All topics")}>
            View all topics
          </Button>
        )}
      </div>
      <div className="panel">
        {loading ? (
          <div className="flex items-center justify-center p-8 text-muted-foreground gap-2">
            <Loader2 className="size-5 animate-spin" />
            Loading answers…
          </div>
        ) : filteredArticles.length > 0 ? (
          <div className="divide-y divide-border">
            {filteredArticles.map((art) => (
              <div
                key={art.id}
                className="p-4 hover:bg-muted/40 transition-colors rounded-lg cursor-pointer"
                onClick={() => setSelectedArticle(selectedArticle?.id === art.id ? null : art)}
              >
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                    <BookOpen className="size-4 text-primary" />
                    {art.title}
                  </h3>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-secondary text-secondary-foreground font-medium">
                    {art.category || "General"}
                  </span>
                </div>
                {selectedArticle?.id === art.id ? (
                  <div className="mt-3 text-xs leading-relaxed text-muted-foreground whitespace-pre-wrap pl-6 border-l-2 border-primary">
                    {art.content}
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground mt-1 line-clamp-2 pl-6">
                    {art.content}
                  </p>
                )}
              </div>
            ))}
          </div>
        ) : (
          <Empty
            title={query ? "No articles found" : "No articles available yet"}
            description={
              query
                ? `No results for “${query}”. Try another keyword.`
                : "Articles will appear here once added to the knowledge base."
            }
            icon={BookOpen}
          />
        )}
      </div>
      <div className="flex items-center justify-between gap-4 py-7">
        <div>
          <h2 className="text-sm font-semibold">Need to test ResolveAI?</h2>
          <p className="text-xs text-muted-foreground mt-2">
            Open a test conversation to verify RAG responses against these articles.
          </p>
        </div>
        <Button asChild>
          <Link to="/chat/$id" params={{ id: "new" }}>
            <MessageSquare className="mr-1.5 size-4" />
            Test AI Chat
          </Link>
        </Button>
      </div>
    </Workspace>
  );
}

export function SettingsPage({ role = "customer" }: { role?: "customer" | "expert" | "admin" }) {
  const { user } = useAuth();
  const [emailUpdates, setEmailUpdates] = useState(true);
  const [ticketUpdates, setTicketUpdates] = useState(true);
  const [tab, setTab] = useState(role === "admin" ? "AI Autonomy" : "Profile");
  const [notice, setNotice] = useState("");

  // AI Autonomy Controls State (Admin only)
  const [autonomyData, setAutonomyData] = useState<any>(null);
  const [selectedMode, setSelectedMode] = useState<string>("balanced");
  const [minConfidence, setMinConfidence] = useState<number>(75);
  const [maxRisk, setMaxRisk] = useState<number>(0.25);
  const [confirmConfidence, setConfirmConfidence] = useState<number>(45);
  const [confirmRisk, setConfirmRisk] = useState<number>(0.55);
  const [frustrationThreshold, setFrustrationThreshold] = useState<number>(0.7);
  const [maxAttempts, setMaxAttempts] = useState<number>(3);
  const [isLoadingAutonomy, setIsLoadingAutonomy] = useState<boolean>(false);
  const [isSavingAutonomy, setIsSavingAutonomy] = useState<boolean>(false);
  const [autonomyError, setAutonomyError] = useState<string | null>(null);
  const [autonomySuccess, setAutonomySuccess] = useState<string | null>(null);
  const [showConfirmModal, setShowConfirmModal] = useState<boolean>(false);

  const initials = (user?.full_name || user?.email || "RA").substring(0, 2).toUpperCase();

  const loadAutonomySettings = async () => {
    if (role !== "admin") return;
    setIsLoadingAutonomy(true);
    setAutonomyError(null);
    try {
      const res = await api.get("/admin/autonomy");
      const d = res.data;
      setAutonomyData(d);
      setSelectedMode(d.mode);
      setMinConfidence(d.auto_resolve_min_confidence);
      setMaxRisk(d.auto_resolve_max_risk);
      setConfirmConfidence(d.confirm_min_confidence);
      setConfirmRisk(d.confirm_max_risk);
      setFrustrationThreshold(d.frustration_escalation_threshold);
      setMaxAttempts(d.max_attempts_before_escalate);
    } catch (err: any) {
      setAutonomyError(err.response?.data?.detail || "Failed to load autonomy configuration.");
    } finally {
      setIsLoadingAutonomy(false);
    }
  };

  useEffect(() => {
    if (role === "admin" && tab === "AI Autonomy") {
      loadAutonomySettings();
    }
  }, [role, tab]);

  const handleSelectMode = (mode: string) => {
    setSelectedMode(mode);
    setAutonomyError(null);
    setAutonomySuccess(null);
    // Apply preset defaults for the mode
    if (mode === "conservative") {
      setMinConfidence(85);
      setMaxRisk(0.15);
      setConfirmConfidence(60);
      setConfirmRisk(0.4);
      setFrustrationThreshold(0.5);
      setMaxAttempts(2);
    } else if (mode === "balanced") {
      setMinConfidence(75);
      setMaxRisk(0.25);
      setConfirmConfidence(45);
      setConfirmRisk(0.55);
      setFrustrationThreshold(0.7);
      setMaxAttempts(3);
    } else if (mode === "high_automation") {
      setMinConfidence(65);
      setMaxRisk(0.35);
      setConfirmConfidence(40);
      setConfirmRisk(0.6);
      setFrustrationThreshold(0.8);
      setMaxAttempts(4);
    }
  };

  const handleSaveAutonomy = async () => {
    setIsSavingAutonomy(true);
    setAutonomyError(null);
    setAutonomySuccess(null);
    setShowConfirmModal(false);

    try {
      const payload = {
        mode: selectedMode,
        auto_resolve_min_confidence: Number(minConfidence),
        auto_resolve_max_risk: Number(maxRisk),
        confirm_min_confidence: Number(confirmConfidence),
        confirm_max_risk: Number(confirmRisk),
        frustration_escalation_threshold: Number(frustrationThreshold),
        max_attempts_before_escalate: Number(maxAttempts),
      };

      const res = await api.put("/admin/autonomy", payload);
      setAutonomyData(res.data);
      setSelectedMode(res.data.mode);
      setAutonomySuccess(`Autonomy policy successfully updated to '${res.data.mode}' and persisted.`);
    } catch (err: any) {
      setAutonomyError(err.response?.data?.detail || "Failed to persist autonomy settings.");
    } finally {
      setIsSavingAutonomy(false);
    }
  };

  const handleResetAutonomy = async () => {
    setIsSavingAutonomy(true);
    setAutonomyError(null);
    setAutonomySuccess(null);
    try {
      const res = await api.post("/admin/autonomy/reset");
      const d = res.data;
      setAutonomyData(d);
      setSelectedMode(d.mode);
      setMinConfidence(d.auto_resolve_min_confidence);
      setMaxRisk(d.auto_resolve_max_risk);
      setConfirmConfidence(d.confirm_min_confidence);
      setConfirmRisk(d.confirm_max_risk);
      setFrustrationThreshold(d.frustration_escalation_threshold);
      setMaxAttempts(d.max_attempts_before_escalate);
      setAutonomySuccess("Autonomy configuration reset to default Balanced policy.");
    } catch (err: any) {
      setAutonomyError(err.response?.data?.detail || "Failed to reset autonomy settings.");
    } finally {
      setIsSavingAutonomy(false);
    }
  };

  const handleCancelAutonomy = () => {
    if (autonomyData) {
      setSelectedMode(autonomyData.mode);
      setMinConfidence(autonomyData.auto_resolve_min_confidence);
      setMaxRisk(autonomyData.auto_resolve_max_risk);
      setConfirmConfidence(autonomyData.confirm_min_confidence);
      setConfirmRisk(autonomyData.confirm_max_risk);
      setFrustrationThreshold(autonomyData.frustration_escalation_threshold);
      setMaxAttempts(autonomyData.max_attempts_before_escalate);
      setAutonomyError(null);
      setAutonomySuccess(null);
    }
  };

  const tabs =
    role === "admin"
      ? ["AI Autonomy", "Profile", "Notifications", "Security"]
      : ["Profile", "Notifications", "Security"];

  return (
    <Workspace role={role} title="Settings" active="Settings">
      <Heading
        title={role === "admin" ? "Workspace settings & Autonomy" : "Your settings"}
        description="A space for your account, preferences, and AI decision policies."
      />
      <div className="settings-layout">
        <div className="nav-list !p-0">
          {tabs.map((t) => (
            <Button
              key={t}
              variant={tab === t ? "secondary" : "ghost"}
              className="justify-start"
              onClick={() => {
                setTab(t);
                setNotice("");
              }}
            >
              {t === "AI Autonomy" ? (
                <Sliders className="mr-2 size-4 text-primary" />
              ) : t === "Profile" ? (
                <UserRound className="mr-2 size-4" />
              ) : t === "Security" ? (
                <ShieldCheck className="mr-2 size-4" />
              ) : (
                <Clock3 className="mr-2 size-4" />
              )}
              {t}
            </Button>
          ))}
        </div>
        <div>
          {tab === "AI Autonomy" && role === "admin" && (
            <section className="settings-section space-y-6">
              <div>
                <h2>AI Decision Autonomy & Safety Policy</h2>
                <p>
                  Configure how much autonomous resolution latitude the AI agent exercises
                  across incoming customer issues before clarifying or escalating to human experts.
                </p>
              </div>

              {isLoadingAutonomy ? (
                <div className="flex items-center justify-center p-12 text-muted-foreground gap-2">
                  <Loader2 className="size-5 animate-spin text-primary" />
                  <span>Loading workspace autonomy configuration...</span>
                </div>
              ) : (
                <>
                  {/* Status Alerts */}
                  {autonomySuccess && (
                    <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-900 dark:text-emerald-200 text-xs flex items-center gap-2">
                      <CheckCircle2 className="size-4 text-emerald-600 shrink-0" />
                      <span>{autonomySuccess}</span>
                    </div>
                  )}

                  {autonomyError && (
                    <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-900 dark:text-rose-200 text-xs flex items-center gap-2">
                      <AlertTriangle className="size-4 text-rose-600 shrink-0" />
                      <span>{autonomyError}</span>
                    </div>
                  )}

                  {/* Mode Selection Cards */}
                  <div className="space-y-3">
                    <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground block">
                      Operational Autonomy Mode
                    </label>
                    <div className="grid md:grid-cols-3 gap-3">
                      {/* Conservative */}
                      <div
                        onClick={() => handleSelectMode("conservative")}
                        className={`p-4 rounded-xl border text-left cursor-pointer transition-all ${
                          selectedMode === "conservative"
                            ? "bg-primary/5 border-primary shadow-sm ring-1 ring-primary/20"
                            : "bg-card hover:border-border/80 border-border"
                        }`}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <span className="font-semibold text-sm">Conservative</span>
                          {selectedMode === "conservative" && (
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-primary text-primary-foreground">
                              Selected
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground leading-relaxed">
                          Requires 85%+ confidence. Prefers clarification questions or early human
                          review whenever uncertainty or failure risk is elevated.
                        </p>
                        <div className="mt-3 pt-2 border-t border-border/50 text-[11px] text-muted-foreground font-mono">
                          Auto-resolve: ≥85% conf · Max 2 attempts
                        </div>
                      </div>

                      {/* Balanced (Default) */}
                      <div
                        onClick={() => handleSelectMode("balanced")}
                        className={`p-4 rounded-xl border text-left cursor-pointer transition-all ${
                          selectedMode === "balanced"
                            ? "bg-primary/5 border-primary shadow-sm ring-1 ring-primary/20"
                            : "bg-card hover:border-border/80 border-border"
                        }`}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <span className="font-semibold text-sm">Balanced (Default)</span>
                          {selectedMode === "balanced" && (
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-primary text-primary-foreground">
                              Selected
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground leading-relaxed">
                          Standard production baseline (75% confidence). Proven balance between autonomous
                          resolution of routine cases and timely human handoff.
                        </p>
                        <div className="mt-3 pt-2 border-t border-border/50 text-[11px] text-muted-foreground font-mono">
                          Auto-resolve: ≥75% conf · Max 3 attempts
                        </div>
                      </div>

                      {/* High Automation */}
                      <div
                        onClick={() => handleSelectMode("high_automation")}
                        className={`p-4 rounded-xl border text-left cursor-pointer transition-all ${
                          selectedMode === "high_automation"
                            ? "bg-primary/5 border-primary shadow-sm ring-1 ring-primary/20"
                            : "bg-card hover:border-border/80 border-border"
                        }`}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <span className="font-semibold text-sm">High Automation</span>
                          {selectedMode === "high_automation" && (
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-primary text-primary-foreground">
                              Selected
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground leading-relaxed">
                          Allows verified low-risk, routine requests to resolve autonomously with relaxed
                          confidence (65%+). All security and tool safeguards remain intact.
                        </p>
                        <div className="mt-3 pt-2 border-t border-border/50 text-[11px] text-muted-foreground font-mono">
                          Auto-resolve: ≥65% conf · Max 4 attempts
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Non-Negotiable Safety Invariants */}
                  <div className="p-4 rounded-xl bg-muted/40 border border-border/60 space-y-2">
                    <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
                      <ShieldCheck className="size-4 text-emerald-600" />
                      Platform Safety Boundaries (Non-Negotiable)
                    </div>
                    <ul className="text-xs text-muted-foreground space-y-1 list-disc list-inside">
                      <li>
                        Security-sensitive issues (<code>SECURITY_ISSUE</code>) and <code>CRITICAL</code> priority requests unconditionally escalate.
                      </li>
                      <li>
                        Restricted tool actions (refund processing, account alterations) strictly require explicit customer confirmation.
                      </li>
                      <li>
                        Observed tool failures and customer-reported failed solutions force expert handoff regardless of mode.
                      </li>
                      <li>
                        Tenant isolation and role authorization barriers cannot be bypassed by autonomy settings.
                      </li>
                    </ul>
                  </div>

                  {/* Threshold Parameters (Bounded Overrides) */}
                  <div className="p-4 rounded-xl bg-card border space-y-4">
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-semibold text-foreground">
                        Calibrated Thresholds for &apos;{selectedMode}&apos; Policy
                      </h3>
                      <span className="text-[11px] text-muted-foreground">
                        Adjust within safety bounds
                      </span>
                    </div>

                    <div className="grid md:grid-cols-2 gap-4">
                      <label className="field text-xs">
                        Auto-Resolve Minimum Confidence (%) [60 – 95]
                        <Input
                          type="number"
                          step="1"
                          min="60"
                          max="95"
                          value={minConfidence}
                          onChange={(e) => setMinConfidence(Number(e.target.value))}
                        />
                      </label>

                      <label className="field text-xs">
                        Auto-Resolve Max Risk (0.05 – 0.40)
                        <Input
                          type="number"
                          step="0.05"
                          min="0.05"
                          max="0.40"
                          value={maxRisk}
                          onChange={(e) => setMaxRisk(Number(e.target.value))}
                        />
                      </label>

                      <label className="field text-xs">
                        Confirmation Minimum Confidence (%) [35 – 80]
                        <Input
                          type="number"
                          step="1"
                          min="35"
                          max="80"
                          value={confirmConfidence}
                          onChange={(e) => setConfirmConfidence(Number(e.target.value))}
                        />
                      </label>

                      <label className="field text-xs">
                        Confirmation Max Risk (0.20 – 0.70)
                        <Input
                          type="number"
                          step="0.05"
                          min="0.20"
                          max="0.70"
                          value={confirmRisk}
                          onChange={(e) => setConfirmRisk(Number(e.target.value))}
                        />
                      </label>

                      <label className="field text-xs">
                        Customer Frustration Escalation Trigger (0.30 – 0.90)
                        <Input
                          type="number"
                          step="0.05"
                          min="0.30"
                          max="0.90"
                          value={frustrationThreshold}
                          onChange={(e) => setFrustrationThreshold(Number(e.target.value))}
                        />
                      </label>

                      <label className="field text-xs">
                        Max Unsuccessful Turns Before Escalation (1 – 5)
                        <Input
                          type="number"
                          step="1"
                          min="1"
                          max="5"
                          value={maxAttempts}
                          onChange={(e) => setMaxAttempts(Number(e.target.value))}
                        />
                      </label>
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div className="flex items-center justify-between pt-2">
                    <div className="flex items-center gap-2">
                      <Button
                        onClick={() => {
                          if (autonomyData && selectedMode !== autonomyData.mode) {
                            setShowConfirmModal(true);
                          } else {
                            handleSaveAutonomy();
                          }
                        }}
                        disabled={isSavingAutonomy}
                      >
                        {isSavingAutonomy ? (
                          <>
                            <Loader2 className="mr-2 size-4 animate-spin" />
                            Persisting...
                          </>
                        ) : (
                          "Save Autonomy Policy"
                        )}
                      </Button>

                      <Button
                        variant="ghost"
                        onClick={handleCancelAutonomy}
                        disabled={isSavingAutonomy}
                      >
                        Cancel Changes
                      </Button>
                    </div>

                    <Button
                      variant="outline"
                      onClick={handleResetAutonomy}
                      disabled={isSavingAutonomy}
                      className="text-xs"
                    >
                      <RotateCcw className="mr-1.5 size-3.5" />
                      Reset to Default Policy
                    </Button>
                  </div>

                  {/* Confirmation Modal */}
                  {showConfirmModal && (
                    <div className="fixed inset-0 bg-background/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
                      <div className="bg-card text-card-foreground rounded-2xl shadow-2xl border border-border w-full max-w-md overflow-hidden animate-in fade-in zoom-in-95 duration-200">
                        <div className="p-6 space-y-4">
                          <div className="flex items-center gap-3">
                            <div className="size-10 rounded-full bg-amber-500/15 text-amber-600 flex items-center justify-center shrink-0">
                              <AlertTriangle className="size-5" />
                            </div>
                            <div>
                              <h3 className="font-semibold text-sm">
                                Confirm Autonomy Policy Change
                              </h3>
                              <p className="text-xs text-muted-foreground mt-0.5">
                                Switch workspace mode to &apos;{selectedMode}&apos;?
                              </p>
                            </div>
                          </div>

                          <p className="text-xs text-muted-foreground leading-relaxed">
                            You are changing the active autonomy policy from{" "}
                            <span className="font-semibold text-foreground">
                              {autonomyData?.mode}
                            </span>{" "}
                            to{" "}
                            <span className="font-semibold text-foreground">
                              {selectedMode}
                            </span>
                            . This directly modifies confidence and escalation thresholds for all
                            incoming customer conversations.
                          </p>

                          <div className="flex justify-end gap-2 pt-2">
                            <Button
                              variant="ghost"
                              onClick={() => setShowConfirmModal(false)}
                            >
                              Cancel
                            </Button>
                            <Button onClick={handleSaveAutonomy}>
                              Confirm & Apply
                            </Button>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Audit Trail Section */}
                  {autonomyData?.recent_audit_trail && autonomyData.recent_audit_trail.length > 0 && (
                    <div className="p-4 rounded-xl bg-card border space-y-3">
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                        Recent Policy Changes (Audit Trail)
                      </h3>
                      <div className="divide-y divide-border/40 text-xs">
                        {autonomyData.recent_audit_trail.slice(-5).reverse().map((entry: any, i: number) => (
                          <div key={i} className="py-2.5 flex items-center justify-between text-muted-foreground">
                            <div>
                              <span className="font-medium text-foreground">
                                {entry.previous_mode} → {entry.new_mode}
                              </span>
                              <span className="text-[11px] block text-muted-foreground">
                                Updated by {entry.user_email || `User #${entry.user_id}`}
                              </span>
                            </div>
                            <span className="text-[11px] font-mono">
                              {new Date(entry.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </section>
          )}

          {tab === "Profile" && (
            <section className="settings-section">
              <h2>Profile information</h2>
              <p>Your account profile authenticated with ResolveAI.</p>
              <div className="flex items-center gap-4 mb-6">
                <div className="avatar !size-16 !text-base bg-primary text-primary-foreground font-semibold flex items-center justify-center rounded-full">
                  {initials}
                </div>
                <div>
                  <h3 className="text-sm font-semibold">{user?.full_name || user?.email || "Active User"}</h3>
                  <p className="!mb-0 !mt-1 text-xs text-muted-foreground">{user?.email}</p>
                </div>
              </div>
              <div className="form-grid">
                <label className="field">
                  Full name
                  <Input readOnly value={user?.full_name || ""} placeholder="Your full name" />
                </label>
                <label className="field">
                  Email address
                  <Input
                    readOnly
                    value={user?.email || ""}
                    type="email"
                    placeholder="you@example.com"
                  />
                </label>
                <label className="field">
                  Account role
                  <Input readOnly value={user?.role?.toUpperCase() || "CUSTOMER"} />
                </label>
              </div>
            </section>
          )}

          {tab === "Notifications" && (
            <section className="settings-section">
              <h2>Notification preferences</h2>
              <p>Choose the updates that matter to you.</p>
              <div className="preference">
                <div>
                  <h3>Conversation updates</h3>
                  <p>Replies and changes to your ticket status</p>
                </div>
                <Switch
                  aria-label="Conversation updates"
                  checked={ticketUpdates}
                  onCheckedChange={setTicketUpdates}
                />
              </div>
              <div className="preference">
                <div>
                  <h3>Email notifications</h3>
                  <p>Important updates sent to your inbox</p>
                </div>
                <Switch
                  aria-label="Email notifications"
                  checked={emailUpdates}
                  onCheckedChange={setEmailUpdates}
                />
              </div>
              <Button
                className="mt-5"
                onClick={() => setNotice("Preferences updated successfully.")}
              >
                Save preferences
              </Button>
            </section>
          )}

          {tab === "Security" && (
            <section className="settings-section">
              <h2>Account security</h2>
              <p>Session and security managed via ResolveAI Authentication.</p>
              <div className="p-4 rounded-lg bg-card border space-y-2">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <ShieldCheck className="size-4 text-emerald-600" />
                  Authenticated Session Active
                </div>
                <p className="text-xs text-muted-foreground">
                  Your session is protected with JWT token refresh and secure HTTP headers.
                </p>
              </div>
            </section>
          )}

          {notice && (
            <p role="status" className="text-emerald-600 text-xs mt-5">
              {notice}
            </p>
          )}
        </div>
      </div>
    </Workspace>
  );
}
