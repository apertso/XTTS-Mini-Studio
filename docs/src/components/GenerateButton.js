import { html } from "../lib/html.js";
import { AUTOPLAY_CHUNK_THRESHOLD } from "../constants.js";
import { clampPercent } from "../utils/audioUtils.js";

export const GenerateButton = ({
    disabled,
    isGenerating,
    label,
    progress,
    bufferCount,
    showBuffer,
    onClick,
}) => {
    const safeProgress = clampPercent(progress);
    const safeBuffer = Math.max(0, Math.min(AUTOPLAY_CHUNK_THRESHOLD, Number(bufferCount) || 0));

    return html`
        <button
            className=${`generate-btn ${isGenerating ? "is-generating" : ""}`}
            type="button"
            onClick=${onClick}
            disabled=${disabled}
        >
            ${isGenerating
                ? html`<span className="generate-progress" style=${{ width: `${safeProgress}%` }}></span>`
                : null}
            <span className="generate-content">
                <span className="generate-label">${label}</span>
                ${isGenerating && showBuffer ? html`
                    <span className="generate-buffer" aria-hidden="true">
                        ${Array.from({ length: AUTOPLAY_CHUNK_THRESHOLD }, (_, index) => html`
                            <span className=${`buffer-slot ${index < safeBuffer ? "buffer-slot-filled" : ""}`}></span>
                        `)}
                    </span>
                ` : null}
            </span>
        </button>
    `;
};
