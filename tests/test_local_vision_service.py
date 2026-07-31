from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_local_vision_service_is_tuned_for_two_cpu_cores() -> None:
    service = (ROOT / "deploy/systemd/shortsflow-vision.service.in").read_text(encoding="utf-8")

    assert "Qwen3-VL-2B-Instruct-Q4_K_M.gguf" in service
    assert "--ctx-size 2048" in service
    assert "--image-min-tokens 512" in service
    assert "--image-max-tokens 512" in service
    assert "--flash-attn on" in service
    assert "--parallel 1" in service
    assert "--cache-ram 0" in service


def test_local_vision_installer_enables_native_cpu_build() -> None:
    installer = (ROOT / "scripts/install_local_vision_service.sh").read_text(encoding="utf-8")

    assert "-DGGML_NATIVE=ON" in installer
    assert "Qwen/Qwen3-VL-2B-Instruct-GGUF" in installer
