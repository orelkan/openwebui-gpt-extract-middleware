"""Run the sample cases against the live API and report which replies pass.

Not a unit test: it needs OPENAI_API_KEY and spends credits. Run it with
`make samples` from the repository root.
"""

import argparse
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import load_settings
from app.prompt import inject_system_prompt, load_system_prompt
from prompt_eval.cases import CASES, SAMPLES_DIR, Case, check_case, count_shared

logger = logging.getLogger("prompt_eval")


def ask_model(
    client: httpx.Client,
    prompt: str,
    model_settings: dict[str, Any],
    messages: list[dict[str, Any]],
) -> tuple[str, int]:
    """Send a conversation with the system prompt injected. Return the reply and tokens used."""
    response = client.post(
        "/chat/completions",
        json={**model_settings, "messages": inject_system_prompt(messages, prompt)},
    )
    response.raise_for_status()
    body = response.json()
    return body["choices"][0]["message"]["content"], body["usage"]["total_tokens"]


def run_case(
    client: httpx.Client, prompt: str, model_settings: dict[str, Any], case: Case
) -> tuple[str, int]:
    """Play one case's conversation. Return the reply to check and the tokens used."""
    sample_text = (SAMPLES_DIR / case.sample).read_text(encoding="utf-8").strip()
    messages: list[dict[str, Any]] = [{"role": "user", "content": sample_text}]
    reply, tokens = ask_model(client, prompt, model_settings, messages)
    if case.follow_up is None:
        return reply, tokens

    messages.append({"role": "assistant", "content": reply})
    messages.append({"role": "user", "content": case.follow_up})
    follow_up_reply, follow_up_tokens = ask_model(client, prompt, model_settings, messages)
    return follow_up_reply, tokens + follow_up_tokens


def run_all_cases(
    client: httpx.Client,
    prompt: str,
    model_settings: dict[str, Any],
    cases: list[Case],
    runs: int,
    workers: int,
) -> list[list[tuple[str, int]]]:
    """Run every repeat of every case, several at a time.

    Almost all the time of a run is spent waiting for the API, so the requests
    are sent from a pool of threads. The result keeps the order of `cases`:
    entry i holds the (reply, tokens) of each repeat of cases[i].
    """
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            [executor.submit(run_case, client, prompt, model_settings, case) for _ in range(runs)]
            for case in cases
        ]
        return [[future.result() for future in case_futures] for case_futures in futures]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gpt-6-luna")
    parser.add_argument(
        "--reasoning-effort", help="sent as reasoning_effort; omitted when not given"
    )
    parser.add_argument(
        "--temperature", type=float, help="sent as temperature; omitted when not given"
    )
    parser.add_argument("--runs", type=int, default=3, help="repeats per case")
    parser.add_argument("--case", help="run only the case with this name")
    parser.add_argument("--workers", type=int, default=8, help="requests sent at the same time")
    parser.add_argument("--verbose", action="store_true", help="print every reply")
    return parser.parse_args()


def build_model_settings(arguments: argparse.Namespace) -> dict[str, Any]:
    """The model and the optional settings to send with every request.

    These are the settings a user would choose in Open WebUI; the middleware
    itself never sets them.
    """
    model_settings: dict[str, Any] = {"model": arguments.model}
    if arguments.reasoning_effort is not None:
        model_settings["reasoning_effort"] = arguments.reasoning_effort
    if arguments.temperature is not None:
        model_settings["temperature"] = arguments.temperature
    return model_settings


@dataclass(frozen=True)
class CaseSummary:
    """The numbers one case contributes to the totals."""

    passed_runs: int
    tokens: int
    shared_names: int = 0
    total_names: int = 0
    shared_values: int = 0
    total_values: int = 0


def report_case(case: Case, case_results: list[tuple[str, int]], verbose: bool) -> CaseSummary:
    """Check every repeat of one case, print its result line and return its numbers."""
    replies = [reply for reply, _ in case_results]
    tokens = sum(reply_tokens for _, reply_tokens in case_results)
    failures = []
    for run, reply in enumerate(replies, start=1):
        problems = check_case(case, reply)
        if problems:
            failures.append((run, problems))
        if verbose:
            logger.info("--- %s, run %d\n%s", case.name, run, reply)

    passed_runs = len(replies) - len(failures)
    summary = CaseSummary(passed_runs=passed_runs, tokens=tokens)
    consistency = ""
    if case.expects_extraction:
        shared_names, total_names = count_shared(replies, "name")
        shared_values, total_values = count_shared(replies, "value")
        summary = CaseSummary(
            passed_runs, tokens, shared_names, total_names, shared_values, total_values
        )
        consistency = (
            f"  in every repeat: {shared_names}/{total_names} names, "
            f"{shared_values}/{total_values} values"
        )

    verdict = "PASS" if not failures else "FAIL"
    logger.info("%s %d/%d  %-21s%s", verdict, passed_runs, len(replies), case.name, consistency)
    for run, problems in failures:
        for problem in problems:
            logger.info("       run %d: %s", run, problem)
    return summary


def main() -> int:
    """Run the selected cases and return the process exit code (0 when all passed)."""
    arguments = parse_arguments()
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    # httpx logs every request at INFO, which would drown the report.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    settings = load_settings()
    prompt = load_system_prompt(settings.system_prompt_path)
    model_settings = build_model_settings(arguments)
    cases = [case for case in CASES if arguments.case in (None, case.name)]

    started_at = time.perf_counter()
    with httpx.Client(
        base_url=settings.openai_base_url,
        headers={"Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}"},
        timeout=settings.upstream_read_timeout_seconds,
    ) as client:
        results = run_all_cases(
            client, prompt, model_settings, cases, arguments.runs, arguments.workers
        )
    elapsed_seconds = time.perf_counter() - started_at

    summaries = [
        report_case(case, case_results, arguments.verbose)
        for case, case_results in zip(cases, results, strict=True)
    ]

    passed_runs = sum(summary.passed_runs for summary in summaries)
    total_runs = len(cases) * arguments.runs
    logger.info("\n%d/%d runs passed", passed_runs, total_runs)
    logger.info(
        "in every repeat of their case: %d/%d field names, %d/%d values",
        sum(summary.shared_names for summary in summaries),
        sum(summary.total_names for summary in summaries),
        sum(summary.shared_values for summary in summaries),
        sum(summary.total_values for summary in summaries),
    )
    logger.info(
        "settings %s, %d tokens used, %.0f seconds",
        model_settings,
        sum(summary.tokens for summary in summaries),
        elapsed_seconds,
    )
    return 0 if passed_runs == total_runs else 1


if __name__ == "__main__":
    sys.exit(main())
