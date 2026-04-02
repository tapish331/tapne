import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Search } from "lucide-react";
import Footer from "@/components/Footer";
import { Input } from "@/components/ui/input";
import FrontendNavbar from "@frontend/components/FrontendNavbar";
import { EmptyState, ErrorState, LoadingState } from "@frontend/components/PageState";
import TripCard from "@frontend/components/TripCard";
import { FrontendTrip, apiGet, apiUrl } from "@frontend/lib/api";

type TripListPayload = {
  trips: FrontendTrip[];
};

export default function TripsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [payload, setPayload] = useState<TripListPayload | null>(null);
  const [search, setSearch] = useState(searchParams.get("destination") || "");
  const [tripType, setTripType] = useState(searchParams.get("trip_type") || "all");
  const [error, setError] = useState("");

  useEffect(() => {
    const url = new URL(apiUrl("trips"), window.location.origin);
    if (search.trim()) {
      url.searchParams.set("destination", search.trim());
    }
    if (tripType !== "all") {
      url.searchParams.set("trip_type", tripType);
    }

    const timeout = window.setTimeout(() => {
      apiGet<TripListPayload>(url.pathname + url.search)
        .then((nextPayload) => {
          setPayload(nextPayload);
          setError("");
          const nextParams = new URLSearchParams();
          if (search.trim()) {
            nextParams.set("destination", search.trim());
          }
          if (tripType !== "all") {
            nextParams.set("trip_type", tripType);
          }
          setSearchParams(nextParams, { replace: true });
        })
        .catch((err: Error) => setError(err.message));
    }, 150);

    return () => window.clearTimeout(timeout);
  }, [search, tripType, setSearchParams]);

  const tripTypes = useMemo(() => {
    if (!payload) {
      return [];
    }
    return Array.from(
      new Set(
        payload.trips
          .map((trip) => String(trip.trip_type || "").trim())
          .filter(Boolean),
      ),
    );
  }, [payload]);

  return (
    <div className="flex min-h-screen flex-col">
      <FrontendNavbar />
      <main className="flex-1">
        <div className="mx-auto max-w-6xl px-4 py-8">
          <h1 className="mb-2 text-3xl font-bold text-foreground">Explore Trips</h1>
          <p className="mb-6 text-muted-foreground">Discover your next adventure with live Tapne trip data.</p>

          <div className="mb-8 flex flex-col gap-3 sm:flex-row">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search destinations or trips..."
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                className="pl-10"
              />
            </div>
            <select
              className="h-10 rounded-md border bg-background px-3 text-sm"
              value={tripType}
              onChange={(event) => setTripType(event.target.value)}
            >
              <option value="all">All trip types</option>
              {tripTypes.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>

          {error ? <ErrorState title="Trip catalog unavailable" body={error} /> : null}
          {!payload && !error ? <LoadingState label="Loading live trips..." /> : null}
          {payload && payload.trips.length === 0 ? (
            <EmptyState title="No trips found" body="Try adjusting your search or publish a trip to populate the catalog." />
          ) : null}
          {payload && payload.trips.length > 0 ? (
            <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {payload.trips.map((trip) => (
                <TripCard key={trip.id} trip={trip} />
              ))}
            </div>
          ) : null}
        </div>
      </main>
      <Footer />
    </div>
  );
}
