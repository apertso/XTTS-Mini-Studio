import { html } from "../lib/html.js";

export const StudioHeader = () => html`
    <header className="studio-header">
        <h1 className="studio-title">XTTS Mini Studio</h1>
        <span className="engine-badge">
            <span className="engine-badge-dot"></span>
            Powered by coqui/XTTS-v2
        </span>
    </header>
`;
