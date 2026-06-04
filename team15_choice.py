"""Minimal example solver server.

This file shows the required HTTP endpoints and a very simple filtering
strategy. Replace the Solver logic with your own method.
"""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np

def parse_feedback(text):
    """채점기의 피드백 해석"""

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

def batch_compute_feedback(arr, weight, guess, parsed):
    """arr의 각 단어들이 정답일 때 guess로 추측했다면,
    채점기가 parsed를 알려주는 단어의 개수를 계산"""

    # 초록색 체크: 초록색인데 글자가 다른 경우, 초록색이 아닌데 글자가 같은 경우 걸러내기
    green = parsed == 2
    mask = np.all(
        arr[:, green] == guess[green],
        axis=1
    ) & np.all(
        arr[:, ~green] != guess[~green],
        axis=1
    )
    arr = arr[mask]; weight = weight[mask]
    if len(arr) == 0: return 0

    yellow = parsed == 1
    gray = parsed == 0
    in_arr = np.bincount(guess[yellow], minlength=32) # bincount: b[x] == <원래 배열에서 x의 개수>인 배열 만들기
    not_in_arr = np.bincount(guess[gray], minlength=32)

    # 어차피 parsed에 이를 준수하는 입력만 들어오므로, 노란색이 왼쪽에 있어야 하는 규칙은 구현하지 않음.
    nongreen = np.apply_along_axis(lambda e: np.bincount(e, minlength=32), 1, arr[:, ~green]) # arr의 각 단어에서, 초록색에 이미 쓰이지 않은 글자들.
    remaining = nongreen - in_arr
    yellow_check = np.all(remaining >= 0, axis=1) # 만약 초록색에 이미 쓰이지 않은 글자들보다 guess의 노란색의 글자들이 많다면, 답이 아님.
    gray_check = np.all(remaining[:, not_in_arr > 0] == 0, axis=1) # 만약 초록색에 이미 쓰이지 않은 글자들이 남았는데, 회색 글자가 있다면, 답이 아님.
    return np.sum(weight[yellow_check & gray_check])

def calc_probability_noise_0(word, guess, parsed):
    """노이즈 없음이 보장된 상황에서,
    정답이 word일 때 guess를 추측했다면 채점기가 parsed를 알려줄 확률(여기선 0 또는 1)"""

    return batch_compute_feedback(
        np.array([[ord(word[i])-97 for i in range(5)]], np.int8),
        np.array([1]),
        np.fromiter((ord(e)-97 for e in guess), np.int8, count=5),
        np.fromiter((ord(e)-48 for e in parsed), np.int8, count=5)
    )

def calc_probability_noise_1(word, guess, parsed):
    """글자 하나를 바꾸는 노이즈가 보장된 상황에서,
    정답이 word일 때 guess를 추측했다면 채점기가 parsed를 알려줄 확률"""

    word = [ord(word[i])-97 for i in range(5)]
    word_noise = word[:]
    guess = [ord(guess[i])-97 for i in range(5)]
    tests = []; weights = []
    char_in_guess = set(guess)
    # word의 글자 하나를 바꿔 생길 수 있는 모든 경우 확인
    # 최적화를 위해, guess에 없는 글자로 바뀌는 경우는 하나로 묶어 처리함
    for i in range(5):
        collision = 0
        for e in char_in_guess:
            if e == word[i]:
                collision += 1
                continue
            word_noise[i] = e
            tests.append(word_noise[:])
            weights.append(1)
        word_noise[i] = 26
        tests.append(word_noise[:])
        weights.append(25 - len(char_in_guess) + collision)
        word_noise[i] = word[i]
    return batch_compute_feedback(
        np.array(tests, np.int8),
        np.array(weights, np.int16),
        np.fromiter(guess, np.int8, count=5),
        np.fromiter((ord(e)-48 for e in parsed), np.int8, count=5)
    ) / (5*25)

def calc_probability_noise_2(word, guess, parsed):
    """글자 둘을 바꾸는 노이즈가 보장된 상황에서,
    정답이 word일 때 guess를 추측했다면 채점기가 parsed를 알려줄 확률"""

    word = [ord(word[i])-97 for i in range(5)]
    word_noise = word[:]
    guess = [ord(guess[i])-97 for i in range(5)]
    tests = []; weights = []
    char_in_guess = set(guess)
    # word의 글자 두 개를 바꿔 생길 수 있는 모든 경우 확인
    # 최적화를 위해, guess에 없는 글자로 바뀌는 경우는 하나로 묶어 처리함
    for i in range(5):
        for j in range(i+1, 5):
            collision = 0
            for e in char_in_guess:
                for ee in char_in_guess:
                    if e == word[i] or ee == word[j]:
                        collision += 1
                        continue
                    word_noise[i] = e
                    word_noise[j] = ee
                    tests.append(word_noise[:])
                    weights.append(1)
            word_noise[i] = word_noise[j] = 26
            tests.append(word_noise[:])
            weights.append((25 - len(char_in_guess)) * (25 - len(char_in_guess)) + collision)
            word_noise[i] = word[i]
            word_noise[j] = word[j]
    return batch_compute_feedback(
        np.array(tests, np.int8),
        np.array(weights, np.int16),
        np.fromiter(guess, np.int8, count=5),
        np.fromiter((ord(e)-48 for e in parsed), np.int8, count=5)
    ) / (10*25*25)

def calc_probability(noise, word, guess, parsed):
    """노이즈의 종류가 보장되지 않은 상황에서,
    정답이 word일 때 guess를 추측했다면 채점기가 parsed를 알려줄 확률
    (그냥 선형결합 하면 됨)"""

    return noise[0] * calc_probability_noise_0(word, guess, parsed) + \
        noise[1] * calc_probability_noise_1(word, guess, parsed) + \
        noise[2] * calc_probability_noise_2(word, guess, parsed)

def force_noise_turn(turn, state, last_guess, parsed):
    """강제로 노이즈가 하나는 있는 첫 세 턴 때의 단어 확률을 관리하는 함수
    임시방편으로 p와 q 늘리기 등의 여러 방법을 떠올렸지만, 결국 정확성을 위해 멀티버스 방안을 채용"""

    p_for_noise = np.array([[
        calc_probability_noise_0(state["candidates"][i], last_guess, parsed) if state["probability"][i] != 0 else 0
        for i in range(len(state["candidates"]))
    ], [
        calc_probability_noise_1(state["candidates"][i], last_guess, parsed) if state["probability"][i] != 0 else 0
        for i in range(len(state["candidates"]))
    ], [
        calc_probability_noise_2(state["candidates"][i], last_guess, parsed) if state["probability"][i] != 0 else 0
        for i in range(len(state["candidates"]))
    ]], np.float32)

    # numpy로 멀티버스 만들기
    match turn:
        case 1: state["multi_probability"] = p_for_noise * state["multi_probability"]
        case 2: state["multi_probability"] = p_for_noise[None, :, :] * state["multi_probability"][:, None, :]
        case 3: state["multi_probability"] = p_for_noise[None, None, :, :] * state["multi_probability"][:, :, None, :]
    
    # 첫 turn턴에서 어떤 노이즈가 어떤 순서로 뜰지의 확률 저장, 3턴 노이즈 보정 반영
    noise_p = np.array(state["noise"])
    if turn == 2: noise_p = noise_p[:, None] * noise_p[None, :]
    elif turn == 3: noise_p = noise_p[:, None, None] * noise_p[None, :, None] * noise_p[None, None, :]
    p1 = (1-state["force_noise"]) * (state["noise"][0])**turn / 3
    p2 = state["force_noise"] * (state["noise"][0])**turn / 3
    match turn:
        case 1:
            noise_p[0] *= 2/3
            noise_p[1] += p1; noise_p[2] += p2
        case 2:
            noise_p[0][0] *= 1/3
            noise_p[1][0] += p1; noise_p[0][1] += p1
            noise_p[2][0] += p2; noise_p[0][2] += p2
        case 3:
            noise_p[0][0][0] = 0
            noise_p[1][0][0] += p1; noise_p[0][1][0] += p1; noise_p[0][0][1] += p1
            noise_p[2][0][0] += p2; noise_p[0][2][0] += p2; noise_p[0][0][2] += p2

    # 모든 멀티버스를 대변하는 확률값을 state["probability"]에 저장
    # 3번째 턴이 끝나면 더 이상 멀티버스를 안 만들어도 되므로, 그대로 state["probability"]만을 사용하게 됨
    state["probability"] = np.sum(state["multi_probability"] * noise_p[..., None], axis=tuple(range(turn)))
    if turn == 3:
        del state["multi_probability"]
        del state["force_noise"]

class Solver:
    """정보 저장 및 단어 선택"""

    def __init__(self):
        self.problems = {}
    
    def start_problem(self, data):
        """문제 풀이 시작
        작년 프로젝트에선 문제 여러 개를 저글링하듯이 풀어야 됐는데,
        이번에는 그렇지 않은 것으로 보인다."""
        
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
        """피드백을 반영해 추측/제출 단어 선정"""

        state = self.problems[data["problem_id"]]
        if state["guesses"]:
            parsed = parse_feedback(data.get("feedback"))
            if parsed is not None:
                last_guess = state["guesses"][-1]

                print(f"guess #{len(state["guesses"])}")
                print(f"guess: {last_guess} -> {parsed}")
                
                if len(state["guesses"]) == 1: force_noise_turn(1, state, last_guess, parsed)
                elif len(state["guesses"]) == 2: force_noise_turn(2, state, last_guess, parsed)
                elif len(state["guesses"]) == 3: force_noise_turn(3, state, last_guess, parsed)
                else:
                    # 베이즈 정리를 활용한 확률 업데이트
                    p = [
                        calc_probability(state["noise"], state["candidates"][i], last_guess, parsed) if state["probability"][i] != 0 else 0
                        for i in range(len(state["candidates"]))
                    ]
                    state["probability"] *= p
                
                psum = sum(state["probability"])
                if psum != 0: state["probability"] /= psum

                print(f"probability: ({np.count_nonzero(state["probability"])} possible)")
                for i in np.argsort(-state["probability"], kind='stable')[:10]:
                    if state["probability"][i] == 0: break
                    print(f"{state["candidates"][i]}: {state["probability"][i]:.4f} | ", end='')
                print()

        p_sorted = np.argsort(-state["probability"], kind='stable')
        p_max = p_sorted[0]

        if state["probability"][p_max] == 0:
            return {"action": "submit", "word": "sad"} # :(

        if (1 - state["probability"][p_max]) < 5e-5: # 0.005%의 확률로 틀린다면 죽어야지 뭐
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
