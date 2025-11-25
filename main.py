#!/usr/bin/env python3
"""
Main entry point for ASX Announcement Scraper A2A System.
Starts all agents as separate processes using Google ADK.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

from utils.logging import get_logger
from utils.config import get_settings

logger = get_logger()
settings = get_settings()


# Agent module paths
AGENT_MODULES = {
    "coordinator": "agents.coordinator.main",
    "scraper": "agents.scraper.main",
    "analyzer": "agents.analyzer.main",
    "stock": "agents.stock.main",
    "memory": "agents.memory.main",
    "evaluation": "agents.evaluation.main",
    "trading": "agents.trading.main",  # Now A2A service!
}

AGENT_PORTS = {
    "coordinator": settings.coordinator_agent_port,
    "scraper": settings.scraper_agent_port,
    "analyzer": settings.analyzer_agent_port,
    "stock": settings.stock_agent_port,
    "memory": settings.memory_agent_port,
    "evaluation": settings.evaluation_agent_port,
    "trading": settings.trading_agent_port,
}


def run_agent_process(agent_name: str, module_path: str):
    """
    Run a single agent as a subprocess.

    Args:
        agent_name: Name of the agent
        module_path: Python module path (e.g., "agents.scraper_agent")

    Returns:
        subprocess.Popen object
    """
    logger.info(f"Starting {agent_name}...")

    # Run as Python module
    process = subprocess.Popen(
        [sys.executable, "-m", module_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    return process


def start_all_agents():
    """Start all ADK agents as separate processes."""
    processes = []

    logger.info("="*60)
    logger.info("Starting ASX Announcement Scraper A2A System (Google ADK)")
    logger.info("="*60)

    try:
        # Start each agent in a separate process
        for agent_name, module_path in AGENT_MODULES.items():
            process = run_agent_process(agent_name, module_path)
            processes.append((process, agent_name))
            logger.info(f"✓ Started {agent_name} (PID: {process.pid})")
            time.sleep(0.5)  # Stagger starts

        logger.info("="*60)
        logger.info("All agents started successfully!")
        logger.info("="*60)
        logger.info("\nAgent URLs:")
        for agent_name, port in AGENT_PORTS.items():
            logger.info(f"  {agent_name:12s} http://localhost:{port}")

        logger.info("\n✨ All agents using Google ADK + A2A SDK")
        logger.info("✨ Agent cards: http://localhost:<port>/.well-known/agent-card.json")
        logger.info("\nPress Ctrl+C to stop all agents...")

        # Monitor processes
        while True:
            time.sleep(1)
            # Check if any process died
            for process, agent_name in processes:
                if process.poll() is not None:
                    logger.error(f"❌ {agent_name} process died unexpectedly!")
                    # Read any error output
                    output = process.stdout.read() if process.stdout else ""
                    if output:
                        logger.error(f"Output: {output}")

    except KeyboardInterrupt:
        logger.info("\n\nShutting down all agents...")
        for process, agent_name in processes:
            process.terminate()
            logger.info(f"  Stopped {agent_name}")

        # Wait for all to terminate
        for process, agent_name in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning(f"  Force killing {agent_name}")
                process.kill()

        logger.info("All agents stopped.")

    except Exception as e:
        logger.error(f"Error running agents: {e}")
        # Cleanup
        for process, _ in processes:
            if process.poll() is None:
                process.terminate()
        raise


def start_single_agent(agent_name: str):
    """
    Start a single ADK agent.

    Args:
        agent_name: Name of agent to start
    """
    module_path = AGENT_MODULES.get(agent_name.lower())
    if not module_path:
        logger.error(f"Unknown agent: {agent_name}")
        logger.info(f"Available agents: {', '.join(AGENT_MODULES.keys())}")
        return

    port = AGENT_PORTS.get(agent_name.lower())
    logger.info(f"Starting {agent_name} agent on port {port}...")
    logger.info(f"URL: http://localhost:{port}")
    logger.info(f"Agent card: http://localhost:{port}/.well-known/agent-card.json")

    # Run the agent module directly
    try:
        subprocess.run([sys.executable, "-m", module_path], check=True)
    except KeyboardInterrupt:
        logger.info(f"\n{agent_name} stopped by user")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running {agent_name}: {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="ASX Announcement Scraper A2A System (Google ADK)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start all agents
  python main.py --all

  # Start specific agent
  python main.py --agent coordinator
  python main.py --agent scraper

  # List available agents
  python main.py --list
        """
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Start all agents (default)"
    )
    parser.add_argument(
        "--agent",
        type=str,
        help="Start specific agent (coordinator, scraper, analyzer, stock, memory, evaluation, trading)"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available agents"
    )

    args = parser.parse_args()

    if args.list:
        print("Available A2A agents (Google ADK + A2A SDK):")
        print(f"  ✅ coordinator  (Port {settings.coordinator_agent_port}) - Main orchestrator (root agent)")
        print(f"  ✅ scraper      (Port {settings.scraper_agent_port}) - ASX scraping with Playwright")
        print(f"  ✅ analyzer     (Port {settings.analyzer_agent_port}) - PDF processing and analysis")
        print(f"  ✅ stock        (Port {settings.stock_agent_port}) - Market data fetching")
        print(f"  ⚠️  memory       (Port {settings.memory_agent_port}) - Memory management (DISABLED in pipeline)")
        print(f"  ✅ evaluation   (Port {settings.evaluation_agent_port}) - Quality assessment + recommendations")
        print(f"  ✅ trading      (Port {settings.trading_agent_port}) - Trading with (HTIL)")
        print("\nCurrent Pipeline Flow:")
        print("  Scraper → Analyzer → Stock → Evaluation → Trading (via A2A)")
        print("  (Memory agent skipped in current pipeline)")
        print("\nArchitecture Notes:")
        print("  ✨ Coordinator = ROOT AGENT (has access to user for human approval)")
        print("  ✨ Trading = REMOTE A2A AGENT")
        print("  ✨ When BUY signal detected:")
        print("     1. Coordinator delegates to Trading Agent via A2A")
        print("     2. Trading Agent returns 'pending' status")
        print("     3. Coordinator surfaces approval request to user")
        print("     4. User approves/rejects via Coordinator")
        print("     5. Trading Agent executes paper trade if approved")
        return

    if args.agent:
        # Start single agent
        start_single_agent(args.agent)
    else:
        # Start all agents (default)
        start_all_agents()


if __name__ == "__main__":
    main()
