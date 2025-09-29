#!/bin/sh
set -e

# Map LOGS_LEVEL to Redis loglevel
lvl=${LOGS_LEVEL_REDIS:-${LOGS_LEVEL:-INFO}}
case "$lvl" in
  DEBUG|debug) rl=debug ;;
  VERBOSE|verbose) rl=verbose ;;
  INFO|info|NOTICE|notice) rl=notice ;;
  WARNING|warning) rl=warning ;;
  ERROR|error|CRITICAL|critical) rl=warning ;;
  *) rl=warning ;;
esac

exec redis-server /usr/local/etc/redis/redis.conf --loglevel "$rl"


