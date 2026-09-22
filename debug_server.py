
import time, threading
from server import BaseHTTPRequestHandler, ThreadingHTTPServer, AerisController, ControllerHandler, TICK_SECONDS, PORT, HOST
def run():
    controller = AerisController()
    def handler_factory(*args, **kwargs):
        ControllerHandler(controller, *args, **kwargs)
    server = ThreadingHTTPServer((HOST, PORT), handler_factory)
    threading.Thread(target=lambda: [controller.tick() or time.sleep(TICK_SECONDS) for _ in iter(int, 1)], daemon=True).start()
    server.serve_forever()
if __name__ == '__main__':
    run()
