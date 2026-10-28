# To DO!

- there are two .py files and I do not know why. 
- I should add a podman or a conda environement that performs the webassembly export here instead of in the other repository. So I need a folder with the exported sites, and another one with the crypted ones
   - hence, I should also add in the gitignore the different project becuase I cannot push everything it is too heavy
- I added /tools scripts from the website Page, they are supposed to change the favicon etc so that everyting is done here but need to test it
- there is a /vendor folder and I do not know what it does now
- I this is is written "dévérouiller" in french on the webpage
- je crois que le code make\_icons ne devrais pas rester là. je en l'ai pas bien vu marcher pour le site marimo mais en tout cas il semble marcher pour le site tout cours

ok it seems that the real file is générateur\_etc.py not the other one



For an interactive website that works online:
marimo export html-wasm notebook.py -o dist --mode run


For a more self-contained export, bundling the browser runtime and compatible Python packages so the site can run without internet access to those resources:
python -m playwright install chromium
marimo export html-wasm notebook.py -o dist --mode run --offline


The offline option still requires internet access during export to retrieve the necessary runtime and packages. Your exported directory includes the assets needed by the site.




### Comment utiliser le script pour l'export
Comment l'utiliser
Enregistre le script, par exemple sous tools/export_notebook.sh, puis rends-le exécutable :
chmod +x tools/export_notebook.sh


Lance-le depuis ton terminal :
./tools/export_notebook.sh

-

# github_protected_website
Makes crypted github pages website

# protected_website — sites chiffrés pour GitHub Pages

Génère autant de sites protégés par code que nécessaire, à partir d'autant de
dossiers sources (ex. exports marimo `html-wasm`). Chaque site est un dossier
indépendant, prêt à copier dans un repo GitHub.

## Principe

1. Le dossier source est **compressé (zip) puis chiffré** en AES-256-GCM.
   La clé est dérivée du code d'accès via PBKDF2-SHA256 (200 000 itérations).
2. En ligne, seul `app.enc` (binaire illisible) existe — le contenu n'est
   **jamais** publié en clair, ni en hash contournable.
3. Dans le navigateur : la page d'entrée déchiffre avec le code saisi,
   décompresse, et un service worker sert les fichiers en mémoire.
   Un mauvais code fait échouer le déchiffrement (AES-GCM) : rien ne s'affiche.

## Structure du projet

```
protected_website/
├── protected_website.py    # le générateur (ce fichier)
├── README.md
└── sites/                  # créé automatiquement — c'est ce qui est publié
    ├── app-alpha/
    │   ├── index.html      # page d'entrée (titre, infos, demande du code)
    │   ├── app.enc         # contenu chiffré
    │   ├── sw.js           # service worker
    │   └── robots.txt
    └── app-beta/
        └── … (même structure)
```

## Environement

Puis :
bash
Copier

conda env create -f environment.yml
conda activate protected_website




Ensuite, workflow complet dans cet environnement :
bash

python protected_website.py build/ app-alpha --generate-code




## Utilisation

```bash
pip install cryptography

# Mode interactif (demande chemin, nom, code masqué) :
python protected_website.py

# Ou en ligne de commande :
python protected_website.py build/ app-alpha "MON-CODE"

# Générer un code aléatoire (recommandé, 16+ caractères) :
python protected_website.py build/ app-alpha --generate-code

# Personnaliser la page d'entrée :
python protected_website.py build/ app-alpha "MON-CODE" \
    --title "Outil interne" \
    --info "Réservé à l'équipe. Contactez Aymeric pour le code."
```

## Déployer sur GitHub Pages

1. Créez un repo GitHub (public pour Pages gratuit).
2. Copiez chaque dossier `sites/<nom>/` dans le repo, par exemple tel quel :
   ```
   mon-repo/
   ├── app-alpha/
   └── app-beta/
   ```
3. Settings → Pages → Deploy from a branch → `main`, dossier racine.
4. URLs obtenues :
   - `https://<user>.github.io/mon-repo/app-alpha/`
   - `https://user.github.io/mon-repo/app-beta/`

Chaque site fonctionne indépendamment avec son propre code.

## Organiser les codes

- Gardez les codes **hors du repo** (le repo est public !) : gestionnaire de
  mots de passe, ou un fichier local `codes.md` jamais commité (ajoutez-le
  au `.gitignore` si vous le mettez dans le repo en local).
- Un code par site. Pour changer un code : relancer le script (nouveau sel +
  IV générés), puis copier les 4 fichiers régénérés dans le repo.

## Sécurité et limites

- ✅ Le contenu est **réellement chiffré** au repos : lire le code source de
  la page, télécharger `app.enc` ou deviner des URLs ne donne rien sans le code.
- ⚠️ Une fois déverrouillé, l'utilisateur légitime voit le contenu (c'est le
  but) : ne partagez les codes qu'avec des personnes de confiance.
- ⚠️ Toujours entrer par la page d'entrée (`…/<nom>/`). Si l'app affiche 404
  après un long temps d'inactivité (le service worker a redémarré), rouvrez
  la page d'entrée et ressaisissez le code.
- ℹ️ Chargements en flux (vidéo) non supportés ; les fichiers sont servis
  en mémoire.
- ℹ️ La page d'entrée charge la petite librairie `fflate` depuis un CDN —
  internet requis, comme pour l'app marimo elle-même (Pyodide vient aussi
  d'un CDN).
- ℹ️ Le sel et le nombre d'itérations ne sont pas des secrets ; seul le code
  l'est.
