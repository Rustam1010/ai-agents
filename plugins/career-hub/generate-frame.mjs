import {readFile,writeFile} from "node:fs/promises";
const html=await readFile(new URL("./ui.html",import.meta.url),"utf8");
const addon=await readFile(new URL("./frame-addon.js",import.meta.url),"utf8");
const value=html.replace("/* CAREER_ADDON */",addon);
await writeFile(new URL("./frame.generated.ts",import.meta.url),"// Generated from ui.html and frame-addon.js.\nexport const frameHtml = "+JSON.stringify(value)+";\n");
