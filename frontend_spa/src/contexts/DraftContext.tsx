import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { apiGet, apiPost, apiPatch, apiDelete } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import type { TripData, MyTripsResponse } from "@/types/api";

type DraftFormData = Record<string, any>;
type PersistedTripData = TripData & { draft_form_data?: Record<string, any> };

export interface TripDraft {
  id: number;
  title: string;
  destination: string;
  category: string;
  summary: string;
  startDate: string;
  endDate: string;
  status: "draft" | "published";
  lastEditedAt: string;
  createdAt: string;
  formData: DraftFormData;
}

function isRecord(value: unknown): value is Record<string, any> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function mapServerContactPreferenceToUi(value: unknown): string[] {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "email") return ["Email"];
  if (normalized === "whatsapp") return ["WhatsApp"];
  if (normalized === "phone") return ["WhatsApp"];
  return ["In-app chat"];
}

function mapContactPreferencesToServer(value: unknown): string {
  if (!Array.isArray(value)) return "in_app";
  if (value.includes("WhatsApp")) return "whatsapp";
  if (value.includes("Email")) return "email";
  return "in_app";
}

function sanitizeDraftFormData(formData: DraftFormData): DraftFormData {
  const sanitized: DraftFormData = { ...formData };

  if (typeof sanitized.heroImage === "string" && sanitized.heroImage.startsWith("data:image/")) {
    delete sanitized.heroImage;
  }

  if (Array.isArray(sanitized.galleryImages)) {
    sanitized.galleryImages = sanitized.galleryImages.filter(
      (item: unknown) => typeof item === "string" && !item.startsWith("data:image/"),
    );
  }

  return sanitized;
}

function tripDataToDraft(t: PersistedTripData): TripDraft {
  const persistedFormData = isRecord(t.draft_form_data) ? t.draft_form_data : {};

  return {
    id: t.id,
    title: t.title || "",
    destination: t.destination || "",
    category: t.trip_type || "",
    summary: t.summary || "",
    startDate: t.starts_at || "",
    endDate: t.ends_at || "",
    status: t.is_draft || t.is_published === false ? "draft" : "published",
    lastEditedAt: new Date().toISOString(),
    createdAt: new Date().toISOString(),
    formData: {
      ...persistedFormData,
      description: persistedFormData.description ?? t.description ?? "",
      heroImage: t.banner_image_url || persistedFormData.heroImage || null,
      accessType: persistedFormData.accessType ?? t.access_type ?? "open",
      currency: persistedFormData.currency ?? t.currency ?? "INR",
      totalPrice:
        persistedFormData.totalPrice
        ?? t.price_per_person?.toString()
        ?? t.total_trip_price?.toString()
        ?? "",
      earlyBirdPrice: persistedFormData.earlyBirdPrice ?? t.early_bird_price?.toString() ?? "",
      paymentTerms: persistedFormData.paymentTerms ?? t.payment_terms ?? "full",
      totalSeats: persistedFormData.totalSeats ?? t.total_seats?.toString() ?? "",
      minSeats: persistedFormData.minSeats ?? t.minimum_seats?.toString() ?? "",
      bookingCloseDate: persistedFormData.bookingCloseDate ?? t.booking_closes_at ?? "",
      highlights: persistedFormData.highlights ?? t.highlights ?? [],
      itinerary: persistedFormData.itinerary ?? (t.itinerary_days || []).map((day, index) => ({
        id: `d${day.day_number ?? index + 1}`,
        title: day.title,
        description: day.description,
        isFlexible: day.is_flexible || false,
      })),
      includedItems: persistedFormData.includedItems ?? t.included_items ?? [],
      notIncludedItems: persistedFormData.notIncludedItems ?? t.not_included_items ?? [],
      thingsToCarry: persistedFormData.thingsToCarry ?? t.things_to_carry ?? [],
      suitableFor: persistedFormData.suitableFor ?? t.suitable_for ?? [],
      tripVibes: persistedFormData.tripVibes ?? t.trip_vibe ?? [],
      codeOfConduct: persistedFormData.codeOfConduct ?? t.code_of_conduct ?? "",
      generalPolicy: persistedFormData.generalPolicy ?? t.general_policies ?? "",
      cancellationPolicy: persistedFormData.cancellationPolicy ?? t.cancellation_policy ?? "",
      faqs:
        persistedFormData.faqs
        ?? (t.faqs || []).map((faq, index) => ({
          id: `f${index}`,
          question: faq.question,
          answer: faq.answer,
        })),
      paymentMethod: persistedFormData.paymentMethod ?? t.payment_method ?? "direct_contact",
      paymentDetails: persistedFormData.paymentDetails ?? t.payment_details ?? "",
      hosts: persistedFormData.hosts ?? t.co_hosts ?? "",
      contactPreferences:
        persistedFormData.contactPreferences
        ?? mapServerContactPreferenceToUi((t as Record<string, unknown>).contact_preference),
    },
  };
}

function draftToServerPayload(updates: Partial<TripDraft>): Record<string, any> {
  const payload: Record<string, any> = {};

  if (updates.title !== undefined) payload.title = updates.title;
  if (updates.destination !== undefined) payload.destination = updates.destination;
  if (updates.category !== undefined) payload.trip_type = updates.category;
  if (updates.summary !== undefined) payload.summary = updates.summary;
  if (updates.startDate !== undefined) payload.starts_at = updates.startDate;
  if (updates.endDate !== undefined) payload.ends_at = updates.endDate;

  if (updates.formData) {
    const formData = updates.formData;
    payload.draft_form_data = sanitizeDraftFormData(formData);

    if (formData.description !== undefined) payload.description = formData.description;
    if (formData.accessType !== undefined) payload.access_type = formData.accessType;
    if (formData.currency !== undefined) payload.currency = formData.currency;
    if (formData.totalPrice !== undefined) {
      const normalizedPrice = formData.totalPrice ? Number(formData.totalPrice) : null;
      payload.price_per_person = normalizedPrice;
      payload.total_trip_price = normalizedPrice;
    }
    if (formData.earlyBirdPrice !== undefined) {
      payload.early_bird_price = formData.earlyBirdPrice ? Number(formData.earlyBirdPrice) : null;
    }
    if (formData.paymentTerms !== undefined) payload.payment_terms = formData.paymentTerms;
    if (formData.totalSeats !== undefined) payload.total_seats = formData.totalSeats ? Number(formData.totalSeats) : null;
    if (formData.minSeats !== undefined) payload.minimum_seats = formData.minSeats ? Number(formData.minSeats) : null;
    if (formData.bookingCloseDate !== undefined) payload.booking_closes_at = formData.bookingCloseDate;
    if (formData.highlights !== undefined) payload.highlights = formData.highlights;
    if (formData.itinerary !== undefined) {
      payload.itinerary_days = formData.itinerary.map((day: any, index: number) => ({
        day_number: index + 1,
        title: day.title,
        description: day.description,
        is_flexible: day.isFlexible || false,
      }));
    }
    if (formData.includedItems !== undefined) payload.included_items = formData.includedItems;
    if (formData.notIncludedItems !== undefined) payload.not_included_items = formData.notIncludedItems;
    if (formData.thingsToCarry !== undefined) payload.things_to_carry = formData.thingsToCarry;
    if (formData.suitableFor !== undefined) payload.suitable_for = formData.suitableFor;
    if (formData.tripVibes !== undefined) payload.trip_vibe = formData.tripVibes;
    if (formData.codeOfConduct !== undefined) payload.code_of_conduct = formData.codeOfConduct;
    if (formData.generalPolicy !== undefined) payload.general_policies = formData.generalPolicy;
    if (formData.cancellationPolicy !== undefined) payload.cancellation_policy = formData.cancellationPolicy;
    if (formData.faqs !== undefined) {
      payload.faqs = formData.faqs.map((faq: any) => ({ question: faq.question, answer: faq.answer }));
    }
    if (formData.paymentMethod !== undefined) payload.payment_method = formData.paymentMethod;
    if (formData.paymentDetails !== undefined) payload.payment_details = formData.paymentDetails;
    if (formData.medicalDeclaration !== undefined) {
      payload.medical_declaration_required = !!formData.medicalDeclaration;
    }
    if (formData.emergencyContact !== undefined) {
      payload.emergency_contact_required = !!formData.emergencyContact;
    }
    if (formData.contactPreferences !== undefined) {
      payload.contact_preference = mapContactPreferencesToServer(formData.contactPreferences);
    }
    if (formData.hosts !== undefined) payload.co_hosts = formData.hosts;
    if (typeof formData.heroImage === "string" && formData.heroImage.startsWith("data:image/")) {
      payload.banner_image_data = formData.heroImage;
    }
  }

  return payload;
}

interface DraftContextType {
  drafts: TripDraft[];
  createDraft: () => Promise<number>;
  updateDraft: (id: number, updates: Partial<TripDraft>) => void;
  deleteDraft: (id: number) => void;
  duplicateDraft: (id: number) => Promise<number>;
  getDraft: (id: number) => TripDraft | undefined;
  publishDraft: (id: number, currentFormData?: Record<string, any>) => Promise<void>;
  loading: boolean;
}

const DraftContext = createContext<DraftContextType | undefined>(undefined);

export const DraftProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [drafts, setDrafts] = useState<TripDraft[]>([]);
  const [loading, setLoading] = useState(false);
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const isAuthenticatedRef = useRef(isAuthenticated);

  useEffect(() => {
    isAuthenticatedRef.current = isAuthenticated;
  }, [isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated) {
      setDrafts([]);
      return;
    }

    const cfg = window.TAPNE_RUNTIME_CONFIG;
    setLoading(true);
    apiGet<MyTripsResponse>(cfg.api.my_trips)
      .then((data) => {
        setDrafts(data.trips.map((trip) => tripDataToDraft(trip as PersistedTripData)));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [isAuthenticated]);

  const createDraft = useCallback(async (): Promise<number> => {
    if (!isAuthenticatedRef.current) return 0;

    const cfg = window.TAPNE_RUNTIME_CONFIG;
    const data = await apiPost<{ draft: TripData }>(cfg.api.trip_drafts, { title: "", destination: "" });
    const newDraft = tripDataToDraft(data.draft as PersistedTripData);
    setDrafts((prev) => [newDraft, ...prev]);
    return newDraft.id;
  }, []);

  const updateDraft = useCallback((id: number, updates: Partial<TripDraft>) => {
    setDrafts((prev) =>
      prev.map((draft) => {
        if (draft.id !== id) return draft;

        const nextFormData =
          updates.formData !== undefined
            ? { ...draft.formData, ...updates.formData }
            : draft.formData;

        return {
          ...draft,
          ...updates,
          formData: nextFormData,
          lastEditedAt: new Date().toISOString(),
        };
      }),
    );

    const cfg = window.TAPNE_RUNTIME_CONFIG;
    const payload = draftToServerPayload(updates);
    if (Object.keys(payload).length > 0) {
      apiPatch(`${cfg.api.trip_drafts}${id}/`, payload).catch(() => {});
    }
  }, []);

  const deleteDraft = useCallback(async (id: number) => {
    const cfg = window.TAPNE_RUNTIME_CONFIG;
    try {
      await apiDelete(`${cfg.api.trip_drafts}${id}/`);
      setDrafts((prev) => prev.filter((draft) => draft.id !== id));
    } catch {}
  }, []);

  const duplicateDraft = useCallback(async (id: number): Promise<number> => {
    const original = drafts.find((draft) => draft.id === id);
    if (!original) return 0;

    const cfg = window.TAPNE_RUNTIME_CONFIG;
    const payload = draftToServerPayload(original);
    payload.title = original.title ? `Copy of ${original.title}` : "";
    const data = await apiPost<{ draft: TripData }>(cfg.api.trip_drafts, payload);
    const newDraft = tripDataToDraft(data.draft as PersistedTripData);
    setDrafts((prev) => [newDraft, ...prev]);
    return newDraft.id;
  }, [drafts]);

  const getDraft = useCallback((id: number) => drafts.find((draft) => draft.id === id), [drafts]);

  const publishDraft = useCallback(async (id: number, currentFormData?: Record<string, any>) => {
    const cfg = window.TAPNE_RUNTIME_CONFIG;

    if (currentFormData && Object.keys(currentFormData).length > 0) {
      const payload = draftToServerPayload({ formData: currentFormData } as Partial<TripDraft>);
      if (Object.keys(payload).length > 0) {
        await apiPatch(`${cfg.api.trip_drafts}${id}/`, payload);
      }
    }

    try {
      await apiPost(`${cfg.api.trip_drafts}${id}/publish/`, {});
    } catch (err: any) {
      throw new Error(err?.message || err?.error || "Could not publish trip");
    }

    setDrafts((prev) => prev.filter((draft) => draft.id !== id));
    navigate("/my-trips");
  }, [navigate]);

  return (
    <DraftContext.Provider
      value={{ drafts, createDraft, updateDraft, deleteDraft, duplicateDraft, getDraft, publishDraft, loading }}
    >
      {children}
    </DraftContext.Provider>
  );
};

export function useDrafts() {
  const ctx = useContext(DraftContext);
  if (!ctx) throw new Error("useDrafts must be used within DraftProvider");
  return ctx;
}
