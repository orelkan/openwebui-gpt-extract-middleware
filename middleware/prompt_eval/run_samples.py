"""Run the sample cases against the live API and report which replies pass.

Not a unit test: it needs OPENAI_API_KEY and spends credits. Run it with
`make samples` from the repository root.
"""

import argparse
import logging
import sys
from typing import Any

import httpx

from app.config import Settings
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


def main() -> int:
    """Run the selected cases and return the process exit code (0 when all passed)."""
    arguments = parse_arguments()
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    # httpx logs every request at INFO, which would drown the report.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    settings = Settings()
    prompt = load_system_prompt(settings.system_prompt_path)
    model_settings = build_model_settings(arguments)
    cases = [case for case in CASES if arguments.case in (None, case.name)]
    passed_runs = 0
    total_tokens = 0
    # [shared, total], summed over all extraction cases.
    name_agreement = [0, 0]
    value_agreement = [0, 0]

    with httpx.Client(
        base_url=settings.openai_base_url,
        headers={"Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}"},
        timeout=settings.upstream_read_timeout_seconds,
    ) as client:
        for case in cases:
            replies = []
            failures = []
            for run in range(1, arguments.runs + 1):
                reply, tokens = run_case(client, prompt, model_settings, case)
                replies.append(reply)
                total_tokens += tokens
                problems = check_case(case, reply)
                if problems:
                    failures.append((run, problems))
                else:
                    passed_runs += 1
                if arguments.verbose:
                    logger.info("--- %s, run %d\n%s", case.name, run, reply)

            verdict = "PASS" if not failures else "FAIL"
            passed = arguments.runs - len(failures)
            consistency = ""
            if case.expects_extraction:
                shared_names, total_names = count_shared(replies, "name")
                shared_values, total_values = count_shared(replies, "value")
                name_agreement[0] += shared_names
                name_agreement[1] += total_names
                value_agreement[0] += shared_values
                value_agreement[1] += total_values
                consistency = (
                    f"  in every repeat: {shared_names}/{total_names} names, "
                    f"{shared_values}/{total_values} values"
                )
            logger.info(
                "%s %d/%d  %-21s%s", verdict, passed, arguments.runs, case.name, consistency
            )
            for run, problems in failures:
                for problem in problems:
                    logger.info("       run %d: %s", run, problem)

    total_runs = len(cases) * arguments.runs
    logger.info("\n%d/%d runs passed", passed_runs, total_runs)
    logger.info(
        "in every repeat of their case: %d/%d field names, %d/%d values",
        *name_agreement,
        *value_agreement,
    )
    logger.info("settings %s, %d tokens used", model_settings, total_tokens)
    return 0 if passed_runs == total_runs else 1


if __name__ == "__main__":
    sys.exit(main())
