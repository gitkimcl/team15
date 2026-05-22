"""Minimal example solver server.

This file shows the required HTTP endpoints and a very simple filtering
strategy. Replace the Solver logic with your own method.
"""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


def compute_feedback(secret, guess):
    """Return Wordle feedback as a string over 0, 1, 2."""
    feedback = [0] * 5
    secret_chars = list(secret)
    guess_chars = list(guess)

    for i in range(5):
        if guess_chars[i] == secret_chars[i]:
            feedback[i] = 2
            secret_chars[i] = None
            guess_chars[i] = None

    remaining = {}
    for ch in secret_chars:
        if ch is not None:
            remaining[ch] = remaining.get(ch, 0) + 1

    for i in range(5):
        ch = guess_chars[i]
        if ch is not None and remaining.get(ch, 0) > 0:
            feedback[i] = 1
            remaining[ch] -= 1

    return "".join(str(x) for x in feedback)


def parse_feedback(text):
    """Parse the deterministic rule-based feedback string from the grader."""
    if text is None:
        return None
    text = str(text).strip()

    lowered = text.lower()
    marks = []
    for sentence in lowered.split("\n"):
        sentence = sentence.strip()
        if not sentence:
            continue
        if "correct" in sentence:
            marks.append("2")
        elif "misplaced" in sentence:
            marks.append("1")
        elif "absent" in sentence:
            marks.append("0")
    return "".join(marks) if len(marks) == 5 else None


class Solver:
    """Stores per-problem state and chooses the next action."""

    def __init__(self):
        self.problems = {}

    def start_problem(self, data):
        """Initialize state for a new problem."""
        candidates = list(data["candidate_words"])
        self.problems[data["problem_id"]] = {
            "candidates": candidates,
            "possible": candidates[:],
            "guesses": [],
        }

    def act(self, data):
        """Update state from the latest feedback and return guess/submit."""
        state = self.problems[data["problem_id"]]
        if state["guesses"]:
            parsed = parse_feedback(data.get("feedback"))
            if parsed is not None:
                last_guess = state["guesses"][-1]
                state["possible"] = [
                    word
                    for word in state["possible"]
                    if compute_feedback(word, last_guess) == parsed
                ]

        if len(state["possible"]) == 1:
            return {"action": "submit", "word": state["possible"][0]}

        guess = state["possible"][0] if state["possible"] else state["candidates"][0]
        state["guesses"].append(guess)
        return {"action": "guess", "word": guess}


solver = Solver()


class Handler(BaseHTTPRequestHandler):
    """HTTP wrapper around the Solver object."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        data = json.loads(self.rfile.read(length))

        if self.path == "/start_problem":
            solver.start_problem(data)
            self._send_json({})
            return

        if self.path == "/act":
            self._send_json(solver.act(data))
            return

        self.send_response(404)
        self.end_headers()

    def _send_json(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def log_message(self, format, *args):
        return


def run():
    """Run the HTTP server on the port selected by the grader."""
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Starter solver running on port {port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
