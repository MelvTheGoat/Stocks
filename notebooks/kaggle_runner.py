"""Paste this into one Kaggle cell. Click Save & Run All. It does the rest.

Each time it runs it:

  1. clones the repository (public, so no token is needed to read it)
  2. installs dependencies and starts vLLM
  3. reads runs/queue.yaml and picks the first job with no results yet
  4. fetches the market database from Hugging Face, or collects it if there is none
  5. runs the job, stopping cleanly before Kaggle's limit
  6. pushes results and traces to the "results" branch
  7. uploads the response cache and the database to Hugging Face

Set these in Kaggle's Add-ons -> Secrets, then enable each one for this notebook:

  GH_TOKEN            a GitHub token with permission to push to this repository
  HF_TOKEN            a Hugging Face token with write access
  HF_REPO             your private dataset, as "username/stock-agent-data"
  TWELVEDATA_API_KEY  only needed the first time, to collect the database
  SEC_EMAIL           your contact address, which the SEC requires

Notebook settings: Accelerator GPU T4 x2, Internet on.

A note on the vLLM version. T4 is a Turing card with no bfloat16, and vLLM's
support for it has moved between releases. VLLM_VERSION below is a starting
point, not a verified fact: the smoke job's job is partly to establish what
actually works here. The script prints the detected compute capability and the
installed version so a failure is diagnosable rather than mysterious.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# --- settings ---------------------------------------------------------------

REPO = "https://github.com/MelvTheGoat/Stocks.git"
BRANCH = "main"
RESULTS_BRANCH = "results"
WORK = Path("/kaggle/working/Stocks")

# Starting point, to be confirmed by the first smoke run. See the note above.
VLLM_VERSION = "0.7.3"

# Leave this much of the session spare, so results get pushed rather than the
# session being killed mid-write.
RESERVE_MINUTES = 25

STARTED = time.monotonic()


def say(message: str) -> None:
    elapsed = (time.monotonic() - STARTED) / 60
    print(f"[{elapsed:6.1f}m] {message}", flush=True)


def run(command, *, cwd=None, check=True, quiet=False):
    say(f"$ {' '.join(str(part) for part in command)}")
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=quiet,
        text=True,
    )
    if check and result.returncode != 0:
        if quiet:
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
        raise SystemExit(f"command failed with {result.returncode}")
    return result


def secret(name: str, *, required: bool = True) -> str:
    """Read a Kaggle secret, or fall back to an environment variable."""
    try:
        from kaggle_secrets import UserSecretsClient

        value = UserSecretsClient().get_secret(name)
    except Exception:
        value = os.environ.get(name, "")
    value = (value or "").strip()
    if required and not value:
        raise SystemExit(f"the secret {name} is not set, or not enabled for this notebook")
    return value


# --- 1. the repository ------------------------------------------------------

GH_TOKEN = secret("GH_TOKEN")
HF_TOKEN = secret("HF_TOKEN")
HF_REPO = secret("HF_REPO")

if WORK.exists():
    shutil.rmtree(WORK)
run(["git", "clone", "--depth", "50", "--branch", BRANCH, REPO, str(WORK)])
run(["git", "config", "user.name", "kaggle-runner"], cwd=WORK)
run(["git", "config", "user.email", "runner@example.invalid"], cwd=WORK)

sys.path.insert(0, str(WORK / "src"))

# --- 2. dependencies --------------------------------------------------------

run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"], cwd=WORK)
run([sys.executable, "-m", "pip", "install", "-q", "huggingface_hub"], cwd=WORK)
run([sys.executable, "-m", "pip", "install", "-q", f"vllm=={VLLM_VERSION}"], cwd=WORK, check=False)

try:
    import torch

    capability = torch.cuda.get_device_capability() if torch.cuda.is_available() else None
    say(f"gpu: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none'}")
    say(f"compute capability: {capability}  (T4 is (7, 5); no bfloat16 below (8, 0))")
except Exception as error:  # noqa: BLE001
    say(f"could not inspect the GPU: {error}")

# --- 3. which job to run ----------------------------------------------------

from stockagent.config import RunConfig  # noqa: E402
from stockagent.runner import completed_from_results, load_queue  # noqa: E402

OUT = WORK / "runs" / "output"
OUT.mkdir(parents=True, exist_ok=True)

# The results branch holds what has already been produced. Fetched into a
# worktree so the main checkout stays clean.
RESULTS_DIR = Path("/kaggle/working/results")
if RESULTS_DIR.exists():
    shutil.rmtree(RESULTS_DIR)

fetched = run(
    ["git", "fetch", "origin", f"{RESULTS_BRANCH}:{RESULTS_BRANCH}"],
    cwd=WORK,
    check=False,
    quiet=True,
)
if fetched.returncode == 0:
    run(["git", "worktree", "add", str(RESULTS_DIR), RESULTS_BRANCH], cwd=WORK)
    existing = [p.name for p in RESULTS_DIR.rglob("*-results.json")]
else:
    say(f"no {RESULTS_BRANCH} branch yet; this is the first run")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    existing = []

queue = load_queue(WORK / "runs" / "queue.yaml")
completed = completed_from_results(existing)
say(queue.status(completed))

job = queue.next_job(completed)
if job is None:
    for name, missing in queue.blocked(completed):
        say(f"{name} is still waiting for {', '.join(missing)}")
    say("nothing left to run. Add a job to runs/queue.yaml and merge it.")
    raise SystemExit(0)

say(f"running {job.name}: {job.note.strip()}")
config = RunConfig.from_yaml(WORK / job.config)

# --- 4. the data ------------------------------------------------------------

from huggingface_hub import HfApi, snapshot_download, upload_folder  # noqa: E402

DATABASE = WORK / "data" / "db"
CACHE = WORK / ".cache" / "responses"
api = HfApi(token=HF_TOKEN)

# The database cannot live in the repository: Twelve Data licenses it for
# internal use and not for redistribution. A private Hugging Face dataset is
# where it belongs.
try:
    api.create_repo(HF_REPO, repo_type="dataset", private=True, exist_ok=True)
    say(f"hugging face dataset ready: {HF_REPO} (private)")
except Exception as error:  # noqa: BLE001
    say(f"could not prepare the dataset: {error}")

try:
    snapshot_download(
        repo_id=HF_REPO,
        repo_type="dataset",
        local_dir=str(WORK / "data" / "hf"),
        token=HF_TOKEN,
    )
    for name in ("db", "responses"):
        source = WORK / "data" / "hf" / name
        if source.exists():
            target = DATABASE if name == "db" else CACHE
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source, target)
            say(f"restored {name} from hugging face")
except Exception as error:  # noqa: BLE001
    say(f"nothing to restore yet: {error}")

if not (DATABASE / "bars.parquet").exists():
    say("no database found, collecting it. This takes about twenty minutes.")
    environment = {
        **os.environ,
        "TWELVEDATA_API_KEY": secret("TWELVEDATA_API_KEY"),
        "SEC_EMAIL": secret("SEC_EMAIL", required=False),
        "PYTHONPATH": str(WORK / "src"),
    }
    subprocess.run(
        [sys.executable, "scripts/collect_us.py", "--start", "2019-01-01"],
        cwd=WORK,
        env=environment,
        check=False,
    )
    subprocess.run([sys.executable, "scripts/write_coverage.py"], cwd=WORK, check=False)

# --- 5. vLLM --------------------------------------------------------------

server = None
if config.agent.kind or True:  # every job needs the model
    command = [
        sys.executable,
        "-m",
        "vllm.entrypoints.openai.api_server",
        "--model",
        config.model.hf_repo or config.model.name,
        "--served-model-name",
        config.model.name,
        "--dtype",
        config.model.dtype,
        "--max-model-len",
        str(config.model.max_model_len),
        "--gpu-memory-utilization",
        str(config.model.gpu_memory_utilization),
        "--port",
        "8000",
    ]
    if config.model.quantization != "none":
        command += ["--quantization", config.model.quantization]

    say("starting vLLM. Loading weights takes several minutes.")
    log = open(OUT / f"{job.name}-vllm.log", "w")
    server = subprocess.Popen(command, cwd=WORK, stdout=log, stderr=subprocess.STDOUT)

    from stockagent.llm.openai_client import OpenAICompatibleClient  # noqa: E402

    probe = OpenAICompatibleClient(base_url=config.model.endpoint, timeout_s=10.0)
    deadline = time.monotonic() + 20 * 60
    while time.monotonic() < deadline:
        if server.poll() is not None:
            print((OUT / f"{job.name}-vllm.log").read_text()[-4000:])
            raise SystemExit("vLLM exited before it was ready; the log is above")
        if probe.is_ready():
            say("vLLM is ready")
            break
        time.sleep(10)
    else:
        raise SystemExit("vLLM did not become ready within twenty minutes")

# --- 6. run the job ---------------------------------------------------------

budget = min(job.budget_minutes, max(5, 11 * 60 - RESERVE_MINUTES))
say(f"running with a budget of {budget} minutes")

environment = {**os.environ, "PYTHONPATH": str(WORK / "src")}
completed_run = subprocess.run(
    [sys.executable, "scripts/run_eval.py", "--config", job.config, "--out", str(OUT)],
    cwd=WORK,
    env=environment,
    timeout=budget * 60,
    check=False,
)
say(f"run_eval exited with {completed_run.returncode}")

if server is not None:
    server.terminate()
    try:
        server.wait(timeout=60)
    except subprocess.TimeoutExpired:
        server.kill()

# --- 7. push the results ----------------------------------------------------

# Results and traces are derived figures and logs, not vendor data, so they can
# be published. The database and the response cache cannot, and go to Hugging
# Face instead.
produced = sorted(OUT.glob(f"{job.name}-*"))
say(f"{len(produced)} files to publish")

if produced:
    target = RESULTS_DIR / job.name
    target.mkdir(parents=True, exist_ok=True)
    for path in produced:
        shutil.copy2(path, target / path.name)

    authenticated = REPO.replace("https://", f"https://x-access-token:{GH_TOKEN}@")
    if (RESULTS_DIR / ".git").exists() or list(RESULTS_DIR.iterdir()):
        run(["git", "add", "-A"], cwd=RESULTS_DIR, check=False)
        run(
            ["git", "-c", "user.name=kaggle-runner",
             "-c", "user.email=runner@example.invalid",
             "commit", "-m", f"Results for {job.name}"],
            cwd=RESULTS_DIR,
            check=False,
        )
        for attempt in range(4):
            pushed = run(
                ["git", "push", authenticated, f"HEAD:{RESULTS_BRANCH}"],
                cwd=RESULTS_DIR,
                check=False,
                quiet=True,
            )
            if pushed.returncode == 0:
                say(f"pushed results to the {RESULTS_BRANCH} branch")
                break
            say(f"push failed, retrying in {2 ** (attempt + 1)}s")
            time.sleep(2 ** (attempt + 1))
        else:
            say("could not push results. They are in runs/output in this notebook's output.")

# --- 8. keep the cache and the database -------------------------------------

staging = Path("/kaggle/working/hf-upload")
if staging.exists():
    shutil.rmtree(staging)
staging.mkdir(parents=True)
for name, source in (("db", DATABASE), ("responses", CACHE)):
    if source.exists():
        shutil.copytree(source, staging / name)

if any(staging.iterdir()):
    try:
        upload_folder(
            repo_id=HF_REPO,
            repo_type="dataset",
            folder_path=str(staging),
            token=HF_TOKEN,
            commit_message=f"after {job.name}",
        )
        say("uploaded the database and response cache to hugging face")
    except Exception as error:  # noqa: BLE001
        say(f"the upload failed: {error}")

# --- 9. what happened -------------------------------------------------------

results_file = next(iter(OUT.glob(f"{job.name}-*-results.json")), None)
if results_file:
    payload = json.loads(results_file.read_text())
    accuracy = payload["accuracy"]
    say(
        f"{job.name}: {accuracy['point']:.1%} "
        f"({accuracy['low']:.1%}-{accuracy['high']:.1%}) over {payload['total']} questions"
    )
    say(f"tokens per question: {payload['tokens_per_question']}")
    say(f"latency: {payload['latency']}")
    say(f"how runs ended: {payload['stops']}")
else:
    say("no results file was produced. Check the output above and the vLLM log.")

say("done. Click Save & Run All again for the next job.")
