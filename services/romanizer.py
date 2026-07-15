HANGUL_START = 0xAC00
HANGUL_END = 0xD7A3
HANGUL_BASE = 588
VOWEL_BASE = 28

INITIALS = [
    "g",
    "kk",
    "n",
    "d",
    "tt",
    "r",
    "m",
    "b",
    "pp",
    "s",
    "ss",
    "",
    "j",
    "jj",
    "ch",
    "k",
    "t",
    "p",
    "h",
]
VOWELS = [
    "a",
    "ae",
    "ya",
    "yae",
    "eo",
    "e",
    "yeo",
    "ye",
    "o",
    "wa",
    "wae",
    "oe",
    "yo",
    "u",
    "wo",
    "we",
    "wi",
    "yu",
    "eu",
    "ui",
    "i",
]
FINALS = [
    "",
    "k",
    "k",
    "ks",
    "n",
    "nj",
    "nh",
    "t",
    "l",
    "lk",
    "lm",
    "lb",
    "ls",
    "lt",
    "lp",
    "lh",
    "m",
    "p",
    "ps",
    "t",
    "t",
    "ng",
    "t",
    "t",
    "k",
    "t",
    "p",
    "t",
]
FINAL_LIAISON = {
    1: "g",
    2: "kk",
    4: "n",
    7: "d",
    8: "r",
    16: "m",
    17: "b",
}


def has_hangul(text):
    return any(HANGUL_START <= ord(char) <= HANGUL_END for char in text or "")


def decompose_syllable(char):
    code = ord(char)
    if code < HANGUL_START or code > HANGUL_END:
        return None

    offset = code - HANGUL_START
    return (
        offset // HANGUL_BASE,
        (offset % HANGUL_BASE) // VOWEL_BASE,
        offset % VOWEL_BASE,
    )


def romanize_syllable(char):
    syllable = decompose_syllable(char)
    if not syllable:
        return char

    initial_index, vowel_index, final_index = syllable
    return INITIALS[initial_index] + VOWELS[vowel_index] + FINALS[final_index]


def romanize_korean(text):
    if not text:
        return ""
    if not has_hangul(text):
        return ""

    romanized = []
    index = 0
    while index < len(text):
        syllable = decompose_syllable(text[index])
        if not syllable:
            romanized.append(text[index])
            index += 1
            continue

        initial_index, vowel_index, final_index = syllable
        next_syllable = decompose_syllable(text[index + 1]) if index + 1 < len(text) else None
        if final_index in FINAL_LIAISON and next_syllable and next_syllable[0] == 11:
            romanized.append(INITIALS[initial_index] + VOWELS[vowel_index])
            romanized.append(FINAL_LIAISON[final_index] + VOWELS[next_syllable[1]] + FINALS[next_syllable[2]])
            index += 2
            continue

        romanized.append(INITIALS[initial_index] + VOWELS[vowel_index] + FINALS[final_index])
        index += 1

    return "".join(romanized)
