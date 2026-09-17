"""
J.A.R.V.I.S. Stark Engineering Lab ("Autonomous Code & Script Engine").

Provides on-demand autonomous scripting and execution:
1. Safe sandboxed script creation in data/scratchpad/.
2. Static syntax linting (py_compile for Python, bash -n for shell).
3. Sandboxed execution via SystemCommander with configurable timeouts.
4. Articulate J.A.R.V.I.S. debriefing of script execution output and metrics.
"""

import os
import re
import sys
import time
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))
from core.system_commander import get_system_commander

SCRATCHPAD_DIR = Path(__file__).parent.parent / "data" / "scratchpad"


class EngineeringLab:
    """
    On-demand engineering script authoring and execution engine for J.A.R.V.I.S.
    """

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or SCRATCHPAD_DIR
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.commander = get_system_commander()

    def _normalize_name(self, name: str, language: str) -> Tuple[str, str]:
        clean_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', name.lower().strip())
        lang = language.lower().strip()
        ext = ".py" if "py" in lang else ".sh"
        if not clean_name.endswith(ext):
            clean_name += ext
        return clean_name, ext

    def create_script(self, name: str, language: str, code: str) -> Dict[str, Any]:
        """
        Write custom script to scratchpad storage.
        """
        filename, ext = self._normalize_name(name, language)
        filepath = self.workspace_dir / filename

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(code.strip() + "\n")

            if ext == ".sh":
                os.chmod(filepath, 0o755)

            line_count = len(code.strip().splitlines())
            return {
                "success": True,
                "filename": filename,
                "filepath": str(filepath),
                "lines": line_count,
                "language": "python" if ext == ".py" else "bash"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def lint_script(self, filepath: str, language: str) -> Dict[str, Any]:
        """
        Statically lint the script for syntax errors before running.
        """
        if not os.path.exists(filepath):
            return {"valid": False, "error": f"Script not found at '{filepath}'"}

        lang = language.lower()
        if "py" in lang:
            proc = subprocess.run(
                [sys.executable, "-m", "py_compile", filepath],
                capture_output=True, text=True, timeout=5.0
            )
            if proc.returncode != 0:
                err = proc.stderr.strip() or "Syntax compilation error"
                return {"valid": False, "error": err}
        else:
            proc = subprocess.run(
                ["bash", "-n", filepath],
                capture_output=True, text=True, timeout=5.0
            )
            if proc.returncode != 0:
                err = proc.stderr.strip() or "Bash syntax error"
                return {"valid": False, "error": err}

        return {"valid": True, "error": ""}

    def execute_script(self, filepath: str, language: str, timeout: float = 30.0) -> Dict[str, Any]:
        """
        Execute the script safely using SystemCommander.
        """
        if not os.path.exists(filepath):
            return {"success": False, "error": "Script does not exist."}

        lang = language.lower()
        runner = sys.executable if "py" in lang else "bash"
        cmd = f"{runner} {filepath}"

        res = self.commander.execute(cmd, timeout=timeout)
        return res

    def run_task(self, name: str, language: str, code: str, timeout: float = 30.0) -> Dict[str, Any]:
        """
        Complete engineering workflow: create, lint, execute, and debrief.
        """
        # 1. Create
        c_res = self.create_script(name, language, code)
        if not c_res["success"]:
            return {
                "success": False,
                "debrief": f"Sir, failed to write script '{name}': {c_res.get('error')}"
            }

        filepath = c_res["filepath"]
        lang = c_res["language"]

        # 2. Lint
        l_res = self.lint_script(filepath, lang)
        if not l_res["valid"]:
            return {
                "success": False,
                "filepath": filepath,
                "debrief": f"Script '{c_res['filename']}' failed syntax verification, Sir: {l_res.get('error')[:200]}"
            }

        # 3. Execute
        e_res = self.execute_script(filepath, lang, timeout=timeout)
        stdout = e_res.get("stdout", "").strip()
        stderr = e_res.get("stderr", "").strip()
        exit_code = e_res.get("exit_code", 0)
        elapsed = e_res.get("elapsed_sec", 0.0)

        output_preview = stdout or stderr or "Execution completed with zero terminal output."
        lines_preview = output_preview.splitlines()
        first_line = lines_preview[0][:100] if lines_preview else ""

        if e_res["success"]:
            debrief = (
                f"Engineering script '{c_res['filename']}' executed successfully in {elapsed}s (exit {exit_code}), Sir. "
                f"Output: \"{first_line}\"."
            )
        else:
            debrief = (
                f"Script '{c_res['filename']}' encountered an exception (exit code {exit_code}) in {elapsed}s, Sir: "
                f"\"{first_line}\"."
            )

        return {
            "success": e_res["success"],
            "filename": c_res["filename"],
            "filepath": filepath,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "elapsed_sec": elapsed,
            "debrief": debrief
        }

    def list_scratchpad_scripts(self) -> List[Dict[str, Any]]:
        """
        List all scripts residing in the scratchpad workspace.
        """
        scripts = []
        if not self.workspace_dir.exists():
            return scripts

        for item in sorted(self.workspace_dir.glob("*.*")):
            if item.suffix in (".py", ".sh"):
                stat = item.stat()
                scripts.append({
                    "name": item.name,
                    "path": str(item),
                    "size_bytes": stat.st_size,
                    "modified_time": time.ctime(stat.st_mtime)
                })
        return scripts
