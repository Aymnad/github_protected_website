##!/usr/bin/env bash
## Usage : tools/export_notebook.sh demo   → src-notebooks/demo.py  →  nb/demo/
#set -euo pipefail
#cd "$(dirname "$0")/.."
#name="${1:?nom du notebook (sans .py)}"
#rm -rf "nb/$name"
#marimo export html-wasm "src-notebooks/$name.py" -o "nb/$name" --mode run
#python tools/postprocess.py "nb/$name" --name "$name"
#echo "Export terminé : nb/$name/  (à committer)"


#!/usr/bin/env bash
set -euo pipefail

# Se placer à la racine du projet
cd "$(dirname "$0")/.."

# 1. Chemin du notebook
read -r -p "Chemin du notebook Python à exporter (.py) : " notebook

if [[ ! -f "$notebook" ]]; then
    echo "Erreur : le fichier '$notebook' n'existe pas."
    exit 1
fi

# 2. Chemin du dossier de destination
read -r -p "Chemin du dossier de destination (ex. nb) : " output_path

# 3. Nom du dossier exporté
read -r -p "Nom du dossier d'export (ex. demo) : " output_name

if [[ -z "$output_path" || -z "$output_name" ]]; then
    echo "Erreur : le chemin et le nom du dossier sont obligatoires."
    exit 1
fi

output_dir="${output_path%/}/$output_name"

# Vérifier si le dossier existe déjà
if [[ -e "$output_dir" ]]; then
    read -r -p "Le dossier '$output_dir' existe déjà. Le remplacer ? [o/N] " confirm
    if [[ ! "$confirm" =~ ^[OoYy]$ ]]; then
        echo "Export annulé."
        exit 0
    fi
    rm -rf -- "$output_dir"
fi

# Créer le dossier parent si nécessaire
mkdir -p -- "$output_path"

# 4. Export marimo
echo "Export du notebook '$notebook' vers '$output_dir'..."
    
marimo export html-wasm "$notebook" --output "$output_dir" --mode run
