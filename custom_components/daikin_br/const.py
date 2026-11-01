"""Constants for Daikin smart AC."""

from __future__ import annotations

DOMAIN = "daikin_br"
COMMAND_SUFFIX = "BZ"
# Defined in seconds.
POLL_INTERVAL = 10
# Fan speeds offered by the climate entity and the fan speed select.
FAN_MODES = ["auto", "high", "medium_high", "medium", "low_medium", "low", "quiet"]
