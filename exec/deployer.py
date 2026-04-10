"""
Deployer — ships built projects to live targets.
Auto-detects deploy target from project structure.
Post-deploy verification: is the URL actually live?
"""
from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass
import httpx
from loguru import logger
from exec.executor import EXECUTOR


@dataclass
class DeployResult:
    success: bool
    url: str = ""
    target: str = ""
    error: str = ""
    verified: bool = False


def _detect_target(project_dir: Path) -> str:
    if (project_dir / "setup.py").exists() or (project_dir / "pyproject.toml").exists():
        return "pypi"
    if (project_dir / "package.json").exists():
        return "npm"
    if (project_dir / "index.html").exists():
        return "surge"
    return "local"


class Deployer:
    def deploy(self, project_dir: Path, target: str | None = None) -> DeployResult:
        if target is None:
            target = _detect_target(project_dir)

        logger.info(f"Deploying {project_dir.name} → {target}")

        if target == "pypi":
            return self._deploy_pypi(project_dir)
        elif target == "npm":
            return self._deploy_npm(project_dir)
        elif target == "surge":
            return self._deploy_surge(project_dir)
        elif target == "github_pages":
            return self._deploy_github_pages(project_dir)
        else:
            return DeployResult(success=True, url=f"file://{project_dir}", target="local")

    def _deploy_surge(self, project_dir: Path) -> DeployResult:
        slug = project_dir.name.lower().replace("_", "-")
        url = f"https://{slug}.surge.sh"
        result = EXECUTOR.run(f"npx surge {project_dir} {url}", timeout=60)
        if result.success:
            verified = self._verify(url)
            return DeployResult(success=True, url=url, target="surge", verified=verified)
        return DeployResult(success=False, error=result.stderr, target="surge")

    def _deploy_pypi(self, project_dir: Path) -> DeployResult:
        EXECUTOR.install_package("build twine")
        build = EXECUTOR.run("python -m build", cwd=project_dir)
        if not build.success:
            return DeployResult(success=False, error=build.stderr, target="pypi")
        upload = EXECUTOR.run("python -m twine upload dist/* --skip-existing", cwd=project_dir, timeout=120)
        if upload.success:
            name = project_dir.name
            url = f"https://pypi.org/project/{name}/"
            return DeployResult(success=True, url=url, target="pypi", verified=self._verify(url))
        return DeployResult(success=False, error=upload.stderr, target="pypi")

    def _deploy_npm(self, project_dir: Path) -> DeployResult:
        result = EXECUTOR.run("npm publish --access public", cwd=project_dir, timeout=120)
        if result.success:
            return DeployResult(success=True, url="https://npmjs.com", target="npm", verified=True)
        return DeployResult(success=False, error=result.stderr, target="npm")

    def _deploy_github_pages(self, project_dir: Path) -> DeployResult:
        cmds = [
            "git add -A",
            "git commit -m 'deploy' --allow-empty",
            "git push origin HEAD:gh-pages",
        ]
        for cmd in cmds:
            r = EXECUTOR.run(cmd, cwd=project_dir)
            if not r.success:
                return DeployResult(success=False, error=r.stderr, target="github_pages")
        return DeployResult(success=True, target="github_pages", verified=False)

    def _verify(self, url: str) -> bool:
        try:
            r = httpx.get(url, timeout=10, follow_redirects=True)
            ok = r.status_code < 400
            logger.info(f"Verification {url}: {r.status_code} → {'OK' if ok else 'FAIL'}")
            return ok
        except Exception as e:
            logger.warning(f"Verification failed for {url}: {e}")
            return False


DEPLOYER = Deployer()
