*Give your agent real knowledge — official docs, source code, and your first lines of Python*

In [Part 1](foundry-agent-part-1.ipynb), you built **foundry-expert** — an agent with Web Search that answers questions about Microsoft Foundry. It works, but it's pulling answers from the open web. That's fine for news, but when someone asks "What RBAC roles do I need?" you want the answer from the actual docs, not a blog post from six months ago.

In this part, you'll connect your agent to two MCP servers — Microsoft Learn and GitHub — so it can read official documentation and SDK source code directly. Then you'll see the same agent defined three ways: portal UI, YAML, and Python.

**What you'll do in Part 2:**
- Browse the Foundry tool catalog and understand the three types of tools
- Add the Microsoft Learn MCP server (public, no auth required)
- Add the GitHub MCP server (requires a project connection with a PAT)
- Handle MCP approval requests — a new concept you'll hit immediately
- Discover the YAML and Code views in the agent builder
- Launch VS Code for the web and make a code change

## The Tool Catalog

Your agent can do a lot more than search the web. From the left sidebar, go to **Build → Tools** to open **Foundry Tools**. This is the central place to browse, configure, and manage every tool available to your agents.

The catalog has three types of entries:

| Type | What it is | Examples |
|------|-----------|----------|
| **Remote MCP server** | Publisher-hosted — you just provide the endpoint and (optionally) auth | Microsoft Learn, GitHub, Azure DevOps |
| **Local MCP server** | You host the server yourself, then connect it by URL | Your own custom MCP server |
| **Custom** | Logic Apps connectors converted to MCP servers | Requires additional configuration |

You can filter by publisher, category, authentication method, and registry (public vs. Logic Apps connectors). When you select a tool, the catalog shows the setup details — endpoint URL, auth requirements, and which tools the server exposes.

Most of the tools use **MCP (Model Context Protocol)** — an open standard that works like a universal connector for AI tools. Instead of writing custom integration code for every API, you point your agent at an MCP server URL and it discovers the available tools automatically. Think of it as USB-C for AI: one interface, any data source.

<!-- TODO: Screenshot of Build → Tools page showing the catalog with filters -->

Let's add two tools from the catalog: Microsoft Learn and GitHub.

## Add the Microsoft Learn MCP Server

Right now your agent searches the open web for answers. That works, but wouldn't it be better if it could go straight to the official Microsoft documentation?

The Microsoft Learn MCP server gives your agent direct access to docs.microsoft.com content — API references, tutorials, conceptual guides, all of it. And it's public, so there's no authentication to set up.

Here's how to add it:

1. Open your **foundry-expert** agent in the portal
2. Scroll down to **Tools** and click **Add**
3. Switch to the **Catalog** tab and search for **"Microsoft Learn"**
4. The server URL is pre-filled: `https://learn.microsoft.com/api/mcp`
5. Click **Add** to connect it

<!-- TODO: Screenshot of the Microsoft Learn MCP server card in the catalog -->

Once it's connected, try it out in the chat playground:

> *"What RBAC roles do I need for Foundry Agent Service?"*

Notice the difference from Part 1? Instead of summarizing random web results, your agent now pulls directly from official Microsoft Learn pages. The answers are more precise because they come from the authoritative source.

<!-- TODO: Screenshot of agent response citing Microsoft Learn docs -->

## Add the GitHub MCP Server

Documentation tells you how things *should* work. Source code tells you how they *actually* work. Let's give your agent access to both.

The GitHub MCP server lets your agent read repositories, search code, and understand SDK implementations directly from GitHub. Unlike Microsoft Learn, this one requires authentication.

1. Back in **Tools**, click **Add** and search for **"GitHub"** in the catalog
2. The server URL is `https://api.githubcopilot.com/mcp/`
3. You'll need to create a **project connection** for authentication:
   - Go to GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
   - Create a token with `repo` read access for the repositories you want your agent to explore
   - Back in the Foundry portal, go to your project's **Management → Connected resources** and add a new connection with your PAT
   - Link that connection to the GitHub MCP server using the `project_connection_id` field
4. Save the tool configuration

<!-- TODO: Screenshot of GitHub MCP server configuration with auth -->

> **🛠️ Pro-code alternative:** You can configure MCP tools entirely in Python:
>
> ```python
> from azure.ai.projects.models import MCPTool
>
> github_tool = MCPTool(
>     server_label="github",
>     server_url="https://api.githubcopilot.com/mcp/",
>     require_approval="always",
>     project_connection_id="my-github-connection",
> )
> ```

Once connected, try asking:

> *"What's the latest version of the azure-ai-projects Python SDK?"*

Your agent searches the GitHub repository and returns version information straight from the source.

<!-- TODO: Screenshot of agent response using GitHub tool -->

## MCP Approval Requests

Here's something you'll run into immediately: MCP tools default to `require_approval="always"`. That means every time your agent tries to call an MCP tool, the response comes back with an `mcp_approval_request` instead of the answer. You have to explicitly approve it before the agent can proceed.

In the **portal playground**, this shows up as a prompt asking you to approve the tool call — just click approve and the agent continues. Easy.

In **code**, you need to handle the approval loop yourself. The response contains output items with `type == "mcp_approval_request"`, and you send back an `McpApprovalResponse` with `approve=True`. Here's the pattern:

```python
from openai.types.responses.response_input_param import McpApprovalResponse

response = openai_client.responses.create(
    conversation=conversation.id,
    input="What RBAC roles do I need for Foundry Agent Service?",
    extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}},
)

# Check for MCP approval requests
input_list = []
for item in response.output:
    if item.type == "mcp_approval_request":
        input_list.append(
            McpApprovalResponse(type="mcp_approval_response", approve=True, approval_request_id=item.id)
        )

# If there were approval requests, send them back and get the real answer
if input_list:
    response = openai_client.responses.create(
        conversation=conversation.id,
        input=input_list,
        extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}},
    )

print(response.output_text)
```

If you don't want the approval step (for trusted servers), set `require_approval="never"` when you create the tool. For this tutorial, we'll keep approval on — it's good practice to know what your agent is doing before you let it run unsupervised.

## Test the Enhanced Agent

Your agent now has three knowledge sources working together:
- **Web Search** — current news, blog posts, community discussions
- **Microsoft Learn** — official documentation, API references, tutorials
- **GitHub** — source code, SDK implementations, version history

The real power shows up when you ask questions that need multiple sources. Try this:

> *"Compare what the official docs say about agent versioning with what's actually in the SDK source code."*

Watch what happens — your agent uses Microsoft Learn to find the versioning documentation, then searches GitHub to see how it's implemented. It pulls both sources into a single answer.

<!-- TODO: Screenshot of multi-tool agent response -->

This is a pattern you'll use often: combining official docs with actual source code to get the most accurate answer. Once you're happy with the results, click **Save** to create a new version.

## From Chat to YAML

So far you've been building in the portal UI — clicking buttons, filling forms, chatting in the playground. That's great for getting started, but at some point you want something you can version-control and diff in a pull request.

Look at the top of the agent builder. There are three tabs: **Chat**, **YAML**, and **Code**.

Click **YAML**. You'll see something like this:

<!-- TODO: Screenshot of YAML tab in the agent builder -->

```yaml
name: foundry-expert
model: gpt-5-mini
instructions: |
  You are a helpful agent that looks up the latest information
  on Microsoft Foundry. You search the web, read official
  Microsoft documentation, and explore GitHub repositories
  to provide accurate, up-to-date answers.
tools:
  - type: web_search_preview
  - type: mcp
    server_label: microsoft-learn
    server_url: https://learn.microsoft.com/api/mcp
  - type: mcp
    server_label: github
    server_url: https://api.githubcopilot.com/mcp/
```

That's your entire agent in about 15 lines. Name, model, instructions, and tools — all human-readable and easy to diff.

YAML is a great middle ground between the portal and full code. You can check it into source control alongside your application, and anyone on the team can see exactly what an agent does without clicking through a portal. We'll use this format more in Part 3 when we set up CI/CD.

## From YAML to Code

Click the **Code** tab. This shows the Python (or JavaScript) code that creates the exact same agent:

<!-- TODO: Screenshot of Code tab in the agent builder -->

```python
from azure.ai.projects.models import (
    MCPTool,
    PromptAgentDefinition,
    WebSearchPreviewTool,
)

agent = project_client.agents.create_version(
    agent_name="foundry-expert",
    definition=PromptAgentDefinition(
        model="gpt-5-mini",
        instructions=(
            "You are a helpful agent that looks up the latest information "
            "on Microsoft Foundry. You search the web, read official "
            "Microsoft documentation, and explore GitHub repositories "
            "to provide accurate, up-to-date answers."
        ),
        tools=[
            WebSearchPreviewTool(),
            MCPTool(
                server_label="microsoft-learn",
                server_url="https://learn.microsoft.com/api/mcp",
                require_approval="never",
            ),
            MCPTool(
                server_label="github",
                server_url="https://api.githubcopilot.com/mcp/",
                require_approval="always",
                project_connection_id="my-github-connection",
            ),
        ],
    ),
)
```

Same agent. The portal, YAML, and code are three views of the same thing — you can start in the portal to experiment, prototype in YAML to share with your team, and ship in code for production.

Notice how the code maps directly to what you configured in the UI:
- `agent_name` → the name you typed
- `model` → the model you selected
- `instructions` → the system prompt you wrote
- `tools` → the tools you added, with their server URLs and auth settings

There's nothing hidden. The portal is just a friendly interface for writing this code.

A few things to call out:
- `MCPTool` takes `server_label`, `server_url`, `require_approval`, and optionally `project_connection_id` for authenticated servers
- `WebSearchPreviewTool()` is the same Web Search tool from Part 1, no configuration needed
- The `require_approval` field controls the MCP approval flow we covered earlier — `"never"` for trusted public servers like Microsoft Learn, `"always"` for servers that access private data like GitHub

## VS Code for the Web

You don't have to copy-paste code from the portal into your editor. The Foundry portal includes a built-in VS Code experience connected directly to your project.

1. Click the **Code** tab in the agent builder
2. Click **"Open in VS Code for the Web"**
3. A full VS Code environment opens in your browser, pre-connected to your Foundry project

<!-- TODO: Screenshot of VS Code for the Web launch button -->

From here you can edit your agent's code, run and test changes, and push updates back to your project.

**Try a small change.** Open the agent definition and tweak the instructions — maybe add *"Always cite your sources with links."* Save and run. This creates a new version with the updated instructions.

<!-- TODO: Screenshot of VS Code for the Web editing agent code -->

This is the bridge between portal prototyping and real development. Once you're comfortable making changes here, the jump to a local development environment in Part 3 feels natural.

## What's Next

Your agent now has three knowledge sources — web search, official documentation, and source code. You've seen the same agent defined three ways: in the portal, as YAML, and as Python code. And you've learned about MCP approval requests, which will matter more as you add tools that access private data.

In **Part 3**, you'll go fully pro-code:
- Build a custom tool with an OpenAPI spec
- Connect a Foundry Toolbox — a versioned, centrally-authenticated bundle of tools
- Set up tracing for full observability into every agent decision
- Run automated evaluations against your agent's responses

👉 [Continue to Part 3: Custom Tools, Tracing & Evaluation](foundry-agent-part-3.ipynb)