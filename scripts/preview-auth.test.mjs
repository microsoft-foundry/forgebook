import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { parse } from "yaml";

const consumer = parse(readFileSync(new URL("../.github/workflows/preview-deploy.yml", import.meta.url), "utf8"));
const producer = parse(readFileSync(new URL("../.github/workflows/preview.yml", import.meta.url), "utf8"));
const job = consumer.jobs.deploy;

function step(id) {
  const result = job.steps.find((candidate) => candidate.id === id);
  assert.ok(result, `Missing preview step: ${id}`);
  return result;
}

test("members-only App uses the organization installation lookup", () => {
  const token = step("team-token");
  assert.match(token.uses, /^actions\/create-github-app-token@[a-f0-9]{40}$/);
  assert.equal(token.with.owner, "${{ github.repository_owner }}");
  assert.equal(token.with["permission-members"], "read");
  assert.equal(token.with["private-key"], "${{ secrets.FORGEBOOK_TEAM_CHECK_PRIVATE_KEY }}");
  assert.equal(
    Object.hasOwn(token.with, "repositories"),
    false,
    "A repositories input selects the repository-installation endpoint, which cannot resolve this organization-only App",
  );
  const permissions = Object.keys(token.with).filter((key) => key.startsWith("permission-"));
  assert.deepEqual(permissions, ["permission-members"]);
});

test("only the membership check receives the App token", () => {
  assert.equal(step("membership").with["github-token"], "${{ steps.team-token.outputs.token }}");
  for (const current of job.steps) {
    if (current.uses?.startsWith("actions/download-artifact@")) {
      assert.equal(current.with["github-token"], "${{ secrets.GITHUB_TOKEN }}");
    }
    if (current.uses?.startsWith("actions/github-script@") && current.id !== "membership") {
      assert.equal(current.with["github-token"] ?? "${{ secrets.GITHUB_TOKEN }}", "${{ secrets.GITHUB_TOKEN }}");
    }
  }
});

test("privileged preview deployment stays gated and never runs PR source", () => {
  assert.equal(job.if, "${{ github.event.workflow_run.conclusion == 'success' }}");
  assert.deepEqual(job.permissions, { contents: "write", "pull-requests": "write", actions: "read" });
  assert.equal(job.steps.some((current) => current.uses?.startsWith("actions/checkout@")), false);
  for (const id of ["team-token", "membership"]) {
    assert.equal(step(id)["continue-on-error"] ?? false, false);
  }
  const deploy = job.steps.find((current) => current.uses?.startsWith("JamesIves/github-pages-deploy-action@"));
  assert.ok(deploy);
  assert.equal(deploy.if, "steps.membership.outputs.is_member == 'true'");
});

test("the unprivileged producer runs the authentication regression check", () => {
  const build = producer.jobs["build-and-preview"];
  assert.deepEqual(build.permissions, { contents: "read" });
  const check = build.steps.find((current) => current.run === "npm run test:preview-auth");
  assert.ok(check, "Preview PR must run the token-routing regression check");
  assert.equal(check["working-directory"], "./scripts");
  assert.equal(JSON.stringify(producer).includes("FORGEBOOK_TEAM_CHECK_PRIVATE_KEY"), false);
});
