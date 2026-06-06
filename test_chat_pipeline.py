"""Single-turn chat pipeline test.

Simulates exactly what 'dip-mcp chat' does for one question:
  1. Send user message + tool schemas to Groq
  2. Groq selects the tool and returns a tool-call request
  3. Dispatch to the real DIP API function
  4. Feed result back to Groq for final answer
"""

import asyncio
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

from dip_mcp.cli.chat import TOOL_SCHEMAS, _dispatch_tool  # noqa: E402
import json  # noqa: E402

from dip_mcp.config import settings  # noqa: E402
from dip_mcp.llm.groq_client import CHAT_SYSTEM_PROMPT, GroqClient  # noqa: E402

QUESTION = "Wie ist die Fraktionsverteilung in der 20. Wahlperiode?"


async def run() -> None:
    print("=" * 60)
    print("USER QUESTION:")
    print(f"  {QUESTION}")
    print("=" * 60)

    conversation: list[dict] = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        {"role": "user", "content": QUESTION},
    ]

    async with GroqClient(settings) as llm:
        # -- Step 1: Send to Groq with tool schemas ----------------------
        print("\n[1/4] Sending question to Groq with tool schemas...")
        response = await llm.chat_with_tools(conversation, TOOL_SCHEMAS)
        choice = response.choices[0]

        print(f"      finish_reason = {choice.finish_reason!r}")

        if choice.finish_reason != "tool_calls":
            print("\n[WARN] Model answered directly without calling a tool:")
            print(choice.message.content)
            return

        tool_calls = choice.message.tool_calls or []
        print(f"      tool_calls requested: {[tc.function.name for tc in tool_calls]}")

        # -- Step 2: Log tool selection ----------------------------------
        for tc in tool_calls:
            args = json.loads(tc.function.arguments)
            print(f"\n[2/4] Tool selected: {tc.function.name!r}")
            print(f"      Arguments: {args}")

        # Append assistant tool-call message to conversation
        conversation.append({
            "role": "assistant",
            "content": choice.message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ],
        })

        # -- Step 3: Execute each tool (real DIP API call) ---------------
        for tc in tool_calls:
            args = json.loads(tc.function.arguments)
            print(f"\n[3/4] Calling DIP API via {tc.function.name}({args})...")
            print("      (fetching real data -- may take a few seconds)")

            result_str = await _dispatch_tool(tc.function.name, args)
            result = json.loads(result_str)

            # Print a summary of what came back
            if "distribution" in result:
                dist = result["distribution"]
                print(f"      -> Got distribution with {len(dist)} Fraktionen")
                print(f"         total_persons: {result.get('total_persons')}")
                print(f"         unaffiliated:  {result.get('unaffiliated_count')}")
                print("         Top 5:")
                for entry in dist[:5]:
                    print(f"           {entry['fraktion_name']}: {entry['person_count']} ({entry['percentage']}%)")
            else:
                print(f"      -> Result keys: {list(result.keys())}")

            conversation.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_str,
            })

        # -- Step 4: Get final German-language answer from Groq ----------
        print("\n[4/4] Asking Groq to compose the final answer...")
        final = await llm.chat_with_tools(conversation, TOOL_SCHEMAS)
        answer = final.choices[0].message.content or ""

        print("\n" + "=" * 60)
        print("GROQ FINAL ANSWER (German):")
        print("=" * 60)
        print(answer)
        print("=" * 60)

        # -- Verify the answer contains expected Fraktion names ----------
        expected_fraktionen = ["CDU", "SPD", "FDP", "AfD", "GRÜNE", "LINKE", "Grüne"]
        found = [f for f in expected_fraktionen if f.lower() in answer.lower()]
        print(f"\n[CHECK] Fraktion names in answer: {found}")
        if len(found) >= 3:
            print("[PASS]  Answer contains real Fraktion data from DIP API")
        else:
            print("[WARN]  Answer may not contain sufficient Fraktion names")

        has_percent = "%" in answer
        print(f"[CHECK] Contains percentage values: {'YES' if has_percent else 'NO'}")


if __name__ == "__main__":
    asyncio.run(run())
