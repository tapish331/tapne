import { useRef } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import TripCard from "@frontend/components/TripCard";
import { FrontendTrip } from "@frontend/lib/api";

type Props = {
  title: string;
  trips: FrontendTrip[];
  emptyLabel?: string;
};

export default function TripCarousel({ title, trips, emptyLabel }: Props) {
  const scrollerRef = useRef<HTMLDivElement | null>(null);

  const scroll = (direction: "left" | "right") => {
    const el = scrollerRef.current;
    if (!el) return;
    const delta = el.clientWidth * 0.8 * (direction === "left" ? -1 : 1);
    el.scrollBy({ left: delta, behavior: "smooth" });
  };

  if (trips.length === 0) {
    return (
      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold text-foreground">{title}</h2>
        <p className="text-sm text-muted-foreground">{emptyLabel ?? "No trips here yet."}</p>
      </section>
    );
  }

  return (
    <section className="mb-8">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-foreground">{title}</h2>
        <div className="flex gap-1">
          <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => scroll("left")}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => scroll("right")}>
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <div
        ref={scrollerRef}
        className="flex gap-4 overflow-x-auto scroll-smooth pb-2 [&::-webkit-scrollbar]:hidden"
        style={{ scrollbarWidth: "none" }}
      >
        {trips.map((trip) => (
          <div key={trip.id} className="w-[280px] shrink-0 sm:w-[320px]">
            <TripCard trip={trip} />
          </div>
        ))}
      </div>
    </section>
  );
}
