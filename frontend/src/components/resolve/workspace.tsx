import { useState, useEffect, type ReactNode } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import {
  LayoutDashboard,
  MessageSquare,
  MessagesSquare,
  BookOpen,
  Settings,
  ChevronDown,
  ChevronRight,
  Bell,
  Search,
  PanelLeftClose,
  Headphones,
  ArrowUpRight,
  Layers,
  ListFilter,
  Users,
  ChartNoAxesCombined,
  Files,
  Inbox,
  X,
  Menu,
  Loader2,
  PhoneCall,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { useWebSocket } from "@/lib/ws";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
export type Role = "customer" | "expert" | "admin";
export function Logo() {
  return (
    <span className="brand">
      <span className="logo-mark">
        <MessagesSquare className="size-4.5 text-primary-foreground" strokeWidth={2} />
      </span>
      <span>
        Resolve<span className="text-primary">AI</span>
      </span>
    </span>
  );
}
const navigation = {
  customer: [
    { label: "Dashboard", to: "/dashboard", icon: LayoutDashboard },
    { label: "Voice Call", to: "/call", icon: PhoneCall },
    { label: "AI Support Chat", to: "/chat/$id", icon: MessageSquare },
    { label: "My Conversations", to: "/conversations", icon: MessagesSquare },
    { label: "Help Center", to: "/help", icon: BookOpen },
  ],
  expert: [
    { label: "Dashboard", to: "/expert", icon: LayoutDashboard },
    { label: "Case Queue", to: "/expert/queue", icon: Inbox },
    { label: "My Assigned Cases", to: "/expert/assigned", icon: ListFilter },
    { label: "Conversation History", to: "/expert/history", icon: MessagesSquare },
  ],
  admin: [
    { label: "Overview", to: "/admin", icon: LayoutDashboard },
    { label: "Analytics", to: "/admin/analytics", icon: ChartNoAxesCombined },
    { label: "Knowledge Base", to: "/admin/knowledge", icon: Files },
    { label: "Tickets", to: "/admin/tickets", icon: Inbox },
    { label: "Users & Roles", to: "/admin/users", icon: Users },
    { label: "Autonomy Settings", to: "/admin/settings", icon: Settings },
  ],
} as const;
export function Workspace({
  children,
  role = "customer",
  title,
  active,
}: {
  children: ReactNode;
  role?: Role;
  title: string;
  active?: string;
}) {
  const [mobile, setMobile] = useState(false);
  const [search, setSearch] = useState(false);
  const [query, setQuery] = useState("");
  const { user, logout, isLoading } = useAuth();
  const navigate = useNavigate();
  const { isConnected } = useWebSocket();

  useEffect(() => {
    if (!isLoading && !user) {
      navigate({ to: "/login", replace: true });
    }
  }, [isLoading, user, navigate]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <Loader2 className="size-6 animate-spin text-primary" />
      </div>
    );
  }

  if (!user) {
    return null;
  }

  const settings =
    role === "customer" ? "/settings" : role === "expert" ? "/expert/profile" : "/admin/settings";

  const initials = user?.full_name
    ? user.full_name
        .split(" ")
        .map((n) => n[0])
        .join("")
        .substring(0, 2)
        .toUpperCase()
    : "RA";
  return (
    <div className="workspace">
      <aside className={`sidebar ${mobile ? "open" : ""}`}>
        <div className="sidebar-brand">
          <Link to="/" aria-label="ResolveAI home">
            <Logo />
          </Link>
        </div>
        <div className="workspace-label">
          <span className="small-icon !size-7">
            <Layers className="!size-3.5" />
          </span>
          <span className="flex-1">
            {role === "customer"
              ? "Customer Portal"
              : role === "expert"
                ? "Expert Workspace"
                : "Admin Workspace"}
          </span>
          <ChevronDown className="size-3 text-muted-foreground" />
        </div>
        <p className="nav-label">Workspace</p>
        <nav className="nav-list">
          {navigation[role].map((item) => (
            <Link
              key={item.label}
              to={item.to}
              activeOptions={{ exact: true }}
              params={item.to === "/chat/$id" ? { id: "new" } : {}}
              className={`nav-item ${active === item.label ? "active" : ""}`}
              onClick={() => setMobile(false)}
            >
              <item.icon />
              {item.label}
              {active === item.label && <span className="nav-dot" />}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="assistance">
            <Headphones className="size-5 text-primary" />
            <h3>A little help goes a long way.</h3>
            <p>Find answers, or start a conversation with ResolveAI.</p>
            <Button asChild variant="outline" size="sm" className="w-full justify-between">
              <Link to="/help">
                Visit Help Center
                <ArrowUpRight />
              </Link>
            </Button>
          </div>
          <nav className="nav-list !p-0">
            <Link to={settings} className={`nav-item ${active === "Settings" ? "active" : ""}`}>
              <Settings />
              Settings
            </Link>
          </nav>
          <div className="profile-row">
            <div className="avatar">{initials}</div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold truncate">{user ? user.full_name : "ResolveAI User"}</p>
              <p className="text-[10px] text-muted-foreground mt-0.5 truncate">
                {user ? user.email : "Not signed in"}
              </p>
            </div>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon-sm" aria-label="Account menu">
                  <ChevronDown />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuLabel>Account</DropdownMenuLabel>
                {user ? (
                  <>
                    <DropdownMenuItem asChild>
                      <Link to={settings}>Account settings</Link>
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={logout} className="text-destructive cursor-pointer">
                      Sign out
                    </DropdownMenuItem>
                  </>
                ) : (
                  <DropdownMenuItem asChild>
                    <Link to="/login">Sign in</Link>
                  </DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
          <details className="workspace-switch">
            <summary>Switch workspace</summary>
            <Link to="/dashboard">Customer portal</Link>
            <Link to="/expert">Expert workspace</Link>
            <Link to="/admin">Admin workspace</Link>
          </details>
        </div>
      </aside>
      <main className="main-shell">
        <header className="topbar">
          <div className="topbar-title">
            <Button
              variant="ghost"
              size="icon-sm"
              className="mobile-menu"
              onClick={() => setMobile(!mobile)}
              aria-label="Toggle navigation"
            >
              {mobile ? <X /> : <Menu />}
            </Button>
            <PanelLeftClose className="size-4 text-muted-foreground hidden md:block" />
            <span className="text-border hidden md:block">/</span>
            {title}
          </div>
          <div className="topbar-actions">
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Search workspace"
              className="search-button"
              onClick={() => setSearch(true)}
            >
              <Search />
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon-sm" aria-label="Notifications">
                  <Bell />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-64 p-4">
                <DropdownMenuLabel>Notifications</DropdownMenuLabel>
                <p className="text-xs text-muted-foreground p-2">
                  No new notifications.
                </p>
              </DropdownMenuContent>
            </DropdownMenu>
            <span className="h-6 border-l border-border mx-1" />
            <Link to={user ? settings : "/login"} className="avatar" aria-label="Account">
              {initials}
            </Link>
          </div>
        </header>
        <div className="content">
          {children}
          <footer className="page-footer">
            <span>© 2026 ResolveAI. Agentic Multilingual Customer Support.</span>
            <span className={isConnected ? "connection text-emerald-600 font-medium" : "connection text-muted-foreground"}>
              {isConnected ? "● Connected" : "Connecting..."}
            </span>
          </footer>
        </div>
      </main>
      <Dialog open={search} onOpenChange={setSearch}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Search your workspace</DialogTitle>
          </DialogHeader>
          <Input
            autoFocus
            placeholder="Find a page…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="nav-list">
            {navigation[role]
              .filter((i) => i.label.toLowerCase().includes(query.toLowerCase()))
              .map((i) => (
                <Link
                  key={i.label}
                  to={i.to}
                  params={i.to === "/chat/$id" ? { id: "new" } : {}}
                  className="nav-item"
                  onClick={() => setSearch(false)}
                >
                  <i.icon />
                  {i.label}
                  <ChevronRight className="ml-auto" />
                </Link>
              ))}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
