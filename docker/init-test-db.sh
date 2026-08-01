#!/bin/bash
# 컨테이너 최초 생성 시 vivac_test DB를 자동으로 만듭니다.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    SELECT 'CREATE DATABASE vivac_test'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'vivac_test')\gexec
EOSQL
