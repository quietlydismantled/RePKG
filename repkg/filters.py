"""Noise filtering — patterns for junk that nearly every install touches."""
import re

# Filesystem path substrings / suffixes considered noise (case-insensitive).
NOISE_FILE_PATTERNS = [
    r"\\temp\\",
    r"\\tmp\\",
    r"\\prefetch\\",
    r"\\inetcache\\",
    r"\\windows\\softwaredistribution\\",
    r"\\microsoft\\windows\\wer\\",
    r"\\microsoft\\windows\\caches\\",
    r"\\fontcache",
    r"\\thumbcache",
    r"\.log$",
    r"\.tmp$",
    r"\.etl$",
    r"\.evtx$",
    r"\\\$recycle\.bin\\",
]

# Registry key substrings considered noise (case-insensitive).
NOISE_REG_PATTERNS = [
    r"\\muicache\\",
    r"\\recentdocs\\",
    r"\\userassist\\",
    r"\\bagmru\\",
    r"\\bags\\",
    r"\\shellnoroam\\",
    r"\\typedurls\\",
    r"\\openwithlist\\",
    r"\\openwithprogids\\",
    r"\\store\\.+\\dcomlaunch",
    r"\\trace\\",
    r"\\appcompatflags\\",
    r"\\notifications\\",
]

_file_re = re.compile("|".join(NOISE_FILE_PATTERNS), re.IGNORECASE)
_reg_re = re.compile("|".join(NOISE_REG_PATTERNS), re.IGNORECASE)


def is_noise_file(path: str) -> bool:
    return bool(_file_re.search(path))


def is_noise_reg(key: str) -> bool:
    return bool(_reg_re.search(key))
