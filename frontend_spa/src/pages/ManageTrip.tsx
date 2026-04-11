import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/AuthContext";
import { apiGet, apiPost } from "@/lib/api";
import type { EnrollmentRequestData, ManageTripResponse, ParticipantData, TripData } from "@/types/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ClipboardList,
  Eye,
  Loader2,
  Lock,
  MessageSquare,
  Send,
  Unlock,
  UserMinus,
  Users,
  XCircle,
  Clock,
} from "lucide-react";

export default function ManageTrip() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();
  const [trip, setTrip] = useState<TripData | null>(null);
  const [participants, setParticipants] = useState<ParticipantData[]>([]);
  const [applications, setApplications] = useState<EnrollmentRequestData[]>([]);
  const [loading, setLoading] = useState(true);
  const [removeId, setRemoveId] = useState<number | null>(null);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [messageOpen, setMessageOpen] = useState(false);
  const [messageText, setMessageText] = useState("");
  const [appFilter, setAppFilter] = useState<"pending" | "approved" | "denied">("pending");

  useEffect(() => {
    if (!isAuthenticated) {
      navigate("/login");
      return;
    }
    const cfg = window.TAPNE_RUNTIME_CONFIG;
    if (!cfg?.api?.manage_trip || !id) {
      setLoading(false);
      return;
    }
    setLoading(true);
    apiGet<ManageTripResponse>(`${cfg.api.manage_trip}${id}/`)
      .then((data) => {
        setTrip(data.trip);
        setParticipants(data.participants);
        setApplications(data.applications);
      })
      .catch(() => toast.error("Failed to load trip data"))
      .finally(() => setLoading(false));
  }, [id, isAuthenticated, navigate]);

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
          <Button asChild>
            <Link to="/my-trips">Back to My Trips</Link>
          </Button>
        </main>
        <Footer />
      </div>
    );
  }

  const bookingStatus = trip.booking_status || "open";
  const seatsFilled = (trip.total_seats || 0) - (trip.spots_left ?? 0);
  const isApplyType = trip.access_type === "apply";
  const pendingApps = applications.filter((app) => app.status === "pending");
  const filteredApps = applications.filter((app) => app.status === appFilter);

  async function handleBookingToggle() {
    const cfg = window.TAPNE_RUNTIME_CONFIG;
    const newStatus = bookingStatus === "open" ? "closed" : "open";
    try {
      await apiPost(`${cfg.api.manage_trip}${id}/booking-status/`, { status: newStatus });
      setTrip((current) => (current ? { ...current, booking_status: newStatus } : current));
      toast.success(newStatus === "closed" ? "Bookings closed" : "Bookings reopened");
    } catch {
      toast.error("Failed to update");
    }
  }

  async function handleRemoveParticipant() {
    if (!removeId) {
      return;
    }
    const cfg = window.TAPNE_RUNTIME_CONFIG;
    try {
      await apiPost(`${cfg.api.manage_trip}${id}/participants/${removeId}/remove/`, {});
      setParticipants((current) => current.filter((participant) => participant.id !== removeId));
      toast.success("Participant removed");
    } catch {
      toast.error("Failed to remove");
    }
    setRemoveId(null);
  }

  async function handleDecision(requestId: number, decision: "approve" | "deny") {
    const cfg = window.TAPNE_RUNTIME_CONFIG;
    try {
      await apiPost(`${cfg.api.base}/hosting-requests/${requestId}/decision/`, { decision });
      setApplications((current) =>
        current.map((app) =>
          app.id === requestId
            ? { ...app, status: decision === "approve" ? "approved" : "denied" }
            : app,
        ),
      );
      toast.success(decision === "approve" ? "Application approved!" : "Application rejected.");
    } catch {
      toast.error("Failed to process");
    }
  }

  async function handleCancelTrip() {
    if (!cancelReason.trim()) {
      toast.error("Please provide a reason");
      return;
    }
    const cfg = window.TAPNE_RUNTIME_CONFIG;
    try {
      await apiPost(`${cfg.api.manage_trip}${id}/cancel/`, { reason: cancelReason });
      setTrip((current) => (current ? { ...current, status: "cancelled" } : current));
      toast.success("Trip cancelled. Participants will be notified.");
      setCancelOpen(false);
    } catch {
      toast.error("Failed to cancel trip");
    }
  }

  async function handleMessage() {
    if (!messageText.trim()) {
      toast.error("Please enter a message");
      return;
    }
    const cfg = window.TAPNE_RUNTIME_CONFIG;
    try {
      const data = await apiPost<{ ok: boolean; sent_count?: number }>(`${cfg.api.manage_trip}${id}/message/`, {
        message: messageText,
      });
      toast.success(
        data.sent_count && data.sent_count > 0
          ? `Message delivered to ${data.sent_count} participant${data.sent_count === 1 ? "" : "s"}`
          : "Message sent to all participants",
      );
      setMessageOpen(false);
      setMessageText("");
    } catch (error: any) {
      toast.error(error?.message || error?.error || "Failed to send message");
    }
  }

  function statusBadge() {
    if (trip.status === "cancelled") {
      return <Badge variant="destructive">Cancelled</Badge>;
    }
    if (bookingStatus === "full") {
      return <Badge className="border-amber-200 bg-amber-100 text-amber-800">Full</Badge>;
    }
    if (bookingStatus === "closed") {
      return <Badge variant="secondary">Closed</Badge>;
    }
    return <Badge className="border-primary/20 bg-primary/10 text-primary">Open</Badge>;
  }

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Navbar />
      <main className="flex-1">
        <div className="mx-auto max-w-5xl px-4 py-6">
          <Button variant="ghost" size="sm" asChild className="mb-4">
            <Link to="/my-trips">
              <ArrowLeft className="mr-1.5 h-4 w-4" />
              Back to My Trips
            </Link>
          </Button>

          <Card className="mb-6">
            <CardContent className="p-5">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0 flex-1">
                  <div className="mb-2 flex items-center gap-3">
                    <h1 className="truncate text-xl font-bold text-foreground">{trip.title}</h1>
                    {statusBadge()}
                  </div>
                  <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
                    <span className="flex items-center gap-1.5">
                      <Users className="h-4 w-4" />
                      {seatsFilled} / {trip.total_seats || "?"} seats filled
                    </span>
                    {isApplyType && pendingApps.length > 0 ? (
                      <span className="flex items-center gap-1.5">
                        <ClipboardList className="h-4 w-4" />
                        {pendingApps.length} pending application{pendingApps.length === 1 ? "" : "s"}
                      </span>
                    ) : null}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" size="sm" asChild>
                    <Link to={`/trips/${trip.id}`}>
                      <Eye className="mr-1.5 h-4 w-4" />
                      Preview
                    </Link>
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setMessageOpen(true)}
                    disabled={participants.length === 0}
                  >
                    <MessageSquare className="mr-1.5 h-4 w-4" />
                    Message All
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleBookingToggle}
                    disabled={trip.status === "cancelled"}
                  >
                    {bookingStatus === "open" ? (
                      <>
                        <Lock className="mr-1.5 h-4 w-4" />
                        Close Bookings
                      </>
                    ) : (
                      <>
                        <Unlock className="mr-1.5 h-4 w-4" />
                        Reopen Bookings
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          <Tabs defaultValue="participants">
            <TabsList className="mb-4">
              <TabsTrigger value="participants">
                Participants
                {participants.length > 0 ? <Badge variant="secondary" className="ml-2 text-xs">{participants.length}</Badge> : null}
              </TabsTrigger>
              {isApplyType ? (
                <TabsTrigger value="applications">
                  Applications
                  {pendingApps.length > 0 ? <Badge variant="secondary" className="ml-2 text-xs">{pendingApps.length}</Badge> : null}
                </TabsTrigger>
              ) : null}
            </TabsList>

            <TabsContent value="participants">
              {participants.length === 0 ? (
                <Card>
                  <CardContent className="flex flex-col items-center justify-center py-12">
                    <Users className="mb-3 h-10 w-10 text-muted-foreground/40" />
                    <p className="text-sm text-muted-foreground">No participants yet</p>
                  </CardContent>
                </Card>
              ) : (
                <div className="space-y-3">
                  {participants.map((participant) => (
                    <Card key={participant.id}>
                      <CardContent className="flex items-center gap-3 p-4">
                        <Avatar className="h-10 w-10">
                          <AvatarFallback>{(participant.display_name || participant.username)[0]}</AvatarFallback>
                        </Avatar>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium">{participant.display_name || participant.username}</p>
                          <p className="text-xs text-muted-foreground">
                            Joined{" "}
                            {new Date(participant.joined_at).toLocaleDateString("en-US", {
                              month: "short",
                              day: "numeric",
                              year: "numeric",
                            })}
                          </p>
                        </div>
                        <Badge variant="outline" className="border-primary/30 text-xs text-primary">
                          <CheckCircle2 className="mr-1 h-3 w-3" />
                          Confirmed
                        </Badge>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-destructive hover:text-destructive"
                          onClick={() => setRemoveId(participant.id)}
                        >
                          <UserMinus className="h-4 w-4" />
                        </Button>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </TabsContent>

            {isApplyType ? (
              <TabsContent value="applications">
                <div className="mb-4 flex gap-2">
                  {(["pending", "approved", "denied"] as const).map((status) => (
                    <Button
                      key={status}
                      variant={appFilter === status ? "default" : "outline"}
                      size="sm"
                      onClick={() => setAppFilter(status)}
                      className="capitalize"
                    >
                      {status}
                      <Badge variant="secondary" className="ml-1.5 text-xs">
                        {applications.filter((app) => app.status === status).length}
                      </Badge>
                    </Button>
                  ))}
                </div>

                {filteredApps.length === 0 ? (
                  <Card>
                    <CardContent className="flex flex-col items-center justify-center py-12">
                      <ClipboardList className="mb-3 h-10 w-10 text-muted-foreground/40" />
                      <p className="text-sm text-muted-foreground">No {appFilter} applications</p>
                    </CardContent>
                  </Card>
                ) : (
                  <div className="space-y-3">
                    {filteredApps.map((application) => (
                      <Card key={application.id}>
                        <CardContent className="p-4">
                          <div className="flex items-start gap-3">
                            <Avatar className="h-10 w-10">
                              <AvatarFallback>{(application.requester_display_name || application.requester_username)[0]}</AvatarFallback>
                            </Avatar>
                            <div className="min-w-0 flex-1">
                              <div className="mb-1 flex items-center gap-2">
                                <p className="text-sm font-medium">
                                  {application.requester_display_name || application.requester_username}
                                </p>
                                <Badge
                                  variant="outline"
                                  className={cn(
                                    "h-5 text-[10px]",
                                    application.status === "pending"
                                      ? "border-amber-300 text-amber-600"
                                      : application.status === "approved"
                                        ? "border-primary/30 text-primary"
                                        : "border-destructive/30 text-destructive",
                                  )}
                                >
                                  {application.status === "pending" ? <Clock className="mr-0.5 h-3 w-3" /> : null}
                                  {application.status === "approved" ? <CheckCircle2 className="mr-0.5 h-3 w-3" /> : null}
                                  {application.status === "denied" ? <XCircle className="mr-0.5 h-3 w-3" /> : null}
                                  {application.status}
                                </Badge>
                              </div>
                              {application.message ? (
                                <p className="mb-2 line-clamp-2 text-sm text-muted-foreground">{application.message}</p>
                              ) : null}
                              <p className="text-xs text-muted-foreground">
                                Applied{" "}
                                {new Date(application.created_at).toLocaleDateString("en-US", {
                                  month: "short",
                                  day: "numeric",
                                })}
                              </p>
                            </div>
                            {application.status === "pending" ? (
                              <div className="flex gap-1.5">
                                <Button size="sm" className="h-8 text-xs" onClick={() => void handleDecision(application.id, "approve")}>
                                  Approve
                                </Button>
                                <Button size="sm" variant="outline" className="h-8 text-xs" onClick={() => void handleDecision(application.id, "deny")}>
                                  Reject
                                </Button>
                              </div>
                            ) : null}
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                )}
              </TabsContent>
            ) : null}
          </Tabs>

          {trip.status !== "cancelled" ? (
            <div className="mt-10 rounded-lg border border-destructive/30 p-5">
              <div className="mb-2 flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-destructive" />
                <h3 className="font-semibold text-destructive">Danger Zone</h3>
              </div>
              <p className="mb-4 text-sm text-muted-foreground">
                Cancelling a trip will notify all participants. This action cannot be undone.
              </p>
              <Button variant="destructive" size="sm" onClick={() => setCancelOpen(true)}>
                Cancel Trip
              </Button>
            </div>
          ) : null}
        </div>
      </main>
      <Footer />

      <Dialog open={removeId != null} onOpenChange={() => setRemoveId(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              Remove Participant
            </DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Are you sure you want to remove this participant? They will be notified.
          </p>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setRemoveId(null)}>Cancel</Button>
            <Button variant="destructive" onClick={() => void handleRemoveParticipant()}>Remove</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={cancelOpen} onOpenChange={setCancelOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              Cancel Trip
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              This will cancel the trip and notify all {participants.length} participant{participants.length === 1 ? "" : "s"}.
            </p>
            <Textarea
              placeholder="Reason for cancellation (required)"
              value={cancelReason}
              onChange={(event) => setCancelReason(event.target.value)}
              rows={3}
            />
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <CheckCircle2 className="h-3.5 w-3.5" />
              Participants will be notified with your reason
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setCancelOpen(false)}>Keep Trip</Button>
            <Button variant="destructive" onClick={() => void handleCancelTrip()}>Confirm Cancel</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={messageOpen} onOpenChange={setMessageOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Send className="h-5 w-5 text-primary" />
              Message Participants
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Send a message to all {participants.length} participant{participants.length === 1 ? "" : "s"}.
            </p>
            <Textarea
              placeholder="Type your message..."
              value={messageText}
              onChange={(event) => setMessageText(event.target.value)}
              rows={4}
            />
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setMessageOpen(false)}>Cancel</Button>
            <Button onClick={() => void handleMessage()}>
              <Send className="mr-1.5 h-4 w-4" />
              Send Message
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
