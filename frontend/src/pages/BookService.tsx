import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { Calendar, Clock, CheckCircle2, Loader2, ArrowLeft, Video, User, Mail, Phone } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const API_URL = import.meta.env.VITE_API_URL || "https://web-production-9f69.up.railway.app";

interface ServiceInfo {
  id: string;
  title: string;
  description: string;
  duration_minutes: number;
  price: number;
  platform: string;
}

interface CreatorInfo {
  id: string;
  name: string;
}

interface Slot {
  start_time: string;
  end_time: string;
  available: boolean;
}

interface BookingConfirmation {
  id: string;
  service: string;
  date: string;
  start_time: string;
  end_time: string;
  meeting_url: string;
}

type BookingStep = "loading" | "select-date" | "select-time" | "form" | "confirming" | "confirmed" | "error";

const WEEKDAYS = ["Lu", "Ma", "Mi", "Ju", "Vi", "Sa", "Do"];
const MONTHS = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];

export default function BookService() {
  const { creatorId, serviceId } = useParams<{ creatorId: string; serviceId: string }>();

  const [step, setStep] = useState<BookingStep>("loading");
  const [error, setError] = useState<string>("");

  // Data states
  const [service, setService] = useState<ServiceInfo | null>(null);
  const [creator, setCreator] = useState<CreatorInfo | null>(null);
  const [availableDates, setAvailableDates] = useState<string[]>([]);
  const [activeDays, setActiveDays] = useState<number[]>([]);
  const [slots, setSlots] = useState<Slot[]>([]);

  // Selection states
  const [currentMonth, setCurrentMonth] = useState(new Date().getMonth() + 1);
  const [currentYear, setCurrentYear] = useState(new Date().getFullYear());
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<Slot | null>(null);

  // Form states
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");

  // Confirmation
  const [booking, setBooking] = useState<BookingConfirmation | null>(null);

  // Load service info on mount
  useEffect(() => {
    async function loadServiceInfo() {
      try {
        const response = await fetch(`${API_URL}/booking/${creatorId}/public/${serviceId}`);
        const data = await response.json();

        if (data.status === "ok") {
          setService(data.service);
          setCreator(data.creator);
          await loadAvailableDates(currentMonth, currentYear);
          setStep("select-date");
        } else {
          setError(data.detail || "Service not found");
          setStep("error");
        }
      } catch (err) {
        setError("Could not load service information");
        setStep("error");
      }
    }

    if (creatorId && serviceId) {
      loadServiceInfo();
    }
  }, [creatorId, serviceId]);

  // Load available dates for a month
  async function loadAvailableDates(month: number, year: number) {
    try {
      const response = await fetch(
        `${API_URL}/booking/${creatorId}/public/${serviceId}/available-dates?month=${month}&year=${year}`
      );
      const data = await response.json();

      if (data.status === "ok") {
        setAvailableDates(data.available_dates || []);
        setActiveDays(data.active_days_of_week || []);
      }
    } catch (err) {
      console.error("Error loading available dates:", err);
    }
  }

  // Load slots for a selected date
  async function loadSlots(dateStr: string) {
    try {
      const response = await fetch(
        `${API_URL}/booking/${creatorId}/slots?date_str=${dateStr}&service_id=${serviceId}`
      );
      const data = await response.json();

      if (data.status === "ok") {
        setSlots(data.slots || []);
      }
    } catch (err) {
      console.error("Error loading slots:", err);
      setSlots([]);
    }
  }

  // Handle month navigation
  function goToPreviousMonth() {
    let newMonth = currentMonth - 1;
    let newYear = currentYear;
    if (newMonth < 1) {
      newMonth = 12;
      newYear -= 1;
    }
    setCurrentMonth(newMonth);
    setCurrentYear(newYear);
    loadAvailableDates(newMonth, newYear);
  }

  function goToNextMonth() {
    let newMonth = currentMonth + 1;
    let newYear = currentYear;
    if (newMonth > 12) {
      newMonth = 1;
      newYear += 1;
    }
    setCurrentMonth(newMonth);
    setCurrentYear(newYear);
    loadAvailableDates(newMonth, newYear);
  }

  // Handle date selection
  function handleDateSelect(dateStr: string) {
    setSelectedDate(dateStr);
    setSelectedSlot(null);
    loadSlots(dateStr);
  }

  // Handle slot selection
  function handleSlotSelect(slot: Slot) {
    setSelectedSlot(slot);
    setStep("form");
  }

  // Handle booking submission
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    if (!selectedDate || !selectedSlot || !name || !email) {
      return;
    }

    setStep("confirming");

    try {
      const response = await fetch(`${API_URL}/booking/${creatorId}/reserve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          service_id: serviceId,
          date: selectedDate,
          start_time: selectedSlot.start_time,
          name,
          email,
          phone
        })
      });

      const data = await response.json();

      if (data.status === "ok") {
        setBooking(data.booking);
        setStep("confirmed");
      } else {
        setError(data.detail || "Could not complete booking");
        setStep("error");
      }
    } catch (err) {
      setError("Could not complete booking");
      setStep("error");
    }
  }

  // Generate calendar grid
  function generateCalendarDays() {
    const firstDay = new Date(currentYear, currentMonth - 1, 1);
    const lastDay = new Date(currentYear, currentMonth, 0);
    const daysInMonth = lastDay.getDate();

    // Get day of week for first day (0 = Sunday, we want Monday = 0)
    let startDayOfWeek = firstDay.getDay() - 1;
    if (startDayOfWeek < 0) startDayOfWeek = 6;

    const days: { day: number; dateStr: string; available: boolean; isPast: boolean }[] = [];

    // Add empty cells for days before the first of the month
    for (let i = 0; i < startDayOfWeek; i++) {
      days.push({ day: 0, dateStr: "", available: false, isPast: true });
    }

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    // Add days of the month
    for (let d = 1; d <= daysInMonth; d++) {
      const dateStr = `${currentYear}-${String(currentMonth).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      const date = new Date(currentYear, currentMonth - 1, d);
      const isPast = date < today;
      const available = availableDates.includes(dateStr);

      days.push({ day: d, dateStr, available, isPast });
    }

    return days;
  }

  // Format date for display
  function formatDisplayDate(dateStr: string): string {
    const date = new Date(dateStr);
    return date.toLocaleDateString("es-ES", {
      weekday: "long",
      day: "numeric",
      month: "long"
    });
  }

  // Render loading state
  if (step === "loading") {
    return (
      <div className="min-h-screen bg-[#0d0d0d] flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-12 h-12 animate-spin text-primary mx-auto mb-4" />
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  // Render error state
  if (step === "error") {
    return (
      <div className="min-h-screen bg-[#0d0d0d] flex items-center justify-center p-4">
        <div className="bg-card border border-border rounded-2xl p-8 max-w-md w-full text-center">
          <div className="w-16 h-16 bg-destructive/10 rounded-full flex items-center justify-center mx-auto mb-4">
            <span className="text-3xl">:(</span>
          </div>
          <h1 className="text-xl font-semibold text-foreground mb-2">Oops!</h1>
          <p className="text-muted-foreground mb-6">{error}</p>
          <Button onClick={() => window.location.reload()}>
            Try Again
          </Button>
        </div>
      </div>
    );
  }

  // Render confirmation state
  if (step === "confirmed" && booking) {
    return (
      <div className="min-h-screen bg-[#0d0d0d] flex items-center justify-center p-4">
        <div className="bg-card border border-border rounded-2xl p-8 max-w-md w-full text-center">
          <div className="w-20 h-20 bg-green-500/10 rounded-full flex items-center justify-center mx-auto mb-6 animate-in zoom-in duration-300">
            <CheckCircle2 className="w-10 h-10 text-green-500" />
          </div>

          <h1 className="text-2xl font-bold text-foreground mb-2">Booking Confirmed!</h1>
          <p className="text-muted-foreground mb-6">
            We've sent you a confirmation email to <span className="text-foreground">{email}</span>
          </p>

          <div className="bg-muted/50 rounded-xl p-4 mb-6 text-left space-y-3">
            <div className="flex items-center gap-3">
              <Video className="w-5 h-5 text-primary" />
              <span className="text-foreground">{booking.service}</span>
            </div>
            <div className="flex items-center gap-3">
              <Calendar className="w-5 h-5 text-primary" />
              <span className="text-foreground">{formatDisplayDate(booking.date)}</span>
            </div>
            <div className="flex items-center gap-3">
              <Clock className="w-5 h-5 text-primary" />
              <span className="text-foreground">{booking.start_time} - {booking.end_time}</span>
            </div>
          </div>

          {booking.meeting_url && booking.meeting_url !== "Link will be sent before the call" && (
            <Button
              className="w-full mb-4"
              onClick={() => window.open(booking.meeting_url, "_blank")}
            >
              <Video className="w-4 h-4 mr-2" />
              Join Meeting
            </Button>
          )}

          <p className="text-sm text-muted-foreground">
            {booking.meeting_url === "Link will be sent before the call"
              ? "The meeting link will be sent to your email before the call."
              : "Add this to your calendar and we'll see you soon!"}
          </p>
        </div>
      </div>
    );
  }

  // Main booking flow
  return (
    <div className="min-h-screen bg-[#0d0d0d] py-8 px-4">
      {/* Header */}
      <div className="max-w-lg mx-auto mb-8 text-center">
        <div className="w-12 h-12 bg-primary/10 rounded-xl flex items-center justify-center mx-auto mb-4">
          <span className="text-2xl font-bold text-primary">C</span>
        </div>
        <h1 className="text-xl text-muted-foreground">
          Book a call with <span className="text-foreground font-semibold">{creator?.name || creatorId}</span>
        </h1>
      </div>

      {/* Main Card */}
      <div className="max-w-lg mx-auto bg-card border border-border rounded-2xl overflow-hidden">
        {/* Service Info */}
        <div className="p-6 border-b border-border">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 bg-primary/10 rounded-xl flex items-center justify-center shrink-0">
              <Video className="w-6 h-6 text-primary" />
            </div>
            <div className="flex-1">
              <h2 className="text-lg font-semibold text-foreground">{service?.title}</h2>
              {service?.description && (
                <p className="text-sm text-muted-foreground mt-1">{service.description}</p>
              )}
              <div className="flex items-center gap-4 mt-2 text-sm">
                <span className="flex items-center gap-1 text-muted-foreground">
                  <Clock className="w-4 h-4" />
                  {service?.duration_minutes} min
                </span>
                {service && service.price > 0 && (
                  <span className="text-primary font-medium">{service.price}€</span>
                )}
                {service?.price === 0 && (
                  <span className="text-green-500 font-medium">Free</span>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Form step - show booking form */}
        {step === "form" && selectedDate && selectedSlot && (
          <div className="p-6">
            <button
              onClick={() => setStep("select-date")}
              className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-4 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Change date/time
            </button>

            <div className="bg-muted/50 rounded-xl p-4 mb-6">
              <div className="flex items-center gap-3 text-foreground">
                <Calendar className="w-5 h-5 text-primary" />
                <span>{formatDisplayDate(selectedDate)}</span>
                <span className="text-muted-foreground">at</span>
                <span>{selectedSlot.start_time}</span>
              </div>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-2">
                  <User className="w-4 h-4 inline mr-2" />
                  Your name *
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  className="w-full bg-muted border border-border rounded-lg px-4 py-3 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="John Doe"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground mb-2">
                  <Mail className="w-4 h-4 inline mr-2" />
                  Email *
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="w-full bg-muted border border-border rounded-lg px-4 py-3 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="john@example.com"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground mb-2">
                  <Phone className="w-4 h-4 inline mr-2" />
                  Phone (optional)
                </label>
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="w-full bg-muted border border-border rounded-lg px-4 py-3 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="+34 600 000 000"
                />
              </div>

              <Button type="submit" className="w-full h-12 text-base">
                Confirm Booking
              </Button>
            </form>
          </div>
        )}

        {/* Confirming step */}
        {step === "confirming" && (
          <div className="p-12 text-center">
            <Loader2 className="w-12 h-12 animate-spin text-primary mx-auto mb-4" />
            <p className="text-muted-foreground">Confirming your booking...</p>
          </div>
        )}

        {/* Date/time selection */}
        {step === "select-date" && (
          <div className="p-6">
            {/* Calendar Header */}
            <div className="flex items-center justify-between mb-4">
              <button
                onClick={goToPreviousMonth}
                className="p-2 hover:bg-muted rounded-lg transition-colors text-muted-foreground hover:text-foreground"
              >
                <ArrowLeft className="w-5 h-5" />
              </button>
              <h3 className="text-lg font-semibold text-foreground">
                {MONTHS[currentMonth - 1]} {currentYear}
              </h3>
              <button
                onClick={goToNextMonth}
                className="p-2 hover:bg-muted rounded-lg transition-colors text-muted-foreground hover:text-foreground rotate-180"
              >
                <ArrowLeft className="w-5 h-5" />
              </button>
            </div>

            {/* Weekday headers */}
            <div className="grid grid-cols-7 gap-1 mb-2">
              {WEEKDAYS.map((day) => (
                <div key={day} className="text-center text-sm font-medium text-muted-foreground py-2">
                  {day}
                </div>
              ))}
            </div>

            {/* Calendar grid */}
            <div className="grid grid-cols-7 gap-1 mb-6">
              {generateCalendarDays().map((day, index) => (
                <button
                  key={index}
                  disabled={!day.available || day.day === 0}
                  onClick={() => day.available && handleDateSelect(day.dateStr)}
                  className={cn(
                    "aspect-square flex items-center justify-center rounded-lg text-sm font-medium transition-all",
                    day.day === 0 && "invisible",
                    day.isPast && "text-muted-foreground/30 cursor-not-allowed",
                    !day.isPast && !day.available && "text-muted-foreground/50 cursor-not-allowed",
                    day.available && "hover:bg-primary/10 text-foreground cursor-pointer",
                    selectedDate === day.dateStr && "bg-primary text-primary-foreground hover:bg-primary"
                  )}
                >
                  {day.day > 0 ? day.day : ""}
                </button>
              ))}
            </div>

            {/* Selected date slots */}
            {selectedDate && (
              <div className="border-t border-border pt-6">
                <h4 className="text-sm font-medium text-muted-foreground mb-3">
                  Available times for {formatDisplayDate(selectedDate)}
                </h4>

                {slots.length === 0 ? (
                  <p className="text-center text-muted-foreground py-4">
                    No available times for this date
                  </p>
                ) : (
                  <div className="grid grid-cols-3 gap-2">
                    {slots.map((slot) => (
                      <button
                        key={slot.start_time}
                        onClick={() => handleSlotSelect(slot)}
                        className={cn(
                          "py-3 px-4 rounded-lg border text-sm font-medium transition-all",
                          selectedSlot?.start_time === slot.start_time
                            ? "bg-primary text-primary-foreground border-primary"
                            : "border-border hover:border-primary text-foreground hover:bg-primary/10"
                        )}
                      >
                        {slot.start_time}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {!selectedDate && availableDates.length === 0 && (
              <p className="text-center text-muted-foreground py-4">
                No availability for this month. Try another month.
              </p>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="max-w-lg mx-auto mt-6 text-center">
        <p className="text-sm text-muted-foreground">
          Powered by <span className="text-primary font-medium">Clonnect</span>
        </p>
      </div>
    </div>
  );
}
