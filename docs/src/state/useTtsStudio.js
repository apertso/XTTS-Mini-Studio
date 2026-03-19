import { React } from "../lib/html.js";
import {
    API_BASE_URL,
    API_MODE,
    DEFAULT_LANGUAGE,
    MAX_TEXT_CHARACTERS,
    RUNPOD_FALLBACK_VOICES,
    RUNPOD_POLL_INTERVAL_MS,
    STORAGE_KEYS,
} from "../constants.js";
import { createAudioController } from "../audio/audioController.js";
import {
    TERMINAL_JOB_STATUSES,
    cancelTtsJob,
    checkTtsJobStatus,
    fetchTtsJobAudioBytes,
    submitTtsJob,
} from "../api/ttsJobs.js";
import {
    clampPercent,
    formatTime,
    readUint32LE,
    triggerBlobDownload,
} from "../utils/audioUtils.js";

const { useCallback, useEffect, useMemo, useRef, useState } = React;

const INITIAL_STATUS = { text: "Ready to synthesize.", tone: "idle" };
const RUNPOD_MODE = "runpod";
const PENDING_JOB_VERSION = 1;
const TEXT_LIMIT_ERROR_PREFIX = "Text exceeds maximum length:";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const normalizeTextValue = (value) => String(value || "").trim();

const getNormalizedTextCharCount = (value) => normalizeTextValue(value).length;

const getTextLimitErrorText = (charCount) =>
    `${TEXT_LIMIT_ERROR_PREFIX} ${MAX_TEXT_CHARACTERS} symbols (got ${charCount}).`;

const toFiniteInteger = (value) => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return null;
    return Math.floor(numeric);
};

const parseChunkProgressObject = (candidate) => {
    if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) {
        return null;
    }

    const processedChunks = toFiniteInteger(
        candidate.processed_chunks
        ?? candidate.processedChunks
        ?? candidate.chunks_processed
        ?? candidate.chunksProcessed
        ?? candidate.processed
        ?? candidate.current,
    );
    const totalChunks = toFiniteInteger(
        candidate.total_chunks
        ?? candidate.totalChunks
        ?? candidate.chunks_total
        ?? candidate.chunksTotal
        ?? candidate.total,
    );

    if (processedChunks === null && totalChunks === null) {
        return null;
    }

    return {
        processedChunks: processedChunks === null ? null : Math.max(0, processedChunks),
        totalChunks: totalChunks === null ? null : Math.max(0, totalChunks),
    };
};

const extractJobChunkProgress = (statusPayload) => {
    if (!statusPayload || typeof statusPayload !== "object" || Array.isArray(statusPayload)) {
        return null;
    }

    const outputPayload = statusPayload.output && typeof statusPayload.output === "object" && !Array.isArray(statusPayload.output)
        ? statusPayload.output
        : null;
    const candidates = [
        outputPayload?.chunk_progress,
        outputPayload?.chunkProgress,
        outputPayload?.progress,
        outputPayload,
        statusPayload.chunk_progress,
        statusPayload.chunkProgress,
        statusPayload.progress,
        statusPayload,
    ];

    for (const candidate of candidates) {
        const parsed = parseChunkProgressObject(candidate);
        if (parsed) {
            return parsed;
        }
    }

    return null;
};

const normalizeJobStatus = (status) => String(status || "").trim().toUpperCase();

const readPendingJobSnapshot = () => {
    try {
        const raw = localStorage.getItem(STORAGE_KEYS.pendingJob);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
        if (parsed.v !== PENDING_JOB_VERSION) return null;
        if (String(parsed.mode || "").trim().toLowerCase() !== API_MODE) return null;
        const jobId = String(parsed.jobId || "").trim();
        if (!jobId) return null;

        const request = parsed.request && typeof parsed.request === "object" && !Array.isArray(parsed.request)
            ? parsed.request
            : {};

        return {
            jobId,
            submittedAt: Number(parsed.submittedAt) || Date.now(),
            request: {
                text: String(request.text || ""),
                language: String(request.language || DEFAULT_LANGUAGE),
                voice_id: request.voice_id ? String(request.voice_id) : "",
            },
        };
    } catch (_error) {
        return null;
    }
};

const writePendingJobSnapshot = (jobId, requestPayload) => {
    const payload = {
        v: PENDING_JOB_VERSION,
        mode: API_MODE,
        jobId: String(jobId || "").trim(),
        submittedAt: Date.now(),
        request: {
            text: String(requestPayload?.text || ""),
            language: String(requestPayload?.language || DEFAULT_LANGUAGE),
            voice_id: requestPayload?.voice_id ? String(requestPayload.voice_id) : "",
        },
    };
    localStorage.setItem(STORAGE_KEYS.pendingJob, JSON.stringify(payload));
};

const clearPendingJobSnapshot = () => {
    localStorage.removeItem(STORAGE_KEYS.pendingJob);
};

export const useTtsStudio = () => {
    const [text, setText] = useState("");
    const [voice, setVoice] = useState("");
    const [language, setLanguage] = useState(DEFAULT_LANGUAGE);
    const [voices, setVoices] = useState([]);
    const [voicesReady, setVoicesReady] = useState(false);
    const [voiceLoadFailed, setVoiceLoadFailed] = useState(false);
    const [status, setStatus] = useState(INITIAL_STATUS);
    const [isGenerating, setIsGenerating] = useState(false);
    const [isCancelling, setIsCancelling] = useState(false);
    const [streamProgress, setStreamProgress] = useState(0);
    const [loadedChunkCount, setLoadedChunkCount] = useState(0);
    const [totalChunkCount, setTotalChunkCount] = useState(0);
    const [playerVisible, setPlayerVisible] = useState(false);
    const [downloadReady, setDownloadReady] = useState(false);
    const [isDownloading, setIsDownloading] = useState(false);
    const [isPlaying, setIsPlaying] = useState(false);
    const [playerMode, setPlayerMode] = useState("idle");
    const [playedPercent, setPlayedPercent] = useState(0);
    const [loadedPercent, setLoadedPercent] = useState(0);
    const [timeDisplay, setTimeDisplay] = useState("0:00 / 0:00");
    const [activeJobId, setActiveJobId] = useState("");

    const audioControllerRef = useRef(null);
    const generatedWavBlobRef = useRef(null);
    const sampleRateRef = useRef(22050);
    const loadedChunksRef = useRef(0);
    const totalChunksRef = useRef(0);
    const pollingTokenRef = useRef(0);
    const activeJobIdRef = useRef("");
    const isRunpodMode = API_MODE === RUNPOD_MODE;

    useEffect(() => {
        activeJobIdRef.current = activeJobId;
    }, [activeJobId]);

    const selectedVoice = useMemo(
        () => voices.find((item) => item.id === voice) || null,
        [voices, voice],
    );

    const referenceVoices = useMemo(
        () => voices.filter((item) => item.source_type === "reference"),
        [voices],
    );

    const presetVoices = useMemo(
        () => voices.filter((item) => item.source_type !== "reference"),
        [voices],
    );

    const backendNeedsRestart = !isRunpodMode
        && voicesReady
        && !voiceLoadFailed
        && voices.length > 0
        && referenceVoices.length === 0;

    const syncPlayerUi = useCallback((controller) => {
        const loaded = controller.loadedDuration > 0 ? 100 : 0;
        const played = controller.loadedDuration > 0
            ? (controller.currentTime / controller.loadedDuration) * 100
            : 0;

        setLoadedPercent(clampPercent(loaded));
        setPlayedPercent(clampPercent(played));
        setTimeDisplay(`${formatTime(controller.currentTime)} / ${formatTime(controller.loadedDuration)}`);
        setIsPlaying(controller.isPlaying);
        setPlayerMode(
            controller.isPlaying
                ? (controller.isBuffering ? "buffering" : "playing")
                : (controller.loadedDuration > 0 ? "ready" : "idle"),
        );
    }, []);

    const resetGenerationTracking = useCallback(() => {
        loadedChunksRef.current = 0;
        totalChunksRef.current = 0;
        setLoadedChunkCount(0);
        setTotalChunkCount(0);
        setStreamProgress(0);
    }, []);

    const applyChunkProgress = useCallback((loadedRaw, totalRaw) => {
        const nextLoaded = Number.isFinite(Number(loadedRaw))
            ? Math.max(0, Math.floor(Number(loadedRaw)))
            : loadedChunksRef.current;
        const nextTotal = Number.isFinite(Number(totalRaw))
            ? Math.max(0, Math.floor(Number(totalRaw)))
            : totalChunksRef.current;

        const safeLoaded = Math.max(loadedChunksRef.current, nextLoaded);
        const safeTotal = nextTotal > 0
            ? Math.max(totalChunksRef.current, nextTotal, safeLoaded)
            : totalChunksRef.current;

        loadedChunksRef.current = safeLoaded;
        totalChunksRef.current = safeTotal;

        const displayLoaded = safeTotal > 0 ? Math.min(safeLoaded, safeTotal) : safeLoaded;
        setLoadedChunkCount(displayLoaded);
        setTotalChunkCount(safeTotal);

        if (safeTotal > 0) {
            const progress = clampPercent((displayLoaded / safeTotal) * 100);
            setStreamProgress(progress);
        }
    }, []);

    const clearActivePendingJob = useCallback(() => {
        clearPendingJobSnapshot();
        setActiveJobId("");
        activeJobIdRef.current = "";
    }, []);

    const finishGeneration = useCallback((nextStatusText, nextStatusTone) => {
        setIsGenerating(false);
        setIsCancelling(false);
        setStatus({ text: nextStatusText, tone: nextStatusTone });
        clearActivePendingJob();
    }, [clearActivePendingJob]);

    const applyWavBytesToPlayer = useCallback(async (wavBytes) => {
        const controller = audioControllerRef.current;
        if (!controller) {
            throw new Error("Player is not initialized yet.");
        }

        controller.reset();

        const wavBlob = new Blob([wavBytes], { type: "audio/wav" });
        generatedWavBlobRef.current = wavBlob;

        const arrayBuffer = await wavBlob.arrayBuffer();
        const wavData = new Uint8Array(arrayBuffer);
        const inferredSampleRate = wavData.byteLength >= 28 ? readUint32LE(wavData, 24) : 22050;
        sampleRateRef.current = inferredSampleRate || 22050;
        controller.sampleRate = sampleRateRef.current;

        if (wavData.byteLength > 44) {
            const pcmData = new Int16Array(arrayBuffer, 44, Math.floor((wavData.byteLength - 44) / 2));
            if (pcmData.length > 0) {
                controller.addChunk(pcmData);
            }
        }
        controller.markGenerationDone();

        setPlayerVisible(true);
        setDownloadReady(true);
        setStreamProgress(100);
        syncPlayerUi(controller);
    }, [syncPlayerUi]);

    const pollJobUntilTerminal = useCallback(async (jobId) => {
        const normalizedJobId = String(jobId || "").trim();
        if (!normalizedJobId) {
            finishGeneration("Error: Missing active job id.", "error");
            return;
        }

        const token = ++pollingTokenRef.current;
        let consecutiveStatusErrors = 0;

        while (pollingTokenRef.current === token) {
            let statusPayload = null;
            try {
                statusPayload = await checkTtsJobStatus(normalizedJobId);
                consecutiveStatusErrors = 0;
            } catch (error) {
                const message = error instanceof Error ? error.message : String(error);
                const lowered = message.toLowerCase();

                if (lowered.includes("not found")) {
                    finishGeneration("Pending job was not found. Lock was cleared.", "error");
                    resetGenerationTracking();
                    return;
                }

                consecutiveStatusErrors += 1;
                setStatus({
                    text: `Status check failed (${consecutiveStatusErrors}). Retrying...`,
                    tone: "error",
                });
                await sleep(RUNPOD_POLL_INTERVAL_MS);
                continue;
            }

            const statusJobId = typeof statusPayload?.id === "string"
                ? statusPayload.id.trim()
                : "";
            if (statusJobId && statusJobId !== normalizedJobId) {
                finishGeneration(
                    `Error: Job status mismatch: expected ${normalizedJobId}, got ${statusJobId}.`,
                    "error",
                );
                return;
            }

            const progress = extractJobChunkProgress(statusPayload);
            if (progress) {
                applyChunkProgress(progress.processedChunks, progress.totalChunks);
            }

            const jobStatus = normalizeJobStatus(statusPayload?.status);
            if (jobStatus === "IN_QUEUE") {
                setStatus({
                    text: isRunpodMode
                        ? "RunPod queue: waiting for worker..."
                        : "Local queue: waiting for worker...",
                    tone: "idle",
                });
                if (totalChunksRef.current === 0) {
                    setStreamProgress(24);
                }
                await sleep(RUNPOD_POLL_INTERVAL_MS);
                continue;
            }

            if (jobStatus === "IN_PROGRESS") {
                setStatus({
                    text: isRunpodMode ? "RunPod is generating audio..." : "Local worker is generating audio...",
                    tone: "idle",
                });
                if (totalChunksRef.current === 0) {
                    setStreamProgress(68);
                }
                await sleep(RUNPOD_POLL_INTERVAL_MS);
                continue;
            }

            if (!TERMINAL_JOB_STATUSES.has(jobStatus)) {
                setStatus({ text: `Job status: ${jobStatus || "WAITING"}...`, tone: "idle" });
                await sleep(RUNPOD_POLL_INTERVAL_MS);
                continue;
            }

            if (jobStatus !== "COMPLETED") {
                const errorText = statusPayload?.error
                    || statusPayload?.message
                    || `TTS job ${jobStatus.toLowerCase()}.`;
                const tone = jobStatus === "CANCELLED" ? "idle" : "error";
                const textValue = jobStatus === "CANCELLED"
                    ? "Generation cancelled."
                    : `Error: ${errorText}`;
                finishGeneration(textValue, tone);
                if (jobStatus === "CANCELLED") {
                    resetGenerationTracking();
                }
                return;
            }

            try {
                const wavBytes = await fetchTtsJobAudioBytes(normalizedJobId, statusPayload);
                if (pollingTokenRef.current !== token) {
                    return;
                }
                await applyWavBytesToPlayer(wavBytes);
                finishGeneration("Ready. You can listen or download WAV.", "success");
                return;
            } catch (error) {
                finishGeneration(`Error: ${error instanceof Error ? error.message : String(error)}`, "error");
                return;
            }
        }
    }, [
        applyChunkProgress,
        applyWavBytesToPlayer,
        finishGeneration,
        isRunpodMode,
        resetGenerationTracking,
    ]);

    const restorePendingJob = useCallback((pendingSnapshot) => {
        if (!pendingSnapshot) {
            return;
        }

        const pendingJobId = String(pendingSnapshot.jobId || "").trim();
        if (!pendingJobId) {
            clearPendingJobSnapshot();
            return;
        }

        setActiveJobId(pendingJobId);
        activeJobIdRef.current = pendingJobId;
        setIsGenerating(true);
        setIsCancelling(false);
        setStatus({ text: "Recovered pending job. Resuming status polling...", tone: "idle" });
        setStreamProgress(16);
        void pollJobUntilTerminal(pendingJobId);
    }, [pollJobUntilTerminal]);

    useEffect(() => {
        audioControllerRef.current = createAudioController({
            onUi: syncPlayerUi,
            onDone: () => {
                setStatus({ text: "Playback completed.", tone: "idle" });
            },
        });

        const savedText = localStorage.getItem(STORAGE_KEYS.text) || "";
        const savedVoice = localStorage.getItem(STORAGE_KEYS.voice) || "";
        const savedLanguage = localStorage.getItem(STORAGE_KEYS.language) || DEFAULT_LANGUAGE;
        const pendingSnapshot = readPendingJobSnapshot();
        if (!pendingSnapshot) {
            clearPendingJobSnapshot();
        }

        setText(pendingSnapshot?.request?.text || savedText);
        setLanguage(pendingSnapshot?.request?.language || savedLanguage);

        let cancelled = false;
        (async () => {
            try {
                if (isRunpodMode) {
                    const availableVoices = [...RUNPOD_FALLBACK_VOICES];
                    setVoices(availableVoices);
                    setVoicesReady(true);
                    setVoiceLoadFailed(false);

                    const requestedVoice = pendingSnapshot?.request?.voice_id || savedVoice;
                    const fallbackVoice = availableVoices[0]?.id || "";
                    const hasRequestedVoice = availableVoices.some((item) => item.id === requestedVoice);
                    setVoice(hasRequestedVoice ? requestedVoice : fallbackVoice);

                    if (!pendingSnapshot) {
                        setStatus({
                            text: "Ready to synthesize via RunPod.",
                            tone: "idle",
                        });
                    }
                } else {
                    const response = await fetch(`${API_BASE_URL}/api/voices`);
                    const data = await response.json();
                    if (cancelled) return;

                    const availableVoices = Array.isArray(data.voices) ? data.voices : [];
                    setVoices(availableVoices);
                    setVoicesReady(true);
                    setVoiceLoadFailed(false);

                    const requestedVoice = pendingSnapshot?.request?.voice_id || savedVoice;
                    const fallbackVoice = availableVoices[0]?.id || "";
                    const hasRequestedVoice = availableVoices.some((item) => item.id === requestedVoice);
                    setVoice(hasRequestedVoice ? requestedVoice : fallbackVoice);

                    if (!pendingSnapshot) {
                        if (availableVoices.length === 0) {
                            setStatus({ text: "No voices available.", tone: "error" });
                        } else if (!availableVoices.some((item) => item.source_type === "reference")) {
                            setStatus({
                                text: "Server is missing reference voices. Restart backend if needed.",
                                tone: "error",
                            });
                        }
                    }
                }

                if (!cancelled && pendingSnapshot) {
                    restorePendingJob(pendingSnapshot);
                }
            } catch (error) {
                if (cancelled) return;
                console.error("Failed to load voices:", error);
                setVoicesReady(true);
                setVoiceLoadFailed(true);
                setStatus({ text: "Failed to load voices.", tone: "error" });
                if (pendingSnapshot) {
                    clearActivePendingJob();
                    resetGenerationTracking();
                    setIsGenerating(false);
                    setIsCancelling(false);
                }
            }
        })();

        return () => {
            cancelled = true;
            pollingTokenRef.current += 1;
            audioControllerRef.current?.reset();
        };
    }, [clearActivePendingJob, isRunpodMode, resetGenerationTracking, restorePendingJob, syncPlayerUi]);

    useEffect(() => {
        localStorage.setItem(STORAGE_KEYS.text, text);
    }, [text]);

    useEffect(() => {
        localStorage.setItem(STORAGE_KEYS.voice, voice);
    }, [voice]);

    useEffect(() => {
        localStorage.setItem(STORAGE_KEYS.language, language);
    }, [language]);

    const handleTextChange = useCallback((nextText) => {
        const safeText = String(nextText || "");
        setText(safeText);

        const nextCharCount = getNormalizedTextCharCount(safeText);
        if (nextCharCount <= MAX_TEXT_CHARACTERS) {
            setStatus((currentStatus) => {
                if (
                    currentStatus.tone === "error"
                    && String(currentStatus.text || "").startsWith(TEXT_LIMIT_ERROR_PREFIX)
                ) {
                    return INITIAL_STATUS;
                }
                return currentStatus;
            });
        }
    }, []);

    const startGeneration = useCallback(async () => {
        if (isGenerating) return;

        const normalizedText = normalizeTextValue(text);
        if (!normalizedText) {
            setStatus({ text: "Enter text before generating audio.", tone: "error" });
            return;
        }
        const textCharCount = normalizedText.length;
        if (textCharCount > MAX_TEXT_CHARACTERS) {
            setStatus({ text: getTextLimitErrorText(textCharCount), tone: "error" });
            return;
        }

        const controller = audioControllerRef.current;
        if (!controller) {
            setStatus({ text: "Player is not initialized yet.", tone: "error" });
            return;
        }

        controller.reset();
        generatedWavBlobRef.current = null;
        sampleRateRef.current = 22050;
        setPlayerVisible(false);
        setDownloadReady(false);
        setTimeDisplay("0:00 / 0:00");
        resetGenerationTracking();
        syncPlayerUi(controller);

        const requestPayload = {
            text: normalizedText,
            language,
            voice_id: voice || undefined,
        };

        setIsGenerating(true);
        setIsCancelling(false);
        setStatus({ text: isRunpodMode ? "Submitting RunPod job..." : "Submitting local job...", tone: "idle" });
        setStreamProgress(10);

        try {
            const submitResponse = await submitTtsJob(requestPayload);
            const jobId = String(submitResponse?.id || "").trim();
            if (!jobId) {
                throw new Error("TTS job submit did not return a job id.");
            }

            writePendingJobSnapshot(jobId, requestPayload);
            setActiveJobId(jobId);
            activeJobIdRef.current = jobId;
            setStatus({ text: "Job submitted. Waiting for status...", tone: "idle" });
            setStreamProgress(20);
            void pollJobUntilTerminal(jobId);
        } catch (error) {
            setIsGenerating(false);
            setIsCancelling(false);
            clearActivePendingJob();
            setStatus({ text: `Error: ${error instanceof Error ? error.message : String(error)}`, tone: "error" });
            resetGenerationTracking();
        }
    }, [
        clearActivePendingJob,
        isGenerating,
        isRunpodMode,
        language,
        pollJobUntilTerminal,
        resetGenerationTracking,
        syncPlayerUi,
        text,
        voice,
    ]);

    const cancelGeneration = useCallback(async () => {
        const jobId = activeJobIdRef.current;
        if (!jobId || !isGenerating) return;

        setIsCancelling(true);
        setStatus({ text: "Cancelling active job...", tone: "idle" });

        try {
            await cancelTtsJob(jobId);
            setStatus({ text: "Cancel requested. Waiting for terminal status...", tone: "idle" });
        } catch (error) {
            setIsCancelling(false);
            setStatus({ text: `Cancel failed: ${error instanceof Error ? error.message : String(error)}`, tone: "error" });
        }
    }, [isGenerating]);

    const handlePrimaryAction = useCallback(() => {
        if (isGenerating) {
            void cancelGeneration();
            return;
        }
        void startGeneration();
    }, [cancelGeneration, isGenerating, startGeneration]);

    const downloadAudio = useCallback(async () => {
        if (isGenerating) {
            setStatus({ text: "Wait for generation to finish before downloading.", tone: "error" });
            return;
        }

        if (!generatedWavBlobRef.current) {
            setStatus({ text: "Generate audio first.", tone: "error" });
            return;
        }

        setIsDownloading(true);
        try {
            triggerBlobDownload(generatedWavBlobRef.current, "speech.wav");
            setStatus({ text: "WAV downloaded.", tone: "success" });
        } catch (error) {
            setStatus({ text: `Download error: ${error instanceof Error ? error.message : String(error)}`, tone: "error" });
        } finally {
            setIsDownloading(false);
        }
    }, [isGenerating]);

    const handleTogglePlayback = useCallback(() => {
        const controller = audioControllerRef.current;
        if (!controller) return;
        if (controller.isPlaying) {
            controller.pause();
            return;
        }
        controller.play();
        setPlayerVisible(true);
    }, []);

    const handleSeek = useCallback((event) => {
        const controller = audioControllerRef.current;
        if (!controller) return;
        const inputValue = Number(event.target.value);
        const clampedValue = clampPercent(inputValue);
        controller.seek(clampedValue / 100);
    }, []);

    const playerStateClass = playerMode === "playing"
        ? "player-state-live"
        : playerMode === "buffering" || (isGenerating && !playerVisible)
            ? "player-state-buffer"
            : playerVisible || loadedPercent > 0
                ? "player-state-ready"
                : "player-state-idle";

    const playerStateLabel = playerMode === "playing"
        ? "Playing"
        : playerMode === "buffering"
            ? "Buffering"
            : playerVisible || loadedPercent > 0
                ? "Ready"
                : isGenerating
                    ? "Preparing"
                    : "Idle";

    const playerDescription = playerVisible
        ? "Play or scrub through generated audio. Download is available."
        : isGenerating
            ? (isRunpodMode
                ? "RunPod is generating audio. Player unlocks after completion."
                : "Generating audio. Player unlocks when WAV is ready.")
            : "Generate speech to activate playback controls.";

    const generationLabel = isGenerating
        ? (isCancelling ? "Cancelling..." : "Cancel")
        : "Generate Voice";
    const textCharCount = getNormalizedTextCharCount(text);
    const isTextTooLong = textCharCount > MAX_TEXT_CHARACTERS;
    const maxTextCharacters = MAX_TEXT_CHARACTERS;

    const canDownload = downloadReady && !isGenerating && !isDownloading && !!generatedWavBlobRef.current;
    const statusClass = status.tone === "success"
        ? "status-success"
        : status.tone === "error"
            ? "status-error"
            : "status-idle";

    const runtimeChunkProgressText = totalChunkCount > 0
        ? `Processed chunks: ${Math.min(loadedChunkCount, totalChunkCount)} of ${totalChunkCount}`
        : `Processed chunks: ${Math.max(0, loadedChunkCount)} of ?`;
    const hasChunkProgress = totalChunkCount > 0 || loadedChunkCount > 0;
    const actionStatusText = isGenerating
        ? (isCancelling
            ? status.text
            : (hasChunkProgress ? runtimeChunkProgressText : status.text))
        : status.text;
    const actionStatusClass = isGenerating ? "status-idle" : statusClass;
    const isPrimaryActionDisabled = isTextTooLong || (isGenerating && isCancelling);

    return {
        text,
        textCharCount,
        isTextTooLong,
        maxTextCharacters,
        voice,
        language,
        voices,
        voicesReady,
        voiceLoadFailed,
        selectedVoice,
        referenceVoices,
        presetVoices,
        backendNeedsRestart,
        status,
        statusClass,
        actionStatusText,
        actionStatusClass,
        isGenerating,
        isCancelling,
        activeJobId,
        streamProgress,
        generationLabel,
        isPrimaryActionDisabled,
        playerVisible,
        isPlaying,
        loadedPercent,
        playedPercent,
        timeDisplay,
        playerStateClass,
        playerStateLabel,
        playerDescription,
        canDownload,
        isDownloading,
        onTextChange: handleTextChange,
        onVoiceChange: setVoice,
        onLanguageChange: setLanguage,
        onPrimaryAction: handlePrimaryAction,
        onDownload: downloadAudio,
        onTogglePlayback: handleTogglePlayback,
        onSeek: handleSeek,
    };
};
