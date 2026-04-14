/**
 * Navbar override — replaces the hardcoded mock notifications in
 * lovable/src/components/Navbar.tsx with real activity data from
 * /frontend-api/activity/ and adds click-through navigation per
 * notification type.
 *
 * Everything else (links, dark mode, mobile menu, user dropdown) is
 * preserved verbatim from the Lovable source.
 */
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Menu, X, Bell, Sun, Moon, Inbox, Bookmark, User, LogOut, MapPin as MapPinIcon } from "lucide-react";
import { useState, useEffect, useRef } from "react";
import CreateTripModal from "@/components/CreateTripModal";
import { apiGet } from "@/lib/api";

interface ActivityItem {
  id: string;
  group: string;
  actor_username: string;
  action: string;
  target_label: string;
  target_url: string;
  actor_url: string;
  occurred_at: string;
  preview: string;
}

function _notifNavUrl(item: ActivityItem): string {
  // Route to the right page based on notification type
  if (item.group === "reviews") {
    // Someone reviewed your trip — link to the trip's reviews section
    const url = item.target_url.replace(/\/$/, "");
    return `${url}#reviews`;
  }
  if (item.group === "enrollment") {
    // Enrollment decision — link to the trip page
    return item.target_url;
  }
  if (item.group === "bookmarks") {
    // Someone bookmarked your trip
    return item.target_url;
  }
  if (item.group === "follows") {
    // Someone started following you — open their profile
    return item.actor_url;
  }
  if (item.group === "comments" || item.group === "replies") {
    return item.target_url;
  }
  return item.target_url || "/";
}

function _timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function _groupIcon(group: string): string {
  const icons: Record<string, string> = {
    follows: "👤",
    enrollment: "✅",
    reviews: "⭐",
    bookmarks: "🔖",
    comments: "💬",
    replies: "↩️",
  };
  return icons[group] || "🔔";
}

const Navbar = () => {
  const { user, isAuthenticated, logout, requireAuth } = useAuth();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [darkMode, setDarkMode] = useState(false);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [notifications, setNotifications] = useState<ActivityItem[]>([]);
  const [desktopNotifOpen, setDesktopNotifOpen] = useState(false);
  const [mobileNotifOpen, setMobileNotifOpen] = useState(false);
  const [seenIds, setSeenIds] = useState<Set<string>>(() => {
    try {
      const stored = localStorage.getItem("tapne_seen_notifs");
      return stored ? new Set(JSON.parse(stored)) : new Set();
    } catch {
      return new Set();
    }
  });
  const fetchedRef = useRef(false);

  useEffect(() => {
    if (!isAuthenticated) {
      fetchedRef.current = false;
      setNotifications([]);
      return;
    }
    if (fetchedRef.current) return;
    fetchedRef.current = true;
    const cfg = window.TAPNE_RUNTIME_CONFIG;
    if (!cfg?.api?.activity) return;
    apiGet<{ items: ActivityItem[] }>(cfg.api.activity)
      .then((data) => setNotifications((data.items || []).slice(0, 10)))
      .catch(() => {});
  }, [isAuthenticated]);

  const toggleDarkMode = () => {
    setDarkMode(!darkMode);
    document.documentElement.classList.toggle("dark");
  };

  const handleLogout = () => {
    logout();
    navigate("/");
  };

  const unreadCount = notifications.filter((n) => !seenIds.has(n.id)).length;

  const markAllSeen = () => {
    const allIds = new Set(notifications.map((n) => n.id));
    setSeenIds(allIds);
    localStorage.setItem("tapne_seen_notifs", JSON.stringify([...allIds]));
  };

  const handleNotifClick = (item: ActivityItem) => {
    const allIds = new Set([...seenIds, item.id]);
    setSeenIds(allIds);
    localStorage.setItem("tapne_seen_notifs", JSON.stringify([...allIds]));
    const url = _notifNavUrl(item);
    setDesktopNotifOpen(false);
    setMobileNotifOpen(false);
    navigate(url);
  };

  const NotifList = ({ items }: { items: ActivityItem[] }) => (
    <>
      {items.length === 0 ? (
        <div className="px-3 py-4 text-sm text-muted-foreground text-center">No notifications yet</div>
      ) : (
        items.map((n) => (
          <DropdownMenuItem
            key={n.id}
            className="flex items-start gap-3 px-3 py-2.5 cursor-pointer"
            onClick={() => handleNotifClick(n)}
          >
            <span className="text-lg">{_groupIcon(n.group)}</span>
            <div className="flex-1 min-w-0">
              <p className={`text-sm ${!seenIds.has(n.id) ? "font-medium text-foreground" : "text-muted-foreground"}`}>
                <span className="font-semibold">@{n.actor_username}</span>{" "}
                {n.action}
                {n.target_label ? ` "${n.target_label}"` : ""}
              </p>
              <p className="text-xs text-muted-foreground">{_timeAgo(n.occurred_at)}</p>
            </div>
            {!seenIds.has(n.id) && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary" />}
          </DropdownMenuItem>
        ))
      )}
    </>
  );

  return (
    <>
      <nav className="sticky top-0 z-50 border-b bg-card/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
          <Link to="/" className="text-xl font-bold tracking-tight text-primary">
            Tapne
          </Link>

          {/* Desktop */}
          <div className="hidden items-center gap-1 md:flex">
            <Button variant="ghost" size="sm" asChild>
              <Link to="/trips">Trips</Link>
            </Button>
            <Button variant="ghost" size="sm" asChild>
              <Link to="/experiences">Experiences</Link>
            </Button>

            <Button variant="ghost" size="icon" onClick={toggleDarkMode} className="h-9 w-9">
              {darkMode ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>

            <DropdownMenu
              open={desktopNotifOpen}
              onOpenChange={(open) => {
                setDesktopNotifOpen(open);
                if (open) {
                  setMobileNotifOpen(false);
                  markAllSeen();
                }
              }}
            >
              <DropdownMenuTrigger asChild>
                <button className="relative flex h-9 w-9 items-center justify-center rounded-md transition-colors hover:bg-muted">
                  <Bell className="h-4 w-4" />
                  {unreadCount > 0 && (
                    <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-destructive" />
                  )}
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-80">
                <div className="px-3 py-2 text-sm font-semibold text-foreground">Notifications</div>
                <DropdownMenuSeparator />
                <NotifList items={notifications} />
              </DropdownMenuContent>
            </DropdownMenu>

            {isAuthenticated ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button className="ml-1 rounded-full ring-2 ring-primary/20 transition hover:ring-primary/50">
                    <Avatar className="h-9 w-9">
                      <AvatarImage src={user?.avatar} />
                      <AvatarFallback>{user?.name?.[0]}</AvatarFallback>
                    </Avatar>
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48">
                  <DropdownMenuItem onClick={() => navigate("/profile")}>
                    <User className="mr-2 h-4 w-4" /> My Profile
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/my-trips")}>
                    <MapPinIcon className="mr-2 h-4 w-4" /> My Trips
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/inbox")}>
                    <Inbox className="mr-2 h-4 w-4" /> Inbox
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/bookmarks")}>
                    <Bookmark className="mr-2 h-4 w-4" /> Bookmarks
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={handleLogout}>
                    <LogOut className="mr-2 h-4 w-4" /> Log Out
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <Button size="sm" className="ml-1" onClick={() => requireAuth()}>
                Login
              </Button>
            )}
          </div>

          {/* Mobile toggle */}
          <div className="flex items-center gap-1 md:hidden">
            <Button variant="ghost" size="icon" onClick={toggleDarkMode} className="h-9 w-9">
              {darkMode ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>
            <DropdownMenu
              open={mobileNotifOpen}
              onOpenChange={(open) => {
                setMobileNotifOpen(open);
                if (open) {
                  setDesktopNotifOpen(false);
                  markAllSeen();
                }
              }}
            >
              <DropdownMenuTrigger asChild>
                <button className="relative flex h-9 w-9 items-center justify-center rounded-md">
                  <Bell className="h-4 w-4" />
                  {unreadCount > 0 && <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-destructive" />}
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-72">
                <NotifList items={notifications} />
              </DropdownMenuContent>
            </DropdownMenu>
            <button onClick={() => setMobileOpen(!mobileOpen)}>
              {mobileOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
            </button>
          </div>
        </div>

        {/* Mobile menu */}
        {mobileOpen && (
          <div className="flex flex-col gap-1 border-t bg-card px-4 pb-4 pt-2 md:hidden">
            <Button variant="ghost" className="justify-start" asChild onClick={() => setMobileOpen(false)}>
              <Link to="/trips">Trips</Link>
            </Button>
            <Button variant="ghost" className="justify-start" asChild onClick={() => setMobileOpen(false)}>
              <Link to="/experiences">Experiences</Link>
            </Button>
            {isAuthenticated ? (
              <>
                <Button variant="ghost" className="justify-start" onClick={() => { navigate("/profile"); setMobileOpen(false); }}>
                  <User className="mr-2 h-4 w-4" /> Profile
                </Button>
                <Button variant="ghost" className="justify-start" onClick={() => { navigate("/my-trips"); setMobileOpen(false); }}>
                  <MapPinIcon className="mr-2 h-4 w-4" /> My Trips
                </Button>
                <Button variant="ghost" className="justify-start" onClick={() => { navigate("/inbox"); setMobileOpen(false); }}>
                  <Inbox className="mr-2 h-4 w-4" /> Inbox
                </Button>
                <Button variant="ghost" className="justify-start" onClick={() => { navigate("/bookmarks"); setMobileOpen(false); }}>
                  <Bookmark className="mr-2 h-4 w-4" /> Bookmarks
                </Button>
                <Button variant="ghost" className="justify-start text-destructive" onClick={() => { handleLogout(); setMobileOpen(false); }}>
                  <LogOut className="mr-2 h-4 w-4" /> Log Out
                </Button>
              </>
            ) : (
              <Button size="sm" className="mt-2" onClick={() => { requireAuth(); setMobileOpen(false); }}>
                Login
              </Button>
            )}
          </div>
        )}
      </nav>

      <CreateTripModal open={createModalOpen} onOpenChange={setCreateModalOpen} />
    </>
  );
};

export default Navbar;
