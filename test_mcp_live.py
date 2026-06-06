"""Live MCP server test -- runs the real stdio server and exercises all three tools."""

import asyncio
import io
import json
import sys

# Force UTF-8 stdout so special chars don't crash on Windows cp1252
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

_FAILURES: list[str] = []


def ok(msg: str) -> None:
    print(f"[OK]   {msg}")


def fail(msg: str) -> None:
    print(f"[FAIL] {msg}")
    _FAILURES.append(msg)


async def run() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from dip_mcp.mcp.server import run_server; run_server()"],
        env=None,
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            # -- 1. Initialise -----------------------------------------------
            await session.initialize()
            ok("MCP handshake complete")

            # -- 2. List tools -----------------------------------------------
            tools_result = await session.list_tools()
            tool_names = [t.name for t in tools_result.tools]
            print(f"\n[OK]   Tools registered ({len(tool_names)}):")
            for t in tools_result.tools:
                print(f"       * {t.name}")
                print(f"         {(t.description or '')[:90]}...")

            expected = {"get_fraktion_distribution", "get_person_info", "list_fraktionen"}
            missing = expected - set(tool_names)
            if missing:
                fail(f"Missing tools: {missing}")
            else:
                ok("All 3 expected tools present")

            # -- 3. list_fraktionen ------------------------------------------
            print("\n--- Tool call: list_fraktionen(wahlperiode=20) ---")
            r1 = await session.call_tool("list_fraktionen", {"wahlperiode": 20})
            if r1.isError:
                fail(f"list_fraktionen errored: {r1.content[0].text if r1.content else r1}")  # type: ignore[union-attr]
            else:
                raw1 = r1.content[0].text if r1.content else "[]"  # type: ignore[union-attr]
                fraktionen = json.loads(raw1)
                ok(f"list_fraktionen returned {len(fraktionen)} Fraktionen (empty = endpoint not available)")
                if fraktionen:
                    print(f"       Sample: {fraktionen[0]}")

            # -- 4. get_person_info ------------------------------------------
            print("\n--- Tool call: get_person_info(name='Merz', wahlperiode=20) ---")
            r2 = await session.call_tool("get_person_info", {"name": "Merz", "wahlperiode": 20})
            if r2.isError:
                fail(f"get_person_info errored: {r2.content[0].text if r2.content else r2}")  # type: ignore[union-attr]
            else:
                raw2 = r2.content[0].text if r2.content else "{}"  # type: ignore[union-attr]
                person = json.loads(raw2)
                if "error" in person:
                    fail(f"get_person_info returned error: {person['error']}")
                else:
                    ok("get_person_info found a match")
                    print(f"       full_name  : {person.get('full_name')}")
                    print(f"       fraktion   : {person.get('fraktion')}")
                    print(f"       wahlperiode: {person.get('wahlperiode_nummer')}")

            # -- 5. get_fraktion_distribution --------------------------------
            print("\n--- Tool call: get_fraktion_distribution(wahlperiode=20) ---")
            print("    (fetches ~5000 persons -- may take ~5 s)")
            r3 = await session.call_tool(
                "get_fraktion_distribution", {"wahlperiode": 20}
            )
            if r3.isError:
                fail(f"get_fraktion_distribution errored: {r3.content[0].text if r3.content else r3}")  # type: ignore[union-attr]
            else:
                raw3 = r3.content[0].text if r3.content else "{}"  # type: ignore[union-attr]
                report = json.loads(raw3)
                dist = report.get("distribution", [])
                if not dist:
                    fail("get_fraktion_distribution returned empty distribution")
                else:
                    ok("get_fraktion_distribution returned valid report")
                    print(f"       wahlperiode   : {report.get('wahlperiode')}")
                    print(f"       total_persons : {report.get('total_persons')}")
                    print(f"       unaffiliated  : {report.get('unaffiliated_count')}")
                    print(f"       fraktionen    : {len(dist)}")
                    top = dist[0]
                    print(
                        f"       #1 fraktion   : {top['fraktion_name']} "
                        f"({top['person_count']} persons, {top['percentage']}%)"
                    )

    # -- Summary -------------------------------------------------------------
    print()
    if _FAILURES:
        print(f"[RESULT] {len(_FAILURES)} FAILURE(S):")
        for f in _FAILURES:
            print(f"         - {f}")
        sys.exit(1)
    else:
        print("[RESULT] ALL MCP TOOL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(run())
