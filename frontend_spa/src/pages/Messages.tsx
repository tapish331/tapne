import { useState, useEffect, useRef, useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useAuth } from "@/contexts/AuthContext";
import { apiGet, apiPost } from "@/lib/api";
import type { ThreadData, InboxResponse, MessageData } from "@/types/messaging";
import {
  MessageCircle, Send, ArrowLeft, Users, MapPin,
  Loader2, Inbox as InboxIcon, Search,
} from "lucide-react";
import { cn } from "@/lib/utils";

const MIN_SIDEBAR = 280;
const MAX_SIDEBAR = 480;
const DEFAULT_SIDEBAR = 360;

const Inbox = () => {
  const { user, isAuthenticated, requireAuth } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [threads, setThreads] = useState<ThreadData[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeThreadId, setActiveThreadId] = useState<number | null>(null);
  const [messageInput, setMessageInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [sending, setSending] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(DEFAULT_SIDEBAR);
  const [isResizing, setIsResizing] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const resizeRef = useRef<{ startX: number; startW: number } | null>(null);

  const openThreadParam = searchParams.get("thread");
  const newDmParam = searchParams.get("dm");
  const tripQueryParam = searchParams.get("trip_query");

  const inboxUrl = useMemo(() => {
    const cfg = window.TAPNE_RUNTIME_CONFIG;
    const url = new URL(cfg.api.dm_inbox, window.location.origin);
    if (newDmParam && !url.searchParams.get("dm")) {
      url.searchParams.set("dm", newDmParam);
    }
    return `${url.pathname}${url.search}`;
  }, [newDmParam]);

  useEffect(() => {
    if (!isAuthenticated) {
      requireAuth(() => {});
      return;
    }

    setLoading(true);
    apiGet<InboxResponse>(inboxUrl)
      .then((data) => {
        setThreads(data.threads || []);
        if (openThreadParam) {
          const parsed = Number.parseInt(openThreadParam, 10);
          if (!Number.isNaN(parsed)) {
            setActiveThreadId(parsed);
            return;
          }
        }
        if (data.threads.length > 0 && window.innerWidth >= 768) {
          setActiveThreadId(data.threads[0].id);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [inboxUrl, isAuthenticated, openThreadParam, requireAuth]);

  useEffect(() => {
    if (newDmParam && threads.length > 0) {
      const existing = threads.find(
        (thread) => thread.type === "dm" && thread.participants.some((participant) => participant.username === newDmParam)
      );
      if (existing) setActiveThreadId(existing.id);
    }
    if (tripQueryParam && threads.length > 0) {
      const existing = threads.find(
        (thread) => thread.type === "trip_query" && String(thread.trip_id) === tripQueryParam
      );
      if (existing) setActiveThreadId(existing.id);
    }
  }, [newDmParam, tripQueryParam, threads]);

  const activeThread = useMemo(
    () => threads.find((thread) => thread.id === activeThreadId) || null,
    [threads, activeThreadId]
  );

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeThread?.messages?.length]);

  const handleSend = async () => {
    if (!messageInput.trim() || !activeThread || !user) return;
    setSending(true);
    const cfg = window.TAPNE_RUNTIME_CONFIG;
    const newMessage: MessageData = {
      id: Date.now(),
      thread_id: activeThread.id,
      sender_username: user.username || "dev_user",
      sender_display_name: user.name || "Dev User",
      sender_avatar: user.avatar,
      body: messageInput.trim(),
      sent_at: new Date().toISOString(),
    };

    setThreads((prev) =>
      prev.map((thread) =>
        thread.id === activeThread.id
          ? {
              ...thread,
              messages: [...thread.messages, newMessage],
              last_message: newMessage.body,
              last_sent_at: newMessage.sent_at,
            }
          : thread
      )
    );
    setMessageInput("");

    try {
      await apiPost(`${cfg.api.dm_inbox}${activeThread.id}/messages/`, {
        body: newMessage.body,
      });
    } catch {
      // Message already shown optimistically.
    } finally {
      setSending(false);
    }
  };

  const filteredThreads = useMemo(() => {
    if (!searchQuery.trim()) return threads;
    const query = searchQuery.toLowerCase();
    return threads.filter(
      (thread) =>
        thread.title.toLowerCase().includes(query) ||
        thread.last_message?.toLowerCase().includes(query) ||
        thread.participants.some((participant) => participant.display_name.toLowerCase().includes(query))
    );
  }, [threads, searchQuery]);

  const groupedThreads = useMemo(() => {
    const dms = filteredThreads.filter((thread) => thread.type === "dm");
    const queries = filteredThreads.filter((thread) => thread.type === "trip_query");
    const groups = filteredThreads.filter((thread) => thread.type === "group_chat");
    return { dms, queries, groups };
  }, [filteredThreads]);

  const formatTime = (iso?: string) => {
    if (!iso) return "";
    const date = new Date(iso);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    if (diff < 60000) return "Now";
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h`;
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };

  const getThreadAvatar = (thread: ThreadData) => {
    if (thread.type === "group_chat") return undefined;
    const other = thread.participants.find(
      (participant) => participant.username !== (user?.username || "dev_user")
    );
    return other?.avatar_url;
  };

  const getThreadName = (thread: ThreadData) => {
    if (thread.type === "group_chat" || thread.type === "trip_query") return thread.title;
    const other = thread.participants.find(
      (participant) => participant.username !== (user?.username || "dev_user")
    );
    return other?.display_name || thread.title;
  };

  const getThreadInitial = (thread: ThreadData) => {
    const name = getThreadName(thread);
    return name?.[0]?.toUpperCase() || "?";
  };

  const typeIcon = (type: ThreadData["type"]) => {
    if (type === "group_chat") return <Users className="h-3 w-3" />;
    if (type === "trip_query") return <MapPin className="h-3 w-3" />;
    return null;
  };

  const ThreadItem = ({ thread }: { thread: ThreadData }) => {
    const isActive = activeThreadId === thread.id;
    return (
      <button
        onClick={() => setActiveThreadId(thread.id)}
        className={cn(
          "flex w-full items-start gap-3 rounded-lg px-3 py-3 text-left transition-colors",
          isActive ? "bg-primary/10" : "hover:bg-muted/60"
        )}
      >
        <Avatar className="h-10 w-10 shrink-0">
          <AvatarImage src={getThreadAvatar(thread)} />
          <AvatarFallback className="bg-accent text-sm text-accent-foreground">
            {thread.type === "group_chat" ? <Users className="h-4 w-4" /> : getThreadInitial(thread)}
          </AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <span className={cn("truncate text-sm font-medium text-foreground", thread.unread_count > 0 && "font-semibold")}>
              {getThreadName(thread)}
            </span>
            <span className="shrink-0 text-xs text-muted-foreground">
              {formatTime(thread.last_sent_at)}
            </span>
          </div>
          <div className="mt-0.5 flex items-center gap-1.5">
            {typeIcon(thread.type) && <span className="text-muted-foreground">{typeIcon(thread.type)}</span>}
            <p className={cn("truncate text-xs", thread.unread_count > 0 ? "text-foreground" : "text-muted-foreground")}>
              {thread.last_message || "No messages yet"}
            </p>
          </div>
        </div>
        {thread.unread_count > 0 && (
          <Badge className="ml-1 mt-1 h-5 min-w-[20px] shrink-0 rounded-full px-1.5 text-[10px]">
            {thread.unread_count}
          </Badge>
        )}
      </button>
    );
  };

  const ThreadSection = ({ label, threads: sectionThreads }: { label: string; threads: ThreadData[] }) => {
    if (sectionThreads.length === 0) return null;
    return (
      <div className="mb-2">
        <p className="mb-1 px-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          {label}
        </p>
        {sectionThreads.map((thread) => (
          <ThreadItem key={thread.id} thread={thread} />
        ))}
      </div>
    );
  };

  const SidebarContent = () => (
    <div className="flex h-full flex-col">
      <div className="border-b px-4 py-3">
        <h2 className="text-lg font-bold text-foreground">Inbox</h2>
        <div className="relative mt-2">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search conversations..."
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            className="h-9 pl-8 text-sm"
          />
        </div>
      </div>
      <ScrollArea className="flex-1">
        <div className="px-1 py-2">
          <ThreadSection label="Direct Messages" threads={groupedThreads.dms} />
          <ThreadSection label="Trip Queries" threads={groupedThreads.queries} />
          <ThreadSection label="Group Chats" threads={groupedThreads.groups} />
          {filteredThreads.length === 0 && !loading && (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <InboxIcon className="mb-3 h-10 w-10 text-muted-foreground/40" />
              <p className="text-sm text-muted-foreground">
                {searchQuery ? "No matching conversations" : "No conversations yet"}
              </p>
              {!searchQuery && (
                <p className="mt-1 text-xs text-muted-foreground/60">
                  Start a conversation from a profile or trip page
                </p>
              )}
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );

  const ChatWindow = () => {
    if (!activeThread) {
      return (
        <div className="flex h-full flex-col items-center justify-center p-8 text-center">
          <MessageCircle className="mb-4 h-12 w-12 text-muted-foreground/30" />
          <h3 className="text-lg font-semibold text-foreground">Select a conversation</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Choose a conversation from the sidebar to start messaging
          </p>
        </div>
      );
    }

    const myUsername = user?.username || "dev_user";

    return (
      <div className="flex h-full flex-col">
        <div className="flex items-center gap-3 border-b px-4 py-3">
          <button
            onClick={() => setActiveThreadId(null)}
            className="shrink-0 rounded-md p-1 transition-colors hover:bg-muted md:hidden"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <Avatar className="h-9 w-9 shrink-0">
            <AvatarImage src={getThreadAvatar(activeThread)} />
            <AvatarFallback className="bg-accent text-sm text-accent-foreground">
              {activeThread.type === "group_chat" ? <Users className="h-4 w-4" /> : getThreadInitial(activeThread)}
            </AvatarFallback>
          </Avatar>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-foreground">
              {getThreadName(activeThread)}
            </p>
            <p className="truncate text-xs text-muted-foreground">
              {activeThread.type === "group_chat"
                ? `${activeThread.participants.length} participants`
                : activeThread.type === "trip_query"
                ? activeThread.trip_title
                : "Direct Message"}
            </p>
          </div>
          {activeThread.trip_id && (
            <Button
              variant="ghost"
              size="sm"
              className="shrink-0 text-xs"
              onClick={() => navigate(`/trips/${activeThread.trip_id}`)}
            >
              <MapPin className="mr-1 h-3 w-3" /> View Trip
            </Button>
          )}
        </div>

        <ScrollArea className="flex-1 px-4 py-4">
          <div className="space-y-3">
            {activeThread.messages.length === 0 && (
              <div className="py-12 text-center">
                <p className="text-sm text-muted-foreground">
                  No messages yet. Say hello! 👋
                </p>
              </div>
            )}
            {activeThread.messages.map((message) => {
              const isMine = message.sender_username === myUsername;
              return (
                <div
                  key={message.id}
                  className={cn("flex gap-2", isMine ? "justify-end" : "justify-start")}
                >
                  {!isMine && (
                    <Avatar className="mt-1 h-7 w-7 shrink-0">
                      <AvatarImage src={message.sender_avatar} />
                      <AvatarFallback className="bg-accent text-[10px] text-accent-foreground">
                        {message.sender_display_name?.[0]?.toUpperCase()}
                      </AvatarFallback>
                    </Avatar>
                  )}
                  <div
                    className={cn(
                      "max-w-[75%] rounded-2xl px-3.5 py-2",
                      isMine
                        ? "rounded-br-md bg-primary text-primary-foreground"
                        : "rounded-bl-md bg-muted text-foreground"
                    )}
                  >
                    {!isMine && activeThread.type === "group_chat" && (
                      <p className="mb-0.5 text-[10px] font-medium opacity-70">
                        {message.sender_display_name}
                      </p>
                    )}
                    <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.body}</p>
                    <p
                      className={cn(
                        "mt-1 text-[10px]",
                        isMine ? "text-primary-foreground/60" : "text-muted-foreground"
                      )}
                    >
                      {formatTime(message.sent_at)}
                    </p>
                  </div>
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>
        </ScrollArea>

        <div className="border-t px-4 py-3">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              handleSend();
            }}
            className="flex items-center gap-2"
          >
            <Input
              placeholder="Type a message..."
              value={messageInput}
              onChange={(event) => setMessageInput(event.target.value)}
              className="flex-1"
              autoFocus
            />
            <Button
              type="submit"
              size="icon"
              disabled={!messageInput.trim() || sending}
              className="shrink-0"
            >
              <Send className="h-4 w-4" />
            </Button>
          </form>
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="flex min-h-screen flex-col">
        <Navbar />
        <main className="flex flex-1 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </main>
      </div>
    );
  }

  const showChatOnMobile = activeThreadId !== null;

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Navbar />
      <main className="flex flex-1 overflow-hidden" style={{ height: "calc(100vh - 64px)" }}>
        <div className="hidden w-full md:flex">
          <div className="shrink-0 overflow-hidden border-r bg-card" style={{ width: sidebarWidth }}>
            <SidebarContent />
          </div>
          <div
            className={cn(
              "w-1 cursor-col-resize transition-colors hover:bg-primary/30",
              isResizing && "bg-primary/40"
            )}
            onMouseDown={(event) => {
              event.preventDefault();
              setIsResizing(true);
              resizeRef.current = { startX: event.clientX, startW: sidebarWidth };
              const onMove = (moveEvent: MouseEvent) => {
                if (!resizeRef.current) return;
                const delta = moveEvent.clientX - resizeRef.current.startX;
                const next = Math.min(MAX_SIDEBAR, Math.max(MIN_SIDEBAR, resizeRef.current.startW + delta));
                setSidebarWidth(next);
              };
              const onUp = () => {
                setIsResizing(false);
                resizeRef.current = null;
                document.removeEventListener("mousemove", onMove);
                document.removeEventListener("mouseup", onUp);
              };
              document.addEventListener("mousemove", onMove);
              document.addEventListener("mouseup", onUp);
            }}
          />
          <div className="flex-1 bg-background">
            <ChatWindow />
          </div>
        </div>

        <div className="flex w-full flex-col md:hidden">
          {showChatOnMobile ? <ChatWindow /> : <SidebarContent />}
        </div>
      </main>
      <Footer />
    </div>
  );
};

export default Inbox;
