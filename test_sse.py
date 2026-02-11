"""
Teste SSE do MCP Finance Server (Docker).
Uso: python test_sse.py
"""
import asyncio
import json
import os
from mcp import ClientSession
from mcp.client.sse import sse_client

URL = os.environ.get("MCP_URL", "http://localhost:8000/sse")

# Testa ambos os mercados sem precisar especificar exchange!
SYMBOLS = ["PETR4", "AMZN"]


def pretty(data):
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


async def call(session, tool_name, args):
    r = await session.call_tool(tool_name, args)
    return json.loads(r.content[0].text)


async def test():
    print(f"🔌 Conectando em {URL}...")

    async with sse_client(URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("✅ Conectado!\n")

            tools = await session.list_tools()
            print(f"🔧 {len(tools.tools)} tools disponíveis\n")

            for symbol in SYMBOLS:
                print(f"{'='*60}")
                print(f"📈 Testando: {symbol}")
                print(f"{'='*60}")

                # search
                print(f"\n🔍 search_symbol('{symbol}')")
                data = await call(session, "search_symbol", {"query": symbol})
                pretty(data)

                # price (sem exchange! auto-detecta)
                print(f"\n💰 get_stock_price('{symbol}')")
                data = await call(session, "get_stock_price", {"symbol": symbol})
                pretty(data)

                # fundamentals (Yahoo)
                yahoo_sym = f"{symbol}.SA" if symbol == "PETR4" else symbol
                print(f"\n📊 get_fundamentals('{yahoo_sym}')")
                data = await call(session, "get_fundamentals", {"symbol": yahoo_sym})
                pretty(data)

                print()

            print("✅ Testes finalizados!")


if __name__ == "__main__":
    try:
        asyncio.run(test())
    except ConnectionRefusedError:
        print("❌ Conexão recusada. Docker rodando?")
    except Exception as e:
        print(f"❌ Erro: {e}")
