import { API_BASE_URL, API_MODE } from "../constants.js";
import {
    cancelRunpodJob,
    checkRunpodStatus,
    fetchRunpodAudioBytes,
    submitRunpodJob,
} from "./runpodProxy.js";

export const TERMINAL_JOB_STATUSES = new Set([
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "TIMED_OUT",
]);

const RUNPOD_MODE = "runpod";

const isRunpodMode = API_MODE === RUNPOD_MODE;

const decodeBase64ToBytes = (base64Audio) => {
    const cleanBase64 = String(base64Audio || "").replace(/\s+/g, "");
    if (!cleanBase64) {
        throw new Error("RunPod returned empty audio data.");
    }
    const binary = atob(cleanBase64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
        bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
};

const readApiError = async (response, fallbackMessage) => {
    const payload = await response.json().catch(() => null);
    if (payload && typeof payload.error === "string" && payload.error.trim()) {
        return payload.error;
    }
    if (payload && typeof payload.message === "string" && payload.message.trim()) {
        return payload.message;
    }
    return `${fallbackMessage} (${response.status})`;
};

const normalizeJobId = (jobId) => {
    const normalized = String(jobId || "").trim();
    if (!normalized) {
        throw new Error("Job id is required.");
    }
    return normalized;
};

const normalizeRequestPayload = (payload) => {
    const requestPayload = payload && typeof payload === "object" ? payload : {};
    return {
        text: String(requestPayload.text || "").trim(),
        language: String(requestPayload.language || "en").trim() || "en",
        voice_id: requestPayload.voice_id || undefined,
    };
};

export const submitTtsJob = async (payload) => {
    const requestPayload = normalizeRequestPayload(payload);

    if (isRunpodMode) {
        const response = await submitRunpodJob({
            input: requestPayload,
        });
        return response;
    }

    const response = await fetch(`${API_BASE_URL}/tts/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestPayload),
    });
    if (!response.ok) {
        throw new Error(await readApiError(response, "Job submission failed"));
    }
    return response.json();
};

export const checkTtsJobStatus = async (jobId) => {
    const normalizedJobId = normalizeJobId(jobId);
    if (isRunpodMode) {
        return checkRunpodStatus(normalizedJobId);
    }

    const response = await fetch(`${API_BASE_URL}/tts/jobs/${encodeURIComponent(normalizedJobId)}`, {
        method: "GET",
    });
    if (!response.ok) {
        throw new Error(await readApiError(response, "Status check failed"));
    }
    return response.json();
};

export const cancelTtsJob = async (jobId) => {
    const normalizedJobId = normalizeJobId(jobId);
    if (isRunpodMode) {
        return cancelRunpodJob(normalizedJobId);
    }

    const response = await fetch(
        `${API_BASE_URL}/tts/jobs/${encodeURIComponent(normalizedJobId)}/cancel`,
        { method: "POST" },
    );
    if (!response.ok) {
        throw new Error(await readApiError(response, "Cancel request failed"));
    }
    return response.json();
};

export const fetchTtsJobAudioBytes = async (jobId, statusPayload) => {
    const normalizedJobId = normalizeJobId(jobId);

    if (isRunpodMode) {
        const outputPayload = statusPayload && typeof statusPayload.output === "object"
            ? statusPayload.output
            : {};
        const outputError = outputPayload.error
            || statusPayload?.error
            || statusPayload?.message;
        if (typeof outputError === "string" && outputError.trim()) {
            throw new Error(outputError);
        }

        const audioBase64 = outputPayload.audio_base64 || statusPayload?.audio_base64;
        if (typeof audioBase64 === "string" && audioBase64.trim()) {
            return decodeBase64ToBytes(audioBase64);
        }

        const audioUrl = outputPayload.audio_url || statusPayload?.audio_url;
        if (typeof audioUrl === "string" && audioUrl.trim()) {
            return fetchRunpodAudioBytes(audioUrl);
        }

        throw new Error("RunPod completed but returned no audio.");
    }

    const response = await fetch(
        `${API_BASE_URL}/tts/jobs/${encodeURIComponent(normalizedJobId)}/audio`,
        { method: "GET" },
    );
    if (!response.ok) {
        throw new Error(await readApiError(response, "Audio download failed"));
    }
    const arrayBuffer = await response.arrayBuffer();
    if (!arrayBuffer.byteLength) {
        throw new Error("Audio endpoint returned empty payload.");
    }
    return new Uint8Array(arrayBuffer);
};
