"""
Test script for Evaluation Agent.
Tests the evaluation agent's LLM-as-a-Judge capability.
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


async def test_evaluation_agent():
    """
    Test the Evaluation Agent by requesting aggregate scores.
    """
    print(f"\n{'='*80}")
    print(f"TESTING EVALUATION AGENT")
    print(f"{'='*80}\n")

    agent_url = settings.get_agent_url("evaluation")

    print(f"📍 Configuration:")
    print(f"   Agent URL: {agent_url}")
    print()

    # Build prompt for the evaluation agent
    prompt = "Get aggregate evaluation scores for all analyses"

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
            print("📤 Sending request to Evaluation Agent...")
            response = await client.post(agent_url, json=payload)
            response.raise_for_status()
            result = response.json()

            # Check for immediate errors
            if "error" in result:
                print("❌ Error: Evaluation agent returned an error.")
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
                    print("\n✅ Evaluation Agent completed successfully!")

                    # Extract output from A2A response
                    message = task_status.get("message", {})
                    parts = message.get("parts", [])

                    print("\n📊 Evaluation Results:")
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
        print(f"❌ HTTP Error: Could not connect to the Evaluation Agent at {agent_url}.")
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
        description="Test Evaluation Agent via A2A protocol",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test getting aggregate evaluation scores
  python scripts/test_evaluation_agent.py

Note: You need to have run some evaluations first. Run the full pipeline to create evaluation records.
        """
    )

    args = parser.parse_args()

    try:
        asyncio.run(test_evaluation_agent())
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
