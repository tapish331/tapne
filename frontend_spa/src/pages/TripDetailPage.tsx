import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  Calendar,
  CheckCircle2,
  Clock,
  DollarSign,
  MapPin,
  Send,
  Shield,
  Star,
  UserCircle,
  Users,
  Loader2,
} from "lucide-react";
import Footer from "@/components/Footer";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import FrontendNavbar from "@frontend/components/FrontendNavbar";
import { ErrorState, LoadingState } from "@frontend/components/PageState";
import TripCard from "@frontend/components/TripCard";
import { FrontendTrip, apiGet, apiPost, apiUrl } from "@frontend/lib/api";
import { formatCurrency, formatDateRange } from "@frontend/lib/format";
import { useAuth } from "@frontend/context/AuthContext";

type TripDetailPayload = {
  trip: FrontendTrip;
  can_manage_trip: boolean;
  host?: {
    username: string;
    display_name: string;
    bio: string;
    location: string;
  };
  participants?: Array<{
    username: string;
    display_name: string;
    role: string;
  }>;
  similar_trips?: FrontendTrip[];
  join_request?: {
    status: string;
    outcome: string;
  } | null;
};

export default function TripDetailPage() {
  const { id } = useParams();
  const { isAuthenticated } = useAuth();
  const [payload, setPayload] = useState<TripDetailPayload | null>(null);
  const [error, setError] = useState("");
  const [joinMessage, setJoinMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!id) {
      return;
    }
    apiGet<TripDetailPayload>(`${apiUrl("trips")}${id}/`)
      .then((nextPayload) => setPayload(nextPayload))
      .catch((err: Error) => setError(err.message));
  }, [id]);

  async function submitJoinRequest() {
    if (!id) {
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const response = await apiPost<{ outcome: string; request?: { status: string } }>(`${apiUrl("trips")}${id}/join-request/`, {
        message: joinMessage,
      });
      setPayload((current) =>
        current
          ? {
              ...current,
              join_request: {
                status: response.request?.status || "pending",
                outcome: response.outcome,
              },
            }
          : current,
      );
      setJoinMessage("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to submit join request.");
    } finally {
      setSubmitting(false);
    }
  }

  if (error) {
    return (
      <div className="flex min-h-screen flex-col">
        <FrontendNavbar />
        <main className="mx-auto flex w-full max-w-6xl flex-1 px-4 py-10">
          <ErrorState title="Trip unavailable" body={error} />
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
          <LoadingState label="Loading live trip details..." />
        </main>
        <Footer />
      </div>
    );
  }

  const { trip } = payload;
  const priceValue = trip.price_per_person ?? trip.total_trip_price;

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <FrontendNavbar />
      <main className="flex-1">
        <div className="relative">
          <div className="aspect-[21/9] max-h-[480px] w-full overflow-hidden sm:aspect-[3/1]">
            <img src={trip.banner_image_url || "/placeholder.svg"} alt={trip.title} className="h-full w-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-black/20 to-transparent" />
          </div>
          <div className="absolute inset-x-0 bottom-0 mx-auto max-w-6xl px-4 pb-6 md:pb-8">
            <Button variant="ghost" size="sm" asChild className="mb-3 text-white/80 hover:bg-white/10 hover:text-white">
              <Link to="/trips">
                <ArrowLeft className="mr-1 h-4 w-4" /> Back
              </Link>
            </Button>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              {trip.trip_type_label ? <Badge className="bg-primary text-primary-foreground">{trip.trip_type_label}</Badge> : null}
              {(trip.trip_vibe || []).map((value) => (
                <Badge key={value} variant="secondary" className="border-0 bg-white/20 text-white backdrop-blur-sm text-xs">
                  {value}
                </Badge>
              ))}
            </div>
            <h1 className="text-2xl font-bold text-white md:text-4xl lg:text-5xl">{trip.title}</h1>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-white/80 md:text-base">
              <span className="flex items-center gap-1">
                <MapPin className="h-4 w-4" />
                {trip.destination || "Destination announced soon"}
              </span>
              <span className="flex items-center gap-1">
                <Calendar className="h-4 w-4" />
                {formatDateRange(trip.starts_at, trip.ends_at)}
              </span>
              {trip.duration_label ? (
                <span className="flex items-center gap-1">
                  <Clock className="h-4 w-4" />
                  {trip.duration_label}
                </span>
              ) : null}
              {trip.spots_left_label ? (
                <span className="flex items-center gap-1">
                  <Users className="h-4 w-4" />
                  {trip.spots_left_label}
                </span>
              ) : null}
            </div>
          </div>
        </div>

        <div className="mx-auto max-w-6xl px-4 py-6">
          <div className="flex gap-8">
            <div className="min-w-0 flex-1 space-y-5">
              <DetailSection icon={Star} title="Overview">
                <p className="leading-relaxed text-muted-foreground">{trip.summary || trip.description || "Trip details are being prepared."}</p>
              </DetailSection>

              {trip.highlights?.length ? (
                <DetailSection icon={Star} title="Highlights">
                  <ul className="space-y-2.5">
                    {trip.highlights.map((highlight) => (
                      <li key={highlight} className="flex items-start gap-2.5">
                        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                        <span className="text-foreground">{highlight}</span>
                      </li>
                    ))}
                  </ul>
                </DetailSection>
              ) : null}

              {trip.itinerary_days?.length ? (
                <DetailSection icon={Calendar} title="Itinerary">
                  <div className="space-y-4">
                    {trip.itinerary_days.map((day, index) => (
                      <div key={index} className="rounded-lg border bg-card p-4">
                        <h4 className="font-semibold text-foreground">Day {index + 1}: {String(day.title || "Itinerary segment")}</h4>
                        <p className="mt-2 text-sm text-muted-foreground">{String(day.description || "")}</p>
                      </div>
                    ))}
                  </div>
                </DetailSection>
              ) : null}

              {(trip.included_items?.length || trip.not_included_items?.length) ? (
                <div className="grid gap-5 sm:grid-cols-2">
                  <DetailSection icon={CheckCircle2} title="What's Included">
                    <ul className="space-y-2">
                      {(trip.included_items || []).map((item) => (
                        <li key={item} className="flex items-center gap-2 text-sm">
                          <CheckCircle2 className="h-4 w-4 shrink-0 text-primary" />
                          <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                  </DetailSection>
                  <DetailSection icon={AlertTriangle} title="Not Included">
                    <ul className="space-y-2">
                      {(trip.not_included_items || []).map((item) => (
                        <li key={item} className="flex items-center gap-2 text-sm text-muted-foreground">
                          <AlertTriangle className="h-4 w-4 shrink-0 text-destructive/70" />
                          <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                  </DetailSection>
                </div>
              ) : null}

              <DetailSection icon={DollarSign} title="Pricing">
                <div className="rounded-lg bg-primary/5 p-4">
                  <div className="text-sm text-muted-foreground">Price per traveler</div>
                  <div className="mt-2 text-3xl font-bold text-primary">{formatCurrency(priceValue, trip.currency || "INR")}</div>
                </div>
              </DetailSection>

              {trip.cancellation_policy || trip.code_of_conduct ? (
                <DetailSection icon={Shield} title="Policies & Safety">
                  <div className="space-y-4">
                    {trip.cancellation_policy ? (
                      <div>
                        <h4 className="text-sm font-semibold">Cancellation policy</h4>
                        <p className="mt-1 text-sm text-muted-foreground">{trip.cancellation_policy}</p>
                      </div>
                    ) : null}
                    {trip.code_of_conduct ? (
                      <div>
                        <h4 className="text-sm font-semibold">Code of conduct</h4>
                        <p className="mt-1 text-sm text-muted-foreground">{trip.code_of_conduct}</p>
                      </div>
                    ) : null}
                  </div>
                </DetailSection>
              ) : null}

              {payload.host ? (
                <DetailSection icon={UserCircle} title="Meet Your Host">
                  <div className="flex items-start gap-4">
                    <Avatar className="h-16 w-16 border-2 border-primary/20">
                      <AvatarFallback>{payload.host.display_name.slice(0, 1).toUpperCase()}</AvatarFallback>
                    </Avatar>
                    <div className="flex-1">
                      <h4 className="text-lg font-semibold text-foreground">{payload.host.display_name}</h4>
                      <p className="text-sm text-muted-foreground">{payload.host.location}</p>
                      {payload.host.bio ? <p className="mt-2 text-sm text-muted-foreground">{payload.host.bio}</p> : null}
                    </div>
                  </div>
                </DetailSection>
              ) : null}

              {payload.participants?.length ? (
                <DetailSection icon={Users} title="Travelers">
                  <div className="flex flex-wrap gap-3">
                    {payload.participants.map((participant) => (
                      <div key={`${participant.role}-${participant.username}`} className="flex items-center gap-2 rounded-full bg-muted/50 px-3 py-1.5">
                        <Avatar className="h-7 w-7">
                          <AvatarFallback className="text-xs">{participant.display_name.slice(0, 1).toUpperCase()}</AvatarFallback>
                        </Avatar>
                        <span className="text-sm font-medium">{participant.display_name}</span>
                        {participant.role === "host" ? <Badge variant="outline" className="text-[10px]">Host</Badge> : null}
                      </div>
                    ))}
                  </div>
                </DetailSection>
              ) : null}

              {payload.similar_trips?.length ? (
                <section>
                  <h2 className="mb-4 text-xl font-bold text-foreground">Similar Trips</h2>
                  <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
                    {payload.similar_trips.map((similarTrip) => (
                      <TripCard key={similarTrip.id} trip={similarTrip} />
                    ))}
                  </div>
                </section>
              ) : null}
            </div>

            <aside className="hidden w-[320px] shrink-0 lg:block">
              <div className="sticky top-32">
                <Card className="border-primary/20 shadow-md">
                  <CardContent className="space-y-4 p-5">
                    <div>
                      <div className="text-sm text-muted-foreground">Price per person</div>
                      <div className="mt-1 text-3xl font-bold text-foreground">{formatCurrency(priceValue, trip.currency || "INR")}</div>
                    </div>
                    <div className="space-y-2 text-sm">
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Dates</span>
                        <span className="font-medium">{formatDateRange(trip.starts_at, trip.ends_at)}</span>
                      </div>
                      {trip.duration_label ? (
                        <div className="flex items-center justify-between">
                          <span className="text-muted-foreground">Duration</span>
                          <span className="font-medium">{trip.duration_label}</span>
                        </div>
                      ) : null}
                      {trip.spots_left_label ? (
                        <div className="flex items-center justify-between">
                          <span className="text-muted-foreground">Capacity</span>
                          <span className="font-medium">{trip.spots_left_label}</span>
                        </div>
                      ) : null}
                    </div>
                    {payload.can_manage_trip ? (
                      <Button className="w-full" asChild>
                        <a href={`/trips/${trip.id}/edit/`}>Manage Trip</a>
                      </Button>
                    ) : (
                      <JoinAction
                        isAuthenticated={isAuthenticated}
                        joinRequest={payload.join_request}
                        joinMessage={joinMessage}
                        onJoinMessageChange={setJoinMessage}
                        onSubmit={submitJoinRequest}
                        submitting={submitting}
                      />
                    )}
                  </CardContent>
                </Card>
              </div>
            </aside>
          </div>
        </div>
      </main>
      <Footer />
    </div>
  );
}

function DetailSection({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
              <Icon className="h-4 w-4 text-primary" />
            </div>
            <CardTitle className="text-lg">{title}</CardTitle>
          </div>
        </CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
    </section>
  );
}

function JoinAction({
  isAuthenticated,
  joinRequest,
  joinMessage,
  onJoinMessageChange,
  onSubmit,
  submitting,
}: {
  isAuthenticated: boolean;
  joinRequest?: { status: string; outcome: string } | null;
  joinMessage: string;
  onJoinMessageChange: (value: string) => void;
  onSubmit: () => Promise<void>;
  submitting: boolean;
}) {
  if (!isAuthenticated) {
    return (
      <Button className="w-full" asChild>
        <Link to="/login">Log in to request</Link>
      </Button>
    );
  }
  if (joinRequest?.status === "approved") {
    return <Button className="w-full" disabled>Approved</Button>;
  }
  if (joinRequest?.status === "pending") {
    return <Button className="w-full" disabled>Request Pending</Button>;
  }
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button className="w-full">Request to Join</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Request to join this trip</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 pt-2">
          <Textarea
            rows={5}
            placeholder="Tell the host a bit about why you want to join."
            value={joinMessage}
            onChange={(event) => onJoinMessageChange(event.target.value)}
          />
          <Button className="w-full" disabled={submitting} onClick={() => void onSubmit()}>
            {submitting ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Send className="mr-1.5 h-4 w-4" />}
            Send request
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
