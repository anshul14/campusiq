
# Bedrock AgentCore client — Tutor Agent invocation
#
# Environment variables required (set in CDK TutorLambda stack):
#   TUTOR_AGENT_ID        — Bedrock Agent resource ID (e.g. ABCD1234EF)
#   TUTOR_AGENT_ALIAS_ID  — Agent alias ID (e.g. TSTALIASID for test, prod alias for prod)

import os
import boto3

# Client is module-level — reused across Lambda invocations (warm starts)
_client = boto3.client("bedrock-agent-runtime")

TUTOR_AGENT_ID = os.environ["TUTOR_AGENT_ID"]
TUTOR_AGENT_ALIAS_ID = os.environ["TUTOR_AGENT_ALIAS_ID"]


def invoke_tutor_agent(session_id: str, user_message: str) -> str:
    """
    Invoke the Tutor Agent in Bedrock AgentCore and return the full response.

    Even in non-streaming mode, invoke_agent returns an EventStream — this is
    the boto3 API design. There is no "return full text" option. You must iterate
    the event stream and accumulate chunk bytes.

    session_id:
        AgentCore uses this to maintain conversation history across turns.
        The client generates a UUID for each new conversation and passes the
        same ID on follow-up messages.

    inputText:
        The student's message or question.

    Event stream structure:
        Each event is a dict. We care about events with a 'chunk' key.
        chunk['bytes'] is the UTF-8 encoded response fragment.

    Returns:
        Full response text as a single string.
    """
    response = _client.invoke_agent(
        agentId=TUTOR_AGENT_ID,
        agentAliasId=TUTOR_AGENT_ALIAS_ID,
        sessionId=session_id,
        inputText=user_message,
    )

    # Accumulate all chunk bytes from the EventStream
    completion = ""
    for event in response["completion"]:
        if "chunk" in event:
            completion += event["chunk"]["bytes"].decode("utf-8")

    return completion