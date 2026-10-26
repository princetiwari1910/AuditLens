import { useState, useRef, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom';
import {
  Upload,
  Video,
  Mic,
  Square,
  Trash2,
  Play,
  Pause,
  AlertCircle,
  FileCheck,
  CheckCircle2,
  Sparkles,
  ArrowLeft,
  Loader2,
  Info,
} from 'lucide-react';
import { createAudit, getTemplate, uploadVoiceNote } from '../api/client';
import type { Template } from '../api/types';
import Disclaimer from '../components/Disclaimer';
import { formatTimestamp } from '../utils/formatters';

const MAX_UPLOAD_MB = 200;
const ALLOWED_TYPES = ['video/mp4', 'video/quicktime', 'video/webm', 'image/jpeg', 'image/png'];

export default function Capture() {
  const { templateId } = useParams<{ templateId: string }>();
  const [searchParams] = useSearchParams();
  const customRuleQuery = searchParams.get('rule') || '';
  const navigate = useNavigate();

  const [template, setTemplate] = useState<Template | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Voice recording state
  const [isRecording, setIsRecording] = useState(false);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [recordSeconds, setRecordSeconds] = useState(0);
  const [micPermissionDenied, setMicPermissionDenied] = useState(false);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    if (templateId && templateId !== 'custom') {
      getTemplate(templateId).then(setTemplate).catch(console.error);
    }
  }, [templateId]);

  // Clean up object URLs on unmount
  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [previewUrl, audioUrl]);

  function handleFileSelected(selectedFile: File) {
    setValidationError(null);

    // Type validation
    if (!ALLOWED_TYPES.includes(selectedFile.type) && !selectedFile.name.match(/\.(mp4|mov|webm|jpg|jpeg|png)$/i)) {
      setValidationError(`Unsupported format "${selectedFile.type}". Please upload MP4, MOV, WebM, or JPG/PNG.`);
      return;
    }

    // Size validation
    const sizeMb = selectedFile.size / (1024 * 1024);
    if (sizeMb > MAX_UPLOAD_MB) {
      setValidationError(`File size (${sizeMb.toFixed(1)} MB) exceeds ${MAX_UPLOAD_MB} MB limit.`);
      return;
    }

    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(selectedFile);
    setPreviewUrl(URL.createObjectURL(selectedFile));
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  }

  // ── Voice Recording Helpers ──────────────────────────────────────────────────
  async function startRecording() {
    setMicPermissionDenied(false);
    audioChunksRef.current = [];

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      recorder.onstop = () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        setAudioBlob(blob);
        if (audioUrl) URL.revokeObjectURL(audioUrl);
        setAudioUrl(URL.createObjectURL(blob));
        stream.getTracks().forEach((track) => track.stop());
      };

      recorder.start();
      setIsRecording(true);
      setRecordSeconds(0);
      timerRef.current = setInterval(() => {
        setRecordSeconds((s) => s + 1);
      }, 1000);
    } catch (err: any) {
      console.warn('Microphone access denied:', err);
      setMicPermissionDenied(true);
    }
  }

  function stopRecording() {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      if (timerRef.current) clearInterval(timerRef.current);
    }
  }

  function deleteRecording() {
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    setAudioBlob(null);
    setAudioUrl(null);
    setRecordSeconds(0);
  }

  // ── Submit Audit ────────────────────────────────────────────────────────────
  async function handleSubmit() {
    if (!file) return;

    try {
      setIsSubmitting(true);
      const fd = new FormData();
      fd.append('video', file);

      if (templateId === 'custom' || customRuleQuery) {
        fd.append('custom_rules', JSON.stringify([customRuleQuery || 'Ensure emergency exit is clear']));
      } else if (templateId) {
        fd.append('template_id', templateId);
      }

      const res = await createAudit(fd);

      // Upload voice note if recorded
      if (audioBlob) {
        try {
          await uploadVoiceNote(res.id, audioBlob, 2.0);
        } catch (vnErr) {
          console.warn('Voice note upload failed:', vnErr);
        }
      }

      navigate(`/audits/${res.id}/processing`);
    } catch (err: any) {
      setValidationError(err.message || 'Failed to initiate audit.');
    } finally {
      setIsSubmitting(false);
    }
  }

  const isVideo = file?.type.startsWith('video/') || file?.name.match(/\.(mp4|mov|webm)$/i);

  return (
    <div className="min-h-screen bg-[var(--color-bg)] pb-16">
      {/* Header */}
      <header className="border-b border-[var(--color-border)] bg-[var(--color-surface)] px-6 py-4">
        <div className="mx-auto flex max-w-4xl items-center justify-between">
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Checklists
          </Link>
          <span className="text-xs font-mono text-[var(--color-text-secondary)]">
            Step 1: Walkthrough Footage Capture
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-8 space-y-8">
        {/* Title & Selected Checklist */}
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="rounded-md bg-blue-100 px-2 py-0.5 text-xs font-mono font-semibold text-blue-800 dark:bg-blue-950 dark:text-blue-200">
              {template ? template.name : customRuleQuery ? 'Custom Rule Audit' : 'Safety Audit'}
            </span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-[var(--color-text)]">
            Upload Walkthrough Video or Photos
          </h1>
          <p className="text-sm text-[var(--color-text-secondary)]">
            {customRuleQuery
              ? `Inspecting for: "${customRuleQuery}"`
              : template?.description || 'Upload inspection footage for AI compliance analysis.'}
          </p>
        </div>

        {/* Drag and Drop Uploader */}
        <div className="space-y-4">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragOver(true);
            }}
            onDragLeave={() => setIsDragOver(false)}
            onDrop={handleDrop}
            className={`relative flex flex-col items-center justify-center rounded-2xl border-2 border-dashed p-8 text-center transition-all ${
              isDragOver
                ? 'border-[var(--color-accent)] bg-blue-50/50 dark:bg-blue-950/20'
                : 'border-[var(--color-border)] bg-[var(--color-surface)] hover:border-slate-400'
            }`}
          >
            <input
              type="file"
              accept="video/mp4,video/quicktime,video/webm,image/jpeg,image/png"
              onChange={(e) => e.target.files?.[0] && handleFileSelected(e.target.files[0])}
              className="absolute inset-0 opacity-0 cursor-pointer"
            />

            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-blue-50 text-[var(--color-accent)] dark:bg-blue-950/60 mb-3">
              <Upload className="h-7 w-7" />
            </div>

            <p className="font-semibold text-sm text-[var(--color-text)] mb-1">
              Drag and drop your walkthrough video here, or <span className="text-[var(--color-accent)] underline">browse files</span>
            </p>
            <p className="text-xs text-[var(--color-text-secondary)]">
              MP4, MOV, WebM, or JPEG/PNG up to {MAX_UPLOAD_MB} MB
            </p>
          </div>

          {validationError && (
            <div className="flex items-center gap-2 rounded-lg bg-red-50 p-3 text-xs text-red-800 border border-red-200 dark:bg-red-950 dark:text-red-200">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{validationError}</span>
            </div>
          )}

          {/* Media Preview Card */}
          {file && previewUrl && (
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 shadow-sm space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Video className="h-4 w-4 text-[var(--color-accent)]" />
                  <span className="font-medium text-xs text-[var(--color-text)] truncate max-w-xs">
                    {file.name}
                  </span>
                  <span className="font-mono text-xs text-[var(--color-text-secondary)]">
                    ({(file.size / (1024 * 1024)).toFixed(1)} MB)
                  </span>
                </div>
                <button
                  onClick={() => {
                    setFile(null);
                    setPreviewUrl(null);
                  }}
                  className="text-xs text-red-600 hover:underline"
                >
                  Remove
                </button>
              </div>

              {isVideo ? (
                <video
                  src={previewUrl}
                  controls
                  className="w-full max-h-72 rounded-lg bg-black object-contain"
                />
              ) : (
                <img
                  src={previewUrl}
                  alt="Walkthrough preview"
                  className="w-full max-h-72 rounded-lg object-contain bg-slate-900"
                />
              )}
            </div>
          )}
        </div>

        {/* Voice Note Recorder */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Mic className="h-4 w-4 text-[var(--color-accent)]" />
              <h3 className="font-semibold text-sm text-[var(--color-text)]">
                Auditor Voice Note (Optional)
              </h3>
            </div>
            {audioBlob && (
              <span className="inline-flex items-center gap-1 text-xs font-mono text-green-600 font-medium">
                <CheckCircle2 className="h-3.5 w-3.5" /> Memo Attached
              </span>
            )}
          </div>

          <p className="text-xs text-[var(--color-text-secondary)]">
            Record spoken auditor context (e.g. "Checked extinguisher pressure gauge, expiry verified").
            Audio is transcribed and linked to nearest timestamps.
          </p>

          {micPermissionDenied && (
            <div className="rounded-lg bg-amber-50 p-3 text-xs text-amber-900 border border-amber-200">
              Microphone permission denied. Check your browser settings if you wish to record voice memos.
            </div>
          )}

          <div className="flex items-center gap-3 pt-1">
            {!isRecording ? (
              <button
                type="button"
                onClick={startRecording}
                className="inline-flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-2 text-xs font-medium text-[var(--color-text)] hover:bg-[var(--color-bg-secondary)]"
              >
                <Mic className="h-4 w-4 text-red-500" />
                <span>{audioBlob ? 'Re-record Memo' : 'Record Voice Note'}</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={stopRecording}
                className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-3.5 py-2 text-xs font-medium text-white hover:bg-red-700 animate-pulse"
              >
                <Square className="h-4 w-4" />
                <span>Stop Recording ({formatTimestamp(recordSeconds)})</span>
              </button>
            )}

            {audioUrl && !isRecording && (
              <div className="flex items-center gap-2">
                <audio ref={audioPlayerRef} src={audioUrl} onEnded={() => setIsPlayingAudio(false)} className="hidden" />
                <button
                  type="button"
                  onClick={() => {
                    if (audioPlayerRef.current) {
                      if (isPlayingAudio) {
                        audioPlayerRef.current.pause();
                        setIsPlayingAudio(false);
                      } else {
                        audioPlayerRef.current.play();
                        setIsPlayingAudio(true);
                      }
                    }
                  }}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-text)]"
                >
                  {isPlayingAudio ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                  <span>{isPlayingAudio ? 'Pause' : 'Play'}</span>
                </button>
                <button
                  type="button"
                  onClick={deleteRecording}
                  className="rounded-lg p-1.5 text-red-600 hover:bg-red-50 dark:hover:bg-red-950"
                  aria-label="Delete recording"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Tips Panel */}
        <div className="rounded-xl border border-blue-100 bg-blue-50/60 p-5 dark:border-blue-900/40 dark:bg-blue-950/30 space-y-2.5">
          <div className="flex items-center gap-2 text-blue-900 dark:text-blue-200">
            <Info className="h-4 w-4 shrink-0" />
            <span className="font-semibold text-xs uppercase tracking-wider">
              Walkthrough Filming Guidelines
            </span>
          </div>
          <ul className="grid sm:grid-cols-2 gap-2 text-xs text-blue-950/80 dark:text-blue-300/80 list-disc list-inside">
            <li>Keep emergency exit signs and extinguishers fully in frame.</li>
            <li>Place an A4 paper sheet on the floor in bottlenecks for optical scale.</li>
            <li>Walk slowly and pan steadily; avoid rapid rotation or motion blur.</li>
            <li>Avoid capturing employee faces to respect workplace privacy.</li>
          </ul>
        </div>

        {/* Start Button & Disclaimer */}
        <div className="space-y-4 pt-2">
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!file || isSubmitting}
            className="w-full flex items-center justify-center gap-2 rounded-xl bg-[var(--color-accent)] py-3.5 px-6 font-semibold text-white shadow-md transition-all hover:bg-[var(--color-accent-hover)] disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] focus:ring-offset-2"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="h-5 w-5 animate-spin" />
                <span>Uploading Walkthrough & Initiating Agent...</span>
              </>
            ) : (
              <>
                <Sparkles className="h-5 w-5" />
                <span>Start Evidence-Backed Audit</span>
              </>
            )}
          </button>

          <Disclaimer />
        </div>
      </main>
    </div>
  );
}
