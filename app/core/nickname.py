import secrets

_ADJECTIVES: tuple[str, ...] = (
    "happy", "brave", "calm", "bright", "cozy", "swift", "kind", "bold",
    "gentle", "lively", "merry", "quiet", "sunny", "witty", "fancy",
    "mighty", "lucky", "jolly", "fluffy", "breezy", "eager", "fresh",
    "glad", "golden", "grand", "humble", "lush", "misty", "nimble",
    "noble", "plucky", "proud", "rapid", "royal", "silver", "snug",
    "spry", "sturdy", "tidy", "vivid", "warm", "wise", "zesty",
    "amber", "cool", "dewy", "frosty", "rustic", "shiny", "smooth",
)

_NOUNS: tuple[str, ...] = (
    "tiger", "panda", "otter", "fox", "owl", "deer", "whale", "lynx",
    "eagle", "bear", "hawk", "wolf", "puma", "koala", "moose",
    "bison", "ranger", "hiker", "camper", "scout",
    "pine", "oak", "river", "lake", "peak", "ridge", "valley", "meadow",
    "cliff", "brook", "ember", "lantern", "compass", "tent", "flame",
    "stove", "trail", "summit", "forest", "canyon", "glacier", "breeze",
    "stone", "branch", "dune", "harbor", "marsh", "raven", "falcon",
    "sparrow",
)


def generate_nickname() -> str:
    """랜덤 닉네임을 `형용사-명사-숫자` 형태로 생성한다.

    예: `happy-tiger-1234`. 약 22.5M 조합이라 실 충돌 가능성은 매우 낮지만
    호출부에서 unique 충돌 시 재시도해야 한다.
    """
    adjective = secrets.choice(_ADJECTIVES)
    noun = secrets.choice(_NOUNS)
    number = secrets.randbelow(9000) + 1000
    return f"{adjective}-{noun}-{number}"
