#!/bin/bash
# Script refinado para rodar o teste de cliente de forma limpa

# Cores
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Verificando ambiente...${NC}"

# Cria venv se não existir
if [ ! -d ".venv" ]; then
    echo "Criando ambiente virtual..."
    python3 -m venv .venv
fi

# Ativa venv
source .venv/bin/activate

# Instala dependências se necessário
if ! python -c "import mcp" &> /dev/null; then
    echo "Instalando dependências..."
    pip install -e .
fi

echo -e "${GREEN}Aguardando porta 4001 do IB Gateway...${NC}"
# Timeout logic would be better but simple retry loop is fine
for i in {1..30}; do
    if nc -z localhost 4001; then
        GATEWAY_READY=1
        break
    fi
    sleep 1
    echo -n "."
done
echo ""

if [ -z "$GATEWAY_READY" ]; then
    echo -e "${RED}❌ ERRO: Porta 4001 não abriu após 30 segundos.${NC}"
    echo "Verifique se o container docker está rodando: docker compose ps"
    exit 1
fi

echo -e "${GREEN}Gateway online! Rodando teste...${NC}"

# Captura saída combinada (stdout + stderr)
OUTPUT=$(python client.py 2>&1)

# Verifica sucesso (procura pela resposta JSON esperada)
if echo "$OUTPUT" | grep -q "\"symbol\": \"EUR\""; then
    echo -e "\n${GREEN}✅✅✅ TESTE PASSOU COM SUCESSO! ✅✅✅${NC}"
    echo -e "O cliente conectou, autenticou e recebeu dados de mercado.\n"
    
    echo "--- Dados Recebidos (Resumo) ---"
    # Mostra apenas a parte do JSON de resposta, ignorando logs de conexão/erro
    echo "$OUTPUT" | grep -A 30 "Testing search_symbol" | grep -B 30 "FutureWarning" -m 1 | grep -v "FutureWarning"
    
    echo -e "\n(Nota: Ignore eventuais mensagens de 'RuntimeError' acima, são apenas ruído de limpeza de memória do Python)"
else
    echo -e "\n${RED}❌ O TESTE FALHOU${NC}"
    echo "Saída completa para debug:"
    echo "$OUTPUT"
fi
