import type { TripData } from "@/types/api";
import ApplicationModal from "@/components/ApplicationModal";
import OriginalBookingModal from "../../../lovable/src/components/BookingModal";

interface BookingModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  trip: TripData;
}

export default function BookingModal(props: BookingModalProps) {
  if (props.trip.access_type === "apply") {
    return <ApplicationModal open={props.open} onOpenChange={props.onOpenChange} trip={props.trip} />;
  }
  return <OriginalBookingModal {...props} />;
}
