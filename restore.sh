#!/bin/bash
echo "Host: "
read host

echo "Port:"
read port

echo "username: "
read username

echo "db_name: "
read dbname

echo "Dump file: "
read file

pg_restore --host $host --port $port --username $username --dbname $dbname --verbose $file
