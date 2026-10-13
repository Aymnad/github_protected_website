#!/usr/bin/env python3
"""
protected_website.py — Génère un site chiffré déployable sur GitHub Pages.

Le dossier source (ex. export marimo `html-wasm`) est compressé (zip)
puis chiffré (AES-256-GCM, clé dérivée du code via PBKDF2-SHA256,
200 000 itérations). Le site généré contient :

    sites/<nom>/
    ├── index.html   page d'entrée (informations + demande du code)
    ├── app.enc      contenu chiffré — illisible sans le code
    ├── sw.js        service worker servant les fichiers déchiffrés en mémoire
    └── robots.txt   empêche l'indexation par les moteurs de recherche

Exemples :
    python protected_website.py                      # mode interactif
    python protected_website.py build/ mon-app
    python protected_website.py build/ mon-app --generate-code
    python protected_website.py build/ mon-app "MON-CODE" --title "Mon outil"

Dépendance : pip install cryptography
"""

import argparse
import getpass
import io
import os
import re
import secrets
import sys
import zipfile
import hashlib

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ITERATIONS = 200_000

SKIP_DIRS = {"__pycache__", ".git", ".ipynb_checkpoints", "node_modules", ".marimo"}
SKIP_FILES = {".DS_Store", "Thumbs.db"}

ROBOTS_TXT = "User-agent: *\nDisallow: /\n"

GATE_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{{TITLE}}</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    background: #f4f5f7; color: #1c1e21;
  }
  .card {
    background: #fff; border-radius: 14px; padding: 2.2rem 2.4rem;
    max-width: 420px; width: calc(100% - 2rem);
    box-shadow: 0 6px 30px rgba(0,0,0,.09);
  }
  h1 { font-size: 1.35rem; margin: 0 0 .6rem; }
  p.info { color: #556; margin: 0 0 1.4rem; line-height: 1.5; }
  input[type="password"] {
    width: 100%; padding: .75rem .9rem; font-size: 1rem;
    border: 1.5px solid #c9ccd1; border-radius: 8px; outline: none;
  }
  input[type="password"]:focus { border-color: #4a6cf7; }
  button {
    margin-top: .9rem; width: 100%; padding: .75rem; font-size: 1rem; font-weight: 600;
    color: #fff; background: #4a6cf7; border: none; border-radius: 8px; cursor: pointer;
  }
  button:disabled { opacity: .55; cursor: wait; }
  .error { color: #b3261e; margin-top: .7rem; min-height: 1.2em; font-size: .92rem; }
  #app { position: fixed; inset: 0; width: 100vw; height: 100vh; border: none; display: none; }
</style>
</head>
<body>
<main class="card" id="gate">
  <h1>{{TITLE}}</h1>
  <p class="info">{{INFO}}</p>
  <form id="form">
    <input type="password" id="code" placeholder="Code d'accès" autocomplete="off" autofocus>
    <button id="go" type="submit">Déverrouiller</button>
    <div class="error" id="err"></div>
  </form>
</main>
<iframe id="app" title="Application"></iframe>
<script src="https://cdn.jsdelivr.net/npm/fflate@0.8.2/umd/index.js"></script>
<script>
"use strict";

// Doit correspondre à ITERATIONS dans protected_website.py
const ITERATIONS = 200000;

document.getElementById("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = document.getElementById("go");
  const err = document.getElementById("err");
  const code = document.getElementById("code").value;
  err.textContent = "";
  btn.disabled = true; btn.textContent = "Déverrouillage…";
  try {
    if (typeof fflate === "undefined") throw new Error("lib manquante");

    // 1. Récupérer le contenu chiffré : [sel: 16][iv: 12][chiffré]
    const resp = await fetch("app.enc");
    if (!resp.ok) throw new Error("fetch");
    const data = new Uint8Array(await resp.arrayBuffer());
    const salt = data.slice(0, 16);
    const iv   = data.slice(16, 28);
    const ct   = data.slice(28);

    // 2. Dériver la clé depuis le code saisi
    const enc = new TextEncoder();
    const base = await crypto.subtle.importKey("raw", enc.encode(code), "PBKDF2", false, ["deriveKey"]);
    const key = await crypto.subtle.deriveKey(
      { name: "PBKDF2", salt, iterations: ITERATIONS, hash: "SHA-256" },
      base, { name: "AES-GCM", length: 256 }, false, ["decrypt"]);

    // 3. Déchiffrer — un mauvais code fait échouer decrypt()
    const zipBytes = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, ct);

    // 4. Décompresser en mémoire
    const zipFiles = fflate.unzipSync(new Uint8Array(zipBytes));

    // 5. Transférer les fichiers au service worker
    await navigator.serviceWorker.register("sw.js");
    const reg = await navigator.serviceWorker.ready;
    const filesObj = {}; const transfer = [];
    for (const [name, u8] of Object.entries(zipFiles)) {
      const buf = u8.buffer.slice(u8.byteOffset, u8.byteOffset + u8.byteLength);
      filesObj[name] = buf; transfer.push(buf);
    }
    reg.active.postMessage({ files: filesObj }, transfer);

    // 6. Afficher l'application (servie par le service worker)
    const frame = document.getElementById("app");
    frame.src = "app/";
    frame.style.display = "block";
    document.getElementById("gate").style.display = "none";
  } catch (_) {
    err.textContent = "Code invalide ou erreur de chargement.";
  } finally {
    btn.disabled = false; btn.textContent = "Déverrouiller";
  }
});
</script>
</body>
</html>
"""

SW_JS = """/* Service worker : sert les fichiers déchiffrés (en mémoire) sous le chemin virtuel app/ */
"use strict";

const files = new Map();

self.addEventListener("message", (event) => {
  const data = event.data;
  if (data && data.files) {
    files.clear();
    for (const [name, buf] of Object.entries(data.files)) {
      files.set(name, new Uint8Array(buf));
    }
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

  const data = files.get(name);
  if (!data) {
    event.respondWith(new Response("Not found", { status: 404 }));
    return;
  }
  const ext = name.includes(".") ? name.split(".").pop().toLowerCase() : "";
  event.respondWith(new Response(data, {
    headers: { "Content-Type": MIME[ext] || "application/octet-stream" },
  }));
});
"""


def zip_folder(src: str) -> bytes:
    """Compresse tout le contenu du dossier source dans un zip en mémoire."""
    buf = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for root, dirs, names in os.walk(src):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for n in sorted(names):
                if n in SKIP_FILES:
                    continue
                full = os.path.join(root, n)
                rel = os.path.relpath(full, src).replace(os.sep, "/")
                z.write(full, rel)
                count += 1
    if count == 0:
        sys.exit(f"Erreur : le dossier source « {src} » est vide.")
    return buf.getvalue()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Génère un site chiffré (AES-256-GCM) déployable sur GitHub Pages.")
    p.add_argument("source", nargs="?", help="dossier à chiffrer (ex. export marimo html-wasm)")
    p.add_argument("name", nargs="?", help="nom du site (lettres, chiffres, - et _)")
    p.add_argument("code", nargs="?", help="code d'accès (si absent : demande masquée)")
    p.add_argument("--out", default="sites", help="dossier de sortie (défaut : sites)")
    p.add_argument("--title", help="titre affiché sur la page d'entrée (défaut : nom du site)")
    p.add_argument("--info", help="texte d'information affiché (HTML autorisé)")
    p.add_argument("--generate-code", action="store_true",
                   help="génère un code aléatoire et l'affiche")
    p.add_argument("--force", action="store_true",
                   help="écraser un site existant sans demander confirmation")
    return p


def main() -> None:
    args = build_parser().parse_args()

    # Mode interactif : demander ce qui manque
    if not args.source:
        args.source = input("Chemin du dossier à chiffrer : ").strip()
    if not args.name:
        args.name = input("Nom du site : ").strip()

    if not os.path.isdir(args.source):
        sys.exit(f"Erreur : « {args.source} » n'est pas un dossier.")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.name):
        sys.exit("Erreur : le nom du site ne peut contenir que lettres, chiffres, - et _.")

    outdir = os.path.join(args.out, args.name)
    if os.path.exists(os.path.join(outdir, "app.enc")) and not args.force:
        rep = input(f"Le site « {args.name} » existe déjà. Écraser ? [o/N] ").strip().lower()
        if rep != "o":
            sys.exit("Annulé.")

    # Code d'accès
    if args.generate_code:
        code = secrets.token_urlsafe(15)
        print(f"Code d'accès généré : {code}\n")
    elif args.code:
        code = args.code
    else:
        code = getpass.getpass("Code d'accès : ")
    if len(code) < 8:
        sys.exit("Erreur : le code doit faire au moins 8 caractères.")

    # Chiffrement : [sel: 16][iv: 12][zip chiffré]
    print(f"Chiffrement de « {args.source} » …")
    zip_bytes = zip_folder(args.source)
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", code.encode("utf-8"), salt, ITERATIONS)
    iv = secrets.token_bytes(12)
    encrypted = salt + iv + AESGCM(key).encrypt(iv, zip_bytes, None)

    # Écriture du site
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "app.enc"), "wb") as f:
        f.write(encrypted)

    title = args.title or args.name
    info = args.info or ("Cette application est réservée aux personnes disposant "
                         "d'un code d'accès.<br>Pour l'obtenir, contactez l'administrateur.")
    with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
        f.write(GATE_HTML.replace("{{TITLE}}", title).replace("{{INFO}}", info))
    with open(os.path.join(outdir, "sw.js"), "w", encoding="utf-8") as f:
        f.write(SW_JS)
    with open(os.path.join(outdir, "robots.txt"), "w") as f:
        f.write(ROBOTS_TXT)

    print(f"Site généré : {outdir}/")
    print("  ├── index.html   page d'entrée")
    print(f"  ├── app.enc      contenu chiffré ({len(encrypted):,} octets)")
    print("  ├── sw.js        service worker")
    print("  └── robots.txt")
    print()
    print("Déploiement : copiez le dossier dans votre repo GitHub, puis activez")
    print("Pages (Settings → Pages → Deploy from branch → main, dossier racine).")
    print("URL du site : https://<votre-user>.github.io/<repo>/<chemin>/<nom>/")


if __name__ == "__main__":
    main()