"""Publish the JavaScript web edition to GitHub Pages (the gh-pages branch).

    python tools/deploy_web.py            build the site into build/site and stop (a dry run)
    python tools/deploy_web.py --push     ...then replace the gh-pages branch with it

The site is a plain folder of static files: web/index.html, web/src, favicon and the built assets. Nothing runs on
a server. `--push` force-replaces gh-pages (it only ever holds a built site, never source), so it asks git for the
origin URL of this repo and pushes a fresh one-commit history there.
"""
import os
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
    return subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()


def build_site():
    subprocess.run([sys.executable, str(ROOT / "tools" / "build_web_js.py")], check=True, cwd=ROOT)
    if SITE.exists():
        rmtree(SITE)
    SITE.mkdir(parents=True)
    web = ROOT / "web"
    for name in ("index.html", "favicon.png"):
        shutil.copy2(web / name, SITE / name)
    shutil.copytree(web / "src", SITE / "src")
    shutil.copytree(web / "assets", SITE / "assets")
    (SITE / ".nojekyll").write_text("")  # GitHub Pages: serve the files as they are
    total = sum(f.stat().st_size for f in SITE.rglob("*") if f.is_file())
    print(f"built {SITE} ({total / 1e6:.1f} MB)")


def push():
    url = run("git", "remote", "get-url", "origin")
    who = ("-c", f"user.name={run('git', 'config', 'user.name')}", "-c", f"user.email={run('git', 'config', 'user.email')}")
    for cmd in (("git", "init", "-q", "-b", "gh-pages"), ("git", "add", "-A"),
                ("git", *who, "commit", "-q", "-m", "Publish the web edition"),
                ("git", "push", "--force", url, "gh-pages")):
        run(*cmd, cwd=SITE)
    rmtree(SITE / ".git")
    print("pushed to gh-pages")


if __name__ == "__main__":
    build_site()
    if "--push" in sys.argv:
        push()
    else:
        print("dry run: nothing pushed (add --push to publish)")
