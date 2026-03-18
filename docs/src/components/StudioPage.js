import { html } from "../lib/html.js";
import { GenerateButton } from "./GenerateButton.js";
import { PlayerPanel } from "./PlayerPanel.js";
import { StudioHeader } from "./StudioHeader.js";
import { TextInputPanel } from "./TextInputPanel.js";
import { VoiceLanguageControls } from "./VoiceLanguageControls.js";
import { useTtsStudio } from "../state/useTtsStudio.js";

export const StudioPage = () => {
    const studio = useTtsStudio();

    return html`
        <div className="page-shell">
            <main className="studio-card">
                ${StudioHeader()}

                ${TextInputPanel({
                    text: studio.text,
                    onTextChange: studio.onTextChange,
                    onSubmit: studio.onSpeak,
                })}

                ${VoiceLanguageControls({
                    voice: studio.voice,
                    language: studio.language,
                    voices: studio.voices,
                    voicesReady: studio.voicesReady,
                    voiceLoadFailed: studio.voiceLoadFailed,
                    selectedVoice: studio.selectedVoice,
                    referenceVoices: studio.referenceVoices,
                    presetVoices: studio.presetVoices,
                    backendNeedsRestart: studio.backendNeedsRestart,
                    onVoiceChange: studio.onVoiceChange,
                    onLanguageChange: studio.onLanguageChange,
                })}

                <section className="action-panel">
                    ${GenerateButton({
                        disabled: studio.isGenerating,
                        isGenerating: studio.isGenerating,
                        label: studio.generationLabel,
                        progress: studio.streamProgress,
                        bufferCount: studio.bufferCount,
                        showBuffer: studio.isStreamingEnabled,
                        onClick: studio.onSpeak,
                    })}
                    <p className=${`status-line ${studio.statusClass}`}>${studio.status.text}</p>
                </section>

                ${PlayerPanel({
                    playerVisible: studio.playerVisible,
                    isPlaying: studio.isPlaying,
                    loadedPercent: studio.loadedPercent,
                    playedPercent: studio.playedPercent,
                    timeDisplay: studio.timeDisplay,
                    onTogglePlayback: studio.onTogglePlayback,
                    onSeek: studio.onSeek,
                    onDownload: studio.onDownload,
                    canDownload: studio.canDownload,
                    isDownloading: studio.isDownloading,
                    playerStateClass: studio.playerStateClass,
                    playerStateLabel: studio.playerStateLabel,
                    playerDescription: studio.playerDescription,
                })}
            </main>
        </div>
    `;
};
