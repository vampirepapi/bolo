"""Devanagari -> Hinglish, by rule, so it is instant and works on live text."""
import re

# Devanagari -> Hinglish (Hindi in casual Roman spelling), by rule, so it is instant and works on live text.
NUKTA_LETTERS = "".join(map(chr, range(0x958, 0x960)))  # क़ ख़ ग़ ज़ ड़ ढ़ फ़ य़ as single codepoints
CONSONANTS = dict(zip("कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसह" + NUKTA_LETTERS,
                      "k kh g gh n ch chh j jh n t th d dh n t th d dh n p ph b bh m y r l v sh sh s h q kh g z d dh f y".split()))
VOWELS = dict(zip("अआइईउऊऋएऐओऔऑऍ", "a aa i i u u ri e ai o au o e".split()))
MATRAS = dict(zip("ािीुूृेैोौॉॅॆॊ", "a i i u u ri e ai o au o e e o".split()))
SIGNS = {"ं": "n", "ँ": "n", "ः": "h"}
NUKTA = {c + "़": n for c, n in zip("कखगजडढफय", NUKTA_LETTERS)}  # base + dot -> the single codepoint
# Common words whose casual spelling the rules don't produce: the seed of the user's list in Settings,
# where English loanwords in Devanagari (प्रोजेक्ट) that come out phonetic can be fixed.
HINGLISH_WORDS = {"में": "mein", "मैंने": "maine", "हूँ": "hoon", "हूं": "hoon", "नहीं": "nahi", "यह": "yeh", "वह": "woh",
                  "वो": "woh", "ये": "ye", "अच्छा": "accha", "ठीक": "theek", "बात": "baat", "काम": "kaam", "नाम": "naam",
                  "साथ": "saath", "बाद": "baad", "कुछ": "kuch", "यूज": "use", "यूज़": "use", "ओके": "okay", "सही": "sahi", "ऑफिस": "office"}
# English words Claude's speech recognition writes in Devanagari when you mix them into Hindi; the rules alone
# would spell them by sound (वर्क -> vark). Added to existing users' lists in seed 2 (see settings.py).
LOANWORDS = {"वर्क": "work", "वर्क्स": "works", "वर्किंग": "working", "इज़": "is", "इज": "is", "इट": "it", "इट्स": "it's", "द": "the", "दिस": "this", "दैट": "that", "थिंक": "think", "यू": "you", "वी": "we", "एंड": "and", "फॉर": "for", "टू": "to", "ऑफ": "of", "ऑन": "on", "नॉट": "not", "कैन": "can", "विल": "will", "डू": "do", "डन": "done", "गुड": "good", "बैड": "bad", "थैंक्स": "thanks", "थैंक": "thank", "थैंक्यू": "thank you", "प्लीज़": "please", "प्लीज": "please", "सॉरी": "sorry", "हाय": "hi", "हेलो": "hello", "हैलो": "hello", "बाय": "bye", "यस": "yes", "टेस्ट": "test", "टेस्टिंग": "testing", "कोड": "code", "फाइल": "file", "फ़ाइल": "file", "ऐप": "app", "फ़ोन": "phone", "फोन": "phone", "मैसेज": "message", "मीटिंग": "meeting", "कॉल": "call", "टाइम": "time", "टीम": "team", "प्रोजेक्ट": "project", "इशू": "issue", "इश्यू": "issue", "फिक्स": "fix", "बग": "bug", "अपडेट": "update", "सर्वर": "server", "डेटा": "data", "डाटा": "data", "ईमेल": "email", "लिंक": "link", "चेक": "check", "सेंड": "send", "पुश": "push", "कमिट": "commit", "रिपो": "repo", "ब्रांच": "branch", "डिप्लॉय": "deploy", "रिव्यू": "review", "प्रॉब्लम": "problem", "सिस्टम": "system", "सेटिंग्स": "settings", "सेटिंग": "setting", "स्क्रीन": "screen", "विंडो": "window", "कीबोर्ड": "keyboard", "लैपटॉप": "laptop", "कंप्यूटर": "computer", "इंटरनेट": "internet", "ऑनलाइन": "online", "यूज़र": "user", "यूजर": "user", "स्ट्रीमिंग": "streaming", "लाइव": "live", "टाइप": "type", "टाइपिंग": "typing", "वॉइस": "voice", "वॉयस": "voice", "क्लॉड": "Claude", "स्टार्ट": "start", "स्टॉप": "stop", "बिल्ड": "build", "फीचर": "feature", "डिज़ाइन": "design", "डिजाइन": "design", "टास्क": "task", "डेडलाइन": "deadline", "क्लाइंट": "client", "कस्टमर": "customer", "मैनेजर": "manager", "वीक": "week", "वीकेंड": "weekend", "टुडे": "today", "टुमॉरो": "tomorrow", "नाउ": "now", "एक्चुअली": "actually", "बेसिकली": "basically", "बट": "but", "ऑलसो": "also", "जस्ट": "just", "रियली": "really", "नाइस": "nice", "ग्रेट": "great", "कूल": "cool", "परफेक्ट": "perfect", "वर्ड": "word", "वर्ड्स": "words", "करेक्ट": "correct", "रॉन्ग": "wrong", "राइट": "right", "स्पेलिंग": "spelling", "इंग्लिश": "English", "ऐम": "am", "वॉज़": "was", "वाज़": "was", "हैव": "have", "नो": "no", "वांट": "want", "नीड": "need", "मीन": "mean", "गेस": "guess", "होप": "hope", "फील": "feel", "सेड": "said"}
WORDS_SEED = 2
# आई is both English "I" and Hindi "came" (वो आई थी): it becomes "I" only before one of these.
AFTER_I = {"am", "think", "was", "will", "have", "had", "can", "know", "want", "need", "mean", "guess", "hope",
            "feel", "said", "just", "also", "really", "don't", "do", "did", "would", "should", "could"}


def normalize(word):
    """Dotted letters as single codepoints (ज़ typed as ज + ़ or as one character), so word lists match either."""
    for pair, single in NUKTA.items():
        word = word.replace(pair, single)
    return word


HINGLISH_WORDS = {normalize(k): v for k, v in {**HINGLISH_WORDS, **LOANWORDS}.items()}
LOANWORDS = {normalize(k): v for k, v in LOANWORDS.items()}
DEVANAGARI = re.compile("[ऀ-ॿ]")
DEVANAGARI_WORD = re.compile("[ऀ-ॣ॰-ॿ]+")


def hinglish_word(word, words=HINGLISH_WORDS):
    word = normalize(word)
    if word in words:
        return words[word]
    syllables = []  # [onset, vowel, coda, inherent 'a', open halant]
    for ch in word:
        cur = syllables[-1] if syllables else None
        if ch in CONSONANTS:
            if cur and cur[4]:  # after a halant: a consonant cluster
                cur[0] += CONSONANTS[ch]
                cur[4] = False
            else:
                syllables.append([CONSONANTS[ch], "a", "", True, False])
        elif ch == "्" and cur:  # halant: no vowel
            cur[1], cur[3], cur[4] = "", False, True
        elif ch in MATRAS and cur:
            cur[1], cur[3] = MATRAS[ch], False
        elif ch in SIGNS and cur:
            cur[2] += SIGNS[ch]
        elif ch in VOWELS:
            syllables.append(["", VOWELS[ch], "", False, False])
    # Hindi drops the inherent 'a' at the end of a word and in a VC_CV middle (करके -> karke, बोलता -> bolta),
    # judged right to left (समझना -> samajhna).
    if len(syllables) > 1 and syllables[-1][3] and not syllables[-1][2]:
        syllables[-1][1] = ""
    for i in range(len(syllables) - 2, 0, -1):
        s, prev, nxt = syllables[i], syllables[i - 1], syllables[i + 1]
        if s[3] and not s[2] and prev[1] and nxt[0] and nxt[1]:
            s[1] = ""
    return "".join(s[0] + s[1] + s[2] for s in syllables)


def hinglish(text, words=HINGLISH_WORDS):
    """`words`: Devanagari word -> how to type it, checked before the rules (the user's list in Settings)."""
    text = DEVANAGARI_WORD.sub(lambda m: hinglish_word(m.group(), words), text)
    text = re.sub(r"\baai(?= +(\w[\w']*))", lambda m: "I" if m.group(1).lower() in AFTER_I else "aai", text)
    return text.translate({0x964: ".", 0x965: ".", **{0x966 + d: str(d) for d in range(10)}})  # danda, digits
