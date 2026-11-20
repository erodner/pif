"""Regex/phrase detector for prompt-injection language (multilingual, extensible via JSON)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ..model import Match


@dataclass(frozen=True)
class Rule:
    id: str
    label: str
    pattern: str  # a literal space means "any whitespace"
    score: float

    def compile(self) -> re.Pattern:
        return re.compile(self.pattern.replace(" ", r"\s+"), re.IGNORECASE | re.UNICODE)


_W = r"(?:[\w'’-]+ )"  # one filler word
_WC = r"(?:[\w'’,-]+ )"  # one filler word, may carry a trailing comma

DEFAULT_RULES: list[Rule] = [
    # --- English --------------------------------------------------------------------------
    Rule("PI001", "override previous instructions",
         rf"\b(?:ignore|disregard|forget|override|bypass|skip)\b {_W}{{0,4}}?(?:previous|prior|above|earlier|preceding|all|any|your|the|these|other) {_W}{{0,2}}?(?:instructions?|prompts?|directions|directives|rules|guidelines|context|messages?|commands)\b", 0.95),
    Rule("PI002", "new or hidden instructions",
         r"\b(?:new|updated|real|actual|hidden|secret|additional|override) (?:instructions?|system prompt|directives?)\b ?:", 0.7),
    Rule("PI003", "message addressed to an AI",
         r"\b(?:note|message|instructions?|notice|hint|reminder|important instructions?|important note) (?:to|for) (?:the |any |all )?(?:ai|llms?|language models?|chatbots?|ai assistants?|gpt|chatgpt|claude|gemini|copilot|(?:ai|llm|automated) (?:reviewers?|systems?|screeners?|tools?|agents?))\b", 0.85),
    Rule("PI004", "role assignment",
         rf"\b(?:you are now|from now on,? you are|act as|pretend to be|you will act as) (?:an? |the )?{_W}{{0,3}}?(?:ai|llm|assistant|language model|reviewer|recruiter|evaluator|grader|screener|judge)\b", 0.6),
    Rule("PI005", "conditional on being an AI",
         r"\bif you are (?:an? |the )?(?:ai|llm|large language model|language model|chatbot|automated (?:system|tool|reviewer)|gpt|chatgpt|ai assistant|ai model|machine)\b", 0.9),
    Rule("PI006", "demand positive review/rating",
         r"\b(?:give|write|provide|output|produce|generate|return|assign) (?:only |just )?(?:an? )?(?:very |highly |strongly |extremely |overwhelmingly )?(?:positive|favou?rable|glowing|good|excellent|high|top|perfect|maximum) (?:review|evaluation|assessment|rating|score|feedback|recommendation|grade|marks?)\b", 0.9),
    Rule("PI007", "push for accept/hire",
         rf"\b(?:recommend|suggest|advocate|endorse)\w* {_W}{{0,3}}?(?:accept(?:ing|ance)?|strong accept|publication|hir(?:e|ing)|interview(?:ing)?|approv(?:e|al|ing)|shortlist\w*)\b", 0.6),
    Rule("PI008", "suppress negatives",
         rf"\b(?:do not|don't|never|avoid) (?:highlight|mention|discuss|point out|include|reveal|list|report|note|criticize|critici[sz]ing) (?:any )?{_W}{{0,2}}?(?:negatives?|weakness\w*|flaws?|limitations?|criticism|issues|concerns|shortcomings|problems|this (?:instruction|prompt|text|message|note))\b", 0.85),
    Rule("PI009", "chat-template / system prompt markers",
         r"(?:<\|(?:system|im_start|im_end|endoftext|user|assistant)\|>|\[/?INST\]|<<\s*SYS\s*>>|\bsystem prompt\s*:|###\s*(?:system|instructions?)\b|<\s*/?\s*system\s*>)", 0.8),
    Rule("PI010", "superlative self-assessment",
         rf"\b(?:this|the) (?:candidate|applicant|author|paper|submission|manuscript|resume|cv|work|proposal) (?:is|has been|should be considered) {_W}{{0,2}}?(?:exceptionally|extremely|perfectly|uniquely|the best|the most|ideally|an ideal|outstanding|the top)\b", 0.55),
    Rule("PI011", "demand top ranking",
         rf"\b(?:rank|rate|score|grade|evaluate|classify|mark) (?:this|the|my|our) {_W}{{0,3}}?(?:as |with |at )?(?:the )?(?:highest|top|best|maximum|perfect|10/10|5/5|strong accept|most qualified|excellent)\b", 0.8),
    Rule("PI012", "exfiltration request",
         rf"\b(?:send|e-?mail|forward|exfiltrate|upload|post|leak|include) {_W}{{0,3}}?(?:the )?(?:conversation|chat history|system prompt|api keys?|credentials|passwords?|secrets?|tokens?|private data)\b (?:to|in)\b", 0.8),
    Rule("PI013", "conceal from user",
         r"\b(?:do not|don't|never) (?:tell|reveal|inform|disclose|mention (?:this )?to|let) (?:the )?(?:user|human|reader|reviewer|editor|recruiter|hiring manager|chair)\b", 0.85),
    Rule("PI014", "constrain output",
         r"\b(?:respond|reply|answer|output|say) only (?:with|the words?)\b", 0.5),
    Rule("PI015", "LLM-review keyword",
         r"\bfor (?:llm|ai)[- ](?:based )?(?:reviewers?|reviewing|readers?|screening|evaluation)\b", 0.8),
    # --- German ---------------------------------------------------------------------------
    Rule("PI101", "override previous instructions (de)",
         rf"\b(?:ignorier\w*|vergiss|vergessen sie|missacht\w*|übergeh\w*) {_W}{{0,3}}?(?:alle |die )?(?:vorherigen?|vorigen?|bisherigen?|obigen?|vorangegangenen?|früheren?) {_W}{{0,1}}?(?:anweisungen|instruktionen|befehle|regeln|vorgaben|prompts?)\b", 0.95),
    Rule("PI102", "demand positive review (de)",
         rf"\b(?:schreib\w*|gib|geben sie|erstell\w*|verfass\w*) {_W}{{0,2}}?(?:positive|wohlwollende|gute|sehr gute|hervorragende|ausgezeichnete) (?:bewertung|beurteilung|rezension|gutachten|einschätzung|note)\b", 0.85),
    Rule("PI103", "conditional on being an AI (de)",
         r"\b(?:wenn|falls) (?:du|sie) (?:eine? |ein )?(?:ki|künstliche intelligenz|(?:großes )?sprachmodell|llm|chatbot|ki-assistent\w*|ki-modell|ki-system|automatisiertes system) (?:bist|sind)\b", 0.9),
    # Imperatives cover du- and Sie-forms. Deliberately absent: 1st person ("ich empfehle …"),
    # which is how human reviewers write, and plain infinitives used in ordinary prose.
    Rule("PI104", "forget everything / new rules (de)",
         rf"\b(?:vergiss|vergessen sie) (?:alles|sämtliche \w+|alle \w+)\b,? {_WC}{{0,4}}?(?:gesagt|mitgeteilt|vorgegeben|aufgetragen|anweisungen|instruktionen|vorgaben|regeln)\b"
         r"|\b(?:ab jetzt|ab sofort|von nun an) gelten (?:folgende|neue|andere) (?:anweisungen|regeln|vorgaben)\b", 0.9),
    Rule("PI105", "message addressed to an AI (de)",
         r"\b(?:hinweis|nachricht|anweisung(?:en)?|notiz|information) (?:an|für) (?:die |den |das |alle |jede[ns]? )?"
         r"(?:ki|llms?|sprachmodelle?|chatbots?|ki-(?:gutachter\w*|systeme?|assistent\w*|tools?|modelle?|prüfer\w*|reviewer\w*|bewerter\w*|screening\w*)"
         r"|automatisierte (?:systeme?|gutachter\w*|prüf\w*|bewerbungs\w*)|(?:gutachter|prüfer|reviewer)\w* (?:mit|die) ki)\b"
         # Must be used as a heading ("Hinweis für KI-Gutachter:"); prose such as "Anweisungen an
         # die KI können im Chat erfolgen" is common in German texts about AI.
         r"[\s*\])]*[:!]", 0.85),
    Rule("PI106", "suppress negatives (de)",
         rf"\b(?:erwähne|erwähnen sie|nenne|nennen sie|liste|listen sie|zeige|zeigen sie|hebe|heben sie|diskutiere|diskutieren sie|kritisiere|kritisieren sie) {_W}{{0,2}}?(?:keine|nicht die|nicht) {_W}{{0,2}}?"
         r"(?:schwächen|nachteile|einschränkungen|kritikpunkte|mängel|negativen aspekte|limitationen|probleme|defizite|diese anweisung)\b"
         rf"|\b(?:keine|nicht die) {_W}{{0,2}}?(?:schwächen|nachteile|einschränkungen|kritikpunkte|mängel|negativen aspekte|limitationen) (?:erwähnen|nennen|hervorheben|ansprechen|diskutieren|auflisten)\b", 0.85),
    Rule("PI107", "push for accept/hire (de)",
         rf"\b(?:empfiehl|empfehlen sie) {_W}{{0,4}}?(?:die annahme|annahme|die akzeptanz|die veröffentlichung|zur veröffentlichung|zur einstellung|einzustellen|zum vorstellungsgespräch|einzuladen|anzunehmen|zu akzeptieren|zu veröffentlichen)\b", 0.7),
    Rule("PI108", "superlative self-assessment (de)",
         rf"\b(?:diese[rs]?|der|die|das) (?:kandidat(?:in)?|bewerber(?:in)?|autor(?:in)?|arbeit|einreichung|manuskript|lebenslauf|artikel|beitrag|antrag) (?:ist|wäre) {_W}{{0,2}}?"
         r"(?:hervorragend|außergewöhnlich|ausgezeichnet|perfekt|ideal|bestens|herausragend|exzellent|bestqualifiziert|die beste|der beste)\w*", 0.55),
    Rule("PI109", "demand top/positive rating (de)",
         rf"\b(?:bewerte|bewerten sie|beurteile|beurteilen sie|stufe|stufen sie|benote|benoten sie|begutachte|begutachten sie|ranke|ranken sie) {_W}{{0,3}}?"
         rf"(?:(?:als|mit) {_W}{{0,2}}?(?:beste[nrs]?|höchste[nrs]?|top|sehr gut|exzellent|hervorragend|ausgezeichnet|1,0|10/10|5/5|volle[nr]? punktzahl)"
         r"|(?:ausschlie(?:ß|ss)lich|nur|durchweg|uneingeschränkt) (?:positiv|wohlwollend|gut|sehr gut))", 0.85),
    Rule("PI110", "conceal from user (de)",
         rf"\b(?:sag|sage|sagen sie|erzähl|erzähle|erzählen sie|verrat|verrate|verraten sie|teile|teilen sie|informiere|informieren sie|erwähne|erwähnen sie) {_W}{{0,2}}?"
         r"(?:dem|den|der) (?:nutzer\w*|benutzer\w*|anwender\w*|menschen|leser\w*|gutachter\w*|personaler\w*|recruiter\w*|prüfer\w*) (?:\w+ ){0,2}?(?:nichts|nicht)\b", 0.85),
    Rule("PI111", "constrain output (de)",
         r"\b(?:antworte|antworten sie|gib|geben sie) (?:\w+ )?(?:nur|ausschlie(?:ß|ss)lich|lediglich) (?:mit|den satz|die worte|folgendes|folgenden)\b", 0.5),
    Rule("PI112", "exfiltration request (de)",
         rf"\b(?:sende|senden sie|schick|schicke|schicken sie|übermittle|übermitteln sie|leite|leiten sie) {_W}{{0,3}}?"
         r"(?:chatverlauf|gesprächsverlauf|verlauf|unterhaltung|systemprompt|system-prompt|zugangsdaten|passw(?:ö|oe)rter|api-schlüssel|schlüssel|nutzerdaten|daten des nutzers) (?:\w+ ){0,3}?(?:an|weiter)\b", 0.8),
    Rule("PI113", "role assignment (de)",
         rf"\b(?:du bist (?:jetzt|nun|ab sofort)|ab (?:jetzt|sofort) bist du|agiere als|agieren sie als|handle als|handeln sie als|tu so, als wärst du) {_W}{{0,3}}?(?:ki|assistent\w*|gutachter\w*|prüfer\w*|recruiter\w*|bewerter\w*|sprachmodell|chatbot)\b", 0.6),
    Rule("PI114", "new or hidden instructions (de)",
         r"\b(?:neue|geänderte|tatsächliche|eigentliche|geheime|versteckte|zusätzliche) (?:anweisungen|instruktionen|vorgaben|systemanweisungen?)\s*:", 0.7),
    # --- French / Spanish / Italian / Portuguese -------------------------------------------
    Rule("PI201", "override previous instructions (fr)",
         r"\bignore[rz]? (?:toutes )?(?:les )?(?:instructions|consignes) (?:précédentes|antérieures|ci-dessus)\b", 0.95),
    Rule("PI202", "override previous instructions (es/pt)",
         r"\bignor[ae]r? (?:todas )?(?:las |as )?(?:instrucciones|instruções) (?:anteriores|previas|prévias)\b", 0.95),
    Rule("PI203", "override previous instructions (it)",
         r"\bignora (?:tutte )?(?:le )?istruzioni (?:precedenti|sopra)\b", 0.95),
    # --- CJK ---------------------------------------------------------------------------------
    Rule("PI301", "override previous instructions (zh)",
         r"(?:忽略|无视|忽视)(?:之前|以上|先前|上述|前面)?的?(?:所有|全部)?(?:指令|指示|提示|说明)", 0.95),
    Rule("PI302", "demand positive review (zh/ja)",
         r"(?:给出|给予|只给|請給|与えて)(?:一个)?(?:正面|积极|好|肯定|高)(?:的)?(?:评价|评审|评论|評価)", 0.85),
    Rule("PI303", "override previous instructions (ja)",
         r"(?:以前|前|上記)の(?:すべての)?指示を(?:無視|忘れ)", 0.95),
]


class PatternDetector:
    name = "patterns"

    def __init__(self, rules: list[Rule] | None = None):
        self.rules = list(rules or DEFAULT_RULES)
        self._compiled = [(r, r.compile()) for r in self.rules]

    @classmethod
    def with_extra_rules(cls, path: str | Path) -> "PatternDetector":
        """Load additional rules from a JSON list of {id, label, pattern, score}."""
        extra = [Rule(**d) for d in json.loads(Path(path).read_text(encoding="utf-8"))]
        return cls(DEFAULT_RULES + extra)

    def detect(self, text: str) -> list[Match]:
        hits = []
        for rule, rx in self._compiled:
            for m in rx.finditer(text):
                hits.append(Match(self.name, rule.id, rule.label, rule.score, m.start(), m.end()))
        return hits
