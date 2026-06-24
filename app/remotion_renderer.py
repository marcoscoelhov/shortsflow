from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from app.pipelines.common import FatalStepError
from app.utils import ensure_dir, path_from_uri, read_json


PREMIUM_COMPOSITION_ID = "YtsPremiumShort"


def _remotion_cli_bin(project_dir: Path) -> Path:
    base = project_dir / "node_modules" / ".bin" / "remotion"
    if sys.platform == "win32":
        windows_bin = base.with_suffix(".cmd")
        if windows_bin.exists():
            return windows_bin
    return base


class RemotionCliRenderer:
    def __init__(self, project_dir: Path | None = None, timeout_sec: int = 900, allowed_media_root: Path | None = None) -> None:
        self.project_dir = project_dir or Path(__file__).resolve().parent.parent / "remotion"
        self.timeout_sec = timeout_sec
        self.allowed_media_root = allowed_media_root.resolve() if allowed_media_root else None

    def preflight_environment(self) -> dict[str, object]:
        remotion_bin = _remotion_cli_bin(self.project_dir)
        entrypoint = self.project_dir / "src" / "index.ts"
        package_lock = self.project_dir / "package-lock.json"
        missing_items: list[str] = []
        if not self.project_dir.exists():
            missing_items.append("diretorio remotion/ ausente")
        if not remotion_bin.exists():
            missing_items.append("remotion/node_modules/.bin/remotion ausente; rode npm install em remotion/")
        if not entrypoint.exists():
            missing_items.append("remotion/src/index.ts ausente")
        if not package_lock.exists():
            missing_items.append("remotion/package-lock.json ausente")
        return {
            "backend": "remotion",
            "ready": not missing_items,
            "missing_items": missing_items,
            "project_dir": str(self.project_dir),
            "remotion_bin": str(remotion_bin),
            "entrypoint": str(entrypoint),
        }

    def assert_environment_ready(self) -> None:
        status = self.preflight_environment()
        missing_items = [str(item) for item in status["missing_items"]]
        if missing_items:
            raise FatalStepError("; ".join(missing_items))

    def render(self, *, plan_path: Path, output_path: Path, log_path: Path) -> list[str]:
        remotion_bin = _remotion_cli_bin(self.project_dir)
        entrypoint = self.project_dir / "src" / "index.ts"
        resolved_plan_path = plan_path.resolve()
        resolved_output_path = output_path.resolve()
        resolved_log_path = log_path.resolve()
        self.assert_environment_ready()
        command = [
            str(remotion_bin),
            "render",
            str(entrypoint),
            PREMIUM_COMPOSITION_ID,
            str(resolved_output_path),
            "--props",
            str(resolved_plan_path),
            "--codec",
            "h264",
            "--audio-codec",
            "aac",
            "--pixel-format",
            "yuv420p",
            "--crf",
            "20",
            "--x264-preset",
            "veryfast",
            "--overwrite",
            "--concurrency",
            "2",
            "--disable-web-security",
            "--log",
            "info",
        ]
        local_media_paths = self._preflight_local_media(resolved_plan_path)
        redaction_paths = [
            self.project_dir.resolve(),
            remotion_bin.resolve(),
            entrypoint.resolve(),
            resolved_plan_path,
            resolved_output_path,
            resolved_log_path,
            *local_media_paths,
        ]
        ensure_dir(resolved_output_path.parent)
        try:
            result = subprocess.run(
                command,
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_sec,
            )
        except subprocess.TimeoutExpired as exc:
            resolved_log_path.write_text(
                self._redacted_process_output(exc.stdout, exc.stderr, redaction_paths),
                encoding="utf-8",
            )
            raise FatalStepError("render premium excedeu o tempo limite") from exc
        resolved_log_path.write_text(
            self._redacted_process_output(result.stdout, result.stderr, redaction_paths),
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise FatalStepError("render premium falhou no Remotion CLI")
        return command

    def _preflight_local_media(self, plan_path: Path) -> list[Path]:
        try:
            plan = read_json(plan_path)
        except Exception as exc:  # noqa: BLE001
            raise FatalStepError("plano de acabamento Remotion invalido ou ilegivel") from exc
        if not isinstance(plan, dict):
            raise FatalStepError("plano de acabamento Remotion invalido")
        missing: list[str] = []
        local_media_paths: list[Path] = []
        for scene in plan.get("scenes") or []:
            if not isinstance(scene, dict):
                continue
            media_path = self._local_media_path(str(scene.get("asset_uri") or scene.get("asset_path") or ""))
            if media_path:
                local_media_paths.append(media_path.resolve())
                if not self._allowed_local_media_path(media_path):
                    missing.append(f"{media_path.name} fora da raiz permitida")
                    continue
                if not media_path.exists():
                    missing.append(media_path.name)
        audio = plan.get("audio") if isinstance(plan.get("audio"), dict) else {}
        media_path = self._local_media_path(str(audio.get("uri") or audio.get("path") or ""))
        if media_path:
            local_media_paths.append(media_path.resolve())
            if not self._allowed_local_media_path(media_path):
                missing.append(f"{media_path.name} fora da raiz permitida")
            elif not media_path.exists():
                missing.append(media_path.name)
        if missing:
            self._raise_missing(missing)
        return local_media_paths

    def _raise_missing(self, missing: list[str]) -> None:
        preview = ", ".join(missing[:4])
        suffix = f" e mais {len(missing) - 4}" if len(missing) > 4 else ""
        raise FatalStepError(f"assets locais do Remotion ausentes: {preview}{suffix}")

    def _allowed_local_media_path(self, path: Path) -> bool:
        if self.allowed_media_root is None:
            return True
        try:
            path.resolve().relative_to(self.allowed_media_root)
        except (OSError, ValueError):
            return False
        return True

    def _local_media_path(self, value: str) -> Path | None:
        if not value:
            return None
        if value.startswith("file://"):
            return path_from_uri(value)
        path = Path(value)
        return path if path.is_absolute() else None

    def _process_text(self, value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    def _redacted_process_output(self, stdout: str | bytes | None, stderr: str | bytes | None, paths: list[Path]) -> str:
        text = self._process_text(stdout) + "\n" + self._process_text(stderr)
        for path in sorted({item.resolve() for item in paths}, key=lambda item: len(str(item)), reverse=True):
            replacement = f"<{path.name or 'path'}>"
            raw = str(path)
            text = text.replace(raw, replacement)
            try:
                text = text.replace(path.as_uri(), replacement)
            except ValueError:
                pass
        return text
