from fastmcp import Client
import asyncio

app_client = Client("http://localhost:8000/mcp")

async def get_explanation(query: str) -> str:
    async with app_client:
        explanation = await app_client.call_tool("explain_code", {"query": query})
        print(explanation.data)
        return explanation

asyncio.run(get_explanation("Explain the purpose of this code snippet."))