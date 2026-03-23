const runtimeConfig = (typeof window !== "undefined" && window.__TTS_CONFIG__)
    ? window.__TTS_CONFIG__
    : {};

const getStringSetting = (value, fallback = "") => {
    if (typeof value !== "string") return fallback;
    const normalized = value.trim();
    return normalized || fallback;
};

const getNumericSetting = (value, fallback, min) => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return fallback;
    return Math.max(min, Math.floor(numeric));
};

export const API_MODE = getStringSetting(runtimeConfig.apiMode, "runpod").toLowerCase();
export const API_BASE_URL = getStringSetting(runtimeConfig.apiBaseUrl, "http://localhost:5000");
export const RUNPOD_PROXY_URL = getStringSetting(runtimeConfig.runpodProxyUrl, "https://twilight-dream-8480.djlokiart.workers.dev/api/runpod");
export const RUNPOD_POLL_INTERVAL_MS = getNumericSetting(runtimeConfig.runpodPollIntervalMs, 2000, 500);
export const RUNPOD_TIMEOUT_MS = getNumericSetting(runtimeConfig.runpodTimeoutMs, 900000, 10000);
export const MAX_TEXT_CHARACTERS = getNumericSetting(runtimeConfig.maxTextCharacters, 25000, 1);
export const DEFAULT_LANGUAGE = "en";
export const RUNPOD_FALLBACK_VOICES = [
    { id: "af_heart", name: "Heart (US)", gender: "female", source_type: "preset", locale: "en-US" },
    { id: "af_bella", name: "Bella (US)", gender: "female", source_type: "preset", locale: "en-US" },
    { id: "af_nicole", name: "Nicole (US)", gender: "female", source_type: "preset", locale: "en-US" },
    { id: "af_sarah", name: "Sarah (US)", gender: "female", source_type: "preset", locale: "en-US" },
    { id: "af_sky", name: "Sky (US)", gender: "female", source_type: "preset", locale: "en-US" },
    { id: "am_adam", name: "Adam (US)", gender: "male", source_type: "preset", locale: "en-US" },
    { id: "am_michael", name: "Michael (US)", gender: "male", source_type: "preset", locale: "en-US" },
    { id: "bf_emma", name: "Emma (UK)", gender: "female", source_type: "preset", locale: "en-GB" },
    { id: "bf_isabella", name: "Isabella (UK)", gender: "female", source_type: "preset", locale: "en-GB" },
    { id: "bf_alice", name: "Alice (UK)", gender: "female", source_type: "preset", locale: "en-GB" },
    { id: "bf_lily", name: "Lily (UK)", gender: "female", source_type: "preset", locale: "en-GB" },
    { id: "bm_george", name: "George (UK)", gender: "male", source_type: "preset", locale: "en-GB" },
    { id: "bm_fable", name: "Fable (UK)", gender: "male", source_type: "preset", locale: "en-GB" },
    { id: "bm_lewis", name: "Lewis (UK)", gender: "male", source_type: "preset", locale: "en-GB" },
    { id: "bm_daniel", name: "Daniel (UK)", gender: "male", source_type: "preset", locale: "en-GB" },
];

export const STORAGE_KEYS = {
    text: "tts_text",
    voice: "tts_voice",
    pendingJob: "tts_pending_job_v1",
};
