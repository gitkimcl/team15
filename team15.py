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

def calc_noise_0(word, guess, parsed):
    return 1 if compute_feedback(word, guess) == parsed else 0

def calc_noise_1(word, guess, parsed):
    wordl = list(word)
    ccnt = 0
    char_in_guess = set()
    for e in guess: char_in_guess.add(e)
    for i in range(5):
        collision = False
        for e in char_in_guess:
            if e == word[i]:
                collision = True
                continue
            wordl[i] = e
            if compute_feedback("".join(wordl), guess) == parsed: ccnt += 1
        wordl[i] = '*'
        if compute_feedback("".join(wordl), guess) == parsed:
            ccnt += 25 - len(char_in_guess)
            if collision: ccnt += 1
        wordl[i] = word[i]
    return ccnt / (5*25)

def calc_noise_2(word, guess, parsed):
    wordl = list(word)
    ccnt = 0
    char_in_guess = set()
    for e in guess: char_in_guess.add(e)
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
            wordl[i] = wordl[j] = '*'
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
    p_noise_0 = { k: calc_noise_0(k, last_guess, parsed) for k in state["candidates"] }
    p_noise_1 = { k: calc_noise_1(k, last_guess, parsed) for k in state["candidates"] }
    p_noise_2 = { k: calc_noise_2(k, last_guess, parsed) for k in state["candidates"] }

    state["multi_probability"][1][0][0] = {
        k: v * p_noise_0[k]
        for k, v in state["multi_probability"][0][0][0].items()
    }
    state["multi_probability"][2][0][0] = {
        k: v * p_noise_1[k]
        for k, v in state["multi_probability"][0][0][0].items()
    }
    state["multi_probability"][3][0][0] = {
        k: v * p_noise_2[k]
        for k, v in state["multi_probability"][0][0][0].items()
    }
    p = state["noise"][:]
    r = 0 if (state["noise"][1] == state["noise"][2] == 0) else (state["noise"][2])/(state["noise"][1]+state["noise"][2])
    p1 = (1-r) * p[0] / 3
    p2 = r * p[0] / 3
    p[0] *= 2/3
    p[1] += p1; p[2] += p2
    state["probability"] = {
        k: sum(p[i] * state["multi_probability"][i+1][0][0][k] for i in range(3)) for k in state["probability"]
    }

def special_turn_2(state, last_guess, parsed):
    print("guess #2")
    p_noise_0 = { k: calc_noise_0(k, last_guess, parsed) for k in state["candidates"] }
    p_noise_1 = { k: calc_noise_1(k, last_guess, parsed) for k in state["candidates"] }
    p_noise_2 = { k: calc_noise_2(k, last_guess, parsed) for k in state["candidates"] }

    for i in range(1, 4):
        state["multi_probability"][i][1][0] = {
            k: v * p_noise_0[k]
            for k, v in state["multi_probability"][i][0][0].items()
        }
        state["multi_probability"][i][2][0] = {
            k: v * p_noise_1[k]
            for k, v in state["multi_probability"][i][0][0].items()
        }
        state["multi_probability"][i][3][0] = {
            k: v * p_noise_2[k]
            for k, v in state["multi_probability"][i][0][0].items()
        }
    p = [[state["noise"][i]*state["noise"][j] for j in range(3)] for i in range(3)]
    r = 0 if (state["noise"][1] == state["noise"][2] == 0) else (state["noise"][2])/(state["noise"][1]+state["noise"][2])
    p1 = (1-r) * p[0][0] / 3
    p2 = r * p[0][0] / 3
    p[0][0] *= 1/3
    p[1][0] += p1; p[0][1] += p1
    p[2][0] += p2; p[0][2] += p2
    state["probability"] = {
        k: sum(p[i][j] * state["multi_probability"][i+1][j+1][0][k] for i in range(3) for j in range(3)) for k in state["probability"]
    }

def special_turn_3(state, last_guess, parsed):
    print("guess #3")
    p_noise_0 = { k: calc_noise_0(k, last_guess, parsed) for k in state["candidates"] }
    p_noise_1 = { k: calc_noise_1(k, last_guess, parsed) for k in state["candidates"] }
    p_noise_2 = { k: calc_noise_2(k, last_guess, parsed) for k in state["candidates"] }

    for i in range(1, 4):
        for j in range(1, 4):
            state["multi_probability"][i][j][1] = {
                k: v * p_noise_0[k]
                for k, v in state["multi_probability"][i][j][0].items()
            }
            state["multi_probability"][i][j][2] = {
                k: v * p_noise_1[k]
                for k, v in state["multi_probability"][i][j][0].items()
            }
            state["multi_probability"][i][j][3] = {
                k: v * p_noise_2[k]
                for k, v in state["multi_probability"][i][j][0].items()
            }
    p = [[[state["noise"][i]*state["noise"][j]*state["noise"][k] for k in range(3)] for j in range(3)] for i in range(3)]
    r = 0 if (state["noise"][1] == state["noise"][2] == 0) else (state["noise"][2])/(state["noise"][1]+state["noise"][2])
    p1 = (1-r) * p[0][0][0] / 3
    p2 = r * p[0][0][0] / 3
    p[1][0][0] += p1; p[0][1][0] += p1; p[0][0][1] += p1
    p[2][0][0] += p2; p[0][2][0] += p2; p[0][0][2] += p2
    p[0][0][0] = 0
    state["probability"] = {
        k: sum(p[i][j][l] * state["multi_probability"][i+1][j+1][l+1][k] for i in range(3) for j in range(3) for l in range(3)) for k in state["probability"]
    }

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
            "multi_probability": [[[{} for _ in range(4)] for _ in range(4)] for _ in range(4)],
            "probability": {k: 1/n for k in candidates},
            "guesses": [],
        }
        self.problems[data["problem_id"]]["multi_probability"][0][0][0] = {k: 1/n for k in candidates}

    def act(self, data):
        """Update state from the latest feedback and return guess/submit."""
        state = self.problems[data["problem_id"]]
        if state["guesses"]:
            parsed = parse_feedback(data.get("feedback"))
            if parsed is not None:
                last_guess = state["guesses"][-1]

                print(f"probability before: ({len(state["probability"])} possible)")
                for k, v in sorted(state["probability"].items(), key=lambda e: -e[1])[:10]:
                    print(f"{k}: {v:.4f} | ", end='')
                print(f"\nguess result: {last_guess} -> {parsed}")

                if len(state["guesses"]) == 1: special_turn_1(state, last_guess, parsed)
                elif len(state["guesses"]) == 2: special_turn_2(state, last_guess, parsed)
                elif len(state["guesses"]) == 3: special_turn_3(state, last_guess, parsed)
                else:
                    state["probability"] = {
                        k: v * calc_probability(state["noise"], k, last_guess, parsed)
                        for k, v in state["probability"].items()
                    }
                
                psum = sum(state["probability"].values())
                state["probability"] = {
                    k: v / psum
                    for k, v in state["probability"].items()
                    if v > 1e-10 # 에이 설마
                }

                print(f"probability after: ({len(state["probability"])} possible)")
                for k, v in sorted(state["probability"].items(), key=lambda e: -e[1])[:10]:
                    print(f"{k}: {v:.4f} | ", end='')
                print()

        if len(state["probability"]) == 1 or (1 - max(state["probability"].items(), key=lambda e: e[1])[1]) < 1e-5:
            return {"action": "submit", "word": max(state["probability"].items(), key=lambda e: e[1])[0]}
        elif len(state["probability"]) == 0:
            # ???
            pass
        
        if not state["probability"]: guess = state["candidates"][0] # ???
        else: 
            #정답 후보 선정
            p = 0.9 * max(state["probability"].items(), key=lambda e: e[1])[1]#가장 확률이 높은 단어에 대해 이 비율 이상이면 후보로 모음.
            guess_candidates = []
            for word in sorted(state["probability"].items(), key=lambda e: -e[1]):
                if word[1] > p:
                    guess_candidates.append(word[0])
                else: break
            #정답 후보 간 차이 추출
            best_word = guess_candidates[0]
            if len(guess_candidates) != 1:
                alphabet = {chr(i):0 for i in range(97, 123)}
                for word in guess_candidates:
                    #비슷하다면 다른 알파벳을 추가
                    q = 2
                    for idx in range(5):
                        if q and word[idx] != best_word[idx]:
                            q -= 1
                    if q:
                        for idx in range(5):
                            if word[idx] != best_word[idx]:
                                alphabet[word[idx]] += 1
                #단어 선정
                #단어의 알파벳을 set으로 나타내서 alphabet[각 요소] 의 합이 가장 높은 단어 선정
                best_word_score = 0
                for word in state["candidates"]: #전체 단어로 변경
                    word_score = sum(alphabet[i] for i in set(list(word)))
                    if word_score > best_word_score:
                        best_word = word
                        best_word_score = word_score
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
