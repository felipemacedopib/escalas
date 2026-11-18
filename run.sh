#!/usr/bin/env bash
# Inicia o sistema de escalas. Primeira vez: cria o ambiente e instala as dependências.
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
export ESCALAS_ADMIN_PASSWORD="${ESCALAS_ADMIN_PASSWORD:-louvor123}"
echo "Painel do responsável: http://localhost:${PORT:-5000}/admin   (senha: $ESCALAS_ADMIN_PASSWORD)"
exec python app.py
