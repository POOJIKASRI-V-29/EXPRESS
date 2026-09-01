"""What is the user actually asking for?

This runs *before* any tool is chosen, and it exists because the previous
behaviour was indefensible: the planner fell through to `create_task` for
anything it didn't recognise, so "how are you", "I'm tired" and "thanks" each
silently created a task.

The governing rule here is that **creating a record is opt-in, not the
default**. A message becomes a write only when it reads as an instruction to
change something. Everything else is conversation, a question, or — when it
genuinely could be an instruction but is too vague to act on — a request for
clarification. Guessing wrong costs the user a junk row they have to find and
delete; asking costs one sentence.
"""
import re
from enum import Enum


class Intent(str, Enum):
    CONVERSATION = "conversation"    # greetings, small talk, acknowledgements
    QUESTION = "question"            # asking about EXPRESS data
    READ = "read"                    # explicit lookup
    SUGGESTION = "suggestion"        # "what should I do" — advice, not a write
    PLANNING = "planning"            # "plan my day" — propose a schedule
    CREATE = "create"
    EDIT = "edit"                    # change an existing record
    RESCHEDULE = "reschedule"        # move something in time
    DELETE = "delete"
    COMPLETE = "complete"
    ATTENDANCE = "attendance"
    LEARNING = "learning"
    MEMORY = "memory"
    LOG = "log"                      # reporting something that already happened
    TIMETABLE = "timetable"          # importing or replacing a timetable
    CLARIFY = "clarify"              # plausibly an instruction, too vague to act
    UNKNOWN = "unknown"


#: Intents that may write. Anything else must not reach a mutating tool.
WRITE_INTENTS = {Intent.CREATE, Intent.EDIT, Intent.RESCHEDULE, Intent.DELETE,
                 Intent.COMPLETE, Intent.ATTENDANCE, Intent.LEARNING, Intent.MEMORY,
                 Intent.LOG, Intent.TIMETABLE}

# ---------------------------------------------------------------- patterns
# Ordered: the first match wins, so the more specific patterns come first.

_GREET_WORD = (r"(?:hey|hi|hello|yo|hiya|heya|"
               r"good\s+(?:morning|afternoon|evening|night))")
# A greeting on its own.
GREETING = re.compile(rf"^{_GREET_WORD}\b(\s+(?:jocasta|joc|there|mate))?\s*[!.?]*$")
# A greeting used as an opener: "hey jocasta, how are you?". Stripped so the
# rest of the sentence is classified on its own merits — without this, the
# greeting prefix made the whole message look like a question and it fell
# through to "I'm not sure what to do with that".
GREETING_PREFIX = re.compile(
    rf"^{_GREET_WORD}\b(\s+(?:jocasta|joc|there|mate))?\s*[,.!—-]*\s*")

# Speech recognition mangles "JOCasta" constantly — real transcripts have
# included "Ja Costa", "Da Costa", "jacosta" and "Jata". The address can't be a
# fixed list, so a short message that *ends* in unmistakable small talk is
# treated as small talk whatever precedes it. Guarded to short messages with no
# action verb, so "hey jocasta add a task" is unaffected.
TRAILING_SMALL_TALK = re.compile(
    r"\b(how (are|r) (you|u)( doing| today| going)?|how'?s it going|"
    r"what'?s up|whats up|you (ok|okay|alright|good))\s*[!.?]*$")

SMALL_TALK = re.compile(
    r"^(how (are|r) (you|u)( doing| today| going)?|how'?s it going|how goes it|"
    r"what'?s up|whats up|sup|you (ok|okay|alright|good)|"
    r"who are you|what are you|what can you do|are you (there|awake|ok|working))"
    r"(\s+(jocasta|joc|mate|then))?\s*[!.?]*$")

_ACK_WORD = (r"(?:thanks|thank you|ta|cheers|ok|okay|k|cool|nice|great|"
             r"got it|sure|never ?mind|nvm|no|nope|yes|yeah|yep|alright|"
             r"perfect|awesome|lovely|brilliant)")
# Short acknowledgements often arrive stacked — "ok cool", "yeah thanks".
ACKNOWLEDGEMENT = re.compile(rf"^{_ACK_WORD}(\s+{_ACK_WORD}){{0,2}}\s*[!.?]*$")

# Sign-offs. Conversation, not instructions — and answered with a send-off
# rather than a list of what is still outstanding.
FAREWELL = re.compile(
    r"^(good ?night|night( night)?|nighty night|bye( bye)?|goodbye|"
    r"see (you|ya)( later| tomorrow)?|later|catch you later|"
    r"i'?m off|signing off|that'?s me( done)?|done for (today|the day|now))"
    r"(\s+(jocasta|joc|mate))?\s*[!.?]*$")

FEELING = re.compile(
    r"\b(i'?m|i am|im|feeling|feel)\s+(so |really |a bit |quite |very )?"
    r"(tired|exhausted|knackered|shattered|sleepy|stressed|anxious|"
    r"overwhelmed|burnt ?out|burned ?out|bored|lost|stuck|sad|low|down|"
    r"fine|good|great|ok|okay|alright)\b")

# "What should I ..." is advice, never a write.
SUGGESTION = re.compile(
    r"\b(what should i|should i|what'?s worth|any(thing)? (i should|worth)|"
    r"recommend|suggest|what next|what would you (do|suggest))\b")

PLANNING = re.compile(
    r"\b(plan my|plan the|fix my day|sort (out )?my|organi[sz]e my|"
    r"make me a (plan|schedule)|help me plan|catch up on|i'?m behind|"
    r"reschedule everything|rebalance)\b")

# Free-time statements are an invitation to advise, not to book.
FREE_TIME = re.compile(
    r"\b(i have|i've got|i got|there'?s)\s+(an?\s+)?[\w.]+\s*"
    r"(hours?|hrs?|minutes?|mins?)\s+(free|spare|left|to kill)\b"
    r"|\bfree (tonight|today|tomorrow|this evening|after)\b")

QUESTION_WORD = re.compile(r"^(what|when|where|which|who|how|why|is|are|do|does|did|can|could|will)\b")

READ = re.compile(
    r"\b(what'?s (on|due|urgent|next|left)|what is (due|on|urgent|next|left)|"
    r"what do i have|show me|list|"
    r"my (schedule|tasks|day|week|plan|goals|habits|projects|courses|memories)|"
    r"how (is|are|am) (my|i)\b|how many|what am i behind on|"
    r"what do you remember|remind me what)\b")

#: "Add X to my courses" is an instruction, not a lookup — but READ matches the
#: trailing "my courses" and is checked first. Narrow on purpose: it needs a
#: leading create verb AND "to my <collection>", so "what courses do I have"
#: is untouched.
ADD_TO_COLLECTION = re.compile(
    r"^\s*(?:jocasta[,\s]+)?(?:please\s+)?(?:add|create|new)\b.+"
    r"\bto (?:my|the) (?:courses|course list|planner|tasks|goals|projects|habits)\b")

DELETE = re.compile(
    r"\b(delete|remove|cancel|get rid of|scrap|drop|clear)\b")

RESCHEDULE = re.compile(
    r"\b(move|push|shift|reschedul\w*|postpone|bump|bring forward|"
    r"make (it|that) (\d|noon|midnight)|change .* to (\d|noon))\b")

EDIT = re.compile(
    r"\b(rename|change (the )?(title|name|time|date|duration|category)|"
    r"edit|update|set .* to|actually (make|call) it)\b")

COMPLETE = re.compile(
    r"\b(i (just )?(finished|completed|did|wrapped up)|mark .* (as )?(done|complete)|"
    r"tick off|check off|done with|finished)\b")

ATTENDANCE = re.compile(
    r"\b(attended|went to|was (in|at)|missed|skipped|bunked|didn'?t go)\b")

MEMORY = re.compile(
    r"\b(remember\b|note that|make a note|jot down|keep in mind|"
    r"don'?t forget that|i prefer|for future reference)\b")

CREATE = re.compile(
    r"\b(add|create|schedule|book|set up|put .* (on|in)|new |make a |"
    r"remind me to|block out|pencil in|my goal is|i want to)\b")

# Importing a timetable. Checked early so "add this timetable to my planner"
# is never read as "add a task called this timetable".
TIMETABLE = re.compile(
    r"\b(add|import|update|replace|load|read|set up|upload)\b"
    r".{0,40}?\b(time ?table|classes|schedule)\b"
    r"|\b(time ?table)\b.{0,30}\b(from|pdf|file|attachment|document)\b")

# Questions about the schedule — a lookup, never an import.
SCHEDULE_READ = re.compile(
    r"^(what|which|when|do|does|have)\b.*\b(timetable|classes?|schedule|lecture)\b"
    r"|\b(classes?|lectures?)\s+(do i have|have i got|are there)\b"
    r"|\bwhat'?s my (timetable|schedule)\b"
    r"|\bdo i have\b.{0,30}\b(class|lecture|today|tomorrow|monday|tuesday|"
    r"wednesday|thursday|friday|saturday|sunday)\b")

# Reporting something that already happened. These are writes — the user is
# telling EXPRESS a fact about the past, not asking a question.
LOG = re.compile(
    r"\b(spent|paid|bought|earned|received|got paid)\b.*\d"
    r"|\b(studied|revised|practised|practiced|read|worked on)\b.*"
    r"\b(\d+\s*(min|minute|hour|hr)|for a bit|for ages)"
    r"|\b(did|logged|completed)\s+(my|the)\s+\w+"
    r"|\bset (a )?budget\b")

# An action paired with an explicit future time is a scheduling request, even
# without an "add"/"schedule" verb — "revise transformers tomorrow at 9pm".
TIMED_ACTION = re.compile(
    r"\b(revise|study|practice|practise|work on|do|finish|write|read|call|meet|"
    r"submit|review|prep|prepare)\b.{0,60}?"
    r"\b(today|tonight|tomorrow|this (evening|afternoon|morning)|next week|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"at \d{1,2}(:\d{2})?\s*(am|pm)?|in \d+\s*(hours?|hrs?|minutes?|mins?))\b")

# "Do something" with no object — plausibly an instruction, too vague to act on.
VAGUE_INSTRUCTION = re.compile(
    r"^(add|create|schedule|book|delete|remove|move|cancel|change|update|"
    r"set|do|fix|sort)\s*(it|that|this|something|stuff|things)?\s*"
    r"(for|on|to|at)?\s*(tonight|today|tomorrow|later|sometime|soon)?\s*[!.?]*$")

REFERENTIAL = re.compile(r"\b(it|that|this|those|them|the one)\b")


def classify(text: str) -> tuple[Intent, str]:
    """Return (intent, why). `why` is for logs and the /intent endpoint."""
    t = (text or "").strip().lower()
    if not t:
        return Intent.UNKNOWN, "empty message"

    if GREETING.match(t):
        return Intent.CONVERSATION, "greeting"

    # "hey jocasta, how are you?" — greet, then whatever follows.
    opened = GREETING_PREFIX.sub("", t, count=1)
    if opened != t:
        if not opened.strip(" ?!."):
            return Intent.CONVERSATION, "greeting"
        if (SMALL_TALK.match(opened) or ACKNOWLEDGEMENT.match(opened)
                or FAREWELL.match(opened) or FEELING.search(opened)):
            return Intent.CONVERSATION, "greeting with small talk"
        # A greeting attached to a real request: classify the request.
        t = opened

    if SMALL_TALK.match(t):
        return Intent.CONVERSATION, "small talk"

    # "hey ja costa how are you" — the name came back garbled from speech.
    if (len(t.split()) <= 8 and not CREATE.search(t) and not DELETE.search(t)
            and not RESCHEDULE.search(t) and TRAILING_SMALL_TALK.search(t)):
        return Intent.CONVERSATION, "small talk after a garbled address"
    if ACKNOWLEDGEMENT.match(t):
        return Intent.CONVERSATION, "acknowledgement"
    if FAREWELL.match(t):
        return Intent.CONVERSATION, "sign-off"
    if FEELING.search(t):
        return Intent.CONVERSATION, "statement of how they feel"

    # A vague imperative must never be executed on a guess.
    if VAGUE_INSTRUCTION.match(t):
        return Intent.CLARIFY, "instruction with nothing to act on"

    if PLANNING.search(t):
        return Intent.PLANNING, "asked for a plan"
    if FREE_TIME.search(t):
        return Intent.SUGGESTION, "stated free time"
    if SUGGESTION.search(t):
        return Intent.SUGGESTION, "asked what to do"

    if SCHEDULE_READ.search(t):
        return Intent.READ, "asked about the schedule"
    if TIMETABLE.search(t):
        return Intent.TIMETABLE, "asked to import or replace a timetable"
    if MEMORY.search(t):
        return Intent.MEMORY, "asked to remember something"
    if LOG.search(t):
        return Intent.LOG, "reported something that already happened"
    if ATTENDANCE.search(t):
        return Intent.ATTENDANCE, "reported attending or missing a class"
    if DELETE.search(t):
        return Intent.DELETE, "asked to remove something"
    if RESCHEDULE.search(t):
        return Intent.RESCHEDULE, "asked to move something in time"
    if COMPLETE.search(t):
        return Intent.COMPLETE, "reported finishing something"
    if EDIT.search(t):
        return Intent.EDIT, "asked to change something"

    if ADD_TO_COLLECTION.search(t):
        return Intent.CREATE, "asked to add something"
    if READ.search(t):
        return Intent.READ, "asked to look something up"
    if CREATE.search(t):
        return Intent.CREATE, "asked to add something"
    if TIMED_ACTION.search(t):
        return Intent.CREATE, "named an action with a time"

    # A question with no other signal is a question, not an instruction.
    if t.endswith("?") or QUESTION_WORD.match(t):
        return Intent.QUESTION, "phrased as a question"

    # Deliberately NOT create. An unrecognised statement is far more often
    # conversation than a silent instruction to file a record.
    return Intent.UNKNOWN, "no recognisable instruction"


def is_referential(text: str) -> bool:
    """Does this lean on something said earlier ("move it", "make that 8")?"""
    return bool(REFERENTIAL.search((text or "").lower()))


def may_write(intent: Intent) -> bool:
    return intent in WRITE_INTENTS
