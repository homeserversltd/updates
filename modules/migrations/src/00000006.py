#!/usr/bin/env python3
"""Migration 00000006: CRA to Vite frontend build (field retrofit)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from migrations_common import log, require_root

MIGRATION_ID = "00000006"
WEBROOT = Path("/var/www/homeserver")
PACKAGE_JSON = WEBROOT / "package.json"
VITE_CONFIG = WEBROOT / "vite.config.ts"
INDEX_HTML = WEBROOT / "public/index.html"

VITE_CONFIG_BODY = """import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  root: 'public',
  plugins: [react()],
  build: {
    outDir: 'build',
  },
  define: {
    'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV || 'production'),
  },
});
"""


def _strip_cra_deps(pkg: dict) -> None:
    deps = pkg.get("dependencies")
    if isinstance(deps, dict):
        for k in (
            "react-scripts",
        ):
            deps.pop(k, None)
    dev = pkg.get("devDependencies")
    if isinstance(dev, dict):
        for k in (
            "@testing-library/react",
            "@testing-library/jest-dom",
            "@testing-library/user-event",
            "eslint-config-react-app",
            "@babel/plugin-proposal-private-property-in-object",
        ):
            dev.pop(k, None)


def _ensure_vite_deps(pkg: dict) -> None:
    deps = pkg.setdefault("dependencies", {})
    if not isinstance(deps, dict):
        return
    if "vite" not in deps:
        deps["vite"] = "^5.0.0"
    if "@vitejs/plugin-react" not in deps:
        deps["@vitejs/plugin-react"] = "^4.0.0"
    if "fast-deep-equal" not in deps:
        deps["fast-deep-equal"] = "^3.1.3"


def main() -> int:
    require_root()
    log(MIGRATION_ID, "CRA to Vite Frontend Build")

    if not PACKAGE_JSON.is_file():
        log(MIGRATION_ID, "HOMESERVER frontend not installed; nothing to do")
        return 0

    raw = PACKAGE_JSON.read_text(encoding="utf-8")
    if VITE_CONFIG.is_file() and '"react-scripts"' not in raw:
        log(MIGRATION_ID, "Already on Vite; nothing to do")
        return 0

    backup_dir = Path(f"/var/log/homeserver/migration-00000006-{int(time.time())}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PACKAGE_JSON, backup_dir / "package.json")
    if INDEX_HTML.is_file():
        shutil.copy2(INDEX_HTML, backup_dir / "public_index.html")
    if VITE_CONFIG.is_file():
        shutil.copy2(VITE_CONFIG, backup_dir / "vite.config.ts")

    pkg = json.loads(raw)
    _strip_cra_deps(pkg)
    scripts = pkg.setdefault("scripts", {})
    if isinstance(scripts, dict):
        if scripts.get("start") == "react-scripts start":
            del scripts["start"]
            scripts["dev"] = "vite"
        if scripts.get("build") == "react-scripts build":
            scripts["build"] = (
                "vite build && (if [ -f premium/utils/post_build_tab_restore.py ]; then "
                'python3 premium/utils/post_build_tab_restore.py; else echo '
                '"[post-build-tabs] premium utils not present, skipping"; fi)'
            )
        if scripts.get("test") == "react-scripts test":
            scripts["test"] = 'echo "Vite-based tests not yet configured"'
        scripts.pop("eject", None)

    _ensure_vite_deps(pkg)
    PACKAGE_JSON.write_text(json.dumps(pkg, indent=4) + "\n", encoding="utf-8")

    VITE_CONFIG.write_text(VITE_CONFIG_BODY, encoding="utf-8")

    if INDEX_HTML.is_file():
        html = INDEX_HTML.read_text(encoding="utf-8")
        if not re.search(r'type="module".*src=.*index\.tsx', html):
            html = re.sub(
                r'<script defer="defer" src="/static/js/main[^"]*\.js"></script>\s*',
                "",
                html,
            )
            if '<div id="root"></div>' in html and 'src="/src/index.tsx"' not in html:
                html = html.replace(
                    '<div id="root"></div>',
                    '<div id="root"></div>\n    <script type="module" src="/src/index.tsx"></script>',
                    1,
                )
            elif "</body>" in html and 'src="/src/index.tsx"' not in html:
                html = re.sub(
                    r"(</body>)",
                    r'    <script type="module" src="/src/index.tsx"></script>\n\1',
                    html,
                    count=1,
                )
            INDEX_HTML.write_text(html, encoding="utf-8")

    env = os.environ.copy()
    env["PWD"] = str(WEBROOT)
    r = subprocess.run(
        ["npm", "install", "--no-audit", "--no-fund"],
        cwd=str(WEBROOT),
        env=env,
    )
    if r.returncode != 0:
        log(MIGRATION_ID, "npm install failed", level="ERROR")
        return 1

    r = subprocess.run(["npm", "run", "build"], cwd=str(WEBROOT), env=env)
    if r.returncode != 0:
        log(MIGRATION_ID, "npm run build failed", level="ERROR")
        return 1

    ls = subprocess.run(
        ["systemctl", "list-unit-files", "--type=service", "--no-pager"],
        capture_output=True,
        text=True,
        check=False,
    )
    if ls.stdout and "gunicorn" in ls.stdout:
        subprocess.run(["systemctl", "restart", "gunicorn.service"], check=False)

    log(MIGRATION_ID, f"SUCCESS: CRA→Vite complete; backup at {backup_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
