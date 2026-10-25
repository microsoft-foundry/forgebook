This is synthetic application-specific guidance for the Atlas tutorial.

## A request works locally but returns 403 in staging

Confirm that the running Atlas staging container app has its system-assigned
managed identity enabled. Check the role assignment for that identity, not the
developer who signed in locally. The sample requires Cognitive Services OpenAI
User on the target Foundry resource.

Confirm that the app uses the intended Foundry endpoint. Allow for role-assignment
propagation before retrying. This checklist does not prove the cause of every 403:
network restrictions and an incorrect endpoint also require investigation.

## A question asks about an unrecorded exception

Prepare a handoff containing the question, retrieved sources, and the missing
record. Do not approve an exception, infer an expiry date, or change credentials.
