import jsQR from "jsqr";

// Images remain inside the browser. One bounded frame is processed at a time.
self.onmessage = (
  event: MessageEvent<{
    pixels: Uint8ClampedArray;
    width: number;
    height: number;
  }>,
) => {
  const { pixels, width, height } = event.data;
  try {
    if (
      width < 1 ||
      height < 1 ||
      width > 768 ||
      height > 768 ||
      pixels.length !== width * height * 4
    )
      throw Error("Invalid camera frame");
    const result = jsQR(pixels, width, height, {
      inversionAttempts: "attemptBoth",
    });
    self.postMessage({ value: result?.data || "" });
  } catch {
    self.postMessage({ error: true });
  }
};
