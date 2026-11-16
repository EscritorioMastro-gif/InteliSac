#!/usr/bin/env bash
# Build do serviço "intelisac" no Render: dependências da API + tela React montada.
set -euo pipefail

echo "==> API: dependências do Python"
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt

echo "==> Tela: montando o React (frontend/dist)"
if ! command -v npm >/dev/null 2>&1; then
  echo "ERRO: npm não existe neste ambiente do Render (a tela precisa do Node para montar)." >&2
  exit 1
fi
cd frontend
npm ci --include=dev
npm run build
test -f dist/index.html
echo "==> pronto"
