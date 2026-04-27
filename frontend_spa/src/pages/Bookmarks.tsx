import { useEffect, useState } from "react";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import TripCard from "@/components/TripCard";
import { apiGet } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import type { TripData } from "@/types/api";
import { Bookmark, Loader2 } from "lucide-react";

const Bookmarks = () => {
  const { isAuthenticated, requireAuth } = useAuth();
  const [trips, setTrips] = useState<TripData[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isAuthenticated) {
      requireAuth();
      setLoading(false);
      return;
    }

    const cfg = window.TAPNE_RUNTIME_CONFIG;
    setLoading(true);
    apiGet<{ trips: TripData[] }>(cfg.api.bookmarks)
      .then((data) => setTrips(data.trips || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [isAuthenticated, requireAuth]);

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Navbar />
      <main className="flex-1">
        <div className="mx-auto max-w-6xl px-4 py-8">
          <div className="mb-6 flex items-center gap-2">
            <Bookmark className="h-5 w-5 text-primary" />
            <h1 className="text-2xl font-bold text-foreground">Saved Trips</h1>
          </div>

          {!isAuthenticated ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <Bookmark className="mb-3 h-10 w-10 text-muted-foreground/40" />
              <p className="text-lg font-medium text-foreground">Login to see your saved trips</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Your bookmarks will appear here after you sign in.
              </p>
            </div>
          ) : loading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          ) : trips.length > 0 ? (
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {trips.map((trip) => (
                <TripCard key={trip.id} trip={trip} initialBookmarked={true} />
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <Bookmark className="mb-3 h-10 w-10 text-muted-foreground/40" />
              <p className="text-lg font-medium text-foreground">No saved trips yet</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Bookmark trips you're interested in and they'll show up here.
              </p>
            </div>
          )}
        </div>
      </main>
      <Footer />
    </div>
  );
};

export default Bookmarks;
