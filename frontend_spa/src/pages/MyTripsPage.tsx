import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Calendar, Edit, Plus } from "lucide-react";
import Footer from "@/components/Footer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import FrontendNavbar from "@frontend/components/FrontendNavbar";
import { EmptyState, ErrorState, LoadingState } from "@frontend/components/PageState";
import TripCard from "@frontend/components/TripCard";
import { FrontendTrip, apiGet, apiUrl } from "@frontend/lib/api";
import { useAuth } from "@frontend/context/AuthContext";

type MyTripsPayload = {
  trips: FrontendTrip[];
  active_tab: string;
  tab_counts: Record<string, number>;
};

export default function MyTripsPage() {
  const { ready, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [payload, setPayload] = useState<MyTripsPayload | null>(null);
  const [error, setError] = useState("");
  const tab = searchParams.get("tab") || "drafts";

  useEffect(() => {
    if (ready && !isAuthenticated) {
      navigate("/login");
      return;
    }
    if (!isAuthenticated) {
      return;
    }
    apiGet<MyTripsPayload>(`${apiUrl("my_trips")}?tab=${encodeURIComponent(tab)}`)
      .then((nextPayload) => setPayload(nextPayload))
      .catch((err: Error) => setError(err.message));
  }, [ready, isAuthenticated, tab, navigate]);

  const isDrafts = tab === "drafts";

  return (
    <div className="flex min-h-screen flex-col">
      <FrontendNavbar />
      <main className="flex-1">
        <div className="mx-auto max-w-5xl px-4 py-8">
          <div className="mb-8 flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-foreground">My Trips</h1>
              <p className="mt-1 text-muted-foreground">Manage your drafts and published trips.</p>
            </div>
            <Button asChild>
              <Link to="/create-trip">
                <Plus className="mr-1.5 h-4 w-4" /> Create Trip
              </Link>
            </Button>
          </div>

          <Tabs
            value={tab}
            onValueChange={(nextTab) =>
              setSearchParams(nextTab === "drafts" ? new URLSearchParams() : new URLSearchParams({ tab: nextTab }))
            }
          >
            <TabsList className="mb-6">
              <TabsTrigger value="drafts">
                Drafts {payload?.tab_counts?.drafts ? <Badge variant="secondary" className="ml-2 text-xs">{payload.tab_counts.drafts}</Badge> : null}
              </TabsTrigger>
              <TabsTrigger value="published">
                Published {payload?.tab_counts?.published ? <Badge variant="secondary" className="ml-2 text-xs">{payload.tab_counts.published}</Badge> : null}
              </TabsTrigger>
              <TabsTrigger value="past">Past Trips</TabsTrigger>
            </TabsList>
          </Tabs>

          {error ? <ErrorState title="Trips unavailable" body={error} /> : null}
          {!payload && !error ? <LoadingState label="Loading your trips..." /> : null}
          {payload && payload.trips.length === 0 ? (
            <EmptyState
              title={isDrafts ? "No drafts yet" : "No trips in this section"}
              body={isDrafts ? "Start creating your first trip and it will appear here." : "Trips matching this section will appear here."}
              action={
                isDrafts ? (
                  <Button asChild>
                    <Link to="/create-trip">
                      <Plus className="mr-1.5 h-4 w-4" /> Create your first trip
                    </Link>
                  </Button>
                ) : undefined
              }
            />
          ) : null}
          {payload && payload.trips.length > 0 ? (
            isDrafts ? (
              <div className="space-y-4">
                {payload.trips.map((trip) => (
                  <Card key={trip.id}>
                    <CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
                      <div className="space-y-2">
                        <div className="flex items-center gap-3">
                          <h2 className="text-lg font-semibold text-foreground">{trip.title}</h2>
                          <Badge variant="outline">Draft</Badge>
                        </div>
                        <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
                          <span>{trip.destination || "Destination announced soon"}</span>
                          <span className="flex items-center gap-1">
                            <Calendar className="h-3.5 w-3.5" />
                            {trip.date_label || "Dates announced soon"}
                          </span>
                        </div>
                      </div>
                      <Button asChild>
                        <Link to={`/create-trip?draft=${trip.id}`}>
                          <Edit className="mr-1.5 h-4 w-4" /> Edit Draft
                        </Link>
                      </Button>
                    </CardContent>
                  </Card>
                ))}
              </div>
            ) : (
              <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
                {payload.trips.map((trip) => (
                  <TripCard key={trip.id} trip={trip} />
                ))}
              </div>
            )
          ) : null}
        </div>
      </main>
      <Footer />
    </div>
  );
}
