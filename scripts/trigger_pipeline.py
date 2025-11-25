"""
Script to trigger the coordinator agent's announcement processing pipeline.

This provides a simple, code-based alternative to using `curl`.
Uses the A2A protocol format to communicate with the coordinator agent.
"""
import httpx
import sys
import json
import time

# Configuration
COORDINATOR_URL = "http://localhost:8000"

def trigger_pipeline(asx_code: str, limit: int = None, price_sensitive_only: bool = True):
    """
    Sends a request to the Coordinator Agent to start the announcement pipeline.
    Uses the A2A protocol format: sends task, gets task_id, polls for completion.

    Args:
        asx_code: ASX ticker code (e.g., "BHP", "CBA")
        limit: Maximum number of announcements to process (None = use config default)
        price_sensitive_only: Filter to only price-sensitive announcements
    """
    print(f"▶️ Triggering pipeline for {asx_code} on coordinator at {COORDINATOR_URL}...")

    # Use text prompt to invoke the LLM agent (which has the skill as a tool)
    # This matches A2A v0.3.0 message/send requirements
    import uuid
    message_id = str(uuid.uuid4())

    # Build prompt with parameters
    limit_text = f"limit={limit}" if limit is not None else "using default limit from config"
    prompt_text = f"Run the announcement pipeline for ASX code {asx_code} with {limit_text} and price_sensitive_only={price_sensitive_only}"

    payload = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "params": {
            "message": {
                "messageId": message_id,
                "role": "user",
                "parts": [{
                    "text": prompt_text
                }]
            }
        },
        "id": "1"
    }

    try:
        with httpx.Client(timeout=300.0) as client:
            # 1. Send the task
            print("📤 Sending task to coordinator...")
            response = client.post(COORDINATOR_URL, json=payload)
            response.raise_for_status()

            result = response.json()

            # Check for immediate errors
            if "error" in result:
                print("❌ Error: Pipeline execution failed.")
                print("Details:", result["error"])
                return

            # Get task_id from response (A2A returns it in result.id)
            task_id = result.get("result", {}).get("id") or result.get("task_id")
            if not task_id:
                print("❌ Error: No task_id received from coordinator.")
                print("Response:", json.dumps(result, indent=2))
                return

            print(f"✅ Task created successfully! Task ID: {task_id}")

            # 2. Poll for the result
            print(f"🔄 Polling for task completion (press Ctrl+C to stop)...")
            poll_for_result(client, task_id)

    except httpx.RequestError as e:
        print(f"❌ HTTP Error: Could not connect to the Coordinator Agent at {COORDINATOR_URL}.")
        print(f"   Please ensure the multi-agent system is running. You can start it with './run.sh'.")
        print(f"   Error details: {e}")
    except KeyboardInterrupt:
        print("\n⚠️  Polling stopped by user. Task may still be running on the server.")
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")


def poll_for_result(client: httpx.Client, task_id: str, poll_interval: int = 2):
    """
    Polls the coordinator for the status of a given task ID until it completes or fails.
    Uses A2A protocol tasks/get JSON-RPC method.
    """
    status = "in_progress"
    start_time = time.time()

    while status == "in_progress":
        time.sleep(poll_interval)

        try:
            # Use A2A protocol tasks/get method
            payload = {
                "jsonrpc": "2.0",
                "method": "tasks/get",
                "params": {"id": task_id},  # Parameter is 'id' not 'taskId'
                "id": "2"
            }

            response = client.post(COORDINATOR_URL, json=payload)
            response.raise_for_status()

            result = response.json()

            # Extract task status from A2A response
            task_data = result.get("result", {})
            task_status = task_data.get("status", {})
            status = task_status.get("state", "unknown")
            elapsed = int(time.time() - start_time)

            print(f"  [{elapsed}s] Task status: {status}")

            if status == "completed":
                print("\n✅ Pipeline completed successfully!")

                # Extract pipeline results from function_response in history
                history = task_data.get("history", [])
                pipeline_result = None

                for hist_item in reversed(history):
                    if hist_item.get("role") == "agent":
                        parts = hist_item.get("parts", [])
                        for part in parts:
                            if "data" in part:
                                data = part["data"]
                                metadata = part.get("metadata", {})
                                if metadata.get("adk_type") == "function_response":
                                    response_data = data.get("response", {})
                                    if "result" in response_data:
                                        pipeline_result = response_data["result"]
                                        break
                    if pipeline_result:
                        break

                if pipeline_result:
                    print("\n📊 Pipeline Results:")
                    print(f"   Announcements processed: {pipeline_result.get('announcements_processed', 0)}")

                    analyses = pipeline_result.get('analyses', [])
                    print(f"   Analyses generated: {len(analyses)}")

                    evaluations = pipeline_result.get('evaluations', [])
                    print(f"   Evaluations created: {len(evaluations)}")
                    if evaluations:
                        for i, ev in enumerate(evaluations, 1):
                            rec = ev.get('recommendation', 'N/A')
                            conf = ev.get('confidence_score', 0)
                            print(f"      {i}. Recommendation: {rec} (confidence: {conf:.2f})")

                    trading_signals = pipeline_result.get('trading_signals', [])
                    print(f"   Trading signals: {len(trading_signals)}")
                    if trading_signals:
                        for i, sig in enumerate(trading_signals, 1):
                            status_sig = sig.get('status', 'N/A')
                            ticket = sig.get('ticket_id', '')
                            print(f"      {i}. Status: {status_sig}")
                            if ticket:
                                print(f"         Ticket: {ticket}")
                                approval_url = sig.get('approval_url', '')
                                if approval_url:
                                    print(f"         🌐 Approval UI: {approval_url}")

                    errors = pipeline_result.get('errors', [])
                    if errors:
                        print(f"   ⚠️  Errors: {len(errors)}")
                        for err in errors:
                            print(f"      - {err}")

                    print("\n📄 Full results (JSON):")
                    print(json.dumps(pipeline_result, indent=2))
                else:
                    # Fallback: show last agent message
                    message = task_status.get("message", {})
                    parts = message.get("parts", [])
                    if parts and "text" in parts[0]:
                        print(f"\n📝 Agent response: {parts[0]['text']}")
                    else:
                        print("\n📊 Full task data:")
                        print(json.dumps(task_data, indent=2))
                break

            elif status == "failed":
                print("\n❌ Task failed!")
                error_message = task_status.get("message", {})
                print("Error details:", json.dumps(error_message, indent=2))
                break

            elif status not in ["in_progress", "pending"]:
                print(f"\n⚠️  Unknown status: {status}")
                print("Full response:", json.dumps(result, indent=2))
                break

        except httpx.HTTPStatusError as e:
            print(f"\n❌ HTTP error while polling: {e}")
            print(f"   Response: {e.response.text}")
            break
        except Exception as e:
            print(f"\n❌ Error while polling: {e}")
            import traceback
            traceback.print_exc()
            break


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Trigger ASX announcement processing pipeline for a specific company",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process BHP announcements (using default limit of 3)
  python scripts/trigger_pipeline.py --asx-code BHP

  # Process CBA announcements with custom limit
  python scripts/trigger_pipeline.py --asx-code CBA --limit 5

  # Include all announcements, not just price-sensitive
  python scripts/trigger_pipeline.py --asx-code RIO --no-price-sensitive
        """
    )

    parser.add_argument(
        "--asx-code",
        type=str,
        required=True,
        help="ASX ticker code (e.g., BHP, CBA, WBC)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of announcements to process (default: from config, typically 3)"
    )
    parser.add_argument(
        "--no-price-sensitive",
        action="store_true",
        help="Include all announcements, not just price-sensitive ones"
    )

    args = parser.parse_args()

    trigger_pipeline(
        asx_code=args.asx_code.upper(),
        limit=args.limit,
        price_sensitive_only=not args.no_price_sensitive
    )
