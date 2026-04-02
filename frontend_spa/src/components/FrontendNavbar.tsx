import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Bell,
  Bookmark,
  Inbox,
  LogOut,
  Menu,
  Moon,
  Settings,
  Sun,
  User,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { apiGet, apiUrl } from "@frontend/lib/api";
import { useAuth } from "@frontend/context/AuthContext";

type ActivityItem = {
  id: string;
  title: string;
  summary: string;
  url?: string;
};

export default function FrontendNavbar() {
  const { user, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [darkMode, setDarkMode] = useState(false);
  const [activityItems, setActivityItems] = useState<ActivityItem[]>([]);

  useEffect(() => {
    if (!isAuthenticated) {
      setActivityItems([]);
      return;
    }
    apiGet<{ items?: Array<Record<string, unknown>> }>(apiUrl("activity"))
      .then((payload) => {
        const items = Array.isArray(payload.items)
          ? payload.items.slice(0, 3).map((item, index) => ({
              id: String(item.id ?? index),
              title: String(item.title ?? item.actor_label ?? "Update"),
              summary: String(item.summary ?? item.description ?? ""),
              url: typeof item.target_url === "string" ? item.target_url : undefined,
            }))
          : [];
        setActivityItems(items);
      })
      .catch(() => {
        setActivityItems([]);
      });
  }, [isAuthenticated]);

  const unreadCount = useMemo(() => activityItems.length, [activityItems]);

  function toggleDarkMode() {
    const next = !darkMode;
    setDarkMode(next);
    document.documentElement.classList.toggle("dark", next);
  }

  async function handleLogout() {
    await logout();
    navigate("/");
  }

  const profileInitial = user?.display_name?.[0] || user?.username?.[0] || "T";

  return (
    <nav className="sticky top-0 z-50 border-b bg-card/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
        <Link to="/" className="text-xl font-bold tracking-tight text-primary">
          Tapne
        </Link>

        <div className="hidden items-center gap-1 md:flex">
          <Button variant="ghost" size="sm" asChild>
            <Link to="/trips">Trips</Link>
          </Button>
          <Button variant="ghost" size="sm" asChild>
            <Link to="/blogs">Blogs</Link>
          </Button>
          {isAuthenticated ? (
            <Button variant="ghost" size="sm" asChild>
              <Link to="/my-trips">My Trips</Link>
            </Button>
          ) : null}

          <Button variant="ghost" size="icon" className="h-9 w-9" onClick={toggleDarkMode}>
            {darkMode ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="relative flex h-9 w-9 items-center justify-center rounded-md transition-colors hover:bg-muted">
                <Bell className="h-4 w-4" />
                {unreadCount > 0 ? <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-destructive" /> : null}
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-80">
              <div className="px-3 py-2 text-sm font-semibold text-foreground">Activity</div>
              <DropdownMenuSeparator />
              {activityItems.length === 0 ? (
                <div className="px-3 py-4 text-sm text-muted-foreground">No recent updates.</div>
              ) : (
                activityItems.map((item) => (
                  <DropdownMenuItem
                    key={item.id}
                    className="block px-3 py-2.5"
                    onClick={() => {
                      if (item.url) {
                        window.location.assign(item.url);
                      } else {
                        window.location.assign("/activity/");
                      }
                    }}
                  >
                    <div className="text-sm font-medium text-foreground">{item.title}</div>
                    {item.summary ? <div className="mt-1 text-xs text-muted-foreground">{item.summary}</div> : null}
                  </DropdownMenuItem>
                ))
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => window.location.assign("/activity/")}>
                View all activity
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          {isAuthenticated && user ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="ml-1 rounded-full ring-2 ring-primary/20 transition hover:ring-primary/50">
                  <Avatar className="h-9 w-9">
                    <AvatarFallback>{profileInitial}</AvatarFallback>
                  </Avatar>
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-52">
                <DropdownMenuItem onClick={() => navigate("/profile")}>
                  <User className="mr-2 h-4 w-4" /> My Profile
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => navigate("/create-trip")}>
                  Create Trip
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => window.location.assign("/interactions/dm/")}>
                  <Inbox className="mr-2 h-4 w-4" /> Inbox
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => window.location.assign("/social/bookmarks/")}>
                  <Bookmark className="mr-2 h-4 w-4" /> Bookmarks
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => window.location.assign("/settings/")}>
                  <Settings className="mr-2 h-4 w-4" /> Settings
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => void handleLogout()}>
                  <LogOut className="mr-2 h-4 w-4" /> Log Out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            <Button size="sm" asChild className="ml-1">
              <Link to="/login">Login</Link>
            </Button>
          )}
        </div>

        <div className="flex items-center gap-1 md:hidden">
          <Button variant="ghost" size="icon" className="h-9 w-9" onClick={toggleDarkMode}>
            {darkMode ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
          <button type="button" onClick={() => setMobileOpen((current) => !current)}>
            {mobileOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
          </button>
        </div>
      </div>

      {mobileOpen ? (
        <div className="flex flex-col gap-1 border-t bg-card px-4 pb-4 pt-2 md:hidden">
          <Button variant="ghost" className="justify-start" asChild>
            <Link to="/trips" onClick={() => setMobileOpen(false)}>
              Trips
            </Link>
          </Button>
          <Button variant="ghost" className="justify-start" asChild>
            <Link to="/blogs" onClick={() => setMobileOpen(false)}>
              Blogs
            </Link>
          </Button>
          {isAuthenticated ? (
            <>
              <Button variant="ghost" className="justify-start" asChild>
                <Link to="/create-trip" onClick={() => setMobileOpen(false)}>
                  Create Trip
                </Link>
              </Button>
              <Button variant="ghost" className="justify-start" asChild>
                <Link to="/my-trips" onClick={() => setMobileOpen(false)}>
                  My Trips
                </Link>
              </Button>
              <Button variant="ghost" className="justify-start" asChild>
                <Link to="/profile" onClick={() => setMobileOpen(false)}>
                  Profile
                </Link>
              </Button>
              <Button variant="ghost" className="justify-start" onClick={() => window.location.assign("/interactions/dm/")}>
                Inbox
              </Button>
              <Button variant="ghost" className="justify-start" onClick={() => window.location.assign("/social/bookmarks/")}>
                Bookmarks
              </Button>
              <Button variant="ghost" className="justify-start" onClick={() => window.location.assign("/settings/")}>
                Settings
              </Button>
              <Button variant="ghost" className="justify-start text-destructive" onClick={() => void handleLogout()}>
                Log Out
              </Button>
            </>
          ) : (
            <Button className="justify-start" asChild>
              <Link to="/login" onClick={() => setMobileOpen(false)}>
                Login
              </Link>
            </Button>
          )}
          {unreadCount > 0 ? (
            <div className="pt-2 text-xs text-muted-foreground">
              <Badge variant="secondary" className="mr-2">
                {unreadCount}
              </Badge>
              recent update{unreadCount === 1 ? "" : "s"}
            </div>
          ) : null}
        </div>
      ) : null}
    </nav>
  );
}
