import asyncio
import sys
import shutil
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def run():
    # Detect python executable (use the one in venv if possible, or current)
    python_exe = sys.executable
    server_script = "server.py"
    
    # Create server parameters
    server_params = StdioServerParameters(
        command=python_exe,
        args=[server_script],
        env=None # Inherit env
    )

    print(f"Starting MCP Client connecting to {server_script}...")
    
    # Simple list resources and prompts check
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize
            await session.initialize()
            
            # List tools
            print("\n--- Available Tools ---")
            tools = await session.list_tools()
            for tool in tools.tools:
                print(f"- {tool.name}: {tool.description}")

            # List Resources
            print("\n--- Available Resources ---")
            resources = await session.list_resources()
            for resource in resources.resources:
                print(f"- {resource.name}: {resource.uri}")

            # List Prompts
            print("\n--- Available Prompts ---")
            prompts = await session.list_prompts()
            for prompt in prompts.prompts:
                print(f"- {prompt.name}: {prompt.description}")
            
            # Call tools (simplified for test)
            print("\n--- Testing search_symbol('EUR') ---")
            try:
                result = await session.call_tool("search_symbol", arguments={"query": "EUR"})
                print(result.content[0].text)
            except Exception as e:
                print(f"Error calling search_symbol: {e}")




if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("Client stopped.")
    except Exception as e:
        print(f"An error occurred: {e}")
