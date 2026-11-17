import { useCallback, useEffect, useRef, useState } from "react";
import { prepareZXingModule, readBarcodes } from "zxing-wasm/reader";
import wasmUrl from "zxing-wasm/reader/zxing_reader.wasm?url";
import Icon from "./Icon.jsx";

const DECODER_OPTIONS = {
  formats: ["QRCode"],
  tryHarder: true,
  maxNumberOfSymbols: 1,
};

let decoderReady = null;
function loadDecoder() {
  if (!decoderReady) {
    decoderReady = prepareZXingModule({
      overrides: { locateFile: () => wasmUrl },
      fireImmediately: true,
    }).catch((error) => {
      decoderReady = null;
      throw error;
    });
  }
  return decoderReady;
}

/**
 * Camera QR scanner for the sandbox payer.
 *
 * iOS Safari only opens the camera after a direct tap, so the stream is
 * started from a button. Frames are decoded locally with the ZXing-C++
 * WebAssembly build, which also reads the styled KHQR image used by PayWay.
 * A photo upload and a typed-reference fallback keep the flow usable when the
 * camera is blocked.
 */
export default function QrScanner({ onScan, disabled = false }) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const fileRef = useRef(null);
  const streamRef = useRef(null);
  const timerRef = useRef(0);
  const activeRef = useRef(false);
  const busyRef = useRef(false);
  const [scanning, setScanning] = useState(false);
  const [starting, setStarting] = useState(false);
  const [fileBusy, setFileBusy] = useState(false);
  const [error, setError] = useState("");
  const [manual, setManual] = useState("");

  const stop = useCallback(() => {
    activeRef.current = false;
    busyRef.current = false;
    window.clearInterval(timerRef.current);
    timerRef.current = 0;
    const stream = streamRef.current;
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) videoRef.current.srcObject = null;
    setScanning(false);
  }, []);

  useEffect(() => () => stop(), [stop]);

  const tick = useCallback(async () => {
    if (!activeRef.current || busyRef.current) return;
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < video.HAVE_CURRENT_DATA) return;
    const sourceWidth = video.videoWidth;
    const sourceHeight = video.videoHeight;
    if (!sourceWidth || !sourceHeight) return;

    busyRef.current = true;
    try {
      const scale = Math.min(1, 1000 / Math.max(sourceWidth, sourceHeight));
      const width = Math.max(1, Math.round(sourceWidth * scale));
      const height = Math.max(1, Math.round(sourceHeight * scale));
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d", { willReadFrequently: true });
      context.drawImage(video, 0, 0, width, height);
      const image = context.getImageData(0, 0, width, height);
      const results = await readBarcodes(image, DECODER_OPTIONS);
      const text = results[0]?.text;
      if (text) {
        stop();
        onScan(text);
      }
    } catch {
      // A single unreadable frame is normal; keep scanning.
    } finally {
      busyRef.current = false;
    }
  }, [onScan, stop]);

  const start = async () => {
    setError("");
    if (!window.isSecureContext) {
      setError("The camera needs a secure https:// page. Open the public site address, not a local IP.");
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("This browser cannot open the camera. Upload a photo of the QR or type the reference below.");
      return;
    }

    setStarting(true);
    try {
      const streamPromise = navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
        audio: false,
      });
      const decoderPromise = loadDecoder();
      const [stream] = await Promise.all([streamPromise, decoderPromise]);
      streamRef.current = stream;
      const video = videoRef.current;
      video.srcObject = stream;
      await video.play();
      activeRef.current = true;
      setScanning(true);
      timerRef.current = window.setInterval(tick, 200);
      tick();
    } catch (e) {
      stop();
      const denied = e?.name === "NotAllowedError" || e?.name === "SecurityError";
      const inApp = /FBAN|FBAV|Instagram|Line\/|Telegram|Zalo|MicroMessenger/i.test(
        navigator.userAgent,
      );
      if (denied) {
        setError(
          inApp
            ? "This in-app browser blocks the camera. Tap the menu and open the site in Safari or Chrome, then try again. You can also upload a photo of the QR below."
            : "Camera access is blocked. On iPhone: Settings → Safari → Camera → Allow, then reload this page. On Android: tap the lock icon in the address bar → Permissions → Camera → Allow. You can also upload a photo of the QR below.",
        );
      } else if (e?.name === "NotFoundError" || e?.name === "OverconstrainedError") {
        setError("No camera was found on this device. Upload a photo of the QR or type the reference below.");
      } else if (e?.name === "NotReadableError") {
        setError("The camera is busy in another app. Close the other camera app, then try again. You can also upload a photo of the QR below.");
      } else {
        setError("Could not start the QR reader. Reload the page and try again, or upload a photo of the QR below.");
      }
    } finally {
      setStarting(false);
    }
  };

  const upload = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || disabled) return;
    setError("");
    setFileBusy(true);
    try {
      await loadDecoder();
      const results = await readBarcodes(file, DECODER_OPTIONS);
      const text = results[0]?.text;
      if (text) {
        onScan(text);
      } else {
        setError("No QR code found in that image. Take a clear, straight photo of the QR and try again.");
      }
    } catch {
      setError("Could not read that image. Try a PNG or JPG photo of the QR.");
    } finally {
      setFileBusy(false);
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
        <video ref={videoRef} className="qr-video" muted playsInline autoPlay />
        {!scanning && (
          <div className="qr-scanner-placeholder">
            <Icon name="qr" size={38} />
            <strong>Scan the QR shown on checkout</strong>
            <p className="small">
              Point the camera at the POS screen. The code never leaves this device.
            </p>
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
          <button className="primary" type="button" onClick={start} disabled={disabled || starting}>
            <Icon name="qr" size={16} /> {starting ? "Starting camera…" : "Scan QR code"}
          </button>
        )}
        <input
          ref={fileRef}
          className="qr-file-input"
          type="file"
          accept="image/*"
          onChange={upload}
          disabled={disabled || fileBusy}
        />
        <button
          className="ghost"
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={disabled || fileBusy}
        >
          <Icon name="upload" size={16} /> {fileBusy ? "Reading image…" : "Upload QR photo"}
        </button>
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
