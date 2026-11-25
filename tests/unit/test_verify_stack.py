"""The parts of `scripts/verify_stack.py` that need no running stack (S2.1-S2.4 support).

The scenarios themselves (a real private stack up, health, down, dev stack untouched) need
Docker and take half a minute; they are run by the verifier's QA procedure. What is checked
here is what decides whether the private stack can ever collide with the dev one: names, ports,
and what happens to a dev `.env`.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import scripts.verify_stack as vs

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_names_and_ports_are_derived_from_the_run_id_and_base_port():
    env = vs.stack_env("abc", 18100)
    assert env == {
        "INFLUX_PORT": "18100",
        "POSTGRES_PORT": "18101",
        "INFLUX_CONTAINER_NAME": "dac-verify-abc-influxdb",
        "POSTGRES_CONTAINER_NAME": "dac-verify-abc-postgres",
        "GRAFANA_PORT": "18102",
        "GRAFANA_CONTAINER_NAME": "dac-verify-abc-grafana",
        "RENDERER_CONTAINER_NAME": "dac-verify-abc-renderer",
    }
    assert vs.project_name("abc") == "dac-verify-abc"


def test_no_private_name_or_port_equals_a_dev_one():
    env = vs.stack_env("local", vs.DEFAULT_PORT_BASE)
    assert env["INFLUX_CONTAINER_NAME"] not in {"dac-influxdb", "dac-postgres"}
    assert env["POSTGRES_CONTAINER_NAME"] not in {"dac-influxdb", "dac-postgres"}
    assert int(env["INFLUX_PORT"]) not in {8181, 5432, 3000}
    assert int(env["POSTGRES_PORT"]) not in {8181, 5432, 3000}
    assert int(env["GRAFANA_PORT"]) not in {8181, 5432, 3000}
    assert env["GRAFANA_CONTAINER_NAME"] not in {"dac-grafana", "dac-renderer"}
    assert env["RENDERER_CONTAINER_NAME"] not in {"dac-grafana", "dac-renderer"}


@pytest.mark.parametrize("bad", ["", "ABC def", "-x", "a/b", "x" * 60, "a;b"])
def test_an_unusable_run_id_is_refused(monkeypatch, bad):
    monkeypatch.setenv("FLOW_RUN_ID", bad)
    if bad == "":
        monkeypatch.delenv("FLOW_RUN_ID")
        assert vs.run_id() == vs.DEFAULT_RUN_ID
        return
    with pytest.raises(vs.StackError):
        vs.run_id()


@pytest.mark.parametrize("bad", ["abc", "80", "70000"])
def test_an_unusable_port_base_is_refused(monkeypatch, bad):
    monkeypatch.setenv("FLOW_PORT_BASE", bad)
    with pytest.raises(vs.StackError):
        vs.port_base()


@pytest.fixture
def env_files(tmp_path, monkeypatch):
    monkeypatch.setattr(vs, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(vs, "ENV_BACKUP_PATH", tmp_path / ".env.pre-verify")
    return tmp_path


def test_a_dev_env_is_backed_up_not_overwritten_and_restored_on_down(env_files):
    (env_files / ".env").write_text("INFLUX_TOKEN=dev-secret\nINFLUX_PORT=8181\n", encoding="utf-8")
    vs.write_private_env("abc", 18100)
    private = (env_files / ".env").read_text(encoding="utf-8")
    assert private.startswith(vs.ENV_MARKER_PREFIX + "abc")
    assert "INFLUX_HOST=http://localhost:18100" in private
    assert "POSTGRES_PORT=18101" in private
    assert "dev-secret" not in private
    assert (
        (env_files / ".env.pre-verify").read_text(encoding="utf-8").startswith("INFLUX_TOKEN=dev")
    )

    vs.restore_env()
    assert (env_files / ".env").read_text(encoding="utf-8").startswith("INFLUX_TOKEN=dev-secret")
    assert not (env_files / ".env.pre-verify").exists()


def test_a_second_up_for_the_same_run_keeps_its_token_and_a_new_run_does_not(env_files):
    vs.write_private_env("abc", 18100)
    text = (
        (env_files / ".env")
        .read_text(encoding="utf-8")
        .replace("INFLUX_TOKEN=", "INFLUX_TOKEN=minted-token")
    )
    (env_files / ".env").write_text(text, encoding="utf-8")

    vs.write_private_env("abc", 18100)
    assert "INFLUX_TOKEN=minted-token" in (env_files / ".env").read_text(encoding="utf-8")

    vs.write_private_env("other", 18200)
    assert "minted-token" not in (env_files / ".env").read_text(encoding="utf-8")


def test_a_generated_env_is_never_taken_for_a_dev_one(env_files):
    vs.write_private_env("abc", 18100)
    vs.write_private_env("def", 18200)
    assert not (env_files / ".env.pre-verify").exists()
    vs.restore_env()
    assert not (env_files / ".env").exists()  # nothing to give back: the file was ours


def test_plain_compose_keeps_the_dev_container_names():  # S2.4, second half
    env = {k: v for k, v in os.environ.items() if not k.endswith("_CONTAINER_NAME")}
    result = subprocess.run(  # noqa: S603
        ["docker", "compose", "config"],  # noqa: S607
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "container_name: dac-influxdb" in result.stdout
    assert "container_name: dac-postgres" in result.stdout
    assert "container_name: dac-grafana" in result.stdout


def test_compose_takes_the_private_names_when_asked():
    env = {**os.environ, **vs.stack_env("abc", 18100)}
    result = subprocess.run(  # noqa: S603
        ["docker", "compose", "-p", "dac-verify-abc", "config"],  # noqa: S607
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "container_name: dac-verify-abc-influxdb" in result.stdout
    assert "container_name: dac-verify-abc-postgres" in result.stdout
    assert 'published: "18100"' in result.stdout
    assert 'published: "18101"' in result.stdout
    assert "container_name: dac-verify-abc-grafana" in result.stdout
    assert 'published: "18102"' in result.stdout


# ---------------------------------------------------------------- Grafana (M6: S6.1 to S6.3)


def test_the_grafana_port_is_the_base_plus_two_for_any_base():
    for base in (18100, 20000, 40000):
        assert vs.stack_env("abc", base)["GRAFANA_PORT"] == str(base + 2)


def test_the_private_env_points_the_clients_at_the_private_grafana(env_files):
    vs.write_private_env("abc", 18100)
    text = (env_files / ".env").read_text(encoding="utf-8")
    assert "GRAFANA_PORT=18102" in text
    assert "GRAFANA_URL=http://localhost:18102" in text
    assert "GRAFANA_ADMIN_USER=admin" in text
    assert "GRAFANA_ADMIN_PASSWORD=" in text
    assert "GRAFANA_URL=http://localhost:3000" not in text


class Recorder:
    """Replaces the steps of `cmd_up` and records what ran, in order."""

    def __init__(self, monkeypatch, env_files):
        self.steps: list[str] = []
        monkeypatch.setenv("FLOW_RUN_ID", "abc")
        monkeypatch.setenv("FLOW_PORT_BASE", "18100")
        monkeypatch.setattr(vs, "compose", self.compose)
        monkeypatch.setattr(vs, "run_step", lambda label, cmd, env: self.steps.append(label))
        monkeypatch.setattr(vs, "wait_for_grafana", lambda base: self.steps.append(f"wait {base}"))
        real_write = vs.write_private_env
        monkeypatch.setattr(
            vs,
            "write_private_env",
            lambda rid, base: (self.steps.append("write .env"), real_write(rid, base)),
        )

    def compose(self, rid, *args, env=None, timeout=None):
        self.steps.append("compose " + " ".join(args))
        self.last_env = env

        class Result:
            returncode = 0
            stdout = stderr = ""

        return Result()


def test_up_starts_the_stores_first_and_grafana_last_after_the_token_exists(monkeypatch, env_files):
    recorder = Recorder(monkeypatch, env_files)
    assert vs.cmd_up() == 0
    steps = recorder.steps
    assert steps[0].startswith("compose up -d --wait") and steps[0].endswith("influxdb postgres")
    assert "grafana" not in steps[0]
    assert steps[1:7] == [
        "write .env",
        "bootstrap admin token",
        "postgres migrations",
        "create influx databases",
        "load experiments",
        "compose up -d --wait --wait-timeout 240 grafana",
    ]
    assert steps[-1] == "wait 18100"
    assert recorder.last_env["GRAFANA_PORT"] == "18102"


def test_a_second_up_runs_the_same_steps_and_never_recreates_grafana(monkeypatch, env_files):
    recorder = Recorder(monkeypatch, env_files)
    vs.cmd_up()
    first = list(recorder.steps)
    recorder.steps.clear()
    vs.cmd_up()
    assert recorder.steps == first
    assert not any("recreate" in step or "--build" in step for step in first)


def test_health_is_unhealthy_when_grafana_is(monkeypatch, capsys):
    monkeypatch.setenv("FLOW_RUN_ID", "abc")
    monkeypatch.setattr(vs, "container_running", lambda name: True)
    monkeypatch.setattr(vs, "influx_healthy", lambda base: True)
    monkeypatch.setattr(vs, "postgres_ready", lambda name: True)
    monkeypatch.setattr(vs, "grafana_problems", lambda base: [])
    assert vs.cmd_health() == 0
    monkeypatch.setattr(vs, "grafana_problems", lambda base: ["datasource influx-dac reports X"])
    assert vs.cmd_health() == 1
    assert "influx-dac" in capsys.readouterr().err


def test_health_names_a_grafana_container_that_is_not_running(monkeypatch, capsys):
    monkeypatch.setenv("FLOW_RUN_ID", "abc")
    monkeypatch.setattr(vs, "container_running", lambda name: not name.endswith("-grafana"))
    assert vs.cmd_health() == 1
    assert "dac-verify-abc-grafana is not running" in capsys.readouterr().err


def test_grafana_problems_reports_an_unreachable_server_without_raising():
    # nothing listens on base + 2 = 3
    problems = vs.grafana_problems(1)
    assert len(problems) == 1 and "did not answer" in problems[0]


def test_down_removes_volumes_and_the_render_profile(monkeypatch, env_files):
    recorder = Recorder(monkeypatch, env_files)
    assert vs.cmd_down() == 0
    assert recorder.steps == ["compose --profile render down --volumes --remove-orphans"]
