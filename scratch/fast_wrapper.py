
import time
import requests
import sys

def fast_sleep(s):
    pass
time.sleep = fast_sleep

with open('tools/fresh_408_validator.py', 'r') as f:
    source = f.read()

exec(source, globals())
