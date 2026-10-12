"""Native ASGI Socket.IO with request contexts for IRIS collaboration handlers."""
import asyncio
import inspect

import socketio
from starlette.concurrency import run_in_threadpool

from .web import current_app, request


Namespace = socketio.AsyncNamespace


class _TransportApp(socketio.ASGIApp):
    def __init__(self, transport):
        self.transport = transport
        super().__init__(transport.server, other_asgi_app=transport.app)

    async def __call__(self, scope, receive, send):
        self.transport.loop = asyncio.get_running_loop()
        await super().__call__(scope, receive, send)


class SocketIO:
    def __init__(self, app, cors_allowed_origins="*"):
        self.app = app
        self.server = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=cors_allowed_origins)
        self.loop = None
        self.asgi_app = _TransportApp(self)
        app.extensions["socketio"] = self

    def on_namespace(self, namespace):
        self.server.register_namespace(namespace)

    def on(self, event, namespace=None):
        selected_namespace = namespace or "/"

        def decorate(handler):
            async def invoke(sid, *args):
                self.loop = asyncio.get_running_loop()
                environ = self.server.get_environ(sid, namespace=selected_namespace)
                if environ is None:
                    return None

                def dispatch():
                    with self.app.request_context(environ):
                        request.sid = sid
                        request.namespace = selected_namespace
                        # New engineio versions provide a disconnect reason. Existing
                        # handlers either accept it or ignore transport-level arguments.
                        expected = inspect.signature(handler).parameters
                        selected_args = args if expected else ()
                        return handler(*selected_args)

                return await run_in_threadpool(dispatch)

            self.server.on(event, handler=invoke, namespace=selected_namespace)
            return handler

        return decorate

    def _submit(self, coroutine):
        # HTTP notifications originate in the same thread pool as socket callbacks.
        # Celery's separate process has no connected clients, matching the original
        # in-process Socket.IO configuration.
        if self.loop is None or not self.loop.is_running():
            coroutine.close()
            return None
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result()

    def emit(self, event, data=None, *, to=None, room=None, skip_sid=None,
             namespace=None, broadcast=False, **kwargs):
        return self._submit(self.server.emit(event, data, to=to or room,
                                             skip_sid=skip_sid, namespace=namespace or "/", **kwargs))

    def enter_room(self, sid, room, namespace=None):
        return self._submit(self.server.enter_room(sid, room, namespace=namespace or "/"))

    def stop(self):
        # The external updater stops/replaces Uvicorn after taking ownership.
        # Finish Socket.IO's background activity before that process handoff.
        return self._submit(self.server.shutdown())


def emit(event, data=None, *, to=None, room=None, skip_sid=None,
         namespace=None, broadcast=False, **kwargs):
    transport = current_app.extensions["socketio"]
    destination = to or room
    if destination is None and not broadcast:
        destination = request.sid
    return transport.emit(event, data, to=destination, skip_sid=skip_sid,
                          namespace=namespace or request.namespace, **kwargs)


def join_room(room, sid=None, namespace=None):
    return current_app.extensions["socketio"].enter_room(sid or request.sid, room,
                                                        namespace=namespace or request.namespace)
