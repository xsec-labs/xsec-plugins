from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "src" / "jwt_analysis_mcp" / "__main__.py"


def build(output: Path) -> Path:
    output = output.resolve()
    if output.suffix not in ("", ".exe"):
        raise ValueError("output must be an extensionless executable or .exe")
    if (sys.platform == "win32") != (output.suffix == ".exe"):
        raise ValueError("choose an output extension matching the build host")
    output.parent.mkdir(parents=True, exist_ok=True)
    work = output.parent / ".pyinstaller-work"
    spec = output.parent / ".pyinstaller-spec"
    command = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "--onefile",
               "--console", "--name", output.stem, "--distpath", str(output.parent),
               "--workpath", str(work), "--specpath", str(spec), "--paths", str(ROOT / "src"),
               "--add-data", f"{ROOT / 'jwt_tool'}{os.pathsep}jwt_tool",
               "--collect-all", "Cryptodome", "--collect-all", "requests",
               "--collect-all", "urllib3", "--collect-all", "idna",
               "--collect-all", "certifi", "--collect-all", "charset_normalizer",
               "--collect-all", "ratelimit", "--collect-all", "termcolor",
               str(ENTRY)]
    subprocess.run(command, cwd=ROOT, check=True)
    built = output.parent / (output.stem + (".exe" if sys.platform == "win32" else ""))
    if built != output:
        shutil.move(built, output)
    for directory in (work, spec):
        shutil.rmtree(directory)
    output.chmod(0o755)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the JWT MCP Sidecar for the current OS/architecture")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(build(args.output))


if __name__ == "__main__":
    main()
