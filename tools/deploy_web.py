"""Publish the JavaScript web edition to GitHub Pages (the gh-pages branch).

    python tools/deploy_web.py            build the site into build/site and stop (a dry run)
    python tools/deploy_web.py --push     ...then replace the gh-pages branch with it

The site is a plain folder of static files: web/index.html, web/src, favicon and the built assets. Nothing runs on
a server. `--push` force-replaces gh-pages (it only ever holds a built site, never source), so it asks git for the
origin URL of this repo and pushes a fresh one-commit history there.
"""
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "build" / "site"


def rmtree(path):
    """Delete a folder, including git's read-only object files (Windows refuses them otherwise)."""
    def unlock(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, onexc=unlock)


def run(*cmd, cwd=ROOT):
    """Run a command (for example git) and return its output without the trailing newline; raises if it fails."""
    return subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()


def stamp_versions():
    """Add ?v=<hash of the code> to every script address in the built site.

    GitHub Pages lets browsers keep files for ten minutes, and some phones keep them longer, so after a deploy a phone
    could run a mix of old and new scripts. A new address for every changed build makes each deploy load as one piece.
    """
    files = sorted((SITE / "src").rglob("*.js"))
    version = hashlib.sha256(b"".join(f.read_bytes() for f in files)).hexdigest()[:10]
    # `from "./x.js"` and `import "./x.js"` become `from "./x.js?v=..."`.
    pattern = re.compile(r"""((?:from|import)\s*["'])(\.{1,2}/[^"']+?\.js)(["'])""")
    for f in files:
        text = f.read_text(encoding="utf-8")
        f.write_text(pattern.sub(lambda m: f"{m[1]}{m[2]}?v={version}{m[3]}", text), encoding="utf-8")
    index = SITE / "index.html"
    html = index.read_text(encoding="utf-8")
    index.write_text(html.replace('src="src/main.js"', f'src="src/main.js?v={version}"'), encoding="utf-8")
    print(f"stamped scripts with version {version}")


def build_site():
    """Rebuild the assets and copy everything the website needs into build/site."""
    # Always rebuild the assets first, so the site never ships stale files.
    subprocess.run([sys.executable, str(ROOT / "tools" / "build_web_js.py")], check=True, cwd=ROOT)
    if SITE.exists():
        rmtree(SITE)
    SITE.mkdir(parents=True)
    web = ROOT / "web"
    for name in ("index.html", "favicon.png"):
        shutil.copy2(web / name, SITE / name)
    shutil.copytree(web / "src", SITE / "src")
    shutil.copytree(web / "assets", SITE / "assets")
    stamp_versions()
    (SITE / ".nojekyll").write_text("")  # GitHub Pages: serve the files as they are
    total = sum(f.stat().st_size for f in SITE.rglob("*") if f.is_file())
    print(f"built {SITE} ({total / 1e6:.1f} MB)")


def push():
    """Publish build/site as a fresh one-commit gh-pages branch on the origin remote."""
    # The site folder gets its own throwaway git repo, so ask this repo where its origin remote points.
    url = run("git", "remote", "get-url", "origin")
    # Commit author, copied from your git settings (a brand-new repo has none of its own).
    who = ("-c", f"user.name={run('git', 'config', 'user.name')}", "-c", f"user.email={run('git', 'config', 'user.email')}")
    # Create a new repo in the site folder, commit everything, and force-push it as gh-pages.
    # Force is safe because that branch only ever holds built files, never source code.
    for cmd in (("git", "init", "-q", "-b", "gh-pages"), ("git", "add", "-A"),
                ("git", *who, "commit", "-q", "-m", "Publish the web edition"),
                ("git", "push", "--force", url, "gh-pages")):
        run(*cmd, cwd=SITE)
    # Remove the temporary repo so the next build starts clean.
    rmtree(SITE / ".git")
    print("pushed to gh-pages")


if __name__ == "__main__":
    build_site()
    # Without --push this is only a dry run, so it is safe to try.
    if "--push" in sys.argv:
        push()
    else:
        print("dry run: nothing pushed (add --push to publish)")
