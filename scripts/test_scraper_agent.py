"""
Test script for Scraper Agent.
Tests the scraper agent via A2A protocol.
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


async def test_scraper_agent(asx_code: str, price_sensitive_only: bool = True, limit: int = 3):
    """
    Test the Scraper Agent by calling it via A2A protocol.

    Args:
        asx_code: ASX ticker code (e.g., "BHP", "CBA")
        price_sensitive_only: Whether to filter price-sensitive announcements
        limit: Maximum number of announcements to fetch
    """
    print(f"\n{'='*80}")
    print(f"TESTING SCRAPER AGENT FOR: {asx_code}")
    print(f"{'='*80}\n")

    asx_code = asx_code.upper()
    agent_url = settings.get_agent_url("scraper")

    print(f"📍 Configuration:")
    print(f"   Agent URL: {agent_url}")
    print(f"   ASX Code: {asx_code}")
    print(f"   Price Sensitive Only: {price_sensitive_only}")
    print(f"   Limit: {limit}")
    print()

    # Build prompt for the scraper agent
    prompt = f"Scrape ASX announcements for {asx_code} with price_sensitive_only={price_sensitive_only} and limit={limit}"

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
            print("📤 Sending request to Scraper Agent...")
            response = await client.post(agent_url, json=payload)
            response.raise_for_status()
            result = response.json()

            # Check for immediate errors
            if "error" in result:
                print("❌ Error: Scraper agent returned an error.")
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
                    print("\n✅ Scraper Agent completed successfully!")

                    # Extract output from A2A response
                    message = task_status.get("message", {})
                    parts = message.get("parts", [])

                    if parts and len(parts) > 0:
                        print("\n📊 Results:")
                        print(json.dumps(parts, indent=2))
                    else:
                        print("\n📊 Full task data:")
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
        print(f"❌ HTTP Error: Could not connect to the Scraper Agent at {agent_url}.")
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
        description="Test Scraper Agent via A2A protocol",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test scraping price-sensitive CBA announcements
  python scripts/test_scraper_agent.py --asx-code CBA

  # Test scraping BHP with custom limit
  python scripts/test_scraper_agent.py --asx-code BHP --limit 5

  # Include all announcements (not just price-sensitive)
  python scripts/test_scraper_agent.py --asx-code WBC --no-price-sensitive
        """
    )

    parser.add_argument(
        "--asx-code",
        type=str,
        required=True,
        help="ASX ticker code (e.g., CBA, BHP, WBC)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Maximum number of announcements to fetch (default: 3)"
    )
    parser.add_argument(
        "--no-price-sensitive",
        action="store_true",
        help="Include all announcements (not just price-sensitive)"
    )

    args = parser.parse_args()

    try:
        asyncio.run(test_scraper_agent(
            asx_code=args.asx_code,
            price_sensitive_only=not args.no_price_sensitive,
            limit=args.limit
        ))
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
