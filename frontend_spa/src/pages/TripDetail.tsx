import { useState, useEffect } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import BookmarkButton from "@/features/trip/components/BookmarkButton";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import TripCard from "@/components/TripCard";
import BookingModal from "@/components/BookingModal";
import ApplicationModal from "@/components/ApplicationModal";
import ApplicationManager from "@/components/ApplicationManager";
import ReviewModal from "@/components/ReviewModal";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { apiGet, apiPost } from "@/lib/api";
import type { TripData, TripDetailResponse } from "@/types/api";
import { useAuth } from "@/contexts/AuthContext";
import {
  Calendar, MapPin, IndianRupee, Users, ArrowLeft, Clock, Star,
  CheckCircle2, XCircle, Hotel, Shield, HelpCircle, Backpack,
  DollarSign, Sparkles, Heart, UserCircle, Eye, Lock, Send,
  AlertTriangle, Loader2, MessageCircle
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

// ─── Section nav items ───
// Sections are built dynamically based on trip data — see visibleSections below

const TripDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, isAuthenticated } = useAuth();
  const [trip, setTrip] = useState<TripData | null>(null);
  const [canManage, setCanManage] = useState(false);
  const [similarTrips, setSimilarTrips] = useState<TripData[]>([]);
  const [loading, setLoading] = useState(true);
  const [bookingModalOpen, setBookingModalOpen] = useState(false);
  const [applyModalOpen, setApplyModalOpen] = useState(false);
  const [reviewModalOpen, setReviewModalOpen] = useState(false);
  const [askingQuestion, setAskingQuestion] = useState(false);

  useEffect(() => {
    if (!id) return;
    const cfg = window.TAPNE_RUNTIME_CONFIG;
    if (!cfg?.api?.trips) { setLoading(false); return; }
    setLoading(true);
    apiGet<TripDetailResponse>(`${cfg.api.trips}${id}/`)
      .then((data) => {
        setTrip(data.trip);
        setCanManage(data.can_manage_trip);
        setSimilarTrips(data.similar_trips || []);
      })
      .catch(() => setTrip(null))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="flex min-h-screen flex-col">
        <Navbar />
        <main className="flex flex-1 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </main>
        <Footer />
      </div>
    );
  }

  if (!trip) {
    return (
      <div className="flex min-h-screen flex-col">
        <Navbar />
        <main className="flex flex-1 flex-col items-center justify-center px-4">
          <h1 className="mb-2 text-2xl font-bold">Trip not found</h1>
          <p className="mb-4 text-muted-foreground">This trip may have been removed.</p>
          <Button asChild><Link to="/trips">Browse Trips</Link></Button>
        </main>
        <Footer />
      </div>
    );
  }

  const spotsLeft = trip.spots_left ?? (trip.total_seats || 0);
  const isFull = spotsLeft <= 0;
  const isHost = canManage;
  const accessType = trip.trip_type === "invite" ? "invite" : "open"; // simplified
  const duration = trip.duration_days || (trip.starts_at && trip.ends_at
    ? Math.max(0, Math.ceil((new Date(trip.ends_at).getTime() - new Date(trip.starts_at).getTime()) / 86400000))
    : 0);
  const price = trip.price_per_person || trip.total_trip_price || 0;

  const joinStatus = trip.join_request_status;
  const isJoined = joinStatus === "approved";
  const isTripPast = trip.ends_at ? new Date(trip.ends_at) < new Date() : false;
  const canReview = isAuthenticated && isJoined && isTripPast;

  // Build visible sections dynamically based on trip data
  const visibleSections = [
    { id: "snapshot", label: "Overview" },
    ...(trip.highlights && trip.highlights.length > 0 ? [{ id: "highlights", label: "Highlights" }] : []),
    ...(trip.itinerary_days && trip.itinerary_days.length > 0 ? [{ id: "itinerary", label: "Itinerary" }] : []),
    ...((trip as any).stay_details || (trip as any).accommodation_type ? [{ id: "stay", label: "Stay" }] : []),
    ...((trip.included_items && trip.included_items.length > 0) || (trip.not_included_items && trip.not_included_items.length > 0) ? [{ id: "included", label: "Included" }] : []),
    { id: "pricing", label: "Pricing" },
    ...(trip.things_to_carry && trip.things_to_carry.length > 0 ? [{ id: "carry", label: "Packing" }] : []),
    ...(trip.cancellation_policy ? [{ id: "policies", label: "Policies" }] : []),
    ...(trip.faqs && trip.faqs.length > 0 ? [{ id: "faqs", label: "FAQs" }] : []),
    { id: "reviews", label: "Reviews" },
  ];

  const { requireAuth } = useAuth();

  const hostCanManage = isHost && !isTripPast;

  const handlePrimaryAction = () => {
    if (isHost) {
      if (hostCanManage) {
        navigate(`/manage-trip/${trip.id}`);
      }
      return;
    }
    requireAuth(() => setBookingModalOpen(true));
  };

  const ctaLabel = isHost ? (hostCanManage ? "Manage Trip" : "Trip Completed") : isJoined ? "Already Joined ✓" : isFull ? "Join Waitlist" :
    joinStatus === "pending" ? "Application Pending" : "Book Now";
  const ctaDisabled = isHost ? !hostCanManage : isJoined || joinStatus === "pending";

  const fmtDate = (iso?: string) => iso ? new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "";
  const fmtDateFull = (iso?: string) => iso ? new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "";

  // ─── Sticky CTA Card (desktop sidebar) ───
  const BookingSidebar = () => (
    <div className="space-y-4">
      <Card className="border-primary/20 shadow-md">
        <CardContent className="p-5">
          <div className="mb-1 text-sm text-muted-foreground">Price per person</div>
          <div className="mb-1 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-foreground">₹{price.toLocaleString()}</span>
            {trip.early_bird_price && (
              <Badge variant="secondary" className="text-xs">Early bird: ₹{trip.early_bird_price.toLocaleString()}</Badge>
            )}
          </div>

          <div className="mb-4 space-y-2 text-sm">
            {trip.starts_at && trip.ends_at && (
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Dates</span>
                <span className="font-medium">{fmtDate(trip.starts_at)} – {fmtDate(trip.ends_at)}</span>
              </div>
            )}
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Duration</span>
              <span className="font-medium">{duration}D / {Math.max(0, duration - 1)}N</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Spots left</span>
              <span className={cn("font-medium", spotsLeft <= 3 ? "text-destructive" : "text-foreground")}>{spotsLeft} of {trip.total_seats || "?"}</span>
            </div>
            {trip.booking_closes_at && (
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Book before</span>
                <span className="font-medium">{fmtDateFull(trip.booking_closes_at)}</span>
              </div>
            )}
          </div>

          {spotsLeft <= 3 && spotsLeft > 0 && (
            <div className="mb-3 flex items-center gap-1.5 rounded-lg bg-destructive/10 px-3 py-2 text-sm font-medium text-destructive">
              <AlertTriangle className="h-4 w-4" />
              Only {spotsLeft} spot{spotsLeft !== 1 ? "s" : ""} left
            </div>
          )}

          <Button
            className="w-full text-base transition-transform hover:scale-[1.02]"
            size="lg"
            disabled={ctaDisabled}
            onClick={handlePrimaryAction}
          >
            <span>{ctaLabel}</span>
          </Button>

          {isHost && !hostCanManage && (
            <p className="mt-2 text-center text-xs text-muted-foreground">
              Completed trips can no longer be managed.
            </p>
          )}

          <Button
            variant="outline"
            className="mt-2 w-full border-primary/30 text-primary hover:bg-primary/5"
            onClick={() => {
              requireAuth(() => setReviewModalOpen(true));
            }}
          >
            <Star className="mr-2 h-4 w-4" /> Write a Review
          </Button>

          {!isAuthenticated && (
            <p className="mt-2 text-center text-xs text-muted-foreground">
              Log in to book or review this trip
            </p>
          )}
          <p className="mt-3 text-center text-xs text-muted-foreground">
            Saved by {Math.floor(Math.random() * 30 + 15)} travelers
          </p>
        </CardContent>
      </Card>

      {/* Meet Your Hosts card */}
      {trip.host_display_name && (
        <Card>
          <CardContent className="p-4 space-y-3">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Meet Your Hosts</p>
            <button
              onClick={() => navigate(`/profile/${trip.host_username}`)}
              className="flex items-center gap-3 w-full text-left hover:opacity-80 transition-opacity"
            >
              <Avatar className="h-11 w-11 border-2 border-primary/20">
                <AvatarFallback>{(trip.host_display_name || "H")[0]}</AvatarFallback>
              </Avatar>
              <div className="min-w-0 flex-1">
                <p className="font-semibold text-foreground">{trip.host_display_name}</p>
                {trip.host_bio && <p className="text-xs text-muted-foreground line-clamp-1">{trip.host_bio}</p>}
              </div>
            </button>
            {(trip as any).co_hosts_profiles?.map((ch: any) => (
              <button
                key={ch.username}
                onClick={() => navigate(`/profile/${ch.username}`)}
                className="flex items-center gap-3 w-full text-left hover:opacity-80 transition-opacity"
              >
                <Avatar className="h-11 w-11 border-2 border-primary/20">
                  <AvatarFallback>{(ch.display_name || ch.username)[0]}</AvatarFallback>
                </Avatar>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-foreground">{ch.display_name}</p>
                  <p className="text-xs text-muted-foreground">Co-host</p>
                </div>
              </button>
            ))}
            {!isHost && (
              <Button
                variant="outline"
                className="w-full border-primary/30 text-primary hover:bg-primary/5"
                size="sm"
                disabled={askingQuestion}
                onClick={async () => {
                  if (!isAuthenticated) { requireAuth(); return; }
                  setAskingQuestion(true);
                  try {
                    const cfg = window.TAPNE_RUNTIME_CONFIG;
                    const data = await apiPost<{ ok: boolean; thread_id?: number; error?: string }>(
                      cfg.api.dm_start,
                      { host_username: trip.host_username }
                    );
                    if (data.ok && data.thread_id) {
                      navigate(`/inbox?thread=${data.thread_id}`);
                    } else {
                      toast.error(data.error || "Could not start conversation. Please try again.");
                    }
                  } catch (err: any) {
                    toast.error(err?.error || "Could not start conversation. Please try again.");
                  } finally {
                    setAskingQuestion(false);
                  }
                }}
              >
                {askingQuestion ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <MessageCircle className="mr-1.5 h-4 w-4" />}
                Ask a Question
              </Button>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );

  // ─── Section Component ───
  const Section = ({ id, icon: Icon, title, children }: { id: string; icon: React.ElementType; title: string; children: React.ReactNode }) => (
    <section id={id} className="scroll-mt-24">
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

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Navbar />
      <main className="flex-1">
        {/* ─── HERO ─── */}
        <div className="relative">
          <div className="aspect-[21/9] max-h-[480px] w-full overflow-hidden sm:aspect-[3/1]">
            {trip.banner_image_url && <img src={trip.banner_image_url} alt={trip.title} className="h-full w-full object-cover" />}
            <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-black/20 to-transparent" />
          </div>
          <div className="absolute inset-x-0 bottom-0 mx-auto max-w-6xl px-4 pb-6 md:pb-8">
            <Button variant="ghost" size="sm" asChild className="mb-3 text-white/80 hover:text-white hover:bg-white/10">
              <Link to="/trips"><ArrowLeft className="mr-1 h-4 w-4" /> Back</Link>
            </Button>
            <div className="flex flex-wrap items-center gap-2 mb-2">
              {trip.trip_type && <Badge className="bg-primary text-primary-foreground">{trip.trip_type}</Badge>}
              {trip.trip_vibe?.map(v => (
                <Badge key={v} variant="secondary" className="bg-white/20 text-white border-0 backdrop-blur-sm text-xs">{v}</Badge>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold text-white md:text-4xl lg:text-5xl">{trip.title}</h1>
              <BookmarkButton
                tripId={trip.id}
                initialBookmarked={Boolean((trip as { is_bookmarked?: boolean }).is_bookmarked)}
                size="md"
              />
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-white/80 md:text-base">
              {trip.destination && <span className="flex items-center gap-1"><MapPin className="h-4 w-4" />{trip.destination}</span>}
              {trip.starts_at && trip.ends_at && <span className="flex items-center gap-1"><Calendar className="h-4 w-4" />{fmtDate(trip.starts_at)} – {fmtDateFull(trip.ends_at)}</span>}
              <span className="flex items-center gap-1"><Clock className="h-4 w-4" />{duration}D/{Math.max(0, duration - 1)}N</span>
              <span className="flex items-center gap-1"><Users className="h-4 w-4" />{spotsLeft} spot{spotsLeft !== 1 ? "s" : ""} left</span>
            </div>
          </div>
          </div>

        {/* ─── Section Nav ─── */}
        <div className="sticky top-16 z-20 border-b bg-card/95 backdrop-blur-sm">
          <div className="mx-auto max-w-6xl">
            <nav className="flex gap-1 overflow-x-auto px-4 py-1.5 no-scrollbar">
              {visibleSections.map(s => (
                <a key={s.id} href={`#${s.id}`} className="shrink-0 rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
                  {s.label}
                </a>
              ))}
            </nav>
          </div>
        </div>

        {/* ─── BODY ─── */}
        <div className="mx-auto max-w-6xl px-4 py-6">
          <div className="flex gap-8">
            {/* Main Content */}
            <div className="min-w-0 flex-1 space-y-5">

              {/* Quick Snapshot */}
              <Section id="snapshot" icon={Eye} title="Quick Overview">
                <p className="mb-4 text-muted-foreground leading-relaxed">{trip.summary || trip.description}</p>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {trip.suitable_for && trip.suitable_for.length > 0 && (
                    <div className="rounded-lg bg-muted/50 p-3">
                      <p className="text-xs text-muted-foreground mb-0.5">Ideal for</p>
                      <p className="text-sm font-medium">{trip.suitable_for.join(", ")}</p>
                    </div>
                  )}
                  {trip.difficulty_level && (
                    <div className="rounded-lg bg-muted/50 p-3">
                      <p className="text-xs text-muted-foreground mb-0.5">Difficulty</p>
                      <p className="text-sm font-medium">{trip.difficulty_level}</p>
                    </div>
                  )}
                  {trip.pace_level && (
                    <div className="rounded-lg bg-muted/50 p-3">
                      <p className="text-xs text-muted-foreground mb-0.5">Pace</p>
                      <p className="text-sm font-medium">{trip.pace_level}</p>
                    </div>
                  )}
                  {trip.group_size_label && (
                    <div className="rounded-lg bg-muted/50 p-3">
                      <p className="text-xs text-muted-foreground mb-0.5">Group size</p>
                      <p className="text-sm font-medium">{trip.group_size_label}</p>
                    </div>
                  )}
                  {trip.total_seats && (
                    <div className="rounded-lg bg-muted/50 p-3">
                      <p className="text-xs text-muted-foreground mb-0.5">Total seats</p>
                      <p className="text-sm font-medium">Max {trip.total_seats} travelers</p>
                    </div>
                  )}
                  {trip.booking_closes_at && (
                    <div className="rounded-lg bg-muted/50 p-3">
                      <p className="text-xs text-muted-foreground mb-0.5">Book before</p>
                      <p className="text-sm font-medium">{fmtDateFull(trip.booking_closes_at)}</p>
                    </div>
                  )}
                </div>
              </Section>

              {/* Highlights */}
              {trip.highlights && trip.highlights.length > 0 && (
                <Section id="highlights" icon={Star} title="Highlights">
                  <ul className="space-y-2.5">
                    {trip.highlights.map((h, i) => (
                      <li key={i} className="flex items-start gap-2.5">
                        <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                        <span className="text-foreground">{h}</span>
                      </li>
                    ))}
                  </ul>
                </Section>
              )}

              {/* Itinerary */}
              {trip.itinerary_days && trip.itinerary_days.length > 0 && (
                <Section id="itinerary" icon={Calendar} title="Day-by-Day Itinerary">
                  {/* Desktop: timeline */}
                  <div className="hidden md:block">
                    <div className="relative border-l-2 border-primary/20 pl-6 space-y-6">
                      {trip.itinerary_days.map((day, i) => (
                        <div key={i} className="relative">
                          <div className="absolute -left-[33px] flex h-8 w-8 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
                            {day.day_number || i + 1}
                          </div>
                          <div className="rounded-lg border bg-card p-4">
                            <div className="flex items-center gap-2 mb-1">
                              <h4 className="font-semibold text-foreground">Day {day.day_number || i + 1}: {day.title}</h4>
                              {day.is_flexible && <Badge variant="outline" className="text-xs">Flexible</Badge>}
                            </div>
                            <p className="text-sm text-muted-foreground mb-2">{day.description}</p>
                            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                              {day.stay && <span>🏨 {day.stay}</span>}
                              {day.meals && <span>🍽 {day.meals}</span>}
                              {day.activities && <span>🎯 {day.activities}</span>}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                  {/* Mobile: accordion */}
                  <div className="md:hidden">
                    <Accordion type="single" collapsible>
                      {trip.itinerary_days.map((day, i) => (
                        <AccordionItem key={i} value={`day-${i}`}>
                          <AccordionTrigger className="text-sm">
                            <span className="flex items-center gap-2">
                              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-[10px] font-bold text-primary-foreground">{day.day_number || i + 1}</span>
                              Day {day.day_number || i + 1}: {day.title}
                            </span>
                          </AccordionTrigger>
                          <AccordionContent>
                            <p className="text-sm text-muted-foreground mb-2">{day.description}</p>
                            <div className="space-y-1 text-xs text-muted-foreground">
                              {day.stay && <p>🏨 {day.stay}</p>}
                              {day.meals && <p>🍽 {day.meals}</p>}
                              {day.activities && <p>🎯 {day.activities}</p>}
                            </div>
                          </AccordionContent>
                        </AccordionItem>
                      ))}
                    </Accordion>
                  </div>
                </Section>
              )}

              {/* Included / Not Included */}
              {(trip.included_items || trip.not_included_items) && (
                <section id="included" className="scroll-mt-24">
                  <div className="grid gap-5 sm:grid-cols-2">
                    {trip.included_items && trip.included_items.length > 0 && (
                      <Card>
                        <CardHeader className="pb-3">
                          <div className="flex items-center gap-2.5">
                            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
                              <CheckCircle2 className="h-4 w-4 text-primary" />
                            </div>
                            <CardTitle className="text-lg">What's Included</CardTitle>
                          </div>
                        </CardHeader>
                        <CardContent>
                          <ul className="space-y-2">
                            {trip.included_items.map((item, i) => (
                              <li key={i} className="flex items-center gap-2 text-sm">
                                <CheckCircle2 className="h-4 w-4 shrink-0 text-primary" />
                                <span>{item}</span>
                              </li>
                            ))}
                          </ul>
                        </CardContent>
                      </Card>
                    )}
                    {trip.not_included_items && trip.not_included_items.length > 0 && (
                      <Card>
                        <CardHeader className="pb-3">
                          <div className="flex items-center gap-2.5">
                            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-destructive/10">
                              <XCircle className="h-4 w-4 text-destructive" />
                            </div>
                            <CardTitle className="text-lg">Not Included</CardTitle>
                          </div>
                        </CardHeader>
                        <CardContent>
                          <ul className="space-y-2">
                            {trip.not_included_items.map((item, i) => (
                              <li key={i} className="flex items-center gap-2 text-sm text-muted-foreground">
                                <XCircle className="h-4 w-4 shrink-0 text-destructive/60" />
                                <span>{item}</span>
                              </li>
                            ))}
                          </ul>
                        </CardContent>
                      </Card>
                    )}
                  </div>
                </section>
              )}

              {/* Price Breakdown */}
              <Section id="pricing" icon={DollarSign} title="Price Breakdown">
                <div className="space-y-3">
                  <div className="flex items-baseline justify-between rounded-lg bg-primary/5 p-3">
                    <span className="font-medium">Total price per person</span>
                    <span className="text-xl font-bold text-primary">₹{price.toLocaleString()}</span>
                  </div>
                  {trip.early_bird_price && (
                    <div className="flex items-center justify-between rounded-lg bg-accent/50 p-3 text-sm">
                      <span>Early bird price</span>
                      <span className="font-semibold text-accent-foreground">₹{trip.early_bird_price.toLocaleString()}</span>
                    </div>
                  )}
                  {trip.payment_terms === "partial" && (
                    <div className="flex items-center justify-between p-3 text-sm border rounded-lg">
                      <span className="text-muted-foreground">Payment type</span>
                      <span className="font-medium">Partial advance</span>
                    </div>
                  )}
                </div>
              </Section>

              {/* Things to Carry */}
              {trip.things_to_carry && trip.things_to_carry.length > 0 && (
                <Section id="carry" icon={Backpack} title="Things to Carry">
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                    {trip.things_to_carry.map((item, i) => (
                      <div key={i} className="flex items-center gap-2 rounded-lg bg-muted/50 px-3 py-2 text-sm">
                        <CheckCircle2 className="h-3.5 w-3.5 text-primary shrink-0" />
                        {item}
                      </div>
                    ))}
                  </div>
                </Section>
              )}

              {/* Policies & Safety */}
              {trip.cancellation_policy && (
                <Section id="policies" icon={Shield} title="Policies & Safety">
                  <div className="space-y-4">
                    <div>
                      <h4 className="text-sm font-semibold mb-1">Cancellation Policy</h4>
                      <p className="text-sm text-muted-foreground">{trip.cancellation_policy}</p>
                    </div>
                  </div>
                </Section>
              )}

              {/* FAQs */}
              {trip.faqs && trip.faqs.length > 0 && (
                <Section id="faqs" icon={HelpCircle} title="Frequently Asked Questions">
                  <Accordion type="single" collapsible>
                    {trip.faqs.map((faq, i) => (
                      <AccordionItem key={i} value={`faq-${i}`}>
                        <AccordionTrigger className="text-sm text-left">{faq.question}</AccordionTrigger>
                        <AccordionContent>
                          <p className="text-sm text-muted-foreground">{faq.answer}</p>
                        </AccordionContent>
                      </AccordionItem>
                    ))}
                  </Accordion>
                </Section>
              )}

              {/* Reviews Section — always visible */}
              <Section id="reviews" icon={Star} title="Reviews & Ratings">
                {trip.average_rating ? (
                  <div className="mb-4 flex items-center gap-3">
                    <div className="flex items-center gap-1">
                      {[1, 2, 3, 4, 5].map(s => (
                        <Star key={s} className={cn("h-5 w-5", s <= Math.round(trip.average_rating || 0) ? "fill-yellow-400 text-yellow-400" : "text-muted-foreground/30")} />
                      ))}
                    </div>
                    <span className="text-lg font-bold text-foreground">{trip.average_rating.toFixed(1)}</span>
                    <span className="text-sm text-muted-foreground">({trip.reviews_count || 0} review{(trip.reviews_count || 0) !== 1 ? "s" : ""})</span>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground mb-4">Not enough reviews yet. Be the first to share your experience!</p>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  className="border-primary/30 text-primary hover:bg-primary/5"
                  onClick={() => requireAuth(() => setReviewModalOpen(true))}
                >
                  <Star className="mr-1.5 h-4 w-4" /> Write a Review
                </Button>
              </Section>



              {/* Host Application Management */}
              {isHost && (
                <ApplicationManager tripId={trip.id} />
              )}

              {/* Similar Trips */}
              {similarTrips.length > 0 && (
                <section className="scroll-mt-24">
                  <h2 className="text-xl font-bold text-foreground mb-4">Similar Trips</h2>
                  <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
                    {similarTrips.map(t => <TripCard key={t.id} trip={t} />)}
                  </div>
                </section>
              )}
            </div>

            {/* ─── Sticky Sidebar (desktop) ─── */}
            <aside className="hidden w-[320px] shrink-0 lg:block">
              <div className="sticky top-32">
                <BookingSidebar />
              </div>
            </aside>
          </div>
        </div>

        {/* ─── Mobile Sticky CTA ─── */}
        <div className="fixed inset-x-0 bottom-0 z-30 border-t bg-card/95 p-3 backdrop-blur-sm lg:hidden">
          <div className="flex items-center justify-between gap-3">
            <div>
              <span className="text-lg font-bold text-foreground">₹{price.toLocaleString()}</span>
              <span className="text-xs text-muted-foreground ml-1">/ person</span>
            </div>
            <Button
              size="lg"
              disabled={ctaDisabled}
              onClick={handlePrimaryAction}
              className="transition-transform hover:scale-[1.02]"
            >
              {ctaLabel}
            </Button>
          </div>
        </div>
        <div className="h-20 lg:hidden" />
      </main>
      <Footer />

      {/* Booking Modal */}
      <BookingModal open={bookingModalOpen} onOpenChange={setBookingModalOpen} trip={trip} />
      {/* Application Modal */}
      <ApplicationModal open={applyModalOpen} onOpenChange={setApplyModalOpen} trip={trip} />
      {/* Review Modal */}
      <ReviewModal open={reviewModalOpen} onOpenChange={setReviewModalOpen} trip={trip} tripId={trip.id} onReviewSubmitted={() => {
        const cfg = window.TAPNE_RUNTIME_CONFIG;
        if (cfg?.api?.trips && id) {
          apiGet<TripDetailResponse>(`${cfg.api.trips}${id}/`)
            .then((data) => { setTrip(data.trip); })
            .catch(() => {});
        }
      }} />
    </div>
  );
};

export default TripDetail;
