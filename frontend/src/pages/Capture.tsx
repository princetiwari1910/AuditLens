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
  AlertTriangle,
  CheckCircle2,
  Sparkles,
  ArrowLeft,
  Loader2,
  Info,
} from 'lucide-react';
import { createAudit, getTemplate, uploadVoiceNote, compileTemplate } from '../api/client';
import type { Template } from '../api/types';
import Disclaimer from '../components/Disclaimer';
import { formatTimestamp } from '../utils/formatters';
import { validateConceptPrompt } from '../utils/conceptValidation';

export function updateRuleConcept(
  template: Template,
  ruleId: string,
  newConcept: string
): { updatedTemplate: Template; error: string | null } {
  const error = validateConceptPrompt(newConcept, ruleId);
  const updatedRules = template.rules.map((r) => {
    if (r.id === ruleId) {
      return {
        ...r,
        sam_prompts: [newConcept],
      };
    }
    return r;
  });
  return {
    updatedTemplate: {
      ...template,
      rules: updatedRules,
    },
    error,
  };
}

const MAX_UPLOAD_MB = 200;
const MAX_DURATION_S = 90;
const ALLOWED_TYPES = ['video/mp4', 'video/quicktime', 'video/webm', 'image/jpeg', 'image/png'];

export interface CaptureProps {
  initialCompiledTemplate?: Template | null;
  initialCompileWarnings?: string[];
  initialCompileErrors?: string[];
  initialHasConfirmedCompound?: boolean;
}

export default function Capture({
  initialCompiledTemplate,
  initialCompileWarnings,
  initialCompileErrors,
  initialHasConfirmedCompound,
}: CaptureProps = {}) {
  const { templateId = 'custom' } = useParams<{ templateId: string }>();
  const [searchParams] = useSearchParams();
  const customRuleQuery = searchParams.get('rule') || '';
  const navigate = useNavigate();

  const [template, setTemplate] = useState<Template | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [videoDuration, setVideoDuration] = useState<number | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Natural Language Checklist Compiler state (WP12)
  const [customText, setCustomText] = useState(customRuleQuery || '');
  const [compiledTemplate, setCompiledTemplate] = useState<Template | null>(initialCompiledTemplate ?? null);
  const [compileErrors, setCompileErrors] = useState<string[]>(initialCompileErrors ?? []);
  const [compileWarnings, setCompileWarnings] = useState<string[]>(initialCompileWarnings ?? []);
  const [hasConfirmedCompound, setHasConfirmedCompound] = useState(initialHasConfirmedCompound ?? false);
  const [isCompiling, setIsCompiling] = useState(false);

  // Voice recording state
  const [isRecording, setIsRecording] = useState(false);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [recordSeconds, setRecordSeconds] = useState(0);
  const [micPermissionDenied, setMicPermissionDenied] = useState(false);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
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
    setVideoDuration(null);

    // Type validation
    if (!ALLOWED_TYPES.includes(selectedFile.type) && !selectedFile.name.match(/\.(mp4|mov|webm|jpg|jpeg|png)$/i)) {
      setValidationError(`Unsupported format "${selectedFile.type || 'unknown'}". Please upload MP4, MOV, WebM, or JPG/PNG.`);
      return;
    }

    // Size validation
    const sizeMb = selectedFile.size / (1024 * 1024);
    if (sizeMb > MAX_UPLOAD_MB) {
      setValidationError(`File size (${sizeMb.toFixed(1)} MB) exceeds maximum allowed limit of ${MAX_UPLOAD_MB} MB.`);
      return;
    }

    const isVid = selectedFile.type.startsWith('video/') || selectedFile.name.match(/\.(mp4|mov|webm)$/i);
    const objectUrl = URL.createObjectURL(selectedFile);

    if (isVid) {
      // Validate video decodability and 90-second duration limit
      const tempVideo = document.createElement('video');
      tempVideo.preload = 'metadata';
      tempVideo.onloadedmetadata = () => {
        const dur = tempVideo.duration;
        setVideoDuration(dur);
        if (dur > MAX_DURATION_S) {
          setValidationError(
            `Walkthrough video exceeds the 90-second limit (${Math.round(dur)}s). Please trim or upload a clip under ${MAX_DURATION_S}s.`
          );
          setFile(null);
          setPreviewUrl(null);
          URL.revokeObjectURL(objectUrl);
        } else {
          setFile(selectedFile);
          setPreviewUrl(objectUrl);
        }
      };
      tempVideo.onerror = () => {
        setValidationError('The selected video file appears corrupt or cannot be decoded.');
        setFile(null);
        setPreviewUrl(null);
        URL.revokeObjectURL(objectUrl);
      };
      tempVideo.src = objectUrl;
    } else {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      setFile(selectedFile);
      setPreviewUrl(objectUrl);
    }
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

  async function handleCompile() {
    if (!customText.trim()) return;
    setIsCompiling(true);
    setCompileErrors([]);
    setCompileWarnings([]);
    setHasConfirmedCompound(false);
    try {
      const res = await compileTemplate(customText.trim());
      setCompiledTemplate(res.template);
      setCompileErrors([]);
      setCompileWarnings(res.warnings || []);
    } catch (err: any) {
      if (err?.data?.detail?.errors) {
        setCompileErrors(err.data.detail.errors);
      } else if (err?.message) {
        setCompileErrors([err.message]);
      } else {
        setCompileErrors(['Failed to compile checklist: Invalid format']);
      }
      setCompiledTemplate(null);
    } finally {
      setIsCompiling(false);
    }
  }

  const conceptErrorsByRuleId: Record<string, string | null> = {};
  if (compiledTemplate) {
    for (const r of compiledTemplate.rules) {
      const prompt = r.sam_prompts?.[0] ?? '';
      conceptErrorsByRuleId[r.id] = validateConceptPrompt(prompt, r.id);
    }
  }
  const hasConceptError = Object.values(conceptErrorsByRuleId).some(Boolean);

  function handleConceptChange(ruleId: string, newConcept: string) {
    if (!compiledTemplate) return;
    const { updatedTemplate } = updateRuleConcept(compiledTemplate, ruleId, newConcept);
    setCompiledTemplate(updatedTemplate);
  }

  // ── Submit Audit ────────────────────────────────────────────────────────────
  async function handleSubmit() {
    if (!file) return;

    if (hasConceptError) {
      setValidationError('Cannot start audit: one or more SAM concepts are invalid. Templates must use plain noun phrases only.');
      return;
    }

    if (templateId === 'custom' && compiledTemplate && compileWarnings.length > 0 && !hasConfirmedCompound) {
      setValidationError('Compound or negated statement: split it into separate rules or confirm before saving.');
      return;
    }

    try {
      setIsSubmitting(true);
      const fd = new FormData();
      fd.append('video', file);

      if (compiledTemplate) {
        fd.append('custom_rules', JSON.stringify(compiledTemplate.rules));
      } else if (templateId === 'custom' || customRuleQuery) {
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
      if (err.name === 'TypeError' || err.message?.includes('Failed to fetch')) {
        setValidationError('Network drop: Failed to connect to AuditLens backend. Please check server connection.');
      } else {
        setValidationError(err.message || 'Failed to initiate audit.');
      }
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
              : template?.description || 'Upload inspection footage for AI pre-inspection analysis.'}
          </p>
        </div>

        {/* Natural Language Checklist Compiler (WP12) */}
        {templateId === 'custom' && (
          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-purple-500" />
                <h3 className="text-sm font-bold text-[var(--color-text)]">
                  Natural Language Checklist Compiler
                </h3>
              </div>
              <span className="rounded-full bg-purple-500/10 px-2 py-0.5 text-[10px] font-bold text-purple-700 dark:text-purple-300 border border-purple-500/20">
                Experimental · Human-Reviewed
              </span>
            </div>

            <p className="text-xs text-[var(--color-text-secondary)]">
              Type or paste your checklist in plain English. SAM 3.1 prompts must be plain noun phrases (no conjunctions, negation, or spatial words).
            </p>

            <div className="space-y-2">
              <textarea
                rows={3}
                value={customText}
                onChange={(e) => {
                  setCustomText(e.target.value);
                  setHasConfirmedCompound(false);
                  setCompileWarnings([]);
                }}
                placeholder="e.g.&#10;- Verify fire extinguisher is mounted on wall&#10;- Ensure exit signs are illuminated&#10;- Check hallway is clear of storage boxes"
                className="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-3 text-xs text-[var(--color-text)] focus:border-[var(--color-accent)] focus:outline-none"
              />

              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={handleCompile}
                  disabled={isCompiling || !customText.trim()}
                  className="inline-flex items-center gap-2 rounded-xl bg-purple-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-purple-700 transition-colors disabled:opacity-50 cursor-pointer"
                >
                  {isCompiling ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                  <span>Compile Rules & Validate Concepts</span>
                </button>
              </div>
            </div>

            {/* Inline Concept Validation Errors */}
            {compileErrors.length > 0 && (
              <div className="rounded-xl border border-rose-300 dark:border-rose-900 bg-rose-50 dark:bg-rose-950/40 p-3.5 text-xs text-rose-800 dark:text-rose-300 space-y-1.5">
                <div className="font-bold flex items-center gap-1.5 text-rose-900 dark:text-rose-200">
                  <AlertCircle className="h-4 w-4 text-rose-600" />
                  <span>Concept Validation Failed:</span>
                </div>
                <ul className="list-disc list-inside space-y-1 text-[11px] font-mono">
                  {compileErrors.map((err, idx) => (
                    <li key={idx}>{err}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Warning for compound or negated statements */}
            {compileWarnings.length > 0 && (
              <div className="rounded-xl border border-amber-300 dark:border-amber-900 bg-amber-50 dark:bg-amber-950/40 p-3.5 text-xs text-amber-900 dark:text-amber-200 space-y-2">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 font-bold text-amber-900 dark:text-amber-200">
                    <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0" />
                    <span>Compound or negated statement: split it into separate rules or confirm</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setHasConfirmedCompound(!hasConfirmedCompound)}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold cursor-pointer border transition-colors ${
                      hasConfirmedCompound
                        ? 'bg-emerald-600 text-white border-emerald-600 hover:bg-emerald-700'
                        : 'bg-amber-600 text-white border-amber-600 hover:bg-amber-700'
                    }`}
                  >
                    {hasConfirmedCompound ? (
                      <>
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        <span>Statement Confirmed</span>
                      </>
                    ) : (
                      <span>Confirm Statement</span>
                    )}
                  </button>
                </div>
                {!hasConfirmedCompound ? (
                  <p className="text-[11px] text-amber-800 dark:text-amber-300">
                    Your rule statement contains conjunctions or negation. Please edit to split into separate rules, or confirm this statement before saving.
                  </p>
                ) : (
                  <p className="text-[11px] text-emerald-800 dark:text-emerald-300">
                    Statement confirmed by user. You can proceed with saving or inspection.
                  </p>
                )}
              </div>
            )}

            {/* Compiled Template Preview */}
            {compiledTemplate && (
              <div className="rounded-xl border border-emerald-300 dark:border-emerald-900 bg-emerald-50 dark:bg-emerald-950/30 p-3.5 text-xs space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-emerald-900 dark:text-emerald-200 flex items-center gap-1.5">
                    <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                    <span>{`Compiled ${compiledTemplate.rules.length} Rule(s)`}</span>
                  </span>
                  <span className="font-mono text-[10px] text-emerald-700 dark:text-emerald-400 uppercase font-semibold">
                    Ready for Walkthrough
                  </span>
                </div>
                <div className="space-y-2">
                  {compiledTemplate.rules.map((r) => {
                    const conceptErr = conceptErrorsByRuleId[r.id];
                    return (
                      <div
                        key={r.id}
                        className="p-3 rounded-lg bg-[var(--color-surface)] border border-emerald-200 dark:border-emerald-800 text-xs space-y-2"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="space-y-1.5 flex-1">
                            <div className="flex items-baseline gap-2">
                              <span className="text-[10px] font-mono uppercase tracking-wider text-[var(--color-text-secondary)] font-bold shrink-0">
                                Condition:
                              </span>
                              <span className="font-medium text-[var(--color-text)]">
                                {(r as any).condition || r.title}
                              </span>
                            </div>

                            <div className="flex flex-col gap-1.5">
                              <div className="flex flex-wrap items-center gap-2">
                                <label
                                  htmlFor={`concept-input-${r.id}`}
                                  className="text-[10px] font-mono uppercase tracking-wider text-[var(--color-text-secondary)] font-bold shrink-0"
                                >
                                  SAM Concept:
                                </label>
                                <input
                                  id={`concept-input-${r.id}`}
                                  data-testid={`concept-input-${r.id}`}
                                  type="text"
                                  value={r.sam_prompts.join(', ')}
                                  onChange={(e) => handleConceptChange(r.id, e.target.value)}
                                  className={`font-mono text-[11px] font-semibold px-2 py-0.5 rounded border ${
                                    conceptErr
                                      ? 'border-rose-400 bg-rose-50 text-rose-800 dark:bg-rose-950/40 dark:text-rose-200'
                                      : 'border-indigo-200 dark:border-indigo-800 bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300'
                                  } focus:outline-none focus:ring-1 focus:ring-purple-500`}
                                />
                                {!conceptErr ? (
                                  <span className="rounded-full bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300 px-2 py-0.5 text-[10px] font-mono font-bold border border-emerald-300 dark:border-emerald-800 inline-flex items-center gap-1">
                                    <CheckCircle2 className="h-3 w-3 text-emerald-600 dark:text-emerald-400" />
                                    SAM concept valid
                                  </span>
                                ) : null}
                              </div>

                              {conceptErr && (
                                <div
                                  data-testid={`concept-error-${r.id}`}
                                  className="text-[11px] text-rose-600 dark:text-rose-400 font-medium flex items-center gap-1"
                                >
                                  <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                                  <span>{conceptErr}</span>
                                </div>
                              )}
                            </div>
                          </div>

                          <span className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-[10px] font-mono text-slate-700 dark:text-slate-300 shrink-0">
                            {r.type}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

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
                    ({(file.size / (1024 * 1024)).toFixed(1)} MB{videoDuration !== null ? ` · ${Math.round(videoDuration)}s` : ''})
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
          {validationError && (
            <div className="rounded-xl border border-rose-300 dark:border-rose-900 bg-rose-50 dark:bg-rose-950/40 p-3 text-xs text-rose-800 dark:text-rose-300 flex items-center gap-2">
              <AlertCircle className="h-4 w-4 shrink-0 text-rose-600" />
              <span>{validationError}</span>
            </div>
          )}

          {templateId === 'custom' && compiledTemplate && compileWarnings.length > 0 && !hasConfirmedCompound && (
            <p className="text-xs text-amber-700 dark:text-amber-400 flex items-center gap-1.5 justify-center">
              <AlertTriangle className="h-4 w-4" />
              <span>Compound or negated statement requires confirmation or editing before saving.</span>
            </p>
          )}

          {hasConceptError && (
            <p className="text-xs text-rose-600 dark:text-rose-400 flex items-center gap-1.5 justify-center">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>SAM concept contains invalid words (conjunction or negation): must be a plain noun phrase.</span>
            </p>
          )}

          <button
            type="button"
            onClick={handleSubmit}
            disabled={
              !file ||
              isSubmitting ||
              (templateId === 'custom' && !!compiledTemplate && compileWarnings.length > 0 && !hasConfirmedCompound) ||
              hasConceptError
            }
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
