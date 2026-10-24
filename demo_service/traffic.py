"""Steady local requests; failure mode changes server responses, not traffic."""
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

if __name__ == '__main__':
    while True:
        try:
            with urlopen('http://checkout-demo:8081/checkout', timeout=2):
                pass
        except (HTTPError, URLError, TimeoutError):
            pass
        time.sleep(0.35)
