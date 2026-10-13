#!/usr/bin/env python3
# Génère un site statique chiffré pour GitHub Pages.
# GitHub Pages reste public : app.enc est téléchargeable par tous.
from __future__ import annotations
import argparse, getpass, hashlib, html, io, os, re, secrets, shutil, sys, zipfile
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ITERATIONS = 600_000
SALT_LEN = 16
IV_LEN = 12
MIN_CODE_LENGTH = 16
SKIP_DIRS = {"__pycache__", ".git", ".ipynb_checkpoints", "node_modules", ".marimo", ".venv", "venv", ".idea", ".vscode"}
SKIP_FILES = {".DS_Store", "Thumbs.db"}
FFLATE_VERSION = "0.8.2"  # chargé depuis jsDelivr, aucune copie locale nécessaire

GATE_HTML = r'''<!doctype html>
<html lang="fr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-src 'self' blob:">
<title>__TITLE__</title>
<style>
:root{color-scheme:light dark}*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:1rem;font-family:system-ui,sans-serif;background:#f4f5f7;color:#1c1e21}.card{background:#fff;color:#1c1e21;border-radius:14px;padding:2rem;max-width:440px;width:100%;box-shadow:0 6px 30px #0002}h1{font-size:1.35rem;margin:0 0 .6rem;overflow-wrap:anywhere}p{color:#556;line-height:1.5}input,button{width:100%;padding:.8rem;font:inherit;border-radius:8px}input{border:1px solid #bbb}button{margin-top:.8rem;border:0;color:white;background:#315efb;cursor:pointer}button:disabled{opacity:.6;cursor:wait}#error{min-height:1.4em;color:#b3261e;font-size:.92rem}#app{position:fixed;inset:0;width:100%;height:100%;border:0;display:none;background:white}
</style></head><body>
<main class="card" id="gate"><h1>__TITLE__</h1><p>__INFO__</p>
<form id="form"><label for="code">Code d'accès</label><input id="code" type="password" autocomplete="current-password" required>
<button id="go" type="submit">Déverrouiller</button><p id="error" role="status" aria-live="polite"></p></form></main>
<iframe id="app" title="Application" sandbox="allow-scripts allow-same-origin allow-forms allow-downloads allow-modals"></iframe>
<script src="https://cdn.jsdelivr.net/npm/fflate@0.8.2/umd/index.js"></script><script src="./gate.js"></script></body></html>'''

GATE_JS = r'''"use strict";
const ITERATIONS=__ITERATIONS__;
const CACHE_NAME="protected-site-__SITE_ID__";
const enc=new TextEncoder();
async function deriveKey(code,salt){const material=await crypto.subtle.importKey("raw",enc.encode(code),"PBKDF2",false,["deriveKey"]);return crypto.subtle.deriveKey({name:"PBKDF2",salt,iterations:ITERATIONS,hash:"SHA-256"},material,{name:"AES-GCM",length:256},false,["decrypt"])}
function safePath(path){return typeof path==="string"&&!!path&&!path.includes("\\")&&!path.startsWith("/")&&!/^[A-Za-z]:/.test(path)&&path.split("/").every(p=>p!==".."&&p!==".")}
function mimeFor(name){const ext=name.split(".").pop().toLowerCase();return ({html:"text/html; charset=utf-8",htm:"text/html; charset=utf-8",js:"text/javascript; charset=utf-8",mjs:"text/javascript; charset=utf-8",css:"text/css; charset=utf-8",json:"application/json",svg:"image/svg+xml",png:"image/png",jpg:"image/jpeg",jpeg:"image/jpeg",gif:"image/gif",webp:"image/webp",ico:"image/x-icon",woff:"font/woff",woff2:"font/woff2",ttf:"font/ttf",otf:"font/otf",wasm:"application/wasm",txt:"text/plain; charset=utf-8",csv:"text/csv",mp3:"audio/mpeg",mp4:"video/mp4",pdf:"application/pdf",webm:"video/webm",avif:"image/avif"})[ext]||"application/octet-stream"}
async function installFiles(files){if(!( "serviceWorker" in navigator)||!("caches" in window))throw Error("Service worker non pris en charge");const reg=await navigator.serviceWorker.register(new URL("./sw.js",location.href),{scope:"./"});await navigator.serviceWorker.ready;const worker=reg.active||reg.waiting||reg.installing;if(!worker)throw Error("Service worker indisponible");await new Promise((resolve,reject)=>{const ch=new MessageChannel();const timer=setTimeout(()=>{ch.port1.close();reject(Error("Délai dépassé"))},30000);ch.port1.onmessage=e=>{clearTimeout(timer);ch.port1.close();e.data&&e.data.ok?resolve():reject(Error("Installation impossible"))};worker.postMessage({type:"INSTALL_FILES",files},[ch.port2])})}
document.getElementById("form").addEventListener("submit",async e=>{e.preventDefault();const btn=document.getElementById("go"),err=document.getElementById("error"),input=document.getElementById("code");btn.disabled=true;btn.textContent="Déverrouillage…";err.textContent="";try{if(!window.fflate||typeof fflate.unzipSync!=="function")throw Error("fflate absent");const resp=await fetch("./app.enc",{cache:"no-store"});if(!resp.ok)throw Error("app.enc introuvable");const bytes=new Uint8Array(await resp.arrayBuffer());if(bytes.length<=28)throw Error("Fichier invalide");const salt=bytes.slice(0,16),iv=bytes.slice(16,28),ct=bytes.slice(28),key=await deriveKey(input.value,salt);const plain=new Uint8Array(await crypto.subtle.decrypt({name:"AES-GCM",iv},key,ct));const entries=fflate.unzipSync(plain),files={};let total=0;for(const [name,data] of Object.entries(entries)){if(!safePath(name))throw Error("Chemin invalide");total+=data.byteLength;if(total>250*1024*1024)throw Error("Archive trop volumineuse");files[name]=Array.from(data)}if(!Object.prototype.hasOwnProperty.call(files,"index.html"))throw Error("index.html absent");await installFiles(files);const frame=document.getElementById("app");frame.src=new URL("./app/index.html",location.href).href;frame.style.display="block";document.getElementById("gate").style.display="none";input.value=""}catch(ex){console.error(ex);err.textContent="Code incorrect ou erreur de chargement. Vérifie le code et réessaie."}finally{btn.disabled=false;btn.textContent="Déverrouiller"}});'''

SW_JS = r'''"use strict";
const CACHE_NAME="protected-site-__SITE_ID__";
const APP_PREFIX=new URL("app/",self.registration.scope).pathname;
function mimeFor(name){const ext=name.split(".").pop().toLowerCase();return ({html:"text/html; charset=utf-8",htm:"text/html; charset=utf-8",js:"text/javascript; charset=utf-8",mjs:"text/javascript; charset=utf-8",css:"text/css; charset=utf-8",json:"application/json",svg:"image/svg+xml",png:"image/png",jpg:"image/jpeg",jpeg:"image/jpeg",gif:"image/gif",webp:"image/webp",ico:"image/x-icon",woff:"font/woff",woff2:"font/woff2",ttf:"font/ttf",otf:"font/otf",wasm:"application/wasm",txt:"text/plain; charset=utf-8",csv:"text/csv",mp3:"audio/mpeg",mp4:"video/mp4",pdf:"application/pdf",webm:"video/webm",avif:"image/avif"})[ext]||"application/octet-stream"}
self.addEventListener("install",e=>self.skipWaiting());self.addEventListener("activate",e=>e.waitUntil(self.clients.claim()));
self.addEventListener("message",event=>{if(!event.data||event.data.type!=="INSTALL_FILES"||!event.ports[0])return;const port=event.ports[0];event.waitUntil((async()=>{try{const entries=event.data.files;if(!entries||typeof entries!=="object")throw Error();const cache=await caches.open(CACHE_NAME);await Promise.all((await cache.keys()).map(k=>cache.delete(k)));for(const [name,bytes] of Object.entries(entries)){if(!Array.isArray(bytes)||name.startsWith("/")||name.includes("\\")||name.split("/").some(p=>p===".."||p==="."))throw Error();const url=new URL("app/"+name.split("/").map(encodeURIComponent).join("/"),self.registration.scope);await cache.put(url,new Response(new Uint8Array(bytes),{headers:{"Content-Type":mimeFor(name),"X-Content-Type-Options":"nosniff"}}))}port.postMessage({ok:true})}catch(err){port.postMessage({ok:false})}finally{port.close()}})())});
self.addEventListener("fetch",event=>{const url=new URL(event.request.url);if(url.origin!==self.location.origin||!url.pathname.startsWith(APP_PREFIX))return;event.respondWith((async()=>{const cache=await caches.open(CACHE_NAME);return await cache.match(event.request)||new Response("Not found",{status:404})})())});'''
ROBOTS_TXT = "User-agent: *\nDisallow: /\n"

def zip_folder(source: Path) -> bytes:
    buf=io.BytesIO(); count=0; source=source.resolve()
    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for root,dirs,names in os.walk(source,followlinks=False):
            rootp=Path(root); dirs[:]=sorted(d for d in dirs if d not in SKIP_DIRS and not (rootp/d).is_symlink())
            for filename in sorted(names):
                path=rootp/filename
                if filename in SKIP_FILES or path.is_symlink() or not path.is_file(): continue
                z.write(path,path.relative_to(source).as_posix()); count+=1
    if not count: raise ValueError(f"Le dossier source « {source} » est vide.")
    return buf.getvalue()

def build_parser():
    p=argparse.ArgumentParser(description="Chiffre un site statique pour GitHub Pages.")
    p.add_argument("source",nargs="?",help="Dossier du site à chiffrer")
    p.add_argument("name",nargs="?",help="Nom du site (lettres, chiffres, - et _)")
    p.add_argument("code",nargs="?",help=argparse.SUPPRESS)
    p.add_argument("--out",default="sites",help="Dossier de sortie (défaut : sites)")
    p.add_argument("--title",help="Titre affiché sur la page de code")
    p.add_argument("--info",default="Cette application est réservée aux personnes disposant d’un code d’accès.",help="Texte affiché sous le titre (texte brut)")
    p.add_argument("--generate-code",action="store_true",help="Génère un code aléatoire robuste")
    p.add_argument("--force",action="store_true",help="Remplace le site existant sans confirmation")
    return p

def main():
    args=build_parser().parse_args(); source=Path(args.source or input("Chemin du dossier du site à chiffrer : ")).expanduser(); name=args.name or input("Nom du site : ").strip()
    if not source.is_dir(): sys.exit(f"Erreur : « {source} » n'est pas un dossier.")
    if not re.fullmatch(r"[A-Za-z0-9_-]+",name): sys.exit("Nom invalide : utilisez lettres, chiffres, - et _.")
    outdir=Path(args.out).expanduser()/name
    if outdir.exists() and not args.force and input(f"Le dossier « {outdir} » existe. Remplacer ? [o/N] ").strip().lower()!="o": sys.exit("Annulé.")
    if outdir.exists(): shutil.rmtree(outdir)
    if args.generate_code:
        code=secrets.token_urlsafe(24); print(f"\nCode d’accès (à conserver dans votre gestionnaire) :\n{code}\n")
    elif args.code:
        code=args.code; print("Attention : le code passé en argument peut apparaître dans l’historique ou la liste des processus.")
    else: code=getpass.getpass("Code d’accès (saisie masquée) : ")
    if len(code)<MIN_CODE_LENGTH: sys.exit(f"Le code doit contenir au moins {MIN_CODE_LENGTH} caractères.")
    plain=zip_folder(source); salt=secrets.token_bytes(SALT_LEN); nonce=secrets.token_bytes(IV_LEN)
    key=hashlib.pbkdf2_hmac("sha256",code.encode("utf-8"),salt,ITERATIONS,dklen=32)
    ciphertext=AESGCM(key).encrypt(nonce,plain,None)
    outdir.mkdir(parents=True,exist_ok=True); (outdir/"app.enc").write_bytes(salt+nonce+ciphertext)
    (outdir/"gate.js").write_text(GATE_JS.replace("__ITERATIONS__",str(ITERATIONS)).replace("__SITE_ID__",name),encoding="utf-8")
    (outdir/"sw.js").write_text(SW_JS.replace("__SITE_ID__",name),encoding="utf-8")
    (outdir/"robots.txt").write_text(ROBOTS_TXT,encoding="utf-8")
    title=html.escape(args.title or name,quote=True); info=html.escape(args.info,quote=True)
    (outdir/"index.html").write_text(GATE_HTML.replace("__TITLE__",title).replace("__INFO__",info),encoding="utf-8")
    print(f"\nSite généré : {outdir}/\nContenu : index.html, gate.js, app.enc, sw.js, robots.txt")
    print("Publiez le contenu de ce dossier sur GitHub Pages. Testez d’abord sur un dépôt de test.")
    print("Note : les fichiers déchiffrés sont conservés dans Cache Storage du navigateur.")

if __name__=="__main__": main()


