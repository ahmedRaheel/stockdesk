import { useEffect, useRef, useState } from "react";
import { t as tr } from "./i18n";

type Detector = {
  detect: (source: HTMLVideoElement) => Promise<{ rawValue: string }[]>;
};
type DetectorConstructor = {
  new (options: { formats: string[] }): Detector;
  getSupportedFormats: () => Promise<string[]>;
};
/** Camera is acquired only after an explicit user gesture. One result per session. */
export default function CameraScanner({
  onCode,
  onClose,
}: {
  onCode: (code: string) => void;
  onClose: () => void;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const callbacks = useRef({ onCode, onClose });
  callbacks.current = { onCode, onClose };
  useEffect(() => {
    let disposed = false;
    let stream: MediaStream | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const stop = () => {
      clearTimeout(timer);
      stream?.getTracks().forEach((track) => track.stop());
    };
    const hidden = () => {
      if (document.hidden) callbacks.current.onClose();
    };
    document.addEventListener("visibilitychange", hidden);
    async function start() {
      try {
        if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia)
          throw Error(tr("Camera scanning requires HTTPS or localhost."));
        const Constructor = (
          window as unknown as { BarcodeDetector?: DetectorConstructor }
        ).BarcodeDetector;
        if (!Constructor)
          throw Error(
            tr(
              "This browser cannot decode camera barcodes. Use a supported browser or enter the code manually.",
            ),
          );
        const supported = await Constructor.getSupportedFormats();
        const formats = [
          "qr_code",
          "ean_13",
          "ean_8",
          "code_128",
          "code_39",
          "upc_a",
          "upc_e",
          "itf",
          "data_matrix",
        ].filter((f) => supported.includes(f));
        if (!formats.includes("qr_code"))
          throw Error(
            tr("This browser cannot decode QR codes. Enter the code manually."),
          );
        if (disposed) return;
        const detector = new Constructor({ formats });
        stream = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: {
            facingMode: { ideal: "environment" },
            width: { ideal: 1280 },
          },
        });
        if (disposed) {
          stop();
          return;
        }
        if (!video.current) {
          stop();
          return;
        }
        video.current.srcObject = stream;
        await video.current.play();
        if (disposed) {
          stop();
          return;
        }
        setReady(true);
        async function scan() {
          if (disposed || !video.current) return;
          try {
            if (video.current.readyState >= 2) {
              const values = await detector.detect(video.current);
              if (disposed) return;
              const value = values
                .find((v) => v.rawValue?.trim())
                ?.rawValue.trim();
              if (value) {
                stop();
                if (value.length > 100 || /[\u0000-\u001f\u007f]/.test(value)) {
                  setError(
                    tr(
                      "Scanned code is invalid or too long. Enter the product code manually.",
                    ),
                  );
                  return;
                }
                callbacks.current.onCode(value);
                return;
              }
            }
            timer = setTimeout(scan, 180);
          } catch {
            stop();
            setError(
              tr("Camera decoding failed. Close the scanner and try again."),
            );
          }
        }
        await scan();
      } catch (e) {
        stop();
        if (!disposed)
          setError(
            e instanceof Error && e.name === "NotAllowedError"
              ? tr(
                  "Camera access was denied. Allow camera access in your browser settings.",
                )
              : e instanceof Error && e.name === "NotFoundError"
                ? tr("No camera was found on this device.")
                : e instanceof Error
                  ? e.message
                  : tr("Camera could not be started."),
          );
      }
    }
    start();
    return () => {
      disposed = true;
      stop();
      document.removeEventListener("visibilitychange", hidden);
      if (video.current) video.current.srcObject = null;
    };
  }, []);
  return (
    <section className="panel" role="dialog" aria-label={tr("Camera scanner")}>
      <div className="actions">
        <h3>{tr("Scan QR or barcode")}</h3>
        <button type="button" className="secondary" onClick={onClose}>
          {tr("Close camera")}
        </button>
      </div>
      {error ? (
        <p role="alert" className="form-error">
          {error}
        </p>
      ) : (
        <>
          <video
            ref={video}
            muted
            playsInline
            aria-label={tr("Camera preview")}
            style={{
              width: "100%",
              maxHeight: 320,
              background: "#142e38",
              borderRadius: 8,
            }}
          />
          <p role="status">
            {ready
              ? tr("Point the camera at one product code.")
              : tr("Starting camera…")}
          </p>
        </>
      )}
      <p className="hint">
        {tr(
          "The scanned value fills the code field. Review the quantity and add it to the bill. QR links are never opened.",
        )}
      </p>
    </section>
  );
}
