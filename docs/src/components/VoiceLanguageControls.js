import { html } from "../lib/html.js";

export const VoiceLanguageControls = ({
    voice,
    voices,
    voicesReady,
    voiceLoadFailed,
    onVoiceChange,
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
                            <optgroup label="Kokoro Voices">
                                ${voices.map((item) => html`<option key=${item.id} value=${item.id}>${item.name}</option>`)}
                            </optgroup>
                        `}
                </select>
            </div>
        </div>
    </section>
`;
