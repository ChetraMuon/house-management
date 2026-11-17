import { useCallback, useEffect, useRef, useState } from "react";
import jsQR from "jsqr";
import Icon from "./Icon.jsx";

/**
 * Camera QR scanner for the sandbox payer.
 *
 * iOS Safari only opens the camera after a direct tap, so the stream is
 * started from a button and the frames are decoded locally with jsQR.
 * A typed-reference fallback keeps the flow usable on a desktop.
 */
export default function QrScanner({ onScan, disabled = false }) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const frameRef = useRef(0);
  const activeRef = useRef(false);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState("");
  const [manual, setManual] = useState("");

  const stop = useCallback(() => {
    activeRef.current = false;
    cancelAnimationFrame(frameRef.current);
    const stream = streamRef.current;
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) videoRef.current.srcObject = null;
    setScanning(false);
  }, []);

  useEffect(() => () => stop(), [stop]);

  const tick = useCallback(() => {
    if (!activeRef.current) return;
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (video && canvas && video.readyState === video.HAVE_ENOUGH_DATA) {
      const width = video.videoWidth;
      const height = video.videoHeight;
      if (width && height) {
        canvas.width = width;
        canvas.height = height;
        const context = canvas.getContext("2d", { willReadFrequently: true });
        context.drawImage(video, 0, 0, width, height);
        const image = context.getImageData(0, 0, width, height);
        const found = jsQR(image.data, width, height, { inversionAttempts: "dontInvert" });
        if (found?.data) {
          stop();
          onScan(found.data);
          return;
        }
      }
    }
    frameRef.current = requestAnimationFrame(tick);
  }, [onScan, stop]);

  const start = async () => {
    setError("");
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("This browser cannot open the camera. Type the reference below instead.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
        audio: false,
      });
      streamRef.current = stream;
      const video = videoRef.current;
      video.srcObject = stream;
      await video.play();
      activeRef.current = true;
      setScanning(true);
      frameRef.current = requestAnimationFrame(tick);
    } catch (e) {
      const denied = e?.name === "NotAllowedError" || e?.name === "SecurityError";
      setError(
        denied
          ? "Camera permission was denied. Allow camera access for this site, or type the reference below."
          : "Could not open the camera on this device. Type the reference below instead.",
      );
    }
  };

  const submitManual = (event) => {
    event.preventDefault();
    const code = manual.trim();
    if (!code || disabled) return;
    setError("");
    onScan(code);
  };

  return (
    <div className="qr-scanner">
      <div className={`qr-scanner-stage${scanning ? " is-scanning" : ""}`}>
        <video ref={videoRef} className="qr-video" muted playsInline />
        {!scanning && (
          <div className="qr-scanner-placeholder">
            <Icon name="qr" size={38} />
            <strong>Scan the QR shown on checkout</strong>
            <p className="small">Point the camera at the POS screen. The code never leaves this device.</p>
          </div>
        )}
        {scanning && <span className="qr-scan-frame" aria-hidden="true" />}
      </div>
      <canvas ref={canvasRef} className="qr-canvas" aria-hidden="true" />

      <div className="row qr-scanner-actions">
        {scanning ? (
          <button className="ghost" type="button" onClick={stop}>
            <Icon name="close" size={16} /> Stop camera
          </button>
        ) : (
          <button className="primary" type="button" onClick={start} disabled={disabled}>
            <Icon name="qr" size={16} /> Scan QR code
          </button>
        )}
      </div>

      {error && (
        <div className="alert error compact-alert">
          <Icon name="warning" size={16} />
          <span>{error}</span>
        </div>
      )}

      <form className="qr-manual" onSubmit={submitManual}>
        <label htmlFor="qr-reference">Or type the reference printed under the QR</label>
        <div className="row qr-manual-row">
          <input
            id="qr-reference"
            value={manual}
            onChange={(e) => setManual(e.target.value)}
            placeholder="e.g. S94ad12f1d1"
            autoComplete="off"
            spellCheck="false"
          />
          <button className="ghost" type="submit" disabled={!manual.trim() || disabled}>
            Find payment
          </button>
        </div>
      </form>
    </div>
  );
}
