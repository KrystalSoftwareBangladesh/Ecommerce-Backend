#!/bin/bash
echo "Host: "
read host

echo "Port:"
read  port

echo "username: "
read username

echo "db_name: "
read dbname

echo "Output file: (optional)"
read output

# If output file name is empty, use current date as the filename
if [ -z "$output" ]; then
    output="backup_$(date +%Y%m%d_%H%M%S).dump"
fi

pg_dump --host $host --port $port --username $username  --format custom --blobs --verbose --file $output $dbname