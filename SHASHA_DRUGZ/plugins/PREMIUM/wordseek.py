# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║              WORDSEEK MODULE — SHASHA FINAL EDITION v4                      ║
# ║                                                                              ║
# ║  v4 ROOT CAUSE FIX:                                                          ║
# ║  ✅ ALL message.reply() calls now have parse_mode="html" explicitly          ║
# ║     (missing parse_mode = Telegram rejects mixed markdown+HTML silently)     ║
# ║  ✅ handle_guess wrapped in try/except → errors now logged, not swallowed    ║
# ║  ✅ board text sent inside <pre> block — emoji safe, no HTML parse conflict  ║
# ║  ✅ All ** bold ** replaced with <b>bold</b> HTML tags throughout            ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

import os
import re
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

from SHASHA_DRUGZ import app
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

WORD_SETS: dict[int, set] = {length: set(words) for length, words in WORDS.items()}

BASE_POINTS    = {4: 8,  5: 10, 6: 14}
DIFFICULTY_EMO = {4: "🟢 Easy", 5: "🟡 Medium", 6: "🔴 Hard"}
GUESS_LIMITS   = [10, 15, 20, 30, 0]
GAME_TTL       = 3600

_WS_COMMANDS = [
    "wordseek", "wordseekend", "wordseektop",
    "wordseekrank", "wordseekhelp",
]

_WS_LIMIT_RE = re.compile(r"^ws_limit_(-?\d+)_([456])_(\d+)$")

# ═══════════════════════════════════════════════════════════════════════════════
#  REDIS / IN-MEMORY LAYER
# ═══════════════════════════════════════════════════════════════════════════════
_redis_client = None
_mem_games: dict = {}
_mem_stats: dict = {}


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
        return _redis_client
    except Exception as exc:
        logger.warning("[WordSeek] Redis unavailable: %s", exc)
        _redis_client = None
        return None


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


def _blank_stats(username: str) -> dict:
    now = datetime.utcnow().isoformat()
    return {
        "username": username, "wins": 0, "points": 0,
        "streak": 0, "max_streak": 0,
        "weekly_points": 0, "monthly_points": 0,
        "week_start": now, "month_start": now,
    }


def _safe_fromisoformat(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s.split("+")[0].rstrip("Z"))
    except Exception:
        return datetime.utcnow()


def _apply_period_reset(data: dict) -> dict:
    now = datetime.utcnow()
    if now - _safe_fromisoformat(data.get("week_start", now.isoformat())) >= timedelta(weeks=1):
        data["weekly_points"] = 0
        data["week_start"] = now.isoformat()
    if now - _safe_fromisoformat(data.get("month_start", now.isoformat())) >= timedelta(days=30):
        data["monthly_points"] = 0
        data["month_start"] = now.isoformat()
    return data


async def _load_stats(scope: str, user_id: int, username: str) -> dict:
    key = f"ws:stats:{scope}:{user_id}"
    r = await _get_redis()
    if r:
        try:
            raw = await r.get(key)
            return json.loads(raw) if raw else _blank_stats(username)
        except Exception:
            pass
    return _mem_stats.get(f"{scope}:{user_id}", _blank_stats(username))


async def _save_stats(scope: str, user_id: int, data: dict) -> None:
    key = f"ws:stats:{scope}:{user_id}"
    r = await _get_redis()
    if r:
        try:
            await r.set(key, json.dumps(data))
            return
        except Exception:
            pass
    _mem_stats[f"{scope}:{user_id}"] = data


async def update_stats(chat_id, user_id, username, *, points=0, won=False):
    for scope in ("global", f"chat:{chat_id}"):
        data = await _load_stats(scope, user_id, username)
        data = _apply_period_reset(data)
        data["username"] = username
        if won:
            data["wins"] += 1
            data["points"] += points
            data["weekly_points"] += points
            data["monthly_points"] += points
            data["streak"] = data.get("streak", 0) + 1
            data["max_streak"] = max(data.get("max_streak", 0), data["streak"])
        else:
            data["streak"] = 0
        await _save_stats(scope, user_id, data)


async def get_leaderboard(scope: str, period: str = "all", limit: int = 10) -> list:
    pts_key = {"all": "points", "weekly": "weekly_points", "monthly": "monthly_points"}.get(period, "points")
    results = []
    r = await _get_redis()
    if r:
        try:
            keys = await r.keys(f"ws:stats:{scope}:*")
            for key in keys:
                raw = await r.get(key)
                if not raw:
                    continue
                data = _apply_period_reset(json.loads(raw))
                uid = key.split(":")[-1]
                results.append((uid, data.get("username", uid), data.get(pts_key, 0), data.get("wins", 0)))
        except Exception as exc:
            logger.warning("[WordSeek] Redis get_leaderboard error: %s", exc)
    if not results:
        prefix = f"{scope}:"
        for mem_key, data in _mem_stats.items():
            if not mem_key.startswith(prefix):
                continue
            data = _apply_period_reset(data)
            uid = mem_key[len(prefix):]
            results.append((uid, data.get("username", uid), data.get(pts_key, 0), data.get("wins", 0)))
    results.sort(key=lambda x: x[2], reverse=True)
    return results[:limit]


async def get_user_stats(chat_id, user_id, username):
    return {
        "global": _apply_period_reset(await _load_stats("global", user_id, username)),
        "chat":   _apply_period_reset(await _load_stats(f"chat:{chat_id}", user_id, username)),
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  GAME LOGIC
# ═══════════════════════════════════════════════════════════════════════════════
_SQ_GREEN  = "🟩"
_SQ_YELLOW = "🟨"
_SQ_RED    = "🟥"


def build_feedback(word: str, guess: str) -> list[str]:
    marks     = [_SQ_RED] * len(guess)
    word_pool = list(word)
    for i, ch in enumerate(guess):
        if ch == word_pool[i]:
            marks[i]     = _SQ_GREEN
            word_pool[i] = None
    for i, ch in enumerate(guess):
        if marks[i] == _SQ_GREEN:
            continue
        if ch in word_pool:
            marks[i] = _SQ_YELLOW
            word_pool[word_pool.index(ch)] = None
    return marks


def build_board(word: str, guesses: list) -> str:
    lines = []
    for g in guesses:
        squares = "".join(build_feedback(word, g))
        lines.append(f"{squares}  {g.upper()}")
    return "\n".join(lines)


def _fmt_attempts(attempts: int, max_att) -> str:
    return f"{attempts}/♾️" if max_att is None else f"{attempts}/{max_att}"


def calc_points(length, attempts, elapsed_secs, max_att=None):
    base          = BASE_POINTS[length]
    ref_max       = max_att if max_att is not None else 30
    attempt_bonus = max(0, ref_max - attempts)
    time_bonus    = max(0, int((300 - elapsed_secs) / 60))
    return base + attempt_bonus + time_bonus, base, time_bonus, attempt_bonus


# ═══════════════════════════════════════════════════════════════════════════════
#  COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.command("wordseek"))
async def cmd_wordseek(client, message: Message):
    chat_id  = message.chat.id
    existing = await get_game(chat_id)
    if existing:
        w       = existing["word"]
        att     = existing["attempts"]
        max_att = existing["max_attempts"]
        att_str = _fmt_attempts(att, max_att)
        return await message.reply(
            f"<blockquote>⚠️ <b>ᴀ ɢᴀᴍᴇ ɪs ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ!</b>\n"
            f"ʟᴇɴɢᴛʜ: <b>{len(w)} ʟᴇᴛᴛᴇʀs</b> | ᴀᴛᴛᴇᴍᴘᴛs: {att_str}\n\n"
            f"ᴜsᴇ /wordseekend ᴛᴏ sᴛᴏᴘ ɪᴛ ғɪʀsᴛ.</blockquote>",
            parse_mode="html",
            quote=True,
        )
    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("4️⃣ 4 ʟᴇᴛᴛᴇʀs", callback_data="ws_start_4"),
        InlineKeyboardButton("5️⃣ 5 ʟᴇᴛᴛᴇʀs", callback_data="ws_start_5"),
        InlineKeyboardButton("6️⃣ 6 ʟᴇᴛᴛᴇʀs", callback_data="ws_start_6"),
    ]])
    await message.reply(
        f"<blockquote>🎮 <b>ᴡᴏʀᴅsᴇᴇᴋ — ᴄʜᴏᴏsᴇ ᴡᴏʀᴅ ʟᴇɴɢᴛʜ</b>\n\n"
        f"4️⃣  <b>4 ʟᴇᴛᴛᴇʀs</b> — {DIFFICULTY_EMO[4]}  ({BASE_POINTS[4]} ʙᴀsᴇ ᴘᴛs)\n"
        f"5️⃣  <b>5 ʟᴇᴛᴛᴇʀs</b> — {DIFFICULTY_EMO[5]}  ({BASE_POINTS[5]} ʙᴀsᴇ ᴘᴛs)\n"
        f"6️⃣  <b>6 ʟᴇᴛᴛᴇʀs</b> — {DIFFICULTY_EMO[6]}  ({BASE_POINTS[6]} ʙᴀsᴇ ᴘᴛs)</blockquote>",
        parse_mode="html",
        reply_markup=buttons,
        quote=True,
    )


@app.on_callback_query(filters.regex(r"^ws_start_([456])$"))
async def cb_choose_length(client, cq: CallbackQuery):
    chat_id  = cq.message.chat.id
    length   = int(cq.data[-1])
    existing = await get_game(chat_id)
    if existing:
        return await cq.answer("❌ ᴀ ɢᴀᴍᴇ ɪs ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ!", show_alert=True)
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔟 10 ʟɪᴍɪᴛ",    callback_data=f"ws_limit_{chat_id}_{length}_10"),
            InlineKeyboardButton("1️⃣5️⃣ 15 ʟɪᴍɪᴛ", callback_data=f"ws_limit_{chat_id}_{length}_15"),
        ],
        [
            InlineKeyboardButton("2️⃣0️⃣ 20 ʟɪᴍɪᴛ", callback_data=f"ws_limit_{chat_id}_{length}_20"),
            InlineKeyboardButton("3️⃣0️⃣ 30 ʟɪᴍɪᴛ", callback_data=f"ws_limit_{chat_id}_{length}_30"),
        ],
        [
            InlineKeyboardButton("♾️ ᴜɴʟɪᴍɪᴛᴇᴅ", callback_data=f"ws_limit_{chat_id}_{length}_0"),
        ],
    ])
    await cq.message.edit_text(
        f"<blockquote>🎮 <b>ᴄʜᴏᴏsᴇ ɢᴜᴇss ʟɪᴍɪᴛ</b>\n\n"
        f"{DIFFICULTY_EMO[length]} — <b>{length}-ʟᴇᴛᴛᴇʀ ᴡᴏʀᴅ</b> sᴇʟᴇᴄᴛᴇᴅ!\n\n"
        f"🔟  <b>10</b> — ᴄʜᴀʟʟᴇɴɢɪɴɢ\n"
        f"1️⃣5️⃣ <b>15</b> — ᴍᴇᴅɪᴜᴍ\n"
        f"2️⃣0️⃣ <b>20</b> — ᴄᴏᴍғᴏʀᴛᴀʙʟᴇ\n"
        f"3️⃣0️⃣ <b>30</b> — ʀᴇʟᴀxᴇᴅ\n"
        f"♾️  <b>ᴜɴʟɪᴍɪᴛᴇᴅ</b></blockquote>",
        parse_mode="html",
        reply_markup=buttons,
    )
    await cq.answer()


@app.on_callback_query(filters.regex(r"^ws_limit_(-?\d+)_([456])_(\d+)$"))
async def cb_start_game(client, cq: CallbackQuery):
    m = _WS_LIMIT_RE.match(cq.data)
    if not m:
        return await cq.answer("❌ ɪɴᴠᴀʟɪᴅ ᴅᴀᴛᴀ.", show_alert=True)

    origin_chat = int(m.group(1))
    length      = int(m.group(2))
    limit_raw   = int(m.group(3))
    chat_id     = cq.message.chat.id

    if chat_id != origin_chat:
        return await cq.answer("❌ ɴᴏᴛ ʏᴏᴜʀ ɢʀᴏᴜᴘ!", show_alert=True)

    existing = await get_game(chat_id)
    if existing:
        return await cq.answer("❌ ɢᴀᴍᴇ ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ!", show_alert=True)

    max_att = None if limit_raw == 0 else limit_raw
    word    = random.choice(WORDS[length])
    game    = {
        "word":         word,
        "length":       length,
        "attempts":     0,
        "max_attempts": max_att,
        "guesses":      [],
        "start_time":   datetime.utcnow().isoformat(),
        "started_by":   cq.from_user.id,
    }
    await set_game(chat_id, game)

    att_display = "♾️ ᴜɴʟɪᴍɪᴛᴇᴅ" if max_att is None else f"{max_att} ɢᴜᴇssᴇs"
    await cq.message.edit_text(
        f"<blockquote>🎮 <b>ᴡᴏʀᴅsᴇᴇᴋ sᴛᴀʀᴛᴇᴅ!</b> {DIFFICULTY_EMO[length]}\n\n"
        f"ɢᴜᴇss ᴛʜᴇ <b>{length}-ʟᴇᴛᴛᴇʀ</b> ᴇɴɢʟɪsʜ ᴡᴏʀᴅ!\n"
        f"ɢᴜᴇss ʟɪᴍɪᴛ: <b>{att_display}</b>\n\n"
        f"🟩 ᴄᴏʀʀᴇᴄᴛ ᴘᴏsɪᴛɪᴏɴ\n"
        f"🟨 ᴡʀᴏɴɢ ᴘᴏsɪᴛɪᴏɴ\n"
        f"🟥 ɴᴏᴛ ɪɴ ᴡᴏʀᴅ\n\n"
        f"ᴛʏᴘᴇ ʏᴏᴜʀ <b>{length}-ʟᴇᴛᴛᴇʀ</b> ɢᴜᴇss ʙᴇʟᴏᴡ 👇</blockquote>",
        parse_mode="html",
    )
    await cq.answer("🎯 ɢᴀᴍᴇ sᴛᴀʀᴛᴇᴅ!")


@app.on_message(filters.command("wordseekend"))
async def cmd_wordseekend(client, message: Message):
    chat_id = message.chat.id
    game    = await get_game(chat_id)
    if not game:
        return await message.reply(
            "<blockquote>❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ.</blockquote>",
            parse_mode="html",
            quote=True,
        )
    word = game["word"]
    await del_game(chat_id)
    await message.reply(
        f"<blockquote>🛑 <b>ɢᴀᴍᴇ ᴇɴᴅᴇᴅ!</b>\n"
        f"ᴛʜᴇ ᴡᴏʀᴅ ᴡᴀs: <b>{word.upper()}</b>\n"
        f"ʙᴇᴛᴛᴇʀ ʟᴜᴄᴋ ɴᴇxᴛ ᴛɪᴍᴇ! 💪</blockquote>",
        parse_mode="html",
        quote=True,
    )


# ── Guess handler ─────────────────────────────────────────────────────────────
@app.on_message(
    filters.text & ~filters.command(_WS_COMMANDS),
    group=10,
)
async def handle_guess(client, message: Message):
    # ══════════════════════════════════════════════════════════════════════════
    # Entire handler in try/except — previously silent exceptions were why
    # the bot never replied after valid guesses.
    # ══════════════════════════════════════════════════════════════════════════
    try:
        chat_id = message.chat.id
        game    = await get_game(chat_id)
        if not game:
            return

        user = message.from_user
        if not user:
            return

        guess  = message.text.strip().lower()
        length = game["length"]

        # Silent skip — not a guess-length word
        if len(guess) != length or not guess.isalpha():
            return

        # Unknown word
        if guess not in WORD_SETS[length]:
            return await message.reply(
                f"<blockquote>❌ <b>{guess.upper()}</b> — ɴᴏᴛ ᴀɴ ᴇɴɢʟɪsʜ ᴡᴏʀᴅ!\n"
                f"ᴋɴᴏᴡɴ {length}-ʟᴇᴛᴛᴇʀ ᴡᴏʀᴅ ᴍᴀᴛᴜᴍᴇ ᴇɴᴛᴇʀ ᴘᴀɴᴀᴠᴜᴍ.</blockquote>",
                parse_mode="html",
                quote=True,
            )

        # Duplicate
        if guess in game.get("guesses", []):
            return await message.reply(
                f"<blockquote>⚠️ <b>{guess.upper()}</b> — ᴀʟʀᴇᴀᴅʏ ɢᴜᴇssᴇᴅ!\n"
                f"ᴅɪғғᴇʀᴇɴᴛ ᴡᴏʀᴅ ᴛʀʏ ᴘᴀɴᴀᴠᴜᴍ.</blockquote>",
                parse_mode="html",
                quote=True,
            )

        word    = game["word"]
        max_att = game["max_attempts"]  # None = unlimited

        # Update state
        game["attempts"] = game.get("attempts", 0) + 1
        game.setdefault("guesses", []).append(guess)
        await set_game(chat_id, game)

        attempts = game["attempts"]
        board    = build_board(word, game["guesses"])
        att_str  = _fmt_attempts(attempts, max_att)

        # ── WIN ───────────────────────────────────────────────────────────────
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
            return await message.reply(
                f"<blockquote><pre>{board}</pre></blockquote>\n"
                f"<blockquote>🏆 {user.mention} <b>ɢᴜᴇssᴇᴅ ɪᴛ!</b>\n"
                f"ᴡᴏʀᴅ: <b>{word.upper()}</b>\n"
                f"ᴀᴛᴛᴇᴍᴘᴛs: {att_str}\n\n"
                f"⭐ <b>+{total} ᴘᴏɪɴᴛs</b>\n"
                f"   └ ʙᴀsᴇ {base}  •  ᴛɪᴍᴇ +{tb}  •  ᴀᴛᴛᴇᴍᴘᴛ +{ab}</blockquote>",
                parse_mode="html",
                quote=True,
            )

        # ── GAME OVER ─────────────────────────────────────────────────────────
        if max_att is not None and attempts >= max_att:
            await del_game(chat_id)
            return await message.reply(
                f"<blockquote><pre>{board}</pre></blockquote>\n"
                f"<blockquote>💀 <b>ɢᴀᴍᴇ ᴏᴠᴇʀ!</b> ɴᴏ ᴍᴏʀᴇ ᴀᴛᴛᴇᴍᴘᴛs.\n"
                f"ᴛʜᴇ ᴡᴏʀᴅ ᴡᴀs: <b>{word.upper()}</b></blockquote>",
                parse_mode="html",
                quote=True,
            )

        # ── CONTINUE ──────────────────────────────────────────────────────────
        hint_text = ""
        if max_att is not None:
            remaining = max_att - attempts
            if remaining <= 3:
                s = "s" if remaining > 1 else ""
                hint_text = (
                    f"\n<blockquote>⚠️ ᴏɴʟʏ <b>{remaining}</b> ᴀᴛᴛᴇᴍᴘᴛ{s} ʟᴇғᴛ!</blockquote>"
                )

        await message.reply(
            f"<blockquote><pre>{board}</pre></blockquote>\n"
            f"<blockquote>ᴀᴛᴛᴇᴍᴘᴛs: {att_str}</blockquote>"
            f"{hint_text}",
            parse_mode="html",
            quote=True,
        )

    except Exception as exc:
        # This is the critical line — before this, all errors were silent
        logger.error("[WordSeek] handle_guess CRASHED: %s", exc, exc_info=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  LEADERBOARD
# ═══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("wordseektop"))
async def cmd_wordseektop(client, message: Message):
    chat_id = message.chat.id
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌍 ɢʟᴏʙᴀʟ-ᴀʟʟ",       callback_data="ws_lb_global_all"),
            InlineKeyboardButton("🌍 ᴡᴇᴇᴋʟʏ",            callback_data="ws_lb_global_weekly"),
        ],
        [
            InlineKeyboardButton("🌍 ᴍᴏɴᴛʜʟʏ",           callback_data="ws_lb_global_monthly"),
        ],
        [
            InlineKeyboardButton("💬 ᴛʜɪs ᴄʜᴀᴛ-ᴀʟʟ",     callback_data=f"ws_lb_{chat_id}_all"),
            InlineKeyboardButton("💬 ᴡᴇᴇᴋʟʏ",            callback_data=f"ws_lb_{chat_id}_weekly"),
        ],
        [
            InlineKeyboardButton("💬 ᴍᴏɴᴛʜʟʏ",           callback_data=f"ws_lb_{chat_id}_monthly"),
        ],
    ])
    await message.reply(
        "<b>📊 ᴡᴏʀᴅsᴇᴇᴋ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ</b>\nᴄʜᴏᴏsᴇ ᴀ ᴄᴀᴛᴇɢᴏʀʏ:",
        parse_mode="html",
        reply_markup=buttons,
        quote=True,
    )


@app.on_callback_query(filters.regex(r"^ws_lb_"))
async def cb_leaderboard(client, cq: CallbackQuery):
    parts     = cq.data.split("_", 3)
    raw_scope = parts[2]
    period    = parts[3] if len(parts) > 3 else "all"

    if raw_scope == "global":
        scope, scope_label = "global", "🌍 ɢʟᴏʙᴀʟ"
    else:
        scope, scope_label = f"chat:{raw_scope}", "💬 ᴛʜɪs ᴄʜᴀᴛ"

    period_label = {"all": "All-Time", "weekly": "Weekly", "monthly": "Monthly"}.get(period, "All-Time")
    rows   = await get_leaderboard(scope, period)
    medals = ["🥇", "🥈", "🥉"]
    lines  = [f"<blockquote><b>📊 {scope_label} — {period_label}</b></blockquote>"]

    if not rows:
        lines.append("ɴᴏ ᴅᴀᴛᴀ ʏᴇᴛ.")
    else:
        for i, (uid, uname, pts, wins) in enumerate(rows):
            prefix = medals[i] if i < 3 else f"{i+1}."
            lines.append(f"{prefix} <b>{uname}</b> — {pts} pts · {wins} wins")

    await cq.message.edit_text("\n".join(lines), parse_mode="html")
    await cq.answer()


# ═══════════════════════════════════════════════════════════════════════════════
#  PERSONAL RANK
# ═══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("wordseekrank"))
async def cmd_wordseekrank(client, message: Message):
    user    = message.from_user
    chat_id = message.chat.id
    all_s   = await get_user_stats(chat_id, user.id, user.username or user.first_name)
    g, c    = all_s["global"], all_s["chat"]

    def streak_bar(n):
        return "—" if n == 0 else "🔥" * min(n, 10) + (f" x{n}" if n > 10 else "")

    await message.reply(
        f"<blockquote><b>📊 {user.mention} ᴡᴏʀᴅsᴇᴇᴋ sᴛᴀᴛs</b></blockquote>\n"
        f"<blockquote><b>🌍 ɢʟᴏʙᴀʟ</b>\n"
        f"  🏆 ᴡɪɴs: <code>{g.get('wins',0)}</code>\n"
        f"  ⭐ ᴘᴏɪɴᴛs: <code>{g.get('points',0)}</code>\n"
        f"  📅 ᴡᴇᴇᴋ: <code>{g.get('weekly_points',0)}</code>\n"
        f"  🗓 ᴍᴏɴᴛʜ: <code>{g.get('monthly_points',0)}</code>\n"
        f"  🔥 sᴛʀᴇᴀᴋ: {streak_bar(g.get('streak',0))} | ʙᴇsᴛ: <code>{g.get('max_streak',0)}</code></blockquote>\n"
        f"<blockquote><b>💬 ᴛʜɪs ᴄʜᴀᴛ</b>\n"
        f"  🏆 ᴡɪɴs: <code>{c.get('wins',0)}</code>\n"
        f"  ⭐ ᴘᴏɪɴᴛs: <code>{c.get('points',0)}</code>\n"
        f"  📅 ᴡᴇᴇᴋ: <code>{c.get('weekly_points',0)}</code>\n"
        f"  🗓 ᴍᴏɴᴛʜ: <code>{c.get('monthly_points',0)}</code>\n"
        f"  🔥 sᴛʀᴇᴀᴋ: {streak_bar(c.get('streak',0))} | ʙᴇsᴛ: <code>{c.get('max_streak',0)}</code></blockquote>",
        parse_mode="html",
        quote=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  HELP
# ═══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("wordseekhelp"))
async def cmd_wordseekhelp(client, message: Message):
    await message.reply(
        "<blockquote><b>🎮 ᴡᴏʀᴅsᴇᴇᴋ — ʜᴇʟᴘ</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "/wordseek      — sᴛᴀʀᴛ ɢᴀᴍᴇ\n"
        "/wordseekend   — ᴇɴᴅ ɢᴀᴍᴇ\n"
        "/wordseektop   — ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ\n"
        "/wordseekrank  — ʏᴏᴜʀ sᴛᴀᴛs\n"
        "/wordseekhelp  — ᴛʜɪs ᴍᴇssᴀɢᴇ\n"
        "━━━━━━━━━━━━━━━━━━━━</blockquote>\n"
        "<blockquote><b>ʜᴏᴡ ᴛᴏ ᴘʟᴀʏ</b>\n"
        "1. /wordseek → ᴡᴏʀᴅ ʟᴇɴɢᴛʜ sᴇʟᴇᴄᴛ ᴘᴀɴᴀᴠᴜᴍ\n"
        "2. ɢᴜᴇss ʟɪᴍɪᴛ sᴇʟᴇᴄᴛ ᴘᴀɴᴀᴠᴜᴍ\n"
        "3. ᴄᴏʀʀᴇᴄᴛ ʟᴇɴɢᴛʜ ᴇɴɢʟɪsʜ ᴡᴏʀᴅ ᴛʏᴘᴇ ᴘᴀɴᴀᴠᴜᴍ\n\n"
        "🟩 ᴄᴏʀʀᴇᴄᴛ ᴘᴏsɪᴛɪᴏɴ\n"
        "🟨 ᴡʀᴏɴɢ ᴘᴏsɪᴛɪᴏɴ\n"
        "🟥 ɴᴏᴛ ɪɴ ᴡᴏʀᴅ</blockquote>\n"
        f"<blockquote><b>ᴘᴏɪɴᴛs</b>\n"
        f"4️⃣ {BASE_POINTS[4]} ʙᴀsᴇ  5️⃣ {BASE_POINTS[5]} ʙᴀsᴇ  6️⃣ {BASE_POINTS[6]} ʙᴀsᴇ\n"
        f"⚡ ᴛɪᴍᴇ ʙᴏɴᴜs + 🎯 ᴀᴛᴛᴇᴍᴘᴛ ʙᴏɴᴜs</blockquote>",
        parse_mode="html",
        quote=True,
    )


__menu__     = "CMD_GAMES"
__mod_name__ = "H_B_79"
__help__ = """
🔻 /wordseekhelp - ꜰᴜʟʟ ɢᴜɪᴅᴇ
🔻 /wordseek - ꜱᴛᴀʀᴛ ɢᴀᴍᴇ
🔻 /wordseekend - ꜱᴛᴏᴘ ɢᴀᴍᴇ
🔻 /wordseektop - ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ
🔻 /wordseekrank - ʏᴏᴜʀ ꜱᴛᴀᴛꜱ
"""
