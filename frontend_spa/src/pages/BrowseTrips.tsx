import { useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiGet } from "@/lib/api";
import type { TripData, TripListResponse } from "@/types/api";
import TripCard from "@/components/TripCard";
import { Search, MapPin, Calendar, Users, IndianRupee, Loader2 } from "lucide-react";
import BookmarkButton from "@/features/trip/components/BookmarkButton";

const TRIP_TYPES = [
  "Backpacking", "Trek", "Social", "Road Trip", "Beach", "Cultural", "Adventure", "Wellness",
];
const DEFAULT_HERO = "https://images.unsplash.com/photo-1488646953014-85cb44e25828?w=1200&q=80";

const BrowseTrips = () => {
  const [searchParams] = useSearchParams();
  const destinationFilter = searchParams.get("destination") || "";

  const [search, setSearch] = useState(destinationFilter);
  const [typeFilter, setTypeFilter] = useState("all");
  const [trips, setTrips] = useState<TripData[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const cfg = window.TAPNE_RUNTIME_CONFIG;
    if (!cfg?.api?.trips) { setLoading(false); return; }
    const params = new URLSearchParams();
    if (search) params.set("destination", search);
    if (typeFilter !== "all") params.set("trip_type", typeFilter);
    const qs = params.toString();
    const url = qs ? `${cfg.api.trips}?${qs}` : cfg.api.trips;
    setLoading(true);
    apiGet<TripListResponse>(url)
      .then((data) => setTrips(data.trips || []))
      .catch(() => setTrips([]))
      .finally(() => setLoading(false));
  }, [search, typeFilter]);

  return (
    <div className="flex min-h-screen flex-col">
      <Navbar />
      <main className="flex-1">
        <div className="mx-auto max-w-6xl px-4 py-8">
          <h1 className="mb-2 text-3xl font-bold text-foreground">Explore Trips</h1>
          <p className="mb-6 text-muted-foreground">Discover your next adventure with amazing people</p>

          <div className="mb-8 flex flex-col gap-3 sm:flex-row">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search destinations or trips..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-10"
              />
            </div>
            <Select value={typeFilter} onValueChange={setTypeFilter}>
              <SelectTrigger className="w-full sm:w-48">
                <SelectValue placeholder="Trip type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Types</SelectItem>
                {TRIP_TYPES.map((t) => (
                  <SelectItem key={t} value={t}>{t}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
            </div>
          ) : trips.length === 0 ? (
            <div className="py-20 text-center">
              <p className="text-xl font-medium text-foreground">No trips found</p>
              <p className="mt-2 text-muted-foreground">Try adjusting your search or filters.</p>
            </div>
          ) : (
            <div className="flex flex-col gap-8">
              {trips.map((trip) => {
                const spotsLeft = trip.spots_left ?? (trip.total_seats || 0);
                const heroImg = trip.banner_image_url || DEFAULT_HERO;
                const price = trip.price_per_person ?? trip.total_trip_price;
                const priceText =
                  price != null
                    ? (typeof price === "number" ? price.toLocaleString() : String(price))
                    : (trip.cost_label?.trim() || "");
                return (
                  <div key={trip.id} className="group relative">
                    <Link to={`/trips/${trip.id}`} className="block">
                      <Card className="h-[220px] overflow-hidden transition-shadow hover:shadow-lg">
                        <div className="flex h-full flex-col sm:flex-row">
                          {/* Left: Image */}
                          <div className="relative hidden h-full shrink-0 overflow-hidden bg-muted sm:block sm:w-72 md:w-80 lg:w-96">
                            <img
                              src={heroImg}
                              alt={trip.title}
                              className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                            />
                          {trip.trip_type && (
                            <Badge className="absolute left-3 top-3 bg-primary/90 text-primary-foreground">
                              {trip.trip_type}
                            </Badge>
                          )}
                        </div>
                        {/* Right: Info */}
                          <div className="flex min-w-0 flex-1 flex-col justify-between p-5 sm:p-6">
                            <div className="min-w-0">
                              <h3 className="mb-1 line-clamp-1 text-lg font-semibold text-foreground transition-colors group-hover:text-primary">
                              {trip.title}
                              </h3>
                              {trip.destination && (
                                <div className="mb-2 flex items-center gap-1 text-sm text-muted-foreground">
                                  <MapPin className="h-3.5 w-3.5 shrink-0" />
                                  <span className="line-clamp-1">{trip.destination}</span>
                                </div>
                              )}
                              <p className="mb-3 line-clamp-2 text-sm text-muted-foreground">
                                {trip.summary || trip.description}
                              </p>
                              <div className="mb-3 flex flex-wrap gap-1.5">
                                {trip.trip_vibe?.slice(0, 3).map((v) => (
                                  <Badge key={v} variant="outline" className="text-xs">{v}</Badge>
                                ))}
                              </div>
                            </div>
                            <div className="flex flex-wrap items-end justify-between gap-3">
                              <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
                                {trip.starts_at && trip.ends_at && (
                                  <span className="flex items-center gap-1">
                                    <Calendar className="h-3.5 w-3.5 shrink-0" />
                                    {new Date(trip.starts_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })} – {new Date(trip.ends_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                                  </span>
                                )}
                                {trip.spots_left != null && (
                                  <span className={`flex items-center gap-1 ${spotsLeft <= 2 ? "font-medium text-destructive" : ""}`}>
                                    <Users className="h-3.5 w-3.5 shrink-0" />
                                    {spotsLeft} spot{spotsLeft !== 1 ? "s" : ""} left
                                  </span>
                                )}
                                {trip.host_display_name && (
                                  <span className="flex items-center gap-1.5">
                                    {trip.host_display_name.split(" ")[0]}
                                  </span>
                                )}
                              </div>
                              {priceText && (
                                <span className="flex shrink-0 items-center gap-1 text-lg font-semibold text-foreground">
                                  {price != null && <IndianRupee className="h-4 w-4" />}
                                  {priceText}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </Card>
                    </Link>
                    <BookmarkButton
                      tripId={trip.id}
                      size="sm"
                      className="absolute right-3 top-3 z-10 opacity-0 transition-opacity duration-200 group-hover:opacity-100 md:opacity-0 max-md:opacity-100"
                    />
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </main>
      <Footer />
    </div>
  );
};

export default BrowseTrips;
