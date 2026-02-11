#!/bin/bash
# Script para rodar o teste de cliente de forma fluida

# Cores
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo -e "${GREEN}Verificando ambiente...${NC}"

# Cria venv se não existir
if [ ! -d ".venv" ]; then
    echo "Criando ambiente virtual..."
    python3 -m venv .venv
fi

# Ativa venv
source .venv/bin/activate

# Instala dependências se necessário (verifica se mcp está instalado)
if ! python -c "import mcp" &> /dev/null; then
    echo "Instalando dependências..."
    pip install -e .
fi

echo -e "${GREEN}Iniciando teste do cliente...${NC}"
echo "Conectando ao IB Gateway (Docker)..."

# Executa o cliente
python client.py
