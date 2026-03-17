import { React } from "./lib/html.js";
import { createRoot } from "https://esm.sh/react-dom@18.3.1/client";
import { StudioPage } from "./components/StudioPage.js";

const rootElement = document.getElementById("root");
if (rootElement) {
    const root = createRoot(rootElement);
    root.render(React.createElement(StudioPage));
}
