"""Which job to run next.

The notebook is clicked once and has to decide for itself what to do. The queue
is an ordered list of jobs in the repository; a job is finished when its results
file exists on the results branch. Nothing writes state back to the main branch,
which matters because the main branch is merged by a human and a runner pushing
to it would race with that.

Deciding "finished" from the presence of a results file rather than from a status
field has a useful property: it is impossible for the queue to claim a job is
done when there is no result to show for it. The two cannot drift apart, because
there is only one of them.

A job also carries a time budget. Kaggle kills a session at its limit, and an
eval that cannot finish inside one session has to stop cleanly and leave its
traces behind rather than being killed mid-write.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import yaml

QUEUE_PATH = Path("runs/queue.yaml")


@dataclass(frozen=True)
class Job:
    name: str
    config: str
    # Why this job exists, for whoever reads the queue later.
    note: str = ""
    # Minutes to allow. The notebook stops cleanly before this and leaves the
    # rest for the next session, which is what makes a long eval possible at all.
    budget_minutes: int = 240
    # Jobs that must have finished first, by name. Used so a comparison is not
    # run before both of its arms exist.
    after: tuple[str, ...] = ()

    def results_name(self, fingerprint: str) -> str:
        return f"{self.name}-{fingerprint}-results.json"


@dataclass
class Queue:
    jobs: list[Job] = field(default_factory=list)

    def names(self) -> list[str]:
        return [job.name for job in self.jobs]

    def next_job(self, completed: Iterable[str]) -> Job | None:
        """The first job that has not finished and whose prerequisites have.

        Returns None when there is nothing to do, which the notebook reports and
        exits on rather than treating as an error.
        """
        done = set(completed)
        for job in self.jobs:
            if job.name in done:
                continue
            if any(prerequisite not in done for prerequisite in job.after):
                # Skipped rather than failed: the prerequisite may be the next
                # session's work, and blocking the whole queue on ordering would
                # waste a week of GPU time.
                continue
            return job
        return None

    def blocked(self, completed: Iterable[str]) -> list[tuple[str, list[str]]]:
        """Jobs waiting on something, and what they are waiting for."""
        done = set(completed)
        waiting = []
        for job in self.jobs:
            if job.name in done:
                continue
            missing = [p for p in job.after if p not in done]
            if missing:
                waiting.append((job.name, missing))
        return waiting

    def status(self, completed: Iterable[str]) -> str:
        done = set(completed)
        lines = [f"{len(self.jobs)} jobs, {len(done & set(self.names()))} finished:"]
        for job in self.jobs:
            if job.name in done:
                mark = "done"
            elif any(p not in done for p in job.after):
                mark = "waiting"
            else:
                mark = "pending"
            lines.append(f"  [{mark:>7}] {job.name}  ({job.config})")
        return "\n".join(lines)

    def check(self) -> None:
        """Fail on a queue that cannot be worked through."""
        names = self.names()
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate job names: {duplicates}")

        known = set(names)
        for job in self.jobs:
            unknown = [p for p in job.after if p not in known]
            if unknown:
                # A dependency on a job that does not exist would stall for ever
                # with no explanation.
                raise ValueError(f"{job.name} waits for jobs that are not in the queue: {unknown}")

        # A job depending on something later in the list would also stall.
        position = {name: index for index, name in enumerate(names)}
        for job in self.jobs:
            for prerequisite in job.after:
                if position[prerequisite] > position[job.name]:
                    raise ValueError(
                        f"{job.name} waits for {prerequisite}, which comes after it in the queue"
                    )


def load_queue(path: str | Path = QUEUE_PATH) -> Queue:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    jobs = [
        Job(
            name=row["name"],
            config=row["config"],
            note=row.get("note", ""),
            budget_minutes=row.get("budget_minutes", 240),
            after=tuple(row.get("after", ())),
        )
        for row in raw.get("jobs", [])
    ]
    queue = Queue(jobs=jobs)
    queue.check()
    return queue


def completed_from_results(paths: Sequence[str | Path]) -> set[str]:
    """Job names inferred from result filenames on the results branch.

    A file is named `<job>-<fingerprint>-results.json`, so the job name is
    everything before the fingerprint. Taking the name from the filename means a
    result that exists cannot be overlooked and a job cannot be marked done
    without one.
    """
    found = set()
    for path in paths:
        stem = Path(path).name
        if not stem.endswith("-results.json"):
            continue
        body = stem[: -len("-results.json")]
        # Strip the trailing fingerprint, which is the last hyphenated part.
        parts = body.rsplit("-", 1)
        found.add(parts[0] if len(parts) == 2 and parts[1] else body)
    return found
