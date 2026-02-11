import asyncio
import json
import sys
import os
from mcp import ClientSession
from mcp.client.sse import sse_client


async def run():
    """Connect to the MCP Finance Server via SSE (Docker) and run tests."""
    url = os.environ.get("MCP_URL", "http://localhost:8000/sse")

    print(f"Connecting to MCP Finance Server at {url}...")

    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # ---- List capabilities ----
            print("\n--- Available Tools ---")
            tools = await session.list_tools()
            for tool in tools.tools:
                print(f"  🔧 {tool.name}")

            print(f"\n  Total: {len(tools.tools)} tools")

            print("\n--- Available Resources ---")
            resources = await session.list_resources()
            for resource in resources.resources:
                print(f"  📄 {resource.name}: {resource.uri}")

            print("\n--- Available Prompts ---")
            prompts = await session.list_prompts()
            for prompt in prompts.prompts:
                print(f"  💬 {prompt.name}")

            # ---- Run test calls ----
            results = {}

            # Test 1: Search symbol
            print("\n--- Test 1: search_symbol('EUR') ---")
            try:
                result = await session.call_tool("search_symbol", arguments={"query": "EUR"})
                data = json.loads(result.content[0].text)
                results["search_symbol"] = data.get("success", False)
                print(f"  ✅ Found {len(data.get('data', []))} results")
            except Exception as e:
                results["search_symbol"] = False
                print(f"  ❌ Error: {e}")

            # Test 2: Yahoo fundamentals (no IB needed)
            print("\n--- Test 2: get_fundamentals('AAPL') ---")
            try:
                result = await session.call_tool("get_fundamentals", arguments={"symbol": "AAPL"})
                data = json.loads(result.content[0].text)
                results["get_fundamentals"] = data.get("success", False)
                pe = data.get("data", {}).get("trailingPE", "N/A")
                print(f"  ✅ AAPL PE Ratio: {pe}")
            except Exception as e:
                results["get_fundamentals"] = False
                print(f"  ❌ Error: {e}")

            # Test 3: Company info
            print("\n--- Test 3: get_company_info('AAPL') ---")
            try:
                result = await session.call_tool("get_company_info", arguments={"symbol": "AAPL"})
                data = json.loads(result.content[0].text)
                results["get_company_info"] = data.get("success", False)
                sector = data.get("data", {}).get("sector", "N/A")
                print(f"  ✅ Sector: {sector}")
            except Exception as e:
                results["get_company_info"] = False
                print(f"  ❌ Error: {e}")

            # ---- Summary ----
            passed = sum(1 for v in results.values() if v)
            total = len(results)

            print("\n" + "=" * 50)
            if passed == total:
                print(f"  ✅ RESULTADO: {passed}/{total} testes passaram!")
            else:
                print(f"  ⚠️  RESULTADO: {passed}/{total} testes passaram")
                for name, ok in results.items():
                    status = "✅" if ok else "❌"
                    print(f"    {status} {name}")
            print("=" * 50)


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nClient stopped.")
    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
        print(f"Verify Docker is running: docker compose ps")
