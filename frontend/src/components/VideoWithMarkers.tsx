import { useState, useRef, useEffect } from 'react';
import { Play, Pause, RotateCcw, Volume2, VolumeX } from 'lucide-react';
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
  findings,
  selectedFindingId,
  onSelectFinding,
}: VideoWithMarkersProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(25);
  const [isMuted, setIsMuted] = useState(true);

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

  return (
    <div className="rounded-2xl border border-[var(--color-border)] bg-black overflow-hidden shadow-md print:hidden">
      {/* Video Display Area with Canvas Overlay */}
      <div className="relative aspect-video w-full bg-slate-950 flex items-center justify-center">
        <video
          ref={videoRef}
          src={videoUrl}
          muted={isMuted}
          playsInline
          onTimeUpdate={() => videoRef.current && setCurrentTime(videoRef.current.currentTime)}
          onLoadedMetadata={() => videoRef.current && setDuration(videoRef.current.duration || 25)}
          onEnded={() => setIsPlaying(false)}
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
          </div>

          <div className="hidden sm:flex items-center gap-3 text-[11px] font-medium text-slate-400">
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-green-500" /> Pass
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-red-500" /> Fail
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
