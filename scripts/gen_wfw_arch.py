"""Generate the architecture hero image for the microsoft-iq-in-foundry recipe.

Run from repo root:  python scripts/gen_wfw_arch.py
Outputs: notebooks/media/microsoft-iq-in-foundry/01-architecture.png
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = "notebooks/media/microsoft-iq-in-foundry/01-architecture.png"

# Palette
INK = "#0f172a"
MUTED = "#475569"
KS_FILL = "#eff6ff"
KS_EDGE = "#3b82f6"
KB_FILL = "#ecfdf5"
KB_EDGE = "#10b981"
MCP_FILL = "#fef3c7"
MCP_EDGE = "#f59e0b"
CON_FILL = "#f5f3ff"
CON_EDGE = "#8b5cf6"

fig, ax = plt.subplots(figsize=(13, 7.2), dpi=150)
ax.set_xlim(0, 130)
ax.set_ylim(0, 72)
ax.axis("off")


def box(x, y, w, h, fill, edge, title, lines, title_size=12, line_size=9):
    p = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.6,rounding_size=2.2",
        linewidth=1.8, edgecolor=edge, facecolor=fill,
        mutation_aspect=1,
    )
    ax.add_patch(p)
    ax.text(x + w / 2, y + h - 4.2, title, ha="center", va="top",
            fontsize=title_size, fontweight="bold", color=INK)
    ax.text(x + w / 2, y + h - 9.2, "\n".join(lines), ha="center", va="top",
            fontsize=line_size, color=MUTED, linespacing=1.45)


def arrow(x1, y1, x2, y2, color=MUTED, lw=1.8, style="-|>"):
    ax.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2), arrowstyle=style, mutation_scale=16,
        linewidth=lw, color=color, shrinkA=2, shrinkB=2,
    ))


# Column headers
ax.text(16, 70, "3 Federated Knowledge Sources", ha="center", fontsize=12.5,
        fontweight="bold", color=KS_EDGE)
ax.text(56, 70, "Unified Knowledge Base", ha="center", fontsize=12.5,
        fontweight="bold", color=KB_EDGE)
ax.text(110, 70, "Consumers", ha="center", fontsize=12.5,
        fontweight="bold", color=CON_EDGE)

# --- Knowledge Sources (left column) ---
box(2, 45, 28, 17, KS_FILL, KS_EDGE, "Work IQ",
    ["Tenant work content:", "mail, chats, files,", "meetings (kind=workIQ)"])
box(2, 25, 28, 17, KS_FILL, KS_EDGE, "Fabric IQ",
    ["Airline ontology in", "Microsoft Fabric", "(fabricOntology)"])
box(2, 5, 28, 17, MCP_FILL, MCP_EDGE, "Web IQ",
    ["Grounding 'Speedbird'", "MCP: web, news,", "videos, browse"])

# --- Knowledge Base (center) ---
box(40, 16, 34, 36, KB_FILL, KB_EDGE, "Knowledge Base",
    ["1. Plan subqueries",
     "2. Retrieve in parallel",
     "   across all 3 sources",
     "3. Rerank candidates",
     "4. Synthesize ONE",
     "   cited answer",
     "",
     "outputMode =",
     "answerSynthesis"], line_size=9.2)

# --- MCP tool (center-right bridge) ---
box(82, 30, 26, 12, MCP_FILL, MCP_EDGE, "MCP tool",
    ["knowledge_base", "_retrieve"], title_size=11, line_size=9)

# --- Consumers (right column) ---
box(96, 47, 30, 13, CON_FILL, CON_EDGE, "Foundry Agent",
    ["RemoteTool connection", "(ProjectManagedIdentity)"], title_size=11)
box(96, 11, 30, 13, CON_FILL, CON_EDGE, "GitHub Copilot",
    [".vscode/mcp.json", "(+ Copilot CLI / hosts)"], title_size=11)

# --- Arrows: KS -> KB ---
arrow(30, 53.5, 40, 45, color=KS_EDGE)
arrow(30, 33.5, 40, 33, color=KS_EDGE)
arrow(30, 13.5, 40, 22, color=MCP_EDGE)

# KB -> MCP tool
arrow(74, 36, 82, 36, color=KB_EDGE, lw=2.2)

# MCP tool -> consumers
arrow(105, 42, 108, 50, color=CON_EDGE)
arrow(105, 30, 108, 20, color=CON_EDGE)

# Footer caption
ax.text(65, 1.5,
        "Federated retrieval: three live sources, one grounded + cited answer, exposed once over MCP.",
        ha="center", fontsize=9.5, color=MUTED, style="italic")

plt.tight_layout()
fig.savefig(OUT, bbox_inches="tight", facecolor="white")
print("wrote", OUT)
