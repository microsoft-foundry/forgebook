"""Plan, create, or remove only this recipe's Learn + team-file sample resources."""

import argparse
import hashlib
import json
import os
import time
import uuid
from pathlib import Path

from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    AzureOpenAIVectorizer, AzureOpenAIVectorizerParameters, HnswAlgorithmConfiguration,
    KnowledgeBase, KnowledgeBaseAzureOpenAIModel, KnowledgeSourceReference,
    McpServerAutoOutputParsing, McpServerKnowledgeSource, McpServerKnowledgeSourceParameters,
    McpServerTool, SearchField, SearchFieldDataType, SearchIndex,
    SearchIndexKnowledgeSource, SearchIndexKnowledgeSourceParameters,
    SemanticConfiguration, SemanticField, SemanticPrioritizedFields, SemanticSearch,
    SimpleField, VectorSearch, VectorSearchProfile,
)
from dotenv import load_dotenv
from openai import AzureOpenAI

from team_data import load_team_documents

PLAN = Path(".learn-team-plan.local")
RECEIPT = Path(".learn-team-sample.local")
LEARN_URL = "https://learn.microsoft.com/api/mcp"


def fingerprint(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def names_for(prefix: str) -> dict:
    return {"index": prefix, "team": f"{prefix}-team", "learn": f"{prefix}-learn", "kb": f"{prefix}-kb"}


def definitions(config: dict) -> dict:
    names = names_for(config["prefix"])
    model_endpoint = config["model_endpoint"]
    index = SearchIndex(
        name=names["index"],
        fields=[
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            *[SearchField(name=field, type=SearchFieldDataType.String, searchable=True)
              for field in ("title", "content")],
            *[SimpleField(name=field, type=SearchFieldDataType.String, filterable=True)
              for field in ("source_path", "application", "environment")],
            SearchField(
                name="content_vector", type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True, vector_search_dimensions=1536, vector_search_profile_name="vector",
            ),
        ],
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
            profiles=[VectorSearchProfile(
                name="vector", algorithm_configuration_name="hnsw", vectorizer_name="embedding"
            )],
            vectorizers=[AzureOpenAIVectorizer(
                vectorizer_name="embedding",
                parameters=AzureOpenAIVectorizerParameters(
                    resource_url=model_endpoint, deployment_name=config["embedding_deployment"],
                    model_name="text-embedding-3-small",
                ),
            )],
        ),
        semantic_search=SemanticSearch(
            default_configuration_name="semantic",
            configurations=[SemanticConfiguration(
                name="semantic",
                prioritized_fields=SemanticPrioritizedFields(
                    title_field=SemanticField(field_name="title"),
                    content_fields=[SemanticField(field_name="content")],
                ),
            )],
        ),
    )
    team = SearchIndexKnowledgeSource(
        name=names["team"],
        description="Synthetic Atlas staging application profile, team standards, and troubleshooting.",
        search_index_parameters=SearchIndexKnowledgeSourceParameters(
            search_index_name=names["index"], semantic_configuration_name="semantic",
            source_data_fields=[{"name": field} for field in
                                ("id", "title", "content", "source_path", "application", "environment")],
        ),
    )
    learn = McpServerKnowledgeSource(
        name=names["learn"], description="Official Microsoft Learn platform documentation.",
        results_processing="rerank",
        mcp_server_parameters=McpServerKnowledgeSourceParameters(
            server_url=LEARN_URL,
            tools=[McpServerTool(
                name="microsoft_docs_search", output_parsing=McpServerAutoOutputParsing(),
                results_processing="none", max_output_tokens=2000,
            )],
        ),
    )
    kb = KnowledgeBase(
        name=names["kb"], description="Microsoft Learn plus synthetic Atlas team documentation",
        models=[KnowledgeBaseAzureOpenAIModel(
            azure_open_ai_parameters=AzureOpenAIVectorizerParameters(
                resource_url=model_endpoint, deployment_name=config["chat_deployment"], model_name="gpt-4.1",
            ),
        )],
        knowledge_sources=[KnowledgeSourceReference(name=names["learn"]),
                           KnowledgeSourceReference(name=names["team"])],
        retrieval_instructions=(
            "Use Microsoft Learn for official platform behavior. For questions about the Atlas "
            "support app or staging environment, search the team source as well as Learn. "
            "Team files are synthetic application context, not Microsoft policy. "
            "Do not invent exception approvals or configuration."
        ),
    )
    return {"index": index, "team": team, "learn": learn, "kb": kb}


def plan_sample() -> None:
    if PLAN.exists() or RECEIPT.exists():
        raise FileExistsError("An existing plan/receipt must be inspected or cleaned up before planning.")
    config = {
        "prefix": f"learn-team-{uuid.uuid4().hex[:12]}",
        "search_endpoint": os.environ["SEARCH_ENDPOINT"],
        "model_endpoint": os.environ["FOUNDRY_ENDPOINT"],
        "chat_deployment": os.getenv("CHAT_DEPLOYMENT", "gpt-4.1"),
        "embedding_deployment": os.getenv("EMBEDDING_DEPLOYMENT", "text-embedding-3-small"),
    }
    documents = load_team_documents()
    plan = {"config": config, "documents_hash": fingerprint({"documents": documents}),
            "objects": {key: value.as_dict() for key, value in definitions(config).items()}}
    PLAN.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(plan, indent=2))
    print("Creates one index, two knowledge sources, and one knowledge base on the existing service.")
    print("Embeddings, query planning, semantic ranking, query vectors, and retrieval can incur charges.")
    print("Does not change shared services, models, identities, permissions, or networking.")
    print(f"Review the plan, then approve this fingerprint: {fingerprint(plan)}")


def create_sample(approved: str) -> None:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    if not approved or approved != fingerprint(plan):
        raise ValueError("Approval must match the unchanged saved plan fingerprint.")
    if RECEIPT.exists():
        raise FileExistsError("A sample receipt already exists. Inspect it before creating resources.")
    config = plan["config"]
    documents = load_team_documents()
    if plan["documents_hash"] != fingerprint({"documents": documents}):
        raise ValueError("Team files changed after planning. Review and regenerate the plan.")
    objects = definitions(config)
    if plan["objects"] != {key: value.as_dict() for key, value in objects.items()}:
        raise ValueError("Resource definitions changed after planning.")
    names = names_for(config["prefix"])
    receipt = {"endpoint": config["search_endpoint"], "names": names, "created": []}

    def save():
        RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    save()
    with DefaultAzureCredential() as credential:
        with AzureOpenAI(
            azure_endpoint=config["model_endpoint"], api_version="2024-10-21",
            azure_ad_token_provider=get_bearer_token_provider(
                credential, "https://cognitiveservices.azure.com/.default"
            ),
        ) as model:
            embedded = model.embeddings.create(
                model=config["embedding_deployment"], input=[doc["content"] for doc in documents],
                dimensions=1536,
            )
        vectors = {item.index: item.embedding for item in embedded.data}
        if len(embedded.data) != len(documents) or set(vectors) != set(range(len(documents))):
            raise ValueError("Embedding response does not cover each input chunk exactly once.")
        rows = [{**doc, "content_vector": vectors[i]} for i, doc in enumerate(documents)]
        with SearchIndexClient(config["search_endpoint"], credential) as indexes:
            indexes.create_index(objects["index"])
            receipt["created"].append("index")
            save()
            with SearchClient(config["search_endpoint"], names["index"], credential) as search:
                uploaded = search.upload_documents(rows)
                if len(uploaded) != len(rows) or any(not item.succeeded for item in uploaded):
                    raise RuntimeError("Not all chunks were indexed. Inspect results and retain the receipt.")
                for _ in range(30):
                    if search.get_document_count() == len(rows):
                        break
                    time.sleep(2)
                else:
                    raise TimeoutError("Indexed chunks were not ready after 60 seconds.")
            for key in ("team", "learn", "kb"):
                create = (indexes.create_or_update_knowledge_base if key == "kb"
                          else indexes.create_or_update_knowledge_source)
                create(objects[key], headers={"If-None-Match": "*"})
                receipt["created"].append(key)
                save()
    print(f"Indexed {len(rows)} chunks from three synthetic files. Add to your notebook .env:")
    print(f'KB_NAME="{names["kb"]}"\nTEAM_SOURCE="{names["team"]}"\nLEARN_SOURCE="{names["learn"]}"')


def cleanup_sample(approved: str) -> None:
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    if approved != fingerprint(receipt):
        raise ValueError("Cleanup approval must match the current ownership receipt fingerprint.")
    names = receipt["names"]
    if not names["index"].startswith("learn-team-") or names != names_for(names["index"]):
        raise ValueError("Receipt does not identify this recipe's resources; nothing deleted.")
    with DefaultAzureCredential() as credential:
        with SearchIndexClient(receipt["endpoint"], credential) as indexes:
            deletes = {
                "kb": indexes.delete_knowledge_base,
                "learn": indexes.delete_knowledge_source,
                "team": indexes.delete_knowledge_source,
                "index": indexes.delete_index,
            }
            for key in ("kb", "learn", "team", "index"):
                if key not in receipt["created"]:
                    continue
                try:
                    deletes[key](names[key])
                except ResourceNotFoundError:
                    print(f"Already absent: {names[key]}")
                else:
                    print(f"Deleted owned sample {key}: {names[key]}")
                receipt["created"].remove(key)
                RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    RECEIPT.unlink()
    PLAN.unlink(missing_ok=True)
    print("Sample objects removed; shared Search service, models, roles and networking retained.")


if __name__ == "__main__":
    load_dotenv(".env", override=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "create", "cleanup-plan", "cleanup"))
    parser.add_argument("--approve", default="")
    args = parser.parse_args()
    if args.action == "plan":
        plan_sample()
    elif args.action == "create":
        create_sample(args.approve)
    elif args.action == "cleanup-plan":
        receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        print(json.dumps(receipt, indent=2))
        print("Deletes only the owned objects above. Approve receipt fingerprint:", fingerprint(receipt))
    else:
        cleanup_sample(args.approve)
