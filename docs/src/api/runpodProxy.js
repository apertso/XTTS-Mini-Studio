// Proxy endpoint for Cloudflare Worker
import { RUNPOD_PROXY_URL } from "../constants.js";

const normalizedProxyUrl = RUNPOD_PROXY_URL.replace(/\/+$/, "");

const readProxyError = async (response, fallbackMessage) => {
    const payload = await response.json().catch(() => null);
    if (payload && typeof payload.error === "string" && payload.error.trim()) {
        return payload.error;
    }
    if (payload && typeof payload.message === "string" && payload.message.trim()) {
        return payload.message;
    }
    return `${fallbackMessage} (${response.status})`;
};

export const submitRunpodJob = async (payload) => {
    const response = await fetch(normalizedProxyUrl, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
    });

    if (!response.ok) {
        throw new Error(await readProxyError(response, "Proxy request failed"));
    }

    return response.json();
};

export const checkRunpodStatus = async (jobId) => {
    const normalizedJobId = String(jobId || "").trim();
    if (!normalizedJobId) {
        throw new Error("RunPod status check requires a job id.");
    }

    const response = await fetch(
        `${normalizedProxyUrl}/status/${encodeURIComponent(normalizedJobId)}`,
        { method: "GET" },
    );

    if (!response.ok) {
        throw new Error(await readProxyError(response, "Status check failed"));
    }

    return response.json();
};

export const fetchRunpodAudioBytes = async (audioUrl) => {
    const normalizedAudioUrl = String(audioUrl || "").trim();
    if (!normalizedAudioUrl) {
        throw new Error("RunPod audio URL is empty.");
    }

    const response = await fetch(
        `${normalizedProxyUrl}/audio?url=${encodeURIComponent(normalizedAudioUrl)}`,
        { method: "GET" },
    );

    if (!response.ok) {
        throw new Error(await readProxyError(response, "Audio download failed"));
    }

    const buffer = await response.arrayBuffer();
    if (!buffer.byteLength) {
        throw new Error("Audio proxy returned empty payload.");
    }

    return new Uint8Array(buffer);
};
