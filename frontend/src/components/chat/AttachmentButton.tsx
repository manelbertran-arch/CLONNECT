import { useRef, useState } from "react";
import { Paperclip, X, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

const MAX_FILE_SIZE = 16 * 1024 * 1024; // 16MB (WhatsApp limit)

interface AttachmentButtonProps {
  onFileSelected: (file: File) => void;
  disabled?: boolean;
}

export function AttachmentButton({ onFileSelected, disabled }: AttachmentButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={() => inputRef.current?.click()}
        disabled={disabled}
        className="text-muted-foreground hover:text-primary shrink-0"
        title="Adjuntar archivo"
      >
        <Paperclip className="w-5 h-5" />
      </Button>
      <input
        ref={inputRef}
        type="file"
        accept="image/*,video/*,audio/*,.pdf,.doc,.docx"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) {
            if (file.size > MAX_FILE_SIZE) {
              alert("El archivo es demasiado grande (máx 16MB)");
              return;
            }
            onFileSelected(file);
            e.target.value = "";
          }
        }}
      />
    </>
  );
}

interface AttachmentPreviewProps {
  file: File;
  uploading: boolean;
  onRemove: () => void;
}

export function AttachmentPreview({ file, uploading, onRemove }: AttachmentPreviewProps) {
  const [previewUrl] = useState(() => {
    if (file.type.startsWith("image/")) return URL.createObjectURL(file);
    if (file.type.startsWith("video/")) return URL.createObjectURL(file);
    return null;
  });

  const isImage = file.type.startsWith("image/");
  const isVideo = file.type.startsWith("video/");

  return (
    <div className="flex items-center gap-2 p-2 bg-secondary/50 rounded-lg border border-border/50">
      {isImage && previewUrl && (
        <img src={previewUrl} alt="Preview" className="w-12 h-12 object-cover rounded" />
      )}
      {isVideo && previewUrl && (
        <video src={previewUrl} className="w-12 h-12 object-cover rounded" muted />
      )}
      {!isImage && !isVideo && (
        <div className="w-12 h-12 bg-muted rounded flex items-center justify-center text-xs text-muted-foreground">
          {file.name.split(".").pop()?.toUpperCase() || "FILE"}
        </div>
      )}
      <div className="flex-1 min-w-0">
        <p className="text-sm truncate">{file.name}</p>
        <p className="text-xs text-muted-foreground">
          {(file.size / 1024).toFixed(0)} KB
          {uploading && " — Subiendo..."}
        </p>
      </div>
      {uploading ? (
        <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
      ) : (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={onRemove}
          className="h-7 w-7 text-muted-foreground hover:text-destructive shrink-0"
        >
          <X className="w-4 h-4" />
        </Button>
      )}
    </div>
  );
}
