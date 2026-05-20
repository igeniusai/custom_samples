import os
import subprocess

from app.config import load_config

_process: subprocess.Popen | None = None


def start() -> dict:
    global _process

    if _process is not None and _process.poll() is None:
        return {"status": "already_running", "pid": _process.pid}

    config = load_config()

    env = {
        **os.environ,
        "DOMYN_API_KEY": config.domyn_api_key,
        "VLLM_API_KEY": config.vllm_api_key,
        "VLLM_BASE_URL": config.vllm_base_url,
        "VLLM_MODEL": config.vllm_model,
    }

    cmd = [
        "domyn", "expose", "agent_expose:graph",
        "--channel-id", config.channel_id,
        "--space-id", config.space_id,
        "--base-url", config.platform_base_url,
    ]

    workdir = os.environ.get("AGENT_WORKDIR", ".")
    _process = subprocess.Popen(cmd, env=env, cwd=workdir)
    return {"status": "started", "pid": _process.pid}


def stop() -> dict:
    global _process

    if _process is None or _process.poll() is not None:
        _process = None
        return {"status": "not_running"}

    _process.terminate()
    try:
        _process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        _process.kill()
        _process.wait()

    _process = None
    return {"status": "stopped"}


def status() -> dict:
    if _process is None:
        return {"status": "not_running"}
    poll = _process.poll()
    if poll is None:
        return {"status": "running", "pid": _process.pid}
    return {"status": "exited", "exit_code": poll}
