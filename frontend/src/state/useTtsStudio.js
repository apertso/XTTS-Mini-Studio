import { React } from "../lib/html.js";
import {
    API_BASE_URL,
    API_STREAMING_ENABLED,
    AUTOPLAY_CHUNK_THRESHOLD,
    DEFAULT_LANGUAGE,
    DEFAULT_READING_MODE,
    STORAGE_KEYS,
} from "../constants.js";
import { createAudioController } from "../audio/audioController.js";
import {
    clampPercent,
    concatUint8,
    createWavBlobFromChunks,
    formatTime,
    readUint32LE,
    triggerBlobDownload,
} from "../utils/audioUtils.js";

const { useCallback, useEffect, useMemo, useRef, useState } = React;

const INITIAL_STATUS = { text: "Ready to synthesize.", tone: "idle" };

export const useTtsStudio = () => {
    const [text, setText] = useState("");
    const [voice, setVoice] = useState("");
    const [language, setLanguage] = useState(DEFAULT_LANGUAGE);
    const [voices, setVoices] = useState([]);
    const [voicesReady, setVoicesReady] = useState(false);
    const [voiceLoadFailed, setVoiceLoadFailed] = useState(false);
    const [status, setStatus] = useState(INITIAL_STATUS);
    const [isGenerating, setIsGenerating] = useState(false);
    const [streamProgress, setStreamProgress] = useState(0);
    const [bufferCount, setBufferCount] = useState(0);
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

    const audioControllerRef = useRef(null);
    const allAudioChunksRef = useRef([]);
    const generatedWavBlobRef = useRef(null);
    const sampleRateRef = useRef(22050);
    const totalChunksRef = useRef(0);
    const loadedChunksRef = useRef(0);
    const autoStartUsedRef = useRef(false);
    const autoStartLockedByUserRef = useRef(false);

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

    const backendNeedsRestart = voicesReady
        && !voiceLoadFailed
        && voices.length > 0
        && referenceVoices.length === 0;

    const syncPlayerUi = useCallback((controller) => {
        const totalChunks = totalChunksRef.current;
        const loadedChunks = loadedChunksRef.current;
        const safeTotalChunks = Math.max(totalChunks, loadedChunks, 1);

        const loaded = (totalChunks > 0 || loadedChunks > 0)
            ? (loadedChunks / safeTotalChunks) * 100
            : (controller.loadedDuration > 0 ? 100 : 0);
        const played = controller.loadedDuration > 0
            ? (controller.currentTime / controller.loadedDuration) * 100
            : 0;

        const loadedClamped = clampPercent(loaded);
        const playedClamped = clampPercent(Math.min(played, loadedClamped > 0 ? loadedClamped : 100));

        setLoadedPercent(loadedClamped);
        setPlayedPercent(playedClamped);
        setTimeDisplay(`${formatTime(controller.currentTime)} / ${formatTime(controller.loadedDuration)}`);
        setIsPlaying(controller.isPlaying);
        setPlayerMode(
            controller.isPlaying
                ? (controller.isBuffering ? "buffering" : "playing")
                : (controller.loadedDuration > 0 ? "ready" : "idle"),
        );
    }, []);

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

        setText(savedText);
        setLanguage(savedLanguage);

        let cancelled = false;
        (async () => {
            try {
                const response = await fetch(`${API_BASE_URL}/api/voices`);
                const data = await response.json();
                if (cancelled) return;

                const availableVoices = Array.isArray(data.voices) ? data.voices : [];
                setVoices(availableVoices);
                setVoicesReady(true);
                setVoiceLoadFailed(false);

                if (availableVoices.length === 0) {
                    setStatus({ text: "No voices available.", tone: "error" });
                } else if (!availableVoices.some((item) => item.source_type === "reference")) {
                    setStatus({
                        text: "Server is missing reference voices. Restart backend if needed.",
                        tone: "error",
                    });
                }

                const fallbackVoice = availableVoices[0]?.id || "";
                const hasSavedVoice = availableVoices.some((item) => item.id === savedVoice);
                setVoice(hasSavedVoice ? savedVoice : fallbackVoice);
            } catch (error) {
                if (cancelled) return;
                console.error("Failed to load voices:", error);
                setVoicesReady(true);
                setVoiceLoadFailed(true);
                setStatus({ text: "Failed to load voices.", tone: "error" });
            }
        })();

        return () => {
            cancelled = true;
            audioControllerRef.current?.reset();
        };
    }, [syncPlayerUi]);

    useEffect(() => {
        localStorage.setItem(STORAGE_KEYS.text, text);
    }, [text]);

    useEffect(() => {
        localStorage.setItem(STORAGE_KEYS.voice, voice);
    }, [voice]);

    useEffect(() => {
        localStorage.setItem(STORAGE_KEYS.language, language);
    }, [language]);

    const speak = useCallback(async () => {
        if (!text.trim()) {
            setStatus({ text: "Enter text before generating audio.", tone: "error" });
            return;
        }

        const controller = audioControllerRef.current;
        if (!controller) {
            setStatus({ text: "Player is not initialized yet.", tone: "error" });
            return;
        }

        controller.reset();

        generatedWavBlobRef.current = null;
        allAudioChunksRef.current = [];
        sampleRateRef.current = 22050;
        totalChunksRef.current = 0;
        loadedChunksRef.current = 0;
        autoStartUsedRef.current = false;
        autoStartLockedByUserRef.current = false;

        setIsGenerating(true);
        setStreamProgress(2);
        setBufferCount(0);
        setLoadedChunkCount(0);
        setTotalChunkCount(0);
        setPlayerVisible(false);
        setDownloadReady(false);
        setTimeDisplay("0:00 / 0:00");
        setStatus({ text: "Preparing...", tone: "idle" });
        syncPlayerUi(controller);

        // Non-streaming mode (RunPod compatibility)
        if (!API_STREAMING_ENABLED) {
            try {
                const response = await fetch(`${API_BASE_URL}/tts/download`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        text: text.trim(),
                        language,
                        voice_id: voice || undefined,
                        reading_mode: DEFAULT_READING_MODE,
                    }),
                });

                if (!response.ok) {
                    const errorPayload = await response.json().catch(() => ({ error: "Unknown generation error" }));
                    throw new Error(errorPayload.error || "Generation failed");
                }

                const wavBlob = await response.blob();
                generatedWavBlobRef.current = wavBlob;

                // Extract audio data for player
                const arrayBuffer = await wavBlob.arrayBuffer();
                const wavData = new Uint8Array(arrayBuffer);
                // Skip WAV header (44 bytes) and feed raw PCM to player
                const pcmData = new Int16Array(wavData.buffer, 44);
                controller.addChunk(pcmData);
                controller.markGenerationDone();

                sampleRateRef.current = 22050; // Default for XTTS v2
                controller.sampleRate = sampleRateRef.current;

                setDownloadReady(true);
                setPlayerVisible(true);
                setStreamProgress(100);
                setIsGenerating(false);
                setStatus({ text: "Ready. You can listen or download WAV.", tone: "success" });
                syncPlayerUi(controller);
            } catch (error) {
                console.error("[TTS] Non-streaming error:", error);
                setIsGenerating(false);
                setStatus({ text: `Error: ${error.message}`, tone: "error" });
            }
            return;
        }

        try {
            const response = await fetch(`${API_BASE_URL}/tts`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    text: text.trim(),
                    language,
                    voice_id: voice || undefined,
                    reading_mode: DEFAULT_READING_MODE,
                }),
            });

            if (!response.ok) {
                const errorPayload = await response.json().catch(() => ({ error: "Unknown generation error" }));
                throw new Error(errorPayload.error || "Generation failed");
            }

            sampleRateRef.current = parseInt(response.headers.get("X-Audio-Sample-Rate"), 10) || 22050;
            controller.sampleRate = sampleRateRef.current;

            if (!response.body) {
                throw new Error("Audio stream is unavailable");
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let readBuffer = new Uint8Array(0);
            let parseState = "metadata_size";
            let expectedMetadataSize = 0;
            let expectedAudioSize = 0;
            const chunkTimes = [];
            let lastChunkTime = Date.now();

            while (true) {
                const { done, value } = await reader.read();
                if (done) {
                    controller.markGenerationDone();
                    break;
                }

                readBuffer = concatUint8(readBuffer, value);

                while (readBuffer.length > 0) {
                    if (parseState === "metadata_size") {
                        if (readBuffer.length < 4) break;
                        expectedMetadataSize = readUint32LE(readBuffer, 0);
                        readBuffer = readBuffer.slice(4);
                        parseState = "metadata";
                    }

                    if (parseState === "metadata") {
                        if (readBuffer.length < expectedMetadataSize) break;
                        const metadataBytes = readBuffer.slice(0, expectedMetadataSize);
                        const metadata = JSON.parse(decoder.decode(metadataBytes));
                        readBuffer = readBuffer.slice(expectedMetadataSize);

                        const metadataTotal = Number(metadata.t);
                        const metadataLoaded = Number(metadata.c) + 1;
                        const safeLoaded = Number.isFinite(metadataLoaded)
                            ? Math.max(0, metadataLoaded)
                            : loadedChunksRef.current;
                        const safeTotal = Number.isFinite(metadataTotal)
                            ? Math.max(0, metadataTotal)
                            : totalChunksRef.current;
                        const safeAudioBytes = Number.isFinite(Number(metadata.s))
                            ? Math.max(0, Number(metadata.s))
                            : 0;

                        loadedChunksRef.current = safeLoaded;
                        totalChunksRef.current = Math.max(safeTotal, safeLoaded, 1);
                        expectedAudioSize = safeAudioBytes;

                        const now = Date.now();
                        chunkTimes.push(now - lastChunkTime);
                        lastChunkTime = now;

                        const displayLoaded = Math.min(loadedChunksRef.current, totalChunksRef.current);
                        const progress = clampPercent((displayLoaded / totalChunksRef.current) * 100);
                        setStreamProgress(progress);
                        setBufferCount(Math.min(loadedChunksRef.current, AUTOPLAY_CHUNK_THRESHOLD));
                        setLoadedChunkCount(displayLoaded);
                        setTotalChunkCount(totalChunksRef.current);

                        if (chunkTimes.length > 1) {
                            const avgChunkTime = chunkTimes.reduce((a, b) => a + b, 0) / chunkTimes.length;
                            const remaining = Math.max(totalChunksRef.current - displayLoaded, 0) * avgChunkTime;
                            setStatus({
                                text: remaining > 1000
                                    ? `~${Math.ceil(remaining / 1000)}s left`
                                    : "Less than 1s left",
                                tone: "success",
                            });
                        } else {
                            setStatus({
                                text: "Estimating time left...",
                                tone: "success",
                            });
                        }

                        parseState = "audio";
                    }

                    if (parseState === "audio") {
                        if (readBuffer.length < expectedAudioSize) break;

                        const audioChunk = new Uint8Array(readBuffer.slice(0, expectedAudioSize));
                        readBuffer = readBuffer.slice(expectedAudioSize);
                        parseState = "metadata_size";
                        expectedAudioSize = 0;

                        allAudioChunksRef.current.push(audioChunk);

                        const int16Data = new Int16Array(
                            audioChunk.buffer,
                            audioChunk.byteOffset,
                            audioChunk.byteLength / 2,
                        );
                        controller.addChunk(int16Data);

                        if (
                            !controller.isPlaying
                            && !autoStartUsedRef.current
                            && !autoStartLockedByUserRef.current
                            && loadedChunksRef.current >= AUTOPLAY_CHUNK_THRESHOLD
                        ) {
                            controller.play();
                            autoStartUsedRef.current = true;
                            setPlayerVisible(true);
                        }
                    }
                }
            }

            if (allAudioChunksRef.current.length > 0) {
                generatedWavBlobRef.current = createWavBlobFromChunks(
                    allAudioChunksRef.current,
                    sampleRateRef.current,
                );
                setDownloadReady(true);
                setPlayerVisible(true);
            }

            setStreamProgress(100);
            setBufferCount(Math.min(loadedChunksRef.current, AUTOPLAY_CHUNK_THRESHOLD));
            setIsGenerating(false);
            setStatus({ text: "Ready. You can listen or download WAV.", tone: "success" });
        } catch (error) {
            console.error("[TTS] Stream error:", error);
            setIsGenerating(false);
            setStatus({ text: `Error: ${error.message}`, tone: "error" });
        }
    }, [language, text, voice, syncPlayerUi]);

    const downloadAudio = useCallback(async () => {
        if (!text.trim()) {
            setStatus({ text: "Enter text before downloading WAV.", tone: "error" });
            return;
        }

        setIsDownloading(true);

        try {
            if (generatedWavBlobRef.current) {
                triggerBlobDownload(generatedWavBlobRef.current, "speech.wav");
                setStatus({ text: "WAV downloaded.", tone: "success" });
                return;
            }

            const response = await fetch(`${API_BASE_URL}/tts/download`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    text: text.trim(),
                    language,
                    voice_id: voice || undefined,
                    reading_mode: DEFAULT_READING_MODE,
                }),
            });

            if (!response.ok) {
                const errorPayload = await response.json().catch(() => ({ error: "Unknown download error" }));
                throw new Error(errorPayload.error || "Download failed");
            }

            const wavBlob = await response.blob();
            triggerBlobDownload(wavBlob, "speech.wav");
            setStatus({ text: "WAV downloaded.", tone: "success" });
            setDownloadReady(true);
        } catch (error) {
            console.error("[TTS] Download error:", error);
            setStatus({ text: `Download error: ${error.message}`, tone: "error" });
        } finally {
            setIsDownloading(false);
        }
    }, [language, text, voice]);

    const handleTogglePlayback = useCallback(() => {
        const controller = audioControllerRef.current;
        if (!controller) return;

        if (controller.isPlaying) {
            autoStartLockedByUserRef.current = true;
            controller.pause();
            return;
        }

        autoStartLockedByUserRef.current = false;
        autoStartUsedRef.current = true;
        controller.play();
        setPlayerVisible(true);
    }, []);

    const handleSeek = useCallback((event) => {
        const controller = audioControllerRef.current;
        if (!controller) return;
        const inputValue = Number(event.target.value);
        const clampedValue = Math.min(inputValue, loadedPercent || 100);
        controller.seek(clampedValue / 100);
    }, [loadedPercent]);

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

    const playerDescription = playerMode === "buffering"
        ? "Buffer is refilling. Playback will continue automatically as new chunks arrive."
        : playerVisible
            ? "Play or scrub through generated audio while the stream is active."
            : isGenerating
                ? "Transport will unlock as soon as the first buffered chunks are ready."
                : "Generate speech to activate streaming playback controls.";

    const generationLabel = isGenerating
        ? (totalChunkCount > 0
            ? `Generating ${Math.min(loadedChunkCount, totalChunkCount)}/${totalChunkCount}`
            : "Generating...")
        : "Generate Voice";

    const canDownload = !isGenerating && !isDownloading && !!text.trim();
    const statusClass = status.tone === "success"
        ? "status-success"
        : status.tone === "error"
            ? "status-error"
            : "status-idle";

    return {
        text,
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
        isGenerating,
        streamProgress,
        bufferCount,
        generationLabel,
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
        onTextChange: setText,
        onVoiceChange: setVoice,
        onLanguageChange: setLanguage,
        onSpeak: speak,
        onDownload: downloadAudio,
        onTogglePlayback: handleTogglePlayback,
        onSeek: handleSeek,
    };
};
