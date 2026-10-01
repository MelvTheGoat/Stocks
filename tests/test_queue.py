"""The job queue the Kaggle notebook works through."""

import pytest
import yaml

from stockagent.config import RunConfig
from stockagent.runner.queue import Job, Queue, completed_from_results, load_queue


def write_queue(tmp_path, jobs) -> str:
    path = tmp_path / "queue.yaml"
    path.write_text(yaml.safe_dump({"jobs": jobs}))
    return str(path)


# --- the shipped queue ------------------------------------------------------


def test_the_shipped_queue_loads_and_is_consistent():
    queue = load_queue()
    assert queue.jobs
    queue.check()


def test_the_smoke_job_comes_first():
    # Everything after it assumes the pipeline works on the GPU at all.
    assert load_queue().names()[0] == "smoke"


def test_every_job_names_a_config_that_loads():
    for job in load_queue().jobs:
        config = RunConfig.from_yaml(job.config)
        assert config.name == job.name, f"{job.config} is named {config.name}"


def test_every_job_has_a_distinct_fingerprint():
    # Two jobs with the same fingerprint are the same run, and comparing them
    # would measure nothing.
    fingerprints = [RunConfig.from_yaml(job.config).fingerprint() for job in load_queue().jobs]
    assert len(fingerprints) == len(set(fingerprints))


def test_the_queue_covers_both_baselines_and_the_agent():
    kinds = {RunConfig.from_yaml(job.config).agent.kind for job in load_queue().jobs}
    assert {"closed_book", "retrieval", "agent"} <= kinds


def test_budgets_fit_inside_a_kaggle_session():
    # Kaggle stops a session at about twelve hours.
    for job in load_queue().jobs:
        assert 0 < job.budget_minutes <= 11 * 60, job.name


# --- choosing the next job --------------------------------------------------


def test_the_first_unfinished_job_is_chosen():
    queue = Queue([Job("a", "c1"), Job("b", "c2")])
    assert queue.next_job([]).name == "a"
    assert queue.next_job(["a"]).name == "b"


def test_nothing_left_returns_none():
    queue = Queue([Job("a", "c1")])
    assert queue.next_job(["a"]) is None


def test_a_prerequisite_being_done_unblocks_the_job():
    queue = Queue([Job("a", "c1"), Job("b", "c2", after=("a",))])
    assert queue.next_job(["a"]).name == "b"


def test_a_job_waiting_on_another_is_skipped_rather_than_blocking_the_queue():
    # Blocking the whole queue on ordering would waste a week of GPU time, so a
    # job whose prerequisite is unfinished is passed over and the next one runs.
    queue = Queue([Job("a", "c1"), Job("b", "c2", after=("a",)), Job("c", "c3")])
    assert queue.next_job(["a", "b"]).name == "c"
    assert queue.next_job(["c"]).name == "a"


def test_what_a_job_is_waiting_for_is_reported():
    queue = Queue([Job("a", "c1"), Job("b", "c2", after=("a",))])
    assert queue.blocked([]) == [("b", ["a"])]


def test_the_status_lines_distinguish_done_pending_and_waiting():
    queue = Queue([Job("a", "c1"), Job("b", "c2"), Job("c", "c3", after=("b",))])
    text = queue.status(["a"])

    assert "[   done] a" in text
    assert "[pending] b" in text
    assert "[waiting] c" in text


# --- integrity --------------------------------------------------------------


def test_duplicate_job_names_are_refused(tmp_path):
    path = write_queue(tmp_path, [{"name": "a", "config": "c"}, {"name": "a", "config": "c"}])
    with pytest.raises(ValueError, match="duplicate job names"):
        load_queue(path)


def test_waiting_on_a_job_that_does_not_exist_is_refused(tmp_path):
    # It would stall for ever with no explanation.
    path = write_queue(tmp_path, [{"name": "a", "config": "c", "after": ["ghost"]}])
    with pytest.raises(ValueError, match="not in the queue"):
        load_queue(path)


def test_waiting_on_a_later_job_is_refused(tmp_path):
    path = write_queue(
        tmp_path,
        [{"name": "a", "config": "c", "after": ["b"]}, {"name": "b", "config": "c"}],
    )
    with pytest.raises(ValueError, match="comes after it"):
        load_queue(path)


def test_an_empty_queue_file_loads_as_empty(tmp_path):
    path = tmp_path / "queue.yaml"
    path.write_text("")
    assert load_queue(path).jobs == []


# --- what counts as finished ------------------------------------------------


def test_a_results_filename_identifies_its_job():
    # The job name is taken from the file that exists, so the queue cannot claim
    # a job is done when there is nothing to show for it.
    found = completed_from_results(
        [
            "agent-dev-3588f0ba1195-results.json",
            "smoke-c58ff3478429-results.json",
            "results/agent-dev/agent-dev-3588f0ba1195-traces.jsonl",
        ]
    )
    assert found == {"agent-dev", "smoke"}


def test_files_that_are_not_results_are_ignored():
    assert completed_from_results(["agent-dev-calls.jsonl", "notes.md"]) == set()


def test_nothing_on_the_branch_means_nothing_is_finished():
    assert completed_from_results([]) == set()
