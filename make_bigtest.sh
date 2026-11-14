#!/usr/bin/env bash
# Builds a ~4 million row practice table in its own schema.
set -e
MYSQL="docker exec -i sample-mysql mysql -uroot -pchangeme"

$MYSQL -e "DROP DATABASE IF EXISTS bigtest; CREATE DATABASE bigtest;"

$MYSQL bigtest <<'SQL'
CREATE TABLE orders (
  order_id    BIGINT AUTO_INCREMENT PRIMARY KEY,
  customer_id INT NOT NULL,
  status      VARCHAR(10) NOT NULL,
  amount      DECIMAL(10,2) NULL,
  notes       VARCHAR(100) NULL,
  created_at  DATETIME NOT NULL
) ENGINE=InnoDB;

-- seed with 1,000 random rows
INSERT INTO orders (customer_id, status, amount, notes, created_at)
WITH RECURSIVE seq AS (SELECT 1 AS n UNION ALL SELECT n + 1 FROM seq WHERE n < 1000)
SELECT FLOOR(1 + RAND() * 50000),
       ELT(1 + FLOOR(RAND() * 4), 'new', 'paid', 'shipped', 'returned'),
       IF(RAND() < 0.1, NULL, ROUND(RAND() * 500, 2)),
       IF(RAND() < 0.8, NULL, 'gift'),
       NOW() - INTERVAL FLOOR(RAND() * 365) DAY
FROM seq;
SQL

# each pass doubles the table: 1,000 x 2^12 = 4,096,000 rows
for i in $(seq 1 12); do
  $MYSQL bigtest -e "INSERT INTO orders (customer_id, status, amount, notes, created_at)
                     SELECT customer_id, status, amount, notes, created_at FROM orders;"
  echo "doubling $i/12 done"
done