import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Calendar, MapPin, Search, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import Footer from "@/components/Footer";
import FrontendNavbar from "@frontend/components/FrontendNavbar";
import { EmptyState, ErrorState, LoadingState } from "@frontend/components/PageState";
import TripCard from "@frontend/components/TripCard";
import { FrontendBlog, FrontendProfile, FrontendTrip, apiGet, apiUrl } from "@frontend/lib/api";
import { formatDateLabel, slugify } from "@frontend/lib/format";

type HomePayload = {
  trips: FrontendTrip[];
  profiles: FrontendProfile[];
  blogs: FrontendBlog[];
};

export default function HomePage() {
  const navigate = useNavigate();
  const [payload, setPayload] = useState<HomePayload | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchFocused, setSearchFocused] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    apiGet<HomePayload>(apiUrl("home"))
      .then((nextPayload) => setPayload(nextPayload))
      .catch((err: Error) => setError(err.message));
  }, []);

  const destinations = useMemo(() => {
    if (!payload) {
      return [];
    }
    const seen = new Map<string, FrontendTrip>();
    payload.trips.forEach((trip) => {
      const name = (trip.destination || "Unknown").split(",")[0]?.trim() || "Unknown";
      const key = slugify(name);
      if (!seen.has(key)) {
        seen.set(key, trip);
      }
    });
    return Array.from(seen.entries()).map(([key, trip]) => ({
      slug: key,
      name: (trip.destination || "Unknown").split(",")[0]?.trim() || "Unknown",
      imageUrl: trip.banner_image_url || "/placeholder.svg",
    }));
  }, [payload]);

  const searchResults = useMemo(() => {
    if (!payload || !searchQuery.trim()) {
      return { trips: [], profiles: [] };
    }
    const normalized = searchQuery.trim().toLowerCase();
    return {
      trips: payload.trips
        .filter((trip) =>
          [trip.title, trip.destination, trip.summary].some((value) =>
            String(value || "").toLowerCase().includes(normalized),
          ),
        )
        .slice(0, 5),
      profiles: payload.profiles
        .filter((profile) =>
          [profile.display_name, profile.username, profile.location, profile.bio].some((value) =>
            String(value || "").toLowerCase().includes(normalized),
          ),
        )
        .slice(0, 3),
    };
  }, [payload, searchQuery]);

  if (error) {
    return (
      <div className="flex min-h-screen flex-col">
        <FrontendNavbar />
        <main className="mx-auto flex w-full max-w-6xl flex-1 px-4 py-10">
          <ErrorState title="Home feed unavailable" body={error} />
        </main>
        <Footer />
      </div>
    );
  }

  if (!payload) {
    return (
      <div className="flex min-h-screen flex-col">
        <FrontendNavbar />
        <main className="mx-auto flex w-full max-w-6xl flex-1 px-4 py-10">
          <LoadingState label="Loading trips and stories..." />
        </main>
        <Footer />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      <FrontendNavbar />
      <main className="flex-1">
        <section className="relative overflow-hidden bg-gradient-to-br from-primary/10 via-accent/30 to-background px-4 py-20 md:py-28">
          <div className="mx-auto max-w-3xl text-center">
            <h1 className="mb-4 text-4xl font-bold leading-tight tracking-tight text-foreground md:text-6xl">
              Find your kind of people. <span className="text-primary">Then travel.</span>
            </h1>
            <p className="mx-auto mb-8 max-w-2xl text-lg text-muted-foreground md:text-xl">
              Join community-led trips with like-minded travelers. Discover real itineraries, real hosts, and real stories on Tapne.
            </p>

            <div className="relative mx-auto max-w-xl">
              <Search className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-muted-foreground" />
              <input
                className="h-14 w-full rounded-full border-2 border-primary/20 bg-card pl-12 pr-4 text-base shadow-lg transition-all focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                placeholder="Search trips or travelers..."
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                onFocus={() => setSearchFocused(true)}
                onBlur={() => setTimeout(() => setSearchFocused(false), 150)}
              />

              {searchFocused && searchQuery.trim() ? (
                <div className="absolute left-0 right-0 top-full z-50 mt-2 rounded-xl border bg-card p-2 shadow-xl">
                  {searchResults.trips.length === 0 && searchResults.profiles.length === 0 ? (
                    <p className="px-3 py-4 text-center text-sm text-muted-foreground">No results found</p>
                  ) : null}
                  {searchResults.trips.length > 0 ? (
                    <div>
                      <p className="px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Trips</p>
                      {searchResults.trips.map((trip) => (
                        <button
                          key={trip.id}
                          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition-colors hover:bg-muted"
                          onMouseDown={() => navigate(`/trips/${trip.id}`)}
                        >
                          <img src={trip.banner_image_url || "/placeholder.svg"} alt="" className="h-10 w-10 rounded-lg object-cover" />
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-medium text-foreground">{trip.title}</p>
                            <p className="flex items-center gap-1 text-xs text-muted-foreground">
                              <MapPin className="h-3 w-3" />
                              {trip.destination || "Destination announced soon"}
                            </p>
                          </div>
                        </button>
                      ))}
                    </div>
                  ) : null}
                  {searchResults.profiles.length > 0 ? (
                    <div className="mt-1">
                      <p className="px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Travelers</p>
                      {searchResults.profiles.map((profile) => (
                        <button
                          key={profile.username}
                          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition-colors hover:bg-muted"
                          onMouseDown={() => {
                            if (profile.url) {
                              window.location.assign(profile.url);
                            } else {
                              navigate("/profile");
                            }
                          }}
                        >
                          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10 text-primary">
                            {String(profile.display_name || profile.username || "T").slice(0, 1).toUpperCase()}
                          </div>
                          <div>
                            <p className="text-sm font-medium text-foreground">{profile.display_name || profile.username}</p>
                            <p className="text-xs text-muted-foreground">{profile.location || profile.bio || "Tapne member"}</p>
                          </div>
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-4 py-14">
          <div className="mb-6 flex items-end justify-between">
            <div>
              <h2 className="text-2xl font-bold text-foreground md:text-3xl">Explore Trips</h2>
              <p className="mt-1 text-muted-foreground">Discover live trips created by real hosts.</p>
            </div>
            <Button variant="ghost" asChild className="hidden sm:flex">
              <Link to="/trips">
                View all <ArrowRight className="ml-1 h-4 w-4" />
              </Link>
            </Button>
          </div>
          {payload.trips.length === 0 ? (
            <EmptyState title="No trips published yet" body="Publish a trip to make it appear on the Tapne home feed." />
          ) : (
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {payload.trips.slice(0, 6).map((trip) => (
                <TripCard key={trip.id} trip={trip} />
              ))}
            </div>
          )}
        </section>

        <section className="bg-muted/30 py-14">
          <div className="mx-auto max-w-6xl px-4">
            <h2 className="mb-2 text-2xl font-bold text-foreground md:text-3xl">Explore Destinations</h2>
            <p className="mb-6 text-muted-foreground">Find live trips by destination.</p>
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              {destinations.map((destination) => (
                <Link key={destination.slug} to={`/trips?destination=${destination.name}`} className="group">
                  <Card className="overflow-hidden transition-shadow hover:shadow-lg">
                    <div className="relative aspect-[4/3] overflow-hidden">
                      <img
                        src={destination.imageUrl}
                        alt={destination.name}
                        className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                      />
                      <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
                      <div className="absolute inset-x-0 bottom-0 p-4">
                        <div className="flex items-center gap-1.5 text-white">
                          <MapPin className="h-4 w-4" />
                          <span className="text-lg font-semibold">{destination.name}</span>
                        </div>
                      </div>
                    </div>
                  </Card>
                </Link>
              ))}
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-4 py-14">
          <div className="mb-6 flex items-end justify-between">
            <div>
              <h2 className="text-2xl font-bold text-foreground md:text-3xl">From the Community</h2>
              <p className="mt-1 text-muted-foreground">Stories, tips, and experiences from real travelers.</p>
            </div>
            <Button variant="ghost" asChild className="hidden sm:flex">
              <Link to="/blogs">
                View all <ArrowRight className="ml-1 h-4 w-4" />
              </Link>
            </Button>
          </div>
          {payload.blogs.length === 0 ? (
            <EmptyState title="No stories published yet" body="Publish a blog post to make it appear on the Tapne home feed." />
          ) : (
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {payload.blogs.slice(0, 6).map((blog) => (
                <Link key={blog.slug} to={`/blogs/${blog.slug}`}>
                  <Card className="group overflow-hidden transition-shadow hover:shadow-lg">
                    <div className="relative aspect-[16/10] overflow-hidden">
                      <img
                        src={blog.cover_image_url || "/placeholder.svg"}
                        alt={blog.title}
                        className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                      />
                    </div>
                    <CardContent className="p-4">
                      <h3 className="line-clamp-2 text-base font-semibold leading-tight text-foreground transition-colors group-hover:text-primary">
                        {blog.title}
                      </h3>
                      <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
                        <div className="flex items-center gap-1">
                          <User className="h-3 w-3" />
                          {blog.author_display_name || blog.author_username || "Tapne"}
                        </div>
                        <div className="flex items-center gap-1">
                          <Calendar className="h-3 w-3" />
                          {blog.published_label || formatDateLabel(new Date().toISOString())}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              ))}
            </div>
          )}
        </section>
      </main>
      <Footer />
    </div>
  );
}
