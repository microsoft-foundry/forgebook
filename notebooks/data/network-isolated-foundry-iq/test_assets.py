"""Offline artifact checks; BICEP_CLI enables compilation, never live validation."""
import ast
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parent


class AssetTests(unittest.TestCase):
    def test_python_sources_compile_without_importing_cloud_sdks(self):
        for p in ROOT.rglob("*.py"):
            if ".venv" not in p.parts:
                with self.subTest(path=str(p.relative_to(ROOT))):
                    ast.parse(p.read_text(encoding="utf-8"), filename=str(p))

    def test_all_bicep_modules_are_checked_in(self):
        for p in (ROOT / "infra").rglob("*.bicep"):
            text = p.read_text(encoding="utf-8")
            for module in re.findall(r"module\s+\w+\s+'([^']+)'", text):
                self.assertTrue((p.parent/module).is_file(), (p, module))

    def test_private_template_deltas(self):
        mods = ROOT/"infra/standard/modules-network-secured"
        search = (mods/"standard-dependent-resources.bicep").read_text(encoding="utf-8")
        self.assertIn("name: 'standard2'", search)
        self.assertNotIn("disableLocalAuth: false", search)
        self.assertNotIn("bypass: 'AzureServices'", search)
        account = (mods/"ai-account-identity.bicep").read_text(encoding="utf-8")
        self.assertIn("bypass: 'None'", account)
        wrapper = (ROOT/"infra/main.bicep").read_text(encoding="utf-8")
        self.assertIn("developerIpCidr: ''", wrapper)
        self.assertNotIn("param existing", wrapper)
        network = (ROOT/"infra/network.bicep").read_text(encoding="utf-8")
        self.assertIn("Microsoft.Network/natGateways", network)
        self.assertIn("nextHopType: 'VirtualAppliance'", network)
        self.assertNotIn("virtualNetworkPeerings", network)

    def test_knowledge_resource_names_are_nested_parameters(self):
        wrapper = (ROOT/"infra/main.bicep").read_text(encoding="utf-8")
        module = (ROOT/"infra/knowledge-resources.bicep").read_text(encoding="utf-8")
        self.assertIn("module knowledge 'knowledge-resources.bicep'", wrapper)
        for name, standard_output in (("accountName", "deployedAccountName"),
                                      ("searchName", "searchName"), ("storageName", "storageName")):
            self.assertIn(f"{name}: standard.outputs.{standard_output}", wrapper)
            self.assertIn(f"param {name} string", module)
        self.assertNotIn("resource ", wrapper)
        self.assertIn("storage_endpoint: knowledge.outputs.storageEndpoint", wrapper)
        self.assertIn("embedding_deployment: knowledge.outputs.embeddingDeployment", wrapper)
        self.assertNotIn("#disable", module)

    @unittest.skipUnless(os.environ.get("BICEP_CLI"), "Set BICEP_CLI to an approved local compiler")
    def test_compiled_knowledge_resources_preserve_scope_and_order(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/"main.json"
            compiled = subprocess.run(
                [os.environ["BICEP_CLI"], "build", str(ROOT/"infra/main.bicep"),
                 "--no-restore", "--outfile", str(output)],
                capture_output=True, text=True, encoding="utf-8", check=False,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            template = json.loads(output.read_text(encoding="utf-8"))
        modules = template["resources"]
        self.assertEqual(len(modules), 3)
        knowledge = next(r for r in modules if "-knowledge" in r["name"])
        self.assertEqual(len(knowledge["dependsOn"]), 1)
        self.assertIn("-standard", knowledge["dependsOn"][0])
        standard = next(r for r in modules if "-standard" in r["name"])
        self.assertIn("-network", standard["dependsOn"][0])
        nested = knowledge["properties"]["template"]
        for name in ("accountName", "searchName", "storageName"):
            self.assertEqual(nested["parameters"][name]["type"], "string")
        resources = nested["resources"]
        self.assertEqual(len(resources), 6)
        for resource in resources:
            self.assertNotIn("reference(", resource["name"])
            self.assertNotIn("reference(", resource.get("scope", ""))
        container = next(r for r in resources if r["type"].endswith("/containers"))
        self.assertEqual(container["properties"]["publicAccess"], "None")
        links = [r for r in resources if r["type"].endswith("/sharedPrivateLinkResources")]
        self.assertEqual({r["properties"]["groupId"] for r in links}, {"blob", "openai_account"})
        roles = [r for r in resources if r["type"] == "Microsoft.Authorization/roleAssignments"]
        self.assertEqual(len(roles), 2)
        for role in roles:
            self.assertIn("parameters('searchName')", role["properties"]["principalId"])
        blob_role = next(r for r in roles if "2a2b9908" in r["properties"]["roleDefinitionId"])
        model_role = next(r for r in roles if "a97b65f3" in r["properties"]["roleDefinitionId"])
        self.assertIn("Microsoft.Storage/storageAccounts/blobServices/containers", blob_role["scope"])
        self.assertIn("Microsoft.CognitiveServices/accounts", model_role["scope"])
        self.assertIn("parameters('storageName')", nested["outputs"]["storageEndpoint"]["value"])

    def test_hosted_lock_and_configuration(self):
        lock = tomllib.loads((ROOT/"hosted/uv.lock").read_text(encoding="utf-8"))
        versions = {p["name"]: p["version"] for p in lock["package"]}
        self.assertEqual(versions["agent-framework-foundry-hosting"], "1.0.0b260821")
        self.assertEqual(versions["agent-framework-foundry"], "1.12.0")
        source = (ROOT/"hosted/main.py").read_text(encoding="utf-8")
        self.assertIn("ResponsesHostServer(agent)", source)
        self.assertIn("FoundryToolbox(credential", source)
        self.assertIn("LAB_EGRESS_PROBE_APPROVAL", source)
        config = (ROOT/"hosted/azure.yaml").read_text(encoding="utf-8")
        self.assertIn("image: ${HOSTED_IMAGE_DIGEST}", config)
        self.assertNotIn("FOUNDRY_PROJECT_ENDPOINT:", config)

    def test_saved_evidence_is_not_live(self):
        evidence = json.loads((ROOT/"evidence.json").read_text(encoding="utf-8"))
        self.assertFalse(evidence["live_run"])
        self.assertFalse(evidence["publish_ready"])
        self.assertTrue(all(c["status"] == "BLOCKED" for c in evidence["controls"]))

    def test_no_unresolved_local_notebook_links(self):
        notebook = json.loads((ROOT.parents[1]/"network-isolated-foundry-iq.ipynb").read_text(encoding="utf-8"))
        for cell in notebook["cells"]:
            if cell["cell_type"] == "markdown":
                for link in re.findall(r"\]\(((?:data|media)/[^)#]+)", "".join(cell["source"])):
                    self.assertTrue((ROOT.parents[1]/link).exists(), link)


if __name__ == "__main__":
    unittest.main(verbosity=2)
