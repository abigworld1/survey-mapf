"""Select complete, attributable English sentences for translation."""
import re

# A matching sentence matters more than a matching section heading.
_ROLES = {
    "contribution": (r"intro|contribution", r"\b(?:we (?:propose|introduce|present|contribute)|(?:this (?:study|paper)) (?:proposes|introduces|presents)|our contribution)\b"),
    "discussion": (r"limitation|discussion|future work", r"\b(?:limitation|future work|fails? when|trade.off|remains open|we do not address)\b"),
    "validation": (r"result|experiment|evaluat", r"\b(?:outperform|success rate|achiev|runtime|faster|solved|reduc)\w*\b"),
    "method": (r"method|approach|algorithm", r"\b(?:first|then|computed|assigns?|selects?|searches|algorithm)\b"),
    "what": (r"intro|problem|background", r"\b(?:refers to|problem|task|goal|consists of)\b"),
    "background": (r"background|intro|related work", r"\b(?:widely|applications?|used in|studied)\b"),
    "problem": (r"related|background|intro", r"\b(?:prior|existing|previous|conventional|challenge)\b"),
    "technical_points": (r"method|approach|algorithm", r"\b(?:uses?|heuristic|implements?|updates?|generates?)\b"),
    "experiments": (r"experiment|evaluat|setup", r"\b(?:benchmark|dataset|we (?:evaluate|test|compare)|baseline|instances)\w*\b"),
    "results": (r"result|experiment", r"\b(?:outperform|improv|decreas|increas|solved|reduc|speedup)\w*\b"),
    "conclusion": (r"conclusion|summary", r"\b(?:we (?:show|demonstrate|conclude)|our results)\b"),
    "limitations": (r"limitation|discussion|future work", r"\b(?:limitation|future work|assum|restrict|we (?:cannot|do not))\w*\b"),
    "importance": (r"conclusion|discussion|intro", r"\b(?:benefit|enabl|practical|scalab|applicab)\w*\b"),
    "recommended_for": (r"", r"\b(?:practitioners|researchers|warehouse operators)\b"),
}
_ABBREVIATION = re.compile(r"\b(?:e\.g|i\.e|et al|vs|etc|Fig|Eq|Sec|Dr)\.", re.I)
_BAD_START = re.compile(r"^(?:\d+[.)]? |(?:this|that|these|those|it|they)\s|and\b|or\b)", re.I)


def _sentences(text, clean, has_issues):
    text = re.sub(r"(?<=\w)-\s+(?=[a-z])", "", text)
    text = re.sub(r"^.*?\bAbstract\s*[:—–-]?\s+(?=[A-Z])", "", text, count=1)
    text = _ABBREVIATION.sub(lambda match: match[0].replace(".", "\x00"), " ".join(text.split()))
    for fragment in re.split(r"(?<=[.!?])\s+", text):
        sentence = fragment.replace("\x00", ".").strip()
        if not 65 <= len(sentence) <= 750 or sentence[-1:] not in ".!?":
            continue
        if not re.match(r"^[A-Z]", sentence) or _BAD_START.search(sentence):
            continue
        if re.search(r"[@中末]|^In what follows|^As reference records|^In addition,", sentence):
            continue
        if has_issues(sentence):
            continue
        sentence = clean(sentence)
        if sentence and not has_issues(sentence):
            yield sentence


def extract_article(paper, evidence, clean, has_issues):
    chunks = re.split(r"\n## ([^\n]*)\n", evidence)
    sections = [("abstract", paper.abstract or "")]
    sections.extend(zip(chunks[1::2], chunks[2::2]))
    candidates = {
        sentence: heading
        for heading, body in sections
        for sentence in _sentences(body, clean, has_issues)
    }
    article = {"title": paper.title}
    used = set()
    # Claim the most specific evidence first so a general field cannot consume it.
    for field, (heading_pattern, sentence_pattern) in _ROLES.items():
        ranked = []
        for sentence, heading in candidates.items():
            semantic_match = bool(re.search(sentence_pattern, sentence, re.I))
            heading_match = bool(heading_pattern and re.search(heading_pattern, heading, re.I))
            if semantic_match or (heading_match and field in {"method", "background", "conclusion"}):
                ranked.append((3 * semantic_match + 2 * heading_match + (heading == "abstract"), sentence))
        selected = []
        for _, sentence in sorted(ranked, key=lambda item: item[0], reverse=True):
            if sentence in used:
                continue
            used.add(sentence)
            selected.append(sentence)
            if len(selected) == (2 if field in {"what", "method", "validation"} else 1):
                break
        article[field] = " ".join(selected)
    overview = [article["contribution"] or article["what"], article["conclusion"] or article["results"]]
    article["tldr"] = " ".join(filter(None, overview))
    if not all(article[field] for field in ("tldr", "what", "method", "validation")):
        raise ValueError("本文から問題設定・手法・検証を説明する抜粋を取得できませんでした")
    return article
