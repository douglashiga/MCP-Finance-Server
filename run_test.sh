#!/bin/bash
# Script para testar o MCP Finance Server rodando no Docker

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   MCP Finance Server — Teste Rápido      ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"

# 1. Setup venv
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}Criando ambiente virtual...${NC}"
    python3 -m venv .venv
fi
source .venv/bin/activate

# 2. Instala deps se necessário
if ! python -c "import mcp" &> /dev/null; then
    echo -e "${YELLOW}Instalando dependências...${NC}"
    pip install -e . -q
fi

# 3. Espera porta 8000 (MCP SSE Server)
echo -e "\n${YELLOW}Aguardando MCP Server na porta 8000...${NC}"
for i in {1..60}; do
    if nc -z localhost 8000 2>/dev/null; then
        echo -e "${GREEN}Servidor online!${NC}"
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo -e "${RED}❌ Timeout: Porta 8000 não abriu.${NC}"
        echo "Verifique: docker compose ps"
        exit 1
    fi
    echo -n "."
    sleep 1
done

# 4. Roda o cliente de teste
echo ""
python client.py 2>&1 | grep -v "RuntimeError" | grep -v "Exception ignored" | grep -v "deallocator"
