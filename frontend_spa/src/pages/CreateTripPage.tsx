import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Loader2, Save, Send } from "lucide-react";
import Footer from "@/components/Footer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import FrontendNavbar from "@frontend/components/FrontendNavbar";
import { ErrorState, LoadingState } from "@frontend/components/PageState";
import { FrontendTrip, JsonObject, apiDelete, apiGet, apiPatch, apiPost } from "@frontend/lib/api";
import { joinDelimitedText, splitDelimitedText } from "@frontend/lib/format";
import { useAuth } from "@frontend/context/AuthContext";

type DraftPayload = {
  ok: boolean;
  trip: FrontendTrip;
};

type TripFormState = {
  title: string;
  destination: string;
  summary: string;
  description: string;
  trip_type: string;
  starts_at: string;
  ends_at: string;
  booking_closes_at: string;
  total_seats: string;
  minimum_seats: string;
  price_per_person: string;
  total_trip_price: string;
  highlights: string;
  included_items: string;
  not_included_items: string;
  things_to_carry: string;
  suitable_for: string;
  trip_vibe: string;
  cancellation_policy: string;
  code_of_conduct: string;
};

const DEFAULT_FORM: TripFormState = {
  title: "",
  destination: "",
  summary: "",
  description: "",
  trip_type: "",
  starts_at: "",
  ends_at: "",
  booking_closes_at: "",
  total_seats: "",
  minimum_seats: "",
  price_per_person: "",
  total_trip_price: "",
  highlights: "",
  included_items: "",
  not_included_items: "",
  things_to_carry: "",
  suitable_for: "",
  trip_vibe: "",
  cancellation_policy: "",
  code_of_conduct: "",
};

export default function CreateTripPage() {
  const { ready, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const draftId = searchParams.get("draft");
  const [form, setForm] = useState<TripFormState>(DEFAULT_FORM);
  const [saving, setSaving] = useState(false);
  const [loadingDraft, setLoadingDraft] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    if (ready && !isAuthenticated) {
      navigate("/login");
    }
  }, [ready, isAuthenticated, navigate]);

  useEffect(() => {
    if (!draftId) {
      setForm(DEFAULT_FORM);
      return;
    }
    setLoadingDraft(true);
    apiGet<DraftPayload>(`/frontend-api/trips/drafts/${draftId}/`)
      .then((payload) => {
        setForm(fromTrip(payload.trip));
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoadingDraft(false));
  }, [draftId]);

  const completion = useMemo(() => {
    const fields = [
      form.title,
      form.destination,
      form.summary,
      form.starts_at,
      form.ends_at,
      form.total_seats,
      form.price_per_person || form.total_trip_price,
      form.highlights,
      form.included_items,
      form.cancellation_policy,
    ];
    return Math.round((fields.filter((value) => value.trim()).length / fields.length) * 100);
  }, [form]);

  function updateField<K extends keyof TripFormState>(key: K, value: TripFormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function saveDraft() {
    setSaving(true);
    setError("");
    setStatus("");
    try {
      const payload = toDraftPayload(form);
      if (draftId) {
        const response = await apiPatch<DraftPayload>(`/frontend-api/trips/drafts/${draftId}/`, payload);
        setForm(fromTrip(response.trip));
      } else {
        const response = await apiPost<DraftPayload>("/frontend-api/trips/drafts/", payload);
        setSearchParams(new URLSearchParams({ draft: String(response.trip.id) }), { replace: true });
        setForm(fromTrip(response.trip));
      }
      setStatus("Draft saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save draft.");
    } finally {
      setSaving(false);
    }
  }

  async function publishTrip() {
    setSaving(true);
    setError("");
    setStatus("");
    try {
      let activeDraftId = draftId;
      if (!activeDraftId) {
        const created = await apiPost<DraftPayload>("/frontend-api/trips/drafts/", toDraftPayload(form));
        activeDraftId = String(created.trip.id);
        setSearchParams(new URLSearchParams({ draft: activeDraftId }), { replace: true });
      } else {
        await apiPatch<DraftPayload>(`/frontend-api/trips/drafts/${activeDraftId}/`, toDraftPayload(form));
      }
      await apiPost(`/frontend-api/trips/drafts/${activeDraftId}/publish/`);
      navigate("/my-trips?tab=published");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to publish trip.");
    } finally {
      setSaving(false);
    }
  }

  async function deleteDraft() {
    if (!draftId) {
      setForm(DEFAULT_FORM);
      setStatus("Draft cleared.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await apiDelete(`/frontend-api/trips/drafts/${draftId}/`);
      setSearchParams(new URLSearchParams(), { replace: true });
      setForm(DEFAULT_FORM);
      setStatus("Draft deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete draft.");
    } finally {
      setSaving(false);
    }
  }

  if (!ready || loadingDraft) {
    return (
      <div className="flex min-h-screen flex-col">
        <FrontendNavbar />
        <main className="mx-auto flex w-full max-w-6xl flex-1 px-4 py-10">
          <LoadingState label="Loading trip editor..." />
        </main>
        <Footer />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      <FrontendNavbar />
      <main className="flex-1">
        <div className="mx-auto max-w-6xl px-4 py-8">
          <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <h1 className="text-3xl font-bold text-foreground">Create Trip</h1>
              <p className="mt-2 text-muted-foreground">
                Save live trip drafts to Django and publish them when they are ready for the public catalog.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <Badge variant="secondary">{completion}% complete</Badge>
              {draftId ? <Badge variant="outline">Draft #{draftId}</Badge> : null}
            </div>
          </div>

          {error ? <div className="mb-6"><ErrorState title="Trip editor unavailable" body={error} /></div> : null}
          {status ? <div className="mb-6 rounded-xl border bg-primary/5 px-4 py-3 text-sm text-primary">{status}</div> : null}

          <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle>Overview</CardTitle>
                </CardHeader>
                <CardContent className="grid gap-4 sm:grid-cols-2">
                  <Field label="Title">
                    <Input value={form.title} onChange={(event) => updateField("title", event.target.value)} />
                  </Field>
                  <Field label="Destination">
                    <Input value={form.destination} onChange={(event) => updateField("destination", event.target.value)} />
                  </Field>
                  <Field label="Trip type">
                    <Input value={form.trip_type} onChange={(event) => updateField("trip_type", event.target.value)} placeholder="trekking, coastal, wellness..." />
                  </Field>
                  <Field label="Summary" className="sm:col-span-2">
                    <Textarea rows={3} value={form.summary} onChange={(event) => updateField("summary", event.target.value)} />
                  </Field>
                  <Field label="Description" className="sm:col-span-2">
                    <Textarea rows={6} value={form.description} onChange={(event) => updateField("description", event.target.value)} />
                  </Field>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Schedule & Pricing</CardTitle>
                </CardHeader>
                <CardContent className="grid gap-4 sm:grid-cols-2">
                  <Field label="Starts at">
                    <Input type="datetime-local" value={form.starts_at} onChange={(event) => updateField("starts_at", event.target.value)} />
                  </Field>
                  <Field label="Ends at">
                    <Input type="datetime-local" value={form.ends_at} onChange={(event) => updateField("ends_at", event.target.value)} />
                  </Field>
                  <Field label="Booking closes at">
                    <Input type="datetime-local" value={form.booking_closes_at} onChange={(event) => updateField("booking_closes_at", event.target.value)} />
                  </Field>
                  <Field label="Total seats">
                    <Input value={form.total_seats} onChange={(event) => updateField("total_seats", event.target.value)} />
                  </Field>
                  <Field label="Minimum seats">
                    <Input value={form.minimum_seats} onChange={(event) => updateField("minimum_seats", event.target.value)} />
                  </Field>
                  <Field label="Price per person">
                    <Input value={form.price_per_person} onChange={(event) => updateField("price_per_person", event.target.value)} />
                  </Field>
                  <Field label="Total trip price">
                    <Input value={form.total_trip_price} onChange={(event) => updateField("total_trip_price", event.target.value)} />
                  </Field>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Trip content</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <Field label="Highlights (one per line)">
                    <Textarea rows={4} value={form.highlights} onChange={(event) => updateField("highlights", event.target.value)} />
                  </Field>
                  <Field label="Included items (one per line)">
                    <Textarea rows={4} value={form.included_items} onChange={(event) => updateField("included_items", event.target.value)} />
                  </Field>
                  <Field label="Not included items (one per line)">
                    <Textarea rows={4} value={form.not_included_items} onChange={(event) => updateField("not_included_items", event.target.value)} />
                  </Field>
                  <Field label="Things to carry (one per line)">
                    <Textarea rows={4} value={form.things_to_carry} onChange={(event) => updateField("things_to_carry", event.target.value)} />
                  </Field>
                  <Field label="Suitable for (comma or line separated)">
                    <Textarea rows={3} value={form.suitable_for} onChange={(event) => updateField("suitable_for", event.target.value)} />
                  </Field>
                  <Field label="Trip vibe (comma or line separated)">
                    <Textarea rows={3} value={form.trip_vibe} onChange={(event) => updateField("trip_vibe", event.target.value)} />
                  </Field>
                  <Field label="Cancellation policy">
                    <Textarea rows={4} value={form.cancellation_policy} onChange={(event) => updateField("cancellation_policy", event.target.value)} />
                  </Field>
                  <Field label="Code of conduct">
                    <Textarea rows={4} value={form.code_of_conduct} onChange={(event) => updateField("code_of_conduct", event.target.value)} />
                  </Field>
                </CardContent>
              </Card>
            </div>

            <aside className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Actions</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <Button className="w-full" variant="outline" disabled={saving} onClick={() => void saveDraft()}>
                    {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Save className="mr-1.5 h-4 w-4" />}
                    Save Draft
                  </Button>
                  <Button className="w-full" disabled={saving} onClick={() => void publishTrip()}>
                    {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Send className="mr-1.5 h-4 w-4" />}
                    Publish Trip
                  </Button>
                  <Button className="w-full" variant="ghost" disabled={saving} onClick={() => void deleteDraft()}>
                    Clear Draft
                  </Button>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Next step</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-sm text-muted-foreground">
                  <p>Save drafts any time. Publishing immediately moves the trip into your live hosted catalog.</p>
                  <Button variant="outline" className="w-full" asChild>
                    <Link to="/my-trips">Back to my trips</Link>
                  </Button>
                </CardContent>
              </Card>
            </aside>
          </div>
        </div>
      </main>
      <Footer />
    </div>
  );
}

function Field({
  label,
  children,
  className = "",
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`space-y-1.5 ${className}`.trim()}>
      <Label>{label}</Label>
      {children}
    </div>
  );
}

function fromTrip(trip: FrontendTrip): TripFormState {
  return {
    title: trip.title || "",
    destination: trip.destination || "",
    summary: trip.summary || "",
    description: trip.description_html || trip.description || "",
    trip_type: trip.trip_type || "",
    starts_at: toInputDateTime(trip.starts_at),
    ends_at: toInputDateTime(trip.ends_at),
    booking_closes_at: toInputDateTime(trip.booking_closes_at),
    total_seats: trip.total_seats ? String(trip.total_seats) : "",
    minimum_seats: trip.minimum_seats ? String(trip.minimum_seats) : "",
    price_per_person: trip.price_per_person ? String(trip.price_per_person) : "",
    total_trip_price: trip.total_trip_price ? String(trip.total_trip_price) : "",
    highlights: joinDelimitedText(trip.highlights),
    included_items: joinDelimitedText(trip.included_items),
    not_included_items: joinDelimitedText(trip.not_included_items),
    things_to_carry: joinDelimitedText(trip.things_to_carry),
    suitable_for: joinDelimitedText(trip.suitable_for),
    trip_vibe: joinDelimitedText(trip.trip_vibe),
    cancellation_policy: trip.cancellation_policy || "",
    code_of_conduct: trip.code_of_conduct || "",
  };
}

function toDraftPayload(form: TripFormState): JsonObject {
  return {
    title: form.title,
    destination: form.destination,
    summary: form.summary,
    description: form.description,
    trip_type: form.trip_type,
    starts_at: form.starts_at,
    ends_at: form.ends_at,
    booking_closes_at: form.booking_closes_at,
    total_seats: form.total_seats,
    minimum_seats: form.minimum_seats,
    price_per_person: form.price_per_person,
    total_trip_price: form.total_trip_price,
    highlights: splitDelimitedText(form.highlights),
    included_items: splitDelimitedText(form.included_items),
    not_included_items: splitDelimitedText(form.not_included_items),
    things_to_carry: splitDelimitedText(form.things_to_carry),
    suitable_for: splitDelimitedText(form.suitable_for),
    trip_vibe: splitDelimitedText(form.trip_vibe),
    cancellation_policy: form.cancellation_policy,
    code_of_conduct: form.code_of_conduct,
  };
}

function toInputDateTime(value: unknown): string {
  if (!value) {
    return "";
  }
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60_000);
  return local.toISOString().slice(0, 16);
}
