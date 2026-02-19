import { useState, useRef, useEffect, lazy, Suspense } from "react";
import { Smile } from "lucide-react";
import { Button } from "@/components/ui/button";

const Picker = lazy(() => import("@emoji-mart/react"));

interface EmojiPickerProps {
  onSelect: (emoji: string) => void;
  disabled?: boolean;
}

export function EmojiPicker({ onSelect, disabled }: EmojiPickerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const pickerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isOpen]);

  return (
    <div className="relative" ref={pickerRef}>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={() => setIsOpen(!isOpen)}
        disabled={disabled}
        className="text-muted-foreground hover:text-primary shrink-0"
        title="Emojis"
      >
        <Smile className="w-5 h-5" />
      </Button>

      {isOpen && (
        <div className="absolute bottom-12 left-0 z-50">
          <Suspense
            fallback={
              <div className="w-[352px] h-[435px] bg-popover rounded-lg border shadow-lg animate-pulse" />
            }
          >
            <Picker
              data={async () => (await import("@emoji-mart/data")).default}
              onEmojiSelect={(emoji: { native: string }) => {
                onSelect(emoji.native);
              }}
              theme="dark"
              locale="es"
              previewPosition="none"
              skinTonePosition="search"
              maxFrequentRows={2}
              perLine={8}
            />
          </Suspense>
        </div>
      )}
    </div>
  );
}
