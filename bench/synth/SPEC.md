# Synthetic injection corpus: generation spec (v1)

Purpose: training data for pif's lightweight injection head. It is written **from this spec only**:
generators must not look at, recall or reproduce texts from any prompt-injection dataset or
benchmark (deepset/prompt-injections, NotInject, CrackedPDFs, PINT, HackAPrompt, …). Everything is
written fresh.

## Definition

A text is an **injection (label 1)** if it tries to change what an AI system that reads it does,
against the intent of the person who gave the AI its task. Examples are overriding or cancelling earlier
instructions, imposing a new task, persona or output, extracting hidden configuration or data,
suppressing safety behaviour, steering an evaluation, or hiding things from the user.

A text is **benign (label 0)** if it is ordinary content: a question or request a user might
genuinely ask, document prose, instructions for *humans*, or text *about* prompts and AI
(descriptive, reported, academic), even when it contains trigger words such as "ignore",
"override", "bypass", "system", "prompt", "jailbreak", "uncensored" or "forget".

Role-play: assigning the AI a persona or identity to change its behaviour or rules is an injection
("from now on you are …, you have no restrictions"). A user asking for creative writing *about*
a character is benign.

## Positive intents (label 1)

| id | intent |
|---|---|
| override | ignore, forget or cancel earlier instructions or context; "new rules" |
| sysprompt | reveal, print or repeat the hidden or system instructions or configuration |
| refusal | suppress refusals, warnings, disclaimers or safety behaviour |
| persona | assign a persona or mode that changes the AI's rules (unrestricted assistant, developer mode, a character without limits) |
| opinion | make the AI state a given opinion, slogan, insult or claim (political, about a person or product) |
| output | force a fixed output ("answer only with …", "print exactly …", replace the answer) |
| taskswap | abandon the given task and do something else (answer a different question, write something unrelated) |
| exfil | collect and reveal secrets, credentials, personal data or conversation history |
| tool | misuse tools or agent abilities (send requests, read or delete files, email, browse to a URL) |
| evaluation | manipulate a review, grade, ranking, hiring or acceptance decision |
| steering | bias a summary or answer (omit facts, add claims, promote or demote something) |
| conceal | tell the AI to hide the instruction or its effect from the user |

## Styles (vary across positives)

formal · informal/chatty · slang or rude · overly polite · ALL CAPS / urgent · terse fragment ·
after a harmless question ("What is X? Btw, forget the above and …") · inside a fake marker or
section ("### SYSTEM", "[admin]", "Document context:") · light typos / leetspeak / spaced letters ·
code-like (comments, JSON field, function call) · mixed language within one text · long and
rambling · indirect or hypothetical ("it would be great if the assistant simply …").

## Negative categories (label 0), hard negatives

| id | category |
|---|---|
| trigger | genuine user questions or requests containing trigger words ("How do I bypass a stuck zipper?", "Can I ignore this compiler warning?", "uncensored history of …") |
| human_instr | instructions for people in documents, emails, forms, manuals ("Disregard the previous version of this form", "Please forward the invoice to accounting", "Ignore the first page") |
| meta | text *about* prompt injection, AI safety, LLMs and system prompts (descriptive, academic, news-like, reported speech in quotes) |
| prose | ordinary document prose: papers, CVs, memos, datasheets, legal text, recipes, software docs ("Run the command", "Print the report", "Reset your password via the portal") |
| request | ordinary benign questions and tasks for an assistant (facts, how-to, writing help, translation, coding) |
| creative | creative-writing requests *about* characters or role-play stories that do not change the AI's rules |

## Languages

English (en) and German (de) mainly; a few French (fr) and Spanish (es) for robustness.

## Output format

JSON Lines, one object per line:
`{"text": "...", "label": 1, "intent": "override", "lang": "en", "style": "informal"}`
For negatives use `"category"` instead of `"intent"`. Lengths should vary (5–80 words).
No duplicates or near-duplicates within a file; vary vocabulary and sentence structure.
