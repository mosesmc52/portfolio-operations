#!/bin/sh

#echo "Migrating Django Database"
# python manage.py flush --no-input
#python manage.py migrate

#python manage.py collectstatic --no-input


exec "$@"
