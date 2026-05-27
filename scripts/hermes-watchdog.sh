#!/bin/bash
# ============================================================
# HERMES WATCHDOG — Resurrects dead tasks every 5 minutes
# ============================================================
# Stores task state in ~/.hermes-socrates/watchdog/state.json
# If task is "dead" (no heartbeat for 2 cycles), relaunches it.
# ============================================================

WATCHDOG_DIR="$HOME/.hermes-socrates/watchdog"
STATE_FILE="$WATCHDOG_DIR/state.json"
LOG_FILE="$WATCHDOG_DIR/watchdog.log"
TASK_MARKER="$WATCHDOG_DIR/task.marker"
HERMES_DIR="/home/will/whatsapp-rag"

mkdir -p "$WATCHDOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# ============================================================
# TASK DEFINITION — Edit this to change what gets resurrected
# ============================================================
CURRENT_TASK="reversa-fase0"

load_task() {
    if [ -f "$STATE_FILE" ]; then
        TASK_STATUS=$(cat "$STATE_FILE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','unknown'))" 2>/dev/null)
        TASK_CYCLE=$(cat "$STATE_FILE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('cycle',0))" 2>/dev/null)
        LAST_RUN=$(cat "$STATE_FILE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('last_run',''))" 2>/dev/null)
    else
        TASK_STATUS="pending"
        TASK_CYCLE=0
        LAST_RUN=""
    fi
}

save_state() {
    python3 -c "
import json
state = {
    'task': '$CURRENT_TASK',
    'status': '$1',
    'cycle': $TASK_CYCLE,
    'last_run': '$(date '+%Y-%m-%d %H:%M:%S')',
    'heartbeat': '$(date '+%Y-%m-%d %H:%M:%S')'
}
with open('$STATE_FILE', 'w') as f:
    json.dump(state, f)
"
}

heartbeat() {
    python3 -c "
import json
try:
    with open('$STATE_FILE', 'r') as f:
        state = json.load(f)
    state['heartbeat'] = '$(date '+%Y-%m-%d %H:%M:%S')'
    with open('$STATE_FILE', 'w') as f:
        json.dump(state, f)
except: pass
"
}

is_task_running() {
    # Check if there's a hermes process handling our task
    pgrep -f "hermes" > /dev/null 2>&1 && return 0
    # Check if heartbeat is recent (within 3 minutes)
    if [ -f "$STATE_FILE" ]; then
        LAST_HB=$(cat "$STATE_FILE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('heartbeat',''))" 2>/dev/null)
        if [ -n "$LAST_HB" ]; then
            HB_EPOCH=$(date -d "$LAST_HB" +%s 2>/dev/null || echo 0)
            NOW_EPOCH=$(date +%s)
            DIFF=$((NOW_EPOCH - HB_EPOCH))
            [ $DIFF -lt 180 ] && return 0  # heartbeat < 3 min ago = alive
        fi
    fi
    return 1
}

mark_done() {
    python3 -c "
import json
state = {'task': '$CURRENT_TASK', 'status': 'done', 'completed': '$(date '+%Y-%m-%d %H:%M:%S')'}
with open('$STATE_FILE', 'w') as f:
    json.dump(state, f)
"
    echo "done" > "$TASK_MARKER"
}

# ============================================================
# EXECUTE THE ACTUAL WORK
# ============================================================
do_work() {
    log "WORK: Starting Reversa FASE 0 audit"
    
    cd "$HERMES_DIR" || exit 1
    
    mkdir -p docs/reversa
    
    # Phase 1: Top-level inventory
    {
        echo "# AUDITORIA FASE 0 — $(date '+%Y-%m-%d %H:%M:%S')"
        echo "## Top-level structure"
        ls -la
        echo ""
        echo "## app/ structure"
        find app/ -type f -name "*.py" 2>/dev/null | sort
        echo ""
        echo "## refrimix_core/ structure"
        find refrimix_core/ -type f -name "*.py" 2>/dev/null | sort
        echo ""
        echo "## prisma/ structure"
        find prisma/ -type f 2>/dev/null | sort
        echo ""
        echo "## Legacy debt candidates"
        find . -name "__pycache__" -o -name ".venv" -o -name "node_modules" -o -name "*.pyc" 2>/dev/null | head -20
    } > docs/reversa/auditoria-fase0-20260526.md
    
    # Phase 2: Rules extraction
    {
        echo "# RULES EXTRACTED — $(date '+%Y-%m-%d %H:%M:%S')"
        echo "## Commercial rules found in code"
        grep -r "R\$" --include="*.py" . 2>/dev/null | grep -v "__pycache__" | head -30
        echo ""
        echo "## Intent mapping"
        grep -r "intent\|INTENT\|Intent" --include="*.py" refrimix_core/ 2>/dev/null | head -20
        echo ""
        echo "## Response catalog keys"
        grep -r "response_catalog\|ResponseCatalog\|RESPONSE" --include="*.py" app/ 2>/dev/null | head -20
    } > docs/reversa/rules-extracted.md
    
    # Phase 3: Debt map
    {
        echo "# DEBT MAP — $(date '+%Y-%m-%d %H:%M:%S')"
        echo "## agent_graph/ (legacy LangGraph — verify if still used)"
        ls -la agent_graph/ 2>/dev/null || echo "not found"
        echo ""
        echo "## Old test files that don't reflect current state"
        find . -path "*/test*" -name "*.py" 2>/dev/null | grep -v "__pycache__" | head -20
        echo ""
        echo "## Duplicate or obsolete scripts"
        find scripts/ -name "*.py" 2>/dev/null | head -20
        echo ""
        echo "## Docs that are debt"
        find . -maxdepth 2 -name "*.md" 2>/dev/null | grep -v "^./.git" | sort
    } > docs/reversa/debt-map.md
    
    # Phase 4: Sync if we have changes
    if git status --short docs/reversa/ | grep -q .; then
        git add docs/reversa/
        git commit -m "reversa: fase0 auditoria completa $(date '+%Y%m%d-%H%M%S')"
        git push github 2>&1 | head -5
        log "WORK: Committed Reversa FASE 0 docs"
    fi
    
    mark_done
    log "WORK: FASE 0 COMPLETE"
}

# ============================================================
# MAIN WATCHDOG LOOP
# ============================================================
load_task

log "CHECK: status=$TASK_STATUS cycle=$TASK_CYCLE heartbeat=$LAST_RUN"

# Check if already done
if [ "$TASK_STATUS" = "done" ]; then
    log "ALREADY_DONE: Task completed at $LAST_RUN"
    exit 0
fi

# Check if running
if is_task_running; then
    log "ALIVE: Task runner active, sending heartbeat"
    heartbeat
    exit 0
fi

# Dead or unknown — relaunch
TASK_CYCLE=$((TASK_CYCLE + 1))
log "DEAD/UNKNOWN: Relaunching task (cycle $TASK_CYCLE)"
save_state "running"

do_work

log "CYCLE $TASK_CYCLE COMPLETE"