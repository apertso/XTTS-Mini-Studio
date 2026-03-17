export const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
export const clampPercent = (value) => clamp(Number.isFinite(value) ? value : 0, 0, 100);

export const formatTime = (seconds) => {
    const safeSeconds = Number.isFinite(seconds) ? Math.max(0, seconds) : 0;
    const mins = Math.floor(safeSeconds / 60);
    const secs = Math.floor(safeSeconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
};

export const concatUint8 = (a, b) => {
    const result = new Uint8Array(a.length + b.length);
    result.set(a, 0);
    result.set(b, a.length);
    return result;
};

export const readUint32LE = (buffer, offset) => {
    const bytes = buffer.slice(offset, offset + 4);
    return new DataView(bytes.buffer, bytes.byteOffset, 4).getUint32(0, true);
};

const writeString = (view, offset, value) => {
    for (let i = 0; i < value.length; i += 1) {
        view.setUint8(offset + i, value.charCodeAt(i));
    }
};

const createWavHeader = (sampleRate, dataSize) => {
    const buffer = new ArrayBuffer(44);
    const view = new DataView(buffer);
    const numChannels = 1;
    const bitsPerSample = 16;
    const bytesPerSample = bitsPerSample / 8;
    const blockAlign = numChannels * bytesPerSample;
    const byteRate = sampleRate * blockAlign;

    writeString(view, 0, "RIFF");
    view.setUint32(4, 36 + dataSize, true);
    writeString(view, 8, "WAVE");
    writeString(view, 12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, byteRate, true);
    view.setUint16(32, blockAlign, true);
    view.setUint16(34, bitsPerSample, true);
    writeString(view, 36, "data");
    view.setUint32(40, dataSize, true);
    return buffer;
};

export const createWavBlobFromChunks = (chunks, sampleRate) => {
    const totalAudioSize = chunks.reduce((acc, chunk) => acc + chunk.length, 0);
    const header = createWavHeader(sampleRate, totalAudioSize);
    const wavData = new Uint8Array(header.byteLength + totalAudioSize);
    wavData.set(new Uint8Array(header), 0);

    let offset = header.byteLength;
    for (const chunk of chunks) {
        wavData.set(chunk, offset);
        offset += chunk.length;
    }
    return new Blob([wavData], { type: "audio/wav" });
};

export const triggerBlobDownload = (blob, fileName) => {
    const blobUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = blobUrl;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(blobUrl);
};
