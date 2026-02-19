import { useState, useRef, useCallback, useEffect } from "react";
import { Mic, Square, FileText, Send, Trash2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { transcribeAudio } from "@/services/api";

type RecorderState = "idle" | "recording" | "recorded" | "transcribing";

interface AudioRecorderProps {
  onTranscription: (text: string) => void;
  onSendAudio?: (blob: Blob) => void;
  disabled?: boolean;
}

export function AudioRecorder({ onTranscription, onSendAudio, disabled }: AudioRecorderProps) {
  const [state, setState] = useState<RecorderState>("idle");
  const [duration, setDuration] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const audioBlobRef = useRef<Blob | null>(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
        mediaRecorderRef.current.stop();
      }
    };
  }, []);

  const startRecording = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      // Prefer webm/opus, fallback to whatever is available
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
          ? "audio/webm"
          : "";

      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = () => {
        // Stop all tracks to release the microphone
        stream.getTracks().forEach((t) => t.stop());

        const blob = new Blob(chunksRef.current, {
          type: mimeType || "audio/webm",
        });
        audioBlobRef.current = blob;
        setState("recorded");
      };

      mediaRecorderRef.current = recorder;
      recorder.start(250); // Collect data every 250ms
      setState("recording");
      setDuration(0);

      timerRef.current = setInterval(() => {
        setDuration((d) => d + 1);
      }, 1000);
    } catch (err) {
      setError("No se pudo acceder al microfono");
      setState("idle");
    }
  }, []);

  const stopRecording = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
      mediaRecorderRef.current.stop();
    }
  }, []);

  const handleTranscribe = useCallback(async () => {
    if (!audioBlobRef.current) return;
    setState("transcribing");
    setError(null);
    try {
      const result = await transcribeAudio(audioBlobRef.current);
      onTranscription(result.text);
      // Reset after successful transcription
      audioBlobRef.current = null;
      setState("idle");
      setDuration(0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Transcripcion fallida");
      setState("recorded");
    }
  }, [onTranscription]);

  const handleSendAudio = useCallback(() => {
    if (!audioBlobRef.current || !onSendAudio) return;
    onSendAudio(audioBlobRef.current);
    audioBlobRef.current = null;
    setState("idle");
    setDuration(0);
    setError(null);
  }, [onSendAudio]);

  const handleDiscard = useCallback(() => {
    audioBlobRef.current = null;
    setState("idle");
    setDuration(0);
    setError(null);
  }, []);

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  // Idle state: just the mic button
  if (state === "idle") {
    return (
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={startRecording}
        disabled={disabled}
        className="text-muted-foreground hover:text-primary shrink-0"
        title="Grabar audio"
      >
        <Mic className="w-5 h-5" />
      </Button>
    );
  }

  // Recording state: pulsing indicator + stop button
  if (state === "recording") {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 bg-red-500/10 rounded-full border border-red-500/30">
        <div className="w-2.5 h-2.5 bg-red-500 rounded-full animate-pulse" />
        <span className="text-sm text-red-400 font-mono tabular-nums min-w-[3ch]">
          {formatTime(duration)}
        </span>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={stopRecording}
          className="h-7 w-7 text-red-400 hover:text-red-300 hover:bg-red-500/20"
          title="Detener"
        >
          <Square className="w-4 h-4" />
        </Button>
      </div>
    );
  }

  // Recorded / Transcribing state: action buttons
  return (
    <div className="flex items-center gap-1.5">
      {error && (
        <span className="text-xs text-destructive max-w-[120px] truncate" title={error}>
          {error}
        </span>
      )}
      <span className="text-xs text-muted-foreground font-mono">{formatTime(duration)}</span>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={handleTranscribe}
        disabled={state === "transcribing"}
        className="h-7 w-7 text-primary hover:text-primary/80"
        title="Transcribir a texto"
      >
        {state === "transcribing" ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <FileText className="w-4 h-4" />
        )}
      </Button>
      {onSendAudio && (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={handleSendAudio}
          disabled={state === "transcribing"}
          className="h-7 w-7 text-green-500 hover:text-green-400"
          title="Enviar audio"
        >
          <Send className="w-4 h-4" />
        </Button>
      )}
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={handleDiscard}
        disabled={state === "transcribing"}
        className="h-7 w-7 text-muted-foreground hover:text-destructive"
        title="Descartar"
      >
        <Trash2 className="w-4 h-4" />
      </Button>
    </div>
  );
}
