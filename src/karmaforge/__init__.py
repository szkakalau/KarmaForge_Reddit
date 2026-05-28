"""KarmaForge — Reddit Growth Co-pilot for Indie Developers."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("karmaforge")
except PackageNotFoundError:
    __version__ = "3.0.0"
