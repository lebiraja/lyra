import { useCallback, useRef, useState } from 'react';

/** AudioWorklet that batches mic input into ~64ms Int16 PCM chunks. */
const WORKLET_SOURCE = `
class PCMCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.chunks = [];
    this.length = 0;
  }
  process(inputs) {
    const channel = inputs[0]?.[0];
    if (channel) {
      this.chunks.push(new Float32Array(channel));
      this.length += channel.length;
      if (this.length >= 1024) {
        const all = new Float32Array(this.length);
        let offset = 0;
        for (const c of this.chunks) {
          all.set(c, offset);
          offset += c.length;
        }
        const pcm = new Int16Array(all.length);
        for (let i = 0; i < all.length; i++) {
          const s = Math.max(-1, Math.min(1, all[i]));
          pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }
        this.port.postMessage(pcm.buffer, [pcm.buffer]);
        this.chunks = [];
        this.length = 0;
      }
    }
    return true;
  }
}
registerProcessor('pcm-capture', PCMCapture);
`;

interface MicStream {
  isActive: boolean;
  error: string | null;
  start: () => Promise<void>;
  stop: () => void;
  /** Mic level analyser for the live waveform (null until started). */
  analyser: AnalyserNode | null;
}

export function useMicStream(
  onChunk: (pcm: ArrayBuffer) => void,
  onVideoFrame?: (base64: string) => void
): MicStream {
  const [isActive, setIsActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const intervalRef = useRef<number | null>(null);

  const onChunkRef = useRef(onChunk);
  onChunkRef.current = onChunk;
  const onVideoFrameRef = useRef(onVideoFrame);
  onVideoFrameRef.current = onVideoFrame;

  const start = useCallback(async () => {
    if (ctxRef.current) return;
    try {
      let stream: MediaStream;
      let hasVideo = false;
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            channelCount: 1,
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
          video: onVideoFrameRef.current
            ? {
                width: { ideal: 320 },
                height: { ideal: 240 },
                frameRate: { ideal: 5 },
              }
            : false,
        });
        hasVideo = !!onVideoFrameRef.current && stream.getVideoTracks().length > 0;
      } catch {
        // Fallback to audio only
        stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            channelCount: 1,
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        });
      }

      const ctx = new AudioContext({ sampleRate: 16000 });
      const workletUrl = URL.createObjectURL(
        new Blob([WORKLET_SOURCE], { type: 'application/javascript' })
      );
      await ctx.audioWorklet.addModule(workletUrl);
      URL.revokeObjectURL(workletUrl);

      const source = ctx.createMediaStreamSource(stream);
      const node = new AudioWorkletNode(ctx, 'pcm-capture');
      node.port.onmessage = (e: MessageEvent<ArrayBuffer>) => onChunkRef.current(e.data);

      const analyserNode = ctx.createAnalyser();
      analyserNode.fftSize = 512;
      source.connect(analyserNode);
      source.connect(node);

      // Start video snapshotting loop if video is active
      if (hasVideo && onVideoFrameRef.current) {
        const videoElement = document.createElement('video');
        videoElement.srcObject = stream;
        videoElement.autoplay = true;
        videoElement.playsInline = true;
        videoElement.muted = true;
        videoElement.onloadedmetadata = () => {
          videoElement.play().catch(() => {});
        };

        const canvas = document.createElement('canvas');
        canvas.width = 320;
        canvas.height = 240;
        const ctx2d = canvas.getContext('2d');

        const intervalId = window.setInterval(() => {
          if (videoElement.readyState >= 2 && ctx2d) {
            ctx2d.drawImage(videoElement, 0, 0, 320, 240);
            const dataUrl = canvas.toDataURL('image/jpeg', 0.5);
            const base64Str = dataUrl.split(',')[1];
            if (base64Str) {
              onVideoFrameRef.current?.(base64Str);
            }
          }
        }, 200);

        videoRef.current = videoElement;
        intervalRef.current = intervalId;
      }

      ctxRef.current = ctx;
      streamRef.current = stream;
      setAnalyser(analyserNode);
      setIsActive(true);
      setError(null);
    } catch {
      setError('Microphone unavailable — you can still type below.');
    }
  }, []);

  const stop = useCallback(() => {
    if (intervalRef.current !== null) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.pause();
      videoRef.current.srcObject = null;
      videoRef.current = null;
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    void ctxRef.current?.close();
    streamRef.current = null;
    ctxRef.current = null;
    setAnalyser(null);
    setIsActive(false);
  }, []);

  return { isActive, error, start, stop, analyser };
}
