/**
 * MyTrips override — mirrors lovable/src/pages/MyTrips.tsx but keeps the
 * active tab in the URL so post-publish landing is deterministic in production.
 */
import { useState, useEffect } from "react";
import { useLocation, useNavigate, Link } from "react-router-dom";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/contexts/AuthContext";
import { useDrafts } from "@/contexts/DraftContext";
import { apiGet, apiPost } from "@/lib/api";
import type { TripData, MyTripsResponse } from "@/types/api";
import { toast } from "sonner";
import {
  Plus, Edit, Trash2, Copy, MapPin, Calendar, FileText, Clock,
  AlertTriangle, Loader2, Eye, Settings, Lock, Unlock, MoreVertical,
  Users, CheckCircle2,
} from "lucide-react";

type MyTripsTab = "drafts" | "published" | "completed";

function normalizeTab(value: string | null): MyTripsTab {
  if (value === "published") return "published";
  if (value === "completed" || value === "past") return "completed";
  return "drafts";
}

const MyTrips = () => {
  const { user, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [activeTab, setActiveTab] = useState<MyTripsTab>("drafts");
  const { drafts, deleteDraft, duplicateDraft, loading: draftsLoading } = useDrafts();
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [publishedTrips, setPublishedTrips] = useState<TripData[]>([]);
  const [pastTrips, setPastTrips] = useState<TripData[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isAuthenticated || !user) {
      navigate("/login");
    }
  }, [isAuthenticated, navigate, user]);

  useEffect(() => {
    const stateTab =
      location.state && typeof location.state === "object" && "tab" in location.state
        ? String((location.state as { tab?: unknown }).tab || "")
        : null;
    const searchTab = new URLSearchParams(location.search).get("tab");
    setActiveTab(normalizeTab(stateTab || searchTab));
  }, [location.key, location.search, location.state]);

  useEffect(() => {
    if (!isAuthenticated) return;
    const cfg = window.TAPNE_RUNTIME_CONFIG;
    if (!cfg?.api?.my_trips) {
      setLoading(false);
      return;
    }

    let ignore = false;
    apiGet<MyTripsResponse>(cfg.api.my_trips)
      .then((data) => {
        if (ignore) return;
        const now = new Date();
        const published = data.trips.filter(
          (trip) => !trip.is_draft && trip.is_published && (!trip.ends_at || new Date(trip.ends_at) >= now),
        );
        const past = data.trips.filter((trip) => !trip.is_draft && trip.ends_at && new Date(trip.ends_at) < now);
        setPublishedTrips(published);
        setPastTrips(past);
      })
      .catch(() => {})
      .finally(() => {
        if (!ignore) {
          setLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [isAuthenticated]);

  if (!isAuthenticated || !user) {
    return null;
  }

  const userDrafts = drafts.filter((draft) => draft.status === "draft");

  const formatDate = (iso: string) => {
    if (!iso) return "";
    const date = new Date(iso);
    return date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  };

  const timeAgo = (iso: string) => {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "Just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
  };

  const computeProgress = (draft: typeof drafts[0]) => {
    let filled = 0;
    const total = 8;
    if (draft.title) filled++;
    if (draft.destination) filled++;
    if (draft.category) filled++;
    if (draft.startDate && draft.endDate) filled++;
    if (draft.formData?.totalPrice) filled++;
    if (draft.formData?.highlights?.some((highlight: string) => highlight.trim())) filled++;
    if (draft.formData?.itinerary?.some((day: any) => day.title?.trim())) filled++;
    if (draft.formData?.cancellationPolicy) filled++;
    return Math.round((filled / total) * 100);
  };

  const handleDelete = async () => {
    if (deleteId != null) {
      await deleteDraft(deleteId);
      setDeleteId(null);
    }
  };

  const handleDuplicate = async (id: number) => {
    await duplicateDraft(id);
    toast.success("Draft duplicated");
  };

  const handleDuplicatePublished = async (tripId: number) => {
    const cfg = window.TAPNE_RUNTIME_CONFIG;
    try {
      await apiPost(`${cfg.api.trips}${tripId}/duplicate/`, {});
      toast.success("Trip duplicated as new draft");
      window.location.reload();
    } catch {
      toast.error("Failed to duplicate");
    }
  };

  const handleBookingToggle = async (tripId: number, current: string) => {
    const cfg = window.TAPNE_RUNTIME_CONFIG;
    const nextStatus = current === "open" ? "closed" : "open";
    try {
      await apiPost(`${cfg.api.manage_trip}${tripId}/booking-status/`, { status: nextStatus });
      setPublishedTrips((prev) =>
        prev.map((trip) => (trip.id === tripId ? { ...trip, booking_status: nextStatus as any } : trip)),
      );
      toast.success(nextStatus === "closed" ? "Bookings closed" : "Bookings reopened");
    } catch {
      toast.error("Failed to update");
    }
  };

  const getStatusBadge = (trip: TripData) => {
    const bookingStatus = trip.booking_status || (trip.spots_left === 0 ? "full" : "open");
    if (bookingStatus === "full") {
      return <Badge className="border-amber-200 bg-amber-100 text-xs text-amber-800">Full</Badge>;
    }
    if (bookingStatus === "closed") {
      return <Badge variant="secondary" className="text-xs">Closed</Badge>;
    }
    return <Badge className="border-primary/20 bg-primary/10 text-xs text-primary">Open</Badge>;
  };

  const PublishedTripCard = ({ trip }: { trip: TripData }) => {
    const seatsFilled = (trip.total_seats || 0) - (trip.spots_left ?? 0);
    const bookingStatus = trip.booking_status || (trip.spots_left === 0 ? "full" : "open");

    return (
      <Card className="overflow-hidden transition-shadow hover:shadow-md">
        <CardContent className="p-0">
          <div className="flex flex-col sm:flex-row">
            {trip.banner_image_url ? (
              <div className="relative h-36 w-full shrink-0 overflow-hidden sm:h-auto sm:w-48">
                <img src={trip.banner_image_url} alt={trip.title} className="h-full w-full object-cover" />
              </div>
            ) : null}
            <div className="flex-1 p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="mb-1 flex items-center gap-2">
                    <h3 className="truncate text-base font-semibold text-foreground">{trip.title}</h3>
                    {getStatusBadge(trip)}
                  </div>
                  <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                    {trip.destination ? (
                      <span className="flex items-center gap-1">
                        <MapPin className="h-3.5 w-3.5" /> {trip.destination}
                      </span>
                    ) : null}
                    {trip.starts_at && trip.ends_at ? (
                      <span className="flex items-center gap-1">
                        <Calendar className="h-3.5 w-3.5" />
                        {formatDate(trip.starts_at)} - {formatDate(trip.ends_at)}
                      </span>
                    ) : null}
                    <span className="flex items-center gap-1">
                      <Users className="h-3.5 w-3.5" />
                      {seatsFilled}/{trip.total_seats || "?"} seats
                    </span>
                  </div>
                </div>

                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0">
                      <MoreVertical className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-48">
                    <DropdownMenuItem onClick={() => navigate(`/trips/${trip.id}`)}>
                      <Eye className="mr-2 h-4 w-4" /> Preview Trip
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => navigate(`/create-trip?draft=${trip.id}`)}>
                      <Edit className="mr-2 h-4 w-4" /> Edit Trip
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => navigate(`/manage-trip/${trip.id}`)}>
                      <Settings className="mr-2 h-4 w-4" /> Manage Trip
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={() => handleBookingToggle(trip.id, bookingStatus)}>
                      {bookingStatus === "open" ? (
                        <><Lock className="mr-2 h-4 w-4" /> Close Bookings</>
                      ) : (
                        <><Unlock className="mr-2 h-4 w-4" /> Reopen Bookings</>
                      )}
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => handleDuplicatePublished(trip.id)}>
                      <Copy className="mr-2 h-4 w-4" /> Duplicate
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Button size="sm" variant="outline" className="h-8 text-xs" onClick={() => navigate(`/manage-trip/${trip.id}`)}>
                  <Settings className="mr-1 h-3.5 w-3.5" /> Manage
                </Button>
                <Button size="sm" variant="outline" className="h-8 text-xs" asChild>
                  <Link to={`/trips/${trip.id}`}><Eye className="mr-1 h-3.5 w-3.5" /> Preview</Link>
                </Button>
                {trip.applications_count != null && trip.applications_count > 0 ? (
                  <Badge variant="secondary" className="text-xs">
                    {trip.applications_count} pending app{trip.applications_count !== 1 ? "s" : ""}
                  </Badge>
                ) : null}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  };

  const CompletedTripCard = ({ trip }: { trip: TripData }) => (
    <Card className="overflow-hidden opacity-80">
      <CardContent className="p-0">
        <div className="flex flex-col sm:flex-row">
          {trip.banner_image_url ? (
            <div className="relative h-36 w-full shrink-0 overflow-hidden sm:h-auto sm:w-48">
              <img src={trip.banner_image_url} alt={trip.title} className="h-full w-full object-cover grayscale-[30%]" />
            </div>
          ) : null}
          <div className="flex-1 p-4">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex items-center gap-2">
                  <h3 className="truncate text-base font-semibold text-foreground">{trip.title}</h3>
                  <Badge variant="secondary" className="text-xs"><CheckCircle2 className="mr-1 h-3 w-3" /> Completed</Badge>
                </div>
                <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                  {trip.destination ? (
                    <span className="flex items-center gap-1"><MapPin className="h-3.5 w-3.5" /> {trip.destination}</span>
                  ) : null}
                  {trip.starts_at && trip.ends_at ? (
                    <span className="flex items-center gap-1">
                      <Calendar className="h-3.5 w-3.5" /> {formatDate(trip.starts_at)} - {formatDate(trip.ends_at)}
                    </span>
                  ) : null}
                </div>
              </div>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0">
                    <MoreVertical className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-44">
                  <DropdownMenuItem onClick={() => navigate(`/trips/${trip.id}`)}>
                    <Eye className="mr-2 h-4 w-4" /> View Trip
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleDuplicatePublished(trip.id)}>
                    <Copy className="mr-2 h-4 w-4" /> Duplicate
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Navbar />
      <main className="flex-1">
        <div className="mx-auto max-w-5xl px-4 py-8">
          <div className="mb-8 flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-foreground">My Trips</h1>
              <p className="mt-1 text-muted-foreground">Manage your drafts and published trips</p>
            </div>
            <Button onClick={() => navigate("/create-trip")}>
              <Plus className="mr-1.5 h-4 w-4" /> Create Trip
            </Button>
          </div>

          <Tabs value={activeTab} onValueChange={(nextTab) => setActiveTab(normalizeTab(nextTab))}>
            <TabsList className="mb-6">
              <TabsTrigger value="drafts">
                Drafts {userDrafts.length > 0 ? <Badge variant="secondary" className="ml-2 text-xs">{userDrafts.length}</Badge> : null}
              </TabsTrigger>
              <TabsTrigger value="published">
                Published {publishedTrips.length > 0 ? <Badge variant="secondary" className="ml-2 text-xs">{publishedTrips.length}</Badge> : null}
              </TabsTrigger>
              <TabsTrigger value="completed">
                Completed {pastTrips.length > 0 ? <Badge variant="secondary" className="ml-2 text-xs">{pastTrips.length}</Badge> : null}
              </TabsTrigger>
            </TabsList>

            <TabsContent value="drafts">
              {draftsLoading ? (
                <div className="flex items-center justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
              ) : userDrafts.length === 0 ? (
                <Card>
                  <CardContent className="flex flex-col items-center justify-center py-16">
                    <FileText className="mb-4 h-12 w-12 text-muted-foreground/40" />
                    <h3 className="mb-1 text-lg font-semibold text-foreground">No drafts yet</h3>
                    <p className="mb-6 text-sm text-muted-foreground">Start creating your first trip and it will appear here.</p>
                    <Button onClick={() => navigate("/create-trip")}>
                      <Plus className="mr-1.5 h-4 w-4" /> Create Your First Trip
                    </Button>
                  </CardContent>
                </Card>
              ) : (
                <div className="space-y-4">
                  {userDrafts.map((draft) => {
                    const progress = computeProgress(draft);
                    return (
                      <Card key={draft.id} className="overflow-hidden transition-shadow hover:shadow-md">
                        <CardContent className="p-0">
                          <div className="flex flex-col sm:flex-row">
                            <div className="flex-1 p-5">
                              <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0 flex-1">
                                  <h3 className="truncate text-lg font-semibold text-foreground">
                                    {draft.title || "Untitled Trip"}
                                  </h3>
                                  <div className="mt-1.5 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                                    {draft.destination ? (
                                      <span className="flex items-center gap-1">
                                        <MapPin className="h-3.5 w-3.5" /> {draft.destination}
                                      </span>
                                    ) : null}
                                    {draft.startDate ? (
                                      <span className="flex items-center gap-1">
                                        <Calendar className="h-3.5 w-3.5" /> {formatDate(draft.startDate)}
                                      </span>
                                    ) : null}
                                    {draft.category ? (
                                      <Badge variant="outline" className="text-xs">{draft.category}</Badge>
                                    ) : null}
                                  </div>
                                </div>
                                <Badge variant="secondary" className="shrink-0 text-xs">
                                  <Clock className="mr-1 h-3 w-3" /> {timeAgo(draft.lastEditedAt)}
                                </Badge>
                              </div>

                              <div className="mt-4">
                                <div className="mb-1.5 flex items-center justify-between text-xs text-muted-foreground">
                                  <span>Completion</span>
                                  <span>{progress}%</span>
                                </div>
                                <Progress value={progress} className="h-1.5" />
                              </div>

                              <div className="mt-4 flex items-center gap-2">
                                <Button size="sm" onClick={() => navigate(`/create-trip?draft=${draft.id}`)}>
                                  <Edit className="mr-1.5 h-3.5 w-3.5" /> Edit Draft
                                </Button>
                                <Button variant="outline" size="sm" onClick={() => handleDuplicate(draft.id)}>
                                  <Copy className="mr-1.5 h-3.5 w-3.5" /> Duplicate
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="text-destructive hover:text-destructive"
                                  onClick={() => setDeleteId(draft.id)}
                                >
                                  <Trash2 className="mr-1.5 h-3.5 w-3.5" /> Delete
                                </Button>
                              </div>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              )}
            </TabsContent>

            <TabsContent value="published">
              {loading ? (
                <div className="flex items-center justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
              ) : publishedTrips.length === 0 ? (
                <Card>
                  <CardContent className="flex flex-col items-center justify-center py-16">
                    <FileText className="mb-4 h-12 w-12 text-muted-foreground/40" />
                    <h3 className="mb-1 text-lg font-semibold text-foreground">No published trips</h3>
                    <p className="text-sm text-muted-foreground">Publish a trip and it will show up here.</p>
                  </CardContent>
                </Card>
              ) : (
                <div className="space-y-4">
                  {publishedTrips.map((trip) => <PublishedTripCard key={trip.id} trip={trip} />)}
                </div>
              )}
            </TabsContent>

            <TabsContent value="completed">
              {loading ? (
                <div className="flex items-center justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
              ) : pastTrips.length === 0 ? (
                <Card>
                  <CardContent className="flex flex-col items-center justify-center py-16">
                    <Calendar className="mb-4 h-12 w-12 text-muted-foreground/40" />
                    <h3 className="mb-1 text-lg font-semibold text-foreground">No completed trips</h3>
                    <p className="text-sm text-muted-foreground">Completed trips will appear here after the end date passes.</p>
                  </CardContent>
                </Card>
              ) : (
                <div className="space-y-4">
                  {pastTrips.map((trip) => <CompletedTripCard key={trip.id} trip={trip} />)}
                </div>
              )}
            </TabsContent>
          </Tabs>
        </div>
      </main>
      <Footer />

      <Dialog open={deleteId != null} onOpenChange={() => setDeleteId(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              Delete Draft
            </DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Are you sure you want to delete this draft? This action cannot be undone.
          </p>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setDeleteId(null)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete}>Delete Draft</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default MyTrips;
