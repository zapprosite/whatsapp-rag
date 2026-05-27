# Config package — re-export runtime config
from runtime_config import (
    MonitoringConfig,
    RuntimeMode,
    IntentFilter,
    get_runtime_config,
    is_shadow_mode,
    is_assisted_mode,
    is_canary_mode,
    can_auto_reply,
)