import asyncio
from mcp_agent.core.fastagent import FastAgent

# Create the application
fast = FastAgent("fast-agent example")


# Define the agent
@fast.agent(instruction="You are a helpful AI Agent")

@fast.agent(
    "url_fetcher",
    "Given a URL, list the first 10 urls in the page, and then fetch the content of the first 3 urls. return the content of those urls in full.",
    servers=["fetch"], # Name of an MCP Server defined in fastagent.config.yaml
)
async def main():
    # use the --model command line switch or agent arguments to change model
    async with fast.run() as agent:
        await agent.interactive()


if __name__ == "__main__":
    asyncio.run(main())
