import { html } from "../lib/html.js";

export const TextInputPanel = ({ text, onTextChange, onSubmit }) => html`
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
    </section>
`;
