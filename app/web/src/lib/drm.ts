// DRM capability detection (P2 desktop).
//
// Spotify's Web Playback SDK needs Widevine. Chrome, Edge and Firefox have it;
// macOS WKWebView (which the Tauri desktop shell uses) does not — verified on
// macOS 26 / AppleWebKit 605.1.15, where only FairPlay and ClearKey are
// available. Rather than let the SDK fail with an opaque error inside the
// desktop app, detect it up front and hand that one surface to the system
// browser, where the same localhost app plays fine.

let widevine: Promise<boolean> | null = null;

/** Whether this browser can play Widevine-protected audio (Spotify SDK). */
export function hasWidevine(): Promise<boolean> {
  if (!widevine) {
    widevine = (async () => {
      if (typeof navigator.requestMediaKeySystemAccess !== "function") return false;
      try {
        await navigator.requestMediaKeySystemAccess("com.widevine.alpha", [
          {
            initDataTypes: ["cenc"],
            audioCapabilities: [{ contentType: 'audio/mp4;codecs="mp4a.40.2"' }],
          },
        ]);
        return true;
      } catch {
        return false;
      }
    })();
  }
  return widevine;
}
