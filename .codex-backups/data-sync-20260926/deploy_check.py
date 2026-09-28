"""Check planned Compose drift without exposing environment values."""
import argparse
import json
import subprocess
import time

p = argparse.ArgumentParser()
p.add_argument("repo")
p.add_argument("container")
p.add_argument("--deploy", action="store_true")
p.add_argument("--in-place", action="store_true")
a = p.parse_args()


def output(command):
    return subprocess.check_output(command, text=True)


def inspect(target):
    return json.loads(output(["docker", "inspect", target]))[0]


before = inspect(a.container)
labels = before["Config"]["Labels"]
files = labels["com.docker.compose.project.config_files"].split(",")
service = labels["com.docker.compose.service"]
command = ["docker", "compose", "--project-directory", a.repo, "-p", labels["com.docker.compose.project"]]
for file in files:
    command += ["-f", file]
planned_command = command.copy()
if not a.deploy:
    planned_command[-1] = a.repo + "/.codex-backups/data-sync-20260926/compose.after.yml"
planned = json.loads(output(planned_command + ["config", "--format", "json"]))["services"][service]
image = inspect(planned["image"])
assert before["Image"] == image["Id"], "Planned image differs from running image"
image_env = dict(item.split("=", 1) for item in image["Config"]["Env"])
planned_env = image_env | {k: str(v) for k, v in planned.get("environment", {}).items()}
actual_env = dict(item.split("=", 1) for item in before["Config"]["Env"])
changed = sorted(k for k in planned_env.keys() | actual_env.keys() if planned_env.get(k) != actual_env.get(k))
allowed_drift = {"BULLPILOT_NOTIFY_TELEGRAM_BOT_TOKEN", "TBULL_OPS_BOT_TOKEN"} if a.in_place else set()
assert set(changed) <= allowed_drift, "Environment drift (names only): " + ", ".join(changed)
assert (planned["command"] if planned.get("command") is not None else image["Config"].get("Cmd")) == before["Config"].get("Cmd"), "Command drift"
assert (planned["entrypoint"] if planned.get("entrypoint") is not None else image["Config"].get("Entrypoint")) == before["Config"].get("Entrypoint"), "Entrypoint drift"
actual_mounts = {x["Destination"]: (x["Source"], not x["RW"]) for x in before["Mounts"]}
planned_mounts = {x["target"]: (x["source"], x.get("read_only", False)) for x in planned.get("volumes", [])}
target = "/app/bot/core/trifecta.py"
assert planned_mounts.pop(target) == (a.repo + "/bot/core/trifecta.py", True), "Missing read-only code mount"
assert actual_mounts == planned_mounts, "Unexpected mount drift"
print(json.dumps({"container": a.container, "preflight": "passed", "image_unchanged": True, "environment_unchanged": not changed, "preserving_running_environment": a.in_place, "existing_mounts_unchanged": True}), flush=True)
if a.deploy:
    if a.in_place:
        subprocess.run(["docker", "cp", a.repo + "/bot/core/trifecta.py", a.container + ":/app/bot/core/trifecta.py"], check=True)
        subprocess.run(["docker", "restart", a.container], check=True)
    else:
        subprocess.run(command + ["up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", service], check=True)
    after = inspect(a.container)
    assert dict(item.split("=", 1) for item in before["Config"]["Env"]) == dict(item.split("=", 1) for item in after["Config"]["Env"]), "Post-deploy environment drift"
    assert before["Image"] == after["Image"], "Post-deploy image drift"
    assert before["HostConfig"]["PortBindings"] == after["HostConfig"]["PortBindings"], "Port drift"
    assert set(before["NetworkSettings"]["Networks"]) == set(after["NetworkSettings"]["Networks"]), "Network drift"
    for attempt in range(18):
        after = inspect(a.container)
        health = after["State"].get("Health", {}).get("Status")
        if health == "healthy":
            print(json.dumps({"container": a.container, "health": health, "started": after["State"]["StartedAt"], "environment_unchanged": True}), flush=True)
            break
        time.sleep(5)
    else:
        raise RuntimeError("Container did not become healthy within 90 seconds")
