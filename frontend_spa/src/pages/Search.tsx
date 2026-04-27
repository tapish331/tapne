import { useState, useEffect } from "react";
import { useSearchParams, Link, useNavigate } from "react-router-dom";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { apiGet } from "@/lib/api";
import type { TripData, BlogData } from "@/types/api";
import TripCard from "@/components/TripCard";
import { useAuth } from "@/contexts/AuthContext";
import { Search as SearchIcon, Loader2, Plus } from "lucide-react";

type SearchTab = "trips" | "stories" | "users";

function getActiveTab(searchParams: URLSearchParams): SearchTab {
  const tab = searchParams.get("tab");
  if (tab === "stories" || tab === "users") {
    return tab;
  }
  return "trips";
}

const SearchPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = getActiveTab(searchParams);
  const navigate = useNavigate();
  const { isAuthenticated, requireAuth } = useAuth();
  const initialQ = searchParams.get("q") || "";
  const destination = searchParams.get("destination") || "";
  const [query, setQuery] = useState(initialQ);
  const [submitted, setSubmitted] = useState(initialQ);
  const [trips, setTrips] = useState<TripData[]>([]);
  const [stories, setStories] = useState<BlogData[]>([]);
  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [sort, setSort] = useState<"recent" | "popular">("recent");

  const hasCriteria = Boolean(submitted.trim() || destination.trim());

  useEffect(() => {
    const cfg = window.TAPNE_RUNTIME_CONFIG;
    if (!cfg?.api?.trips || !cfg?.api?.blogs || !cfg?.api?.users_search) {
      return;
    }

    const shouldLoadTrips = activeTab === "trips" || hasCriteria;
    const shouldLoadStories = activeTab === "stories" || hasCriteria;
    const shouldLoadUsers = hasCriteria;

    if (!shouldLoadTrips) setTrips([]);
    if (!shouldLoadStories) setStories([]);
    if (!shouldLoadUsers) setUsers([]);

    const tasks: Promise<void>[] = [];
    const q = encodeURIComponent(submitted.trim());
    const dest = encodeURIComponent(destination.trim());

    if (shouldLoadTrips) {
      const tripsUrl = `${cfg.api.trips}?q=${q}&sort=${sort}${dest ? `&destination=${dest}` : ""}`;
      tasks.push(
        apiGet<{ trips: TripData[] }>(tripsUrl).then((data) => {
          setTrips(data.trips || []);
        })
      );
    }

    if (shouldLoadStories) {
      const storiesUrl = submitted.trim() ? `${cfg.api.blogs}?q=${q}` : cfg.api.blogs;
      tasks.push(
        apiGet<{ blogs: BlogData[] }>(storiesUrl).then((data) => {
          setStories(data.blogs || []);
        })
      );
    }

    if (shouldLoadUsers) {
      tasks.push(
        apiGet<{ users: any[] }>(`${cfg.api.users_search}?q=${q}`).then((data) => {
          setUsers(data.users || []);
        })
      );
    }

    if (tasks.length === 0) {
      setLoading(false);
      return;
    }

    setLoading(true);
    Promise.allSettled(tasks).finally(() => setLoading(false));
  }, [activeTab, submitted, sort, destination, hasCriteria]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitted(query);
    const next = new URLSearchParams(searchParams);
    if (query.trim()) next.set("q", query);
    else next.delete("q");
    if (destination) next.set("destination", destination);
    else next.delete("destination");
    if (activeTab === "trips") next.delete("tab");
    else next.set("tab", activeTab);
    setSearchParams(next);
  };

  const handleTabChange = (value: string) => {
    const nextTab = value as SearchTab;
    const next = new URLSearchParams(searchParams);
    if (nextTab === "trips") next.delete("tab");
    else next.set("tab", nextTab);
    setSearchParams(next);
  };

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Navbar />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        <h1 className="mb-6 text-2xl font-bold text-foreground">Search</h1>
        <form onSubmit={handleSubmit} className="mb-6 flex gap-2">
          <div className="relative flex-1">
            <SearchIcon className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search trips, stories, people…" className="pl-9" />
          </div>
          <Button type="submit">Search</Button>
        </form>

        {activeTab === "stories" && (
          <div className="mb-6 flex justify-end">
            <Button
              size="sm"
              onClick={() => {
                if (isAuthenticated) navigate("/stories/new");
                else requireAuth(() => navigate("/stories/new"));
              }}
            >
              <Plus className="mr-1 h-4 w-4" /> Write
            </Button>
          </div>
        )}

        <Tabs value={activeTab} onValueChange={handleTabChange}>
          <div className="flex items-center justify-between gap-4">
            <TabsList>
              <TabsTrigger value="trips">Trips ({trips.length})</TabsTrigger>
              <TabsTrigger value="stories">Stories ({stories.length})</TabsTrigger>
              <TabsTrigger value="users">People ({users.length})</TabsTrigger>
            </TabsList>
            <select className="rounded-md border bg-background px-3 py-1.5 text-sm" value={sort} onChange={e => setSort(e.target.value as "recent" | "popular")}>
              <option value="recent">Most recent</option>
              <option value="popular">Most popular</option>
            </select>
          </div>

          {loading && <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>}

          <TabsContent value="trips" className="mt-6">
            {!loading && trips.length === 0 ? <p className="py-8 text-center text-muted-foreground">No trips found.</p> : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {trips.map(t => <TripCard key={t.id} trip={t} />)}
              </div>
            )}
          </TabsContent>
          <TabsContent value="stories" className="mt-6">
            {!loading && stories.length === 0 ? <p className="py-8 text-center text-muted-foreground">No stories found.</p> : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {stories.map(s => (
                  <Link key={s.slug} to={`/stories/${s.slug}`}>
                    <Card className="overflow-hidden transition-shadow hover:shadow-lg">
                      {s.cover_image_url && <img src={s.cover_image_url} alt={s.title} className="aspect-[16/10] w-full object-cover" />}
                      <CardContent className="p-4">
                        <h3 className="line-clamp-2 text-sm font-semibold text-foreground">{s.title}</h3>
                        <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{s.short_description || s.excerpt}</p>
                      </CardContent>
                    </Card>
                  </Link>
                ))}
              </div>
            )}
          </TabsContent>
          <TabsContent value="users" className="mt-6">
            {!hasCriteria ? <p className="py-8 text-center text-muted-foreground">Enter a name or username to search people.</p> : (
              !loading && users.length === 0 ? <p className="py-8 text-center text-muted-foreground">No people found.</p> : (
                <div className="grid gap-3 sm:grid-cols-2">
                  {users.map((u: any) => (
                    <Link key={u.username} to={`/users/${u.username}`}>
                      <Card className="transition-shadow hover:shadow-md">
                        <CardContent className="flex items-center gap-3 p-4">
                          <Avatar className="h-12 w-12">
                            <AvatarFallback>{(u.display_name || u.username || "?")[0]?.toUpperCase()}</AvatarFallback>
                          </Avatar>
                          <div className="min-w-0 flex-1">
                            <div className="truncate font-medium text-foreground">{u.display_name || u.username}</div>
                            {u.location && <div className="truncate text-xs text-muted-foreground">{u.location}</div>}
                          </div>
                        </CardContent>
                      </Card>
                    </Link>
                  ))}
                </div>
              )
            )}
          </TabsContent>
        </Tabs>
      </main>
      <Footer />
    </div>
  );
};

export default SearchPage;
