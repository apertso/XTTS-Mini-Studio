import { html } from "../lib/html.js";
import { clampPercent } from "../utils/audioUtils.js";
import { DownloadIcon, PauseIcon, PlayIcon } from "./icons.js";

export const PlayerPanel = ({
    playerVisible,
    isPlaying,
    loadedPercent,
    playedPercent,
    timeDisplay,
    onTogglePlayback,
    onSeek,
    onDownload,
    canDownload,
    isDownloading,
    playerStateClass,
    playerStateLabel,
    playerDescription,
}) => {
    const safeLoaded = clampPercent(loadedPercent);
    const safePlayed = clampPercent(playedPercent);
    const timeParts = String(timeDisplay).split(" / ");
    const currentTime = timeParts[0] || "0:00";
    const totalTime = timeParts[1] || "0:00";

    return html`
        <section className="player-panel">
            ${playerVisible ? html`
                <div className="player-transport">
                    <button
                        className="play-btn"
                        type="button"
                        onClick=${onTogglePlayback}
                        disabled=${safeLoaded === 0}
                        aria-label=${isPlaying ? "Pause" : "Play"}
                    >
                        ${isPlaying ? PauseIcon() : PlayIcon()}
                    </button>

                    <div className="track-shell">
                        <div className="track">
                            <div className="track-rail"></div>
                            <div className="track-loaded" style=${{ width: `${safeLoaded}%` }}></div>
                            <div className="track-played" style=${{ width: `${safePlayed}%` }}></div>
                            <input
                                className="range-input"
                                type="range"
                                min="0"
                                max="100"
                                value=${safePlayed}
                                onChange=${onSeek}
                                disabled=${safeLoaded === 0}
                            />
                            <div className="track-times">
                                <span>${currentTime}</span>
                                <span>${totalTime}</span>
                            </div>
                        </div>
                    </div>
                    <button
                        className="download-btn"
                        type="button"
                        onClick=${onDownload}
                        disabled=${!canDownload}
                        aria-label=${isDownloading ? "Downloading WAV" : "Download WAV"}
                        title=${isDownloading ? "Downloading WAV" : "Download WAV"}
                    >
                        ${DownloadIcon()}
                    </button>
                </div>
            ` : null}
        </section>
    `;
};
