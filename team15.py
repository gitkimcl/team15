"""Minimal example solver server.

This file shows the required HTTP endpoints and a very simple filtering
strategy. Replace the Solver logic with your own method.
"""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np

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

def calc_noise_0(word, guess, parsed):
    return 1 if compute_feedback(word, guess) == parsed else 0

def calc_noise_1(word, guess, parsed):
    wordl = list(word)
    ccnt = 0
    char_in_guess = set(guess)
    for i in range(5):
        collision = False
        for e in char_in_guess:
            if e == word[i]:
                collision = True
                continue
            wordl[i] = e
            if compute_feedback("".join(wordl), guess) == parsed: ccnt += 1
        wordl[i] = '~'
        if compute_feedback("".join(wordl), guess) == parsed:
            ccnt += 25 - len(char_in_guess)
            if collision: ccnt += 1
        wordl[i] = word[i]
    return ccnt / (5*25)

def calc_noise_2(word, guess, parsed):
    wordl = list(word)
    ccnt = 0
    char_in_guess = set(guess)
    for i in range(5):
        for j in range(i+1, 5):
            collision = 0
            for e in char_in_guess:
                for ee in char_in_guess:
                    if e == word[i] or ee == word[j]:
                        collision += 1
                        continue
                    wordl[i] = e
                    wordl[j] = ee
                    if (compute_feedback("".join(wordl), guess)) == parsed: ccnt += 1
            wordl[i] = wordl[j] = '~'
            if compute_feedback("".join(wordl), guess) == parsed:
                ccnt += (25 - len(char_in_guess)) * (25 - len(char_in_guess))
                ccnt += collision
            wordl[i] = word[i]
            wordl[j] = word[j]
    return ccnt / (10*25*25)

def calc_probability(noise, word, guess, parsed):
    return noise[0] * calc_noise_0(word, guess, parsed) + \
        noise[1] * calc_noise_1(word, guess, parsed) + \
        noise[2] * calc_noise_2(word, guess, parsed)


def special_turn_1(state, last_guess, parsed):
    print("guess #1")
    p_noise_0 = [
        calc_noise_0(state["candidates"][i], last_guess, parsed) if state["probability"][i] != 0 else 0
        for i in range(len(state["candidates"]))
    ]
    p_noise_1 = [
        calc_noise_1(state["candidates"][i], last_guess, parsed) if state["probability"][i] != 0 else 0
        for i in range(len(state["candidates"]))
    ]
    p_noise_2 = [
        calc_noise_2(state["candidates"][i], last_guess, parsed) if state["probability"][i] != 0 else 0
        for i in range(len(state["candidates"]))
    ]
    p_noise = np.array([p_noise_0, p_noise_1, p_noise_2], np.float32)

    state["multi_probability"] = p_noise * state["multi_probability"]

    p = state["noise"][:]
    p1 = (1-state["force_noise"]) * p[0] / 3
    p2 = state["force_noise"] * p[0] / 3
    p[0] *= 2/3
    p[1] += p1; p[2] += p2
    state["probability"] = np.sum(state["multi_probability"], axis=0)

def special_turn_2(state, last_guess, parsed):
    print("guess #2")
    p_noise_0 = [
        calc_noise_0(state["candidates"][i], last_guess, parsed) if state["probability"][i] != 0 else 0
        for i in range(len(state["candidates"]))
    ]
    p_noise_1 = [
        calc_noise_1(state["candidates"][i], last_guess, parsed) if state["probability"][i] != 0 else 0
        for i in range(len(state["candidates"]))
    ]
    p_noise_2 = [
        calc_noise_2(state["candidates"][i], last_guess, parsed) if state["probability"][i] != 0 else 0
        for i in range(len(state["candidates"]))
    ]
    p_noise = np.array([p_noise_0, p_noise_1, p_noise_2], np.float32)

    state["multi_probability"] = p_noise[None, :, :] * state["multi_probability"][:, None, :]

    p = [[state["noise"][i]*state["noise"][j] for j in range(3)] for i in range(3)]
    p1 = (1-state["force_noise"]) * p[0][0] / 3
    p2 = state["force_noise"] * p[0][0] / 3
    p[0][0] *= 1/3
    p[1][0] += p1; p[0][1] += p1
    p[2][0] += p2; p[0][2] += p2
    state["probability"] = np.sum(state["multi_probability"], axis=(0,1))

def special_turn_3(state, last_guess, parsed):
    print("guess #3")
    p_noise_0 = [
        calc_noise_0(state["candidates"][i], last_guess, parsed) if state["probability"][i] != 0 else 0
        for i in range(len(state["candidates"]))
    ]
    p_noise_1 = [
        calc_noise_1(state["candidates"][i], last_guess, parsed) if state["probability"][i] != 0 else 0
        for i in range(len(state["candidates"]))
    ]
    p_noise_2 = [
        calc_noise_2(state["candidates"][i], last_guess, parsed) if state["probability"][i] != 0 else 0
        for i in range(len(state["candidates"]))
    ]
    p_noise = np.array([p_noise_0, p_noise_1, p_noise_2], np.float32)

    state["multi_probability"] = p_noise[None, None, :, :] * state["multi_probability"][:, :, None, :]

    p = [[[state["noise"][i]*state["noise"][j]*state["noise"][k] for k in range(3)] for j in range(3)] for i in range(3)]
    p1 = (1-state["force_noise"]) * p[0][0][0] / 3
    p2 = state["force_noise"] * p[0][0][0] / 3
    p[1][0][0] += p1; p[0][1][0] += p1; p[0][0][1] += p1
    p[2][0][0] += p2; p[0][2][0] += p2; p[0][0][2] += p2
    p[0][0][0] = 0
    state["probability"] = np.sum(state["multi_probability"], axis=(0,1,2))

    del state["multi_probability"]
    del state["force_noise"]

class Solver:
    """Stores per-problem state and chooses the next action."""

    def __init__(self):
        self.problems = {}
    
    def start_problem(self, data):
        """Initialize state for a new problem."""
        candidates = list(data["candidate_words"])
        n = len(candidates)
        self.problems[data["problem_id"]] = {
            "candidates": candidates,
            "noise": [1-data["noise_probability"]-data["two_letter_noise_probability"], data["noise_probability"], data["two_letter_noise_probability"]],
            "force_noise": 0 if (data["noise_probability"] == data["two_letter_noise_probability"] == 0) else (data["two_letter_noise_probability"])/(data["noise_probability"]+data["two_letter_noise_probability"]),
            "multi_probability": np.full((n,), 1/n, np.float32),
            "probability": np.full((n,), 1/n, np.float32),
            "guesses": [],
        }

    def act(self, data):
        """Update state from the latest feedback and return guess/submit."""
        state = self.problems[data["problem_id"]]
        if state["guesses"]:
            parsed = parse_feedback(data.get("feedback"))
            if parsed is not None:
                last_guess = state["guesses"][-1]

                if len(state["guesses"]) == 1: special_turn_1(state, last_guess, parsed)
                elif len(state["guesses"]) == 2: special_turn_2(state, last_guess, parsed)
                elif len(state["guesses"]) == 3: special_turn_3(state, last_guess, parsed)
                else:
                    p = [
                        calc_probability(state["noise"], state["candidates"][i], last_guess, parsed) if state["probability"][i] != 0 else 0
                        for i in range(len(state["candidates"]))
                    ]
                    state["probability"] *= p
                
                psum = sum(state["probability"])
                if psum != 0: state["probability"] /= psum

                print(f"guess: {last_guess} -> {parsed}")
                print(f"probability: ({np.count_nonzero(state["probability"])} possible)")
                for i in np.argsort(-state["probability"], kind='stable')[:10]:
                    if state["probability"][i] == 0: break
                    print(f"{state["candidates"][i]}: {state["probability"][i]:.4f} | ", end='')
                print()

        p_sorted = np.argsort(-state["probability"], kind='stable')
        p_max = p_sorted[0]

        if state["probability"][p_max] == 0:
            return {"action": "submit", "word": "sad"} # ???

        if (1 - state["probability"][p_max]) < 1e-5:
            return {"action": "submit", "word": state["candidates"][p_max]}
        
        # 정답 후보 선정
        p = 0.9 * state["probability"][p_max] # 가장 확률이 높은 단어에 대해 이 비율 이상이면 후보로 모음.
        guess_candidates = []
        for word in p_sorted:
            if state["probability"][word] > p:
                guess_candidates.append(state["candidates"][word])
            else: break
        # 정답 후보 간 차이 추출
        best_word = state["candidates"][p_max]
        if len(guess_candidates) != 1:
            alphabet = {chr(i):0 for i in range(97, 123)}
            for word in guess_candidates:
                # 비슷하다면 다른 알파벳을 추가
                q = 2
                for idx in range(5):
                    if q and word[idx] != best_word[idx]:
                        q -= 1
                if q:
                    for idx in range(5):
                        if word[idx] != best_word[idx]:
                            alphabet[word[idx]] += 1
            # 단어 선정
            # 단어의 알파벳을 set으로 나타내서 alphabet[각 요소] 의 합이 가장 높은 단어 선정
            # 이미 정답이 아님이 판명 난 단어도 선정될 수 있음
            best_score = 0
            for e in p_sorted:
                score = sum(alphabet[ee] for ee in set(state["candidates"][e]))
                if best_score < score:
                    best_score = score
                    best_word = state["candidates"][e]
        guess = best_word
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
