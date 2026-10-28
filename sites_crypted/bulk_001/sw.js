/* Service worker : sert les fichiers déchiffrés (en mémoire) sous le chemin virtuel app/ */
"use strict";

const files = new Map();

// Prendre le contrôle immédiatement, même à la première visite
self.addEventListener("install", (e) => e.waitUntil(self.skipWaiting()));
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("message", (event) => {
  const data = event.data;
  if (data && data.files) {
    files.clear();
    for (const [name, buf] of Object.entries(data.files)) {
      files.set(name, new Uint8Array(buf));
    }
    const keys = [...files.keys()];
    console.info("[sw] fichiers servis :", keys.slice(0, 5).join(", "),
                 keys.length > 5 ? "…" : "");
  }
});

const MIME = {
  html: "text/html", htm: "text/html",
  js: "text/javascript", mjs: "text/javascript",
  css: "text/css", json: "application/json",
  png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg",
  gif: "image/gif", svg: "image/svg+xml", ico: "image/x-icon",
  webp: "image/webp", woff: "font/woff", woff2: "font/woff2",
  ttf: "font/ttf", otf: "font/otf", wasm: "application/wasm",
  txt: "text/plain", md: "text/plain", csv: "text/csv",
  mp3: "audio/mpeg", mp4: "video/mp4", pdf: "application/pdf",
};

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;

  const scopePath = new URL(self.registration.scope).pathname;
  if (!url.pathname.startsWith(scopePath)) return;

  let name = url.pathname.slice(scopePath.length);
  if (!name.startsWith("app/")) return;
  name = name.slice(4) || "index.html";
  if (name.endsWith("/")) name += "index.html";
  try { name = decodeURIComponent(name); } catch (_) {}

  let data = files.get(name);
  if (!data) {
    // Tolérance : l'app peut être imbriquée dans un sous-dossier du zip
    // (ex. build/index.html au lieu de index.html)
    for (const [k, v] of files) {
      if (k === name || k.endsWith("/" + name)) { data = v; break; }
    }
  }
  if (!data) {
    event.respondWith(new Response("Not found", { status: 404 }));
    return;
  }
  const ext = name.includes(".") ? name.split(".").pop().toLowerCase() : "";
  event.respondWith(new Response(data, {
    headers: { "Content-Type": MIME[ext] || "application/octet-stream" },
  }));
});
