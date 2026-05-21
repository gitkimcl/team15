# 워들 푸는 프로그램 만들기

## 게임 규칙

워들인데, 채점기가 우리에게 사기를 칠 수 있다.  
입력으로 주어지는 0 이상 1 이하의 두 수 `p`, `q`에 대해

* `1-p-q`의 확률로 우리의 추측에 정상적으로 답하며,
* `p`의 확률로 실제 정답과 한 글자가 다른 단어가 정답인 양 우리의 추측에 답하고,
* `q`의 확률로 실제 정답과 두 글자가 다른 단어가 정답인 양 우리의 추측에 답한다.

우리의 목표는 정답을 알아낼 때까지의 횟수를 최소화하는 것이다.

## 소통 방법

### 게임 시작

우리의 프로그램이 시작된 지 5초 뒤, 채점기가 우리에게 요청을 보낸다.

```text
POST /start_problem
Content-Type: application/json
{
    "problem_id": "<problem_id>",
    "candidate_words": ["word1, "word2", ..., "wordN"],
    "noise_probability": 0.33,
    "two_letter_noise_probability": 0.33,
    "force_noise_turns": 3,
    "max_turns": 100,
    "guess_time_budget": 60
}
```

`problem_id`는 이후 소통에 사용할 문제 id이다.  
`candidate_words`는 우리가 추측에 사용할 수 있는 단어들이며, 정답도 이 중 하나이다.  
`noise_probability`는 `p`, 즉 정답의 한 글자를 다르게 해 추측에 답할 확률이다.  
`two_letter_noise_probability`는 `q`, 즉 정답의 두 글자를 다르게 해 추측에 답할 확률이다.  
`force_noise_turns`는 적어도 한 번의 사기가 일어날 턴 수를 지정한다. 예를 들어, `force_noise_turns`가 3이라면 첫 세 턴 중 적어도 한 턴에는 무조건 사기가 일어난다.  
`max_turns`는 우리가 사용할 수 있는 최대 턴수이며, 점수 계산에 사용한다.  
`guess_time_budget`은 우리가 사용할 수 있는 최대 시간이다. `guess_time_budget`이 60이라면 60초 안에 답이 나오지 않을 시 시간 초과로 간주된다.

사기가 일어났을 때 채점기가 정답이라고 간주하는 단어는 `candidate_words` 안에 없을 수도 있다.

우리의 프로그램은 이 요청을 받았을 때 다음과 같이 응답해야 한다.

```text
HTTP 200 OK
Content-Type: application/json
{}
```

응답하지 않는다면 채점기는 이를 시간 초과로 간주한다. 이 요청이 프로그램을 시작하고 5초 뒤에 들어오므로, 우리의 프로그램은 초기화/전처리를 5초 이내에 해 응답을 받을 수 있는 상태를 만들어야 한다.

### 게임 진행

게임 시작 요청에 응답했다면, 채점기는 반복적으로 우리에게 다음과 같은 요청을 보낸다.

```text
POST /act
Content-Type: application/json
{
    "problem_id": "<problem-id>",
    "feedback": "<feedback_for_previous_guess>",
    "turn": <turn_number>
}
```

`problem_id`는 앞서 말한 문제 id이다.  
`feedback`은 우리의 바로 전 추측에 대한 결과이다. 첫 추측에서 `feedback`은 `null`이다.  
`turn`은 현재 턴이며, 1부터 올라간다.

`feedback`은 다음과 같은 형태로 주어진다.

```text
추측이 melee이며, 정답(또는 채점기가 정답으로 간주하는 단어)이 tweet일 때

The first letter 'm' is absent.
The second letter 'e' is misplaced.
The third letter 'l' is absent.
The fourth letter 'e' is correct.
The fifth letter 'e' is absent.
```

`absent`는 해당 글자가 정답에 없다는 것을 뜻한다. 회색과 같다.  
`misplaced`는 해당 글자가 정답에 있으나 그 위치는 아니라는 것을 뜻한다. 노란색과 같다.  
`correct`는 해당 글자가 정확한 위치에 있다는 것을 뜻한다. 초록색과 같다.

정답이나 추측에 같은 글자가 여러 개 있는 경우, 우선 `correct`인 글자를 정한 뒤 정답의 글자 수와 같아질 때까지 왼쪽부터 `misplaced`를 채운다.  
예를 들어 정답이 tweet, 추측이 melee라면 두 번째 e는 `correct`, 첫 번째 e는 `misplaced`, 세 번째 e는 `absent`가 된다.

우리는 이에 두 가지 방식 중 하나로 응답해야 한다.

#### 추측

피드백을 듣기 위해 추측을 할 수 있다. 추측을 하려면 다음과 같은 형태로 응답한다.

```text
HTTP 200 OK
Content-Type: application/json
{
    "action": "guess",
    "word": "<your_guess>"
}
```

`word`는 영어 소문자 다섯 글자로 이루어진 문자열이어야 하며, `candidate_words` 안에 있어야 한다. 만약 아니라면, 문제가 즉시 실패 처리된다.

#### 답 제출

피드백을 충분히 들었다면 답을 제출할 수 있다. 다음과 같은 형태로 응답한다.

```text
HTTP 200 OK
Content-Type: application/json
{
    "action": "submit",
    "word": "<your_final_answer>"
}
```

마찬가지로 `word`는 영어 소문자 다섯 글자로 이루어진 문자열이어야 하며, `candidate_words` 안에 있어야 한다. 답이 정확할 경우, 문제가 성공 처리된다. 답이 정확하지 않을 경우, 문제가 즉시 실패 처리된다.

## 점수 계산

점수는 아래의 점수들을 반영해 계산한다.

### 트랙 점수

채점기는 같은 문제들에 대해 매개변수를 바꿔서 3회의 트랙을 실행한다.

`t`를 문제를 풀 때까지 걸린 턴 수라고 하자. 만약 문제 풀이에 실패했다면(시간 초과, 턴 수 초과, 오답 제출 등), `t`는 `max_turns`와 같다.

트랙 하나에 대해, `t`의 평균을 `x`라고 하고, 모든 팀에서 `x`의 최솟값을 `y`라고 하자. 해당 트랙에서 우리의 점수는

$$\max\left(0,100-20\log_2\left(\frac{x}{y}\right)\right)$$

이다. 예를 들어, 한 트랙에서 $x=10$, $y=5$라면 그 트랙에서는 80점을 받는다.

아래는 각 트랙이 사용하는 매개변수이다.

#### Track 1

```json
{
    "noise_probability": 0.00,
    "two_letter_noise_probability": 0.00,
    "force_noise_turns": 3,
    "max_turns": 100,
    "guess_time_budget": 60
}
```

(force_noise_turns의 영향으로 첫 세 턴 중 한 번 사기가 일어난다.)

#### Track 2

```json
{
    "noise_probability": 0.33,
    "two_letter_noise_probability": 0.33,
    "force_noise_turns": 3,
    "max_turns": 100,
    "guess_time_budget": 60
}
```

#### Track 3

```json
{
    "noise_probability": 0.33,
    "two_letter_noise_probability": 0.66,
    "force_noise_turns": 3,
    "max_turns": 100,
    "guess_time_budget": 60
}
```

### 문제 제출

평가에는 미리 만든 문제들과 더불어, 각 팀이 제출한 문제들도 사용된다. 이 문제를 제출하는 것도 점수에 반영된다.

문제는 다음과 같은 형식으로 제출하여야 한다.

```json
{
    "secret_word": "<word>",
    "candidate_words": [
        "<word1>",
        "<word2>",
        ...,
        "<wordn>"
    ]
}
```

한 문제만을 제출해야 하며, 정답과 사용 가능 단어들은 모두 별도로 주어진 5글자 영단어 목록에서 선택해야 한다.

### 발표 점수

발표 점수이다. 발표는 5분 내외이다.

## 마감

코드, 문제, 발표 슬라이드를 6월 14일 23시 59분까지 제출해야 한다. 코드는 zip 파일로 제출해야 하며, 용량이 1MB를 넘지 않아야 한다.
보고서는 발표 슬라이드로 대체한다.

## 기타

* 원래(작년)는 피드백을 지금처럼 딱딱 맞춰서 주는 게 아니라 자연어로 줘서, 자연어 처리를 해야 됐었던 것 같다ㄷㄷ
* 외부 라이브러리를 사용하지 않는 것을 권장한다.
