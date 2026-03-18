const runtimeConfig = (typeof window !== "undefined" && window.__XTTS_CONFIG__)
    ? window.__XTTS_CONFIG__
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

const getBooleanSetting = (value, fallback) => {
    if (typeof value === "boolean") return value;
    return fallback;
};

export const API_MODE = getStringSetting(runtimeConfig.apiMode, "runpod").toLowerCase();
export const API_BASE_URL = getStringSetting(runtimeConfig.apiBaseUrl, "http://localhost:5000");
export const RUNPOD_BASE_URL = getStringSetting(runtimeConfig.runpodBaseUrl, "https://api.runpod.ai/v2");
export const RUNPOD_ENDPOINT_ID = getStringSetting(runtimeConfig.runpodEndpointId, "q3hbkez7bvinur");
export const RUNPOD_API_KEY = getStringSetting(runtimeConfig.runpodApiKey, "");
export const RUNPOD_POLL_INTERVAL_MS = getNumericSetting(runtimeConfig.runpodPollIntervalMs, 2000, 500);
export const RUNPOD_TIMEOUT_MS = getNumericSetting(runtimeConfig.runpodTimeoutMs, 180000, 10000);
export const API_STREAMING_ENABLED = getBooleanSetting(
    runtimeConfig.apiStreamingEnabled,
    API_MODE !== "runpod",
);
export const AUTOPLAY_CHUNK_THRESHOLD = 5;
export const DEFAULT_LANGUAGE = "en";
export const DEFAULT_READING_MODE = "default";
export const RUNPOD_FALLBACK_VOICES = [
    { id: "lila_tretikov", name: "Lila Tretikov", gender: "female", source_type: "reference" },
    { id: "julie_etchingham", name: "Julie Etchingham", gender: "female", source_type: "reference" },
    { id: "david_lammy", name: "David Lammy", gender: "male", source_type: "reference" },
    { id: "david_harewood", name: "David Harewood", gender: "male", source_type: "reference" },
    { id: "Claribel Dervla", name: "Claribel Dervla", gender: "female", source_type: "preset" },
    { id: "Daisy Studious", name: "Daisy Studious", gender: "female", source_type: "preset" },
    { id: "Gracie Wise", name: "Gracie Wise", gender: "female", source_type: "preset" },
    { id: "Ana Florence", name: "Ana Florence", gender: "female", source_type: "preset" },
    { id: "Andrew Chipper", name: "Andrew Chipper", gender: "male", source_type: "preset" },
    { id: "Viktor Eka", name: "Viktor Eka", gender: "male", source_type: "preset" },
    { id: "Gilberto Mathias", name: "Gilberto Mathias", gender: "male", source_type: "preset" },
    { id: "Damien Black", name: "Damien Black", gender: "male", source_type: "preset" },
];

export const STORAGE_KEYS = {
    text: "tts_text",
    voice: "tts_voice",
    language: "tts_language",
    runpodApiKey: "runpod_api_key",
};
