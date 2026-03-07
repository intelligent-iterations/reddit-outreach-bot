"""
Per-run data logging for debugging and auditing.

Each bot run gets a timestamped folder under run-data/ containing:
- meta.json: run configuration and timing
- raw_leads_{strategy}.json: all scraped leads before triage
- triage_{strategy}.json: Grok's full response + parsed decisions
- actions.json: actual actions taken and their results
- errors.json: any errors during the run
"""

import json
import os
from datetime import datetime


class RunLogger:
    def __init__(self, base_dir: str):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.run_dir = os.path.join(base_dir, "run-data", timestamp)
        os.makedirs(self.run_dir, exist_ok=True)
        self._actions = []
        self._errors = []
        self._meta = {
            "run_id": timestamp,
            "started_at": datetime.now().isoformat(),
        }

    def save_meta(self, accounts: list[str], strategies: list[str], dry_run: bool):
        self._meta.update({
            "accounts": accounts,
            "strategies_run": strategies,
            "dry_run": dry_run,
        })
        self._write("meta.json", self._meta)

    def save_raw_leads(self, leads: list[dict], strategy: str):
        filename = f"raw_leads_{strategy}.json"
        self._write(filename, {
            "strategy": strategy,
            "count": len(leads),
            "leads": leads,
        })

    def save_triage_result(self, triage_result, strategy: str):
        filename = f"triage_{strategy}.json"
        data = triage_result.to_dict()
        data["strategy"] = strategy
        self._write(filename, data)

    def save_discovery_result(self, discovery_result, strategy: str):
        """Save discovery phase results separately for easy debugging."""
        if discovery_result is None:
            return
        filename = f"discovery_{strategy}.json"
        data = discovery_result.to_dict()
        data["strategy"] = strategy
        self._write(filename, data)

    def log_action(
        self,
        username: str,
        action_type: str,
        result: str,
        template_name: str,
        filled_message: str,
        permalink: str = "",
        strategy: str = "",
    ):
        self._actions.append({
            "username": username,
            "action_type": action_type,
            "result": result,
            "template_name": template_name,
            "filled_message": filled_message,
            "permalink": permalink,
            "strategy": strategy,
            "timestamp": datetime.now().isoformat(),
        })

    def log_error(self, context: str, error: str):
        self._errors.append({
            "context": context,
            "error": error,
            "timestamp": datetime.now().isoformat(),
        })

    def finalize(self):
        self._meta["completed_at"] = datetime.now().isoformat()
        self._meta["total_actions"] = len(self._actions)
        self._meta["total_errors"] = len(self._errors)
        self._write("meta.json", self._meta)

        if self._actions:
            self._write("actions.json", self._actions)
        if self._errors:
            self._write("errors.json", self._errors)

    def _write(self, filename: str, data):
        path = os.path.join(self.run_dir, filename)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @property
    def run_dir_path(self) -> str:
        return self.run_dir
