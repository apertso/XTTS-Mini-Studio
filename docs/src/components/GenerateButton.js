import { html } from "../lib/html.js";
import { clampPercent } from "../utils/audioUtils.js";

export const GenerateButton = ({
    disabled,
    isGenerating,
    label,
    progress,
    onClick,
}) => {
    const safeProgress = clampPercent(progress);

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
            </span>
        </button>
    `;
};
