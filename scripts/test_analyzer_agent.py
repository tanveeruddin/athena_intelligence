"""
Test script for Analyzer Agent.
Tests the analyzer agent's ability to process and analyze announcements via A2A protocol.
"""

import asyncio
import sys
import httpx
import json
import uuid
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger()
settings = get_settings()

# Enable DEBUG logging for detailed output
logger.remove()
logger.add(sys.stdout, level="DEBUG", colorize=True)


async def test_analyzer_agent(pdf_url: str, asx_code: str, announcement_id: str = "test_announcement_001"):
    """
    Test the Analyzer Agent by calling it via A2A protocol.

    Args:
        pdf_url: URL to the PDF announcement
        asx_code: ASX ticker code (e.g., "BHP", "CBA")
        announcement_id: ID for the announcement (for testing)
    """
    print(f"\n{'='*80}")
    print(f"TESTING ANALYZER AGENT")
    print(f"{'='*80}\n")

    asx_code = asx_code.upper()
    agent_url = settings.get_agent_url("analyzer")

    print(f"📍 Configuration:")
    print(f"   Agent URL: {agent_url}")
    print(f"   ASX Code: {asx_code}")
    print(f"   PDF URL: {pdf_url[:80]}...")
    print(f"   Announcement ID: {announcement_id}")
    print()

    # Build prompt for the analyzer agent
    prompt = f"Process and analyze the announcement PDF from {pdf_url} for {asx_code}"

    payload = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "params": {
            "message": {
                "messageId": str(uuid.uuid4()),
                "role": "user",
                "parts": [{"text": prompt}]
            }
        },
        "id": str(uuid.uuid4())
    }

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            # Send the task
            print("📤 Sending request to Analyzer Agent...")
            print("   (This may take 30-60 seconds for PDF download and analysis...)")
            response = await client.post(agent_url, json=payload)
            response.raise_for_status()
            result = response.json()

            # Check for immediate errors
            if "error" in result:
                print("❌ Error: Analyzer agent returned an error.")
                print("Details:", result["error"])
                return

            # Get task_id from response
            task_id = result.get("result", {}).get("id")
            if not task_id:
                print("❌ Error: No task_id received from agent.")
                print("Response:", json.dumps(result, indent=2))
                return

            print(f"✅ Task created successfully! Task ID: {task_id}")
            print(f"🔄 Polling for task completion...\n")

            # Poll for the result
            while True:
                await asyncio.sleep(3)  # Longer sleep for analyzer

                poll_payload = {
                    "jsonrpc": "2.0",
                    "method": "tasks/get",
                    "params": {"id": task_id},
                    "id": str(uuid.uuid4())
                }

                response = await client.post(agent_url, json=poll_payload)
                response.raise_for_status()
                poll_result = response.json()

                task_data = poll_result.get("result", {})
                task_status = task_data.get("status", {})
                state = task_status.get("state", "unknown")

                print(f"   Task status: {state}")

                if state == "completed":
                    print("\n✅ Analyzer Agent completed successfully!")

                    # Extract output from A2A response
                    message = task_status.get("message", {})
                    parts = message.get("parts", [])

                    print("\n📊 Analysis Results:")
                    if parts and len(parts) > 0:
                        print(json.dumps(parts, indent=2))
                    else:
                        print("Full task data:")
                        print(json.dumps(task_data, indent=2))
                    break

                elif state == "failed":
                    print("\n❌ Task failed!")
                    error_message = task_status.get("message", {})
                    print("Error details:", json.dumps(error_message, indent=2))
                    break

                elif state not in ["in_progress", "pending"]:
                    print(f"\n⚠️  Unknown status: {state}")
                    print("Full response:", json.dumps(poll_result, indent=2))
                    break

    except httpx.RequestError as e:
        print(f"❌ HTTP Error: Could not connect to the Analyzer Agent at {agent_url}.")
        print(f"   Please ensure the agent is running. You can start it with './run.sh'.")
        print(f"   Error details: {e}")
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user.")
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Test Analyzer Agent via A2A protocol",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test analyzing a specific announcement PDF
  python scripts/test_analyzer_agent.py --pdf-url "https://..." --asx-code CBA

Note: You need a valid PDF URL from ASX announcements page.
You can get one by running the test_scraper_agent.py script first.
        """
    )

    parser.add_argument(
        "--pdf-url",
        type=str,
        required=True,
        help="URL to the PDF announcement"
    )
    parser.add_argument(
        "--asx-code",
        type=str,
        required=True,
        help="ASX ticker code (e.g., CBA, BHP, WBC)"
    )
    parser.add_argument(
        "--announcement-id",
        type=str,
        default="test_announcement_001",
        help="Announcement ID for testing (default: test_announcement_001)"
    )

    args = parser.parse_args()

    try:
        asyncio.run(test_analyzer_agent(
            pdf_url=args.pdf_url,
            asx_code=args.asx_code,
            announcement_id=args.announcement_id
        ))
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
