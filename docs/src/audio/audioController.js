import { clamp } from "../utils/audioUtils.js";

export const createAudioController = ({ onUi, onDone }) => ({
    audioContext: null,
    isPlaying: false,
    isBuffering: false,
    currentTime: 0,
    loadedDuration: 0,
    sampleRate: 22050,
    chunks: [],
    chunkDurations: [],
    nextChunkIndex: 0,
    nextChunkOffset: 0,
    nextStartTime: 0,
    queuedMediaUntil: 0,
    scheduledChunks: [],
    schedulerTimer: null,
    progressFrame: null,
    generationDone: false,
    completionNotified: false,
    transportStartContextTime: 0,
    transportStartMediaTime: 0,
    lookAheadSeconds: 1.2,
    schedulerIntervalMs: 80,
    scheduleLeadInSeconds: 0.04,
    sourceId: 0,

    initContext() {
        if (!this.audioContext) {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: this.sampleRate,
            });
        }
        if (this.audioContext.state === "suspended") {
            this.audioContext.resume();
        }
    },

    clearSchedulerTimer() {
        if (this.schedulerTimer) {
            clearTimeout(this.schedulerTimer);
            this.schedulerTimer = null;
        }
    },

    stopProgressLoop() {
        if (this.progressFrame) {
            cancelAnimationFrame(this.progressFrame);
            this.progressFrame = null;
        }
    },

    startProgressLoop() {
        if (this.progressFrame) return;
        const step = () => {
            this.progressFrame = null;
            if (!this.isPlaying) return;
            this.syncCurrentTime();
            onUi(this);
            this.progressFrame = requestAnimationFrame(step);
        };
        this.progressFrame = requestAnimationFrame(step);
    },

    scheduleHeartbeat() {
        this.clearSchedulerTimer();
        if (!this.isPlaying) return;
        this.schedulerTimer = setTimeout(() => {
            this.schedulerTimer = null;
            if (!this.isPlaying) return;
            this.maybeSchedule();
            this.maybeFinishPlayback();
            this.scheduleHeartbeat();
        }, this.schedulerIntervalMs);
    },

    addChunk(int16Data) {
        const duration = int16Data.length / this.sampleRate;
        this.chunks.push(int16Data);
        this.chunkDurations.push(duration);
        this.loadedDuration += duration;
        if (this.isPlaying) {
            this.maybeSchedule();
        }
        onUi(this);
    },

    getFloatChunk(index) {
        const int16Data = this.chunks[index];
        const float32Data = new Float32Array(int16Data.length);
        for (let i = 0; i < int16Data.length; i += 1) {
            float32Data[i] = int16Data[i] / 32767;
        }
        return float32Data;
    },

    getChunkPosition(targetTime) {
        let accumulatedTime = 0;
        for (let i = 0; i < this.chunkDurations.length; i += 1) {
            const chunkDuration = this.chunkDurations[i];
            if (accumulatedTime + chunkDuration > targetTime) {
                return { chunkIndex: i, chunkOffset: targetTime - accumulatedTime };
            }
            accumulatedTime += chunkDuration;
        }
        return { chunkIndex: this.chunkDurations.length, chunkOffset: 0 };
    },

    clearScheduledChunks() {
        const scheduled = this.scheduledChunks;
        this.scheduledChunks = [];
        scheduled.forEach((item) => {
            item.source.onended = null;
            try {
                item.source.stop();
            } catch (_error) {
                // already stopped
            }
        });
    },

    prepareTransportFromCurrentTime() {
        const { chunkIndex, chunkOffset } = this.getChunkPosition(this.currentTime);
        const startAt = this.audioContext.currentTime + this.scheduleLeadInSeconds;
        this.nextChunkIndex = chunkIndex;
        this.nextChunkOffset = chunkOffset;
        this.nextStartTime = startAt;
        this.queuedMediaUntil = this.currentTime;
        this.transportStartContextTime = startAt;
        this.transportStartMediaTime = this.currentTime;
        this.isBuffering = false;
    },

    syncCurrentTime() {
        if (!this.audioContext || !this.isPlaying || this.isBuffering) {
            this.currentTime = clamp(this.currentTime, 0, this.loadedDuration);
            return;
        }

        const elapsed = Math.max(0, this.audioContext.currentTime - this.transportStartContextTime);
        const projectedTime = this.transportStartMediaTime + elapsed;
        const playableUntil = Math.min(Math.max(this.queuedMediaUntil, this.currentTime), this.loadedDuration);
        this.currentTime = clamp(projectedTime, 0, playableUntil);

        if (
            this.scheduledChunks.length === 0
            && this.nextChunkIndex >= this.chunks.length
            && !this.generationDone
            && this.currentTime >= this.loadedDuration - 0.01
        ) {
            this.isBuffering = true;
        }
    },

    play() {
        if (this.isPlaying || this.chunks.length === 0) return;
        if (this.generationDone && this.currentTime >= this.loadedDuration - 0.001) {
            this.currentTime = 0;
        }

        this.initContext();
        this.isPlaying = true;
        this.completionNotified = false;
        this.prepareTransportFromCurrentTime();
        this.startProgressLoop();
        this.maybeSchedule();
        this.scheduleHeartbeat();
        onUi(this);
    },

    maybeSchedule() {
        if (!this.isPlaying) return;
        if (!this.audioContext) {
            this.initContext();
        }

        if (this.scheduledChunks.length === 0 && this.nextChunkIndex < this.chunks.length) {
            this.nextStartTime = this.audioContext.currentTime + this.scheduleLeadInSeconds;
            this.transportStartContextTime = this.nextStartTime;
            this.transportStartMediaTime = this.currentTime;
            this.queuedMediaUntil = this.currentTime;
            this.isBuffering = false;
        }

        while (
            this.nextChunkIndex < this.chunks.length
            && this.nextStartTime - this.audioContext.currentTime < this.lookAheadSeconds
        ) {
            const chunkIndex = this.nextChunkIndex;
            const chunkOffset = this.nextChunkOffset;
            const floatData = this.getFloatChunk(chunkIndex);
            const audioBuf = this.audioContext.createBuffer(1, floatData.length, this.sampleRate);
            audioBuf.getChannelData(0).set(floatData);

            const source = this.audioContext.createBufferSource();
            source.buffer = audioBuf;
            source.connect(this.audioContext.destination);
            source.start(this.nextStartTime, chunkOffset);

            const chunkDuration = Math.max(0, floatData.length / this.sampleRate - chunkOffset);
            const mediaStart = this.queuedMediaUntil;
            const mediaEnd = mediaStart + chunkDuration;
            const id = ++this.sourceId;

            this.scheduledChunks.push({ id, source, chunkIndex, mediaEnd });
            source.onended = () => this.onChunkEnded(id, mediaEnd);

            this.queuedMediaUntil = mediaEnd;
            this.nextStartTime += chunkDuration;
            this.nextChunkIndex += 1;
            this.nextChunkOffset = 0;
        }
        onUi(this);
    },

    onChunkEnded(sourceId, mediaEnd) {
        this.scheduledChunks = this.scheduledChunks.filter((item) => item.id !== sourceId);
        if (!this.isPlaying) return;
        this.currentTime = clamp(Math.max(this.currentTime, mediaEnd), 0, this.loadedDuration);

        if (this.scheduledChunks.length === 0 && this.nextChunkIndex >= this.chunks.length && !this.generationDone) {
            this.isBuffering = true;
        }

        this.maybeSchedule();
        this.maybeFinishPlayback();
        onUi(this);
    },

    maybeFinishPlayback() {
        if (!this.isPlaying || !this.generationDone || this.completionNotified) return;
        if (this.nextChunkIndex < this.chunks.length || this.scheduledChunks.length > 0) return;
        this.completionNotified = true;
        this.isPlaying = false;
        this.isBuffering = false;
        this.currentTime = this.loadedDuration;
        this.clearSchedulerTimer();
        this.stopProgressLoop();
        onUi(this);
        onDone();
    },

    markGenerationDone() {
        this.generationDone = true;
        this.maybeSchedule();
        this.maybeFinishPlayback();
        onUi(this);
    },

    pause() {
        if (!this.isPlaying) return;
        this.syncCurrentTime();
        this.isPlaying = false;
        this.isBuffering = false;
        this.clearSchedulerTimer();
        this.stopProgressLoop();
        this.clearScheduledChunks();
        onUi(this);
    },

    toggle() {
        this.isPlaying ? this.pause() : this.play();
    },

    seek(position) {
        if (this.loadedDuration === 0) return;
        const targetTime = clamp(position * this.loadedDuration, 0, this.loadedDuration);
        const wasPlaying = this.isPlaying;
        if (wasPlaying) this.pause();

        this.currentTime = targetTime;
        this.queuedMediaUntil = targetTime;
        this.isBuffering = false;
        onUi(this);
        if (wasPlaying) this.play();
    },

    reset() {
        this.pause();
        this.currentTime = 0;
        this.loadedDuration = 0;
        this.chunks = [];
        this.chunkDurations = [];
        this.nextChunkIndex = 0;
        this.nextChunkOffset = 0;
        this.nextStartTime = 0;
        this.queuedMediaUntil = 0;
        this.generationDone = false;
        this.completionNotified = false;
        this.transportStartContextTime = 0;
        this.transportStartMediaTime = 0;
        this.sourceId = 0;
        this.clearSchedulerTimer();
        this.stopProgressLoop();
        if (this.audioContext) {
            try {
                this.audioContext.close();
            } catch (_error) {
                // already closed
            }
            this.audioContext = null;
        }
        onUi(this);
    },
});
