import { forwardRef, useCallback, useEffect, useRef, useState } from "react";
import { IconCompress, IconExpand, IconPause, IconPip, IconPlay, IconVolume, IconVolumeMute } from "./icons";

function fmt(t) {
  if (!Number.isFinite(t) || t < 0) return "0:00";
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

const SPEEDS = [1, 1.25, 1.5, 2, 0.75];

/**
 * A themed video player. The <video> itself stays real and focusable (no `controls`
 * attribute, but tabIndex={0}) — everything drawn on top is a layer of ordinary buttons
 * and range inputs, so keyboard and screen-reader behaviour comes for free rather than
 * being reimplemented. Fullscreen targets the wrapper, not the video, so the themed bar
 * stays visible in fullscreen too, unlike the browser's own native video fullscreen.
 *
 * Deliberately does not bind Left/Right arrow keys: on the review desk those already
 * move to the next/previous story (see useHotkeys in pages/Review.jsx), and a player
 * that silently stole them here would be a confusing, hard-to-notice conflict.
 */
const VideoPlayer = forwardRef(function VideoPlayer(
  { src, ariaLabel, onError, autoPlay = false, className = "", chapters = [] },
  outerRef
) {
  const videoRef = useRef(null);
  const wrapRef = useRef(null);
  const hideTimer = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [current, setCurrent] = useState(0);
  const [buffered, setBuffered] = useState(0);
  const [muted, setMuted] = useState(false);
  const [volume, setVolume] = useState(1);
  const [barAwake, setBarAwake] = useState(true);
  const [scrubbing, setScrubbing] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [pipActive, setPipActive] = useState(false);
  const pipSupported = typeof document !== "undefined" && document.pictureInPictureEnabled;

  const setVideoRef = useCallback(
    (node) => {
      videoRef.current = node;
      if (typeof outerRef === "function") outerRef(node);
      else if (outerRef) outerRef.current = node;
    },
    [outerRef]
  );

  const wake = useCallback(() => {
    setBarAwake(true);
    clearTimeout(hideTimer.current);
    if (videoRef.current && !videoRef.current.paused) {
      hideTimer.current = setTimeout(() => setBarAwake(false), 2200);
    }
  }, []);

  useEffect(() => () => clearTimeout(hideTimer.current), []);

  useEffect(() => {
    function onFsChange() {
      setFullscreen(document.fullscreenElement === wrapRef.current);
    }
    document.addEventListener("fullscreenchange", onFsChange);
    return () => document.removeEventListener("fullscreenchange", onFsChange);
  }, []);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return undefined;
    const onEnter = () => setPipActive(true);
    const onLeave = () => setPipActive(false);
    v.addEventListener("enterpictureinpicture", onEnter);
    v.addEventListener("leavepictureinpicture", onLeave);
    return () => {
      v.removeEventListener("enterpictureinpicture", onEnter);
      v.removeEventListener("leavepictureinpicture", onLeave);
    };
  }, [src]);

  function toggle() {
    const v = videoRef.current;
    if (!v) return;
    (v.paused ? v.play() : v.pause())?.catch?.(() => {});
  }

  function onSurfaceKeyDown(e) {
    // Only the bare surface, not a button/input inside it — those handle their own keys.
    if (e.target !== e.currentTarget) return;
    if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      toggle();
    }
  }

  function seek(e) {
    const v = videoRef.current;
    const t = Number(e.target.value);
    if (v) v.currentTime = t;
    setCurrent(t);
  }

  function changeVolume(e) {
    const v = videoRef.current;
    const vol = Number(e.target.value);
    if (v) {
      v.volume = vol;
      v.muted = vol === 0;
    }
    setVolume(vol);
    setMuted(vol === 0);
  }

  function toggleMute() {
    const v = videoRef.current;
    if (!v) return;
    v.muted = !v.muted;
    setMuted(v.muted);
  }

  function toggleFullscreen() {
    if (document.fullscreenElement) document.exitFullscreen?.();
    else wrapRef.current?.requestFullscreen?.();
  }

  function cycleSpeed() {
    // Functional form deliberately: reads the latest committed speed even if two clicks
    // land in the same batched update, instead of both computing "next" from the same
    // stale closure value and only actually advancing one step.
    setSpeed((prev) => {
      const next = SPEEDS[(SPEEDS.indexOf(prev) + 1) % SPEEDS.length];
      if (videoRef.current) videoRef.current.playbackRate = next;
      return next;
    });
  }

  async function togglePip() {
    try {
      if (document.pictureInPictureElement) await document.exitPictureInPicture();
      else await videoRef.current?.requestPictureInPicture?.();
    } catch {
      // PiP can refuse (e.g. mid-metadata-load) — nothing useful to recover here.
    }
  }

  const pct = duration ? Math.min(100, (current / duration) * 100) : 0;
  const bufPct = duration ? Math.min(100, (buffered / duration) * 100) : 0;

  return (
    <div
      ref={wrapRef}
      className={`vplayer ${className}`}
      data-playing={playing || undefined}
      data-awake={barAwake || undefined}
      onMouseMove={wake}
      onFocus={wake}
      onMouseLeave={() => playing && setBarAwake(false)}
    >
      <video
        ref={setVideoRef}
        src={src}
        playsInline
        preload="metadata"
        tabIndex={0}
        aria-label={ariaLabel}
        onClick={toggle}
        onKeyDown={onSurfaceKeyDown}
        onPlay={() => { setPlaying(true); wake(); }}
        onPause={() => { setPlaying(false); setBarAwake(true); }}
        onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
        onTimeUpdate={(e) => !scrubbing && setCurrent(e.currentTarget.currentTime)}
        onProgress={(e) => {
          const b = e.currentTarget.buffered;
          if (b.length) setBuffered(b.end(b.length - 1));
        }}
        onVolumeChange={(e) => {
          setVolume(e.currentTarget.volume);
          setMuted(e.currentTarget.muted);
        }}
        onError={onError}
        autoPlay={autoPlay}
      />

      {!playing && (
        <button type="button" className="vplayer-hero" onClick={toggle} aria-label="Play">
          <IconPlay />
        </button>
      )}

      <div className="vplayer-bar">
        <button type="button" className="vplayer-btn" onClick={toggle} aria-label={playing ? "Pause" : "Play"}>
          {playing ? <IconPause /> : <IconPlay />}
        </button>

        <span className="vplayer-time">{fmt(current)}</span>

        <div className="vplayer-scrub">
          <span className="vplayer-scrub-track" aria-hidden="true">
            <span className="vplayer-scrub-buffer" style={{ width: `${bufPct}%` }} />
            <span className="vplayer-scrub-fill" style={{ width: `${pct}%` }} />
            {duration > 0 && chapters.filter((t) => t > 0).map((t) => (
              <span key={t} className="vplayer-scrub-chapter" style={{ left: `${(t / duration) * 100}%` }} />
            ))}
          </span>
          <input
            type="range"
            className="vplayer-range vplayer-seek"
            min={0}
            max={duration || 0}
            step={0.01}
            value={current}
            onChange={seek}
            onPointerDown={() => setScrubbing(true)}
            onPointerUp={() => setScrubbing(false)}
            aria-label="Seek"
            aria-valuetext={`${fmt(current)} of ${fmt(duration)}`}
          />
        </div>

        <span className="vplayer-time">{fmt(duration)}</span>

        <div className="vplayer-volume">
          <button type="button" className="vplayer-btn" onClick={toggleMute} aria-label={muted || volume === 0 ? "Unmute" : "Mute"}>
            {muted || volume === 0 ? <IconVolumeMute /> : <IconVolume />}
          </button>
          <input
            type="range"
            className="vplayer-range vplayer-vol"
            min={0}
            max={1}
            step={0.05}
            value={muted ? 0 : volume}
            onChange={changeVolume}
            aria-label="Volume"
          />
        </div>

        <button type="button" className="vplayer-btn vplayer-speed" onClick={cycleSpeed} aria-label={`Playback speed, currently ${speed}×`}>
          {speed}×
        </button>

        {pipSupported && (
          <button type="button" className="vplayer-btn vplayer-pip" onClick={togglePip} aria-label={pipActive ? "Exit picture-in-picture" : "Picture-in-picture"} aria-pressed={pipActive}>
            <IconPip />
          </button>
        )}

        <button type="button" className="vplayer-btn" onClick={toggleFullscreen} aria-label={fullscreen ? "Exit fullscreen" : "Fullscreen"}>
          {fullscreen ? <IconCompress /> : <IconExpand />}
        </button>
      </div>
    </div>
  );
});

export default VideoPlayer;
