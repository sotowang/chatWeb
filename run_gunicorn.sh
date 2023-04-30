#!/bin/bash

source venv/bin/activate
gunicorn -w 10 -b 0.0.0.0:5000 main:app --timeout 120 >> gunicorn.log 2>&1 &
