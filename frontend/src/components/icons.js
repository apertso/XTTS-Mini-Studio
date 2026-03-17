import { html } from "../lib/html.js";

export const PlayIcon = () => html`
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M7 5.25a1 1 0 0 1 1.52-.86l9.5 6.25a1 1 0 0 1 0 1.72l-9.5 6.25A1 1 0 0 1 7 17.5z"></path>
    </svg>
`;

export const PauseIcon = () => html`
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M7.5 5h3a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1h-3a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zm6 0h3a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1h-3a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z"></path>
    </svg>
`;

export const DownloadIcon = () => html`
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M11 4a1 1 0 1 1 2 0v8.59l2.3-2.29a1 1 0 1 1 1.4 1.41l-4 4a1 1 0 0 1-1.4 0l-4-4a1 1 0 0 1 1.4-1.41L11 12.59z"></path>
        <path d="M5 18a1 1 0 0 1 1-1h12a1 1 0 1 1 0 2H6a1 1 0 0 1-1-1z"></path>
    </svg>
`;
