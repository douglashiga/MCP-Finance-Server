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

# IB usa "PETR4" + exchange "BOVESPA"
# Yahoo usa "PETR4.SA"
IB_SYMBOL = "PETR4"
YAHOO_SYMBOL = "PETR4.SA"


def pretty(data):
    """Print JSON formatado."""
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


async def call(session, tool_name, args):
    """Chama um tool e retorna o JSON."""
    r = await session.call_tool(tool_name, args)
    return json.loads(r.content[0].text)


async def test():
    print(f"🔌 Conectando em {URL}...")

    async with sse_client(URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("✅ Conectado!\n")

            # 1. Listar tools
            tools = await session.list_tools()
            print(f"🔧 {len(tools.tools)} tools disponíveis:")
            for t in tools.tools:
                print(f"   - {t.name}")

            # ========== IB Tools (usa PETR4 + BOVESPA) ==========

            # 2. search_symbol
            print(f"\n{'='*60}")
            print(f"🔍 search_symbol('{IB_SYMBOL}')  [IB]")
            print(f"{'='*60}")
            data = await call(session, "search_symbol", {"query": IB_SYMBOL})
            pretty(data)

            # 3. get_stock_price
            print(f"\n{'='*60}")
            print(f"💰 get_stock_price('{IB_SYMBOL}', exchange='BOVESPA', currency='BRL')  [IB]")
            print(f"{'='*60}")
            data = await call(session, "get_stock_price", {
                "symbol": IB_SYMBOL,
                "exchange": "BOVESPA",
                "currency": "BRL"
            })
            pretty(data)

            # ========== Yahoo Tools (usa PETR4.SA) ==========

            # 4. get_fundamentals
            print(f"\n{'='*60}")
            print(f"📊 get_fundamentals('{YAHOO_SYMBOL}')  [Yahoo]")
            print(f"{'='*60}")
            data = await call(session, "get_fundamentals", {"symbol": YAHOO_SYMBOL})
            pretty(data)

            # 5. get_company_info
            print(f"\n{'='*60}")
            print(f"🏢 get_company_info('{YAHOO_SYMBOL}')  [Yahoo]")
            print(f"{'='*60}")
            data = await call(session, "get_company_info", {"symbol": YAHOO_SYMBOL})
            pretty(data)

            # 6. get_dividends
            print(f"\n{'='*60}")
            print(f"💵 get_dividends('{YAHOO_SYMBOL}')  [Yahoo]")
            print(f"{'='*60}")
            data = await call(session, "get_dividends", {"symbol": YAHOO_SYMBOL})
            pretty(data)

            print(f"\n✅ Todos os testes finalizados!")
            print(f"   IB:    {IB_SYMBOL} (exchange BOVESPA)")
            print(f"   Yahoo: {YAHOO_SYMBOL}")


if __name__ == "__main__":
    try:
        asyncio.run(test())
    except ConnectionRefusedError:
        print("❌ Conexão recusada. O Docker está rodando?")
        print("   docker compose up -d --build")
    except Exception as e:
        print(f"❌ Erro: {e}")
