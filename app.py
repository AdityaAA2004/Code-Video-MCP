from fastmcp import FastMCP

mcp_app = FastMCP("Code Explanation Video MCP server",
                  version="1.0.0")

@mcp_app.tool
def explain_code(query: str) -> str:
    explanation = f"This is the explanation: {query}"
    return explanation

if __name__ == "__main__":
    mcp_app.run(transport="http", show_banner=True, host="127.0.0.1", port=8000)

