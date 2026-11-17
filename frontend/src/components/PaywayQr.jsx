import { useCallback, useEffect, useRef, useState } from "react";
import api, { errMsg, money } from "../api";
import Icon from "./Icon.jsx";

const TERMINAL = new Set(["FAILED", "EXPIRED", "CANCELLED", "ERROR"]);

const clock = (seconds) => {
  const safe = Math.max(0, seconds);
  return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, "0")}`;
};

/** ABA PayWay dynamic QR + status polling. The backend verifies every status
 *  with PayWay before it marks the sale paid. */
export default function PaywayQr({ sale, onPaid, onPendingChange, sandbox = false }) {
  const [qr, setQr] = useState(null);
  const [status, setStatus] = useState("LOADING");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(0);
  const startedRef = useRef(false);
  const onPaidRef = useRef(onPaid);
  onPaidRef.current = onPaid;

  const start = useCallback(async () => {
    setStatus("LOADING");
    setError("");
    try {
      const { data } = await api.post(`/sales/${sale.id}/payway/qr`);
      setQr(data);
      setStatus(data.status || "PENDING");
    } catch (e) {
      setStatus("ERROR");
      setError(errMsg(e));
    }
  }, [sale.id]);

  // StrictMode runs effects twice in dev; only create one QR per mount.
  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    start();
  }, [start]);

  useEffect(() => {
    onPendingChange?.(status === "LOADING" || status === "PENDING");
  }, [status, onPendingChange]);

  // Poll the backend; it calls PayWay's status API before confirming.
  useEffect(() => {
    if (status !== "PENDING") return;
    let active = true;
    const tick = async () => {
      try {
        const { data } = await api.get(`/sales/${sale.id}/payway/status`);
        if (!active) return;
        if (data.status === "SUCCEEDED" && data.sale) {
          setStatus("SUCCEEDED");
          onPaidRef.current?.(data.sale);
          return;
        }
        if (TERMINAL.has(data.status)) {
          setStatus(data.status);
          setError(data.message || "Payment did not complete.");
        }
      } catch (e) {
        // Network hiccup: keep polling.
      }
    };
    tick();
    const timer = setInterval(tick, 2500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [status, sale.id]);

  // Countdown. At zero we keep polling: the backend allows a short grace
  // period and may still confirm a payment made just before expiry.
  useEffect(() => {
    if (!qr?.expires_at || status !== "PENDING") return;
    const update = () => {
      const expires = new Date(qr.expires_at).getTime();
      setSecondsLeft(Math.max(0, Math.floor((expires - Date.now()) / 1000)));
    };
    update();
    const timer = setInterval(update, 1000);
    return () => clearInterval(timer);
  }, [qr, status]);

  const cancel = async () => {
    setBusy(true);
    setError("");
    try {
      const { data } = await api.post(`/sales/${sale.id}/payway/cancel`);
      if (data.status === "SUCCEEDED" && data.sale) {
        setStatus("SUCCEEDED");
        onPaidRef.current?.(data.sale);
        return;
      }
      setStatus(data.status || "CANCELLED");
      setError(data.message || "QR payment cancelled.");
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  const retry = () => {
    startedRef.current = true;
    start();
  };

  const src = qr?.qr_image
    ? qr.qr_image.startsWith("data:")
      ? qr.qr_image
      : `data:image/png;base64,${qr.qr_image}`
    : null;

  return (
    <div className="payway-panel">
      {status === "LOADING" && (
        <div className="payway-loading">
          <span className="spinner" />
          <span>Creating your QR code…</span>
        </div>
      )}

      {status === "PENDING" && qr && (
        <>
          <div className="qr-step-label">
            <span className="eyebrow">Step 1 of 4</span>
            <strong>Payment request created</strong>
          </div>

          {(sandbox || qr.sandbox) && (
            <div className="alert warn compact-alert">
              <Icon name="warning" size={16} />
              <span>
                Sandbox QR: the live ABA Mobile app cannot pay this. On a phone, open
                Operations → ABA Simulator and scan this code, or let a manager pick it
                from the pending list.
              </span>
            </div>
          )}

          <div className="qr-frame">
            {src ? (
              <img src={src} alt="ABA PayWay QR code" />
            ) : (
              <div className="qr-placeholder">QR image unavailable</div>
            )}
          </div>

          <div className="qr-amount">{money(sale.total)}</div>
          <p className="small qr-hint">
            {sandbox || qr.sandbox
              ? "Manager: scan this code from Operations → ABA Simulator."
              : "Ask the customer to scan with ABA Mobile or any KHQR banking app."}
          </p>

          <div className="qr-meta">
            <span>Ref <strong className="mono">{qr.tran_id}</strong></span>
            <span>{secondsLeft > 0 ? `Expires in ${clock(secondsLeft)}` : "Checking final status…"}</span>
          </div>

          <div className="qr-wait">
            <span className="spinner" />
            <span>Waiting for payment…</span>
          </div>

          <button className="ghost full" type="button" onClick={cancel} disabled={busy}>
            {busy ? "Cancelling…" : "Cancel QR"}
          </button>
        </>
      )}

      {status === "SUCCEEDED" && (
        <div className="payway-loading">
          <span className="spinner" />
          <span>Payment confirmed. Opening receipt…</span>
        </div>
      )}

      {TERMINAL.has(status) && (
        <>
          <div className="alert error">{error || "Payment did not complete."}</div>
          <button className="primary full" type="button" onClick={retry} disabled={busy}>
            <Icon name="refresh" size={16} /> Try again
          </button>
        </>
      )}
    </div>
  );
}
