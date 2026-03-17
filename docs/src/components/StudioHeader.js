import { html } from "../lib/html.js";

export const StudioHeader = () => html`
    <header className="studio-header">
        <h1 className="studio-title">XTTS Mini Studio</h1>
        <span className="stream-badge">
            <span className="stream-badge-dot"></span>
            Streaming Ready
        </span>
    </header>
`;
