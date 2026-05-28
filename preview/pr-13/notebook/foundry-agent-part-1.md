*Build a Foundry Expert that searches the web — entirely from the portal*

This is **Part 1** of a 4-part series where you build a **Foundry Expert** — an AI agent that knows everything about Microsoft Foundry. By the end of this series, your agent will search documentation, browse the web, execute code, recommend models, and deploy to Microsoft 365 Copilot.

| Part | Focus |
|------|-------|
| **1. Create Your First Agent** | Portal walkthrough — deploy a model, create an agent, test it |
| 2. Tools and Your First Code | Add MCP tools, explore YAML & Code views |
| 3. Custom Tools, Tracing & Evaluation | Pro-code: custom tools, observability, evals |
| 4. Red Team, Deploy & Optimize | Security testing, `azd up`, M365 Copilot |

**What you'll do in Part 1:**
- Navigate the Foundry portal and find your project endpoint
- Deploy `gpt-5-mini` alongside frontier models from multiple providers
- Create an agent with a name, instructions, and the Web Search tool
- Test your agent with a real question
- Understand versioning, response details, and debug tracing

## What is Foundry Agent Service?

Foundry Agent Service is the platform inside Microsoft Foundry for building, testing, and deploying AI agents. An agent is more than a chat model — it's a model that can *act*. It can search the web, look up documents, run code, and call APIs, all based on natural language instructions you give it.

Think of it this way: a model *thinks*, but an agent *does*.

Every agent you build is assembled from six building blocks:

| Building Block | What It Means |
|---------------|---------------|
| **Name** | What it's called — its identity in the API |
| **Instructions** | How it should behave — its system prompt |
| **Model** | The reasoning engine it thinks with |
| **Knowledge** | What it should know — docs, files, search indexes |
| **Tools** | What it can do — search, execute code, call APIs |
| **Memory** | What it remembers across conversations |

In this tutorial, you'll set the first five: a name, instructions, a model, and a tool. Memory is something we'll touch on later as the agent matures — for now, each conversation starts fresh.

## Navigate to Your Project

Head to [ai.azure.com/nextgen](https://ai.azure.com/nextgen) and select your project. The first thing you'll want to note is your **Project endpoint** — you'll need this later when you move to code.

![Microsoft Foundry portal home page showing the Welcome message, project endpoint highlighted in a red rectangle, along with API key and region fields](media/foundry-agent-part-1/01-project-endpoint.png)

## Deploy Your First Model


> **🛠️ Pro-code alternative:** Prefer the command line? You can deploy models with the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) instead of the portal. Make sure you're logged in with `az login` first.

```bash
# Deploy gpt-5-mini via Azure CLI
az cognitiveservices account deployment create \
    --name <your-foundry-resource> \
    --resource-group <your-resource-group> \
    --deployment-name gpt-5-mini \
    --model-name gpt-5-mini \
    --model-version "1" \
    --model-format OpenAI \
    --sku-capacity 10 \
    --sku-name GlobalStandard
```

> **📍 Region availability:** Not every model is available in every region. Run this to check what's available in yours:
>
> ```bash
> az cognitiveservices model list --location <your-region> -o table
> ```


Before you can create an agent, you need a model deployed in your project. Let's get one running.

From the left sidebar, click **Discover** → **Models**. This opens the model catalog — a searchable collection of hundreds of models from OpenAI, Meta, Mistral, Microsoft, and more.

![Foundry portal home page with the Discover tab highlighted in a red rectangle in the top navigation bar](media/foundry-agent-part-1/02-discover-models.png)

Search for **gpt-5-mini** and select it. You'll see the model card with details about capabilities, pricing, and benchmarks.

![Discover page showing the model catalog with the Models nav item highlighted, displaying featured models from providers like OpenAI, Anthropic, Meta, and DeepSeek](media/foundry-agent-part-1/03-model-catalog.png)

Click **Deploy** and choose **Custom Settings** so you can configure the deployment yourself.

![Models page with gpt-5-mini typed in the search bar, showing 40 search results with gpt-5-mini highlighted as the top result](media/foundry-agent-part-1/04-search-results.png)

Give the deployment a name and set the quota to the maximum available. For a tutorial like this, higher quota means less throttling while you experiment.

![gpt-5-mini model details page showing Quick facts sidebar with model provider, type, lifecycle status, and the Deploy button highlighted in a red rectangle](media/foundry-agent-part-1/05-deploy-button.png)

Once the deployment completes, you'll see it listed under your project's deployments.

![Deploy dropdown showing Default settings and Custom settings options, with Custom settings highlighted in a red rectangle showing SKU, quota, PTU, and spillover configuration](media/foundry-agent-part-1/06-custom-settings.png)

While we're here, let's deploy a few more models to see the breadth of what's available. Foundry isn't locked to a single provider — you can deploy frontier models from across the industry.

![Build > Models > Deployments page showing a table of 6 deployed models including DeepSeek-V3.2, Mistral-Large-3, Llama-4-Maverick, Phi-4, grok-4, and gpt-5-mini, all with Succeeded status and Global Standard deployment type](media/foundry-agent-part-1/07-deployed-models.png)

Notice the variety — DeepSeek, Mistral, Meta's Llama, Microsoft's Phi, xAI's Grok, and OpenAI's gpt-5-mini. Foundry gives you access to frontier models from every major provider, all through a single API. For this tutorial, we'll stick with `gpt-5-mini`, but it's good to know your options.


## Create Your Agent

> **🛠️ Pro-code alternative:** You can create agents entirely in Python with the [Azure AI Projects SDK](https://learn.microsoft.com/en-us/python/api/overview/azure/ai-projects-readme?view=azure-python-preview):

```bash
pip install azure-ai-projects --pre
pip install openai azure-identity python-dotenv
```

```python
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition, WebSearchPreviewTool

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(
        endpoint="https://<resource>.services.ai.azure.com/api/projects/<project>",
        credential=credential,
    ) as project_client,
):
    agent = project_client.agents.create_version(
        agent_name="foundry-expert",
        definition=PromptAgentDefinition(
            model="gpt-5-mini",
            instructions="You are a helpful agent that looks up the latest information on Microsoft Foundry.",
            tools=[WebSearchPreviewTool()],
        ),
    )
```

Now for the fun part. From the left sidebar, click **Build** → **Agents**, then click **Create agent**.

![Build section showing the Models > Deployments table with the Agents nav item highlighted in a red rectangle in the left sidebar](media/foundry-agent-part-1/08-agents-nav.png)

You'll land in the agent builder. The first thing to set is the **Name** — this isn't just a label, it's the identifier you'll use to reference this agent in code later. We're calling ours `foundry-expert`.

![Agents page showing an empty state with the message "Create your first agent" and a Create agent button highlighted in a red rectangle](media/foundry-agent-part-1/09-create-agent.png)

Pick a name that's descriptive and lowercase. Avoid spaces — think of it like a function name. This is the handle you'll use in the API, so make it something meaningful.

![Create an agent dialog with the Agent name field filled in as "foundry-expert" and the Create button highlighted in a red rectangle](media/foundry-agent-part-1/10-name-agent.png)


## Add Instructions

Instructions are the system prompt — they shape how your agent behaves, what it focuses on, and how it responds. Think of them as the job description you'd give a new team member.

In the **Instructions** field, paste the following:


```python
You are a helpful agent that looks up the latest information on Microsoft Foundry. You search the web for current news, documentation updates, and announcements about Microsoft Foundry and Azure AI services.
```

![Agent playground for foundry-expert showing the Instructions field populated with system prompt text, gpt-5-mini model selected, and the Chat, YAML, Code tabs on the right panel](media/foundry-agent-part-1/11-agent-instructions.png)

Keep instructions clear and specific. Tell the agent *what* it is, *what* it should do, and *how* it should do it. You can always refine these later — every change creates a new version, so there's no risk in iterating.


## Add the Web Search Tool

Right now your agent can think, but it can't *do* anything. Let's fix that by giving it the ability to search the web.

Scroll down to the **Tools** section and click **Add**.

![Agent playground Tools section with the Add button highlighted in a red rectangle, showing options to Add tools or Upload files](media/foundry-agent-part-1/12-add-tool.png)

You'll see a list of preconfigured tools — these are ready-to-use capabilities you can attach to any agent. Select **Web search**.

![Select a tool dialog showing the Configured tab with 9 available tools including File search, Code interpreter, Azure AI search, Grounding with Bing Search, Web search (selected with checkmark), Computer Use, Fabric Data Agent, SharePoint, and Browser Automation](media/foundry-agent-part-1/13-select-web-search.png)

Click **Add tool** to attach it.

![Agent playground showing Web search tool added to the Tools section with a Bing usage notice banner at the top of the page](media/foundry-agent-part-1/14-web-search-added.png)

Web Search lets your agent access real-time information from the internet. Without it, the agent can only respond based on its training data. With it, your agent can pull current news, documentation, and announcements — exactly what a Foundry Expert needs.

## Save and Versioning

Click **Save** in the top bar. You'll notice something important: the portal doesn't just save — it creates a **new version**.

![Agent playground showing version updated to v2 saved Today 1:46 PM highlighted in a red rectangle, with a test prompt typed in the chat input](media/foundry-agent-part-1/15-save-version.png)

Open the version history and you'll see every save listed with a timestamp. This is crucial for iterating safely — you can always compare versions and roll back if something breaks.

![Version dropdown expanded showing v2 (Today 1:46 PM) checked as current and v1 (Today 1:42 PM) available, with options to Compare versions, Show all version history, and Delete current version](media/foundry-agent-part-1/16-version-history.png)

In the API, you reference agents by name + version (e.g., `foundry-expert` version `1`). This means you can test new instructions or tools on a new version while your stable version keeps running. We'll use this more in later parts of the series.

## Test Your Agent

Time to see it in action. In the chat panel on the right side, type:


```python
What's the latest news about Microsoft Foundry?
```

![Agent playground with the prompt "What's the latest news about Microsoft Foundry?" typed in the chat input field, ready to send](media/foundry-agent-part-1/17-test-prompt.png)

Hit send and watch what happens. Your agent searches the web, finds current information, and synthesizes a response with real-time results.

![Agent response showing bullet-pointed list of recent Microsoft Foundry news items with dates, a cited source link, and response metadata bar showing gpt-5-mini, 29.3s, 18361 tokens, Web search tool used, AI Quality 100%, Safety 100%, and Debug button](media/foundry-agent-part-1/18-agent-response.png)

That's your agent working end to end — it received your question, decided it needed to search the web, executed the search, and composed a response from the results. All from a few lines of instructions and a single tool.


> **🛠️ Pro-code alternative:** Run a conversation with your agent using the SDK:


```python
import os
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(
        endpoint="https://<resource>.services.ai.azure.com/api/projects/<project>",
        credential=credential,
    ) as project_client,
    project_client.get_openai_client() as openai_client,
):
    # Create a conversation with your question
    conversation = openai_client.conversations.create(
        items=[{"type": "message", "role": "user", "content": "What's the latest news about Microsoft Foundry?"}],
    )

    # Run the agent
    response = openai_client.responses.create(
        conversation=conversation.id,
        extra_body={"agent": {"name": "foundry-expert", "type": "agent_reference"}},
        input="",
    )

    print(response.output_text)

```

```python
# Expected output:
# Here are the latest developments regarding Microsoft Foundry:
#
# - **Microsoft Foundry Portal** — The unified portal at ai.azure.com for
#   building, deploying, and managing AI agents and models.
#
# - **Multi-provider model catalog** — Deploy frontier models from OpenAI,
#   Meta, Mistral, Microsoft, and others through a single API.
#
# - **Agent Service** — Build agents with tools like Web Search, Code
#   Interpreter, and File Search, all managed through the portal or SDK.

```

## Understanding Response Details

Look at the toolbar below the agent's response. This is where you go from "it works" to "I understand *how* it works."

![Response metadata toolbar highlighted in a red rectangle showing model (gpt-5-mini), latency (16.5s), token count (11648t), tool used (Web search), AI Quality (100%), Safety (100%), and Debug button](media/foundry-agent-part-1/19-response-toolbar.png)

Each element gives you a different lens into what just happened:

| Element | What It Tells You |
|---------|-------------------|
| **Model** | Which model processed this response (e.g., `gpt-5-mini`) |
| **Tokens** | How many tokens were consumed — both the response tokens and the conversation total |
| **Tools** | Which tools the agent invoked (e.g., `Web search`) |
| **AI Quality** | Automated evaluation of response quality (0-100%) |
| **Safety** | Automated safety evaluation — checks for harmful content (0-100%) |
| **Debug** | Opens the full execution trace — see exactly what happened under the hood |

These metrics update with every response. The quality and safety scores are powered by [Foundry's built-in evaluators](https://learn.microsoft.com/azure/ai-foundry/evaluation) — the same ones you can run at scale in Part 3.

## Debug Tracing

Click **Debug** to open the full execution trace. This is where you see *exactly* what happened behind the scenes.

![Same response metadata toolbar with the Debug button highlighted in a red circle, ready to open the debug trace view](media/foundry-agent-part-1/20-click-debug.png)

The trace shows the complete execution flow: **Conversation → Response → tool calls**. You can see that the agent decided to call `web_search` and then used the results to compose its answer.

![Debug trace dialog showing a Conversation tree with Conversation, Response, and Tool (web_search) nodes, with the Response node selected displaying Input (user prompt) and Output (agent response with news items)](media/foundry-agent-part-1/21-debug-trace.png)

Click into the `web_search` node and you'll see something interesting — the exact search query the model generated on its own.

![Debug trace with the web_search Tool node selected, showing the auto-generated search query "Microsoft Foundry latest news February 2026 Microsoft Foundry announcement" highlighted in a red rectangle](media/foundry-agent-part-1/22-search-query.png)

Look at that: from your simple prompt "What's the latest news about Microsoft Foundry?", the model autonomously crafted the search query *"Microsoft Foundry latest news February 2026 Microsoft Foundry announcement"*. It added the current date and refined the query for better results — no prompt engineering required.

This is observability built in — no extra setup, no external tracing tools, no SDK configuration. You get full visibility into every decision your agent makes, right from the portal. In Part 3, we'll export these traces and build automated evaluations on top of them.


## Preview, Share, and Code

Your agent is working — but right now only you can see it. Before deploying to production, you can share a preview with your team.

Click **Preview** in the top bar to open the dropdown, then select **Preview agent**.

![Preview button dropdown expanded showing Last saved timestamp, Preview agent option, and View sample app code option with GitHub icon linking to a sample app that consumes an agent](media/foundry-agent-part-1/23-preview-dropdown.png)

This opens a clean, standalone chat interface — no portal chrome, no configuration panels. Just your agent, ready for someone to try.

![Agent preview page showing a clean chat interface with "How can I help you today, Nick?" greeting, message input field, and toolbar with New chat, Share, Code, and ellipsis menu buttons](media/foundry-agent-part-1/24-preview-chat.png)

The preview page toolbar gives you four actions:

| Button | What it does |
| --- | --- |
| **New chat** | Start a fresh conversation |
| **Share** | Copy a shareable link so teammates can test the agent |
| **Code** (GitHub icon) | View sample app code on GitHub — an off-the-shelf app you can fork and customize |
| **⋯** (ellipsis) | Settings (theme, language), terms of use, privacy, and feedback |

### Sharing Your Agent

Click **Share** to get a link you can send to anyone on your team.

![Share foundry-expert dialog with instructions to share the link with users who have project access to view the agent preview, and a Copy link button](media/foundry-agent-part-1/26-share-dialog.png)

> **Important:** To use a shared agent link, users must have at minimum the **Azure AI User** role on your project. Without this role, the link will return an access denied error. You can assign roles in the Azure portal under **Access control (IAM)** for your AI resource or resource group.

### Getting the Code

Click the **Code** button (with the GitHub icon) to see a ready-to-use sample application.

![Preview page with the Code button dropdown open, showing View sample app code option described as "An off the shelf sample app that consumes an agent"](media/foundry-agent-part-1/29-view-code.png)

Select **View sample app code** to open the GitHub repository. This is an off-the-shelf application that consumes your agent — fork it, customize it, and deploy it as your own.

Back on the Playground, you'll also find a **Code** tab that generates a Python, C#, or JavaScript snippet with your project endpoint and agent name pre-filled. We'll explore that path in **Part 2**.


## What's Next

You just built and tested your first agent — entirely from the portal. It has a name, instructions, a model, and a tool. It can search the web and answer questions about Microsoft Foundry with real-time information.

In **Part 2** (coming soon), you'll:
- Explore the full tool catalog (1,400+ tools and counting)
- Add Microsoft Learn and GitHub MCP servers to your agent
- Switch from the portal to code using the YAML and Code tabs
- Launch VS Code for the web and make your first code change