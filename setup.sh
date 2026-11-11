#!/usr/bin/env bash
set -e
docker rm -f sample-mysql 2>/dev/null || true
docker network create scanner-net 2>/dev/null || true
docker run --name sample-mysql -e MYSQL_ROOT_PASSWORD=changeme \
  --network scanner-net \
  -p 3306:3306 -v mysql-data:/var/lib/mysql -d mysql:8

echo "Waiting for MySQL..."
until docker exec sample-mysql mysqladmin ping -h127.0.0.1 -uroot -pchangeme --silent 2>/dev/null; do
  sleep 2
done

if ! docker exec sample-mysql mysql -uroot -pchangeme -e "USE sakila" 2>/dev/null; then
  [ -d sakila-db ] || { curl -sLO https://downloads.mysql.com/docs/sakila-db.tar.gz && tar -xzf sakila-db.tar.gz; }
  docker exec -i sample-mysql mysql -uroot -pchangeme < sakila-db/sakila-schema.sql
  docker exec -i sample-mysql mysql -uroot -pchangeme < sakila-db/sakila-data.sql
  echo "Sakila loaded."
else
  echo "Sakila already present."
fi