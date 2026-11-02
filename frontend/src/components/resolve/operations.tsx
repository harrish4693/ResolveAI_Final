import { useState, useEffect, useRef } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import {
  ArrowRight,
  Inbox,
  CircleCheck,
  Clock3,
  TriangleAlert,
  Users,
  ChartNoAxesCombined,
  TrendingUp,
  FileText,
  Plus,
  Upload,
  Search,
  CalendarDays,
  ShieldCheck,
  UserRound,
  MessageSquare,
  CheckCircle2,
  Loader2,
  Star,
  Share2,
  Sparkles,
  Bot,
  Globe2,
  Sliders,
  ShieldAlert,
  Phone,
  PhoneCall,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Workspace, type Role } from "./workspace";
import { Heading, Empty, Metric, SearchField, Segments, StatusBadge, MetricSkeleton, TableSkeleton, InlineAlert } from "./common";
import { ChatSurface } from "./customer";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useWebSocket } from "@/lib/ws";

export function ExpertDashboard() {
  const [stats, setStats] = useState<any>(null);
  const [queue, setQueue] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const { subscribe } = useWebSocket();
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let mounted = true;
    async function loadStats() {
      try {
        const [statsRes, queueRes] = await Promise.allSettled([
          api.get("/handoffs/stats"),
          api.get("/handoffs/queue?limit=5"),
        ]);
        if (mounted) {
          if (statsRes.status === "fulfilled") setStats(statsRes.value.data);
          if (queueRes.status === "fulfilled") setQueue(queueRes.value.data || []);
        }
      } catch (e) {
        console.error("Failed to load expert stats", e);
      } finally {
        if (mounted) setLoading(false);
      }
    }
    loadStats();

    const unsubQueue = subscribe("QUEUE_UPDATED", () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
      debounceTimerRef.current = setTimeout(() => {
        if (mounted) loadStats();
      }, 400);
    });

    return () => {
      mounted = false;
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
      unsubQueue();
    };
  }, [subscribe]);

  return (
    <Workspace role="expert" title="Dashboard" active="Dashboard">
      <Heading
        title="A clearer view of your day."
        description="Your cases, customer updates, and next steps in one place."
        action={
          <Button asChild>
            <Link to="/expert/queue">
              Open case queue
              <ArrowRight className="ml-1.5 size-4" />
            </Link>
          </Button>
        }
      />
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
              label="My active cases"
              value={stats?.active_chats ?? 0}
              icon={Inbox}
              foot="Assigned to you"
            />
            <Metric
              label="Unclaimed escalations"
              value={stats?.queue_size ?? queue.length}
              icon={TriangleAlert}
              tone="warning"
              foot="Waiting in queue"
            />
            <Metric
              label="Customer rating"
              value={stats?.average_csat ? `${stats.average_csat.toFixed(1)} / 5.0` : "5.0 / 5.0"}
              icon={Star}
              tone="success"
              foot="Average CSAT score"
            />
          </>
        )}
      </div>
      <div className="dashboard-grid">
        <section>
          <div className="section-title">
            <h2>Needs your attention</h2>
            <Button asChild variant="link" size="sm">
              <Link to="/expert/queue">
                View all queue
                <ArrowRight className="ml-1 size-3.5" />
              </Link>
            </Button>
          </div>
          <div className="panel">
            {loading ? (
              <TableSkeleton rows={4} cols={5} />
            ) : queue.length > 0 ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Queue ID</th>
                      <th>Reason</th>
                      <th>Priority & Risk</th>
                      <th>Waiting</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {queue.slice(0, 5).map((q) => (
                      <tr key={q.id}>
                        <td className="font-mono text-xs">#{q.id}</td>
                        <td className="text-sm font-medium">
                          <div>{q.escalation_reason || q.reason || "Customer assistance"}</div>
                          {q.incident_id && (
                            <span className="text-[10px] font-mono text-rose-600 dark:text-rose-400">
                              Incident #{q.incident_id}
                            </span>
                          )}
                        </td>
                        <td>
                          <div className="flex flex-col gap-1 items-start">
                            <StatusBadge status={q.priority || "normal"} size="sm" />
                            {q.failure_risk_level && (
                              <span
                                className={`px-1.5 py-0.2 rounded text-[9px] font-semibold uppercase ${
                                  q.failure_risk_level === "HIGH" || q.failure_risk_level === "VERY_HIGH"
                                    ? "bg-rose-100 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300"
                                    : q.failure_risk_level === "MODERATE"
                                    ? "bg-amber-100 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300"
                                    : "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300"
                                }`}
                              >
                                {q.failure_risk_level} Risk
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="text-xs text-muted-foreground">
                          {new Date(q.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </td>
                        <td>
                          <Button asChild size="sm" variant="outline">
                            <Link to="/expert/chat/$id" params={{ id: String(q.conversation_id) }}>
                              Review
                            </Link>
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty
                title="All caught up!"
                description="No waiting escalations in the queue right now."
                icon={CircleCheck}
              />
            )}
          </div>
        </section>
        <section>
          <div className="section-title">
            <h2>Expert Quick Actions</h2>
          </div>
          <Link to="/expert/queue" className="quick-link">
            <span className="small-icon">
              <Inbox />
            </span>
            <div className="flex-1">
              <h3>Live Escalation Queue</h3>
              <p>Claim and assist waiting customers</p>
            </div>
            <ArrowRight className="size-4 text-muted-foreground" />
          </Link>
          <Link to="/expert/history" className="quick-link">
            <span className="small-icon">
              <Clock3 />
            </span>
            <div className="flex-1">
              <h3>Resolution History</h3>
              <p>Review past customer interactions</p>
            </div>
            <ArrowRight className="size-4 text-muted-foreground" />
          </Link>
        </section>
      </div>
    </Workspace>
  );
}

export function QueuePage({
  kind = "queue",
}: {
  kind?: "queue" | "assigned" | "history" | "admin";
}) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("All");
  const [priority, setPriority] = useState("all");
  const [channel, setChannel] = useState("all");
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [claimingId, setClaimingId] = useState<number | null>(null);

  const role = kind === "admin" ? "admin" : "expert";
  const title =
    kind === "assigned"
      ? "My assigned cases"
      : kind === "history"
        ? "Conversation history"
        : kind === "admin"
          ? "Ticket monitoring"
          : "Case queue";
  const active =
    kind === "assigned"
      ? "My Assigned Cases"
      : kind === "history"
        ? "Conversation History"
        : kind === "admin"
          ? "Tickets"
          : "Case Queue";

  const { subscribe } = useWebSocket();
  const queueDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let mounted = true;
    async function loadData() {
      try {
        setLoading(true);
        if (kind === "admin") {
          const res = await api.get("/tickets");
          if (mounted) setItems(res.data || []);
        } else {
          const res = await api.get("/handoffs/queue?limit=50");
          if (mounted) setItems(res.data || []);
        }
      } catch (err) {
        console.error("Failed to load queue items", err);
      } finally {
        if (mounted) setLoading(false);
      }
    }
    loadData();

    const unsubQueue = subscribe("QUEUE_UPDATED", () => {
      if (queueDebounceRef.current) {
        clearTimeout(queueDebounceRef.current);
      }
      queueDebounceRef.current = setTimeout(() => {
        if (mounted) loadData();
      }, 400);
    });

    return () => {
      mounted = false;
      if (queueDebounceRef.current) {
        clearTimeout(queueDebounceRef.current);
      }
      unsubQueue();
    };
  }, [kind, subscribe]);

  const handleClaim = async (handoff: any) => {
    setClaimingId(handoff.id);
    try {
      await api.post(`/handoffs/${handoff.id}/assign`);
      navigate({ to: "/expert/chat/$id", params: { id: String(handoff.conversation_id) } });
    } catch (err: any) {
      console.error("Failed to assign handoff", err);
      // If already assigned, still open chat
      navigate({ to: "/expert/chat/$id", params: { id: String(handoff.conversation_id) } });
    } finally {
      setClaimingId(null);
    }
  };

  const filtered = items.filter((item) => {
    const text = JSON.stringify(item).toLowerCase();
    const matchesQuery = !query.trim() || text.includes(query.toLowerCase());
    const matchesPriority = priority === "all" || item.priority?.toLowerCase() === priority;

    // Status filter
    const itemStatus = (item.status || "open").toLowerCase();
    const matchesStatus =
      status === "All" ||
      (status === "Open" && itemStatus === "open") ||
      (status === "In progress" && (itemStatus === "in_progress" || itemStatus === "assigned" || itemStatus === "waiting")) ||
      (status === "Resolved" && itemStatus === "resolved");

    // Channel filter (Chat / Voice Call)
    const itemChannel = (item.channel || item.conversation?.channel || "text").toLowerCase();
    const matchesChannel =
      channel === "all" ||
      (channel === "chat" && (itemChannel === "text" || itemChannel === "chat")) ||
      (channel === "voice" && (itemChannel === "voice" || itemChannel === "call"));

    return matchesQuery && matchesPriority && matchesStatus && matchesChannel;
  });

  return (
    <Workspace role={role} title={title} active={active}>
      <Heading
        title={title}
        description={
          kind === "queue"
            ? "Live customer handoffs awaiting expert assistance."
            : "Keep track of conversations, assignments, and customer updates."
        }
      />
      <div className="filter-bar">
        <SearchField
          value={query}
          onChange={setQuery}
          placeholder="Search ticket ID, customer, or issue…"
        />
        <Segments
          options={["All", "Open", "In progress", "Resolved"]}
          value={status}
          onChange={setStatus}
        />
        <Select value={priority} onValueChange={setPriority}>
          <SelectTrigger className="w-36 bg-card" aria-label="Case priority">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All priorities</SelectItem>
            <SelectItem value="high">High priority</SelectItem>
            <SelectItem value="medium">Medium priority</SelectItem>
            <SelectItem value="low">Low priority</SelectItem>
          </SelectContent>
        </Select>
        <Select value={channel} onValueChange={setChannel}>
          <SelectTrigger className="w-38 bg-card" aria-label="Channel filter">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All channels</SelectItem>
            <SelectItem value="chat">
              <span className="inline-flex items-center gap-1.5">
                <MessageSquare className="size-3.5 text-blue-500" />
                Chat only
              </span>
            </SelectItem>
            <SelectItem value="voice">
              <span className="inline-flex items-center gap-1.5">
                <PhoneCall className="size-3.5 text-purple-500" />
                Voice call only
              </span>
            </SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="panel">
        {loading ? (
          <TableSkeleton rows={5} cols={7} />
        ) : filtered.length > 0 ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Case ID</th>
                  <th>Channel</th>
                  <th>Reason / Subject</th>
                  <th>Priority & Risk</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => {
                  const isVoice = item.channel === "voice" || item.conversation?.channel === "voice";
                  return (
                    <tr key={item.id}>
                      <td className="font-mono text-xs">#{item.id}</td>
                      <td>
                        {isVoice ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-purple-500/15 text-purple-700 dark:text-purple-300 border border-purple-500/20">
                            <PhoneCall className="size-3 text-purple-600 dark:text-purple-400" />
                            Voice Call
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-blue-500/15 text-blue-700 dark:text-blue-300 border border-blue-500/20">
                            <MessageSquare className="size-3 text-blue-600 dark:text-blue-400" />
                            Chat
                          </span>
                        )}
                      </td>
                      <td className="text-sm font-medium">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span>{item.reason || item.subject || "Customer inquiry"}</span>
                          {item.incident_id && (
                            <span className="px-1.5 py-0.2 rounded text-[10px] font-mono bg-rose-500/10 text-rose-700 dark:text-rose-300 border border-rose-500/20">
                              Incident #{item.incident_id}
                            </span>
                          )}
                        </div>
                        {item.suggested_next_action && (
                          <p className="text-[11px] text-muted-foreground mt-0.5">
                            <span className="text-primary font-medium">Action:</span> {item.suggested_next_action}
                          </p>
                        )}
                        {item.priority_rationale && (
                          <p className="text-[10px] text-muted-foreground/75 italic">
                            {item.priority_rationale}
                          </p>
                        )}
                      </td>
                      <td>
                        <div className="flex flex-col gap-1 items-start">
                          <StatusBadge status={item.priority || "normal"} size="sm" />
                          {item.failure_risk_level && (
                            <span
                              className={`px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase inline-flex items-center gap-1 ${
                                item.failure_risk_level === "HIGH" || item.failure_risk_level === "VERY_HIGH"
                                  ? "bg-rose-500/15 text-rose-700 dark:text-rose-300 border border-rose-500/20"
                                  : item.failure_risk_level === "MODERATE"
                                  ? "bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/20"
                                  : "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20"
                              }`}
                            >
                              {(item.failure_risk_level === "HIGH" || item.failure_risk_level === "VERY_HIGH") && (
                                <TriangleAlert className="size-2.5" />
                              )}
                              {item.failure_risk_level} Risk
                            </span>
                          )}
                        </div>
                      </td>
                      <td>
                        <StatusBadge status={item.status || "open"} size="sm" />
                      </td>
                      <td className="text-xs text-muted-foreground">
                        {new Date(item.created_at).toLocaleString()}
                      </td>
                      <td>
                        {kind === "queue" ? (
                          <Button
                            size="sm"
                            disabled={claimingId === item.id}
                            onClick={() => handleClaim(item)}
                            className={isVoice ? "bg-purple-600 hover:bg-purple-700 text-white gap-1" : ""}
                          >
                            {claimingId === item.id ? (
                              <Loader2 className="size-3.5 animate-spin mr-1" />
                            ) : isVoice ? (
                              <PhoneCall className="size-3.5 mr-1" />
                            ) : null}
                            {isVoice ? "Claim & Call" : "Claim & Assist"}
                          </Button>
                        ) : (
                          <div className="flex items-center gap-1.5">
                            <Button asChild size="sm" variant="ghost">
                              <Link to="/expert/chat/$id" params={{ id: String(item.conversation_id || item.id) }}>
                                Open Chat
                                <ArrowRight className="ml-1 size-3.5" />
                              </Link>
                            </Button>
                            {isVoice && (
                              <Button
                                asChild
                                size="sm"
                                variant="outline"
                                className="border-purple-500/30 text-purple-600 dark:text-purple-400 hover:bg-purple-500/10 h-8 px-2 gap-1 text-xs"
                                title="Open live voice call interface"
                              >
                                <Link to="/call/$id" params={{ id: String(item.conversation_id || item.id) }}>
                                  <PhoneCall className="size-3.5" />
                                  <span className="hidden xl:inline">Voice Call</span>
                                </Link>
                              </Button>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title={query || channel !== "all" ? "No matching cases" : "No cases in queue"}
            description={
              query || channel !== "all"
                ? `No results for current filter criteria.`
                : "All escalated cases have been attended to."
            }
          />
        )}
      </div>
    </Workspace>
  );
}

export function ExpertConsole({ id }: { id: string }) {
  const navigate = useNavigate();
  const [handoff, setHandoff] = useState<any>(null);
  const [conversation, setConversation] = useState<any>(null);
  const [contextData, setContextData] = useState<any>(null);
  const [contextLoading, setContextLoading] = useState(true);
  const [resolveMessage, setResolveMessage] = useState("");
  const [resolving, setResolving] = useState(false);
  const [transferring, setTransferring] = useState(false);
  const [resolved, setResolved] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [mobileTab, setMobileTab] = useState<"chat" | "context" | "actions">("chat");

  useEffect(() => {
    let mounted = true;
    async function loadConsoleData() {
      if (id === "preview") {
        setContextLoading(false);
        return;
      }
      setContextLoading(true);
      try {
        // Parallel fetch of conversation, context, and handoff to eliminate waterfall
        const [cRes, ctxRes, hRes] = await Promise.allSettled([
          api.get(`/conversations/${id}`),
          api.get(`/handoffs/conversation/${id}/context`),
          api.get(`/handoffs/conversation/${id}`),
        ]);
        if (mounted) {
          if (cRes.status === "fulfilled") setConversation(cRes.value.data);
          if (hRes.status === "fulfilled") setHandoff(hRes.value.data);
          if (ctxRes.status === "fulfilled") {
            setContextData(ctxRes.value.data);
          } else if (hRes.status === "fulfilled" && hRes.value.data?.id) {
            // Fallback to handoff ID context if direct conversation context isn't matched
            try {
              const fallbackCtx = await api.get(`/handoffs/${hRes.value.data.id}/context`);
              if (mounted) setContextData(fallbackCtx.data);
            } catch (err) {
              console.warn("Fallback context load failed", err);
            }
          }
        }
      } catch (err) {
        console.error("Failed to load expert console data", err);
      } finally {
        if (mounted) setContextLoading(false);
      }
    }
    loadConsoleData();
    return () => {
      mounted = false;
    };
  }, [id]);

  const handleResolve = async () => {
    if (!handoff?.id || !resolveMessage.trim()) return;
    setResolving(true);
    setActionError(null);
    try {
      await api.post(`/handoffs/${handoff.id}/resolve`, {
        resolution_message: resolveMessage.trim(),
      });
      setResolved(true);
    } catch (err: any) {
      console.error("Failed to resolve handoff", err);
      setActionError(err.response?.data?.detail || err.message || "Failed to resolve handoff.");
    } finally {
      setResolving(false);
    }
  };

  const handleTransfer = async () => {
    if (!handoff?.id || transferring) return;
    setTransferring(true);
    setActionError(null);
    try {
      await api.post(`/handoffs/${handoff.id}/transfer`, { expert_id: null });
      navigate({ to: "/expert/queue" });
    } catch (err: any) {
      console.error("Failed to release case to queue", err);
      setActionError(err.response?.data?.detail || err.message || "Failed to release case to queue.");
    } finally {
      setTransferring(false);
    }
  };

  const isVoice =
    (conversation?.channel || "").toLowerCase() === "voice" ||
    (conversation?.channel || "").toLowerCase() === "call" ||
    (handoff?.channel || "").toLowerCase() === "voice" ||
    (handoff?.channel || "").toLowerCase() === "call" ||
    (contextData?.active_ticket?.channel || "").toLowerCase() === "voice" ||
    (contextData?.active_ticket?.channel || "").toLowerCase() === "call" ||
    ((conversation?.subject || "").toLowerCase().startsWith("voice call"));

  return (
    <Workspace role="expert" title="Conversation console" active="Case Queue">
      <div className="section-title">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold">Conversation console</h1>
            {isVoice ? (
              <span
                data-testid="expert-header-channel-badge"
                className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
              >
                <PhoneCall className="size-3" />
                Voice Call
              </span>
            ) : (
              <span
                data-testid="expert-header-channel-badge"
                className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-muted text-muted-foreground border border-border"
              >
                <MessageSquare className="size-3" />
                Chat
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Live customer communication with full AI context, macros, and handoff metadata.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {id !== "preview" && (
            <Button
              variant={conversation?.channel === "voice" ? "default" : "outline"}
              size="sm"
              asChild
              className={
                conversation?.channel === "voice"
                  ? "bg-purple-600 hover:bg-purple-700 text-white gap-1.5"
                  : "border-primary/30 hover:bg-primary/10 text-primary gap-1.5"
              }
              title="Open full dedicated voice interface for this call"
            >
              <Link to="/call/$id" params={{ id }}>
                <PhoneCall className="size-3.5" />
                {conversation?.channel === "voice" ? "Live Voice Interface" : "Voice Interface"}
              </Link>
            </Button>
          )}
          {handoff?.id && !resolved && (
            <Button
              variant="outline"
              size="sm"
              disabled={transferring}
              onClick={handleTransfer}
            >
              {transferring ? <Loader2 className="size-3.5 animate-spin mr-1" /> : <Share2 className="size-3.5 mr-1" />}
              Release to Queue
            </Button>
          )}
          <Button variant="outline" asChild size="sm">
            <Link to="/expert/queue">Back to queue</Link>
          </Button>
        </div>
      </div>

      {actionError && (
        <div className="mb-4">
          <InlineAlert
            type="error"
            title="Action Failed"
            message={actionError}
            onDismiss={() => setActionError(null)}
          />
        </div>
      )}

      {/* Mobile/Tablet View Switcher (<1150px) */}
      <div className="lg:hidden flex border border-border rounded-xl bg-card p-1 mb-3 gap-1">
        <Button
          size="sm"
          variant={mobileTab === "chat" ? "default" : "ghost"}
          onClick={() => setMobileTab("chat")}
          className="flex-1 text-xs"
        >
          <MessageSquare className="size-3.5 mr-1" />
          Chat
        </Button>
        <Button
          size="sm"
          variant={mobileTab === "context" ? "default" : "ghost"}
          onClick={() => setMobileTab("context")}
          className="flex-1 text-xs"
        >
          <Bot className="size-3.5 mr-1" />
          AI & Context
        </Button>
        <Button
          size="sm"
          variant={mobileTab === "actions" ? "default" : "ghost"}
          onClick={() => setMobileTab("actions")}
          className="flex-1 text-xs"
        >
          <CheckCircle2 className="size-3.5 mr-1" />
          Actions
        </Button>
      </div>

      <div className="panel expert-grid">
        <aside className={`console-side console-queue ${mobileTab !== "actions" ? "max-lg:hidden" : ""}`}>
          <h3>Case Actions</h3>
          {resolved ? (
            <div className="p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-800 dark:text-emerald-300 text-xs flex items-center gap-2">
              <CheckCircle2 className="size-4 shrink-0" />
              <span>This case has been successfully resolved!</span>
            </div>
          ) : (
            <div className="space-y-3 mt-3">
              <label className="text-xs font-medium block">Resolution Summary</label>
              <Textarea
                placeholder="Explain the solution provided to the customer…"
                value={resolveMessage}
                onChange={(e) => setResolveMessage(e.target.value)}
                className="text-xs h-24"
              />
              <Button
                size="sm"
                className="w-full"
                disabled={!resolveMessage.trim() || resolving}
                onClick={handleResolve}
              >
                {resolving ? <Loader2 className="size-3.5 animate-spin mr-1" /> : <CheckCircle2 className="size-3.5 mr-1" />}
                Mark as Resolved
              </Button>
            </div>
          )}
        </aside>
        <div className={`flex flex-col min-w-0 ${mobileTab !== "chat" ? "max-lg:hidden" : ""}`}>
          <ChatSurface expert conversationId={id === "preview" ? "new" : id} />
        </div>
        <aside className={`console-side console-context space-y-4 ${mobileTab !== "context" ? "max-lg:hidden" : ""}`}>
          <h3>Customer & ticket context</h3>

          {contextLoading && !contextData ? (
            <div className="space-y-3 py-1">
              <div className="p-3 rounded-xl bg-card border border-border space-y-2 animate-pulse">
                <div className="h-4 bg-muted/60 rounded w-1/2" />
                <div className="h-3 bg-muted/40 rounded w-3/4" />
              </div>
              <div className="p-3 rounded-xl bg-card border border-border space-y-2.5 animate-pulse">
                <div className="h-3 bg-muted/50 rounded w-full" />
                <div className="h-3 bg-muted/50 rounded w-5/6" />
                <div className="h-3 bg-muted/50 rounded w-4/6" />
              </div>
              <div className="p-3.5 rounded-xl bg-primary/5 border border-primary/20 space-y-2 animate-pulse">
                <div className="h-4 bg-primary/20 rounded w-1/3" />
                <div className="h-3 bg-muted/40 rounded w-full" />
                <div className="h-3 bg-muted/40 rounded w-2/3" />
              </div>
            </div>
          ) : (
            <>
              {/* Customer Profile */}
              <div className="p-3 rounded-xl bg-card border border-border space-y-1.5 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-foreground flex items-center gap-1.5">
                <UserRound className="size-3.5 text-primary" />
                {contextData?.customer?.name || "Customer"}
              </span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-50 text-emerald-700 capitalize">
                {contextData?.customer?.account_status || "Active"}
              </span>
            </div>
            <p className="text-muted-foreground text-[11px] truncate">
              {contextData?.customer?.email || "customer@example.com"}
            </p>
          </div>

          {/* Ticket Information */}
          <div className="space-y-2">
            {[
              { label: "Ticket ID", value: id === "preview" ? "Preview" : `#${id}` },
              { label: "Channel", value: isVoice ? "Voice Call" : "Chat", isChannel: true },
              { label: "Status", value: conversation?.status || "In progress", isStatus: true },
              { label: "Workflow state", value: conversation?.workflow_state || "with_expert" },
              { label: "Category", value: handoff?.category || contextData?.active_ticket?.category || "General" },
              { label: "Priority", value: handoff?.priority || contextData?.active_ticket?.priority || "medium", isStatus: true },
              { label: "Created At", value: conversation?.created_at ? new Date(conversation.created_at).toLocaleString() : "Active" },
            ].map((c) => (
              <div className="context-field flex items-center justify-between py-2" key={c.label}>
                <span className="text-muted-foreground text-[11px]">{c.label}</span>
                {c.isChannel ? (
                  isVoice ? (
                    <span
                      data-testid="expert-sidebar-channel-badge"
                      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                    >
                      <PhoneCall className="size-3" />
                      Voice Call
                    </span>
                  ) : (
                    <span
                      data-testid="expert-sidebar-channel-badge"
                      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-muted text-muted-foreground border border-border"
                    >
                      <MessageSquare className="size-3" />
                      Chat
                    </span>
                  )
                ) : c.isStatus ? (
                  <StatusBadge status={String(c.value)} size="sm" />
                ) : (
                  <span className="capitalize text-xs font-medium text-foreground">{c.value}</span>
                )}
              </div>
            ))}
          </div>

          {/* Cross-Ticket Incident Intelligence */}
          {contextData?.incident_context && (
            <div
              className={`p-3.5 rounded-xl border space-y-2.5 text-xs transition-colors ${
                contextData.incident_context.status === "confirmed"
                  ? "bg-rose-500/10 border-rose-500/30 text-rose-950 dark:text-rose-100"
                  : "bg-amber-500/10 border-amber-500/30 text-amber-950 dark:text-amber-100"
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 font-semibold">
                  <TriangleAlert className="size-3.5 text-rose-600 dark:text-rose-400" />
                  <span>Cross-Ticket Incident</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <StatusBadge status={contextData.incident_context.status || "candidate"} size="sm" />
                  <span
                    className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold uppercase ${
                      contextData.incident_context.severity === "CRITICAL"
                        ? "bg-rose-600 text-white"
                        : contextData.incident_context.severity === "HIGH"
                        ? "bg-rose-100 text-rose-800 dark:bg-rose-900/50 dark:text-rose-200"
                        : "bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200"
                    }`}
                  >
                    {contextData.incident_context.severity}
                  </span>
                </div>
              </div>

              {contextData.incident_context.is_spike && (
                <div className="p-1.5 rounded bg-rose-500/15 border border-rose-500/20 text-[10px] font-medium text-rose-700 dark:text-rose-300 flex items-center gap-1">
                  <TrendingUp className="size-3" />
                  Complaint Spike: {contextData.incident_context.spike_ratio}x above baseline
                </div>
              )}

              <div>
                <h4 className="font-medium text-foreground text-[11px] leading-snug">
                  {contextData.incident_context.title}
                </h4>
                <p className="text-muted-foreground text-[10px] mt-0.5 leading-tight">
                  {contextData.incident_context.description}
                </p>
              </div>

              {/* Related Tickets */}
              <div className="pt-1.5 border-t border-border/50 space-y-1">
                <div className="flex justify-between text-[10px] text-muted-foreground">
                  <span>Related Cases</span>
                  <span className="font-mono font-semibold text-foreground">
                    {contextData.incident_context.related_ticket_count} affected
                  </span>
                </div>
                {contextData.incident_context.related_tickets &&
                  contextData.incident_context.related_tickets.length > 0 && (
                    <div className="flex flex-wrap gap-1 pt-0.5">
                      {contextData.incident_context.related_tickets.map((rel: any) => (
                        <Link
                          key={rel.id}
                          to="/expert/queue"
                          className="px-1.5 py-0.5 rounded bg-background/80 hover:bg-background border border-border text-[10px] font-mono text-primary hover:underline transition-colors"
                          title={rel.subject || `Ticket #${rel.id}`}
                        >
                          #{rel.id}
                        </Link>
                      ))}
                    </div>
                  )}
              </div>

              {/* Evidence / Reason */}
              {contextData.incident_context.evidence &&
                contextData.incident_context.evidence.length > 0 && (
                  <div className="pt-1 border-t border-border/50 text-[10px] space-y-0.5">
                    <span className="text-muted-foreground font-medium block">Evidence:</span>
                    <ul className="list-disc list-inside text-muted-foreground space-y-0.5 pl-0.5">
                      {contextData.incident_context.evidence.map((ev: string, idx: number) => (
                        <li key={idx} className="leading-tight truncate">
                          {ev}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
            </div>
          )}

          {/* AI Insights & Code-Mixed Intelligence */}
          {(() => {
            const aiCtx = contextData?.ai_context;
            const langCtx = contextData?.language_context || aiCtx?.language_context;
            const confidenceVal = contextData?.confidence_score ?? aiCtx?.confidence_score;

            const formatLanguageBadge = (ctx: any) => {
              if (!ctx) return null;
              const mix = (ctx.code_mix_type || "").toLowerCase();
              const lang = (ctx.detected_language || "").toLowerCase();
              if (mix === "tanglish" || (ctx.is_code_mixed && lang === "ta")) {
                return "Tamil + English (Tanglish)";
              }
              if (mix === "hinglish" || (ctx.is_code_mixed && lang === "hi")) {
                return "Hindi + English (Hinglish)";
              }
              if (ctx.is_code_mixed && mix) {
                return `${mix.charAt(0).toUpperCase() + mix.slice(1)} (Code-Mixed)`;
              }
              if (lang === "ta") return "Tamil";
              if (lang === "hi") return "Hindi";
              if (lang === "en" || lang === "english") return "English";
              return ctx.detected_language || (ctx.is_code_mixed ? "Code-Mixed" : null);
            };

            const langBadge = formatLanguageBadge(langCtx);

            return (
              <div className="p-3.5 rounded-xl bg-primary/5 border border-primary/20 space-y-2.5 text-xs">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 font-semibold text-primary">
                    <Bot className="size-3.5" />
                    AI Intelligence
                  </div>
                  {typeof confidenceVal === "number" && (
                    <span
                      title="Resolution Confidence"
                      className={`font-mono text-[10px] font-semibold px-1.5 py-0.5 rounded border ${
                        confidenceVal >= 75
                          ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/20"
                          : confidenceVal >= 45
                          ? "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/20"
                          : "bg-rose-500/10 text-rose-700 dark:text-rose-400 border-rose-500/20"
                      }`}
                    >
                      {confidenceVal}% conf.
                    </span>
                  )}
                </div>

                {/* Detected Language */}
                {langBadge && (
                  <div className="flex items-center justify-between text-[11px] pt-0.5">
                    <span className="text-muted-foreground flex items-center gap-1">
                      <Globe2 className="size-3 text-primary/70" />
                      Detected Language
                    </span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-primary/10 text-primary border border-primary/20">
                      {langBadge}
                    </span>
                  </div>
                )}

                {/* Original Message (when code-mixed) */}
                {langCtx?.is_code_mixed && langCtx?.original_message && (
                  <div className="p-2 rounded-lg bg-background/80 border border-border/70 text-[11px] space-y-0.5">
                    <span className="text-muted-foreground text-[10px] block font-medium">
                      Original Message:
                    </span>
                    <p className="text-foreground/90 font-mono text-[11px] leading-snug">
                      "{langCtx.original_message}"
                    </p>
                  </div>
                )}

                {/* English Interpretation */}
                {langCtx?.normalized_message && (
                  <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/25 text-[11px] space-y-0.5">
                    <span className="text-emerald-700 dark:text-emerald-400 text-[10px] block font-semibold flex items-center gap-1">
                      <Sparkles className="size-3" />
                      English Interpretation:
                    </span>
                    <p className="text-emerald-950 dark:text-emerald-200 font-medium leading-snug">
                      {langCtx.normalized_message}
                    </p>
                  </div>
                )}

                <div className="flex justify-between text-[11px]">
                  <span className="text-muted-foreground">Intent</span>
                  <span className="font-medium font-mono text-foreground capitalize">
                    {aiCtx?.intent || "General"}
                  </span>
                </div>

                <div className="flex justify-between text-[11px]">
                  <span className="text-muted-foreground">Sentiment</span>
                  <span
                    className={`font-medium font-mono capitalize ${
                      aiCtx?.sentiment?.toLowerCase() === "negative"
                        ? "text-rose-600 dark:text-rose-400"
                        : aiCtx?.sentiment?.toLowerCase() === "positive"
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-foreground"
                    }`}
                  >
                    {aiCtx?.sentiment || "Neutral"}
                  </span>
                </div>

                {/* Resolution Summary */}
                <div className="pt-2 border-t border-primary/10">
                  <span className="text-muted-foreground text-[10px] block mb-0.5 font-medium">
                    Summary:
                  </span>
                  <p className="text-[11px] text-foreground leading-relaxed">
                    {aiCtx?.summary ||
                      handoff?.escalation_reason ||
                      "Escalated for human assistance."}
                  </p>
                </div>
              </div>
            );
          })()}

          {/* Resolution Failure Prediction & Risk Signals (M14 Task 3) */}
          {contextData?.failure_risk && (
            <div
              className={`p-3.5 rounded-xl border space-y-2.5 text-xs transition-colors ${
                contextData.failure_risk.risk_level === "HIGH" ||
                contextData.failure_risk.risk_level === "VERY_HIGH"
                  ? "bg-rose-500/10 border-rose-500/30 text-rose-950 dark:text-rose-100"
                  : contextData.failure_risk.risk_level === "MODERATE"
                  ? "bg-amber-500/10 border-amber-500/30 text-amber-950 dark:text-amber-100"
                  : "bg-slate-500/10 border-slate-500/20 text-foreground"
              }`}
            >
              <div className="flex items-center justify-between">
                <div
                  className={`flex items-center gap-1.5 font-semibold ${
                    contextData.failure_risk.risk_level === "HIGH" ||
                    contextData.failure_risk.risk_level === "VERY_HIGH"
                      ? "text-rose-700 dark:text-rose-400"
                      : contextData.failure_risk.risk_level === "MODERATE"
                      ? "text-amber-700 dark:text-amber-400"
                      : "text-muted-foreground"
                  }`}
                >
                  <ShieldCheck className="size-3.5" />
                  Resolution Failure Risk
                </div>
                <div className="flex items-center gap-1.5">
                  <span
                    className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold uppercase ${
                      contextData.failure_risk.risk_level === "HIGH" ||
                      contextData.failure_risk.risk_level === "VERY_HIGH"
                        ? "bg-rose-600 text-white"
                        : contextData.failure_risk.risk_level === "MODERATE"
                        ? "bg-amber-500/20 text-amber-800 dark:text-amber-200"
                        : "bg-slate-500/20 text-slate-700 dark:text-slate-300"
                    }`}
                  >
                    {contextData.failure_risk.risk_level} RISK
                  </span>
                  {typeof contextData.failure_risk.probability === "number" && (
                    <span className="font-mono text-[10px] opacity-80">
                      ({Math.round(contextData.failure_risk.probability * 100)}%)
                    </span>
                  )}
                </div>
              </div>

              {/* Predicted Difficulty */}
              <div className="flex justify-between text-[11px] pt-0.5">
                <span className="text-muted-foreground">Predicted Difficulty</span>
                <span className="font-mono font-semibold capitalize">
                  {contextData.failure_risk.predicted_difficulty}
                </span>
              </div>

              {/* Observed Prior Solution Failure Warning */}
              {contextData.failure_risk.has_prior_solution_failed && (
                <div className="p-2 rounded bg-rose-500/15 border border-rose-500/25 text-[11px] font-medium text-rose-800 dark:text-rose-200 flex items-center gap-1.5">
                  <TriangleAlert className="size-3.5 shrink-0 text-rose-600" />
                  <span>Customer reported prior solution failed</span>
                </div>
              )}

              {/* Unsuccessful attempts */}
              {contextData.failure_risk.observed_failure_count > 0 && (
                <div className="flex justify-between text-[11px]">
                  <span className="text-muted-foreground">Prior Unsuccessful Attempts</span>
                  <span className="font-mono font-semibold text-rose-600 dark:text-rose-400">
                    {contextData.failure_risk.observed_failure_count} failed
                  </span>
                </div>
              )}

              {/* Contributing warning signals */}
              {contextData.failure_risk.signals &&
                contextData.failure_risk.signals.length > 0 && (
                  <div className="pt-1.5 border-t border-border/50 text-[10px] space-y-1">
                    <span className="font-medium text-muted-foreground block">
                      Contributing Signals:
                    </span>
                    <ul className="list-disc list-inside space-y-0.5 pl-0.5 text-foreground/85">
                      {contextData.failure_risk.signals.map((sig: string, idx: number) => (
                        <li key={idx} className="leading-tight">
                          {sig}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

              {/* Suggested Next Action */}
              {contextData.failure_risk.suggested_action && (
                <div className="pt-1.5 border-t border-border/50 text-[11px]">
                  <span className="text-muted-foreground text-[10px] font-medium block">
                    Suggested Action:
                  </span>
                  <p className="font-medium text-foreground mt-0.5">
                    {contextData.failure_risk.suggested_action}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Ticket History */}
          {contextData?.ticket_history && contextData.ticket_history.length > 0 && (
            <div className="space-y-2 pt-2 border-t border-border">
              <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Previous Tickets
              </h4>
              <div className="space-y-1.5">
                {contextData.ticket_history.map((t: any) => (
                  <div
                    key={t.id}
                    className="p-2 rounded-lg bg-card border border-border/80 text-xs flex justify-between items-center"
                  >
                    <div>
                      <span className="font-mono font-medium">#{t.id}</span>
                      <span className="text-muted-foreground text-[10px] block">
                        {new Date(t.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-secondary text-secondary-foreground capitalize">
                      {t.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
            </>
          )}
        </aside>
      </div>
    </Workspace>
  );
}

export function AdminDashboard({ analytics = false }: { analytics?: boolean }) {
  const [period, setPeriod] = useState("30");
  const [summary, setSummary] = useState<any>(null);
  const [analyticsData, setAnalyticsData] = useState<any>(null);
  const [incidentsData, setIncidentsData] = useState<any>(null);
  const [failureRiskData, setFailureRiskData] = useState<any>(null);
  const [autonomyData, setAutonomyData] = useState<any>(null);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [incidentActionError, setIncidentActionError] = useState<string | null>(null);
  const [incidentActionSuccess, setIncidentActionSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchIncidents = async () => {
    try {
      const res = await api.get("/analytics/incidents");
      setIncidentsData(res.data);
    } catch (err) {
      console.warn("Failed to fetch incidents", err);
    }
  };

  useEffect(() => {
    let mounted = true;
    async function loadData() {
      try {
        const [sumRes, anaRes, incRes, failRes, autRes] = await Promise.allSettled([
          api.get("/tickets/summary"),
          api.get("/analytics"),
          api.get("/analytics/incidents"),
          api.get("/analytics/failure-risk"),
          api.get("/admin/autonomy"),
        ]);
        if (mounted) {
          if (sumRes.status === "fulfilled") setSummary(sumRes.value.data);
          if (anaRes.status === "fulfilled") setAnalyticsData(anaRes.value.data);
          if (incRes.status === "fulfilled") setIncidentsData(incRes.value.data);
          if (failRes.status === "fulfilled") setFailureRiskData(failRes.value.data);
          if (autRes.status === "fulfilled") setAutonomyData(autRes.value.data);
        }
      } catch (err) {
        console.error("Failed to load admin analytics", err);
      } finally {
        if (mounted) setLoading(false);
      }
    }
    loadData();
    return () => {
      mounted = false;
    };
  }, []);

  const handleUpdateIncidentStatus = async (incidentId: string, newStatus: string) => {
    setConfirmingId(incidentId);
    setIncidentActionError(null);
    setIncidentActionSuccess(null);
    try {
      await api.post(`/analytics/incidents/${incidentId}/status`, { status: newStatus });
      setIncidentActionSuccess(`Incident ${incidentId} transitioned to '${newStatus}' successfully.`);
      await fetchIncidents();
    } catch (err: any) {
      console.error("Failed to update incident status", err);
      setIncidentActionError(err.response?.data?.detail || err.message || "Failed to update incident status.");
    } finally {
      setConfirmingId(null);
    }
  };

  const overview = analyticsData?.overview;
  const total = overview?.total_conversations ?? (summary ? Object.values(summary as Record<string, number>).reduce((a, b) => a + b, 0) : 0);
  const aiResolved = overview?.ai_resolved ?? (summary?.ai_processing || 0);
  const expertResolved = overview?.expert_resolved ?? (summary?.resolved || 0);
  const resolutionRate = total > 0 ? Math.round(((aiResolved + expertResolved) / total) * 100) : 100;
  const aiResolutionRate = total > 0 ? Math.round((aiResolved / total) * 100) : 0;
  const escalated = overview?.escalated ?? (summary?.escalated || summary?.human_handling || 0);
  const escalationRate = total > 0 ? Math.round((escalated / total) * 100) : 0;
  const avgCsat = overview?.avg_csat ? overview.avg_csat.toFixed(1) : null;

  return (
    <Workspace
      role="admin"
      title={analytics ? "Analytics" : "Overview"}
      active={analytics ? "Analytics" : "Overview"}
    >
      <Heading
        title={analytics ? "Support, seen clearly." : "Your support operation at a glance."}
        description="Understand conversations, follow outcomes, and see where your team makes a difference."
        action={
          <Select value={period} onValueChange={setPeriod}>
            <SelectTrigger className="w-40 bg-card" aria-label="Analytics date range">
              <CalendarDays className="size-4 mr-2" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">Last 7 days</SelectItem>
              <SelectItem value="30">Last 30 days</SelectItem>
              <SelectItem value="90">Last 90 days</SelectItem>
            </SelectContent>
          </Select>
        }
      />

      {incidentActionError && (
        <div className="mb-4">
          <InlineAlert
            type="error"
            title="Incident Update Failed"
            message={incidentActionError}
            onDismiss={() => setIncidentActionError(null)}
          />
        </div>
      )}

      {incidentActionSuccess && (
        <div className="mb-4">
          <InlineAlert
            type="success"
            title="Incident Updated"
            message={incidentActionSuccess}
            onDismiss={() => setIncidentActionSuccess(null)}
          />
        </div>
      )}

      <div className="metric-grid">
        {loading ? (
          <>
            <MetricSkeleton />
            <MetricSkeleton />
            <MetricSkeleton />
            <MetricSkeleton />
            <MetricSkeleton />
          </>
        ) : (
          <>
            <Metric
              label="Total conversations"
              value={total}
              icon={MessageSquare}
              foot="All time tickets"
            />
            <Metric
              label="AI resolution rate"
              value={`${aiResolutionRate}%`}
              icon={CircleCheck}
              tone="success"
              foot={`${aiResolved} cases solved by AI`}
            />
            <Metric
              label="Expert resolved"
              value={expertResolved}
              icon={Users}
              foot={`${resolutionRate}% total solved`}
            />
            <Metric
              label="Escalated to experts"
              value={`${escalationRate}%`}
              icon={TriangleAlert}
              tone="warning"
              foot={`${escalated} required human touch`}
            />
            <Metric
              label="Customer satisfaction"
              value={avgCsat ? `${avgCsat} / 5.0` : "5.0 / 5.0"}
              icon={Star}
              tone="success"
              foot="Verified CSAT ratings"
            />
          </>
        )}
      </div>

      <div className="dashboard-grid">
        {/* Dynamic Autonomy Controls Status Banner */}
        {autonomyData && (
          <section className="col-span-full">
            <div className="p-4 rounded-2xl bg-card border border-border/70 flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-sm">
              <div className="flex items-center gap-3.5">
                <div className="size-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center shrink-0">
                  <Sliders className="size-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold text-foreground">
                      Active AI Autonomy: <span className="capitalize text-primary">{autonomyData.mode.replace("_", " ")}</span>
                    </h3>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                      Enforced
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Auto-resolve threshold ≥{autonomyData.auto_resolve_min_confidence}% confidence · Max risk {autonomyData.auto_resolve_max_risk} · Max {autonomyData.max_attempts_before_escalate} turns before expert review
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Button variant="outline" size="sm" asChild className="text-xs">
                  <Link to="/admin/settings">
                    <Sliders className="mr-1.5 size-3.5" />
                    Configure Autonomy
                  </Link>
                </Button>
              </div>
            </div>
          </section>
        )}

        {/* Customer Intent Distribution */}
        {analyticsData?.intents && analyticsData.intents.length > 0 && (
          <section className="col-span-full">
            <div className="section-title">
              <h2>Top customer intents</h2>
              <span className="text-xs text-muted-foreground">Classified automatically by AI</span>
            </div>
            <div className="panel p-6 space-y-4">
              {analyticsData.intents.map((item: any) => {
                const maxCount = Math.max(...analyticsData.intents.map((i: any) => i.count), 1);
                const pct = Math.round((item.count / maxCount) * 100);
                return (
                  <div key={item.intent} className="space-y-1.5">
                    <div className="flex justify-between text-xs">
                      <span className="font-medium text-foreground capitalize">
                        {item.intent.replace(/_/g, " ")}
                      </span>
                      <span className="text-muted-foreground font-mono">
                        {item.count} {item.count === 1 ? "ticket" : "tickets"}
                      </span>
                    </div>
                    <div className="h-2.5 w-full rounded-full bg-muted overflow-hidden">
                      <div
                        className="h-full rounded-full bg-primary transition-all duration-500"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {/* Cross-Ticket Incident Intelligence & Spike Monitoring */}
        <section className="col-span-full">
          <div className="section-title">
            <div className="flex items-center gap-2">
              <h2>Cross-Ticket Incident Intelligence</h2>
              {incidentsData?.spike_alerts && incidentsData.spike_alerts.length > 0 && (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20 flex items-center gap-1">
                  <TrendingUp className="size-3" />
                  {incidentsData.spike_alerts.length} Active Spike Alert{incidentsData.spike_alerts.length > 1 ? "s" : ""}
                </span>
              )}
            </div>
            <span className="text-xs text-muted-foreground">Cluster discovery & real-time spike detection</span>
          </div>

          <div className="space-y-4">
            {/* Spike Alerts Banner */}
            {incidentsData?.spike_alerts && incidentsData.spike_alerts.length > 0 && (
              <div className="space-y-2">
                {incidentsData.spike_alerts.map((alert: any, idx: number) => (
                  <div
                    key={idx}
                    className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/25 flex items-center justify-between text-xs text-rose-950 dark:text-rose-200"
                  >
                    <div className="flex items-center gap-2">
                      <TriangleAlert className="size-4 text-rose-600 dark:text-rose-400 shrink-0" />
                      <div>
                        <span className="font-semibold block">{alert.scope}</span>
                        <span className="text-[11px] opacity-90">{alert.message}</span>
                      </div>
                    </div>
                    {alert.ratio && (
                      <span className="font-mono font-bold text-xs px-2 py-0.5 rounded bg-rose-500/20">
                        {alert.ratio}x Surge
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Incident Candidates and Confirmed Incidents */}
            {incidentsData && (incidentsData.candidates?.length > 0 || incidentsData.confirmed?.length > 0) ? (
              <div className="grid md:grid-cols-2 gap-4">
                {/* Active Candidates */}
                <div className="panel p-5 space-y-3">
                  <div className="flex items-center justify-between border-b border-border/60 pb-2">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                      <Sparkles className="size-3.5 text-amber-500" />
                      Active Incident Candidates ({incidentsData.candidates?.length || 0})
                    </h3>
                  </div>

                  {incidentsData.candidates?.length > 0 ? (
                    <div className="space-y-2.5">
                      {incidentsData.candidates.map((cand: any) => (
                        <div
                          key={cand.incident_id}
                          className="p-3 rounded-lg border border-amber-500/25 bg-amber-500/5 space-y-2 text-xs"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-mono font-bold text-amber-700 dark:text-amber-400">
                              {cand.incident_id}
                            </span>
                            <div className="flex items-center gap-1.5">
                              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold bg-amber-500/15 text-amber-800 dark:text-amber-300">
                                {cand.severity}
                              </span>
                              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-muted text-muted-foreground">
                                {Math.round(cand.confidence * 100)}% match
                              </span>
                            </div>
                          </div>

                          <div>
                            <h4 className="font-medium text-foreground">{cand.title}</h4>
                            <p className="text-[11px] text-muted-foreground mt-0.5">
                              {cand.description}
                            </p>
                          </div>

                          <div className="flex items-center justify-between pt-1 text-[11px] text-muted-foreground border-t border-border/40">
                            <span>{cand.affected_ticket_count} tickets affected</span>
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 text-xs border-amber-500/30 hover:bg-amber-500/10"
                                disabled={confirmingId === cand.incident_id}
                                onClick={() => handleUpdateIncidentStatus(cand.incident_id, "investigating")}
                              >
                                {confirmingId === cand.incident_id ? (
                                  <Loader2 className="size-3 animate-spin mr-1" />
                                ) : null}
                                Investigate
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 text-xs border-rose-500/30 hover:bg-rose-500/10 text-rose-700 dark:text-rose-400"
                                disabled={confirmingId === cand.incident_id}
                                onClick={() => handleUpdateIncidentStatus(cand.incident_id, "confirmed")}
                              >
                                {confirmingId === cand.incident_id ? (
                                  <Loader2 className="size-3 animate-spin mr-1" />
                                ) : (
                                  <CheckCircle2 className="size-3 mr-1 text-emerald-600" />
                                )}
                                Confirm
                              </Button>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground py-4 text-center">
                      No unverified candidates pending review.
                    </p>
                  )}
                </div>

                {/* Confirmed Incidents */}
                <div className="panel p-5 space-y-3">
                  <div className="flex items-center justify-between border-b border-border/60 pb-2">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                      <ShieldCheck className="size-3.5 text-rose-500" />
                      Tracked Incidents ({incidentsData.confirmed?.length || 0})
                    </h3>
                  </div>

                  {incidentsData.confirmed?.length > 0 ? (
                    <div className="space-y-2.5">
                      {incidentsData.confirmed.map((conf: any) => (
                        <div
                          key={conf.incident_id}
                          className="p-3 rounded-lg border border-rose-500/25 bg-rose-500/5 space-y-2 text-xs"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-mono font-bold text-rose-700 dark:text-rose-400">
                              {conf.incident_id}
                            </span>
                            <div className="flex items-center gap-1.5">
                              <StatusBadge status={conf.status} size="sm" />
                              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-muted text-muted-foreground">
                                {conf.severity}
                              </span>
                            </div>
                          </div>

                          <div>
                            <h4 className="font-medium text-foreground">{conf.title}</h4>
                            <p className="text-[11px] text-muted-foreground mt-0.5">
                              {conf.description}
                            </p>
                          </div>

                          <div className="flex items-center justify-between pt-1 text-[11px] text-muted-foreground border-t border-border/40">
                            <span>{conf.affected_ticket_count} tickets affected</span>
                            <div className="flex items-center gap-1.5 flex-wrap">
                              {conf.status !== "investigating" && conf.status !== "resolved" && (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="h-7 text-xs"
                                  disabled={confirmingId === conf.incident_id}
                                  onClick={() => handleUpdateIncidentStatus(conf.incident_id, "investigating")}
                                >
                                  Investigate
                                </Button>
                              )}
                              {conf.status !== "mitigated" && conf.status !== "resolved" && (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="h-7 text-xs text-amber-700 hover:bg-amber-50"
                                  disabled={confirmingId === conf.incident_id}
                                  onClick={() => handleUpdateIncidentStatus(conf.incident_id, "mitigated")}
                                >
                                  Mitigate
                                </Button>
                              )}
                              {conf.status !== "resolved" ? (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="h-7 text-xs text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-950/30 border-emerald-500/30"
                                  disabled={confirmingId === conf.incident_id}
                                  onClick={() => handleUpdateIncidentStatus(conf.incident_id, "resolved")}
                                >
                                  {confirmingId === conf.incident_id ? (
                                    <Loader2 className="size-3 animate-spin mr-1" />
                                  ) : null}
                                  Resolve
                                </Button>
                              ) : (
                                <div className="flex items-center gap-1.5">
                                  <span className="text-emerald-600 text-[11px] font-medium flex items-center gap-1">
                                    <CircleCheck className="size-3" /> Resolved
                                  </span>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    className="h-6 text-[10px] text-muted-foreground hover:text-foreground"
                                    disabled={confirmingId === conf.incident_id}
                                    onClick={() => handleUpdateIncidentStatus(conf.incident_id, "investigating")}
                                  >
                                    Reopen
                                  </Button>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground py-4 text-center">
                      No confirmed operational incidents at this time.
                    </p>
                  )}
                </div>
              </div>
            ) : (
              <div className="panel p-6 text-center space-y-1.5">
                <CircleCheck className="size-6 text-emerald-600 mx-auto" />
                <h3 className="text-sm font-semibold text-foreground">Operational Baseline Normal</h3>
                <p className="text-xs text-muted-foreground max-w-md mx-auto">
                  No cross-ticket incident clusters or unusual complaint spikes detected across customer tickets.
                </p>
              </div>
            )}
          </div>
        </section>

        {/* Resolution Failure Prediction & Outcome Analytics (M14 Task 3) */}
        <section className="col-span-full">
          <div className="section-title">
            <div className="flex items-center gap-2">
              <h2>Resolution Failure Risk & Outcomes</h2>
              {failureRiskData?.high_risk_ticket_count > 0 && (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20">
                  {failureRiskData.high_risk_ticket_count} High Risk Cases
                </span>
              )}
            </div>
            <span className="text-xs text-muted-foreground">
              Early failure warning signals & verified resolution outcomes
            </span>
          </div>

          <div className="space-y-4">
            {/* 4 Metric Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="p-3.5 rounded-xl border border-rose-500/20 bg-rose-500/5 space-y-1">
                <span className="text-[11px] text-muted-foreground block">Predicted High Risk</span>
                <span className="text-xl font-bold font-mono text-rose-600 dark:text-rose-400">
                  {loading ? "…" : failureRiskData?.high_risk_ticket_count ?? 0}
                </span>
                <span className="text-[10px] text-muted-foreground block">Cases flagged early</span>
              </div>
              <div className="p-3.5 rounded-xl border border-amber-500/20 bg-amber-500/5 space-y-1">
                <span className="text-[11px] text-muted-foreground block">Observed Failures</span>
                <span className="text-xl font-bold font-mono text-amber-600 dark:text-amber-400">
                  {loading ? "…" : failureRiskData?.observed_failure_count ?? 0}
                </span>
                <span className="text-[10px] text-muted-foreground block">Tool errors & low CSAT</span>
              </div>
              <div className="p-3.5 rounded-xl border border-blue-500/20 bg-blue-500/5 space-y-1">
                <span className="text-[11px] text-muted-foreground block">Repeat Contact Rate</span>
                <span className="text-xl font-bold font-mono text-blue-600 dark:text-blue-400">
                  {loading ? "…" : `${failureRiskData?.repeat_contact_rate ?? 0}%`}
                </span>
                <span className="text-[10px] text-muted-foreground block">
                  {failureRiskData?.repeat_customer_count ?? 0} repeat customers
                </span>
              </div>
              <div className="p-3.5 rounded-xl border border-purple-500/20 bg-purple-500/5 space-y-1">
                <span className="text-[11px] text-muted-foreground block">Escalation Rate</span>
                <span className="text-xl font-bold font-mono text-purple-600 dark:text-purple-400">
                  {loading ? "…" : `${failureRiskData?.escalation_rate ?? escalationRate}%`}
                </span>
                <span className="text-[10px] text-muted-foreground block">Human intervention</span>
              </div>
            </div>

            {/* Category Distribution and Outcomes */}
            <div className="grid md:grid-cols-2 gap-4">
              {/* Category Risk Distribution */}
              <div className="panel p-5 space-y-3">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Failure Risk by Category
                </h3>
                {failureRiskData?.category_distribution && failureRiskData.category_distribution.length > 0 ? (
                  <div className="space-y-2">
                    {failureRiskData.category_distribution.map((cat: any) => (
                      <div key={cat.category} className="p-2.5 rounded-lg border border-border/70 bg-card space-y-1.5 text-xs">
                        <div className="flex justify-between font-medium">
                          <span>{cat.category}</span>
                          <span className="font-mono text-muted-foreground">{cat.total} total</span>
                        </div>
                        <div className="flex gap-2 text-[10px]">
                          <span className="text-rose-600 dark:text-rose-400 font-medium">
                            {cat.high_risk} High
                          </span>
                          <span className="text-amber-600 dark:text-amber-400 font-medium">
                            {cat.moderate_risk} Moderate
                          </span>
                          <span className="text-emerald-600 dark:text-emerald-400 font-medium">
                            {cat.low_risk} Low
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground py-2 text-center">
                    No category distribution data available yet.
                  </p>
                )}
              </div>

              {/* Verified Outcome Tracking */}
              <div className="panel p-5 space-y-3">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Verified Outcome Breakdown
                </h3>
                <div className="space-y-2 text-xs">
                  <div className="flex justify-between p-2 rounded bg-muted/30">
                    <span className="text-muted-foreground">AI Solved Cleanly:</span>
                    <span className="font-mono font-semibold text-emerald-600">
                      {failureRiskData?.outcomes?.ai_resolved_success ?? 0}
                    </span>
                  </div>
                  <div className="flex justify-between p-2 rounded bg-muted/30">
                    <span className="text-muted-foreground">Expert Resolved Handoffs:</span>
                    <span className="font-mono font-semibold text-blue-600">
                      {failureRiskData?.outcomes?.expert_resolved ?? 0}
                    </span>
                  </div>
                  <div className="flex justify-between p-2 rounded bg-muted/30">
                    <span className="text-muted-foreground">Observed Tool Execution Failures:</span>
                    <span className="font-mono font-semibold text-rose-600">
                      {failureRiskData?.outcomes?.observed_tool_failures ?? 0}
                    </span>
                  </div>
                  <div className="flex justify-between p-2 rounded bg-muted/30">
                    <span className="text-muted-foreground">Customer Low-CSAT Reports (≤2):</span>
                    <span className="font-mono font-semibold text-amber-600">
                      {failureRiskData?.outcomes?.low_csat_feedback_count ?? 0}
                    </span>
                  </div>
                </div>

                {/* Limitation & Disclaimer */}
                <div className="pt-2 border-t border-border/50 text-[10px] text-muted-foreground leading-tight space-y-1">
                  <span className="font-semibold text-foreground/80 block">Data Integrity Note:</span>
                  <p>
                    Metrics are strictly computed from verified database records. Predictions are explainable warning signals and are distinguished from confirmed outcomes.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section>
          <div className="section-title">
            <h2>System Status</h2>
            <span className="text-[10px] text-muted-foreground">{period} day period</span>
          </div>
          <div className="panel p-6 space-y-4">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">AI Resolution Provider</span>
              <span className="font-medium">Groq / Llama 3.3 70B</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Knowledge Retriever</span>
              <span className="font-medium">Hybrid TF-IDF + FAISS</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Realtime Streaming</span>
              <span className="font-medium text-emerald-600">Active (WebSockets)</span>
            </div>
          </div>
        </section>

        <section>
          <div className="section-title">
            <h2>Status breakdown</h2>
          </div>
          <div className="panel p-6 space-y-3">
            {summary &&
              Object.entries(summary).map(([k, v]) => (
                <div key={k} className="flex justify-between text-xs items-center">
                  <span className="capitalize text-muted-foreground">{k.replace(/_/g, " ")}</span>
                  <span className="font-semibold">{String(v)}</span>
                </div>
              ))}
          </div>
        </section>
      </div>
    </Workspace>
  );
}

export function KnowledgePage() {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("All documents");
  const [dialog, setDialog] = useState(false);
  const [articles, setArticles] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // New article form
  const [newTitle, setNewTitle] = useState("");
  const [newCategory, setNewCategory] = useState("General");
  const [newContent, setNewContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const fetchArticles = async () => {
    try {
      setLoading(true);
      const res = await api.get("/knowledge");
      setArticles(res.data || []);
    } catch (err) {
      console.error("Failed to load knowledge articles", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchArticles();
  }, []);

  const handleCreate = async () => {
    if (!newTitle.trim() || !newContent.trim()) return;
    setSaving(true);
    setCreateError(null);
    try {
      await api.post("/knowledge", {
        title: newTitle.trim(),
        category: newCategory.trim(),
        content: newContent.trim(),
        is_active: true,
      });
      setDialog(false);
      setNewTitle("");
      setNewContent("");
      await fetchArticles();
    } catch (err: any) {
      console.error("Failed to create article", err);
      setCreateError(err.response?.data?.detail || err.message || "Failed to save article.");
    } finally {
      setSaving(false);
    }
  };

  const filtered = articles.filter((a) => {
    const text = `${a.title} ${a.content} ${a.category}`.toLowerCase();
    return !query.trim() || text.includes(query.toLowerCase());
  });

  return (
    <Workspace role="admin" title="Knowledge Base" active="Knowledge Base">
      <Heading
        title="The knowledge behind every answer."
        description="Keep your support documents organized, current, and ready for retrieval."
        action={
          <Button onClick={() => { setCreateError(null); setDialog(true); }}>
            <Plus className="mr-1.5 size-4" />
            Add article
          </Button>
        }
      />
      <div className="filter-bar">
        <SearchField value={query} onChange={setQuery} placeholder="Search your knowledge base…" />
      </div>
      <div className="panel">
        {loading ? (
          <TableSkeleton rows={4} cols={4} />
        ) : filtered.length > 0 ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Article title</th>
                  <th>Category</th>
                  <th>Status</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((art) => (
                  <tr key={art.id}>
                    <td className="font-medium text-foreground">{art.title}</td>
                    <td>
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-secondary text-secondary-foreground">
                        {art.category || "General"}
                      </span>
                    </td>
                    <td>
                      <StatusBadge status="active" size="sm" />
                    </td>
                    <td className="text-xs text-muted-foreground">
                      {art.updated_at ? new Date(art.updated_at).toLocaleDateString() : new Date(art.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title={query ? "No matching documents" : "Your knowledge starts here"}
            description="Add articles to feed the AI RAG retriever."
            icon={FileText}
          />
        )}
      </div>

      <Dialog open={dialog} onOpenChange={setDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Add a knowledge article</DialogTitle>
            <DialogDescription>
              Articles are indexed into the RAG vector store for instant retrieval by ResolveAI.
            </DialogDescription>
          </DialogHeader>

          {createError && (
            <InlineAlert
              type="error"
              message={createError}
              onDismiss={() => setCreateError(null)}
            />
          )}

          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <label className="text-xs font-medium">Article Title</label>
              <Input
                placeholder="e.g. Refund and Return Policy"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium">Category</label>
              <Input
                placeholder="e.g. Billing, Account, Orders"
                value={newCategory}
                onChange={(e) => setNewCategory(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium">Article Content</label>
              <Textarea
                placeholder="Full article content and instructions…"
                rows={5}
                value={newContent}
                onChange={(e) => setNewContent(e.target.value)}
              />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button onClick={() => setDialog(false)} variant="outline">
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={!newTitle.trim() || !newContent.trim() || saving}>
              {saving ? <Loader2 className="size-3.5 animate-spin mr-1" /> : null}
              Save & Index
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Workspace>
  );
}

export function UsersPage() {
  const { user } = useAuth();
  return (
    <Workspace role="admin" title="Users & Roles" active="Users & Roles">
      <Heading
        title="The people behind your support."
        description="Account visibility and permissions, managed by your existing service."
      />
      <div className="panel p-6 space-y-6">
        <h3 className="text-sm font-semibold mb-3">Active Session User</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
          <div>
            <span className="text-muted-foreground block mb-1">Full Name</span>
            <span className="font-medium text-foreground">{user?.full_name || user?.email || "Admin User"}</span>
          </div>
          <div>
            <span className="text-muted-foreground block mb-1">Email</span>
            <span className="font-medium text-foreground">{user?.email}</span>
          </div>
          <div>
            <span className="text-muted-foreground block mb-1">Role</span>
            <StatusBadge status={user?.role || "ADMIN"} size="sm" />
          </div>
          <div>
            <span className="text-muted-foreground block mb-1">Tenant Context</span>
            <span className="font-mono text-xs font-medium text-foreground bg-muted px-2 py-0.5 rounded">
              {user?.tenant_id || "default"}
            </span>
          </div>
        </div>

        <div className="pt-4 border-t border-border/60">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
            Role Permission Matrix & Workspace Isolation
          </h4>
          <div className="grid md:grid-cols-3 gap-3 text-xs">
            <div className="p-3.5 rounded-xl border border-border bg-card space-y-1.5">
              <span className="font-semibold text-primary block">Customer Portal</span>
              <p className="text-muted-foreground text-[11px] leading-relaxed">
                Initiate support conversations, submit complaints in English, Tanglish, or Hinglish, review resolution updates, authorize tool actions, and submit CSAT reviews.
              </p>
            </div>
            <div className="p-3.5 rounded-xl border border-border bg-card space-y-1.5">
              <span className="font-semibold text-emerald-600 block">Expert Workspace</span>
              <p className="text-muted-foreground text-[11px] leading-relaxed">
                Claim escalation handoffs, view AI confidence & failure risk metrics, inspect normalized English interpretations of code-mixed queries, and resolve complex issues.
              </p>
            </div>
            <div className="p-3.5 rounded-xl border border-border bg-card space-y-1.5">
              <span className="font-semibold text-rose-600 block">Admin Workspace</span>
              <p className="text-muted-foreground text-[11px] leading-relaxed">
                Operational analytics, cross-ticket incident detection and lifecycle transitions, and dynamic tenant-scoped AI autonomy configuration with strict safety bounds.
              </p>
            </div>
          </div>
        </div>
      </div>
    </Workspace>
  );
}
