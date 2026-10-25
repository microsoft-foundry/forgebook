This file describes a fictional team for this tutorial. It is not Microsoft policy.

## Atlas staging authentication

The Atlas support app uses its container app's system-assigned managed identity
when deployed to staging. Use DefaultAzureCredential in Python. Assign Cognitive
Services OpenAI User to that identity on the target Foundry resource. Do not
configure a user-assigned identity client ID for this sample.

Use Azure CLI sign-in for local development. The developer and the deployed
application are different principals; a successful local request does not prove
that the application has access.

## Credentials and exceptions

Do not put API keys in the application configuration. An exception request is not
an approval. This sample contains no exception register, approver decisions, or
exception expiry dates. Questions requiring a specific exception record must be
reviewed by the team's owner; do not invent that record from the general standard.
