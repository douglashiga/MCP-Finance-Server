# 🐳 Como Rodar o MCP Finance no Docker

## Pré-requisitos

1. **Docker e Docker Compose** instalados
2. **Arquivo `.env`** com credenciais do IB (se for usar IB Gateway)

---

## 🚀 Quick Start

### 1. Criar arquivo `.env` (opcional, só se usar IB Gateway)

```bash
# Na raiz do projeto
cat > .env << 'EOF'
TWS_USERID=seu_usuario_ib
TWS_PASSWORD=sua_senha_ib
TRADING_MODE=paper
IB_GATEWAY_PORT=4004
IB_ENABLED=true
EOF
```

### 2. Build e Start

```bash
# Build das imagens
docker compose build

# Subir todos os serviços
docker compose up -d

# Ver logs
docker compose logs -f
```

Importante:
- `docker compose build` **apenas constrói** as imagens.
- Para abrir a UI, você precisa rodar `docker compose up -d`.
- Se aparecer `Cannot connect to the Docker daemon`, inicie o Docker Desktop primeiro.

### 3. Acessar os serviços

- **Data Loader UI**: http://localhost:8001
- **MCP Server**: http://localhost:8000
- **IB Gateway VNC** (debug): vnc://localhost:5901 (senha: `password`)

Para subir só a parte web (sem MCP/IB):

```bash
docker compose up -d postgres dataloader
```

---

## 📦 Serviços

### 1. **ib-gateway** (Porta 4001)
- Interactive Brokers Gateway (headless)
- Requer credenciais no `.env`
- Healthcheck automático
- Internamente usa `IB_GATEWAY_PORT` (paper=`4004`, live=`4003`)

### 2. **mcp-finance** (Porta 8000)
- MCP Server principal
- Conecta ao IB Gateway
- Consulta banco de dados PostgreSQL

### 3. **dataloader** (Porta 8001)
- Scheduler + API + UI
- Roda jobs ELT em background
- Interface web para gerenciar jobs

---

## 🛠️ Comandos Úteis

```bash
# Parar tudo
docker compose down

# Parar e remover volumes (limpa banco)
docker compose down -v

# Rebuild após mudanças no código
docker compose build --no-cache

# Ver logs de um serviço específico
docker compose logs -f dataloader

# Executar comando dentro do container
docker compose exec dataloader python -m dataloader.seed

# Restart de um serviço
docker compose restart mcp-finance
```

---

## 🔧 Configuração Avançada

### Rodar sem IB Gateway (Yahoo-only)

Use `IB_ENABLED=false` para manter o MCP ativo sem tentar conectar no IB:

```bash
IB_ENABLED=false docker compose up -d mcp-finance postgres dataloader
```

---

## 📊 Inicializar Banco

```bash
# Entrar no container
docker compose exec dataloader bash

# Rodar seed
python -m dataloader.seed

# Sair
exit
```

---

## 🐛 Troubleshooting

### IB Gateway não conecta
```bash
# Ver logs
docker compose logs ib-gateway

# Acessar VNC para debug visual
# Abrir VNC Viewer em: vnc://localhost:5901
# Senha: password
```

### Data Loader não inicia
```bash
# Ver logs
docker compose logs dataloader

# Verificar se porta 8001 está livre
lsof -i :8001
```

### Rebuild completo
```bash
docker compose down -v
docker compose build --no-cache
docker compose up -d
```

---

## 📝 Notas

- O banco principal em Docker é PostgreSQL (volume `postgres-data`)
- Logs ficam em `./logs/` (mapeado do host)
- Para produção, use volumes persistentes e não rode com `DATALOADER_ALLOW_INSECURE=true`
