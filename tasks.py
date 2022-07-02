import shlex
import subprocess

from summon.tasks import task


@task
def run(command_args: list[str]) -> None:
    print(f"Running {shlex.join(command_args)}")
    subprocess.run(command_args)


@task
def run_task(task_number: int = 0) -> None:
    tasks = [
        "python -m tj_scraper webapp",
        "mypy tests --strict",
        "mypy tj_scraper --strict",
    ]
    run(shlex.split(tasks[task_number]))


@task
def strict_lint() -> None:
    run(["mypy", "tj_scraper", "--strict"])
    run(["mypy", "tests", "--strict"])


@task
def watch_task(task: str) -> None:
    watch(f"summon {task}")


@task
def watch(command: str) -> None:
    print(f"Watching command '{command}'")
    run(
        [
            "watchexec",
            "--exts=py,toml"
            "-r",
            "-c",
            "-s",
            "SIGKILL",
            "--",
            *shlex.split(command),
        ]
    )
