import { html } from "../lib/html.js";

export const TextInputPanel = ({ text, charCount, onTextChange, onSubmit }) => html`
    <section className="input-panel">
        <textarea
            id="tts-text"
            className="text-area"
            placeholder="Enter text to synthesize..."
            value=${text}
            onChange=${(event) => onTextChange(event.target.value)}
            onKeyDown=${(event) => {
                if (event.key === "Enter" && event.ctrlKey) {
                    onSubmit();
                }
            }}
        ></textarea>
        <div className="text-meta">
            <span className="text-char-count">${Number(charCount) || 0} symbols</span>
        </div>
    </section>
`;
