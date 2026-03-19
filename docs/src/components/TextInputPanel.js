import { html } from "../lib/html.js";

export const TextInputPanel = ({
    text,
    charCount,
    maxTextCharacters,
    isTextTooLong,
    onTextChange,
    onSubmit,
}) => {
    const safeCharCount = Math.max(0, Number(charCount) || 0);
    const safeMaxChars = Math.max(1, Number(maxTextCharacters) || 1);
    const overflowCount = Math.max(0, safeCharCount - safeMaxChars);

    return html`
    <section className="input-panel">
        <textarea
            id="tts-text"
            className="text-area"
            placeholder="Enter text to synthesize..."
            value=${text}
            aria-invalid=${isTextTooLong}
            onChange=${(event) => onTextChange(event.target.value)}
            onKeyDown=${(event) => {
                if (event.key === "Enter" && event.ctrlKey) {
                    onSubmit();
                }
            }}
        ></textarea>
        <div className="text-meta">
            <span className=${`text-char-count ${isTextTooLong ? "text-char-count-error" : ""}`}>
                ${safeCharCount}/${safeMaxChars}
            </span>
        </div>
        ${isTextTooLong ? html`
            <p className="text-limit-warning">
                Text exceeds maximum length by ${overflowCount} symbols.
            </p>
        ` : null}
    </section>
`;
};
