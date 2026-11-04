import { useState, useRef, useEffect } from 'react';
import { Play, Pause, RotateCcw, Volume2, VolumeX, AlertCircle, ChevronLeft, ChevronRight } from 'lucide-react';
import type { Finding } from '../api/types';
import OverlayCanvas from './OverlayCanvas';
import { formatTimestamp, getStatusMeta } from '../utils/formatters';

interface VideoWithMarkersProps {
  videoUrl: string;
  findings: Finding[];
  selectedFindingId: string | null;
  onSelectFinding: (findingId: string) => void;
}

export default function VideoWithMarkers({
  videoUrl,
  findings = [],
  selectedFindingId,
  onSelectFinding,
}: VideoWithMarkersProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(25);
  const [isMuted, setIsMuted] = useState(true);
  const [videoError, setVideoError] = useState<string | null>(null);

  // Clear video error state whenever videoUrl changes
  useEffect(() => {
    setVideoError(null);
  }, [videoUrl]);

  // Sync video time when user clicks a finding in the checklist
  useEffect(() => {
    if (selectedFindingId && videoRef.current) {
      const f = findings.find((item) => item.id === selectedFindingId);
      if (f && Math.abs(videoRef.current.currentTime - f.timestamp_s) > 0.5) {
        videoRef.current.currentTime = f.timestamp_s;
        setCurrentTime(f.timestamp_s);
      }
    }
  }, [selectedFindingId, findings]);

  function togglePlay() {
    if (!videoRef.current) return;
    if (isPlaying) {
      videoRef.current.pause();
      setIsPlaying(false);
    } else {
      videoRef.current.play();
      setIsPlaying(true);
    }
  }

  function handleSeek(e: React.ChangeEvent<HTMLInputElement>) {
    const val = parseFloat(e.target.value);
    setCurrentTime(val);
    if (videoRef.current) {
      videoRef.current.currentTime = val;
    }
  }

  function handleMarkerClick(finding: Finding) {
    if (videoRef.current) {
      videoRef.current.currentTime = finding.timestamp_s;
      setCurrentTime(finding.timestamp_s);
    }
    onSelectFinding(finding.id);
  }

  const sortedFindings = [...findings].sort((a, b) => a.timestamp_s - b.timestamp_s);
  const currentFindingIdx = sortedFindings.findIndex((f) => f.id === selectedFindingId);

  function jumpToFinding(idx: number) {
    if (idx >= 0 && idx < sortedFindings.length) {
      handleMarkerClick(sortedFindings[idx]);
    }
  }

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-950 overflow-hidden shadow-xl shadow-blue-950/20 print:hidden">
      {/* Top Camera Status Header */}
      <div className="flex items-center justify-between border-b border-slate-800/80 bg-slate-900/80 px-4 py-2 text-xs font-mono">
        <div className="flex items-center gap-2 text-cyan-400">
          <span className="h-2 w-2 rounded-full bg-cyan-400 animate-pulse" />
          <span className="font-bold tracking-wider uppercase text-[11px]">WALKTHROUGH FOOTAGE</span>
          <span className="text-slate-600">•</span>
          <span className="text-slate-400 text-[11px]">SAM 3.1 RETICLES &amp; SEGMENTATION</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-slate-400 font-mono">
            {findings.length} visual markers
          </span>
        </div>
      </div>

      {/* Video Display Area with Canvas Overlay */}
      <div className="relative aspect-video w-full bg-slate-950 flex items-center justify-center">
        {videoError && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-slate-950/95 p-6 text-center text-slate-200">
            <AlertCircle className="h-10 w-10 text-red-500 mb-2" />
            <p className="text-sm font-semibold text-white">Video Playback Error</p>
            <p className="text-xs text-slate-400 max-w-sm mt-1">{videoError}</p>
            <a
              href={videoUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700 transition-colors"
            >
              Open video URL directly
            </a>
          </div>
        )}

        <video
          ref={videoRef}
          src={videoUrl}
          muted={isMuted}
          playsInline
          onTimeUpdate={() => videoRef.current && setCurrentTime(videoRef.current.currentTime)}
          onLoadedMetadata={() => {
            console.log('[VideoPlayer] Loaded metadata:', {
              duration: videoRef.current?.duration,
              videoWidth: videoRef.current?.videoWidth,
              videoHeight: videoRef.current?.videoHeight,
              readyState: videoRef.current?.readyState,
              src: videoRef.current?.currentSrc || videoUrl,
            });
            setVideoError(null);
            if (videoRef.current) setDuration(videoRef.current.duration || 25);
          }}
          onCanPlay={() => {
            console.log('[VideoPlayer] onCanPlay readyState:', videoRef.current?.readyState);
            setVideoError(null);
          }}
          onEnded={() => setIsPlaying(false)}
          onError={(e) => {
            const target = e.currentTarget as HTMLVideoElement;
            const mediaErr = target?.error;
            const activeSrc = target?.currentSrc || target?.src || videoUrl;

            console.error('[VideoPlayer] <video> onError:', {
              code: mediaErr?.code,
              message: mediaErr?.message,
              src: activeSrc,
              videoUrlProp: videoUrl,
              readyState: target?.readyState,
              networkState: target?.networkState,
            });

            // Prevent setting error state too early or if src is unset/empty
            if (!videoUrl || !activeSrc || activeSrc === window.location.href) {
              console.warn('[VideoPlayer] Ignoring onError because src is empty or not yet set');
              return;
            }

            const codeDesc =
              mediaErr?.code === 1 ? 'Aborted' :
              mediaErr?.code === 2 ? 'Network error' :
              mediaErr?.code === 3 ? 'Decode error' :
              mediaErr?.code === 4 ? 'Format / codec not supported by browser' :
              'Unknown media error';

            setVideoError(`Playback error (code ${mediaErr?.code ?? 'N/A'}: ${codeDesc}${mediaErr?.message ? ` - ${mediaErr.message}` : ''})`);
          }}
          className="h-full w-full object-contain"
        />

        {/* Synchronized Letterbox Overlay Canvas */}
        <OverlayCanvas
          videoElement={videoRef.current}
          findings={findings}
          selectedFindingId={selectedFindingId}
          currentTime={currentTime}
        />
      </div>

      {/* Timeline Controls & Finding Markers */}
      <div className="bg-slate-900 p-4 space-y-3">
        {/* Timeline Bar with Markers */}
        <div className="relative flex items-center">
          <input
            type="range"
            min={0}
            max={duration || 25}
            step={0.1}
            value={currentTime}
            onChange={handleSeek}
            aria-label="Video scrubber"
            className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-[var(--color-accent)] z-10"
          />

          {/* Finding Markers Placed on Timeline */}
          {duration > 0 &&
            findings.map((f) => {
              const pct = Math.min(100, Math.max(0, (f.timestamp_s / duration) * 100));
              const meta = getStatusMeta(f.status);
              const isSelected = f.id === selectedFindingId;

              return (
                <button
                  key={f.id}
                  onClick={() => handleMarkerClick(f)}
                  title={`${f.rule_id} (${meta.label}) at ${formatTimestamp(f.timestamp_s)}`}
                  className={`absolute -top-1.5 -translate-x-1/2 z-20 h-5 w-5 rounded-full border-2 transition-transform hover:scale-125 focus:outline-none focus:ring-2 focus:ring-white ${
                    isSelected ? 'scale-125 ring-2 ring-white z-30' : ''
                  }`}
                  style={{
                    left: `${pct}%`,
                    backgroundColor: meta.colorHex,
                    borderColor: '#ffffff',
                  }}
                  aria-label={`Jump to ${f.rule_id}`}
                />
              );
            })}
        </div>

        {/* Playback Controls & Time Display */}
        <div className="flex items-center justify-between text-white text-xs">
          <div className="flex items-center gap-3">
            <button
              onClick={togglePlay}
              className="rounded-lg p-1.5 hover:bg-slate-800 transition-colors focus:outline-none focus:ring-1 focus:ring-slate-400"
              aria-label={isPlaying ? 'Pause' : 'Play'}
            >
              {isPlaying ? <Pause className="h-5 w-5" /> : <Play className="h-5 w-5" />}
            </button>

            <button
              onClick={() => {
                if (videoRef.current) {
                  videoRef.current.currentTime = 0;
                  setCurrentTime(0);
                }
              }}
              className="rounded-lg p-1.5 hover:bg-slate-800 transition-colors"
              aria-label="Restart video"
            >
              <RotateCcw className="h-4 w-4" />
            </button>

            <button
              onClick={() => setIsMuted(!isMuted)}
              className="rounded-lg p-1.5 hover:bg-slate-800 transition-colors"
              aria-label={isMuted ? 'Unmute' : 'Mute'}
            >
              {isMuted ? <VolumeX className="h-4 w-4 text-slate-400" /> : <Volume2 className="h-4 w-4" />}
            </button>

            <span className="font-mono text-slate-300">
              {formatTimestamp(currentTime)} / {formatTimestamp(duration)}
            </span>

            {/* Jump to Findings */}
            {sortedFindings.length > 0 && (
              <div className="hidden md:flex items-center gap-1 border-l border-slate-700 pl-3">
                <span className="text-[10px] text-slate-400 font-mono uppercase tracking-wider mr-1">
                  Findings:
                </span>
                <button
                  onClick={() => jumpToFinding(currentFindingIdx - 1)}
                  disabled={currentFindingIdx <= 0}
                  className="rounded px-1.5 py-1 bg-slate-800 hover:bg-slate-700 disabled:opacity-30 disabled:pointer-events-none transition-colors text-[10px] flex items-center gap-0.5"
                  title="Jump to previous finding"
                >
                  <ChevronLeft className="h-3 w-3" />
                  Prev
                </button>
                <span className="text-[10px] font-mono text-slate-300 px-1">
                  {currentFindingIdx >= 0 ? `${currentFindingIdx + 1}/${sortedFindings.length}` : `-/${sortedFindings.length}`}
                </span>
                <button
                  onClick={() => jumpToFinding(currentFindingIdx + 1)}
                  disabled={currentFindingIdx >= sortedFindings.length - 1}
                  className="rounded px-1.5 py-1 bg-slate-800 hover:bg-slate-700 disabled:opacity-30 disabled:pointer-events-none transition-colors text-[10px] flex items-center gap-0.5"
                  title="Jump to next finding"
                >
                  Next
                  <ChevronRight className="h-3 w-3" />
                </button>
              </div>
            )}
          </div>

          <div className="hidden sm:flex items-center gap-3 text-[11px] font-medium text-slate-400">
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-green-500" /> Passed
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-red-500" /> Attention
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-amber-500" /> Needs Review
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
