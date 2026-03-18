"""CLI for agent-orchestrator."""
import sys, json, argparse
from .core import AgentOrchestrator

def main():
    parser = argparse.ArgumentParser(description="Multi-agent orchestration framework for coordinating AI agents on complex tasks")
    parser.add_argument("command", nargs="?", default="status", choices=["status", "run", "info"])
    parser.add_argument("--input", "-i", default="")
    args = parser.parse_args()
    instance = AgentOrchestrator()
    if args.command == "status":
        print(json.dumps(instance.get_stats(), indent=2))
    elif args.command == "run":
        print(json.dumps(instance.process(input=args.input or "test"), indent=2, default=str))
    elif args.command == "info":
        print(f"agent-orchestrator v0.1.0 — Multi-agent orchestration framework for coordinating AI agents on complex tasks")

if __name__ == "__main__":
    main()
