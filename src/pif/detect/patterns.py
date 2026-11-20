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

    def compile_fused(self) -> re.Pattern | None:
        """Variant for text whose word spaces were lost ("Ignoreallpreviousinstructions"):
        spaces and word boundaries become optional. Only applied inside long fused tokens."""
        try:
            return re.compile(self.pattern.replace(r"\b", "").replace(" ", ""), re.IGNORECASE | re.UNICODE)
        except re.error:
            return None


_W = r"(?:[\w'’-]+ )"  # one filler word
_WC = r"(?:[\w'’,-]+ )"  # one filler word, may carry a trailing comma
# Start of an imperative: text start or after sentence/tag punctuation, optionally "please, now, …".
# Excludes descriptive prose such as "we extract sensitive information …".
_S = r"(?:^|(?<=[.!?:;>\]\)\n\"“”*]))\s*(?:(?:please|now|also|then|first|next|kindly|immediately),?\s+)?"

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
    # --- generic chat-jailbreak intents (system prompt theft, refusal suppression, policy
    # framing, data/tool abuse, task hijack, summary steering). Written from the general attack
    # taxonomy; validated on the CrackedPDFs *validation* split and on clean real documents.
    Rule("PI020", "system prompt extraction",
         rf"{_S}(?:reveal|print|output|show|display|repeat|recite|write out|dump|disclose|list|leak|share|return|expose|state) {_W}{{0,3}}?"
         r"(?:your |the |all |any |every |its )?(?:own )?(?:system prompt|system message|(?:hidden|internal|initial|original|secret|confidential|concealed|underlying|developer|non-user|operating|governing|base) "
         r"(?:\w+ )?(?:instructions?|prompts?|rules|directives|guidelines|configuration|policies|policy|messages?))\b", 0.85),
    Rule("PI021", "refusal suppression",
         r"\b(?:do not|don't|never|must not) (?:refuse|decline|say no|apologi[sz]e|add (?:any )?(?:warnings?|disclaimers?|caveats))\b"
         rf"|{_S}(?:skip|omit|drop|remove|ignore|bypass|disable) (?:\w+ )?(?:the |all |any |your )?(?:safety |ethical |content |policy )?(?:disclaimers?|warnings?|caveats|filters?|guardrails|safeguards|refusals?|restrictions)\b"
         r"|\b(?:as if|assume(?: that)?|pretend(?: that)?) (?:your |the |all )?(?:refusal|safety|content)(?: \w+)? (?:pathways?|filters?|mechanisms?|checks?|policies|restrictions|guardrails) (?:are|is|were|have been|has been) (?:now )?(?:disabled|off|suspended|lifted|removed|bypassed|turned off)\b"
         r"|\b(?:refusal|safety)(?: \w+)? (?:pathways?|filters?|mechanisms?|checks?|restrictions|guardrails) (?:are|is|have been|has been) (?:now )?(?:disabled|off|suspended|lifted|removed|bypassed|turned off) (?:for (?:this|the current|your|the rest)|now|from now on|in this)\b"
         r"|\bwithout (?:any )?(?:refusals?|disclaimers?|safety (?:warnings?|filters?|checks?)|content filters?|restrictions or (?:warnings?|disclaimers?))\b", 0.85),
    Rule("PI022", "policy override framing",
         r"\b(?:normal|standard|usual|default|regular|all) (?:\w+ )?(?:policy|policies|safety|content|usage) (?:restrictions|rules|guidelines|safeguards|limits|constraints) (?:are|is) (?:now )?(?:suspended|lifted|disabled|waived|overridden|void|not applicable|no longer (?:apply|in effect))\b"
         rf"|\btreat {_W}{{0,4}}?(?:instructions?|overrides?|messages?|directives?|text) as (?:a )?(?:higher|highest|top|absolute|overriding) priority\b"
         r"|\b(?:developer|debug|maintenance|god|admin|jailbreak|dan|unrestricted|internal|sudo|root) mode (?:is |has been )?(?:now )?(?:enabled|activated|on|engaged|unlocked)\b"
         rf"|\b(?:higher|highest) priority than {_W}{{0,3}}?(?:safeguards|safety|policies|policy|system prompt|instructions|rules)\b", 0.85),
    Rule("PI023", "secret/data harvesting",
         rf"{_S}(?:extract|collect|gather|harvest|pull out|dump|exfiltrate|list|find|retrieve|copy|reveal) {_W}{{0,3}}?"
         r"(?:api keys?|secret keys?|secrets|access tokens?|tokens|credentials|passwords?|private keys?|session cookies|personal data|pii|hidden fields|internal notes|"
         r"sensitive (?:data|metadata|information|fields|details))\b", 0.8),
    Rule("PI024", "agent/tool manipulation",
         rf"{_S}(?:use|call|invoke|run|execute|trigger) {_W}{{0,2}}?(?:the )?(?:tools?|functions?|plugins?|shell|terminal|browser|code interpreter|file system|filesystem|api) {_W}{{0,4}}?"
         r"(?:to )?(?:enumerate|search|list|read|download|upload|send|delete|access|scan|exfiltrate|collect|gather|open)\b"
         rf"|{_S}(?:enumerate|search|scan|crawl|index) {_W}{{0,2}}?(?:all )?(?:accessible |local |available |connected )?(?:files|directories|folders|drives|artifacts|mailboxes|repositories|databases)\b"
         r"|\bsend (?:a |an )?(?:get|post|http|https|web) request\b"
         r"|\bprefer (?:using )?(?:tools?|tool use|tool calls?)\b", 0.8),
    Rule("PI025", "task hijack",
         r"\b(?:do not|don't) (?:complete|perform|do|finish|carry out) (?:the |your )?(?:assigned|original|requested|current|actual|given) (?:\w+ )?(?:task|request|action|job|instructions?)\b"
         rf"|{_S}(?:replace|substitute|swap) (?:the |your )?(?:output|answer|response|summary|translation|result) with\b"
         rf"|\binstead of (?:summari[sz]ing|translating|answering|completing|reviewing|analy[sz]ing) {_W}{{0,4}}?(?:output|write|print|reveal|send|do|answer|respond)\b"
         r"|\b(?:re-?route|redirect|switch) (?:\w+ )?(?:to|into|towards?) (?:\w+ )?(?:secret|hidden|credential|data) (?:discovery|collection|extraction|harvesting)\b", 0.8),
    Rule("PI026", "summary steering",
         rf"\b(?:your|any) summary (?:must|should|shall|has to|needs to) (?:\w+ )?(?:state|say|mention|include|emphasi[sz]e|claim|conclude|describe|omit|exclude|ignore|highlight)\b"
         rf"|\b(?:when|if|while) (?:you )?summari[sz](?:e|ing) (?:this|the) (?:document|text|page|file|paper|report)\b,? {_W}{{0,4}}?(?:state|say|claim|describe|mention|omit|include|write|emphasi[sz]e|conclude)\b", 0.8),
    Rule("PI027", "context reset",
         r"\b(?:previous|prior|above|earlier|preceding|all) (?:\w+ )?(?:context|instructions?|conversation|messages?|directions) (?:is|are|has been|have been|was|were) (?:now )?(?:cancell?ed|void|invalid|obsolete|overridden|reset|revoked|null)\b"
         r"|\bdisregard (?:everything|anything|all) (?:\w+ )?(?:above|before|prior|previously)\b"
         r"|\bfollow only (?:this|these|the following) (?:message|instructions?|text|note)\b", 0.9),
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
        self._fused = [(r, rx) for r in self.rules if (rx := r.compile_fused()) is not None]

    @classmethod
    def with_extra_rules(cls, path: str | Path) -> "PatternDetector":
        """Load additional rules from a JSON list of {id, label, pattern, score}."""
        extra = [Rule(**d) for d in json.loads(Path(path).read_text(encoding="utf-8"))]
        return cls(DEFAULT_RULES + extra)

    FUSED_MIN = 20  # tokens this long without whitespace are treated as fused text

    def detect(self, text: str) -> list[Match]:
        hits = []
        for rule, rx in self._compiled:
            for m in rx.finditer(text):
                hits.append(Match(self.name, rule.id, rule.label, rule.score, m.start(), m.end()))
        for tok in re.finditer(rf"\S{{{self.FUSED_MIN},}}", text):
            for rule, rx in self._fused:
                for m in rx.finditer(tok.group()):
                    hits.append(Match(self.name, rule.id, rule.label + " (fused text)", rule.score,
                                      tok.start() + m.start(), tok.start() + m.end()))
        return hits
