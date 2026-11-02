import { Link } from "@tanstack/react-router";
import {
  PhoneCall,
  MessageSquare,
  ArrowRight,
  Headphones,
  Sparkles,
  ArrowUpRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Logo } from "./workspace";
import { useAuth } from "@/lib/auth";

export function LandingPage() {
  const { user } = useAuth();

  const dashboardRoute =
    user?.role === "expert"
      ? "/expert"
      : user?.role === "admin"
      ? "/admin"
      : "/dashboard";

  return (
    <div className="min-h-screen bg-[#080A08] text-[#F9F9F9] font-sans antialiased selection:bg-[#A7FE08]/30 selection:text-[#A7FE08]">
      {/* 1. Header Navigation */}
      <header className="sticky top-0 z-50 border-b border-[#30382C]/60 bg-[#080A08]/90 backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center">
            <Logo />
          </Link>

          <nav className="hidden sm:flex items-center gap-6 text-xs text-[#A3A4A1] font-medium">
            <Link to="/call" className="hover:text-[#A7FE08] transition-colors">
              Voice Call
            </Link>
            <Link to="/help" className="hover:text-[#A7FE08] transition-colors">
              Help Center
            </Link>
          </nav>

          <div className="flex items-center gap-3">
            {user ? (
              <Link to={dashboardRoute}>
                <Button className="h-9 px-4 bg-[#A7FE08] text-[#10130A] font-semibold hover:bg-[#BBFF45] transition-all text-xs gap-1.5 shadow-[0_0_16px_rgba(167,254,8,0.2)]">
                  Go to Dashboard
                  <ArrowRight className="size-3.5" />
                </Button>
              </Link>
            ) : (
              <div className="flex items-center gap-2">
                <Link
                  to="/login"
                  className="text-xs font-semibold px-3 py-2 text-[#F9F9F9] hover:text-[#A7FE08] transition-colors"
                >
                  Sign In
                </Link>
                <Link to="/register">
                  <Button className="h-9 px-4 bg-[#A7FE08] text-[#10130A] font-bold hover:bg-[#BBFF45] transition-all text-xs gap-1.5 shadow-[0_0_16px_rgba(167,254,8,0.2)]">
                    Get Started
                    <ArrowUpRight className="size-3.5" />
                  </Button>
                </Link>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* 2. Hero Section */}
      <section className="pt-14 pb-16 md:pt-20 md:pb-24 max-w-4xl mx-auto px-4 sm:px-6 text-center space-y-6">
        {/* Eyebrow Badge */}
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#151A14] border border-[#30382C] text-xs text-[#A3A4A1]">
          <Sparkles className="size-3 text-[#A7FE08]" />
          <span className="text-[#A7FE08] font-medium">ResolveAI</span>
          <span>· Real-time Voice &amp; Chat Support</span>
        </div>

        {/* Headline */}
        <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-white leading-[1.15]">
          Intelligent Customer Support,{" "}
          <span className="text-[#A7FE08]">Powered by Voice AI</span>
        </h1>

        {/* Simple Description */}
        <p className="text-sm sm:text-base text-[#A3A4A1] max-w-xl mx-auto leading-relaxed">
          Talk or chat with an intelligent AI support agent that resolves your inquiries in real-time —
          from order status and password resets to instant assistance.
        </p>

        {/* CTA Actions */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
          <Link to="/call" className="w-full sm:w-auto">
            <Button className="w-full sm:w-auto h-11 px-6 bg-[#A7FE08] text-[#10130A] font-bold text-xs hover:bg-[#BBFF45] transition-all gap-2 shadow-[0_0_20px_rgba(167,254,8,0.3)]">
              <PhoneCall className="size-4" />
              Start Voice Call
            </Button>
          </Link>
          <Link to={user ? "/dashboard" : "/login"} className="w-full sm:w-auto">
            <Button
              variant="outline"
              className="w-full sm:w-auto h-11 px-6 bg-[#111411] border-[#30382C] text-white hover:bg-[#1A2018] text-xs font-semibold transition-all gap-2"
            >
              <MessageSquare className="size-4 text-[#A7FE08]" />
              Open Support Chat
            </Button>
          </Link>
        </div>
      </section>

      {/* 3. Simple Highlights (3 Pillars) */}
      <section className="py-16 border-t border-[#30382C]/60 bg-[#0A0D0A]">
        <div className="max-w-5xl mx-auto px-4 sm:px-6">
          <div className="text-center max-w-lg mx-auto mb-10 space-y-2">
            <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
              What ResolveAI Does
            </h2>
            <p className="text-xs text-[#A3A4A1]">
              A complete support platform designed to give you fast, effortless answers.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {/* Pillar 1 */}
            <div className="p-6 rounded-xl bg-[#111411] border border-[#30382C] space-y-3">
              <div className="size-10 rounded-lg bg-[#A7FE08]/10 border border-[#A7FE08]/20 flex items-center justify-center text-[#A7FE08]">
                <PhoneCall className="size-5" />
              </div>
              <h3 className="text-base font-bold text-white">Natural Voice Calls</h3>
              <p className="text-xs text-[#A3A4A1] leading-relaxed">
                Call our AI agent directly from your browser. Speak naturally with real-time audio and
                instant responses.
              </p>
            </div>

            {/* Pillar 2 */}
            <div className="p-6 rounded-xl bg-[#111411] border border-[#30382C] space-y-3">
              <div className="size-10 rounded-lg bg-[#5DAF08]/15 border border-[#5DAF08]/20 flex items-center justify-center text-[#5DAF08]">
                <MessageSquare className="size-5" />
              </div>
              <h3 className="text-base font-bold text-white">AI Support Chat</h3>
              <p className="text-xs text-[#A3A4A1] leading-relaxed">
                Type your questions, track support tickets, and get immediate answers with zero hold time.
              </p>
            </div>

            {/* Pillar 3 */}
            <div className="p-6 rounded-xl bg-[#111411] border border-[#30382C] space-y-3">
              <div className="size-10 rounded-lg bg-[#A7FE08]/10 border border-[#A7FE08]/20 flex items-center justify-center text-[#A7FE08]">
                <Headphones className="size-5" />
              </div>
              <h3 className="text-base font-bold text-white">Human Expert Handoff</h3>
              <p className="text-xs text-[#A3A4A1] leading-relaxed">
                When an issue needs specialized attention, our team of support experts is ready to step in
                seamlessly.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* 4. Simple How It Works (3 Steps) */}
      <section className="py-16 max-w-4xl mx-auto px-4 sm:px-6">
        <div className="text-center max-w-lg mx-auto mb-10 space-y-2">
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
            How It Works
          </h2>
          <p className="text-xs text-[#A3A4A1]">
            Getting help takes only three simple steps.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 text-center">
          <div className="space-y-2 p-4">
            <span className="inline-flex items-center justify-center size-8 rounded-full bg-[#151A14] border border-[#A7FE08]/40 text-xs font-bold text-[#A7FE08]">
              1
            </span>
            <h4 className="text-sm font-semibold text-white">Connect via Voice or Chat</h4>
            <p className="text-xs text-[#A3A4A1] leading-relaxed">
              Start a voice call or open a chat message anytime, 24/7.
            </p>
          </div>

          <div className="space-y-2 p-4">
            <span className="inline-flex items-center justify-center size-8 rounded-full bg-[#151A14] border border-[#A7FE08]/40 text-xs font-bold text-[#A7FE08]">
              2
            </span>
            <h4 className="text-sm font-semibold text-white">Get Instant Resolution</h4>
            <p className="text-xs text-[#A3A4A1] leading-relaxed">
              The AI answers questions, checks details, and solves requests on the spot.
            </p>
          </div>

          <div className="space-y-2 p-4">
            <span className="inline-flex items-center justify-center size-8 rounded-full bg-[#151A14] border border-[#A7FE08]/40 text-xs font-bold text-[#A7FE08]">
              3
            </span>
            <h4 className="text-sm font-semibold text-white">Track &amp; Stay Updated</h4>
            <p className="text-xs text-[#A3A4A1] leading-relaxed">
              Review full conversation histories and ticket status in your dashboard.
            </p>
          </div>
        </div>
      </section>

      {/* 5. Simple CTA Banner */}
      <section className="py-16 max-w-4xl mx-auto px-4 sm:px-6">
        <div className="rounded-2xl p-8 sm:p-10 bg-[#111411] border border-[#30382C] text-center space-y-4 shadow-lg">
          <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
            Ready to experience ResolveAI?
          </h2>
          <p className="text-xs sm:text-sm text-[#A3A4A1] max-w-md mx-auto leading-relaxed">
            Start a voice call right now or create your free account to get started.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
            <Link to="/call" className="w-full sm:w-auto">
              <Button className="w-full sm:w-auto h-11 px-6 bg-[#A7FE08] text-[#10130A] font-bold text-xs hover:bg-[#BBFF45] transition-all gap-1.5 shadow-[0_0_16px_rgba(167,254,8,0.25)]">
                <PhoneCall className="size-4" />
                Start Voice Call
              </Button>
            </Link>
            <Link to="/register" className="w-full sm:w-auto">
              <Button
                variant="outline"
                className="w-full sm:w-auto h-11 px-6 bg-[#151A14] border-[#30382C] text-white hover:bg-[#1A2018] text-xs font-semibold transition-all gap-1.5"
              >
                Create Account
                <ArrowRight className="size-3.5" />
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* 6. Clean Minimal Footer */}
      <footer className="border-t border-[#30382C]/60 py-8 text-xs text-[#A3A4A1] bg-[#050605]">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <Logo />
            <span className="text-[#A3A4A1] text-[11px]">
              Autonomous Voice &amp; Chat Support
            </span>
          </div>
          <div className="flex items-center gap-5 text-[11px]">
            <Link to="/call" className="hover:text-[#A7FE08] transition-colors">
              Voice Call
            </Link>
            <Link to="/dashboard" className="hover:text-[#A7FE08] transition-colors">
              Dashboard
            </Link>
            <Link to="/help" className="hover:text-[#A7FE08] transition-colors">
              Help
            </Link>
            <Link to="/login" className="hover:text-[#A7FE08] transition-colors">
              Sign In
            </Link>
          </div>
          <p className="text-[11px] text-[#A3A4A1]/80">
            © {new Date().getFullYear()} ResolveAI. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}
