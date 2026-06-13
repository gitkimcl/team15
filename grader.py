"""Local grader for the starter Wordle solver.

This script launches a solver server, sends problems through the project HTTP
protocol, and prints a JSON summary of the local run.
"""

import argparse
import hashlib
import json
import os
import random
import string
import subprocess
import sys
import time

import requests

WORD_LENGTH = 5
LETTERS = string.ascii_lowercase
DEFAULT_SOLVER_SCRIPT = os.path.join(os.path.dirname(__file__), "team15.py")
DEFAULT_PROBLEMS_PATH = os.path.join(os.path.dirname(__file__), "team15_problem_list.json")

max_time = 0

def compute_feedback(secret, guess):
    """Return Wordle feedback as a string over 0, 1, 2."""
    feedback = [0] * WORD_LENGTH
    secret_chars = list(secret)
    guess_chars = list(guess)

    for i in range(WORD_LENGTH):
        if guess_chars[i] == secret_chars[i]:
            feedback[i] = 2
            secret_chars[i] = None
            guess_chars[i] = None

    remaining = {}
    for ch in secret_chars:
        if ch is not None:
            remaining[ch] = remaining.get(ch, 0) + 1

    for i in range(WORD_LENGTH):
        ch = guess_chars[i]
        if ch is not None and remaining.get(ch, 0) > 0:
            feedback[i] = 1
            remaining[ch] -= 1

    return "".join(str(x) for x in feedback)


def perturb_secret(secret, rng, num_changes):
    """Change num_changes positions of the secret to different random letters."""
    chars = list(secret)
    for pos in rng.sample(range(WORD_LENGTH), num_changes):
        choices = [ch for ch in LETTERS if ch != chars[pos]]
        chars[pos] = rng.choice(choices)
    return "".join(chars)


def choose_noise_kind(rng, p, q):
    draw = rng.random()
    if draw < p:
        return 1
    if draw < p + q:
        return 2
    return 0


def choose_forced_noise_kind(rng, p, q):
    if p + q == 0.0:
        return 1
    return 1 if rng.random() < p / (p + q) else 2


def make_problem_rng(seed, problem_id):
    """Use one deterministic random stream per problem."""
    digest = hashlib.sha256(f"{seed}:{problem_id}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def is_valid_word(word):
    """Check the local problem-file word format."""
    return isinstance(word, str) and len(word) == WORD_LENGTH and word.isalpha() and word.islower()


def validate_problem(problem, idx):
    """Validate one problem object and raise a helpful error if it is invalid."""
    if not isinstance(problem, dict):
        raise ValueError(f"Problem {idx} must be a JSON object.")

    if "secret_word" not in problem:
        raise ValueError(f"Problem {idx} is missing 'secret_word'.")
    if "candidate_words" not in problem:
        raise ValueError(f"Problem {idx} is missing 'candidate_words'.")

    secret = problem["secret_word"]
    candidates = problem["candidate_words"]

    if not is_valid_word(secret):
        raise ValueError(f"Problem {idx} has invalid secret_word: {secret!r}.")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError(f"Problem {idx} candidate_words must be a non-empty list.")

    for word in candidates:
        if not is_valid_word(word):
            raise ValueError(f"Problem {idx} has invalid candidate word: {word!r}.")

    if secret not in candidates:
        raise ValueError(f"Problem {idx} secret_word must be included in candidate_words.")


def load_problems(path):
    """Load either one problem object or a list of problem objects."""
    with open(path) as f:
        data = json.load(f)

    problems = data if isinstance(data, list) else [data]
    normalized = []
    for idx, problem in enumerate(problems, start=1):
        validate_problem(problem, idx)
        item = dict(problem)
        item["problem_id"] = str(item.get("problem_id", idx))
        normalized.append(item)
    return normalized


def make_noise_events(seed, problem, max_turns, p, q, force_noise_turns):
    """Precompute noisy effective secrets for all turns of one problem."""
    rng = make_problem_rng(seed, problem["problem_id"])
    secret = problem["secret_word"]
    schedule = [choose_noise_kind(rng, p, q) for _ in range(max_turns)]
    if force_noise_turns > 0 and not any(schedule[:force_noise_turns]):
        schedule[rng.randrange(force_noise_turns)] = choose_forced_noise_kind(rng, p, q)

    events = []
    for kind in schedule:
        events.append(
            {
                "noise_kind": kind,
                "effective_secret": perturb_secret(secret, rng, kind) if kind else secret,
            }
        )
    return events


def rule_verbalize(guess, feedback):
    """Convert numeric feedback to the deterministic public feedback string."""
    names = ["first", "second", "third", "fourth", "fifth"]
    parts = []
    for name, ch, mark in zip(names, guess, feedback):
        if mark == "2":
            parts.append(f"The {name} letter '{ch}' is correct.")
        elif mark == "1":
            parts.append(f"The {name} letter '{ch}' is misplaced.")
        else:
            parts.append(f"The {name} letter '{ch}' is absent.")
    return "\n".join(parts)


def start_solver(script_path, port):
    """Start the submitted solver as a separate HTTP server process."""
    env = os.environ.copy()
    env["PORT"] = str(port)
    return subprocess.Popen(
        [sys.executable, os.path.basename(script_path)],
        cwd=os.path.dirname(os.path.abspath(script_path)),
        env=env,
    )


def post_json(url, payload, timeout):
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json() if response.content else {}


def result(problem, status, turns, score_turns, history, **extra):
    out = {
        "problem_id": problem["problem_id"],
        "secret": problem["secret_word"],
        "status": status,
        "turns": turns,
        "score_turns": score_turns,
        "history": history,
    }
    out.update(extra)
    print(f"{problem["problem_id"]} done")
    return out


def run_problem(base_url, problem, args):
    """Run one problem against a live solver server."""
    events = make_noise_events(
        args.seed,
        problem,
        args.max_turns,
        args.noise_probability,
        args.two_letter_noise_probability,
        args.force_noise_turns,
    )
    history = []
    feedback = None

    try:
        post_json(
            f"{base_url}/start_problem",
            {
                "problem_id": problem["problem_id"],
                "candidate_words": problem["candidate_words"],
                "noise_probability": args.noise_probability,
                "two_letter_noise_probability": args.two_letter_noise_probability,
                "force_noise_turns": args.force_noise_turns,
                "max_turns": args.max_turns,
                "guess_time_budget": args.guess_time_budget,
            },
            args.start_timeout,
        )
    except requests.RequestException as e:
        return result(problem, "timeout", args.max_turns, args.max_turns, history, error=str(e))

    guess_time_left = args.guess_time_budget
    for turn in range(1, args.max_turns + 1):
        if guess_time_left <= 0:
            return result(problem, "timeout", args.max_turns, args.max_turns, history)

        try:
            start = time.monotonic()
            reply = post_json(
                f"{base_url}/act",
                {
                    "problem_id": problem["problem_id"],
                    "turn": turn,
                    "feedback": feedback,
                },
                guess_time_left,
            )
            guess_time_left -= time.monotonic() - start
        except requests.RequestException as e:
            return result(problem, "timeout", args.max_turns, args.max_turns, history, error=str(e))

        action = reply.get("action")
        word = reply.get("word")
        if word not in problem["candidate_words"]:
            return result(problem, "invalid_word", turn, args.max_turns, history, bad_reply=reply)

        if action == "submit":
            if word == problem["secret_word"]:
                global max_time
                if args.guess_time_budget - guess_time_left > max_time:
                    max_time = args.guess_time_budget - guess_time_left
                return result(problem, "solved", turn, turn, history, submitted=word)
            return result(
                problem,
                "wrong_submit",
                turn,
                args.wrong_submit_penalty,
                history,
                submitted=word,
            )

        if action != "guess":
            return result(problem, "invalid_action", turn, args.max_turns, history, bad_reply=reply)

        event = events[turn - 1]
        feedback = compute_feedback(event["effective_secret"], word)
        formatted_feedback = rule_verbalize(word, feedback)
        history.append(
            {
                "turn": turn,
                "guess": word,
                "feedback": formatted_feedback,
            }
        )
        feedback = formatted_feedback

    return result(problem, "max_turns", args.max_turns, args.max_turns, history)


def run_suite(args):
    """Start a fresh solver process for each local problem."""
    problems = load_problems(args.problems_path)

    results = []
    for problem in problems[: args.num_problems]:
        proc = start_solver(args.solver_script, args.port)
        time.sleep(args.startup_delay)
        try:
            results.append(run_problem(f"http://localhost:{args.port}", problem, args))
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    return results


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver-script", default=DEFAULT_SOLVER_SCRIPT)
    parser.add_argument("--problems-path", default=DEFAULT_PROBLEMS_PATH)
    parser.add_argument("--num-problems", type=int, default=100)
    parser.add_argument("--noise-probability", type=float, default=0.66)
    parser.add_argument("--two-letter-noise-probability", type=float, default=0.33)
    parser.add_argument("--force-noise-turns", type=int, default=3)
    parser.add_argument("--max-turns", type=int, default=100)
    parser.add_argument("--wrong-submit-penalty", type=int, default=100)
    parser.add_argument("--start-timeout", type=float, default=5.0)
    parser.add_argument("--guess-time-budget", type=float, default=60.0)
    parser.add_argument("--startup-delay", type=float, default=5.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--port", type=int, default=18000)
    return parser


def main():
    args = build_parser().parse_args()
    if args.noise_probability + args.two_letter_noise_probability > 1.0:
        raise ValueError("Noise probabilities must sum to at most 1.")
    results = run_suite(args)
    solved = sum(1 for item in results if item["status"] == "solved")
    avg_score = sum(item["score_turns"] for item in results) / len(results)
    print(json.dumps({"solved": solved, "average_score_turns": avg_score, "results": results}, indent=2))
    print(solved)
    print(avg_score)
    print(max_time)


if __name__ == "__main__":
    main()
