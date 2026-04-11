/**
 * ReviewModal override — same UI as lovable/src/components/ReviewModal.tsx but
 * actually POSTs the review to the Django backend instead of just showing a
 * toast stub.
 */
import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Star, Camera, ArrowLeft, ArrowRight, Check, X, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { apiPost } from "@/lib/api";
import type { TripData } from "@/types/api";

const POSITIVE_TAGS = [
  "Well organized", "Great people", "Worth the money",
  "Amazing itinerary", "Good vibes", "Helpful host",
];
const NEGATIVE_TAGS = [
  "Poor planning", "Miscommunication", "Not worth the price",
  "Felt rushed", "Safety concerns", "Uncomfortable stay",
];

interface ReviewModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  trip: TripData;
}

const ReviewModal = ({ open, onOpenChange, trip }: ReviewModalProps) => {
  const [step, setStep] = useState(0);
  const [rating, setRating] = useState(0);
  const [hoverRating, setHoverRating] = useState(0);
  const [loved, setLoved] = useState("");
  const [improve, setImprove] = useState("");
  const [travelAgain, setTravelAgain] = useState<"Yes" | "Maybe" | "No" | "">("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [photos, setPhotos] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const toggleTag = (tag: string) => {
    setSelectedTags(prev =>
      prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]
    );
  };

  const handleSubmit = async () => {
    const cfg = window.TAPNE_RUNTIME_CONFIG;
    const body = [loved, improve, selectedTags.join(", ")]
      .filter(Boolean)
      .join("\n\n");
    const headline = loved.slice(0, 160);

    setSubmitting(true);
    try {
      await apiPost(`${cfg.api.trip_review}${trip.id}/review/`, {
        rating,
        body,
        headline,
      });
      toast.success("Thanks for sharing your experience ❤️");
      onOpenChange(false);
      resetForm();
    } catch {
      toast.error("Could not save your review. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const resetForm = () => {
    setStep(0);
    setRating(0);
    setLoved("");
    setImprove("");
    setTravelAgain("");
    setSelectedTags([]);
    setPhotos([]);
  };

  const ratingLabels = ["", "Poor", "Fair", "Good", "Great", "Amazing"];
  const totalSteps = 4;
  const currentProgress = step + 1;

  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) resetForm(); }}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader className="sr-only">
          <DialogTitle>Share your trip review</DialogTitle>
          <DialogDescription>
            Rate your trip and describe what worked well and what could be improved.
          </DialogDescription>
        </DialogHeader>
        {/* Progress */}
        <div className="flex gap-1.5 mb-2">
          {Array.from({ length: totalSteps }).map((_, i) => (
            <div key={i} className={cn("h-1 flex-1 rounded-full transition-colors", i < currentProgress ? "bg-primary" : "bg-muted")} />
          ))}
        </div>

        {/* Step 0: Rating */}
        {step === 0 && (
          <div className="space-y-6 py-2">
            <div className="text-center">
              <h3 className="text-lg font-semibold text-foreground">How was your overall experience?</h3>
              <p className="text-xs text-muted-foreground mt-1">Don't overthink it — just your gut feeling</p>
            </div>
            <div className="flex justify-center gap-2">
              {[1, 2, 3, 4, 5].map(s => (
                <button key={s} onMouseEnter={() => setHoverRating(s)} onMouseLeave={() => setHoverRating(0)}
                  onClick={() => setRating(s)} className="transition-transform hover:scale-110">
                  <Star className={cn("h-10 w-10 transition-colors", (hoverRating || rating) >= s ? "fill-yellow-400 text-yellow-400" : "text-muted-foreground/30")} />
                </button>
              ))}
            </div>
            {rating > 0 && <p className="text-center text-sm font-medium text-primary">{ratingLabels[rating]}</p>}
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => onOpenChange(false)} className="flex-1">Cancel</Button>
              <Button onClick={() => setStep(1)} disabled={rating === 0} className="flex-1">Continue <ArrowRight className="ml-1.5 h-4 w-4" /></Button>
            </div>
          </div>
        )}

        {/* Step 1: Feedback */}
        {step === 1 && (
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <label className="text-sm font-medium">What did you love the most? *</label>
              <Textarea rows={3} value={loved} onChange={e => setLoved(e.target.value)} placeholder="The people, the places, the vibe..." />
              <p className="text-xs text-muted-foreground">{loved.length < 10 ? `${10 - loved.length} more chars needed` : "✓"}</p>
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">What could have been better? <span className="text-xs text-muted-foreground">(optional)</span></label>
              <Textarea rows={2} value={improve} onChange={e => setImprove(e.target.value)} placeholder="Anything you'd improve..." />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Would you travel with this group again?</label>
              <div className="flex gap-2">
                {(["Yes", "Maybe", "No"] as const).map(opt => (
                  <Button key={opt} variant={travelAgain === opt ? "default" : "outline"} size="sm" onClick={() => setTravelAgain(opt)} className="flex-1">{opt}</Button>
                ))}
              </div>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep(0)} className="flex-1"><ArrowLeft className="mr-1.5 h-4 w-4" /> Back</Button>
              <Button onClick={() => setStep(2)} disabled={loved.length < 10} className="flex-1">Continue <ArrowRight className="ml-1.5 h-4 w-4" /></Button>
            </div>
          </div>
        )}

        {/* Step 2: Tags */}
        {step === 2 && (
          <div className="space-y-4 py-2">
            <h3 className="text-lg font-semibold text-center">Quick tags</h3>
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Positive</p>
              <div className="flex flex-wrap gap-2">
                {POSITIVE_TAGS.map(tag => (
                  <Badge key={tag} variant={selectedTags.includes(tag) ? "default" : "outline"} className="cursor-pointer transition-colors" onClick={() => toggleTag(tag)}>{tag}</Badge>
                ))}
              </div>
            </div>
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Could improve</p>
              <div className="flex flex-wrap gap-2">
                {NEGATIVE_TAGS.map(tag => (
                  <Badge key={tag} variant={selectedTags.includes(tag) ? "destructive" : "outline"} className="cursor-pointer transition-colors" onClick={() => toggleTag(tag)}>{tag}</Badge>
                ))}
              </div>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep(1)} className="flex-1"><ArrowLeft className="mr-1.5 h-4 w-4" /> Back</Button>
              <Button onClick={() => setStep(3)} className="flex-1">Continue <ArrowRight className="ml-1.5 h-4 w-4" /></Button>
            </div>
          </div>
        )}

        {/* Step 3: Photos + Summary + Submit */}
        {step === 3 && (
          <div className="space-y-5 py-2">
            <div>
              <div className="flex items-center gap-2 mb-3">
                <Camera className="h-5 w-5 text-muted-foreground" />
                <div>
                  <h3 className="text-sm font-semibold">Add photos <span className="text-xs font-normal text-muted-foreground">(optional)</span></h3>
                </div>
              </div>
              <div className="flex gap-3 flex-wrap">
                {photos.map((url, i) => (
                  <div key={i} className="relative h-16 w-16">
                    <img src={url} alt="" className="h-full w-full rounded-lg object-cover" />
                    <button onClick={() => setPhotos(prev => prev.filter((_, idx) => idx !== i))} className="absolute -right-1 -top-1 rounded-full bg-destructive p-0.5"><X className="h-3 w-3 text-white" /></button>
                  </div>
                ))}
                <label className="flex h-16 w-16 cursor-pointer items-center justify-center rounded-lg border-2 border-dashed border-border hover:border-primary/50">
                  <Camera className="h-5 w-5 text-muted-foreground" />
                  <input type="file" accept="image/*" className="hidden" onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (!file) return;
                    const reader = new FileReader();
                    reader.onload = () => setPhotos(prev => [...prev, reader.result as string]);
                    reader.readAsDataURL(file);
                    e.target.value = "";
                  }} />
                </label>
              </div>
            </div>

            <div className="rounded-lg border p-4 space-y-3 text-sm">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Review Summary</p>
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">Rating:</span>
                <div className="flex">{[1, 2, 3, 4, 5].map(s => <Star key={s} className={cn("h-4 w-4", s <= rating ? "fill-yellow-400 text-yellow-400" : "text-muted-foreground/30")} />)}</div>
              </div>
              <div><span className="text-muted-foreground">Loved:</span> <span>{loved}</span></div>
              {improve && <div><span className="text-muted-foreground">Improve:</span> <span>{improve}</span></div>}
              {travelAgain && <div><span className="text-muted-foreground">Travel again:</span> <span>{travelAgain}</span></div>}
              {selectedTags.length > 0 && (
                <div className="flex flex-wrap gap-1">{selectedTags.map(t => <Badge key={t} variant="outline" className="text-xs">{t}</Badge>)}</div>
              )}
            </div>

            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep(2)} className="flex-1"><ArrowLeft className="mr-1.5 h-4 w-4" /> Back</Button>
              <Button onClick={handleSubmit} className="flex-1" disabled={submitting}>
                {submitting ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Check className="mr-1.5 h-4 w-4" />}
                Post Review
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default ReviewModal;
