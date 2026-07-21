#!/bin/bash
# Pre-launch bootstrap for agent-deck (Mac/Linux), run automatically via
# agent_config.json's pre_launch_command before every agy session start.
# Creates the venv and builds skills on first run; keeps skills up to date
# on every subsequent run.
#
# Invoked non-interactively (agent-deck captures stdout/stderr, no TTY), so
# this must never block on user input — setup.py's own _prompt() helper
# degrades to an empty answer when AGENT_DECK_NONINTERACTIVE is set below
# (confirmed for real: relying on sys.stdin.isatty() alone was not a
# reliable enough signal on Windows and still hung indefinitely).
set -e
cd "$(dirname "$0")"
export AGENT_DECK_NONINTERACTIVE=1

echo "Checking configuration..."
python3 python/scripts/setup/setup.py config

if [ ! -d "venv" ]; then
    echo "First-time setup (this can take a few minutes)..."
    python3 python/scripts/setup/setup.py init
fi

echo "Updating skills..."
if [ -x "venv/bin/python3" ]; then
    venv/bin/python3 python/scripts/setup/setup.py skills rebuild
else
    python3 python/scripts/setup/setup.py skills rebuild
fi
echo "Ready."
