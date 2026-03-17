import { html } from "../lib/html.js";

export const VoiceLanguageControls = ({
    voice,
    language,
    voices,
    voicesReady,
    voiceLoadFailed,
    selectedVoice,
    referenceVoices,
    presetVoices,
    backendNeedsRestart,
    onVoiceChange,
    onLanguageChange,
}) => html`
    <section className="controls-grid">
        <div className="control-group">
            <div className="panel-row">
                <label className="field-label" htmlFor="voice">Voice</label>
            </div>
            <div className="select-shell">
                <select
                    id="voice"
                    className="select-field"
                    value=${voice}
                    onChange=${(event) => onVoiceChange(event.target.value)}
                    disabled=${!voicesReady}
                >
                    ${voices.length === 0
                        ? html`<option value="">${voiceLoadFailed ? "Voices unavailable" : "Loading voices..."}</option>`
                        : html`
                            ${referenceVoices.length > 0 ? html`
                                <optgroup label="Reference Voices">
                                    ${referenceVoices.map((item) => html`<option key=${item.id} value=${item.id}>${item.name}</option>`)}
                                </optgroup>
                            ` : null}
                            ${presetVoices.length > 0 ? html`
                                <optgroup label="XTTS Presets">
                                    ${presetVoices.map((item) => html`<option key=${item.id} value=${item.id}>${item.name}</option>`)}
                                </optgroup>
                            ` : null}
                        `}
                </select>
            </div>
        </div>

        <div className="control-group">
            <div className="panel-row">
                <label className="field-label" htmlFor="language">Language</label>
            </div>
            <div className="select-shell">
                <select
                    id="language"
                    className="select-field"
                    value=${language}
                    onChange=${(event) => onLanguageChange(event.target.value)}
                >
                    <option value="en">English</option>
                    <option value="ru">Russian</option>
                    <option value="es">Spanish</option>
                    <option value="fr">French</option>
                    <option value="de">German</option>
                    <option value="zh">Chinese</option>
                    <option value="ja">Japanese</option>
                    <option value="pt">Portuguese</option>
                    <option value="it">Italian</option>
                    <option value="pl">Polish</option>
                    <option value="tr">Turkish</option>
                    <option value="ar">Arabic</option>
                </select>
            </div>
        </div>
    </section>
`;
