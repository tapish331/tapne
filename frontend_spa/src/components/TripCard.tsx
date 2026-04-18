import { Link } from "react-router-dom";
import { Calendar, IndianRupee, MapPin, Users } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { FrontendTrip } from "@frontend/lib/api";
import { formatCurrency, formatDateRange } from "@frontend/lib/format";

export default function TripCard({ trip }: { trip: FrontendTrip }) {
  const priceValue = trip.price_per_person ?? trip.total_trip_price;
  const isCompleted = trip.status === "completed";
  return (
    <Link to={`/trips/${trip.id}`}>
      <Card className="group h-full overflow-hidden transition-shadow hover:shadow-lg">
        <div className="relative aspect-[16/10] overflow-hidden">
          <img
            src={trip.banner_image_url || "/placeholder.svg"}
            alt={trip.title}
            className={`h-full w-full object-cover transition-transform duration-300 group-hover:scale-105 ${
              isCompleted ? "opacity-80" : ""
            }`}
          />
          {trip.trip_type_label ? (
            <Badge className="absolute left-3 top-3 bg-primary/90 text-primary-foreground">
              {trip.trip_type_label}
            </Badge>
          ) : null}
          {isCompleted ? (
            <Badge className="absolute right-3 top-3 bg-muted text-muted-foreground">
              Completed
            </Badge>
          ) : null}
        </div>
        <CardContent className="space-y-2 p-4">
          <div>
            <h3 className="text-lg font-semibold leading-tight text-foreground transition-colors group-hover:text-primary">
              {trip.title}
            </h3>
            {trip.summary ? <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{trip.summary}</p> : null}
          </div>
          <div className="flex items-center gap-1 text-sm text-muted-foreground">
            <MapPin className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">{trip.destination || "Destination announced soon"}</span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-sm text-muted-foreground">
            <div className="flex items-center gap-1 truncate">
              <Calendar className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{formatDateRange(trip.starts_at, trip.ends_at)}</span>
            </div>
            <div className="flex items-center gap-1 truncate">
              <IndianRupee className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{formatCurrency(priceValue, trip.currency || "INR")}</span>
            </div>
          </div>
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-1 text-sm text-muted-foreground">
              <Users className="h-3.5 w-3.5 text-primary" />
              <span>{trip.spots_left_label || trip.group_size_label || "Limited spots"}</span>
            </div>
            <div className="text-sm text-muted-foreground">
              {trip.host_display_name || trip.host_username || "Tapne host"}
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
