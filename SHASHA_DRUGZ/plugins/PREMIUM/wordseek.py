# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║              WORDSEEK MODULE — SHASHA FINAL EDITION v2                      ║
# ║                                                                              ║
# ║  FIXES APPLIED:                                                              ║
# ║  ✅ Uses `from SHASHA_DRUGZ import app` — no raw Client                      ║
# ║  ✅ All handlers use @app.on_message / @app.on_callback_query                ║
# ║  ✅ Guess handler uses group=10 to avoid 500-plugin conflicts                ║
# ║  ✅ All callback regexes start with ^ws_ (strict, no conflicts)              ║
# ║  ✅ Redis silently falls back to in-memory on any error (no crash)           ║
# ║  ✅ Redis reconnect guard: resets broken client before retrying              ║
# ║  ✅ datetime.fromisoformat wrapped in try/except (no timezone crash)         ║
# ║  ✅ [NEW] Word validation — only words in WORD_SETS accepted                 ║
# ║       • Wrong / gibberish words → "not an english word" reply               ║
# ║  ✅ [NEW] Duplicate-guess detection → "word already guessed" reply           ║
# ║  ✅ [NEW] Guess-limit selection after length pick                            ║
# ║       • Options: 10 / 15 / 20 / 30 / ♾️ Unlimited                           ║
# ║  ✅ [NEW] Group isolation — each chat_id gets its own independent game;      ║
# ║       limit callbacks are scoped to the originating chat so two groups       ║
# ║       clicking at the same time can never cross-start each other's game      ║
# ║  ✅ Per-chat leaderboard (separate stats per group)                          ║
# ║  ✅ Weekly / Monthly auto-reset logic (no cron needed)                       ║
# ║  ✅ 4 / 5 / 6 letter word selection via inline buttons on /wordseek          ║
# ║  ✅ Alphabet hint tracker shown after every guess                            ║
# ║  ✅ Time + attempt + streak bonus points                                     ║
# ║  ✅ Wordle-accurate feedback (no double-counting duplicate letters)          ║
# ║  ✅ Streak tracking with fire bar in /wordseekrank                           ║
# ║  ✅ 6-view leaderboard: Global/Chat x All-Time/Weekly/Monthly                ║
# ║  ✅ Board display: 🟥🟨🟩 squares LEFT, ALL CAPS word RIGHT (per screenshot) ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

import os
import json
import random
import logging
from datetime import datetime, timedelta

from pyrogram import filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

# ── SHASHA client import ──────────────────────────────────────────────────────
from SHASHA_DRUGZ import app

# ── Optional Redis ────────────────────────────────────────────────────────────
from config import REDIS_URL

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://default:LMXY37qj1iU91xEci0uaCcQa6kBEn4G3@redis-18407.crce286.ap-south-1-1.ec2.cloud.redislabs.com:18407",
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
#  WORD LISTS
# ═══════════════════════════════════════════════════════════════════════════════
WORDS = {
    4: [
        "able", "acid", "aged", "also", "area", "army", "atom", "baby", "back", "bake",
        "ball", "band", "bare", "bark", "barn", "base", "bath", "bead", "beam", "bean",
        "bear", "beat", "beck", "beef", "been", "beer", "bell", "belt", "bend", "best",
        "bird", "bite", "blow", "blue", "blur", "boat", "body", "bold", "bolt", "bond",
        "bone", "book", "boom", "boot", "born", "both", "bowl", "buck", "bunk", "burn",
        "bush", "busy", "byte", "cage", "cake", "calf", "calm", "came", "camp", "cane",
        "card", "care", "carp", "cart", "case", "cash", "cast", "cave", "cell", "chat",
        "chip", "chop", "city", "clay", "clip", "club", "clue", "coal", "coat", "code",
        "coil", "coin", "cold", "colt", "come", "cone", "cook", "cool", "core", "cork",
        "corn", "cost", "cozy", "crab", "crop", "crow", "cube", "cure", "curl", "cute",
        "dame", "dare", "dark", "dart", "dash", "date", "dawn", "daze", "dead", "deal",
        "dear", "debt", "deck", "deep", "deer", "deft", "dent", "desk", "dial", "dice",
        "dime", "dine", "dire", "dirt", "disc", "dish", "disk", "diva", "dive", "dock",
        "dome", "done", "door", "dose", "dove", "down", "drab", "drag", "draw", "drip",
        "drop", "drum", "duel", "duke", "dull", "dune", "dusk", "dust", "duty", "each",
        "earl", "earn", "ease", "east", "edge", "emit", "epic", "even", "ever", "evil",
        "exam", "face", "fact", "fail", "fair", "fall", "fame", "fang", "farm", "fast",
        "fate", "fawn", "faze", "fear", "feat", "feed", "feel", "feet", "fell", "felt",
        "fern", "file", "fill", "film", "find", "fine", "fire", "firm", "fish", "fist",
        "flag", "flat", "flaw", "flea", "fled", "flew", "flip", "flow", "foam", "fold",
        "fond", "font", "food", "fool", "ford", "fork", "form", "fort", "foul", "four",
        "free", "frog", "fuel", "full", "fund", "fuse", "fuzz", "gate", "gave", "gaze",
        "gear", "gene", "glow", "glue", "gnat", "goal", "gold", "good", "gown", "grab",
        "gray", "grid", "grim", "grin", "grip", "grit", "grow", "gulf", "gust", "hack",
        "hail", "half", "hall", "halt", "hand", "hard", "hare", "harm", "hash", "hate",
        "haul", "have", "hawk", "haze", "head", "heal", "heap", "heat", "heel", "held",
        "helm", "hemp", "herb", "here", "hide", "high", "hike", "hill", "hint", "hire",
        "hive", "hold", "hole", "home", "hood", "hook", "hope", "hose", "host", "hour",
        "howl", "hull", "hump", "hunt", "hurl", "hymn", "idea", "idle", "inch", "iris",
        "iron", "isle", "item", "jade", "jail", "jolt", "jump", "just", "keen", "keep",
        "kelp", "kind", "king", "knee", "knit", "knot", "lace", "lack", "lake", "lamp",
        "land", "lane", "last", "late", "leaf", "lean", "leap", "left", "lend", "lens",
        "lift", "like", "lime", "line", "link", "lion", "list", "live", "load", "loaf",
        "lock", "loft", "long", "look", "loom", "loot", "lord", "lore", "loss", "loud",
        "love", "luck", "lure", "lurk", "made", "main", "make", "mall", "mane", "many",
        "mark", "mask", "mast", "maze", "meal", "mean", "meet", "meld", "melt", "mesh",
        "mild", "mile", "milk", "mill", "mine", "mint", "mist", "mode", "mole", "moon",
        "more", "moss", "most", "moth", "move", "much", "must", "myth", "nail", "name",
        "near", "neck", "need", "nest", "next", "nice", "nick", "nine", "node", "noon",
        "norm", "nose", "note", "null", "oath", "obey", "odds", "open", "oral", "orbs",
        "orca", "over", "oven", "owls", "pace", "pack", "page", "paid", "pain", "pair",
        "pale", "palm", "park", "part", "path", "pave", "peak", "peel", "peer", "pelt",
        "pest", "pick", "pier", "pile", "pine", "pink", "pipe", "plan", "play", "plow",
        "plug", "plum", "plus", "poem", "pole", "poll", "pond", "pool", "poor", "port",
        "post", "pour", "prey", "prop", "pull", "pump", "pure", "push", "quit", "race",
        "rack", "rage", "raid", "rail", "rain", "rake", "ramp", "rank", "rare", "rate",
        "read", "real", "reap", "reel", "rely", "rent", "rest", "rice", "rich", "ride",
        "ring", "rise", "risk", "road", "roam", "roar", "robe", "rock", "rode", "role",
        "roll", "rope", "rose", "ruin", "rule", "ruse", "rush", "rust", "safe", "sage",
        "sail", "sake", "sale", "salt", "same", "sand", "sane", "sang", "sank", "sash",
        "save", "scam", "scar", "seal", "seam", "seat", "seed", "seek", "seen", "self",
        "sell", "sent", "shed", "ship", "shoe", "shop", "shot", "show", "shut", "side",
        "sigh", "silk", "sill", "sing", "sink", "slab", "slam", "slap", "slew", "slim",
        "slip", "slow", "slug", "snap", "snow", "soak", "soar", "sock", "soft", "soil",
        "sole", "some", "song", "soot", "sort", "soul", "span", "spar", "spin", "spit",
        "spot", "spur", "stab", "stem", "step", "stew", "stir", "stop", "stub", "stun",
        "suit", "sung", "sunk", "swam", "swap", "swat", "swim", "tail", "tale", "talk",
        "tall", "tame", "tank", "tape", "task", "team", "teal", "tear", "tell", "tend",
        "tent", "term", "test", "than", "that", "them", "then", "thin", "this", "tide",
        "tied", "tile", "till", "time", "tiny", "tire", "toad", "told", "toll", "tomb",
        "tome", "tone", "tore", "torn", "tort", "toss", "tour", "town", "trap", "tree",
        "trim", "trip", "trod", "tuck", "tuft", "tune", "twig", "type", "ugly", "unit",
        "upon", "used", "vain", "vale", "vane", "vast", "veil", "vein", "vent", "verb",
        "very", "vest", "veto", "view", "vine", "void", "volt", "wade", "wage", "wake",
        "walk", "wall", "wand", "ward", "warm", "warp", "wart", "wash", "wasp", "wave",
        "weld", "well", "went", "west", "whim", "whip", "wide", "wild", "will", "wilt",
        "wind", "wine", "wing", "wink", "wipe", "wire", "wise", "wish", "wisp", "with",
        "woke", "wolf", "womb", "wood", "word", "wore", "work", "worm", "wove", "wrap",
        "wren", "yell", "yoke", "yore", "zero", "zone", "zoom",
    ],
    5: [
        "abbey", "abode", "abyss", "adore", "adult", "agile", "aglow", "agony", "ahead",
        "aisle", "alert", "algae", "alien", "align", "alike", "alive", "allay", "allot",
        "allow", "alloy", "alone", "aloof", "aloud", "altar", "alter", "amaze", "amend",
        "ample", "angel", "anger", "angle", "angry", "anvil", "apart", "apple", "apply",
        "arena", "argue", "arise", "armor", "arson", "aside", "asset", "atone", "attic",
        "audio", "avail", "avoid", "awake", "award", "aware", "awful", "azure", "babel",
        "badge", "badly", "barge", "basic", "basis", "batch", "bayou", "beach", "began",
        "begin", "below", "bench", "berry", "bevel", "binds", "birch", "bison", "black",
        "blade", "bland", "blank", "blare", "blast", "blaze", "bleak", "bleed", "blend",
        "bless", "blimp", "blind", "blink", "block", "blood", "bloom", "blown", "board",
        "boned", "bonus", "boost", "booth", "botch", "bound", "boxed", "brace", "brain",
        "brand", "brave", "brawl", "bread", "break", "breed", "bribe", "brick", "bride",
        "brine", "brisk", "broil", "brook", "broth", "brown", "brunt", "brush", "build",
        "built", "bulge", "bully", "bunch", "burst", "butch", "cable", "camel", "candy",
        "cargo", "carry", "catch", "cause", "cease", "chain", "chair", "chalk", "chaos",
        "chant", "charm", "chart", "chase", "cheap", "cheat", "check", "cheek", "chess",
        "chest", "child", "china", "choir", "chore", "chunk", "cider", "civic", "civil",
        "claim", "clash", "clasp", "class", "clean", "clear", "clerk", "click", "cliff",
        "climb", "clink", "cloak", "clock", "clone", "close", "cloud", "clown", "coach",
        "coast", "cobra", "comet", "comic", "comma", "coral", "count", "court", "cover",
        "crack", "craft", "crane", "crash", "crawl", "cream", "creed", "creek", "creep",
        "crest", "crisp", "cross", "crowd", "crown", "crumb", "crush", "crypt", "curly",
        "curve", "cycle", "daily", "dance", "dandy", "dazed", "debug", "decoy", "delta",
        "dense", "depot", "depth", "derby", "digit", "diner", "ditty", "dizzy", "dodge",
        "doozy", "doubt", "dowdy", "draft", "drain", "drama", "drank", "drape", "drawl",
        "dream", "dress", "dried", "drift", "drill", "drink", "drive", "drone", "drool",
        "drove", "dryer", "dwarf", "eager", "eagle", "early", "earth", "easel", "eight",
        "elite", "ember", "empty", "enemy", "enjoy", "enter", "equal", "error", "event",
        "every", "exact", "exist", "extra", "fable", "faced", "fairy", "false", "fancy",
        "feast", "feral", "fence", "fetch", "fever", "fiber", "field", "fifty", "fight",
        "final", "first", "fjord", "fixed", "flame", "flash", "flask", "fleck", "flick",
        "fling", "flint", "flirt", "float", "flock", "flood", "floor", "flour", "flown",
        "flute", "foamy", "focus", "force", "forge", "forum", "found", "frame", "frank",
        "fresh", "front", "frost", "froze", "fruit", "fugue", "fully", "fungi", "gauge",
        "gauze", "gavel", "gawky", "gecko", "genie", "ghost", "giant", "giddy", "given",
        "gland", "glass", "globe", "gloom", "gloss", "glove", "gnome", "going", "gorge",
        "gouge", "gourd", "grace", "grade", "grain", "grand", "grant", "graph", "grasp",
        "grass", "grave", "graze", "great", "greed", "green", "greet", "grief", "grill",
        "grind", "groan", "grope", "gross", "group", "grove", "growl", "grown", "guard",
        "guess", "guide", "guild", "guile", "guise", "gulch", "gusto", "gypsy", "habit",
        "happy", "harsh", "hasty", "haunt", "haven", "heart", "heavy", "hedge", "hence",
        "hinge", "hippo", "hoard", "holly", "honey", "honor", "horse", "hotel", "house",
        "human", "humor", "hurry", "hyper", "icily", "image", "imply", "inbox", "index",
        "indie", "inner", "input", "inter", "intro", "irony", "ivory", "jewel", "joust",
        "judge", "juice", "juicy", "jumpy", "karma", "kebab", "knack", "kneel", "knife",
        "knock", "knoll", "known", "label", "lance", "lapel", "laser", "layer", "leafy",
        "leaky", "learn", "ledge", "legal", "lemon", "level", "light", "linen", "liver",
        "llama", "local", "lodge", "logic", "loose", "lover", "lower", "lucky", "lunar",
        "lunch", "lusty", "lyric", "magic", "major", "maker", "manga", "manor", "maple",
        "march", "marsh", "match", "mayor", "media", "mercy", "merge", "metal", "metro",
        "might", "mirth", "model", "money", "month", "moral", "mossy", "motif", "motor",
        "mount", "mouse", "mouth", "movie", "muddy", "music", "naive", "naval", "nerve",
        "never", "night", "ninja", "noble", "noise", "north", "novel", "nurse", "nymph",
        "ocean", "offer", "olive", "onset", "opera", "orbit", "order", "other", "outer",
        "owner", "oxide", "ozone", "paint", "panic", "paper", "party", "pasta", "paste",
        "patch", "pause", "peace", "pearl", "pedal", "penny", "perch", "phase", "phone",
        "photo", "piano", "piece", "pilot", "pitch", "pixel", "pizza", "place", "plaid",
        "plain", "plane", "plant", "plate", "plaza", "plead", "pluck", "plumb", "plume",
        "plump", "plunk", "point", "poise", "poker", "polar", "posse", "pound", "power",
        "press", "price", "pride", "prime", "print", "prize", "probe", "prone", "proof",
        "prose", "proud", "prove", "proxy", "pulse", "pupil", "purse", "quest", "quick",
        "quiet", "quota", "quote", "radar", "radio", "rainy", "rally", "ranch", "range",
        "rapid", "razor", "reach", "ready", "realm", "rebel", "refer", "reign", "remix",
        "repay", "rider", "rifle", "right", "risky", "rival", "river", "robot", "rocky",
        "rouge", "rough", "round", "route", "rover", "royal", "ruler", "rural", "rusty",
        "sadly", "saint", "sauce", "scale", "scene", "scope", "score", "scout", "seize",
        "sense", "serve", "seven", "shade", "shaft", "shake", "shame", "shape", "share",
        "shark", "sharp", "sheep", "sheer", "shelf", "shell", "shift", "shirt", "shock",
        "shore", "short", "shout", "shove", "sight", "silky", "since", "sixth", "sixty",
        "skill", "slash", "slate", "slave", "sleek", "sleep", "slice", "slide", "sling",
        "slope", "sloth", "smart", "smell", "smile", "smoke", "solar", "solve", "sonic",
        "sorry", "south", "space", "spare", "spark", "spawn", "speak", "speed", "spend",
        "spice", "spike", "spine", "spite", "split", "sport", "spray", "squad", "stack",
        "staff", "stage", "stain", "stale", "stall", "stamp", "stand", "stark", "start",
        "state", "stave", "steam", "steel", "steep", "steer", "stern", "stick", "stiff",
        "still", "sting", "stock", "stomp", "stone", "stood", "store", "storm", "story",
        "stove", "strap", "straw", "stray", "strip", "strum", "study", "style", "sugar",
        "suite", "sunny", "super", "surge", "swamp", "swear", "sweep", "sweet", "swept",
        "swift", "swipe", "swirl", "swoop", "sword", "synth", "table", "taste", "teach",
        "tease", "teeth", "tempo", "tense", "terms", "thorn", "those", "three", "threw",
        "throw", "tiger", "tight", "timer", "tired", "title", "toast", "today", "token",
        "tooth", "topic", "total", "touch", "tough", "tower", "toxic", "track", "trade",
        "trail", "train", "trait", "trash", "treat", "trend", "trial", "tribe", "trick",
        "tried", "troop", "trove", "truce", "truck", "truly", "trunk", "trust", "truth",
        "tumor", "turbo", "tweak", "twice", "twist", "ultra", "unify", "until", "upper",
        "upset", "urban", "usage", "usual", "utter", "valid", "value", "valve", "vapor",
        "vault", "vigor", "viral", "virus", "visor", "vista", "vital", "vivid", "vocal",
        "vogue", "voice", "voter", "wagon", "water", "weary", "weave", "wedge", "weigh",
        "weird", "whale", "wheat", "wheel", "where", "which", "while", "white", "whole",
        "whose", "wider", "witch", "woody", "world", "worry", "worse", "worst", "worth",
        "would", "wound", "wrath", "write", "wrote", "yacht", "yield", "young", "youth",
        "zebra", "zesty",
    ],
    6: [
        "abrupt", "accent", "accept", "access", "action", "active", "actual", "advice",
        "aerial", "affect", "afford", "afraid", "agency", "agenda", "almost", "alpine",
        "always", "ambush", "anchor", "animal", "annual", "answer", "anyone", "arcade",
        "arctic", "around", "arrive", "aspect", "assess", "assist", "assume", "attach",
        "attack", "attend", "author", "autumn", "avatar", "backed", "backup", "ballot",
        "banner", "battle", "beauty", "before", "behind", "belong", "better", "biopsy",
        "bitter", "blotch", "border", "bottle", "bounce", "branch", "breach", "breeze",
        "bridge", "bright", "broken", "bronze", "budget", "bundle", "burden", "button",
        "bypass", "camera", "cancel", "candle", "canopy", "canvas", "carbon", "castle",
        "casual", "caught", "center", "change", "charge", "choice", "chrome", "circle",
        "circus", "classy", "clever", "client", "cloudy", "clover", "coarse", "combat",
        "comedy", "coming", "commit", "common", "copper", "corner", "cotton", "couple",
        "course", "credit", "crisis", "critic", "custom", "dagger", "damage", "danger",
        "daring", "darken", "deadly", "debate", "decade", "decide", "defeat", "defend",
        "define", "degree", "delete", "deluge", "demand", "desert", "design", "detail",
        "detect", "devour", "differ", "divine", "domain", "double", "dragon", "drawer",
        "driven", "dusted", "effect", "effort", "either", "eleven", "engage", "enigma",
        "ensure", "entity", "escape", "evolve", "exceed", "excuse", "exempt", "expand",
        "expect", "expert", "export", "extend", "fading", "fallen", "famous", "faster",
        "father", "figure", "filter", "finger", "finish", "firmly", "fitted", "flight",
        "follow", "forget", "formal", "format", "fought", "fourth", "frozen", "galaxy",
        "gambit", "garden", "garlic", "gentle", "glitch", "global", "golden", "gotten",
        "gravel", "grieve", "grotto", "guided", "guitar", "harbor", "harden", "health",
        "height", "hidden", "holler", "humble", "hunger", "hybrid", "impact", "import",
        "insult", "intake", "intent", "island", "issued", "jangle", "jigsaw", "jungle",
        "junior", "kernel", "kettle", "kidnap", "knight", "larger", "latest", "launch",
        "leader", "legacy", "legend", "lively", "lizard", "locked", "lumber", "luxury",
        "magnet", "margin", "market", "matter", "mayhem", "melody", "member", "mental",
        "middle", "minute", "mirror", "modern", "monkey", "mother", "motion", "motive",
        "muzzle", "myself", "mystic", "nature", "needle", "negate", "nephew", "nested",
        "neural", "normal", "notice", "object", "obtain", "online", "opener", "option",
        "origin", "output", "oyster", "packet", "palace", "parade", "pardon", "parent",
        "patent", "pencil", "people", "permit", "phrase", "pickup", "planet", "pledge",
        "plenty", "pocket", "policy", "portal", "potent", "pretty", "prince", "prison",
        "profit", "proper", "public", "python", "rabbit", "racial", "random", "rating",
        "reason", "recent", "record", "reduce", "refund", "region", "reject", "repair",
        "repeat", "rescue", "resist", "result", "retain", "retire", "return", "reveal",
        "review", "reward", "rocket", "rotate", "rubber", "runner", "saddle", "safety",
        "salmon", "sample", "school", "screen", "script", "search", "season", "second",
        "secret", "sector", "select", "sender", "senior", "series", "settle", "severe",
        "shadow", "signal", "silver", "simple", "single", "sister", "sketch", "social",
        "socket", "source", "speech", "spread", "spring", "sprint", "square", "stable",
        "static", "status", "steady", "stolen", "stream", "street", "stress", "strict",
        "string", "stroke", "strong", "struck", "studio", "submit", "sunset", "supply",
        "switch", "symbol", "system", "tablet", "talent", "target", "terror", "theory",
        "thread", "though", "threat", "timber", "tissue", "tongue", "toward", "tribal",
        "triple", "trojan", "tunnel", "turkey", "turtle", "twitch", "unique", "unlock",
        "update", "uphold", "useful", "vacuum", "vendor", "verbal", "victim", "virtue",
        "vision", "visual", "volume", "warden", "wealth", "weapon", "winter", "wisdom",
        "within", "wonder", "wooden", "worker", "zealot", "zombie",
    ],
}

# ── Pre-build sets for O(1) lookup ────────────────────────────────────────────
WORD_SETS: dict[int, set] = {length: set(words) for length, words in WORDS.items()}

# ═══════════════════════════════════════════════════════════════════════════════
#  GAME CONFIG
# ═══════════════════════════════════════════════════════════════════════════════
BASE_POINTS    = {4: 8,  5: 10, 6: 14}
DIFFICULTY_EMO = {4: "🟢 Easy", 5: "🟡 Medium", 6: "🔴 Hard"}

# Available guess limits; 0 = unlimited (♾️)
GUESS_LIMITS   = [10, 15, 20, 30, 0]

GAME_TTL       = 3600   # Redis TTL per active game (1 hour)

# Commands excluded from the guess handler
_WS_COMMANDS = [
    "wordseek", "wordseekend", "wordseektop",
    "wordseekrank", "wordseekhelp",
]

# ═══════════════════════════════════════════════════════════════════════════════
#  REDIS / IN-MEMORY LAYER
# ═══════════════════════════════════════════════════════════════════════════════
_redis_client = None
_mem_games: dict = {}    # chat_id -> game dict
_mem_stats: dict = {}    # "scope:user_id" -> stats dict


async def _get_redis():
    global _redis_client
    if not REDIS_AVAILABLE:
        return None
    if _redis_client is not None:
        try:
            await _redis_client.ping()
            return _redis_client
        except Exception:
            try:
                await _redis_client.aclose()
            except Exception:
                pass
            _redis_client = None
    try:
        client = aioredis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        await client.ping()
        _redis_client = client
        logger.info("[WordSeek] Redis connected: %s", REDIS_URL)
        return _redis_client
    except Exception as exc:
        logger.warning("[WordSeek] Redis unavailable, falling back to in-memory: %s", exc)
        _redis_client = None
        return None


# ── Game helpers ──────────────────────────────────────────────────────────────
async def set_game(chat_id: int, game: dict) -> None:
    r = await _get_redis()
    if r:
        try:
            await r.set(f"ws:game:{chat_id}", json.dumps(game, default=str), ex=GAME_TTL)
            return
        except Exception as exc:
            logger.warning("[WordSeek] Redis set_game error: %s", exc)
    _mem_games[chat_id] = game


async def get_game(chat_id: int) -> dict | None:
    r = await _get_redis()
    if r:
        try:
            raw = await r.get(f"ws:game:{chat_id}")
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.warning("[WordSeek] Redis get_game error: %s", exc)
    return _mem_games.get(chat_id)


async def del_game(chat_id: int) -> None:
    r = await _get_redis()
    if r:
        try:
            await r.delete(f"ws:game:{chat_id}")
            return
        except Exception as exc:
            logger.warning("[WordSeek] Redis del_game error: %s", exc)
    _mem_games.pop(chat_id, None)


# ── Stats helpers ─────────────────────────────────────────────────────────────
def _blank_stats(username: str) -> dict:
    now = datetime.utcnow().isoformat()
    return {
        "username":       username,
        "wins":           0,
        "points":         0,
        "streak":         0,
        "max_streak":     0,
        "weekly_points":  0,
        "monthly_points": 0,
        "week_start":     now,
        "month_start":    now,
    }


def _safe_fromisoformat(s: str) -> datetime:
    try:
        clean = s.split("+")[0].rstrip("Z")
        return datetime.fromisoformat(clean)
    except Exception:
        return datetime.utcnow()


def _apply_period_reset(data: dict) -> dict:
    now         = datetime.utcnow()
    week_start  = _safe_fromisoformat(data.get("week_start",  now.isoformat()))
    month_start = _safe_fromisoformat(data.get("month_start", now.isoformat()))
    if now - week_start >= timedelta(weeks=1):
        data["weekly_points"] = 0
        data["week_start"]    = now.isoformat()
    if now - month_start >= timedelta(days=30):
        data["monthly_points"] = 0
        data["month_start"]    = now.isoformat()
    return data


async def _load_stats(scope: str, user_id: int, username: str) -> dict:
    key = f"ws:stats:{scope}:{user_id}"
    r   = await _get_redis()
    if r:
        try:
            raw = await r.get(key)
            return json.loads(raw) if raw else _blank_stats(username)
        except Exception as exc:
            logger.warning("[WordSeek] Redis _load_stats error: %s", exc)
    return _mem_stats.get(f"{scope}:{user_id}", _blank_stats(username))


async def _save_stats(scope: str, user_id: int, data: dict) -> None:
    key = f"ws:stats:{scope}:{user_id}"
    r   = await _get_redis()
    if r:
        try:
            await r.set(key, json.dumps(data))
            return
        except Exception as exc:
            logger.warning("[WordSeek] Redis _save_stats error: %s", exc)
    _mem_stats[f"{scope}:{user_id}"] = data


async def update_stats(
    chat_id:  int,
    user_id:  int,
    username: str,
    *,
    points: int = 0,
    won:    bool = False,
) -> None:
    for scope in ("global", f"chat:{chat_id}"):
        data = await _load_stats(scope, user_id, username)
        data = _apply_period_reset(data)
        data["username"] = username
        if won:
            data["wins"]           += 1
            data["points"]         += points
            data["weekly_points"]  += points
            data["monthly_points"] += points
            data["streak"]          = data.get("streak", 0) + 1
            data["max_streak"]      = max(data.get("max_streak", 0), data["streak"])
        else:
            data["streak"] = 0
        await _save_stats(scope, user_id, data)


async def get_leaderboard(scope: str, period: str = "all", limit: int = 10) -> list:
    pts_key = {
        "all":     "points",
        "weekly":  "weekly_points",
        "monthly": "monthly_points",
    }.get(period, "points")
    results = []
    r       = await _get_redis()
    if r:
        try:
            keys = await r.keys(f"ws:stats:{scope}:*")
            for key in keys:
                raw = await r.get(key)
                if not raw:
                    continue
                data = json.loads(raw)
                data = _apply_period_reset(data)
                uid  = key.split(":")[-1]
                pts  = data.get(pts_key, 0)
                results.append((uid, data.get("username", uid), pts, data.get("wins", 0)))
        except Exception as exc:
            logger.warning("[WordSeek] Redis get_leaderboard error: %s", exc)
    if not results:
        prefix = f"{scope}:"
        for mem_key, data in _mem_stats.items():
            if not mem_key.startswith(prefix):
                continue
            data = _apply_period_reset(data)
            uid  = mem_key[len(prefix):]
            pts  = data.get(pts_key, 0)
            results.append((uid, data.get("username", uid), pts, data.get("wins", 0)))
    results.sort(key=lambda x: x[2], reverse=True)
    return results[:limit]


async def get_user_stats(chat_id: int, user_id: int, username: str) -> dict:
    g_data = await _load_stats("global",          user_id, username)
    c_data = await _load_stats(f"chat:{chat_id}", user_id, username)
    return {
        "global": _apply_period_reset(g_data),
        "chat":   _apply_period_reset(c_data),
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  GAME LOGIC HELPERS
# ═══════════════════════════════════════════════════════════════════════════════
_SQ_GREEN  = "🟩"
_SQ_YELLOW = "🟨"
_SQ_RED    = "🟥"


def build_feedback(word: str, guess: str) -> list[str]:
    """
    Wordle-accurate two-pass feedback.
    Returns a list of square emoji per letter.
    """
    marks     = [_SQ_RED] * len(guess)
    word_pool = list(word)
    # Pass 1 — exact matches
    for i, ch in enumerate(guess):
        if ch == word_pool[i]:
            marks[i]     = _SQ_GREEN
            word_pool[i] = None
    # Pass 2 — present but misplaced
    for i, ch in enumerate(guess):
        if marks[i] == _SQ_GREEN:
            continue
        if ch in word_pool:
            marks[i] = _SQ_YELLOW
            word_pool[word_pool.index(ch)] = None
    return marks


def build_board(word: str, guesses: list[str]) -> str:
    """
    Render all guesses as a board:
      🟥🟨🟩🟥🟥  HAPPY
    Squares LEFT  •  ALL-CAPS word RIGHT
    """
    lines = []
    for g in guesses:
        squares = "".join(build_feedback(word, g))
        lines.append(f"{squares}  {g.upper()}")
    return "\n".join(lines)


def build_alphabet_tracker(word: str, guesses: list) -> str:
    """Live per-letter 🟩🟨🟥 grid, rendered in rows of 9."""
    correct = set()
    present = set()
    absent  = set()
    for g in guesses:
        for i, ch in enumerate(g):
            if i < len(word) and ch == word[i]:
                correct.add(ch)
            elif ch in word:
                present.add(ch)
            else:
                absent.add(ch)
    present -= correct
    absent  -= correct | present
    parts = []
    for ch in "abcdefghijklmnopqrstuvwxyz":
        if   ch in correct: parts.append(f"{_SQ_GREEN}`{ch}`")
        elif ch in present: parts.append(f"{_SQ_YELLOW}`{ch}`")
        elif ch in absent:  parts.append(f"{_SQ_RED}`{ch}`")
    if not parts:
        return "_No letters guessed yet._"
    rows, row = [], []
    for p in parts:
        row.append(p)
        if len(row) == 9:
            rows.append(" ".join(row))
            row = []
    if row:
        rows.append(" ".join(row))
    return "\n".join(rows)


def _fmt_attempts(attempts: int, max_att) -> str:
    """Format attempt counter respecting unlimited (None) max."""
    return f"{attempts}/♾️" if max_att is None else f"{attempts}/{max_att}"


def calc_points(length: int, attempts: int, elapsed_secs: float, max_att=None):
    """Returns (total, base, time_bonus, attempt_bonus)."""
    base          = BASE_POINTS[length]
    ref_max       = max_att if (max_att is not None) else 30
    attempt_bonus = max(0, ref_max - attempts)
    time_bonus    = max(0, int((300 - elapsed_secs) / 60))
    return base + attempt_bonus + time_bonus, base, time_bonus, attempt_bonus


# ═══════════════════════════════════════════════════════════════════════════════
#  COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("wordseek"))
async def cmd_wordseek(client, message: Message):
    """Show word-length selection buttons."""
    chat_id  = message.chat.id
    existing = await get_game(chat_id)
    if existing:
        w       = existing["word"]
        att     = existing["attempts"]
        max_att = existing["max_attempts"]
        att_str = _fmt_attempts(att, max_att)
        return await message.reply(
            f"<blockquote>⚠️ **ᴀ ɢᴀᴍᴇ ɪs ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ!**</blockquote>\n"
            f"<blockquote>ʟᴇɴɢᴛʜ: **{len(w)} ʟᴇᴛᴛᴇʀs** | ᴀᴛᴛᴇᴍᴘᴛs: {att_str}\n\n"
            f"ᴜsᴇ /wordseekend ᴛᴏ sᴛᴏᴘ ɪᴛ ғɪʀsᴛ.</blockquote>",
            quote=True,
        )
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("4️⃣ 4 ʟᴇᴛᴛᴇʀs", callback_data="ws_start_4"),
            InlineKeyboardButton("5️⃣ 5 ʟᴇᴛᴛᴇʀs", callback_data="ws_start_5"),
            InlineKeyboardButton("6️⃣ 6 ʟᴇᴛᴛᴇʀs", callback_data="ws_start_6"),
        ]
    ])
    await message.reply(
        "<blockquote>🎮 **ᴡᴏʀᴅsᴇᴇᴋ — sᴛᴇᴘ 1: ᴄʜᴏᴏsᴇ ᴡᴏʀᴅ ʟᴇɴɢᴛʜ**</blockquote>\n"
        "<blockquote>sᴇʟᴇᴄᴛ ᴛʜᴇ ᴡᴏʀᴅ ʟᴇɴɢᴛʜ ᴛᴏ ʙᴇɢɪɴ:\n\n"
        f"4️⃣  **4 ʟᴇᴛᴛᴇʀs** — {DIFFICULTY_EMO[4]}  ({BASE_POINTS[4]} ʙᴀsᴇ ᴘᴛs)\n"
        f"5️⃣  **5 ʟᴇᴛᴛᴇʀs** — {DIFFICULTY_EMO[5]}  ({BASE_POINTS[5]} ʙᴀsᴇ ᴘᴛs)\n"
        f"6️⃣  **6 ʟᴇᴛᴛᴇʀs** — {DIFFICULTY_EMO[6]}  ({BASE_POINTS[6]} ʙᴀsᴇ ᴘᴛs)</blockquote>",
        reply_markup=buttons,
        quote=True,
    )


# ── Step 1 callback: length chosen → show guess-limit buttons ─────────────────
@app.on_callback_query(filters.regex(r"^ws_start_([456])$"))
async def cb_choose_length(client, cq: CallbackQuery):
    """Length selected — ask for guess limit next."""
    chat_id  = cq.message.chat.id
    length   = int(cq.data[-1])

    # Guard: another game may have started while the user was deciding
    existing = await get_game(chat_id)
    if existing:
        return await cq.answer("❌ ᴀ ɢᴀᴍᴇ ɪs ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ!", show_alert=True)

    # Embed chat_id in callback_data so Group A's button never starts Group B's game
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔟 10 ʟɪᴍɪᴛ",
                callback_data=f"ws_limit_{chat_id}_{length}_10",
            ),
            InlineKeyboardButton(
                "1️⃣5️⃣ 15 ʟɪᴍɪᴛ",
                callback_data=f"ws_limit_{chat_id}_{length}_15",
            ),
        ],
        [
            InlineKeyboardButton(
                "2️⃣0️⃣ 20 ʟɪᴍɪᴛ",
                callback_data=f"ws_limit_{chat_id}_{length}_20",
            ),
            InlineKeyboardButton(
                "3️⃣0️⃣ 30 ʟɪᴍɪᴛ",
                callback_data=f"ws_limit_{chat_id}_{length}_30",
            ),
        ],
        [
            InlineKeyboardButton(
                "♾️ ᴜɴʟɪᴍɪᴛᴇᴅ  (ᴄᴏʀʀᴇᴄᴛ ᴡᴏʀᴅ ᴠᴀʀᴀɪᴋᴜᴍ)",
                callback_data=f"ws_limit_{chat_id}_{length}_0",
            ),
        ],
    ])
    await cq.message.edit_text(
        f"<blockquote>🎮 **sᴛᴇᴘ 2: ɢᴜᴇss ʟɪᴍɪᴛ ᴄʜᴏᴏsᴇ ᴘᴀɴᴀᴠᴜᴍ**</blockquote>\n"
        f"<blockquote>{DIFFICULTY_EMO[length]} — **{length}-ʟᴇᴛᴛᴇʀ ᴡᴏʀᴅ** sᴇʟᴇᴄᴛᴇᴅ!\n\n"
        f"🔟  **10 ʟɪᴍɪᴛ**  — ᴄʜᴀʟʟᴇɴɢɪɴɢ\n"
        f"1️⃣5️⃣ **15 ʟɪᴍɪᴛ**  — ᴍᴇᴅɪᴜᴍ\n"
        f"2️⃣0️⃣ **20 ʟɪᴍɪᴛ**  — ᴄᴏᴍғᴏʀᴛᴀʙʟᴇ\n"
        f"3️⃣0️⃣ **30 ʟɪᴍɪᴛ**  — ʀᴇʟᴀxᴇᴅ\n"
        f"♾️  **ᴜɴʟɪᴍɪᴛᴇᴅ** — ᴄᴏʀʀᴇᴄᴛ ᴡᴏʀᴅ ᴛʏᴘᴇ ᴘᴀɴʀᴀ ᴠᴀʀᴀɪᴋᴜᴍ ᴄᴏɴᴛɪɴᴜᴇ ᴀᴀɢᴜᴍ</blockquote>",
        reply_markup=buttons,
    )
    await cq.answer()


# ── Step 2 callback: limit chosen → start game ────────────────────────────────
@app.on_callback_query(filters.regex(r"^ws_limit_(-?\d+)_([456])_(\d+)$"))
async def cb_start_game(client, cq: CallbackQuery):
    """Guess limit selected — start the game (chat_id-scoped to prevent cross-group start)."""
    parts       = cq.data.split("_")
    # ws_limit_<chat_id>_<length>_<limit>
    origin_chat = int(parts[2])
    length      = int(parts[3])
    limit_raw   = int(parts[4])
    chat_id     = cq.message.chat.id

    # Strict group isolation: only honour the button in the chat it was created for
    if chat_id != origin_chat:
        return await cq.answer("❌ ᴛʜɪs ʙᴜᴛᴛᴏɴ ɪs ɴᴏᴛ ғᴏʀ ʏᴏᴜʀ ɢʀᴏᴜᴘ!", show_alert=True)

    existing = await get_game(chat_id)
    if existing:
        return await cq.answer("❌ ᴀ ɢᴀᴍᴇ ɪs ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ!", show_alert=True)

    # limit_raw == 0  →  unlimited
    max_att = None if limit_raw == 0 else limit_raw

    word = random.choice(WORDS[length])
    game = {
        "word":         word,
        "length":       length,
        "attempts":     0,
        "max_attempts": max_att,   # None = unlimited
        "guesses":      [],
        "start_time":   datetime.utcnow().isoformat(),
        "started_by":   cq.from_user.id,
    }
    await set_game(chat_id, game)

    att_display = "♾️ ᴜɴʟɪᴍɪᴛᴇᴅ" if max_att is None else f"{max_att} ɢᴜᴇssᴇs"

    await cq.message.edit_text(
        f"<blockquote>🎮 **ᴡᴏʀᴅsᴇᴇᴋ sᴛᴀʀᴛᴇᴅ!** {DIFFICULTY_EMO[length]}</blockquote>\n"
        f"<blockquote>ɢᴜᴇss ᴛʜᴇ **{length}-ʟᴇᴛᴛᴇʀ** ᴇɴɢʟɪsʜ ᴡᴏʀᴅ!\n"
        f"ɢᴜᴇss ʟɪᴍɪᴛ: **{att_display}**</blockquote>\n"
        f"<blockquote>🟩 ᴄᴏʀʀᴇᴄᴛ ᴘᴏsɪᴛɪᴏɴ\n"
        f"🟨 ᴡʀᴏɴɢ ᴘᴏsɪᴛɪᴏɴ (ʟᴇᴛᴛᴇʀ ɪs ɪɴ ᴛʜᴇ ᴡᴏʀᴅ)\n"
        f"🟥 ʟᴇᴛᴛᴇʀ ɴᴏᴛ ɪɴ ᴡᴏʀᴅ\n\n"
        f"ᴛʏᴘᴇ ʏᴏᴜʀ {length}-ʟᴇᴛᴛᴇʀ ɢᴜᴇss ʙᴇʟᴏᴡ 👇</blockquote>"
    )
    await cq.answer("🎯 ɢᴀᴍᴇ sᴛᴀʀᴛᴇᴅ! ɢᴏᴏᴅ ʟᴜᴄᴋ!")


@app.on_message(filters.command("wordseekend"))
async def cmd_wordseekend(client, message: Message):
    """Force-end an active game."""
    chat_id = message.chat.id
    game    = await get_game(chat_id)
    if not game:
        return await message.reply("<blockquote>❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ ɪɴ ᴛʜɪs ᴄʜᴀᴛ.</blockquote>", quote=True)
    word = game["word"]
    await del_game(chat_id)
    await message.reply(
        f"<blockquote>🛑 **ɢᴀᴍᴇ ᴇɴᴅᴇᴅ!**</blockquote>\n"
        f"<blockquote>ᴛʜᴇ ᴡᴏʀᴅ ᴡᴀs: **{word.upper()}**\n"
        f"ʙᴇᴛᴛᴇʀ ʟᴜᴄᴋ ɴᴇxᴛ ᴛɪᴍᴇ! 💪</blockquote>",
        quote=True,
    )


# ── Guess handler ─────────────────────────────────────────────────────────────
@app.on_message(
    filters.text & ~filters.command(_WS_COMMANDS),
    group=10,
)
async def handle_guess(client, message: Message):
    chat_id = message.chat.id
    game    = await get_game(chat_id)
    if not game:
        return

    user = message.from_user
    if not user:
        return

    guess  = message.text.strip().lower()
    length = game["length"]

    # ── Silent skip: wrong length or non-alpha (not meant as a guess) ─────────
    if len(guess) != length or not guess.isalpha():
        return

    # ── Validate: must be a known English word ────────────────────────────────
    if guess not in WORD_SETS[length]:
        return await message.reply(
            f"<blockquote>❌ **\"{guess.upper()}\"** — ɴᴏᴛ ᴀɴ ᴇɴɢʟɪsʜ ᴡᴏʀᴅ!\n"
            f"ᴋɴᴏᴡɴ {length}-ʟᴇᴛᴛᴇʀ ᴇɴɢʟɪsʜ ᴡᴏʀᴅ ᴍᴀᴛᴜᴍᴇ ᴇɴᴛᴇʀ ᴘᴀɴᴀᴠᴜᴍ.</blockquote>",
            quote=True,
        )

    # ── Duplicate guard ────────────────────────────────────────────────────────
    if guess in game.get("guesses", []):
        return await message.reply(
            f"<blockquote>⚠️ **\"{guess.upper()}\"** — ᴡᴏʀᴅ ᴀʟʀᴇᴀᴅʏ ɪɴ ᴛʜᴇ ʟɪsᴛ!\n"
            f"ʏᴏᴜ'ᴠᴇ ᴀʟʀᴇᴀᴅʏ ɢᴜᴇssᴇᴅ ᴛʜɪs ᴡᴏʀᴅ. ᴅɪғғᴇʀᴇɴᴛ ᴡᴏʀᴅ ᴛʀʏ ᴘᴀɴᴀᴠᴜᴍ.</blockquote>",
            quote=True,
        )

    word    = game["word"]
    max_att = game["max_attempts"]   # None = unlimited

    game["attempts"] = game.get("attempts", 0) + 1
    game.setdefault("guesses", []).append(guess)
    await set_game(chat_id, game)

    attempts = game["attempts"]
    board    = build_board(word, game["guesses"])
    att_str  = _fmt_attempts(attempts, max_att)

    # ── WIN ───────────────────────────────────────────────────────────────────
    if guess == word:
        elapsed = (
            datetime.utcnow() - _safe_fromisoformat(game["start_time"])
        ).total_seconds()
        total, base, tb, ab = calc_points(length, attempts, elapsed, max_att)
        await update_stats(
            chat_id, user.id,
            user.username or user.first_name,
            points=total, won=True,
        )
        await del_game(chat_id)
        tracker = build_alphabet_tracker(word, game["guesses"])
        return await message.reply(
            f"<blockquote>{board}</blockquote>\n"
            f"<blockquote>🏆 **{user.mention} ɢᴜᴇssᴇᴅ ɪᴛ!**\n"
            f"ᴡᴏʀᴅ: **{word.upper()}**\n"
            f"ᴀᴛᴛᴇᴍᴘᴛs: {att_str}\n\n"
            f"⭐ **+{total} ᴘᴏɪɴᴛs**\n"
            f"   └ ʙᴀsᴇ {base}  •  ᴛɪᴍᴇ ʙᴏɴᴜs +{tb}  •  ᴀᴛᴛᴇᴍᴘᴛ ʙᴏɴᴜs +{ab}\n\n"
            f"📝 ᴀʟᴘʜᴀʙᴇᴛ ᴛʀᴀᴄᴋᴇʀ:\n{tracker}</blockquote>",
            quote=True,
        )

    # ── GAME OVER (only when limit is set and exhausted) ──────────────────────
    if max_att is not None and attempts >= max_att:
        await del_game(chat_id)
        tracker = build_alphabet_tracker(word, game["guesses"])
        return await message.reply(
            f"<blockquote>{board}</blockquote>\n"
            f"<blockquote>💀 **ɢᴀᴍᴇ ᴏᴠᴇʀ!** ɴᴏ ᴍᴏʀᴇ ᴀᴛᴛᴇᴍᴘᴛs.\n"
            f"ᴛʜᴇ ᴡᴏʀᴅ ᴡᴀs: **{word.upper()}**</blockquote>\n"
            f"<blockquote>📝 ᴀʟᴘʜᴀʙᴇᴛ ᴛʀᴀᴄᴋᴇʀ:\n{tracker}</blockquote>",
            quote=True,
        )

    # ── CONTINUE ──────────────────────────────────────────────────────────────
    tracker = build_alphabet_tracker(word, game["guesses"])

    # Warn only when a finite limit is set and 3 or fewer attempts remain
    if max_att is not None:
        remaining = max_att - attempts
        hint_text = (
            f"\n<blockquote>⚠️ ᴏɴʟʏ **{remaining}** ᴀᴛᴛᴇᴍᴘᴛ{'s' if remaining > 1 else ''} ʟᴇғᴛ!</blockquote>"
            if remaining <= 3 else ""
        )
    else:
        hint_text = ""   # unlimited — no warning needed

    await message.reply(
        f"<blockquote>{board}</blockquote>\n"
        f"<blockquote>ᴀᴛᴛᴇᴍᴘᴛs: {att_str}{hint_text}\n\n"
        f"📝 ᴀʟᴘʜᴀʙᴇᴛ ᴛʀᴀᴄᴋᴇʀ:\n{tracker}</blockquote>",
        quote=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  LEADERBOARD
# ═══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("wordseektop"))
async def cmd_wordseektop(client, message: Message):
    chat_id = message.chat.id
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌍 ɢʟᴏʙᴀʟ-ᴀʟʟ",    callback_data="ws_lb_global_all"),
            InlineKeyboardButton("🌍 ᴡᴇᴇᴋʟʏ",      callback_data="ws_lb_global_weekly"),
        ],
        [
            InlineKeyboardButton("🌍 ᴍᴏɴᴛʜʟʏ",     callback_data="ws_lb_global_monthly"),
        ],
        [
            InlineKeyboardButton("💬 ᴛʜɪs ᴄʜᴀᴛ — ᴀʟʟ", callback_data=f"ws_lb_{chat_id}_all"),
            InlineKeyboardButton("💬 ᴡᴇᴇᴋʟʏ",   callback_data=f"ws_lb_{chat_id}_weekly"),
        ],
        [
            InlineKeyboardButton("💬 ᴍᴏɴᴛʜʟʏ",  callback_data=f"ws_lb_{chat_id}_monthly"),
        ],
    ])
    await message.reply(
        "📊 **ᴡᴏʀᴅsᴇᴇᴋ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ**\nᴄʜᴏᴏsᴇ ᴀ ᴄᴀᴛᴇɢᴏʀʏ:",
        reply_markup=buttons,
        quote=True,
    )


@app.on_callback_query(filters.regex(r"^ws_lb_"))
async def cb_leaderboard(client, cq: CallbackQuery):
    parts     = cq.data.split("_", 3)
    raw_scope = parts[2]
    period    = parts[3] if len(parts) > 3 else "all"
    if raw_scope == "global":
        scope       = "global"
        scope_label = "🌍 ɢʟᴏʙᴀʟ"
    else:
        scope       = f"chat:{raw_scope}"
        scope_label = "💬 ᴛʜɪs ᴄʜᴀᴛ"
    period_label = {
        "all":     "All-Time",
        "weekly":  "Weekly",
        "monthly": "Monthly",
    }.get(period, "All-Time")
    rows   = await get_leaderboard(scope, period)
    medals = ["🥇", "🥈", "🥉"]
    lines  = [f"<blockquote>📊 **{scope_label} — {period_label} ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ**</blockquote>\n"]
    if not rows:
        lines.append("_ɴᴏ ᴅᴀᴛᴀ ʏᴇᴛ! ᴘʟᴀʏ sᴏᴍᴇ ɢᴀᴍᴇs ғɪʀsᴛ._")
    else:
        for i, (uid, uname, pts, wins) in enumerate(rows):
            prefix = medals[i] if i < 3 else f"{i + 1}."
            lines.append(f"{prefix} **{uname}** — {pts} pts · {wins} wins")
    await cq.message.edit_text("\n".join(lines))
    await cq.answer()


# ═══════════════════════════════════════════════════════════════════════════════
#  PERSONAL RANK
# ═══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("wordseekrank"))
async def cmd_wordseekrank(client, message: Message):
    user    = message.from_user
    chat_id = message.chat.id
    all_s   = await get_user_stats(chat_id, user.id, user.username or user.first_name)
    g = all_s["global"]
    c = all_s["chat"]

    def streak_bar(n: int) -> str:
        if n == 0:
            return "—"
        return "🔥" * min(n, 10) + (f" x{n}" if n > 10 else "")

    await message.reply(
        f"<blockquote>📊 **{user.mention}'s ᴡᴏʀᴅsᴇᴇᴋ sᴛᴀᴛs**</blockquote>\n"
        f"<blockquote>**🌍 ɢʟᴏʙᴀʟ**\n"
        f"  🏆 ᴡɪɴs: `{g.get('wins', 0)}`\n"
        f"  ⭐ ᴛᴏᴛᴀʟ ᴘᴛs: `{g.get('points', 0)}`\n"
        f"  📅 ᴛʜɪs ᴡᴇᴇᴋ: `{g.get('weekly_points', 0)} pts`\n"
        f"  🗓 ᴛʜɪs ᴍᴏɴᴛʜ: `{g.get('monthly_points', 0)} pts`\n"
        f"  🔥 sᴛʀᴇᴀᴋ: {streak_bar(g.get('streak', 0))}  |  ʙᴇsᴛ: `{g.get('max_streak', 0)}`</blockquote>\n\n"
        f"<blockquote>**💬 ᴛʜɪs ᴄʜᴀᴛ**\n"
        f"  🏆 ᴡɪɴs: `{c.get('wins', 0)}`\n"
        f"  ⭐ ᴛᴏᴛᴀʟ ᴘᴛs: `{c.get('points', 0)}`\n"
        f"  📅 ᴛʜɪs ᴡᴇᴇᴋ: `{c.get('weekly_points', 0)} pts`\n"
        f"  🗓 ᴛʜɪs ᴍᴏɴᴛʜ: `{c.get('monthly_points', 0)} pts`\n"
        f"  🔥 sᴛʀᴇᴀᴋ: {streak_bar(c.get('streak', 0))}  |  ʙᴇsᴛ: `{c.get('max_streak', 0)}`</blockquote>",
        quote=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  HELP
# ═══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("wordseekhelp"))
async def cmd_wordseekhelp(client, message: Message):
    await message.reply(
        "<blockquote>🎮 **ᴡᴏʀᴅsᴇᴇᴋ — ʜᴇʟᴘ**\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "**Commands**\n"
        "/wordseek      — sᴛᴀʀᴛ ᴀ ɴᴇᴡ ɢᴀᴍᴇ\n"
        "/wordseekend   — ᴇɴᴅ ᴛʜᴇ ᴄᴜʀʀᴇɴᴛ ɢᴀᴍᴇ\n"
        "/wordseektop   — ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ (6 ᴠɪᴇᴡs)\n"
        "/wordseekrank  — ʏᴏᴜʀ ᴘᴇʀsᴏɴᴀʟ sᴛᴀᴛs\n"
        "/wordseekhelp  — ᴛʜɪs ʜᴇʟᴘ ᴍᴇssᴀɢᴇ\n\n"
        "━━━━━━━━━━━━━━━━━━━━</blockquote>\n"
        "<blockquote>**ʜᴏᴡ ᴛᴏ ᴘʟᴀʏ**\n"
        "1. /wordseek ᴛʏᴘᴇ ᴘᴀɴɴɪ **ᴡᴏʀᴅ ʟᴇɴɢᴛʜ** sᴇʟᴇᴄᴛ ᴘᴀɴᴀᴠᴜᴍ.\n"
        "2. ᴛʜᴇɴ **ɢᴜᴇss ʟɪᴍɪᴛ** sᴇʟᴇᴄᴛ ᴘᴀɴᴀᴠᴜᴍ (10 / 15 / 20 / 30 / ♾️).\n"
        "3. ɢᴀᴍᴇ sᴛᴀʀᴛ ᴀᴀɢᴜᴍ — ᴄᴏʀʀᴇᴄᴛ ʟᴇɴɢᴛʜ ᴏғ ᴇɴɢʟɪsʜ ᴡᴏʀᴅ ᴛʏᴘᴇ ᴘᴀɴᴀᴠᴜᴍ.\n"
        "4. ᴄᴏʟᴏᴜʀ ғᴇᴇᴅʙᴀᴄᴋ ᴘᴀᴛᴛᴜ ᴡᴏʀᴅ ɢᴜᴇss ᴘᴀɴᴀᴠᴜᴍ!\n\n"
        "⚠️ ᴡᴏʀᴅ ʟɪsᴛ-ʟᴀ ɪʟʟᴀᴛʜᴀ / ᴍᴇᴀɴɪɴɢ ɪʟʟᴀᴛʜᴀ ᴡᴏʀᴅs ᴀᴄᴄᴇᴘᴛ ᴘᴀɴᴀ ᴍᴀᴛᴛᴇɴ.\n"
        "⚠️ ᴀʟʀᴇᴀᴅʏ ɢᴜᴇssᴇᴅ ᴡᴏʀᴅ ᴛɪʀᴜᴍʙᴀ ᴛʏᴘᴇ ᴘᴀɴɴᴀ ᴋᴜᴅᴀᴛʜᴜ.\n\n"
        "🟩 — ᴄᴏʀʀᴇᴄᴛ ʟᴇᴛᴛᴇʀ, ᴄᴏʀʀᴇᴄᴛ ᴘᴏsɪᴛɪᴏɴ\n"
        "🟨 — ᴄᴏʀʀᴇᴄᴛ ʟᴇᴛᴛᴇʀ, ᴡʀᴏɴɢ ᴘᴏsɪᴛɪᴏɴ\n"
        "🟥 — ʟᴇᴛᴛᴇʀ ɪs ɴᴏᴛ ɪɴ ᴛʜᴇ ᴡᴏʀᴅ\n\n"
        "━━━━━━━━━━━━━━━━━━━━</blockquote>\n"
        "<blockquote>**ɢᴜᴇss ʟɪᴍɪᴛs**\n"
        "🔟  10 ʟɪᴍɪᴛ  — ᴄʜᴀʟʟᴇɴɢɪɴɢ\n"
        "1️⃣5️⃣ 15 ʟɪᴍɪᴛ  — ᴍᴇᴅɪᴜᴍ\n"
        "2️⃣0️⃣ 20 ʟɪᴍɪᴛ  — ᴄᴏᴍғᴏʀᴛᴀʙʟᴇ\n"
        "3️⃣0️⃣ 30 ʟɪᴍɪᴛ  — ʀᴇʟᴀxᴇᴅ\n"
        "♾️  ᴜɴʟɪᴍɪᴛᴇᴅ — ᴄᴏʀʀᴇᴄᴛ ᴡᴏʀᴅ ɢᴜᴇss ᴘᴀɴᴅʀᴀ ᴠᴀʀᴀɪᴋᴜᴍ ᴘʟᴀʏ ᴄᴏɴᴛɪɴᴜᴇ ᴀᴀɢᴜᴍ</blockquote>\n"
        "<blockquote>**ᴅɪғғɪᴄᴜʟᴛʏ & ᴘᴏɪɴᴛs**\n"
        f"4️⃣  4 ʟᴇᴛᴛᴇʀs — {BASE_POINTS[4]} ʙᴀsᴇ ᴘᴛs\n"
        f"5️⃣  5 ʟᴇᴛᴛᴇʀs — {BASE_POINTS[5]} ʙᴀsᴇ ᴘᴛs\n"
        f"6️⃣  6 ʟᴇᴛᴛᴇʀs — {BASE_POINTS[6]} ʙᴀsᴇ ᴘᴛs</blockquote>\n\n"
        "<blockquote>**ʙᴏɴᴜs ᴘᴏɪɴᴛs**\n"
        "⚡ ᴛɪᴍᴇ ʙᴏɴᴜs   — sᴏʟᴠᴇ ғᴀsᴛᴇʀ → ᴍᴏʀᴇ ᴘᴛs\n"
        "🎯 ᴀᴛᴛᴇᴍᴘᴛ ʙᴏɴᴜs — ғᴇᴡᴇʀ ɢᴜᴇssᴇs → ᴍᴏʀᴇ ᴘᴛs\n"
        "🔥 sᴛʀᴇᴀᴋ       — sʜᴏᴡɴ ɪɴ /wordseekrank</blockquote>\n"
        "<blockquote>━━━━━━━━━━━━━━━━━━━━\n"
        "**ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅs**\n"
        "📊 ɢʟᴏʙᴀʟ, ᴘᴇʀ-ᴄʜᴀᴛ, ᴡᴇᴇᴋʟʏ & ᴍᴏɴᴛʜʟʏ\n"
        "ᴘᴇʀɪᴏᴅs ʀᴇsᴇᴛ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ᴇᴠᴇʀʏ 7 / 30 ᴅᴀʏs.\n"
        "━━━━━━━━━━━━━━━━━━━━</blockquote>\n"
        "<blockquote>**ʙᴏᴛ sᴇᴛᴜᴘ ʀᴇᴍɪɴᴅᴇʀ**\n"
        "ᴅɪsᴀʙʟᴇ ᴘʀɪᴠᴀᴄʏ ᴍᴏᴅᴇ ɪɴ ʙᴏᴛғᴀᴛʜᴇʀ:\n"
        "/setprivacy → ᴅɪsᴀʙʟᴇ\n"
        "ᴏᴛʜᴇʀᴡɪsᴇ ᴛʜᴇ ʙᴏᴛ ᴄᴀɴɴᴏᴛ ʀᴇᴀᴅ ɢʀᴏᴜᴘ ᴍᴇssᴀɢᴇs.</blockquote>",
        quote=True,
    )


__menu__     = "CMD_GAMES"
__mod_name__ = "H_B_79"
__help__ = """
🔻 /wordseekhelp -  ꜰᴜʟʟ ᴄᴏᴍᴍᴀɴᴅ ʟɪꜱᴛ
🔻 /wordseek - ꜱᴛᴀʀᴛ ᴀ ɴᴇᴡ ᴡᴏʀᴅꜱᴇᴇᴋ ɢᴀᴍᴇ
🔻 /wordseekend - ꜰᴏʀᴄᴇ ꜱᴛᴏᴘ ᴛʜᴇ ᴄᴜʀʀᴇɴᴛ ɢᴀᴍᴇ
🔻 /wordseektop - ꜱʜᴏᴡ ᴡᴏʀᴅꜱᴇᴇᴋ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ (ɢʟᴏʙᴀʟ / ᴄʜᴀᴛ / ᴡᴇᴇᴋʟʏ / ᴍᴏɴᴛʜʟʏ)
🔻 /wordseekrank - ᴠɪᴇᴡ ʏᴏᴜʀ ᴡᴏʀᴅꜱᴇᴇᴋ ꜱᴛᴀᴛꜱ & ꜱᴛʀᴇᴀᴋ
🔻 /wordseekhelp - ꜰᴜʟʟ ᴄᴏᴍᴍᴀɴᴅ ʟɪꜱᴛ & ɢᴀᴍᴇ ɢᴜɪᴅᴇ
"""
