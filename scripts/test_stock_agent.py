"""
Test script for Stock Agent.
Tests the stock agent's ability to fetch market data via A2A protocol.
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


async def test_stock_agent(asx_code: str):
    """
    Test the Stock Agent by calling it via A2A protocol.

    Args:
        asx_code: ASX ticker code (e.g., "BHP", "CBA")
    """
    print(f"\n{'='*80}")
    print(f"TESTING STOCK AGENT FOR: {asx_code}")
    print(f"{'='*80}\n")

    asx_code = asx_code.upper()
    agent_url = settings.get_agent_url("stock")

    print(f"📍 Configuration:")
    print(f"   Agent URL: {agent_url}")
    print(f"   ASX Code: {asx_code}")
    print()

    # Build prompt for the stock agent
    prompt = f"Get stock data for {asx_code}"

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
            print("📤 Sending request to Stock Agent...")
            response = await client.post(agent_url, json=payload)
            response.raise_for_status()
            result = response.json()

            # Check for immediate errors
            if "error" in result:
                print("❌ Error: Stock agent returned an error.")
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
                await asyncio.sleep(2)

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
                    print("\n✅ Stock Agent completed successfully!")

                    # Extract output from A2A response
                    message = task_status.get("message", {})
                    parts = message.get("parts", [])

                    print("\n📊 Stock Data Results:")
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
        print(f"❌ HTTP Error: Could not connect to the Stock Agent at {agent_url}.")
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
        description="Test Stock Agent via A2A protocol",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test fetching stock data for CBA
  python scripts/test_stock_agent.py --asx-code CBA

  # Test fetching stock data for BHP
  python scripts/test_stock_agent.py --asx-code BHP
        """
    )

    parser.add_argument(
        "--asx-code",
        type=str,
        required=True,
        help="ASX ticker code (e.g., CBA, BHP, WBC)"
    )

    args = parser.parse_args()

    try:
        asyncio.run(test_stock_agent(asx_code=args.asx_code))
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
